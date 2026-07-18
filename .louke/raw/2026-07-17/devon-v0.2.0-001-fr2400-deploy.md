---
date: 2026-07-17
session: devon-v0.2.0-001-fr2400-deploy
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#52]
status: resolved
---

## Topic
FR-2400: Automatic model deployment to prediction service — implement `deploy_model` and `watch_registry` in `src/trader_off/scheduler/deploy.py`.

## Decision
- **`deploy_model(registry, new_version, *, metrics, ic_floor, logs_dir) -> bool`**: Validates `test_ic_mean >= ic_floor`, atomically updates `registry.current_version` via `rollback_to()` (already atomic write), appends `logs/deploy.log`.
- **`watch_registry(registry_path, on_change, *, poll_interval_sec=60.0)`**: Async polling loop monitoring `registry.json` for `current_version` changes. First poll does NOT trigger callback (baseline establishment). Subsequent polls trigger `on_change` when version differs from last observed value.
- Used stdlib `logging` instead of `loguru` for testability (caplog compatibility).
- Atomic pointer swap: leverages `ModelRegistry.rollback_to()` which uses temp+rename internally.

## Tried but abandoned
- **loguru with capsys**: loguru writes to stderr but `capsys.readouterr().err` was empty. Switched to stdlib `logging` for caplog compatibility.
- **watch_registry first-poll callback**: Initially triggered `on_change` on first poll (None -> version). Fixed to only trigger when last_version is not None.

## Open questions
- None. FR-2400 AC-1 through AC-4 are all covered by unit tests (18 tests).
