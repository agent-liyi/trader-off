---
date: 2026-07-22
spec: v0.5.6-001-grid-search
status: done
locked: false
---

# v0.5.6 — grid-search — Acceptance Criteria

## FR-0100 — `trader-off grid-search`

### AC-FR0100-01 — config parsing
- **WHEN** `--config params.yaml` is provided
- **THEN** the YAML is parsed, `param_space` dict extracted
- **AND** the product of all param combinations is computed (e.g. 3×3×2 = 18 combinations)

### AC-FR0100-02 — successful execution emits JSON
- **WHEN** grid-search completes
- **THEN** stdout emits: `{"status":"ok","data":{"best":{"params":{...},"sharpe":1.43,"total_return":0.18},"completed":18,"errors":0}}`

### AC-FR0100-03 — max-workers control
- **WHEN** `--max-workers 4` is set
- **THEN** no more than 4 backtest processes run concurrently

### AC-FR0100-04 — config missing
- **WHEN** `--config` is not provided
- **THEN** exit code 2 (argparse error)

### AC-FR0100-05 — config file not found
- **WHEN** the config file path does not exist
- **THEN** exit code 4 (config error) and stderr message

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — AST validation
- **WHEN** AST parses the CLI file
- **THEN** `quantide.service.grid_search.GridSearch` import is function-scope only
