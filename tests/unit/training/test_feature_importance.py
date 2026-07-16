"""Tests for feature importance extraction (FR-1400)."""

import numpy as np
import polars as pl
import pytest
from lightgbm import Booster, Dataset, train

from trader_off.training.feature_importance import extract_feature_importance


@pytest.fixture
def trained_booster_20f() -> Booster:
    """Train a booster with 20 features."""
    rng = np.random.RandomState(42)
    X = rng.randn(500, 20)
    y = X[:, 0] * 2.0 + X[:, 1] * 1.5 + rng.randn(500) * 0.1
    train_data = Dataset(X, label=y)
    params = {"objective": "regression", "num_leaves": 8, "verbose": -1}
    return train(params, train_data, num_boost_round=20)


@pytest.fixture
def twenty_feature_names() -> list[str]:
    """20 dummy feature names."""
    return [f"feature_{i}" for i in range(20)]


class TestExtractFeatureImportance:
    """Unit tests for extract_feature_importance."""

    # AC-FR1400-01: returns sorted DataFrame with feature, importance, rank
    def test_ac_fr1400_01_extract_sorted(
        self, trained_booster_20f, twenty_feature_names,
    ):
        """AC-FR1400-01: returns 20 rows sorted by importance descending."""
        result = extract_feature_importance(
            trained_booster_20f, twenty_feature_names,
        )

        assert set(result.columns) == {"feature", "importance", "rank"}
        assert len(result) == 20

        # Check sorting
        imps = result["importance"].to_list()
        assert imps == sorted(imps, reverse=True), "Importance not sorted descending"

        # Check rank starts from 1
        assert result["rank"][0] == 1

    # AC-FR1400-03: empty booster → empty DataFrame + INFO log (no error)
    def test_ac_fr1400_03_empty_booster(self, trained_booster_20f):
        """AC-FR1400-03: empty booster returns empty DF, does not raise.

        Simulates an untrained booster by using num_trees() edge case.
        """
        # Use a booster with no features passed → should handle gracefully
        from unittest.mock import MagicMock

        mock_booster = MagicMock()
        mock_booster.num_trees.return_value = 0

        result = extract_feature_importance(mock_booster, ["f1", "f2"])

        assert isinstance(result, pl.DataFrame)
        assert set(result.columns) == {"feature", "importance", "rank"}
        assert len(result) == 0
