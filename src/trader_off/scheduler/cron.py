"""Cron trigger for the scheduler (FR-1600).

Provides:
- next_cron_fire: pure function to compute next cron fire time (T-3).
- CronTrigger: integrates cron configuration with the RetrainScheduler.

Uses croniter as the primary backend per architecture §4.2.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from croniter import croniter  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from trader_off.scheduler.core import SchedulerConfig

logger = logging.getLogger(__name__)

__all__ = ["next_cron_fire", "CronTrigger"]


# ---------------------------------------------------------------------------
# T-3: next_cron_fire pure function
# ---------------------------------------------------------------------------


def next_cron_fire(
    expr: str,
    base: datetime,
    *,
    backend: Literal["croniter", "apscheduler"] = "croniter",
) -> datetime:
    """Compute the next cron fire time after ``base``.

    Pure function (T-3): no side effects, no module-level state,
    deterministic for given inputs.

    The result is exclusive: returns the first cron match strictly
    after ``base``. If ``base`` itself matches the cron schedule, the
    *next* match is returned.

    Args:
        expr: A 5-field cron expression (e.g. ``"0 16 * * 1-5"``).
        base: The reference datetime (tz-aware or naive).
        backend: The cron backend to use (``"croniter"`` is the default;
                 ``"apscheduler"`` is reserved for future swap-in).

    Returns:
        The next datetime when the cron expression fires after ``base``.

    Raises:
        ValueError: If ``expr`` is not a valid cron expression.

    Example:
        >>> from datetime import datetime
        >>> next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0))
        datetime(2026, 7, 17, 16, 0)
    """
    if backend == "apscheduler":
        raise NotImplementedError(
            "APScheduler backend is not yet implemented. Use the default 'croniter' backend."
        )

    if not expr or not expr.strip():
        raise ValueError("Cron expression must be a non-empty string")

    try:
        c = croniter(expr, base)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"Invalid cron expression {expr!r}: {exc}") from exc

    next_time = c.get_next(datetime)
    return next_time


# ---------------------------------------------------------------------------
# CronTrigger
# ---------------------------------------------------------------------------


class CronTrigger:
    """Cron-based retraining trigger for RetrainScheduler.

    Integrates with ``SchedulerConfig`` to determine when full and
    incremental retrains should fire based on cron expressions,
    trading day checks, and frequency gates.

    Args:
        config: The scheduler configuration containing cron expressions,
                frequency gates, and the clock port.

    Example:
        >>> config = SchedulerConfig(full_retrain_cron="0 16 * * 1-5")
        >>> trigger = CronTrigger(config)
        >>> trigger.should_fire_full(last_check=datetime(2026, 7, 17, 16, 0))
        True
    """

    def __init__(self, config: SchedulerConfig) -> None:  # noqa: F821
        self._config = config
        self._clock = config.clock
        self._last_full_retrain_date: date | None = None
        self._last_incremental_retrain_date: date | None = None

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def compute_next_full(self, base: datetime | None = None) -> datetime:
        """Compute the next full retrain trigger time.

        Args:
            base: Reference datetime (defaults to current clock time).

        Returns:
            The next datetime when the full retrain cron fires.
        """
        return self._compute_next(self._config.full_retrain_cron, base)

    def compute_next_incremental(self, base: datetime | None = None) -> datetime:
        """Compute the next incremental retrain trigger time.

        Args:
            base: Reference datetime (defaults to current clock time).

        Returns:
            The next datetime when the incremental retrain cron fires.
        """
        return self._compute_next(self._config.incremental_retrain_cron, base)

    def should_fire_full(self, last_check: datetime) -> bool:
        """Check if a full retrain should be triggered.

        Evaluates:
        1. Is the current day a trading day?
        2. Has today's cron fire time been reached?
        3. Is the frequency gate satisfied?

        Args:
            last_check: The reference time (typically ``clock.now()``).

        Returns:
            True if a full retrain should be triggered.
        """
        if not self._cron_gate_passed(self._config.full_retrain_cron, last_check):
            return False
        return self._frequency_gate_met(last_check)

    def should_fire_incremental(self, last_check: datetime) -> bool:
        """Check if an incremental retrain should be triggered.

        Evaluates:
        1. Is the current day a trading day?
        2. Has today's cron fire time been reached?

        Note: frequency gate only applies to full retrain, not incremental.

        Args:
            last_check: The reference time (typically ``clock.now()``).

        Returns:
            True if an incremental retrain should be triggered.
        """
        return self._cron_gate_passed(self._config.incremental_retrain_cron, last_check)

    @staticmethod
    def is_trading_day(day: date) -> bool:
        """Check if a date is a trading day (Monday-Friday).

        Args:
            day: The date to check.

        Returns:
            True if the day is Monday through Friday.
        """
        return day.weekday() < 5  # 0=Mon .. 4=Fri

    # ------------------------------------------------------------------
    # Setters for testability / RetrainScheduler integration
    # ------------------------------------------------------------------

    def set_last_full_retrain_date(self, dt: date) -> None:
        """Set the last full retrain date (for frequency gate and testing)."""
        self._last_full_retrain_date = dt

    def set_last_incremental_retrain_date(self, dt: date) -> None:
        """Set the last incremental retrain date (for testing)."""
        self._last_incremental_retrain_date = dt

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_next(self, cron_expr: str, base: datetime | None) -> datetime:
        """Compute the next fire time for a cron expression.

        Args:
            cron_expr: The cron expression to evaluate.
            base: Reference datetime (defaults to clock.now()).

        Returns:
            The next cron fire time.
        """
        if base is None:
            base = self._clock.now()
        return next_cron_fire(cron_expr, base)

    def _cron_gate_passed(self, cron_expr: str, last_check: datetime) -> bool:
        """Check if today's cron fire time has been reached.

        Returns False if:
        - Today is not a trading day (logs info).
        - The cron expression is invalid.
        - No cron fire falls on today.
        - The cron fire time has not yet been reached.

        Args:
            cron_expr: The cron expression to evaluate.
            last_check: The reference time.

        Returns:
            True if the cron fire has been reached today.
        """
        if not self._is_on_trading_day(last_check):
            logger.info("cron skipped, not a trading day")
            return False

        today_start = last_check.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            today_fire = next_cron_fire(cron_expr, today_start)
        except ValueError:
            return False

        if today_fire.date() != last_check.date():
            return False

        if last_check < today_fire:
            return False

        return True

    def _is_on_trading_day(self, now: datetime) -> bool:
        """Check if the current datetime falls on a trading day."""
        return self.is_trading_day(now.date())

    def _frequency_gate_met(self, now: datetime) -> bool:
        """Check if the full retrain frequency gate is satisfied.

        Returns True if:
        - No previous full retrain has been recorded, OR
        - The number of calendar days since last full retrain >= frequency_days.
        """
        if self._last_full_retrain_date is None:
            return True

        days_since = (now.date() - self._last_full_retrain_date).days
        return days_since >= self._config.full_retrain_frequency_days
