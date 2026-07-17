"""Scheduler ports (T-1 ClockPort, T-2 TrainerPort, PerfMonitorPort).

Defines Protocol-based ports for dependency injection, enabling unit
tests to inject virtual clocks and mock trainers without touching
external systems.

FR-1500: Scheduler core interfaces and lifecycle.
FR-1900: PerfMonitorPort for IC-based performance decay detection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from trader_off.scheduler.perf_monitor import (
        TriggerDecision as _TriggerDecision,
    )
    from trader_off.training.serialize import ModelArtifact as _ModelArtifact


# ---------------------------------------------------------------------------
# TriggerReason enum
# ---------------------------------------------------------------------------


class TriggerReason(StrEnum):
    """Reasons that can trigger a retraining task.

    Per interfaces.md §1.10.
    """

    CRON_FULL = "cron_full"
    CRON_INCREMENTAL = "cron_incremental"
    DRIFT = "drift"
    PERF_DEGRADATION = "perf_degradation"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# T-1: ClockPort
# ---------------------------------------------------------------------------


class ClockPort(Protocol):
    """Protocol for a clock that returns the current time.

    T-1 testability seam: RetrainScheduler uses this port for all
    time-dependent operations, allowing tests to inject a virtual clock.
    """

    def now(self) -> datetime:
        """Return the current time as a tz-aware UTC datetime."""
        ...


class SystemClockPort:
    """Default ClockPort implementation wrapping datetime.now(UTC)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class VirtualClockPort:
    """Test clock that allows manual control over time.

    Supports set_now() to jump to a specific time and advance() to
    move forward by a number of seconds.
    """

    def __init__(self, start: datetime | None = None) -> None:
        if start is None:
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        self._now = start

    def now(self) -> datetime:
        return self._now

    def set_now(self, t: datetime) -> None:
        """Set the virtual clock to a specific datetime."""
        self._now = t

    def advance(self, seconds: float) -> None:
        """Advance the virtual clock by a number of seconds."""
        self._now += timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# T-2: TrainerPort
# ---------------------------------------------------------------------------


class TrainerPort(Protocol):
    """Protocol for model training operations.

    T-2 testability seam: RetrainScheduler uses this port for all
    training operations, allowing unit tests to inject mock trainers
    and verify execution order without real training.
    """

    async def train(
        self,
        mode: Literal["full", "incremental"],
        *,
        parent_version: str | None = None,
        factor_registry_path: Path | None = None,
        train_window_years: int = 3,
        config_snapshot: dict | None = None,
    ) -> _ModelArtifact:
        """Execute a full or incremental training run.

        Args:
            mode: "full" or "incremental".
            parent_version: Required for incremental mode, the parent model version.
            factor_registry_path: Optional path to factor registry for feature pipeline.
            train_window_years: Number of years of training data.
            config_snapshot: Optional config snapshot for reproducibility.

        Returns:
            A ModelArtifact containing the trained model and its metadata.
        """
        ...

    async def save(
        self,
        artifact: _ModelArtifact,
        *,
        mode: Literal["full", "incremental"],
        trigger: TriggerReason,
        parent_version: str | None = None,
        task_id: str = "",
        metrics: dict | None = None,
    ) -> str:
        """Save a trained model and return the version string.

        Args:
            artifact: The trained ModelArtifact to persist.
            mode: "full" or "incremental".
            trigger: The trigger reason for this training run.
            parent_version: Parent version for incremental models.
            task_id: Associated task ID.
            metrics: Test IC metrics dict.

        Returns:
            The version string of the saved model.
        """
        ...


class DefaultTrainerPort:
    """Default TrainerPort implementation wrapping v0.1.0 training modules.

    Delegates train() to trader_off.training.trainer.train_model() and
    save() to trader_off.training.serialize.save_model().
    """

    def __init__(self, models_dir: Path | None = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else Path("models")

    async def train(
        self,
        mode: Literal["full", "incremental"],
        *,
        parent_version: str | None = None,
        factor_registry_path: Path | None = None,
        train_window_years: int = 3,
        config_snapshot: dict | None = None,
    ) -> _ModelArtifact:
        """Execute training by delegating to v0.1.0 training.trainer.train_model.

        This is a skeleton implementation; full data loading, feature
        engineering, and incremental refit logic is implemented in
        FR-2100 (full retrain) and FR-2200 (incremental retrain).
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "DefaultTrainerPort.train(mode=%s, parent_version=%s, train_window_years=%d)",
            mode,
            parent_version,
            train_window_years,
        )

        # For FR-1500 the trainer is a placeholder; full wiring is done in
        # FR-2100/2200.
        raise NotImplementedError(
            "DefaultTrainerPort.train() requires data wiring (FR-2100/2200). "
            "For unit tests, inject a TrainerPort mock."
        )

    async def save(
        self,
        artifact: _ModelArtifact,
        *,
        mode: Literal["full", "incremental"],
        trigger: TriggerReason,
        parent_version: str | None = None,
        task_id: str = "",
        metrics: dict | None = None,
    ) -> str:
        """Save model by delegating to v0.1.0 training.serialize.save_model."""
        from trader_off.training.serialize import save_model

        metadata: dict = {
            "mode": mode,
            "task_id": task_id,
            "trigger": trigger.value,
        }
        if parent_version:
            metadata["parent_version"] = parent_version
        if metrics:
            metadata["test_ic_mean"] = metrics.get("test_ic_mean")
            metadata["test_rank_ic_mean"] = metrics.get("test_rank_ic_mean")

        saved_path = save_model(
            booster=artifact.booster,
            scaler=artifact.scaler,
            metadata=metadata,
            models_dir=self.models_dir,
            feature_names=artifact.feature_names,
        )
        return str(saved_path)


# ---------------------------------------------------------------------------
# PerfMonitorPort (FR-1900)
# ---------------------------------------------------------------------------


class PerfMonitorPort(Protocol):
    """Protocol for performance degradation detection (Round-2: IC-only).

    FR-1900: IC-based performance decay monitoring. No Sharpe.
    """

    def trigger_perf_degradation(self) -> _TriggerDecision:
        """Evaluate IC-based performance and return a trigger decision.

        Returns:
            TriggerDecision with should_retrain, reason, and notes="ic_only".
        """
        ...
