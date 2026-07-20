"""Integration tests: scheduler CLI start/stop/status + config validation.

Covers AC-FR2700-01~04: scheduler start, scheduler status, missing cron
field → ConfigValidationError, invalid cron → ConfigValidationError.

Per test-plan §8.2, interfaces.md §4.2 / §1.8.
"""

import io
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from trader_off.scheduler.cli import (
    load_scheduler_config,
    run_scheduler_start,
    run_scheduler_status,
    validate_cron_expr,
)
from trader_off.scheduler.core import RetrainScheduler, SchedulerConfig
from trader_off.scheduler.ports import VirtualClockPort
from trader_off.utils.exceptions import ConfigValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_scheduler_yaml(tmp_path: Path, overrides: dict | None = None) -> Path:
    """Write a minimal valid scheduler YAML config."""
    base = {
        "cron": {
            "full_retrain_cron": "0 16 * * 1-5",
            "incremental_retrain_cron": "0 16 * * 1-5",
            "drift_check_cron": "0 9 * * 1-5",
        },
        "tick_interval_sec": 1.0,
    }
    if overrides:
        import copy

        merged = copy.deepcopy(base)
        merged.update(overrides)
    else:
        merged = base

    config_path = tmp_path / "scheduler.yaml"
    config_path.write_text(yaml.dump(merged))
    return config_path


# ---------------------------------------------------------------------------
# AC-FR2700-01: scheduler start with valid config → exit code 0
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2700_01_scheduler_start_exit_code_0(tmp_path, monkeypatch):
    """AC-FR2700-01: scheduler start --config <valid_yaml> returns exit code 0
    and prints 'Scheduler started'."""
    config_path = _write_scheduler_yaml(tmp_path)
    monkeypatch.chdir(tmp_path)

    config = load_scheduler_config(config_path)
    stdout = io.StringIO()

    # Override clock to avoid real time dependency
    config.clock = VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC))

    exit_code = await run_scheduler_start(
        config, config_path=config_path, stdout=stdout, run_loop=False
    )
    output = stdout.getvalue()

    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
    assert "Scheduler started" in output, f"Expected 'Scheduler started' in: {output}"


@pytest.mark.integration
async def test_ac_fr2700_01_scheduler_config_loads_correct_fields(tmp_path, monkeypatch):
    """AC-FR2700-01: Config loaded from YAML has correct fields."""
    config_path = _write_scheduler_yaml(tmp_path)
    monkeypatch.chdir(tmp_path)

    config = load_scheduler_config(config_path)
    assert isinstance(config, SchedulerConfig)
    assert config.full_retrain_cron == "0 16 * * 1-5"
    assert config.incremental_retrain_cron == "0 16 * * 1-5"
    assert config.drift_check_cron == "0 9 * * 1-5"
    assert config.tick_interval_sec == 1.0


# ---------------------------------------------------------------------------
# AC-FR2700-02: scheduler status returns running=False when stopped
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2700_02_scheduler_status_when_stopped(tmp_path, monkeypatch):
    """AC-FR2700-02: scheduler status shows running=False when scheduler
    is not running (exit code 0)."""
    config_path = _write_scheduler_yaml(tmp_path)
    monkeypatch.chdir(tmp_path)

    config = load_scheduler_config(config_path)
    config.clock = VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC))

    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    stdout = io.StringIO()
    exit_code = await run_scheduler_status(scheduler, stdout=stdout)
    output = stdout.getvalue()

    assert exit_code == 0
    assert "running=False" in output, f"Expected running=False, got: {output}"


@pytest.mark.integration
async def test_ac_fr2700_02_scheduler_status_shows_task_info(tmp_path, monkeypatch):
    """AC-FR2700-02: scheduler status shows task_id, mode, reason, status, etc."""
    config_path = _write_scheduler_yaml(tmp_path)
    monkeypatch.chdir(tmp_path)

    config = load_scheduler_config(config_path)
    config.clock = VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC))
    config.state_dir = tmp_path / "scheduler_state"

    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    stdout = io.StringIO()
    exit_code = await run_scheduler_status(scheduler, stdout=stdout)
    output = stdout.getvalue()

    assert exit_code == 0
    # Status output should contain running flag and task counts
    assert "running=" in output
    assert "active_tasks=" in output
    assert "pending_tasks=" in output


# ---------------------------------------------------------------------------
# AC-FR2700-03: Missing cron field → ConfigValidationError
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_fr2700_03_missing_cron_field_raises(tmp_path):
    """AC-FR2700-03: Config without 'cron' field raises ConfigValidationError
    with 'cron is required'."""
    config_path = tmp_path / "bad_config.yaml"
    config_path.write_text(yaml.dump({"tick_interval_sec": 1.0}))

    with pytest.raises(ConfigValidationError, match="cron is required"):
        load_scheduler_config(config_path)


@pytest.mark.integration
def test_ac_fr2700_03_empty_config_raises(tmp_path):
    """AC-FR2700-03: Empty YAML config raises ConfigValidationError."""
    config_path = tmp_path / "empty_config.yaml"
    config_path.write_text(yaml.dump({}))

    with pytest.raises(ConfigValidationError, match="cron is required"):
        load_scheduler_config(config_path)


@pytest.mark.integration
def test_ac_fr2700_03_missing_config_file_raises(tmp_path):
    """AC-FR2700-03: Non-existent config file raises ConfigValidationError."""
    config_path = tmp_path / "nonexistent.yaml"
    assert not config_path.exists()

    with pytest.raises(ConfigValidationError, match="config file not found"):
        load_scheduler_config(config_path)


# ---------------------------------------------------------------------------
# AC-FR2700-04: Invalid cron expression → ConfigValidationError
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_fr2700_04_invalid_cron_expression_raises(tmp_path):
    """AC-FR2700-04: Invalid cron expression ('invalid cron') raises
    ConfigValidationError."""
    config_path = tmp_path / "bad_cron.yaml"
    bad_config = {
        "cron": {
            "full_retrain_cron": "invalid cron",
            "incremental_retrain_cron": "0 16 * * 1-5",
            "drift_check_cron": "0 9 * * 1-5",
        },
    }
    config_path.write_text(yaml.dump(bad_config))

    with pytest.raises(ConfigValidationError, match="invalid cron expression"):
        load_scheduler_config(config_path)


@pytest.mark.integration
def test_ac_fr2700_04_validate_cron_expr_pure(tmp_path):
    """AC-FR2700-04: validate_cron_expr raises for clearly invalid expressions."""
    # Valid expression should not raise
    validate_cron_expr("0 16 * * 1-5")

    # Invalid expression should raise
    with pytest.raises(ConfigValidationError, match="invalid cron expression"):
        validate_cron_expr("not a cron")

    # Empty string should not be a valid cron
    with pytest.raises(ConfigValidationError):
        validate_cron_expr("")


@pytest.mark.integration
def test_ac_fr2700_04_valid_cron_expressions_pass(tmp_path):
    """AC-FR2700-04: Well-known cron expressions validate successfully."""
    valid_expressions = [
        "0 16 * * 1-5",  # Every weekday at 16:00
        "0 9 * * 1-5",  # Every weekday at 09:00
        "*/5 * * * *",  # Every 5 minutes
        "0 0 1 * *",  # First day of month at midnight
        "30 8 * * 1,3,5",  # Mon/Wed/Fri at 08:30
    ]
    for expr in valid_expressions:
        try:
            validate_cron_expr(expr)
        except ConfigValidationError as e:
            pytest.fail(f"Valid cron '{expr}' should not raise: {e}")
