"""Integration tests for prediction service (L2 contract simulation).

Covers the cross-module chain:
  model_io → prediction.service → strategies

Uses mock DataLoader stand-in; no real market data.
"""

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest

from trader_off.data.preprocess import (
    StandardScaler,
    fit_scaler_and_impute,
)
from trader_off.features.momentum import compute_momentum_features
from trader_off.features.volatility import compute_volatility_features
from trader_off.features.volume import compute_volume_features
from trader_off.labels.builder import build_labels
from trader_off.prediction.service import predict
from trader_off.training.serialize import save_model
from trader_off.training.trainer import train_model


def _make_ohlcv_data(
    n_assets: int = 5,
    n_days: int = 200,
    seed: int = 42,
) -> pl.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.RandomState(seed)
    start = date(2023, 1, 1)
    rows = []
    for a in range(n_assets):
        asset = f"{a:06d}.SZ"
        price = 10.0 + rng.randn() * 5
        for i in range(n_days):
            d = start + timedelta(days=i)
            ret = rng.randn() * 0.02
            close = price * (1.0 + ret)
            rows.append({
                "asset": asset,
                "date": d,
                "open": close * 0.99,
                "high": close * 1.02,
                "low": close * 0.98,
                "close": close,
                "volume": float(1_000_000 + i * 10_000),
                "turnover": 0.02 + rng.rand() * 0.01,
                "adj_factor": 1.0,
                "limit_up": False,
                "limit_down": False,
            })
            price = close
    return pl.DataFrame(rows)


@pytest.mark.integration
class TestPredictService:
    """Integration: model loading → feature compute → predict → rank."""

    @pytest.fixture
    def trained_model(self, tmp_path):
        """Train and save a model for prediction testing."""
        data = _make_ohlcv_data(n_assets=5, n_days=200)
        data = compute_momentum_features(data)
        data = compute_volatility_features(data)
        data = compute_volume_features(data)

        label_df = build_labels(
            data.select(["asset", "date", "close"]), horizon=5
        )
        data = data.join(label_df, on=["asset", "date"], how="left")
        data = data.filter(pl.col("label").is_not_null())

        feature_cols = [
            "ret_5", "ret_10", "ret_20", "ret_60",
            "vol_10", "vol_20", "vol_60",
            "turnover_5", "turnover_10", "turnover_20",
            "vp_corr_5", "vp_corr_10", "vp_corr_20",
        ]
        X = data.select(["asset", "date"] + feature_cols)

        dates_sorted = sorted(data["date"].unique().to_list())
        split_idx = int(len(dates_sorted) * 0.7)
        train_dates = dates_sorted[:split_idx]
        valid_dates = dates_sorted[split_idx:]

        X_train = X.filter(pl.col("date").is_in(train_dates))
        y_train = data.filter(
            pl.col("date").is_in(train_dates)
        )["label"].drop_nulls()
        X_valid = X.filter(pl.col("date").is_in(valid_dates))
        y_valid = data.filter(
            pl.col("date").is_in(valid_dates)
        )["label"].drop_nulls()

        X_scaled, scaler, dropped = fit_scaler_and_impute(X_train)
        common = min(len(X_scaled), len(y_train), len(X_valid), len(y_valid))

        params = {"num_leaves": 8, "n_estimators": 20, "verbose": -1}
        booster = train_model(
            X_train=X_scaled.head(common).select(scaler.feature_names),
            y_train=pl.Series("label", y_train.head(common).to_list()),
            X_valid=X_valid.head(common).select(scaler.feature_names),
            y_valid=pl.Series("label", y_valid.head(common).to_list()),
            params=params,
        )

        models_dir = tmp_path / "models"
        version = "20260101_120000"
        model_dir = save_model(
            booster=booster, scaler=scaler,
            metadata={"train_start": "2023-01-01", "max_lookback": 120},
            version=version, models_dir=models_dir,
            dropped_features=dropped,
            feature_names=scaler.feature_names,
        )

        return {
            "data": data,
            "model_dir": model_dir,
            "version": version,
            "models_dir": models_dir,
            "feature_names": scaler.feature_names,
        }

    def test_ac_fr0900_01_predict_returns_dataframe(
        self, trained_model, tmp_path
    ):
        """AC-FR0900-01: predict returns DataFrame with asset, score, rank."""
        data = trained_model["data"]
        watchlist = [
            a for a in data["asset"].unique().to_list()[:3]
        ]

        mock_loader = MagicMock()

        async def mock_get_history(asset, end_date, count=120):
            ad = data.filter(pl.col("asset") == asset).sort("date")
            return ad.head(count)

        mock_loader.get_history = MagicMock(side_effect=mock_get_history)

        async def run():
            return await predict(
                model_version=trained_model["version"],
                watchlist=watchlist,
                asof_date=data["date"].max(),
                data_loader=mock_loader,
                models_dir=trained_model["models_dir"],
                skipped_path=tmp_path / "predict_skipped.json",
            )

        result = asyncio.run(run())

        assert isinstance(result, pl.DataFrame)
        assert {"asset", "score", "rank"}.issubset(set(result.columns))

    def test_ac_fr0900_02_sorted_desc(self, trained_model, tmp_path):
        """AC-FR0900-02: predict returns results sorted by score descending."""
        data = trained_model["data"]
        watchlist = [
            a for a in data["asset"].unique().to_list()[:3]
        ]

        mock_loader = MagicMock()

        async def mock_get_history(asset, end_date, count=120):
            ad = data.filter(pl.col("asset") == asset).sort("date")
            return ad.head(count)

        mock_loader.get_history = MagicMock(side_effect=mock_get_history)

        async def run():
            return await predict(
                model_version=trained_model["version"],
                watchlist=watchlist,
                asof_date=data["date"].max(),
                data_loader=mock_loader,
                models_dir=trained_model["models_dir"],
                skipped_path=tmp_path / "predict_skipped.json",
            )

        result = asyncio.run(run())

        if len(result) > 1:
            scores = result["score"].to_list()
            assert scores == sorted(scores, reverse=True), (
                f"Scores not sorted descending: {scores}"
            )
            ranks = result["rank"].to_list()
            assert ranks == list(range(1, len(result) + 1)), (
                f"Ranks not sequential from 1: {ranks}"
            )

    def test_ac_fr0900_03_skip_insufficient(
        self, trained_model, tmp_path
    ):
        """AC-FR0900-03: assets with insufficient history are skipped."""
        data = trained_model["data"]
        all_assets = [a for a in data["asset"].unique().to_list()]
        watchlist = all_assets + ["999999.SZ"]  # non-existent asset

        mock_loader = MagicMock()

        async def mock_get_history(asset, end_date, count=120):
            if asset == "999999.SZ":
                # Return fewer rows than lookback
                return _make_ohlcv_data(n_assets=1, n_days=10).filter(
                    pl.col("asset") == "000000.SZ"
                ).with_columns(pl.lit("999999.SZ").alias("asset"))
            ad = data.filter(pl.col("asset") == asset).sort("date")
            return ad.head(count)

        mock_loader.get_history = MagicMock(side_effect=mock_get_history)

        skipped_path = tmp_path / "predict_skipped.json"

        async def run():
            return await predict(
                model_version=trained_model["version"],
                watchlist=watchlist,
                asof_date=data["date"].max(),
                data_loader=mock_loader,
                models_dir=trained_model["models_dir"],
                skipped_path=skipped_path,
            )

        result = asyncio.run(run())

        # 999999.SZ should be skipped
        assert "999999.SZ" not in result["asset"].to_list()

        # predict_skipped.json should have the record
        if skipped_path.exists():
            skipped = json.loads(skipped_path.read_text())
            assert any(
                r.get("asset") == "999999.SZ" for r in skipped
            ), f"Skipped record not found in {skipped}"
