---
date: 2026-07-22
spec: v0.5.9-001-check-factor
status: done
locked: false
---

# v0.5.9 — check-factor CLI

## Goal
Single-factor validity evaluation: IC / ICIR / Rank IC / Rank ICIR, with valid/invalid decision.

## Scope

### FR-0100 — `trader-off check-factor`
- Args:
  - `--name NAME` (required) — factor name (e.g., `momentum_5`)
  - `--start DATE` (required)
  - `--end DATE` (required)
  - `--ic-threshold FLOAT` (default 0.3) — minimum |ICIR| for valid
  - `--json` — JSON output

- Behavior:
  - Load OHLCV (QuantideDataLoader if TUSHARE_TOKEN, else fixture)
  - Compute labels (forward returns, N=5)
  - Find factor spec by name (enumerate templates)
  - Call `evaluate_factor(factor_values, labels, dates)` — function-scope lazy import
  - Return JSON with `ic`, `icir`, `rank_ic`, `rank_icir`, `valid`

### NFR-0100 — function-scope lazy imports (inherited)
Allowlist: `factor_mining.evaluation`, `factor_mining.templates`, `factor_mining.expression`, `trader_off.data.quantide_adapter.QuantideDataLoader`
