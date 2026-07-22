# v0.5.0 — paper-trading MVP（用 PaperBroker 替换 BacktestBroker）— Acceptance Criteria

- **Spec ID**: v0.5.0-001-paper-trading-mvp
- **Created**: 2026-07-22
- **继承基线**: v0.3.0 FR-0500 / NFR-0200、v0.4.1 NFR-0100 的 AC 在本文件中**不重复**；本文件仅定义 v0.5.0 新增的 FR / NFR 的 AC。

> 中央注册表：spec.md 只保留 FR/NFR 描述与元数据（testability/decided/valid）；可观察、可断言的通过条件在本表中。
>
> 编号约定:
> - 每个 FR/NFR 单元内 AC-N 从 1 起，按顺序递增；单元之间不复用
> - 完整 AC 引用：**AC-FRXXXX-YY**（4 位 FR + 2 位 AC 序号），与 test-plan / issue schema 保持一致
> - 标题层级：`## FR-XXXX {title}` 为 level-2；`### AC-N` 为 level-3（其后同一行**不**接任何文字，canonical ID 写在下一行）
>
> Lex 阶段 1/2 审查验证: (1) 本表存在; (2) spec.md 每个 FR/NFR 在本表中有对应章节; (3) 每条 AC 可被测试或断言。
>
> EARS 句式关键词约定：`WHEN`（触发条件）/ `WHILE`（持续状态）/ `WHERE`（前置条件）/ `IF ... THEN`（条件分支）/ `THE 系统 SHALL ...`（系统行为）。

---

<a id="ac-fr-0100"></a>
## FR-0100 run_paper_trade() 入口 — PaperBroker + PaperBrokerAdapter + session-style loop（绕开 BacktestRunner）

### AC-1

AC-FR0100-01

- **WHEN** `run_paper_trade(strategy_name, end_date, initial_cash)` 被调用
- **THEN** 系统 SHALL 在函数体内 lazy import `quantide.service.sim_broker.PaperBroker`（函数级，非模块顶层），并实例化 `PaperBroker(portfolio_id=<uuid>, principal=initial_cash, commission=1e-4)`
- **断言**:
  - 给定：`run_paper_trade("optimized_topk", date(2026, 7, 21), 1_000_000)`，mock `PaperBroker` 构造。
  - 当：函数执行到 broker 实例化。
  - 那么：`PaperBroker` 收到调用，`principal` 参数 == `1_000_000`，`commission` 参数 == `1e-4`；`runner.py` 模块顶层无 `from quantide.service.sim_broker import` 语句（见 NFR-0100 AC-1）。
- **对应 EARS**: Story §2.3 AC-01。

### AC-2

AC-FR0100-02

- **WHEN** `run_paper_trade` 实例化 `PaperBroker` 之前
- **THEN** 系统 SHALL 先调用 `db.init(str(report_dir / "paper_state.sqlite"))`（`report_dir = reports/paper_trade_<ts>/`），使 `db` 单例就绪，否则 `PaperBroker.__init__` → `_init_or_sync_state` → `db.get_portfolio` 会失败
- **断言**:
  - 给定：mock `quantide.data.sqlite.db.init` 与 `PaperBroker.__init__`。
  - 当：`run_paper_trade(...)` 执行。
  - 那么：`db.init` 调用**先于** `PaperBroker` 构造调用（可用调用顺序 mock 断言）；`db.init` 的参数为以 `paper_state.sqlite` 结尾的路径，且前缀含 `reports/paper_trade_`；该路径文件在 run 结束后**存在**（PaperBroker 持久化写入）。
- **对应 EARS**: Story §3.3。

### AC-3

AC-FR0100-03

- **WHEN** `run_paper_trade` 被调用
- **THEN** 系统 SHALL 在调用策略之前完成 `daily_bars.connect(store_path, str(tmp_calendar_path))`（与 v0.3.0 `run_backtest` AC-03 同契约），calendar 由 `_generate_inline_calendar` 内联生成
- **断言**:
  - 给定：mock `daily_bars.connect` 与 `_generate_inline_calendar`。
  - 当：`run_paper_trade(...)` 执行。
  - 那么：`daily_bars.connect` 收到调用且**仅**调用一次，第一参数为 store_path、第二参数为以 `.parquet` 结尾的 calendar 路径；该 calendar 路径文件存在且 schema `{date, is_open, prev}`。
- **对应 EARS**: Story §2.3 AC-02。

### AC-4

AC-FR0100-04

- **WHEN** `run_paper_trade` 被调用
- **THEN** 系统 SHALL **不**调用 `quantide.service.runner.BacktestRunner`（绕开其 `_init_backtest` 内部硬编码的 `BacktestBroker` 实例化），改用 session-style loop 驱动策略 on `PaperBroker`（经 `PaperBrokerAdapter`）
- **断言**:
  - 给定：mock `quantide.service.runner.BacktestRunner` 与 `PaperBroker`。
  - 当：`run_paper_trade(...)` 完整执行。
  - 那么：`BacktestRunner` 构造与 `BacktestRunner.run` **均**未被调用（mock.assert_not_called）；`run_paper_trade` 函数体内**不**出现 `from quantide.service.runner import`（仅 `run_backtest` 内保留既有 import）。
- **对应 EARS**: Story §2.3 AC-03。

### AC-5

AC-FR0100-05

- **WHERE** `PaperBrokerAdapter` 包裹 `PaperBroker` 实例传给策略
- **THEN** 系统 SHALL 暴露策略期望的 `BacktestBroker` 接口：`total_asset()`（方法，返回 `PaperBroker.total_assets`）、`market_value()`（方法，返回 `sum(pos.mv for pos in paper_broker.positions)`）、`positions`（property，返回 `dict[str, Position]`，`{pos.asset: pos for pos in paper_broker.positions}`），且 `LGBMTop20Strategy` / `OptimizedTopKStrategy` 代码零改动（AC-06 策略层不破）
- **断言**:
  - 给定：一个 mock `PaperBroker`，其 `total_assets` 返回 `1_500_000.0`，`positions` 返回 `[Position(asset="000001.SZ", mv=500_000.0), Position(asset="600519.SH", mv=200_000.0)]`。
  - 当：`adapter = PaperBrokerAdapter(mock_paper); adapter.total_asset(); adapter.market_value(); adapter.positions`。
  - 那么：`adapter.total_asset() == 1_500_000.0`（方法可调用，非 property）；`adapter.market_value() == 700_000.0`；`isinstance(adapter.positions, dict)` 且 `set(adapter.positions.keys()) == {"000001.SZ", "600519.SH"}`。
  - 当：`git diff` 比较 `src/trader_off/strategies/lgbm_top20.py` 与 `src/trader_off/strategies/optimized_topk.py` 相对 v0.4.1 基线。
  - 那么：两文件 diff 为空（零改动）；策略 `on_day_open` 内 `self.broker.total_asset()` / `self.broker.market_value()` / `self.broker.positions.keys()` 在 adapter 上不抛 `AttributeError`。
- **对应 EARS**: Story §2.3 AC-06。

### AC-6

AC-FR0100-06

- **WHEN** session loop 处理每个交易日 `d`（≤ `end_date`）
- **THEN** 系统 SHALL 从 `daily_bars.get_bars_in_range(d, d, assets)` 取当天 bar 组成 quote dict，并 `msg_hub.publish(Topics.QUOTES_ALL.value, quote)` 触发 `PaperBroker._on_quote_update` 撮合待处理订单（PaperBroker 事件驱动，非历史回放）
- **断言**:
  - 给定：mock `daily_bars.get_bars_in_range` 返回含 2 资产当天 bar 的 DataFrame（`asset/open/high/low/close/volume/amount`）；mock `msg_hub.publish`；mock `PaperBroker` 已有 1 笔待匹配买单。
  - 当：session loop 跑完交易日 `d`。
  - 那么：`msg_hub.publish` 收到调用，第一参数 == `Topics.QUOTES_ALL.value`，第二参数为 dict 且键集合 == 当天 bar 的 asset 集合，每个值含 `lastPrice`/`open`/`high`/`low`/`volume`/`amount`；`PaperBroker._on_quote_update` 被触发（订单进入撮合）。
- **对应 EARS**: Story §2.3 AC-01/03。

### AC-7

AC-FR0100-07

- **WHEN** `run_paper_trade` 完成
- **THEN** 系统 SHALL 返回 `PaperTradeResult(summary, positions, trades, nav, report_dir)`，其中 `nav`/`positions`/`trades` 从 `db`（`from quantide.data.sqlite import db`）按 `portfolio_id` 查询（`db.assets_all` / `db.positions_all` / `db.trades_all`，与 `run_backtest` 末段同模式），`summary` 含 v0.3.0 AC-06 的 6 键且 `total_trades` 为真实成交数（`trades.height`）
- **断言**:
  - 给定：mock `db.assets_all` 返回非空 NAV 记录，`db.trades_all` 返回 5 行成交。
  - 当：`result = run_paper_trade(...)`。
  - 那么：`isinstance(result, PaperTradeResult)`；`result.nav.height > 0` 且列含 `date`/`nav`；`result.summary["total_trades"] == 5`；`result.summary` 含 6 键 `{annualized_return, sharpe_ratio, max_drawdown, win_rate, total_trades, avg_turnover}`。
- **对应 EARS**: Story §2.3 AC-04。

### AC-8

AC-FR0100-08

- **WHEN** `run_paper_trade` 跑完
- **THEN** 系统 SHALL 在 `reports/paper_trade_<ts>/paper_state.sqlite` 落 PaperBroker 持久化账户状态（fresh per run，新文件），且**不**做跨 run 复用 / `PaperBroker.load()` 续跑
- **断言**:
  - 给定：连续两次 `run_paper_trade(...)` 调用（不同 `<ts>`）。
  - 当：两次 run 完成。
  - 那么：两次产出的 `paper_state.sqlite` 路径**不同**（`<ts>` 不同）；每次 run 前该路径文件不存在或被 fresh 初始化（`PaperBroker.create` 语义，不调 `PaperBroker.load`）。
- **对应 EARS**: Story §3.3。

### AC-9

AC-FR0100-09

- **WHILE** `PaperBroker._get_today()` 返回真实 `datetime.date.today()`
- **THEN** 系统 SHALL 接受 PaperBroker 按真实今天日期落库（持久化 / 成交流水日期为真实今天），**不** mock `_get_today`；end_date 默认为今天，session loop 遍历 daily_bars 中 ≤ end_date 的交易日
- **断言**:
  - 给定：`end_date = date(2026, 7, 21)`，daily_bars store 含 `2026-07-15` 至 `2026-07-21` 共 5 个交易日。
  - 当：`run_paper_trade("optimized_topk", date(2026, 7, 21), 1_000_000)`。
  - 那么：session loop 遍历的交易日集合 == store 中 ≤ `2026-07-21` 的日期（5 个）；`run_paper_trade` 函数体**不**出现对 `PaperBroker._get_today` 的 patch / monkeypatch（grep 源码无 `_get_today` 赋值）。
- **对应 EARS**: Story §2.3 + 问题5 决策。

---

<a id="ac-fr-0200"></a>
## FR-0200 trader-off paper-trade CLI — 封装 run_paper_trade + 序列化报告

### AC-1

AC-FR0200-01

- **WHEN** `trader-off-paper-trade --strategy optimized_topk --end 2026-07-21 --capital 1000000` 被执行
- **THEN** 系统 SHALL 解析参数并调用 `run_paper_trade(strategy_name="optimized_topk", end_date=date(2026,7,21), initial_cash=1_000_000)`
- **断言**:
  - 给定：mock `run_paper_trade` 返回 `PaperTradeResult`。
  - 当：`main(["--strategy", "optimized_topk", "--end", "2026-07-21", "--capital", "1000000"])` 执行。
  - 那么：`run_paper_trade` 收到调用，`strategy_name == "optimized_topk"`，`end_date == date(2026,7,21)`，`initial_cash == 1_000_000.0`；返回 `0`。
- **对应 EARS**: Story §2.3 AC-05。

### AC-2

AC-FR0200-02

- **WHEN** CLI 参数缺省
- **THEN** 系统 SHALL `--end` 默认今天（`date.today().isoformat()`）、`--capital` 默认 `1_000_000`、`--output` 默认 `reports/paper_trade_<ts>/`；`--strategy` 必填
- **断言**:
  - 给定：仅传 `--strategy optimized_topk`。
  - 当：`main(["--strategy", "optimized_topk"])` 执行（mock `run_paper_trade`）。
  - 那么：`run_paper_trade` 的 `end_date == date.today()`，`initial_cash == 1_000_000.0`；输出目录前缀为 `reports/paper_trade_`。
  - 当：`main([])` 执行（缺 `--strategy`）。
  - 那么：argparse 报错缺必需参数，退出码 `2`。
- **对应 EARS**: Story §2.1 FR-0200。

### AC-3

AC-FR0200-03

- **WHERE** `pyproject.toml` 被读取
- **THEN** 系统 SHALL 在 `[project.scripts]` 段含 `trader-off-paper-trade = "trader_off.cli.paper_trade:main"`（当前 `pyproject.toml` 无该段，本 FR 新增）
- **断言**:
  - 给定：`pyproject.toml`。
  - 当：`grep -n "trader-off-paper-trade" pyproject.toml` 执行。
  - 那么：返回 1 行匹配，内容含 `trader_off.cli.paper_trade:main`；`[project.scripts]` 段存在。
- **对应 EARS**: Story §2.1 FR-0200。

### AC-4

AC-FR0200-04

- **WHEN** `run_paper_trade` 返回 `PaperTradeResult`
- **THEN** 系统 SHALL 序列化到 `--output` 目录：`summary.json`（6 键 + 真实扩展字段，v0.3.0 AC-06 schema）+ `nav_<ts>.parquet` + `positions_<ts>.parquet` + `trades_<ts>.parquet`
- **断言**:
  - 给定：`PaperTradeResult`（nav 3 行、positions 2 行、trades 5 行、summary 6 键）。
  - 当：`main([...])` 执行，`--output tmp_path/`。
  - 那么：`tmp_path/summary.json` 存在且 `json.load` 含 6 键；`tmp_path/nav_<ts>.parquet` 读回 `height == 3`；`positions_<ts>.parquet` `height == 2`；`trades_<ts>.parquet` `height == 5`。
- **对应 EARS**: Story §2.3 AC-04。

### AC-5

AC-FR0200-05

- **WHEN** `python -m trader_off.cli.paper_trade --help` 被执行
- **THEN** 系统 SHALL 打印 argparse 帮助并退出码 `0`（向后兼容，NFR-1000 继承 v0.1.0）
- **断言**:
  - 给定：`paper_trade.py` 含 `if __name__ == "__main__": sys.exit(main())`。
  - 当：`python -m trader_off.cli.paper_trade --help` 执行。
  - 那么：stdout 含 `--strategy` / `--end` / `--capital` / `--output`；退出码 `0`。
- **对应 EARS**: Story §2.1 FR-0200 compat。

### AC-6

AC-FR0200-06

- **WHEN** `run_paper_trade` 抛 `RuntimeError` 或其它异常
- **THEN** 系统 SHALL logger.error 记录异常并返回退出码 `5`（沿用 `backtest.py` 约定），**不**向上抛未捕获异常
- **断言**:
  - 给定：mock `run_paper_trade` 抛 `RuntimeError("paper engine down")`。
  - 当：`main([...])` 执行。
  - 那么：返回 `5`；`logger.error` 被调用；无未捕获异常冒泡。
- **对应 EARS**: `backtest.py` 退出码约定。

### AC-7

AC-FR0200-07

- **WHEN** CLI 成功完成
- **THEN** 系统 SHALL 打印 `summary.json` 路径 + 关键指标（`total_trades` / NAV 末值）到 stdout（loguru logger）
- **断言**:
  - 给定：`run_paper_trade` 返回 `summary={"total_trades": 5, ...}`，`nav` 末行 nav=`1_200_000`。
  - 当：`main([...])` 执行（捕获 caplog）。
  - 那么：caplog 含 `summary.json` 路径字样与 `total_trades=5`；含 NAV 末值。

---

<a id="ac-nfr-0100"></a>
## NFR-0100 函数级 lazy import — 白名单延伸至 quantide.service.sim_broker.PaperBroker（+ 推行情所需 core 基础设施）

### AC-1

AC-NFR0100-01

- **WHEN** 验证 `src/trader_off/backtest/runner.py` 与 `src/trader_off/cli/paper_trade.py` 模块顶层
- **THEN** 系统 SHALL 无 `import quantide` / `from quantide ...` 语句（模块顶层零 quantide import）
- **断言**:
  - 给定：两文件源码。
  - 当：`grep -rn "^import quantide\|^from quantide" src/trader_off/backtest/runner.py src/trader_off/cli/paper_trade.py` 执行。
  - 那么：无匹配（grep 退出码 `1`，stdout 为空）。

### AC-2

AC-NFR0100-02

- **WHEN** 验证 `runner.py` 函数体内 import
- **THEN** 系统 SHALL 至少含 `from quantide.service.sim_broker import PaperBroker`（v0.5.0 新增 paper 路径接入证明），且 v0.3.0 既有 `from quantide.data.models.daily_bars import daily_bars` / `from quantide.service.runner import BacktestRunner`（仅 `run_backtest` 内）/ `from quantide.data.sqlite import db` 保留
- **断言**:
  - 给定：`runner.py` 源文件。
  - 当：`grep -rn "from quantide" src/trader_off/backtest/runner.py` 执行。
  - 那么：至少 1 行匹配 `from quantide.service.sim_broker import PaperBroker`；既有 `daily_bars` / `BacktestRunner` / `db` import 保留（`run_backtest` 不退化）。

### AC-3

AC-NFR0100-03

- **WHEN** Python AST 解析 `runner.py` 与 `paper_trade.py`
- **THEN** 系统 SHALL 验证所有 `quantide` 导入节点的祖先链含 `FunctionDef` / `AsyncFunctionDef`，无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 quantide import
- **断言**:
  - 给定：`ast.parse(Path(...).read_text())` 后遍历 `ast.ImportFrom` / `ast.Import` 节点。
  - 当：对每个 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点追溯祖先。
  - 那么：所有 quantide import 节点的最近函数祖先存在，且不位于 `if TYPE_CHECKING` 块内或类体内。

### AC-4

AC-NFR0100-04

- **WHEN** 验证白名单外业务符号边界
- **THEN** 系统 SHALL 无 `quantide.portfolio.*` / `quantide.service.metrics` 的 import（白名单外业务符号零出现；`quantide.service.runner.BacktestRunner` / `quantide.service.sim_broker.PaperBroker` 为白名单内）
- **断言**:
  - 给定：两文件源码。
  - 当：`grep -rnE "quantide\.(portfolio|service\.metrics)" src/trader_off/backtest/runner.py src/trader_off/cli/paper_trade.py` 执行。
  - 那么：无匹配（grep 退出码 `1`）。

### AC-5

AC-NFR0100-05

- **WHEN** 验证推行情所需的 core 基础设施 import（⚠️ 待用户确认，见 spec.md NFR-0100 内联讨论）
- **THEN** 系统 SHALL 允许 `runner.py` 函数体内 `from quantide.core.message import msg_hub` + `from quantide.core.enums import Topics`（core 基础设施，非业务符号），且这两个 import 位于函数体内（非模块顶层）
- **断言**:
  - 给定：`runner.py` 源文件。
  - 当：`grep -rn "from quantide.core.message import msg_hub\|from quantide.core.enums import Topics" src/trader_off/backtest/runner.py` 执行。
  - 那么：匹配行**不**以 `^` 锚定行首（即位于函数体内，缩进）；AST 校验这两个 import 节点的祖先含 `FunctionDef` / `AsyncFunctionDef`。
  - **注**：本 AC 依赖 spec.md NFR-0100 ⚠️ 内联讨论的用户确认；若用户拒绝放行 msg_hub/Topics，则 FR-0100 AC-6 的 msg_hub.publish 方案需重新设计。

### AC-6

AC-NFR0100-06

- **WHEN** 验证其它模块隔离承诺延续
- **THEN** 系统 SHALL v0.3.0 NFR-0200 / v0.3.1 NFR-0101 / v0.4.1 NFR-0100 对其他模块的隔离承诺保持通过；本 NFR-0100 仅约束 `backtest/runner.py` 与 `cli/paper_trade.py`
- **断言**:
  - 给定：v0.4.1 NFR-0100 的 `data/quantide_adapter.py` 隔离验证。
  - 当：`grep -rn "^import quantide\|^from quantide" src/trader_off/data/quantide_adapter.py` 执行。
  - 那么：无匹配（v0.4.1 边界不退化，tushare 白名单仍在函数体内）。
