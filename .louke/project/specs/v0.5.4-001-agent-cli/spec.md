---
date: 2026-07-22
spec: v0.5.4-001-agent-cli
status: done
locked: false
---

# v0.5.4 — agent-callable CLI

## Goal
Make all CLI tools agent-callable (LLM/LLM-agent parseable).

## Scope

### FR-0100 — `--json` flag on all 6 CLI modules
Add `--json` argparse flag to all 6 existing CLI modules. When set:
- stdout emits `{"status":"ok","data":{...}}` or `{"status":"error","code":4,"message":"..."}`
- stderr continues to loguru (for humans)
- File outputs unchanged

Modules:
- `cli/backtest.py`
- `cli/paper_trade.py` (created in this version)
- `portfolio/cli.py` (optimize)
- `factor_mining/cli.py`
- `scheduler/cli.py`
- `cli/sync_data.py`

### FR-0200 — `trader-off status` discovery command
Create `cli/status.py` with subcommands: `status`, `status data`, `status models`, `status scheduler`. Always JSON output.

### NFR-0100 — function-scope lazy imports (inherited)

## Implementation

Shared helper `src/trader_off/cli/_json_output.py` provides a `_write_json(...)` helper used by all 6 modules.

Entry-point table (existing + added):
- `trader-off-backtest`
- `trader-off-paper-trade` (NEW in v0.5.4)
- `trader-off-optimize`
- `trader-off-mine-factors`
- `trader-off-scheduler`
- `trader-off-sync-data`
- `trader-off-status` (NEW)
