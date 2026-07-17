"""Scheduler module — Model retraining orchestration (Module B).

Provides:
- ports: ClockPort/TrainerPort/VirtualClockPort/DefaultTrainerPort/
  TriggerReason/PerfMonitorPort
- core: RetrainScheduler/SchedulerConfig/SchedulerStatus/RetrainTask
- cron: next_cron_fire / CronTrigger
- perf_monitor: PerfMonitor / TriggerDecision / detect_perf_decay (FR-1900)
"""

from trader_off.scheduler.core import (
    RetrainScheduler,
    RetrainTask,
    SchedulerConfig,
    SchedulerStatus,
)
from trader_off.scheduler.cron import CronTrigger, next_cron_fire
from trader_off.scheduler.perf_monitor import (
    PerfMonitor,
    TriggerDecision,
    detect_perf_decay,
)
from trader_off.scheduler.ports import (
    DefaultTrainerPort,
    PerfMonitorPort,
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
    "PerfMonitorPort",
    "TriggerReason",
    # Core
    "RetrainScheduler",
    "RetrainTask",
    "SchedulerConfig",
    "SchedulerStatus",
    # Cron
    "CronTrigger",
    "next_cron_fire",
    # Perf Monitor (FR-1900)
    "PerfMonitor",
    "TriggerDecision",
    "detect_perf_decay",
]
