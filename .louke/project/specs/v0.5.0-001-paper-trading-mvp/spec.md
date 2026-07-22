---
status: draft
---
# v0.5.0 — paper-trading MVP（用 PaperBroker 替换 BacktestBroker）— Spec

- **Spec ID**: v0.5.0-001-paper-trading-mvp
- **Created**: 2026-07-22
- **Status**: Draft
- **关联 story**: `.louke/project/specs/v0.5.0-001-paper-trading-mvp/story.md`
- **继承基线**:
  - v0.3.0 STR-0001（FR-0500 `run_backtest` 委托 `quantide.service.runner.BacktestRunner`、AC-03 `daily_bars.connect`、AC-06 输出 6 键 schema、NFR-0200 compat shim / 函数级 import）—— 本 spec **并列新增** paper 路径，**不**改 `run_backtest`。
  - v0.3.1 STR-0002（QuantideSchedulerAdapter 不破）—— 本 spec 不涉及 scheduler 路径。
  - v0.4.1 STR-0003（NFR-0100 函数级 lazy import 白名单 `quantide.data.fetchers.tushare.*` 仅约束 `data/quantide_adapter.py`）—— 本 spec NFR-0100 约束 **`backtest/runner.py`**，白名单为 v0.3.0 既有集合 + 新增 `PaperBroker`（详见 NFR-0100）。

> **职责切分**: 本文档只描述需求本身（FR/NFR 描述 + 元数据）。
> 验收标准（可观察、可断言的通过条件）放在 `acceptance.md` 中。
> 测试计划（`test-plan.md`）同时引用本文件与 `acceptance.md` 作为输入。
>
> **北极星目标**: 一次 CLI 调用 `trader-off paper-trade --strategy optimized_topk --end 2026-07-21 --capital 1000000` 产出 paper NAV 曲线 + 持仓 + 成交记录 + sqlite 持久化账户状态，**不**修改任何策略代码（`LGBMTop20Strategy` / `OptimizedTopKStrategy`），**不**经 `BacktestRunner`（绕开其内部硬编码的 `BacktestBroker`），改用 `PaperBroker` + `PaperBrokerAdapter` + session-style loop 驱动。
>
> **关键约束（继承 + 本 spec 新增）**:
> - 工作量保持小（patch ≤ 2 issue；本 spec 拆 FR-0100 / FR-0200 / NFR-0100 三段便于追踪）。
> - 隔离承诺：`backtest/runner.py` 模块顶层零 `quantide` import；函数级 lazy import 白名单延伸至 `quantide.service.sim_broker.PaperBroker`（+ 推行情所需的 `quantide.core.message.msg_hub` / `quantide.core.enums.Topics`，见 NFR-0100 ⚠️ 内联讨论）。
> - 策略层零改动（AC-06）：通过新增 `PaperBrokerAdapter` 把 `PaperBroker` 适配为策略期望的 `BacktestBroker` 接口（`total_asset()` / `market_value()` / `positions-as-dict`），**不**改 `LGBMTop20Strategy` / `OptimizedTopKStrategy`。
> - `TUSHARE_TOKEN` 仍为数据源前置依赖（继承 v0.4.1）；token 永**不**落盘。
> - 不做 live / cron scheduler / Web UI / multi-portfolio / risk limits / intraday（Out-of-Scope，见 Story §3.2）。

## User Stories

### US-0010

story: 作为一名量化研究员，我希望调用 `run_paper_trade(strategy_name, end_date, initial_cash)` 时，系统用 `quantide.service.sim_broker.PaperBroker`（本地撮合 + sqlite 持久化）替代 `BacktestBroker`（历史回放撮合），复用 v0.3.0 的 `daily_bars` 单例与 `BaseStrategy_compat` 解析，通过 `PaperBrokerAdapter` + session-style loop 驱动**同一套策略代码**（零改动）在 PaperBroker 上跑出 paper NAV/持仓/成交，从而在不接 live broker 的前提下验证"撮合层从历史回放换成纸面成交"的端到端通路。
priority: P0

### US-0020

story: 作为一名量化研究员，我希望有一个 CLI `trader-off paper-trade --strategy ... --end ... --capital ...`，封装 `run_paper_trade()` 并把结果序列化到 `reports/paper_trade_<ts>/{summary.json, nav_<ts>.parquet, positions_<ts>.parquet, trades_<ts>.parquet}`（schema 沿用 v0.3.0 AC-06 的 6 键 + 真实扩展字段），从而一次命令产出可复盘的 paper 交易报告。
priority: P0

## Usage Scenarios

### scenario-0010 本地 paper-trade 跑通

1. 开发者设置 `export TUSHARE_TOKEN=xxx`（token 经 `os.environ` 注入，不落盘）。
2. 开发者执行 `trader-off paper-trade --strategy optimized_topk --end 2026-07-21 --capital 1000000`。
3. `run_paper_trade()` 内函数级 lazy import `PaperBroker` → `db.init(reports/paper_trade_<ts>/paper_state.sqlite)` → `daily_bars.connect(store_path, calendar_store_path)`（与 v0.3.0 同契约）→ 实例化 `PaperBroker(portfolio_id, principal=initial_cash, commission=1e-4)` → 包裹为 `PaperBrokerAdapter` → 解析策略类 → session-style loop 至 `end_date`。
4. session loop 每个交易日：从 `daily_bars` 取当天 bar 组成 quote dict → `msg_hub.publish(Topics.QUOTES_ALL.value, quote)` 触发 `PaperBroker._on_quote_update` 撮合 → 驱动 `strategy.on_day_open(tm)` / `strategy.on_day_close(tm)` + `broker.on_day_open()` / `broker.on_day_close(close_prices)`。
5. `reports/paper_trade_<ts>/` 落 `summary.json`（`total_trades > 0`）+ `nav_<ts>.parquet` + `positions_<ts>.parquet` + `trades_<ts>.parquet` + `paper_state.sqlite`（PaperBroker 持久化账户）。

## Functional Requirements

> **格式约定（必读）**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`（大写、4 位补零）+ {标题} 开头，紧接三列元数据表（Valid / Testable / Decided），再写需求描述；FR 之间用 `---` 分隔。
>
> **编号约定（必读）**: 本 spec 使用 **FR-0100 / FR-0200** 两条 P0 FR + **NFR-0100** 一条 NFR；起始 100 间隔。4 位补零，锁定后不改 ID。
>
> **必读**: FR-XXXX 是该需求唯一 ID，**禁止删除**既有 ID；若 FR 需废弃，改表内 Valid=❌ 并在 Clarification Log 解释。
>
> 引用约定（AC）: 验收标准用 `AC-FRXXXX-YY` 格式（4 位 FR + 2 位 AC），见 `acceptance.md`。
>
> **元数据表（3 列）**:
> - Valid: ✅ = 仍生效，❌ = 已废弃
> - Testable: ✅ = 可测试/可断言，⚠️ {原因} = 存保留意见
> - Decided: ✅ = 用户已确认，⚠️ = 待澄清，❌ = 用户明确拒绝

---

<a id="fr-0100"></a>
### FR-0100 run_paper_trade() 入口 — PaperBroker + PaperBrokerAdapter + session-style loop（绕开 BacktestRunner）

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模块路径：`src/trader_off/backtest/runner.py`（继承 v0.3.0，本 FR 新增 `run_paper_trade` 函数 + `PaperBrokerAdapter` 类，**不**改 `run_backtest`）。
- **函数签名**：`def run_paper_trade(strategy_name: str, end_date: date, initial_cash: float, config: dict | None = None) -> PaperTradeResult`（`config` 透传策略，沿用 v0.3.0 `run_backtest` 的 `store_path` / `calendar_source` / `universe` 键语义；`PaperTradeResult` dataclass 字段：`summary: dict` / `positions: pl.DataFrame` / `trades: pl.DataFrame` / `nav: pl.DataFrame` / `report_dir: Path`，与 v0.3.0 `BacktestResult` 结构一致便于复用序列化）。
- **PaperBroker 实例化（NFR-0100 函数级 lazy import）**:
  - 函数体内 `from quantide.service.sim_broker import PaperBroker`（函数级 lazy，**不**在模块顶层）。
  - 实例化 `PaperBroker(portfolio_id=<uuid>, principal=initial_cash, commission=1e-4)`（构造签名以 `quantide.service.sim_broker.PaperBroker.__init__` 源码为准：`(portfolio_id, principal=1_000_000, commission=1e-4, portfolio_name="simulation", ...)`）。
- **db.init 时序（关键）**:
  - `PaperBroker.__init__()` → `_init_or_sync_state()` → `db.get_portfolio()` 要求 `db` 单例先初始化（与 `BacktestRunner._init_backtest` 的 `db.init(db_path)` 同模式）。
  - `run_paper_trade` 必须在实例化 `PaperBroker` **之前**调用 `from quantide.data.sqlite import db; db.init(str(report_dir / "paper_state.sqlite"))`，其中 `report_dir = reports/paper_trade_<ts>/`。
  - sqlite 每次 run 一个新文件（fresh per run）；**不**做跨 run 复用 / `PaperBroker.load()` 续跑（"供下次接着跑"推迟到 v0.5.1+，Out-of-Scope）。
- **daily_bars 接线（复用 v0.3.0 AC-03）**:
  - 函数体内 `from quantide.data.models.daily_bars import daily_bars` → `daily_bars.connect(store_path, str(tmp_calendar_path))`，store_path 默认 `DEFAULT_STORE_PATH`，calendar 由 `_generate_inline_calendar` 内联生成（与 `run_backtest` Step A/B 同路径，**不**留持久 `calendar_store/`）。
- **PaperBrokerAdapter（AC-06 策略零改动的关键）**:
  - 新增 `PaperBrokerAdapter` 类（位于 `runner.py`），包裹 `PaperBroker` 实例，补齐策略期望的 `BacktestBroker` 接口：
    - `total_asset() -> float`：返回 `PaperBroker.total_assets`（property 适配为方法）。
    - `market_value() -> float`：返回 `sum(pos.mv for pos in paper_broker.positions)`（PaperBroker 无此方法，adapter 计算）。
    - `positions`（property，返回 `dict[str, Position]`）：`{pos.asset: pos for pos in paper_broker.positions}`（PaperBroker 返回 `List[Position]`，adapter 转 dict，供策略 `_reconcile_position_cache` 的 `.keys()` / `[k]` 访问）。
    - `trade_target_pct(asset, target_pct, price=0, order_time=None, timeout=0.5)`（async）：直接 `await self._paper.trade_target_pct(...)` 委托（PaperBroker 已有此 async 方法）。
    - 其余策略未调用的方法（`buy`/`sell`/`buy_percent` 等）由 `__getattr__` 透传给 `PaperBroker`（保持最小适配面）。
  - 策略实例化用 `strategy_cls(adapter, config)`，**不**直接传 `PaperBroker`。
- **绕开 BacktestRunner（路径分叉）**:
  - `run_paper_trade` **不**调用 `quantide.service.runner.BacktestRunner.run(...)`（绕开其 `_init_backtest` 内部硬编码的 `BacktestBroker` 实例化，runner.py L87-95 in quantide）。
  - 改用 session-style loop 自行驱动策略 on `PaperBroker`（经 adapter）。
- **session-style loop（事件驱动撮合）**:
  - 枚举 `daily_bars` store 中 ≤ `end_date` 的交易日（按升序）；枚举方式优先从 `daily_bars` store 直接取可用日期，避免额外 import `calendar`/`FrameType`（若 M-FOUND 确认必须用 `quantide.data.models.calendar.calendar.get_frames`，则该符号加入 NFR-0100 白名单，见 NFR-0100 ⚠️ 内联讨论）。
  - 每个交易日 `d`：
    1. 从 `daily_bars.get_bars_in_range(d, d, assets)` 取当天 bar（`assets` = 当前持仓 ∪ universe），组成 quote dict `{asset: {"lastPrice": close, "open": open, "high": high, "low": low, "volume": volume, "amount": amount}}`。
    2. `from quantide.core.message import msg_hub; from quantide.core.enums import Topics; msg_hub.publish(Topics.QUOTES_ALL.value, quote)` 触发 `PaperBroker._on_quote_update` 撮合待处理订单（PaperBroker 是事件驱动，非历史回放）。
    3. `await broker.on_day_open()` → `await strategy.on_day_open(tm)`（`tm` = `datetime(d.year, d.month, d.day, 9, 30)`）→ 策略 `on_day_open` 内调 `trade_target_pct` 下单 → `await broker.on_day_close(close_prices)`（`close_prices` = 当天收盘价 dict）→ `await strategy.on_day_close(tm_close)`。
  - `PaperBroker._get_today()` 返回真实 `datetime.date.today()`（无模拟时钟 `set_clock`）；持久化按真实今天日期落库（MVP 接受，**不** mock `_get_today`）。
- **返回值**：`PaperTradeResult(summary, positions, trades, nav, report_dir)`，其中 `nav`/`positions`/`trades` 从 `db`（`from quantide.data.sqlite import db`）按 `portfolio_id` 查询（与 `run_backtest` 末段 `db.assets_all` / `db.positions_all` / `db.trades_all` 同模式）；`summary` 含 v0.3.0 AC-06 的 6 键 + 真实 `total_trades`（来自 `trades.height`）/ `avg_turnover`。
- **不接入** CLI / scheduler / live / intraday（Out-of-Scope 继承 Story §3.2）。

---

<a id="fr-0200"></a>
### FR-0200 trader-off paper-trade CLI — 封装 run_paper_trade + 序列化报告

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模块路径：`src/trader_off/cli/paper_trade.py`（新建，CLI 结构继承 `src/trader_off/cli/backtest.py`）。
- **入口函数**：`def main(argv: list[str] | None = None) -> int`（接收 `argv` 便于测试，区别于 `backtest.py` 的 `main()` 无参；`argparse.parse_args(argv)`）。
- **参数（argparse）**:
  - `--strategy`（required）：策略名（`lgbm_top20` / `optimized_topk`），复用 `runner._resolve_strategy_class`。
  - `--end`（default = today，`date.today().isoformat()`）：paper 截止日（YYYY-MM-DD）。
  - `--capital`（default = `1_000_000`，type=float）：初始资金。
  - `--output`（default = `reports/paper_trade_<ts>/`，type=Path）：输出目录（`<ts>` = `_generate_timestamp()`）。
- **注册到 pyproject.toml**：
  - 在 `[project.scripts]` 新增 `trader-off-paper-trade = "trader_off.cli.paper_trade:main"`（当前 `pyproject.toml` 无 `[project.scripts]` 段，本 FR 新增该段）。
- **向后兼容（NFR-1000 / AC-05）**：
  - `python -m trader_off.cli.paper_trade --help` 与 `trader-off paper-trade`（若提供组合命令）均可用；`paper_trade.py` 含 `if __name__ == "__main__": sys.exit(main())`。
- **序列化输出**：
  - 调用 `run_paper_trade(strategy_name=args.strategy, end_date=date.fromisoformat(args.end), initial_cash=args.capital)`，把返回的 `PaperTradeResult` 序列化到 `--output` 目录：
    - `summary.json`（6 键 + 真实扩展字段，沿用 v0.3.0 AC-06 schema）。
    - `nav_<ts>.parquet` / `positions_<ts>.parquet` / `trades_<ts>.parquet`。
  - 打印 `summary.json` 路径 + 关键指标（`total_trades` / NAV 末值）到 stdout（loguru logger）。
- **退出码**（沿用 `backtest.py` 约定）:
  - `0`：成功。
  - `2`：argparse 缺必需参数。
  - `5`：paper 引擎失败（`RuntimeError` / 其它异常，logger.error 后返回 5）。
- **不接入** `trader-off backtest` 已有 CLI（两条路径并列，互不修改）。

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR，此处省略。

<a id="nfr-0100"></a>
### NFR-0100 函数级 lazy import — 白名单延伸至 quantide.service.sim_broker.PaperBroker（+ 推行情所需 core 基础设施）

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ⚠️ |

- **隔离承诺（继承 v0.3.0 NFR-0200 + 本 spec 延伸）**：`src/trader_off/backtest/runner.py` 与 `src/trader_off/cli/paper_trade.py` 模块顶层（含 import 块、`from ... import` 块、类体、`if TYPE_CHECKING` 块、模块级 docstring）**不**出现 `import quantide` 或 `from quantide ...` 语句。
- 所有 `quantide` 导入必须位于 `def` / `async def` 函数体内；导入时机为首次调用。
- **函数级业务符号白名单（`backtest/runner.py`）**:
  - **v0.3.0 既有**（`run_backtest` 已用，本 spec 保持）：`quantide.data.models.daily_bars.daily_bars` / `quantide.service.runner.BacktestRunner`（仅 `run_backtest` 内）/ `quantide.data.sqlite.db`。
  - **v0.5.0 新增**：`quantide.service.sim_broker.PaperBroker`（FR-0100 实例化）。
  - **v0.5.0 新增（推行情所需，⚠️ 待用户确认，见下方内联讨论）**：`quantide.core.message.msg_hub` + `quantide.core.enums.Topics`（FR-0100 session loop 用 `msg_hub.publish(Topics.QUOTES_ALL.value, quote)` 触发 PaperBroker 撮合；二者为 core 基础设施——消息总线 + 枚举，非业务符号 runner/metrics/portfolio）。
  - **不放行**：`quantide.service.metrics` / `quantide.portfolio.*` / `quantide.service.runner`（`run_paper_trade` 内**不**直接 import；`run_backtest` 内的既有 import 保留）/ 其它未列明的 quantide 业务符号。
  - **条件新增（⚠️ 待 M-FOUND 确认）**：若交易日枚举必须用 `quantide.data.models.calendar.calendar.get_frames` + `quantide.core.enums.FrameType`，则这两个符号加入白名单；否则优先从 `daily_bars` store 直接取可用日期，避免该 import。

> **Sage [⚠️ 待确认]:** 你在 Round 1 选了「msg_hub.publish 推行情」（问题2）和「函数级白名单扩 PaperBroker」（问题3）。msg_hub.publish 方案**必然**要求 `run_paper_trade` 函数体内 `from quantide.core.message import msg_hub` + `from quantide.core.enums import Topics`。这两个是 core 基础设施（消息总线 + 枚举），不是业务符号（runner/metrics/portfolio），与 v0.3.1 已放行的 `quantide.core.scheduler.SchedulerManager` 同属 core 层。请确认把 `quantide.core.message.msg_hub` + `quantide.core.enums.Topics` 纳入 `backtest/runner.py` 函数级白名单。另外：交易日枚举若必须用 `quantide.data.models.calendar`，请一并确认是否放行（我倾向优先从 daily_bars store 取日期，避免该 import）。

- **验证 1（模块顶层）**：`grep -rn "^import quantide\|^from quantide" src/trader_off/backtest/runner.py src/trader_off/cli/paper_trade.py` 应无匹配。
- **验证 2（函数级 import 存在性）**：`grep -rn "from quantide" src/trader_off/backtest/runner.py` 至少匹配 `from quantide.service.sim_broker import PaperBroker`（证明 paper 路径实际接入）。
- **验证 3（AST 校验）**：Python AST 解析 `runner.py` 与 `paper_trade.py`，所有 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点的祖先链含 `FunctionDef` / `AsyncFunctionDef`，无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 import。
- **验证 4（非白名单业务符号）**：`grep -rnE "quantide\.(portfolio|service\.metrics)" src/trader_off/backtest/runner.py src/trader_off/cli/paper_trade.py` 应无匹配（`quantide.service.runner.BacktestRunner` / `quantide.service.sim_broker.PaperBroker` 为白名单内，不在此 grep）。
- **验证 5（集成层影响）**：v0.3.0 NFR-0200 / v0.3.1 NFR-0101 / v0.4.1 NFR-0100 对其他模块的隔离承诺保持通过；本 NFR-0100 仅约束 `backtest/runner.py` 与 `cli/paper_trade.py`。

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|
| 0 (Story M-STORY) | Story §2.1 AC-06 "策略零改动 + PaperBroker 实现 AbstractBroker 接口(同 BacktestBroker)，签名兼容" | **代码事实矛盾**：`OptimizedTopKStrategy`/`LGBMTop20Strategy` 调 `self.broker.total_asset()`(方法)/`market_value()`(方法)/`positions`(dict)；`PaperBroker` 只有 `total_assets`(property，无括号)、无 `market_value()`、`positions` 返回 `List`。Story 的"签名兼容"为假。 | ⚠️ → ✅ |
| 1 (User 2026-07-22) | **问题1 策略接口适配** | 用户决策：**新增 `PaperBrokerAdapter` 包装类**，补 `total_asset()`/`market_value()`/`positions-as-dict`，把 PaperBroker 适配为策略期望接口；策略代码零改动，AC-06 成立。adapter 位于 `runner.py`。 | ✅ |
| 1 (User 2026-07-22) | **问题2 行情喂给 PaperBroker** | 用户决策：**msg_hub.publish 推行情**。session loop 每个交易日从 daily_bars 取 bar 组 quote dict，`msg_hub.publish(Topics.QUOTES_ALL.value, quote)` 触发 `PaperBroker._on_quote_update` 撮合。PaperBroker 是事件驱动（非历史回放）。 | ✅ |
| 1 (User 2026-07-22) | **问题3 NFR-0100 白名单边界** | 用户决策：**函数级白名单扩 PaperBroker**。NFR-0100 = runner.py 模块顶层零 quantide import；函数级白名单 = v0.3.0 既有集合(daily_bars/BacktestRunner/db) + 新增 PaperBroker。Story 原文"其余 quantide.service.* 不放行"与现有 run_backtest 冲突（runner.py 现已函数级 import BacktestRunner），已纠正。 | ✅ |
| 1 (User 2026-07-22) | **问题4 db.init + sqlite 路径** | 用户决策：**reports/paper_trade_<ts>/paper_state.sqlite**，fresh per run。run_paper_trade 先 `db.init(path)` 再实例化 PaperBroker。跨 run 复用/PaperBroker.load() 续跑推迟到 v0.5.1+（Out-of-Scope）。 | ✅ |
| 1 (User 2026-07-22) | **问题5 end_date/时钟语义** | 用户决策：**喂 ≤ end_date 的 bar，接受真实 today 落库**。end_date 默认今天；loop 遍历 daily_bars ≤ end_date 的交易日；PaperBroker `_get_today()` 用真实今天落库，MVP 不 mock 时钟。 | ✅ |
| 1 (M-SPEC Sage) | msg_hub/Topics 白名单延伸（问题2 的必然推论） | 问题2 选 msg_hub.publish 必然要求函数级 import `quantide.core.message.msg_hub` + `quantide.core.enums.Topics`。已写入 NFR-0100 白名单但标 ⚠️，待用户在 spec.md 内联讨论确认。 | ⚠️ |
| 1 (M-SPEC Sage) | 交易日枚举 API | 优先从 daily_bars store 直接取可用日期（≤ end_date）避免 import calendar/FrameType；若 M-FOUND 确认必须用 `quantide.data.models.calendar.calendar.get_frames`，该符号加入白名单（⚠️ 内联讨论）。 | ⚠️ |
| 1 (M-SPEC Sage) | Story 行号引用订正 | Story §2.1 称"绕开 BacktestRunner._init_backtest() 内部硬编码的 BacktestBroker 实例化（runner.py L76-82）"。实际：BacktestBroker 实例化在 **quantide** 的 `service/runner.py` L87-95（`_init_backtest`）；trader-off 的 `runner.py` L76-82 是 `_generate_inline_calendar` 的合成前一日逻辑。spec 文本已用准确描述"绕开其 _init_backtest 内部硬编码的 BacktestBroker 实例化"，不引用错误行号。 | ✅ |
| 待 M-FOUND | `PaperBroker.__init__` 真实签名 | 在 M-FOUND 阶段读 `quantide.service.sim_broker.PaperBroker.__init__` 源码确认（已 curl 验证 `(portfolio_id, principal, commission, ...)`）；若签名/默认值与本 FR-0100 描述不符，更新 AC 细节。 | ⚠️ [M-FOUND 锁定] |
| 待 M-FOUND | `daily_bars.get_bars_in_range` 真实签名 | 确认 `(start_date, end_date, assets)` 返回 schema（含 `asset/open/high/low/close/volume/amount`），用于 session loop 组 quote dict。 | ⚠️ [M-FOUND 锁定] |
