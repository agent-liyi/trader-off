---
status: draft
---
# trader-off v0.3.0 — 真实回测引擎接入 (quantide 替换假数据) — Spec

- **Spec ID**: v0.3.0-001-real-backtest
- **Created**: 2026-07-21
- **Status**: Draft
- **关联 PRD/story**: `.louke/project/specs/v0.3.0-001-real-backtest/story.md`
- **继承基线**:
  - v0.1.0 FR-1100 (millionaire 回测接入) + FR-1200 (回测报告 — 绩效指标) — **冻结契约,本文件不重复定义**
  - v0.1.0 NFR-0100~0700 与 v0.2.0 NFR-0100~0900 中关于向后兼容、调度器隔离、compat shim、weights.csv 解耦、性能预算的部分 — **继承为本文件的 NFR**

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。
> 验收标准 (可观察、可断言的通过条件) 放在 `acceptance.md` 中。
> 测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。
>
> **北极星目标**: 执行一次真实的回测 — `summary.json` 里 `total_trades > 0`、`avg_turnover > 0`、NAV 反映 LGBMTop20 策略在 50 资产 × 252 日 OHLCV 上的真实资金曲线,`BacktestBroker.bills()` 的成交笔数与 `trades_<ts>.parquet` 行数一致。
>
> **关键约束 (用户显式确认)**:
> - 工作量保持小 (MVP 范围,1-2 个 issue 工作量)
> - 保持分层:quantide = 通过依赖供应的执行引擎 (不动 fork);trader-off = α 研究平台 (不动)
> - 向后兼容:v0.1.0 全部 AC + v0.2.0 全部 21 个 e2e/perf 测试不退化

## User Stories

### US-0010 真实可信的回测输出

story: 作为一名量化研究员,我希望 `trader-off backtest` 命令输出真实的回测结果(NAV、positions、trades、metrics 均来自 quantide 引擎真实计算),而不是基于 `np.random.RandomState(42)` 的合成数据,使我能够相信优化器与策略闭环在 50 资产 × 252 日 fixture 上给出的指标就是真实可投资的结果,而不是固定种子的演示。
priority: P0

### US-0020 metrics 真实反映交易行为

story: 作为一名量化研究员,我希望 `summary.json` 中的 `total_trades` 与 `avg_turnover` 反映真实成交笔数与真实换手率(来自 `BacktestBroker.bills()`),而不是硬编码的 `0` 与 `0.0`,使我能够基于真实交易成本评估策略质量,而不是看到一个永远为 0 的"零交易"指标。
priority: P0

## Usage Scenarios

### scenario-0010 端到端真实回测

1. 开发者执行 `uv sync` 安装 quantide(自动升级到 Python ≥ 3.13)。
2. 开发者执行 `python scripts/convert_fixture_to_quantide.py` —— 把 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 转成 `tests/fixtures/v0.3.0/daily_bars_store/` (年分区 parquet) + `calendar_store/` (交易日历 parquet)。
3. 开发者执行 `trader-off backtest --model v1 --strategy lgbm_top20 --start 2023-01-01 --end 2023-12-31 --capital 1000000`。
4. `run_backtest` 在 `daily_bars.connect(store_path, calendar_store_path)` 之后委托给 `quantide.service.runner.BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, start_date, end_date, initial_cash)`。
5. 回测完成后,`reports/backtest_<ts>/` 下产出 `summary.json` (含真实 `total_trades > 0` / `avg_turnover > 0` / `sortino` / `drawdown_duration_days` 等) + 4 个真实 parquet (`nav_<ts>.parquet, positions_<ts>.parquet, trades_<ts>.parquet`)。
6. v0.1.0 / v0.2.0 的 e2e 测试 (`tests/e2e/test_full_pipeline_e2e.py::test_full_pipeline_*`) 继续通过,下游 `evaluation/`、`visualization/`、`tests/integration/test_backtest_cli.py` 零改动。

### scenario-0020 升级失败的明确失败模式

1. 开发者未运行 `convert_fixture_to_quantide.py` (即 `daily_bars_store/` 不存在)。
2. 开发者执行 `trader-off backtest ...`。
3. `daily_bars.connect(store_path, calendar_store_path)` 抛 `FileNotFoundError`(store 路径不存在)或 quantide 内部抛 "no bars in range" 异常。
4. CLI 退出码非 0(默认 5 = 引擎失败),stderr 含明确 message 如 `daily_bars store not found at <path>; run scripts/convert_fixture_to_quantide.py first`。
5. **不出现** 静默退化为合成 NAV 的失败模式(原 v0.1.0 兜底分支在 v0.3.0 已删除)。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表 (Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100 ~ FR-0900** 范围 (Module A — Real Backtest),与 v0.2.0 同范围但 spec-id 不同 (`v0.3.0-001-real-backtest`),FR 代码独立命名空间。9 条 FR 全部为 P0。
>
> M-FOUND 锁定标记: 部分 FR 标注 `[M-FOUND 锁定]`,表示真实 quantide API (如 `BacktestRunner.run` 签名) 需在 M-FOUND 阶段读源码确认;若签名与本 spec 描述不符,在 M-FOUND 阶段更新 AC 细节,但总体方案不变 (用户已确认无 A/B 替代)。

---

<a id="fr-0100"></a>
### FR-0100 Python 3.13 运行时升级 (pyproject + uv)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- `pyproject.toml` 中 `[project].requires-python` 从 `">=3.11"` 升级到 `">=3.13"`(quantide 硬性要求)。
- `[tool.ruff].target-version` 从 `"py311"` 同步升级到 `"py313"`。
- `[tool.mypy].python_version` 从 `"3.11"` 同步升级到 `"3.13"`。
- 升级后 `uv sync` 与 `uv run pytest tests/unit tests/integration tests/e2e` 在 Python 3.13 解释器下成功执行(无 `SyntaxError` / `ImportError` / 版本不匹配)。
- 升级后 `uv run ruff check .` 与 `uv run mypy src/trader_off/scheduler/` 退出码为 0。
- **不引入** 除 quantide / Python 升级外的任何新第三方依赖(用户约束)。
- **不修改** `trader_off` 包本身的 source code 以兼容 Python 3.13 新语法(仅调整 pyproject 配置即可,业务代码本身已用 `async/await` 与 PEP 604 union,3.13 下运行无问题)。

---

<a id="fr-0200"></a>
### FR-0200 quantide 依赖接入 (git URL)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- `pyproject.toml` 的 `[project].dependencies` 加入新条目:`quantide @ git+https://github.com/agent-liyi/millionaire.git`。
- `uv sync` 后在项目 venv 下能 `python -c "import quantide; from quantide.service.runner import BacktestRunner; print(BacktestRunner)"` 成功执行并打印类对象。
- `uv.lock` 中出现 `quantide` 条目,记录 commit SHA 与解析后的 wheel 元数据。
- **不修改** quantide fork(`millionaire` 仓)任何文件(用户约束);如发现接口缺失,记录 `[需 quantide 上游补齐]` 并升级依赖版本,不在 fork 上 monkey-patch。
- `trader_off` 项目代码**不直接** `import quantide`(仅 `trader_off.strategies.compat` 通过 `try/except ImportError` 解析,见 NFR-0200)。

---

<a id="fr-0300"></a>
### FR-0300 fixture 转换脚本 — OHLCV → DailyBarsStore

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ⚠️ [M-FOUND 锁定] DailyBarsStore 真实 schema | ✅ |

- 脚本路径:`scripts/convert_fixture_to_quantide.py`。
- 默认输入 fixtures:
  - `tests/fixtures/v0.2.0/ohlcv_50x252.parquet`(50 资产 × 252 日)
  - `tests/e2e/fixtures/ohlcv_10x60.parquet`(10 资产 × 60 日)
- 默认输出根目录:`tests/fixtures/v0.3.0/`,包含两个子目录:
  - `daily_bars_store/`:按年分区的 OHLCV parquet 文件,列定义 `{date, asset, ohlc, volume, adj_factor}`(其中 `ohlc` 为 struct 列含 `open/high/low/close` 子字段)。分区目录命名:`year=YYYY/`,每个分区文件命名为 `part-0.parquet`(quantide 约定)。`[M-FOUND 锁定]` 列顺序、分区键名、struct 子字段命名以 `quantide.data.daily_bars` 源码为准。
  - `calendar_store/`:交易日历 parquet,列定义 `{date, is_trading_day}`,从原 ohlcv 的 `date` 列去重生成(隐含 `is_trading_day=True`)。
- 列映射规则(原 ohlcv → 目标 DailyBarsStore):
  - `date` (Date) → `date` (Date)
  - `asset` (Utf8) → `asset` (Utf8)
  - `open, high, low, close` (Float64) → `ohlc` (Struct[open: Float64, high: Float64, low: Float64, close: Float64])
  - `volume` (Float64) → `volume` (Float64)
  - `adj_factor` (Float64) → `adj_factor` (Float64)
  - 原 ohlcv 的 `turnover, limit_up, limit_down` 列丢弃(quantide DailyBarsStore 不需要)
- CLI:`python scripts/convert_fixture_to_quantide.py [--input <path>] [--output-root <path>] [--source-version v0.2.0|v0.3.0] [--fixture ohlcv_50x252|ohlcv_10x60|all]`。
  - 默认 `--source-version v0.2.0`(读取 v0.2.0 fixtures)
  - 默认 `--fixture all`(同时转换两个 fixtures)
- 退出码:
  - 0: 转换成功,所有 fixtures 落盘
  - 2: 输入文件不存在
  - 3: 输入 parquet schema 不匹配(缺少 `date/asset/open/high/low/close/volume/adj_factor` 列)
- 输出日志:`Converted N rows × M assets from <input> to <output>/daily_bars_store/ (year-partitioned, <K> partitions)`。
- **幂等性**:重复运行覆盖目标目录(`shutil.rmtree(output, ignore_errors=True)` 后重建)。

---

<a id="fr-0400"></a>
### FR-0400 交易日历生成脚本

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ⚠️ [M-FOUND 锁定] quantide calendar 真实 schema | ✅ |

- 脚本路径:`scripts/generate_calendar.py`(与 FR-0300 独立,支持单独重跑)。
- 默认输入:`tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 的 `date` 列(去重排序)。
- 默认输出:`tests/fixtures/v0.3.0/calendar_store/calendar.parquet`,列定义 `{date, is_trading_day}`,所有行 `is_trading_day=True`。
- `[M-FOUND 锁定]` quantide `BacktestRunner.run(start_date, end_date, ...)` 实际如何读交易日历(单文件 vs 分区 vs store 子目录)以源码为准;若 quantide 期望 `calendar_store/calendar.parquet` 之外的结构,本 FR 在 M-FOUND 阶段修正输出 schema。
- CLI:`python scripts/generate_calendar.py [--source <ohlcv_parquet>] [--output <calendar_store_path>] [--start <YYYY-MM-DD>] [--end <YYYY-MM-DD>]`。
- 退出码:0 = 成功,2 = 输入文件缺失,3 = 输出目录无法创建。
- **自动联动**:若在 FR-0300 之后未运行本脚本,`convert_fixture_to_quantide.py --fixture all` 会自动调用 `generate_calendar.py`(避免漏步骤)。

---

<a id="fr-0500"></a>
### FR-0500 重写 runner.py — 删除假数据分支 + 委托 quantide

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ⚠️ [M-FOUND 锁定] BacktestRunner.run 真实签名 | ✅ |

- 模块路径:`src/trader_off/backtest/runner.py`。
- **删除**原 72-100 行 `np.random.RandomState(42)` 合成 NAV / positions / trades 分支(完全移除,不留兜底)。
- **新增**委托逻辑:
  - 通过 `daily_bars.connect(store_path, calendar_store_path)` 在 run 之前接入 daily_bars 单例,`store_path` 与 `calendar_store_path` 默认指向 `tests/fixtures/v0.3.0/daily_bars_store/` 与 `tests/fixtures/v0.3.0/calendar_store/`(可通过 `run_backtest(..., config={"store_path": ..., "calendar_store_path": ...})` 覆盖)。
  - 调用 `quantide.service.runner.BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, start_date=start, end_date=end, initial_cash=capital)`。
  - `[M-FOUND 锁定]` 真实 `BacktestRunner.run` 的参数顺序、关键字参数名、返回值类型 (`BacktestResult` dataclass 字段) 以 `quantide.service.runner` 源码为准;若签名不一致,在 M-FOUND 阶段更新本 FR 描述。
  - 解析策略类:`BaseStrategy_compat = trader_off.strategies.compat.BaseStrategy`(经 compat shim 解析,trader-off 自身不直接 import quantide,见 NFR-0200)。
  - 解析 strategy_name:`lgbm_top20` → `LGBMTop20Strategy`;`optimized_topk` → `OptimizedTopKStrategy`(策略名到类的映射由 `trader_off.strategies.registry` 提供,继承 v0.2.0)。
  - `config` 透传:从 `run_backtest(..., config=...)` 传入的 dict 原样作为 `BacktestRunner.run` 的 `config` 参数。
- **保留** `BacktestResult` dataclass 字段签名:`{summary: dict, positions: pl.DataFrame, trades: pl.DataFrame, nav: pl.DataFrame, report_dir: Path}`(与 v0.2.0 一致,供 `BacktestResult(...)` 返回)。
- **保留** 公开 API:`run_backtest(model_version: str, strategy_name: str, start: date, end: date, capital: float, config: dict | None = None) -> BacktestResult` 签名不变(下游 `cli/backtest.py` 与 e2e 测试零改动)。
- **新增** `store_path` / `calendar_store_path` 配置项:默认从 v0.3.0 fixtures 路径加载,可通过 `run_backtest(..., config={...})` 覆盖为自定义路径(单元测试可用 tmp dir)。
- 日志:`loguru.logger.info("Connecting daily_bars to {store_path}")` → `"Running BacktestRunner with strategy={strategy_name}, capital={capital}"` → `"Backtest finished. Reports saved to {report_dir}"`。

---

<a id="fr-0600"></a>
### FR-0600 CLI 表面与输出 schema 兼容性

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- CLI 入口:`trader-off backtest --model <version> --strategy <name> --start <YYYY-MM-DD> --end <YYYY-MM-DD> --capital <float> [--config <yaml>]`(继承 v0.1.0 FR-1100 AC-1)。
- 退出码(继承 v0.1.0 FR-1100 AC-3 + 扩展):
  - 0: 成功
  - 2: `--capital` 等必填参数缺失(argparse 错误)
  - 4: 配置文件 schema 校验失败(`pydantic.ValidationError`)
  - 5: 回测引擎失败(`BacktestRunner.run` 抛异常,或 `daily_bars.connect` 抛异常)
- 输出目录:`reports/backtest_<ts>/`,其中 `<ts>` 格式 `%Y%m%d_%H%M%S`(继承 v0.1.0 FR-1100)。
- 输出文件清单(继承 v0.1.0 FR-1100 AC-2):
  - `summary.json`
  - `nav_<ts>.parquet`
  - `positions_<ts>.parquet`
  - `trades_<ts>.parquet`
- `summary.json` schema:
  - **6 个 v0.1.0 必需键**(继承 v0.1.0 FR-1200 AC-1):`annualized_return, sharpe_ratio, max_drawdown, win_rate, total_trades, avg_turnover`
  - **类型约束**(继承 v0.1.0 FR-1200 AC-1):`annualized_return, sharpe_ratio, max_drawdown, win_rate, avg_turnover` 为 `float`;`total_trades` 为 `int`
  - **新增可选键**(quantide 提供,缺失即 `None`):
    - `sortino`: float(Sortino 比率)
    - `drawdown_duration_days`: int(最大回撤持续天数)
    - `benchmark_return`: float(基准收益率)
    - `total_trades_real`: int(来自 `BacktestBroker.bills()` 的真实成交笔数)
    - `avg_turnover_real`: float(真实日均换手率)
  - **向后兼容断言**:v0.1.0 e2e 测试断言只检查 6 个必需键存在,扩展键不影响断言通过。
- 日志格式继承 v0.2.0 NFR-0600:`{time} | {level} | {name}:{function}:{line} | {message}`,INFO 级输出关键进度。

---

<a id="fr-0700"></a>
### FR-0700 测试断言升级 — 从「文件存在」到「指标数值合理」

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **`tests/unit/backtest/test_runner.py::TestRunBacktest::test_output_files`** 断言升级:
  - 现有断言:`summary.json` 存在 + 含 6 个必需键 + parquet 行数 > 0(继承 v0.1.0)
  - 新增断言(本 FR):
    - `result.summary["total_trades"] > 0`(真实成交笔数,非硬编码 0)
    - `result.summary["avg_turnover"] > 0.0`(真实换手率,非硬编码 0.0)
    - `result.summary["annualized_return"]` 是有限数(`math.isfinite(...) == True`,非 NaN/Inf)
    - `result.summary["max_drawdown"] <= 0.0`(回撤为负数或零,符合约定)
- **`tests/unit/backtest/test_metrics.py::TestComputePerformanceMetrics::test_keys`** 断言升级:
  - 现有断言:6 个必需键存在 + 类型正确
  - 新增断言:`compute_performance_metrics` 返回值中 `total_trades > 0` 且 `avg_turnover > 0.0`(前提:`run_backtest` 真实执行后传入真实 NAV)
  - **重要**:本测试的 `test_keys` 直接调用 `compute_performance_metrics(nav_df)`,不经过 `run_backtest`;为使其断言 `total_trades > 0`,需扩展 metrics 输入接口(见 FR-0800 公开签名说明 —— 通过 `config` 参数接收 `bills` 数据,或在 metrics 内部委托 quantide 时使用 mock broker)
- **`tests/integration/test_backtest_cli.py::test_metrics_integration`** 断言升级:
  - 现有断言:`run_backtest` 返回 summary 类型正确 + 数值范围合理
  - 新增断言:`summary["total_trades"] > 0` 与 `summary["avg_turnover"] > 0.0`
- **`tests/e2e/test_full_pipeline_e2e.py`** 端到端断言升级(若适用):
  - 全链路真实回测后,断言 `summary.json` 含 `sortino` 字段(`is not None`)
  - 断言 wall time ≤ 600s(NFR-0500 性能预算)
- **保留**所有 v0.1.0 / v0.2.0 已存在的断言(不删旧断言,仅增量添加)。

---

<a id="fr-0800"></a>
### FR-0800 metrics.py 委托给 quantide.service.metrics

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ⚠️ [M-FOUND 锁定] quantide.service.metrics 真实接口 | ✅ |

- 模块路径:`src/trader_off/backtest/metrics.py`。
- **删除**原 66-68 行硬编码:
  ```python
  total_trades = 0
  avg_turnover = 0.0
  ```
- **替换**为委托逻辑:
  - 调用 `quantide.service.metrics.compute_metrics(nav_df=nav_df, bills=bills, benchmark_returns=benchmark_returns)` 返回真实指标 dict。
  - 输入参数:
    - `nav_df`: `pl.DataFrame`,列 `{date, nav}`(继承现有)
    - `bills`: `pl.DataFrame`,列 `{date, asset, action, quantity, price}`,来自 `BacktestBroker.bills()`(由 `run_backtest` 收集后传入 metrics)
    - `benchmark_returns`: `pl.DataFrame` 或 `None`,列 `{date, return}`,基准收益对比(可选,quantide 内部 fallback)
  - 返回值:`dict`,含 6 个 v0.1.0 必需键 + 新增可选键(见 FR-0600 summary schema)。
  - `[M-FOUND 锁定]` `quantide.service.metrics.compute_metrics` 真实函数名、参数名、返回值 schema 以源码为准;若与本 FR 描述不符,在 M-FOUND 阶段更新本 FR 描述与对应 AC。
- **错误处理**:
  - `< 30` 日 NAV 数据时仍抛 `InsufficientDataError`(继承 v0.1.0 FR-1200 AC-3)
  - quantide 委托失败时抛 `RuntimeError`,message 含 quantide 内部异常 traceback 前 3 行
- **日志**:`logger.debug(f"Delegated metrics computation to quantide, returned {len(result)} keys")`。

---

<a id="fr-0900"></a>
### FR-0900 compute_metrics() 公开签名保持不变

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 公开函数签名:`compute_performance_metrics(nav_df: pl.DataFrame) -> dict`(单参数,无新增必填参数)。
- **下游零改动**:
  - `src/trader_off/evaluation/` 模块直接调用 `compute_performance_metrics(nav_df)`,无需修改任何 import 或调用方式
  - `src/trader_off/visualization/` 模块同上
  - `tests/integration/test_backtest_cli.py::test_metrics_integration` 直接调用 `result = run_backtest(...)` 后断言 `result.summary` 字段(已通过 BacktestResult 间接消费 metrics)
  - `tests/unit/backtest/test_metrics.py::TestComputePerformanceMetrics::test_keys` 直接调用 `compute_performance_metrics(nav_df)`
- **内部扩展**(不影响公开签名):
  - 函数体内部可调用 `quantide.service.metrics.compute_metrics(nav_df=..., bills=..., benchmark_returns=...)`,其中 `bills` 与 `benchmark_returns` 通过以下两种方式之一获取:
    - **方式 A**(推荐):在 `run_backtest` 内部收集 `bills = BacktestBroker.bills()` 后,作为 closure 或 thread-local 传入 `compute_performance_metrics`
    - **方式 B**:在 `compute_performance_metrics` 内部新建一个 quantide context,通过 `daily_bars` 单例查询
  - `[M-FOUND 锁定]` 具体方式以 `quantide.service.metrics` 真实接口设计为准;若 quantide 期望 `bills` 作为必传参数,采用方式 A;否则采用方式 B
- **6 个必需键** + **类型约束** 完全继承 v0.1.0 FR-1200 AC-1。
- **新增可选键**(`sortino, drawdown_duration_days, benchmark_return, ...` 等)在返回值中存在但**不**出现在 6 个必需键集合中;下游测试断言 `set(result.keys()) == required_6_keys` 仍通过(若断言使用 `issubset` 则新增键不影响)。

---

## Non-Functional Requirements

<a id="nfr-0100"></a>
### NFR-0100 调度器隔离 (继承 v0.2.0 AC-FR1500-04)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- `src/trader_off/scheduler/` 路径下不出现 `quantide.*` 或 `millionaire` 业务 import。
- 验证命令:`grep -rn "quantide\|millionaire" src/trader_off/scheduler/` 仅返回 `pyproject.toml` 的依赖声明(不在 `src/trader_off/scheduler/` 目录下)。
- v0.2.0 AC-FR1500-04 仍通过(原断言文件 `tests/integration/test_retrain_full.py` 或 `test_scheduler_resilience.py` 中的 scheduler 隔离测试零修改即可继续通过)。
- v0.3.0 仅修改 `src/trader_off/backtest/{runner,metrics}.py` 与新增 `scripts/{convert_fixture_to_quantide,generate_calendar}.py`,scheduler 模块零改动。

---

<a id="nfr-0200"></a>
### NFR-0200 Compat shim 模式保留 (trader-off 不直接 import quantide)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- `trader_off.strategies.compat.BaseStrategy` 通过 `try/except ImportError` 解析 quantide 或 fallback stub(继承 v0.2.0)。
- 验证命令:`grep -rn "import quantide" src/trader_off/backtest/ src/trader_off/strategies/lgbm_top20.py src/trader_off/strategies/optimized_topk.py` 应**仅**在 `src/trader_off/strategies/compat.py` 内出现 import 语句,其他业务模块不直接 import quantide。
- 生产路径(quantide 已装):`from quantide.core.strategy import BaseStrategy` 在 compat.py 内成功执行。
- 测试路径(quantide 未装 / 测试环境 stub):`import quantide` 抛 `ImportError`,compat.py 自动 fallback 到本地 stub 类。
- `backtest/runner.py` 通过 `BaseStrategy_compat = trader_off.strategies.compat.BaseStrategy` 解析,自身代码 `import trader_off.strategies.compat` 不 `import quantide`。

---

<a id="nfr-0300"></a>
### NFR-0300 weights.csv 解耦保留 (OptimizedTopKStrategy)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- v0.2.0 `OptimizedTopKStrategy` 通过读 `reports/portfolio_latest/weights.csv` 与 portfolio 模块解耦(继承 v0.2.0 AC-FR4200-02/04/05)。
- v0.3.0 不修改 `OptimizedTopKStrategy` 类源码。
- 新 `runner.py` 通过 `BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, ...)` 传入 strategy class —— `config` dict 由 `run_backtest` 的 `config` 参数原样透传,`weights.csv` 的加载仍是 strategy 自身的 `init()` 行为。
- e2e 端到端测试中,`OptimizedTopKStrategy` 通过新 `runner.py` 执行回测,产出真实 NAV/positions/trades,而 weights.csv 加载逻辑保持原状。

---

<a id="nfr-0400"></a>
### NFR-0400 向后兼容 — v0.1.0 + v0.2.0 AC 全绿

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- v0.1.0 FR-1100 AC-1/2/3(CLI exit 0 + 输出文件 + `--capital` 缺失报错)继续通过。
- v0.1.0 FR-1200 AC-1/2/3(compute_performance_metrics 6 键 + max_drawdown 计算 + `<30` 天 `InsufficientDataError`)继续通过。
- v0.2.0 全部 21 个 e2e/perf 测试(子集自 v0.2.0 159 AC)继续通过(含 `tests/perf/test_perf_budget.py::TestBacktestPerf::test_backtest_under_600s`)。
- v0.2.0 AC-FR1500-04(调度器隔离)继续通过(见 NFR-0100)。
- v0.2.0 weights.csv 解耦(AC-FR4200-02/04/05)继续工作(见 NFR-0300)。
- 验证命令:`uv run pytest tests/unit tests/integration tests/e2e -v` 全绿,无 `FAILED` 或 `ERROR`。
- **向后兼容断言计数(Ground Truth,核对于 v0.3.0 spec 起草时)**:
  - v0.1.0 acceptance.md:`grep -c "^### AC-[0-9]\+" acceptance.md` = **79 AC**(FR-0100~1600 + NFR-0100~0700,每 FR/NFR 平均 3-4 AC)
  - v0.2.0 acceptance.md:`grep -c "^### AC-[0-9]\+" acceptance.md` = **159 AC**(FR-0100~0900 模块 A + FR-1500~2700 模块 B + FR-3000~4200 模块 C + NFR-0100~0900)
  - v0.2.0 的 21 个 e2e/perf 测试是 159 AC 的**子集**(不是独立于 AC 的另一组断言),其中部分 AC 既属单元/集成测试又覆盖 e2e/perf 路径
  - **总保留断言**:v0.1.0 79 AC + v0.2.0 159 AC = **238 个旧断言**必须全保留,v0.3.0 新增断言增量添加,不删旧断言。


---

<a id="nfr-0500"></a>
### NFR-0500 性能预算 (继承 v0.2.0 NFR-0100)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 单次回测 wall time ≤ 600s(50 资产 × 252 日 fixture,e2e 计时,继承 v0.2.0 NFR-0100 AC-3)。
- 内存峰值 ≤ 16 GB(继承 v0.2.0 NFR-0100)。
- 真实 quantide 回测通常比 `np.random` 快(无 Python 循环),无需缩 fixture。
- 验证:`tests/perf/test_perf_budget.py::TestBacktestPerf::test_backtest_under_600s` 在 v0.3.0 真实回测路径下通过。
- 若真实回测因 quantide 内部开销超 600s,降级方案:把 e2e 默认 fixture 缩到 10×60(已存在 `tests/e2e/fixtures/ohlcv_10x60.parquet`),记录到 `history.md`。

---

## Clarification Log

| Round | Topic | Decision | Status |
|---|---|---|---|
| 0 (Story M-STORY) | FR-1.1~FR-1.7 + FR-2.1~FR-2.2 必要性 | 9 条 FR 全部必要,无冗余 | ✅ (Story §5.1 已论证) |
| 0 (Story M-STORY) | 与 v0.2.0 设计决策兼容性 | 全部兼容,无冲突(AC-FR1500-04 调度器隔离、compat shim、weights.csv 解耦均保留) | ✅ (Story §5.2 已论证) |
| 0 (Story M-STORY) | Out-of-Scope | tushare / grid_search / walk-forward / live trading 推迟到 v0.4.0+ | ✅ (Story §3.2 已确认) |
| 0 (Story M-STORY) | 不修改 quantide fork | 任何接口不足走升级依赖版本路径,不在 fork 上 monkey-patch | ✅ (Story §3.1 Avoid 已确认) |
| 0 (Task) | MVP 工作量 | 控制在 1-2 个 issue 工作量(FR-1 BacktestRunner 接入 + FR-2 metrics 委托 可并行) | ✅ (用户 Task 描述已确认) |
| 0 (Task) | FR 编号 | 使用 FR-0100 ~ FR-0900 (与 v0.2.0 同范围,不同 spec-id,独立命名空间) | ✅ (Sage 决策,文档中已说明) |
| 待 M-FOUND | BacktestRunner.run 真实签名 | 在 M-FOUND 阶段读 `quantide.service.runner` 源码确认;若签名与本 FR-0500 描述不符,更新 AC 细节 | ⚠️ [M-FOUND 锁定] |
| 待 M-FOUND | DailyBarsStore 真实 schema | 在 M-FOUND 阶段读 `quantide.data.daily_bars` 源码确认;若列/分区与本 FR-0300 描述不符,更新 AC 细节 | ⚠️ [M-FOUND 锁定] |
| 待 M-FOUND | quantide.service.metrics 真实接口 | 在 M-FOUND 阶段读 `quantide.service.metrics` 源码确认;若函数名/参数/返回值与本 FR-0800 描述不符,更新 AC 细节 | ⚠️ [M-FOUND 锁定] |
| 待 M-FOUND | calendar store 真实 schema | 在 M-FOUND 阶段读 quantide 源码确认 calendar 路径与列定义 | ⚠️ [M-FOUND 锁定] |
| 待 M-FOUND | BacktestBroker.bills() 真实 schema | 在 M-FOUND 阶段读 `quantide.service.broker.BacktestBroker.bills()` 源码确认返回列定义 | ⚠️ [M-FOUND 锁定] |
