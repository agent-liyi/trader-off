---
date: 2026-07-21
spec: v0.3.0-001-real-backtest
status: draft
---

# STR-0001: 用 quantide 真实回测引擎替换 trader-off 的假数据回测

---

## 0. 原始输入

> v0.3.0 核心目标（一句话）：用真实的 quantide（millionaire）BacktestRunner 替换 trader-off 的假数据回测引擎，并把 trader-off 手写的 metrics 模块切换到 quantide 的真实指标 —— 让所有回测输出从此可信。

**范围（已与用户确认，保持紧凑）**：

**FR-1（BacktestRunner 接入）**：
- 在 `pyproject.toml` 加入 quantide 依赖（`git+https://github.com/agent-liyi/millionaire.git`）
- 把 Python 要求从 `>=3.11` 升级到 `>=3.13`（quantide 硬性要求）
- 写 `scripts/convert_fixture_to_quantide.py`：把 trader-off 现有的 OHLCV parquet fixtures（`tests/fixtures/v0.2.0/ohlcv_50x252.parquet`、`tests/e2e/fixtures/ohlcv_10x60.parquet`）转成 quantide 的 `DailyBarsStore` parquet 格式（按年分区，列：`date, asset, ohlc, volume, adj_factor`）
- 从 `trade_date` 列生成 calendar parquet（独立 store）
- 重写 `src/trader_off/backtest/runner.py`：删除 `np.random.RandomState(42)` 的合成 NAV 分支（原 ~72-100 行），委托给 `quantide.service.runner.BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, start_date, end_date, initial_cash)`
- CLI 表面保持不变：相同 CLI 参数、相同输出路径、相同 JSON schema（用真实字段扩展）
- 在 run 之前通过 `daily_bars.connect(store_path, calendar_store_path)` 接入 `daily_bars` 单例

**FR-2（metrics 委托）**：
- 把 `src/trader_off/backtest/metrics.py` 内部实现替换为委托给 `quantide.service.metrics`（返回 Sortino、回撤持续时长、benchmark 对比、真实换手率、来自 `BacktestBroker.bills()` 的真实成交笔数）
- 移除 `metrics.py` 第 ~66-68 行 `total_trades/avg_turnover` 硬编码 0
- 保持公开函数签名 `compute_metrics(nav, ...) -> dict` 不变，下游（`evaluation/`、`visualization/`、e2e tests）零改动

**v0.3.0 不做（推迟到 v0.4.0+）**：
- tushare fetcher 接入
- grid_search 参数寻优
- walk-forward sample-out 验证
- live / paper trading

**用户约束**：
- 工作量保持小（MVP 范围，约 1-2 个 issue 的工作量）
- 保持分层：quantide = 通过依赖供应的执行引擎（不动 fork）
- trader-off = α 研究平台（不动）

---

## 1. 用户与场景 (Who & Where)

### 1.1 用户画像 (Who)
- **主要角色**：量化研究员（trader-off 唯一使用者，承接 v0.1.0/v0.2.0 用户画像）
- **次要角色**：暂无（v0.3.0 不引入新角色）
- **用户规模**：单一开发者（trader-off 是单人 alpha 研究项目，非协作项目）
- **使用频次**：中频（每周一次完整 pipeline，含一次 `trader-off backtest` 调用）
- **网络环境**：稳定办公网（CI 上跑 e2e；本地 macOS 开发）

### 1.2 使用终端 (Where)
- **终端类型**：CLI（`trader-off backtest ...`）+ Python API（`from trader_off.backtest.runner import run_backtest`）
- **适配要求**：仅桌面/服务器终端；无 Web UI / 移动端；调用入口签名继承 v0.1.0 AC-FR1100-01

---

## 2. 功能与价值 (What & Why)

### 2.1 功能描述 (What)

用真实的 quantide `BacktestRunner` 替换 trader-off 当前 `runner.py` 里的假数据分支（`np.random.RandomState(42)` 合成 NAV + 单资产假持仓 + 单笔假成交），并把 `metrics.py` 里硬编码 `total_trades=0 / avg_turnover=0.0` 的占位实现改为委托给 `quantide.service.metrics`。fixture 数据通过一次性转换脚本从原 OHLCV parquet 转为 quantide 要求的 `DailyBarsStore` 格式（年分区 + calendar store）。CLI 与 Python 公开 API 表面零改动；输出目录结构与 `summary.json` schema 兼容并扩展。

**快乐路径（Happy Path）**：
1. `uv sync` 装上 quantide（自动拉到 `>=3.13` Python）
2. 运行 `python scripts/convert_fixture_to_quantide.py` —— 把 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 转成 `tests/fixtures/v0.3.0/daily_bars_store/` + `calendar_store/`
3. 执行 `trader-off backtest --model v1 --strategy lgbm_top20 --start 2023-01-01 --end 2023-12-31 --capital 1000000`
4. `run_backtest` 在 `daily_bars.connect(...)` 之后委托给 `quantide.service.runner.BacktestRunner.run(...)`，传入 `BaseStrategy_compat` 解析出的策略类与现有 strategy config
5. 回测完成后，`reports/backtest_<ts>/` 下产出 `summary.json`（含真实 `total_trades` / `avg_turnover` / `sortino` / `drawdown_duration_days` 等）+ 4 个真实 parquet
6. v0.1.0/v0.2.0 的 e2e 测试（`tests/e2e/test_full_pipeline_e2e.py::test_full_pipeline_*`）继续通过，下游 `evaluation/`、`visualization/`、`tests/integration/test_backtest_cli.py` 零改动

### 2.2 问题陈述与目标 (Why)

- **问题陈述**：v0.1.0 立项时 quantide 未安装，`backtest/runner.py` 写了 `np.random.RandomState(42)` 合成 NAV 兜底分支；v0.2.0 沿用了该实现。`metrics.py` 的 `total_trades` 和 `avg_turnover` 也硬编码为 0 —— **当前所有回测输出（NAV、positions、trades、metrics）都不是真实回测结果**，而是固定种子合成数据。这让 e2e 测试只能验证"输出文件存在"而非"回测逻辑正确"，v0.2.0 的优化器与策略闭环也只是表演。
- **北极星目标**：执行一次真实的回测 —— `summary.json` 里 `total_trades > 0`、`avg_turnover > 0`、NAV 反映 LGBMTop20 策略在 50 资产 × 252 日 OHLCV 上的真实资金曲线，`BacktestBroker.bills()` 的成交笔数与 `trades_<ts>.parquet` 行数一致。
- **可观测指标**：
  - `summary.json["total_trades"]` 在 50 资产 × 252 日 fixture 上 > 0（当前为 0）
  - `summary.json["avg_turnover"]` 在 50 资产 × 252 日 fixture 上 > 0（当前为 0.0）
  - 删除 `runner.py` 里的 `np.random.RandomState(42)` 后，`tests/unit/backtest/test_runner.py::TestRunBacktest::test_output_files` 仍能产出真实 NAV 而非合成
  - `pytest tests/unit tests/integration tests/e2e` 全绿（v0.2.0 全部 159 AC 不退化）

### 2.3 功能需求（EARS 格式）

| 编号  | EARS 句式 | 说明 |
| :---- | :-------- | :--- |
| AC-01 | `WHEN 用户执行 uv sync AND Python >= 3.13, THE 系统 SHALL 安装 quantide 并可在 importlib 中解析出 quantide.service.runner.BacktestRunner` | 依赖与运行时 |
| AC-02 | `WHEN 用户执行 python scripts/convert_fixture_to_quantide.py, THE 系统 SHALL 在 tests/fixtures/v0.3.0/ 下产出 daily_bars_store/ (按年分区的 parquet) 与 calendar_store/ (交易日历 parquet)` | fixture 转换 |
| AC-03 | `WHEN run_backtest 被调用, THE 系统 SHALL 在调用 BacktestRunner.run 之前完成 daily_bars.connect(store_path, calendar_store_path) 至少一次` | store 接线 |
| AC-04 | `WHEN run_backtest 被调用, THE 系统 SHALL 调用 quantide.service.runner.BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, start_date, end_date, initial_cash) 而非生成合成 NAV` | 真实回测委托 |
| AC-05 | `WHEN run_backtest 被调用, THE 系统 SHALL 不再包含 np.random.RandomState(42) 的合成 NAV / positions / trades 分支（src/trader_off/backtest/runner.py 中）` | 删除假数据 |
| AC-06 | `WHEN run_backtest 完成, THE 系统 SHALL 在 reports/backtest_<ts>/ 下产出 summary.json 与 {nav, positions, trades}_<ts>.parquet，summary.json 含全部 6 个 v0.1.0 必需键 + 新增 sortino/drawdown_duration_days/benchmark_return 等真实现有字段（缺失即视为 None）` | 输出 schema 兼容 + 扩展 |
| AC-07 | `WHEN run_backtest 被调用, THE 系统 SHALL 不修改 trader_off.cli.backtest 的 CLI 参数签名（AC-FR1100-01/02/03 仍通过）` | CLI 兼容 |
| AC-08 | `WHEN compute_performance_metrics 被调用, THE 系统 SHALL 委托给 quantide.service.metrics 计算并返回 dict（保持 6 个 v0.1.0 键 + 真实 total_trades 与 avg_turnover）` | metrics 委托 |
| AC-09 | `WHEN compute_performance_metrics 被调用, THE 系统 SHALL 不再硬编码 total_trades=0 或 avg_turnover=0.0（metrics.py 第 ~66-68 行删除）` | 移除硬编码 0 |
| AC-10 | `WHILE AC-04 委托路径生效, THE 系统 SHALL 仍通过 trader_off.strategies.compat.BaseStrategy 解析策略基类（trader-off 不直接 import quantide.service.runner 的内部）` | 分层保持 |
| AC-11 | `WHERE scheduler 模块被 import, THE 系统 SHALL 仍满足 v0.2.0 AC-FR1500-04：src/trader_off/scheduler/ 路径下不出现 quantide.* 业务依赖（仅 pyproject.toml 声明）` | 调度器隔离不破 |
| AC-12 | `IF 日历 store 缺失或 daily_bars.connect 抛异常, THE 系统 SHALL 抛带明确 message 的异常并退出码非 0（避免静默退化为假数据）` | 失败可见 |

---

## 3. 竞品与边界 (Scope & Competition)

### 3.1 Adopt / Avoid 清单（补全素材，非市场裁决）

| 类型  | 来源    | 内容 | 理由 |
| :---- | :------ | :--- | :--- |
| Adopt | 通用回测引擎模式（zipline/vectorbt/backtrader） | store / calendar 接线顺序：先 connect 再 run，否则引擎读不到 bar 数据 | 我们故事里 §2.3 AC-03 已显式覆盖，但要在 convert 脚本里同时产 calendar store，否则 connect 会因缺少 calendar 而失败 |
| Adopt | quantide 自身 repo 文档 | `BacktestRunner.run()` 的真实签名（strategy_cls, config, start_date, end_date, initial_cash）与 `BacktestBroker.bills()` 的接口 | 我们 story 显式引用，但需要在 M-FOUND 阶段以 `quantide.service.runner.BacktestRunner.run.__doc__` 为准做最终签名锁定（v0.3.0 草稿阶段允许 `[待 quantide 文档确认]`） |
| Adopt | v0.1.0 AC-FR1100-01/02/03 | `trader-off backtest` 的 CLI 签名 + 输出目录 + summary.json schema | 我们 story 通过 AC-06/AC-07 显式继承，避免 v0.2.0 e2e 退化 |
| Avoid | v0.1.0 `runner.py` 第 72-100 行的 `np.random.RandomState(42)` 兜底分支 | 当 quantide 未安装时回退合成 NAV —— v0.3.0 后这是「不允许」的失败模式 | 通过 AC-05/AC-12 禁止兜底：失败即抛异常而非悄悄退回合成数据 |
| Avoid | v0.1.0 `metrics.py` 第 66-68 行硬编码 0 | 当输入只是 NAV 序列时无法获取成交/换手，把字段写死 0 | AC-08/AC-09 显式删除硬编码；改为委托 quantide（quantide 拿 `BacktestBroker.bills()`，输出真实值） |
| Avoid | quantide fork 内的 monkey-patch / 业务定制 | 用户约束明确禁止改 fork | story 不产出对 `millionaire` 仓的任何 patch；如发现接口缺失，写 `[需 quantide 上游补齐]` 并升级依赖版本，不在 fork 上改 |

> 注：v0.3.0 没有"竞品"概念 —— quantide 就是我们唯一接入的执行引擎；本节是"内部参考"，补全可能遗漏的边界。

### 3.2 Out-of-Scope（明确不做）

- [ ] 不接入 tushare / akshare / baostock 任何真实数据 fetcher（v0.4.0+）
- [ ] 不实现 grid_search 参数寻优（v0.4.0+）
- [ ] 不实现 walk-forward sample-out 验证（v0.4.0+）
- [ ] 不接入 live / paper trading（v0.4.0+）
- [ ] 不修改 quantide（millionaire）fork —— 任何接口不足走升级依赖版本路径
- [ ] 不重写策略层：`LGBMTop20Strategy` / `OptimizedTopKStrategy` 在 v0.3.0 保持不变（NFR-1000 向后兼容继承）
- [ ] 不改 `BacktestResult` dataclass 字段签名（v0.2.0 e2e 依赖其 5 个字段）
- [ ] 不改 `summary.json` 的 6 个 v0.1.0 必需键（仅扩展，可选键缺则 None）

### 3.3 约束条件

- **技术约束**：
  - `requires-python` 必须 `>=3.13`（quantide 硬性要求）
  - `quantide` 通过 `pyproject.toml` 的 `dependencies` 以 git URL 形式引入：`quantide @ git+https://github.com/agent-liyi/millionaire.git`
  - 不引入除 quantide / Python 升级外的任何新第三方依赖
- **组织约束**：
  - MVP 范围，控制在 1-2 个 issue 的工作量（建议拆 2 个 issue：`FR-1 BacktestRunner 接入` + `FR-2 metrics 委托`，可并行）
  - v0.2.0 全部 159 AC 必须保持绿色（含 NFR-1000 向后兼容集成测试）
  - 所有 e2e/perf 测试（21 个）wall time 不退化（quantide 真实回测应远小于 NFR-0100 AC-3 600s 预算）

---

## 4. 风险与假设 (Risk & Assumption)

### 4.1 关键假设

| #    | 假设内容 | 验证方式 | 验证负责人 |
| :--- | :------- | :------- | :--------- |
| 1 | quantide 的 `BacktestRunner.run()` 签名与用户描述完全一致（`strategy_cls, config, start_date, end_date, initial_cash`） | 在 M-FOUND 阶段读 `quantide.service.runner.BacktestRunner.run` 的源码或 docstring | M-FOUND Agent（Devon） |
| 2 | quantide 的 `DailyBarsStore` parquet 格式约定与用户描述一致（年分区、`date/asset/ohlc/volume/adj_factor` 列） | 在 M-FOUND 阶段读 `quantide.data.daily_bars` 源码 + 文档 | M-FOUND Agent（Devon） |
| 3 | 现有 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet`（50 资产 × 252 日）与 `tests/e2e/fixtures/ohlcv_10x60.parquet`（10 资产 × 60 日）的 OHLCV 列可直接 1:1 映射到 `DailyBarsStore`（无缺失 `ohlc`/`adj_factor` 列） | 写 convert 脚本时实际读 schema 验证 | M-DEV（Devon） |
| 4 | `BacktestBroker.bills()` 提供真实成交笔数与换手率，且接口稳定 | 在 M-FOUND 阶段 `dir(BacktestBroker.bills)` / `help()` | M-FOUND Agent（Devon） |
| 5 | Python 3.13 在本机（macOS，darwin）与 CI 上可用，pyproject 升级不会破坏 ruff/mypy 的 `target-version` 配置 | 升级后跑 `uv run ruff check . && uv run pytest` | M-DEV（Devon） |

### 4.2 主要风险

| #    | 风险描述 | 影响 | 应对策略 |
| :--- | :------- | :--- | :------- |
| 1 | quantide 接口签名与本 story 描述不一致（如 `run()` 参数顺序不同、`daily_bars` 不是单例等），需在 M-FOUND 阶段重新对齐 spec | 中 | 把 §2.3 AC-01/03/04 标 `[M-FOUND 锁定]`，M-FOUND Agent 必读 `quantide` 源码并产出对齐报告 |
| 2 | v0.2.0 的 e2e/perf 测试（21 个，含 NFR-0100 AC-3「单次回测 ≤ 600s」）因 quantide 真实回测比 `np.random` 慢而超时 | 中 | convert 脚本默认输出 50×252 fixture（与原 fixture 等大），保留 e2e 时间预算；如仍超时，把 fixture 缩到 10×60（已有现成 fixture） |
| 3 | `daily_bars.connect(store_path, calendar_store_path)` 是全局副作用，单元测试并发跑时会互相污染 | 中 | `run_backtest` 内部确保 `connect` 是幂等/覆盖式（用 pytest fixture 在每次 test 前 reset）；e2e 用独立 tmp dir |
| 4 | `summary.json` 扩展字段（sortino/drawdown_duration_days 等）若命名与 quantide 不一致，下游消费者会拿错字段名 | 低 | M-SPEC 阶段对 summary schema 做 lock（与现有 6 键并列），e2e 断言只用 6 键 + 1-2 个新键（如 sortino） |
| 5 | Python 3.13 升级后某些 v0.2.0 依赖（如 lightgbm、apscheduler）出现版本冲突 | 低 | 升级前先跑 `uv lock --upgrade` 试探；若冲突，锁次要依赖到 v0.2.0 兼容版本，记录到 history.md |

---

## 5. 必要性与冲突 (Necessity & Conflict)

### 5.1 必要性核查（每条 FR 是否必要）

| FR | 必要性论证 |
| -- | --------- |
| FR-1.1 加入 quantide 依赖 | **必要** —— 不引入 quantide，AC-04 委托目标不存在；无法导入 `quantide.service.runner.BacktestRunner` |
| FR-1.2 Python `>=3.13` | **必要** —— quantide 硬性要求；不升级则 `import quantide` 直接抛异常 |
| FR-1.3 写 `scripts/convert_fixture_to_quantide.py` | **必要** —— 原 OHLCV parquet 是 v0.2.0 fixture 格式（11 列含 `turnover/limit_up/limit_down`），与 `DailyBarsStore`（`date/asset/ohlc/volume/adj_factor`）不匹配；无转换脚本则 store 里无 bar 数据，回测静默失败 |
| FR-1.4 生成 calendar parquet | **必要** —— quantide `BacktestRunner.run(start_date, end_date, ...)` 需要交易日历定位实际交易 bar；缺 calendar 则 connect 抛错 |
| FR-1.5 重写 `runner.py`（删假数据分支 + 委托） | **必要** —— 这是 v0.3.0 的核心目标；不删假数据则"真实回测"目标不达成 |
| FR-1.6 CLI 表面 + 输出 schema 不变 | **必要** —— v0.1.0 AC-FR1100-01/02/03 + v0.2.0 21 个 e2e/perf 测试依赖；改动则 NFR-1000 向后兼容破 |
| FR-1.7 `daily_bars.connect()` 接线 | **必要** —— 不显式 connect，BacktestRunner 跑出空 NAV（与原假数据同样不可信，但不报错） |
| FR-2.1 metrics 委托 | **必要** —— `total_trades=0 / avg_turnover=0.0` 是假数据的最直接残留；不删则"metrics 真实"目标不达成 |
| FR-2.2 metrics 签名不变 | **必要** —— `evaluation/`、`visualization/`、e2e 测试、`tests/integration/test_backtest_cli.py::test_metrics_integration` 直接调用 `compute_performance_metrics`；签名变则全链路坏 |

**结论**：所有 9 条 FR 都是达到"回测输出从此可信"这一北极星目标的必要条件；无冗余 FR。

### 5.2 冲突核查（与 v0.2.0 设计决策的兼容性）

| v0.2.0 决策 | v0.3.0 是否冲突？ | 说明 |
| ---------- | ---------------- | ---- |
| **AC-FR1500-04 调度器隔离**：`src/trader_off/scheduler/` 不出现 `quantide.*` 业务 import | ❌ **不冲突** | v0.3.0 仅修改 `src/trader_off/backtest/{runner,metrics}.py` 与新增 `scripts/convert_fixture_to_quantide.py`；scheduler 模块零改动。AC-11 在 §2.3 显式重申此约束 |
| **Compat shim 模式（`trader_off.strategies.compat`）**：当 quantide 未安装时用 stub BaseStrategy / Broker | ❌ **不冲突，反而加强** | v0.3.0 把 quantide 升级为正式依赖后，`compat.py` 的 try/import 块在生产路径会成功 import 真 quantide；stub 仅在测试环境（quantide 未装）生效。`backtest/runner.py` 通过 `BaseStrategy_compat = trader_off.strategies.compat.BaseStrategy` 解析，**trader-off 自身代码不直接 `import quantide`**（AC-10 显式约束） |
| **`weights.csv` 文件解耦（AC-FR4200-02/04/05 + OptimizedTopKStrategy）**：策略通过读 `reports/portfolio_latest/weights.csv` 与 portfolio 模块解耦 | ❌ **不冲突** | v0.3.0 不改 OptimizedTopKStrategy，文件耦合模式原样保留。新 `runner.py` 通过 `BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, ...)` 传入 strategy class —— `config` dict 由 `run_backtest` 的 `config` 参数原样透传，weights.csv 的加载仍是 strategy 自身的 `init()` 行为 |
| **NFR-1000 v0.1.0 向后兼容**：LGBMTop20Strategy / OptimizedTopKStrategy 必须仍可 import + 实例化 + 运行 | ❌ **不冲突** | AC-10 强制策略经 `BaseStrategy_compat` 解析，v0.1.0 策略的 `__init__(broker, config)` 签名原样工作；AC-07 保持 CLI 表面不变 |
| **NFR-0100 性能预算（backtest ≤ 600s）** | ⚠️ **需验证** | 真实 quantide 回测通常比 `np.random` 快（无 Python 循环），但需在 e2e 上验证；纳入 §4.2 风险 #2 |
| **Summary.json 6 键 schema（AC-FR1200-01）** | ❌ **不冲突** | AC-06 显式继承 6 键 + 可选扩展 |

**结论**：v0.3.0 与 v0.2.0 全部设计决策兼容，不产生冲突。**v0.3.0 是对 v0.1.0/v0.2.0 立下的「quantide 接入」承诺的最终兑现**，而非推翻既有架构。

---

## 6. 方案疑议（A/B Advisory，非决策）

- **状态**：**无异议**
- **说明**：
  - 用户请求的方案 A（直接委托 quantide BacktestRunner.run + 删除假数据 + metrics 委托）与 v0.3.0 北极星目标（"回测输出从此可信"）完全对齐，无更优替代方案。
  - §5.1 必要性核查显示 9 条 FR 都是必要条件，无冗余可删。
  - §5.2 冲突核查显示与 v0.2.0 设计决策全部兼容，无隐性冲突。
  - **唯一待 M-FOUND 阶段确认的是 quantide 真实接口签名**（§4.1 假设 #1/#2/#4）—— 这是事实层确认，非方案 A/B 选择；若发现签名不符，需在 M-FOUND 阶段更新 AC-03/AC-04 的细节，但总体方案不变。

---

## 7. 分流结论与门禁 (Gate)

- **分流结论**：**Go**（Agent 建议）
- **理由**：
  - ✅ 4W 清晰：单用户、CLI+Python、明确委托路径、问题陈述具体（假数据导致不可信）
  - ✅ 风险可控：5 条风险均有应对策略（最重的是 quantide 接口签名，但 M-FOUND 阶段可锁定）
  - ✅ 价值指标可观测：`total_trades > 0` / `avg_turnover > 0` 即为成功标志
  - ✅ 与 v0.2.0 全部设计决策兼容（见 §5.2）
  - ✅ MVP 工作量可控：2 个 issue（FR-1 + FR-2 可并行）
  - ✅ v0.4.0+ 的 tushare / grid_search / walk-forward / live trading 已明确划在 Out-of-Scope

- **Human 确认**（仅决策点）：
  - [x] 分流结论认同（**Go**）
  - [x] 冲突 / A-B 建议已裁决（**无冲突 / 无异议**）
  - [x] Out-of-Scope 认同（tushare / grid_search / walk-forward / live trading 推迟到 v0.4.0+）

- **Backlog 登记**：**Go → 进入 M-FOUND**

---

## 8. 可追溯种子 (Traceability)

- **Story ID**：`STR-0001`
- **创建时间**：`2026-07-21T00:00:00Z`
- **Spec ID**：`v0.3.0-001-real-backtest`
- **关联 Issue（待填充）**：`#待创建`（建议拆 2 个：`FR-1 BacktestRunner 接入` + `FR-2 metrics 委托`）
- **关联 Spec ID（待 M-FOUND 填充）**：`#待创建`
- **继承基线**：
  - v0.1.0 `FR-1100 millionaire 回测接入` + `FR-1200 回测报告 — 绩效指标`（本 story 是其兑现）
  - v0.2.0 `NFR-1000 向后兼容` + `AC-FR1500-04 调度器隔离`（本 story 不破）

---

*—— 本故事由 M-STORY Agent 于 2026-07-21 生成；经 Human 确认后：Go → 进入 M-FOUND。*
