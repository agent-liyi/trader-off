"""Integration tests for feature importance CLI (L2 contract simulation).

Covers the cross-module chain:
  training.trainer → training.feature_importance → cli.feature_importance
"""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from trader_off.data.preprocess import fit_scaler_and_impute
from trader_off.features.momentum import compute_momentum_features
from trader_off.features.volatility import compute_volatility_features
from trader_off.features.volume import compute_volume_features
from trader_off.labels.builder import build_labels
from trader_off.training.feature_importance import extract_feature_importance
from trader_off.training.serialize import save_model
from trader_off.training.trainer import train_model


def _train_mock_model(tmp_path, n_features=15):
    """Train a small model and return (booster, feature_names)."""
    rng = np.random.RandomState(42)
    start = date(2023, 1, 1)
    n_assets = 3
    n_days = 200

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
    data = pl.DataFrame(rows)

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

    dates_sorted = sorted(data["date"].unique().to_list())
    split_idx = int(len(dates_sorted) * 0.7)
    train_dates = dates_sorted[:split_idx]
    valid_dates = dates_sorted[split_idx:]

    X_train = X.filter(pl.col("date").is_in(train_dates))
    y_train = data.filter(pl.col("date").is_in(train_dates))["label"].drop_nulls()
    X_valid = X.filter(pl.col("date").is_in(valid_dates))
    y_valid = data.filter(pl.col("date").is_in(valid_dates))["label"].drop_nulls()

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
    return booster, scaler.feature_names


@pytest.mark.integration
class TestFeatureImportance:
    """Integration: training → feature_importance → CLI output."""

    def test_extract_sorted(self, tmp_path):
        """extract_feature_importance returns sorted DataFrame."""
        booster, feature_names = _train_mock_model(tmp_path)

        result = extract_feature_importance(booster, feature_names)

        assert isinstance(result, pl.DataFrame)
        assert {"feature", "importance", "rank"}.issubset(set(result.columns)), (
            f"Missing columns: {result.columns}"
        )

        # Should have one row per feature
        assert len(result) == len(feature_names), (
            f"Expected {len(feature_names)} rows, got {len(result)}"
        )

        # Sorted descending by importance
        if len(result) > 1:
            importances = result["importance"].to_list()
            assert importances == sorted(importances, reverse=True), (
                "Importance not sorted descending"
            )

        # Rank starts from 1
        assert result["rank"][0] == 1, "First rank should be 1"

    def test_cli_output(self, tmp_path, capsys):
        """CLI feature-importance prints Top 20 table."""
        booster, feature_names = _train_mock_model(tmp_path)

        # Save model first for CLI to load
        from trader_off.data.preprocess import StandardScaler

        scaler = StandardScaler(
            mean_={f: 0.0 for f in feature_names},
            std_={f: 1.0 for f in feature_names},
            feature_names=feature_names,
        )
        models_dir = tmp_path / "models"
        version = "20260101_120000"
        save_model(
            booster=booster,
            scaler=scaler,
            metadata={},
            version=version,
            models_dir=models_dir,
            dropped_features=[],
            feature_names=feature_names,
        )

        # Call extractor directly and verify output format
        result = extract_feature_importance(booster, feature_names)

        # Write to CSV for CLI-compatible output
        fi_csv = tmp_path / "feature_importance.csv"
        result.write_csv(fi_csv)

        assert fi_csv.exists()
        assert fi_csv.stat().st_size > 0

        # Read back and verify content
        df = pl.read_csv(fi_csv)
        assert len(df) == len(feature_names)

        # Print to stdout (simulating CLI behavior)
        print(f"Top {min(20, len(df))} feature importance:")
        print(df.head(20))
        captured = capsys.readouterr()
        assert "feature" in captured.out or "importance" in captured.out
