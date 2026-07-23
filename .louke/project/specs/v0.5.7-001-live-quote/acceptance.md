---
date: 2026-07-22
spec: v0.5.7-001-live-quote
status: done
locked: false
---

# v0.5.7 — live quote — Acceptance Criteria

## FR-0100 — `trader-off live`

### AC-FR0100-01 — status default
- **WHEN** `trader-off live` is run with no subcommand
- **THEN** behaves like `--status`: emits `{"status":"ok","data":{"running":<bool>}}`

### AC-FR0100-02 — start
- **WHEN** `trader-off live --start` is run
- **THEN** LiveQuote is instantiated and `start()` called
- **AND** stdout emits: `{"status":"ok","data":{"running":true}}`

### AC-FR0100-03 — stop
- **WHEN** `trader-off live --stop` is run
- **THEN** LiveQuote is stopped
- **AND** stdout emits: `{"status":"ok","data":{"running":false}}`

### AC-FR0100-04 — assets filter
- **WHEN** `trader-off live --start --assets 000001.SZ,600000.SH` is run
- **THEN** LiveQuote subscribes to the specified stock codes

### AC-FR0100-05 — no gateway
- **WHEN** qmt-gateway is not running
- **THEN** JSON error: `{"status":"error","code":4,"message":"qmt-gateway not available"}`

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — AST validation
- **WHEN** AST parses the CLI file
- **THEN** `quantide.service.livequote.LiveQuote` import is function-scope only
