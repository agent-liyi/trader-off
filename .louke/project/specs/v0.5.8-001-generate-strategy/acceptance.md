---
date: 2026-07-22
spec: v0.5.8-001-generate-strategy
status: done
locked: false
---

# v0.5.8 — generate-strategy — Acceptance Criteria

## FR-0100 — `trader-off generate-strategy`

### AC-FR0100-01 — file creation
- **WHEN** `trader-off generate-strategy --name MyStrategy` is run
- **THEN** `src/trader_off/strategies/my_strategy.py` is created with all 5 lifecycle method stubs

### AC-FR0100-02 — dry-run output
- **WHEN** `--dry-run` is passed
- **THEN** no file is created; the generated code is printed to stdout
- **AND** exit code 0

### AC-FR0100-03 — JSON output
- **WHEN** `--json` is passed
- **THEN** stdout emits: `{"status":"ok","data":{"file":"...","class":"MyStrategy","methods":5}}`

### AC-FR0100-04 — class name conversion
- **WHEN** `--name MomentumReversion` is passed
- **THEN** file is named `momentum_reversion.py` (snake_case) and class is `MomentumReversion` (PascalCase)

### AC-FR0100-05 — file exists
- **WHEN** the target file already exists
- **THEN** exit with error (4) and stderr message

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — AST validation
- **WHEN** AST parses the CLI file
- **THEN** no top-level quantide imports
