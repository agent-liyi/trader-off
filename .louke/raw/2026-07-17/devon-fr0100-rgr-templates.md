---
date: 2026-07-17
session: devon-fr0100-rgr-templates
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#34]
status: resolved
supersedes: []
---

## Topic
FR-0100 因子模板库定义 — Red-Green-Refactor cycle for the first implementation issue in v0.2.0 M-DEV stage.

## Decision

### Modules created
- `src/trader_off/factor_mining/__init__.py` — package init, re-exports public API
- `src/trader_off/factor_mining/templates.py` — 213 lines, includes:
  - `FactorTemplate` dataclass (frozen, 5 fields: name, category, fields, params, formula)
  - `IntRangeParam` dataclass (frozen, name/min/max/step, expanded() method)
  - `ChoiceParam` dataclass (frozen, name/choices)
  - `BoolParam` dataclass (frozen, name, expanded() → [False, True])
  - `FACTOR_TEMPLATE_VERSION = "v1"` constant
  - `list_templates()` → 13 templates across 4 categories (momentum: 3, volatility: 3, volume: 3, fundamental: 4)
  - All templates defined as module-level `_TEMPLATES` list with explicit field declarations

### Tests created
- `tests/unit/factor_mining/test_templates.py` — 171 lines, 15 tests
  - AC-FR0100-01: 3 tests (count ≥12, field integrity, ≥3 per category)
  - AC-FR0100-02: 1 test (momentum_N IntRangeParam assertion)
  - AC-FR0100-03: 1 test (fundamental templates have fundamental-only fields)
  - AC-FR0100-04: 1 test (FACTOR_TEMPLATE_VERSION == "v1")
  - IntRangeParam: 5 tests (default step, custom step, single value, uneven step, frozen)
  - ChoiceParam: 2 tests (creation, frozen)
  - BoolParam: 2 tests (expanded, frozen)

### Additional changes
- `pyproject.toml`: added "unit" marker to pytest markers list
- `from __future__ import annotations` added to templates.py due to mypy pre-commit hook environment not recognizing X|Y union syntax

### Results
- Coverage: 100% (34/34 statements in templates.py)
- All 122 existing unit tests still pass (no regression)
- Ruff format: repo-wide formatting fixes (49 files reformatted, not committed — pre-existing issues)

### Commits
1. `8489edd` feat: green – #34 – FR-0100: factor template library
2. `a53f68c` refactor: FR-0100 — add test for IntRangeParam uneven step edge case, achieve 100% coverage

## Tried but abandoned
- Attempted to avoid `from __future__ import annotations` but mypy in pre-commit hook had default Python version < 3.10, causing X|Y union syntax errors. Adding `from __future__ import annotations` was the pragmatic fix.
- Attempted `lk agent devon commit-rgr` but it failed silently; used `git commit` directly instead.

## Open questions
- AC-FR0100-03 references `enumerate_factors()` behavior (FR-0200). The FR-0100 test only validates that fundamental templates have fundamental-only column fields, setting up the skip mechanism for FR-0200. This is a reasonable boundary split — FR-0200 will implement the actual skip logic and INFO logging.
- The 49 ruff-format changes to pre-existing v0.1.0 files remain unstaged. These should be committed in a separate "chore: ruff format" commit to avoid mixing with feature work.
