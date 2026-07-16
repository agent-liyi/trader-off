"""Tests for visualization output (FR-1600)."""

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from trader_off.visualization.plots import (
    render_nav_curve,
    render_ic_timeseries,
    render_feature_importance,
)
from trader_off.utils.exceptions import VisualizationDependencyError


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nav_df() -> pl.DataFrame:
    """Simple nav DataFrame with 50 days."""
    start = date(2024, 1, 1)
    return pl.DataFrame({
        "date": [start + timedelta(days=i) for i in range(50)],
        "nav": [100.0 + i * 0.5 for i in range(50)],
    }, schema={"date": pl.Date, "nav": pl.Float64})


@pytest.fixture
def baseline_df() -> pl.DataFrame:
    """Simple baseline nav."""
    start = date(2024, 1, 1)
    return pl.DataFrame({
        "date": [start + timedelta(days=i) for i in range(50)],
        "nav": [100.0 + i * 0.3 for i in range(50)],
    }, schema={"date": pl.Date, "nav": pl.Float64})


@pytest.fixture
def ic_df() -> pl.DataFrame:
    """Simple IC time series."""
    start = date(2024, 1, 1)
    return pl.DataFrame({
        "date": [start + timedelta(days=i) for i in range(20)],
        "ic": [0.02 + (i % 5) * 0.01 for i in range(20)],
        "rank_ic": [0.03 + (i % 5) * 0.01 for i in range(20)],
    }, schema={"date": pl.Date, "ic": pl.Float64, "rank_ic": pl.Float64})


@pytest.fixture
def importance_df() -> pl.DataFrame:
    """Simple feature importance with 25 features."""
    return pl.DataFrame({
        "feature": [f"feat_{i}" for i in range(25)],
        "importance": [1.0 / (i + 1) for i in range(25)],
        "rank": list(range(1, 26)),
    })


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestRenderNavCurve:
    """Unit tests for render_nav_curve."""

    # AC-FR1600-1: PNG generated, size > 1024, dimensions 1200×720
    def test_ac_fr1600_01_nav_curve_png(self, nav_df, baseline_df, tmp_path):
        """AC-FR1600-1: render_nav_curve creates valid PNG."""
        output = tmp_path / "figures" / "nav_curve.png"
        result = render_nav_curve(nav_df, baseline_df, output_path=output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 1024, f"PNG too small: {output.stat().st_size}"


class TestRenderICTimeseries:
    """Unit tests for render_ic_timeseries."""

    # AC-FR1600-2: PNG generated with IC + Rank IC
    def test_ac_fr1600_02_ic_timeseries_png(self, ic_df, tmp_path):
        """AC-FR1600-2: render_ic_timeseries creates valid PNG."""
        output = tmp_path / "figures" / "ic_timeseries.png"
        result = render_ic_timeseries(ic_df, output_path=output)

        assert output.exists()
        assert output.stat().st_size > 1024


class TestRenderFeatureImportance:
    """Unit tests for render_feature_importance."""

    # AC-FR1600-3: Top 20 barh PNG
    def test_ac_fr1600_03_feature_importance_png(
        self, importance_df, tmp_path,
    ):
        """AC-FR1600-3: render_feature_importance creates barh PNG with top 20."""
        output = tmp_path / "figures" / "feature_importance_top20.png"
        result = render_feature_importance(
            importance_df, top_k=20, output_path=output,
        )

        assert output.exists()
        assert output.stat().st_size > 1024


# AC-FR1600-4: VisualizationDependencyError when matplotlib missing
def test_ac_fr1600_04_missing_dep_error(monkeypatch):
    """AC-FR1600-4: ImportError for matplotlib raises VisualizationDependencyError."""
    import builtins

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError("No module named 'matplotlib'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    # Need to reload the module to trigger the import error
    import importlib
    from trader_off.visualization import plots as vp

    importlib.reload(vp)

    with pytest.raises(VisualizationDependencyError, match="matplotlib is required"):
        vp._check_matplotlib()
