"""Scheduler module — Model retraining orchestration (Module B).

Provides:
- ports: ClockPort / TrainerPort / VirtualClockPort / DefaultTrainerPort / TriggerReason
- core: RetrainScheduler / SchedulerConfig / SchedulerStatus / RetrainTask
"""

from trader_off.scheduler.core import (
    RetrainScheduler,
    RetrainTask,
    SchedulerConfig,
    SchedulerStatus,
)
from trader_off.scheduler.ports import (
    DefaultTrainerPort,
    SystemClockPort,
    TrainerPort,
    TriggerReason,
    VirtualClockPort,
)

__all__ = [
    # Ports
    "TrainerPort",
    "DefaultTrainerPort",
    "SystemClockPort",
    "VirtualClockPort",
    "TriggerReason",
    # Core
    "RetrainScheduler",
    "RetrainTask",
    "SchedulerConfig",
    "SchedulerStatus",
]
