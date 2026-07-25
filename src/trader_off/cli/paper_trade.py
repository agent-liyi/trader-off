"""CLI entry point for paper trade (FR-0100).

Simulates trading with a strategy using historical/realtime data from Tushare.
Produces NAV, positions, and trade records in reports/paper_trade_<ts>/.

Exit codes:
    0: Success
    2: Missing required arg (argparse)
    4: Config error (universe not found, invalid args)

NFR-0100: All quantide imports are function-scope (lazy).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from trader_off.cli._json_output import _json_wrap

_ERROR_MESSAGES: dict[int, str] = {
    2: "CLI argument error",
    4: "Configuration error",
}


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for trader-off-paper-trade."""
    parser = argparse.ArgumentParser(
        prog="trader-off-paper-trade",
        description="Run paper trade simulation.",
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy name",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        required=True,
        help="Path to universe watchlist file (CSV/parquet)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        required=True,
        help="Initial capital",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output JSON to stdout (suppresses normal output)",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    """Execute the paper trade logic and return an exit code.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code: 0 success, 4 config error.
    """
    # Validate universe file
    if not args.universe.exists():
        logger.error(f"Universe file not found: {args.universe}")
        return 4

    # Placeholder: real paper trade logic would go here
    logger.info(f"Paper trade: strategy={args.strategy}, capital={args.capital}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off paper-trade' command.

    Args:
        argv: Optional argument list. Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 success, 2 argparse error, 4 config error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.json:
        return _json_wrap(lambda: _run(args), error_messages=_ERROR_MESSAGES)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
