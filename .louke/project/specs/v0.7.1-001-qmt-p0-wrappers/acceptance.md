---
date: 2026-07-23
spec: v0.7.1-001-qmt-p0-wrappers
status: reviewing
---

# v0.7.1 — qmt-gateway P0 wrappers — Acceptance Criteria

- **Spec ID**: v0.7.1-001-qmt-p0-wrappers
- **Created**: 2026-07-23

> Central registry of acceptance criteria. spec.md keeps FR/NFR descriptions + metadata; detailed observable, assertable pass conditions live here.
> AC numbering: `### AC-N` within each unit (pure heading, no suffix); full reference `AC-FRXXXX-YY` on the next line.

<a id="ac-fr-0100">

## FR-0100 QmtGatewayBroker P0 wrappers (5 methods)

### AC-1
AC-FR0100-01
- **WHEN** `broker.get_connection_status()` is called on a `QmtGatewayBroker` whose `base_url` points at a stub returning `{"connected": true}` for `GET /connection_status`
- **THEN** a `GET` request is issued to `{base_url}/connection_status` with no query params
- **AND** the parsed JSON `{"connected": true}` is returned

### AC-2
AC-FR0100-02
- **WHEN** `broker.restart_qmt("s3cret")` is called against a stub returning `{"ok": true}` for `POST /restart_qmt`
- **THEN** a `POST` request is issued to `{base_url}/restart_qmt?password=s3cret`
- **AND** the parsed JSON is returned
- **AND** `qmt_gateway.py` contains no `logging` / `logger` / `open(` / `write(` call that references the `password` param (story §3.3 risk #2: query not locally persisted)

### AC-3
AC-FR0100-03
- **WHEN** `broker.search_stocks("平安")` is called against a stub returning `[{"symbol":"000001.SZ","name":"平安银行","market":"SZ"}]` for `GET /search_stocks`
- **THEN** a `GET` request is issued to `{base_url}/search_stocks?q=平安`
- **AND** the parsed `list[dict]` is returned unchanged

### AC-4
AC-FR0100-04
- **WHEN** `broker.get_stock_info("000001.SZ")` is called against a stub returning `{"symbol":"000001.SZ","name":"平安银行"}` for `GET /stock_info`
- **THEN** a `GET` request is issued to `{base_url}/stock_info?symbol=000001.SZ`
- **AND** the parsed JSON `dict` is returned unchanged (broker does not validate or transform keys)

### AC-5
AC-FR0100-05
- **WHEN** `broker.get_all_stocks()` is called against a stub returning a `list[dict]` for `GET /all_stocks`
- **THEN** a `GET` request is issued to `{base_url}/all_stocks` with no query params
- **AND** the full `list[dict]` is returned (no pagination, no caching, no size limit enforced by broker)

### AC-6
AC-FR0100-06
- **WHEN** any of the 5 methods receives a non-200 response, or encounters a network failure (connection refused / DNS error / timeout)
- **THEN** `RuntimeError` is raised (inherited from `_request`: non-200 → `HTTP {status}: {body}`; network failure → `Request failed: {error}`)
- **AND** the broker does not retry

<a id="ac-nfr-0100">

## NFR-0100 function-scope lazy imports (inherited)

### AC-1
AC-NFR0100-01
- **WHEN** `ast.parse` is run on `src/trader_off/broker/qmt_gateway.py`
- **THEN** every `import httpx` statement is located inside a function body (`_get_client` / `_request`)
- **AND** the 5 new methods add no module-level `import` (they reuse `_get` / `_post`)

### AC-2
AC-NFR0100-02
- **WHEN** the project dependency manifest (`pyproject.toml` / lockfile) is inspected
- **THEN** no new third-party dependency is introduced by v0.7.1 (`httpx` was already added in v0.6.0)
