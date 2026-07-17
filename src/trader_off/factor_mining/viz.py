"""Visualization for factor mining — heatmap and evaluation report (FR-0500, FR-0700).

Generates static PNG correlation heatmaps using matplotlib with Agg backend
and self-contained HTML + Markdown evaluation reports using string.Template.
Reuses patterns from v0.1.0 visualization.plots.
"""

from __future__ import annotations

import string
from datetime import UTC, datetime  # type: ignore[attr-defined]
from pathlib import Path

import numpy as np
from loguru import logger

from trader_off.factor_mining.evaluation import FactorEvaluation
from trader_off.factor_mining.expression import FactorSpec
from trader_off.utils.exceptions import VisualizationDependencyError


def _check_matplotlib():
    """Verify matplotlib is available; raise VisualizationDependencyError if not."""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        raise VisualizationDependencyError(
            "matplotlib is required for visualization, install via `uv add matplotlib`"
        )


# ---------------------------------------------------------------------------
# HTML template — self-contained with inline CSS, uses string.Template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = string.Template(
    """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Factor Evaluation Report</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       margin: 2em; color: #333; background: #fff; }
h1 { color: #1a1a1a; border-bottom: 2px solid #4a90d9; padding-bottom: 0.3em; }
h2 { color: #2c3e50; margin-top: 1.5em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: right; }
th { background-color: #4a90d9; color: #fff; }
tr:nth-child(even) { background-color: #f9f9f9; }
td:first-child, th:first-child { text-align: center; }
td:nth-child(2), th:nth-child(2) { text-align: left; }
img { max-width: 100%; height: auto; margin: 1em 0; border: 1px solid #eee; }
.summary { background: #f0f7ff; padding: 12px 16px; border-left: 4px solid #4a90d9;
           margin: 1em 0; }
.footer { margin-top: 2em; font-size: 0.85em; color: #888; }
</style>
</head>
<body>
<h1>Factor Evaluation Report</h1>
<div class="summary">
<p>This report presents the evaluation results for $factor_count selected factors,
ranked by Information Coefficient IR (ICIR). The ICIR measures the consistency
of a factor's predictive power — higher values indicate more reliable factors.</p>
<p>Selected factors: $factor_count | Report generated at: $generated_at</p>
</div>
<h2>ICIR Ranking</h2>
$table
<h2>Correlation Heatmap</h2>
<img src="figures/correlation_heatmap.png" alt="Correlation Heatmap">
<h2>Top Layer Cumulative Return</h2>
<img src="figures/top_layer_cumret.png" alt="Top Layer Cumulative Return">
<div class="footer">Generated at: $generated_at</div>
</body>
</html>"""
)

# ---------------------------------------------------------------------------
# Markdown template
# ---------------------------------------------------------------------------

_MD_TEMPLATE = string.Template(
    """\
# Factor Evaluation Report

**Generated at:** $generated_at
**Selected Factors:** $factor_count

## Summary

This report presents the evaluation results for $factor_count factors selected
via ICIR ranking and Pearson correlation deduplication.

| Metric | Min | Mean | Max |
|--------|-----|------|-----|
| ICIR | $icir_min | $icir_mean | $icir_max |
| IC Mean | $ic_mean_min | $ic_mean_mean | $ic_mean_max |

## ICIR Ranking

$table

## Selected Factor IDs

$factor_list
"""
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
        corr_matrix: NxN correlation matrix (numpy array).
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


# ---------------------------------------------------------------------------
# Evaluation report generation (FR-0700)
# ---------------------------------------------------------------------------


def render_evaluation_report(
    evaluations: list[FactorEvaluation],
    selected: list[FactorSpec],
    output_dir: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Generate self-contained HTML and Markdown evaluation reports.

    Generates a correlation heatmap and top-layer return chart as PNG figures,
    then produces HTML (self-contained with inline CSS) and GitHub-flavored
    Markdown reports referencing those figures via relative paths.

    The ``evaluations`` list must have the same length and element order as
    ``selected``; each entry corresponds to one selected factor.

    Args:
        evaluations: FactorEvaluation instances, one per selected factor.
        selected: FactorSpec instances, one per selected factor.
        output_dir: Root directory for report output. A ``figures/``
            sub-directory will be created for PNG assets.
        generated_at: Timestamp string for the report. When ``None``,
            defaults to the current UTC time in ISO format.

    Returns:
        A dict mapping ``"html"``, ``"md"``, ``"figures_dir"`` to their
        respective paths.
    """
    output_dir = Path(output_dir)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    n = len(selected)
    pair_count = min(len(evaluations), len(selected))

    # ------------------------------------------------------------------
    # Generate correlation heatmap
    # ------------------------------------------------------------------
    if n >= 2 and pair_count >= 2:
        _check_matplotlib()
        labels = [s.id for s in selected]
        # Use only paired evaluations for correlation computation
        paired_evals = evaluations[:pair_count]
        corr_matrix = _compute_ic_correlation_matrix(paired_evals)
        heatmap_path = figures_dir / "correlation_heatmap.png"
        render_correlation_heatmap(corr_matrix, labels, heatmap_path)
    else:
        heatmap_path = _generate_empty_heatmap(figures_dir)

    # ------------------------------------------------------------------
    # Generate top-layer cumulative return chart
    # ------------------------------------------------------------------
    if pair_count > 0:
        _check_matplotlib()
        _render_top_layer_chart(evaluations[:pair_count], selected[:pair_count], figures_dir)
    else:
        _generate_empty_top_layer_chart(figures_dir)

    # ------------------------------------------------------------------
    # Build HTML and Markdown tables
    # ------------------------------------------------------------------
    if generated_at is None:
        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")  # type: ignore[attr-defined]

    # Sort by ICIR descending for ranking
    ranked = sorted(
        zip(selected[:pair_count], evaluations[:pair_count]),
        key=lambda x: x[1].icir,
        reverse=True,
    )

    html_table, md_table = _build_tables(ranked)

    # Factor ID list for Markdown — with formula detail
    factor_list_lines: list[str] = []
    for spec in selected[:pair_count]:
        factor_list_lines.append(f"- **{spec.id}** ({spec.category}) — `{spec.formula}`")
    factor_list = "\n".join(factor_list_lines)

    # Summary statistics for Markdown
    icirs = [ev.icir for _spec, ev in ranked]
    ic_means = [ev.ic_mean for _spec, ev in ranked]
    icir_min = float(min(icirs)) if icirs else 0.0
    icir_mean = float(np.mean(icirs)) if icirs else 0.0
    icir_max = float(max(icirs)) if icirs else 0.0
    ic_mean_min = float(min(ic_means)) if ic_means else 0.0
    ic_mean_mean = float(np.mean(ic_means)) if ic_means else 0.0
    ic_mean_max = float(max(ic_means)) if ic_means else 0.0

    # ------------------------------------------------------------------
    # Write HTML
    # ------------------------------------------------------------------
    html_path = output_dir / "evaluation_report.html"
    html_content = _HTML_TEMPLATE.substitute(
        table=html_table,
        generated_at=generated_at,
        factor_count=str(pair_count),
    )
    html_path.write_text(html_content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Write Markdown
    # ------------------------------------------------------------------
    md_path = output_dir / "evaluation_report.md"
    md_content = _MD_TEMPLATE.substitute(
        table=md_table,
        generated_at=generated_at,
        factor_list=factor_list,
        factor_count=str(pair_count),
        icir_min=f"{icir_min:.4f}",
        icir_mean=f"{icir_mean:.4f}",
        icir_max=f"{icir_max:.4f}",
        ic_mean_min=f"{ic_mean_min:.4f}",
        ic_mean_mean=f"{ic_mean_mean:.4f}",
        ic_mean_max=f"{ic_mean_max:.4f}",
    )
    md_path.write_text(md_content, encoding="utf-8")

    logger.info("render_evaluation_report done -> html={}, md={}", html_path, md_path)

    return {
        "html": html_path,
        "md": md_path,
        "figures_dir": figures_dir,
    }


# ---------------------------------------------------------------------------
# Internal: table builders
# ---------------------------------------------------------------------------


def _build_tables(
    ranked: list[tuple[FactorSpec, FactorEvaluation]],
) -> tuple[str, str]:
    """Build HTML and Markdown ICIR ranking tables from ranked factor pairs.

    Args:
        ranked: List of (FactorSpec, FactorEvaluation) tuples sorted by ICIR
            descending.

    Returns:
        A tuple of (html_table, md_table) strings.
    """
    html_rows: list[str] = []
    md_rows: list[str] = []
    for rank, (spec, ev) in enumerate(ranked, start=1):
        html_rows.append(
            f"<tr><td>{rank}</td><td>{spec.id}</td><td>{spec.category}</td>"
            f"<td>{ev.icir:.4f}</td><td>{ev.ic_mean:.4f}</td>"
            f"<td>{ev.ic_std:.4f}</td><td>{ev.rank_ic_mean:.4f}</td></tr>"
        )
        md_rows.append(
            f"| {rank} | {spec.id} | {spec.category} | {ev.icir:.4f} | "
            f"{ev.ic_mean:.4f} | {ev.ic_std:.4f} | {ev.rank_ic_mean:.4f} |"
        )

    html_table = (
        "<table>\n<tr><th>Rank</th><th>Factor ID</th><th>Category</th>"
        "<th>ICIR</th><th>IC Mean</th><th>IC Std</th><th>Rank IC Mean</th></tr>\n"
        + "\n".join(html_rows)
        + "\n</table>"
    )

    md_header = "| Rank | Factor ID | Category | ICIR | IC Mean | IC Std | Rank IC Mean |"
    md_sep = "|------|-----------|----------|------|---------|--------|--------------|"
    md_table = "\n".join([md_header, md_sep] + md_rows)

    return html_table, md_table


# ---------------------------------------------------------------------------
# Internal: correlation matrix from IC time series
# ---------------------------------------------------------------------------


def _compute_ic_correlation_matrix(evaluations: list[FactorEvaluation]) -> np.ndarray:
    """Compute NxN Pearson correlation matrix from daily IC time series.

    Each entry (i, j) is the Pearson correlation between the IC time series
    of factor i and factor j, computed on overlapping dates. Requires
    at least 3 overlapping dates; returns 0.0 for pairs with fewer.
    """
    n = len(evaluations)
    corr = np.eye(n)

    for i in range(n):
        for j in range(i + 1, n):
            c = _pearson_ic(evaluations[i], evaluations[j])
            corr[i, j] = c
            corr[j, i] = c

    return corr


def _pearson_ic(a: FactorEvaluation, b: FactorEvaluation) -> float:
    """Pearson correlation of two factors' daily IC time series on overlapping dates."""
    joined = a.ic_ts.join(b.ic_ts, on="date", how="inner", suffix="_b")
    if len(joined) < 3:
        return 0.0
    ic_a = joined["ic"].to_numpy()
    ic_b = joined["ic_b"].to_numpy()
    std_a = np.std(ic_a)
    std_b = np.std(ic_b)
    if std_a < 1e-12 or std_b < 1e-12:
        return 0.0
    return float(np.corrcoef(ic_a, ic_b)[0, 1])


# ---------------------------------------------------------------------------
# Internal: top-layer cumulative return chart
# ---------------------------------------------------------------------------


def _render_top_layer_chart(
    evaluations: list[FactorEvaluation],
    selected: list[FactorSpec],
    figures_dir: Path,
) -> None:
    """Render a bar chart of per-layer mean returns for the top-ranked factor."""
    # Find top factor by ICIR
    best_idx = max(range(len(evaluations)), key=lambda i: evaluations[i].icir)
    best_eval = evaluations[best_idx]
    best_spec = selected[best_idx]

    lr = best_eval.layered_returns
    if "layer" not in lr.columns or "mean_return" not in lr.columns:
        return

    layers = lr["layer"].to_list()
    returns = lr["mean_return"].to_list()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = ["#2ecc71" if r >= 0 else "#e74c3c" for r in returns]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(layers, returns, color=colors, edgecolor="#333")
    ax.axhline(y=0, color="#888", linewidth=0.8)
    ax.set_xlabel("Layer")
    ax.set_ylabel("Mean Return")
    ax.set_title(f"Layered Returns — {best_spec.id} (ICIR={best_eval.icir:.4f})")
    ax.set_xticks(layers)
    plt.tight_layout()
    fig.savefig(figures_dir / "top_layer_cumret.png")
    plt.close(fig)


def _generate_empty_heatmap(figures_dir: Path) -> Path:
    """Generate a minimal placeholder heatmap when no factors are available."""
    _check_matplotlib()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.text(0.5, 0.5, "No correlation data available", ha="center", va="center")
    ax.set_title("Correlation Heatmap")
    path = figures_dir / "correlation_heatmap.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def _generate_empty_top_layer_chart(figures_dir: Path) -> None:
    """Generate a minimal placeholder chart when no factors are available."""
    _check_matplotlib()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.text(0.5, 0.5, "No layered return data available", ha="center", va="center")
    ax.set_title("Top Layer Cumulative Return")
    path = figures_dir / "top_layer_cumret.png"
    fig.savefig(path)
    plt.close(fig)
