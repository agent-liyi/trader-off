---
date: 2026-07-17
session: devon-v0.2.0-001-fr0500-heatmap
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#38]
status: resolved
---

## Topic
FR-0500 相关性热力图输出 — `render_correlation_heatmap` in `trader_off.factor_mining.viz`

## Decision

Implemented `render_correlation_heatmap(corr_matrix, labels, output_path, figsize=(12,10), dpi=120) -> Path` following the interfaces.md §3.5 contract.

Key implementation choices:
- Reused v0.1.0 patterns: `_check_matplotlib()`, `matplotlib.use("Agg")`, `plt.close(fig)`
- Colormap: `RdBu_r` with vmin=-1, vmax=1 (as specified in interfaces.md §2.8)
- Dense label auto-shrink: fontsize=6 when n >= 30, with `logger.info("densely labeled, font shrunk")`
- Default fontsize for non-dense: 10

Tests (3 ACs, all passing):
1. AC-FR0500-01: PNG file existence + size > 5KB (20x20 matrix)
2. AC-FR0500-02: Image dimensions 1200×1440 (H×W) using `matplotlib.image.imread`
3. AC-FR0500-03: Dense labels (n=30) trigger font shrink + log message

Commit: `dee891a` feat: green – #38 – add render_correlation_heatmap in factor_mining.viz

## Tried but abandoned

1. **loguru caplog for AC-03**: Tried `caplog` fixture (stdlib logging) but loguru doesn't propagate to stdlib by default. Used `io.StringIO` sink instead.

2. **Fontsize check via `plt.gcf()`**: Considered monkeypatching `plt.close` to inspect axes fontsize. Chose log-based approach as it matches AC-03's "或" (OR) alternative.

3. **Extracting `_check_matplotlib` to shared location**: Considered but rejected — only 6 lines, premature abstraction.

## Open questions

1. `_check_matplotlib` has two copies (`visualization/plots.py` and `factor_mining/viz.py`). Both private. Future Librarian may warrant extracting to `utils`.

2. Coverage report could not be generated due to `ImportError: cannot load module more than once per process` when combining `--cov` with matplotlib/numpy in the uv build cache. Manual inspection: all code paths covered except `_check_matplotlib`'s `except ImportError` branch (requires uninstalling matplotlib).

3. Pre-commit mypy v1.18.1 conflicts with ruff UP007 on `Union[Path, str]` vs `Path | str`. Fixed with `# noqa: UP007` on `logging.py`. This is a toolchain-level issue that may recur.
