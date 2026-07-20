---
date: 2026-07-20
session: shield-v0.2.0-001-batch2-integration
agents: [Shield]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: []
status: resolved
supersedes: []
---

## Topic
M-E2E Batch 2 — Module A integration tests: factor mining CLI and train with registry.

## Decision
Wrote 2 integration test files (18 tests total), all passing:

1. **`tests/integration/test_factor_mining_cli.py`** (10 tests, AC-FR0800-01~05)
   - Calls CLI entry `main()` with real `enumerate_factors`, `select_factors`, `save_factor_registry`
   - Only `evaluate_factor` is mocked (CLI pipeline doesn't yet have data loading wiring)
   - Covers exit codes 0/3/4, stdout messages, config validation, registry file output
   - Known gap: `test_cli_exit_4_on_bad_yaml` — YAML parse errors are not caught gracefully by CLI (documented)

2. **`tests/integration/test_train_with_registry.py`** (8 tests, AC-FR0900-01~03 + NFR-1000 compat)
   - Cross-module: factor_mining.registry → factor_mining.score → training.trainer
   - Generates real FactorSpecs via `enumerate_factors`, computes factor scores, trains lightGBM
   - Verifies feature_names ↔ factor ID synchronisation
   - Tests legacy fallback when no registry is provided (raw OHLCV features)
   - Model serialization roundtrip tested (joblib save/load with metadata)

No `src/` modifications — pure integration tests.

Commit: `c9b83fb` on `releases/v0.2.0`

## Tried but abandoned
- Tried mocking `Path.mkdir` in `test_cli_pipeline_writes_registry` — but `save_factor_registry` uses `tempfile.mkstemp` inside the registry dir, which requires the directory to actually exist. Switched to unmocked mkdir.
- Tried using `caplog` to assert loguru WARNING messages — but `caplog` only captures Python `logging` module, not loguru. Switched to `capsys` for stdout assertion + reliance on pytest's own stderr capture for log display.
- Tried truly malformed YAML (NUL byte, tab chars) — `yaml.safe_load` is very lenient and parses even malformed input. Current CLI doesn't catch parse errors gracefully (known gap documented in test).

## Open questions
- CLI pipeline's `_run_pipeline` has a stub `evaluate_factor` path that appends raw function objects instead of calling them with data. Full data loading integration is pending FR-0900+ work.
- No `selected_factors.json` is written by the CLI pipeline — only `factors.yaml`. The save_selected_factors function exists in interfaces.md but isn't called from CLI.
