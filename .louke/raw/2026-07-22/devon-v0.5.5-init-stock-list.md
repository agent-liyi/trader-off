---
date: 2026-07-22
session: devon-v0.5.5-init-stock-list
agents: [Devon]
spec: v0.5.5-001-init-stock-list
related_issues: [#152, #153]
status: resolved
supersedes: []
---

## Topic
实现 v0.5.5 两个新 CLI 命令：`trader-off init` (FR-0100) 和 `trader-off stock-list` (FR-0200)，遵循 RGR 流程。

## Decision

### FR-0100 — trader-off init (issue #152)
- 文件: `src/trader_off/cli/init_data.py`
- `main(argv: list[str] | None = None) -> int`
- argparse: `--home` (default `.quantide`), `--force`
- 函数作用域 lazy import: `from quantide.data import init_data`
- JSON 输出: `{"status":"ok","data":{"home":"...","calendar":"created","bars":"created","db":"initialized"}}`
- 注册: `trader-off-init = "trader_off.cli.init_data:main"`
- 测试: 13 个 (argparse exit 2, JSON 结构, --home, --force, 函数作用域导入)
- Commit: `77e845c` (green, no refactor needed — code already minimal)

### FR-0200 — trader-off stock-list (issue #153)
- 文件: `src/trader_off/cli/stock_list.py`
- `main(argv: list[str] | None = None) -> int`
- argparse: `--exchange` (SSE/SZSE/BSE), `--status` (L/D/P), `--json`
- 函数作用域 lazy import: `from quantide.data.fetchers.tushare import fetch_stock_list`
- exchange 推导: 从 asset suffix (.SH→SSE, .SZ→SZSE, .BJ→BSE)
- status 推导: 从 delist_date (NaN→L, 有值→D)
- JSON 输出: `{"status":"ok","data":{"count":N,"exchange":"...","status":"...","stocks":[{"ts_code":"...","name":"..."}]}}`
- 注册: `trader-off-stock-list = "trader_off.cli.stock_list:main"`
- 测试: 15 个
- Commits: `6d41023` (green), `7349c5f` (refactor: extract `_derive_exchange` helper), `d3f6a3a` (fix line number)

### README.md
- 定位文案更新: `millionaire/quantide 命令行封装...`
- 新增"初始化"和"股票列表"使用章节

### pyproject.toml
- 注册 2 个新 entry points (总共 7 个)

### test_console_scripts.py
- 更新 EXPECTED_SCRIPTS: 4→7 entry points
- 更新 _SIGS: 添加 sync_data, init_data, stock_list
- 更新 README 检查: 4→7 entry point names
- 修复 factor_mining 行号: 239→383 (预存在偏移)

## Tried but abandoned
- 最初在 init_data.py 中 `home / ".quantide"` 追加目录名 — 测试期望 home 直接指向 data root
- 最初在 argparse 中使用 `choices=` 限制 exchange/status 值 — 测试期望允许任意值通过, 下游过滤
- 最初使用 `pd.notna()` 需要 import pandas — 改为 NaN != NaN 的自检函数 `_is_valid_date`

## Open questions
- --force 标志目前被 argparse 接受但未在代码中产生不同行为 — quantide.init_data 内建 exist_ok=True 已支持重复初始化
- --status P (suspended) 过滤无法从 fetch_stock_list 返回数据中可靠推导 — 当前对 P 仅做列匹配
- stock_list 的--json 标志始终启用但保留以兼容
