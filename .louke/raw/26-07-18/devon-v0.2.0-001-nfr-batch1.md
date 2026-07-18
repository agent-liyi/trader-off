---
date: 2026-07-18
session: devon-v0.2.0-001-nfr-batch1
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#69, #74, #75, #76]
status: resolved
---

## NFR-0100 perf budget (#69) — AC coverage

- **AC-1..AC-3, AC-5**: e2e/perf timings belong to Shield (M-E2E). Unit-level perf benchmarks added in `tests/perf/test_perf_budget.py` with `@pytest.mark.perf`.
  - `enumerate_factors` with N=1..10: < 1s threshold
  - `select_factors` with 30 candidates: < 0.5s threshold
  - `baselines.json` fixture baseline reference
- **AC-4 (memory)**: psutil check that skips if not installed, defers to Shield otherwise.
- Added `perf` marker to `pyproject.toml`.

## NFR-0600 logging (#74) — AC coverage

- **AC-1 (structured format)**: `setup_logger(format="json")` uses loguru's `serialize=True` for JSON lines. `format="text"` for human-readable.
- **AC-2 (per-module log files)**: Already implemented (module prefix in filename).
- **AC-3 (level via env)**: `LOG_LEVEL` env var read at setup time; default INFO.
- **AC-4 (no PII)**: Docstring note + test verifying no PII keys in JSON output.
- Tests: `fresh_logger` autouse fixture to isolate loguru state between tests (critical — loguru's global `min_level` persists across `logger.remove()` calls).
- Note: loguru's global min_level vs per-handler level is a subtle interaction; using explicit `level=` on test capture sinks works around it.

## NFR-0700 security (#75) — AC coverage

- **bandit**: Clean (0 issues). Config in `pyproject.toml [tool.bandit]` already existed.
- **pip-audit**: Available via `uv tool run pip-audit`. No vulnerabilities found.
- **No hardcoded secrets**: `grep -rE` test verifies no `api_key/password/token/secret = '...'` in source.
- **scripts/security_check.sh**: Unified script for bandit + ruff + pip-audit.
- Did NOT add to pre-commit (bandit already in dev deps but not pre-commit hook). Note: pre-commit config does not include bandit; could be a gap to flag.

## NFR-0800 reproducibility (#76) — AC coverage

- **AC-1 (deterministic seeds)**: Created `trader_off.utils.random.set_seed(seed)`. Seeds numpy and Python random. Explicit seed required (None/-1 raise ValueError). No lightgbm global seed call (LGBM trains with per-model random_state in params, not global).
- **AC-2 (frozen deps)**: `uv.lock` exists and is valid TOML. `pyproject.toml` deps have explicit `>=version` constraints.
- **AC-3 (fixture versioning)**: Not implemented — no fixture versioning system exists in codebase. Could be a gap to flag for Archer.

## Commits

| NFR | Commit | Files |
|-----|--------|-------|
| #69 NFR-0100 | `c097ebd` | `tests/perf/test_perf_budget.py`, `tests/perf/baselines.json`, `pyproject.toml` |
| #74 NFR-0600 | `08b3b7b` | `src/trader_off/utils/logging.py`, `tests/unit/utils/test_logging.py` |
| #75 NFR-0700 | `b2e3202` | `scripts/security_check.sh`, `tests/unit/nfr/test_nfr_0700_security.py` |
| #76 NFR-0800 | `77f289d` | `src/trader_off/utils/random.py`, `tests/unit/nfr/test_nfr_0800_reproducibility.py` |

## Final test count

- **570 → 586 passed** (16 new tests across 4 NFRs, no regressions)

## Open questions

1. **NFR-0700 pre-commit gap**: `.pre-commit-config.yaml` does NOT include bandit or pip-audit. Should it? Archer may need to decide.
2. **NFR-0800 fixture versioning**: AC-3 mentions "fixture versioning" but no such system exists. Could be out-of-scope or deferred.
3. **NFR-0100 AC-4 memory**: psutil is not a dependency. If memory tracking is critical, psutil should be added to deps.
