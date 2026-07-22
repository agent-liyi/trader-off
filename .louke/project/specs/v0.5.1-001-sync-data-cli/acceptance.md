# v0.5.1 — `trader-off sync-data` CLI — Acceptance Criteria

- **Spec ID**: v0.5.1-001-sync-data-cli
- **Created**: 2026-07-22
- **继承基线**: v0.4.1 FR-0100 `QuantideDataLoader.get_daily()` 公开契约;v0.3.0 DailyBarsStore 年分区 parquet 契约;v0.4.2 `[project.scripts]` PEP 621 dash-prefix 注册模式。本文件仅定义 v0.5.1 新增 FR / NFR 的 AC。

> 中央注册表: spec.md 只保留 FR/NFR 描述与元数据 (testability/decided/valid);可观察、可断言的通过条件在本表中。
>
> 编号约定:
> - 每个 FR/NFR 单元内 AC-N 从 1 起,按顺序递增;单元之间不复用
> - 完整 AC 引用: **AC-FRXXXX-YY** (4 位 FR + 2 位 AC 序号),与 test-plan / issue schema 保持一致
> - 标题层级: `## FR-XXXX {title}` 为 level-2;`### AC-N` 为 level-3 (其后同一行**不**接任何文字,canonical ID 写在下一行)
>
> Lex 阶段 1/2 审查验证: (1) 本表存在; (2) spec.md 每个 FR/NFR 在本表中有对应章节; (3) 每条 AC 可被测试或断言。
>
> EARS 句式关键词约定: `WHEN` (触发条件) / `WHILE` (持续状态) / `WHERE` (前置条件) / `IF ... THEN` (条件分支) / `THE 系统 SHALL ...` (系统行为)。

---

<a id="ac-fr-0100"></a>
## FR-0100 `trader-off sync-data` CLI — 封装 `QuantideDataLoader.get_daily()` + 落 `DailyBarsStore` 年分区 parquet + 写 `.quantide/calendar/`

### AC-1

AC-FR0100-01

- **WHEN** `trader-off-sync-data` 被执行 AND env `TUSHARE_TOKEN` 未设置
- **THEN** 系统 SHALL 写 stderr `"TUSHARE_TOKEN environment variable is required; set it before running sync-data"` + 退出码 **4**,且**不**发起任何网络 IO、**不** lazy import `quantide.*`
- **断言**:
  - 给定: `os.environ` 中无 `TUSHARE_TOKEN`
  - 当: `trader-off-sync-data --universe universe.csv --start 2024-01-01 --end 2024-12-31` 执行
  - 那么:
    - 退出码 = 4
    - stderr 含 `"TUSHARE_TOKEN environment variable is required"`
    - `quantide.data.fetchers.tushare.*` 任意符号**未被**触发 (可用 `unittest.mock.patch("quantide.data.fetchers.tushare.TushareFetcher")` + `unittest.mock.patch("quantide.data.fetchers.tushare.fetch_calendar")` 验证未触发)
    - `quantide.data.models.calendar.calendar` **未被**调用
- **对应 EARS**: Story §2.4 AC-01

### AC-2

AC-FR0100-02

- **WHEN** `trader-off-sync-data` 被执行 AND 所有 args 完整 (含 `--universe` / `--start` / `--end`) AND token 已设置
- **THEN** 系统 SHALL 解析 args + 读 universe 文件 + 顺序遍历每个 asset 调 `await loader.get_daily(asset, end_date=end, count=trading_days_in_range(start, end))`(函数级 lazy import `QuantideDataLoader` + `quantide.data.fetchers.tushare.fetch_calendar` + `quantide.data.models.calendar.calendar`)
- **断言**:
  - 给定: `os.environ['TUSHARE_TOKEN'] = "fake-token-for-test"`,universe 含 3 个 asset (`000001.SZ` / `600519.SH` / `000858.SZ`),`--start 2024-01-01` `--end 2024-12-31`,`--store-path /tmp/test_store/`
  - 当: monkeypatch/mock `TushareFetcher` 返回固定 60 天 OHLCV fixture,`fetch_calendar` mock 返回包含 [start-30d, end+30d] 范围的真实交易日,`get_daily` 走通 mock `fetch_bars` 路径
  - 那么:
    - `QuantideDataLoader(token="fake-token-for-test")` 实例化**一次**
    - `loader.get_daily(asset, end_date=date(2024,12,31), count=N)` 对每个 asset 调用**一次**(共 3 次),`N >= 1`
    - `fetch_calendar(start - timedelta(days=30))` 调用**至少** 1 次
    - `quantide.data.models.calendar.calendar.save(cal_df)` 调用**至少** 1 次,`calendar._path` 含 `.quantide/calendar/calendar.parquet`
    - 退出码 = 0
- **对应 EARS**: Story §2.4 AC-02

### AC-3

AC-FR0100-03

- **WHEN** `loader.get_daily()` 返回 polars OHLCV DataFrame
- **THEN** 系统 SHALL 写 OHLCV 到 `{store_path}/year=YYYY/part-N.parquet` (schema `{date: Date, asset: Utf8, open: Float64, high: Float64, low: Float64, close: Float64, volume: Float64, adj_factor: Float64}`) + 写 calendar 到 `.quantide/calendar/calendar.parquet` (经 `quantide.data.models.calendar.calendar.save(cal_df)`)
- **断言**:
  - 给定: AC-2 mock 环境 (`TushareFetcher` mock 返回 60 天 OHLCV,`fetch_calendar` mock 返回 60 个 ≤ end_date 的真实交易日),`--store-path /tmp/test_store/`,`--start 2024-01-01` `--end 2024-12-31`
  - 当: `trader-off-sync-data` 执行完整链路
  - 那么:
    - `/tmp/test_store/year=2024/part-*.parquet` 存在(因 2024 年数据,**至少** 1 个 part-N.parquet 文件)
    - parquet schema 严格匹配 `{date, asset, open, high, low, close, volume, adj_factor}`(含 8 列,类型正确)
    - `.quantide/calendar/calendar.parquet` 文件存在(默认 calendar 路径)
    - parquet 数据可被 polars 读回,行数 ≥ 3 (3 asset × 至少 1 行 OHLCV)
    - 退出码 = 0
- **对应 EARS**: Story §2.4 AC-03

### AC-4

AC-FR0100-04

- **WHEN** `--dry-run` 启用
- **THEN** 系统 SHALL 仅打印 `[dry-run] asset=... start=... end=... → ...` 计划到 stderr/log,**不**写任何 parquet 文件、**不**调 `fetch_calendar` / `get_daily` / `calendar.save`、**不**发起任何网络 IO
- **断言**:
  - 给定: token 已设置,universe 含 3 个 asset,`--dry-run` 启用,`--store-path /tmp/test_dryrun/`
  - 当: `trader-off-sync-data --universe universe.csv --start 2024-01-01 --end 2024-12-31 --store-path /tmp/test_dryrun/ --dry-run` 执行
  - 那么:
    - 退出码 = 0
    - stderr 含 `[dry-run]` 标记,至少 N 行 (N = asset 数 = 3)
    - `/tmp/test_dryrun/` 目录**不**存在 (或为空,无 `.parquet` 文件)
    - `.quantide/calendar/calendar.parquet` **不**存在或未被修改 (mtime 不变)
    - `quantide.data.fetchers.tushare.TushareFetcher` / `fetch_calendar` / `fetch_bars` **未被**实例化/调用
    - `quantide.data.models.calendar.calendar.save` **未被**调用
- **对应 EARS**: Story §2.4 AC-04

### AC-5

AC-FR0100-05

- **WHERE** 单 asset 同步失败 (网络异常 / Tushare 返回空 / 数据缺失 → `loader.get_daily` 返回空 DataFrame 或抛异常)
- **THEN** 系统 SHALL 记录到 stderr + loguru logger,继续下一个 asset,最后退出码 = **5**
- **断言**:
  - 给定: universe 含 3 个 asset,monkeypatch 使 `loader.get_daily("000001.SZ", ...)` 抛 `RuntimeError("network down")` 或返回空 DataFrame (高度 == 0),其他 2 个 asset 正常 mock 返回 OHLCV
  - 当: `trader-off-sync-data` 执行完整链路
  - 那么:
    - 失败的 asset 错误信息**含**于 stderr/log (`"network down"` 或 `"empty"` 等关键词)
    - 其他 2 个 asset 的 parquet **被**写入 `{store_path}/year=YYYY/`(可读回,行数 ≥ 1)
    - 退出码 = 5
    - loguru `logger.exception` 调用**至少** 1 次
- **对应 EARS**: Story §2.4 AC-05

### AC-6

AC-FR0100-06

- **WHEN** `pyproject.toml` 被加载
- **THEN** 系统 SHALL 暴露 `trader-off-sync-data` entry point 指向 `trader_off.cli.sync_data:main`
- **断言**:
  - 给定: `pyproject.toml`
  - 当: `grep -A1 "trader-off-sync-data" pyproject.toml` 执行
  - 那么: 返回 1 行匹配,内容为 `trader-off-sync-data = "trader_off.cli.sync_data:main"`
  - 当: `uv sync` 执行
  - 那么: 退出码 = 0,`.venv/bin/trader-off-sync-data` 文件存在且可执行 (`os.access(".venv/bin/trader-off-sync-data", os.X_OK)` 为真)
  - 当: `uv run trader-off-sync-data --help` 执行
  - 那么: 退出码 = 0,stdout 含 `--universe` / `--start` / `--end` / `--store-path` / `--dry-run` argparse help 文本
- **对应 EARS**: Story §2.4 AC-07

### AC-7

AC-FR0100-07

- **WHEN** argparse 失败 (参数缺失 / 日期格式错误)
- **THEN** 系统 SHALL 退出码 = **2**,且 stderr 含 argparse 错误信息
- **断言**:
  - 给定: 任意 token 设置 (或不设置,token 检查在 argparse 之后)
  - 当 (case 1): `trader-off-sync-data` (无 args) 执行
  - 那么: 退出码 = 2,stderr 含 `"the following arguments are required: --universe, --start, --end"` (argparse 默认错误信息)
  - 当 (case 2): `trader-off-sync-data --universe u.csv --start invalid-date --end 2024-12-31` 执行
  - 那么: 退出码 = 2,stderr 含 `"invalid isoformat"` 或类似日期解析错误
- **对应 EARS**: 任务描述 Exit codes (2 = argparse)

### AC-8

AC-FR0100-08

- **WHEN** universe 文件不存在 / 读取失败 / 无 `asset` 列 OR `--start > --end`
- **THEN** 系统 SHALL 退出码 = **4**,且 stderr 含明确错误信息(`"universe file not found"` / `"no 'asset' column"` / `"start date must be <= end date"` 等)
- **断言**:
  - 给定: token 已设置
  - 当 (case 1): `trader-off-sync-data --universe /tmp/nonexistent.csv --start 2024-01-01 --end 2024-12-31` 执行
  - 那么: 退出码 = 4,stderr 含 `"universe file not found"` 或 `"universe"` 关键词
  - 当 (case 2): `trader-off-sync-data --universe universe_no_asset_col.csv --start 2024-01-01 --end 2024-12-31` 执行 (CSV 不含 `asset` 列)
  - 那么: 退出码 = 4,stderr 含 `"asset column"` 关键词
  - 当 (case 3): `trader-off-sync-data --universe u.csv --start 2024-12-31 --end 2024-01-01` 执行
  - 那么: 退出码 = 4,stderr 含 `"start"` / `"end"` 关键词
- **对应 EARS**: 任务描述 Exit codes (4 = config error)

---

<a id="ac-nfr-0100"></a>
## NFR-0100 函数级 lazy import — 白名单延伸至 `cli/sync_data.py` (含 `quantide.data.models.calendar.calendar`)

### AC-1

AC-NFR0100-01

- **WHEN** 验证 `src/trader_off/cli/sync_data.py` 模块顶层
- **THEN** 系统 SHALL 无 `import quantide` / `from quantide ...` 语句(模块顶层零 quantide import)
- **断言**:
  - 给定: `src/trader_off/cli/sync_data.py` 源文件
  - 当: `grep -rn "^import quantide\|^from quantide" src/trader_off/cli/sync_data.py` 执行 (使用 `^` 锚定行首,过滤 import 行)
  - 那么: 无匹配 (grep 退出码 `1`,stdout 为空)。该断言覆盖模块顶部 import 块、`if TYPE_CHECKING` 块、模块级 docstring。

### AC-2

AC-NFR0100-02

- **WHEN** 验证 `sync_data.py` 函数体内 import
- **THEN** 系统 SHALL 至少 2 个 `from quantide ...` 匹配:
  1. `from quantide.data.fetchers.tushare import fetch_calendar` (继承 v0.4.1 白名单)
  2. `from quantide.data.models.calendar import calendar` (本 spec 新增放行)
- **断言**:
  - 给定: `sync_data.py` 源文件
  - 当: `grep -rn "from quantide" src/trader_off/cli/sync_data.py` 执行 (无 `^` 锚定,允许函数体内任意位置)
  - 那么: **至少** 2 行匹配,内容分别含 `from quantide.data.fetchers.tushare import` 与 `from quantide.data.models.calendar import calendar` (允许 import 行包含其他符号,例如 `from quantide.data.fetchers.tushare import fetch_calendar` 或 `from quantide.data.fetchers.tushare import TushareFetcher, fetch_calendar`)

### AC-3

AC-NFR0100-03

- **WHEN** Python AST 解析 `sync_data.py`
- **THEN** 系统 SHALL 验证所有 `quantide` 导入节点的祖先链含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 quantide import
- **断言**:
  - 给定: `ast.parse(Path("src/trader_off/cli/sync_data.py").read_text())` 后遍历 `ast.ImportFrom` / `ast.Import` 节点
  - 当: 对每个 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点,沿 `ast.walk` 反向追溯父节点(`ast.FunctionDef` / `ast.AsyncFunctionDef` / `ast.ClassDef` / `ast.If` 测试是否为 `TYPE_CHECKING`)
  - 那么: **所有** quantide import 节点的最近函数祖先存在,且**不**位于 `if TYPE_CHECKING` 块内或类体内。断言失败若任一 import 出现在模块顶层 / 类体 / TYPE_CHECKING 块。

### AC-4

AC-NFR0100-04

- **WHEN** 验证 `sync_data.py` 业务符号白名单边界
- **THEN** 系统 SHALL **无** `quantide.service.*` / `quantide.portfolio.*` / `quantide.backtest.*` / `quantide.core.scheduler.*` / `quantide.data.models.daily_bars.*` / `quantide.data.fetchers.<非 tushare>.*` 的 import;白名单内**仅**允许 `quantide.data.fetchers.tushare.*` 与 `quantide.data.models.calendar.calendar`
- **断言**:
  - 给定: `sync_data.py` 源文件
  - 当: `grep -rnE "quantide\.(service|portfolio|backtest|core\.scheduler|models\.daily_bars|fetchers\.(?!tushare))" src/trader_off/cli/sync_data.py` 执行 (Perl/PCRE negative lookahead)
  - 那么: 无匹配 (grep 退出码 `1`,stdout 为空)。白名单内**仅**允许 `quantide.data.fetchers.tushare.*` (`fetch_calendar` / `fetch_bars` / `TushareFetcher` 等) 与 `quantide.data.models.calendar.calendar` (singleton),**不**放行 `Calendar` 类 / `FrameType` / `daily_bars` singleton / 其他子模块。

### AC-5

AC-NFR0100-05

- **WHEN** 验证 `src/trader_off/cli/` 目录的集成层隔离
- **THEN** 系统 SHALL 除 `sync_data.py` 函数体内 import 外,`cli/__init__.py` / `cli/backtest.py` 无模块顶层 `import quantide` / `from quantide ...` 语句 (即 `cli/` 目录仅 `sync_data.py` 引入 quantide,且仅在函数体内;延续 v0.4.2 隔离承诺)
- **断言**:
  - 给定: `src/trader_off/cli/` 目录所有 `.py` 文件
  - 当: `grep -rn "^import quantide\|^from quantide" src/trader_off/cli/` 执行
  - 那么: **无**模块顶层 `^import quantide` / `^from quantide` 匹配(grep 退出码 `1`,stdout 为空);函数体内 import **仅**出现在 `sync_data.py` 内(`cli/__init__.py` / `cli/backtest.py` 仍零 quantide import,延续 v0.4.2 NFR-0100 compat shim 模式)
