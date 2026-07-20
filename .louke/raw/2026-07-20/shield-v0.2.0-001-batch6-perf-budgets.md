---
date: 2026-07-20
session: shield-v0.2.0-001-batch6-perf-budgets
agents: [Shield]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: []
status: resolved
supersedes: []
---

## Topic
M-E2E Batch 6 — extend tests/perf/test_perf_budget.py to fully cover NFR-0100
all 5 AC (AC-NFR0100-01 through AC-NFR0100-05).

## Decision
Extended tests/perf/test_perf_budget.py from 3 unit-level baselines to 8 tests:

1. `test_enumerate_factors_small_fixture_perf` — existing, unchanged
2. `test_select_factors_small_fixture_perf` — existing, unchanged
3. `test_psutil_available_or_deferred` — existing, renamed class to TestPerfMemoryGate
4. `test_mine_factors_pipeline_perf` — NEW AC-NFR0100-01: enumerate + evaluate + select
   pipeline within 600s budget. Measured ~0.5s.
5. `test_predict_4000_assets_perf` — NEW AC-NFR0100-02: predict over 4000 assets
   within 5s budget. Currently takes ~8.8s, exceeding budget.
6. `test_backtest_1year_50assets_perf` — NEW AC-NFR0100-03: run_backtest 1y window
   within 600s budget. Measured ~0.003s (synthetic data).
7. `test_peak_memory_below_16gb` — NEW AC-NFR0100-04: psutil RSS check ≤16GB.
   Skipped (psutil not installed).
8. `test_incremental_retrain_perf` — NEW AC-NFR0100-05: DefaultTrainerPort
   incremental refit within 60s. Measured ~0.5s. Fixed version collision
   with `await asyncio.sleep(1.1)` workaround since save auto-generates
   timestamp-based versions.

All new tests: @pytest.mark.perf + @pytest.mark.e2e + @pytest.mark.timeout(1.1x budget).

## Tried but abandoned
- Using subprocess.run for mine-factors CLI: `trader-off` is not registered as
  a console script and the CLI's evaluation step is broken. Switched to direct
  Python function invocation.
- Using `sharpe` as backtest summary key: actual key is `sharpe_ratio`.
- Passing version=None to avoid incremental save collision: DefaultTrainerPort
  doesn't expose version parameter. Used sleep workaround instead.

## Open questions
- AC-NFR0100-02 predict budget (5s for 4000 assets) is not met by current
  code (~8.8s). The bottleneck is per-asset for-loop in prediction/service.py
  calling compute_momentum_features + compute_volatility_features +
  compute_volume_features for each asset. Optimization needed.
- psutil not installed — memory budget check is deferred.
- No dedicated CI step for perf tests; they require explicit `-m perf` or
  `-m e2e` invocation.

## Results
- Commit: 9df4d0c (releases/v0.2.0)
- 5 passed, 2 skipped (psutil), 1 failed (predict budget exceeded)
