---
date: 2026-07-25
spec: v0.7.5-001-unified-cli
status: draft
---

# v0.7.5 — Unified CLI — Acceptance Criteria

## FR-0100 — `to` unified CLI entry point

### AC-FR0100-01 — help output
- **WHEN** `to` is run with no arguments
- **THEN** exit code 0 and help text listing all 16 commands is printed to stdout

### AC-FR0100-02 — version flag
- **WHEN** `to --version` is run
- **THEN** stdout contains the version string and exit code 0

### AC-FR0100-03 — dispatch to subcommand
- **WHEN** `to backtest --help` is run
- **THEN** exit code 0 and argparse help for the backtest module is displayed (not the global help)

### AC-FR0100-04 — unknown command
- **WHEN** `to nonexistent` is run
- **THEN** exit code 2 and error message on stderr

### AC-FR0100-05 — args forwarded
- **WHEN** `to backtest --model v1 --help` is run
- **THEN** backtest's main() receives the exact arguments

### AC-FR0100-06 — lazy import
- **WHEN** `to status` is run
- **THEN** only `trader_off.cli.status` module is newly imported; other CLI modules are NOT loaded

### AC-FR0100-07 — backward compat
- **WHEN** `trader-off-backtest --help` is run (the per-command binary)
- **THEN** it still works as before

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — AST validation
- **WHEN** AST parses `src/trader_off/cli/main.py`
- **THEN** no `import quantide` at module level (all imports happen inside `main()`)
