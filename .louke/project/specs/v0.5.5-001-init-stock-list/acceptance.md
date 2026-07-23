---
date: 2026-07-22
spec: v0.5.5-001-init-stock-list
status: done
locked: false
---

# v0.5.5 — init + stock-list — Acceptance Criteria

## FR-0100 — `trader-off init`

### AC-FR0100-01 — default home path
- **WHEN** `trader-off init` is run (no args)
- **THEN** data directory initialized at `.quantide/` (call `quantide.data.init_data(home=Path(".quantide"))`)

### AC-FR0100-02 — custom home path
- **WHEN** `trader-off init --home /mnt/data` is run
- **THEN** data directory initialized at `/mnt/data` instead

### AC-FR0100-03 — JSON output
- **WHEN** init succeeds with `--json`
- **THEN** stdout emits: `{"status":"ok","data":{"home":"...","calendar":"created","bars":"created","db":"initialized"}}`

## FR-0200 — `trader-off stock-list`

### AC-FR0200-01 — default fetch all
- **WHEN** `trader-off stock-list` is run (no filters)
- **THEN** fetches all A-share stocks via `fetch_stock_list()`

### AC-FR0200-02 — exchange filter
- **WHEN** `trader-off stock-list --exchange SSE` is run
- **THEN** only SSE (Shanghai) stocks returned

### AC-FR0200-03 — status filter
- **WHEN** `trader-off stock-list --status L` is run
- **THEN** only listed (not delisted/suspended) stocks returned

### AC-FR0200-04 — combined filter
- **WHEN** `trader-off stock-list --exchange SSE --status L --json` is run
- **THEN** stdout emits JSON: `{"status":"ok","data":{"count":N,"exchange":"SSE","stocks":[{"ts_code":"...","name":"..."}]}}`

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — AST validation
- **WHEN** AST parses the CLI files
- **THEN** all `quantide.data.*` imports are function-scope (no top-level imports)
