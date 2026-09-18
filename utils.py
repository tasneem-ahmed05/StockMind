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
