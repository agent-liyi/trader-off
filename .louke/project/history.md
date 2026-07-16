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
