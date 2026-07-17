"""Visualization for factor mining — heatmap and evaluation report (FR-0500, FR-0700).

Generates static PNG correlation heatmaps using matplotlib with Agg backend.
Reuses patterns from v0.1.0 visualization.plots.
"""

from pathlib import Path

import numpy as np
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


def render_correlation_heatmap(
    corr_matrix: np.ndarray,
    labels: list[str],
    output_path: Path,
    figsize: tuple = (12, 10),
    dpi: int = 120,
) -> Path:
    """Render factor correlation heatmap as PNG.

    Args:
        corr_matrix: N×N correlation matrix (numpy array).
        labels: Factor ID labels for axes (length N).
        output_path: Path for output PNG file.
        figsize: Figure size in inches. Default (12, 10).
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

    n = len(labels)
    # Auto-shrink font for dense labels (≥30 factors)
    label_fontsize = 6 if n >= 30 else 10
    if n >= 30:
        logger.info("densely labeled, font shrunk (n={})", n)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    im = ax.imshow(corr_matrix, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=90, fontsize=label_fontsize)
    ax.set_yticklabels(labels, fontsize=label_fontsize)
    ax.set_title("Factor Correlation Heatmap")

    plt.colorbar(im, ax=ax, label="Pearson r")
    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)

    logger.info("render_correlation_heatmap done -> {}", output_path)
    return output_path
