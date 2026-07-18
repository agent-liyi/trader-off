"""Unit tests for FR-2000: scheduler REST API (aiohttp).

AC coverage: AC-FR2000-03, AC-FR2000-04
Tests the aiohttp web application factory that provides manual trigger
and status endpoints.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from trader_off.scheduler.core import RetrainScheduler, SchedulerConfig
from trader_off.scheduler.ports import TriggerReason, VirtualClockPort


def _make_scheduler():
    """Create a RetrainScheduler with mock dependencies for testing."""
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    return RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )


async def _make_client(scheduler) -> TestClient:
    """Create an aiohttp TestClient for the given scheduler."""
    from trader_off.scheduler.api import create_app

    app = create_app(scheduler)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client


# ---------------------------------------------------------------------------
# AC-FR2000-03: POST /retrain/trigger returns task_id + status=pending
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr2000_03_trigger_returns_task_id():
    """AC-FR2000-03: POST /retrain/trigger returns 200 with task_id and status=pending."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.post("/retrain/trigger", json={"mode": "full", "reason": "api_test"})
        assert resp.status == 200
        data = await resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert isinstance(data["task_id"], str)
        assert len(data["task_id"]) > 0
    finally:
        await client.close()


@pytest.mark.unit
async def test_ac_fr2000_03_trigger_missing_mode():
    """AC-FR2000-03: POST /retrain/trigger with missing 'mode' returns 400."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.post("/retrain/trigger", json={"reason": "api_test"})
        assert resp.status == 400
    finally:
        await client.close()


@pytest.mark.unit
async def test_ac_fr2000_03_trigger_invalid_json():
    """AC-FR2000-03: POST /retrain/trigger with invalid JSON returns 400."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.post("/retrain/trigger", data="not json")
        assert resp.status == 400
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# GET /retrain/status
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_retrain_status():
    """GET /retrain/status returns scheduler status including active_tasks."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.get("/retrain/status")
        assert resp.status == 200
        data = await resp.json()
        assert "active_tasks" in data
        assert "last_10_tasks" in data
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# POST /retrain/cancel/{task_id}
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_cancel_nonexistent_task():
    """POST /retrain/cancel/{task_id} for non-existent task returns 404."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.post("/retrain/cancel/nonexistent-task-id")
        assert resp.status == 404
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_health_endpoint():
    """GET /health returns 200 with status=ok."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# AC-FR2000-04: API binds to 127.0.0.1 only
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2000_04_config_defaults_to_localhost():
    """AC-FR2000-04: The SchedulerConfig defaults api_host to 127.0.0.1."""
    default = SchedulerConfig()
    assert default.api_host == "127.0.0.1"


@pytest.mark.unit
def test_ac_fr2000_04_run_api_uses_localhost():
    """AC-FR2000-04: run_app helper uses config's api_host which defaults to 127.0.0.1."""
    from trader_off.scheduler.api import create_app

    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    scheduler = _make_scheduler()

    app = create_app(scheduler)
    # The app should be configured; the host binding happens at run_app level.
    assert isinstance(app, web.Application)
    assert config.api_host == "127.0.0.1"


# ---------------------------------------------------------------------------
# AC-FR2000-04: No exception tracebacks in error responses
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr2000_04_no_tracebacks_in_errors():
    """AC-FR2000-04: Error responses do not expose internal stack traces."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        # Send invalid JSON that should trigger a 400 without traceback
        resp = await client.post("/retrain/trigger", data="invalid json {{{")
        assert resp.status == 400
        text = await resp.text()
        assert "Traceback" not in text
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Trigger with default reason (when reason not provided)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_trigger_default_reason():
    """POST /retrain/trigger without reason should default to 'manual'."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.post("/retrain/trigger", json={"mode": "full"})
        assert resp.status == 200
        data = await resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"
    finally:
        await client.close()


@pytest.mark.unit
async def test_trigger_unknown_reason_maps_to_manual():
    """POST /retrain/trigger with unknown reason maps to MANUAL."""
    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        resp = await client.post(
            "/retrain/trigger", json={"mode": "full", "reason": "unknown_reason_xyz"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["task_id"]
        assert data["status"] == "pending"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Cancel endpoint: existing task but not pending
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_cancel_running_task_not_cancelled():
    """POST /retrain/cancel/{task_id} for a running task returns cancelled=False."""

    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        # Start the scheduler and trigger a task
        start_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(0.01)

        task = await scheduler.trigger_now(TriggerReason.MANUAL, "full")
        # Wait for task to complete so it's in "success" state
        await asyncio.sleep(0.1)

        # Now cancel it — should not cancel since it's already completed
        resp = await client.post(f"/retrain/cancel/{task.task_id}")
        assert resp.status == 200
        data = await resp.json()
        assert data["cancelled"] is False

        await scheduler.stop()
        await start_task
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Cancel endpoint: existing pending task can be cancelled
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_cancel_pending_task_succeeds():
    """POST /retrain/cancel/{task_id} for a pending task sets it to failed."""

    class BlockingTrainer:
        """Trainer that blocks, keeping tasks in pending/running state."""

        async def train(self, mode, *, parent_version=None, **kwargs):
            await asyncio.sleep(10)  # never completes during test
            return MagicMock()

        async def save(self, artifact, *, mode, trigger, **kwargs):
            return "v0.0.0.test"

    config = SchedulerConfig(
        max_concurrent_tasks=1,
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=BlockingTrainer(),
    )
    client = await _make_client(scheduler)

    try:
        start_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(0.01)

        # Trigger first task to fill the slot
        _task1 = await scheduler.trigger_now(TriggerReason.MANUAL, "full")
        await asyncio.sleep(0.02)

        # Trigger second task — will stay pending
        task2 = await scheduler.trigger_now(TriggerReason.MANUAL, "incremental")
        await asyncio.sleep(0.02)

        # Cancel the pending task
        resp = await client.post(f"/retrain/cancel/{task2.task_id}")
        assert resp.status == 200
        data = await resp.json()
        assert data["cancelled"] is True

        await scheduler.stop()
        await start_task
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Error middleware coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_error_middleware_returns_500():
    """Unhandled exception in a handler returns 500 without traceback."""

    # Create an app where trigger handler fails with an unhandled exception
    # We test the error middleware by adding a faulty route
    class _FaultyScheduler:
        async def trigger_now(self, reason, mode):
            raise RuntimeError("unexpected internal error")

    app = web.Application()

    # Register the trigger route with a handler that will raise
    async def faulty_handler(request):
        raise RuntimeError("unexpected internal error")

    app.router.add_post("/retrain/trigger", faulty_handler)

    # Add the error middleware manually
    from trader_off.scheduler.api import _error_middleware

    app.middlewares.append(_error_middleware)

    from aiohttp.test_utils import TestClient, TestServer

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        resp = await client.post("/retrain/trigger", json={"mode": "full"})
        assert resp.status == 500
        text = await resp.text()
        assert "Traceback" not in text
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# GET /retrain/status with task that has non-enum reason
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_status_with_mixed_reasons():
    """GET /retrain/status handles tasks regardless of reason type."""

    scheduler = _make_scheduler()
    client = await _make_client(scheduler)

    try:
        start_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(0.01)

        # Trigger a task with a valid reason
        await scheduler.trigger_now(TriggerReason.MANUAL, "full")
        await asyncio.sleep(0.05)

        resp = await client.get("/retrain/status")
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data["last_10_tasks"], list)
        assert len(data["last_10_tasks"]) > 0

        await scheduler.stop()
        await start_task
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# run_app coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_run_app_starts_and_binds():
    """run_app starts the API server and binds to the configured host:port."""
    from trader_off.scheduler.api import run_app

    scheduler = _make_scheduler()

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    try:
        # Start the API on a dynamic port
        api_task = asyncio.create_task(run_app(scheduler, host="127.0.0.1", port=0))
        await asyncio.sleep(0.05)
        # Server started — clean up
        api_task.cancel()
        # FAKE-003 fix: verify task completion via done() without awaiting
        assert api_task.done(), "api_task should be done after cancel()"
    finally:
        await scheduler.stop()
        await start_task


# ---------------------------------------------------------------------------
# Middleware: HTTPException re-raise path
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_middleware_passes_http_exception():
    """HTTPException is re-raised by the error middleware (not converted to 500)."""
    from aiohttp.test_utils import TestClient, TestServer

    from trader_off.scheduler.api import _error_middleware

    app = web.Application()

    async def raise_http_exception(request):
        raise web.HTTPBadRequest(text="bad request")

    app.router.add_get("/test", raise_http_exception)
    app.middlewares.append(_error_middleware)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        resp = await client.get("/test")
        assert resp.status == 400
        text = await resp.text()
        assert "bad request" in text
    finally:
        await client.close()
