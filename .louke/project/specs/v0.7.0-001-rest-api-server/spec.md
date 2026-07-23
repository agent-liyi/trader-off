---
date: 2026-07-23
spec: v0.7.0-001-rest-api-server
status: draft
---

# v0.7.0 — RESTful API server (FastAPI wrapping CLI internal functions)

- **Spec ID**: v0.7.0-001-rest-api-server
- **Created**: 2026-07-23
- **Status**: Draft

**Responsibility split**: This document only describes the requirements themselves (FR/NFR descriptions + metadata). Acceptance criteria (observable, assertable pass conditions) live in `acceptance.md` so they can grow without bloating spec. The test plan (`test-plan.md`) references both spec.md and acceptance.md as inputs.

## User Stories

### US-0010
story: As an LLM agent / quant researcher, I want to call trader-off's CLI internal functions over HTTP+JSON, so that I can run backtest / sync / factor workflows without fragile shell subprocess calls (encoding / exit-code / timeout pain).
priority: P0

### US-0020
story: As an LLM agent, I want a single `trader-off server` process I can start and then issue many HTTP calls against, so that integration is stable and standard.
priority: P0

## Usage Scenarios

### scenario-0010

1. Operator runs `trader-off server --port 8000` → uvicorn serves the FastAPI app on `127.0.0.1:8000`.
2. Agent issues `POST /backtest {"start":"2024-01-01","end":"2024-06-30", ...}`.
3. Server dispatches the backtest internal function to a threadpool (`run_in_executor`), waits synchronously, and returns `{"status":"ok","data":{...}}` field-for-field consistent with `trader-off-backtest --json`.
4. On failure the server returns `{"status":"error","code":N,"message":"..."}` with HTTP status mapped from the CLI exit code; no Python traceback leaks.
5. Agent polls `GET /api/health` to confirm liveness.

## Functional Requirements

**Format convention**: Each FR unit starts with a level-3 heading + FR-XXXX + title, followed by a 3-column metadata table (Valid / Testable / Decided), then the description; separate FRs with `---`.

**Metadata fields**: Valid `✅`=active / `❌`=deprecated; Testable `✅` / `⚠️ {reason}`; Decided `✅`=user approved / `⚠️`=pending / `❌`=rejected.

### FR-0100 REST API endpoints (FastAPI)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

Create `src/trader_off/api/server.py` — a FastAPI application that wraps the existing CLI internal functions as HTTP endpoints. The 14 internal functions are exposed as **13 endpoints (12 function endpoints + 1 health)** per the confirmed inventory:

- `POST /backtest` — run backtest
- `POST /paper-trade` — paper trading
- `POST /sync-data` — sync market data
- `GET /stock-list` — read stock list
- `POST /init` — initialize data
- `POST /grid-search` — grid search
- `POST /check-factor` — evaluate a single factor
- `POST /generate-strategy` — generate strategy
- `POST /live` — live quote / live mode
- `POST /live-trade` — live trading
- `POST /scheduler` — scheduler lifecycle control (start/stop)
- `GET /status` — read scheduler / system status
- `GET /api/health` — health check

**HTTP method rule** (confirmed): `GET` for read-only endpoints (`/api/health`, `/status`, `/stock-list`); `POST` for all action endpoints.

**Success contract**: success → HTTP 200 + `{"status":"ok","data":{...}}`, where `data` is field-for-field consistent with the corresponding CLI `--json` output (v0.5.4 contract). The 14 internal functions are NOT modified — wrapping only (story §3 Avoid).

**Error contract** (confirmed AC-02 shape): on internal-function error / non-zero exit code → `{"status":"error","code":N,"message":"..."}`. This is an extension of the `--json` contract (it adds a top-level numeric `code`; the CLI `--json` error shape `{"status":"error","data":{"message":...}}` is NOT reused verbatim — delta documented).

**Exit-code → HTTP status mapping**:

| CLI exit code | HTTP status | Meaning |
|---|---|---|
| 0 | 200 | success |
| 2 | 422 | input validation / file error |
| 4 | 400 | config error |
| 5 | 500 | evaluation failure |
| 1 | 500 | generic / not-found |
| 3 | 422 | business-rule failure |
| other | 500 | unspecified / fallback |

> **Sage [RESOLVED]:** AC-02 only pins exit-code→HTTP for codes 4→400, 5→500, 2→422. The existing CLIs also emit exit 0 (success), 1 (generic / not-found, e.g. `check-factor` returns 1 for "factor not found"), and 3 (business-rule, e.g. portfolio "too few assets", mine-factors "fewer than 10 factors"). Proposed completing the table as: 0→200, 1→500, 3→422, any other→500.
>> **User:** Accepted the proposed mapping.

**Execution model** (confirmed): blocking internal functions are dispatched via `asyncio.get_running_loop().run_in_executor(...)` so the uvicorn event loop is not blocked (story Risk #1 mitigation). The HTTP response remains synchronous — one request, one response, same call semantics as the subprocess path; NO job-id / polling surface.

**Binding & safety**: bound to `127.0.0.1` only (localhost); error middleware suppresses Python tracebacks (mirror `scheduler/api.py` pattern). Auth / authz / rate-limiting / TLS / multi-instance are explicitly Out-of-Scope (story §3).

**Request schema scope** (confirmed): spec/acceptance define the response envelope, error contract, and representative key params per endpoint; the exhaustive per-endpoint request JSON schema (full param→arg mapping, types, required) is deferred to `interfaces.md` (Prism).

---

### FR-0200 `trader-off server` CLI entry

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

Create `src/trader_off/cli/server.py` — the `trader-off server` CLI entry point.

**Args**:

- `--port` (default **8000**) — overridden from the story's 5800 due to the qmt-gateway port conflict (story §6 advisory; qmt-gateway v0.6.0 defaults to `http://localhost:5800`). Human ruling: use 8000.
- `--host` (default `"127.0.0.1"`)
- `--json` — when passed, emit a single startup JSON line for agent parsing: `{"status":"ok","data":{"host":"<host>","port":<port>}}` (AC-05).

**Behavior**: launches uvicorn programmatically (`uvicorn.run` / `uvicorn.Server`, NOT a subprocess) serving the FastAPI app from FR-0100 on `host:port`. `fastapi` / `uvicorn` are imported at function scope (see NFR-0100).

> **Sage [RESOLVED]:** AC-05 requires `--json` to emit startup info as "JSON line(s)" for agent parsing; the exact shape was unspecified. Proposed a single startup line consistent with the `--json` envelope: `{"status":"ok","data":{"host":"127.0.0.1","port":8000}}`.
>> **User:** Accepted the proposed shape.

---

## Non-Functional Requirements

### NFR-0100 function-scope lazy imports + new dependencies

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

**Inherited constraint** — function-scope lazy imports: `fastapi` and `uvicorn` MUST be imported inside function bodies, not at module top level, so that `trader-off` startup and the other 9 console scripts do not pay the new import cost. Verified by AST (no top-level `import fastapi` / `import uvicorn` in `api/server.py` or `cli/server.py`).

**New dependencies** (major-version locked):

- `fastapi>=0.115,<1.0`
- `uvicorn[standard]>=0.34,<1.0`

**Port-conflict resolution** (story §6): REST API default port changed 5800 → **8000** to avoid collision with qmt-gateway (v0.6.0, defaults `:5800`). Typical split-machine deployment (Mac trader-off server + remote Windows qmt-gateway) is unaffected; same-machine co-run no longer conflicts by default.

**Coexistence** (story §6 secondary point): the existing `scheduler/api.py` (aiohttp, `:8765`, 4 retrain endpoints) is NOT migrated into the new FastAPI server; the two HTTP surfaces coexist. Unification would require a separate story.

---

## Clarification Log

- 2026-07-23 Sage (Step-1 questioning): resolved 4 items with user — (1) execution model = `run_in_executor` + synchronous response (no job-id/polling); (2) error envelope = AC-02 shape `{"status":"error","code":N,"message":"..."}` (delta from CLI `--json` data-wrapper, documented); (3) GET/POST mapping = `/api/health` + `/status` + `/stock-list` are GET, all action endpoints POST; (4) schema scope = envelope + key params in spec, full per-endpoint schema deferred to `interfaces.md`.
- 2026-07-23 Sage: port default ruled **8000** by Human (story §6 advisory; qmt-gateway v0.6.0 occupies `:5800`).
- 2026-07-23 Sage: `scheduler/api.py` (aiohttp, `:8765`) NOT migrated; coexists with new FastAPI server (story §6 secondary point).
- 2026-07-23 Sage: "14 CLI internal functions" reconciled to the user-provided inventory of **12 function endpoints + `/api/health` = 13 endpoints**. Import-existence verification of the 14 internal functions is deferred to M-DEV (story Risk #1, owner Devon).
- 2026-07-23 Sage (Step-3 resolution): both open quotes resolved with user — (1) exit-code→HTTP mapping completed: 0→200, 1→500, 3→422, other→500 (in addition to 2→422, 4→400, 5→500); (2) `--json` startup shape = `{"status":"ok","data":{"host":"<host>","port":<port>}}`. FR-0100 / FR-0200 flipped ⚠️→✅. All threads resolved.
