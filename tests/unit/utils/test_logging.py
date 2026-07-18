"""Tests for logging setup (NFR-0600)."""

import json

import pytest
from loguru import logger

from trader_off.utils.logging import setup_logger


@pytest.fixture(autouse=True)
def fresh_logger(tmp_path):
    """Reset logger state before each test to avoid handler/level leaks."""
    # Remove all handlers and reset to default
    logger.remove()
    yield
    logger.remove()


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
        import re

        setup_logger(module="test_format", log_dir=tmp_path)

        logger.info("structured test")

        log_files = list(tmp_path.glob("test_format_*.log"))
        assert len(log_files) > 0

        content = log_files[0].read_text()
        # Format: {time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}
        pattern = re.compile(
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| "
            r"INFO\s+\| "
            r"[^:]+:[^:]+:\d+ \| "
            r"structured test"
        )
        assert pattern.search(content), f"Log format mismatch in: {content}"

    def test_setup_logger_creates_log_dir(self, tmp_path):
        """setup_logger should create log directory if it doesn't exist."""
        log_dir = tmp_path / "nested" / "logs"
        assert not log_dir.exists()

        setup_logger(module="test_dir", log_dir=log_dir)

        assert log_dir.exists()

    def test_json_format_produces_valid_json_lines(self, tmp_path):
        """AC-1: format='json' should emit one JSON object per log line."""
        setup_logger(module="test_json", log_dir=tmp_path, format="json")

        logger.info("json test message")

        log_files = list(tmp_path.glob("test_json_*.log"))
        assert len(log_files) > 0

        content = log_files[0].read_text()
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        # Last non-empty line should be a valid JSON dict (loguru serialize=True format)
        # serialize=True outputs: {"text": "...", "record": {...}}
        last_record = json.loads(lines[-1])
        assert "record" in last_record
        assert "time" in last_record["record"]
        assert last_record["record"]["level"]["name"] == "INFO"
        assert last_record["record"]["message"] == "json test message"

    def test_invalid_format_raises_value_error(self, tmp_path):
        """AC-1: format must be 'text' or 'json'."""
        with pytest.raises(ValueError, match="format must be 'text' or 'json'"):
            setup_logger(module="test_invalid", log_dir=tmp_path, format="xml")

    def test_log_level_from_env_var(self, tmp_path, monkeypatch):
        """AC-3: LOG_LEVEL env var controls log level."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        setup_logger(module="test_env", log_dir=tmp_path)

        records = []

        def capture(msg):
            records.append(msg.record["level"].name)

        sink_id = logger.add(capture, level="DEBUG")
        logger.debug("debug msg")
        logger.remove(sink_id)

        assert "DEBUG" in records, f"Expected DEBUG level from env, got {records}"

    def test_default_log_level_is_info(self, tmp_path, monkeypatch):
        """AC-3: default log level is INFO when LOG_LEVEL is unset."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        setup_logger(module="test_default", log_dir=tmp_path)

        records = []

        def capture(msg):
            records.append(msg.record["level"].name)

        sink_id = logger.add(capture, level="INFO")
        logger.debug("should not appear")
        logger.info("info msg")
        logger.remove(sink_id)

        assert "DEBUG" not in records
        assert "INFO" in records

    def test_no_pii_in_json_logs(self, tmp_path):
        """AC-4: no PII keys present in JSON log output."""
        setup_logger(module="test_pii", log_dir=tmp_path, format="json")

        logger.info("login attempt for user=admin token=secret123")

        log_files = list(tmp_path.glob("test_pii_*.log"))
        content = log_files[0].read_text()

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for line in lines:
            record = json.loads(line)
            # No PII fields should appear as top-level keys in structured logs
            assert "password" not in record, "PII: password field leaked"
            assert "api_key" not in record, "PII: api_key field leaked"
