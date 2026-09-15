"""
StockMind - shared logic
=========================
This module takes every piece of logic that was scattered across the
notebook cells (per-store/product risk table, the reorder-point
recommendation, and the single-product SARIMA forecast) and turns it
into plain reusable functions.

Every Streamlit page imports from here instead of re-writing the same
pandas code, so there is exactly ONE place to fix a bug or tweak a
threshold.
"""

import math

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config - tweak these in one place
# ---------------------------------------------------------------------------
DATA_PATH = "retail_store_inventory.csv"
LEAD_TIME_DAYS = 7
SAFETY_FACTOR = 0.20

# simple in-memory caches (Flask has no built-in st.cache_data/cache_resource)
_data_cache: dict = {}
_sarima_cache: dict = {}

# ---------------------------------------------------------------------------
# Featured products - the ONLY (Store, Product) pairs shown on the Products
# page / used for the product showcase, instead of every combo in the CSV.
#
# Edit this list to change which products appear:
# - store_id / product_id MUST match values that exist in retail_store_inventory.csv
# - display_name: whatever you want shown instead of the raw Product ID
# - image: path to a photo under static/images/ (put the file there and it
#   will show up automatically). Leave as None to fall back to a category icon.
# ---------------------------------------------------------------------------
FEATURED_PRODUCTS = [
    {"store_id": "S001", "product_id": "P0006", "display_name": "Laptop Pro 15", "category": "Electronics", "image": "images/products/laptop-pro-15.jpg"},
    {"store_id": "S001", "product_id": "P0011", "display_name": "Wireless Headphones", "category": "Electronics", "image": "images/products/wireless-headphones.jpg"},
    {"store_id": "S001", "product_id": "P0007", "display_name": "Running Shoes", "category": "Clothing", "image": "images/products/running-shoes.jpg"},
    {"store_id": "S001", "product_id": "P0002", "display_name": "Office Chair", "category": "Furniture", "image": "images/products/office-chair.jpg"},
    {"store_id": "S001", "product_id": "P0004", "display_name": "Snack Pack", "category": "Groceries", "image": "images/products/snack-pack.jpg"},
    {"store_id": "S002", "product_id": "P0010", "display_name": "Building Blocks Set", "category": "Toys", "image": "images/products/building-blocks.jpg"},
]

CATEGORY_ICONS = {
    "Electronics": "💻",
    "Clothing": "👟",
    "Furniture": "🪑",
    "Groceries": "🥫",
    "Toys": "🧸",
}


def get_featured_catalog(inventory_analysis: pd.DataFrame) -> pd.DataFrame:
    """
    Slice of the full inventory analysis restricted to FEATURED_PRODUCTS,
    with display_name / image / icon attached. This is what the Products
    page renders — a curated showcase, not the whole dataset.
    """
    featured_df = pd.DataFrame(FEATURED_PRODUCTS).rename(
        columns={"store_id": "Store ID", "product_id": "Product ID"}
    )
    merged = featured_df.merge(inventory_analysis, on=["Store ID", "Product ID"], how="left")

    # The raw CSV assigns a *random* Category to every row, so the "Category"
    # coming out of the analysis is just whichever value the last row happened
    # to get - it is not a real property of the product. The curated category
    # in FEATURED_PRODUCTS is the source of truth for anything user-facing.
    merged["Category"] = merged["category"]
    merged = merged.drop(columns="category")

    merged["icon"] = merged["Category"].map(CATEGORY_ICONS).fillna("📦")
    # keep the curated order from FEATURED_PRODUCTS rather than whatever merge/sort gives us
    merged["_order"] = range(len(merged))
    return merged.sort_values("_order").drop(columns="_order")


def get_featured_meta(store_id: str, product_id: str) -> dict:
    """display_name / category / image / icon for one featured product, used by the detail page."""
    for p in FEATURED_PRODUCTS:
        if p["store_id"] == store_id and p["product_id"] == product_id:
            meta = dict(p)
            meta["icon"] = CATEGORY_ICONS.get(meta.get("category"), "📦")
            return meta
    return {"display_name": product_id, "category": None, "image": None, "icon": "📦"}


def get_demand_trend(df: pd.DataFrame, store_id: str, product_id: str, window: int = 30) -> str:
    """
    'up' / 'down' / 'flat' - compares average daily Units Sold in the most
    recent `window` days of real sales history against the `window` days
    before that, for one (store, product). Powers the Demand Trend arrow
    on the Products page - this is a genuine signal from the sales data,
    not a placeholder.
    """
    mask = (df["Store ID"] == store_id) & (df["Product ID"] == product_id)
    series = df[mask].sort_values("Date")["Units Sold"]
    if len(series) < window * 2:
        window = max(1, len(series) // 2)
    if window == 0:
        return "flat"

    recent = series.tail(window).mean()
    previous = series.iloc[-window * 2 : -window].mean() if len(series) >= window * 2 else series.head(window).mean()

    if pd.isna(recent) or pd.isna(previous) or previous == 0:
        return "flat"

    change = (recent - previous) / previous
    if change > 0.05:
        return "up"
    elif change < -0.05:
        return "down"
    return "flat"


# ---------------------------------------------------------------------------
# 1) Data loading
# ---------------------------------------------------------------------------
def load_data(path: str = DATA_PATH) -> pd.DataFrame:
    """Load and lightly clean the raw dataset (Task 1-2 from the notebook)."""
    if path in _data_cache:
        return _data_cache[path]
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    _data_cache[path] = df
    return df


# ---------------------------------------------------------------------------
# 2) Fast, scalable per Store+Product analysis
#    -> powers the "Products" catalog page and the "Upload Data" page
# ---------------------------------------------------------------------------
def classify_risk(days: float) -> str:
    """Same thresholds as the notebook's classify_risk()."""
    if pd.isna(days):
        return "Unknown"
    elif days < 3:
        return "Critical"
    elif days < 7:
        return "High"
    elif days < 14:
        return "Medium"
    else:
        return "Low"


def compute_stockout_probability(
    mean_daily_demand: float, std_daily_demand: float, current_stock: float, lead_time: int = LEAD_TIME_DAYS
) -> float:
    """
    P(total demand during the supplier lead time > current stock), using the
    normal approximation behind classic safety-stock / service-level
    calculations:

        demand over the lead time ~ Normal(mean_daily * lead_time,
                                            std_daily * sqrt(lead_time))

    This is a real statistic derived from each product's own daily sales
    variability (not a flat/made-up percentage) - a product with the same
    average demand but spikier sales gets a higher probability.
    """
    if mean_daily_demand is None or pd.isna(mean_daily_demand) or mean_daily_demand <= 0:
        return 0.0

    mu = mean_daily_demand * lead_time
    std = 0.0 if (std_daily_demand is None or pd.isna(std_daily_demand)) else float(std_daily_demand)
    sigma = std * math.sqrt(lead_time)

    if sigma <= 0:
        return 100.0 if current_stock < mu else 0.0

    z = (current_stock - mu) / sigma
    prob = 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))  # P(X > current_stock)
    return round(float(np.clip(prob * 100, 0, 100)), 1)


def build_inventory_analysis(
    df: pd.DataFrame,
    lead_time: int = LEAD_TIME_DAYS,
    safety_factor: float = SAFETY_FACTOR,
) -> pd.DataFrame:
    """
    One row per (Store, Product) with: current inventory, average daily
    demand, days of inventory left, risk level, reorder point and the
    recommended order quantity.

    This is the table that feeds the Products catalog, the risk
    distribution chart, and "Top products by risk".
    """
    latest_inventory = (
        df.sort_values("Date")
        .groupby(["Store ID", "Product ID"])
        .tail(1)[["Store ID", "Product ID", "Category", "Inventory Level"]]
        .reset_index(drop=True)
    )

    product_demand = (
        df.groupby(["Store ID", "Product ID"])
        .agg(
            Average_Daily_Demand=("Units Sold", "mean"),
            Std_Daily_Demand=("Units Sold", "std"),
            Total_Demand=("Units Sold", "sum"),
        )
        .reset_index()
    )

    inv = latest_inventory.merge(product_demand, on=["Store ID", "Product ID"], how="left")

    inv["Days of Inventory"] = (
        inv["Inventory Level"] / inv["Average_Daily_Demand"].replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)

    inv["Risk Level"] = inv["Days of Inventory"].apply(classify_risk)

    inv["Lead Time Demand"] = inv["Average_Daily_Demand"] * lead_time
    inv["Safety Stock"] = inv["Lead Time Demand"] * safety_factor
    inv["Reorder Point"] = inv["Lead Time Demand"] + inv["Safety Stock"]
    inv["Recommended Order"] = (inv["Reorder Point"] - inv["Inventory Level"]).clip(lower=0)
    inv["Recommendation"] = np.where(
        inv["Inventory Level"] <= inv["Reorder Point"], "REORDER", "NO REORDER"
    )
    inv["Stockout_Probability_Pct"] = [
        compute_stockout_probability(m, s, stock, lead_time)
        for m, s, stock in zip(inv["Average_Daily_Demand"], inv["Std_Daily_Demand"], inv["Inventory Level"])
    ]
    return inv


def get_inventory_context(
    inventory_analysis: pd.DataFrame, store_id: str | None = None, product_id: str | None = None
) -> pd.DataFrame:
    """Filtered slice of the analysis table - used to feed the chatbot."""
    data = inventory_analysis.copy()
    if store_id is not None:
        data = data[data["Store ID"] == store_id]
    if product_id is not None:
        data = data[data["Product ID"] == product_id]
    return data[
        [
            "Store ID",
            "Product ID",
            "Category",
            "Inventory Level",
            "Average_Daily_Demand",
            "Days of Inventory",
            "Risk Level",
            "Reorder Point",
            "Recommended Order",
            "Recommendation",
        ]
    ]


def create_inventory_context(
    inventory_analysis: pd.DataFrame, store_id: str | None = None, product_id: str | None = None
) -> str:
    """Plain-text context string - this is what gets sent to n8n/the LLM for RAG."""
    data = get_inventory_context(inventory_analysis, store_id, product_id)
    return data.to_string(index=False)


# ---------------------------------------------------------------------------
# 3) Deep per-product time-series forecast (SARIMA)
#    -> powers the "Product Analysis" detail page
# ---------------------------------------------------------------------------
def build_product_time_series(df: pd.DataFrame, product_id: str, store_id: str | None = None) -> pd.DataFrame:
    """
    Daily demand series for a single product, resampled to every day.

    If store_id is given, the series is filtered to that store only, so it
    stays consistent with the per-Store+Product KPIs shown on the same page
    (Avg Daily Demand, Reorder Point, ...). Without it, demand would be
    summed across every store carrying the product, which is a different
    (much larger) number than the single-store KPIs.
    """
    mask = df["Product ID"] == product_id
    if store_id is not None:
        mask &= df["Store ID"] == store_id

    series = (
        df[mask]
        .groupby("Date")["Units Sold"]
        .sum()
        .reset_index()
    )
    ts = series.set_index("Date").sort_index().asfreq("D")
    ts["Units Sold"] = ts["Units Sold"].fillna(0)
    return ts


def fit_sarima(ts: pd.DataFrame, cache_key: str, order=(2, 0, 2), seasonal_order=(1, 1, 1, 7)):
    """Fit SARIMA once per (store, product) and cache the fitted model object in memory."""
    if cache_key in _sarima_cache:
        return _sarima_cache[cache_key]

    from statsmodels.tsa.statespace.sarimax import SARIMAX

    model = SARIMAX(
        ts["Units Sold"],
        order=order,
        seasonal_order=seasonal_order,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False, maxiter=200, method="powell")
    _sarima_cache[cache_key] = fit
    return fit


def forecast_product_demand(ts: pd.DataFrame, cache_key: str, steps: int = 30) -> pd.Series:
    """30-day-ahead forecast for one (store, product)'s demand (Task 10)."""
    fit = fit_sarima(ts, cache_key)
    forecast = fit.forecast(steps=steps)
    future_dates = pd.date_range(start=ts.index[-1] + pd.Timedelta(days=1), periods=steps, freq="D")
    forecast.index = future_dates
    forecast.name = "Forecasted_Demand"
    return forecast


def product_risk_from_forecast(forecast: pd.Series) -> pd.Series:
    """Per-day risk label for the forecast window (Task 11, single-product version)."""
    avg = forecast.mean()
    std = forecast.std()
    return pd.Series(
        np.where(
            forecast > (avg + std),
            "High Demand / Stockout Risk",
            np.where(forecast < (avg - std), "Low Demand / Overstock Risk", "Normal Risk"),
        ),
        index=forecast.index,
        name="Risk_Level",
    )


# ---------------------------------------------------------------------------
# 4) Precomputed forecasts (exported once from Colab) - preferred path
# ---------------------------------------------------------------------------
FORECASTS_PATH = "forecasts.csv"
_forecasts_cache: dict = {}


def load_precomputed_forecasts(path: str = FORECASTS_PATH):
    """
    Load the forecasts.csv exported from Colab (see export_forecasts_colab_cell.py).
    Returns None if the file isn't there yet, so callers can fall back to
    fitting SARIMA live for that one product instead of crashing.
    """
    if path in _forecasts_cache:
        return _forecasts_cache[path]
    try:
        fc = pd.read_csv(path)
        fc["Date"] = pd.to_datetime(fc["Date"])
    except FileNotFoundError:
        fc = None
    _forecasts_cache[path] = fc
    return fc


def get_product_forecast(df: pd.DataFrame, store_id: str, product_id: str, steps: int = 30) -> pd.Series:
    """
    Preferred entry point for a page/endpoint that needs a product's forecast:
    uses the precomputed table if available (fast, matches the notebook's
    trained model), and only fits SARIMA live as a fallback (e.g. for a
    product that wasn't in the export, or during local development).

    A precomputed row is only trusted if it actually starts AFTER the last
    day of real history. An export produced from a train/test split forecasts
    a window that has already happened, which is a backtest, not a forecast -
    plotting it next to the full history draws a chart that jumps backwards
    in time. When that is detected we ignore the file and fit live instead.
    """
    history_end = df[(df["Store ID"] == store_id) & (df["Product ID"] == product_id)]["Date"].max()

    precomputed = load_precomputed_forecasts()
    if precomputed is not None:
        rows = precomputed[
            (precomputed["Store ID"] == store_id) & (precomputed["Product ID"] == product_id)
        ].sort_values("Date")
        if not rows.empty and (pd.isna(history_end) or rows["Date"].min() > history_end):
            return rows.set_index("Date")["Forecasted_Demand"].iloc[:steps]

    # Fallback: fit live (slower, and not persisted across restarts)
    ts = build_product_time_series(df, product_id, store_id=store_id)
    return forecast_product_demand(ts, cache_key=f"{store_id}_{product_id}", steps=steps)


# ---------------------------------------------------------------------------
# 5) Product Analysis page helpers
#    Everything below feeds /api/product/<store>/<product>, i.e. the page you
#    land on after clicking "Analyze". All of it is derived from the real
#    sales history + the SARIMA forecast - no invented numbers.
# ---------------------------------------------------------------------------
def get_monthly_sales(df: pd.DataFrame, store_id: str, product_id: str, months: int = 6) -> pd.Series:
    """
    Total Units Sold per calendar month for one (store, product), last `months`
    complete months. Powers the "Sales Trend" chart.

    Partial months are dropped: the CSV ends on the 1st of a month, so keeping
    it would draw a cliff down to a single day's sales and read as a demand
    collapse that never happened.
    """
    mask = (df["Store ID"] == store_id) & (df["Product ID"] == product_id)
    sub = df[mask].set_index("Date")["Units Sold"]
    if sub.empty:
        return sub

    totals = sub.resample("ME").sum()
    day_counts = sub.resample("ME").count()
    # a month needs most of its days present to be trustworthy
    totals = totals[day_counts >= 20]
    return totals.tail(months)


def get_price_stats(df: pd.DataFrame, store_id: str, product_id: str) -> dict:
    """
    Price summary for one (store, product).

    NOTE: in this dataset Price is re-rolled on every row, so a single "current
    price" is meaningless. We report the average over the whole history plus
    the observed range, which is the honest version of that column.
    """
    mask = (df["Store ID"] == store_id) & (df["Product ID"] == product_id)
    prices = df[mask]["Price"].dropna()
    if prices.empty:
        return {"avg": None, "min": None, "max": None}
    return {
        "avg": round(float(prices.mean()), 2),
        "min": round(float(prices.min()), 2),
        "max": round(float(prices.max()), 2),
    }


def project_inventory_depletion(
    inventory_level: float,
    avg_daily_demand: float,
    reorder_point: float,
    days: int = 30,
    forecast: pd.Series | None = None,
) -> dict:
    """
    Day-by-day projection of remaining stock if nothing is reordered.

    Uses the SARIMA forecast for daily demand when available (so the curve
    bends with predicted demand) and falls back to flat average daily demand.
    Returns the curve plus the day the stock is projected to run out and the
    day it crosses the reorder point.
    """
    if forecast is not None and len(forecast) > 0:
        daily = [max(0.0, float(v)) for v in forecast.values[:days]]
        while len(daily) < days:
            daily.append(float(avg_daily_demand or 0))
    else:
        daily = [float(avg_daily_demand or 0)] * days

    remaining = float(inventory_level or 0)
    curve, stockout_day, reorder_day = [], None, None

    for i, demand in enumerate(daily, start=1):
        remaining = max(0.0, remaining - demand)
        curve.append(round(remaining, 1))
        if reorder_day is None and remaining <= reorder_point:
            reorder_day = i
        if stockout_day is None and remaining <= 0:
            stockout_day = i

    return {
        "days": list(range(1, days + 1)),
        "values": curve,
        "stockout_day": stockout_day,
        "reorder_day": reorder_day,
    }


def build_restock_timing(days_of_inventory: float, lead_time: int = LEAD_TIME_DAYS) -> dict:
    """
    Turns "days of stock left" + supplier lead time into a plain-language
    restock window. If stock runs out sooner than the supplier can deliver,
    the order is already overdue.
    """
    if pd.isna(days_of_inventory):
        return {"label": "Unknown", "detail": "Not enough demand history"}

    slack = days_of_inventory - lead_time
    if slack <= 0:
        return {
            "label": "Order now",
            "detail": f"Stock lasts ~{days_of_inventory:.0f}d but lead time is {lead_time}d",
        }
    if slack <= 3:
        return {"label": "Within 3 days", "detail": f"Only ~{slack:.0f}d of slack before lead time"}
    if slack <= 7:
        return {"label": "This week", "detail": f"~{slack:.0f}d of slack before lead time"}
    if slack <= 21:
        return {"label": f"In {int(slack // 7)}-{int(slack // 7) + 1} weeks", "detail": f"~{slack:.0f}d of slack"}
    return {"label": "Not urgent", "detail": f"~{days_of_inventory:.0f}d of stock on hand"}


def build_risk_reasons(
    info: dict,
    demand_change_pct: float | None,
    stockout_day: int | None,
    high_risk_days: int,
    lead_time: int = LEAD_TIME_DAYS,
) -> list[str]:
    """
    The "Why this risk?" bullets. Each line is generated from a real computed
    value so the explanation always matches the numbers shown on the page.
    """
    reasons = []
    days_left = info.get("Days of Inventory")
    stock = info.get("Inventory Level")
    reorder_point = info.get("Reorder Point")
    stockout_prob = info.get("Stockout_Probability_Pct")

    if days_left is not None and not pd.isna(days_left):
        reasons.append(
            f"Current stock covers about {days_left:.1f} days of average demand, "
            f"against a {lead_time}-day supplier lead time."
        )

    if stock is not None and reorder_point is not None and not pd.isna(reorder_point):
        if stock <= reorder_point:
            reasons.append(
                f"Stock ({stock:,.0f} units) is below the reorder point "
                f"({reorder_point:,.0f} units), which already triggers a restock."
            )
        else:
            reasons.append(
                f"Stock ({stock:,.0f} units) is still above the reorder point "
                f"({reorder_point:,.0f} units)."
            )

    if stockout_prob is not None and not pd.isna(stockout_prob) and stockout_prob > 0:
        reasons.append(
            f"Based on how much daily sales vary, there's roughly a {stockout_prob:.0f}% "
            f"chance of running out before the next delivery arrives."
        )

    if demand_change_pct is not None:
        direction = "rising" if demand_change_pct > 0 else "falling"
        reasons.append(
            f"Forecast demand for the next 30 days is {direction} "
            f"{abs(demand_change_pct):.0f}% versus the last 30 days of actual sales."
        )

    if stockout_day is not None:
        reasons.append(
            f"At the forecast demand rate, stock is projected to run out around day {stockout_day}."
        )

    if high_risk_days:
        reasons.append(
            f"{high_risk_days} of the next 30 forecast days fall in the high-demand / "
            "stockout-risk band."
        )

    return reasons


# ---------------------------------------------------------------------------
# 6) Upload Data page helpers
#    Powers /api/upload and /api/uploaded/<id>/* - a user's own CSV, analyzed
#    with the exact same functions as the demo dataset (classify_risk,
#    build_inventory_analysis, the reorder-point formula, SARIMA forecast).
#    Nothing here is a separate/simplified code path.
# ---------------------------------------------------------------------------
REQUIRED_UPLOAD_COLUMNS = ["Date", "Store ID", "Product ID", "Category", "Inventory Level", "Units Sold"]
OPTIONAL_UPLOAD_COLUMNS = [
    "Price", "Units Ordered", "Demand Forecast", "Discount", "Region",
    "Weather Condition", "Holiday/Promotion", "Competitor Pricing", "Seasonality",
]
OPTIONAL_NUMERIC_COLUMNS = ["Price", "Units Ordered", "Demand Forecast", "Discount", "Competitor Pricing"]
MAX_UPLOAD_ROWS = 500_000


def validate_and_prepare_upload(raw: pd.DataFrame) -> tuple[pd.DataFrame | None, list[str]]:
    """
    Checks an uploaded CSV against the schema every other part of the app
    assumes, and coerces types. Returns (None, [fatal errors]) if the file
    can't be analyzed at all, or (cleaned_df, [warnings]) if it's usable
    (warnings are informational, e.g. "N rows were skipped").
    """
    errors: list[str] = []

    missing = [c for c in REQUIRED_UPLOAD_COLUMNS if c not in raw.columns]
    if missing:
        return None, [
            f"Missing required column(s): {', '.join(missing)}. "
            f"Expected at least: {', '.join(REQUIRED_UPLOAD_COLUMNS)}."
        ]

    if len(raw) == 0:
        return None, ["The file has no rows."]
    if len(raw) > MAX_UPLOAD_ROWS:
        return None, [f"File has {len(raw):,} rows, which is over the {MAX_UPLOAD_ROWS:,} row limit."]

    df = raw.copy()

    try:
        df["Date"] = pd.to_datetime(df["Date"])
    except Exception:
        return None, ["Couldn't parse the 'Date' column - check the date format (e.g. 2024-01-31)."]

    df["Store ID"] = df["Store ID"].astype(str)
    df["Product ID"] = df["Product ID"].astype(str)
    df["Category"] = df["Category"].astype(str)

    for col in ["Inventory Level", "Units Sold"] + [c for c in OPTIONAL_NUMERIC_COLUMNS if c in df.columns]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    before = len(df)
    df = df.dropna(subset=["Date", "Store ID", "Product ID", "Inventory Level", "Units Sold"])
    dropped = before - len(df)
    if dropped:
        errors.append(f"{dropped:,} row(s) were skipped for missing or invalid values in required columns.")

    if df.empty:
        return None, ["No valid rows left after cleaning - check that the required columns are filled in."]

    for col in OPTIONAL_UPLOAD_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    df = df.sort_values("Date").reset_index(drop=True)
    return df, errors


def build_aggregate_daily_series(df: pd.DataFrame) -> pd.Series:
    """Total Units Sold per calendar day, summed across every store + product."""
    series = df.groupby("Date")["Units Sold"].sum().sort_index()
    return series.asfreq("D").fillna(0)


def get_aggregate_monthly_sales(df: pd.DataFrame, months: int = 6) -> pd.Series:
    """
    Same "complete months only" logic as get_monthly_sales(), but summed
    across the whole uploaded file instead of one product.
    """
    daily = build_aggregate_daily_series(df)
    totals = daily.resample("ME").sum()
    day_counts = daily.resample("ME").count()
    totals = totals[day_counts >= 20]
    return totals.tail(months)


def sales_by_category(df: pd.DataFrame, top: int = 8) -> pd.Series:
    """Total Units Sold grouped by the Category values present in the file, largest first."""
    return df.groupby("Category")["Units Sold"].sum().sort_values(ascending=False).head(top)


def restock_by_category(inv: pd.DataFrame, top: int = 8) -> pd.Series:
    """Total recommended restock units grouped by Category, largest first."""
    return inv.groupby("Category")["Recommended Order"].sum().sort_values(ascending=False).head(top)


def inventory_health_counts(inv: pd.DataFrame) -> dict:
    """How many (store, product) rows need a restock right now vs are fine."""
    counts = inv["Recommendation"].value_counts().to_dict()
    return {"needs_restock": int(counts.get("REORDER", 0)), "healthy": int(counts.get("NO REORDER", 0))}


def risk_bucket_counts(inv: pd.DataFrame) -> dict:
    """
    Full 4-level Risk Level counts (Critical/High/Medium/Low/Unknown), plus a
    collapsed 3-bucket view (Critical folded into High) for the Overview
    donut, which only has room for High/Medium/Low.
    """
    full = inv["Risk Level"].value_counts().to_dict()
    collapsed = {
        "High Risk": full.get("Critical", 0) + full.get("High", 0),
        "Medium Risk": full.get("Medium", 0),
        "Low Risk": full.get("Low", 0),
    }
    return {"full": {k: int(v) for k, v in full.items()}, "collapsed": {k: int(v) for k, v in collapsed.items()}}


def build_key_insights(inv: pd.DataFrame, demand_change_pct: float | None) -> list[str]:
    """
    Plain-language takeaways for the Overview tab. Every sentence is derived
    from `inv` (the same build_inventory_analysis table used everywhere
    else) - nothing here is templated filler.
    """
    insights = []
    total = len(inv)
    at_risk = int(inv["Risk Level"].isin(["Critical", "High"]).sum())
    if total:
        pct = round(at_risk / total * 100)
        insights.append(f"Overall stockout risk is {pct}% ({at_risk} of {total} products at Critical or High risk).")

    risky = inv[inv["Risk Level"].isin(["Critical", "High"])]
    if not risky.empty:
        top_cat = risky["Category"].value_counts().idxmax()
        insights.append(f"'{top_cat}' has the most products at Critical or High risk.")

    if demand_change_pct is not None:
        direction = "increase" if demand_change_pct > 0 else "decrease"
        insights.append(
            f"Total demand is projected to {direction} by {abs(demand_change_pct):.0f}% "
            "over the next 30 days versus the last 30 days of actual sales."
        )

    top_restock = inv[inv["Recommendation"] == "REORDER"].sort_values("Recommended Order", ascending=False).head(2)
    if not top_restock.empty:
        names = [f"{r['Product ID']} ({r['Store ID']})" for _, r in top_restock.iterrows()]
        insights.append(f"Consider restocking {', '.join(names)} first — they need the largest orders.")

    return insights
