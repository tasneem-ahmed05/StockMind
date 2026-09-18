"""
StockMind - Flask backend
=========================
Serves the same logic from utils.py as JSON, so the plain HTML/CSS/JS
frontend can fetch real numbers instead of hard-coded mock data.

Run:  python app.py   (then open http://127.0.0.1:5000)
"""
import io

import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, render_template, request

from utils import (
    LEAD_TIME_DAYS,
    build_inventory_analysis,
    build_product_time_series,
    build_restock_timing,
    build_risk_reasons,
    create_inventory_context,
    forecast_product_demand,
    get_demand_trend,
    get_featured_catalog,
    get_featured_meta,
    get_monthly_sales,
    get_price_stats,
    get_product_forecast,
    load_data,
    product_risk_from_forecast,
    project_inventory_depletion,
)

app = Flask(__name__)

# TODO: replace with your real n8n webhook URL once it's deployed
N8N_WEBHOOK_URL = "https://tasneemahmedzaki.app.n8n.cloud/webhook/chatbot"

def _clean(records):
    """Replace NaN/Inf with None so jsonify doesn't choke."""
    return [
        {k: (None if (isinstance(v, float) and (np.isnan(v) or np.isinf(v))) else v) for k, v in r.items()}
        for r in records
    ]


# ---------------------------------------------------------------------------
# Pages (HTML)
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/products")
def products_page():
    return render_template("products.html")


@app.route("/product")
def product_page():
    return render_template("product.html")


@app.route("/upload")
def upload_page():
    return render_template("upload.html")


@app.route("/analysis")
def analysis_page():
    """Report page for the CSV most recently analyzed in this browser."""
    return render_template("analysis.html")


@app.route("/chatbot")
def chatbot_page():
    return render_template("chatbot.html")


# ---------------------------------------------------------------------------
# API (JSON)
# ---------------------------------------------------------------------------
@app.route("/api/products")
def api_products():
    """
    Returns only the curated FEATURED_PRODUCTS list (see utils.py), not every
    Store+Product combo in the CSV. This is the showcase used on the
    Products page - the Upload Data page still analyzes the FULL uploaded
    file separately (see /api/upload below), that's unaffected.
    """
    df = load_data()
    inv = build_inventory_analysis(df)
    view = get_featured_catalog(inv)

    # Prepend the app's static URL so <img src="..."> works straight from the API.
    view["image"] = view["image"].apply(lambda p: f"/static/{p}" if p else None)

    # Real signal from the sales history (last 30 days vs the 30 before that),
    # not a hard-coded value - see get_demand_trend() in utils.py.
    view["Trend"] = [
        get_demand_trend(df, row["Store ID"], row["Product ID"]) for _, row in view.iterrows()
    ]

    risk_filter = request.args.get("risk")
    search = request.args.get("search", "")
    if risk_filter and risk_filter != "All":
        view = view[view["Risk Level"] == risk_filter]
    if search:
        view = view[
            view["Product ID"].str.contains(search, case=False, na=False)
            | view["display_name"].str.contains(search, case=False, na=False)
        ]

    return jsonify(_clean(view.to_dict(orient="records")))


@app.route("/api/product/<store_id>/<product_id>")
def api_product_detail(store_id, product_id):
    """
    Everything the Product Analysis page needs, in one call.

    All figures are derived from the real sales history in
    retail_store_inventory.csv plus the SARIMA demand forecast - there are no
    placeholder or invented numbers in this payload.
    """
    df = load_data()
    inv = build_inventory_analysis(df)
    row = inv[(inv["Store ID"] == store_id) & (inv["Product ID"] == product_id)]
    if row.empty:
        return jsonify({"error": "not found"}), 404
    row = row.iloc[0].to_dict()

    meta = get_featured_meta(store_id, product_id)
    image = meta.get("image")

    # Curated category wins over the CSV's randomly-assigned one (see
    # get_featured_catalog in utils.py for why).
    category = meta.get("category", row.get("Category"))
    row["Category"] = category

    ts = build_product_time_series(df, product_id, store_id=store_id)
    forecast = get_product_forecast(df, store_id, product_id, steps=30)
    risk_series = product_risk_from_forecast(forecast)
    high_risk_days = int((risk_series == "High Demand / Stockout Risk").sum())

    history = ts["Units Sold"].iloc[-90:]

    # --- demand: next 30 forecast days vs last 30 actual days -------------
    next_30 = float(forecast.iloc[:30].sum())
    prev_30 = float(ts["Units Sold"].iloc[-30:].sum())
    demand_change_pct = ((next_30 - prev_30) / prev_30 * 100) if prev_30 else None

    # --- forecast bucketed into 4 weeks (bar chart) -----------------------
    weekly_labels, weekly_values = [], []
    for w in range(4):
        chunk = forecast.iloc[w * 7 : (w + 1) * 7]
        if len(chunk):
            weekly_labels.append(f"Week {w + 1}")
            weekly_values.append(round(float(chunk.sum()), 1))

    # --- monthly sales trend ---------------------------------------------
    monthly = get_monthly_sales(df, store_id, product_id, months=6)

    # --- stock depletion projection ---------------------------------------
    projection = project_inventory_depletion(
        inventory_level=row.get("Inventory Level"),
        avg_daily_demand=row.get("Average_Daily_Demand"),
        reorder_point=row.get("Reorder Point"),
        days=30,
        forecast=forecast,
    )

    timing = build_restock_timing(row.get("Days of Inventory"), LEAD_TIME_DAYS)
    reasons = build_risk_reasons(
        row, demand_change_pct, projection["stockout_day"], high_risk_days, LEAD_TIME_DAYS
    )

    # Donut: how the reorder point is made up, and how much of it current
    # stock actually covers.
    stock = float(row.get("Inventory Level") or 0)
    reorder_point = float(row.get("Reorder Point") or 0)

    return jsonify(
        {
            "store_id": store_id,
            "product_id": product_id,
            "display_name": meta.get("display_name", product_id),
            "image": f"/static/{image}" if image else None,
            "category": category,
            "icon": meta.get("icon", "📦"),
            "info": _clean([row])[0],
            "lead_time_days": LEAD_TIME_DAYS,
            "price": get_price_stats(df, store_id, product_id),
            "history": {
                "dates": history.index.strftime("%Y-%m-%d").tolist(),
                "values": [round(float(v), 1) for v in history.values],
            },
            "monthly_sales": {
                "labels": monthly.index.strftime("%b %Y").tolist(),
                "values": [round(float(v), 1) for v in monthly.values],
            },
            "forecast": {
                "dates": forecast.index.strftime("%Y-%m-%d").tolist(),
                "values": [round(float(v), 1) for v in forecast.values],
            },
            "forecast_weekly": {"labels": weekly_labels, "values": weekly_values},
            "projection": projection,
            "coverage": {
                "on_hand": round(min(stock, reorder_point), 1),
                "shortfall": round(max(0.0, reorder_point - stock), 1),
                "surplus": round(max(0.0, stock - reorder_point), 1),
                "reorder_point": round(reorder_point, 1),
                "lead_time_demand": round(float(row.get("Lead Time Demand") or 0), 1),
                "safety_stock": round(float(row.get("Safety Stock") or 0), 1),
            },
            "demand_summary": {
                "next_30": round(next_30, 1),
                "prev_30": round(prev_30, 1),
                "change_pct": round(demand_change_pct, 1) if demand_change_pct is not None else None,
            },
            "risk_breakdown": {
                k: int(v) for k, v in risk_series.value_counts().to_dict().items()
            },
            "high_risk_days": high_risk_days,
            "timing": timing,
            "reasons": reasons,
        }
    )


@app.route("/api/upload", methods=["POST"])
def api_upload():
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "no file uploaded"}), 400

    if not file.filename or not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please upload a CSV file."}), 400

    try:
        raw = pd.read_csv(io.BytesIO(file.read()))
        required = {"Date", "Store ID", "Product ID", "Category", "Inventory Level", "Units Sold"}
        missing = sorted(required.difference(raw.columns))
        if missing:
            return jsonify({"error": f"Missing required columns: {', '.join(missing)}"}), 400
        raw["Date"] = pd.to_datetime(raw["Date"], errors="coerce")
        if raw["Date"].isna().any():
            return jsonify({"error": "The Date column contains invalid values."}), 400
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        return jsonify({"error": f"We couldn't read that CSV: {exc}"}), 400

    inv = build_inventory_analysis(raw)

    risk_counts = inv["Risk Level"].value_counts().to_dict()
    inv["Stockout Probability"] = (
        ((inv["Reorder Point"] - inv["Inventory Level"]) / inv["Reorder Point"].replace(0, np.nan))
        .clip(lower=0, upper=1).fillna(0).mul(100).round()
    )
    risk_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Unknown": 4}
    inv["_risk_order"] = inv["Risk Level"].map(risk_order).fillna(5)
    top_risk = (
        inv.sort_values(["_risk_order", "Stockout Probability", "Recommended Order"], ascending=[True, False, False]).head(5)
    )
    category_risk = (
        inv.assign(_at_risk=inv["Risk Level"].isin(["Critical", "High"]))
        .groupby("Category")["_at_risk"].sum().sort_values(ascending=False)
    )
    # Supporting datasets for the report tabs.  They are calculated from the
    # uploaded file, rather than from the app's bundled demo dataset.
    monthly_sales = raw.groupby(raw["Date"].dt.to_period("M"))["Units Sold"].sum().tail(12)
    latest_day = raw[raw["Date"] == raw["Date"].max()]
    forecast_source = "Demand Forecast" if "Demand Forecast" in raw.columns else "Units Sold"
    forecast_daily = float(latest_day[forecast_source].sum())
    sales_last_30 = float(raw[raw["Date"] > raw["Date"].max() - pd.Timedelta(days=30)]["Units Sold"].sum())
    forecast_30 = forecast_daily * 30
    forecast_change = ((forecast_30 - sales_last_30) / sales_last_30 * 100) if sales_last_30 else 0.0
    inventory_rows = inv.sort_values("Inventory Level").head(10)
    recommendation_rows = inv[inv["Recommendation"] == "REORDER"].sort_values("Recommended Order", ascending=False).head(10)

    return jsonify(
        {
            # Each row is a distinct inventory item at a store, matching the
            # risk distribution and the products ranked in this report.
            "total_products": int(len(inv)),
            "total_records": int(len(raw)),
            "date_range": [str(raw["Date"].min().date()), str(raw["Date"].max().date())],
            "risk_distribution": risk_counts,
            "top_risk_products": _clean(top_risk.to_dict(orient="records")),
            "historical_sales": {
                "labels": [str(period) for period in monthly_sales.index],
                "values": [round(float(value), 0) for value in monthly_sales.values],
            },
            "inventory": {
                "total_on_hand": int(inv["Inventory Level"].sum()),
                "total_reorder_point": round(float(inv["Reorder Point"].sum()), 0),
                "items": _clean(inventory_rows[["Store ID", "Product ID", "Category", "Inventory Level", "Days of Inventory", "Risk Level"]].to_dict(orient="records")),
            },
            "forecast": {
                "daily_demand": round(forecast_daily, 0),
                "next_30_demand": round(forecast_30, 0),
                "previous_30_sales": round(sales_last_30, 0),
                "change_pct": round(forecast_change, 1),
            },
            "recommendations": {
                "total_order_quantity": round(float(recommendation_rows["Recommended Order"].sum()), 0),
                "items": _clean(recommendation_rows[["Store ID", "Product ID", "Category", "Risk Level", "Inventory Level", "Recommended Order"]].to_dict(orient="records")),
            },
            "insights": {
                "high_risk_count": int(inv["Risk Level"].isin(["Critical", "High"]).sum()),
                "highest_risk_category": str(category_risk.index[0]) if len(category_risk) else None,
                "reorder_count": int((inv["Recommendation"] == "REORDER").sum()),
            },
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.get_json(force=True)
    question = payload.get("question", "")
    product_id = payload.get("product_id")
    store_id = payload.get("store_id")

    df = load_data()
    inv = build_inventory_analysis(df)
    if product_id:
        context = create_inventory_context(inv, store_id=store_id, product_id=product_id)
    else:
        context = ""

    try:
        resp = requests.post(N8N_WEBHOOK_URL, json={"question": question, "context": context}, timeout=30)
        answer = resp.json().get("answer", "Sorry, I couldn't process that.")
    except Exception as e:
        answer = f"Chatbot service not reachable yet ({e}). Set N8N_WEBHOOK_URL in app.py."

    return jsonify({"answer": answer})


if __name__ == "__main__":
    app.run(debug=True)
