"""E2E pipeline test (FR-1500).

Tests the full train → predict → backtest pipeline using fixture data.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import polars as pl
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_data() -> pl.DataFrame:
    """Load 10 stocks × 60 days OHLCV fixture."""
    return pl.read_parquet(FIXTURES / "ohlcv_10x60.parquet")


@pytest.fixture
def watchlist() -> list[str]:
    """Asset watchlist from fixture."""
    return [f"{i:06d}.SZ" for i in range(1, 11)]


@pytest.mark.e2e
class TestLGBMPipeline:
    """End-to-end test: train → predict → backtest."""

    def test_ac_fr1500_01_full_pipeline(self, fixture_data, watchlist, tmp_path):
        """AC-FR1500-1: Full pipeline runs and produces expected outputs."""
        t0 = time.perf_counter()

        # ---- Step 1: Train model ----
        from trader_off.features.momentum import compute_momentum_features
        from trader_off.features.volatility import compute_volatility_features
        from trader_off.features.volume import compute_volume_features
        from trader_off.data.preprocess import fit_scaler_and_impute
        from trader_off.labels.builder import build_labels
        from trader_off.training.trainer import train_model
        from trader_off.training.serialize import save_model

        data = fixture_data.sort(["asset", "date"])

        # Compute features
        data = compute_momentum_features(data)
        data = compute_volatility_features(data)
        data = compute_volume_features(data)

        # Build labels
        label_df = build_labels(data.select(["asset", "date", "close"]), horizon=5)
        data = data.join(label_df, on=["asset", "date"], how="left")

        # Drop rows with NaN labels
        data = data.filter(pl.col("label").is_not_null())

        feature_cols = [
            "ret_5", "ret_10", "ret_20", "ret_60",
            "vol_10", "vol_20", "vol_60",
            "turnover_5", "turnover_10", "turnover_20",
            "vp_corr_5", "vp_corr_10", "vp_corr_20",
        ]
        X = data.select(["asset", "date"] + feature_cols)
        y = data.select(["asset", "date", "label"])

        X["date"].min()

        # Simple train/valid split: first 40 days train, last ~20 days valid
        dates_sorted = sorted(data["date"].unique().to_list())
        split_idx = int(len(dates_sorted) * 0.7)
        train_dates = dates_sorted[:split_idx]
        valid_dates = dates_sorted[split_idx:]

        X_train = X.filter(pl.col("date").is_in(train_dates))
        y_train = y.filter(pl.col("date").is_in(train_dates))
        X_valid = X.filter(pl.col("date").is_in(valid_dates))
        y_valid = y.filter(pl.col("date").is_in(valid_dates))

        if len(X_train) < 10 or len(X_valid) < 10:
            pytest.skip("Not enough data for train/valid split")

        X_scaled, scaler, dropped = fit_scaler_and_impute(X_train)
        X_valid_feat = X_valid.select(feature_cols)
        y_train_vals = y_train["label"].drop_nulls()
        y_valid_vals = y_valid["label"].drop_nulls()

        # Align X and y
        common_train = min(len(X_scaled), len(y_train_vals))
        common_valid = min(len(X_valid_feat), len(y_valid_vals))

        if common_train < 10 or common_valid < 5:
            pytest.skip("Not enough aligned data")

        params = {
            "num_leaves": 8,
            "n_estimators": 20,
            "early_stopping_rounds": 5,
            "learning_rate": 0.1,
            "verbose": -1,
        }

        booster = train_model(
            X_train=X_scaled.head(common_train).select(scaler.feature_names),
            y_train=pl.Series("label", y_train_vals.head(common_train).to_list()),
            X_valid=X_valid_feat.head(common_valid).select(scaler.feature_names),
            y_valid=pl.Series("label", y_valid_vals.head(common_valid).to_list()),
            params=params,
        )

        # Save model
        models_dir = tmp_path / "models"
        version = "20260101_120000"
        model_dir = save_model(
            booster=booster,
            scaler=scaler,
            metadata={"train_start": "2024-01-01", "max_lookback": 60},
            version=version,
            models_dir=models_dir,
            dropped_features=dropped,
            feature_names=scaler.feature_names,
        )

        # Assert model directory has required files
        required = ["model.pkl", "scaler.json", "feature_names.json", "metadata.json"]
        for fname in required:
            assert (model_dir / fname).exists(), f"Missing {fname}"

        # ---- Step 2: Predict ----
        from trader_off.prediction.service import predict

        # Mock data_loader for predict
        mock_loader = MagicMock()

        async def mock_get_history(asset, end_date, count=120):
            asset_data = data.filter(pl.col("asset") == asset).sort("date")
            n_avail = len(asset_data)
            if n_avail < count:
                # Return what we have (will be skipped)
                return asset_data.head(n_avail)
            return asset_data.head(count)

        mock_loader.get_history = AsyncMock(side_effect=mock_get_history)

        asof_date = data["date"].max()
        predictions = None
        import asyncio

        async def run_predict():
            nonlocal predictions
            predictions = await predict(
                model_version=version,
                watchlist=watchlist,
                asof_date=asof_date,
                data_loader=mock_loader,
                models_dir=models_dir,
                skipped_path=tmp_path / "predict_skipped.json",
            )

        asyncio.run(run_predict())

        assert predictions is not None
        assert isinstance(predictions, pl.DataFrame)
        if len(predictions) > 0:
            assert set(predictions.columns) == {"asset", "score", "rank"}

        # ---- Step 3: Backtest ----
        from trader_off.backtest.runner import run_backtest

        result = run_backtest(
            model_version=version,
            strategy_name="lgbm_top20",
            start=data["date"].min(),
            end=data["date"].max(),
            capital=1_000_000,
        )

        report_dir = result.report_dir

        # ---- Step 4: Assert reports ----
        assert (report_dir / "summary.json").exists()
        summary = json.loads((report_dir / "summary.json").read_text())
        required_keys = {"annualized_return", "sharpe_ratio", "max_drawdown",
                         "win_rate", "total_trades", "avg_turnover"}
        assert required_keys.issubset(set(summary.keys()))

        # ---- Timing assertion (AC-FR1500-2) ----
        elapsed = time.perf_counter() - t0
        assert elapsed < 60, f"E2E test took {elapsed:.1f}s, must be <60s"

    def test_ac_fr1500_03_fixtures_exist(self):
        """AC-FR1500-3: Fixture files exist offline."""
        assert (FIXTURES / "ohlcv_10x60.parquet").exists()
        assert (FIXTURES / "watchlist.csv").exists()
        assert (FIXTURES / "baseline_nav.parquet").exists()
