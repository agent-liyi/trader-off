---
date: 2026-07-17
session: devon-v0.2.0-001-module-c-portfolio-foundations
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#56, #57, #58, #59, #60]
status: resolved
---

## Topic
模块 C portfolio 基础组件实现：协方差估计、预期收益输入、行业映射、约束规范

## Decision

### FR-3000 (#56) — 协方差估计 (covariance.py)
- 使用 sklearn.covariance.LedoitWolf 作为默认方法
- sample 方法使用 np.cov
- 自动剔除全 NaN 列并 log WARNING
- 强制对称化: `(cov + cov.T) / 2`
- PSD 校验: eigenvalues >= -1e-8 tol
- 最少 30 日数据，不足抛 InsufficientDataError
- 使用 loguru logger（与项目一致）
- 4 个单元测试

### FR-3100 (#57) — 预期收益输入 (expected_returns.py)
- `build_expected_returns(predictions, mode)` 支持 raw/zscore 模式
- NaN 检测抛 ValueError
- `validate_asset_alignment(mu, cov_assets)` 校验资产一致性
- 新增 `AssetMismatchError` 异常
- 4 个单元测试

### FR-3200 (#58) — 行业映射 (industry.py)
- `load_industry_map(path)` 从 CSV 加载
- 重复 asset 抛 `IndustryMapConflictError`
- `get_industry(ticker, industry_map)` 未知返回 "UNKNOWN" + WARNING
- 新增 `IndustryMapConflictError` 异常
- 3 个单元测试

### FR-3300 (#59) + FR-3400 (#60) — 约束规范 (constraints.py)
- `full_position_constraint(n)` 返回 (a_eq, b_eq) 实现 Σw=1
- `long_only_constraint(n)` 返回 (lb, ub) 实现 w≥0
- 纯数据，不求解
- Ruff N806 要求变量名小写(a_eq vs A_eq)
- 4 个单元测试

## Tried but abandoned
- 最初 covariance.py 用 `logging.getLogger`，改为 loguru 以匹配项目风格
- 测试中用 `caplog` fixture 捕获 loguru 输出失败，改用 `io.StringIO` + `logger.add()`
- Loguru 用 `{}` 而非 `%s` 格式化

## Open questions
- 无
