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
