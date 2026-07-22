# STR-0007: v0.5.3 patch — `run_backtest()` 默认走 `.quantide/` 真数据

> spec: v0.5.3-001-backtest-on-real · status: confirmed-go · 2026-07-22

## 0. 原始输入
> Change `run_backtest()` default paths to prefer `.quantide/bars/` (real data from sync-data) over `tests/fixtures/v0.3.0/`, so `trader-off-sync-data + trader-off-backtest` forms one end-to-end pipeline on true A-share data.

## 1. 用户与场景
量化研究员/单一开发者，本地 CLI `trader-off-backtest`（无 UI）；有无 token 两种场景。

## 2. 功能与价值
- **FR-0100**：改 `src/trader_off/backtest/runner.py` 默认路径解析——`.quantide/bars/` 存在则优先连 `DailyBarsStore`（否则回落 `tests/fixtures/v0.3.0/daily_bars_store`）；`.quantide/calendar/calendar.parquet` 存在则优先加载（否则回落 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 内联生成）；启动 INFO 日志一次性输出选定路径 + `real-data | fixture` 来源标记。
- **快乐路径 / 目标**：`trader-off-sync-data` → `trader-off-backtest` 零参数端到端跑通；离线无 token 仍走 fixture；日志可观测。

### 2.1 EARS
| # | 句式 |
|---|---|
| AC-01 | `WHEN .quantide/bars/ 存在, THE 系统 SHALL 默认连接该 DailyBarsStore 并标记 "real-data store"` |
| AC-02 | `IF .quantide/bars/ 不存在, THE 系统 SHALL 回落到 tests/fixtures/v0.3.0/daily_bars_store 并标记 "fixture store"` |
| AC-03 | `WHEN .quantide/calendar/calendar.parquet 存在, THE 系统 SHALL 默认加载该日历` |
| AC-04 | `IF .quantide/calendar/calendar.parquet 不存在, THE 系统 SHALL 从 ohlcv_50x252.parquet 内联生成` |
| AC-05 | `WHILE run_backtest() 启动, THE 系统 SHALL INFO 日志输出 store_path / calendar_source 及来源标记` |

## 3. 竞品与边界
- **Adopt**：v0.5.1 `.quantide/bars/` + `.quantide/calendar/` 契约；v0.3.0 fixture 作回落。
- **Avoid**：改 `DailyBarsStore` schema / `calendar` 契约；新增 CLI 参数。
- **Out-of-Scope**：真数据训练；数据新鲜度/增量校验；增量回测。
- **约束**：Python ≥3.13；fixture 单测零回归。

## 4. 风险与假设
| # | 假设 | 验证 / 负责人 |
|---|---|---|
| 1 | `.quantide/bars/` schema 与 v0.3.0 `daily_bars.connect` 兼容 | 沿用 v0.5.1 验收 / M-DEV |
| # | 风险 | 影响 / 应对 |
| 1 | 真数据部分缺失致 silent fallback | 中；日志 + 非 0 退出码 |
| 2 | fixture 测试因默认切换失败 | 高；CI monkeypatch 显式 fixture 路径 |
| 3 | 真/假 calendar 字段不一致 | 低；启动时 schema 校验 |

## 5. 必要性与冲突
- **已实现？** 否；`runner.py:17-18` 仍 hard-code fixture。
- **相抵触？** 否；与 v0.5.1 路径契约对齐，仅改探测顺序。
- **结论**：新建 patch（证据：`runner.py:17-18,154-155`；`sync_data.py:117,254`）。

## 6. 方案疑议 / 分流结论
无异议 → Go → M-FOUND（Agent 建议；Human 已确认）· `STR-0007` · `2026-07-22T00:00:00Z`

*—— M-STORY Agent 于 2026-07-22 生成；Human 已确认 Go。*
