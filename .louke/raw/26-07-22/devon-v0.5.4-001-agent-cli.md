---
date: 2026-07-22
session: devon-v0.5.4-001-agent-cli
agents: [Devon]
spec: v0.5.4-001-agent-cli
related_issues: [#150, #151]
status: resolved
supersedes: []
---

## Topic: FR-0100 — add --json flag to 6 CLI modules

### Decision
- Created shared helper `src/trader_off/cli/_json_output.py` with `_json_wrap()` function that suppresses stdout and emits JSON blob on exit
- Pattern: each CLI main() checks `args.json` → wraps `_run()` call in `_json_wrap(lambda: _run(args), error_messages=...)`
- 6 modules modified: backtest.py, paper_trade.py (new), sync_data.py, portfolio/cli.py, factor_mining/cli.py, scheduler/cli.py
- JSON format on success: `{"status":"ok","data":{}}`
- JSON format on error: `{"status":"error","code":N,"message":"..."}`
- stderr (loguru) preserved in all cases
- backtest.py refactored: extracted `_build_parser()` and `_run()` from monolithic `main()`
- sync_data.py refactored: extracted `_run_sync()` from `main()`

### Tried but abandoned
- Initially considered a context manager approach for JSON output, but settled on `_json_wrap()` function since context managers can't capture return values cleanly
- Considered putting `_ERROR_MESSAGES` as module-level constants in each CLI, but ruff N806 required lowercase for function-scope variables (factor_mining/cli.py had to move it inside main())

### Open questions
- None

## Topic: FR-0200 — trader-off status command

### Decision
- Created `src/trader_off/cli/status.py` with subcommands: (none), data, models, scheduler
- No argparse (always JSON output by design)
- Subcommand routing via simple if/elif chain in main()
- status data: checks `.quantide/bars/`, scans first parquet for date range + asset count
- status models: lists factor_registry/*.parquet filenames
- status scheduler: checks `scheduler_state/.pid` file with `os.kill(pid, 0)`
- Registered as `trader-off-status` entry point in pyproject.toml
- `_check_models()` returns `[]` for global status; `_status_models()` returns actual file list for dedicated subcommand

### Tried but abandoned
- First implementation had `_check_models` returning inconsistent types (int/list); fixed during refactor to return `[]` for global status
- Had `_count_registry_files()` helper removed during refactor — unnecessary indirection

### Open questions
- `last_backtest` field from the story.md spec is not implemented; deferred (no clear source of truth for last backtest date)
