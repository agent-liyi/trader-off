---
date: 2026-07-22
spec: v0.6.0-001-qmt-gateway-live-trading
status: done
locked: false
---

# v0.6.0 — qmt-gateway live trading — Acceptance Criteria

## FR-0100 — QmtGatewayBroker

### AC-FR0100-01 — buy routes to /buy_stock
- **WHEN** `broker.buy("000001.SZ", 10.0, 100, qtoid="test")` is called
- **THEN** POST to `http://localhost:5800/buy_stock?symbol=000001.SZ&price=10.0&shares=100&qtoid=test` is made
- **AND** the response JSON is returned

### AC-FR0100-02 — sell routes to /sell_stock
- **WHEN** `broker.sell(...)` is called
- **THEN** POST to `/sell_stock` with same params

### AC-FR0100-03 — get_positions routes to /positions
- **WHEN** `broker.get_positions()` is called
- **THEN** GET `/positions` and returns parsed JSON

### AC-FR0100-04 — HTTP error raises RuntimeError
- **WHEN** qmt-gateway returns 4xx or 5xx
- **THEN** `RuntimeError` raised with status code + response body

### AC-FR0100-05 — connection refused
- **WHEN** gateway URL is unreachable
- **THEN** RuntimeError raised with connection error message

## FR-0200 — `trader-off live-trade`

### AC-FR0200-01 — strategy execution with QmtGatewayBroker
- **WHEN** `trader-off live-trade --strategy optimized_topk --universe watchlist.csv --gateway-url http://localhost:5800` is run
- **THEN** strategy runs, orders are sent to qmt-gateway via QmtGatewayBroker
- **AND** JSON output: `{"status":"ok","data":{"orders":N,"positions":N,"account":{...}}}`

### AC-FR0200-02 — env var fallback for API key
- **WHEN** `--gateway-api-key` is not provided but `QMT_GATEWAY_KEY` env var is set
- **THEN** the env var value is used

### AC-FR0200-03 — gateway unavailable
- **WHEN** gateway URL is unreachable
- **THEN** JSON error: `{"status":"error","code":4,"message":"gateway not reachable"}`

## NFR-0100 — function-scope lazy imports

### AC-NFR0100-01 — httpx is function-scope
- **WHEN** AST parses the broker file
- **THEN** `import httpx` is inside a function body, not at module level
