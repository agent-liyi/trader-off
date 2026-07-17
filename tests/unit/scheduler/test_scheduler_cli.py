"""Unit tests for FR-2700: scheduler CLI (start/stop/status) and config loading.

AC coverage: AC-FR2700-01, AC-FR2700-02, AC-FR2700-03, AC-FR2700-04
Tests the argparse-based CLI subcommands for scheduler lifecycle management
and YAML config loading with precedence (CLI args > YAML > defaults).
"""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from trader_off.scheduler.core import SchedulerConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, name: str, content: dict) -> Path:
    """Write a YAML file to tmp_path and return its Path."""
    p = tmp_path / name
    p.write_text(yaml.dump(content))
    return p


def _minimal_scheduler_yaml() -> dict:
    """Return a minimal valid scheduler YAML config dict."""
    return {
        "cron": {
            "full_retrain_cron": "0 16 * * 1-5",
            "incremental_retrain_cron": "0 16 * * 1-5",
            "full_retrain_frequency_days": 5,
            "drift_check_cron": "0 9 * * 1-5",
        },
    }


# ---------------------------------------------------------------------------
# AC-FR2700-03: config missing cron field → ConfigValidationError
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2700_03_config_missing_cron_field(tmp_path: Path):
    """AC-FR2700-03: missing 'cron' key raises ConfigValidationError."""
    config_content = {
        "tick_interval_sec": 2.0,
        "max_concurrent_tasks": 2,
    }
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.utils.exceptions import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="cron is required"):
        from trader_off.scheduler.cli import load_scheduler_config

        load_scheduler_config(config_path)


@pytest.mark.unit
def test_ac_fr2700_03_config_empty_cron_section(tmp_path: Path):
    """AC-FR2700-03: empty 'cron' dict also raises ConfigValidationError."""
    config_content = {"cron": {}}
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.utils.exceptions import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="cron is required"):
        from trader_off.scheduler.cli import load_scheduler_config

        load_scheduler_config(config_path)


# ---------------------------------------------------------------------------
# AC-FR2700-04: invalid cron expression → ConfigValidationError
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2700_04_invalid_cron_expression(tmp_path: Path):
    """AC-FR2700-04: invalid cron expression raises ConfigValidationError."""
    config_content = {
        "cron": {
            "full_retrain_cron": "invalid cron",
            "incremental_retrain_cron": "0 16 * * 1-5",
            "full_retrain_frequency_days": 5,
            "drift_check_cron": "0 9 * * 1-5",
        },
    }
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.utils.exceptions import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="cron"):
        from trader_off.scheduler.cli import load_scheduler_config

        load_scheduler_config(config_path)


@pytest.mark.unit
def test_ac_fr2700_04_invalid_drift_cron(tmp_path: Path):
    """AC-FR2700-04: invalid drift_check_cron raises ConfigValidationError."""
    config_content = {
        "cron": {
            "full_retrain_cron": "0 16 * * 1-5",
            "incremental_retrain_cron": "0 16 * * 1-5",
            "full_retrain_frequency_days": 5,
            "drift_check_cron": "not a cron",
        },
    }
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.utils.exceptions import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="cron"):
        from trader_off.scheduler.cli import load_scheduler_config

        load_scheduler_config(config_path)


# ---------------------------------------------------------------------------
# Config loading — precedence: CLI args > YAML > defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_scheduler_config_precedence_cli_over_yaml(tmp_path: Path):
    """CLI args override YAML values."""
    config_content = {
        "cron": {
            "full_retrain_cron": "0 16 * * 1-5",
            "incremental_retrain_cron": "0 16 * * 1-5",
            "full_retrain_frequency_days": 5,
            "drift_check_cron": "0 9 * * 1-5",
        },
        "tick_interval_sec": 5.0,
        "max_concurrent_tasks": 3,
    }
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.scheduler.cli import load_scheduler_config

    config = load_scheduler_config(
        config_path,
        cli_overrides={"tick_interval_sec": 1.0, "max_concurrent_tasks": 1},
    )
    # CLI override takes precedence
    assert config.tick_interval_sec == 1.0
    assert config.max_concurrent_tasks == 1


@pytest.mark.unit
def test_load_scheduler_config_yaml_fallback_to_defaults(tmp_path: Path):
    """Missing YAML fields fall back to SchedulerConfig defaults."""
    config_content = _minimal_scheduler_yaml()
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.scheduler.cli import load_scheduler_config

    config = load_scheduler_config(config_path)
    # SchedulerConfig defaults
    assert config.tick_interval_sec == 1.0
    assert config.max_concurrent_tasks == 1
    assert config.ic_floor == 0.005
    assert config.keep_latest_n == 10


@pytest.mark.unit
def test_load_scheduler_config_yaml_overrides_defaults(tmp_path: Path):
    """YAML values override defaults when no CLI args given."""
    config_content = {
        "cron": {
            "full_retrain_cron": "0 16 * * 1-5",
            "incremental_retrain_cron": "0 16 * * 1-5",
            "full_retrain_frequency_days": 5,
            "drift_check_cron": "0 9 * * 1-5",
        },
        "tick_interval_sec": 3.0,
        "ic_floor": 0.01,
        "keep_latest_n": 5,
    }
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.scheduler.cli import load_scheduler_config

    config = load_scheduler_config(config_path)
    assert config.tick_interval_sec == 3.0
    assert config.ic_floor == 0.01
    assert config.keep_latest_n == 5
    # Unspecified fields remain at default
    assert config.max_concurrent_tasks == 1


@pytest.mark.unit
def test_load_scheduler_config_valid_full_config(tmp_path: Path):
    """A complete YAML config loads without errors."""
    config_content = {
        "cron": {
            "full_retrain_cron": "0 16 * * 1-5",
            "incremental_retrain_cron": "45 17 * * 1-5",
            "full_retrain_frequency_days": 10,
            "drift_check_cron": "0 10 * * 1-5",
        },
        "tick_interval_sec": 2.0,
        "max_concurrent_tasks": 1,
        "trading_calendar": "exchange_calendar",
        "psi_threshold": 0.3,
        "ks_pvalue_threshold": 0.01,
        "psi_strong": 0.6,
        "min_drift_features_incremental": 3,
        "min_drift_features_full": 2,
        "ic_floor": 0.01,
        "ic_drop_ratio": 0.5,
        "ic_window": 30,
        "keep_latest_n": 5,
        "keep_pinned_versions": ["v0.2.0.1"],
        "keep_full_retrain_only": False,
        "model_load_mode": "hot-reload",
        "run_api": True,
        "api_host": "0.0.0.0",
        "api_port": 9876,
        "state_dir": "/tmp/state",
        "models_dir": "/tmp/models",
        "reports_dir": "/tmp/reports",
    }
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.scheduler.cli import load_scheduler_config

    config = load_scheduler_config(config_path)
    assert config.tick_interval_sec == 2.0
    assert config.max_concurrent_tasks == 1
    assert config.trading_calendar == "exchange_calendar"
    assert config.psi_threshold == 0.3
    assert config.ks_pvalue_threshold == 0.01
    assert config.psi_strong == 0.6
    assert config.min_drift_features_incremental == 3
    assert config.min_drift_features_full == 2
    assert config.ic_floor == 0.01
    assert config.ic_drop_ratio == 0.5
    assert config.ic_window == 30
    assert config.keep_latest_n == 5
    assert config.keep_pinned_versions == ["v0.2.0.1"]
    assert config.keep_full_retrain_only is False
    assert config.model_load_mode == "hot-reload"
    assert config.run_api is True
    assert config.api_host == "0.0.0.0"
    assert config.api_port == 9876
    assert str(config.state_dir) == "/tmp/state"
    assert str(config.models_dir) == "/tmp/models"
    assert str(config.reports_dir) == "/tmp/reports"


@pytest.mark.unit
def test_load_scheduler_config_file_not_found(tmp_path: Path):
    """Non-existent config file raises ConfigValidationError."""
    config_path = tmp_path / "nonexistent.yaml"

    from trader_off.utils.exceptions import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="config file not found"):
        from trader_off.scheduler.cli import load_scheduler_config

        load_scheduler_config(config_path)


# ---------------------------------------------------------------------------
# validate_cron_expr utility function
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_cron_expr_valid():
    """validate_cron_expr accepts standard cron expressions."""
    from trader_off.scheduler.cli import validate_cron_expr

    # Should not raise
    validate_cron_expr("0 16 * * 1-5")
    validate_cron_expr("*/5 * * * *")
    validate_cron_expr("0 0 1 1 0")
    validate_cron_expr("30 9 * * 1,3,5")


@pytest.mark.unit
def test_validate_cron_expr_invalid():
    """validate_cron_expr raises ConfigValidationError for bad cron."""
    from trader_off.scheduler.cli import validate_cron_expr
    from trader_off.utils.exceptions import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="invalid cron"):
        validate_cron_expr("not valid cron at all")


@pytest.mark.unit
def test_validate_cron_expr_empty_string():
    """validate_cron_expr raises for empty string."""
    from trader_off.scheduler.cli import validate_cron_expr
    from trader_off.utils.exceptions import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="invalid cron"):
        validate_cron_expr("")


# ---------------------------------------------------------------------------
# AC-FR2700-01: scheduler start CLI
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr2700_01_start_with_config(tmp_path: Path):
    """AC-FR2700-01: 'scheduler start --config' exits 0 and prints 'Scheduler started'."""
    config_content = _minimal_scheduler_yaml()
    config_path = _write_yaml(tmp_path, "scheduler.yaml", config_content)

    from trader_off.scheduler.cli import run_scheduler_start

    config = SchedulerConfig()
    captured_stdout = StringIO()

    # The start function should accept a config and a mock-flag so the test
    # doesn't actually block on the infinite loop.
    exit_code = await run_scheduler_start(
        config=config,
        config_path=config_path,
        stdout=captured_stdout,
        run_loop=False,
    )

    assert exit_code == 0
    output = captured_stdout.getvalue()
    assert "Scheduler started" in output


@pytest.mark.unit
def test_build_scheduler_parser_start_subcommand():
    """scheduler start subcommand parses --config correctly."""
    from trader_off.scheduler.cli import build_scheduler_parser

    parser = build_scheduler_parser()
    args = parser.parse_args(["start", "--config", "configs/scheduler.yaml"])
    assert args.subcommand == "start"
    assert args.config == "configs/scheduler.yaml"


@pytest.mark.unit
def test_build_scheduler_parser_start_requires_config():
    """scheduler start requires --config."""
    from trader_off.scheduler.cli import build_scheduler_parser

    parser = build_scheduler_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["start"])


# ---------------------------------------------------------------------------
# AC-FR2700-02: scheduler status CLI
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ac_fr2700_02_status_not_running():
    """AC-FR2700-02: status shows running=False when scheduler is stopped."""
    from trader_off.scheduler.cli import run_scheduler_status

    config = SchedulerConfig()
    # Create a scheduler (stopped state) so we can query status
    from trader_off.scheduler.core import RetrainScheduler

    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    captured_stdout = StringIO()
    exit_code = await run_scheduler_status(
        scheduler=scheduler,
        stdout=captured_stdout,
    )

    assert exit_code == 0
    output = captured_stdout.getvalue()
    assert "running=False" in output


@pytest.mark.unit
async def test_ac_fr2700_02_status_when_running():
    """AC-FR2700-02: status shows running=True when scheduler is started."""
    from datetime import UTC, datetime

    from trader_off.scheduler.cli import run_scheduler_status
    from trader_off.scheduler.core import RetrainScheduler
    from trader_off.scheduler.ports import VirtualClockPort

    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    # Start scheduler briefly
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        exit_code = await run_scheduler_status(
            scheduler=scheduler,
            stdout=captured_stdout,
        )
    finally:
        await scheduler.stop()
        await start_task

    assert exit_code == 0
    output = captured_stdout.getvalue()
    assert "running=True" in output


@pytest.mark.unit
def test_build_scheduler_parser_status_subcommand():
    """scheduler status subcommand parses without arguments."""
    from trader_off.scheduler.cli import build_scheduler_parser

    parser = build_scheduler_parser()
    args = parser.parse_args(["status"])
    assert args.subcommand == "status"


# ---------------------------------------------------------------------------
# scheduler stop CLI
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_run_scheduler_stop_exit_code():
    """scheduler stop exits 0 when stop is called."""
    from datetime import UTC, datetime

    from trader_off.scheduler.cli import run_scheduler_stop
    from trader_off.scheduler.core import RetrainScheduler
    from trader_off.scheduler.ports import VirtualClockPort

    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
    )
    scheduler = RetrainScheduler(
        config=config,
        model_registry=MagicMock(),
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=MagicMock(),
    )

    # Start scheduler so we can stop it
    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    captured_stdout = StringIO()
    try:
        exit_code = await run_scheduler_stop(
            scheduler=scheduler,
            stdout=captured_stdout,
        )
    finally:
        await start_task

    assert exit_code == 0
    output = captured_stdout.getvalue()
    assert "Scheduler stopped" in output


@pytest.mark.unit
def test_build_scheduler_parser_stop_subcommand():
    """scheduler stop subcommand parses without arguments."""
    from trader_off.scheduler.cli import build_scheduler_parser

    parser = build_scheduler_parser()
    args = parser.parse_args(["stop"])
    assert args.subcommand == "stop"


# ---------------------------------------------------------------------------
# scheduler parser edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_scheduler_parser_requires_subcommand():
    """scheduler parser requires a subcommand."""
    from trader_off.scheduler.cli import build_scheduler_parser

    parser = build_scheduler_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


@pytest.mark.unit
def test_build_scheduler_parser_invalid_subcommand():
    """scheduler parser rejects unknown subcommands."""
    from trader_off.scheduler.cli import build_scheduler_parser

    parser = build_scheduler_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


@pytest.mark.unit
def test_scheduler_use_default_config():
    """_build_config_from_dict with minimal cron section returns default SchedulerConfig."""
    from trader_off.scheduler.cli import _build_config_from_dict
    from trader_off.scheduler.core import SchedulerConfig

    config = _build_config_from_dict(
        {
            "cron": {
                "full_retrain_cron": "0 16 * * 1-5",
                "incremental_retrain_cron": "0 16 * * 1-5",
                "full_retrain_frequency_days": 5,
                "drift_check_cron": "0 9 * * 1-5",
            },
        },
        cli_overrides={},
    )
    assert isinstance(config, SchedulerConfig)
    assert config.tick_interval_sec == 1.0
