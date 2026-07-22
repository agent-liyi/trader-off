---
status: draft
locked: false
---
# v0.5.3 — `run_backtest()` 默认走 `.quantide/` 真数据 — Spec

- **Spec ID**: v0.5.3-001-backtest-on-real
- **Created**: 2026-07-22
- **Status**: Draft
- **关联 story**: `.louke/project/specs/v0.5.3-001-backtest-on-real/story.md` (STR-0007)
- **继承基线**:
  - v0.3.0 `DailyBarsStore` 年分区 parquet 契约 (`daily_bars.connect(store_path, ...)`)
  - v0.5.1 `.quantide/bars/` + `.quantide/calendar/calendar.parquet` 落盘契约 (本 spec **不**改 schema)
  - v0.2.0 fixture `ohlcv_50x252.parquet` 作为回落源(本 spec 仅切换探测顺序,不改 fixture 内容)
  - v0.3.0 NFR-0100 函数级 lazy import 隔离承诺(`quantide.*` 不出现在模块顶层) — 本 spec 沿用并显式登记为 NFR-0100

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。验收标准放在 `acceptance.md` 中。测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。

> **北极星目标**: `trader-off-sync-data` → `trader-off-backtest` 零参数端到端跑通;离线无 token 仍走 fixture;启动日志可观测 `store_path / calendar_source` 与 `real-data | fixture` 来源标记。fixture 单测零回归(CI 显式 monkeypatch fixture 路径覆盖回归风险)。

> **关键约束 (继承 Story §3)**:
> - 本 spec 范围:**仅** `src/trader_off/backtest/runner.py`(含 2 个模块常量与 `run_backtest()` 内路径解析逻辑);**不**改 `DailyBarsStore` schema / `calendar` 契约 / CLI / 任何 `quantide.*` 模块
> - patch ≤ 1 issue;本 spec 拆 FR-0100 (行为) + NFR-0100 (结构约束) 两条便于追踪
> - Python ≥3.13
> - fixture 单测零回归(CI monkeypatch 显式 fixture 路径,见 Story §4 风险 #2)
> - 不新增 CLI 参数(Story §3 Avoid:新增 CLI 参数)
> - 不做数据新鲜度/增量校验(Story §3 Out-of-Scope)

## User Stories

### US-0010

story: 作为一名量化研究员/单一开发者,我在本地持有 `trader-off-sync-data` 同步好的 `.quantide/bars/` + `.quantide/calendar/calendar.parquet` 时,通过 `trader-off-backtest ...` 零参数(沿用 v0.5.0 CLI 契约)即可跑通基于真 A 股数据的端到端回测;当我尚未运行 `sync-data` 或离线环境无 token 时,系统自动回落到 `tests/fixtures/v0.3.0/daily_bars_store` + `tests/fixtures/v0.2.0/ohlcv_50x252.parquet`,并通过启动 INFO 日志明确告知选定路径与 `real-data | fixture` 来源标记,确保可观测性与 fixture 单测零回归。
priority: P0

## Usage Scenarios

### scenario-0010 happy path (`.quantide/` 存在,真数据端到端)

1. 开发者先执行 `trader-off-sync-data` (v0.5.1) 产出 `.quantide/bars/year=YYYY/part-N.parquet` 与 `.quantide/calendar/calendar.parquet`。
2. 开发者执行 `trader-off-backtest --strategy lgbm_top20 --start 2024-01-01 --end 2024-12-31 --capital 100000`。
3. CLI 内部调 `run_backtest(...)` (v0.5.0 公开签名,本 spec **不**改),`run_backtest()` 启动期:
   - 探测 `Path(".quantide/bars").exists() == True` → `store_path` 取真数据路径,来源标记 `"real-data store"`
   - 探测 `Path(".quantide/calendar/calendar.parquet").exists() == True` → `calendar_source` 取真数据路径,来源标记 `"real-data calendar"`
4. 一次性 INFO 日志输出 `store_path=<真数据路径> (real-data store)` + `calendar_source=<真数据路径> (real-data calendar)`。
5. 后续 `daily_bars.connect(store_path, ...)` (v0.3.0 契约) 直接连真数据,calendar 由真数据 `.quantide/calendar/calendar.parquet` 提供,fixture 路径**不**被读取。

### scenario-0020 fixture fallback (`.quantide/` 不存在,离线无 token)

1. 开发者离线环境未运行 `sync-data`(或 TUSHARE_TOKEN 未设置) → `.quantide/bars/` 与 `.quantide/calendar/calendar.parquet` 均不存在。
2. 开发者执行 `trader-off-backtest ...`(同 scenario-0010)。
3. `run_backtest()` 启动期:
   - `Path(".quantide/bars").exists() == False` → `store_path` 回落到 `tests/fixtures/v0.3.0/daily_bars_store` (沿用 v0.3.0 fixture 契约),来源标记 `"fixture store"`
   - `Path(".quantide/calendar/calendar.parquet").exists() == False` → `calendar_source` 回落到 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 内联生成,来源标记 `"fixture calendar"`
4. 一次性 INFO 日志输出 `store_path=<fixture 路径> (fixture store)` + `calendar_source=<fixture 路径> (fixture calendar)`。
5. 后续 `daily_bars.connect(store_path, str(tmp_calendar_path))` 走 v0.3.0 fixture 链路,calendar 由 fixture `ohlcv_50x252.parquet` 内联生成的 `tmp_calendar_path` 提供,行为与 patch 前完全一致(保证 fixture 单测零回归)。

### scenario-0030 partial fallback (`bars/` 在,`calendar/` 不在)

1. 开发者已运行 `sync-data` 但 calendar 写入失败 → `.quantide/bars/` 存在,`.quantide/calendar/calendar.parquet` 不存在。
2. `run_backtest()` 探测:bars 真数据 + calendar 回落 fixture。
3. 日志同时输出两个标记:`(real-data store)` + `(fixture calendar)`;`store_path` 取 `.quantide/bars/`、`calendar_source` 取 fixture。

### scenario-0040 fixture 路径显式传入(单测 monkeypatch)

1. 单测通过 `config = {"store_path": "tests/fixtures/v0.3.0/daily_bars_store", "calendar_source": "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"}` 显式传入(覆盖 `.quantide/` 探测),保证 fixture 单测零回归(继承 Story §4 风险 #2)。
2. `run_backtest()` 启动期:由于 `config.get(...)` 命中,探测路径**不**被读取(无 `Path.exists()` 调用),来源标记沿用配置路径 + 标记 `fixture`(因路径字面值含 `fixtures/`)。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表 (Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100** 一条 P0 FR + **NFR-0100** 一条 NFR;起始 100 间隔 (patch ≤ 1 issue 范围,沿用 v0.4.2 / v0.5.1 编号策略)。后续 review round 插入 10 间隔位。
>
> **必读**: FR-XXXX 是该需求唯一 ID,**禁止删除**既有 ID;若 FR 需废弃,改表内 Valid=❌ 并在 Clarification Log 解释。
>
> 引用约定 (AC): 验收标准用 `AC-FRXXXX-YY` 格式 (4 位 FR + 2 位 AC),见 `acceptance.md`。
>
> **元数据表 (3 列)**:
> - Valid (原 yaml `valid`): ✅ = 仍生效,❌ = 已废弃
> - Testable (原 yaml `testability`): ✅ = 可测试/可断言,⚠️ {原因} = 存保留意见
> - Decided (原 yaml `resolved`): ✅ = 用户已确认,⚠️ = 待澄清,❌ = 用户明确拒绝

---

<a id="fr-0100"></a>
### FR-0100 `run_backtest()` 默认路径解析 — 优先 `.quantide/` 真数据,fallback 至 fixture,启动日志可观测

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **修改文件**: `src/trader_off/backtest/runner.py` (现有模块,本 spec **不**新建文件)
- **模块常量变更** (2 处):
  - L17 `DEFAULT_STORE_PATH`:
    - **改前**: `"tests/fixtures/v0.3.0/daily_bars_store"` (fixture path)
    - **改后**: `".quantide/bars/"` (v0.5.1 `sync-data` 默认落盘路径,v0.3.0 `daily_bars.connect` 默认对齐)
  - L18 `DEFAULT_CALENDAR_SOURCE`:
    - **改前**: `"tests/fixtures/v0.2.0/ohlcv_50x252.parquet"` (fixture path)
    - **改后**: `".quantide/calendar/calendar.parquet"` (v0.5.1 `sync-data` calendar 默认落盘路径)
- **`run_backtest()` 启动期路径解析** (位于 L154-155 `config.get(...)` 之后,INFO 日志输出之前;基于模块常量默认值):
  - **store_path 探测**:
    - **WHEN** `config` 未显式提供 `store_path` (走默认值 `DEFAULT_STORE_PATH = ".quantide/bars/"`) AND `Path(DEFAULT_STORE_PATH).exists() == True`
    - **THEN** `store_path = DEFAULT_STORE_PATH` (即 `.quantide/bars/`),来源标记 `"real-data store"`
    - **IF** `config` 未显式提供 `store_path` AND `Path(DEFAULT_STORE_PATH).exists() == False`
    - **THEN** `store_path = "tests/fixtures/v0.3.0/daily_bars_store"` (fixture 回落值,硬编码回落常量,避免 DEFAULT_STORE_PATH 与 fixture 强耦合),来源标记 `"fixture store"`
    - **WHEN** `config` 显式提供 `store_path` (覆盖 DEFAULT_STORE_PATH)
    - **THEN** `store_path = config["store_path"]`,**不**触发 `Path.exists()` 探测;来源标记根据路径字面值判定 — 含 `"fixtures/"` 子串 → `"fixture store"`,否则 → `"real-data store"`
  - **calendar_source 探测** (逻辑同 store_path,独立探测):
    - **WHEN** `config` 未显式提供 `calendar_source` AND `Path(DEFAULT_CALENDAR_SOURCE).exists() == True`
    - **THEN** `calendar_source = DEFAULT_CALENDAR_SOURCE` (即 `.quantide/calendar/calendar.parquet`),来源标记 `"real-data calendar"`
    - **IF** `config` 未显式提供 `calendar_source` AND `Path(DEFAULT_CALENDAR_SOURCE).exists() == False`
    - **THEN** `calendar_source = "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"` (fixture 回落值),来源标记 `"fixture calendar"`
    - **WHEN** `config` 显式提供 `calendar_source`
    - **THEN** `calendar_source = config["calendar_source"]`,**不**触发探测;标记同 store_path 规则
  - **回落值硬编码** (避免 DEFAULT 常量与 fixture 路径耦合): 引入模块常量 `FIXTURE_STORE_PATH = "tests/fixtures/v0.3.0/daily_bars_store"` + `FIXTURE_CALENDAR_SOURCE = "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"`(或在 `run_backtest()` 内 inline 字符串;常量版更清晰,推荐);探测定义为 `exists() == False` 时**直接**使用回落常量,**不**动态探测 fixture 路径(`Path(fixture).exists()` 可能因环境差异失败,造成 silent fallback 风险,见 Story §4 风险 #1)
- **启动期 INFO 日志** (一次性,位于 L156-159 报告目录创建之后,L162 `ohlcv = pl.read_parquet(calendar_source)` 之前):
  - **WHEN** `store_path` 已选定(无论来源)
  - **THEN** `logger.info(f"store_path={store_path} ({source_marker_store})")`,其中 `source_marker_store ∈ {"real-data store", "fixture store"}`
  - **WHEN** `calendar_source` 已选定
  - **THEN** `logger.info(f"calendar_source={calendar_source} ({source_marker_calendar})")`,其中 `source_marker_calendar ∈ {"real-data calendar", "fixture calendar"}`
  - 日志**只输出一次**(无重复);`run_backtest()` 内**不**再二次打印 store_path / calendar_source(避免冗余;若后续步骤日志含路径,需确保与启动期日志一致)
- **后续步骤零行为变更** (本 spec **不**改):
  - L162 `ohlcv = pl.read_parquet(calendar_source)`:calendar_source 现在可为 `.quantide/calendar/calendar.parquet` (真数据) 或 fixture 路径 (回落)
  - L168 `_generate_inline_calendar(...)`:无论来源,统一生成 inline calendar parquet 到 `tmp_calendar_path`(兼容 v0.3.0 `daily_bars.connect` 需要本地 calendar parquet 文件的契约);真数据 calendar 仅用于**存在性探测**,**不**直接传给 `daily_bars.connect` — 统一走 inline 生成路径(因 `daily_bars.connect(store_path, str(tmp_calendar_path))` 期望 str 路径,且 `quantide` 模块行为统一要求 calendar parquet 文件)
  - L172-175 `daily_bars.connect(store_path, str(tmp_calendar_path))`:接收新的 store_path 即可,`daily_bars` 沿用 v0.3.0 年分区 parquet 契约
  - 后续 runner / db / report 写入**不**改
- **fixture 单测零回归 (继承 Story §4 风险 #2)**:
  - 现有 fixture 单测可通过 `config={"store_path": "tests/fixtures/v0.3.0/daily_bars_store", "calendar_source": "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"}` 显式传入,绕过 `Path.exists()` 探测(因 config 命中路径早于探测),保证 `run_backtest()` 行为与 patch 前字节级一致(仅启动日志多输出 2 行 INFO)
  - 若 fixture 单测未传 config,fixture 路径需**仍**存在 (即 `tests/fixtures/v0.3.0/daily_bars_store/` 与 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 已在仓库,本 spec 不删除 fixture)
- **silent fallback 防护 (继承 Story §4 风险 #1)**:
  - 真数据 `.quantide/bars/` 部分缺失 (e.g. 文件夹存在但 parquet 数据空 / schema 不匹配) → 本 spec **不**新增校验,沿用 `daily_bars.connect` 自身错误抛出(v0.3.0 契约);后续 v0.5.4+ 可加 schema 校验(Story §3 Out-of-Scope:数据新鲜度/增量校验)
  - fixture 回落时 `Path(fixture).exists()` 不再探测(避免 silent fallback 风险),如 fixture 文件被删,`pl.read_parquet(calendar_source)` (L162) 抛 `FileNotFoundError` 向上抛,非零退出码由 CLI 层处理
- **真/假 calendar 字段一致性 (继承 Story §4 风险 #3)**:
  - 启动时**不**做 schema 校验(本 spec 范围内不引入额外校验开销);统一走 `_generate_inline_calendar()` 生成兼容 v0.3.0 `daily_bars` 契约的 calendar parquet(无论 calendar_source 是真数据还是 fixture,生成的 tmp_calendar_path schema 固定为 `{date: Date, is_open: Int64, prev: Int64}`,见 runner.py L91-98)
- **out-of-scope** (继承 Story §3,显式**不**做):
  - 改 `DailyBarsStore` schema / `calendar` 契约(锁定)
  - 新增 CLI 参数(Story §3 Avoid)
  - 真数据训练 / 数据新鲜度 / 增量校验 / 增量回测
  - 改 `QuantideDataLoader` / `get_daily` 签名(v0.4.1 锁定)
  - 改 v0.3.0 `daily_bars.connect` 接口 / v0.5.1 `sync-data` 落盘契约
  - 删除 fixture(`tests/fixtures/v0.3.0/daily_bars_store` 与 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 保留作为回落源)

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR,此处省略。

---

<a id="nfr-0100"></a>
### NFR-0100 函数级 lazy import — `runner.py` 模块顶层零 `quantide.*` 导入(继承 v0.3.0 NFR-0100)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **隔离承诺 (继承 v0.3.0)**: `src/trader_off/backtest/runner.py` 模块顶层(含 `import` 块、`from ... import` 块、`if TYPE_CHECKING` 块、模块级 docstring 示例代码、`__all__` 列表)**不**出现 `import quantide` 或 `from quantide ...` 语句。
- 所有 `quantide` 导入必须位于 `def` / `async def` 函数体内;导入时机为首次调用(沿用 runner.py L172 `from quantide.data.models.daily_bars import daily_bars` + L178 `from quantide.service.runner import BacktestRunner` + L221 `from quantide.data.sqlite import db` 三处函数级 import 模式)。
- **白名单边界**:本 spec **不**引入新的 quantide import;所有现有 quantide import 仍位于白名单内(`quantide.data.models.daily_bars.daily_bars` / `quantide.service.runner.BacktestRunner` / `quantide.data.sqlite.db`)。本 NFR 仅承诺 import **位置**(模块顶层 vs 函数体)合规,**不**约束白名单内容(白名单由各 FR 锁定)。
- **新常量导入**: 本 spec 新增的模块常量(`DEFAULT_STORE_PATH` / `DEFAULT_CALENDAR_SOURCE` / 可选 `FIXTURE_STORE_PATH` / `FIXTURE_CALENDAR_SOURCE`)均为 `str` 字面值 + `pathlib.Path`,**不**引入新依赖,模块顶层 import 块**不**增加。
- **验证 1 (模块顶层)**:
  - `grep -rn "^import quantide\|^from quantide" src/trader_off/backtest/runner.py` 应无匹配(grep 退出码 `1`,stdout 为空)
- **验证 2 (AST 校验)**:
  - Python AST 解析(`ast.parse` + 遍历 `ast.ImportFrom` / `ast.Import`) `runner.py`,所有 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点的祖先链必须含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 import
- **验证 3 (现有函数级 import 保留)**:
  - `grep -rn "from quantide" src/trader_off/backtest/runner.py` 应**至少** 3 个匹配(函数体内,无 `^` 行首锚定),分别含 `from quantide.data.models.daily_bars import daily_bars` (L172) + `from quantide.service.runner import BacktestRunner` (L178) + `from quantide.data.sqlite import db` (L221)
- **验证 4 (无新依赖引入)**:
  - `pyproject.toml` `[project]` `dependencies` 列表 SHA 锁定不变(继承 v0.3.0 / v0.5.1);`git diff pyproject.toml` 应无依赖增删

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|
| 0 (Story M-STORY) | Story §6 Human 确认 | 分流结论 Go / FR-0100 路径解析行为 / NFR-0100 函数级 import 继承 / Out-of-Scope 认同 (M-FOUND 已通过) | ✅ |
| 0 (M-SPEC) | Task description vs Story §2 | Task description 简述"探测 `.quantide/` 存在 → 用,否则 fallback",Story §2 给出 5 条 EARS AC(AC-01~AC-05),涵盖 store/calendar 双探测 + 来源标记 + INFO 日志。**决策**: FR-0100 行为条款以 Story §2 + EARS 为准,Task description 简述作为实施意图概要;AC 编号沿用 AC-01~AC-05 | ✅ |
| 0 (M-SPEC) | DEFAULT_STORE_PATH 改后值 | Task description 明确 `DEFAULT_STORE_PATH = ".quantide/bars/"`(v0.5.1 `sync-data` 默认落盘路径),Story §2 隐含同意(`.quantide/bars/` 与 `tests/fixtures/v0.3.0/daily_bars_store` 是 v0.5.1 与 v0.3.0 的契约对齐点)。**决策**: 模块常量统一改为真数据路径(`.quantide/bars/` + `.quantide/calendar/calendar.parquet`),fixture 路径**不**作为常量值,而是硬编码在 `run_backtest()` 回落逻辑内(可读性 + 避免 DEFAULT 常量与 fixture 路径耦合) | ✅ |
| 0 (M-SPEC) | fixture 路径回落后行为字节级一致 | Story §3 "fixture 单测零回归"约束,意味着回落路径下 `run_backtest()` 输出/行为与 patch 前一致(仅多 2 行 INFO 日志)。**决策**: 回落时 `Path(fixture).exists()` **不**再探测(避免 silent fallback 风险,Story §4 风险 #1),直接使用硬编码 fixture 路径;fixture 单测通过 `config={...}` 显式传入 fixture 路径,绕过探测定完全保持字节级一致 | ✅ |
| 0 (M-SPEC) | `calendar_source` 为真数据时是否直接传 `daily_bars.connect` | Story §2 AC-03 "默认加载该日历"语义模糊 — 可理解为直接传 calendar parquet 文件给 `daily_bars.connect`,或理解为触发 `daily_bars.connect` 后真数据 calendar 作为输入。**决策**: 沿用 v0.3.0 `_generate_inline_calendar()` 中间步骤(L162-168),`calendar_source` 仅作为"日历来源"输入,**不**直接传给 `daily_bars.connect`(因 `daily_bars.connect` 期望 `str` 路径 + v0.3.0 `daily_bars` 内部仍需要 calendar parquet 文件);若真数据 calendar schema 与内联生成兼容(L91-98 `{date, is_open, prev}`),后续 v0.5.4+ 可优化跳过内联生成(本 spec Out-of-Scope) | ✅ |
| 0 (M-SPEC) | 来源标记 `"real-data | fixture"` | Story §2 明确"启动 INFO 日志一次性输出选定路径 + `real-data | fixture` 来源标记";AC-01/AC-02 仅用 `"real-data store"` / `"fixture store"` 二元标记。**决策**: FR-0100 标记规则 = `{"real-data store", "fixture store"}`(store_path) + `{"real-data calendar", "fixture calendar"}`(calendar_source),与 EARS AC-01~AC-04 对齐;AC-05 日志输出同时含 2 行(store + calendar) | ✅ |
| 0 (M-SPEC) | `config` 显式提供路径时是否探测 | Task description 未明确 `config` 显式提供路径时是否触发 `Path.exists()` 探测。**决策**: `config` 显式提供路径时**不**触发探测(单测 fixture 路径可能在 CI 环境不存在,触发探测会破坏 fixture 单测零回归);标记按路径字面值判定 — 含 `"fixtures/"` 子串 → fixture,否则 → real-data(此规则可配置 monkeypatch 时临时覆盖,例如显式传入 `.quantide/` 子串路径但实际是测试 fixture → 标记 real-data;此为可接受语义,因显式 config 意图清晰) | ✅ |
