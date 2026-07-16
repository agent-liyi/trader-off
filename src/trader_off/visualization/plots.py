"""Visualization rendering (FR-1600).

Generates static PNG charts using matplotlib with Agg backend.
- render_nav_curve: NAV curve with baseline comparison
- render_ic_timeseries: IC and Rank IC time series
- render_feature_importance: Top-K feature importance horizontal bar chart
"""

from pathlib import Path

import polars as pl
from loguru import logger

from trader_off.utils.exceptions import VisualizationDependencyError


def _check_matplotlib():
    """Verify matplotlib is available; raise VisualizationDependencyError if not."""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        raise VisualizationDependencyError(
            "matplotlib is required for visualization, install via `uv add matplotlib`"
        )


def render_nav_curve(
    nav_df: pl.DataFrame,
    baseline_df: pl.DataFrame,
    output_path: Path | str,
    figsize: tuple = (10, 6),
    dpi: int = 120,
) -> Path:
    """Render NAV curve with baseline comparison as PNG.

    Args:
        nav_df: DataFrame with date (Date) and nav (Float64) columns.
        baseline_df: DataFrame with date (Date) and nav (Float64) columns.
        output_path: Path for output PNG file.
        figsize: Figure size in inches. Default (10, 6).
        dpi: DPI for output. Default 120.

    Returns:
        Path to the generated PNG.
    """
    _check_matplotlib()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.plot(nav_df["date"].to_list(), nav_df["nav"].to_list(), label="Portfolio NAV")
    ax.plot(baseline_df["date"].to_list(), baseline_df["nav"].to_list(),
            label="Baseline", linestyle="--")
    ax.set_xlabel("Date")
    ax.set_ylabel("NAV")
    ax.set_title("NAV Curve")
    ax.legend()
    fig.autofmt_xdate()
    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)

    logger.info(f"render_nav_curve done -> {output_path}")
    return output_path


def render_ic_timeseries(
    ic_df: pl.DataFrame,
    output_path: Path | str,
    figsize: tuple = (10, 6),
    dpi: int = 120,
) -> Path:
    """Render IC and Rank IC time series as dual-line chart PNG.

    Args:
        ic_df: DataFrame with date (Date), ic (Float64), rank_ic (Float64).
        output_path: Path for output PNG file.
        figsize: Figure size in inches. Default (10, 6).
        dpi: DPI for output. Default 120.

    Returns:
        Path to the generated PNG.
    """
    _check_matplotlib()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dates = ic_df["date"].to_list()
    ic_vals = ic_df["ic"].to_list()
    rank_ic_vals = ic_df["rank_ic"].to_list()
    ic_mean = sum(ic_vals) / len(ic_vals) if ic_vals else 0.0

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.plot(dates, ic_vals, label="IC (Pearson)", marker="o", markersize=2)
    ax.plot(dates, rank_ic_vals, label="Rank IC (Spearman)", marker="s", markersize=2)
    ax.axhline(y=ic_mean, color="gray", linestyle="--", label=f"IC mean={ic_mean:.4f}")
    ax.set_xlabel("Date")
    ax.set_ylabel("IC Value")
    ax.set_title("IC Time Series")
    ax.legend()
    fig.autofmt_xdate()
    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)

    logger.info("render_ic_timeseries done")
    return output_path


def render_feature_importance(
    importance_df: pl.DataFrame,
    top_k: int = 20,
    output_path: Path | str = "feature_importance_top20.png",
    figsize: tuple = (10, 6),
    dpi: int = 120,
) -> Path:
    """Render top-K feature importance as horizontal bar chart PNG.

    Args:
        importance_df: DataFrame with feature (Utf8), importance (Float64).
        top_k: Number of top features to show. Default 20.
        output_path: Path for output PNG file.
        figsize: Figure size in inches. Default (10, 6).
        dpi: DPI for output. Default 120.

    Returns:
        Path to the generated PNG.
    """
    _check_matplotlib()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Select top_k features sorted by importance descending
    top_features = importance_df.sort("importance", descending=True).head(top_k)
    features = top_features["feature"].to_list()[::-1]  # Reverse for barh (bottom-to-top)
    importances = top_features["importance"].to_list()[::-1]

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.barh(features, importances)
    ax.set_xlabel("Importance (gain)")
    ax.set_title(f"Feature Importance Top {top_k}")
    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)

    logger.info(f"render_feature_importance done -> {output_path}")
    return output_path
