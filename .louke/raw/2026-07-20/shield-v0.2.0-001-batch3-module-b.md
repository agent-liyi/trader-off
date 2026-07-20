---
date: 2026-07-20
session: shield-v0.2.0-001-batch3-module-b
agents: [Shield]
spec: v0.2.0-001-factor-mining-retrain-optimizer
# T-1 (ClockPort), T-2 (TrainerPort) well-formed in scheduler/ports.py
# T-3 (next_cron_fire) pure function tested in scheduler CLI tests
# T-4 (configurable output dirs) verified via tmp_path isolation
related_issues: []
status: resolved
---

## Topic
M-E2E Batch 3 — Module B (scheduler) integration tests: 6 files covering
retrain CLI/API, full/incremental retrain pipeline, deploy + hot-reload,
scheduler CLI + config validation, and crash resilience.

## Decision

Wrote 42 integration tests across 6 files in `tests/integration/`:

| File | Tests | AC Coverage |
|------|-------|-------------|
| `test_retrain_cli_api.py` | 9 | AC-FR2000-01~04, AC-NFR0700-04 |
| `test_retrain_full.py` | 5 | AC-FR2100-01~04 |
| `test_retrain_incremental.py` | 4 | AC-FR2200-01~04 |
| `test_deploy.py` | 5 | AC-FR2400-01~04 |
| `test_scheduler_cli.py` | 10 | AC-FR2700-01~04 |
| `test_scheduler_resilience.py` | 9 | AC-FR2500-02/03, AC-NFR0900-01~03 |

All tests marked `@pytest.mark.integration`, pass with:
`uv run pytest tests/integration -m integration -v` → **76 passed, 1 skipped**

### Coding caveats resolved:

1. **Race condition in polling**: Original `for _ in range(100): if active_tasks==0: break` loop
   would exit immediately before tasks dequeued. Fixed by adding `_wait_for_task_completion()`
   helper that double-checks after a short re-sleep.

2. **aiohttp_client fixture unavailable**: No `pytest-aiohttp` plugin. Replaced with
   `_fetch()` helper using `web.TCPSite` on random port + `aiohttp.ClientSession`.

3. **Timestamp collision in DefaultTrainerPort.save()**: `save_model()` auto-generates
   `YYYYMMDD_HHMMSS` directories. Multiple saves in <1s raise `ModelVersionExistsError`.
   Workaround: added `asyncio.sleep(1.1)` in tracking trainer's save() for incremental tests.

4. **parent_version not propagated to save()**: `_TrackingTrainerPort` auto-resolves parent
   during `train()` but scheduler passes `task.parent_version==None` to `save()`.
   Workaround: stored `_resolved_parent` and used in `save()`.

5. **lgb.Booster constructor fails with `Data list can only be of ndarray`**: Switched
   to `lgb.train()` with numpy arrays for the version conflict test model.

## Tried but abandoned

- Using `aiohttp.test_utils.AioHTTPTestCase` — too heavyweight for simple integration tests.
- Mocking `DefaultTrainerPort.train()` — loses real train/save integration coverage.
- Using `time.sleep(0.15)` for timestamp collision — still within same second.
- Skipping parent_version chain test — valuable for verifying refit behavior end-to-end.

## Open questions

- `test_scheduler_resilience.py::test_ac_nfr0900_02_subprocess_sigkill` uses `PYTHONPATH`
  injection; may need adjustment in CI where src layout differs.
- `DefaultTrainerPort.save()` generates timestamp-based versions → 1-second collision risk
  is a production concern worth an issue.
