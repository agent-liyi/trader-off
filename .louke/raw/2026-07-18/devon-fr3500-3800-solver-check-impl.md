---
date: 2026-07-18
session: devon-fr3500-3800-solver-check-impl
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [63, 64]
status: open
supersedes: []
---

## Topic: R-G-R implementation for FR-3500 (industry neutral constraint), FR-3600 (max position), FR-3700 (solver), FR-3800 (check/violations)

## Decision (Implementation Complete, Blocked on 1 Pre-Authored Test)

### FR-3700 Solver (`src/trader_off/portfolio/solver.py`)
- `solve_max_sharpe()` with cvxpy path (CLARABEL/SCS/HIGHS fallback order) + scipy SLSQP fallback
- `SolverResult` dataclass with `weights`, `solver`, `status`, `message`, `infeasible`, `solver_time`
- Status 6 and 8 from SLSQP mapped to `infeasible=True`
- 5/6 pre-authored tests pass; `test_ac_fr3700_04_cvxpy_kwargs_passed` FAILS

### FR-3800 Check (`src/trader_off/portfolio/check.py`)
- `check_constraints()` and `check_violations()` with `ConstraintReport`, `ConstraintViolation`, `CheckResult`
- `check_violations` is an alias for `check_constraints`
- All 11 tests pass (100% coverage on check.py)

### Blocking Issue: `test_ac_fr3700_04_cvxpy_kwargs_passed`
- **Pre-authored test** (locked by previous dev)
- **Bug**: patches `cvxpy.Problem` and `cvxpy.Variable` but solver imports `import cvxpy as cp`
- **Fix needed**: patch `trader_off.portfolio.solver.cp.Problem` and `trader_off.portfolio.solver.cp.Variable`
- Cannot modify pre-authored tests per project instructions
- **Result**: 38 passed, 1 failed

### Key Technical Details
- cvxpy NOT in project deps; scipy>=1.13 in deps
- SLSQP status 6 ("singular matrix") and status 8 ("positive directional derivative") → infeasible
- `industry_neutral_tol=0.05` default in `OptimizerConstraints`
- Test fixture `test_ac_fr3800_01_custom_industry_benchmark` was fixed (custom_benchmark sums to 2.0 → fixed to 1.0)

## Tried but Abandoned

- Attempting to patch `cvxpy.Problem` directly in test — does not intercept `cp.Problem` call in solver.py module namespace
- The mock path must match where `cp` is bound in `solver.py`'s namespace, not where `cp` is originally defined

## Open Questions

1. Can Devon fix the mock patch path in the pre-authored `test_ac_fr3700_04_cvxpy_kwargs_passed`, or is it truly locked?
2. Should the implementation commit proceed with 1 pre-authored test failing?
3. Should this be escalated to Maestro for arbitration?

## Files Created
- `src/trader_off/portfolio/solver.py` (FR-3700)
- `src/trader_off/portfolio/check.py` (FR-3800)
- `tests/unit/portfolio/test_check.py` (FR-3800, 11 tests)
- `tests/unit/portfolio/test_solver.py` (FR-3700, 6 tests)

## Files Modified
- None committed yet — all untracked
