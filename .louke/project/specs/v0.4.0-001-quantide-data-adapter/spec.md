---
locked: false
---
# v0.4.0 — Quantide DataLoader Adapter — Spec

- **Spec ID**: v0.4.0-001-quantide-data-adapter
- **Created**: 2026-07-21
- **Status**: Draft

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。
> 验收标准 (可观察、可断言的通过条件) 放在 `acceptance.md` 中。
> 测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。

## User Stories

### US-0010

story: 作为一名量化研究员，我希望 `trader_off.data.DataLoader` 能通过一个薄适配层接入 `quantide.data.fetchers.tushare`，从而在保持现有 `await loader.get_history(asset, end_date, count)` 接口不变的前提下，由适配器把 `(asset, end_date, count)` 翻译成 `quantide.data.fetchers.tushare.fetch_bars(dates)` 调用，使 v0.3.0 推迟的 "tushare 真数据接入" 在 v0.4.0 闭环；同时 `quantide` 导入必须全部下沉到函数体，避免模块顶层副作用影响测试与冷启动。
priority: P0

## Usage Scenarios

### scenario-0010

1. 开发者实现 `src/trader_off/data/quantide_adapter.py`，定义 `QuantideDataLoader` 类（持有可选 `fetcher` 参数，缺省时通过函数级 lazy import 拉取 `quantide.data.fetchers.tushare.fetch_bars`）。
2. 现有 `DataLoader.get_history` 在传入 `QuantideDataLoader` 实例作为 fetcher 时，`await loader.get_history(asset, end_date, count)` 走通：调用栈为 `DataLoader.get_history → QuantideDataLoader.get_daily → quantide.data.fetchers.tushare.fetch_bars(dates) → polars.DataFrame`。
3. 单元测试通过 `unittest.mock.patch("quantide.data.fetchers.tushare.fetch_bars")` 或 monkeypatch 替换 fetch_bars 为 fixture-backed 函数，验证 `(asset, end_date, count) → fetch_bars(dates) → polars.DataFrame` 的参数转换与返回过滤（按 asset 过滤 + 限制返回行数 ≤ count）。
4. 模块顶层 `grep -rn "^import quantide\|^from quantide" src/trader_off/data/quantide_adapter.py` 无匹配；AST 验证 `from quantide.data.fetchers.tushare import fetch_bars`（或等价 import）的祖先节点为 `FunctionDef`/`AsyncFunctionDef`。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表 (Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100** 1 条 P0 FR + **NFR-0100** 1 条 NFR;起始 100 间隔,首次复审后按 10 插入。4 位补零,锁定后不改 ID,deprecated 时 Valid=❌ + 备注。
>
> **必读**: FR-XXXX 是该需求唯一 ID,**禁止删除**既有 ID;若 FR 需废弃,改表内 Valid=❌ 并在 Clarification Log 解释。
>
> 引用约定 (AC): 验收标准用 `AC-FRXXXX-YY` 格式 (4 位 FR + 2 位 AC),见 `acceptance.md`。
>
> **元数据表 (3 列)**:
> - Valid (原 yaml `valid`): ✅ = 仍生效,❌ = 已废弃
> - Testable (原 yaml `testability`): ✅ = 可测试/可断言,⚠️ {原因} = 存保留意见
> - Decided (原 yaml `resolved`): ✅ = 用户已确认,⚠️ = 待澄清,❌ = 用户明确拒绝

<a id="fr-0100"></a>
### FR-0100 Quantide DataLoader adapter — `QuantideDataLoader.get_daily` 桥接 `quantide.data.fetchers.tushare.fetch_bars`

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 新建文件：`src/trader_off/data/quantide_adapter.py`（位于 `src/trader_off/data/loader.py` 同目录）。
- 定义类 `QuantideDataLoader`，签名匹配 `DataLoader.get_history` 已有的 fetcher 契约（见 `loader.py` line 49：`await self._fetcher.get_daily(asset, end_date, count)`）：
  - `async def get_daily(self, asset: str, end_date: date, count: int) -> pl.DataFrame`
  - 参数语义与 `DataLoader.get_history` 完全一致：`asset` 为资产代码（如 `"000001.SZ"`），`end_date` 为最末交易日（含），`count` 为最大返回行数（默认 120）。
  - 返回 `polars.DataFrame`，schema 与 `DataLoader.get_history` 缺省路径一致（`asset/date/open/high/low/close/volume/turnover/adj_factor`）；当 `count` 行不可得时可少于 `count` 行，**不**抛异常。
- 内部调用 `quantide.data.fetchers.tushare.fetch_bars(dates)`（函数级 lazy import，详见 NFR-0100）：
  - 由 `count` + `end_date` 反推 `dates` 列表（包含 `end_date` 及之前共 `count` 个日历日候选；过滤到交易日由 `fetch_bars` 上游处理，或在此处用 `pandas.bdate_range(end_date - timedelta(days=count*2), end_date)` 简单近似，**不**调用 quantide calendar，calendar 接入留 v0.4.0+ 后续 backlog）。
  - 接收返回 `(pd.DataFrame, errors)`；将 `ts_code → asset`、`trade_date → date`、`vol → volume` 列重命名，按 `asset == <input asset>` 过滤，限制返回行数 ≤ `count`，转换为 `pl.DataFrame`。
  - `errors` 列表非空时通过 `loguru.logger.warning` 记录（不抛异常；不向调用方泄漏 fetch 错误细节，DataLoader 接口未定义错误传播）。
- 不实例化 `TushareFetcher`（不动其 `__init__` / `self.pro = ts.pro_api()` 网络路径）；不读取 / 使用 `TUSHARE_TOKEN`；不发起任何实际网络 IO。`fetch_bars` 路径在测试中通过 mock 替换。
- **不**改 `DataLoader` 现有签名 / 行为；本 FR 仅新增文件 `quantide_adapter.py`。
- **不**接入 CLI（无 `trader_off data sync` 命令新增/改动）。
- **不**接入 paper trading / live trading；adapter 仅作为 fetcher 候选实现存在。
- 模块导出：`QuantideDataLoader`（一个类，无其他公共 API）；不需要 `__all__`。

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR,此处省略。

<a id="nfr-0100"></a>
### NFR-0100 `quantide_adapter` 模块顶层零 `import quantide` — 函数级 lazy import + 数据 fetcher 业务符号白名单

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 隔离承诺（用户确认 2026-07-21，继承 v0.3.1 NFR-0101 函数级 lazy import 模式）：`src/trader_off/data/quantide_adapter.py` 模块顶层（含 `import` 块、`from ... import` 块、类体、`if TYPE_CHECKING` 块、`__init__` 方法体、模块级 docstring 示例代码）**不**出现 `import quantide` 或 `from quantide ...` 语句。
- 所有 `quantide` 导入必须位于 `def` / `async def` 函数体内；导入时机为首次调用（如 `QuantideDataLoader.get_daily` 内部 `from quantide.data.fetchers.tushare import fetch_bars`），延迟到运行时执行。
- 业务符号白名单（本文件专用）：本 adapter 的目的即为包装 quantide 数据 fetcher，因此允许 import `quantide.data.fetchers.tushare` 及其内部函数（`fetch_bars` / `fetch_adjust_factor` / `fetch_stock_list` 等本次实际用到的）；**禁止** import `quantide.service.*` / `quantide.portfolio.*` / `quantide.backtest.*` / `quantide.core.scheduler.*` 等非数据 fetcher 的 quantide 模块（与 v0.3.1 NFR-0101 业务符号白名单范围保持一致：`data.*` 在 scheduler adapter 中禁止，但在 data adapter 中是允许的；其余业务符号继续禁止）。
- 验证 1（模块顶层）：`grep -rn "^import quantide\|^from quantide" src/trader_off/data/quantide_adapter.py` 应无匹配。
- 验证 2（非白名单业务符号）：`grep -rnE "quantide\.(service|portfolio|backtest|core\.scheduler)" src/trader_off/data/quantide_adapter.py` 应无匹配。
- 验证 3（函数级 import 存在性）：`grep -rn "from quantide" src/trader_off/data/quantide_adapter.py` 至少 1 个匹配，证明实际接入了 quantide。
- 验证 4（AST 校验）：Python AST 解析（`ast.parse` + 遍历 `ast.ImportFrom` / `ast.Import`）`quantide_adapter.py`，所有 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点的祖先链必须含 `FunctionDef` / `AsyncFunctionDef`，无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 import。
- 验证 5（集成层影响）：`grep -rn "^import quantide\|^from quantide" src/trader_off/data/` 除本 FR 新增文件外应无其他匹配（即 DataLoader 模块本身仍零 quantide 顶层 import，隔离承诺延续 v0.3.0 NFR-0200 / v0.3.1 NFR-0101 的 compat shim 模式）。
- v0.3.0 NFR-0200 / v0.3.1 NFR-0101 对其他模块的隔离承诺保持通过，本 NFR-0100 仅约束本 spec 新增的 `quantide_adapter.py` 模块。

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|
| 0 (Story) | M-STORY | 原始 story 提到 "Define the adapter layer that bridges DataLoader and quantide's fetcher interface / Handle date ranges, symbol filtering, and field selection consistently / Maintain backward compatibility" | ⚠️ [M-SPEC 锁定] |
| 0 (User 2026-07-21) | M-SPEC Step 1 | **范围圈定 (用户决策)**：本 spec 仅产出 1 个文件 `src/trader_off/data/quantide_adapter.py`，类 `QuantideDataLoader`；FR-0100 单一 FR + NFR-0100 函数级 lazy import；不实例化 TushareFetcher / 不使用 TUSHARE_TOKEN / 不发网络请求 / 不接 CLI / 不接 paper/live trading | ✅ |
| 0 (User 2026-07-21) | M-SPEC Step 1 | **接口契约确认 (用户决策)**：adapter 暴露 `async def get_daily(asset, end_date, count) -> pl.DataFrame`，与 `DataLoader.get_history` line 49 的 `await self._fetcher.get_daily(asset, end_date, count)` 完全对齐 | ✅ |
| 0 (User 2026-07-21) | M-SPEC Step 1 | **NFR-0100 隔离承诺 (用户决策)**：继承 v0.3.1 NFR-0101 函数级 lazy import 模式；模块顶层零 `import quantide`；业务符号白名单适配本 adapter 用途，仅放行 `quantide.data.fetchers.tushare.*`，其余业务模块维持禁止 | ✅ |
| 0 (M-SPEC) | 本 spec | **`fetch_bars` 调用契约 (Sage 提议，用户确认)**：`get_daily` 内部由 `count + end_date` 反推 `dates` 列表（用 `pandas.bdate_range(end_date - timedelta(days=count*2), end_date)` 近似交易日序列，**不**调用 quantide calendar），将返回的 `(pd.DataFrame, errors)` 重命名 `ts_code → asset` / `trade_date → date` / `vol → volume`，按 `asset` 过滤并限制行数 ≤ `count`，转 `pl.DataFrame` 返回 | ✅ |
| 0 (M-SPEC) | 本 spec | **错误处理 (Sage 提议，用户确认)**：`fetch_bars` 返回的 `errors` 列表非空时仅 `logger.warning` 记录，不抛异常 / 不返回错误元组，保持 `DataLoader.get_history` 的"返回 DataFrame"接口稳定 | ✅ |
