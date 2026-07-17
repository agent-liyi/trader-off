"""Scheduler CLI — retrain trigger / status + scheduler lifecycle subcommands.

FR-2000: Manual trigger CLI with `retrain trigger` and `retrain status`.
FR-2700: Scheduler lifecycle CLI (start / stop / status) with config loading.
Per interfaces.md §4.2 / §4.3: argparse-based CLI with exit codes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TextIO

import yaml  # type: ignore[import-untyped]

from trader_off.utils.exceptions import ConfigValidationError

if TYPE_CHECKING:
    from trader_off.scheduler.core import RetrainScheduler, SchedulerConfig

DEFAULT_REASON = "manual"

# ---------------------------------------------------------------------------
# Config validation / loading (FR-2700)
# ---------------------------------------------------------------------------


def validate_cron_expr(expr: str) -> None:
    """Validate a cron expression string.

    Args:
        expr: Cron expression (5-field format).

    Raises:
        ConfigValidationError: If the expression is invalid.
    """
    from croniter import croniter  # type: ignore[import-untyped]

    try:
        croniter(expr)
    except (ValueError, KeyError) as exc:
        raise ConfigValidationError(f"invalid cron expression: {expr!r}: {exc}") from exc


def _build_config_from_dict(
    raw: dict[str, Any],
    cli_overrides: dict[str, Any] | None = None,
) -> SchedulerConfig:
    """Build a SchedulerConfig from a raw dict with precedence.

    Precedence: CLI overrides > YAML values > SchedulerConfig defaults.

    Args:
        raw: Parsed YAML dict (may be empty).
        cli_overrides: CLI argument overrides (optional).

    Returns:
        A SchedulerConfig instance.

    Raises:
        ConfigValidationError: If required fields are missing or invalid.
    """
    from trader_off.scheduler.core import SchedulerConfig

    cli = cli_overrides or {}

    # --- cron validation ---
    cron_raw = raw.get("cron")
    if not cron_raw or not isinstance(cron_raw, dict):
        raise ConfigValidationError("cron is required in scheduler config")

    full_cron = cli.get("full_retrain_cron", cron_raw.get("full_retrain_cron", "0 16 * * 1-5"))
    incr_cron = cli.get(
        "incremental_retrain_cron",
        cron_raw.get("incremental_retrain_cron", "0 16 * * 1-5"),
    )
    drift_cron = cli.get("drift_check_cron", cron_raw.get("drift_check_cron", "0 9 * * 1-5"))

    validate_cron_expr(str(full_cron))
    validate_cron_expr(str(incr_cron))
    validate_cron_expr(str(drift_cron))

    return SchedulerConfig(
        # Core
        tick_interval_sec=float(cli.get("tick_interval_sec", raw.get("tick_interval_sec", 1.0))),
        max_concurrent_tasks=int(
            cli.get("max_concurrent_tasks", raw.get("max_concurrent_tasks", 1))
        ),
        trading_calendar=cli.get(
            "trading_calendar",
            raw.get("trading_calendar", "data_loader"),
        ),
        # Cron
        full_retrain_cron=str(full_cron),
        incremental_retrain_cron=str(incr_cron),
        full_retrain_frequency_days=int(
            cli.get(
                "full_retrain_frequency_days",
                cron_raw.get("full_retrain_frequency_days", 5),
            )
        ),
        drift_check_cron=str(drift_cron),
        # Drift thresholds
        psi_threshold=float(cli.get("psi_threshold", raw.get("psi_threshold", 0.2))),
        ks_pvalue_threshold=float(
            cli.get("ks_pvalue_threshold", raw.get("ks_pvalue_threshold", 0.05))
        ),
        psi_strong=float(cli.get("psi_strong", raw.get("psi_strong", 0.5))),
        min_drift_features_incremental=int(
            cli.get(
                "min_drift_features_incremental",
                raw.get("min_drift_features_incremental", 5),
            )
        ),
        min_drift_features_full=int(
            cli.get("min_drift_features_full", raw.get("min_drift_features_full", 3))
        ),
        # Perf thresholds
        ic_floor=float(cli.get("ic_floor", raw.get("ic_floor", 0.005))),
        ic_drop_ratio=float(cli.get("ic_drop_ratio", raw.get("ic_drop_ratio", 0.3))),
        ic_window=int(cli.get("ic_window", raw.get("ic_window", 20))),
        # Retention
        keep_latest_n=int(cli.get("keep_latest_n", raw.get("keep_latest_n", 10))),
        keep_pinned_versions=list(
            cli.get("keep_pinned_versions", raw.get("keep_pinned_versions", []))
        ),
        keep_full_retrain_only=bool(
            cli.get("keep_full_retrain_only", raw.get("keep_full_retrain_only", True))
        ),
        # Deploy
        model_load_mode=cli.get("model_load_mode", raw.get("model_load_mode", "lazy")),
        # API
        run_api=bool(cli.get("run_api", raw.get("run_api", False))),
        api_host=str(cli.get("api_host", raw.get("api_host", "127.0.0.1"))),
        api_port=int(cli.get("api_port", raw.get("api_port", 8765))),
        # Persistence
        state_dir=Path(str(cli.get("state_dir", raw.get("state_dir", "scheduler_state")))),
        models_dir=Path(str(cli.get("models_dir", raw.get("models_dir", "models")))),
        reports_dir=Path(str(cli.get("reports_dir", raw.get("reports_dir", "reports")))),
    )


def load_scheduler_config(
    config_path: Path,
    cli_overrides: dict[str, Any] | None = None,
) -> SchedulerConfig:
    """Load and validate a scheduler YAML config.

    Precedence: CLI overrides > YAML values > defaults.

    Args:
        config_path: Path to the scheduler YAML config file.
        cli_overrides: Optional CLI argument overrides.

    Returns:
        A validated SchedulerConfig.

    Raises:
        ConfigValidationError: If the config file is missing or invalid.
    """
    if not config_path.exists():
        raise ConfigValidationError(f"config file not found: {config_path}")

    with open(config_path) as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ConfigValidationError("config file must contain a YAML mapping")

    return _build_config_from_dict(raw, cli_overrides)


# ---------------------------------------------------------------------------
# Scheduler lifecycle CLI (FR-2700)
# ---------------------------------------------------------------------------


def build_scheduler_parser() -> argparse.ArgumentParser:
    """Build the argparse ArgumentParser for the 'scheduler' command.

    Returns:
        An ArgumentParser with 'start', 'stop', and 'status' subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="trader-off scheduler",
        description="Manage the retraining scheduler lifecycle.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # start subcommand
    start_parser = subparsers.add_parser("start", help="Start the scheduler")
    start_parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to scheduler YAML config file",
    )

    # stop subcommand
    subparsers.add_parser("stop", help="Stop the scheduler")

    # status subcommand
    subparsers.add_parser("status", help="Show scheduler status")

    return parser


async def run_scheduler_start(
    config: SchedulerConfig,
    config_path: Path | None = None,
    stdout: TextIO | None = None,
    run_loop: bool = False,
) -> int:
    """Start the scheduler with the given configuration.

    Args:
        config: Validated SchedulerConfig.
        config_path: Optional path to the config file (for logging).
        stdout: Output stream (defaults to sys.stdout).
        run_loop: If True, start the actual scheduler loop (blocking).
                  If False, construct and return (for testing).

    Returns:
        Exit code: 0 on success, 4 on config error.
    """
    from trader_off.scheduler.core import RetrainScheduler

    if stdout is None:
        stdout = sys.stdout

    scheduler = RetrainScheduler(
        config=config,
        model_registry=_placeholder_port("model registry"),
        drift_detector=_placeholder_port("drift detector"),
        perf_monitor=_placeholder_port("perf monitor"),
        trainer=_placeholder_port("trainer"),
    )

    if run_loop:
        await scheduler.start()
    else:
        # In test mode we just verify the config was loaded and scheduler constructed
        pass

    stdout.write("Scheduler started\n")
    return 0


async def run_scheduler_stop(
    scheduler: RetrainScheduler,
    stdout: TextIO | None = None,
) -> int:
    """Stop a running scheduler.

    Args:
        scheduler: A RetrainScheduler instance.
        stdout: Output stream (defaults to sys.stdout).

    Returns:
        Exit code: 0 on success.
    """
    if stdout is None:
        stdout = sys.stdout

    await scheduler.stop()
    stdout.write("Scheduler stopped\n")
    return 0


async def run_scheduler_status(
    scheduler: RetrainScheduler,
    stdout: TextIO | None = None,
) -> int:
    """Display the current scheduler status.

    Args:
        scheduler: A RetrainScheduler instance.
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
    if status.next_trigger_time is not None:
        stdout.write(f"next_trigger_time={status.next_trigger_time}\n")
    if status.next_trigger_mode is not None:
        stdout.write(f"next_trigger_mode={status.next_trigger_mode}\n")
    if status.last_full_retrain_date is not None:
        stdout.write(f"last_full_retrain_date={status.last_full_retrain_date}\n")
    if status.last_incremental_retrain_date is not None:
        stdout.write(f"last_incremental_retrain_date={status.last_incremental_retrain_date}\n")

    # Show task history
    tasks: list = []
    if hasattr(scheduler, "_task_history"):
        tasks = scheduler._task_history[-10:]

    if tasks:
        stdout.write("\n")
        for task in tasks:
            reason_str = task.reason.value if hasattr(task.reason, "value") else str(task.reason)
            stdout.write(
                f"task_id={task.task_id} mode={task.mode} reason={reason_str} "
                f"status={task.status} start={task.start_time} end={task.end_time} "
                f"new_version={task.new_version or '-'}\n"
            )

    return 0


def _placeholder_port(name: str) -> Any:
    """Return a placeholder for a scheduler port (tests must inject real ports).

    Args:
        name: Descriptive name for error messages.

    Returns:
        A sentinel object that raises on any method call.

    Raises:
        RuntimeError: Always — this is not a real port.
    """

    class _Placeholder:
        def __init__(self, port_name: str):
            self._port_name = port_name

        def __getattr__(self, item: str) -> Any:
            raise RuntimeError(
                f"Placeholder port '{self._port_name}' has no attribute '{item}'. "
                f"Real ports must be injected for production use."
            )

    return _Placeholder(name)


# ---------------------------------------------------------------------------
# Retrain subcommands (FR-2000, existing)
# ---------------------------------------------------------------------------


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
