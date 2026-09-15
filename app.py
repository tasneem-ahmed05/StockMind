"""
StockMind - Flask backend
=========================
Serves the same logic from utils.py as JSON, so the plain HTML/CSS/JS
frontend can fetch real numbers instead of hard-coded mock data.

Run:  python app.py   (then open http://127.0.0.1:5000)
"""
import io
import os
import uuid

import numpy as np
import pandas as pd
import requests
from flask import Flask, abort, jsonify, render_template, request, send_file

from utils import (
    LEAD_TIME_DAYS,
    build_aggregate_daily_series,
    build_inventory_analysis,
    build_key_insights,
    build_product_time_series,
    build_restock_timing,
    build_risk_reasons,
    create_inventory_context,
    forecast_product_demand,
    get_aggregate_monthly_sales,
    get_demand_trend,
    get_featured_catalog,
    get_featured_meta,
    get_monthly_sales,
    get_price_stats,
    get_product_forecast,
    inventory_health_counts,
    load_data,
    product_risk_from_forecast,
    project_inventory_depletion,
    restock_by_category,
    risk_bucket_counts,
    sales_by_category,
    validate_and_prepare_upload,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB, matches the "Supported format" note on the Upload page

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# TODO: replace with your real n8n webhook URL once it's deployed
N8N_WEBHOOK_URL = "https://tasneemahmedzaki.app.n8n.cloud/webhook/chatbot"

@app.errorhandler(413)
def _file_too_large(_e):
    return jsonify({"error": "File is larger than the 10MB limit."}), 413


def _upload_path(upload_id: str) -> str:
    """uuid4-hex only, so this can never be a path outside UPLOAD_DIR."""
    if not upload_id or not all(c in "0123456789abcdef" for c in upload_id):
        abort(404)
    return os.path.join(UPLOAD_DIR, f"{upload_id}.csv")


def _save_upload(df: pd.DataFrame) -> str:
    upload_id = uuid.uuid4().hex
    df.to_csv(_upload_path(upload_id), index=False)
    return upload_id


def _load_upload(upload_id: str) -> pd.DataFrame:
    path = _upload_path(upload_id)
    if not os.path.exists(path):
        abort(404, description="Upload not found - it may have been removed, please upload the file again.")
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


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


def _build_overview_payload(df: pd.DataFrame, upload_id: str, filename: str, warnings: list[str]) -> dict:
    """
    Shared by POST /api/upload (right after a file is analyzed) and
    GET /api/uploaded/<id>/overview (rebuilding the same tab after a page
    refresh) - one code path, so the two can never drift apart.
    """
    inv = build_inventory_analysis(df)

    # Single SARIMA fit on the TOTAL daily demand across the whole file - not
    # one fit per product - so this stays fast no matter how many products
    # are in the upload. Cached under this upload_id so the Forecast tab
    # reuses the same fitted model instead of refitting.
    agg_series = build_aggregate_daily_series(df)
    demand_change_pct = None
    if len(agg_series) >= 14:
        ts_df = agg_series.to_frame(name="Units Sold")
        forecast = forecast_product_demand(ts_df, cache_key=f"agg_{upload_id}", steps=30)
        prev_30 = float(agg_series.tail(30).sum())
        if prev_30:
            demand_change_pct = round((float(forecast.sum()) - prev_30) / prev_30 * 100, 1)

    risk = risk_bucket_counts(inv)
    top_risk = inv.sort_values("Stockout_Probability_Pct", ascending=False).head(5)

    return {
        "upload_id": upload_id,
        "filename": filename,
        "warnings": warnings,
        "total_products": int(inv["Product ID"].nunique()),
        "total_stores": int(inv["Store ID"].nunique()),
        "total_records": int(len(df)),
        "date_range": [str(df["Date"].min().date()), str(df["Date"].max().date())],
        "risk_distribution": risk["collapsed"],
        "risk_distribution_full": risk["full"],
        "top_risk_products": _clean(
            top_risk[
                [
                    "Store ID", "Product ID", "Category", "Risk Level",
                    "Stockout_Probability_Pct", "Inventory Level", "Recommended Order",
                ]
            ].to_dict(orient="records")
        ),
        "key_insights": build_key_insights(inv, demand_change_pct),
        "demand_change_pct": demand_change_pct,
    }


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Validate + save the uploaded CSV, run the SAME build_inventory_analysis()
    used for the demo dataset and the Products page, and return everything
    the Overview tab needs. The tabs (Historical/Inventory/Forecast/
    Recommendations) are separate GET calls below, keyed by upload_id.
    """
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify({"error": "No file was uploaded."}), 400
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only .csv files are supported."}), 400

    try:
        raw = pd.read_csv(io.BytesIO(file.read()))
    except Exception:
        return jsonify({"error": "Couldn't read that file as CSV."}), 400

    df, messages = validate_and_prepare_upload(raw)
    if df is None:
        return jsonify({"error": messages[0] if messages else "Invalid file."}), 400

    upload_id = _save_upload(df)
    # remember the original filename alongside the data so a page refresh
    # (GET /api/uploaded/<id>/overview) can still show it
    with open(_upload_path(upload_id) + ".meta", "w") as f:
        f.write(file.filename)

    return jsonify(_build_overview_payload(df, upload_id, file.filename, messages))


@app.route("/api/uploaded/<upload_id>/overview")
def api_uploaded_overview(upload_id):
    """Rebuilds the Overview tab payload for an existing upload_id (used on page refresh)."""
    df = _load_upload(upload_id)
    meta_path = _upload_path(upload_id) + ".meta"
    filename = open(meta_path).read().strip() if os.path.exists(meta_path) else "your file"
    return jsonify(_build_overview_payload(df, upload_id, filename, []))


@app.route("/api/uploaded/<upload_id>/historical")
def api_uploaded_historical(upload_id):
    df = _load_upload(upload_id)
    daily = build_aggregate_daily_series(df).tail(90)
    monthly = get_aggregate_monthly_sales(df, months=6)
    by_category = sales_by_category(df)

    return jsonify(
        {
            "daily": {"dates": daily.index.strftime("%Y-%m-%d").tolist(), "values": [round(float(v), 1) for v in daily.values]},
            "monthly": {"labels": monthly.index.strftime("%b %Y").tolist(), "values": [round(float(v), 1) for v in monthly.values]},
            "by_category": {"labels": by_category.index.tolist(), "values": [round(float(v), 1) for v in by_category.values]},
            "summary": {
                "total_units_sold": round(float(df["Units Sold"].sum()), 1),
                "avg_daily_units": round(float(build_aggregate_daily_series(df).mean()), 1),
                "num_stores": int(df["Store ID"].nunique()),
                "num_categories": int(df["Category"].nunique()),
                "num_products": int(df["Product ID"].nunique()),
                "records": int(len(df)),
            },
        }
    )


@app.route("/api/uploaded/<upload_id>/inventory")
def api_uploaded_inventory(upload_id):
    df = _load_upload(upload_id)
    inv = build_inventory_analysis(df)
    health = inventory_health_counts(inv)
    by_category = restock_by_category(inv)

    return jsonify(
        {
            "health": health,
            "restock_by_category": {
                "labels": by_category.index.tolist(),
                "values": [round(float(v), 1) for v in by_category.values],
            },
            "risk_breakdown": risk_bucket_counts(inv)["full"],
            "summary": {
                "total_current_stock": round(float(inv["Inventory Level"].sum()), 1),
                "total_reorder_point": round(float(inv["Reorder Point"].sum()), 1),
                "total_recommended_order": round(float(inv["Recommended Order"].sum()), 1),
                "avg_days_of_inventory": round(float(inv["Days of Inventory"].mean(skipna=True)), 1),
                "products_needing_restock": health["needs_restock"],
                "products_healthy": health["healthy"],
            },
        }
    )


@app.route("/api/uploaded/<upload_id>/forecast")
def api_uploaded_forecast(upload_id):
    df = _load_upload(upload_id)
    agg_series = build_aggregate_daily_series(df)
    if len(agg_series) < 14:
        return jsonify({"error": "Not enough daily history in this file to forecast (need at least 14 days)."}), 400

    ts_df = agg_series.to_frame(name="Units Sold")
    forecast = forecast_product_demand(ts_df, cache_key=f"agg_{upload_id}", steps=30)
    risk_series = product_risk_from_forecast(forecast)

    history = agg_series.tail(90)
    prev_30 = float(agg_series.tail(30).sum())
    next_30 = float(forecast.sum())
    change_pct = round((next_30 - prev_30) / prev_30 * 100, 1) if prev_30 else None

    return jsonify(
        {
            "history": {"dates": history.index.strftime("%Y-%m-%d").tolist(), "values": [round(float(v), 1) for v in history.values]},
            "forecast": {"dates": forecast.index.strftime("%Y-%m-%d").tolist(), "values": [round(float(v), 1) for v in forecast.values]},
            "risk_breakdown": {k: int(v) for k, v in risk_series.value_counts().to_dict().items()},
            "summary": {
                "next_30": round(next_30, 1),
                "prev_30": round(prev_30, 1),
                "change_pct": change_pct,
                "avg_per_day": round(next_30 / len(forecast), 1),
                "peak_day": round(float(forecast.max()), 1),
                "low_day": round(float(forecast.min()), 1),
                "high_risk_days": int((risk_series == "High Demand / Stockout Risk").sum()),
            },
        }
    )


@app.route("/api/uploaded/<upload_id>/recommendations")
def api_uploaded_recommendations(upload_id):
    df = _load_upload(upload_id)
    inv = build_inventory_analysis(df)
    needs_restock = inv[inv["Recommendation"] == "REORDER"].copy()

    # Estimated order value, only for rows where we actually have a Price column
    has_price = df["Price"].notna().any() if "Price" in df.columns else False
    order_value = None
    if has_price:
        avg_price = df.groupby(["Store ID", "Product ID"])["Price"].mean().rename("avg_price")
        needs_restock = needs_restock.merge(avg_price, on=["Store ID", "Product ID"], how="left")
        needs_restock["order_value"] = needs_restock["Recommended Order"] * needs_restock["avg_price"]
        order_value = round(float(needs_restock["order_value"].sum(skipna=True)), 2)

    top = needs_restock.sort_values("Recommended Order", ascending=False).head(10)
    cols = ["Store ID", "Product ID", "Category", "Risk Level", "Stockout_Probability_Pct", "Inventory Level", "Reorder Point", "Recommended Order"]
    if has_price:
        cols += ["avg_price", "order_value"]

    worst_category = None
    if not needs_restock.empty:
        worst_category = needs_restock["Category"].value_counts().idxmax()

    return jsonify(
        {
            "total_products": int(len(inv)),
            "needs_restock_count": int(len(needs_restock)),
            "total_units_to_reorder": round(float(needs_restock["Recommended Order"].sum()), 1),
            "estimated_order_value": order_value,
            "worst_category": worst_category,
            "top_products": _clean(top[cols].to_dict(orient="records")),
            "lead_time_days": LEAD_TIME_DAYS,
        }
    )


@app.route("/api/uploaded/<upload_id>/download")
def api_uploaded_download(upload_id):
    """The 'Download Report' button: the full per-(store,product) analysis table as CSV."""
    df = _load_upload(upload_id)
    inv = build_inventory_analysis(df)
    cols = [
        "Store ID", "Product ID", "Category", "Inventory Level", "Average_Daily_Demand",
        "Days of Inventory", "Risk Level", "Stockout_Probability_Pct", "Reorder Point",
        "Recommended Order", "Recommendation",
    ]
    buf = io.BytesIO()
    inv[cols].to_csv(buf, index=False)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"stockmind_report_{upload_id[:8]}.csv",
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.get_json(force=True)
    question = payload.get("question", "")
    product_id = payload.get("product_id")
    store_id = payload.get("store_id")

    df = load_data()
    inv = build_inventory_analysis(df)
    context = create_inventory_context(inv, store_id=store_id, product_id=product_id)

    try:
        resp = requests.post(N8N_WEBHOOK_URL, json={"question": question, "context": context}, timeout=30)
        answer = resp.json().get("answer", "Sorry, I couldn't process that.")
    except Exception as e:
        answer = f"Chatbot service not reachable yet ({e}). Set N8N_WEBHOOK_URL in app.py."

    return jsonify({"answer": answer})


if __name__ == "__main__":
    app.run(debug=True)
