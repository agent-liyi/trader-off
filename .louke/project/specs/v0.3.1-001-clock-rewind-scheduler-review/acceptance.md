# v0.3.1 patch — ClockRewind fixture fix + scheduler decoupling review — Acceptance Criteria

- **Spec ID**: v0.3.1-001-clock-rewind-scheduler-review
- **Created**: 2026-07-21

> Central registry of acceptance criteria. spec.md only keeps FR/NFR requirement descriptions and metadata (testability/resolved/valid);
> detailed observable, assertable pass conditions live in this table.
>
> Numbering convention:
> - Within each FR/NFR unit, AC-N starts from 1 and increments sequentially; cannot be reused across units
> - Full AC reference: **AC-FRXXXX-YY** (4-digit FR + 2-digit AC sequence), consistent with test-plan/issue schema
>
> During Lex phase 1/2 review, verify: (1) this table exists; (2) every FR/NFR in spec.md has a corresponding section here; (3) each AC can be tested/asserted.

## FR-0100 ClockRewind fixture 修复 — 移除 2（自然 3）个 e2e skip

<a id="ac-fr-0100"></a>

### AC-1

AC-FR0100-01

- 给定：v0.3.0 spec `scripts/convert_fixture_to_quantide.py` 默认参数下，`tests/fixtures/v0.3.0/daily_bars_store/` 中 `ohlcv_10x60` fixture 起始日为 2024-01-02。
- 当：执行 `python scripts/convert_fixture_to_quantide.py --fixture ohlcv_10x60`（默认参数已被修改，使起始日前移至 2023-12-29 或更早）。
- 那么：`tests/fixtures/v0.3.0/daily_bars_store/` 中 `ohlcv_10x60` 对应分区的 `date` 列 `min()` ≤ `2023-12-29`。
- 断言：`polars.scan_parquet("tests/fixtures/v0.3.0/daily_bars_store/**/*.parquet").select(pl.col("date").min()).collect().item() <= datetime.date(2023, 12, 29)`。

### AC-2

AC-FR0100-02

- 给定：FR-0100 修复后的 `ohlcv_10x60` fixture（起始 ≤ 2023-12-29）。
- 当：调用 `quantide.service.calendar.Calendar.load(...)`（或 quantide 等价 API）后，再调 `calendar.day_shift(start_date, -1)`（其中 `start_date` 取自 fixture 的 `date.min()`）。
- 那么：`day_shift` 返回 `start_date - 1 day`（即 2023-12-28 或更早），与 `start_date` 不相等。
- 断言：`prev_day != start_date and prev_day == start_date - timedelta(days=1)`（具体 API 名称以 quantide 源码为准；M-FOUND 阶段核对）。

### AC-3

AC-FR0100-03

- 给定：`tests/e2e/test_real_backtest_e2e.py` 中 `test_run_backtest_real_summary_keys`（原 line 54-64）。
- 当：移除 `@pytest.mark.skip(...)` 装饰器后执行 `pytest tests/e2e/test_real_backtest_e2e.py::test_run_backtest_real_summary_keys -v`。
- 那么：测试通过（exit 0），断言 `BacktestResult.summary` 真实键齐全（`total_trades / sortino / drawdown_duration_days / benchmark_compare` 等来自 quantide 非 `np.random`）。
- 断言：`result.returncode == 0`，且测试函数体内部 `assert` 全通过（pytest 不报 `AssertionError`）。

### AC-4

AC-FR0100-04

- 给定：`tests/e2e/test_real_backtest_e2e.py` 中 `test_run_backtest_nav_curve_is_real`（原 line 158-165）。
- 当：移除 `@pytest.mark.skip(...)` 装饰器后执行。
- 那么：测试通过，断言 `BacktestResult.nav_curve` 来自 quantide（与 np.random.RandomState(42) 合成曲线不一致）。
- 断言：`result.returncode == 0`，且测试体内 `assert nav_curve != synthetic_curve`（synthetic_curve 由 v0.2.0 fixture 锚定的种子生成）成立。

### AC-5

AC-FR0100-05

- 给定：`tests/e2e/test_real_backtest_e2e.py` 中 `test_run_backtest_with_custom_store_path`（原 line 269-277）。
- 当：移除 `@pytest.mark.skip(...)` 装饰器后执行（自然覆盖，per story §3.1 Avoid，同 ClockRewind 根因）。
- 那么：测试通过，断言 `run_backtest(config={"store_path": tmp_path})` 不抛 ClockRewind 异常，且能从自定义 store 路径读到 daily_bars。
- 断言：`result.returncode == 0`，且测试体内无 `pytest.fail` / `AssertionError`。

### AC-6

AC-FR0100-06

- 给定：`tests/e2e/test_real_backtest_e2e.py` 中上述 3 个测试。
- 当：执行 `pytest tests/e2e/test_real_backtest_e2e.py -v`。
- 那么：退出码 0，9 passed / 0 skipped（不计 lgbm_top20+预训练模型那 7 个保留 v0.4.0 的 skip，e2e/perf 全局口径）。
- 断言：`result.returncode == 0 and "9 passed" in result.stdout and "0 skipped" in result.stdout.replace("7 skipped", "")`（或更严格的 collected/deselected 计数解析）。

### AC-7

AC-FR0100-07

- 给定：`scripts/convert_fixture_to_quantide.py` 源码。
- 当：用 `git diff` 或 `git log -p scripts/convert_fixture_to_quantide.py | grep` 检查。
- 那么：默认参数（或默认 `--start-date` / 默认 fixture 起始常量）已被修改为 ≤ `2023-12-29`；脚本 docstring 或 arg-help 中同步说明该默认值与 calendar 兼容性。
- 断言：`grep -n "2023-12-29\\|2023-12-28\\|2023-12-30" scripts/convert_fixture_to_quantide.py` 至少 1 个匹配（默认值或常量定义位置）。

### AC-8

AC-FR0100-08

- 给定：`history.md`（位于 `history/` 或 `.louke/project/` 下，按仓库实际位置）。
- 当：检查 v0.3.1 行（最新行）。
- 那么：v0.3.1 行说明本 patch 的 FR-0100 落地：fixture 起始前移、3 个 e2e unskip（`test_run_backtest_real_summary_keys` / `test_run_backtest_nav_curve_is_real` / `test_run_backtest_with_custom_store_path`）。
- 断言：`grep -n "v0.3.1" history.md | tail -1` 之后 30 行内含 "ClockRewind" + "unskip" 或等价表述。

---

## FR-0200 Scheduler decoupling migration — verdict (M) Migrate to `quantide.core.scheduler.SchedulerManager`

<a id="ac-fr-0200"></a>

### AC-1

AC-FR0200-01

- 给定：`.louke/project/decisions/v0.3.1-scheduler-review.md` 不存在。
- 当：M-FOUND/M-DEV 阶段完成决策文档。
- 那么：文件存在，篇幅 ≤ 1 页 markdown（约 200 行内），含三段证据：(a) `quantide.core.scheduler.SchedulerManager` 接口清单（`init/start/stop/add_job/add_listener` 5 个方法，以源码为准）；(b) `src/trader_off/scheduler/` 中原 apscheduler/croniter 调用清单（含文件:行号）；(c) 隔离承诺影响评估（函数级 lazy import 与模块顶层 import 的可测性 / 重构 / 静态分析差异）。
- 断言：`Path(".louke/project/decisions/v0.3.1-scheduler-review.md").exists() and Path(".louke/project/decisions/v0.3.1-scheduler-review.md").stat().st_size < 30_000`（粗略页面大小上界），且文档第一段含 "verdict = (M)" 或 "verdict=Migrate"。

### AC-2

AC-FR0200-02

- 给定：决策文档（AC-FR0200-01 落盘）。
- 当：grep "verdict" 关键词。
- 那么：明确 verdict = (M) Migrate，且无任何 (S)/(P) 段落冲突结论。
- 断言：`re.search(r"verdict\\s*[=:]\\s*\\(M\\)", content) is not None`。

### AC-3

AC-FR0200-03

- 给定：`src/trader_off/scheduler/` 模块文件。
- 当：`grep -rn "^import quantide\|^from quantide" src/trader_off/scheduler/`。
- 那么：无匹配（模块顶层零 `import quantide`）。
- 断言：命令输出为空（exit 1 即 grep no-match 语义），不含 `pyproject.toml` 行。

### AC-4

AC-FR0200-04

- 给定：`src/trader_off/scheduler/` 模块文件。
- 当：`grep -rn "quantide\\.\\(service\\|portfolio\\|data\\|backtest\\)" src/trader_off/scheduler/`。
- 那么：无匹配（无 quantide 业务符号 import）。
- 断言：命令输出为空。

### AC-5

AC-FR0200-05

- 给定：`src/trader_off/scheduler/` 模块文件。
- 当：`grep -rn "from quantide.core.scheduler" src/trader_off/scheduler/`。
- 那么：至少 1 个匹配，证明实际接入了 `SchedulerManager`。
- 断言：`result.stdout.strip() != ""`。

### AC-6

AC-FR0200-06

- 给定：`from quantide.core.scheduler` 的所有匹配行（AC-FR0200-05 输出）。
- 当：Python AST 校验（`ast.parse` + 遍历 `ast.ImportFrom`/`ast.Import`，确认每个匹配的 `import quantide.core.scheduler` 语句的祖先节点是 `FunctionDef`/`AsyncFunctionDef`）。
- 那么：全部位于函数体内，无模块顶层 / 类体 / `TYPE_CHECKING` 块内的 import。
- 断言：自定义 Python 脚本遍历：`for node in ast.walk(tree): if isinstance(node, ast.ImportFrom) and node.module == "quantide.core.scheduler": assert isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef))` 全部成立。

### AC-7

AC-FR0200-07

- 给定：`tests/integration/test_scheduler_resilience.py`（或新建文件 `tests/integration/test_scheduler_quantide_adapter.py`）。
- 当：执行 `pytest tests/integration -m integration -k "quantide or scheduler_manager" -v`。
- 那么：至少 1 条新 AC 通过 —— 验证 `SchedulerManager` 通过函数级 lazy import 被实例化（首次调用时 `quantide.core.scheduler` 模块被加载），且 `SchedulerManager.init()` / `add_job()` 调用栈中无模块顶层 import 副作用（可通过 `sys.modules` 检查或 `importlib.reload` 行为断言）。
- 断言：`result.returncode == 0 and "passed" in result.stdout`。

### AC-8

AC-FR0200-08

- 给定：`pyproject.toml`。
- 当：检查 `[project].dependencies` 或 `[tool.uv.sources]`。
- 那么：`quantide` 已通过 git URL 声明（v0.3.0 FR-0200 完成），无新增 / 删除。
- 断言：`grep -n "quantide" pyproject.toml` 至少 1 行（声明位置），且 git URL 与 v0.3.0 一致（`re.search(r"quantide\\s*=\\s*\\{.*git.*\\}", content)`）。

---

## NFR-0101 调度器隔离改写 — 函数级 lazy import + 零业务符号 (继承 v0.2.0 AC-FR1500-04，替代 v0.3.0 NFR-0100)

<a id="ac-nfr-0101"></a>

### AC-1

AC-NFR0101-01

- 给定：`src/trader_off/scheduler/` 下所有 `.py` 文件。
- 当：`grep -rn "^import quantide\\|^from quantide" src/trader_off/scheduler/`。
- 那么：无任何模块顶层 import。
- 断言：命令输出为空（exit 1）。

### AC-2

AC-NFR0101-02

- 给定：`src/trader_off/scheduler/` 下所有 `.py` 文件。
- 当：`grep -rn "quantide\\.\\(service\\|portfolio\\|data\\|backtest\\)" src/trader_off/scheduler/`。
- 那么：无任何 quantide 业务符号 import。
- 断言：命令输出为空。

### AC-3

AC-NFR0101-03

- 给定：`src/trader_off/scheduler/` 下所有 `.py` 文件。
- 当：Python AST 解析 + 收集所有 `ast.ImportFrom(module="quantide.core.scheduler")` 节点。
- 那么：每个节点的祖先链均含 `FunctionDef` 或 `AsyncFunctionDef`，无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 import。
- 断言：自定义脚本 `python scripts/check_scheduler_imports.py`（M-DEV 阶段新增）退出码 0。

---

## NFR-0200 Compat shim 模式保留 (trader-off 不直接 import quantide) — 继承 v0.3.0

<a id="ac-nfr-0200"></a>

### AC-1

AC-NFR0200-01

- 给定：`src/trader_off/backtest/` 与 `src/trader_off/strategies/lgbm_top20.py`、`src/trader_off/strategies/optimized_topk.py`。
- 当：`grep -rn "import quantide" src/trader_off/backtest/ src/trader_off/strategies/lgbm_top20.py src/trader_off/strategies/optimized_topk.py`。
- 那么：仅在 `src/trader_off/strategies/compat.py` 内出现 import 语句，其他路径无匹配。
- 断言：命令输出行数 = 1，且行内容来自 `compat.py`。

---

## No Acceptance

无（本 spec 所有 FR/NFR 均有 AC 覆盖）。
