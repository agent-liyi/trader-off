---
date: 2026-07-22
spec: v0.5.1-001-sync-data-cli
status: draft
---

# STR-0005: v0.5.1 patch — `trader-off sync-data` CLI wrapper around `QuantideDataLoader`

## 0. 原始输入
> v0.5.1 patch（一句话）：新增 `trader-off sync-data` CLI 命令，封装 v0.4.1 落地的 `QuantideDataLoader`，从 `quantide.data.fetchers.tushare.fetch_bars(dates)` + `fetch_calendar(epoch)` 拉 A 股 OHLCV，写入 `DailyBarsStore`（按年分区 parquet）+ `.quantide/calendar/`，供 v0.5.0 `PaperBroker` 在缺数据时一键补齐。

## 1. 用户与场景 (Who & Where)
- **Who**：量化研究员（继承 STR-0003/0004，单一开发者）。
- **Where**：本地 CLI（`trader-off sync-data --universe ... --start ... --end ...`）；无 UI；`TUSHARE_TOKEN` 仍经 `os.environ` 注入（v0.4.1 FR-0100）。

## 2. 功能与价值 (What & Why)
- **FR-0100 `sync_data` CLI**：新建 `src/trader_off/cli/sync_data.py` 导出 `main(argv)`；args = `--universe PATH`（CSV/parquet 含 `asset` 列）· `--start DATE` · `--end DATE` · `--store-path PATH`（默认 `.quantide/bars/`）· `--dry-run`；遍历 universe 每 asset → 函数级 lazy import `QuantideDataLoader` → `loader.get_daily(asset, start, end)` → 写 `DailyBarsStore`（年分区 parquet） + 写 `.quantide/calendar/`；`pyproject.toml [project.scripts]` 注册 `trader-off-sync-data`。
- **NFR-0100 白名单延伸**：v0.5.0 已有白名单 `quantide.data.fetchers.tushare.*` + `service.sim_broker.PaperBroker`；本 spec 新模块 `cli/sync_data.py` 复用 `data.fetchers.tushare.*`，**零冲突**；其余 `quantide.*` 不放行。

**快乐路径**：
1. `export TUSHARE_TOKEN=xxx && trader-off sync-data --universe universe/a_share_top50.csv --start 2024-01-01 --end 2024-12-31`
2. CLI 读 universe → lazy import `QuantideDataLoader(token=os.environ['TUSHARE_TOKEN'])` → 顺序遍历每 asset 调 `get_daily()`
3. OHLCV 落 `.quantide/bars/asset=YEAR.parquet`，日历落 `.quantide/calendar/`；`--dry-run` 仅打印计划不落盘

**问题与目标**：v0.4.1 `QuantideDataLoader` 仅 Python API；v0.5.0 `PaperBroker` 跑 paper-trade 前需先有数据，CLI 缺失阻碍 daily 复用。北极星 = 一次 `trader-off sync-data` 产出 `DailyBarsStore` 全量 bar + 日历，paper-trade 直接 `daily_bars.connect(...)` 即可。

### 2.1 功能需求（EARS 格式）
| 编号 | EARS 句式 |
| :--- | :-------- |
| AC-01 | `WHEN sync-data 被执行 AND TUSHARE_TOKEN 未设置, THE 系统 SHALL 抛非零退出码 + 明确错误信息且不发网络 IO` |
| AC-02 | `WHEN sync-data 被执行 AND args 完整, THE 系统 SHALL 解析 args 并顺序遍历 universe 每个 asset 调 get_daily()` |
| AC-03 | `WHEN get_daily() 返回 polars OHLCV, THE 系统 SHALL 写 DailyBarsStore 按年分区 parquet + 写 .quantide/calendar/` |
| AC-04 | `WHEN --dry-run 启用, THE 系统 SHALL 仅打印 [asset, start, end, target_path] 计划且不写盘不调网络` |
| AC-05 | `WHERE 单 asset 同步失败, THE 系统 SHALL 记录到 stderr 并继续下一个 asset，最后以非零退出码退出` |
| AC-06 | `WHERE cli/sync_data.py 模块被 import, THE 系统 SHALL 仅函数级 lazy import `quantide.data.fetchers.tushare.*` + v0.5.0 已放行符号；其余 quantide.* 不放行` |
| AC-07 | `WHEN pyproject.toml 被加载, THE 系统 SHALL 暴露 `trader-off-sync-data` 入口指向 trader_off.cli.sync_data:main` |

## 3. 完整性 (Completeness)

### 3.1 Adopt / Avoid
| 类型 | 来源 | 内容 |
| :--- | :--- | :--- |
| Adopt | v0.4.1 `QuantideDataLoader.get_daily()` | 真 Tushare 通路 + 日历反推（FR-0100 主调用） |
| Adopt | v0.3.0 `DailyBarsStore` 年分区契约 | 路径/分区 schema 沿用 |
| Adopt | v0.5.0 paper-trade CLI 注册模式 | `[project.scripts]` entry_point |
| Avoid | resume / partial sync / 并行下载 / scheduler | v0.5.1 推迟（Out-of-Scope） |
| Avoid | `import quantide.data.*` 模块顶层 | 函数级 lazy 强制（NFR-0100 / AC-06） |

### 3.2 Out-of-Scope & 约束
- **Out-of-Scope**：resume / 增量同步（永远全量）· 并行下载（顺序 per asset）· cron / scheduler 自动触发（仅手动 CLI）· universe 自动发现（需显式 `--universe`）· calendar 可视化 / 数据质量校验报告 · 改 `QuantideDataLoader` 签名 / 接口（v0.4.1 锁定）。
- **技术**：Python ≥ 3.13；`QuantideDataLoader` import 必须函数级 lazy（AC-06）；TUSHARE_TOKEN 仍前置依赖（继承 v0.4.1）。
- **安全**：Token 永不落盘 —— CLI 输出禁 echo token；`.env*` gitignore（继承 v0.4.1）。
- **组织**：patch ≤ 1 issue；`--store-path` 默认 `.quantide/bars/` 与 v0.3.0 `daily_bars.connect` 默认对齐。

## 4. 必要性与冲突 (Necessity & Conflict)
- **FR-0100 必要**：v0.4.1 / v0.5.0 均显式 Out-of-Scope "不做 sync CLI / 不接 scheduler"；v0.5.1 兑现。
- **NFR-0100 必要**：新 `cli/` 模块必须延续隔离承诺；放行范围仅 `data.fetchers.tushare.*`。
- **冲突**：v0.5.0 NFR-0100 白名单 ⚠️ 局部延伸（CLI 复用 `data.fetchers.tushare.*`，零冲突；spec.md 记录"白名单扩到 `cli/sync_data.py`"）；v0.4.1 FR-0100 / v0.3.0 AC-03 / v0.5.0 `run_paper_trade` 全部 ❌ 不冲突（封装 / 落盘路径对齐 / 反而为 paper-trade 数据前置）。
- **结论**：**Go**；唯一 Human 决策点 = **NFR-0100 白名单延伸至 `cli/sync_data.py`**（不认可则 CLI 路径需破隔离 import）。FR-0100 与既有 spec 决策零破坏性冲突。

## 5. 方案疑议（A/B Advisory，非决策）
- **状态**：**无 A/B 疑议**。v0.5.1 是 v0.4.1 + v0.5.0 留尾 CLI 兑现，路径单一（wrap `QuantideDataLoader`，不动签名）。v0.5.0 §3.2 已显式 Out-of-Scope "sync CLI / scheduler" —— 本 spec 是其反转兑现，**不**涉及 live / Web UI 决策。

## 6. 分流结论与门禁 (Gate)
- **分流结论**：**Go**（Agent 建议）—— 1 FR（CLI 封装）+ 1 NFR（白名单延伸）路径明确；`get_daily()` 已在 v0.4.1 验证；`DailyBarsStore` 沿用 v0.3.0 契约；paper-trade 路径零下游改动。
- **Human 确认**（仅决策点）：[ ] 分流结论认同（Go）· [ ] NFR-0100 白名单延伸至 `cli/sync_data.py` 认同 · [ ] Out-of-Scope 认同（resume / 并行 / scheduler / universe 自动发现 / 数据质量校验推迟到 v0.5.2+）。
- **Backlog**：**Go → 进入 M-FOUND**

## 7. 可追溯种子 (Traceability)
- **Story ID**：`STR-0005` · **创建时间**：`2026-07-22T00:00:00Z`
- **Spec ID**：`v0.5.1-001-sync-data-cli` · **关联 Issue**：`#待创建`
- **继承基线**：v0.4.1 STR-0003（FR-0100 真 Tushare + NFR-0100 函数级 lazy 白名单）+ v0.5.0 STR-0004（NFR-0100 白名单延伸至 `PaperBroker` + paper-trade CLI 注册）+ v0.3.0 STR-0001（`daily_bars` 落盘契约）。

---
*—— 本故事由 M-STORY Agent 于 2026-07-22 生成；经 Human 确认后：Go → 进入 M-FOUND。*
