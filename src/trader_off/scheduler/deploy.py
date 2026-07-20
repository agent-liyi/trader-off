"""Automatic model deployment to prediction service (FR-2400).

Provides:
- deploy_model: Validates new model metrics and atomically updates the
  registry's current_version pointer. Writes deploy.log on success.
- watch_registry: Polls registry.json for hot-reload support, calling
  a callback when current_version changes (polling 60s default).

Architecture constraints (architecture.md §3 Module B sub-module 8):
- Hot-reload = polling (60s default), watchdog optional and NOT default.
- Deploy failure must NOT leave prediction service in broken state
  (atomic pointer swap via registry's atomic write).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trader_off.scheduler.registry import ModelRegistry

logger = logging.getLogger(__name__)


def deploy_model(
    registry: ModelRegistry,
    new_version: str,
    *,
    metrics: dict,
    ic_floor: float = 0.005,
    logs_dir: Path | None = None,
) -> bool:
    """Deploy a newly trained model to the prediction service.

    Validates that the model's test_ic_mean meets or exceeds the ic_floor
    before deployment. On success, atomically updates the registry's
    current_version pointer and writes a deploy log entry.

    Per interfaces.md §3.14 / FR-2400.

    Args:
        registry: ModelRegistry instance managing model versions.
        new_version: Version string identifying the model to deploy.
        metrics: Dict with at least 'test_ic_mean' (float).
        ic_floor: Minimum acceptable IC mean value (default 0.005).
        logs_dir: Directory for deploy.log. Defaults to ./logs/.

    Returns:
        True if deployment succeeded (validated and deployed).
        False if validation failed (metrics below floor).

    Side effects:
        - Updates registry.current_version via atomic write.
        - Appends to logs_dir/deploy.log on success.
    """
    test_ic_mean = float(metrics.get("test_ic_mean", 0.0))

    if test_ic_mean < ic_floor:
        logger.warning(f"validation failed, not deploying {new_version}")
        return False

    old_version = registry.current()

    # Atomic pointer swap: rollback_to writes registry atomically (temp + rename)
    registry.rollback_to(new_version)

    # Write deploy log
    _write_deploy_log(old_version, new_version, "success", logs_dir)
    logger.info(f"from={old_version} to={new_version} status=success")

    return True


def _write_deploy_log(
    from_version: str | None,
    to_version: str,
    status: str,
    logs_dir: Path | None = None,
) -> None:
    """Append a deploy log entry to logs/deploy.log.

    Args:
        from_version: Previous active version (or None for first deploy).
        to_version: Newly deployed version.
        status: Outcome string (e.g., "success").
        logs_dir: Directory for the log file. Defaults to ./logs/.
    """
    log_dir = logs_dir or Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "deploy.log"

    entry = f"from={from_version} to={to_version} status={status}"
    with open(log_path, "a") as f:
        f.write(entry + "\n")


async def watch_registry(
    registry_path: Path,
    on_change: Callable[[], None] | Callable[[], Awaitable[None]],
    *,
    poll_interval_sec: float = 60.0,
) -> None:
    """Watch registry.json for current_version changes (hot-reload support).

    Polls registry_path at poll_interval_sec intervals. When the
    current_version field changes from the previously observed value,
    invokes on_change.

    Per interfaces.md §3.14 / AC-FR2400-03.

    Args:
        registry_path: Path to the registry.json file to monitor.
        on_change: Callback invoked when current_version changes.
            May be sync or async. Receives no arguments.
        poll_interval_sec: Seconds between polls (default 60s).
    """
    last_version: str | None = None

    while True:
        try:
            if registry_path.exists():
                data = json.loads(registry_path.read_text())
                current: str | None = data.get("current_version")
                if current != last_version:
                    if last_version is not None:
                        # Version changed from a previously observed value —
                        # trigger the hot-reload callback.
                        logger.info(
                            f"hot-reload: detected version change {last_version} -> {current}"
                        )
                        if asyncio.iscoroutinefunction(on_change):
                            await on_change()  # type: ignore[operator]
                        else:
                            on_change()  # type: ignore[operator]
                    last_version = current
        except Exception as exc:
            logger.error(f"watch_registry: error reading registry: {exc}")

        await asyncio.sleep(poll_interval_sec)
