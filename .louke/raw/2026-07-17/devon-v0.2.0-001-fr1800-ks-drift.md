---
date: 2026-07-17
session: devon-v0.2.0-001-fr1800-ks-drift
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#46]
status: resolved
supersedes: []
---

## Topic
FR-1800 KS drift detection: implement `compute_ks_pvalue`, `compute_feature_ks`, and `detect_ks` using scipy.stats.ks_2samp in `src/trader_off/scheduler/drift/ks.py`.

## Decision
- **File**: `src/trader_off/scheduler/drift/ks.py` (45 lines, 100% coverage)
- **Tests**: `tests/unit/scheduler/test_ks.py` (16 tests)
- **Functions**:
  - `compute_ks_pvalue(baseline, current) -> float`: wraps scipy.stats.ks_2samp, returns p-value
  - `compute_feature_ks(baseline_df, current_df, feature_cols, *, threshold=0.05) -> pl.DataFrame`: batch per-feature KS with k_statistic, p_value, is_drift columns
  - `detect_ks(reference, current, *, threshold=0.05) -> DriftResult`: convenience wrapper using DriftResult from drift.result (method="ks", score=KS_statistic, is_drift=p_value < threshold, bin_edges=[])
- **ACs covered**: AC-FR1800-01 (p>0.05 same dist), AC-FR1800-02 (p<0.001 2σ shift), AC-FR1800-03 (NaN baseline → 0.0/1.0/False + WARNING)
- **Commit**: `61206c9` (`feat: green – #46 – KS drift detection`)

## Tried but abandoned
- **0.5σ shift with N=1000 as moderate shift**: KS test is too sensitive — p-value was ~4e-20. Switched to 0.2σ with N=100.
- **Custom threshold test with 0.5σ shift**: p-value far below 0.001 for large N. Switched to same-distribution (N=30) with strict threshold=0.001.

## Open questions
None — all ACs covered, 100% coverage, zero lint errors, 31 tests pass (16 KS + 15 PSI).
