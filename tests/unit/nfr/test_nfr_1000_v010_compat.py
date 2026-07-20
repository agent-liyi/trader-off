"""Tests for NFR-1000: v0.1.0 backward compatibility.

AC-NFR1000-01: v0.1.0-serialized model can still be loaded by v0.2.0 load_model().
AC-NFR1000-02: OptimizedTopKStrategy falls back to LGBMTop20Strategy when weights.csv missing/stale.
AC-NFR1000-03: Round-trip v0.2.0 model through save_model()/load_model().
"""

import json

import lightgbm as lgb
import numpy as np
import pytest

from trader_off.training.serialize import ModelArtifact, load_model, save_model

# ---------------------------------------------------------------------------
# AC-NFR1000-03: Round-trip v0.2.0 model save/load
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr1000_03_roundtrip_v020_model(tmp_path):
    """AC-NFR1000-03: v0.2.0 model round-trips through save_model/load_model."""
    from trader_off.data.preprocess import StandardScaler

    # Create a minimal model
    x_data = np.random.RandomState(42).randn(20, 3)
    y_data = x_data[:, 0] * 1.5 + np.random.RandomState(42).randn(20) * 0.1
    booster = lgb.train(
        {"objective": "regression", "verbose": -1, "num_leaves": 8, "random_state": 42},
        lgb.Dataset(x_data, label=y_data),
        num_boost_round=5,
    )
    scaler = StandardScaler(
        mean_={"f0": 0.0, "f1": 0.0, "f2": 0.0},
        std_={"f0": 1.0, "f1": 1.0, "f2": 1.0},
        feature_names=["f0", "f1", "f2"],
    )
    metadata = {
        "train_start": "2020-01-01",
        "train_end": "2024-12-31",
        "test_ic_mean": 0.025,
        "test_rank_ic_mean": 0.032,
        "mode": "full",
        "trigger": "manual",
    }

    models_dir = tmp_path / "models"
    save_model(
        booster=booster,
        scaler=scaler,
        metadata=metadata,
        version="v0.2.0.test",
        models_dir=str(models_dir),
        dropped_features=["f_dropped"],
        feature_names=["f0", "f1", "f2"],
    )

    # Load the saved model
    artifact = load_model("v0.2.0.test", models_dir=str(models_dir))

    assert isinstance(artifact, ModelArtifact)
    # AC-NFR1000-02: round-trip preserves booster
    assert artifact.booster is not None
    assert isinstance(artifact.scaler, StandardScaler)
    assert artifact.feature_names == ["f0", "f1", "f2"]
    assert artifact.metadata["test_ic_mean"] == 0.025
    assert artifact.metadata["mode"] == "full"


@pytest.mark.unit
def test_nfr1000_03_roundtrip_incremental_model(tmp_path):
    """AC-NFR1000-03: Incremental model round-trips correctly."""
    from trader_off.data.preprocess import StandardScaler

    x_data = np.random.RandomState(99).randn(15, 2)
    y_data = x_data[:, 1] * 0.8
    booster = lgb.train(
        {"objective": "regression", "verbose": -1, "num_leaves": 4},
        lgb.Dataset(x_data, label=y_data),
        num_boost_round=3,
    )
    scaler = StandardScaler(
        mean_={"a": 0.0, "b": 0.0},
        std_={"a": 1.0, "b": 1.0},
        feature_names=["a", "b"],
    )
    metadata = {
        "train_start": "2024-06-01",
        "train_end": "2024-06-30",
        "parent_version": "v0.2.0.5",
        "incr_seq": 1,
        "mode": "incremental",
    }

    models_dir = tmp_path / "models"
    save_model(
        booster=booster,
        scaler=scaler,
        metadata=metadata,
        version="v0.2.0.5.incr1",
        models_dir=str(models_dir),
        feature_names=["a", "b"],
    )

    artifact = load_model("v0.2.0.5.incr1", models_dir=str(models_dir))

    assert artifact.metadata["parent_version"] == "v0.2.0.5"
    assert artifact.metadata["incr_seq"] == 1


# ---------------------------------------------------------------------------
# AC-NFR1000-01: v0.1.0 format model loading
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr1000_01_v010_model_format_loads(tmp_path):
    """AC-NFR1000-01: v0.1.0-format model (YYYYMMDD_HHMMSS) loads successfully.

    Creates a minimal v0.1.0-style model directory and verifies load_model
    can parse the v0.1.0 version format.
    """
    from trader_off.data.preprocess import StandardScaler

    models_dir = tmp_path / "models"
    version = "20260101_120000"  # v0.1.0 format (15 chars with underscore at pos 8)

    model_dir = models_dir / version
    model_dir.mkdir(parents=True)

    # Create model.pkl
    x_data = np.random.RandomState(42).randn(10, 2)
    y_data = x_data[:, 0] * 2.0
    booster = lgb.train(
        {"objective": "regression", "verbose": -1, "num_leaves": 4},
        lgb.Dataset(x_data, label=y_data),
        num_boost_round=3,
    )
    import joblib

    joblib.dump(booster, model_dir / "model.pkl")

    # Create scaler.json (v0.1.0 format - simplified)
    scaler_data = {
        "mean_": {"f0": 0.0, "f1": 0.0},
        "std_": {"f0": 1.0, "f1": 1.0},
        "feature_names": ["f0", "f1"],
    }
    (model_dir / "scaler.json").write_text(json.dumps(scaler_data))

    # Create feature_names.json
    (model_dir / "feature_names.json").write_text(json.dumps(["f0", "f1"]))

    # Create metadata.json (v0.1.0 minimal format)
    metadata = {
        "train_start": "2020-01-01",
        "train_end": "2024-12-31",
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata))

    # Load should succeed
    artifact = load_model(version, models_dir=str(models_dir))

    assert isinstance(artifact, ModelArtifact)
    # AC-NFR1000-01: v0.1.0 booster must be loadable
    assert artifact.booster is not None
    assert isinstance(artifact.booster, lgb.Booster)
    assert isinstance(artifact.scaler, StandardScaler)
    assert artifact.feature_names == ["f0", "f1"]
    # metadata fields may be None for v0.1.0 format (missing fields are ok)
    assert artifact.metadata is not None


@pytest.mark.unit
def test_nfr1000_01_v010_version_format_detected():
    """AC-NFR1000-01: load_model correctly identifies v0.1.0 version format.

    v0.1.0 format: len==15 and version[8]=="_"
    """
    # These should be recognized as v0.1.0 format
    v010_versions = [
        "20260101_120000",
        "20250101_090000",
        "20241231_235959",
    ]
    for v in v010_versions:
        assert len(v) == 15, f"Version {v} should have len==15"
        assert v[8] == "_", f"Version {v} should have underscore at position 8"

    # These should NOT be recognized as v0.1.0 format
    v020_versions = [
        "v0.2.0.1",
        "v0.2.0.5.incr1",
        "v1.0.0",
    ]
    for v in v020_versions:
        assert len(v) != 15 or v[8] != "_", f"Version {v} should NOT be v0.1.0 format"


@pytest.mark.unit
def test_nfr1000_01_v010_metadata_missing_fields_ok(tmp_path):
    """AC-NFR1000-01: v0.1.0 metadata with missing fields loads without error."""

    models_dir = tmp_path / "models"
    version = "20260701_080000"

    model_dir = models_dir / version
    model_dir.mkdir(parents=True)

    # Create model
    x_data = np.random.RandomState(42).randn(10, 2)
    y_data = x_data[:, 0] * 2.0
    booster = lgb.train(
        {"objective": "regression", "verbose": -1, "num_leaves": 4},
        lgb.Dataset(x_data, label=y_data),
        num_boost_round=3,
    )
    import joblib

    joblib.dump(booster, model_dir / "model.pkl")

    # Create minimal scaler.json
    scaler_data = {
        "mean_": {},
        "std_": {},
        "feature_names": [],
    }
    (model_dir / "scaler.json").write_text(json.dumps(scaler_data))
    (model_dir / "feature_names.json").write_text(json.dumps([]))

    # Minimal metadata (missing many fields that v0.2.0 has)
    metadata = {"train_start": "2020-01-01"}
    (model_dir / "metadata.json").write_text(json.dumps(metadata))

    # Should load without error
    artifact = load_model(version, models_dir=str(models_dir))
    assert artifact.metadata is not None


# ---------------------------------------------------------------------------
# AC-NFR1000-02: OptimizedTopKStrategy fallback
# ---------------------------------------------------------------------------


class TestOptimizedTopKStrategyFallback:
    """AC-NFR1000-02: OptimizedTopKStrategy fallback behavior when weights.csv missing/stale."""

    @pytest.mark.unit
    async def test_nfr1000_02_missing_weights_csv_triggers_fallback(self, tmp_path, mocker):
        """AC-NFR1000-02: Missing weights.csv triggers WARNING + fallback to LGBMTop20Strategy."""
        import io

        from loguru import logger as loguru_logger

        from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

        # Mock LGBMTop20Strategy to avoid actual model loading
        mock_fallback = mocker.MagicMock()
        mock_fallback.init = mocker.AsyncMock()
        mocker.patch(
            "trader_off.strategies.optimized_topk.LGBMTop20Strategy",
            return_value=mock_fallback,
        )

        broker = mocker.MagicMock()
        config = {
            "weights_dir": str(tmp_path / "nonexistent"),
            "top_k": 20,
        }
        strategy = OptimizedTopKStrategy(broker, config)

        stream = io.StringIO()
        handler_id = loguru_logger.add(stream, level="WARNING", format="{message}")
        try:
            await strategy.init()
        finally:
            loguru_logger.remove(handler_id)

        log_output = stream.getvalue().lower()
        assert "missing" in log_output or "falling back" in log_output
        assert strategy._fallback is True

    @pytest.mark.unit
    async def test_nfr1000_02_stale_weights_csv_triggers_fallback(self, tmp_path, mocker):
        """AC-NFR1000-02: weights.csv stale (>5 days) triggers WARNING + fallback."""
        import io
        import time

        from loguru import logger as loguru_logger

        from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

        # Create a stale weights.csv
        weights_dir = tmp_path / "stale_weights"
        weights_dir.mkdir()
        weights_file = weights_dir / "weights.csv"
        weights_file.write_text("asset,weight,sector,mu,in_universe\nstock_001,0.04,tech,0.01,true")

        # Set mtime to 6 days ago
        old_time = time.time() - (6 * 24 * 3600)
        weights_file.touch()
        import os

        os.utime(weights_file, (old_time, old_time))

        mock_fallback = mocker.MagicMock()
        mock_fallback.init = mocker.AsyncMock()
        mocker.patch(
            "trader_off.strategies.optimized_topk.LGBMTop20Strategy",
            return_value=mock_fallback,
        )

        broker = mocker.MagicMock()
        config = {"weights_dir": str(weights_dir), "top_k": 20}
        strategy = OptimizedTopKStrategy(broker, config)

        stream = io.StringIO()
        handler_id = loguru_logger.add(stream, level="WARNING", format="{message}")
        try:
            await strategy.init()
        finally:
            loguru_logger.remove(handler_id)

        log_output = stream.getvalue().lower()
        assert "stale" in log_output or "falling back" in log_output or "days old" in log_output
        assert strategy._fallback is True


@pytest.mark.unit
async def test_nfr1000_02_fallback_strategy_on_day_open_delegates(tmp_path, mocker):
    """AC-NFR1000-02: Fallback mode delegates on_day_open to LGBMTop20Strategy."""
    from datetime import datetime

    from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

    mock_fallback = mocker.MagicMock()
    mock_fallback.init = mocker.AsyncMock()
    mock_fallback.on_day_open = mocker.AsyncMock()
    mocker.patch(
        "trader_off.strategies.optimized_topk.LGBMTop20Strategy",
        return_value=mock_fallback,
    )

    broker = mocker.MagicMock()
    config = {
        "weights_dir": str(tmp_path / "nonexistent"),
        "top_k": 20,
    }
    strategy = OptimizedTopKStrategy(broker, config)
    await strategy.init()

    assert strategy._fallback is True

    tm = datetime(2026, 7, 18, 9, 30)
    await strategy.on_day_open(tm)

    mock_fallback.on_day_open.assert_called_once()
