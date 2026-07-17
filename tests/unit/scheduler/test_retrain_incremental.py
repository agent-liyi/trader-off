"""Unit tests for FR-2200: incremental retrain via DefaultTrainerPort.train(mode='incremental').

AC coverage: AC-FR2200-01, AC-FR2200-02, AC-FR2200-03, AC-FR2200-04
"""

from pathlib import Path
from unittest.mock import patch

import lightgbm as lgb
import numpy as np
import pytest

from trader_off.data.preprocess import StandardScaler
from trader_off.scheduler.ports import DefaultTrainerPort
from trader_off.training.serialize import ModelArtifact, save_model

# ---------------------------------------------------------------------------
# Helper: create a parent model for incremental training tests
# ---------------------------------------------------------------------------


def _create_parent_model(models_dir: Path) -> tuple[str, lgb.Booster, StandardScaler]:
    """Create and save a base model to serve as parent for incremental training.

    Returns (version_str, booster, scaler) so tests can inspect them.
    """
    rng = np.random.RandomState(42)
    n_samples = 200
    X = rng.randn(n_samples, 3)  # noqa: N806
    y = X[:, 0] * 2.0 + X[:, 1] * 3.0 - X[:, 2] * 1.0 + rng.randn(n_samples) * 0.1

    params = {
        "objective": "regression",
        "num_leaves": 15,
        "learning_rate": 0.1,
        "random_state": 42,
        "verbose": -1,
    }

    train_data = lgb.Dataset(X[:150], label=y[:150])
    booster = lgb.train(params, train_data, num_boost_round=50)

    feature_names = [f"f{i}" for i in range(3)]
    scaler = StandardScaler(
        mean_={f"f{i}": float(X[:, i].mean()) for i in range(3)},
        std_={f"f{i}": max(float(X[:, i].std()), 1.0) for i in range(3)},
        feature_names=feature_names,
    )

    save_model(
        booster=booster,
        scaler=scaler,
        metadata={"mode": "full", "test_ic_mean": 0.5, "test_rank_ic_mean": 0.45},
        version="v0.2.0.5",
        models_dir=models_dir,
        feature_names=feature_names,
    )

    return "v0.2.0.5", booster, scaler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIncrementalRetrain:
    """FR-2200: Incremental retrain via lightGBM Booster.refit()."""

    # ------------------------------------------------------------------
    # AC-FR2200-01: Requires parent_version
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2200_01_incremental_requires_parent_version(self, tmp_path):
        """AC-FR2200-01: train(mode='incremental') raises error without parent_version."""
        port = DefaultTrainerPort(models_dir=tmp_path)
        with pytest.raises(ValueError, match="parent_version"):
            await port.train(mode="incremental")

    # ------------------------------------------------------------------
    # AC-FR2200-02: Uses Booster.refit() not LGBMRegressor.fit()
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2200_02_incremental_uses_refit_not_fit(self, tmp_path):
        """AC-FR2200-02: Incremental retrain uses Booster.refit(), not LGBMRegressor.fit().

        Creates a parent model, then patches both lightgbm.Booster.refit and
        lightgbm.LGBMRegressor.fit to verify:
        - refit was called exactly once
        - fit was NOT called
        """
        _create_parent_model(tmp_path)
        port = DefaultTrainerPort(models_dir=tmp_path)

        with (
            patch("lightgbm.Booster.refit") as mock_refit,
            patch("lightgbm.LGBMRegressor.fit") as mock_fit,
        ):
            _artifact = await port.train(
                mode="incremental",
                parent_version="v0.2.0.5",
                train_window_years=1,
            )

            # refit must have been called exactly once
            mock_refit.assert_called_once()
            # fit must NOT have been called
            mock_fit.assert_not_called()

    # ------------------------------------------------------------------
    # AC-FR2200-03: Returns ModelArtifact with parent metadata
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2200_03_incremental_returns_artifact_with_metadata(self, tmp_path):
        """AC-FR2200-03: Incremental training returns ModelArtifact with parent info."""
        _create_parent_model(tmp_path)
        port = DefaultTrainerPort(models_dir=tmp_path)

        artifact = await port.train(
            mode="incremental",
            parent_version="v0.2.0.5",
            train_window_years=1,
        )

        assert isinstance(artifact, ModelArtifact)
        assert isinstance(artifact.booster, lgb.Booster)
        assert artifact.booster.num_trees() > 0

        # Metadata must include parent chain info
        assert "parent_version" in artifact.metadata, (
            f"metadata missing parent_version: {list(artifact.metadata.keys())}"
        )
        assert artifact.metadata["parent_version"] == "v0.2.0.5"
        assert "refit_iterations" in artifact.metadata, (
            f"metadata missing refit_iterations: {list(artifact.metadata.keys())}"
        )
        assert isinstance(artifact.metadata["refit_iterations"], int)
        assert artifact.metadata["refit_iterations"] > 0

        # Mode must be recorded
        assert artifact.metadata.get("mode") == "incremental"

    # ------------------------------------------------------------------
    # AC-FR2200-04: Incremental training computes IC metrics
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2200_04_incremental_metrics_include_ic(self, tmp_path):
        """AC-FR2200-04: Incremental training computes and records IC metrics."""
        _create_parent_model(tmp_path)
        port = DefaultTrainerPort(models_dir=tmp_path)

        artifact = await port.train(
            mode="incremental",
            parent_version="v0.2.0.5",
            train_window_years=1,
        )

        metadata = artifact.metadata
        assert "test_ic_mean" in metadata
        assert "test_rank_ic_mean" in metadata
        assert isinstance(metadata["test_ic_mean"], float)
        assert isinstance(metadata["test_rank_ic_mean"], float)
        assert -1.0 <= metadata["test_ic_mean"] <= 1.0
        assert -1.0 <= metadata["test_rank_ic_mean"] <= 1.0

    # ------------------------------------------------------------------
    # Bonus: incremental retrain preserves parent's scaler and feature_names
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2200_05_incremental_preserves_scaler_and_features(self, tmp_path):
        """Incremental retrain inherits parent scaler and feature_names."""
        _, parent_booster, parent_scaler = _create_parent_model(tmp_path)
        port = DefaultTrainerPort(models_dir=tmp_path)

        artifact = await port.train(
            mode="incremental",
            parent_version="v0.2.0.5",
            train_window_years=1,
        )

        # Feature names should match parent
        assert artifact.feature_names == parent_scaler.feature_names
        # Scaler should match parent
        assert artifact.scaler.mean_ == parent_scaler.mean_
        assert artifact.scaler.std_ == parent_scaler.std_
