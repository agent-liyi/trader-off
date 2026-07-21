"""QuantideSchedulerAdapter — thin wrapper around quantide.core.scheduler.SchedulerManager.

FR-0200: Migrate scheduler to use quantide's SchedulerManager.
NFR-0101: All quantide imports are function-scope (inside function bodies), not module-level.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _get_scheduler_manager():
    """Lazy-import and return the singleton SchedulerManager instance.

    NFR-0101: quantide import is inside a function body, not at module level.
    """
    from quantide.core.scheduler import scheduler

    return scheduler


class QuantideSchedulerAdapter:
    """Thin adapter wrapping quantide's SchedulerManager.

    Provides init/start/stop/add_job/add_listener with the same interface
    as the underlying SchedulerManager, but with trader-off-level logging
    and future extensibility hooks.

    All quantide imports are deferred to function bodies (NFR-0101).
    """

    def __init__(self) -> None:
        """Initialize the adapter without connecting to the scheduler.

        Call init() to set up the underlying scheduler.
        """
        self._scheduler_manager = _get_scheduler_manager()
        self._initialized = False

    def init(self, timezone: str | None = None) -> None:
        """Initialize the underlying scheduler with an optional timezone.

        Idempotent: if already initialized, this is a no-op.

        Args:
            timezone: Timezone string (e.g., "Asia/Shanghai"). If None,
                      uses the runtime timezone from quantide config.
        """
        if self._initialized:
            return
        self._scheduler_manager.init(timezone=timezone)
        self._initialized = True

    def start(self) -> None:
        """Start the underlying scheduler."""
        self._scheduler_manager.start()

    def stop(self) -> None:
        """Stop the underlying scheduler."""
        self._scheduler_manager.stop()

    def add_job(
        self,
        func: Callable,
        trigger: Any = None,
        args: tuple | None = None,
        kwargs: dict | None = None,
        id: str | None = None,
        name: str | None = None,
        **trigger_args: Any,
    ) -> Any:
        """Add a job to the underlying scheduler.

        Delegates directly to SchedulerManager.add_job().

        Args:
            func: Callable to execute.
            trigger: APScheduler trigger (e.g., 'cron', 'interval').
            args: Positional arguments for the job function.
            kwargs: Keyword arguments for the job function.
            id: Unique job ID.
            name: Human-readable job name.
            **trigger_args: Additional trigger-specific arguments.

        Returns:
            The job object created by APScheduler.
        """
        call_kwargs: dict[str, Any] = {"trigger": trigger}
        if args is not None:
            call_kwargs["args"] = args
        if kwargs is not None:
            call_kwargs["kwargs"] = kwargs
        if id is not None:
            call_kwargs["id"] = id
        if name is not None:
            call_kwargs["name"] = name
        call_kwargs.update(trigger_args)
        return self._scheduler_manager.add_job(func, **call_kwargs)

    def add_listener(
        self,
        callback: Callable,
        mask: Any = None,
    ) -> Any:
        """Add an event listener to the underlying scheduler.

        Delegates directly to SchedulerManager.add_listener().

        Args:
            callback: Callable to invoke on scheduler events.
            mask: Event mask to filter which events trigger the callback.

        Returns:
            The listener object.
        """
        return self._scheduler_manager.add_listener(callback, mask=mask)
