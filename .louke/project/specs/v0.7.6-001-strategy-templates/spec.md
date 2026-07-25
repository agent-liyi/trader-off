---
date: 2026-07-25
spec: v0.7.6-001-strategy-templates
status: draft
---

# v0.7.6 — Strategy templates for generate-strategy

## Goal
Add `--template` parameter with pre-built strategy implementations (double-ma, momentum, multi-factor).

## Scope

### FR-0100 — --template parameter
- `to generate-strategy --name X --template double-ma` → generates double-MA cross strategy
- `to generate-strategy --name X --template momentum` → generates momentum ranking strategy
- `to generate-strategy --name X --template multi-factor` → generates multi-factor z-score strategy
- Without `--template` → skeleton with empty lifecycle methods (backward compatible)

### NFR-0100 — function-scope lazy imports (inherited)

## Files changed
- MODIFY: `src/trader_off/cli/generate_strategy.py` — add `_TEMPLATES` dict + `--template` argparse
