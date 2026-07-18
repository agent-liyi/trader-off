"""Unit tests for portfolio.expected_returns (FR-3100).

AC-FR3100-01: build_expected_returns raw mode returns dict of {asset: score}
AC-FR3100-02: build_expected_returns zscore mode returns normalized scores
AC-FR3100-03: validate_asset_alignment raises AssetMismatchError on mismatch
"""

import numpy as np
import polars as pl
import pytest

from trader_off.utils.exceptions import AssetMismatchError


class TestBuildExpectedReturns:
    """Tests for build_expected_returns function."""

    @pytest.fixture
    def predictions_df(self):
        """Synthetic predictions DataFrame with 50 assets."""
        rng = np.random.default_rng(42)
        n = 50
        scores = rng.normal(0.001, 0.02, n)
        assets = [f"stock_{i:03d}" for i in range(n)]
        return pl.DataFrame(
            {
                "asset": assets,
                "score": scores,
                "rank": list(range(1, n + 1)),
            }
        )

    def test_ac_fr3100_01_raw_mode(self, predictions_df):
        """AC-FR3100-01: raw mode returns dict with original scores."""
        from trader_off.portfolio.expected_returns import build_expected_returns

        result = build_expected_returns(predictions_df, mode="raw")
        assert isinstance(result, dict)
        assert len(result) == 50
        first_asset = predictions_df["asset"][0]
        expected_score = predictions_df.filter(pl.col("asset") == first_asset)["score"].item()
        assert result[first_asset] == pytest.approx(expected_score)

    def test_ac_fr3100_02_zscore_mode(self, predictions_df):
        """AC-FR3100-02: zscore mode returns mean=0, std=1 scores."""
        from trader_off.portfolio.expected_returns import build_expected_returns

        result = build_expected_returns(predictions_df, mode="zscore")
        values = np.array(list(result.values()))
        assert abs(np.mean(values)) < 1e-9
        assert abs(np.std(values) - 1.0) < 1e-6

    def test_ac_fr3100_01_nan_raises(self, predictions_df):
        """FR-3100: predictions with NaN scores should raise error."""
        from trader_off.portfolio.expected_returns import build_expected_returns

        df = predictions_df.clone()
        df = df.with_columns(
            pl.when(pl.col("asset") == "stock_000")
            .then(pl.lit(None).cast(pl.Float64))
            .otherwise(pl.col("score"))
            .alias("score")
        )

        with pytest.raises(ValueError, match="NaN"):
            build_expected_returns(df, mode="raw")

    def test_zscore_near_zero_std_warning(self):
        """zscore mode with near-zero std logs warning and uses std=1.0."""
        from trader_off.portfolio.expected_returns import build_expected_returns

        # All scores identical -> std=0
        df = pl.DataFrame(
            {
                "asset": ["A", "B", "C"],
                "score": [0.5, 0.5, 0.5],
                "rank": [1, 2, 3],
            }
        )

        import io

        from loguru import logger

        stream = io.StringIO()
        handler_id = logger.add(stream, level="WARNING", format="{message}")
        try:
            result = build_expected_returns(df, mode="zscore")
        finally:
            logger.remove(handler_id)

        # Should still return values (degenerate but defined)
        assert isinstance(result, dict)
        assert len(result) == 3
        # Warning should be logged
        assert "degenerate" in stream.getvalue() or "zero" in stream.getvalue()

    def test_unknown_mode_raises(self, predictions_df):
        """build_expected_returns with unknown mode raises ValueError."""
        from trader_off.portfolio.expected_returns import build_expected_returns

        with pytest.raises(ValueError, match="Unknown mode"):
            build_expected_returns(predictions_df, mode="invalid_mode")


class TestValidateAssetAlignment:
    """Tests for validate_asset_alignment function."""

    def test_ac_fr3100_03_asset_mismatch(self):
        """AC-FR3100-03: mismatch between mu assets and cov assets raises error."""
        from trader_off.portfolio.expected_returns import validate_asset_alignment

        # mu has 50 assets, cov assets list has 48 (2 missing)
        mu = {f"stock_{i:03d}": 0.01 for i in range(50)}
        cov_assets = [f"stock_{i:03d}" for i in range(48)]

        with pytest.raises(AssetMismatchError, match="missing assets"):
            validate_asset_alignment(mu, cov_assets)

    def test_validate_asset_alignment_missing_from_mu(self):
        """validate_asset_alignment detects assets in covariance but missing from mu."""
        from trader_off.portfolio.expected_returns import validate_asset_alignment

        mu = {f"stock_{i:03d}": 0.01 for i in range(10)}
        cov_assets = [f"stock_{i:03d}" for i in range(15)]  # 5 extra assets

        with pytest.raises(AssetMismatchError, match="missing from mu"):
            validate_asset_alignment(mu, cov_assets)

    def test_validate_asset_alignment_missing_from_cov(self):
        """validate_asset_alignment detects assets in mu but missing from covariance."""
        from trader_off.portfolio.expected_returns import validate_asset_alignment

        mu = {f"stock_{i:03d}": 0.01 for i in range(15)}
        cov_assets = [f"stock_{i:03d}" for i in range(10)]  # 5 missing

        with pytest.raises(AssetMismatchError, match="missing from covariance"):
            validate_asset_alignment(mu, cov_assets)

    def test_validate_asset_alignment_both_directions(self):
        """validate_asset_alignment reports both missing directions when both exist."""
        from trader_off.portfolio.expected_returns import validate_asset_alignment

        mu = {
            "A": 0.01,
            "B": 0.01,  # 2 missing from cov
        }
        cov_assets = ["A", "C", "D"]  # 1 missing from mu

        with pytest.raises(AssetMismatchError, match="missing assets"):
            validate_asset_alignment(mu, cov_assets)

    def test_validate_asset_alignment_success(self):
        """validate_asset_alignment with matching assets passes silently."""
        from trader_off.portfolio.expected_returns import validate_asset_alignment

        mu = {f"stock_{i:03d}": 0.01 for i in range(10)}
        cov_assets = [f"stock_{i:03d}" for i in range(10)]

        # Should not raise
        validate_asset_alignment(mu, cov_assets)
