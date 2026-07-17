"""Scheduler CLI — retrain trigger / status subcommands.

FR-2000: Manual trigger CLI with `retrain trigger` and `retrain status`.
Per interfaces.md §4.3: argparse-based CLI with exit codes.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, Literal, TextIO

if TYPE_CHECKING:
    from trader_off.scheduler.core import RetrainScheduler

DEFAULT_REASON = "manual"


def build_retrain_parser() -> argparse.ArgumentParser:
    """Build the argparse ArgumentParser for the 'retrain' command.

    Returns:
        An ArgumentParser with 'trigger' and 'status' subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="trader-off retrain",
        description="Manually trigger retraining or view task status.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # trigger subcommand
    trigger_parser = subparsers.add_parser("trigger", help="Trigger a retraining task")
    trigger_parser.add_argument(
        "--mode",
        required=True,
        choices=["full", "incremental"],
        help="Retrain mode: full or incremental",
    )
    trigger_parser.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help="Reason for manual trigger (default: '%(default)s')",
    )

    # status subcommand
    status_parser = subparsers.add_parser("status", help="Show recent task history")
    status_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of tasks to show (default: %(default)s)",
    )

    return parser


async def run_trigger(
    scheduler: RetrainScheduler,
    mode: Literal["full", "incremental"],
    reason: str,
    stdout: TextIO | None = None,
) -> int:
    """Execute a manual retrain trigger.

    Args:
        scheduler: A running RetrainScheduler instance.
        mode: "full" or "incremental".
        reason: Human-readable reason for the trigger.
        stdout: Output stream (defaults to sys.stdout).

    Returns:
        Exit code: 0 on success.
    """
    from trader_off.scheduler.ports import TriggerReason

    if stdout is None:
        stdout = sys.stdout

    try:
        trigger_reason = TriggerReason(reason)
    except ValueError:
        trigger_reason = TriggerReason.MANUAL

    task = await scheduler.trigger_now(trigger_reason, mode)
    stdout.write(f"task_id={task.task_id} status={task.status}\n")
    return 0


async def run_status(
    scheduler: RetrainScheduler,
    limit: int = 10,
    stdout: TextIO | None = None,
) -> int:
    """Display the most recent retraining tasks.

    Args:
        scheduler: A RetrainScheduler instance.
        limit: Maximum number of tasks to display.
        stdout: Output stream (defaults to sys.stdout).

    Returns:
        Exit code: 0 on success.
    """
    if stdout is None:
        stdout = sys.stdout

    status = await scheduler.get_status()
    stdout.write(f"running={status.running}\n")
    stdout.write(f"active_tasks={status.active_tasks}\n")
    stdout.write(f"pending_tasks={status.pending_tasks}\n")
    stdout.write("\n")

    # Show task history
    tasks: list = []
    if hasattr(scheduler, "_task_history"):
        tasks = scheduler._task_history[-limit:]

    if not tasks:
        stdout.write("No tasks recorded.\n")
        return 0

    for task in tasks:
        reason_str = task.reason.value if hasattr(task.reason, "value") else str(task.reason)
        stdout.write(
            f"task_id={task.task_id} mode={task.mode} reason={reason_str} "
            f"status={task.status} start={task.start_time} end={task.end_time} "
            f"new_version={task.new_version or '-'}\n"
        )
    return 0


def main(args: list[str] | None = None) -> int:
    """CLI entry point for 'trader-off retrain'.

    Parses arguments and delegates to the appropriate subcommand.
    In a full integration scenario, this would construct a scheduler
    from the config; for unit testing the individual run_* functions
    are called directly.

    Returns:
        Exit code: 0 on success, non-zero on error.
    """
    parser = build_retrain_parser()
    _parsed = parser.parse_args(args)
    # With required=True on subparsers, _parsed.subcommand is always set
    return 0


if __name__ == "__main__":
    sys.exit(main())
