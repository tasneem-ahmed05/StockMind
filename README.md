# StockMind — Team handoff

## What's ready

- `app.py` — Flask backend, all routes + API endpoints wired up.
- `utils.py` — all the data/model logic (risk scoring, reorder point, stockout probability, SARIMA forecast, `FEATURED_PRODUCTS`, upload validation).
- `retail_store_inventory.csv` — the demo dataset.
- `forecasts.csv` — precomputed SARIMA forecasts for the demo dataset, trained on the FULL history (see `regenerate_forecasts.py` below). The app reads this instead of retraining live; it auto-falls-back to a live fit if this file is ever missing or stale.
- `templates/base.html` + `static/css/base.css` — shared navbar and design system (colors, buttons, cards, badges, `.grid`). Reuse these classes instead of redefining them.
- **Home page** — done.
- **Products page** (`templates/products.html` / `static/{css,js}/products.js`) — the 6 curated `FEATURED_PRODUCTS`, real risk-based filters, working Analyze + Random Product buttons. Backed by `GET /api/products`.
- **Product Analysis page** (`templates/product.html` / `static/{css,js}/product.js`) — 5 tabs (Overview / Historical Sales / Inventory / Forecast / Recommendations), 8 charts, all real numbers from the sales history + SARIMA forecast. Backed by `GET /api/product/<store_id>/<product_id>`.
- **Upload Data page** (`templates/upload.html` / `static/{css,js}/upload.js`) — drag-and-drop CSV upload with a 4-step progress tracker, then the same 5-tab analysis dashboard as the Product Analysis page but **aggregated across every product in the uploaded file**. Uses the exact same `classify_risk` / reorder-point / stockout-probability formulas — see "How the Upload page relates to Product Analysis" below. Backed by `POST /api/upload` + `GET /api/uploaded/<upload_id>/{overview,historical,inventory,forecast,recommendations,download}`.

**Left for the team:**

| Page | Template | CSS | JS | API it should call |
|---|---|---|---|---|
| Chatbot | `templates/chatbot.html` | `static/css/chatbot.css` | `static/js/chatbot.js` | `POST /api/chat` |

The chatbot template has a `<!-- TODO -->` comment explaining the API. `_reference/` has a previous plain-but-working version of every page (including Upload) if useful as a starting point — not linked anywhere.

## How the Upload page relates to Product Analysis

Same risk level and recommendation, yes — it's not a separate/simplified model:

- **Risk Level** for every row in the uploaded file comes from the same `classify_risk()` thresholds (Critical < 3 days of stock, High < 7, Medium < 14, Low ≥ 14).
- **Reorder Point / Recommended Order** use the identical formula: `(avg daily demand × 7-day lead time) + 20% safety stock`, and `Recommended Order = Reorder Point − current stock`.
- **Stockout Probability %** (new) is a normal-approximation service-level calculation from each product's own daily demand and its variability — the same field now also shows up on the single-Product Analysis page ("X% chance of stockout").
- The only real difference: the Upload page **aggregates** these per-product numbers across the whole file (totals, category breakdowns, a single SARIMA fit on total daily demand instead of one fit per product) so it stays fast and readable no matter how many products are in the file. The "Download Report" button exports the full, ungrouped per-product table as CSV if you want the raw numbers.

## Running it

```
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

Uploaded files are saved under `uploads/` (created automatically, git-ignored) so a page refresh can reload the same analysis via its `?id=` in the URL. Safe to delete that folder any time — it's just a cache of past uploads.

## Regenerating `forecasts.csv`

If you change `retail_store_inventory.csv`, re-run:
```
python regenerate_forecasts.py
```
This refits SARIMA on the full history for all 100 (store, product) pairs (~1 minute) and overwrites `forecasts.csv`. Skipping this just means the app fits SARIMA live per product on first request instead (slower, not persisted across restarts) — everything still works, just not instant.

## Changing the 6 featured products / their photos / category

Open `utils.py`, find `FEATURED_PRODUCTS` near the top. Each entry is:
```python
{"store_id": "S001", "product_id": "P0006", "display_name": "Laptop Pro 15", "category": "Electronics", "image": "images/products/laptop-pro-15.jpg"}
```
- `store_id` / `product_id` must exist in `retail_store_inventory.csv`.
- `category` is curated on purpose: this dataset assigns a *random* Category to every row, so pulling "Category" straight from the CSV for a specific product is meaningless — set the real one here instead.
- Put an image file under `static/images/products/` and reference it here as a relative path (`images/products/yourfile.jpg`). Leave `"image": None` to fall back to a category icon (emoji).
