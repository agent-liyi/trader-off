---
date: 2026-07-22
spec: v0.5.4-001-agent-cli
status: done
locked: false
---

# v0.5.4 — Agent-Callable CLI — Acceptance Criteria

## FR-0100 — `--json` flag on all 6 CLI modules

### AC-FR0100-01 — argparse `--json` flag registered
- **WHEN** any of the 6 CLI modules is invoked with `--help`
- **THEN** the help text shows `--json` as a registered flag

### AC-FR0100-02 — Successful execution emits JSON
- **WHEN** a CLI is run with `--json` and execution succeeds
- **THEN** stdout emits exactly one JSON object: `{"status":"ok","data":{...}}`
- **AND** no loguru INFO lines are written to stdout

### AC-FR0100-03 — Failed execution emits JSON error
- **WHEN** a CLI is run with `--json` and execution fails
- **THEN** stdout emits `{"status":"error","code":<N>,"message":"..."}`
- **AND** exit code is non-zero (e.g. 4 for config error, 5 for engine failure)

### AC-FR0100-04 — stderr preserved
- **WHEN** a CLI is run with `--json`
- **THEN** stderr still receives loguru progress messages (unaffected by `--json`)

## FR-0200 — `trader-off status` discovery

### AC-FR0200-01 — Global status subcommand
- **WHEN** `trader-off status` is run with `--json`
- **THEN** stdout emits JSON: `{"status":"ok","data":{"version":"...","data_source":"fixture|real|none","models":[...],"scheduler":"running|stopped","last_backtest":null|<date>}}`

### AC-FR0200-02 — `status data` subcommand
- **WHEN** `trader-off status data` is run
- **THEN** stdout emits JSON describing DailyBarsStore date range and asset count (or "none" if not initialized)

### AC-FR0200-03 — `status models` subcommand
- **WHEN** `trader-off status models` is run
- **THEN** stdout emits JSON listing trained model versions (parquet files in `factor_registry/`)

### AC-FR0200-04 — `status scheduler` subcommand
- **WHEN** `trader-off status scheduler` is run
- **THEN** stdout emits JSON: `{"status":"ok","data":{"running":<bool>,"last_trigger":null|<date>}}`

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — AST validation
- **WHEN** `ast.parse()` walks the 6 CLI files
- **THEN** all `quantide.*` imports are inside `FunctionDef` or `AsyncFunctionDef` bodies (no module-level imports)
