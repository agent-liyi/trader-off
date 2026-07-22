---
date: 2026-07-22
spec: v0.5.0-001-paper-trading-mvp
status: draft
---

# STR-0004: v0.5.0 — paper-trading MVP（用 PaperBroker 替换 BacktestBroker）

## 0. 原始输入
> v0.5.0（一句话）：实现 paper-trading MVP —— 在现有 `BacktestRunner` 集成路径之外新增 `run_paper_trade(...)` 入口，用 `quantide.service.sim_broker.PaperBroker`（本地撮合 + sqlite 持久化）替代 `BacktestBroker`（历史回放撮合）。同一套策略代码（`lgbm_top20` / `optimized_topk`）、同一套 `daily_bars` 数据层、同一个 scheduler —— 只把撮合层从"历史回放"换成"纸面成交"。

## 1. 用户与场景 (Who & Where)
- **Who**：量化研究员（继承 STR-0001/0002/0003，单一开发者；沿用 NFR-1000 向后兼容）。
- **Where**：本地 CLI（`trader-off paper-trade ...`）+ Python API（`from trader_off.backtest.runner import run_paper_trade`）；桌面/服务器，无 UI；`TUSHARE_TOKEN` 经 `os.environ` 注入（继承 v0.4.1 FR-0100）。
- **北极星**：一次 CLI 调用产出 paper NAV 曲线 + 持仓 + 成交记录 + sqlite 持久化账户状态，**不**修改任何策略代码。

## 2. 功能与价值 (What & Why)

### 2.1 功能描述 (What)
- **FR-0100 `run_paper_trade()` 入口**：在 `src/trader_off/backtest/runner.py` 内新增 `run_paper_trade(strategy_name, end_date, initial_cash, ...)` —— 函数级 lazy import `PaperBroker(portfolio_id, principal=initial_cash, commission=1e-4)`，复用 v0.3.0 的 `daily_bars.connect(...)` 与 `BaseStrategy_compat` 解析，**绕开** `BacktestRunner._init_backtest()` 内部硬编码的 `BacktestBroker` 实例化（runner.py L76-82），改用 session-style loop 驱动策略 on `PaperBroker`。返回/打印 NAV、positions、trade count。
- **FR-0200 `trader-off paper-trade` CLI**：新增 `trader-off paper-trade --strategy optimized_topk --end 2026-07-21 --capital 1000000`，封装 `run_paper_trade()` 并把结果序列化到 `reports/paper_trade_<ts>/{summary.json, nav_<ts>.parquet, positions_<ts>.parquet, trades_<ts>.parquet}`（schema 沿用 v0.3.0 AC-06 的 6 键 + 真实扩展字段）。
- **NFR-0100 函数级 lazy import — 白名单延伸**：v0.4.1 白名单仅 `quantide.data.fetchers.tushare.*`；本 spec **新增放行 `quantide.service.sim_broker.PaperBroker`**。其余 `quantide.service.*`（runner / metrics / portfolio）**仍不放行**——metrics 走 v0.3.0 已落地的 `compute_performance_metrics` 委托（详见 §4.2 冲突表）。

### 2.2 快乐路径 (Happy Path)
1. `export TUSHARE_TOKEN=xxx && trader-off paper-trade --strategy optimized_topk --end 2026-07-21 --capital 1000000`
2. `run_paper_trade()` 内 lazy import `PaperBroker` → `daily_bars.connect(...)` → 策略 on broker → session loop 至 `end_date`
3. `reports/paper_trade_<ts>/` 落 summary.json（`total_trades > 0`）+ 4 parquet；PaperBroker sqlite 持久化账户供下次接着跑

### 2.3 功能需求（EARS 格式）
| 编号 | EARS 句式 | 说明 |
| :--- | :-------- | :--- |
| AC-01 | `WHEN run_paper_trade 被调用, THE 系统 SHALL 函数级 lazy import quantide.service.sim_broker.PaperBroker 并以 principal=initial_cash 实例化` | broker 替换 |
| AC-02 | `WHEN run_paper_trade 被调用, THE 系统 SHALL 在调用策略之前完成 daily_bars.connect(store_path, calendar_store_path)（与 v0.3.0 AC-03 同契约）` | 数据层复用 |
| AC-03 | `WHEN run_paper_trade 被调用, THE 系统 SHALL 不调用 BacktestRunner（绕开 L76-82 BacktestBroker 硬编码），改用 session-style loop 驱动策略 on PaperBroker` | 路径分叉 |
| AC-04 | `WHEN run_paper_trade 完成, THE 系统 SHALL 在 reports/paper_trade_<ts>/ 下产出 summary.json（6 键继承 v0.3.0 AC-06 + 真实 total_trades/avg_turnover）+ nav/positions/trades_<ts>.parquet` | 输出 schema 兼容 |
| AC-05 | `WHEN trader-off paper-trade CLI 被执行, THE 系统 SHALL 解析参数并调用 run_paper_trade(...)，打印 summary.json 路径 + 关键指标` | CLI 入口 |
| AC-06 | `WHILE AC-01/02 生效, THE 系统 SHALL 保持 LGBMTop20Strategy / OptimizedTopKStrategy 代码零改动（NFR-1000 向后兼容继承 v0.1.0）` | 策略层不破 |
| AC-07 | `WHERE src/trader_off/backtest/runner.py 模块被 import, THE 系统 SHALL 满足 v0.4.1 NFR-0100 + 本 spec NFR-0100 延伸：仅允许 `quantide.data.fetchers.tushare.*` + `quantide.service.sim_broker.PaperBroker` 函数级 import，其余 quantide.* 业务符号不放行` | 白名单延伸 |
| AC-08 | `WHEN smoke test 启动 AND env TUSHARE_TOKEN 缺失, THE 系统 SHALL pytest.skip；存在 token 时跑 PaperBroker 真撮合 e2e 断言 NAV > 0 且 sqlite 持久化文件存在` | 测试门控 |

## 3. 完整性 (Completeness)

### 3.1 Adopt / Avoid
| 类型 | 来源 | 内容 | 理由 |
| :--- | :--- | :--- | :--- |
| Adopt | quantide `service/sim_broker.py`（已 curl 验证） | `PaperBroker(AbstractBroker)` 构造函数 `(portfolio_id, principal, commission, ...)` + 注释 "仿真交易 Broker...维护账户状态...sqlite 数据库" | FR-0100 真实 broker |
| Adopt | v0.3.0 `BacktestRunner.run` runner.py L76-82 | `BacktestBroker(bt_start, bt_end, portfolio_id, data_feed, principal, match_level, portfolio_name)` 字段顺序 | PaperBroker 参数对齐参考 |
| Adopt | v0.3.0 AC-03 + AC-06 | `daily_bars.connect(...)` 接线 + `reports/backtest_<ts>/` 输出目录 + 6 键 schema | FR-0200 输出兼容 |
| Avoid | 直接 `import quantide.service.runner.BacktestRunner` | PaperBroker 路径**不**经 BacktestRunner，避免 L76-82 硬编码 BacktestBroker 反向污染 | AC-03 强制 session loop |
| Avoid | v0.3.0 `np.random.RandomState(42)` 兜底 | 任何"假数据兜底"分支禁入 paper 路径 | 防静默退化 |
| Avoid | 引入 quantide.service.metrics 直接调用 | 通过 v0.3.0 已落地的 `compute_performance_metrics` 委托 | NFR-0100 白名单不放行 metrics |

### 3.2 Out-of-Scope（推迟到 v0.5.1+）
- [ ] 不接 live trading（QMT gateway / 独立服务）
- [ ] 不做自动化 daily scheduler 任务（cron 触发）—— 本 MVP 仅手动 CLI
- [ ] 不做 paper PnL Web UI / 可视化看板
- [ ] 不做 multi-portfolio 支持
- [ ] 不做 risk limits / 单笔仓位上限 / 行业敞口约束
- [ ] 不接 intraday 实时行情（paper 撮合仍用 v0.4.1 daily bars）

### 3.3 约束条件
- **技术**：Python ≥ 3.13；PaperBroker import 必须函数级 lazy（AC-07）；TUSHARE_TOKEN 仍为 paper 撮合数据源前置依赖；sqlite 路径落 `reports/paper_trade_<ts>/paper_state.sqlite` 或 PaperBroker 默认位置（M-FOUND 锁定）。
- **组织**：MVP ≤ 1-2 issue；v0.4.1 全部 AC 不退化。

## 4. 必要性与冲突 (Necessity & Conflict)

### 4.1 必要性
- **FR-0100 必要**：v0.3.0 spec 行 122 显式划入 Out-of-Scope "不接入 live / paper trading"；v0.5.0 兑现。
- **FR-0200 必要**：仅 Python API 不够；CLI 沿用 v0.3.0 AC-07 表面兼容。
- **NFR-0100 必要**：不延伸则 paper 路径需破隔离 `import quantide.service.*`，违反 v0.4.1 NFR-0100。

### 4.2 冲突
| 既有决策 | 冲突 | 说明 |
| -------- | :--: | ---- |
| **v0.4.1 NFR-0100 函数级 lazy + 白名单 `quantide.data.fetchers.tushare.*`** | ⚠️ **局部延伸** | 本 spec NFR-0100 显式放行 `quantide.service.sim_broker.PaperBroker`；其余 `quantide.service.*`（runner / metrics / portfolio）**不放行**。spec.md 需记"白名单从 1 个数据 fetcher 子树扩到 1 个数据 fetcher + 1 个 sim_broker 子树" |
| **v0.3.1 QuantideSchedulerAdapter（封装 quantide.core.scheduler.SchedulerManager）** | ❌ **不冲突** | scheduler 适配层仅 `from quantide.core.scheduler import SchedulerManager`；本 spec 不涉及 scheduler 路径，FR-0100/0200 均不动 `src/trader_off/scheduler/`；v0.3.1 NFR-0101 隔离放宽保持 |
| **v0.3.0 AC-04 `BacktestRunner.run(...)` 委托路径** | ❌ **不冲突，反而补充** | v0.5.0 新增**并列**的 paper 路径，**不**改 `run_backtest`；两条路径共用 `daily_bars` 单例 + `BaseStrategy_compat` + `compute_performance_metrics` |
| **v0.3.0 AC-11 / v0.4.1 AC-NFR0100-04 隔离承诺** | ⚠️ **局部延伸** | 同上：仅 `quantide.service.sim_broker.PaperBroker` 放行；`grep -rn "^import quantide\|^from quantide" src/trader_off/backtest/` 仍仅命中 `runner.py` 函数体 |
| **NFR-1000 v0.1.0 策略层向后兼容** | ❌ | AC-06 强制策略零改动；PaperBroker 实现 `AbstractBroker` 接口（同 BacktestBroker），`strategy.on_quote(broker)` 签名兼容 |

**结论**：**Go**；唯一 Human 决策点 = **NFR-0100 白名单延伸**（不认可则无替代，因 PaperBroker 是 quantide 唯一仿真 broker）。FR-0100/0200 与既有 spec 决策零破坏性冲突。

## 5. 方案疑议（A/B Advisory，非决策）
- **状态**：**有边界提示** —— 用户提方案 A = "新增 `run_paper_trade` + 新 CLI + 绕开 BacktestRunner"。Agent **倾向认同 A**，无更优 B。**边界**：若 Human 偏好"扩展 BacktestRunner 加 `broker_cls` 参数"（方案 B），需 monkey-patch / fork quantide —— **违反 v0.3.0 "不修改 quantide fork" 约束**，A 唯一可行。Agent 不替用户决策 paper vs live 优先级。

## 6. 分流结论与门禁 (Gate)
- **分流结论**：**Go**（Agent 建议）—— 4W 清晰（单用户 / CLI+Python / 撮合层替换 / 数据层复用）；范围紧凑（2 FR + 1 NFR）；PaperBroker 接口 §3.1 已 curl 验证；与 v0.3.0/0.3.1/0.4.1 决策全部兼容或局部显式延伸。
- **Human 确认**（仅决策点）：
  - [ ] 分流结论认同（**Go**）
  - [ ] **NFR-0100 白名单延伸至 `quantide.service.sim_broker.PaperBroker`** 认同
  - [ ] Out-of-Scope 认同（live / cron / Web UI / multi-portfolio / risk limits / intraday 推迟到 v0.5.1+）
- **Backlog**：**Go → 进入 M-FOUND**

## 7. 可追溯种子 (Traceability)
- **Story ID**：`STR-0004` · **创建时间**：`2026-07-22T00:00:00Z`
- **Spec ID**：`v0.5.0-001-paper-trading-mvp` · **关联 Issue（待填充）**：`#待创建`（建议拆 2：`FR-0100 run_paper_trade()` + `FR-0200 paper-trade CLI`）
- **继承基线**：v0.3.0 STR-0001（AC-03/04/06/07/11）+ v0.3.1 STR-0002（QuantideSchedulerAdapter 不破）+ v0.4.1 STR-0003（NFR-0100 白名单局部延伸）。

---
*—— 本故事由 M-STORY Agent 于 2026-07-22 生成；经 Human 确认后：Go → 进入 M-FOUND。*
