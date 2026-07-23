---
date: 2026-07-22
spec: v0.5.5-001-init-stock-list
status: done
locked: false
---

# v0.5.5 — init + stock-list + positioning

## Goal
Wrap `quantide.data.init_data` and `quantide.data.fetchers.tushare.fetch_stock_list`. Update trader-off positioning to "millionaire/quantide CLI wrapper".

## Scope

### FR-0100 — `trader-off init`
Wrap `quantide.data.init_data(home)`. Args:
- `--home PATH` — data root (default `.quantide/`)

### FR-0200 — `trader-off stock-list`
Wrap `quantide.data.fetchers.tushare.fetch_stock_list`. Args:
- `--exchange SSE|SZSE|BSE` — filter by exchange
- `--status L|D|P` — filter by status (listed/delisted/suspended)
- `--json` — JSON output (per v0.5.4)

### NFR-0100 — function-scope lazy imports (inherited)
Allowlist: `quantide.data.fetchers.tushare.*` + `quantide.data.*`

### Positioning update (README)
- L1: `A 股量化研究 + 回测平台，基于 millionaire/quantide` → `millionaire/quantide 命令行封装。涵盖回测、纸交易、网格寻优、数据同步、实时行情。`

## Removed in v0.5.5
- `--force` flag in `trader-off init` (was not functional; removed in commit 6919924)
