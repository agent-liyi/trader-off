---
date: 2026-07-22
session: devon-v0.5.9-157-check-factor-cli
agents: [Devon]
spec: v0.5.9
related_issues: [#157]
status: resolved
---

## Topic
Implement FR-0100 check-factor CLI command for v0.5.9.

## Decision

### Created files
- `src/trader_off/cli/check_factor.py` — CLI module with main(argv)
- `tests/unit/cli/test_check_factor.py` — 17 unit tests

### Modified files
- `pyproject.toml` — registered `trader-off-check-factor` script entry
- `tests/unit/test_console_scripts.py` — updated expected entry count (7→8), added check_factor signature, updated README entries
- `README.md` — added check-factor usage section

### Implementation details
- Args: --name (required), --start (required), --end (required), --capital (default 1M), --ic-threshold (default 0.3), --json
- Data loading: reuses v0.5.2 pattern — QuantideDataLoader if TUSHARE_TOKEN, else fixture
- Labels: 5-day forward returns from close prices
- Factor matching: 2-pass algorithm — exact match against candidate.id, then compact name match (template_name with param placeholders substituted)
- Evaluation: function-scope lazy import from factor_mining.evaluation
- rank_icir: computed as rank_ic_mean / rank_ic_std (same formula as ICIR)
- No-data case: ic/icir=0, valid=false, reason="no valid data"
- All quantide imports are function-scoped (NFR-0100 compliant)

### R-G-R commits
- `c5d9e87` — feat: green – add check-factor CLI
- `976613f` — refactor: add TYPE_CHECKING import for FactorSpec

## Tried but abandoned
- Name matching via `startswith`: candidate IDs like `momentum_N_5` don't start with `momentum_5`. Switched to 2-pass compact name match algorithm.
- Direct FactorSpec import for return type annotation: triggered mypy error. Used TYPE_CHECKING guard instead.

## Open questions
None.
