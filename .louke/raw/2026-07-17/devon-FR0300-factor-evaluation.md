---
date: 2026-07-17
session: devon-FR0300-factor-evaluation
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#36]
status: resolved
supersedes: []
---

## Topic
FR-0300: 因子评估 — IC / ICIR / Rank IC (issue #36)

## Decision

### Implementation approach
- Created `src/trader_off/factor_mining/evaluation.py` with `FactorEvaluation` (frozen dataclass) and `evaluate_factor()` function
- **Reused** v0.1.0 `trader_off.evaluation.ic` for `ic_pearson`, `ic_spearman`, `compute_layered_returns`
- Input: `factor_values` (columns: asset, date, value) + `labels` (columns: asset, date, label) + `dates: list[date]`
- Output: FactorEvaluation with ic_ts, rank_ic_ts, ic_mean, ic_std, icir, rank_ic_mean, rank_ic_std, layered_returns
- ICIR = ic_mean / ic_std; when std == 0 → 0.0 + WARNING log

### Key design decisions
- Used `_safe_mean` / `_safe_std` helpers filtering NaN values (avoids numpy warnings from constant-factor edges)
- Extracted `_factor_values_to_predictions` to eliminate duplicate `rename({"value": "score"})`
- `validate_columns` raises ValueError for missing columns
- Empty merged data returns zero-filled FactorEvaluation

### Tests
- 13 tests covering all 5 ACs: structure validation, perfect positive/negative correlation, zero std, v0.1.0 reuse verification, edge cases (missing columns, no overlapping data, extra dates)
- Coverage: 100% on evaluation.py

### Commits
- `4ce3e5c` feat: green – #36 – Implement FactorEvaluation and evaluate_factor reusing v0.1.0 evaluation.ic
- `ecf8c59` refactor: – #36 – Extract _safe_mean/_safe_std helpers, eliminate duplicate rename, add edge case tests

## Tried but abandoned
- **numpy nanmean/nanstd direct**: caused RuntimeWarning noise ("Mean of empty slice", "Degrees of freedom <= 0"); replaced with manual NaN-filter approach
- **pytest-cov inline**: caused "cannot load module more than once per process" on macOS; used separate `coverage run` pass

## Open questions
- None. v0.1.0 evaluation.ic was fully reusable as-is — no wrapper needed beyond column rename (value→score).
