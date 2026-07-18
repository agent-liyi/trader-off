---
date: 2026-07-17
session: scout-v0.2.0-001-foundation
agents: [Scout]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#31, #32, #33]
status: resolved
supersedes: []
---

## Topic

M-FOUND project foundation for v0.2.0 — factor mining, retrain scheduler, portfolio optimizer.

## Decision

1. **Spec strategy**: One mega-spec `v0.2.0-001-factor-mining-retrain-optimizer` (not 3 separate specs). Rationale: 3 scope items are tightly coupled milestone deliverables.

2. **因子挖掘**: Expression enumeration from predefined template library + IC/ICIR evaluation + Top-K selection with redundancy removal (Pearson >0.9 filter).

3. **再训练调度**: Cron timer + data drift detection (PSI/KS) triggers, full + incremental retrain, versioned model storage with rollback.

4. **组合优化器**: Max Sharpe objective, long-only constraint, industry neutrality, individual stock cap. Risk model: Ledoit-Wolf shrunk covariance.

5. **DoD**: Unit >=97%, mutmut >=80%, performance budgets (train<=300s, predict<=5s, backtest<=600s, mem<=16GB), documentation sync + >=3 ADRs, security audit.

6. **Branch**: `releases/v0.2.0` created from `main` (v0.1.0 tag).

## Commands/files/specs

- `lk agent scout identity-check --repo agent-liyi/trader-off` -> PASS
- `lk agent scout foundation --repo agent-liyi/trader-off --version v0.2.0 --spec-id v0.2.0-001-factor-mining-retrain-optimizer --keyword factor-mining-retrain-optimizer --story-file /tmp/v0.2.0-story.md --dod "..." --security-audit enabled` -> PASS (after 3 retries due to spec-id auto-inference bug)
- `lk agent scout install-precommit --force` -> PASS (added ruff + mypy hooks)
- `lk agent scout commit-foundation` -> PASS (commit cd4a95a, pushed to origin)
- Created GitHub Project #5 `trader-off-v0.2.0`
- Smoke Test Issue #33 (closed) + Smoke Test PR #32 (closed)

## Tried but abandoned

1. **Running foundation without removing old project.toml**: Failed with spec-id mismatch (F6 check). The foundation command checks against existing project.toml and rejects mismatches before writing.

2. **Three separate specs**: Abandoned in favor of one mega-spec for simpler milestone management.

3. **Running foundation with vv0.2.0-* auto-inferred spec-id**: Foundation command has a bug where it constructs spec-ids with double-v prefix (`vv0.2.0-002-*`). Had to pass `--spec-id` explicitly.

4. **gh auth refresh -s user**: Requires interactive browser flow, not possible in subagent context. Created Test PR manually instead.

## Open questions

1. **mypy version in pre-commit**: `lk agent scout install-precommit` installed mypy 2.1.0 which requires Python >=3.10, but the pre-commit runtime uses Python 3.9. Downgraded to 1.18.1 manually.

2. **Smoke test issue number keeps incrementing**: Foundation creates a new issue each run instead of detecting existing one (#29 -> #31 -> #33).

3. **e2e/integration test sections**: Foundation command didn't preserve them from v0.1.0 project.toml. Had to re-add manually.
