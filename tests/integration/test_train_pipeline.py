"""Integration tests for the training pipeline (L2 contract simulation).

Covers the cross-module chain:
  features → preprocess → labels → walk-forward → training → serialization

Uses fixture-backed DataLoader stand-ins; no real market data.
"""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from trader_off.data.preprocess import (
    fit_scaler_and_impute,
)
from trader_off.features.momentum import compute_momentum_features
from trader_off.features.volatility import compute_volatility_features
from trader_off.features.volume import compute_volume_features
from trader_off.labels.builder import build_labels
from trader_off.training.serialize import load_model, save_model
from trader_off.training.trainer import train_model


def _make_ohlcv_data(
    n_assets: int = 5,
    n_days: int = 200,
    seed: int = 42,
) -> pl.DataFrame:
    """Generate synthetic OHLCV data for n assets × n days."""
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
            rows.append(
                {
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
                }
            )
            price = close
    return pl.DataFrame(rows)


@pytest.mark.integration
class TestTrainPipeline:
    """Integration: feature engineering → labels → scaling → training → save."""

    def test_full_train_pipeline(self, tmp_path):
        """Full training pipeline produces valid model files.

        Verifies the cross-module contract:
          features → data.preprocess → labels → training.trainer → model_io
        """
        data = _make_ohlcv_data(n_assets=5, n_days=200)

        # ---- Features ----
        data = compute_momentum_features(data)
        data = compute_volatility_features(data)
        data = compute_volume_features(data)

        assert "ret_5" in data.columns, "Missing momentum features"
        assert "vol_10" in data.columns, "Missing volatility features"
        assert "turnover_5" in data.columns, "Missing volume features"

        # ---- Labels ----
        label_df = build_labels(data.select(["asset", "date", "close"]), horizon=5)
        data = data.join(label_df, on=["asset", "date"], how="left")
        data = data.filter(pl.col("label").is_not_null())

        assert len(data) > 0, "No data after label filtering"
        assert data["label"].null_count() == 0, "Labels should be non-null"

        # ---- Train/valid split ----
        feature_cols = [
            "ret_5",
            "ret_10",
            "ret_20",
            "ret_60",
            "vol_10",
            "vol_20",
            "vol_60",
            "turnover_5",
            "turnover_10",
            "turnover_20",
            "vp_corr_5",
            "vp_corr_10",
            "vp_corr_20",
        ]
        X = data.select(["asset", "date"] + feature_cols)
        y = data.select(["asset", "date", "label"])

        dates_sorted = sorted(data["date"].unique().to_list())
        split_idx = int(len(dates_sorted) * 0.7)
        train_dates = dates_sorted[:split_idx]
        valid_dates = dates_sorted[split_idx:]

        X_train = X.filter(pl.col("date").is_in(train_dates))
        y_train = y.filter(pl.col("date").is_in(train_dates))
        X_valid = X.filter(pl.col("date").is_in(valid_dates))
        y_valid = y.filter(pl.col("date").is_in(valid_dates))

        # ---- Scaling ----
        from trader_off.data.preprocess import StandardScaler

        X_scaled, scaler, dropped = fit_scaler_and_impute(X_train)
        assert isinstance(scaler, StandardScaler), f"Expected StandardScaler, got {type(scaler)}"
        assert len(scaler.feature_names) > 0, "No feature names in scaler"
        # ret_60 and vol_60 may be dropped if data is insufficient
        assert isinstance(dropped, list)

        X_valid_feat = X_valid.select(feature_cols)
        y_train_vals = y_train["label"].drop_nulls()
        y_valid_vals = y_valid["label"].drop_nulls()
        common_train = min(len(X_scaled), len(y_train_vals))
        common_valid = min(len(X_valid_feat), len(y_valid_vals))

        # ---- Training ----
        params = {
            "num_leaves": 8,
            "n_estimators": 30,
            "early_stopping_rounds": 10,
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

        assert booster.num_trees() > 0, "No trees trained"

        # ---- Serialization ----
        models_dir = tmp_path / "models"
        version = "20260101_120000"
        model_dir = save_model(
            booster=booster,
            scaler=scaler,
            metadata={"train_start": "2023-01-01", "max_lookback": 120},
            version=version,
            models_dir=models_dir,
            dropped_features=dropped,
            feature_names=scaler.feature_names,
        )

        # Verify all 5 files
        required = [
            "model.pkl",
            "scaler.json",
            "dropped_features.json",
            "feature_names.json",
            "metadata.json",
        ]
        for fname in required:
            assert (model_dir / fname).exists(), f"Missing {fname}"

        # Verify round-trip load
        import lightgbm as lgb

        from trader_off.data.preprocess import StandardScaler

        artifact = load_model(version=version, models_dir=models_dir)
        assert isinstance(artifact.booster, lgb.Booster), (
            f"Expected Booster, got {type(artifact.booster)}"
        )
        assert isinstance(artifact.scaler, StandardScaler), (
            f"Expected StandardScaler, got {type(artifact.scaler)}"
        )
        assert len(artifact.feature_names) > 0
        assert isinstance(artifact.metadata, dict)

    def test_ac_fr0800_03_version_exists_error(self, tmp_path):
        """AC-FR0800-03: Duplicate version raises ModelVersionExistsError."""
        from trader_off.utils.exceptions import ModelVersionExistsError

        data = _make_ohlcv_data(n_assets=3, n_days=200)
        data = compute_momentum_features(data)
        data = compute_volatility_features(data)
        data = compute_volume_features(data)
        label_df = build_labels(data.select(["asset", "date", "close"]), horizon=5)
        data = data.join(label_df, on=["asset", "date"], how="left")
        data = data.filter(pl.col("label").is_not_null())

        feature_cols = [
            "ret_5",
            "ret_10",
            "ret_20",
            "ret_60",
            "vol_10",
            "vol_20",
            "vol_60",
            "turnover_5",
            "turnover_10",
            "turnover_20",
            "vp_corr_5",
            "vp_corr_10",
            "vp_corr_20",
        ]
        X = data.select(["asset", "date"] + feature_cols)

        X_scaled, scaler, dropped = fit_scaler_and_impute(X)
        y_vals = data["label"].drop_nulls()

        params = {"num_leaves": 4, "n_estimators": 10, "verbose": -1}
        booster = train_model(
            X_train=X_scaled.select(scaler.feature_names),
            y_train=pl.Series("label", y_vals.to_list()),
            X_valid=X_scaled.head(20).select(scaler.feature_names),
            y_valid=pl.Series("label", y_vals.head(20).to_list()),
            params=params,
        )

        models_dir = tmp_path / "models"
        version = "20260101_120000"

        # First save succeeds
        save_model(
            booster=booster,
            scaler=scaler,
            metadata={},
            version=version,
            models_dir=models_dir,
            dropped_features=dropped,
            feature_names=scaler.feature_names,
        )

        # Second save with same version must fail
        with pytest.raises(ModelVersionExistsError, match="already exists"):
            save_model(
                booster=booster,
                scaler=scaler,
                metadata={},
                version=version,
                models_dir=models_dir,
                dropped_features=dropped,
                feature_names=scaler.feature_names,
            )
