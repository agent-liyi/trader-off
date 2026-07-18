"""Unit tests for portfolio.covariance (FR-3000).

AC-FR3000-01: sample covariance returns symmetric positive-definite matrix
AC-FR3000-02: Ledoit-Wolf shrinkage produces different but similar covariance
AC-FR3000-03: all-NaN asset columns are dropped, logged
AC-FR3000-04: fewer than 30 observations raises InsufficientDataError
"""

import io

import numpy as np
import polars as pl
import pytest
from loguru import logger

from trader_off.utils.exceptions import InsufficientDataError


class TestEstimateCovariance:
    """Tests for estimate_covariance function."""

    @pytest.fixture
    def returns_df_100x252(self):
        """Generate 100 assets x 252 days of synthetic return data."""
        rng = np.random.default_rng(42)
        n_assets = 100
        n_days = 252
        # Create correlated returns via a factor model
        factor = rng.normal(0.0005, 0.01, n_days)
        data = {
            "date": pl.date_range(
                start=pl.date(2020, 1, 1),
                end=pl.date(2020, 12, 31),
                interval="1d",
                eager=True,
            )[:n_days]
        }
        for i in range(n_assets):
            beta = 0.5 + 0.5 * rng.random()
            noise = rng.normal(0, 0.015, n_days)
            data[f"asset_{i:03d}"] = beta * factor + noise
        return pl.DataFrame(data)

    @pytest.fixture
    def returns_df_10x20(self):
        """Generate 10 assets x 20 days (too few)."""
        rng = np.random.default_rng(42)
        n_assets = 10
        n_days = 20
        data = {
            "date": pl.date_range(
                start=pl.date(2020, 1, 1),
                end=pl.date(2020, 1, 20),
                interval="1d",
                eager=True,
            )
        }
        for i in range(n_assets):
            data[f"asset_{i:03d}"] = rng.normal(0, 0.01, n_days)
        return pl.DataFrame(data)

    # -- Red-phase tests: written first, expected to fail until implementation exists --

    def test_ac_fr3000_01_sample_symmetric_psd(self, returns_df_100x252):
        """AC-FR3000-01: sample covariance returns symmetric, positive-definite matrix."""
        from trader_off.portfolio.covariance import estimate_covariance

        result = estimate_covariance(returns_df_100x252, method="sample")
        assert result.shape == (100, 100)
        assert np.allclose(result, result.T)
        eigvals = np.linalg.eigvalsh(result)
        assert eigvals.min() > 0

    def test_ac_fr3000_02_ledoit_wolf_shrinkage(self, returns_df_100x252):
        """AC-FR3000-02: LW covariance differs from sample with Frobenius ratio <0.5."""
        from trader_off.portfolio.covariance import estimate_covariance

        sample_cov = estimate_covariance(returns_df_100x252, method="sample")
        lw_cov = estimate_covariance(returns_df_100x252, method="ledoit_wolf")

        frob_diff = np.linalg.norm(lw_cov - sample_cov, "fro")
        frob_sample = np.linalg.norm(sample_cov, "fro")
        assert frob_diff / frob_sample < 0.5

    def test_ac_fr3000_03_nan_column_dropped(self, returns_df_100x252):
        """AC-FR3000-03: all-NaN asset column is dropped, logged, shape is N-1."""
        from trader_off.portfolio.covariance import estimate_covariance

        # Make one column all NaN
        df_with_nan = returns_df_100x252.clone()
        nan_column = "asset_050"
        df_with_nan = df_with_nan.with_columns(pl.lit(None).cast(pl.Float64).alias(nan_column))

        # Capture loguru output
        stream = io.StringIO()
        handler_id = logger.add(stream, level="WARNING", format="{message}")
        try:
            result = estimate_covariance(df_with_nan, method="sample")
        finally:
            logger.remove(handler_id)

        # Shape should be 99x99 (one column dropped)
        assert result.shape == (99, 99)
        # The dropped asset should be logged
        assert nan_column in stream.getvalue()

    def test_ac_fr3000_04_insufficient_data(self, returns_df_10x20):
        """AC-FR3000-04: fewer than 30 observations raises InsufficientDataError."""
        from trader_off.portfolio.covariance import estimate_covariance

        with pytest.raises(InsufficientDataError, match="need at least 30 days"):
            estimate_covariance(returns_df_10x20, method="sample")

    def test_unknown_method_raises(self, returns_df_100x252):
        """Unknown method name raises ValueError."""
        from trader_off.portfolio.covariance import estimate_covariance

        with pytest.raises(ValueError, match="Unknown method"):
            estimate_covariance(returns_df_100x252, method="invalid_method")

    def test_negative_eigenvalue_warning(self, returns_df_100x252, mocker):
        """Covariance with negative eigenvalues logs warning."""
        import io

        from loguru import logger

        from trader_off.portfolio.covariance import estimate_covariance

        stream = io.StringIO()
        handler_id = logger.add(stream, level="WARNING", format="{message}")

        # Mock eigvalsh to return values including negatives
        mocker.patch("numpy.linalg.eigvalsh", return_value=np.array([-1e-5, 0.1, 0.2, 0.3]))

        try:
            estimate_covariance(returns_df_100x252, method="sample")
        finally:
            logger.remove(handler_id)

        # Should have logged warning about negative eigenvalues
        log_output = stream.getvalue()
        assert "negative" in log_output.lower() or "eigenvalue" in log_output.lower()
