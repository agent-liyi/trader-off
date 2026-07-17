"""Unit tests for FR-2000: scheduler CLI (retrain trigger/status).

AC coverage: AC-FR2000-01, AC-FR2000-02
Tests the argparse-based CLI subcommand for manual retrain triggering.
"""

import asyncio
import re
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import MagicMock

import pytest

from trader_off.scheduler.core import RetrainScheduler, SchedulerConfig
from trader_off.scheduler.ports import TriggerReason, VirtualClockPort


def _make_scheduler():
    """Create a RetrainScheduler with mock dependencies for testing."""
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    return RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )


# ---------------------------------------------------------------------------
# AC-FR2000-01: retrain trigger CLI
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr2000_01_trigger_output_format():
    """AC-FR2000-01: trigger outputs task_id=<uuid> and status=pending."""
    from trader_off.scheduler.cli import run_trigger

    scheduler = _make_scheduler()

    # Start the scheduler so trigger_now works
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        exit_code = await run_trigger(
            scheduler=scheduler,
            mode="full",
            reason="manual_test",
            stdout=captured_stdout,
        )
    finally:
        await scheduler.stop()
        await start_task

    assert exit_code == 0
    output = captured_stdout.getvalue()

    # Verify task_id=<uuid> format
    match = re.search(r"task_id=(\S+)", output)
    assert match is not None, f"Expected 'task_id=...' in output, got: {output}"
    task_id = match.group(1)
    assert len(task_id) > 0

    # Verify status=pending
    assert "status=pending" in output


@pytest.mark.unit
async def test_ac_fr2000_01_trigger_with_incremental_mode():
    """AC-FR2000-01: trigger with --mode incremental works correctly."""
    from trader_off.scheduler.cli import run_trigger

    scheduler = _make_scheduler()
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        exit_code = await run_trigger(
            scheduler=scheduler,
            mode="incremental",
            reason="drift_manual",
            stdout=captured_stdout,
        )
    finally:
        await scheduler.stop()
        await start_task

    assert exit_code == 0
    output = captured_stdout.getvalue()
    assert "task_id=" in output
    assert "status=pending" in output


@pytest.mark.unit
async def test_ac_fr2000_01_trigger_default_reason():
    """AC-FR2000-01: trigger without --reason defaults to 'manual'."""
    from trader_off.scheduler.cli import run_trigger

    scheduler = _make_scheduler()
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        exit_code = await run_trigger(
            scheduler=scheduler,
            mode="full",
            reason="manual",
            stdout=captured_stdout,
        )
    finally:
        await scheduler.stop()
        await start_task

    assert exit_code == 0
    assert "task_id=" in captured_stdout.getvalue()


# ---------------------------------------------------------------------------
# AC-FR2000-02: retrain status CLI
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr2000_02_status_output():
    """AC-FR2000-02: 'retrain status' outputs last 10 tasks with required fields."""
    from trader_off.scheduler.cli import run_status

    scheduler = _make_scheduler()
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        # Trigger a couple of tasks so we have task history
        await scheduler.trigger_now(TriggerReason.MANUAL, "full")
        await scheduler.trigger_now(TriggerReason.DRIFT, "incremental")
        await asyncio.sleep(0.05)

        exit_code = await run_status(
            scheduler=scheduler,
            limit=10,
            stdout=captured_stdout,
        )
    finally:
        await scheduler.stop()
        await start_task

    assert exit_code == 0
    output = captured_stdout.getvalue()
    # Should contain task_id references
    assert "task_id" in output


@pytest.mark.unit
async def test_ac_fr2000_02_status_with_limit():
    """AC-FR2000-02: retrain status accepts a --limit flag."""
    from trader_off.scheduler.cli import run_status

    scheduler = _make_scheduler()
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        exit_code = await run_status(
            scheduler=scheduler,
            limit=5,
            stdout=captured_stdout,
        )
    finally:
        await scheduler.stop()
        await start_task

    assert exit_code == 0


# ---------------------------------------------------------------------------
# CLI argparse tests (unit-level, no scheduler needed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_retrain_parser_trigger_subcommand():
    """retrain trigger subcommand parses --mode and --reason correctly."""
    from trader_off.scheduler.cli import build_retrain_parser

    parser = build_retrain_parser()
    args = parser.parse_args(["trigger", "--mode", "full", "--reason", "test_run"])
    assert args.subcommand == "trigger"
    assert args.mode == "full"
    assert args.reason == "test_run"


@pytest.mark.unit
def test_retrain_parser_trigger_default_reason():
    """retrain trigger --reason defaults to 'manual'."""
    from trader_off.scheduler.cli import build_retrain_parser

    parser = build_retrain_parser()
    args = parser.parse_args(["trigger", "--mode", "incremental"])
    assert args.subcommand == "trigger"
    assert args.mode == "incremental"
    assert args.reason == "manual"


@pytest.mark.unit
def test_retrain_parser_status_subcommand():
    """retrain status subcommand parses correctly."""
    from trader_off.scheduler.cli import build_retrain_parser

    parser = build_retrain_parser()
    args = parser.parse_args(["status"])
    assert args.subcommand == "status"


@pytest.mark.unit
def test_retrain_parser_status_with_limit():
    """retrain status --limit parses correctly."""
    from trader_off.scheduler.cli import build_retrain_parser

    parser = build_retrain_parser()
    args = parser.parse_args(["status", "--limit", "5"])
    assert args.subcommand == "status"
    assert args.limit == 5


@pytest.mark.unit
def test_retrain_parser_requires_subcommand():
    """retrain parser requires a subcommand."""
    from trader_off.scheduler.cli import build_retrain_parser

    parser = build_retrain_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_run_trigger_unknown_reason_maps_to_manual():
    """run_trigger with unknown reason falls back to MANUAL."""
    from trader_off.scheduler.cli import run_trigger

    scheduler = _make_scheduler()
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        exit_code = await run_trigger(
            scheduler=scheduler,
            mode="incremental",
            reason="bogus_reason_123",
            stdout=captured_stdout,
        )
    finally:
        await scheduler.stop()
        await start_task

    assert exit_code == 0
    output = captured_stdout.getvalue()
    assert "task_id=" in output
    assert "status=pending" in output


@pytest.mark.unit
async def test_run_status_empty_history():
    """run_status with no task history handles gracefully."""
    from trader_off.scheduler.cli import run_status

    scheduler = _make_scheduler()
    captured_stdout = StringIO()

    exit_code = await run_status(
        scheduler=scheduler,
        limit=10,
        stdout=captured_stdout,
    )

    assert exit_code == 0
    output = captured_stdout.getvalue()
    assert "No tasks recorded" in output


@pytest.mark.unit
async def test_run_status_default_stdout():
    """run_status uses sys.stdout when no stdout argument is given."""
    from trader_off.scheduler.cli import run_status

    scheduler = _make_scheduler()
    # Don't pass stdout — covers the sys.stdout default branch
    exit_code = await run_status(
        scheduler=scheduler,
        limit=10,
    )
    assert exit_code == 0


@pytest.mark.unit
async def test_run_trigger_default_stdout():
    """run_trigger uses sys.stdout when no stdout argument is given."""
    from trader_off.scheduler.cli import run_trigger

    scheduler = _make_scheduler()
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    try:
        # Don't pass stdout — covers the sys.stdout default branch
        exit_code = await run_trigger(
            scheduler=scheduler,
            mode="full",
            reason="test_default_stdout",
        )
        assert exit_code == 0
    finally:
        await scheduler.stop()
        await start_task


@pytest.mark.unit
def test_main_no_args_prints_help():
    """main() with no args returns non-zero exit code."""
    from trader_off.scheduler.cli import main

    # When called with empty args, parser requires subcommand and exits
    with pytest.raises(SystemExit):
        main([])


@pytest.mark.unit
def test_main_with_subcommand():
    """main() with 'trigger' subcommand returns 0."""
    from trader_off.scheduler.cli import main

    exit_code = main(["trigger", "--mode", "full", "--reason", "test"])
    assert exit_code == 0
