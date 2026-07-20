"""Scheduler core: RetrainScheduler lifecycle and interfaces.

FR-1500: Scheduler core interfaces and lifecycle.

Provides:
- SchedulerConfig: configuration dataclass with ClockPort injection.
- SchedulerStatus: immutable status snapshot.
- RetrainTask: task representation.
- RetrainScheduler: main scheduler with start/stop/trigger_now/get_status.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from trader_off.scheduler.ports import ClockPort, SystemClockPort, TrainerPort, TriggerReason

# ---------------------------------------------------------------------------
# SchedulerConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class SchedulerConfig:
    """Scheduler configuration.

    Per interfaces.md §1.8. The `clock` field provides the T-1 testability
    seam for time-dependent operations.
    """

    # Core scheduler
    tick_interval_sec: float = 1.0
    max_concurrent_tasks: int = 1
    trading_calendar: Literal["data_loader", "exchange_calendar"] = "data_loader"

    # Virtual clock injection (T-1)
    clock: ClockPort = field(default_factory=lambda: SystemClockPort())

    # Cron (FR-1600)
    full_retrain_cron: str = "0 16 * * 1-5"
    incremental_retrain_cron: str = "0 16 * * 1-5"
    full_retrain_frequency_days: int = 5
    drift_check_cron: str = "0 9 * * 1-5"

    # Drift thresholds (FR-2600)
    psi_threshold: float = 0.2
    ks_pvalue_threshold: float = 0.05
    psi_strong: float = 0.5
    min_drift_features_incremental: int = 5
    min_drift_features_full: int = 3

    # Performance degradation thresholds (FR-1900)
    ic_floor: float = 0.005
    ic_drop_ratio: float = 0.3
    ic_window: int = 20

    # Retention policy (FR-2300)
    keep_latest_n: int = 10
    keep_pinned_versions: list[str] = field(default_factory=list)
    keep_full_retrain_only: bool = True

    # Deploy (FR-2400)
    model_load_mode: Literal["lazy", "hot-reload"] = "lazy"

    # API (FR-2000)
    run_api: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    # Persistence (T-4: configurable output roots)
    state_dir: Path = field(default_factory=lambda: Path("scheduler_state"))
    models_dir: Path = field(default_factory=lambda: Path("models"))
    reports_dir: Path = field(default_factory=lambda: Path("reports"))


# ---------------------------------------------------------------------------
# SchedulerStatus dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchedulerStatus:
    """Immutable snapshot of scheduler state.

    Per interfaces.md §1.9.
    """

    running: bool
    next_trigger_time: datetime | None = None
    next_trigger_mode: Literal["full", "incremental"] | None = None
    active_tasks: int = 0
    pending_tasks: int = 0
    last_full_retrain_date: date | None = None
    last_incremental_retrain_date: date | None = None


# ---------------------------------------------------------------------------
# RetrainTask dataclass
# ---------------------------------------------------------------------------


@dataclass
class RetrainTask:
    """Representation of a retraining task.

    Per interfaces.md §1.10.
    """

    task_id: str
    mode: Literal["full", "incremental"]
    reason: TriggerReason
    parent_version: str | None = None
    status: Literal["pending", "running", "success", "failed"] = "pending"
    start_time: datetime | None = None
    end_time: datetime | None = None
    error: str | None = None
    new_version: str | None = None
    metrics: dict | None = None


def _generate_task_id() -> str:
    """Generate a unique task ID: T-<YYYYMMDD>-<uuid8>."""
    now = datetime.now(UTC)
    return f"T-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# RetrainScheduler
# ---------------------------------------------------------------------------


class RetrainScheduler:
    """Main scheduler orchestrating retraining tasks.

    All four public methods (start, stop, trigger_now, get_status) are
    async coroutine functions (AC-FR1500-01).

    Concurrency model (AC-FR1500-02, NFR-0900):
    - max_concurrent_tasks limits simultaneous running tasks (default 1).
    - Pending tasks wait in a FIFO queue.
    - An asyncio.Lock protects task state transitions.
    """

    def __init__(
        self,
        config: SchedulerConfig,
        model_registry,  # ModelRegistryPort - injected, formal import in FR-2300
        drift_detector,  # DriftDetectorPort - injected, formal import in FR-2600
        perf_monitor,  # PerfMonitorPort - injected, formal import in FR-1900
        trainer: TrainerPort,
    ) -> None:
        self._config = config
        self._clock = config.clock
        self._trainer = trainer
        self._model_registry = model_registry
        self._drift_detector = drift_detector
        self._perf_monitor = perf_monitor

        # Internal state
        self._running = False
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._task_lock = asyncio.Lock()
        self._pending_queue: list[RetrainTask] = []
        self._active_tasks = 0
        self._task_history: list[RetrainTask] = []
        self._last_full_retrain_date: date | None = None
        self._last_incremental_retrain_date: date | None = None

    # ------------------------------------------------------------------
    # Public async methods (AC-FR1500-01)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the scheduler main loop.

        The loop ticks at tick_interval_sec, processes pending tasks,
        and exits when stop() is called. Wakes early when new tasks
        are enqueued via trigger_now.
        """
        self._running = True
        self._stop_event.clear()
        self._wake_event.clear()
        try:
            while not self._stop_event.is_set():
                await self._process_pending_task()
                # Sleep for the tick interval, but wake early on stop or new task
                await self._sleep_with_stop_check(self._config.tick_interval_sec)
        finally:
            self._running = False

    async def stop(self) -> None:
        """Signal the scheduler to stop after the current tick completes."""
        self._stop_event.set()

    async def trigger_now(
        self, reason: TriggerReason, mode: Literal["full", "incremental"]
    ) -> RetrainTask:
        """Trigger an immediate retraining task.

        Creates a RetrainTask and enqueues it in the FIFO pending queue.
        The task will be executed when it reaches the front of the queue.

        Args:
            reason: Why the retrain was triggered.
            mode: "full" or "incremental".

        Returns:
            The created RetrainTask (status will be "pending" initially).
        """
        task = RetrainTask(
            task_id=_generate_task_id(),
            mode=mode,
            reason=reason,
        )
        async with self._task_lock:
            self._pending_queue.append(task)
            self._task_history.append(task)
            # Wake the main loop so the enqueued task is picked up immediately
            self._wake_event.set()
        return task

    async def get_status(self) -> SchedulerStatus:
        """Return an immutable snapshot of the current scheduler state.

        Returns:
            SchedulerStatus with running flag, task counts, and last retrain dates.
        """
        async with self._task_lock:
            return SchedulerStatus(
                running=self._running,
                active_tasks=self._active_tasks,
                pending_tasks=len(self._pending_queue),
                last_full_retrain_date=self._last_full_retrain_date,
                last_incremental_retrain_date=self._last_incremental_retrain_date,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _process_pending_task(self) -> None:
        """Dequeue one task and execute it if under concurrency limit."""
        async with self._task_lock:
            if not self._pending_queue:
                return
            if self._active_tasks >= self._config.max_concurrent_tasks:
                return
            task = self._pending_queue.pop(0)
            self._active_tasks += 1

        # Release lock before awaiting trainer (to avoid blocking other ops)
        await self._run_task(task)

    async def _run_task(self, task: RetrainTask) -> None:
        """Execute a single retraining task."""
        try:
            task.status = "running"
            task.start_time = self._clock.now()

            artifact = await self._trainer.train(
                mode=task.mode,
                parent_version=task.parent_version,
            )
            new_version = await self._trainer.save(
                artifact=artifact,
                mode=task.mode,
                trigger=task.reason,
                parent_version=task.parent_version,
                task_id=task.task_id,
                metrics=task.metrics,
            )

            task.status = "success"
            task.new_version = new_version
            task.end_time = self._clock.now()

            # Update last retrain dates
            today = self._clock.now().date()
            if task.mode == "full":
                self._last_full_retrain_date = today
            else:
                self._last_incremental_retrain_date = today

        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.end_time = self._clock.now()
        finally:
            async with self._task_lock:
                self._active_tasks -= 1
                # Wake the loop if there are more tasks waiting
                if self._pending_queue:
                    self._wake_event.set()

    async def _sleep_with_stop_check(self, seconds: float) -> None:
        """Sleep for `seconds`, but wake early if stop is requested or new task enqueued."""
        stop_task = asyncio.ensure_future(self._stop_event.wait())
        wake_task = asyncio.ensure_future(self._wake_event.wait())
        try:
            await asyncio.wait(
                {stop_task, wake_task},
                timeout=seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (stop_task, wake_task):
                if not task.done():
                    task.cancel()
        self._wake_event.clear()
