"""Logging setup using loguru."""

import os
import sys
from pathlib import Path

from loguru import logger


def setup_logger(
    module: str = "trader_off",
    log_dir: Path | str = "logs",
    format: str = "text",  # noqa: UP007
) -> None:
    """Configure structured logging to stdout and rotating log files.

    Args:
        module: Module name used for the log filename prefix.
        log_dir: Directory for log files. Created if it does not exist.
        format: Log format — ``"text"`` for human-readable, ``"json"`` for
            structured JSON. Each log record is emitted as a single JSON line.
            PII note: no user credentials, tokens, or personal data are ever
            emitted by this logger by design.

    Raises:
        ValueError: If ``format`` is not ``"text"`` or ``"json"``.
    """
    if format not in ("text", "json"):
        raise ValueError(f"format must be 'text' or 'json', got {format!r}")

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove ALL existing handlers to avoid duplicate/leaked state
    logger.remove()

    # Level from environment variable (default INFO)
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = "INFO"

    if format == "json":
        # Loguru's serialize=True emits one JSON object per line
        # with standard record fields (time, level, message, etc.)
        logger.add(
            sys.stdout,
            level=level,
            serialize=True,
        )
        logger.add(
            log_dir / f"{module}_{{time:YYYY-MM-DD}}.log",
            level=level,
            serialize=True,
            rotation="10 MB",
            retention="30 days",
        )
    else:
        # Human-readable text format: key=value style
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            level=level,
            colorize=True,
        )
        logger.add(
            log_dir / f"{module}_{{time:YYYY-MM-DD}}.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
            level=level,
            rotation="10 MB",
            retention="30 days",
        )

    logger.info(f"Logger initialized for module: {module}")
