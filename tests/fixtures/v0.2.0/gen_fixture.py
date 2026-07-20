"""Generate synthetic v0.2.0 e2e fixtures with deterministic seed=42.

Produces:
    ohlcv_50x252.parquet — 50 assets × 252 trading days OHLCV + turnover
    industry_map.csv — 50 assets → 10 industries (round-robin)
    predictions_fixture.csv — asset, score, rank (50 rows)
"""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

OUT_DIR = Path(__file__).parent
SEED = 42
N_ASSETS = 50
N_DAYS = 252
N_INDUSTRIES = 10


def generate_ohlcv() -> pl.DataFrame:
    """Generate 50 assets × 252 trading days of synthetic OHLCV data."""
    rng = np.random.default_rng(SEED)

    # Generate trading dates (252 consecutive weekdays)
    start_date = date(2022, 1, 3)
    dates: list[date] = []
    current = start_date
    while len(dates) < N_DAYS:
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current)
        current += timedelta(days=1)

    asset_ids = [f"{i:06d}.SZ" for i in range(1, N_ASSETS + 1)]

    # Each asset gets a different drift and volatility
    drifts = rng.uniform(-0.001, 0.001, N_ASSETS)  # daily drift
    volatilities = rng.uniform(0.01, 0.03, N_ASSETS)  # daily volatility
    # Starting prices vary by asset
    start_prices = rng.uniform(5.0, 100.0, N_ASSETS)

    rows = []
    for i, asset in enumerate(asset_ids):
        mu = drifts[i]
        sigma = volatilities[i]
        # Generate random walk for close prices
        daily_returns = rng.normal(mu, sigma, N_DAYS)
        close_prices = start_prices[i] * np.exp(np.cumsum(daily_returns))
        for d_idx, d in enumerate(dates):
            close = float(close_prices[d_idx])
            open_price = close * float(rng.uniform(0.98, 1.02))
            high = max(open_price, close) * float(rng.uniform(1.0, 1.05))
            low = min(open_price, close) * float(rng.uniform(0.95, 1.0))
            volume = float(max(1000, rng.normal(1_000_000, 500_000)))
            turnover = volume / (close * rng.uniform(50000, 200000))
            adj_factor = 1.0
            rows.append(
                {
                    "asset": asset,
                    "date": d,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "turnover": turnover,
                    "adj_factor": adj_factor,
                    "limit_up": close * 1.10,
                    "limit_down": close * 0.90,
                }
            )

    df = pl.DataFrame(rows)
    df = df.with_columns(
        [
            pl.col("date").cast(pl.Date),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
            pl.col("turnover").cast(pl.Float64),
            pl.col("adj_factor").cast(pl.Float64),
            pl.col("limit_up").cast(pl.Float64),
            pl.col("limit_down").cast(pl.Float64),
        ]
    )
    return df.sort(["asset", "date"])


def generate_industry_map() -> pl.DataFrame:
    """Generate 50 assets → 10 industries (round-robin)."""
    industries = [
        "banking",
        "real_estate",
        "technology",
        "healthcare",
        "energy",
        "materials",
        "consumer",
        "industrial",
        "utilities",
        "telecom",
    ]
    asset_ids = [f"{i:06d}.SZ" for i in range(1, N_ASSETS + 1)]

    rows = []
    for i, asset in enumerate(asset_ids):
        industry = industries[i % len(industries)]
        rows.append({"asset": asset, "industry": industry})
    return pl.DataFrame(rows)


def generate_predictions() -> pl.DataFrame:
    """Generate 50 assets with score and rank."""
    rng = np.random.default_rng(SEED)
    asset_ids = [f"{i:06d}.SZ" for i in range(1, N_ASSETS + 1)]
    scores = rng.uniform(-0.05, 0.05, N_ASSETS)
    # Rank: higher score = lower rank number (1 = best)
    sorted_idx = np.argsort(-scores)  # descending
    ranks = np.zeros(N_ASSETS, dtype=int)
    ranks[sorted_idx] = np.arange(1, N_ASSETS + 1)

    rows = []
    for i, asset in enumerate(asset_ids):
        rows.append(
            {
                "asset": asset,
                "score": float(scores[i]),
                "rank": int(ranks[i]),
            }
        )
    df = pl.DataFrame(rows)
    return df.sort("rank")


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def main():
    """Generate all v0.2.0 fixtures and MANIFEST.json."""
    print("Generating ohlcv_50x252.parquet...")  # noqa: T201
    ohlcv = generate_ohlcv()
    ohlcv_path = OUT_DIR / "ohlcv_50x252.parquet"
    ohlcv.write_parquet(ohlcv_path)
    print(f"  → {ohlcv_path} ({ohlcv.height} rows × {ohlcv.width} cols)")  # noqa: T201

    print("Generating industry_map.csv...")  # noqa: T201
    industry_map = generate_industry_map()
    industry_path = OUT_DIR / "industry_map.csv"
    industry_map.write_csv(industry_path)
    print(f"  → {industry_path} ({industry_map.height} rows)")  # noqa: T201

    print("Generating predictions_fixture.csv...")  # noqa: T201
    predictions = generate_predictions()
    pred_path = OUT_DIR / "predictions_fixture.csv"
    predictions.write_csv(pred_path)
    print(f"  → {pred_path} ({predictions.height} rows)")  # noqa: T201

    # Generate MANIFEST.json
    manifest = {}
    for name, path in [
        ("ohlcv_50x252.parquet", ohlcv_path),
        ("industry_map.csv", industry_path),
        ("predictions_fixture.csv", pred_path),
    ]:
        manifest[name] = {
            "sha256": compute_sha256(path),
            "size_bytes": path.stat().st_size,
            "rows": None,
        }

    # Add row counts
    manifest["ohlcv_50x252.parquet"]["rows"] = ohlcv.height
    manifest["industry_map.csv"]["rows"] = industry_map.height
    manifest["predictions_fixture.csv"]["rows"] = predictions.height

    manifest_path = OUT_DIR / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"  → {manifest_path}")  # noqa: T201
    print("Done.")  # noqa: T201


if __name__ == "__main__":
    main()
