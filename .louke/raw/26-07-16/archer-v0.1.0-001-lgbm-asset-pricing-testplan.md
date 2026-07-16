---
date: 2026-07-16
session: archer-v0.1.0-001-lgbm-asset-pricing-testplan
agents: [Archer]
spec: v0.1.0-001-lgbm-asset-pricing
related_issues: ["#6-#28"]
status: resolved
supersedes: []
---

## Topic
M-TESTPLAN Stage 1: produce test-plan.md for the lightGBM A-share pricing model (23 FR/NFR, 79 AC).

## Decision
- Wrote `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/test-plan.md` (604 lines) following `.louke/templates/test-plan.md` structure.
- Strategy: 3-layer pyramid — unit (Devon, L1) / integration (Shield, L2) / e2e (Shield, L1 full pipeline).
- Tooling: pytest + pytest-cov + pytest-asyncio + pytest-mock; polars/numpy/scipy for ground truth; matplotlib Agg for viz tests.
- Ground truth isolation: `tests/ground_truth/` scripts forbidden to `import trader_off.*` (scipy.stats as IC reference, independent max-drawdown script).
- millionaire boundary: fetcher = external dep (replace with fixture DataLoader stand-in); broker/BacktestRunner/strategy logic = under-test (mock broker only in unit tests for call-count, use real components in e2e).
- E2E contract (§6.5): single file `tests/e2e/test_lgbm_pipeline.py`, 10 stocks × 60 days fixture, train→predict→backtest→reports, ≤60s, no network. `[e2e]`/`[integration]` TOML sections deferred to Stage 2 (M-ARCH).
- AC coverage: 79/79 explicit AC-FRXXXX-YY references; 73 test functions + 6 CI gates.
- validate-test-plan exit 0 → author-result.json verdict=pass persisted.
- Commits: f5070a8 (initial), 42b7577 (AC ref fix: expand `~` range notation + add NFR-0300 subsection).

## Tried but abandoned
- Range notation `AC-FRXXXX-01~03` in tables — check_acs.py regex only matches explicit 2-digit AC refs, so ranges left AC-02/03 uncounted. Fixed by expanding to explicit comma-separated refs.
- Initially omitted a dedicated NFR-0300 subsection (only had it in summary table without explicit AC-NFR0300-01 ref). Added subsection.
- Considered writing `[e2e]`/`[integration]` into project.toml now, but per Archer.md §5.3.4 those belong to Stage 2 (M-ARCH); documented the planned contract in test-plan §6.5 instead.

## Open questions
- Stage 2 (M-ARCH): must materialize `[integration]`/`[e2e]` sections into project.toml, and mark cross-module `modules` column in interfaces.md so Shield has an integration-test checklist.
- The `current_stage` field in project.toml was advanced M-FOUND→M-TESTPLAN by Maestro; confirmed legitimate state transition (committed).
- pytest-timeout / pytest-socket may be needed for AC-FR1500-02 (≤60s) and AC-FR1500-03 (no network) — Devon to add as dev deps.
