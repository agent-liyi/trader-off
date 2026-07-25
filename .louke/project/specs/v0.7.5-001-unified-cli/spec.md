---
date: 2026-07-25
spec: v0.7.5-001-unified-cli
status: draft
---

# v0.7.5 — Unified CLI (`to` command)

## Goal
Add a unified entry point `to` that dispatches to all 15 subcommands.

## Scope

### FR-0100 — `to` unified CLI entry point
- `to` (`src/trader_off/cli/main.py`) dispatches to per-command main() by name
- `to --help` prints command list
- `to backtest --help` delegates to the backtest module's help
- Lazy imports: only the subcommand's module is imported when run
- Backward compat: individual `trader-off-*` binaries still work

### FR-0200 — Standardize main() signatures
- All 15 CLI modules accept `main(argv: list[str] | None = None) -> int`
- prog strings use `"to <cmd>"` format
- `--version` shows `to <cmd> v<version>`

### NFR-0100 — function-scope lazy imports (inherited)

## Files changed
- NEW: `src/trader_off/cli/main.py` — unified dispatcher
- MODIFY: `pyproject.toml` — add `to = "trader_off.cli.main:main"` entry point
- MODIFY: all 15 CLI modules — main(argv) signature + prog string
- MODIFY: `src/trader_off/cli/_version.py` — version string format
