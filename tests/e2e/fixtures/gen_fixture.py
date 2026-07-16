"""Generate e2e fixture data: 10 stocks × 60 trading days.

Usage: python tests/e2e/fixtures/gen_fixture.py
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

OUT_DIR = Path(__file__).parent
ASSETS = [f"{i:06d}.SZ" for i in range(1, 11)]
N_DAYS = 60
START_DATE = date(2024, 1, 2)
SEED = 42


def generate():
    rng = np.random.RandomState(SEED)
    dates = [START_DATE + timedelta(days=i) for i in range(N_DAYS)]

    rows = []
    for asset in ASSETS:
        price = 10.0 + rng.randn() * 5
        for i, d in enumerate(dates):
            ret = rng.randn() * 0.02
            close = price * (1.0 + ret)
            rows.append({
                "asset": asset,
                "date": d,
                "open": close * 0.99,
                "high": close * 1.02,
                "low": close * 0.98,
                "close": close,
                "volume": float(1_000_000 + i * 10_000 + rng.randint(0, 500000)),
                "turnover": 0.01 + rng.rand() * 0.02,
                "adj_factor": 1.0,
                "limit_up": False,
                "limit_down": False,
            })
            price = close

    df = pl.DataFrame(rows, schema={
        "asset": pl.Utf8, "date": pl.Date,
        "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
        "close": pl.Float64, "volume": pl.Float64,
        "turnover": pl.Float64, "adj_factor": pl.Float64,
        "limit_up": pl.Boolean, "limit_down": pl.Boolean,
    })

    df.write_parquet(OUT_DIR / "ohlcv_10x60.parquet")

    # Write watchlist
    watchlist = pl.DataFrame({
        "asset": ASSETS,
        "frame_type": ["DAY"] * len(ASSETS),
    })
    watchlist.write_csv(OUT_DIR / "watchlist.csv")

    # Baseline nav
    bdates = [START_DATE + timedelta(days=i) for i in range(N_DAYS)]
    returns = rng.randn(N_DAYS) * 0.01 + 0.0003
    bnav = 1000.0 * np.cumprod(1.0 + returns)
    baseline = pl.DataFrame({
        "date": bdates,
        "nav": bnav.tolist(),
    })
    baseline.write_parquet(OUT_DIR / "baseline_nav.parquet")

    print(f"Fixtures generated in {OUT_DIR}")


if __name__ == "__main__":
    generate()
