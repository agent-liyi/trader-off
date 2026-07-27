---
date: 2026-07-22
session: devon-v0.5.7-001-live-quote
agents: [Devon]
spec: v0.5.7-001-live-quote
related_issues: [#155]
status: resolved
supersedes: []
---

## Topic
FR-0100: `trader-off live` CLI — 封装 `quantide.service.livequote.LiveQuote` 实时行情订阅。

## Decision

### 实现决策
1. **模块结构**：`src/trader_off/cli/live.py`，遵循 9 个 CLI 模块的已有模式（`main(argv) -> int`）。
2. **参数设计**：`--start`/`--stop`/`--status` 为互斥动作标志；`--assets` 为逗号分隔股票代码；`--json` 兼容标志（始终 JSON 输出）。
3. **错误处理**：`_get_live_quote()` 函数封装了 lazy import + 异常捕获，失败时输出 `{"status":"error","code":4,"message":"qmt-gateway not available: ..."}` 并返回 None。
4. **退出码**：0 成功，2 argparse 错误，4 gateway 不可用（与 sync_data.py 一致）。

### 重构
- 提取了 `_write_json(data: dict)` 辅助函数，消除了 4 处 `sys.stdout.write(json.dumps(...))` 重复。

### 文件变更
| 文件 | 操作 |
|---|---|
| `src/trader_off/cli/live.py` | 新建（201 行，包含 main + 6 个 helpers） |
| `tests/unit/cli/test_live.py` | 新建（14 个测试，覆盖 7 个测试类） |
| `pyproject.toml` | 添加 `trader-off-live = "trader_off.cli.live:main"` |
| `tests/unit/test_console_scripts.py` | 更新 EXPECTED_SCRIPTS（7→8）、_SIGS、_CLI_IDS、count 断言、README 入口名称列表 |
| `README.md` | 功能列表添加"实时行情"项，用法部分添加 `### 实时行情` 节 |

### 提交
- Green: `a5a9af8` — `feat: green – #155 – add live quote CLI (FR-0100) with LiveQuote integration`
- Refactor: `0325024` — `refactor: – #155 – extract _write_json helper to eliminate JSON output duplication`

## Tried but abandoned
- 考虑过将 `lq = _get_live_quote(); if lq is None: return 4` （3 处出现）也提取为 helper，但认为这种 2 行 guard clause 的抽象会降低可读性，不符合"避免过早抽象"原则。

## Open questions
无。
