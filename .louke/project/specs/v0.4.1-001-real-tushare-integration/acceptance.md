# v0.4.1 — QuantideDataLoader 真数据接入 + Smoke Test — Acceptance Criteria

- **Spec ID**: v0.4.1-001-real-tushare-integration
- **Created**: 2026-07-21
- **继承基线**: v0.4.0 FR-0100 / NFR-0100 的 AC 在本文件中**不重复**;v0.4.0 行 63 "不实例化 TushareFetcher / 不用 TUSHARE_TOKEN / 不发网络 IO" 在 v0.4.1 显式反转(见本 spec FR-0100 与 AC 描述)。本文件仅定义 v0.4.1 新增 / 反转的 FR / NFR 的 AC。

> 中央注册表:spec.md 只保留 FR/NFR 描述与元数据 (testability/decided/valid);可观察、可断言的通过条件在本表中。
>
> 编号约定:
> - 每个 FR/NFR 单元内 AC-N 从 1 起,按顺序递增;单元之间不复用
> - 完整 AC 引用:**AC-FRXXXX-YY** (4 位 FR + 2 位 AC 序号),与 test-plan / issue schema 保持一致
> - 标题层级:`## FR-XXXX {title}` 为 level-2;`### AC-N` 为 level-3(其后同一行**不**接任何文字,canonical ID 写在下一行)
>
> Lex 阶段 1/2 审查验证: (1) 本表存在; (2) spec.md 每个 FR/NFR 在本表中有对应章节; (3) 每条 AC 可被测试或断言。
>
> EARS 句式关键词约定:`WHEN` (触发条件) / `WHILE` (持续状态) / `WHERE` (前置条件) / `IF ... THEN` (条件分支) / `THE 系统 SHALL ...` (系统行为)。

---

<a id="ac-fr-0100"></a>
## FR-0100 QuantideDataLoader 真数据接入 — TushareFetcher 实例化 + Calendar 替换 pandas.bdate_range

### AC-1

AC-FR0100-01

- **WHEN** `QuantideDataLoader(token=None)` AND env `TUSHARE_TOKEN` 未设置
- **THEN** 系统 SHALL 抛 `RuntimeError("TUSHARE_TOKEN environment variable is required for QuantideDataLoader; set it before running smoke tests")` 且不发起任何网络 IO
- **断言**:
  - 给定:`os.environ` 中无 `TUSHARE_TOKEN`。
  - 当:`QuantideDataLoader()` 实例化。
  - 那么:`pytest.raises(RuntimeError, match="TUSHARE_TOKEN environment variable is required for QuantideDataLoader")`,且无 `quantide.*` 网络调用(可用 `unittest.mock.patch("quantide.data.fetchers.tushare.TushareFetcher")` 验证未触发)。
- **对应 EARS**: Story §2.4 AC-01。

### AC-2

AC-FR0100-02

- **WHEN** env `TUSHARE_TOKEN` 已设置
- **THEN** 系统 SHALL 在 `get_daily` 函数体内 lazy import `quantide.data.fetchers.tushare.TushareFetcher`,实例化 `TushareFetcher(token=<env_value>)`,调 `fetcher.fetch_calendar(epoch)` 获取交易日锚点,再用 `quantide.data.models.calendar.Calendar.get_frames_by_count(end_date, count, FrameType.DAY)` 反推最近 `count` 个真实交易日(CN 假期自动剔除)
- **断言**:
  - 给定:`os.environ['TUSHARE_TOKEN'] = "fake-token-for-test"`。
  - 当:`loader = QuantideDataLoader()` 实例化 → `loader.get_daily("000001.SZ", date(2024, 1, 31), count=60)` 调用,内部 mock `TushareFetcher` / `Calendar.get_frames_by_count`。
  - 那么:实例化时 `TushareFetcher(token="fake-token-for-test")` 收到调用且**仅**调用一次;`Calendar.get_frames_by_count(date(2024, 1, 31), 60, FrameType.DAY)` 收到调用且**仅**调用一次。
- **对应 EARS**: Story §2.4 AC-02。

### AC-3

AC-FR0100-03

- **WHILE** 反推交易日
- **THEN** 系统 SHALL 不再调用 `pandas.bdate_range`(完全移除 `_compute_trade_dates` 中的 `pd.bdate_range` 路径,防止双路径漂移)
- **断言**:
  - 给定:`quantide_adapter.py` 源码。
  - 当:`grep -rn "bdate_range" src/trader_off/data/quantide_adapter.py` 执行。
  - 那么:无匹配(返回码非 0,stdout 为空)。同时 AST 解析该文件,无 `pd.bdate_range` 调用节点。
  - 函数 `_compute_trade_dates` 应被替换或重命名为 `_compute_real_trade_dates`,内部仅调 `Calendar.get_frames_by_count`。
- **对应 EARS**: Story §2.4 AC-03。

### AC-4

AC-FR0100-04

- **WHEN** 真实交易日列表就绪
- **THEN** 系统 SHALL 调用 `fetcher.fetch_bars(dates)`(TushareFetcher 实例方法,**非**模块级 `fetch_bars` 单独调用)并返回 polars OHLCV DataFrame,schema 与 v0.4.0 一致(`asset/date/open/high/low/close/volume/turnover/adj_factor`)
- **断言**:
  - 给定:`loader.get_daily("000001.SZ", date(2024, 1, 31), count=60)`,内部 mock `TushareFetcher` 返回固定 60 天 OHLCV fixture。
  - 当:调用链走通 `_compute_real_trade_dates` → `fetcher.fetch_bars(dates)` → `_to_polars_ohlcv`。
  - 那么:返回 `pl.DataFrame`,`height <= 60` 且 `height >= 1`;schema 严格为 `{asset: Utf8, date: Date, open: Float64, high: Float64, low: Float64, close: Float64, volume: Float64, turnover: Float64, adj_factor: Float64}`;列重命名 `ts_code → asset` / `trade_date → date` / `vol → volume` / `amount → turnover` 全部生效。
  - `fetcher.fetch_bars(dates)` 调用**至少** 1 次,参数 `dates` 长度 == `Calendar.get_frames_by_count` 返回交易日数(由 mock 控制)。
- **对应 EARS**: Story §2.4 AC-04。

### AC-5

AC-FR0100-05

- **WHEN** `QuantideDataLoader(token="explicit")` 显式传 token
- **THEN** 系统 SHALL 优先使用显式 token,**不**读 `os.environ`,且抛 `RuntimeError` 的行为**不**触发
- **断言**:
  - 给定:`os.environ` 中**无** `TUSHARE_TOKEN`(显式清空)。
  - 当:`loader = QuantideDataLoader(token="explicit-token")` 实例化。
  - 那么:不抛 `RuntimeError`,`loader._token == "explicit-token"`;后续 `get_daily` 调用传入 `TushareFetcher(token="explicit-token")`(mock 验证参数)。

### AC-6

AC-FR0100-06

- **WHEN** `quantide.data.fetchers.tushare.TushareFetcher` 实例化失败或 `fetch_bars` 抛异常
- **THEN** 系统 SHALL 通过 `loguru.logger.exception` / `logger.warning` 记录错误,且**不**向调用方(`DataLoader.get_history`)抛异常 —— 沿用 v0.4.0 `_fetch_bars_for_dates` 的 try/except + 返回空 DataFrame 行为
- **断言**:
  - 给定:`TushareFetcher` mock 在 `__init__` 抛 `RuntimeError("network down")`,**或** `fetch_bars` mock 抛异常。
  - 当:`loader.get_daily("000001.SZ", date(2024, 1, 31), count=60)` 调用。
  - 那么:`DataLoader.get_history` 接收到的 `pl.DataFrame` 为空 DataFrame(`height == 0`,schema 仍正确);`logger.exception` / `logger.warning` 被调用至少 1 次;`pytest.raises` 不命中(loader 不向上抛)。

---

<a id="ac-fr-0200"></a>
## FR-0200 End-to-end smoke test — 真 token 拉 3 stocks × 60 交易日 + 落 DailyBarsStore + BacktestRunner.run + NAV 非空

### AC-1

AC-FR0200-01

- **WHEN** smoke test 启动 AND env `TUSHARE_TOKEN` 缺失
- **THEN** 系统 SHALL `pytest.skip("TUSHARE_TOKEN not set; skipping real Tushare E2E")`,**不**抛 `RuntimeError`,**不**发起任何网络 IO
- **断言**:
  - 给定:`os.environ` 中无 `TUSHARE_TOKEN`。
  - 当:`pytest tests/smoke/test_real_tushare_smoke.py -v` 执行。
  - 那么:测试结果为 `1 skipped`,退出码 `0` 或 `5`(pytest 默认 skip 不算 fail);traceback 中**不**含 `RuntimeError` 字样。
- **对应 EARS**: Story §2.4 AC-05。

### AC-2

AC-FR0200-02

- **WHEN** smoke test 启动 AND env `TUSHARE_TOKEN` 存在
- **THEN** 系统 SHALL 拉 3 stocks (`000001.SZ` / `600519.SH` / `000858.SZ`) × 60 交易日 → 数据按 v0.3.0 `DailyBarsStore` schema 写入 `tmp_path/daily_bars_store/`(年分区 parquet) → `BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, start_date, end_date, initial_cash=100000)` → 断言 `result.nav.height > 0`
- **断言**:
  - 给定:`os.environ['TUSHARE_TOKEN']` 已设置,smoke test 用 `monkeypatch` 替换 `quantide.data.fetchers.tushare.TushareFetcher` 为 mock(返回 60 天 × 3 资产 OHLCV fixture),`Calendar.get_frames_by_count` 也 mock 返回 60 个交易日。
  - 当:smoke test 跑完整链路。
  - 那么:
    - 3 个资产的 `pl.DataFrame` 全部 `height >= 1`,schema 与 FR-0100 AC-4 一致;
    - `tmp_path/daily_bars_store/` 存在,含 `year=YYYY/part-0.parquet` 分区,schema `{date, asset, ohlc struct, volume, adj_factor}`;
    - `BacktestRunner.run(...)` 返回 `BacktestResult`,`result.nav.height > 0`,`result.nav.columns` 含 `date` / `nav`;
    - `result.positions.height >= 0`(允许 0 行,只要 nav 非空);
    - traceback / 日志中**不**含 `TUSHARE_TOKEN` 字面值。
- **对应 EARS**: Story §2.4 AC-06。

### AC-3

AC-FR0200-03

- **WHEN** CI 跑 smoke test(无 token,monkeypatch `TushareFetcher` 为 mock)
- **THEN** 系统 SHALL 走 mock `fetch_bars` 路径,产出固定 OHLCV fixture → 落 store → `BacktestRunner.run()` → 断言**全绿**(同 AC-2 的断言集)
- **断言**:
  - 给定:CI 环境无 token,smoke test 通过 fixture 提供 `monkeypatch.setattr("quantide.data.fetchers.tushare.TushareFetcher", MockTushareFetcher)`。
  - 当:`pytest tests/smoke/test_real_tushare_smoke.py -v` 在 CI 执行。
  - 那么:测试通过(无 `FAILED` / `ERROR`),断言覆盖与 AC-2 一致(`result.nav.height > 0` + 3 资产 × 60 天 fetch)。
  - mock 模式下 token 缺失走 `pytest.skip`(**不**强制注入占位符 token),mock 模式需显式注入占位符 token 时走 mock 路径(由 smoke 实现选择,AC 接受两种实现)。
- **对应 EARS**: Story §2.4 AC-05 (CI 分支)。

### AC-4

AC-FR0200-04

- **WHILE** smoke test 落盘产物输出
- **THEN** 系统 SHALL 落 `tests/smoke/output/` 目录且该目录已在 `.gitignore`,任何 parquet / 日志中**禁止 echo token 值**,`.env*` 已在 gitignore(继承 v0.4.0)
- **断言**:
  - 给定:`tests/smoke/output/` 目录。
  - 当:`grep -n "smoke/output" .gitignore` 执行。
  - 那么:返回至少 1 行匹配(`tests/smoke/output/` 在 gitignore 中)。
  - 当:跑 smoke test(monkeypatch mock 触发落盘)。
  - 那么:`tests/smoke/output/` 下所有文件内容经 `grep -r "TUSHARE_TOKEN="` / `grep -rE "token=[a-zA-Z0-9]{20,}"` 检查,无匹配(token 字面值不出现)。

### AC-5

AC-FR0200-05

- **WHEN** smoke test 用真 token 跑通
- **THEN** 系统 SHALL 在 `< 60s` 单次 fetch 内返回 60 天 × 1 资产 OHLCV(网络性能基线),且全部 3 资产 fetch 总耗时 `< 300s`(网络容许慢)
- **断言**:
  - 给定:真 `TUSHARE_TOKEN` + 网络可达。
  - 当:`time.monotonic()` 包裹 `loader.get_daily(asset, end_date, count=60)` 3 次调用。
  - 那么:单次 fetch elapsed `< 60s`,3 次总 elapsed `< 300s`。
  - 性能为 soft assertion(仅记录,不阻塞 smoke 通过);真实网络可能波动,故不作为 hard fail,只在 CI 报告里 warning。

---

<a id="ac-nfr-0100"></a>
## NFR-0100 函数级 lazy import — 白名单延伸至 `quantide.data.models.calendar.*` (继承 v0.4.0 NFR-0100)

### AC-1

AC-NFR0100-01

- **WHEN** 验证 `src/trader_off/data/quantide_adapter.py` 模块顶层
- **THEN** 系统 SHALL 无 `import quantide` / `from quantide ...` 语句(模块顶层零 quantide import)
- **断言**:
  - 给定:`src/trader_off/data/quantide_adapter.py` 源文件。
  - 当:`grep -rn "^import quantide\|^from quantide" src/trader_off/data/quantide_adapter.py` 执行(使用 `^` 锚定行首,过滤 import 行)。
  - 那么:无匹配(grep 退出码 `1`,stdout 为空)。该断言覆盖模块顶部 import 块、类体外、`if TYPE_CHECKING` 块。

### AC-2

AC-NFR0100-02

- **WHEN** 验证 `quantide_adapter.py` 函数体内 import
- **THEN** 系统 SHALL 至少 2 个 `from quantide ...` 匹配,证明实际接入了 `quantide.data.fetchers.tushare.TushareFetcher` 与 `quantide.data.models.calendar.Calendar, FrameType`
- **断言**:
  - 给定:`quantide_adapter.py` 源文件。
  - 当:`grep -rn "from quantide" src/trader_off/data/quantide_adapter.py` 执行(无 `^` 锚定,允许函数体内任意位置)。
  - 那么:至少 2 行匹配,内容分别包含 `from quantide.data.fetchers.tushare import TushareFetcher` 与 `from quantide.data.models.calendar import Calendar, FrameType`(允许顺序、import 风格小变)。

### AC-3

AC-NFR0100-03

- **WHEN** Python AST 解析 `quantide_adapter.py`
- **THEN** 系统 SHALL 验证所有 `quantide` 导入节点的祖先链含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 quantide import
- **断言**:
  - 给定:`ast.parse(Path("src/trader_off/data/quantide_adapter.py").read_text())` 后遍历 `ast.ImportFrom` / `ast.Import` 节点。
  - 当:对每个 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点,沿 `ast.walk` 反向追溯父节点(`ast.FunctionDef` / `ast.AsyncFunctionDef` / `ast.ClassDef` / `ast.If` 测试是否为 `TYPE_CHECKING`)。
  - 那么:**所有** quantide import 节点的最近函数祖先存在,且**不**位于 `if TYPE_CHECKING` 块内或类体内。断言失败若任一 import 出现在模块顶层 / 类体 / TYPE_CHECKING 块。

### AC-4

AC-NFR0100-04

- **WHEN** 验证 `quantide_adapter.py` 业务符号白名单边界
- **THEN** 系统 SHALL 无 `quantide.service.*` / `quantide.portfolio.*` / `quantide.backtest.*` / `quantide.core.scheduler.*` 的 import(白名单外模块零出现)
- **断言**:
  - 给定:`quantide_adapter.py` 源文件。
  - 当:`grep -rnE "quantide\.(service|portfolio|backtest|core\.scheduler)" src/trader_off/data/quantide_adapter.py` 执行。
  - 那么:无匹配(grep 退出码 `1`,stdout 为空)。白名单内仅允许 `quantide.data.fetchers.tushare.*` 与 `quantide.data.models.calendar.*`。

### AC-5

AC-NFR0100-05

- **WHEN** 验证 `src/trader_off/data/` 目录的集成层隔离
- **THEN** 系统 SHALL 除 `quantide_adapter.py` 外无其他文件含模块顶层 `import quantide` / `from quantide ...` 语句(即 `DataLoader` 模块本身仍零 quantide 顶层 import,延续 v0.3.0 NFR-0200 / v0.3.1 NFR-0101 / v0.4.0 NFR-0100 compat shim 模式)
- **断言**:
  - 给定:`src/trader_off/data/` 目录所有 `.py` 文件。
  - 当:`grep -rn "^import quantide\|^from quantide" src/trader_off/data/` 执行。
  - 那么:**仅** `src/trader_off/data/quantide_adapter.py` 命中函数体内 import(模块顶层 `^import quantide` / `^from quantide` 应**不**在该文件中出现);`loader.py` / 其他 data 模块**无** quantide 顶层 import。
