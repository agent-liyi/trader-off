---
date: 2026-07-23
spec: v0.7.0-001-rest-api-server
status: draft
---

# v0.7.0 — RESTful API server — Acceptance Criteria

- **Spec ID**: v0.7.0-001-rest-api-server
- **Created**: 2026-07-23

> Central registry of acceptance criteria. spec.md keeps FR/NFR descriptions + metadata; detailed observable, assertable pass conditions live here.
>
> Numbering: within each FR/NFR unit, AC-N starts from 1 and increments; full reference **AC-FRXXXX-YY** (4-digit FR + 2-digit AC) shown on the line below the heading.

## FR-0100 REST API endpoints (FastAPI)

### AC-1
AC-FR0100-01
- **WHEN** an agent sends `POST /backtest` with a valid JSON body (e.g. `{"start":"2024-01-01","end":"2024-06-30"}`)
- **THEN** the server invokes the backtest internal function and returns HTTP 200
- **AND** the body is `{"status":"ok","data":{...}}` whose `data` is field-for-field consistent with `trader-off-backtest --json` output.

### AC-2
AC-FR0100-02
- **WHEN** an agent sends `GET /api/health`
- **THEN** the server returns HTTP 200 with `{"status":"ok"}`.

### AC-3
AC-FR0100-03
- **WHEN** an internal function raises an error or returns a non-zero exit code
- **THEN** the server returns `{"status":"error","code":N,"message":"..."}` where `N` is the CLI exit code
- **AND** the HTTP status is mapped per the spec table (0→200, 2→422, 4→400, 5→500; 1→500, 3→422, other→500 per confirmed mapping)
- **AND** the response body contains no Python traceback.

### AC-4
AC-FR0100-04
- **WHEN** a long-running endpoint (`/backtest`, `/sync-data`, `/grid-search`) is invoked
- **THEN** the internal function executes in a threadpool via `run_in_executor` (not on the uvicorn event loop)
- **AND** the HTTP exchange is a single synchronous request→response with no `job_id` / polling surface.

### AC-5
AC-FR0100-05
- **WHEN** the server is running
- **THEN** it binds only to `127.0.0.1` (loopback); a connection to any non-loopback interface is not accepted.

### AC-6
AC-FR0100-06
- **WHEN** an agent sends `GET /status` or `GET /stock-list`
- **THEN** the server returns HTTP 200 with `{"status":"ok","data":{...}}` consistent with the corresponding `--json` CLI output.

### AC-7
AC-FR0100-07
- **WHEN** the FastAPI app routes are enumerated
- **THEN** all 13 endpoints exist: 10 POST (`/backtest`, `/paper-trade`, `/sync-data`, `/init`, `/grid-search`, `/check-factor`, `/generate-strategy`, `/live`, `/live-trade`, `/scheduler`) and 3 GET (`/stock-list`, `/status`, `/api/health`).

## FR-0200 `trader-off server` CLI entry

### AC-1
AC-FR0200-01
- **WHEN** the user runs `trader-off server --port 8000 --host 127.0.0.1`
- **THEN** uvicorn is launched programmatically (not as a subprocess) and serves the FastAPI app from FR-0100 on `127.0.0.1:8000`.

### AC-2
AC-FR0200-02
- **WHEN** `trader-off server` is run with no `--port`
- **THEN** the default port is **8000** (NOT 5800).

### AC-3
AC-FR0200-03
- **WHEN** `trader-off server --json` is run
- **THEN** a single startup JSON line is emitted: `{"status":"ok","data":{"host":"<host>","port":<port>}}`, parseable by an agent.

### AC-4
AC-FR0200-04
- **WHEN** `trader-off server` is run with no `--host`
- **THEN** the default host is `127.0.0.1`.

### AC-5
AC-FR0200-05
- **WHEN** the server CLI module is parsed
- **THEN** `uvicorn` / `fastapi` are imported at function scope, not at module top level.

## NFR-0100 function-scope lazy imports + new dependencies

### AC-1
AC-NFR0100-01
- **WHEN** `src/trader_off/api/server.py` and `src/trader_off/cli/server.py` are AST-parsed
- **THEN** there is no top-level `import fastapi` or `import uvicorn`; both imports live inside function bodies.

### AC-2
AC-NFR0100-02
- **WHEN** `pyproject.toml` dependencies are inspected
- **THEN** `fastapi>=0.115,<1.0` and `uvicorn[standard]>=0.34,<1.0` are present with major-version upper bounds.

### AC-3
AC-NFR0100-03
- **WHEN** the default port is observed
- **THEN** it is 8000 (port-conflict resolution vs qmt-gateway `:5800`, story §6).
