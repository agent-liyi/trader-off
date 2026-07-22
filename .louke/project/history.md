# Release History

## v0.1.0 — 2026-07-16

**Spec**: v0.1.0-001-lgbm-asset-pricing
**Branch**: releases/v0.1.0 → merged to main
**Tag**: v0.1.0

### Summary
基于 lightGBM 的短时 A 股定价模型，集成 millionaire 量化回测框架。预测个股未来 5 个交易日收益率，通过 Top 20 等权策略进行回测。

### Modules (12)
- `trader_off/features/` — 动量/波动率/成交量特征工程 (FR-0100~FR-0300)
- `trader_off/data/` — 标准化/缺失值/walk-forward 切分/DataLoader (FR-0400, FR-0600)
- `trader_off/labels/` — 未来 5 日收益率标签构建 (FR-0500)
- `trader_off/training/` — lightGBM 训练/序列化/特征重要性 (FR-0700, FR-0800, FR-1400)
- `trader_off/prediction/` — 预测服务 (FR-0900)
- `trader_off/strategies/` — LGBMTop20Strategy + millionaire compat shim (FR-1000)
- `trader_off/backtest/` — 回测运行器/绩效指标 (FR-1100, FR-1200)
- `trader_off/evaluation/` — IC/Rank IC/分层回测 (FR-1300)
- `trader_off/visualization/` — 3 个静态 PNG 图表 (FR-1600)
- `trader_off/cli/` — CLI 入口 (train/predict/backtest/feature-importance)
- `trader_off/utils/` — 日志/异常

### Stats
- 23 FR/NFR implemented
- 126 tests passing (109 unit + 14 integration + 3 e2e)
- 97% code coverage
- 0 security findings
- e2e runtime: 0.90s

### Stage artifacts
- M-FOUND: project.toml, story.md, GitHub Project #3
- M-SPEC: spec.md (23 FR/NFR), acceptance.md (79 AC), 23 GitHub Issues (#6-#28)
- M-TESTPLAN: test-plan.md (604 lines, 79/79 AC coverage)
- M-ARCH: architecture.md (534 lines), interfaces.md (572 lines, ~40 API, 24 cross-module)
- M-DEV: 48 source files, 50 test files, 97% coverage
- M-E2E: 3 e2e tests + 17 integration tests
- M-SECURITY: 0 findings (Judge audit pass)

## v0.2.0 — 2026-07-20

**Spec**: v0.2.0-001-factor-mining-retrain-optimizer
**Branch**: releases/v0.2.0 → merged to main
**Tag**: v0.2.0

### Summary
因子挖掘 + 定时重训练 + 组合优化器。LightGBM 因子挖掘流水线、scheduler 增量重训练（croniter 调度 + 并发安全）、cvxpy 组合优化（long-only / 满仓 / 行业中性 / 个股上限 10% / Max Sharpe），OptimizedTopKStrategy 作为 v0.1.0 策略输入，向后兼容 v0.1.0 模型与策略。

### Stats
- 159 AC (FR-0100~FR-4200 + NFR-0100~NFR-1000)
- 21 e2e/perf tests passing (runtime ~31s); 单元+集成测试全覆盖（158/159 AC 验证，waiver 记录）
- 性能预算达标：train≤300s / predict(4000资产)≤5s / backtest≤600s / 内存≤16GB
- 安全审计：0 blocking（stage-1 六处 re.compile 误报经语义复审驳回；1 medium + 2 low 记入 backlog）

### Stage artifacts
- M-E2E: 21 e2e/perf tests（6 批次），AC-trace 31/159 人工豁免（e2e 设计仅覆盖 happy path）
- M-BUGFIX: 无 bug，豁免跳过
- M-SECURITY: Judge S 级审计 pass（人工确认）
- Agent 模型统一：kimi-for-coding/k3 ×5 + deepseek/deepseek-v4-pro ×8（MiniMax 不可用已移除）

## v0.3.0 — 2026-07-21

**Spec**: v0.3.0-001-real-backtest
**Branch**: releases/v0.3.0 → merged to main
**Tag**: v0.3.0

### Summary
真回测引擎里程碑。把 trader-off 的"假数据回测"（`np.random.RandomState(42)` 生成合成 NAV）替换为真实 quantide/millionaire BacktestRunner —— 真实撮合（手续费/涨跌停/T+1）、真实记账（`BacktestBroker.bills()`）、真实指标（Sortino/回撤持续期/基准对比）。Python 3.13 升级，quantide 作为引擎供应商通过依赖接入（不改 fork）。trader-off 继续作为 alpha 研究层（features/labels/training/factor_mining/portfolio）。

### 复用 millionaire 原则达成
- ✅ BacktestRunner + BacktestBroker + Calendar → 100% 委托 quantide
- ✅ metrics.py → 委托 quantide.service.metrics
- ✅ 数据存储格式 → 委托 quantide DailyBarsStore (parquet 分区)
- ✅ 策略基类 + Broker 接口 → compat shim 已对齐 quantide
- 🔜 推迟到 v0.4.0+：tushare、grid_search、walk-forward、polars-talib 指标、qfq/hfq 复权、scheduler cron 触发器复审

### Stats
- 8 FR + 5 NFR + 71 AC 实现
- 32 e2e tests passing（9 skipped — 7 因 lgbm_top20 + 预训练模型不在 v0.3.0 MVP scope，2 因 ClockRewind fixture 日期问题）
- 单元测试 40 passed（v0.3.0 改动）+ 41 pre-existing
- 安全审计 PASS（0 critical/high；4 low 记入 v0.4.0 backlog）

### Stage artifacts
- M-DEV: 8 FRs (FR-0100~0900)，8 commits，Prism PASS，Keeper gate via waiver（AC trace gap 是基础设施 FR 无独立测试）
- M-E2E: 5 commits 添加 convert_fixture/real_backtest/cli/backward-compat e2e，Prism PASS
- M-SECURITY: Judge S 级审计 PASS（stage-1 linter 误报人工确认）
- M-BUGFIX: 无 bug 跳过
- Backlog for v0.4.0：scheduler 复审 AC-FR1500-04、ClockRewind fixture 修正、4 security low 项

## v0.3.1 — 2026-07-21

**Spec**: v0.3.1-001-clock-rewind-scheduler-review
**Branch**: fix/102 → releases/v0.3.1 → merged to main
**Tag**: v0.3.1

### Summary
Patch 修复 + 架构迁移。ClockRewind 修复（inline calendar prev day，Devon (b)，用户接受偏差）；scheduler 迁入 `quantide.core.scheduler.SchedulerManager`（NFR-0101 函数级 lazy import 替代 v0.3.0 NFR-0100）；决策文档 `.louke/project/decisions/v0.3.1-scheduler-review.md` 落地。

### Stats
- 4 FR/NFR + 20 AC
- 28 e2e passed + 3 xfailed（capital exhaustion bug 暴露 → v0.3.2 修）

## v0.3.2 — 2026-07-21

**Branch**: fix/102 → merged to main
**Tag**: v0.3.2

### Summary
资金耗尽 bug 修复。根因：(1) `trade_target_pct()` 使用 `total_asset()` 做分母，现金稀释导致每个持仓权重被缩小，每天产生净买入消耗现金；(2) 调仓顺序为「先买后卖」，卖出回流前现金已耗尽；(3) quantide `pos.mv` 跨日不更新，使用过期数据。修复：先清仓非目标 → 计算 `cash_factor = market_value / total_asset` → 按调整后权重调入目标。3 个 v0.3.1 xfailed 测试全部转 PASS。

### Stats
- 891 测试通过（+6 vs v0.3.1），0 xfail
- Security PASS（0 critical/high；2 medium 调仓风险记入 v0.3.3 backlog）

### Backlog for v0.3.3
- 调仓非原子性（buy-after-fail 无补偿）
- `cash_factor` 资产轮换时系统性扩大现金仓位
- `cash_factor` 范围校验（NaN/负值/超额）

## v0.3.1 — 2026-07-21

**Spec**: v0.3.1-001-clock-rewind-scheduler-review
**Branch**: releases/v0.3.1
**Tag**: (pending merge to main)

### Summary
v0.3.0 patch — 处置两件延期尾巴：(1) ClockRewind fixture 修复使 3 个 e2e 回测测试重新启用（改为 xfail，capital exhaustion 记入 v0.4.0 backlog）；(2) scheduler 迁移评估落地，创建 QuantideSchedulerAdapter 封装 quantide.core.scheduler.SchedulerManager（函数级 lazy import，NFR-0101 隔离条款放宽）。

### FR-0100: ClockRewind fixture fix
- **Spec 选项 (a) "modify convert_fixture_to_quantide.py" → 实施选项 (b) "modify _generate_inline_calendar() prepend synthetic prev day"**
  - Resolution: spec said option (a); implementation chose (b) because the root cause was inline calendar generation in runner.py, not the fixture conversion script. Both approaches fix the same bug; (b) is more minimal and doesn't require altering upstream fixture data. Deviation recorded in spec.md Clarification Log.
- Fix: `_generate_inline_calendar()` in `src/trader_off/backtest/runner.py` prepends a synthetic previous trading day to the inline calendar, ensuring `quantide calendar.day_shift(start, -1)` returns a real prior day instead of clamping to the first day.
- Also fixed multiple quantide API compatibility issues unmasked after unskipping:
  - `pct` → `target_pct` (BacktestBroker.trade_target_pct parameter name)
  - `on_bar(tm, quote, frame_type)` signature alignment
  - Async `trade_target_pct` → added `await`
  - `order_time` required by BacktestBroker.buy_amount
  - `adj_factor` → `adjust` column rename; `up_limit`/`down_limit` computation
  - `year=` → `partition_key_year=` Hive partition naming
- 3 e2e tests unskipped → marked `xfail(strict=False)` due to capital exhaustion bug discovered (v0.4.0 backlog)

### FR-0200: scheduler migration to quantide.core.scheduler.SchedulerManager
- **Verdict**: (M) Migrate
- Created `src/trader_off/scheduler/adapter.py` — `QuantideSchedulerAdapter` wrapping `SchedulerManager`
- Exposes: `init`, `start`, `stop`, `add_job`, `add_listener`
- Decision document: `.louke/project/decisions/v0.3.1-scheduler-review.md`

### NFR-0101: function-scope lazy imports (replaces v0.3.0 NFR-0100 for scheduler)
- All quantide imports in scheduler/ are inside function bodies (AST-verified)
- Zero business symbol imports (`quantide.service`, `quantide.data`, etc.)
- `test_ac_fr1500_04_no_external_deps` updated to NFR-0101 rules

### Capital exhaustion bug discovered
- Backtest with 10 equal-weight positions + 1M capital exhausts cash by day 5
- Quantide UNIQUE constraint violation on `orders.qtoid, orders.tm` in error path
- Both moved to v0.4.0 backlog; 3 e2e tests marked `xfail(strict=False)`

### Design drift
- FR-0100: spec prescribed option (a) → implemented option (b); see Clarification Log
- NFR-0100 → NFR-0101 relaxation (scheduler only; other modules still governed by v0.3.0 NFR-0200)

### Stats
- 4 FR/NFR implemented (FR-0100, FR-0200, NFR-0101, NFR-0200)
- 43 unit tests passing (14 runner + 12 adapter + 17 strategies)
- 3 e2e tests xfailed (capital exhaustion, v0.4.0 backlog)
- 1 compat test pre-existing failure (quantide installed → stubs not used)

## v0.4.1 — 2026-07-21

**Spec**: v0.4.1-001-real-tushare-integration
**Branch**: releases/v0.4.1 → merged to main
**Tag**: v0.4.1

### Summary
真数据接入里程碑。`QuantideDataLoader` 现在实际调用 `quantide.data.fetchers.tushare.fetch_bars()` + `fetch_calendar()`（受 `TUSHARE_TOKEN` 环境变量门控）。原计划用 `quantide.data.models.calendar.Calendar.get_frames_by_count()` 替换 `pandas.bdate_range`，但实现发现该方法有内部 bug（pyarrow `pc.sum` 抛 TypeError），改用模块级 `fetch_calendar(start_epoch)`。TUSHARE_TOKEN 三道防线：env-only / memory-only / 不入日志。Token 仅在本会话使用，**未**落盘。

### Smoke 测试结果
`uv run python` + TUSHARE_TOKEN → QuantideDataLoader.get_daily("000001.SZ", 2026-07-17, count=10) → **10 rows 真实数据**（2026-07-06 至 2026-07-17，含 OHLCV/turnover/adj_factor）。

### Stats
- 2 FR + 1 NFR + 16 AC
- 22 单元测试 + 4 e2e mock + 1 skip（无 token 时）通过
- Security PASS（0 critical/high；2 placeholder token 误报已澄清）

### Backlog for v0.4.2+
- `Calendar.get_frames_by_count` bug 已识别，可向 quantide 上游提 issue
- 完整 BacktestRunner.run on 真实数据（当前 smoke 只验证 fetch_bars）
- CLI `trader-off sync-data` 命令
- 自动重试 / token 轮换

## v0.3.3 — 2026-07-21

**Branch**: fix/115 → merged to main
**Tag**: v0.3.3

### Summary
调仓逻辑风险修复（v0.3.2 backlog 的 3 项）。`optimized_topk.py` + `lgbm_top20.py` 的 `on_day_open` 方法加固：(1) `_reconcile_position_cache()` 在 try/finally 中执行，删除幽灵 cache 项；(2) `cash_factor` 用卖出前快照计算，避免资产轮换时系统性扩大现金仓位；(3) `_compute_cash_factor()` 加 `math.isfinite()` + 范围校验（0 ≤ x ≤ 1.0），无效值 fallback 1.0 + warning。

### Stats
- 1 bug issue (#115) + 10 new unit tests
- 927 测试通过，0 回归
- Security PASS（0 critical/high；2 low 记入 v0.4.x backlog）

### Backlog for v0.4.x
- 双向 reconcile（snapshot/restore 模式）
- `_compute_cash_factor` 区分「空仓回退 1.0」与「broker 损坏 raise」

## v0.4.3 — 2026-07-22

**Branch**: fix/120 → merged to main
**Tag**: v0.4.3 (renamed from v0.3.4)

### Summary
调仓逻辑完善 + 文档同步。`optimized_topk.py` + `lgbm_top20.py` 三项加固：(1) `_reconcile_position_cache()` 改为**双向**（添加 broker 中缺失、删除 cache 中多余）；(2) `_compute_cash_factor()` 对 NaN/负数/overflow 改**抛 RuntimeError**（fail-closed vs 之前 fail-open 静默 fallback 1.0）；(3) `on_day_open` 加 snapshot/restore 模式，异常时回滚 `_position_cache`。`cli/__init__.py` docstring 移除不存在的 `train/predict/feature-importance` 模块引用。

### 安全提升
- `cash_factor` 从 **fail-open**（broker 故障时仍全仓买入）改为 **fail-closed**（broker 故障时 raise + 跳过 rebalance）—— 符合交易系统应有的安全姿势

### Stats
- 1 bug issue (#120) + 7 new unit tests
- 784 测试通过，0 回归
- Security PASS（0 critical/high/medium；1 low 关于 RuntimeError 嵌入组合数值 → 留 live-trading scope）

### Backlog
- RuntimeError message 嵌入 portfolio 数值（live-trading 时考虑脱敏）
