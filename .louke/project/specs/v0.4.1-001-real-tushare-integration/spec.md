---
status: draft
locked: true
locked-at: 2026-07-21T11:00:37Z
locked-by: lk agent sage record-lock
---
# v0.4.1 — QuantideDataLoader 真数据接入 + Smoke Test — Spec

- **Spec ID**: v0.4.1-001-real-tushare-integration
- **Created**: 2026-07-21
- **Status**: Draft
- **关联 story**: `.louke/project/specs/v0.4.1-001-real-tushare-integration/story.md`
- **继承基线**:
  - v0.4.0 FR-0100 (QuantideDataLoader adapter — `fetch_bars` 桥接) — **本 spec 行 19-22 显式反转**:v0.4.0 行 63 "不实例化 TushareFetcher / 不用 TUSHARE_TOKEN / 不发网络 IO" → v0.4.1 兑现
  - v0.4.0 NFR-0100 (函数级 lazy import + 数据 fetcher 业务符号白名单) — **白名单保持**:仅允许 `quantide.data.fetchers.tushare.*`(`TushareFetcher` / `fetch_bars` / **`fetch_calendar`** / `fetch_adjust_factor` / `fetch_stock_list` 等),**不**额外放行 `quantide.data.models.calendar.*`(Round 1 偏差后维持 v0.4.0 白名单边界,见 Clarification Log)

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。
> 验收标准 (可观察、可断言的通过条件) 放在 `acceptance.md` 中。
> 测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。
>
> **北极星目标**: 用户本地持有 `TUSHARE_TOKEN` 时,执行 `pytest tests/smoke/test_real_tushare_smoke.py -v` 一次跑通 3 stocks × 60 trading days end-to-end — `QuantideDataLoader` 实例化 `TushareFetcher` 走真实抓取 + **`fetch_calendar(start_epoch)` 模块级函数**取交易日历 + 截取**最后 `count` 个 ≤ end_date 的真实交易日** → 替换 `pandas.bdate_range` → 数据落 v0.3.0 `DailyBarsStore` → `BacktestRunner.run()` 返回 NAV 曲线非空。CI 无 token 时同文件改 mock `TushareFetcher` 跑同一断言,全绿。
>
> **关键约束 (继承 v0.4.0 story)**:
> - 工作量保持小 (patch ≤ 1 issue,本 spec 仍拆 FR-0100 / FR-0200 / NFR-0100 三段便于追踪)
> - 隔离承诺:v0.4.0 NFR-0100 函数级 lazy import 模式保留;**白名单维持** v0.4.0 边界 — 仅放行 `quantide.data.fetchers.tushare.*`,**不**放行 `quantide.data.models.calendar.*` (Round 1 偏差说明见 Clarification Log)
> - token 永**不**落盘 — smoke 输出落 `tests/smoke/output/` (gitignore),`.env*` gitignore
> - 不做 CLI / scheduler / 可视化 (Out-of-Scope,见 Story §3.2)

## User Stories

### US-0010

story: 作为一名量化研究员,我希望 `QuantideDataLoader` 在传入 `TUSHARE_TOKEN` 时通过 `quantide.data.fetchers.tushare.TushareFetcher()` 真正实例化并调用,同时用 `quantide.data.fetchers.tushare.fetch_calendar(start_epoch)` 模块级函数取交易日历并截取最后 `count` 个 ≤ end_date 的真实交易日,来替换 `pandas.bdate_range` 的 CN 假期近似 —— 不依赖 `quantide.data.models.calendar.Calendar.get_frames_by_count()`(后者存在内部 bug,见 Clarification Log Round 1),从而使 v0.4.0 留尾的"真数据通路"在本 patch 闭环 —— 不再需要 mock `fetch_bars` 才能跑通单测,真实 token 一次能拉到带正确 CN 假期剔除的交易日序列。
priority: P0

### US-0020

story: 作为一名量化研究员,我希望有一个 end-to-end smoke test (`tests/smoke/test_real_tushare_smoke.py`) 在我有 `TUSHARE_TOKEN` 时拉 3 支 A 股 (000001.SZ / 600519.SH / 000858.SZ) × 60 交易日,落 v0.3.0 `DailyBarsStore`,跑 `BacktestRunner.run()` 并断言 NAV 曲线非空 —— token 缺失则 `pytest.skip`,CI 用 mock `TushareFetcher` 跑同一断言 —— 从而验证"真数据通路"在真 token 下端到端跑通,而不仅仅是 mock 跑通。
priority: P0

## Usage Scenarios

### scenario-0010 本地真 token E2E 跑通

1. 开发者设置 `export TUSHARE_TOKEN=xxx`(token 经 `os.environ` 注入,不落盘)。
2. 开发者执行 `pytest tests/smoke/test_real_tushare_smoke.py -v`。
3. `QuantideDataLoader.__init__(token=None)` 内部读取 `os.environ.get('TUSHARE_TOKEN')` 得到 token;token 缺失则抛 `RuntimeError("TUSHARE_TOKEN environment variable is required for QuantideDataLoader; set it before running smoke tests")`(不静默退化)。
4. `QuantideDataLoader.get_daily(asset, end_date, count)` 在函数体内 lazy import `quantide.data.fetchers.tushare.TushareFetcher`,实例化 `TushareFetcher(token=<token>)`(NFR-0100 沿用函数级 lazy import)。
5. 调**模块级 `quantide.data.fetchers.tushare.fetch_calendar(start_epoch)`**(已验证可用,替代有内部 bug 的 `Calendar.get_frames_by_count`)获取交易日历 → 取**最后 `count` 个 ≤ end_date 的真实交易日**(CN 假期已剔除),返回 list[date];`start_epoch` 选为早于 `end_date - count*2` 的日期以确保截取窗口足够覆盖 `count` 个交易日。
6. 调 `fetcher.fetch_bars(dates)`(或模块级 `fetch_bars(dates)`,路径与 v0.4.0 一致)拿到 `(pd.DataFrame, errors)`,沿用 v0.4.0 列重命名(`ts_code → asset` / `trade_date → date` / `vol → volume`),按 `asset` 过滤 + 限制 ≤ count 行,转 `pl.DataFrame` 返回。
7. smoke test 用 3 个 asset × 60 天循环 fetch → 落 `tests/smoke/output/daily_bars_store/` (v0.3.0 schema) → `BacktestRunner.run(strategy_cls=..., config={...}, start_date, end_date, initial_cash)` → 断言 `result.nav.height > 0` 且至少 1 条 NAV 记录。
8. `TUSHARE_TOKEN` 未设置时,smoke test `pytest.skip("TUSHARE_TOKEN not set; skipping real Tushare E2E")` 而非抛 `RuntimeError`(smoke 层捕获 loader 抛出的 token 错误并 skip)。

### scenario-0020 CI mock `TushareFetcher` 跑同一断言

1. CI 环境无 `TUSHARE_TOKEN`(或 CI 故意不注入)。
2. smoke test 通过 `monkeypatch` 或 fixture 替换 `quantide.data.fetchers.tushare.TushareFetcher` 为 mock 类,mock 实现返回固定的 polars OHLCV fixture(60 天 × 3 资产)。
3. mock 模式下走 `get_daily` → `fetch_bars(dates)` 拿到 fixture → 落 store → `BacktestRunner.run()` → 断言 NAV 非空。
4. CI 跑 `pytest tests/smoke/test_real_tushare_smoke.py -v` 全绿。
5. **mock 不绕过 token 门控**:如果 CI 故意不注入 token,`QuantideDataLoader.__init__` 仍抛 `RuntimeError`,smoke test 在调用前 `pytest.skip`,**不**进入 mock 路径(token 门控是 loader 的契约,不是 smoke 的契约)。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表 (Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100 / FR-0200** 两条 P0 FR + **NFR-0100** 一条 NFR;起始 100 间隔。4 位补零,锁定后不改 ID,deprecated 时 Valid=❌ + 备注。
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
### FR-0100 QuantideDataLoader 真数据接入 — TushareFetcher 实例化 + `fetch_calendar` 替换 pandas.bdate_range

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模块路径:`src/trader_off/data/quantide_adapter.py`(继承 v0.4.0,本 FR 修改既有 `QuantideDataLoader` 类)。
- **token 门控**:
  - `QuantideDataLoader.__init__(self, token: str | None = None)` —— `token=None` 时内部读 `os.environ.get('TUSHARE_TOKEN')`。
  - 读取结果为 `None`(即 env 中也未设置),抛 `RuntimeError("TUSHARE_TOKEN environment variable is required for QuantideDataLoader; set it before running smoke tests")`,**不**静默退化为 mock / 合成数据,**不**发起任何网络 IO。
  - `token` 参数显式传入时优先使用(允许测试或特殊场景显式注入,不强制走 env)。
- **TushareFetcher 实例化**(**反转 v0.4.0 FR-0100 行 63**):
  - `QuantideDataLoader.get_daily` 内部函数级 lazy import `from quantide.data.fetchers.tushare import TushareFetcher`(NFR-0100 函数级 lazy import 沿用)。
  - 实例化 `fetcher = TushareFetcher(token=self._token)`(v0.4.0 行 63 明确禁止,本 FR 兑现)。
  - **真实路径**:数据通过 `fetcher.fetch_bars(dates)` 抓取(沿用 v0.4.0 `fetch_bars` 调用契约,**不**用 `fetch_bars` 模块级函数)。
- **`fetch_calendar` 替换 pandas.bdate_range**(**v0.4.0 行 22 留尾兑现 / Round 1 偏差**):
  - 删除 `_compute_trade_dates` 中 `pd.bdate_range(end_date - timedelta(days=count*2), end_date)` 调用(原 v0.4.0 实现,该近似不识别 CN 假期)。
  - 函数级 lazy import `from quantide.data.fetchers.tushare import fetch_calendar`(注:**模块级**函数,非 `TushareFetcher` 实例方法;与 `TushareFetcher` 同属于 `quantide.data.fetchers.tushare` 子树,NFR-0100 白名单内零冲突)。
  - **不**导入 `quantide.data.models.calendar.Calendar` / `FrameType` —— `Calendar.get_frames_by_count()` 在真实数据上有 pyarrow `pc.sum` TypeError 内部 bug(Round 1 偏差说明),改用 `fetch_calendar(start_epoch)` 模块级函数(已验证可用)。
  - 调用 `fetch_calendar(start_epoch)` 获取交易日历,其中 `start_epoch` 选择早于 `end_date - count * 2` 的日期(如 `end_date - timedelta(days=count*3)` 或更早),确保返回窗口足够覆盖 `count` 个真实交易日(CN 假期已剔除);返回结构以 quantide 源码为准(若 `fetch_calendar` 返回 `pd.DataFrame` / `list[date]` / 其他,需在实现时断言类型并截取)。
  - 从返回的交易日历中**截取最后 `count` 个 ≤ end_date 的真实交易日**(允许窗口超出,取末尾);返回 list[date] 用于 `fetch_bars(dates)`。
  - 若 `fetch_calendar(start_epoch)` 签名/返回结构与本 FR 描述不符,以 quantide 源码为准并在 Clarification Log 记录。
  - **不保留** `pandas.bdate_range` 任何路径(防止双路径漂移),`_compute_trade_dates` 重命名为 `_compute_real_trade_dates`(语义从"近似交易日"变"真实交易日")。
- **沿用 v0.4.0 契约**:
  - `async def get_daily(self, asset: str, end_date: date, count: int) -> pl.DataFrame` 签名不变。
  - 返回 `pl.DataFrame` schema 与 v0.4.0 一致(`asset/date/open/high/low/close/volume/turnover/adj_factor`)。
  - 列重命名(`ts_code → asset` / `trade_date → date` / `vol → volume`)+ `amount → turnover` + `adj_factor` 默认 1.0 + 限制 ≤ count 行 —— 全部沿用 v0.4.0 `_to_polars_ohlcv` 实现,**不重写**。
  - `errors` 列表非空仅 `loguru.logger.warning`,**不**抛异常,不破坏 `DataLoader.get_history` 接口稳定。
- **不修改** `src/trader_off/data/loader.py`(`DataLoader.get_history` 签名/行为零改动)。
- **不接入** CLI / scheduler / paper trading / live trading(Out-of-Scope 继承 Story §3.2)。

---

<a id="fr-0200"></a>
### FR-0200 End-to-end smoke test — 真 token 拉 3 stocks × 60 交易日 + 落 DailyBarsStore + BacktestRunner.run + NAV 非空

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 测试文件路径:`tests/smoke/test_real_tushare_smoke.py`(新建,smoke 目录继承 v0.4.0 测试结构)。
- **测试用例设计**(`pytest`-style function,允许 1 个或多个):
  - **真 token 路径**(本地手动跑):
    - 给定:`os.environ['TUSHARE_TOKEN']` 已设置。
    - 当:`QuantideDataLoader().get_daily(asset, end_date, count=60)` 对 3 个资产 (`000001.SZ` / `600519.SH` / `000858.SZ`) 循环调用。
    - 那么:每次返回 `pl.DataFrame`,行数 ≤ 60 且 ≥ 1(允许节假日窗口返回 < 60 行,只要至少有 1 条记录);列 schema 与 FR-0100 一致。
  - **End-to-end 落库 + 回测**(同一 test 或 split):
    - 给定:3 资产的 daily bars 已 fetch。
    - 当:数据按 v0.3.0 `DailyBarsStore` schema 写入临时 `tmp_path/daily_bars_store/`(年分区 parquet,`{date, asset, ohlc struct, volume, adj_factor}`);`BacktestRunner.run(strategy_cls=BaseStrategy_compat, config={...}, start_date, end_date, initial_cash=100000)` 委托运行。
    - 那么:`result.nav.height > 0`,且至少含 1 条 NAV 记录(`nav` 为 polars DataFrame 含 `date` / `nav` 列,行数 ≥ 1)。
    - **不**断言具体 NAV 数值(真数据波动大,只断"非空"以避免脆弱)。
  - **token 缺失路径**(`pytest.skip`):
    - 给定:`os.environ` 中无 `TUSHARE_TOKEN`。
    - 当:同 test 启动。
    - 那么:smoke test 在调用 `QuantideDataLoader()` 之前 `pytest.skip("TUSHARE_TOKEN not set; skipping real Tushare E2E")`,**不**抛 `RuntimeError`(smoke 层捕获 loader 抛出的 token 错误并 skip,token 门控是 loader 的契约;smoke 层只 skip)。
  - **CI mock 路径**(`TushareFetcher` mock):
    - 给定:CI 环境无 token。
    - 当:smoke test 通过 `monkeypatch` 或 fixture 用 mock 类替换 `quantide.data.fetchers.tushare.TushareFetcher`(mock 实现返回固定 60 天 × N 资产 OHLCV fixture)。
    - 那么:走 `get_daily` → mock `fetch_bars(dates)` 拿到 fixture → 落 store → `BacktestRunner.run()` → 断言 NAV 非空,断言**全绿**。
    - mock 模式下 token 仍可缺失(smoke 入口 skip),也可注入占位符 token 以走通 mock 路径(具体由 smoke 实现决定,**不**强制)。
- **Token 安全**:
  - smoke 输出落 `tests/smoke/output/` (gitignore,新增条目 `tests/smoke/output/` 到 `.gitignore`)。
  - smoke 落盘产物 (parquet / 日志) **禁止 echo token**;`.env*` 已在 gitignore(继承 v0.4.0)。
  - 测试失败时 traceback **禁止** 打印 token 值。
- **CI 兼容性**:
  - smoke test 在 CI 默认 runner 上无 token,通过 mock 路径跑同一断言。
  - mock `TushareFetcher` 的 fixture 与真路径**断言一致**(同 AC):3 资产 × 60 天 → store → runner → NAV 非空;mock 不绕过核心契约。
- **不接入** `trader_off data sync` CLI、不接入 scheduler(Out-of-Scope 继承 Story §3.2)。

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR,此处省略。

<a id="nfr-0100"></a>
### NFR-0100 函数级 lazy import — 白名单维持 v0.4.0 边界 (Round 1 偏差:不放行 `quantide.data.models.calendar.*`)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **隔离承诺 (继承 v0.4.0 NFR-0100 边界,Round 1 偏差后维持)**: `src/trader_off/data/quantide_adapter.py` 模块顶层(含 `import` 块、`from ... import` 块、类体、`if TYPE_CHECKING` 块、`__init__` 方法体、模块级 docstring 示例代码)**不**出现 `import quantide` 或 `from quantide ...` 语句。
- 所有 `quantide` 导入必须位于 `def` / `async def` 函数体内;导入时机为首次调用(如 `QuantideDataLoader.get_daily` 内部 `from quantide.data.fetchers.tushare import TushareFetcher, fetch_calendar` —— **仅** `quantide.data.fetchers.tushare` 子树下的两个符号,**不**导入 `quantide.data.models.calendar.*`)。
- **业务符号白名单维持 (Round 1 偏差后,本 spec 锁定)**:
  - 允许 import `quantide.data.fetchers.tushare.*` (沿用 v0.4.0,含 `TushareFetcher` / **`fetch_calendar`** / `fetch_bars` / `fetch_adjust_factor` / `fetch_stock_list`)。
  - **不放行** `quantide.data.models.calendar.*` (Round 1 偏差:原计划放行 `Calendar` / `FrameType` / `get_frames_by_count`,因 `Calendar.get_frames_by_count()` 真实数据触发 pyarrow `pc.sum` TypeError,改用 `quantide.data.fetchers.tushare.fetch_calendar(start_epoch)` 模块级函数,该符号本就在 v0.4.0 白名单内,无需扩展)。
  - **禁止** import `quantide.service.*` / `quantide.portfolio.*` / `quantide.backtest.*` / `quantide.core.scheduler.*` 等非数据 fetcher 的 quantide 模块(与 v0.3.1 NFR-0101 / v0.4.0 NFR-0100 业务符号白名单范围保持一致)。
- **验证 1 (模块顶层)**: `grep -rn "^import quantide\|^from quantide" src/trader_off/data/quantide_adapter.py` 应无匹配。
- **验证 2 (非白名单业务符号)**: `grep -rnE "quantide\.(service|portfolio|backtest|core\.scheduler|models\.calendar)" src/trader_off/data/quantide_adapter.py` 应无匹配。
- **验证 3 (函数级 import 存在性)**: `grep -rn "from quantide" src/trader_off/data/quantide_adapter.py` 至少 1 个匹配(`from quantide.data.fetchers.tushare import TushareFetcher, fetch_calendar`),证明实际接入了 quantide 子模块。
- **验证 4 (AST 校验)**: Python AST 解析(`ast.parse` + 遍历 `ast.ImportFrom` / `ast.Import`)`quantide_adapter.py`,所有 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点的祖先链必须含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 import。
- **验证 5 (集成层影响)**: `grep -rn "^import quantide\|^from quantide" src/trader_off/data/` 除本 spec 既有 `quantide_adapter.py` 外应无其他匹配(即 `DataLoader` 模块本身仍零 quantide 顶层 import,隔离承诺延续 v0.3.0 NFR-0200 / v0.3.1 NFR-0101 / v0.4.0 NFR-0100 的 compat shim 模式)。
- v0.3.0 NFR-0200 / v0.3.1 NFR-0101 / v0.4.0 NFR-0100 对其他模块的隔离承诺保持通过,本 NFR-0100 仅约束 `quantide_adapter.py` 模块。

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|
| 0 (Story M-STORY) | v0.4.0 FR-0100 行 63 "不实例化 TushareFetcher / 不用 TUSHARE_TOKEN / 不发网络 IO" | v0.4.1 显式反转兑现,本 spec FR-0100 内记录"反转 v0.4.0 FR-0100 行 63" | ✅ |
| 0 (Story M-STORY) | v0.4.0 NFR-0100 业务符号白名单 `quantide.data.fetchers.tushare.*` | **Round 1 偏差后维持**:不放行 `quantide.data.models.calendar.*`(原计划延伸因 `Calendar.get_frames_by_count` 内部 bug 撤销);仅使用 `quantide.data.fetchers.tushare.fetch_calendar(start_epoch)`(原白名单内符号)。本 spec NFR-0100 内记录"白名单维持" | ✅ |
| 0 (Story M-STORY) | Out-of-Scope | 不做 CLI / scheduler / 可视化 / token 管理(刷新/轮换/加密落盘) | ✅ |
| 0 (Story M-STORY) | `TushareFetcher` vs 模块级 `fetch_bars` 二选一 | v0.4.0 spec 已锁定为模块级 `fetch_bars`,本 spec FR-0100 兑现"实例化 TushareFetcher + fetch_bars"为真数据路径,但保留 v0.4.0 模块级 `fetch_bars` 调用契约(列重命名/Schema 不变);真数据经由 `TushareFetcher.fetch_bars(dates)` 实例方法 | ✅ |
| 0 (User 2026-07-21) | Story §6 Human 确认 | 分流结论 Go / 行 63 反转认同 / NFR-0100 白名单延伸认同 / Out-of-Scope 认同 | ✅ |
| 0 (M-SPEC) | token 缺失时的 smoke 行为 | `QuantideDataLoader.__init__` 抛 `RuntimeError`(不静默退化);smoke test 在 loader 之前 `pytest.skip`(smoke 层契约);token 门控是 loader 契约,**不**绕过 | ✅ |
| 0 (M-SPEC) | mock 路径是否绕过 token 门控 | mock 不绕过 token 门控;smoke 入口 skip 后**不**进 mock,或显式注入占位符 token 走 mock(由 smoke 实现决定) | ✅ |
| **1 (User 2026-07-21)** | **`Calendar.get_frames_by_count()` 内部 bug 偏差** | `quantide.data.models.calendar.Calendar.get_frames_by_count(end_date, count, FrameType.DAY)` 在真实交易日历上触发 pyarrow `pc.sum` TypeError(quantide 上游已知 bug)。**偏差决策**:改用 `quantide.data.fetchers.tushare.fetch_calendar(start_epoch)` 模块级函数(已验证可用)取交易日历 + 截取最后 `count` 个 ≤ end_date 的真实交易日。**影响**:FR-0100 兑现路径不变(替换 pandas.bdate_range → 真交易日),仅实现 API 切换;**NFR-0100 白名单维持 v0.4.0 边界**,**不**放行 `quantide.data.models.calendar.*`。acceptance.md AC-FR0100-02/03/04 + AC-FR0200-02 + AC-NFR0100-02/04 同步更新引用。 | ✅ |
| 待 M-FOUND | `fetch_calendar(start_epoch)` 真实签名与返回结构 | 在 M-FOUND 阶段读 `quantide.data.fetchers.tushare.fetch_calendar` 源码确认;若签名/返回类型(`pd.DataFrame` / `list[date]` / 其他)与本 FR-0100 描述不符,更新 AC 细节 | ⚠️ [M-FOUND 锁定] |
