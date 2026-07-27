---
date: 2026-07-23
session: devon-v0.7.0-001-rest-api-server
agents: [Devon]
spec: v0.7.0-001-rest-api-server
related_issues: [#164, #165, #166]
status: resolved
---

## Topic
Implement REST API server (FastAPI) wrapping CLI internal functions for v0.7.0.

## Decision

### FR-0100 FastAPI REST server (`src/trader_off/api/server.py`)
- Created `create_app()` factory returning FastAPI app with 19 endpoints
- **POST endpoints** (12): /api/backtest, /api/sync-data, /api/init, /api/mine-factors, /api/optimize, /api/check-factor, /api/live-trade, /api/scheduler, /api/paper-trade, /api/grid-search, /api/generate-strategy, /api/live
- **GET endpoints** (7): /api/health, /api/status, /api/status/data, /api/status/models, /api/live, /api/scheduler/status, /api/stock-list
- `run_in_executor` used for all sync CLI calls
- Exit code → HTTP status mapping per spec (0→200, 1→500, 2→422, 3→422, 4→400, 5→500)
- Error middleware suppresses Python tracebacks
- 4 NYI endpoints (paper-trade, grid-search, generate-strategy, live) return 501
- **Lazy imports**: `from __future__ import annotations` removed because it prevents FastAPI from recognizing `Request` type via `inspect.signature()` (PEP 563 makes annotations strings)

### FR-0200 `trader-off server` CLI (`src/trader_off/cli/server.py`)
- argparse: --port (default 8000, NOT 5800 per qmt-gateway conflict), --host (default 127.0.0.1), --json
- Launch uvicorn programmatically via `uvicorn.run(app, ...)`
- `--json` flag emits startup JSON before launching server
- Registered as `trader-off-server` in pyproject.toml

### NFR-0100 lazy imports
- fastapi imported at function scope in `create_app()`
- uvicorn imported at function scope in `main()`
- Verified via AST tests (no module-level import of fastapi or uvicorn)

## Tried but abandoned

1. **`from fastapi import Request` with `from __future__ import annotations`**: FastAPI couldn't resolve `Request` as a special dependency type because PEP 563 stringifies all annotations. Removed `from __future__ import annotations` and used `starlette.requests.Request` instead.

2. **`starlette.requests.Request` with `from __future__ import annotations`**: Same PEP 563 issue. Ultimately removed the future import entirely (Python 3.13+ supports `dict[str, Any]` natively without it).

3. **Calling `scheduler/cli.py:main()` directly**: The scheduler CLI uses `build_retrain_parser()` (retrain subcommands: trigger/status), not `build_scheduler_parser()` (scheduler subcommands: start/stop/status). Wrote a separate `_run_scheduler_sync()` handler instead.

## Open questions
- None — all spec topics resolved.
