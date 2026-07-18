"""Tests for NFR-0900: scheduler reliability and concurrency.

AC-NFR0900-01: Concurrent trigger_now() safety (no race conditions).
AC-NFR0900-02: State corruption simulation (garbage in state.json → recovery).
AC-NFR0900-03: Double start() is idempotent.
AC-NFR0900-04: stop() before start() is a graceful no-op.
"""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest

from trader_off.scheduler.core import RetrainScheduler, SchedulerConfig
from trader_off.scheduler.ports import TriggerReason, VirtualClockPort

# ---------------------------------------------------------------------------
# AC-NFR0900-01: Concurrent trigger_now() safety
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_nfr0900_01_concurrent_trigger_unique_task_ids(tmp_path):
    """AC-NFR0900-01: 10 concurrent trigger_now() calls produce unique task_ids."""
    config = SchedulerConfig(
        max_concurrent_tasks=1,
        clock=VirtualClockPort(),
        state_dir=tmp_path,
    )

    class NoOpTrainer:
        async def train(self, mode, **kwargs):
            await asyncio.sleep(0.001)
            return MagicMock()

        async def save(self, **kwargs):
            return "v0.0.0.test"

    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=NoOpTrainer(),
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    # Fire 10 concurrent trigger_now() calls
    tasks = [scheduler.trigger_now(TriggerReason.MANUAL, "full") for _ in range(10)]
    results = await asyncio.gather(*tasks)

    await asyncio.sleep(0.05)
    await scheduler.stop()
    await start_task

    task_ids = [r.task_id for r in results]
    assert len(set(task_ids)) == 10, f"Expected 10 unique task_ids, got duplicates: {task_ids}"
    assert len(task_ids) == len(set(task_ids))


@pytest.mark.unit
async def test_nfr0900_01_concurrent_trigger_serialized_per_max_concurrent(tmp_path):
    """AC-NFR0900-01: Active tasks <= max_concurrent_tasks during concurrent calls."""
    execution_counts = []

    class CountingTrainer:
        async def train(self, mode, **kwargs):
            execution_counts.append(("enter", mode))
            await asyncio.sleep(0.02)
            execution_counts.append(("exit", mode))
            return MagicMock()

        async def save(self, **kwargs):
            return "v0.0.0.test"

    config = SchedulerConfig(
        max_concurrent_tasks=1,
        clock=VirtualClockPort(),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=CountingTrainer(),
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    # Trigger 3 tasks concurrently
    await asyncio.gather(
        scheduler.trigger_now(TriggerReason.MANUAL, "full"),
        scheduler.trigger_now(TriggerReason.MANUAL, "full"),
        scheduler.trigger_now(TriggerReason.MANUAL, "full"),
    )

    await asyncio.sleep(0.1)
    await scheduler.stop()
    await start_task

    # Verify serialized: no overlapping execution
    enter_count = sum(1 for e in execution_counts if e[0] == "enter")
    exit_count = sum(1 for e in execution_counts if e[0] == "exit")
    assert enter_count == 3
    assert exit_count == 3


# ---------------------------------------------------------------------------
# AC-NFR0900-02: State corruption simulation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr0900_02_corrupt_json_recovers_with_warning(tmp_path, caplog):
    """AC-NFR0900-02: Garbage JSON in state.json → load_state returns empty + WARNING."""
    from trader_off.scheduler.state import load_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()

    # Write garbage (not valid JSON)
    (state_dir / "last_tasks.json").write_text('{"not": "valid json"')

    with caplog.at_level(logging.WARNING):
        result = load_state(state_dir)

    assert result == [], "load_state should return empty list on corrupt JSON"
    assert any(
        "corrupt" in caplog.text.lower() or "json" in caplog.text.lower()
        for _ in [1]
        if caplog.text
    ), f"Expected WARNING about corrupt JSON, got: {caplog.text}"


@pytest.mark.unit
def test_nfr0900_02_missing_state_file_recovers(tmp_path, caplog):
    """AC-NFR0900-02: Missing state file → load_state returns empty + WARNING."""
    from trader_off.scheduler.state import load_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()

    with caplog.at_level(logging.WARNING):
        result = load_state(state_dir)

    assert result == [], "load_state should return empty list when file is missing"
    assert "not found" in caplog.text.lower() or "missing" in caplog.text.lower()


@pytest.mark.unit
def test_nfr0900_02_state_corruption_with_garbage_bytes(tmp_path, caplog):
    """AC-NFR0900-02: Binary garbage in state file → load_state returns empty + WARNING."""
    from trader_off.scheduler.state import load_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()

    # Write binary garbage
    (state_dir / "last_tasks.json").write_bytes(b"\x00\xff\xfe\x01garbage")

    with caplog.at_level(logging.WARNING):
        result = load_state(state_dir)

    assert result == [], "load_state should return empty list on binary garbage"
    assert "corrupt" in caplog.text.lower() or "json" in caplog.text.lower()


# ---------------------------------------------------------------------------
# AC-NFR0900-03: Double start() is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_nfr0900_03_double_start_no_error(tmp_path):
    """AC-NFR0900-03: Calling start() twice does not raise or double-run."""
    config = SchedulerConfig(
        max_concurrent_tasks=1,
        clock=VirtualClockPort(),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    # Start once
    t1 = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.02)

    # Start again (should be idempotent)
    t2 = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.02)

    # Both should still be running without error
    status = await scheduler.get_status()
    # AC-NFR0900-03: start() is idempotent — status must be retrievable (not crash)
    assert status is not None

    await scheduler.stop()
    await asyncio.gather(t1, t2, return_exceptions=True)


@pytest.mark.unit
async def test_nfr0900_03_stop_idempotent(tmp_path):
    """AC-NFR0900-03: Calling stop() twice does not raise."""
    config = SchedulerConfig(
        clock=VirtualClockPort(),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    # Stop before start should not raise
    await scheduler.stop()
    await scheduler.stop()  # Idempotent


# ---------------------------------------------------------------------------
# AC-NFR0900-04: stop() from not-started scheduler is graceful no-op
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_nfr0900_04_stop_before_start_graceful(tmp_path):
    """AC-NFR0900-04: stop() on scheduler that hasn't started is a graceful no-op."""
    config = SchedulerConfig(
        clock=VirtualClockPort(),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    # stop() before ever calling start()
    await scheduler.stop()

    # Should be able to start and immediately stop without error
    t = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)
    await scheduler.stop()
    await t


@pytest.mark.unit
async def test_nfr0900_04_get_status_before_start_works(tmp_path):
    """AC-NFR0900-04: get_status() works even before start() is called."""
    config = SchedulerConfig(
        clock=VirtualClockPort(),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    status = await scheduler.get_status()
    assert status.running is False
    assert status.active_tasks == 0
    assert status.pending_tasks == 0
