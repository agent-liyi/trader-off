"""Tests for model serialization and version management (FR-0800)."""

import json
import re
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import polars as pl
import pytest

from trader_off.data.preprocess import StandardScaler
from trader_off.training.serialize import (
    ModelArtifact,
    load_model,
    save_model,
)
from trader_off.utils.exceptions import ModelVersionExistsError


@pytest.fixture
def dummy_booster() -> lgb.Booster:
    """Create a minimal trained lightGBM booster."""
    X = np.random.RandomState(42).randn(100, 3)
    y = np.random.RandomState(42).randn(100)
    train_data = lgb.Dataset(X, label=y)
    params = {
        "objective": "regression",
        "num_leaves": 4,
        "verbose": -1,
    }
    booster = lgb.train(params, train_data, num_boost_round=5)
    return booster


@pytest.fixture
def dummy_scaler() -> StandardScaler:
    """Create a sample StandardScaler."""
    return StandardScaler(
        mean_={"f1": 0.0, "f2": 1.0},
        std_={"f1": 1.0, "f2": 2.0},
        feature_names=["f1", "f2"],
    )


@pytest.fixture
def dummy_metadata() -> dict:
    """Create sample metadata."""
    return {
        "train_time": "2026-07-16T12:00:00Z",
        "train_start": "2021-01-01",
        "train_end": "2024-12-31",
        "params": {"num_leaves": 63, "learning_rate": 0.05},
        "best_iteration": 120,
    }


class TestSaveModel:
    """Unit tests for save_model."""

    # AC-FR0800-1: All files created
    def test_ac_fr0800_01_save_files(
        self, dummy_booster, dummy_scaler, dummy_metadata, tmp_path
    ):
        """AC-FR0800-1: save_model creates all 5 required files."""
        version = "20260101_120000"
        models_dir = tmp_path / "models"

        model_path = save_model(
            booster=dummy_booster,
            scaler=dummy_scaler,
            metadata=dummy_metadata,
            version=version,
            models_dir=models_dir,
            dropped_features=["dropped_feat"],
            feature_names=["f1", "f2"],
        )

        expected_dir = models_dir / version
        assert model_path == expected_dir
        assert expected_dir.is_dir()

        required_files = [
            "model.pkl",
            "scaler.json",
            "dropped_features.json",
            "feature_names.json",
            "metadata.json",
        ]
        for fname in required_files:
            fpath = expected_dir / fname
            assert fpath.exists(), f"Missing {fpath}"

        # Verify content types
        booster = joblib.load(expected_dir / "model.pkl")
        assert isinstance(booster, lgb.Booster)

        scaler_data = json.loads((expected_dir / "scaler.json").read_text())
        assert "mean_" in scaler_data
        assert "std_" in scaler_data

        dropped = json.loads((expected_dir / "dropped_features.json").read_text())
        assert "dropped_feat" in dropped

        feature_names = json.loads((expected_dir / "feature_names.json").read_text())
        assert feature_names == ["f1", "f2"]

        metadata = json.loads((expected_dir / "metadata.json").read_text())
        assert metadata["best_iteration"] == 120

    # AC-FR0800-2: Default version format
    def test_ac_fr0800_02_default_version_format(
        self, dummy_booster, dummy_scaler, dummy_metadata, tmp_path
    ):
        """AC-FR0800-2: Default version is YYYYMMDD_HHMMSS (15 chars)."""
        models_dir = tmp_path / "models"

        # save_model without explicit version → auto-generate
        # We simulate by passing version=None and checking the generated format
        # Actually, the default is generated inside save_model when version is empty
        # For testing, we'll monkeypatch datetime to get a consistent value,
        # then verify the format regex
        generated_path = save_model(
            booster=dummy_booster,
            scaler=dummy_scaler,
            metadata=dummy_metadata,
            models_dir=models_dir,
            dropped_features=[],
            feature_names=["f1"],
        )

        # The last part of the path is the version
        version = generated_path.name
        assert len(version) == 15, f"Version length: {len(version)}, value: {version}"
        assert version[8] == "_", f"Missing underscore at position 8: {version}"
        assert re.match(r"^\d{8}_\d{6}$", version), f"Invalid format: {version}"

    # AC-FR0800-3: Duplicate version error
    def test_ac_fr0800_03_version_exists_error(
        self, dummy_booster, dummy_scaler, dummy_metadata, tmp_path
    ):
        """AC-FR0800-3: Saving to existing version raises ModelVersionExistsError."""
        version = "20260101_120000"
        models_dir = tmp_path / "models"

        # First save should succeed
        save_model(
            booster=dummy_booster,
            scaler=dummy_scaler,
            metadata=dummy_metadata,
            version=version,
            models_dir=models_dir,
            dropped_features=[],
            feature_names=["f1"],
        )

        # Second save with same version should fail
        with pytest.raises(ModelVersionExistsError, match="already exists"):
            save_model(
                booster=dummy_booster,
                scaler=dummy_scaler,
                metadata=dummy_metadata,
                version=version,
                models_dir=models_dir,
                dropped_features=[],
                feature_names=["f1"],
            )

    # AC-FR0800-4: Load model returns ModelArtifact
    def test_ac_fr0800_04_load_artifact(
        self, dummy_booster, dummy_scaler, dummy_metadata, tmp_path
    ):
        """AC-FR0800-4: load_model returns ModelArtifact with all fields non-empty."""
        version = "20260101_120000"
        models_dir = tmp_path / "models"
        feature_names = ["f1", "f2"]

        save_model(
            booster=dummy_booster,
            scaler=dummy_scaler,
            metadata=dummy_metadata,
            version=version,
            models_dir=models_dir,
            dropped_features=[],
            feature_names=feature_names,
        )

        artifact = load_model(version=version, models_dir=models_dir)

        assert isinstance(artifact, ModelArtifact)
        assert isinstance(artifact.booster, lgb.Booster)
        assert isinstance(artifact.scaler, StandardScaler)
        assert artifact.feature_names == feature_names
        assert isinstance(artifact.metadata, dict)
        assert artifact.metadata["best_iteration"] == 120
