"""Tests for lightGBM model training (FR-0700)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import lightgbm as lgb
import numpy as np
import polars as pl
import pytest

from trader_off.training.trainer import (
    DEFAULT_PARAMS,
    train_model,
)


@pytest.fixture
def synthetic_regression_data():
    """Generate synthetic regression data: y = 2*x1 + 3*x2 + noise."""
    rng = np.random.RandomState(42)

    def make_data(n_samples: int, noise_scale: float = 0.1) -> tuple[pl.DataFrame, pl.Series]:
        x1 = rng.randn(n_samples)
        x2 = rng.randn(n_samples)
        noise = rng.randn(n_samples) * noise_scale
        y = 2.0 * x1 + 3.0 * x2 + noise

        X_df = pl.DataFrame({"x1": x1, "x2": x2})
        y_series = pl.Series("label", y)
        return X_df, y_series

    X_train, y_train = make_data(500, noise_scale=0.05)
    X_valid, y_valid = make_data(100, noise_scale=0.05)
    return X_train, y_train, X_valid, y_valid


class TestTrainModel:
    """Unit tests for train_model."""

    # AC-FR0700-01: Returns a trained Booster
    def test_ac_fr0700_01_returns_booster(self, synthetic_regression_data):
        """AC-FR0700-01: train_model returns lightgbm.Booster with num_trees() > 0."""
        X_train, y_train, X_valid, y_valid = synthetic_regression_data

        booster = train_model(
            X_train=X_train,
            y_train=y_train,
            X_valid=X_valid,
            y_valid=y_valid,
        )

        assert isinstance(booster, lgb.Booster)
        assert booster.num_trees() > 0, "Booster should have at least 1 tree"

    # AC-FR0700-02: Default objective is regression
    def test_ac_fr0700_02_objective(self, synthetic_regression_data):
        """AC-FR0700-02: Default objective is 'regression' or 'regression_l2'."""
        X_train, y_train, X_valid, y_valid = synthetic_regression_data

        booster = train_model(
            X_train=X_train,
            y_train=y_train,
            X_valid=X_valid,
            y_valid=y_valid,
        )

        objective = booster.params.get("objective", "")
        assert objective in ("regression", "regression_l2"), (
            f"Unexpected objective: {objective}"
        )

    # AC-FR0700-03: Early stopping
    def test_ac_fr0700_03_early_stopping(self):
        """AC-FR0700-03: Early stopping triggers before n_estimators runs out."""
        # Generate training data with clear signal and validation with different
        # distribution to trigger early stopping
        rng = np.random.RandomState(42)

        # Training: clean linear pattern
        n_train = 300
        x1_train = rng.randn(n_train)
        x2_train = rng.randn(n_train)
        y_train = 2.0 * x1_train + 3.0 * x2_train + rng.randn(n_train) * 0.01

        # Validation: different distribution with more noise, causes early stopping
        n_valid = 100
        x1_valid = rng.randn(n_valid) * 3 + 5  # Shifted distribution
        x2_valid = rng.randn(n_valid) * 3 - 2
        y_valid = 2.0 * x1_valid + 3.0 * x2_valid + rng.randn(n_valid) * 2.0

        X_train_df = pl.DataFrame({"x1": x1_train, "x2": x2_train})
        X_valid_df = pl.DataFrame({"x1": x1_valid, "x2": x2_valid})

        # Use small n_estimators and aggressive early stopping
        params = DEFAULT_PARAMS.copy()
        params["n_estimators"] = 300
        params["early_stopping_rounds"] = 10
        params["learning_rate"] = 0.1

        booster = train_model(
            X_train=X_train_df,
            y_train=pl.Series("label", y_train),
            X_valid=X_valid_df,
            y_valid=pl.Series("label", y_valid),
            params=params,
        )

        # Best iteration should be less than max n_estimators
        best_iter = booster.best_iteration
        assert best_iter < 300, (
            f"Expected early stopping (best_iter < 300), got {best_iter}"
        )

    # AC-FR0700-04: train.log contains best_iteration and final_train_loss
    def test_ac_fr0700_04_train_log(self, synthetic_regression_data, tmp_path):
        """AC-FR0700-04: train.log has best_iteration and final_train_loss."""
        X_train, y_train, X_valid, y_valid = synthetic_regression_data

        log_path = tmp_path / "train.log"

        params = DEFAULT_PARAMS.copy()
        params["n_estimators"] = 50  # Faster training

        booster = train_model(
            X_train=X_train,
            y_train=y_train,
            X_valid=X_valid,
            y_valid=y_valid,
            params=params,
            log_path=log_path,
        )

        assert log_path.exists(), "train.log not created"

        log_content = log_path.read_text()
        assert "best_iteration" in log_content, (
            f"train.log missing 'best_iteration': {log_content[:200]}"
        )
        assert "final_train_loss" in log_content, (
            f"train.log missing 'final_train_loss': {log_content[:200]}"
        )

    # AC-FR0700-05: Params verification (mock LGBMRegressor)
    def test_ac_fr0700_05_params_passed_correctly(self, synthetic_regression_data):
        """AC-FR0700-05: Custom params are passed to LGBMRegressor."""
        X_train, y_train, X_valid, y_valid = synthetic_regression_data

        custom_params = {
            "objective": "regression",
            "num_leaves": 31,
            "learning_rate": 0.01,
            "n_estimators": 100,
            "random_state": 123,
        }

        with patch("trader_off.training.trainer.lgb.LGBMRegressor") as mock_lgb:
            mock_instance = MagicMock()
            mock_instance.best_iteration_ = 50
            mock_instance.booster_ = MagicMock()
            mock_instance.booster_.num_trees.return_value = 1
            mock_lgb.return_value = mock_instance

            train_model(
                X_train=X_train,
                y_train=y_train,
                X_valid=X_valid,
                y_valid=y_valid,
                params=custom_params,
            )

            # Check that LGBMRegressor was called with the right params
            call_kwargs = mock_lgb.call_args.kwargs
            assert call_kwargs["num_leaves"] == 31
            assert call_kwargs["learning_rate"] == 0.01
            assert call_kwargs["n_estimators"] == 100
            assert call_kwargs["random_state"] == 123
