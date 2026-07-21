# v0.4.0 — Quantide DataLoader Adapter — Acceptance Criteria

- **Spec ID**: v0.4.0-001-quantide-data-adapter
- **Created**: 2026-07-21

> Central registry of acceptance criteria. spec.md only keeps FR/NFR requirement descriptions and metadata (testability/resolved/valid);
> detailed observable, assertable pass conditions live in this table.
>
> Numbering convention:
> - Within each FR/NFR unit, AC-N starts from 1 and increments sequentially; cannot be reused across units
> - Full AC reference: **AC-FRXXXX-YY** (4-digit FR + 2-digit AC sequence), consistent with test-plan/issue schema
>
> AC format: EARS (Easy Approach to Requirements Syntax) — 给定/当/那么 + 可断言测试条件。
>
> During Lex phase 1/2 review, verify: (1) this table exists; (2) every FR/NFR in spec.md has a corresponding section here; (3) each AC can be tested/asserted.

<a id="ac-fr-0100"></a>
## FR-0100 Quantide DataLoader adapter — `QuantideDataLoader.get_daily` 桥接 `quantide.data.fetchers.tushare.fetch_bars`

### AC-1

AC-FR0100-01

- The system shall provide a public class `QuantideDataLoader` importable from `trader_off.data.quantide_adapter`.
- 断言：`from trader_off.data.quantide_adapter import QuantideDataLoader` 成功；`inspect.isclass(QuantideDataLoader)` 为 True；类未设置 `__all__`（仅默认公开）时 `dir(QuantideDataLoader)` 至少含 `get_daily`。

### AC-2

AC-FR0100-02

- The system shall expose `get_daily` as an `async` coroutine function with signature `(self, asset: str, end_date: date, count: int) -> pl.DataFrame`.
- 断言：`inspect.iscoroutinefunction(QuantideDataLoader.get_daily)` 为 True；`inspect.signature(QuantideDataLoader.get_daily).parameters` 含 `self / asset / end_date / count` 四个参数，`asset` / `end_date` / `count` 无默认值，`count` 参数类型注解为 `int`（允许 `int` 子类）。

### AC-3

AC-FR0100-03

- When `get_daily` is invoked, the system shall call `quantide.data.fetchers.tushare.fetch_bars` exactly once with a list of `datetime.date` values derived from `(end_date, count)`.
- 给定：mock `quantide.data.fetchers.tushare.fetch_bars`（用 `monkeypatch.setattr` 或 `unittest.mock.patch` 在首次函数体执行时拦截，因为 import 是函数级的）。
- 当：`await QuantideDataLoader().get_daily("000001.SZ", date(2024, 6, 30), 10)`。
- 那么：`mock_fetch_bars.call_count == 1`；`mock_fetch_bars.call_args.args[0]` 是 `Iterable[datetime.date]`，长度 ≥ `count`（含 `end_date`），每个元素为 `datetime.date` 实例；元素最大值 ≥ `date(2024, 6, 30)`（含端点）。

### AC-4

AC-FR0100-04

- When `fetch_bars` returns a `(pd.DataFrame, errors)` tuple, the system shall convert the DataFrame to `pl.DataFrame` with schema `{asset: Utf8, date: Date, open: Float64, high: Float64, low: Float64, close: Float64, volume: Float64, turnover: Float64, adj_factor: Float64}`.
- 给定：mock `fetch_bars` 返回 `pd.DataFrame({...})` 与空 `errors=[]`，至少含 `asset` / `date` / `open` / `high` / `low` / `close` / `volume` / `turnover` / `adj_factor` 列。
- 当：`await adapter.get_daily("000001.SZ", date(2024, 6, 30), 10)`。
- 那么：返回值 `isinstance(result, pl.DataFrame)` 为 True；`result.schema` 等价于上述 schema；列名按 `ts_code → asset`、`trade_date → date`、`vol → volume` 重命名（mock 输入可用 `ts_code` / `trade_date` / `vol` 验证重命名正确）。

### AC-5

AC-FR0100-05

- When `fetch_bars` returns rows for multiple assets, the system shall filter the result to only rows where `asset == <input asset>`.
- 给定：mock `fetch_bars` 返回 3 行：`asset ∈ {"000001.SZ", "000002.SZ", "000001.SZ"}`，其他列合法。
- 当：`await adapter.get_daily("000001.SZ", date(2024, 6, 30), 10)`。
- 那么：`result.filter(pl.col("asset") == "000001.SZ").height == result.height == 2`；`result.filter(pl.col("asset") == "000002.SZ").height == 0`。

### AC-6

AC-FR0100-06

- When `fetch_bars` returns more than `count` rows for the target asset, the system shall limit the returned DataFrame to at most `count` rows.
- 给定：mock `fetch_bars` 返回 20 行（全部 `asset == "000001.SZ"`）。
- 当：`await adapter.get_daily("000001.SZ", date(2024, 6, 30), 5)`。
- 那么：`result.height <= 5`。

### AC-7

AC-FR0100-07

- When `fetch_bars` returns an empty DataFrame or zero rows for the target asset, the system shall return a `pl.DataFrame` (possibly empty) with the canonical schema; the system shall not raise.
- 给定：mock `fetch_bars` 返回 `(pd.DataFrame(), [])`（0 行）。
- 当：`await adapter.get_daily("000001.SZ", date(2024, 6, 30), 10)`。
- 那么：不抛任何异常；返回 `pl.DataFrame` 实例；`result.height == 0`；`result.schema` 与 AC-4 等价（空 DataFrame 仍含列定义）。

### AC-8

AC-FR0100-08

- When `fetch_bars` returns non-empty `errors` list, the system shall emit at least one `loguru.logger.warning` record (or equivalent structured warning) and shall not raise.
- 给定：mock `fetch_bars` 返回 `(pd.DataFrame(), [[..., date(2024,6,30), "fetch failed"]])`（含 1 条错误）。
- 当：`await adapter.get_daily("000001.SZ", date(2024, 6, 30), 10)`。
- 那么：不抛任何异常；返回 `pl.DataFrame`（可能空）；`loguru` sink 中至少 1 条 `WARNING` 级别日志，message 含 `"fetch"` 或 `errors` 内容关键字。

### AC-9

AC-FR0100-09

- When `QuantideDataLoader` is injected as the `fetcher` argument to `DataLoader`, the existing `DataLoader.get_history(asset, end_date, count)` call shall succeed without modification to `DataLoader` itself.
- 给定：未修改 `src/trader_off/data/loader.py`；mock `quantide.data.fetchers.tushare.fetch_bars`。
- 当：`loader = DataLoader(fetcher=QuantideDataLoader())`；`result = await loader.get_history("000001.SZ", date(2024, 6, 30), 10)`。
- 那么：`isinstance(result, pl.DataFrame)` 为 True；`loader._fetcher is not None` 走通 fetcher 分支；`loader.get_history` 不调用缺省 warning 分支。

### AC-10

AC-FR0100-10

- Unit tests covering AC-1 through AC-9 shall pass: `uv run pytest tests/unit/data/test_quantide_adapter.py -v` exits with code 0, ≥ 9 tests passing, 0 failed, 0 errored.
- 断言：`subprocess.run(["uv", "run", "pytest", "tests/unit/data/test_quantide_adapter.py", "-v"], check=True).returncode == 0`；`result.stdout` 包含 `"passed"` 且不含 `"failed"` / `"error"` 关键词。

---

<a id="ac-nfr-0100"></a>
## NFR-0100 `quantide_adapter` 模块顶层零 `import quantide` — 函数级 lazy import + 数据 fetcher 业务符号白名单

### AC-1

AC-NFR0100-01

- The system shall keep `src/trader_off/data/quantide_adapter.py` module top-level (lines before first `def`/`async def`, including `import`/`from` blocks, class body, `__init__`, `if TYPE_CHECKING`) free of any `import quantide` or `from quantide ...` statement.
- 断言：命令行 `grep -nE "^(import quantide|from quantide)" src/trader_off/data/quantide_adapter.py` 输出为空（grep exit 1 / no-match）。

### AC-2

AC-NFR0100-02

- The system shall keep `quantide_adapter.py` free of non-whitelisted `quantide.<business_module>` references (service / portfolio / backtest / core.scheduler).
- 断言：`grep -nE "quantide\.(service|portfolio|backtest|core\.scheduler)" src/trader_off/data/quantide_adapter.py` 输出为空（whitelist 仅放行 `quantide.data.fetchers.*`，其余业务符号继续禁止）。

### AC-3

AC-NFR0100-03

- When the file is parsed, the system shall contain at least one `import quantide.*` or `from quantide.*` statement inside a function body (proving actual quantide reachability via lazy import).
- 断言：`grep -nE "from quantide|import quantide" src/trader_off/data/quantide_adapter.py` 至少 1 行匹配（行号 > 第一条 `def`/`async def` 起始行）。

### AC-4

AC-NFR0100-04

- When Python AST validation is applied to `quantide_adapter.py`, all `Import` / `ImportFrom` nodes whose module string starts with `"quantide"` shall have an ancestor node of type `FunctionDef` or `AsyncFunctionDef`; no module-top-level / class-body / `if TYPE_CHECKING` quantide imports shall exist.
- 断言：自定义校验脚本（位于 `tests/unit/data/test_quantide_adapter.py` 或独立 `scripts/check_quantide_adapter_imports.py`）：
  ```python
  import ast
  tree = ast.parse(open("src/trader_off/data/quantide_adapter.py").read())
  for node in ast.walk(tree):
      if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("quantide"):
          assert any(isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)) for a in ast.walk(tree) if getattr(a, "body", None) and node in getattr(a, "body", []) or ...)
      if isinstance(node, ast.Import):
          for alias in node.names:
              if alias.name.startswith("quantide"):
                  assert ...
  ```
  校验脚本执行 `exit 0`，无 `AssertionError`。

### AC-5

AC-NFR0100-05

- When importing `trader_off.data.quantide_adapter` without ever calling `get_daily`, the system shall not trigger any `quantide` module import side-effect (proving the import is genuinely lazy).
- 断言：测试用例 `test_module_top_level_no_quantide_side_effect`：
  ```python
  import sys
  sys.modules.pop("quantide.data.fetchers.tushare", None)
  import trader_off.data.quantide_adapter
  assert "quantide.data.fetchers.tushare" not in sys.modules
  ```
  通过。

### AC-6

AC-NFR0100-06

- When other modules under `src/trader_off/data/` are scanned, no module-top-level `import quantide` / `from quantide` shall exist (preserving compat shim isolation from v0.3.0 NFR-0200).
- 断言：`grep -rnE "^(import quantide|from quantide)" src/trader_off/data/` 仅匹配 `src/trader_off/data/quantide_adapter.py` 内位于函数体内的行（line number > 第一个 `def`/`async def` 行号），其他文件无匹配。

---

## No Acceptance

无（本 spec 所有 FR/NFR 均有 AC 覆盖）。
