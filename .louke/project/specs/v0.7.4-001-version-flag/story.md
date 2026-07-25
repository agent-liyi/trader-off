---
date: 2026-07-23
spec: v0.7.4-001-version-flag
status: draft
---

# v0.7.4 — version flag for all CLIs

## Goal
Add `--version` to all 15 CLI commands. Single source of truth in `src/trader_off/__init__.py`.

## Scope
- FR-0100: All 15 CLIs have `--version` printing `trader-off-<name> v<version>`
- FR-0200: Bump `__version__` from 0.1.0 to 0.7.4
- NFR-0100: function-scope lazy imports (inherited)

## Out of scope
- N/A

## Delivery
- `src/trader_off/__init__.py` — single source of `__version__`
- `src/trader_off/cli/_version.py` — shared `add_version_argument` helper
- All 15 CLI files — call `add_version_argument(parser, "<name>")`
