"""CLI entry point for paper trading (FR-0200).

Exit codes:
    0: Success
    2: Missing required arg (argparse)
    5: Paper trading engine failure (RuntimeError / other exception)
"""

import sys
from datetime import date
from pathlib import Path

import polars as pl
from loguru import logger

from trader_off.backtest.runner import run_paper_trade


def _read_universe_file(path: Path) -> list[str]:
    """Read a universe file (CSV or Parquet) and return asset list.

    Args:
        path: Path to CSV or Parquet file with an 'asset' column.

    Returns:
        List of asset codes.

    Raises:
        ValueError: If the file cannot be read or has no 'asset' column.
    """
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pl.read_parquet(str(path))
    else:
        # Default to CSV
        df = pl.read_csv(str(path), has_header=True)
    if "asset" not in df.columns:
        raise ValueError(f"Universe file {path} has no 'asset' column; columns: {df.columns}")
    return df["asset"].unique().to_list()


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off-paper-trade' command.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).

    Returns:
        Exit code (0=success, 2=argparse error, 5=engine failure).
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run paper trading session")
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy name (e.g., lgbm_top20, optimized_topk)",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date (YYYY-MM-DD), default today",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000,
        help="Initial capital (default: 1_000_000)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: reports/paper_trade_<ts>/)",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=None,
        help="Universe watchlist file (CSV or Parquet with 'asset' column)",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse calls sys.exit(0) for --help, sys.exit(2) for errors
        return e.code if isinstance(e.code, int) else 2

    # Read universe file if provided
    universe: list[str] = []
    if args.universe:
        try:
            universe = _read_universe_file(args.universe)
            logger.info(f"Loaded {len(universe)} assets from {args.universe}")
        except (ValueError, OSError) as e:
            logger.error(f"Failed to read universe file: {e}")
            return 4  # Exit code 4: config file error (mirrors backtest.py)

    # Exit code 5: Paper engine failure
    try:
        result = run_paper_trade(
            strategy_name=args.strategy,
            end_date=date.fromisoformat(args.end),
            initial_cash=args.capital,
            config={"universe": universe},
        )

        # If --output specified, write files there instead of default location
        output_dir = args.output or result.report_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Serialize output files
        import json

        ts = result.report_dir.name.replace("paper_trade_", "")
        result.nav.write_parquet(output_dir / f"nav_{ts}.parquet")
        result.positions.write_parquet(output_dir / f"positions_{ts}.parquet")
        result.trades.write_parquet(output_dir / f"trades_{ts}.parquet")
        (output_dir / "summary.json").write_text(json.dumps(result.summary, indent=2))

        nav_final = result.nav["nav"].tail(1).item() if result.nav.height > 0 else 0.0
        logger.info(
            f"Paper trade report saved to {output_dir}/summary.json; "
            f"total_trades={result.summary.get('total_trades', 0)}, "
            f"final_nav={nav_final:.2f}"
        )
        return 0
    except RuntimeError as e:
        logger.error(f"Paper trading engine failed: {e}")
        return 5
    except Exception as e:
        logger.error(f"Paper trading failed: {e}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
