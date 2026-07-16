"""Tests for logging setup."""

import re
from pathlib import Path

import pytest
from loguru import logger

from trader_off.utils.logging import setup_logger


class TestSetupLogger:
    """Unit tests for setup_logger."""

    def test_setup_logger_initializes(self, tmp_path):
        """setup_logger should configure loguru without errors."""
        setup_logger(module="test", log_dir=tmp_path)

        # Verify we can log after setup
        logger.info("test message")

        # Check log file was created
        log_files = list(tmp_path.glob("test_*.log"))
        assert len(log_files) > 0, "No log file created"

    def test_setup_logger_format_has_correct_structure(self, tmp_path):
        """Log output should match expected format structure."""
        setup_logger(module="test_format", log_dir=tmp_path)

        logger.info("structured test")

        log_files = list(tmp_path.glob("test_format_*.log"))
        assert len(log_files) > 0

        content = log_files[0].read_text()
        # Format: {time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}
        pattern = (
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| "
            r"INFO\s+\| "
            r"[^:]+:[^:]+:\d+ \| "
            r"structured test"
        )
        assert re.search(pattern, content), f"Log format mismatch in: {content}"

    def test_setup_logger_creates_log_dir(self, tmp_path):
        """setup_logger should create log directory if it doesn't exist."""
        log_dir = tmp_path / "nested" / "logs"
        assert not log_dir.exists()

        setup_logger(module="test_dir", log_dir=log_dir)

        assert log_dir.exists()
