# StockMind — Team handoff

## What's ready vs. what's left

**Ready (don't touch unless you have to):**
- `app.py` — Flask backend, all routes + API endpoints already wired up.
- `utils.py` — all the data/model logic (risk scoring, reorder point, SARIMA forecast, the `FEATURED_PRODUCTS` list for the Products page).
- `retail_store_inventory.csv` — the dataset.
- `forecasts.csv` — precomputed SARIMA forecasts (exported once from Colab, see `export_forecasts_colab_cell.py`). The app reads this instead of retraining live.
- `templates/base.html` + `static/css/base.css` — shared navbar and design system (colors, buttons, cards, badges). Reuse these classes on your page instead of redefining them.
- `templates/index.html` + `static/css/home.css` — **Home page is done.**

**Left for the team — one page each, fully separated so nobody steps on anyone else's files:**

| Page | Template | CSS | JS | API it should call |
|---|---|---|---|---|
| Products (showcase) | `templates/products.html` | `static/css/products.css` | `static/js/products.js` | `GET /api/products` |
| Product Analysis | `templates/product.html` | `static/css/product.css` | `static/js/product.js` | `GET /api/product/<store_id>/<product_id>` |
| Upload Data | `templates/upload.html` | `static/css/upload.css` | `static/js/upload.js` | `POST /api/upload` |
| Chatbot | `templates/chatbot.html` | `static/css/chatbot.css` | `static/js/chatbot.js` | `POST /api/chat` |

Each template already has a `<!-- TODO -->` comment inside it explaining exactly what the API returns and how to link it — read that first. Each CSS/JS file is empty and already linked from its template, so you can start typing straight away without touching `base.html` or anyone else's page.

### `_reference/` folder
A previous working version of each of those 4 pages (table-based UI, plain but functional, using the same API) is kept in `_reference/` — including the old `style.css`. Not linked anywhere, just there if you want to see a working example before building your own design.

## Running it

```
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Changing the 6 featured products / adding their photos
Open `utils.py`, find `FEATURED_PRODUCTS` near the top. Each entry is:
```python
{"store_id": "S001", "product_id": "P0006", "display_name": "Laptop Pro 15", "image": None}
```
- `store_id` / `product_id` must exist in `retail_store_inventory.csv`.
- Put an image file in `static/images/` and set `"image": "/static/images/yourfile.jpg"`.
- Leave `"image": None` to fall back to a category icon (emoji).
