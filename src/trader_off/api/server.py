"""REST API server (FastAPI) wrapping trader-off CLI internal functions.

FR-0100: All endpoints exposed via FastAPI + uvicorn.
NFR-0100: fastapi is imported at function scope (lazy import).
"""

import asyncio
import importlib
import traceback
from typing import Any

# ---------------------------------------------------------------------------
# CLI exit code → HTTP status mapping (spec FR-0100)
# ---------------------------------------------------------------------------

_EXIT_CODE_STATUS: dict[int, int] = {
    0: 200,
    1: 500,
    2: 422,
    3: 422,
    4: 400,
    5: 500,
}


def _map_exit_code(exit_code: int) -> int:
    """Map CLI exit code to HTTP status code."""
    return _EXIT_CODE_STATUS.get(exit_code, 500)


# ---------------------------------------------------------------------------
# argv builder — converts JSON params dict → CLI argv list
# ---------------------------------------------------------------------------


def _params_to_argv(params: dict[str, Any]) -> list[str]:
    """Convert a JSON params dict to a CLI argv list.

    Args:
        params: Dict of parameter names to values.

    Returns:
        A list of CLI argument strings suitable for argparse.
    """
    argv: list[str] = []
    for key, value in params.items():
        flag = f"--{key.replace('_', '-')}"
        if value is True:
            argv.append(flag)
        elif value is False or value is None:
            continue
        elif isinstance(value, list):
            for item in value:
                argv.append(flag)
                argv.append(str(item))
        else:
            argv.append(flag)
            argv.append(str(value))
    return argv


# ---------------------------------------------------------------------------
# Generic CLI runner — dispatches to module.main(argv) via run_in_executor
# ---------------------------------------------------------------------------


def _run_cli_sync(module_path: str, params: dict[str, Any]) -> int:
    """Import a CLI module and call its main(argv); returns exit code.

    Args:
        module_path: Dotted import path, e.g. ``trader_off.cli.sync_data``.
        params: JSON params dict to convert to argv.

    Returns:
        CLI exit code (0 = success).
    """
    mod = importlib.import_module(module_path)
    main_func = getattr(mod, "main")
    argv = _params_to_argv(params)
    try:
        return main_func(argv)
    except SystemExit as e:
        code = e.code
        if isinstance(code, int):
            return code
        return 1
    except Exception:
        traceback.print_exc()
        return 1


async def _run_cli_in_executor(module_path: str, params: dict[str, Any]) -> int:
    """Run a CLI module's main() in a threadpool executor.

    Args:
        module_path: Dotted import path.
        params: JSON params dict.

    Returns:
        CLI exit code.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_cli_sync, module_path, params)


# ---------------------------------------------------------------------------
# Backtest — special handler (main() doesn't accept argv)
# ---------------------------------------------------------------------------


def _run_backtest_sync(params: dict[str, Any]) -> int:
    """Run backtest via the internal run_backtest function.

    Args:
        params: JSON params dict with model, strategy, start, end, capital.

    Returns:
        Exit code: 0 success, 4 config error, 5 engine failure.
    """
    from datetime import date

    from trader_off.backtest.runner import run_backtest

    model = params.get("model")
    strategy = params.get("strategy")
    if not model or not strategy:
        return 2

    try:
        start = date.fromisoformat(params.get("start", "2024-01-01"))
        end = date.fromisoformat(params.get("end", "2024-06-30"))
    except (ValueError, TypeError):
        return 2

    capital = float(params.get("capital", 1_000_000))
    config = params.get("config")

    try:
        run_backtest(
            model_version=str(model),
            strategy_name=str(strategy),
            start=start,
            end=end,
            capital=capital,
            config=config,
        )
        return 0
    except RuntimeError:
        return 5
    except Exception:
        return 5


async def _run_backtest_in_executor(params: dict[str, Any]) -> int:
    """Run backtest in a threadpool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_backtest_sync, params)


# ---------------------------------------------------------------------------
# Scheduler runner
# ---------------------------------------------------------------------------


def _run_scheduler_sync(params: dict[str, Any]) -> int:
    """Run scheduler lifecycle command via internal functions.

    Args:
        params: JSON body with optional ``action`` key (start, stop, status).

    Returns:
        Exit code: 0 on success, 2 on invalid action.
    """
    action = params.get("action", "start")
    config_path = params.get("config")

    if action == "status":
        return 0

    if action in ("start", "stop"):
        if action == "start" and config_path:
            from pathlib import Path

            from trader_off.scheduler.cli import load_scheduler_config

            try:
                load_scheduler_config(Path(config_path))
            except Exception:
                return 4
        return 0

    return 2


async def _run_scheduler_in_executor(params: dict[str, Any]) -> int:
    """Run scheduler command in a threadpool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_scheduler_sync, params)


# ---------------------------------------------------------------------------
# Fallback for modules that don't exist yet
# ---------------------------------------------------------------------------

_NOT_IMPLEMENTED_MODULES = {
    "paper-trade": "Paper trade module not yet implemented",
    "grid-search": "Grid search module not yet implemented",
    "generate-strategy": "Generate strategy module not yet implemented",
    "live": "Live trading module not yet implemented",
}


# ---------------------------------------------------------------------------
# FastAPI app factory (NFR-0100: fastapi imported at function scope)
# ---------------------------------------------------------------------------


def create_app():
    """Create the FastAPI application with all v0.7.0 REST endpoints.

    All ``fastapi`` imports are function-scope per NFR-0100.

    Returns:
        A configured FastAPI application instance.
    """
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from starlette.requests import Request

    app = FastAPI(title="trader-off REST API", version="v0.7.0")

    # ------------------------------------------------------------------
    # Error middleware — suppresses Python tracebacks (mirrors scheduler/api.py)
    # ------------------------------------------------------------------

    @app.middleware("http")
    async def _error_middleware(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "code": 5,
                    "message": "internal server error",
                },
            )

    # ------------------------------------------------------------------
    # GET /api/health
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "v0.7.0"}

    # ==================================================================
    # POST endpoints — action commands
    # ==================================================================

    # --- POST /backtest ---

    @app.post("/backtest")
    async def api_backtest(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_backtest_in_executor(body)
        except Exception:
            code = 5
        http_code = _map_exit_code(code)
        if code == 0:
            return JSONResponse(
                status_code=http_code,
                content={"status": "ok", "data": {"exit_code": 0}},
            )
        return JSONResponse(
            status_code=http_code,
            content={
                "status": "error",
                "code": code,
                "message": f"backtest failed (exit code {code})",
            },
        )

    # --- POST /sync-data ---

    @app.post("/sync-data")
    async def api_sync_data(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_cli_in_executor("trader_off.cli.sync_data", body)
        except Exception:
            code = 1
        return _cli_result_to_response(code, "sync-data")

    # --- POST /init ---

    @app.post("/init")
    async def api_init(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_cli_in_executor("trader_off.cli.init_data", body)
        except Exception:
            code = 1
        return _cli_result_to_response(code, "init")

    # --- POST /mine-factors ---

    @app.post("/mine-factors")
    async def api_mine_factors(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_cli_in_executor("trader_off.factor_mining.cli", body)
        except Exception:
            code = 1
        return _cli_result_to_response(code, "mine-factors")

    # --- POST /optimize ---

    @app.post("/optimize")
    async def api_optimize(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_cli_in_executor("trader_off.portfolio.cli", body)
        except Exception:
            code = 1
        return _cli_result_to_response(code, "optimize")

    # --- POST /check-factor ---

    @app.post("/check-factor")
    async def api_check_factor(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_cli_in_executor("trader_off.cli.check_factor", body)
        except Exception:
            code = 1
        return _cli_result_to_response(code, "check-factor")

    # --- POST /live-trade ---

    @app.post("/live-trade")
    async def api_live_trade(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_cli_in_executor("trader_off.cli.live_trade", body)
        except Exception:
            code = 1
        return _cli_result_to_response(code, "live-trade")

    # --- POST /scheduler ---

    @app.post("/scheduler")
    async def api_scheduler(request: Request) -> JSONResponse:
        body = await _safe_json(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            code = await _run_scheduler_in_executor(body)
        except Exception:
            code = 1
        return _cli_result_to_response(code, "scheduler")

    # --- POST /paper-trade (NYI) ---
    @app.post("/paper-trade")
    async def api_paper_trade() -> JSONResponse:
        return _not_implemented("paper-trade")

    # --- POST /grid-search (NYI) ---
    @app.post("/grid-search")
    async def api_grid_search() -> JSONResponse:
        return _not_implemented("grid-search")

    # --- POST /generate-strategy (NYI) ---
    @app.post("/generate-strategy")
    async def api_generate_strategy() -> JSONResponse:
        return _not_implemented("generate-strategy")

    # --- POST /live/start (NYI) ---
    @app.post("/live/start")
    async def api_live_start() -> JSONResponse:
        return _not_implemented("live")

    # --- POST /live/stop (NYI) ---
    @app.post("/live/stop")
    async def api_live_stop() -> JSONResponse:
        return _not_implemented("live")

    # ==================================================================
    # GET endpoints — read-only status queries
    # ==================================================================

    # --- GET /stock-list ---

    @app.get("/stock-list")
    async def api_stock_list(request: Request) -> JSONResponse:
        try:
            code = await _run_cli_in_executor("trader_off.cli.stock_list", {})
        except Exception:
            code = 1
        return _cli_result_to_response(code, "stock-list")

    # --- GET /status ---

    @app.get("/status")
    async def api_status() -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {"server": "running", "version": "v0.7.0"},
        }

    # --- GET /status/data ---

    @app.get("/status/data")
    async def api_status_data() -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {"data_status": "unknown", "last_sync": None},
        }

    # --- GET /status/models ---

    @app.get("/status/models")
    async def api_status_models() -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {"models": [], "active_model": None},
        }

    # --- GET /live ---

    @app.get("/live")
    async def api_live_status() -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {"live": "not running", "connected": False},
        }

    # --- GET /scheduler/status ---

    @app.get("/scheduler/status")
    async def api_scheduler_status() -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {"scheduler": "unknown", "running": False},
        }

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _safe_json(request) -> dict[str, Any] | Any:
    """Safely parse JSON body; returns a 400 error response on failure."""
    from fastapi.responses import JSONResponse

    try:
        return await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "code": 2,
                "message": "invalid json body",
            },
        )


def _cli_result_to_response(exit_code: int, name: str):
    """Convert a CLI exit code to an HTTP JSON response."""
    from fastapi.responses import JSONResponse

    http_code = _map_exit_code(exit_code)
    if exit_code == 0:
        return JSONResponse(
            status_code=http_code,
            content={"status": "ok", "data": {"exit_code": 0}},
        )
    return JSONResponse(
        status_code=http_code,
        content={
            "status": "error",
            "code": exit_code,
            "message": f"{name} failed (exit code {exit_code})",
        },
    )


def _not_implemented(name: str):
    """Return a 501 Not Implemented response for missing modules."""
    from fastapi.responses import JSONResponse

    msg = _NOT_IMPLEMENTED_MODULES.get(name, f"{name} not implemented")
    return JSONResponse(
        status_code=501,
        content={
            "status": "error",
            "code": 1,
            "message": msg,
        },
    )
