---
date: 2026-07-22
spec: v0.5.7-001-live-quote
status: done
locked: false
---

# v0.5.7 — live quote CLI

## Goal
Wrap `quantide.service.livequote.LiveQuote` for real-time market data subscription.

## Scope

### FR-0100 — `trader-off live`
- Args:
  - `--start` — start subscription
  - `--stop` — stop subscription
  - `--status` — check running state (default)
  - `--assets LIST` — comma-separated stock codes
  - `--json` — JSON output

- Behavior:
  - Function-scope lazy import: `from quantide.service.livequote import LiveQuote`
  - On `--start`: instantiate `LiveQuote()`, call `start()`, return JSON
  - On `--stop`: call `stop()`
  - On `--status`: return `{"running":<bool>}`
  - On no gateway: return error JSON with explanation

### NFR-0100 — function-scope lazy imports (inherited)

## External dependency
Requires `qmt-gateway` deployed (independent Windows service). LiveQuote connects to `gateway_base_url/ws/quotes`.
