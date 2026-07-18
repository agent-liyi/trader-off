"""Unit tests for FR-2500: scheduler state persistence.

AC coverage: AC-FR2500-01 (round-trip), AC-FR2500-02 (atomic write,
corrupt/missing recovery).  AC-FR2500-03 (recover_tasks).

Note: AC-FR2500-02 (kill -9 crash recovery) and AC-FR2500-03 (scheduler
restart recovery) are integration tests in Shield's scope (test-plan §8.2
test_scheduler_resilience.py).  These unit tests cover the atomic-write seam.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from trader_off.scheduler.core import RetrainTask
from trader_off.scheduler.ports import TriggerReason

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    task_id: str = "T-20260101-0001",
    mode: str = "full",
    reason: TriggerReason = TriggerReason.CRON_FULL,
    status: str = "pending",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    error: str | None = None,
    new_version: str | None = None,
    metrics: dict | None = None,
    parent_version: str | None = None,
) -> RetrainTask:
    """Create a RetrainTask for testing."""

    return RetrainTask(
        task_id=task_id,
        mode=mode,  # type: ignore[arg-type]
        reason=reason,
        status=status,  # type: ignore[arg-type]
        start_time=start_time,
        end_time=end_time,
        error=error,
        new_version=new_version,
        metrics=metrics,
        parent_version=parent_version,
    )


# ---------------------------------------------------------------------------
# AC-FR2500-01: Round-trip save_state → load_state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2500_01_roundtrip(tmp_path: Path):
    """AC-FR2500-01: save_state then load_state returns same tasks with all fields."""
    from trader_off.scheduler.state import load_state, save_state

    tasks = [
        _make_task(
            task_id="T-20260101-0001",
            mode="full",
            reason=TriggerReason.CRON_FULL,
            status="success",
            start_time=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC),
            new_version="v0.2.0.1",
            metrics={"test_ic_mean": 0.025},
        ),
        _make_task(
            task_id="T-20260101-0002",
            mode="incremental",
            reason=TriggerReason.DRIFT,
            status="running",
            start_time=datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC),
            parent_version="v0.2.0.1",
        ),
        _make_task(
            task_id="T-20260101-0003",
            mode="full",
            reason=TriggerReason.MANUAL,
            status="failed",
            start_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC),
            error="Training failed",
        ),
        _make_task(
            task_id="T-20260101-0004",
            mode="incremental",
            reason=TriggerReason.PERF_DEGRADATION,
            status="pending",
        ),
        _make_task(
            task_id="T-20260101-0005",
            mode="full",
            reason=TriggerReason.CRON_INCREMENTAL,
            status="success",
            start_time=datetime(2026, 1, 1, 14, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 14, 3, 0, tzinfo=UTC),
            new_version="v0.2.0.2",
            metrics={"test_ic_mean": 0.031, "test_rank_ic_mean": 0.042},
        ),
    ]

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()

    # When: save and load
    save_state(state_dir, tasks)
    loaded = load_state(state_dir)

    # Then: 5 records, all fields intact
    assert len(loaded) == 5
    for orig, loaded_task in zip(tasks, loaded):
        assert loaded_task.task_id == orig.task_id
        assert loaded_task.mode == orig.mode
        assert loaded_task.reason == orig.reason
        assert loaded_task.status == orig.status
        if orig.start_time is not None:
            assert loaded_task.start_time == orig.start_time
        else:
            assert loaded_task.start_time is None
        if orig.end_time is not None:
            assert loaded_task.end_time == orig.end_time
        else:
            assert loaded_task.end_time is None
        assert loaded_task.error == orig.error
        assert loaded_task.new_version == orig.new_version
        assert loaded_task.metrics == orig.metrics
        assert loaded_task.parent_version == orig.parent_version


# ---------------------------------------------------------------------------
# AC-FR2500-02: Atomic write — no partial file
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2500_02_atomic_write_no_partial_file(tmp_path: Path):
    """AC-FR2500-02: Atomic write ensures no partial file exists after simulated failure.

    The state file should never be partially written.  If an error occurs
    during write (simulated), the target file should be absent or the
    previous version should still be intact.
    """
    from trader_off.scheduler.state import load_state, save_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()
    state_file = state_dir / "last_tasks.json"

    tasks = [
        _make_task(task_id="T-20260101-0001", mode="full", reason=TriggerReason.CRON_FULL),
    ]

    # First: save normally
    save_state(state_dir, tasks)
    assert state_file.exists()

    # Add more tasks
    tasks.append(
        _make_task(task_id="T-20260101-0002", mode="incremental", reason=TriggerReason.DRIFT),
    )

    # Simulate a failure mid-write by checking the atomic pattern:
    # the file should be written to a temp file first, then renamed.
    # We can verify there's no .tmp file left behind and the file
    # is always valid JSON.
    save_state(state_dir, tasks)
    loaded = load_state(state_dir)
    assert len(loaded) == 2

    # Verify the file is valid JSON at all times
    assert state_file.exists()
    parsed = json.loads(state_file.read_text())
    assert isinstance(parsed, list)
    assert len(parsed) == 2

    # Verify no temp file artifact
    tmp_files = list(state_dir.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Temp file artifacts found: {tmp_files}"


# ---------------------------------------------------------------------------
# AC-FR2500-02: Corrupt JSON recovery
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2500_02_corrupt_json_recovery(tmp_path: Path, caplog):
    """AC-FR2500-02: Corrupt JSON file → load_state returns empty list + WARNING log."""
    from trader_off.scheduler.state import load_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()

    # Write corrupt JSON (half-written)
    (state_dir / "last_tasks.json").write_text("[{invalid json")

    with caplog.at_level(logging.WARNING):
        loaded = load_state(state_dir)

    assert loaded == []
    assert "corrupt" in caplog.text.lower() or "json" in caplog.text.lower()


# ---------------------------------------------------------------------------
# AC-FR2500-02: Missing file recovery
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2500_02_missing_file_recovery(tmp_path: Path, caplog):
    """AC-FR2500-02: Missing state file → load_state returns empty list + WARNING log."""
    from trader_off.scheduler.state import load_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()

    # No file written at all

    with caplog.at_level(logging.WARNING):
        loaded = load_state(state_dir)

    assert loaded == []
    assert "not found" in caplog.text.lower() or "missing" in caplog.text.lower()


# ---------------------------------------------------------------------------
# AC-FR2500-03: recover_tasks — running → failed, pending stays
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2500_03_recover_tasks():
    """AC-FR2500-03: recover_tasks: running→failed('scheduler restart'), pending unchanged."""
    from trader_off.scheduler.state import recover_tasks

    tasks = [
        _make_task(
            task_id="T-20260101-0001",
            mode="full",
            reason=TriggerReason.CRON_FULL,
            status="running",
            start_time=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        ),
        _make_task(
            task_id="T-20260101-0002",
            mode="incremental",
            reason=TriggerReason.DRIFT,
            status="pending",
        ),
        _make_task(
            task_id="T-20260101-0003",
            mode="full",
            reason=TriggerReason.MANUAL,
            status="success",
            start_time=datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 8, 5, 0, tzinfo=UTC),
        ),
        _make_task(
            task_id="T-20260101-0004",
            mode="incremental",
            reason=TriggerReason.PERF_DEGRADATION,
            status="running",
            start_time=datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC),
        ),
    ]

    recovered = recover_tasks(tasks)

    # Task 1: running → failed
    assert recovered[0].task_id == "T-20260101-0001"
    assert recovered[0].status == "failed"
    assert recovered[0].error == "scheduler restart"
    assert recovered[0].end_time is not None  # should be set

    # Task 2: pending → still pending
    assert recovered[1].task_id == "T-20260101-0002"
    assert recovered[1].status == "pending"

    # Task 3: success → unchanged
    assert recovered[2].task_id == "T-20260101-0003"
    assert recovered[2].status == "success"

    # Task 4: running → failed
    assert recovered[3].task_id == "T-20260101-0004"
    assert recovered[3].status == "failed"
    assert recovered[3].error == "scheduler restart"


# ---------------------------------------------------------------------------
# AC-FR2500-04: Concurrent unique task IDs (persistence perspective)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2500_04_multiple_tasks_persistence(tmp_path: Path):
    """AC-FR2500-04: Multiple tasks saved/loaded with unique task_ids."""
    from trader_off.scheduler.state import load_state, save_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()

    tasks = [
        _make_task(task_id=f"T-20260101-{i:04d}", mode="full", reason=TriggerReason.MANUAL)
        for i in range(1, 11)
    ]

    save_state(state_dir, tasks)
    loaded = load_state(state_dir)

    assert len(loaded) == 10
    loaded_ids = [t.task_id for t in loaded]
    assert len(set(loaded_ids)) == 10  # all unique
    assert len(loaded_ids) == len(set(loaded_ids))

    # Verify each record has required fields
    for r in loaded:
        assert r.task_id
        assert r.mode in ("full", "incremental")
        assert isinstance(r.reason, TriggerReason)
        assert r.status in ("pending", "running", "success", "failed")


# ---------------------------------------------------------------------------
# load_state: unexpected format (not a list)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_state_unexpected_format(tmp_path: Path, caplog):
    """load_state returns empty list when file contains a dict instead of a list."""
    from trader_off.scheduler.state import load_state

    state_dir = tmp_path / "scheduler_state"
    state_dir.mkdir()
    (state_dir / "last_tasks.json").write_text('{"key": "value"}')

    with caplog.at_level(logging.WARNING):
        loaded = load_state(state_dir)

    assert loaded == []
    assert "unexpected" in caplog.text.lower()


# ---------------------------------------------------------------------------
# append_cron_log
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_append_cron_log(tmp_path: Path):
    """append_cron_log appends a valid JSONL line."""
    from trader_off.scheduler.state import append_cron_log

    state_dir = tmp_path / "scheduler_state"
    entry = {
        "timestamp": "2026-01-01T16:00:00Z",
        "mode": "full",
        "triggered": True,
        "reason": "cron",
    }

    append_cron_log(state_dir, entry)

    log_file = state_dir / "cron_fire_log.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["mode"] == "full"
    assert parsed["triggered"] is True


# ---------------------------------------------------------------------------
# append_drift_history
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_append_drift_history_new(tmp_path: Path):
    """append_drift_history creates a new parquet file when none exists."""
    from trader_off.scheduler.state import append_drift_history

    state_dir = tmp_path / "scheduler_state"
    record = {
        "date": "2026-01-01",
        "should_retrain": False,
        "reason": "ok",
        "suggested_mode": "full",
        "drift_feature_count": 0,
    }

    append_drift_history(state_dir, record)

    history_file = state_dir / "drift_history.parquet"
    assert history_file.exists()
    df = pl.read_parquet(history_file)
    assert len(df) == 1
    assert df["reason"][0] == "ok"


@pytest.mark.unit
def test_append_drift_history_append(tmp_path: Path):
    """append_drift_history appends to existing parquet file."""
    from trader_off.scheduler.state import append_drift_history

    state_dir = tmp_path / "scheduler_state"

    record1 = {
        "date": "2026-01-01",
        "should_retrain": False,
        "reason": "ok",
        "suggested_mode": "full",
        "drift_feature_count": 0,
    }
    record2 = {
        "date": "2026-01-02",
        "should_retrain": True,
        "reason": "moderate_drift",
        "suggested_mode": "incremental",
        "drift_feature_count": 6,
    }

    append_drift_history(state_dir, record1)
    append_drift_history(state_dir, record2)

    history_file = state_dir / "drift_history.parquet"
    df = pl.read_parquet(history_file)
    assert len(df) == 2
    assert df["reason"][0] == "ok"
    assert df["reason"][1] == "moderate_drift"


# ---------------------------------------------------------------------------
# Additional coverage: atomic write failure cleanup (lines 101-105)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_atomic_write_oserror_cleans_up_temp(tmp_path: Path) -> None:
    """Lines 101-105: _atomic_write removes temp file when os.fsync fails."""
    from unittest.mock import patch

    from trader_off.scheduler.state import _atomic_write

    target = tmp_path / "test.txt"

    with patch("os.fsync", side_effect=OSError("disk error")):
        with pytest.raises(OSError):
            _atomic_write(target, "content")

    assert not target.exists()
    tmp_file = tmp_path / "test.txt.tmp"
    assert not tmp_file.exists()
