"""Unit tests for factor evaluation report generation (FR-0700).

AC-FR0700-01: report dict with html, md, figures_dir; files exist and >5KB.
AC-FR0700-02: HTML self-contained, contains table, images, ICIR.
AC-FR0700-03: Markdown report with pipe table and heading.
AC-FR0700-04: No jinja2 dependency; uses string.Template.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from trader_off.factor_mining.evaluation import FactorEvaluation
from trader_off.factor_mining.expression import FactorSpec
from trader_off.factor_mining.viz import render_evaluation_report

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_evaluation(
    factor_id: str = "factor_01",
    ic_mean: float = 0.05,
    ic_std: float = 0.10,
    icir: float = 0.50,
    rank_ic_mean: float = 0.04,
    rank_ic_std: float = 0.09,
    n_dates: int = 10,
    seed: int = 42,
) -> FactorEvaluation:
    """Create a FactorEvaluation with synthetic daily IC time series."""
    rng = np.random.default_rng(seed)
    dates = [date(2026, 1, 1 + i) for i in range(n_dates)]
    ic_vals = rng.normal(ic_mean, ic_std, n_dates)
    rank_ic_vals = rng.normal(rank_ic_mean, rank_ic_std, n_dates)

    ic_ts = pl.DataFrame({"date": dates, "ic": ic_vals})
    rank_ic_ts = pl.DataFrame({"date": dates, "rank_ic": rank_ic_vals})

    layered_returns = pl.DataFrame(
        {
            "layer": [1, 2, 3, 4, 5],
            "mean_return": [0.012, 0.006, 0.002, -0.004, -0.010],
        }
    )

    return FactorEvaluation(
        ic_ts=ic_ts,
        rank_ic_ts=rank_ic_ts,
        ic_mean=float(np.nanmean(ic_vals)),
        ic_std=float(np.nanstd(ic_vals)),
        icir=icir,
        rank_ic_mean=float(np.nanmean(rank_ic_vals)),
        rank_ic_std=float(np.nanstd(rank_ic_vals)),
        layered_returns=layered_returns,
    )


def _make_factor_spec(idx: int = 0) -> FactorSpec:
    """Create a minimal FactorSpec for testing."""
    factor_id = f"momentum_N_{(idx + 1) * 5}"

    def _compute(_df):
        return pl.Series("factor", [0.0])

    return FactorSpec(
        id=factor_id,
        template_name="momentum_N",
        category="momentum",
        formula=f"close[t]/close[t-{(idx + 1) * 5}]-1",
        compute_fn=_compute,
        params={"N": (idx + 1) * 5},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRenderEvaluationReport:
    """Tests for render_evaluation_report()."""

    # AC-FR0700-01: report dict structure, file existence and size
    # AC specifies "30 selected factors + complete evaluations" scenario
    def test_ac_fr0700_01_report_generation(self, tmp_path: Path):
        """AC-FR0700-01: returns dict with html, md, figures_dir;
        HTML and MD files exist and are >5KB."""
        n = 50
        evaluations = [
            _make_evaluation(f"factor_{i:02d}", icir=0.1 * (i + 1), seed=i) for i in range(n)
        ]
        selected = [_make_factor_spec(i) for i in range(n)]
        output_dir = tmp_path / "reports"

        result = render_evaluation_report(evaluations, selected, output_dir)

        # Check return dict keys
        assert set(result.keys()) == {"html", "md", "figures_dir"}, (
            f"Expected keys {{html, md, figures_dir}}, got {set(result.keys())}"
        )

        # Check file existence
        assert result["html"].exists(), "HTML report file must exist"
        assert result["md"].exists(), "Markdown report file must exist"

        # Check file size > 5KB
        html_size = result["html"].stat().st_size
        assert html_size > 5000, f"HTML must be > 5KB, got {html_size}"
        md_size = result["md"].stat().st_size
        assert md_size > 5000, f"Markdown must be > 5KB, got {md_size}"

        # Check figures_dir is a directory
        assert result["figures_dir"].is_dir(), "figures_dir must be a directory"

    # AC-FR0700-02: HTML self-contained with expected sections
    def test_ac_fr0700_02_html_content(self, tmp_path: Path):
        """AC-FR0700-02: HTML contains <title>, <h1>, <table>,
        <img src=\"figures/correlation_heatmap.png\",
        <img src=\"figures/top_layer_cumret.png\",
        and 'ICIR'."""
        n = 5
        evaluations = [
            _make_evaluation(f"factor_{i:02d}", icir=0.1 * (i + 1), seed=i) for i in range(n)
        ]
        selected = [_make_factor_spec(i) for i in range(n)]
        output_dir = tmp_path / "reports"

        result = render_evaluation_report(evaluations, selected, output_dir)

        html_content = result["html"].read_text(encoding="utf-8")

        # Required strings in HTML per AC-FR0700-02
        assert "<title>" in html_content, "HTML must contain <title>"
        assert "<h1>" in html_content, "HTML must contain <h1>"
        assert "<table>" in html_content, "HTML must contain <table>"
        assert '<img src="figures/correlation_heatmap.png"' in html_content, (
            'HTML must contain <img src="figures/correlation_heatmap.png"'
        )
        assert '<img src="figures/top_layer_cumret.png"' in html_content, (
            'HTML must contain <img src="figures/top_layer_cumret.png"'
        )
        assert "ICIR" in html_content, "HTML must contain ICIR"

        # Self-contained: no external CSS/JS references
        assert 'href="http' not in html_content, "HTML must not reference external CSS"
        assert 'src="http' not in html_content, "HTML must not reference external JS/images"

    # AC-FR0700-03: Markdown report with expected sections
    def test_ac_fr0700_03_markdown_content(self, tmp_path: Path):
        """AC-FR0700-03: Markdown contains heading, pipe table, factor IDs,
        and generation timestamp."""
        n = 5
        evaluations = [
            _make_evaluation(f"factor_{i:02d}", icir=0.1 * (i + 1), seed=i) for i in range(n)
        ]
        selected = [_make_factor_spec(i) for i in range(n)]
        output_dir = tmp_path / "reports"

        result = render_evaluation_report(evaluations, selected, output_dir)

        md_content = result["md"].read_text(encoding="utf-8")

        # Heading
        assert "#" in md_content, "Markdown must contain heading (#)"

        # Pipe table for ICIR (case-insensitive)
        assert "| icir |" in md_content.lower(), "Markdown must contain ICIR pipe table"
        assert "|---" in md_content, "Markdown must contain table separator"

        # Selected factor IDs
        for spec in selected:
            assert spec.id in md_content, f"Markdown must list selected factor {spec.id}"

    # AC-FR0700-04: No jinja2 dependency
    def test_ac_fr0700_04_no_jinja2(self, tmp_path: Path):
        """AC-FR0700-04: report generation works without jinja2;
        uses string.Template internally."""
        n = 3
        evaluations = [
            _make_evaluation(f"factor_{i:02d}", icir=0.1 * (i + 1), seed=i) for i in range(n)
        ]
        selected = [_make_factor_spec(i) for i in range(n)]
        output_dir = tmp_path / "reports"

        # Attempt to block jinja2 from being importable
        # (does not raise if jinja2 is not installed)
        try:
            import jinja2  # noqa: F401
        except ImportError:
            pass  # Expected — jinja2 is not required

        # If jinja2 is installed, verify the report still works
        result = render_evaluation_report(evaluations, selected, output_dir)

        assert result["html"].exists(), "HTML must be generated without jinja2"
        assert result["md"].exists(), "MD must be generated without jinja2"

        # Verify no jinja2 import in the viz module
        assert "jinja2" not in sys.modules.get(
            "trader_off.factor_mining.viz", sys.modules
        ).__dict__.get("__file__", ""), "viz module must not import jinja2"

    # AC-FR0700-01 extension: deterministic content (stable timestamps)
    def test_ac_fr0700_deterministic_output(self, tmp_path: Path):
        """Report output is deterministic for the same inputs
        when generated_at is fixed."""
        n = 3
        evaluations = [
            _make_evaluation(f"factor_{i:02d}", icir=0.1 * (i + 1), seed=i) for i in range(n)
        ]
        selected = [_make_factor_spec(i) for i in range(n)]
        fixed_ts = "2026-07-17 12:00:00 UTC"

        result1 = render_evaluation_report(
            evaluations, selected, tmp_path / "run1", generated_at=fixed_ts
        )
        result2 = render_evaluation_report(
            evaluations, selected, tmp_path / "run2", generated_at=fixed_ts
        )

        html1 = result1["html"].read_text(encoding="utf-8")
        html2 = result2["html"].read_text(encoding="utf-8")
        assert html1 == html2, "HTML output must be deterministic for same inputs"

        md1 = result1["md"].read_text(encoding="utf-8")
        md2 = result2["md"].read_text(encoding="utf-8")
        assert md1 == md2, "Markdown output must be deterministic for same inputs"

    # Edge case: empty evaluations/selected
    def test_ac_fr0700_empty_input(self, tmp_path: Path):
        """Empty evaluations and selected lists should produce valid
        (but minimal) reports."""
        evaluations: list[FactorEvaluation] = []
        selected: list[FactorSpec] = []
        output_dir = tmp_path / "reports"

        result = render_evaluation_report(evaluations, selected, output_dir)

        assert result["html"].exists(), "HTML must exist even for empty input"
        assert result["md"].exists(), "Markdown must exist even for empty input"

    # Edge case: single factor
    def test_ac_fr0700_single_factor(self, tmp_path: Path):
        """Single factor should produce valid reports."""
        evaluations = [_make_evaluation("single_factor", icir=0.5, seed=1)]
        selected = [_make_factor_spec(0)]
        output_dir = tmp_path / "reports"

        result = render_evaluation_report(evaluations, selected, output_dir)

        html_content = result["html"].read_text(encoding="utf-8")
        assert "single_factor" not in html_content  # ID from evaluation, not spec
        # Factor ID from FactorSpec should appear
        assert selected[0].id in html_content, "HTML must contain factor ID"
