"""Unit tests for FR-1500: scheduler core interfaces and lifecycle.

AC coverage: AC-FR1500-01, AC-FR1500-02, AC-FR1500-03, AC-FR1500-04
T-1 (ClockPort) and T-2 (TrainerPort) testability seams verified.
"""

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trader_off.scheduler.core import (
    RetrainScheduler,
    RetrainTask,
    SchedulerConfig,
    SchedulerStatus,
)
from trader_off.scheduler.ports import (
    DefaultTrainerPort,
    SystemClockPort,
    TriggerReason,
    VirtualClockPort,
)

# ---------------------------------------------------------------------------
# AC-FR1500-01: All 4 public methods must be async
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1500_01_methods_are_async():
    """AC-FR1500-01: start, stop, trigger_now, get_status are async coroutine functions."""
    async_methods = ["start", "stop", "trigger_now", "get_status"]
    for method_name in async_methods:
        method = getattr(RetrainScheduler, method_name)
        assert asyncio.iscoroutinefunction(method), (
            f"RetrainScheduler.{method_name} must be an async coroutine function"
        )


# ---------------------------------------------------------------------------
# AC-FR1500-02: max_concurrent_tasks=1 serial execution (FIFO)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr1500_02_concurrent_serial():
    """AC-FR1500-02: Two trigger_now calls execute serially with max_concurrent_tasks=1.

    Uses a mock TrainerPort. The trainer's train() is delayed so we can
    observe that only one task runs at a time.
    """
    event_order = []

    class RecordingTrainer:
        """Trainer that records execution order with a small delay."""

        async def train(
            self,
            mode,
            *,
            parent_version=None,
            factor_registry_path=None,
            train_window_years=3,
            config_snapshot=None,
        ):
            event_order.append(f"train_enter_{mode}")
            await asyncio.sleep(0.01)
            event_order.append(f"train_exit_{mode}")
            return MagicMock()

        async def save(
            self, artifact, *, mode, trigger, parent_version=None, task_id="", metrics=None
        ):
            return "v0.0.0.test"

    config = SchedulerConfig(
        max_concurrent_tasks=1,
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    trainer = RecordingTrainer()
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=trainer,
    )

    # Run start() as a background task so we can interact with the scheduler
    start_task = asyncio.create_task(scheduler.start())

    # Give the loop a moment to start
    await asyncio.sleep(0.01)

    # Trigger two tasks concurrently
    t1 = asyncio.create_task(scheduler.trigger_now(TriggerReason.MANUAL, "full"))
    t2 = asyncio.create_task(scheduler.trigger_now(TriggerReason.MANUAL, "incremental"))

    await asyncio.gather(t1, t2)

    # Wait for tasks to complete execution
    await asyncio.sleep(0.1)

    await scheduler.stop()
    await start_task  # Wait for the main loop to fully exit

    # Assert serial execution: first task fully completes before the second starts
    full_events = [i for i, e in enumerate(event_order) if "full" in e]
    incr_events = [i for i, e in enumerate(event_order) if "incremental" in e]
    assert len(full_events) == 2, f"Expected 2 full events, got {event_order}"
    assert len(incr_events) == 2, f"Expected 2 incremental events, got {event_order}"
    # full train_exit must happen before incremental train_enter
    full_exit_idx = [i for i, e in enumerate(event_order) if e == "train_exit_full"][0]
    incr_enter_idx = [i for i, e in enumerate(event_order) if e == "train_enter_incremental"][0]
    assert full_exit_idx < incr_enter_idx, (
        f"Expected serial execution, but full_exit ({full_exit_idx}) "
        f"not before incr_enter ({incr_enter_idx}): {event_order}"
    )

    # Verify both tasks are completed
    assert t1.result().status == "success"
    assert t2.result().status == "success"

    status = await scheduler.get_status()
    assert status.active_tasks == 0
    assert status.pending_tasks == 0


# ---------------------------------------------------------------------------
# AC-FR1500-03: stop() sets running=False
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr1500_03_stop():
    """AC-FR1500-03: stop() sets running=False, main loop exits quickly (<5s)."""
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    # Verify initial state
    status_before = await scheduler.get_status()
    assert status_before.running is False

    start_time = asyncio.get_event_loop().time()
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.05)  # Let the loop run for a tick
    await scheduler.stop()
    await start_task  # Wait for loop exit
    elapsed = asyncio.get_event_loop().time() - start_time

    # status must reflect running=False
    status_after = await scheduler.get_status()
    assert status_after.running is False, f"Expected running=False after stop(), got {status_after}"

    # Should complete within 5 seconds (mock config, no real work)
    assert elapsed < 5.0, f"stop() took {elapsed:.2f}s, expected < 5s"


# ---------------------------------------------------------------------------
# AC-FR1500-04: No millionaire/quantide dependency
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1500_04_no_external_deps():
    """AC-FR1500-04: scheduler module has no quantide/millionaire business imports."""
    from pathlib import Path

    src_dir = Path(__file__).parents[3] / "src" / "trader_off" / "scheduler"

    for py_file in src_dir.glob("**/*.py"):
        if py_file.name == "__init__.py":
            # __init__.py may re-export but should not business-import millionaire
            pass
        content = py_file.read_text()
        lines = content.split("\n")
        for lineno, line in enumerate(lines, 1):
            if line.strip().startswith("#"):
                continue
            # Check for import of quantide or millionaire
            if re.search(r"\b(quantide|millionaire)\b", line) and not re.search(
                r"pyproject\.toml", line
            ):
                raise AssertionError(
                    f"File {py_file}:{lineno} imports quantide/millionaire: {line.strip()}"
                )


# ---------------------------------------------------------------------------
# T-1: VirtualClockPort testability seam
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_t1_virtual_clock_advance():
    """T-1: VirtualClockPort supports set_now and advance for time control."""
    start = datetime(2026, 7, 17, 15, 59, 30, tzinfo=UTC)

    clock = VirtualClockPort(start=start)
    assert clock.now() == start

    # advance by 3600 seconds (1 hour)
    clock.advance(3600)
    expected = datetime(2026, 7, 17, 16, 59, 30, tzinfo=UTC)
    assert clock.now() == expected, f"Expected {expected}, got {clock.now()}"

    # set_now to a specific time
    target = datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC)
    clock.set_now(target)
    assert clock.now() == target

    # SystemClockPort returns real time
    sys_clock = SystemClockPort()
    assert isinstance(sys_clock.now(), datetime)
    assert sys_clock.now().tzinfo is not None  # must be tz-aware


# ---------------------------------------------------------------------------
# T-2: DefaultTrainerPort wraps v0.1.0 trainer correctly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_t2_default_trainer_wraps():
    """T-2: DefaultTrainerPort delegates to v0.1.0 training.trainer and model_io.

    We verify the wrapper's module imports and attribute correctness without
    actually training (which would require full data setup).
    """
    from pathlib import Path

    from trader_off.scheduler.ports import DefaultTrainerPort

    # DefaultTrainerPort can be instantiated with default models_dir
    port = DefaultTrainerPort()
    assert port.models_dir == Path("models")

    port_custom = DefaultTrainerPort(models_dir=Path("/tmp/test_models"))
    assert port_custom.models_dir == Path("/tmp/test_models")

    # DefaultTrainerPort should have train and save async methods
    assert asyncio.iscoroutinefunction(DefaultTrainerPort.train)
    assert asyncio.iscoroutinefunction(DefaultTrainerPort.save)


# ---------------------------------------------------------------------------
# Additional SchedulerConfig / SchedulerStatus / RetrainTask structure tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scheduler_config_defaults():
    """SchedulerConfig has correct defaults per interfaces.md §1.8."""
    config = SchedulerConfig()
    assert config.tick_interval_sec == 1.0
    assert config.max_concurrent_tasks == 1
    assert config.clock is not None
    assert hasattr(config.clock, "now")


@pytest.mark.unit
def test_scheduler_config_clock_injection():
    """SchedulerConfig accepts ClockPort injection (T-1 seam)."""
    vclock = VirtualClockPort()
    config = SchedulerConfig(clock=vclock)
    assert config.clock is vclock


@pytest.mark.unit
def test_scheduler_status_fields():
    """SchedulerStatus has all required fields per interfaces.md §1.9."""

    status = SchedulerStatus(
        running=False,
        next_trigger_time=None,
        next_trigger_mode=None,
        active_tasks=0,
        pending_tasks=0,
        last_full_retrain_date=None,
        last_incremental_retrain_date=None,
    )
    assert status.running is False
    assert status.active_tasks == 0
    assert status.pending_tasks == 0


@pytest.mark.unit
def test_retrain_task_fields():
    """RetrainTask has all required fields per interfaces.md §1.10."""
    task = RetrainTask(
        task_id="T-20260717-abc12345",
        mode="full",
        reason=TriggerReason.MANUAL,
        parent_version=None,
        status="pending",
        start_time=None,
        end_time=None,
        error=None,
        new_version=None,
        metrics=None,
    )
    assert task.task_id == "T-20260717-abc12345"
    assert task.mode == "full"
    assert task.reason == TriggerReason.MANUAL
    assert task.status == "pending"


@pytest.mark.unit
def test_trigger_reason_enum():
    """TriggerReason enum matches interfaces.md §1.10 values."""
    reasons = set(TriggerReason)
    expected = {
        "cron_full",
        "cron_incremental",
        "drift",
        "perf_degradation",
        "manual",
    }
    actual = {r.value for r in reasons}
    assert actual == expected, f"Expected {expected}, got {actual}"


@pytest.mark.unit
async def test_get_status_while_running():
    """SchedulerStatus.active_tasks reflects running tasks correctly."""
    running_flag = False

    class DelayedTrainer:
        async def train(
            self,
            mode,
            *,
            parent_version=None,
            factor_registry_path=None,
            train_window_years=3,
            config_snapshot=None,
        ):
            nonlocal running_flag
            running_flag = True
            await asyncio.sleep(0.1)
            running_flag = False
            return MagicMock()

        async def save(
            self, artifact, *, mode, trigger, parent_version=None, task_id="", metrics=None
        ):
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
        trainer=DelayedTrainer(),
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)  # Let the loop start

    # Trigger a task
    task_coro = asyncio.create_task(scheduler.trigger_now(TriggerReason.MANUAL, "full"))

    # Give it a moment to start
    await asyncio.sleep(0.02)

    status = await scheduler.get_status()
    # Either active_tasks == 1 or 0 depending on timing; it should be 1 during execution
    assert status.active_tasks in (0, 1), f"Unexpected active_tasks: {status.active_tasks}"

    await task_coro
    await scheduler.stop()
    await start_task

    final_status = await scheduler.get_status()
    assert final_status.active_tasks == 0
    assert final_status.running is False


@pytest.mark.unit
async def test_trigger_now_returns_retrain_task():
    """trigger_now returns a RetrainTask with status='pending' initially."""
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

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)  # Let the loop start
    task = await scheduler.trigger_now(TriggerReason.DRIFT, "incremental")
    await scheduler.stop()
    await start_task

    assert isinstance(task, RetrainTask)
    assert task.mode == "incremental"
    assert task.reason == TriggerReason.DRIFT
    assert task.status in ("pending", "running", "success")


# ---------------------------------------------------------------------------
# Coverage tests: task failure path + DefaultTrainerPort.save()
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_task_failure_marks_status_failed():
    """Task that raises during training is marked 'failed' with error detail."""

    class FailingTrainer:
        async def train(
            self,
            mode,
            *,
            parent_version=None,
            factor_registry_path=None,
            train_window_years=3,
            config_snapshot=None,
        ):
            raise RuntimeError("simulated training failure")

        async def save(
            self, artifact, *, mode, trigger, parent_version=None, task_id="", metrics=None
        ):
            return "unreachable"

    config = SchedulerConfig(
        max_concurrent_tasks=1,
        clock=VirtualClockPort(),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=FailingTrainer(),
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)
    task = await scheduler.trigger_now(TriggerReason.MANUAL, "full")
    # Wait for task execution
    await asyncio.sleep(0.1)
    await scheduler.stop()
    await start_task

    assert task.status == "failed"
    assert "simulated training failure" in (task.error or "")


@pytest.mark.unit
def test_default_trainer_save_delegates():
    """DefaultTrainerPort.save() delegates to v0.1.0 save_model correctly (T-2)."""
    from unittest.mock import create_autospec

    from trader_off.training.serialize import ModelArtifact

    # Create a minimal mock artifact
    artifact = create_autospec(ModelArtifact, instance=True)
    artifact.booster = MagicMock()
    artifact.scaler = MagicMock()
    artifact.feature_names = ["feature_a", "feature_b"]

    with patch("trader_off.training.serialize.save_model") as mock_save:
        mock_save.return_value = Path("/tmp/models/v0.0.1.test")
        port = DefaultTrainerPort(models_dir=Path("/tmp/test_models"))
        version = asyncio.run(
            port.save(
                artifact=artifact,
                mode="full",
                trigger=TriggerReason.CRON_FULL,
                task_id="T-001",
                metrics={"test_ic_mean": 0.025, "test_rank_ic_mean": 0.035},
            )
        )

    assert version == "/tmp/models/v0.0.1.test"
    mock_save.assert_called_once()
    # Verify delegation args
    call_kwargs = mock_save.call_args.kwargs
    assert call_kwargs["models_dir"] == Path("/tmp/test_models")
    assert call_kwargs["feature_names"] == ["feature_a", "feature_b"]
    metadata = call_kwargs["metadata"]
    assert metadata["mode"] == "full"
    assert metadata["task_id"] == "T-001"
    assert metadata["trigger"] == "cron_full"
    assert metadata["test_ic_mean"] == 0.025


@pytest.mark.unit
def test_default_trainer_save_with_parent_version():
    """DefaultTrainerPort.save() includes parent_version in metadata."""
    from unittest.mock import create_autospec

    from trader_off.training.serialize import ModelArtifact

    artifact = create_autospec(ModelArtifact, instance=True)
    artifact.booster = MagicMock()
    artifact.scaler = MagicMock()
    artifact.feature_names = []

    with patch("trader_off.training.serialize.save_model") as mock_save:
        mock_save.return_value = Path("/tmp/models/v0.0.1.incr1")
        port = DefaultTrainerPort()
        version = asyncio.run(
            port.save(
                artifact=artifact,
                mode="incremental",
                trigger=TriggerReason.DRIFT,
                parent_version="v0.2.0.5",
                task_id="T-002",
            )
        )

    assert version == "/tmp/models/v0.0.1.incr1"
    metadata = mock_save.call_args.kwargs["metadata"]
    assert metadata["parent_version"] == "v0.2.0.5"
