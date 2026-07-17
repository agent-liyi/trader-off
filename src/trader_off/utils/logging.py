"""Logging setup using loguru."""

import sys
from pathlib import Path
from typing import Union

from loguru import logger


def setup_logger(module: str = "trader_off", log_dir: Union[Path, str] = "logs") -> None:  # noqa: UP007
    """Configure structured logging to stdout and rotating log files.

    Args:
        module: Module name used for the log filename prefix.
        log_dir: Directory for log files. Created if it does not exist.

    Log format: {time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Stdout handler with coloured output
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level="INFO",
        colorize=True,
    )

    # File handler with rotation
    logger.add(
        log_dir / f"{module}_{{time:YYYY-MM-DD}}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="30 days",
    )

    logger.info(f"Logger initialized for module: {module}")
