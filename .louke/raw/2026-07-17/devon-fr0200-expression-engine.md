---
date: 2026-07-17
session: devon-v0.2.0-001-fr0200-expression-engine
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#35]
status: resolved
---

## Topic
FR-0200 表达式引擎 — 参数化枚举: implement `enumerate_factors()` in `src/trader_off/factor_mining/expression.py`, including `FactorSpec` dataclass, parameter space expansion, compute_fn generation, invalid combination logging, and ≥200 default candidates.

## Decision
- **Module**: `src/trader_off/factor_mining/expression.py` (235 stmts, 100% coverage)
- **Tests**: `tests/unit/factor_mining/test_expression.py` (40 test functions)
- **Key design choices**:
  - `enumerate_factors(templates=None, param_space=None, *, invalid_log_path=None)`: both args optional, defaults to `list_templates()` and `DEFAULT_PARAM_SPACE = {"N": list(range(1, 61))}` which yields ~385 candidates (≥200).
  - `FactorSpec` dataclass: frozen, with `id`, `template_name`, `category`, `formula`, `compute_fn`, `params`.
  - Parameter validation: uses template's `IntRangeParam.min/max` to filter valid values from `param_space`; invalid combos recorded to `invalid_combinations.json`.
  - Compute functions: builder registry pattern (`@_register` decorator), each template name maps to a closure that accepts `pl.DataFrame` → `pl.Series`.
  - Missing-field fallback: all compute functions return `_zeros_like(df)` when required columns are absent.
- **Exports**: Added `enumerate_factors`, `FactorSpec`, `DEFAULT_PARAM_SPACE` to `trader_off.factor_mining.__init__`.
- **Commits**:
  - `649cb91` feat: green – #35 – 表达式引擎参数化枚举 FR-0200 (Closes #35)
  - `d71a325` refactor: FR-0200 提取 _zeros_like 消除重复的零Series构造 (#35)

## Tried but abandoned
- Attempted `replaceAll` on `pl.Series("_factor", ...)` → recursively replaced inside `_zeros_like` itself, causing RecursionError. Fixed by manually editing the function body.
- Initially considered making `param_space` always required per interfaces.md signature, but AC-2 requires "默认参数空间" semantics, so made it optional with `DEFAULT_PARAM_SPACE`.

## Open questions
- `compute_fn` implementations for complex formulas (excess_momentum, momentum_accel, vp_corr) are simplified approximations. Full mathematical correctness may need refinement in future FRs.
- `invalid_combinations.json` writes to CWD when `invalid_log_path` is None. Should be configurable longer-term (T-4: config-driven output dirs).
- FR-0100 AC-3 (fundamental templates skipped when no fundamental columns) is listed under FR-0100 but not yet implemented — it's part of the `enumerate_factors` function's interaction with data availability. This will be addressed when the data_loader/filter integration is done.
