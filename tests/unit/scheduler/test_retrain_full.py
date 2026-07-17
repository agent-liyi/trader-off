"""Unit tests for FR-2100: full retrain via DefaultTrainerPort.train(mode='full').

AC coverage: AC-FR2100-01, AC-FR2100-02, AC-FR2100-03, AC-FR2100-04
"""

import lightgbm as lgb
import pytest

from trader_off.scheduler.ports import DefaultTrainerPort
from trader_off.training.serialize import ModelArtifact


class TestFullRetrain:
    """FR-2100: Full retrain produces fresh model with IC metrics."""

    # ------------------------------------------------------------------
    # AC-FR2100-01: train(mode='full') returns ModelArtifact with booster,
    # scaler, feature_names, and metadata
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2100_01_full_train_returns_model_artifact(self, tmp_path):
        """AC-FR2100-01: train(mode='full') returns ModelArtifact with booster,
        scaler, feature_names, and metadata."""
        port = DefaultTrainerPort(models_dir=tmp_path)
        artifact = await port.train(mode="full", train_window_years=1)

        assert isinstance(artifact, ModelArtifact), f"Expected ModelArtifact, got {type(artifact)}"
        assert isinstance(artifact.booster, lgb.Booster), (
            f"Expected lgb.Booster, got {type(artifact.booster)}"
        )
        assert artifact.booster.num_trees() > 0, (
            "Booster should have at least 1 tree after training"
        )
        assert artifact.scaler is not None, "Scaler must not be None"
        assert len(artifact.feature_names) > 0, "feature_names must be non-empty"
        assert isinstance(artifact.metadata, dict), "metadata must be a dict"

    # ------------------------------------------------------------------
    # AC-FR2100-02: Metadata includes IC metrics (test_ic_mean, test_rank_ic_mean)
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2100_02_full_train_metrics_include_ic(self, tmp_path):
        """AC-FR2100-02: Metadata includes IC metrics."""
        port = DefaultTrainerPort(models_dir=tmp_path)
        artifact = await port.train(mode="full", train_window_years=1)

        metadata = artifact.metadata
        assert "test_ic_mean" in metadata, f"metadata missing test_ic_mean: {list(metadata.keys())}"
        assert "test_rank_ic_mean" in metadata, (
            f"metadata missing test_rank_ic_mean: {list(metadata.keys())}"
        )
        # IC values must be valid floats in [-1, 1]
        test_ic = metadata["test_ic_mean"]
        rank_ic = metadata["test_rank_ic_mean"]
        assert isinstance(test_ic, float), f"test_ic_mean must be float, got {type(test_ic)}"
        assert isinstance(rank_ic, float), f"test_rank_ic_mean must be float, got {type(rank_ic)}"
        assert -1.0 <= test_ic <= 1.0, f"test_ic_mean {test_ic} out of [-1, 1]"
        assert -1.0 <= rank_ic <= 1.0, f"test_rank_ic_mean {rank_ic} out of [-1, 1]"

    # ------------------------------------------------------------------
    # AC-FR2100-03: Feature names preserved
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2100_03_full_train_feature_names_preserved(self, tmp_path):
        """AC-FR2100-03: Feature names are preserved in the artifact."""
        port = DefaultTrainerPort(models_dir=tmp_path)
        artifact = await port.train(mode="full", train_window_years=1)

        # Should have at least 2 features (the generated features)
        assert len(artifact.feature_names) >= 2, (
            f"Expected at least 2 feature names, got {len(artifact.feature_names)}"
        )
        assert all(isinstance(f, str) for f in artifact.feature_names), (
            "All feature names must be strings"
        )
        # Verify scaler feature_names match
        assert artifact.scaler.feature_names == artifact.feature_names, (
            f"Scaler feature_names {artifact.scaler.feature_names} "
            f"!= artifact feature_names {artifact.feature_names}"
        )

    # ------------------------------------------------------------------
    # AC-FR2100-04: Metadata includes mode and train_window_years
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_ac_fr2100_04_full_train_metadata_fields(self, tmp_path):
        """AC-FR2100-04: Metadata includes training parameters."""
        port = DefaultTrainerPort(models_dir=tmp_path)
        artifact = await port.train(mode="full", train_window_years=3)

        metadata = artifact.metadata
        assert metadata.get("mode") == "full"
        assert metadata.get("train_window_years") == 3
