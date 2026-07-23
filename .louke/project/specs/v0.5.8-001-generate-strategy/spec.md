---
date: 2026-07-22
spec: v0.5.8-001-generate-strategy
status: done
locked: false
---

# v0.5.8 — generate-strategy CLI

## Goal
Scaffold a new quantide `BaseStrategy` subclass with all lifecycle methods as async stubs.

## Scope

### FR-0100 — `trader-off generate-strategy`
- Args:
  - `--name NAME` (required) — class name (e.g., `MomentumReversion`)
  - `--author AUTHOR` (default from git config or "trader-off")
  - `--description DESC` (default "Generated strategy")
  - `--output-dir PATH` (default `src/trader_off/strategies/`)
  - `--dry-run` — print to stdout instead of writing
  - `--json` — JSON output

- Behavior:
  - Generate `{name_snake}.py` with:
    - Module docstring (date, author, description)
    - Import from `compat.py` (BaseStrategy)
    - Class inheriting BaseStrategy
    - All lifecycle methods implemented as async stubs:
      - `__init__(broker, config)`
      - `on_day_open(tm)`
      - `on_bar(tm, quote, frame_type)`
      - `on_day_close(tm)`
      - `on_stop()`

### NFR-0100 — function-scope lazy imports (inherited)
