---
date: 2026-07-22
session: devon-v0.5.8-generate-strategy-cli
agents: [Devon]
spec: v0.5.8-001-generate-strategy
related_issues: [#156]
status: resolved
---

## Topic
FR-0100: Implement `trader-off-generate-strategy` CLI that generates strategy class skeleton files.

## Decision

### Created files
- `src/trader_off/cli/generate_strategy.py` — CLI with `main(argv)`, argparse, code generation template, dry-run, JSON output
- `tests/unit/cli/test_generate_strategy.py` — 43 unit tests covering: CamelCase→snake_case, filename dedup, code generation template, argparse exit codes, dry-run, file creation, JSON output, author/description flags

### Modified files
- `pyproject.toml` — added `trader-off-generate-strategy` entry point
- `README.md` — added "生成策略" section with usage examples
- `tests/unit/test_console_scripts.py` — updated expected scripts count (7→8), added generate_strategy signature expectations

### Implementation details
- 5 lifecycle methods generated: `__init__`, `on_day_open`, `on_bar`, `on_day_close`, `on_stop`
- No `init` method (FR explicitly lists 5 methods, `methods: 5` in JSON output)
- Imports BaseStrategy from `trader_off.strategies.compat`
- Each method body has `logger.debug("ClassName.method called")`
- `--dry-run` prints code to stdout; `--dry-run --json` prints JSON with code content
- File dedup: appends `_1`, `_2`, etc. suffix when target file exists
- Snake_case conversion handles acronyms (LGBMTop20→lgbm_top20) and CamelCase transitions

### Commits
1. `fef21dc` — feat: green – #156 – generate-strategy CLI
2. `ea0b66f` — refactor: move json import to module level

## Tried but abandoned
- Considered including `init()` lifecycle method but FR explicitly lists 5 methods and output shows `methods: 5`
- Considered extracting template to a separate file but single f-string template is clearer for a code generator

## Open questions
- None
