---
date: 2026-07-22
spec: v0.5.9-001-check-factor
status: done
locked: false
---

# v0.5.9 — check-factor — Acceptance Criteria

## FR-0100 — `trader-off check-factor`

### AC-FR0100-01 — successful evaluation emits JSON
- **WHEN** `trader-off check-factor --name momentum_5 --start 2024-01-01 --end 2024-12-31` is run
- **THEN** stdout emits: `{"status":"ok","data":{"factor":"momentum_5","ic":0.032,"icir":0.51,"rank_ic":0.028,"rank_icir":0.42,"valid":true}}`

### AC-FR0100-02 — invalid factor below threshold
- **WHEN** ICIR is below `--ic-threshold` (default 0.3)
- **THEN** `"valid":false` in the JSON

### AC-FR0100-03 — factor not found
- **WHEN** `--name NonExistentFactor` is passed
- **THEN** exit code 4 (config error) and stderr message

### AC-FR0100-04 — missing required arg
- **WHEN** `--name` is not provided
- **THEN** exit code 2 (argparse error)

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — AST validation
- **WHEN** AST parses the CLI file
- **THEN** all `factor_mining.*` and `trader_off.data.*` imports are function-scope
