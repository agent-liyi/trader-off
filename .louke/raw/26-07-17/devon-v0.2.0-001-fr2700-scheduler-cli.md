---
date: 2026-07-17
session: devon-v0.2.0-001-fr2700-scheduler-cli
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#55]
status: resolved
---

## Topic
FR-2700: 调度器 CLI 与配置 (scheduler start/stop/status CLI + YAML config loading with cron validation)

## Decision

### Implementation approach
- Extended `src/trader_off/scheduler/cli.py` with new `build_scheduler_parser()` (argparse start/stop/status subcommands) alongside existing FR-2000 retrain commands.
- Added `load_scheduler_config()`, `_build_config_from_dict()`, and `_precedence()` helper for CLI > YAML > defaults precedence chain per architecture §8.1.
- Added `ConfigValidationError` to `src/trader_off/utils/exceptions.py`.
- Added `validate_cron_expr()` using croniter for cron expression validation.

### Files modified
- `src/trader_off/utils/exceptions.py` — added `ConfigValidationError`
- `src/trader_off/utils/__init__.py` — exported `ConfigValidationError`
- `src/trader_off/scheduler/__init__.py` — exported new CLI functions
- `src/trader_off/scheduler/cli.py` — added scheduler lifecycle CLI + config loading
- `tests/unit/scheduler/test_scheduler_cli.py` — 23 unit tests (new file)

### Test coverage
- 23 new tests covering FR-2700 AC-1 through AC-4
- All 250 scheduler unit tests pass
- No regressions

### Commits
- `50a45fe`: feat: green – #55 – scheduler CLI and config: start/stop/status subcommands, YAML config loading with cron validation, CLI>YAML>defaults precedence (Closes #55)
- `6f42180`: refactor: – #55 – extract _precedence helper for CLI>YAML>defaults resolution

## Tried but abandoned
- Considered putting `_precedence` as a lambda — too terse, extracted as a named function for clarity.
- Considered merging `run_scheduler_status` with `run_status` (retrain) — only 2 call sites, below the 3+ duplication threshold.

## Open questions
- None. All ACs verified.
