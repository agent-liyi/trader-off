---
date: 2026-07-22
spec: v0.6.0-001-qmt-gateway-live-trading
status: done
locked: false
---

# v0.6.0 — qmt-gateway live trading

## Goal
Implement live trading via `qmt-gateway` HTTP API. `QMTBroker` was removed from quantide main; the recommended path is the `qmt-gateway` standalone Windows service.

## Scope

### FR-0100 — QmtGatewayBroker
Create `src/trader_off/broker/qmt_gateway.py` — class wrapping qmt-gateway HTTP API.

Implements the quantide `Broker` interface via HTTP calls to:

| Method | HTTP endpoint |
|---|---|
| `get_account()` | GET `/asset` |
| `get_positions()` | GET `/positions` |
| `get_orders(status)` | GET `/orders?status=all` |
| `get_trades()` | GET `/trades` |
| `buy(symbol, price, shares, qtoid)` | POST `/buy_stock` |
| `sell(symbol, price, shares, qtoid)` | POST `/sell_stock` |
| `cancel_order(qtoid)` | POST `/cancel_order` |
| `set_principal(amount)` | POST `/update_principal` |

Init: `QmtGatewayBroker(base_url="http://localhost:5800", api_key=...)`

### FR-0200 — `trader-off live-trade` CLI
- Args:
  - `--strategy NAME` (required)
  - `--universe PATH` (required)
  - `--gateway-url URL` (default "http://localhost:5800")
  - `--gateway-api-key KEY` (env var QMT_GATEWAY_KEY fallback)
  - `--capital FLOAT` (default 1_000_000)
  - `--json`

- Behavior: same flow as `paper-trade` but with `QmtGatewayBroker` instead of `PaperBroker`.

### NFR-0100 — function-scope lazy imports (inherited)
Allowlist: `httpx` (HTTP client) — `httpx` is a NEW dependency, added in this version.

## External dependency
- `qmt-gateway` deployed (Windows service, default port 5800)
- QMT client installed + authorized
- `QMT_GATEWAY_KEY` env var (if gateway requires auth)
