# trader-off v0.3.0 — 真实回测引擎接入 (quantide 替换假数据) — Acceptance Criteria

- **Spec ID**: v0.3.0-001-real-backtest
- **Created**: 2026-07-21
- **继承基线**: v0.1.0 FR-1100/1200 与 v0.2.0 FR-1500~2700 / FR-3000~4200 的 AC 在本文件中**不重复**;仅通过 v0.1.0 / v0.2.0 acceptance 引用。本文件仅定义 v0.3.0 新增的 9 条 FR 的 AC。

> 中央注册表:spec.md 只保留 FR/NFR 描述与元数据 (testability/decided/valid);可观察、可断言的通过条件在本表中。
>
> 编号约定:
> - 每个 FR/NFR 单元内 AC-N 从 1 起,按顺序递增;单元之间不复用
> - 完整 AC 引用:**AC-FRXXXX-YY** (4 位 FR + 2 位 AC 序号),与 test-plan / issue schema 保持一致
> - 标题层级:`## FR-XXXX {title}` 为 level-2;`### AC-N` 为 level-3(其后同一行**不**接任何文字,canonical ID 写在下一行)
>
> Lex 阶段 1/2 审查验证: (1) 本表存在; (2) spec.md 每个 FR/NFR 在本表中有对应章节; (3) 每条 AC 可被测试或断言。

---

<a id="ac-fr-0100"></a>
## FR-0100 Python 3.13 运行时升级 (pyproject + uv)

### AC-1

AC-FR0100-01

- 给定:`pyproject.toml` 中 `[project].requires-python = ">=3.11"`。
- 当:升级到 `">=3.13"`。
- 那么:文件包含 `"requires-python" = ">=3.13"`,原 `">=3.11"` 不再出现。
- 断言:`tomllib.loads(Path("pyproject.toml").read_text())["project"]["requires-python"] == ">=3.13"`。

### AC-2

AC-FR0100-02

- 给定:`[tool.ruff].target-version = "py311"` 与 `[tool.mypy].python_version = "3.11"`。
- 当:升级。
- 那么:`[tool.ruff].target-version = "py313"`,`[tool.mypy].python_version = "3.13"`。
- 断言:`tomllib.loads(Path("pyproject.toml").read_text())["tool"]["ruff"]["target-version"] == "py313"` 且 `["tool"]["mypy"]["python_version"] == "3.13"`。

### AC-3

AC-FR0100-03

- 给定:Python 3.13 解释器(`python3.13 --version` 退出码 0)。
- 当:执行 `uv sync` 与 `uv run pytest tests/unit -x --no-cov`。
- 那么:两者退出码均为 0,无 `SyntaxError` / `ImportError` / 版本不匹配报错。
- 断言:`subprocess.run(["uv", "sync"]).returncode == 0 and subprocess.run(["uv", "run", "pytest", "tests/unit", "-x", "--no-cov"]).returncode == 0`。

### AC-4

AC-FR0100-04

- 给定:Python 3.13 环境。
- 当:执行 `uv run ruff check .` 与 `uv run mypy src/trader_off/scheduler/`。
- 那么:两者退出码均为 0。
- 断言:`subprocess.run(["uv", "run", "ruff", "check", "."]).returncode == 0 and subprocess.run(["uv", "run", "mypy", "src/trader_off/scheduler/"]).returncode == 0`。

### AC-5

AC-FR0100-05

- 给定:`pyproject.toml` 在 v0.3.0 升级前后。
- 当:比对 `[project].dependencies` 与 `[dependency-groups]`。
- 那么:除 `quantide`(FR-0200)外,无新第三方依赖加入。
- 断言:升级前 `dependencies` 集合与升级后 `dependencies` 集合的差集 == `{"quantide"}`(单向包含)。

---

<a id="ac-fr-0200"></a>
## FR-0200 quantide 依赖接入 (git URL)

### AC-1

AC-FR0200-01

- 给定:`pyproject.toml` 的 `[project].dependencies`。
- 当:读取内容。
- 那么:含条目 `quantide @ git+https://github.com/agent-liyi/millionaire.git`。
- 断言:`"quantide @ git+https://github.com/agent-liyi/millionaire.git" in tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]`。

### AC-2

AC-FR0200-02

- 给定:执行 `uv sync` 后。
- 当:在项目 venv 下执行 `python -c "import quantide; from quantide.service.runner import BacktestRunner; print(BacktestRunner)"`。
- 那么:退出码 0,stdout 含类对象字符串(如 `<class 'quantide.service.runner.BacktestRunner'>`)。
- 断言:`subprocess.run(["uv", "run", "python", "-c", "import quantide; from quantide.service.runner import BacktestRunner; print(BacktestRunner)"]).returncode == 0 and "BacktestRunner" in result.stdout`。

### AC-3

AC-FR0200-03

- 给定:`uv sync` 后。
- 当:检查 `uv.lock`。
- 那么:文件含 `name = "quantide"` 条目,记录 commit SHA 与解析后的 wheel 元数据。
- 断言:`"name = \"quantide\"" in Path("uv.lock").read_text()` 且 grep 命中 `[[package]]` 块中 `name = "quantide"`。

### AC-4

AC-FR0200-04

- 给定:trader-off 项目源码(`src/trader_off/**/*.py`)。
- 当:执行 `grep -rn "quantide" src/trader_off/`。
- 那么:仅在 `src/trader_off/strategies/compat.py` 内出现 `import quantide` 语句,其他业务模块不直接 `import quantide`。
- 断言:`[m for m in Path("src/trader_off").rglob("*.py") if "import quantide" in m.read_text() and m.name != "compat.py"] == []`。

### AC-5

AC-FR0200-05

- 给定:用户约束「不修改 quantide fork」。
- 当:检查 git 工作树。
- 那么:`millionaire` fork 无任何本地 commit(无 `git diff` 输出,HEAD 仍指向原始 commit)。
- 断言:`subprocess.run(["git", "status"], cwd=<millionaire_path>).stdout` 无 modified/added/deleted 区块。

---

<a id="ac-fr-0300"></a>
## FR-0300 fixture 转换脚本 — OHLCV → DailyBarsStore

### AC-1

AC-FR0300-01

- 给定:脚本 `scripts/convert_fixture_to_quantide.py`。
- 当:执行 `python scripts/convert_fixture_to_quantide.py --fixture ohlcv_50x252`(默认参数)。
- 那么:退出码 0,`tests/fixtures/v0.3.0/daily_bars_store/` 下生成年分区 parquet 文件(如 `year=2022/part-0.parquet`、`year=2023/part-0.parquet`)。
- 断言:`subprocess.run(["python", "scripts/convert_fixture_to_quantide.py", "--fixture", "ohlcv_50x252"]).returncode == 0 and any(Path("tests/fixtures/v0.3.0/daily_bars_store/").rglob("*.parquet"))`。

### AC-2

AC-FR0300-02

- 给定:转换完成后的 `daily_bars_store/year=YYYY/part-0.parquet`。
- 当:用 polars 读取。
- 那么:列定义含 `{date, asset, ohlc, volume, adj_factor}`,其中 `ohlc` 为 struct 列含 `{open, high, low, close}` 子字段。
- 断言:`set(df.columns) == {"date", "asset", "ohlc", "volume", "adj_factor"} and set(df.schema["ohlc"].fields) == {"open", "high", "low", "close"}`。

### AC-3

AC-FR0300-03

- 给定:原 ohlcv parquet 50 资产 × 252 日。
- 当:转换完成。
- 那么:行数与原 parquet 一致(50 × 252 = 12600),无丢失;`date` 列范围覆盖原 parquet 的 `[min_date, max_date]`。
- 断言:`len(df) == 12600 and df["date"].min() == pl.read_parquet("tests/fixtures/v0.2.0/ohlcv_50x252.parquet")["date"].min()`。

### AC-4

AC-FR0300-04

- 给定:原 ohlcv parquet 含列 `turnover, limit_up, limit_down`。
- 当:转换完成。
- 那么:目标 parquet 中**不**含这 3 列(quantide DailyBarsStore 不需要)。
- 断言:`"turnover" not in df.columns and "limit_up" not in df.columns and "limit_down" not in df.columns`。

### AC-5

AC-FR0300-05

- 给定:CLI `--fixture all` 或 `--fixture ohlcv_10x60`。
- 当:执行。
- 那么:`tests/fixtures/v0.3.0/daily_bars_store/` 同时(或单独)含 10×60 fixture 的年分区 parquet。
- 断言:`any("ohlcv_10x60" in str(p) for p in Path("tests/fixtures/v0.3.0/daily_bars_store/").rglob("*.parquet"))`。

### AC-6

AC-FR0300-06

- 给定:CLI `--input /nonexistent.parquet`。
- 当:执行。
- 那么:退出码 2,stderr 含 "input file not found"。
- 断言:`result.returncode == 2 and "input file not found" in result.stderr`。

### AC-7

AC-FR0300-07

- 给定:CLI 接受 `--input`(单文件路径)。
- 当:人工构造一个 schema 错误的 parquet(删除 `volume` 列)。
- 那么:退出码 3,stderr 含 "schema mismatch" 或具体缺失列名。
- 断言:`result.returncode == 3 and ("schema mismatch" in result.stderr or "volume" in result.stderr)`。

### AC-8

AC-FR0300-08

- 给定:已存在 `tests/fixtures/v0.3.0/daily_bars_store/` 目录(含旧文件)。
- 当:重新运行 `convert_fixture_to_quantide.py`。
- 那么:旧文件被覆盖,目标目录结构与新转换结果一致(幂等性)。
- 断言:重新转换前后 `daily_bars_store/` 下文件 SHA256 列表相同(`set(old_hashes) == set(new_hashes)`)。

---

<a id="ac-fr-0400"></a>
## FR-0400 交易日历生成脚本

### AC-1

AC-FR0400-01

- 给定:脚本 `scripts/generate_calendar.py`。
- 当:执行 `python scripts/generate_calendar.py`(默认参数)。
- 那么:退出码 0,`tests/fixtures/v0.3.0/calendar_store/calendar.parquet` 生成。
- 断言:`subprocess.run(["python", "scripts/generate_calendar.py"]).returncode == 0 and Path("tests/fixtures/v0.3.0/calendar_store/calendar.parquet").exists()`。

### AC-2

AC-FR0400-02

- 给定:生成的 `calendar.parquet`。
- 当:用 polars 读取。
- 那么:列定义含 `{date, is_trading_day}`,所有行 `is_trading_day == True`。
- 断言:`set(df.columns) == {"date", "is_trading_day"} and df["is_trading_day"].all() == True`。

### AC-3

AC-FR0400-03

- 给定:原 ohlcv_50x252.parquet 的 `date` 列(252 个交易日,可能含周末已过滤)。
- 当:读取 calendar.parquet。
- 那么:行数 ≤ 252(calendar 是去重后的交易日集合),`date` 范围 = 原 parquet 的 date 范围。
- 断言:`len(df) <= 252 and df["date"].min() == source["date"].min() and df["date"].max() == source["date"].max()`。

### AC-4

AC-FR0400-04

- 给定:CLI `--source /nonexistent.parquet`。
- 当:执行。
- 那么:退出码 2,stderr 含 "source not found"。
- 断言:`result.returncode == 2 and "source not found" in result.stderr`。

### AC-5

AC-FR0400-05

- 给定:仅运行 `convert_fixture_to_quantide.py --fixture all` 而**未**单独运行 `generate_calendar.py`。
- 当:执行。
- 那么:convert 脚本自动调用 generate_calendar.py(联动),`calendar_store/calendar.parquet` 与 `daily_bars_store/` 同时生成。
- 断言:`Path("tests/fixtures/v0.3.0/calendar_store/calendar.parquet").exists() and any(Path("tests/fixtures/v0.3.0/daily_bars_store/").rglob("*.parquet"))`。

---

<a id="ac-fr-0500"></a>
## FR-0500 重写 runner.py — 删除假数据分支 + 委托 quantide

### AC-1

AC-FR0500-01

- 给定:`src/trader_off/backtest/runner.py` 在 v0.3.0 重写后。
- 当:用 `grep` 检查。
- 那么:文件内**不**含 `np.random.RandomState(42)` 字符串(原合成 NAV 分支已删除)。
- 断言:`"np.random.RandomState(42)" not in Path("src/trader_off/backtest/runner.py").read_text()`。

### AC-2

AC-FR0500-02

- 给定:重写后的 `runner.py`。
- 当:用 `grep` 检查。
- 那么:含 `daily_bars.connect(` 调用语句,传入 `store_path` 与 `calendar_store_path`。
- 断言:`"daily_bars.connect(" in runner_text and "store_path" in runner_text and "calendar_store_path" in runner_text`。

### AC-3

AC-FR0500-03

- 给定:重写后的 `runner.py`。
- 当:用 `grep` 检查。
- 那么:含 `BacktestRunner.run(` 调用语句,传入 `strategy_cls`, `config`, `start_date`, `end_date`, `initial_cash`。
- 断言:`all(arg in runner_text for arg in ["BacktestRunner.run(", "strategy_cls", "config", "start_date", "end_date", "initial_cash"])`。

### AC-4

AC-FR0500-04

- 给定:重写后的 `runner.py`。
- 当:用 `inspect.getsource` 检查 `run_backtest` 函数。
- 那么:函数签名 `run_backtest(model_version: str, strategy_name: str, start: date, end: date, capital: float, config: dict | None = None) -> BacktestResult` 与 v0.1.0 一致(下游零改动)。
- 断言:`inspect.signature(run_backtest).parameters.keys() == {"model_version", "strategy_name", "start", "end", "capital", "config"}`。

### AC-5

AC-FR0500-05

- 给定:`BacktestResult` dataclass。
- 当:用 `inspect` 检查。
- 那么:字段签名 `{summary: dict, positions: pl.DataFrame, trades: pl.DataFrame, nav: pl.DataFrame, report_dir: Path}` 与 v0.2.0 一致(供现有调用方使用)。
- 断言:`{f.name for f in fields(BacktestResult)} == {"summary", "positions", "trades", "nav", "report_dir"}`。

### AC-6

AC-FR0500-06

- 给定:重写后的 `runner.py`。
- 当:用 `grep` 检查。
- 那么:**不**直接 `import quantide`(经 compat shim 解析,见 NFR-0200)。
- 断言:`"import quantide" not in runner_text`。

### AC-7

AC-FR0500-07

- 给定:`store_path` / `calendar_store_path` 默认值。
- 当:读取 `run_backtest` 内部默认值定义。
- 那么:默认指向 `tests/fixtures/v0.3.0/daily_bars_store/` 与 `tests/fixtures/v0.3.0/calendar_store/`。
- 断言:`"tests/fixtures/v0.3.0/daily_bars_store" in runner_text and "tests/fixtures/v0.3.0/calendar_store" in runner_text`。

### AC-8

AC-FR0500-08

- 给定:`store_path` / `calendar_store_path` 通过 `config` 覆盖。
- 当:调用 `run_backtest(..., config={"store_path": "/tmp/x", "calendar_store_path": "/tmp/y"})`。
- 那么:`BacktestRunner.run` 收到的 store 路径为 `/tmp/x` 与 `/tmp/y`(而非默认 fixture 路径)。
- 断言:用 mock 验证 `daily_bars.connect.call_args == call("/tmp/x", "/tmp/y")`。

---

<a id="ac-fr-0600"></a>
## FR-0600 CLI 表面与输出 schema 兼容性

### AC-1

AC-FR0600-01

- 给定:CLI 命令 `trader-off backtest --model v1 --strategy lgbm_top20 --start 2023-01-01 --end 2023-12-31 --capital 1000000`。
- 当:执行。
- 那么:进程退出码 0,stdout 含 "Backtest finished"(继承 v0.1.0 FR-1100 AC-1)。
- 断言:`subprocess.run(["uv", "run", "trader-off", "backtest", ...]).returncode == 0 and "Backtest finished" in result.stdout`。

### AC-2

AC-FR0600-02

- 给定:同 AC-1 场景,回测完成后。
- 当:检查 `reports/backtest_<ts>/`。
- 那么:含 `summary.json, nav_<ts>.parquet, positions_<ts>.parquet, trades_<ts>.parquet` 四个文件,每个文件非空(parquet 行数 > 0)(继承 v0.1.0 FR-1100 AC-2)。
- 断言:`all(f.exists() for f in [report_dir/"summary.json", report_dir/f"nav_{ts}.parquet", report_dir/f"positions_{ts}.parquet", report_dir/f"trades_{ts}.parquet"]) and len(pl.read_parquet(...)) > 0`。

### AC-3

AC-FR0600-03

- 给定:CLI 命令缺少 `--capital` 参数。
- 当:执行。
- 那么:argparse 退出码 2,stderr 含 "capital" 或 "--capital" 错误信息(继承 v0.1.0 FR-1100 AC-3)。
- 断言:`result.returncode == 2 and ("capital" in result.stderr or "--capital" in result.stderr)`。

### AC-4

AC-FR0600-04

- 给定:CLI 命令 `--config /nonexistent.yaml`。
- 当:执行。
- 那么:pydantic 校验或文件加载失败,退出码 4,stderr 含 "config" 或 "validation" 错误信息。
- 断言:`result.returncode == 4 and ("config" in result.stderr.lower() or "validation" in result.stderr.lower())`。

### AC-5

AC-FR0600-05

- 给定:CLI 命令合法但回测引擎失败(如 `daily_bars.connect` 抛 `FileNotFoundError`)。
- 当:执行。
- 那么:退出码 5,stderr 含 "BacktestRunner" 或 "daily_bars" 错误信息(FR-0500 + 错误传播)。
- 断言:`result.returncode == 5 and ("BacktestRunner" in result.stderr or "daily_bars" in result.stderr)`。

### AC-6

AC-FR0600-06

- 给定:`summary.json` 内容。
- 当:解析为 dict。
- 那么:含 6 个 v0.1.0 必需键:`annualized_return, sharpe_ratio, max_drawdown, win_rate, total_trades, avg_turnover`。
- 断言:`required_6_keys = {"annualized_return", "sharpe_ratio", "max_drawdown", "win_rate", "total_trades", "avg_turnover"}; required_6_keys.issubset(set(summary.keys()))`。

### AC-7

AC-FR0600-07

- 给定:`summary.json` 内容。
- 当:检查类型。
- 那么:`annualized_return, sharpe_ratio, max_drawdown, win_rate, avg_turnover` 为 `float`;`total_trades` 为 `int`(继承 v0.1.0 FR-1200 AC-1)。
- 断言:`isinstance(summary["annualized_return"], float) and isinstance(summary["total_trades"], int) and all(isinstance(summary[k], float) for k in ["sharpe_ratio", "max_drawdown", "win_rate", "avg_turnover"])`。

### AC-8

AC-FR0600-08

- 给定:`summary.json` 内容(quantide 真实回测输出)。
- 当:检查可选键。
- 那么:可选键 `sortino, drawdown_duration_days, benchmark_return` 至少存在 1 个(`is not None`),其他缺失即 `None`。
- 断言:`any(summary.get(k) is not None for k in ["sortino", "drawdown_duration_days", "benchmark_return"])`。

### AC-9

AC-FR0600-09

- 给定:v0.1.0 e2e 测试断言(如 `tests/integration/test_backtest_cli.py::test_metrics_integration`)。
- 当:v0.3.0 升级后运行。
- 那么:断言零修改即可通过(`summary` 含 6 必需键 + 类型正确)。
- 断言:运行 `uv run pytest tests/integration/test_backtest_cli.py -v` 全绿,该测试文件零修改。

---

<a id="ac-fr-0700"></a>
## FR-0700 测试断言升级 — 从「文件存在」到「指标数值合理」

### AC-1

AC-FR0700-01

- 给定:`tests/unit/backtest/test_runner.py::TestRunBacktest::test_output_files`。
- 当:重写后运行。
- 那么:在原有断言(文件存在 + 6 键 + parquet 行数 > 0)基础上,新增断言:
  - `result.summary["total_trades"] > 0`
  - `result.summary["avg_turnover"] > 0.0`
  - `math.isfinite(result.summary["annualized_return"]) == True`
  - `result.summary["max_drawdown"] <= 0.0`
- 断言:测试函数体含上述 4 行 `assert` 语句。

### AC-2

AC-FR0700-02

- 给定:`tests/unit/backtest/test_metrics.py::TestComputePerformanceMetrics::test_keys`。
- 当:升级后运行(通过 mock bills 传入真实 `total_trades > 0` 数据)。
- 那么:在原有断言(6 键 + 类型)基础上,新增断言:`result["total_trades"] > 0` 与 `result["avg_turnover"] > 0.0`。
- 断言:测试函数体含上述 2 行 assert 语句(在 mock 或 fixture 支持下)。

### AC-3

AC-FR0700-03

- 给定:`tests/integration/test_backtest_cli.py::test_metrics_integration`。
- 当:升级后运行(走真实 `run_backtest` → 真实 `BacktestRunner.run`)。
- 那么:在原有断言(类型正确 + win_rate ∈ [0,1] + max_drawdown ≤ 0)基础上,新增断言:`summary["total_trades"] > 0` 与 `summary["avg_turnover"] > 0.0`。
- 断言:测试函数体含上述 2 行 assert 语句。

### AC-4

AC-FR0700-04

- 给定:`tests/e2e/test_full_pipeline_e2e.py::test_full_pipeline_*`(任意 test_full_pipeline_* 用例)。
- 当:v0.3.0 升级后运行。
- 那么:断言 `summary.json["sortino"] is not None`(真实回测含 sortino 字段)+ 端到端 wall time ≤ 600s(NFR-0500)。
- 断言:`test_full_pipeline_e2e.py` 中至少 1 个 test_full_pipeline_* 用例含 `"sortino" in summary` 断言,且 e2e 总耗时 < 600s。

### AC-5

AC-FR0700-05

- 给定:v0.1.0 / v0.2.0 全部测试文件。
- 当:v0.3.0 升级后运行 `uv run pytest tests/unit tests/integration tests/e2e -v`。
- 那么:**无**已删除的旧断言(原断言全部保留),仅增量添加新断言。
- 断言:`pytest` 输出 0 个 `removed` / `deprecated` warning;既有断言文件 diff 显示**仅**新增行,无删除行。

---

<a id="ac-fr-0800"></a>
## FR-0800 metrics.py 委托给 quantide.service.metrics

### AC-1

AC-FR0800-01

- 给定:`src/trader_off/backtest/metrics.py` 在 v0.3.0 重写后。
- 当:用 `grep` 检查。
- 那么:文件**不**含 `total_trades = 0` 或 `avg_turnover = 0.0` 硬编码行(原 66-68 行已删除)。
- 断言:`"total_trades = 0" not in metrics_text and "avg_turnover = 0.0" not in metrics_text`。

### AC-2

AC-FR0800-02

- 给定:重写后的 `metrics.py`。
- 当:用 `grep` 检查。
- 那么:含 `quantide.service.metrics` 导入或函数调用语句。
- 断言:`"quantide.service.metrics" in metrics_text or "from quantide.service.metrics" in metrics_text or "import quantide.service.metrics" in metrics_text`。

### AC-3

AC-FR0800-03

- 给定:`compute_performance_metrics(nav_df)` 调用。
- 当:委托路径生效后,传入 252 日真实 NAV DataFrame + 真实 bills(由 `run_backtest` 收集)。
- 那么:返回 dict 含 6 个 v0.1.0 必需键 + 新增可选键(`sortino` 等)。
- 断言:`set(result.keys()) >= {"annualized_return", "sharpe_ratio", "max_drawdown", "win_rate", "total_trades", "avg_turnover"} and "sortino" in result.keys()`。

### AC-4

AC-FR0800-04

- 给定:`compute_performance_metrics(nav_df)` 调用,nav_df 长度 < 30。
- 当:执行。
- 那么:抛 `InsufficientDataError`,message 含 "30" 或 "need at least"(继承 v0.1.0 FR-1200 AC-3)。
- 断言:`pytest.raises(InsufficientDataError, match="30|need at least")`。

### AC-5

AC-FR0800-05

- 给定:`compute_performance_metrics(nav_df)` 调用,`nav_df` 含 NaN/Inf。
- 当:执行。
- 那么:委托给 quantide 后,quantide 内部抛异常 → `metrics.py` 包装为 `RuntimeError`,message 含 quantide traceback 前 3 行。
- 断言:`pytest.raises(RuntimeError, match="quantide|metric computation failed")`。

### AC-6

AC-FR0800-06

- 给定:`compute_performance_metrics` 调用真实 NAV(252 日,从 `run_backtest` 收集)。
- 当:执行。
- 那么:`result["total_trades"] > 0` 且 `result["avg_turnover"] > 0.0`(真实来自 `BacktestBroker.bills()`,非硬编码 0)。
- 断言:`result["total_trades"] > 0 and result["avg_turnover"] > 0.0`。

---

<a id="ac-fr-0900"></a>
## FR-0900 compute_metrics() 公开签名保持不变

### AC-1

AC-FR0900-01

- 给定:`compute_performance_metrics` 函数。
- 当:用 `inspect.signature` 检查。
- 那么:参数列表 `(*, nav_df: pl.DataFrame)` 或 `(nav_df: pl.DataFrame)`,无新增必填参数。
- 断言:`list(inspect.signature(compute_performance_metrics).parameters.keys()) in (["nav_df"],) or "nav_df" in inspect.signature(compute_performance_metrics).parameters`。

### AC-2

AC-FR0900-02

- 给定:从 `evaluation/`、`visualization/`、`tests/unit/backtest/test_metrics.py`、`tests/integration/test_backtest_cli.py` 的 import 语句。
- 当:grep 检查 `from trader_off.backtest.metrics import`。
- 那么:仅导入 `compute_performance_metrics` 一个公开函数,无新增公开符号。
- 断言:`set(re.findall(r"from trader_off.backtest.metrics import (\\w+)", source_text)) == {"compute_performance_metrics"}`。

### AC-3

AC-FR0900-03

- 给定:6 个 v0.1.0 必需键集合。
- 当:调用 `compute_performance_metrics(nav_df)` 并检查返回 dict 的 keys。
- 那么:必需键集合**完整保留**(`issubset`),可选键可额外存在(`set(result.keys()) >= required_6_keys`)。
- 断言:`required_6_keys.issubset(set(result.keys()))`。

### AC-4

AC-FR0900-04

- 给定:`compute_performance_metrics(nav_df)` 返回值。
- 当:检查类型。
- 那么:`annualized_return, sharpe_ratio, max_drawdown, win_rate, avg_turnover` 为 float;`total_trades` 为 int(继承 v0.1.0 FR-1200 AC-1)。
- 断言:同 FR-0600 AC-7。

### AC-5

AC-FR0900-05

- 给定:下游模块 `trader_off.evaluation` / `trader_off.visualization` 在 v0.3.0 升级前后。
- 当:git diff 检查 `src/trader_off/evaluation/` 与 `src/trader_off/visualization/`。
- 那么:diff 输出为空(下游零改动)。
- 断言:`subprocess.run(["git", "diff", "--", "src/trader_off/evaluation/", "src/trader_off/visualization/"]).stdout == ""`。

### AC-6

AC-FR0900-06

- 给定:`tests/integration/test_backtest_cli.py::test_metrics_integration` 在 v0.3.0 升级前后。
- 当:git diff 检查该文件。
- 那么:diff 输出为空(测试零改动,继承 v0.2.0 既有断言)。
- 断言:`subprocess.run(["git", "diff", "--", "tests/integration/test_backtest_cli.py"]).stdout == ""`(FR-0700 增量的新断言单独 commit,本 AC 关注"既有断言零修改"语义)。

---

<a id="ac-nfr-0100"></a>
## NFR-0100 调度器隔离 (继承 v0.2.0 AC-FR1500-04)

### AC-1

AC-NFR0100-01

- 给定:`src/trader_off/scheduler/` 目录下的所有 `.py` 文件。
- 当:用 `grep -rn "quantide\|millionaire"` 检查。
- 那么:**不**出现任何 `import quantide` 或 `from quantide` 语句。
- 断言:`not any("import quantide" in f.read_text() or "from quantide" in f.read_text() for f in Path("src/trader_off/scheduler/").rglob("*.py"))`。

### AC-2

AC-NFR0100-02

- 给定:v0.2.0 测试 `tests/integration/test_scheduler_resilience.py` 或 `test_retrain_full.py` 中关于 scheduler 隔离的断言。
- 当:v0.3.0 升级后运行。
- 那么:断言继续通过(零修改测试文件)。
- 断言:`uv run pytest tests/integration/test_scheduler_resilience.py -v` 全绿,无 `FAILED`。

### AC-3

AC-NFR0100-03

- 给定:v0.3.0 修改的文件列表。
- 当:git diff 检查。
- 那么:仅修改 `src/trader_off/backtest/{runner,metrics}.py` 与新增 `scripts/{convert_fixture_to_quantide,generate_calendar}.py`,scheduler 路径零修改。
- 断言:`subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD"]).stdout.splitlines()` 与上述列表一致(或子集)。

---

<a id="ac-nfr-0200"></a>
## NFR-0200 Compat shim 模式保留 (trader-off 不直接 import quantide)

### AC-1

AC-NFR0200-01

- 给定:`src/trader_off/backtest/runner.py`、`src/trader_off/backtest/metrics.py`、`src/trader_off/strategies/lgbm_top20.py`、`src/trader_off/strategies/optimized_topk.py`。
- 当:grep `import quantide` 检查。
- 那么:这 4 个文件**均不**直接 `import quantide`(仅 compat.py 内允许)。
- 断言:`all("import quantide" not in f.read_text() for f in [runner, metrics, lgbm_top20, optimized_topk])`。

### AC-2

AC-NFR0200-02

- 给定:`trader_off.strategies.compat` 模块。
- 当:在 quantide 已装环境下 import。
- 那么:`from quantide.core.strategy import BaseStrategy` 在 compat.py `try` 块内成功执行,`BaseStrategy_compat` 指向真实 quantide 类。
- 断言:`trader_off.strategies.compat.BaseStrategy is __import__("quantide.core.strategy", fromlist=["BaseStrategy"]).BaseStrategy`。

### AC-3

AC-NFR0200-03

- 给定:`trader_off.strategies.compat` 模块在 quantide 未装环境(stub fallback)。
- 当:`import quantide` 抛 `ImportError`。
- 那么:compat.py 自动 fallback 到本地 stub `BaseStrategy` 类(抽象方法签名与 quantide 一致)。
- 断言:`hasattr(trader_off.strategies.compat.BaseStrategy, "init") and hasattr(trader_off.strategies.compat.BaseStrategy, "on_day_open") and hasattr(trader_off.strategies.compat.BaseStrategy, "on_bar") and hasattr(trader_off.strategies.compat.BaseStrategy, "on_day_close") and hasattr(trader_off.strategies.compat.BaseStrategy, "on_stop")`。

---

<a id="ac-nfr-0300"></a>
## NFR-0300 weights.csv 解耦保留 (OptimizedTopKStrategy)

### AC-1

AC-NFR0300-01

- 给定:`src/trader_off/strategies/optimized_topk.py` 在 v0.3.0 升级前后。
- 当:git diff 检查。
- 那么:diff 输出为空(策略零修改)。
- 断言:`subprocess.run(["git", "diff", "--", "src/trader_off/strategies/optimized_topk.py"]).stdout == ""`。

### AC-2

AC-NFR0300-02

- 给定:e2e 端到端测试 `tests/e2e/test_full_pipeline_e2e.py`,场景含 `OptimizedTopKStrategy` 通过新 `runner.py` 执行回测。
- 当:执行。
- 那么:`OptimizedTopKStrategy.init()` 仍读 `reports/portfolio_latest/weights.csv`,v0.2.0 AC-FR4200-02/04/05 行为不变。
- 断言:测试含 mock `Path("reports/portfolio_latest/weights.csv").exists()` 行为,且回测真实产出 NAV/positions/trades。

### AC-3

AC-NFR0300-03

- 给定:`run_backtest(..., config={"weights_path": "/tmp/weights.csv"})`。
- 当:执行。
- 那么:config 字典原样透传至 `BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, ...)`,OptimizedTopKStrategy 在 `init()` 中读取 `config["weights_path"]`。
- 断言:用 mock 验证 `BacktestRunner.run.call_args.kwargs["config"] == {"weights_path": "/tmp/weights.csv"}`。

---

<a id="ac-nfr-0400"></a>
## NFR-0400 向后兼容 — v0.1.0 + v0.2.0 AC 全绿

### AC-1

AC-NFR0400-01

- 给定:`uv run pytest tests/unit tests/integration tests/e2e -v`。
- 当:v0.3.0 升级后运行。
- 那么:退出码 0,无 `FAILED` 或 `ERROR`(继承 v0.1.0 + v0.2.0 全部断言)。
- 断言:`result.returncode == 0 and "FAILED" not in result.stdout and "ERROR" not in result.stdout`。

### AC-2

AC-NFR0400-02

- 给定:v0.1.0 FR-1100 AC-1/2/3 与 FR-1200 AC-1/2/3 对应的测试断言。
- 当:v0.3.0 升级后运行。
- 那么:断言全部通过(零修改)。
- 断言:`tests/integration/test_backtest_cli.py` 全绿(覆盖 FR-1100 + FR-1200 关键 AC)+ `tests/unit/backtest/test_metrics.py::test_insufficient_data` 全绿(覆盖 FR-1200 AC-3)。

### AC-3

AC-NFR0400-03

- 给定:v0.2.0 21 个 e2e/perf 测试。
- 当:v0.3.0 升级后运行 `uv run pytest tests/e2e tests/perf -m e2e -v`。
- 那么:退出码 0,21 个测试全绿。
- 断言:`result.returncode == 0 and result.stdout.count("PASSED") >= 21`。

### AC-4

AC-NFR0400-04

- 给定:v0.1.0 159 AC 与 v0.2.0 180 AC(含 e2e/perf)的总数。
- 当:v0.3.0 升级后。
- 那么:≥ 339 个旧断言全保留(v0.3.0 新增断言增量添加,不删旧断言)。
- 断言:`result.stdout.count("PASSED") + result.stdout.count("passed") >= 339`。

---

<a id="ac-nfr-0500"></a>
## NFR-0500 性能预算 (继承 v0.2.0 NFR-0100)

### AC-1

AC-NFR0500-01

- 给定:`tests/perf/test_perf_budget.py::TestBacktestPerf::test_backtest_under_600s`。
- 当:v0.3.0 升级后运行(用 50 资产 × 252 日 fixture)。
- 那么:测试通过,e2e wall time ≤ 600s。
- 断言:测试输出 `PASSED` 且 wall time < 600s(`time` 输出或测试内部断言)。

### AC-2

AC-NFR0500-02

- 给定:`tests/perf/test_perf_budget.py::TestPerfBudget::test_memory_under_16gb`(若存在)或类似内存监控测试。
- 当:v0.3.0 升级后运行。
- 那么:内存峰值 ≤ 16 GB。
- 断言:`psutil.Process().memory_info().rss / (1024**3) < 16` 或测试内部断言通过。

### AC-3

AC-NFR0500-03

- 给定:真实 quantide 回测(50 资产 × 252 日 fixture)。
- 当:计时(`time.time()` 前后差值)。
- 那么:wall time 应**显著小于** v0.1.0 的 `np.random` 合成分支耗时(无 Python 循环,通常快 2-5x)。
- 断言:`real_backtest_time < 300`(经验值,允许 50% 浮动)。

---

## 跨 FR 一致性验证

> 此章节为 Lex 阶段 2 审查参考,不计入 9 条 FR 的 AC 编号。

- **AC-coverage-01**:spec.md 中 FR-0100~0900 全部 9 条 FR 在本 acceptance.md 中均有对应章节(✅ 已覆盖)。
- **AC-coverage-02**:NFR-0100~0500 全部 5 条 NFR 在本 acceptance.md 中均有对应章节(✅ 已覆盖)。
- **AC-coverage-03**:每条 AC 用 EARS 格式(给定/当/那么/断言)描述,可被 pytest / subprocess / 文件 IO 断言(✅ 已检查)。
- **AC-coverage-04**:无 v0.1.0 / v0.2.0 已锁定 AC 的重复定义;新 AC 仅覆盖 v0.3.0 增量需求(✅ 已检查)。
