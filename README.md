# StockMind

**AI-Powered Inventory Management Web Platform**

StockMind uses machine learning to forecast product demand, flag stockout/overstock risk, and recommend restock actions — presented through an interactive web app with a context-aware AI chatbot.

## Overview

Retail teams often react to stockouts and overstock after the fact. StockMind turns historical sales and inventory data into forward-looking decisions:

1. **Forecast** future demand per product using time-series models (SARIMA + ML models).
2. **Assess risk** — classify each product as Stockout Risk / Overstock Risk / Normal.
3. **Recommend** whether to reorder, how much, and when.
4. **Present** everything through a web interface — product catalog, per-product analysis with charts, and a custom dataset upload flow.
5. **Explain** results in plain language via an AI chatbot.

## Screenshots

| Home | Products |
|---|---|
| 
 | 
|

| Product Analysis | Upload Data |
|---|---|
| 
| 
 |

| Chatbot |
|---|
| ![Uploading Screenshot 2026-09-16 180835.png…]()
 |

## Features

- **Home** — landing page introducing the platform.
- **Products** — catalog of featured products with images, risk badges, and filters (High Stockout Risk, Overstock, High Demand, Seasonal, Normal).
- **Product Analysis** — per-product deep dive: sales history, demand forecast (30-day, weekly buckets), inventory depletion projection, stockout/overstock reasoning, and a recommended reorder quantity + timing.
- **Upload Data** — drag-and-drop a custom CSV and get a full risk/recommendation report generated from that dataset instead of the bundled demo data.
- **AI Chatbot** — answers questions about a product's risk, forecast, or recommendation, grounded in the actual data and model output.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Data & Modeling | pandas, NumPy, statsmodels (SARIMA) |
| Frontend | HTML, CSS, JavaScript (no framework) |
| Chatbot | n8n workflow (webhook → AI agent) called from the Flask backend |

## Project Structure

```
StockMind/
├── app.py                     # Flask backend — page routes + JSON API
├── utils.py                   # Data loading, risk scoring, reorder point, SARIMA forecasting
├── regenerate_forecasts.py    # Recomputes forecasts.csv (precomputed SARIMA forecasts)
├── retail_store_inventory.csv # Demo dataset
├── forecasts.csv              # Precomputed forecasts the app reads at runtime
├── requirements.txt
├── templates/                 # Jinja templates (one per page)
├── static/
│   ├── css/                   # Per-page stylesheets
│   ├── js/                    # Per-page frontend logic
│   └── images/                # Product images and UI assets
└── _reference/                # Earlier reference implementation of the 4 pages
```

## Getting Started

### Prerequisites
- Python 3.10+

### Installation

```bash
git clone https://github.com/tasneem-ahmed05/StockMind.git
cd StockMind
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/products` | GET | Featured product catalog with risk level and demand trend; supports `?risk=` and `?search=` filters |
| `/api/product/<store_id>/<product_id>` | GET | Full analysis for one product: history, forecast, risk breakdown, restock timing, and reasoning |
| `/api/upload` | POST | Accepts a CSV, validates it, and returns a full risk/recommendation report |
| `/api/chat` | POST | Forwards a question (with product context) to the chatbot and returns the answer |

## Dataset

The bundled demo dataset (`retail_store_inventory.csv`) contains retail sales and inventory records across multiple stores, products, and categories, with fields including date, store/product IDs, category, inventory level, units sold, demand forecast, price, discount, and seasonality — used to train and validate the forecasting models.

## How It Works

- **Forecasting**: Baseline/naive forecast compared against SARIMA and ML models (Linear Regression, Random Forest, XGBoost); the best-performing approach is used per product.
- **Risk classification**: Combines current inventory level, reorder point, lead time demand, and safety stock to classify each product's risk.
- **Recommendation engine**: Converts the forecast and risk assessment into a concrete reorder decision — quantity and timing — with the reasoning behind it.
- **Precomputed forecasts**: SARIMA forecasts are trained once and exported to `forecasts.csv`, so the app serves fast, consistent results instead of retraining on every request (falls back to live fitting only if the file is missing).

## License

This project was built as an academic graduation/course project. Add a license file if you plan to open it up for reuse.
