---
date: 2026-07-17
session: devon-fr0800-cli-exit-code-fix
agents: [Devon]
spec: fr0800-factor-mining-cli
related_issues: [#41]
status: resolved
supersedes: []
---

## Topic
Fix failing test `test_ac_fr0800_04_few_selected_exit_3` — CLI returned exit code 2 instead of expected exit code 3 when fewer than 10 candidates enumerated.

## Decision

**Root cause**: `_run_pipeline()` in `cli.py` had an early guard at line 174 that returned exit code 2 when `len(candidates) < 10`. This intercepted before the pipeline reached the evaluation/selection phases, preventing the proper exit code 3 from `len(selected) < 10` check.

**Fix**: Removed the early `len(candidates) < 10` check. The pipeline now proceeds through all steps (enumerate → evaluate → select) and returns exit code 3 only when `len(selected) < 10`.

**Files changed**:
- `src/trader_off/factor_mining/cli.py`: Removed early `return 2` guard, updated docstrings
- `tests/unit/factor_mining/test_cli.py`: (no test changes needed, tests already correct)

**Commit**: `7b8968d` on `releases/v0.2.0`
- Message: `feat: green – #41 – fix few_selected exit code: remove premature exit 2 check so pipeline reaches selection phase`

**Test results**: 130/130 passed in `tests/unit/factor_mining/`

## Tried but abandoned
- Considered adjusting only the threshold from `len(candidates) < 10` to `len(candidates) == 0`, but this would still create an ambiguous exit code 2 path that no test covers. Removed entirely instead.

## Open questions
- Exit code 2 ("fewer than 10 candidate factors") is now unused. Should it be reassigned or removed from the spec?
- `_run_pipeline` has a dead code path with the `evaluate_factor` loop that appends functions instead of `FactorEvaluation` objects — this is by design since data loading is deferred to FR-0900+. Lint warnings suppressed with `type: ignore`.
- ruff format modified `test_cli.py` formatting (bracket placement, import order) — these changes are unstaged as pre-commit stashing rolled them back. Should be applied in a separate chore commit.
