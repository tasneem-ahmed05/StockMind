"""
Regenerate forecasts.csv
========================
The original forecasts.csv was exported from a Colab notebook that used a
train/test split: SARIMA was trained on ~85% of the series and asked to
predict the held-out window (2023-09-12 -> 2023-10-11). That is a BACKTEST -
it forecasts a period that has already happened and that overlaps the
history, so plotting it after the full history produces a chart that jumps
backwards in time.

This script refits each (Store, Product) on the FULL history and forecasts
the 30 days that come after the last real day, which is what the Product
Analysis page actually needs.

Run:  python regenerate_forecasts.py
"""
import time

import pandas as pd

from utils import DATA_PATH, build_product_time_series, forecast_product_demand, load_data

OUT_PATH = "forecasts.csv"
STEPS = 30


def main():
    df = load_data(DATA_PATH)
    pairs = df[["Store ID", "Product ID"]].drop_duplicates().sort_values(["Store ID", "Product ID"])
    print(f"Refitting SARIMA for {len(pairs)} (store, product) pairs on full history…")

    frames = []
    started = time.time()

    for n, (_, pair) in enumerate(pairs.iterrows(), start=1):
        store_id, product_id = pair["Store ID"], pair["Product ID"]
        try:
            ts = build_product_time_series(df, product_id, store_id=store_id)
            forecast = forecast_product_demand(ts, cache_key=f"{store_id}_{product_id}", steps=STEPS)
        except Exception as exc:  # a single bad series shouldn't kill the export
            print(f"  !! {store_id}/{product_id} failed: {exc}")
            continue

        frames.append(
            pd.DataFrame(
                {
                    "Store ID": store_id,
                    "Product ID": product_id,
                    "Date": forecast.index,
                    "Forecasted_Demand": forecast.values.round(2),
                }
            )
        )

        if n % 10 == 0:
            print(f"  {n}/{len(pairs)} done ({time.time() - started:.0f}s elapsed)")

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT_PATH, index=False)

    print(f"\nWrote {OUT_PATH}: {len(out)} rows, {out.groupby(['Store ID', 'Product ID']).ngroups} pairs")
    print(f"Forecast window: {out['Date'].min().date()} -> {out['Date'].max().date()}")
    print(f"History ends:    {df['Date'].max().date()}  (forecast must start after this)")
    print(f"Total time: {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
