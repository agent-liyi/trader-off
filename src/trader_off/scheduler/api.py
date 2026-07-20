"""Scheduler REST API (aiohttp, localhost only).

FR-2000: Manual trigger and status endpoints.
Per interfaces.md §5.4: POST /retrain/trigger, GET /retrain/status,
POST /retrain/cancel/{task_id}, GET /health.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from trader_off.scheduler.core import RetrainScheduler

logger = logging.getLogger(__name__)


def create_app(scheduler: RetrainScheduler) -> web.Application:
    """Create an aiohttp web.Application with retrain routes.

    The returned app exposes trigger, status, cancel, and health
    endpoints that delegate to the injected RetrainScheduler.

    Args:
        scheduler: A RetrainScheduler instance. Should be started before
            the app begins serving.

    Returns:
        A configured aiohttp web.Application.
    """
    app = web.Application()

    # POST /retrain/trigger
    app.router.add_post("/retrain/trigger", _handle_trigger(scheduler))

    # GET /retrain/status
    app.router.add_get("/retrain/status", _handle_status(scheduler))

    # POST /retrain/cancel/{task_id}
    app.router.add_post(
        r"/retrain/cancel/{task_id}", _handle_cancel(scheduler)
    )

    # GET /health
    app.router.add_get("/health", _handle_health)

    # Error handler: suppress tracebacks
    app.middlewares.append(_error_middleware)

    return app


async def run_app(
    scheduler: RetrainScheduler,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Convenience wrapper to run the aiohttp app on the given host:port.

    Binds to 127.0.0.1 by default per NFR-0700 AC-4.

    Args:
        scheduler: A RetrainScheduler instance.
        host: Bind address (default 127.0.0.1).
        port: Port number (default 8765).
    """
    app = create_app(scheduler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Retrain API listening on http://%s:%d", host, port)


# ---------------------------------------------------------------------------
# Route handlers (closures that capture the scheduler)
# ---------------------------------------------------------------------------


def _handle_trigger(scheduler):
    async def handler(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response(
                {"error": "invalid json"}, status=400
            )

        mode = body.get("mode")
        if mode not in ("full", "incremental"):
            return web.json_response(
                {"error": "mode is required and must be 'full' or 'incremental'"},
                status=400,
            )

        reason = body.get("reason", "manual")
        from trader_off.scheduler.ports import TriggerReason

        # Map reason string to TriggerReason; default to MANUAL
        try:
            trigger_reason = TriggerReason(reason)
        except ValueError:
            trigger_reason = TriggerReason.MANUAL
            logger.warning(
                "Unknown reason '%s', defaulting to manual", reason
            )

        task = await scheduler.trigger_now(trigger_reason, mode)
        return web.json_response(
            {"task_id": task.task_id, "status": task.status}
        )

    return handler


def _handle_status(scheduler):
    async def handler(request: web.Request) -> web.Response:
        status = await scheduler.get_status()
        # Collect last 10 tasks from scheduler's internal history
        last_10_tasks = []
        if hasattr(scheduler, "_task_history"):
            for task in scheduler._task_history[-10:]:
                reason_str = (
                    task.reason.value
                    if hasattr(task.reason, "value")
                    else str(task.reason)
                )
                last_10_tasks.append({
                    "task_id": task.task_id,
                    "mode": task.mode,
                    "reason": reason_str,
                    "status": task.status,
                    "start_time": (
                        task.start_time.isoformat() if task.start_time else None
                    ),
                    "end_time": (
                        task.end_time.isoformat() if task.end_time else None
                    ),
                    "error": task.error,
                    "new_version": task.new_version,
                })

        return web.json_response({
            "active_tasks": status.active_tasks,
            "last_10_tasks": last_10_tasks,
        })

    return handler


def _handle_cancel(scheduler):
    async def handler(request: web.Request) -> web.Response:
        task_id = request.match_info["task_id"]
        # Check if task exists in scheduler history
        found = False
        if hasattr(scheduler, "_task_history"):
            for task in scheduler._task_history:
                if task.task_id == task_id:
                    found = True
                    # Only cancel pending tasks
                    if task.status == "pending":
                        task.status = "failed"
                        task.error = "cancelled by user"
                        return web.json_response({"cancelled": True})
                    break

        if not found:
            return web.json_response(
                {"error": f"task {task_id} not found"}, status=404
            )
        return web.json_response({"cancelled": False})

    return handler


async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


# ---------------------------------------------------------------------------
# Middleware: suppress internal tracebacks in error responses
# ---------------------------------------------------------------------------


@web.middleware
async def _error_middleware(request: web.Request, handler) -> web.Response:
    """Catch unhandled exceptions and return a clean 500 without traceback."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in API handler")
        return web.json_response(
            {"error": "internal server error"}, status=500
        )
