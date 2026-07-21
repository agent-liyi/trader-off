"""CLI entry point for backtest (FR-0600).

Exit codes:
    0: Success
    2: Missing required arg (argparse)
    4: Config file validation failure (pydantic / file not found)
    5: Backtest engine failure (quantide exception)
"""

import sys
from datetime import date
from pathlib import Path

import yaml  # type: ignore[import-untyped]
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


if __name__ == "__main__":
    sys.exit(main())
