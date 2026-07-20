"""Integration tests: retrain CLI + aiohttp API → scheduler.

Covers AC-FR2000-01~04: CLI trigger/status, REST API trigger/status,
localhost binding enforcement.

Per test-plan §8.2, interfaces.md §4.3 / §5.4.
"""

import asyncio
import io
from datetime import UTC, datetime

import pytest
from aiohttp import web

from trader_off.scheduler.api import create_app
from trader_off.scheduler.cli import run_status, run_trigger
from trader_off.scheduler.core import RetrainScheduler, SchedulerConfig
from trader_off.scheduler.ports import TriggerReason, VirtualClockPort

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _NoopTrainer:
    """Trainer that does nothing and returns success for fast CLI/API tests."""

    async def train(self, mode, *, parent_version=None, **kwargs):
        from unittest.mock import MagicMock

        return MagicMock()

    async def save(self, artifact, *, mode, trigger, parent_version=None, task_id="", metrics=None):
        return "v0.0.0.test"


def _make_scheduler(tmp_path):
    """Build a RetrainScheduler with a noop trainer and virtual clock."""
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
        state_dir=tmp_path / "scheduler_state",
        models_dir=tmp_path / "models",
    )
    from unittest.mock import MagicMock

    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=_NoopTrainer(),
    )
    return scheduler, config


async def _start_scheduler(scheduler):
    """Start the scheduler in background, wait for the loop to begin."""
    task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)
    return task


async def _stop_scheduler(scheduler, start_task):
    """Stop the scheduler and wait for the main loop to exit."""
    await scheduler.stop()
    await start_task


# ---------------------------------------------------------------------------
# AC-FR2000-01: CLI trigger via argparse → stdout
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2000_01_cli_trigger_full(tmp_path):
    """AC-FR2000-01: `retrain trigger --mode full` outputs task_id + status=pending."""
    scheduler, _config = _make_scheduler(tmp_path)
    start_task = await _start_scheduler(scheduler)

    stdout = io.StringIO()
    exit_code = await run_trigger(scheduler, "full", "manual_test", stdout=stdout)
    output = stdout.getvalue()

    await _stop_scheduler(scheduler, start_task)

    assert exit_code == 0
    assert "task_id=" in output, f"Expected task_id in output, got: {output}"
    assert "status=pending" in output, f"Expected status=pending in output, got: {output}"


@pytest.mark.integration
async def test_ac_fr2000_01_cli_trigger_incremental(tmp_path):
    """AC-FR2000-01: `retrain trigger --mode incremental` works."""
    scheduler, _config = _make_scheduler(tmp_path)
    start_task = await _start_scheduler(scheduler)

    stdout = io.StringIO()
    exit_code = await run_trigger(scheduler, "incremental", "manual_test", stdout=stdout)
    output = stdout.getvalue()

    await _stop_scheduler(scheduler, start_task)

    assert exit_code == 0
    assert "task_id=" in output
    assert "status=pending" in output or "status=running" in output


# ---------------------------------------------------------------------------
# AC-FR2000-02: CLI status outputs task history (≤10 tasks)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2000_02_cli_status(tmp_path):
    """AC-FR2000-02: `retrain status` outputs recent tasks with required fields."""
    scheduler, _config = _make_scheduler(tmp_path)
    start_task = await _start_scheduler(scheduler)

    # Trigger 3 tasks to populate history
    await scheduler.trigger_now(TriggerReason.MANUAL, "full")
    await scheduler.trigger_now(TriggerReason.MANUAL, "incremental")
    await scheduler.trigger_now(TriggerReason.DRIFT, "full")

    await asyncio.sleep(0.1)  # Let tasks execute

    stdout = io.StringIO()
    exit_code = await run_status(scheduler, limit=10, stdout=stdout)
    output = stdout.getvalue()

    await _stop_scheduler(scheduler, start_task)

    assert exit_code == 0
    assert "task_id=" in output, f"Expected task_id in status, got: {output}"
    assert "mode=" in output, f"Expected mode= in status, got: {output}"
    assert "running=" in output


# ---------------------------------------------------------------------------
# AC-FR2000-03: REST API POST /retrain/trigger → 200 + task_id
# ---------------------------------------------------------------------------


async def _fetch(app, method, path, json_data=None):
    """Make an HTTP request to the aiohttp app directly via the test framework."""

    # Use aiohttp's low-level test client

    # For simplicity, start the app on a real port and use ClientSession
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)  # random port
    await site.start()

    # Get the actual port
    for sock in site._server.sockets:
        port = sock.getsockname()[1]
        break
    else:
        raise RuntimeError("Could not determine server port")

    import aiohttp

    url = f"http://127.0.0.1:{port}{path}"
    async with aiohttp.ClientSession() as session:
        if method == "POST":
            async with session.post(url, json=json_data) as resp:
                status = resp.status
                body = await resp.json()
                text = await resp.text()
        elif method == "GET":
            async with session.get(url) as resp:
                status = resp.status
                body = await resp.json()
                text = await resp.text()

    await runner.cleanup()
    return status, body, text


@pytest.mark.integration
async def test_ac_fr2000_03_api_trigger(tmp_path):
    """AC-FR2000-03: POST /retrain/trigger returns 200 with task_id + status."""
    scheduler, _config = _make_scheduler(tmp_path)
    app = create_app(scheduler)

    start_task = await _start_scheduler(scheduler)

    status, data, _ = await _fetch(
        app, "POST", "/retrain/trigger", json_data={"mode": "full", "reason": "api_test"}
    )
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert "task_id" in data, f"Expected task_id in response: {data}"
    assert data["status"] in ("pending", "running")

    await _stop_scheduler(scheduler, start_task)


@pytest.mark.integration
async def test_ac_fr2000_03_api_trigger_bad_mode(tmp_path):
    """AC-FR2000-03: POST /retrain/trigger with invalid mode returns 400."""
    scheduler, _config = _make_scheduler(tmp_path)
    app = create_app(scheduler)

    status, data, _ = await _fetch(
        app, "POST", "/retrain/trigger", json_data={"mode": "invalid", "reason": "test"}
    )
    assert status == 400, f"Expected 400 for bad mode, got {status}: {data}"


@pytest.mark.integration
async def test_ac_fr2000_03_api_status(tmp_path):
    """AC-FR2000-03: GET /retrain/status returns active_tasks and last_10_tasks."""
    scheduler, _config = _make_scheduler(tmp_path)
    app = create_app(scheduler)

    start_task = await _start_scheduler(scheduler)
    await scheduler.trigger_now(TriggerReason.MANUAL, "full")
    await asyncio.sleep(0.1)

    status, data, _ = await _fetch(app, "GET", "/retrain/status")
    assert status == 200
    assert "active_tasks" in data
    assert "last_10_tasks" in data
    assert isinstance(data["last_10_tasks"], list)

    await _stop_scheduler(scheduler, start_task)


# ---------------------------------------------------------------------------
# AC-FR2000-04: localhost binding — error handling hides tracebacks
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2000_04_locahost_binding(tmp_path):
    """AC-FR2000-04: API error responses hide internal stack traces."""
    scheduler, _config = _make_scheduler(tmp_path)
    assert _config.api_host == "127.0.0.1"
    app = create_app(scheduler)

    status, data, body_text = await _fetch(
        app, "POST", "/retrain/trigger", json_data={"mode": "full", "reason": "malicious"}
    )
    # Internal traceback should never appear in response body
    assert "Traceback" not in body_text, f"Internal traceback leaked: {body_text[:200]}"
    assert "Traceback" not in str(data)


@pytest.mark.integration
async def test_ac_fr2000_04_api_health_endpoint(tmp_path):
    """AC-FR2000-04: GET /health returns {'status': 'ok'} without leaks."""
    scheduler, _config = _make_scheduler(tmp_path)
    app = create_app(scheduler)

    status, data, _ = await _fetch(app, "GET", "/health")
    assert status == 200
    assert data == {"status": "ok"}


@pytest.mark.integration
def test_ac_fr2000_04_api_default_bind_localhost(tmp_path):
    """AC-FR2000-04 + NFR-0700-04: Default api_host is 127.0.0.1, not 0.0.0.0."""
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    assert config.api_host == "127.0.0.1", (
        f"Default api_host must be 127.0.0.1 for security, got {config.api_host}"
    )
    assert config.api_host != "0.0.0.0"
    assert config.run_api is False
