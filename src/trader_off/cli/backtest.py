"""CLI entry point for backtest (FR-0600, FR-0100).

Exit codes:
    0: Success
    2: Missing required arg (argparse)
    4: Config file validation failure (pydantic / file not found)
    5: Backtest engine failure (quantide exception)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from loguru import logger

from trader_off.backtest.runner import run_backtest
from trader_off.cli._json_output import _json_wrap

_ERROR_MESSAGES: dict[int, str] = {
    2: "CLI argument error",
    4: "Configuration error",
    5: "Execution failure",
}


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for trader-off backtest."""
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--model", required=True, help="Model version")
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, required=True, help="Initial capital")
    parser.add_argument("--config", type=Path, default=None, help="Config YAML path")
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output JSON to stdout (suppresses normal output)",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    """Execute the backtest logic and return an exit code.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code: 0 success, 4 config error, 5 engine failure.
    """
    # Exit code 4: Config file validation
    config_dict = None
    if args.config:
        if not args.config.exists():
            logger.error(f"Config file not found: {args.config}")
            return 4
        try:
            with open(args.config) as f:
                config_dict = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            logger.error(f"Config validation failed: {e}")
            return 4

    # Exit code 0: Success / Exit code 5: Engine failure
    try:
        run_backtest(
            model_version=args.model,
            strategy_name=args.strategy,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            capital=args.capital,
            config=config_dict,
        )
        logger.info("Backtest finished")
        return 0
    except RuntimeError as e:
        logger.error(f"Backtest engine failed: {e}")
        return 5
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return 5


def main() -> int:
    """CLI entry for 'trader-off backtest' command.

    Returns:
        Exit code (see module docstring for mapping).
    """
    parser = _build_parser()
    args = parser.parse_args()

    if args.json:
        return _json_wrap(lambda: _run(args), error_messages=_ERROR_MESSAGES)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
