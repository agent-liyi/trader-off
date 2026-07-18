---
date: 2026-07-17
session: devon-fr0400-selection
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#37]
status: resolved
supersedes: []
---

## Topic
FR-0400 因子选择 — Top-K + Pearson 去冗余。实现 `select_factors` 函数和 `SelectionDiagnostics` dataclass。

## Decision
1. **函数签名**：遵循 `interfaces.md §3.3`：
   `select_factors(evaluations: list[FactorEvaluation], factor_specs: list[FactorSpec], top_k: int = 30, corr_threshold: float = 0.9) -> tuple[list[FactorSpec], SelectionDiagnostics]`

2. **排序键**：按 `icir` desc，tiebreaker 为 `id` asc（AC-FR0400-04 要求字典序）

3. **去冗余算法**：
   - 先排序 → 取前 top_k → 贪心去重
   - Pearson 相关性基于 `FactorEvaluation.ic_ts` 的 IC 时间序列计算
   - 相关性阈值默认 0.9

4. **WARNING 条件**：仅当 `len(evaluations) < top_k`（候选总数不足）时触发，与 AC-FR0400-03 一致

5. **实现文件**：
   - `src/trader_off/factor_mining/selection.py`（150 行）
   - `tests/unit/factor_mining/test_selection.py`（620 行，19 个测试）

6. **覆盖率**：selection.py 100% 行覆盖

## Tried but abandoned
- **按 `|ic_mean|` 排序**：任务描述提到但 acceptance.md 明确要求按 icir 降序，遵循 AC
- **去重后再取 top_k**：与 AC-FR0400-02 "从 50 个取前 30 → 冗余处理保留 25" 不一致，放弃
- **WARNING 条件为 `final_k < top_k`**：与 AC-FR0400-02（50 候选、top_k=30、5 冗余→不触发 WARNING）冲突，改为仅按候选总数判断

## Open questions
- 无需后续讨论。Pearson 相关性基于 IC 时间序列而非原始因子值，这是一个合理的设计决策（IC 时间序列已反映因子的预测模式）
