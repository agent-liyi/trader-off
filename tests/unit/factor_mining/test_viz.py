"""Unit tests for factor mining visualization (FR-0500).

AC-FR0500-01: PNG file existence and size.
AC-FR0500-02: Image dimensions.
AC-FR0500-03: Dense labels font auto-shrink.
"""

import io
from pathlib import Path

import matplotlib
import numpy as np
from loguru import logger

matplotlib.use("Agg")

from trader_off.factor_mining.viz import render_correlation_heatmap  # noqa: E402


def _make_corr_matrix(n: int, seed: int = 42) -> np.ndarray:
    """Create a valid n×n correlation matrix from random data."""
    rng = np.random.default_rng(seed)
    data = rng.normal(0, 1, (100, n))
    corr = np.corrcoef(data, rowvar=False)
    np.fill_diagonal(corr, 1.0)
    return corr


def _make_labels(n: int) -> list[str]:
    """Create factor ID labels."""
    return [f"factor_{i:03d}" for i in range(n)]


class TestRenderCorrelationHeatmap:
    """Tests for render_correlation_heatmap()."""

    # AC-FR0500-01: PNG file existence and minimum size
    def test_ac_fr0500_01_png_output_exists_and_size(self, tmp_path: Path):
        """AC-FR0500-01: render_correlation_heatmap generates PNG,
        file size > 5KB."""
        n = 20
        corr = _make_corr_matrix(n)
        labels = _make_labels(n)
        output_path = tmp_path / "correlation_heatmap.png"

        result = render_correlation_heatmap(corr, labels, output_path)

        assert result == output_path, "Must return the output path"
        assert output_path.exists(), "PNG file must exist"
        file_size = output_path.stat().st_size
        assert file_size > 5000, f"PNG file must be > 5KB (5000 bytes), got {file_size}"

    # AC-FR0500-02: Image dimensions
    def test_ac_fr0500_02_image_dimensions(self, tmp_path: Path):
        """AC-FR0500-02: Image is static PNG, dimensions 1200×1440 (H×W)."""
        n = 5
        corr = _make_corr_matrix(n)
        labels = _make_labels(n)
        output_path = tmp_path / "heatmap.png"

        render_correlation_heatmap(corr, labels, output_path)

        img = matplotlib.image.imread(str(output_path))
        h, w = img.shape[:2]
        assert (h, w) == (1200, 1440), f"Expected (H, W) = (1200, 1440), got ({h}, {w})"

    # AC-FR0500-03: Dense labels font auto-shrink
    def test_ac_fr0500_03_dense_labels_font_shrink(self, tmp_path: Path):
        """AC-FR0500-03: With ≥30 labels, font shrinks to 6;
        confirmed via log message 'densely labeled, font shrunk'."""
        n = 30
        corr = _make_corr_matrix(n)
        labels = _make_labels(n)
        output_path = tmp_path / "heatmap_dense.png"

        stream = io.StringIO()
        handler_id = logger.add(stream, level="INFO", format="{message}")
        try:
            render_correlation_heatmap(corr, labels, output_path)
            log_output = stream.getvalue()
        finally:
            logger.remove(handler_id)

        assert "densely labeled" in log_output, (
            f"Expected 'densely labeled' in log, got: {log_output!r}"
        )
        assert "font shrunk" in log_output, f"Expected 'font shrunk' in log, got: {log_output!r}"
        assert output_path.exists(), "PNG file must still be generated"
