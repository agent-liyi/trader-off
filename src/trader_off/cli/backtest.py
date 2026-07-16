"""CLI entry point for backtest (part of FR-1100)."""

import sys
from datetime import date
from pathlib import Path

from loguru import logger

from trader_off.backtest.runner import run_backtest


def main():
    """CLI entry for 'trader-off backtest' command."""
    import argparse

    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--model", required=True, help="Model version")
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, required=True, help="Initial capital")
    parser.add_argument("--config", type=Path, default=None, help="Config YAML path")

    args = parser.parse_args()

    try:
        run_backtest(
            model_version=args.model,
            strategy_name=args.strategy,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            capital=args.capital,
        )
        logger.info("Backtest finished")
        return 0
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
