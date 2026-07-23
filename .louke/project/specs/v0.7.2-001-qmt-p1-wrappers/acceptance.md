---
date: 2026-07-23
spec: v0.7.2-001-qmt-p1-wrappers
status: reviewing
---

# v0.7.2 — qmt-gateway P1 wrappers — Acceptance Criteria

- **Spec ID**: v0.7.2-001-qmt-p1-wrappers
- **Created**: 2026-07-23

> Central registry of acceptance criteria. spec.md keeps FR/NFR descriptions + metadata; detailed observable, assertable pass conditions live here.
> AC numbering: `### AC-N` within each unit (pure heading, no suffix); full reference `AC-FRXXXX-YY` on the next line.

<a id="ac-fr-0100">

## FR-0100 QmtGatewayBroker P1 wrappers (4 methods)

### AC-1
AC-FR0100-01
- **WHEN** `broker.get_minutes_job("job-abc")` is called against a stub returning `{"job_id":"job-abc","status":"done","progress":100}` for `GET /minutes_job/job-abc`
- **THEN** a `GET` request is issued to `{base_url}/minutes_job/job-abc` (job_id interpolated into the path) with no query params
- **AND** the parsed JSON `dict` is returned unchanged

### AC-2
AC-FR0100-02
- **WHEN** `broker.download_minutes(dates=["2026-07-22","2026-07-23"])` is called against a stub returning `{"job_id":"job-xyz"}` for `POST /download_minutes`
- **THEN** a `POST` request is issued to `{base_url}/download_minutes` with `dates` passed as a query param (via the inherited `_post` → `params`)
- **AND** the parsed JSON `dict` containing `job_id` is returned unchanged (broker does not extract job_id, does not poll, does not impose a timeout)

### AC-3
AC-FR0100-03
- **WHEN** `broker.get_quote_status()` is called against a stub returning `{"subscribed":true,"symbols":["000001.SZ"]}` for `GET /quote_status`
- **THEN** a `GET` request is issued to `{base_url}/quote_status` with no query params
- **AND** the parsed JSON `dict` (WebSocket quote subscription state) is returned unchanged

### AC-4
AC-FR0100-04
- **WHEN** `broker.get_auction_status()` is called against a stub returning `{"phase":"pre_open","matched":false}` for `GET /auction_status`
- **THEN** a `GET` request is issued to `{base_url}/auction_status` with no query params
- **AND** the parsed JSON `dict` (call-auction matching state) is returned unchanged

### AC-5
AC-FR0100-05
- **WHEN** any of the 4 methods receives a non-200 response, or encounters a network failure (connection refused / DNS error / timeout)
- **THEN** `RuntimeError` is raised (inherited from `_request`: non-200 → `HTTP {status}: {body}`; network failure → `Request failed: {error}`)
- **AND** the broker does not retry

### AC-6
AC-FR0100-06
- **WHEN** `src/trader_off/broker/qmt_gateway.py` is inspected after the change
- **THEN** the existing 13 methods (8 trading v0.6.0 + 5 P0 v0.7.1) are unchanged in signature and behavior
- **AND** exactly 4 new public methods are added (`get_minutes_job`, `download_minutes`, `get_quote_status`, `get_auction_status`)

<a id="ac-nfr-0100">

## NFR-0100 function-scope lazy imports (inherited)

### AC-1
AC-NFR0100-01
- **WHEN** `ast.parse` is run on `src/trader_off/broker/qmt_gateway.py`
- **THEN** every `import httpx` statement is located inside a function body (`_get_client` / `_request`)
- **AND** the 4 new methods add no module-level `import` (they reuse `_get` / `_post`)

### AC-2
AC-NFR0100-02
- **WHEN** the project dependency manifest (`pyproject.toml` / lockfile) is inspected
- **THEN** no new third-party dependency is introduced by v0.7.2 (`httpx` was already added in v0.6.0)
