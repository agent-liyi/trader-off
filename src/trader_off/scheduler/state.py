"""Scheduler state persistence (FR-2500).

Provides atomic JSON serialization for RetrainTask lists, recovery from
corrupt or missing files, and task recovery logic for scheduler restarts.

Per interfaces.md §3.15:
- save_state: atomic write (temp file + fsync + rename).
- load_state: recover from corrupt/missing file (WARNING + return default).
- recover_tasks: running → failed("scheduler restart"), pending stays.
- append_cron_log: append JSONL entries.
- append_drift_history: append parquet records.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from trader_off.scheduler.ports import TriggerReason

if TYPE_CHECKING:
    from trader_off.scheduler.core import RetrainTask

logger = logging.getLogger(__name__)

_STATE_FILE: str = "last_tasks.json"
_CRON_LOG_FILE: str = "cron_fire_log.jsonl"
_DRIFT_HISTORY_FILE: str = "drift_history.parquet"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _task_to_dict(task: RetrainTask) -> dict:
    """Serialize a RetrainTask to a JSON-safe dict."""
    return {
        "task_id": task.task_id,
        "mode": task.mode,
        "reason": task.reason.value,
        "parent_version": task.parent_version,
        "status": task.status,
        "start_time": task.start_time.isoformat() if task.start_time else None,
        "end_time": task.end_time.isoformat() if task.end_time else None,
        "error": task.error,
        "new_version": task.new_version,
        "metrics": task.metrics,
    }


def _dict_to_task(d: dict) -> RetrainTask:
    """Deserialize a dict to a RetrainTask.

    Safe against missing keys — fills in defaults for backward compatibility.
    """
    from trader_off.scheduler.core import RetrainTask

    return RetrainTask(
        task_id=d.get("task_id", ""),
        mode=d.get("mode", "full"),  # type: ignore[arg-type]
        reason=TriggerReason(d.get("reason", "manual")),
        parent_version=d.get("parent_version"),
        status=d.get("status", "pending"),  # type: ignore[arg-type]
        start_time=datetime.fromisoformat(d["start_time"]) if d.get("start_time") else None,
        end_time=datetime.fromisoformat(d["end_time"]) if d.get("end_time") else None,
        error=d.get("error"),
        new_version=d.get("new_version"),
        metrics=d.get("metrics"),
    )


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------


def _atomic_write(target: Path, content: str) -> None:
    """Write content to target atomically using temp file + fsync + rename.

    Args:
        target: Destination file path.
        content: String content to write.
    """
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        # Ensure the data is physically on disk before renaming
        fd = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        tmp.replace(target)
    except Exception:
        # Clean up temp file on failure
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_state(state_dir: Path, tasks: list[RetrainTask]) -> None:
    """Persist the task list to state_dir/last_tasks.json atomically.

    Write is atomic: content is written to a temp file, fsync'd, then
    renamed over the target.  This ensures the target file is never
    observed in a partially-written state (AC-FR2500-02).

    Args:
        state_dir: Directory to write the state file into.
        tasks: List of RetrainTask objects to persist.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / _STATE_FILE

    records = [_task_to_dict(t) for t in tasks]
    content = json.dumps(records, ensure_ascii=False, indent=2, default=str)

    _atomic_write(target, content)


def load_state(state_dir: Path) -> list[RetrainTask]:
    """Load the persisted task list with recovery from corrupt/missing files.

    Args:
        state_dir: Directory containing last_tasks.json.

    Returns:
        List of RetrainTask objects.  Returns an empty list if the file
        is missing or the JSON is corrupt (WARNING logged in both cases).
    """
    target = state_dir / _STATE_FILE

    if not target.exists():
        logger.warning("State file %s not found, returning empty task list", target)
        return []

    try:
        raw = target.read_text(encoding="utf-8")
        records = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("State file %s is corrupt (%s), returning empty task list", target, exc)
        return []

    if not isinstance(records, list):
        logger.warning("State file %s has unexpected format, returning empty task list", target)
        return []

    return [_dict_to_task(r) for r in records]


def recover_tasks(tasks: list[RetrainTask]) -> list[RetrainTask]:
    """Recover tasks after a scheduler restart.

    Marks all tasks that were in 'running' status as 'failed' with
    error message "scheduler restart".  Pending, success, and failed
    tasks are left unchanged.

    Also sets end_time to now(UTC) for any running tasks that lacked it.

    Args:
        tasks: List of tasks as persisted in last_tasks.json.

    Returns:
        New list of RetrainTask objects with recovery applied.
        Original objects are not mutated — new RetrainTask objects
        are created for modified entries.
    """
    now_utc = datetime.now(UTC)
    recovered: list[RetrainTask] = []

    for task in tasks:
        if task.status == "running":
            from trader_off.scheduler.core import RetrainTask

            recovered.append(
                RetrainTask(
                    task_id=task.task_id,
                    mode=task.mode,
                    reason=task.reason,
                    parent_version=task.parent_version,
                    status="failed",  # type: ignore[arg-type]
                    start_time=task.start_time,
                    end_time=task.end_time or now_utc,
                    error="scheduler restart",
                    new_version=task.new_version,
                    metrics=task.metrics,
                )
            )
        else:
            recovered.append(task)

    return recovered


def append_cron_log(state_dir: Path, entry: dict) -> None:
    """Append a JSONL entry to the cron fire log.

    Args:
        state_dir: Scheduler state directory.
        entry: Dict with timestamp, mode, triggered, reason fields.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / _CRON_LOG_FILE
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with open(target, "a", encoding="utf-8") as f:
        f.write(line)


def append_drift_history(state_dir: Path, drift_record: dict) -> None:
    """Append a drift detection record to the parquet history file.

    Args:
        state_dir: Scheduler state directory.
        drift_record: Dict with drift detection results (date, should_retrain,
            reason, suggested_mode, drift_feature_count, etc.).
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / _DRIFT_HISTORY_FILE

    new_row = pl.DataFrame([drift_record])

    if target.exists():
        existing = pl.read_parquet(target)
        combined = pl.concat([existing, new_row], how="diagonal_relaxed")
    else:
        combined = new_row

    combined.write_parquet(target)
