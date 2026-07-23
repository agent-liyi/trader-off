---
date: 2026-07-22
spec: v0.5.6-001-grid-search
status: done
locked: false
---

# v0.5.6 — grid-search CLI

## Goal
Wrap `quantide.service.grid_search.GridSearch` for strategy parameter optimization.

## Scope

### FR-0100 — `trader-off grid-search`
- Args:
  - `--config PATH` (required) — YAML with `param_space` dict
  - `--strategy NAME` (required)
  - `--start DATE` (required)
  - `--end DATE` (required)
  - `--capital FLOAT` (default 1_000_000)
  - `--max-workers INT` (default 4)
  - `--json` — JSON output

- Behavior:
  - Function-scope lazy import: `from quantide.service.grid_search import GridSearch`
  - Parse `param_space` from YAML, expand via `itertools.product`
  - Run `GridSearch.run()` (multi-process, `ProcessPoolExecutor`)
  - Return best parameters by Sharpe

### NFR-0100 — function-scope lazy imports (inherited)

## Config YAML format

```yaml
param_space:
  top_k: [10, 20, 30]
  rebalance_days: [5, 10, 20]
  ic_threshold: [0.05, 0.1]
```
