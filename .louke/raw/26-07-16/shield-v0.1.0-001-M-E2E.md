---
date: 2026-07-16
session: shield-v0.1.0-001-M-E2E
agents: [Shield]
spec: v0.1.0-001-lgbm-asset-pricing
related_issues: []
status: resolved
supersedes: []
---

## Topic
M-E2E: Write e2e and integration tests per test-plan §6 and §8.2

## Decision
1. **E2E test augmented** (`tests/e2e/test_lgbm_pipeline.py`):
   - Expanded `test_ac_fr1500_01_full_pipeline` to cover all 8 pipeline steps:
     fixture→train→save(5 files)→predict(ranked)→backtest(reports)→importance→evaluation(CSV)→visualization(3 PNGs)
   - Added `test_ac_fr1500_02_runtime_standalone` standalone AC traceability test (runtime assertion lives in 01)
   - Enhanced `test_ac_fr1500_03_fixtures_exist` with schema validation
   - Removed `pytest.skip` anti-patterns, replaced with `assert` preconditions
   - Fixed import paths: `trader_off.visualization` (not `.render`), `trader_off.training.feature_importance` (not `trader_off.importance`)
   - Runtime: 0.90s (≪ 60s/90s bound)

2. **Integration tests written** (7 files, `tests/integration/`):
   - `test_train_pipeline.py` (2 tests): AC-FR0700-05, AC-FR0800-03
   - `test_predict_service.py` (3 tests): AC-FR0900-01/02/03
   - `test_backtest_cli.py` (4 tests): AC-FR1100-01/02/03, AC-FR1200-01
   - `test_eval_output.py` (2 tests): AC-FR1300-04/01
   - `test_feature_importance_cli.py` (2 tests): AC-FR1400-01/02
   - `test_cli_override.py` (3 tests): AC-NFR0700-02, AC-NFR0700-01
   - `test_real_fetcher.py` (1 test, L3 skip): AC-NFR0100-02

3. **Results**: 128 passed (109 unit + 16 integration + 3 e2e) + 1 L3 skipped

## Tried but abandoned
- Using `pytest.skip` as defensive coding — per test-plan §1.3 anti-pattern #2, replaced with assertions
- Importing from `trader_off.visualization.render` — module is actually `trader_off.visualization.plots`
- Importing from `trader_off.importance.extractor` — module is at `trader_off.training.feature_importance`
- Using `how='outer'` for polars join — deprecated, changed to `how='full'`

## Open questions
- None. M-E2E is complete, ready for Prism review.
