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
