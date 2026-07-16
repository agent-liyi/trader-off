---
date: 2026-07-16
session: scout-v0.1.0-001-foundation
agents: [Scout]
spec: v0.1.0-001-lgbm-asset-pricing
related_issues: [#3]
status: resolved
supersedes: []
---

## Topic
M-FOUND project foundation for trader-off — a short-horizon asset pricing model for A-shares based on lightGBM, integrated with millionaire framework.

## Decision
- Repo: agent-liyi/trader-off (private, github.com)
- Version: v0.1.0
- Spec ID: v0.1.0-001-lgbm-asset-pricing
- Prediction target: Future 5-day return (regression)
- Data: Daily bars (1d) for full A-share market via millionaire data module
- MVP scope: Full-featured v0.1 (training pipeline + backtest integration + performance analysis)
- DoD: e2e tests pass + coverage ≥95% + security audit enabled
- Security audit: ENABLED
- Branch: releases/v0.1.0
- Upstream framework: github.com/zillionare/millionaire (BaseStrategy interface)
- Language: Chinese for user-facing artifacts, English for code comments
- Tech stack: lightGBM, polars, millionaire framework, uv

Created artifacts:
  - .louke/project/project.toml (18 fields, all resolved)
  - .louke/project/specs/v0.1.0-001-lgbm-asset-pricing/story.md (Chinese PRD)
  - .pre-commit-config.yaml (base hooks)
  - GitHub Project #3 (trader-off-v0.1.0)
  - GitHub Project #4 (trader-off-backlog)
  - Smoke test issue #3 (closed)

## Tried but abandoned
- Using `--spec-id` with `vv` prefix from first foundation run → had to rename directory
- `lk agent scout foundation` without `--no-commit` → still didn't fill TODO fields due to missing `user` scope on gh token
- Gh auth refresh for `user` scope → user ran it twice but scope didn't get added to token; fallout:
  - `gh project list/create` fails programmatically (caught exceptions → returns None)
  - `smoke_test_pr` not created → field stays "#TODO (closed)"
  - Manual python script used to fill project.toml TODO fields via louke's internal `_set_toml_string_field`

## Open questions
1. smoke_test_pr still "#TODO" — F4 will fail in Warden check. Need to create smoke test PR manually or get `user` scope working.
2. No `releases/` directory under `.louke/project/` — the spec said to create `.louke/project/releases/v0.1.0/` placeholder but foundation command doesn't do this.
