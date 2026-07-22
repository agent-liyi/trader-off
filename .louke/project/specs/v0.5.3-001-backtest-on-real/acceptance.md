# v0.5.3 — `run_backtest()` 默认走 `.quantide/` 真数据 — Acceptance Criteria

- **Spec ID**: v0.5.3-001-backtest-on-real
- **Created**: 2026-07-22
- **继承基线**: v0.3.0 `DailyBarsStore` 年分区 parquet 契约 (`daily_bars.connect(store_path, str(calendar_path))`);v0.5.1 `.quantide/bars/` + `.quantide/calendar/calendar.parquet` 落盘契约;v0.2.0 fixture `ohlcv_50x252.parquet` 作为回落源;v0.3.0 NFR-0100 函数级 lazy import 隔离承诺。本文件仅定义 v0.5.3 新增 FR / NFR 的 AC。

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
## FR-0100 `run_backtest()` 默认路径解析 — 优先 `.quantide/` 真数据,fallback 至 fixture,启动日志可观测

### AC-1

AC-FR0100-01

- **WHEN** `run_backtest()` 被调用 AND `config` 未提供 `store_path` AND `Path(".quantide/bars/").exists() == True`
- **THEN** 系统 SHALL 选定 `store_path = ".quantide/bars/"` + 来源标记 `"real-data store"` + 启动期输出 INFO 日志 `store_path=.quantide/bars/ (real-data store)`
- **断言**:
  - 给定: 临时目录含 `.quantide/bars/`(可空目录,仅 `Path.exists()` 探测)
  - 当: `run_backtest(model_version=..., strategy_name="lgbm_top20", start=..., end=..., capital=100000)` 执行(无 `config` 参数 / `config={}`),monkeypatch `daily_bars.connect` 验证传入 `store_path`
  - 那么:
    - `daily_bars.connect` 接收的 `store_path` 形参 `.quantide/bars/`
    - loguru 日志 (caplog / loguru 捕获) 含子串 `store_path=.quantide/bars/ (real-data store)`
    - 来源标记正确: `"real-data store"`(无 `fixture` 字样)
- **对应 EARS**: Story §2.1 AC-01

### AC-2

AC-FR0100-02

- **IF** `run_backtest()` 被调用 AND `config` 未提供 `store_path` AND `Path(".quantide/bars/").exists() == False`
- **THEN** 系统 SHALL 回落到 `store_path = "tests/fixtures/v0.3.0/daily_bars_store"` + 来源标记 `"fixture store"` + 启动期输出 INFO 日志 `store_path=tests/fixtures/v0.3.0/daily_bars_store (fixture store)`
- **断言**:
  - 给定: 临时目录**无** `.quantide/bars/`(fixture 路径 `tests/fixtures/v0.3.0/daily_bars_store/` 存在,作为回落源)
  - 当: `run_backtest(...)` 执行,monkeypatch `daily_bars.connect` 验证
  - 那么:
    - `daily_bars.connect` 接收的 `store_path` 形参 `tests/fixtures/v0.3.0/daily_bars_store`
    - loguru 日志含子串 `store_path=tests/fixtures/v0.3.0/daily_bars_store (fixture store)`
    - 来源标记正确: `"fixture store"`
    - 回落期间**未**调用 `Path("tests/fixtures/v0.3.0/daily_bars_store").exists()`(避免 silent fallback 风险,Story §4 风险 #1);可用 `unittest.mock.patch("pathlib.Path.exists")` + side_effect 验证 .quantide 调用 1 次 + fixture 路径调用 0 次
- **对应 EARS**: Story §2.1 AC-02

### AC-3

AC-FR0100-03

- **WHEN** `run_backtest()` 被调用 AND `config` 未提供 `calendar_source` AND `Path(".quantide/calendar/calendar.parquet").exists() == True`
- **THEN** 系统 SHALL 选定 `calendar_source = ".quantide/calendar/calendar.parquet"` + 来源标记 `"real-data calendar"` + 启动期输出 INFO 日志 `calendar_source=.quantide/calendar/calendar.parquet (real-data calendar)`
- **断言**:
  - 给定: 临时目录含 `.quantide/calendar/calendar.parquet`(可空文件,仅 `Path.exists()` 探测)
  - 当: `run_backtest(...)` 执行,monkeypatch `pl.read_parquet` 验证传入 `calendar_source`
  - 那么:
    - `pl.read_parquet` 接收的 `calendar_source` 形参 `.quantide/calendar/calendar.parquet`
    - loguru 日志含子串 `calendar_source=.quantide/calendar/calendar.parquet (real-data calendar)`
    - 来源标记正确: `"real-data calendar"`
- **对应 EARS**: Story §2.1 AC-03

### AC-4

AC-FR0100-04

- **IF** `run_backtest()` 被调用 AND `config` 未提供 `calendar_source` AND `Path(".quantide/calendar/calendar.parquet").exists() == False`
- **THEN** 系统 SHALL 回落到 `calendar_source = "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"` + 来源标记 `"fixture calendar"` + 启动期输出 INFO 日志 `calendar_source=tests/fixtures/v0.2.0/ohlcv_50x252.parquet (fixture calendar)` + 后续从 fixture `ohlcv_50x252.parquet` 内联生成 calendar
- **断言**:
  - 给定: 临时目录**无** `.quantide/calendar/calendar.parquet`(fixture 路径 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 存在)
  - 当: `run_backtest(...)` 执行,monkeypatch `pl.read_parquet` 验证
  - 那么:
    - `pl.read_parquet` 接收的 `calendar_source` 形参 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet`
    - loguru 日志含子串 `calendar_source=tests/fixtures/v0.2.0/ohlcv_50x252.parquet (fixture calendar)`
    - 来源标记正确: `"fixture calendar"`
    - 后续 `_generate_inline_calendar` 被调用(沿用 v0.3.0 行为,fixture 单测零回归)
    - 回落期间**未**调用 `Path("tests/fixtures/v0.2.0/ohlcv_50x252.parquet").exists()`(避免 silent fallback 风险)
- **对应 EARS**: Story §2.1 AC-04

### AC-5

AC-FR0100-05

- **WHILE** `run_backtest()` 启动期(路径解析完毕、报告目录创建之后、`ohlcv = pl.read_parquet(calendar_source)` 之前)
- **THEN** 系统 SHALL 输出 **2 行** INFO 日志(一次性,无重复):1 行 `store_path=<path> (<marker_store>)` + 1 行 `calendar_source=<path> (<marker_calendar>)`,其中 `marker_store ∈ {"real-data store", "fixture store"}` + `marker_calendar ∈ {"real-data calendar", "fixture calendar"}`
- **断言**:
  - 给定: 任意 `.quantide/` 与 fixture 路径状态(可全存在 / 全不存在 / 部分存在)
  - 当: `run_backtest(...)` 执行,使用 loguru `logger.add(sink, level="INFO", format="{message}")` 捕获
  - 那么:
    - 捕获的日志**至少**含 2 条形如 `store_path=... (...)` + `calendar_source=... (...)` 的记录
    - store_path 日志 1 行(无重复);calendar_source 日志 1 行(无重复)
    - 路径字面值与配置解析结果一致;marker 字面值与探测结果一致(AC-1~AC-4 标记规则)
    - 日志输出时机在 `_generate_inline_calendar` 之前(L162 `pl.read_parquet` 之前)
- **对应 EARS**: Story §2.1 AC-05

### AC-6

AC-FR0100-06

- **WHEN** `run_backtest()` 被调用 AND `config = {"store_path": "tests/fixtures/v0.3.0/daily_bars_store", "calendar_source": "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"}`(fixture 单测显式覆盖)
- **THEN** 系统 SHALL **不**触发 `Path(".quantide/bars/").exists()` / `Path(".quantide/calendar/calendar.parquet").exists()` 探测,直接使用 config 提供的 fixture 路径;来源标记 `"fixture store"` + `"fixture calendar"`;日志输出 2 行 INFO,行为字节级一致(仅多 2 行 INFO,其余与 patch 前一致)
- **断言**:
  - 给定: 临时目录**无** `.quantide/`,fixture 路径存在,`config={"store_path": "tests/fixtures/v0.3.0/daily_bars_store", "calendar_source": "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"}`
  - 当: `run_backtest(..., config=config)` 执行,`unittest.mock.patch("pathlib.Path.exists", side_effect=lambda self: True)` + spy 计数器
  - 那么:
    - `Path(".quantide/bars/").exists()` **未**被调用(或调用 0 次,因 config 命中早于探测)
    - `Path(".quantide/calendar/calendar.parquet").exists()` **未**被调用
    - `daily_bars.connect` 接收的 `store_path = config["store_path"] = "tests/fixtures/v0.3.0/daily_bars_store"`
    - `pl.read_parquet` 接收的 `calendar_source = config["calendar_source"] = "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"`
    - loguru 日志含 `store_path=tests/fixtures/v0.3.0/daily_bars_store (fixture store)` + `calendar_source=tests/fixtures/v0.2.0/ohlcv_50x252.parquet (fixture calendar)`
    - 其余行为(calendar 内联生成、BacktestRunner.run、报告写入等)与 patch 前完全一致(可对比 patch 前 snapshot / git tag v0.5.2)
- **fixture 单测零回归保证** (继承 Story §4 风险 #2): fixture 单测可通过 `config={...}` 显式传入绕过探测,保持行为字节级一致
- **对应 EARS**: Story §3 fixture 单测零回归 + Story §4 风险 #2

### AC-7

AC-FR0100-07

- **WHEN** 验证 `src/trader_off/backtest/runner.py` 模块常量值
- **THEN** 系统 SHALL `DEFAULT_STORE_PATH == ".quantide/bars/"` AND `DEFAULT_CALENDAR_SOURCE == ".quantide/calendar/calendar.parquet"`(从 fixture path 切换到 `.quantide/` 真数据路径)
- **断言**:
  - 给定: `src/trader_off/backtest/runner.py` 模块源文件
  - 当: `python -c "from trader_off.backtest.runner import DEFAULT_STORE_PATH, DEFAULT_CALENDAR_SOURCE; print(DEFAULT_STORE_PATH, DEFAULT_CALENDAR_SOURCE)"`
  - 那么: 输出 `.quantide/bars/ .quantide/calendar/calendar.parquet`(2 个字符串,以空格分隔)
  - 当: `git diff releases/v0.5.3 -- src/trader_off/backtest/runner.py` 执行
  - 那么: diff 仅含 L17 + L18 2 行变更(DEFAULT_STORE_PATH / DEFAULT_CALENDAR_SOURCE 值切换为 `.quantide/`);**不**触及 fixture 路径(保留作为回落源)
- **对应 EARS**: Task description + Story §2

### AC-8

AC-FR0100-08

- **WHEN** 验证部分 fallback 场景(`.quantide/bars/` 存在 + `.quantide/calendar/calendar.parquet` 不存在)
- **THEN** 系统 SHALL store_path 走真数据(`"real-data store"`) + calendar_source 回落到 fixture(`"fixture calendar"`);日志同时输出 2 个不同来源标记
- **断言**:
  - 给定: 临时目录含 `.quantide/bars/`(空目录) **AND 不含** `.quantide/calendar/calendar.parquet`,fixture 路径存在
  - 当: `run_backtest(...)` 执行
  - 那么:
    - `daily_bars.connect` 接收 `store_path=".quantide/bars/"`(真数据)
    - `pl.read_parquet` 接收 `calendar_source="tests/fixtures/v0.2.0/ohlcv_50x252.parquet"`(fixture)
    - loguru 日志含 `store_path=.quantide/bars/ (real-data store)` + `calendar_source=tests/fixtures/v0.2.0/ohlcv_50x252.parquet (fixture calendar)`
- **对应 EARS**: scenario-0030 partial fallback(扩展覆盖 EARS 双 AC-01+AC-04 组合)

---

<a id="ac-nfr-0100"></a>
## NFR-0100 函数级 lazy import — `runner.py` 模块顶层零 `quantide.*` 导入(继承 v0.3.0 NFR-0100)

### AC-1

AC-NFR0100-01

- **WHEN** 验证 `src/trader_off/backtest/runner.py` 模块顶层
- **THEN** 系统 SHALL 无 `import quantide` / `from quantide ...` 语句(模块顶层零 quantide import)
- **断言**:
  - 给定: `src/trader_off/backtest/runner.py` 源文件
  - 当: `grep -rn "^import quantide\|^from quantide" src/trader_off/backtest/runner.py` 执行 (使用 `^` 锚定行首,过滤 import 行)
  - 那么: 无匹配 (grep 退出码 `1`,stdout 为空)。该断言覆盖模块顶部 import 块、`if TYPE_CHECKING` 块、模块级 docstring。

### AC-2

AC-NFR0100-02

- **WHEN** Python AST 解析 `runner.py`
- **THEN** 系统 SHALL 验证所有 `quantide` 导入节点的祖先链含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 quantide import
- **断言**:
  - 给定: `ast.parse(Path("src/trader_off/backtest/runner.py").read_text())` 后遍历 `ast.ImportFrom` / `ast.Import` 节点
  - 当: 对每个 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点,沿 `ast.walk` 反向追溯父节点(`ast.FunctionDef` / `ast.AsyncFunctionDef` / `ast.ClassDef` / `ast.If` 测试是否为 `TYPE_CHECKING`)
  - 那么: **所有** quantide import 节点的最近函数祖先存在,且**不**位于 `if TYPE_CHECKING` 块内或类体内。断言失败若任一 import 出现在模块顶层 / 类体 / TYPE_CHECKING 块。

### AC-3

AC-NFR0100-03

- **WHEN** 验证 `runner.py` 函数体内现有 quantide import 保留
- **THEN** 系统 SHALL **至少** 3 个 `from quantide ...` 匹配(函数体内,无 `^` 行首锚定),分别含:
  1. `from quantide.data.models.daily_bars import daily_bars` (L172)
  2. `from quantide.service.runner import BacktestRunner` (L178)
  3. `from quantide.data.sqlite import db` (L221)
- **断言**:
  - 给定: `runner.py` 源文件
  - 当: `grep -rn "from quantide" src/trader_off/backtest/runner.py` 执行 (无 `^` 锚定,允许函数体内任意位置)
  - 那么: **至少** 3 行匹配,内容分别含 `from quantide.data.models.daily_bars import daily_bars` + `from quantide.service.runner import BacktestRunner` + `from quantide.data.sqlite import db`。本 spec **不**新增 quantide import(NFR-0100 仅承诺 import 位置合规)。

### AC-4

AC-NFR0100-04

- **WHEN** 验证 `pyproject.toml` 无新依赖引入
- **THEN** 系统 SHALL `[project]` `dependencies` 列表 SHA 锁定不变(继承 v0.3.0 / v0.5.1);`git diff pyproject.toml` 应无依赖增删
- **断言**:
  - 给定: `pyproject.toml` 当前内容
  - 当: `git diff releases/v0.5.3 -- pyproject.toml` 执行
  - 那么: 无 diff(空输出,退出码 `0`);若 diff 含 `[project]` `dependencies` 列表变更 → 失败
  - 当: `grep -E "^(import|from).*quantide" src/trader_off/backtest/runner.py` 执行(任何位置)
  - 那么: 匹配数 ≤ 3(对应 L172 / L178 / L221 三处函数级 import,无新增)
