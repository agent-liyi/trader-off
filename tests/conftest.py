"""Shared pytest fixtures for trader-off tests."""

from datetime import date, timedelta

import polars as pl
import pytest


class FakeBroker:
    """Test double for millionaire Broker protocol.

    Implements trade_target_pct with a simple call recorder, avoiding
    MagicMock overuse in strategy tests.  # noqa: mock-overuse — test double, not mock
    """

    def __init__(self):
        self.calls: list[dict] = []

    def trade_target_pct(self, asset: str, target_pct: float, extra: dict | None = None) -> None:
        """Record the trade call for assertion."""
        self.calls.append({"asset": asset, "pct": target_pct, "extra": extra})


@pytest.fixture
def fake_broker() -> FakeBroker:
    """Provide a FakeBroker test double."""
    return FakeBroker()


@pytest.fixture
def five_assets_60_days() -> pl.DataFrame:
    """Generate OHLCV data: 5 assets × 60 trading days.

    Returns DataFrame with columns: asset, date, open, high, low, close,
    volume, turnover, adj_factor.
    """
    assets = ["A", "B", "C", "D", "E"]
    start_date = date(2024, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(60)]

    data = []
    for asset in assets:
        for i, d in enumerate(dates):
            base_price = 10.0 + i * 0.1 + (ord(asset) - ord("A")) * 2.0
            data.append(
                {
                    "asset": asset,
                    "date": d,
                    "open": base_price * 1.0,
                    "high": base_price * 1.02,
                    "low": base_price * 0.98,
                    "close": base_price * (1.0 + 0.005 * (i % 5)),
                    "volume": 1_000_000 + i * 10_000,
                    "turnover": 0.02 + (i % 10) * 0.001,
                    "adj_factor": 1.0,
                }
            )

    return pl.DataFrame(
        data,
        schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
            "adj_factor": pl.Float64,
        },
    )


@pytest.fixture
def single_asset_ohlcv() -> pl.DataFrame:
    """Single asset A with 5 close values [10, 11, 9, 12, 14]."""
    close_values = [10.0, 11.0, 9.0, 12.0, 14.0]
    start_date = date(2024, 1, 1)
    data = []
    for i, close_val in enumerate(close_values):
        d = start_date + timedelta(days=i)
        data.append(
            {
                "asset": "A",
                "date": d,
                "open": close_val * 0.99,
                "high": close_val * 1.02,
                "low": close_val * 0.98,
                "close": close_val,
                "volume": 1_000_000.0,
                "turnover": 0.02,
                "adj_factor": 1.0,
            }
        )
    return pl.DataFrame(
        data,
        schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
            "adj_factor": pl.Float64,
        },
    )
