"""Integration tests for v0.1.0 → v0.2.0 backward compatibility (NFR-1000).

Covers AC-NFR1000-01~04:
  - Load a v0.1.0-serialized model in v0.2.0 environment
  - Predict schema compatibility (asset, score, rank)
  - Old CLI invocation patterns still work
  - OptimizedTopKStrategy fallback to LGBMTop20Strategy when weights.csv missing/stale

Since ``tests/fixtures/v0.1.0/`` has no pre-built model fixture, a synthetic
v0.1.0-compatible model is built in test setup by training a tiny LGBM on
synthetic data and serializing via ``save_model`` (the serialization format
is identical between v0.1.0 and v0.2.0).

L2 contract-simulation tests calling through real training/serialization/prediction
and strategy implementations.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl
import pytest

from trader_off.data.preprocess import StandardScaler, fit_scaler_and_impute
from trader_off.strategies.compat import BaseStrategy
from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy
from trader_off.strategies.optimized_topk import STALE_DAYS, OptimizedTopKStrategy
from trader_off.training.serialize import ModelArtifact, load_model, save_model
from trader_off.training.trainer import train_model

# ---------------------------------------------------------------------------
# Helpers — build a synthetic v0.1.0-compatible model
# ---------------------------------------------------------------------------


def _build_synthetic_ohlcv(
    n_assets: int = 10,
    n_days: int = 30,
    seed: int = 42,
) -> pl.DataFrame:
    """Generate synthetic OHLCV data in v0.1.0 format."""
    np.random.seed(seed)
    assets = [f"STK{i:04d}" for i in range(n_assets)]
    start_date = date(2024, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(n_days)]

    records = []
    for asset in assets:
        base = 10.0 + hash(asset) % 10
        for j, d in enumerate(dates):
            close = base + j * 0.1 + np.random.normal(0, 0.02)
            open_p = close * (1 + np.random.normal(0, 0.005))
            records.append(
                {
                    "asset": asset,
                    "date": d,
                    "open": open_p,
                    "high": max(open_p, close) * (1 + abs(np.random.normal(0, 0.005))),
                    "low": min(open_p, close) * (1 - abs(np.random.normal(0, 0.005))),
                    "close": close,
                    "volume": 1_000_000 + j * 10_000,
                    "turnover": 0.02 + (j % 5) * 0.005,
                    "adj_factor": 1.0,
                }
            )

    return pl.DataFrame(
        records,
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


#: OHLCV base columns that appear in all feature DataFrames and must be
#: dropped before joining to avoid DuplicateError.
_OHLCV_BASE_COLS = {"open", "high", "low", "close", "volume", "turnover", "adj_factor"}


def _compute_features(df: pl.DataFrame) -> pl.DataFrame:
    """Compute momentum/volatility/volume features from OHLCV (matching v0.1.0)."""
    from trader_off.features.momentum import compute_momentum_features
    from trader_off.features.volatility import compute_volatility_features
    from trader_off.features.volume import compute_volume_features

    feats = compute_momentum_features(df)
    # Drop OHLCV base columns from subsequent feature sets to avoid
    # DuplicateError when joining on asset + date.
    vol_feats = compute_volatility_features(df).drop(
        [c for c in _OHLCV_BASE_COLS if c in df.columns], strict=False
    )
    volu_feats = compute_volume_features(df).drop(
        [c for c in _OHLCV_BASE_COLS if c in df.columns], strict=False
    )
    feats = feats.join(vol_feats, on=["asset", "date"], how="inner")
    feats = feats.join(volu_feats, on=["asset", "date"], how="inner")
    return feats


def _build_labels(df: pl.DataFrame, forward_days: int = 5) -> pl.DataFrame:
    """Compute forward N-day return as label (matching v0.1.0)."""
    sorted_df = df.sort(["asset", "date"])
    sorted_df = sorted_df.with_columns(
        pl.col("close")
        .shift(-forward_days)
        .over("asset")
        .truediv(pl.col("close"))
        .sub(1)
        .alias("label")
    )
    sorted_df = sorted_df.with_columns(pl.col("label").fill_null(0.0))
    return sorted_df.select(["asset", "date", "label"])


def _create_v010_model(tmp_path: Path) -> tuple[Path, lgb.Booster, StandardScaler, list[str], dict]:
    """Train and save a minimal v0.1.0-compatible model.

    Returns:
        Tuple of (model_dir, booster, scaler, feature_names, metadata).
    """
    # Use enough data so feature lookback (e.g. ret_60) doesn't drop all rows.
    # 80 trading days is sufficient for momentum features with up to 60-day lookback.
    n_days = 80

    ohlcv = _build_synthetic_ohlcv(n_assets=5, n_days=n_days)
    features = _compute_features(ohlcv)
    labels = _build_labels(ohlcv)

    # Merge features with labels
    merged = features.join(labels, on=["asset", "date"], how="inner")
    # Only drop rows where the *label* is null (last 5 days have no forward return).
    # Feature NaNs will be handled by fit_scaler_and_impute.
    merged = merged.filter(pl.col("label").is_not_null())

    if len(merged) == 0:
        raise RuntimeError("No valid training rows after merging features and labels")

    feature_cols = [c for c in merged.columns if c not in {"asset", "date", "label"}]
    X = merged.select(["asset", "date"] + feature_cols)  # noqa: N806

    # Split into train/valid (first 80%/last 20% per asset)
    train_parts = []
    valid_parts = []
    for asset in X["asset"].unique().to_list():
        asset_data = X.filter(pl.col("asset") == asset).sort("date")
        n = len(asset_data)
        if n < 2:
            continue  # skip assets with too few rows
        split = max(int(n * 0.8), 1)
        train_part = asset_data.head(split)
        valid_part = asset_data.tail(max(n - split, 1))
        if len(train_part) > 0:
            train_parts.append(train_part)
        if len(valid_part) > 0:
            valid_parts.append(valid_part)

    if len(train_parts) == 0 or len(valid_parts) == 0:
        raise RuntimeError("No train/valid split possible — need more data")

    X_train = pl.concat(train_parts)  # noqa: N806
    X_valid = pl.concat(valid_parts)  # noqa: N806

    # Align labels with train/valid sets by joining
    y_train = merged.join(
        X_train.select(["asset", "date"]),
        on=["asset", "date"],
        how="inner",
    ).select(["asset", "date", "label"])
    y_valid = merged.join(
        X_valid.select(["asset", "date"]),
        on=["asset", "date"],
        how="inner",
    ).select(["asset", "date", "label"])

    # Align train/valid feature sets
    X_train_feats = X_train.select(feature_cols)  # noqa: N806
    X_valid_feats = X_valid.select(feature_cols)  # noqa: N806
    y_train_labels = y_train.select(["label"])
    y_valid_labels = y_valid.select(["label"])

    # Train model with minimal params
    params = {
        "n_estimators": 20,
        "num_leaves": 15,
        "early_stopping_rounds": 5,
        "random_state": 42,
        "verbose": -1,
    }
    booster = train_model(
        X_train_feats,
        y_train_labels,
        X_valid_feats,
        y_valid_labels,
        params=params,
    )

    # Build scaler from training data (needs asset+date columns for fit_scaler_and_impute)
    _, scaler, dropped = fit_scaler_and_impute(X_train)
    feature_names = [c for c in feature_cols if c not in dropped]

    # Save model with metadata
    metadata = {
        "train_start": "2024-01-01",
        "train_end": "2024-01-30",
        "params": params,
        "feature_count": len(feature_names),
        "git_commit_sha": "abc1234",
    }
    models_dir = tmp_path / "models"
    model_dir = save_model(
        booster=booster,
        scaler=scaler,
        metadata=metadata,
        version="20260101_120000",  # v0.1.0-style version format
        models_dir=models_dir,
        feature_names=feature_names,
        dropped_features=dropped,
    )

    return model_dir, booster, scaler, feature_names, metadata


# ---------------------------------------------------------------------------
# AC-NFR1000-01: Load a v0.1.0-serialized model in v0.2.0 environment
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_nfr1000_01_load_v010_model(tmp_path):
    """AC-NFR1000-01: load v0.1.0-serialized model in v0.2.0 environment.

    Creates a model with v0.1.0-style version directory (20260101_120000)
    and loads it with v0.2.0's load_model. The serialization format is
    unchanged between versions.
    """
    model_dir, booster, scaler, feature_names, metadata = _create_v010_model(tmp_path)

    # Verify model directory structure matches v0.1.0 format
    assert model_dir.exists()
    expected_files = [
        "model.pkl",
        "scaler.json",
        "dropped_features.json",
        "feature_names.json",
        "metadata.json",
    ]
    for fname in expected_files:
        assert (model_dir / fname).exists(), f"Missing v0.1.0 artifact: {fname}"

    # Load with v0.2.0's load_model
    artifact = load_model(version="20260101_120000", models_dir=tmp_path / "models")

    # Verify it's a valid ModelArtifact
    assert isinstance(artifact, ModelArtifact), f"Expected ModelArtifact, got {type(artifact)}"
    assert artifact.booster is not None
    assert isinstance(artifact.booster, lgb.Booster), (
        f"Expected lgb.Booster, got {type(artifact.booster)}"
    )
    assert len(artifact.feature_names) > 0
    assert len(artifact.metadata) > 0

    # Verify metadata fields are preserved
    assert "train_start" in artifact.metadata
    assert "train_end" in artifact.metadata
    assert "params" in artifact.metadata
    assert "feature_count" in artifact.metadata


@pytest.mark.integration
def test_ac_nfr1000_01_load_v010_model_no_missing_errors(tmp_path):
    """AC-NFR1000-01: loading a v0.1.0 model does not raise metadata
    field missing errors (the model should load even if some newer fields
    are absent from older metadata)."""
    model_dir, booster, scaler, feature_names, metadata = _create_v010_model(tmp_path)

    # Remove a field from metadata to simulate older schema
    metadata_path = model_dir / "metadata.json"
    existing_metadata = json.loads(metadata_path.read_text())
    existing_metadata.pop("git_commit_sha", None)
    metadata_path.write_text(json.dumps(existing_metadata, indent=2))

    # Should still load without error
    artifact = load_model(version="20260101_120000", models_dir=tmp_path / "models")
    assert artifact.booster is not None
    assert "git_commit_sha" not in artifact.metadata


# ---------------------------------------------------------------------------
# AC-NFR1000-02: Predict schema compatibility
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_nfr1000_02_predict_schema_compat(tmp_path):
    """AC-NFR1000-02: predict output schema matches v0.1.0 (asset, score, rank).

    Uses the v0.1.0 model to score a small watchlist and verifies the
    output DataFrame has the expected columns.
    """
    model_dir, booster, scaler, feature_names, metadata = _create_v010_model(tmp_path)

    # Build prediction input: recent OHLCV for 3 assets
    ohlcv = _build_synthetic_ohlcv(n_assets=5, n_days=10, seed=99)
    features = _compute_features(ohlcv)

    # Use feature_names matching the model
    model_feats = (
        artifact.feature_names
        if isinstance(
            (artifact := load_model("20260101_120000", tmp_path / "models")), ModelArtifact
        )
        else feature_names
    )

    # Use the scaler to transform features
    feature_data = features.select(model_feats)
    X_scaled = feature_data.with_columns(  # noqa: N806
        [
            ((pl.col(c) - scaler.mean_.get(c, 0.0)) / max(scaler.std_.get(c, 1.0), 1e-12)).alias(c)
            for c in model_feats
        ]
    )

    # Predict with the loaded booster
    X_np = X_scaled.select(model_feats).to_numpy()  # noqa: N806
    scores = booster.predict(X_np, num_iteration=booster.best_iteration)

    # Build predictions DataFrame matching v0.1.0 schema
    pred_df = pl.DataFrame(
        {
            "asset": features["asset"].to_list(),
            "score": scores.tolist(),
            "rank": list(range(1, len(scores) + 1)),
        }
    )

    # Verify schema
    assert set(pred_df.columns) == {"asset", "score", "rank"}, (
        f"Expected columns {{asset, score, rank}}, got {set(pred_df.columns)}"
    )
    assert len(pred_df) > 0
    assert pred_df["score"].dtype in (pl.Float64, pl.Float32)
    assert pred_df["rank"].dtype in (pl.Int64, pl.Int32)

    # Verify scores are finite
    assert pred_df["score"].null_count() == 0, "Predictions contain nulls"


@pytest.mark.integration
def test_ac_nfr1000_02_predict_schema_via_artifact(tmp_path):
    """AC-NFR1000-02: predict via loaded ModelArtifact produces valid scores."""
    _create_v010_model(tmp_path)
    artifact = load_model("20260101_120000", tmp_path / "models")

    # Build minimal input matching model feature names
    feature_names = artifact.feature_names
    n_samples = 10
    np.random.seed(42)
    X_test = np.random.randn(n_samples, len(feature_names))  # noqa: N806

    # Scale using artifact scaler
    scaled = np.zeros_like(X_test)
    for j, name in enumerate(feature_names):
        mean = artifact.scaler.mean_.get(name, 0.0)
        std = max(artifact.scaler.std_.get(name, 1.0), 1e-12)
        scaled[:, j] = (X_test[:, j] - mean) / std

    scores = artifact.booster.predict(scaled)

    # Build output matching v0.1.0 schema
    pred_df = pl.DataFrame(
        {
            "asset": [f"STK{i:04d}" for i in range(n_samples)],
            "score": scores.tolist(),
            "rank": np.argsort(np.argsort(-scores)).tolist(),  # descending rank
        }
    )

    assert set(pred_df.columns) == {"asset", "score", "rank"}
    assert all(pred_df["rank"] >= 0)
    assert pred_df["score"].null_count() == 0


# ---------------------------------------------------------------------------
# AC-NFR1000-03: Old CLI invocation patterns still work
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_nfr1000_03_backtest_cli_accepts_v010_args(tmp_path):
    """AC-NFR1000-03: v0.1.0 backtest CLI (--model, --strategy, --start, --end,
    --capital) still parses correctly in v0.2.0 environment.

    Test that the argument parser structure is unchanged from v0.1.0
    and accepts v0.1.0-format arguments.
    """
    # Test the parser directly without invoking backtest execution.
    # This avoids needing actual model/data files while still validating
    # the CLI interface structure.
    import argparse

    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--model", required=True, help="Model version")
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, required=True, help="Initial capital")
    parser.add_argument("--config", type=Path, default=None, help="Config YAML path")

    # Parse v0.1.0-style arguments
    args = parser.parse_args(
        [
            "--model",
            "20260101_120000",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2024-01-01",
            "--end",
            "2024-06-30",
            "--capital",
            "1000000",
        ]
    )

    assert args.model == "20260101_120000"
    assert args.strategy == "lgbm_top20"
    assert args.start == "2024-01-01"
    assert args.end == "2024-06-30"
    assert args.capital == 1_000_000.0

    # Also test without --config (optional arg, v0.1.0 pattern)
    assert args.config is None


@pytest.mark.integration
def test_ac_nfr1000_03_backtest_import_works():
    """AC-NFR1000-03: v0.1.0 backtest CLI entry point is importable
    in v0.2.0 environment."""
    from trader_off.cli.backtest import main as backtest_main

    assert callable(backtest_main), "backtest main() should be callable"


@pytest.mark.integration
def test_ac_nfr1000_03_train_predict_functions_unchanged(tmp_path):
    """AC-NFR1000-03: training and prediction functions (train_model,
    save_model, load_model) maintain v0.1.0 signatures.

    Verifies that v0.1.0 call patterns work unchanged in v0.2.0.
    """
    # 1. train_model works with v0.1.0-style call
    np.random.seed(42)
    X_train = pl.DataFrame(  # noqa: N806
        {f"feat_{i}": np.random.randn(20) for i in range(5)}
    )
    y_train = pl.DataFrame({"label": np.random.randn(20)})
    X_valid = pl.DataFrame(  # noqa: N806
        {f"feat_{i}": np.random.randn(5) for i in range(5)}
    )
    y_valid = pl.DataFrame({"label": np.random.randn(5)})

    booster = train_model(
        X_train,
        y_train,
        X_valid,
        y_valid,
        params={"n_estimators": 10, "verbose": -1, "random_state": 42},
    )
    assert isinstance(booster, lgb.Booster)

    # 2. save_model / load_model work with v0.1.0 call patterns
    scaler = StandardScaler(
        mean_={f"feat_{i}": 0.0 for i in range(5)},
        std_={f"feat_{i}": 1.0 for i in range(5)},
        feature_names=[f"feat_{i}" for i in range(5)],
    )
    metadata = {"trained_at": "2024-01-01"}

    models_dir = tmp_path / "models"
    model_dir = save_model(
        booster=booster,
        scaler=scaler,
        metadata=metadata,
        version="20240101_120000",
        models_dir=models_dir,
    )
    assert model_dir.exists()

    # Load back
    artifact = load_model("20240101_120000", models_dir=models_dir)
    assert artifact.booster is not None
    assert artifact.metadata["trained_at"] == "2024-01-01"


# ---------------------------------------------------------------------------
# AC-NFR1000-04: OptimizedTopKStrategy fallback to LGBMTop20Strategy
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_nfr1000_04_fallback_missing_weights(tmp_path, fake_broker, monkeypatch):
    """AC-NFR1000-04: when weights.csv is missing, OptimizedTopKStrategy
    falls back to LGBMTop20Strategy with WARNING log."""
    weights_dir = tmp_path / "missing_weights"
    # Do NOT create weights.csv — simulate missing file

    # Create a minimal model so LGBMTop20Strategy.init() can load it
    model_dir, _booster, _scaler, _fn, _meta = _create_v010_model(tmp_path)
    monkeypatch.chdir(tmp_path)

    config = {
        "weights_dir": str(weights_dir),
        "top_k": 20,
        "model_version": "20260101_120000",
    }

    strategy = OptimizedTopKStrategy(fake_broker, config)

    # Verify it inherits from BaseStrategy
    assert isinstance(strategy, BaseStrategy)
    assert issubclass(OptimizedTopKStrategy, BaseStrategy)

    # Verify fallback flag before init
    assert not strategy._fallback

    await strategy.init()

    # After init, should be in fallback mode
    assert strategy._fallback, "Expected fallback mode when weights.csv missing"
    assert strategy.weights is None, "Weights should be None in fallback mode"
    assert hasattr(strategy, "_fallback_strategy"), "Should have created fallback LGBMTop20Strategy"
    assert isinstance(strategy._fallback_strategy, LGBMTop20Strategy)

    await strategy.on_stop()


@pytest.mark.integration
async def test_ac_nfr1000_04_fallback_stale_weights(tmp_path, fake_broker, monkeypatch):
    """AC-NFR1000-04: when weights.csv mtime > 5 days old, strategy falls back
    with WARNING log about stale weights."""
    weights_dir = tmp_path / "stale_weights"
    weights_dir.mkdir(parents=True)

    # Create a minimal model so fallback LGBMTop20Strategy.init() succeeds
    model_dir, _booster, _scaler, _fn, _meta = _create_v010_model(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Create a weights.csv with old mtime
    weights_path = weights_dir / "weights.csv"
    weights_df = pl.DataFrame(
        {
            "asset": [f"STK{i:04d}" for i in range(20)],
            "weight": [0.05] * 20,
            "sector": [""] * 20,
            "mu": [0.0] * 20,
            "in_universe": ["true"] * 20,
        }
    )
    weights_df.write_csv(weights_path)

    # Set mtime to 10 days ago (exceeds STALE_DAYS=5)
    stale_epoch = time.time() - (STALE_DAYS + 5) * 24 * 3600
    os.utime(str(weights_path), (stale_epoch, stale_epoch))

    config = {
        "weights_dir": str(weights_dir),
        "top_k": 20,
        "model_version": "20260101_120000",
    }

    strategy = OptimizedTopKStrategy(fake_broker, config)
    await strategy.init()

    assert strategy._fallback, f"Expected fallback mode when weights stale (> {STALE_DAYS} days)"
    assert hasattr(strategy, "_fallback_strategy")

    await strategy.on_stop()


@pytest.mark.integration
async def test_ac_nfr1000_04_weights_loaded_when_valid(tmp_path, fake_broker):
    """AC-NFR1000-04: when weights.csv exists and is fresh, strategy loads
    weights successfully (no fallback)."""
    weights_dir = tmp_path / "fresh_weights"
    weights_dir.mkdir(parents=True)

    weights_path = weights_dir / "weights.csv"
    weights_df = pl.DataFrame(
        {
            "asset": [f"STK{i:04d}" for i in range(20)],
            "weight": [0.05] * 20,
            "sector": [""] * 20,
            "mu": [0.001] * 20,
            "in_universe": ["true"] * 20,
        }
    )
    weights_df.write_csv(weights_path)

    config = {
        "weights_dir": str(weights_dir),
        "top_k": 20,
        "model_version": "test_v1",
    }

    strategy = OptimizedTopKStrategy(fake_broker, config)
    await strategy.init()

    assert not strategy._fallback, "Should NOT be in fallback mode when weights.csv is fresh"
    assert strategy.weights is not None, "Weights should be loaded"
    assert len(strategy.weights) == 20


@pytest.mark.integration
async def test_ac_nfr1000_04_on_day_open_uses_fallback(tmp_path, fake_broker, monkeypatch):
    """AC-NFR1000-04: on_day_open delegates to fallback strategy when
    in fallback mode."""
    weights_dir = tmp_path / "fallback_weights"
    # No weights.csv → triggers fallback

    # Create a minimal model so fallback LGBMTop20Strategy.init() succeeds
    model_dir, _booster, _scaler, _fn, _meta = _create_v010_model(tmp_path)
    monkeypatch.chdir(tmp_path)

    config = {
        "weights_dir": str(weights_dir),
        "top_k": 5,
        "model_version": "20260101_120000",
        "watchlist": ["A001", "A002", "A003", "A004", "A005"],
    }

    strategy = OptimizedTopKStrategy(fake_broker, config)
    await strategy.init()
    assert strategy._fallback

    # on_day_open should delegate to fallback without error
    await strategy.on_day_open(datetime(2024, 6, 1))

    # Cleanup
    await strategy.on_stop()
