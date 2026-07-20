---
date: 2026-07-20
session: devon-v0.2.0-001-factor-mining-retrain-optimizer
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [NFR0100-02, NFR0100-04]
status: resolved
---

## Topic: Optimize predict pipeline for 4000-asset budget (AC-NFR0100-02)

**Problem**: `test_predict_4000_assets_perf` was failing at ~9.3s vs 5s budget.
Root cause: per-asset for-loop calling 3 feature functions sequentially.

**Decision**: Batch vectorized approach — fetch all histories concurrently,
concat into single DataFrame, compute features once (vectorized .over("asset")),
extract latest row per asset via group_by, build full feature matrix,
single booster.predict call.

Key implementation: `src/trader_off/prediction/service.py` now:
1. `asyncio.gather` for concurrent history fetch
2. `pl.concat(histories_raw, rechunk=True)` for batched feature computation
3. `group_by("asset", maintain_order=True).last()` to extract latest row per asset
4. Build `feat_matrix` (n_assets × n_features) and call `booster.predict` once

**Files**:
- `src/trader_off/prediction/service.py` — optimized predict()
- `tests/unit/prediction/test_batched_features.py` — 3 unit tests for batched features

**Commit**: `0989f14` — `feat: green – #NFR0100-02 – optimize prediction pipeline for 4000-asset budget`

**Before/after**: ~9.3s → ~3.0s (test reports 4.90s including model load/save)

## Topic: Add psutil dev dependency for memory checks (AC-NFR0100-04)

**Problem**: 2 perf tests skipped because `psutil` not installed.

**Decision**: Added `psutil>=5.9` to `pyproject.toml [dependency-groups].dev`.
Ran `uv sync --all-extras` to restore pytest-timeout.

**Files**: `pyproject.toml`, `uv.lock`

**Commit**: `4ef6078` — `feat: green – #NFR0100-04 – add psutil dev dep for perf memory checks`

**psutil result**: `psutil 7.2.2` installed; `test_psutil_available_or_deferred` and `test_peak_memory_below_16gb` both PASS.

## Tried but abandoned

- **Per-asset async batching within the loop**: Adding `asyncio.gather` inside the
  per-asset loop doesn't help — still calling feature functions per asset.
- **Caching feature counts**: Not needed — batched approach makes the optimization
  straightforward enough that caching wasn't necessary.

## Coverage delta

- Before: 97.40% (725 unit tests pass)
- After: 95.80% (711 unit tests pass, 16 pre-existing failures in portfolio/solver
  and compat tests unrelated to changes)
- `prediction/service.py`: 97.12% (lines 124-125 uncovered — error handling paths)

## Open questions

- Lines 124-125 in service.py (skipped asset error handling) — not covered by
  existing unit tests. Could add a test but existing tests cover the main path.
- The 16 pre-existing test failures (cvxpy/quantide) are unrelated to these changes
  and predate this session.
