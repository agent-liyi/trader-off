"""Integration tests for per-module log file outputs (NFR-0600 AC-3).

Covers AC-NFR0600-03: when factor_mining, scheduler, and portfolio modules
each run, log files are written under logs/ (one log file per module).

Per test-plan §8.2, interfaces.md §2.9 (persistent file contract).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from trader_off.utils.logging import setup_logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_log_files(log_dir: Path, module: str) -> list[Path]:
    """Find log files for a given module name in log_dir.

    Log files follow pattern: {module}_YYYY-MM-DD.log (per logging.py).
    """
    pattern = re.compile(rf"^{re.escape(module)}_\d{{4}}-\d{{2}}-\d{{2}}\.log$")
    return sorted([p for p in log_dir.glob(f"{module}_*.log") if pattern.match(p.name)])


# ---------------------------------------------------------------------------
# AC-NFR0600-03: Three modules each produce a log file
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_nfr0600_03_log_file_written_per_module(tmp_path):
    """AC-NFR0600-03: Calling setup_logger for each of the three modules
    creates a distinct log file under the configured log directory, and
    each log file contains logged content."""
    log_dir = tmp_path / "logs"
    modules = ["factor_mining", "scheduler", "portfolio"]

    mod_files: dict[str, Path] = {}

    for mod in modules:
        setup_logger(module=mod, log_dir=log_dir, format="text")
        found = _find_log_files(log_dir, mod)
        assert len(found) == 1, (
            f"Expected 1 log file for module '{mod}', found {len(found)}: {found}"
        )
        mod_files[mod] = found[0]

    # Verify each file is distinct (different paths)
    paths = set(str(p) for p in mod_files.values())
    assert len(paths) == 3, f"Expected 3 distinct log files, got {len(paths)}: {paths}"

    # Verify each log file has content (logger.info is called in setup_logger)
    for mod, fpath in mod_files.items():
        content = fpath.read_text()
        assert len(content) > 0, f"Log file for '{mod}' is empty: {fpath}"
        assert "Logger initialized for module" in content, (
            f"Log file for '{mod}' missing initialization message. Content: {content[:200]}"
        )
        assert mod in content, (
            f"Log file for '{mod}' does not reference module name. Content: {content[:200]}"
        )


@pytest.mark.integration
def test_ac_nfr0600_03_log_files_have_expected_format(tmp_path):
    """AC-NFR0600-03: Log files contain entries in the expected structured
    format: {time} | {level} | {name}:{function}:{line} | {message}."""
    log_dir = tmp_path / "logs"

    setup_logger(module="test_mod", log_dir=log_dir, format="text")
    found = _find_log_files(log_dir, "test_mod")
    assert len(found) == 1

    content = found[0].read_text()
    lines = [line for line in content.strip().split("\n") if line]

    # Each log line should match the pattern:
    # YYYY-MM-DD HH:MM:SS | LEVEL | module:function:line | message
    log_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| "
        r"(DEBUG|INFO|WARNING|ERROR|CRITICAL) \| "
        r"[\w.]+:[\w.]+:\d+ \| "
        r".+$"
    )

    for line in lines:
        assert log_pattern.match(line), (
            f"Log line does not match expected structured format:\n  {line[:120]}"
        )


@pytest.mark.integration
def test_ac_nfr0600_03_log_dir_auto_created(tmp_path):
    """AC-NFR0600-03: When log_dir does not exist, setup_logger
    creates it automatically and writes log files successfully."""
    log_dir = tmp_path / "nonexistent" / "logs" / "subdir"

    assert not log_dir.exists(), "Precondition: log_dir should not exist yet"

    setup_logger(module="auto_create", log_dir=log_dir, format="text")

    assert log_dir.exists(), f"setup_logger should have created {log_dir}"
    found = _find_log_files(log_dir, "auto_create")
    assert len(found) == 1, f"No log file created in auto-created dir {log_dir}"


@pytest.mark.integration
def test_ac_nfr0600_03_json_format_log_written(tmp_path):
    """AC-NFR0600-03: When format='json', log files contain valid JSON
    lines with standard loguru record fields."""
    log_dir = tmp_path / "logs"

    setup_logger(module="json_test", log_dir=log_dir, format="json")
    found = _find_log_files(log_dir, "json_test")
    assert len(found) == 1

    content = found[0].read_text().strip()
    lines = [line for line in content.split("\n") if line]

    import json

    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            raise AssertionError(f"Log line is not valid JSON:\n  {line[:120]}\n  Error: {e}")
        # Standard loguru serialized fields
        for key in ("text", "record"):
            assert key in record, f"JSON log record missing required field '{key}': {record}"


@pytest.mark.integration
def test_ac_nfr0600_03_setup_logger_raises_on_invalid_format(tmp_path):
    """AC-NFR0600-03: Passing an unsupported format to setup_logger
    raises ValueError (validates config)."""
    log_dir = tmp_path / "logs"

    with pytest.raises(ValueError, match="format must be 'text' or 'json'"):
        setup_logger(module="bad_fmt", log_dir=log_dir, format="xml")


@pytest.mark.integration
def test_ac_nfr0600_03_multiple_calls_different_modules(tmp_path):
    """AC-NFR0600-03: Calling setup_logger multiple times with different
    module names creates distinct log files without interference."""
    log_dir = tmp_path / "logs"

    modules = ["factor_mining", "scheduler", "portfolio"]
    for mod in modules:
        setup_logger(module=mod, log_dir=log_dir, format="text")

    # Each module should have exactly one log file
    for mod in modules:
        found = _find_log_files(log_dir, mod)
        assert len(found) == 1, f"Module '{mod}' should have exactly 1 log file, found {len(found)}"

    # Module-specific logging goes to the right file
    from loguru import logger

    for mod in modules:
        setup_logger(module=mod, log_dir=log_dir, format="text")
        logger.info(f"test message for {mod}")
        found = _find_log_files(log_dir, mod)
        content = found[0].read_text()
        assert f"test message for {mod}" in content.replace("\n", " "), (
            f"Log file for {mod} missing test message"
        )
