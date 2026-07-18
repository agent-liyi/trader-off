---
date: 2026-07-17
session: maestro-v0.2.0-001-m-found-m-spec-complete
agents: [Maestro, Scout, Warden, Sage, Lex]
spec: v0.2.0-001-factor-mining-retrain-optimizer
status: resolved
---

## Topic
v0.2.0 M-FOUND + M-SPEC stage completion — new milestone for factor mining + retrain scheduler + portfolio optimizer.

## Decision
- **Spec ID**: `v0.2.0-001-factor-mining-retrain-optimizer` (single spec for 3 modules)
- **Version**: v0.2.0
- **Branch**: `releases/v0.2.0` (created from main)
- **Project #5**: trader-off-v0.2.0
- **Smoke test**: Issue #33 / PR #32
- **FR count**: 45 (9 factor mining + 13 retrain scheduler + 13 portfolio optimizer + 10 NFR)
- **AC count**: 159
- **DoD**: coverage≥97% + mutation≥80% + perf budgets (train≤300s/predict≤5s/backtest≤600s/mem≤16GB) + docs sync + M-SECURITY
- **Locked**: true (Sage record-lock)

## Key design decisions
- Factor DSL: dataclass + enum (≥200 candidates)
- Covariance: Ledoit-Wolf
- Optimizer: cvxpy + ECOS default + scipy SLSQP fallback
- Scheduler: JSONL + parquet persistence; single-process asyncio, max_concurrent=1
- Drift detection: PSI + KS three-level (light/moderate/strong)
- Online Sharpe: **DISABLED** (user chose IC-only)
- v0.1.0 CLI commands retained; new `--factor-registry` flag

## Tried but abandoned
- **louke verify-project bug**: `gh project item-list` default limit=30 incorrectly reports #64-#67 as unlinked. Manual verification confirmed 45/45 actually linked. Worked around with M-SPEC waiver + force advance. Should be fixed in louke project (add `--limit 200` to verify-project).
- **Spec ID double-v bug**: `lk agent scout foundation` auto-infers `vv0.2.0-...` if spec-id not explicit. Scout passed `--spec-id` explicitly to avoid.

## Open questions
- Proceeding to M-TESTPLAN: Archer (model `glm-5.2`, verified) generates test-plan.md for 45 FR/159 AC.
- Estimated test-plan size: ~800-1200 lines (v0.1.0 was 604 lines for 23 FR/79 AC).
- M-DEV batches: ~45 FR is 5x v0.1.0. May need 6-8 batches instead of 5.
