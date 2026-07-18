---
date: 2026-07-17
session: devon-fr0700-report-impl
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#40]
status: resolved
---

## Topic
FR-0700: Factor evaluation report generation — self-contained HTML + GitHub-flavored Markdown.

## Decision
Implemented `render_evaluation_report()` in `src/trader_off/factor_mining/viz.py` following R-G-R cycle:

1. **Red**: Wrote 7 tests in `tests/unit/factor_mining/test_reports.py` covering:
   - AC-01: dict structure, file existence, size >5KB (50 factors)
   - AC-02: HTML content verification (title, h1, table, img tags, ICIR)
   - AC-03: Markdown content verification (heading, pipe table, factor IDs)
   - AC-04: No jinja2 dependency
   - Deterministic output with fixed timestamps
   - Empty input handling
   - Single factor edge case

2. **Green**: Implemented in `src/trader_off/factor_mining/viz.py`:
   - `render_evaluation_report(evaluations, selected, output_dir, *, generated_at=None) -> dict[str, Path]`
   - Returns `{"html", "md", "figures_dir"}`
   - HTML: self-contained with inline CSS using `string.Template`
   - Markdown: GFM tables with summary statistics
   - Internal functions: `_build_tables()`, `_compute_ic_correlation_matrix()`, `_pearson_ic()`, `_render_top_layer_chart()`, `_generate_empty_heatmap()`, `_generate_empty_top_layer_chart()`

3. **Refactor**: Extracted `_build_tables()` helper to reduce complexity of `render_evaluation_report()`.

## Key design choices
- Matches evaluations to selected FactorSpecs by list index (1:1 alignment assumed)
- Correlation heatmap computed from daily IC time series
- Top-layer chart is a bar chart of per-layer mean returns for the top-ranked factor
- `generated_at` parameter allows deterministic output in tests
- Used `datetime.UTC` with `# type: ignore[attr-defined]` for mypy compatibility
- Placeholder charts generated for empty input cases

## Tried but abandoned
- Jinja2 templates: explicitly forbidden by AC-FR0700-04
- Non-deterministic timestamps: fixed by adding `generated_at` parameter
- Matching evaluations to FactorSpecs by FactorSpec.id: would require FactorSpec list not in signature; kept index-based matching

## Open questions
- `_pearson_ic()` duplicates logic from `selection.py:_pearson_ic_correlation()` — should be extracted to shared utility
- Coverage at 97% (5 missed lines in edge cases: matplotlib ImportError handler, zero-std correlation, missing layered returns columns)

## Commits
- `c21c95c`: feat: green – #40 – implement render_evaluation_report for HTML+Markdown factor evaluation reports
- `e6709a4`: refactor – #40 – extract _build_tables helper, simplify render_evaluation_report

## Test summary
- 125 tests total in factor_mining unit suite, all passing
- 7 new tests for FR-0700
- 0 regressions in existing FR-0500 tests
