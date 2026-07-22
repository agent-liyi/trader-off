"""CLI entry point for sync-data (FR-0100).

Downloads OHLCV data from Tushare via QuantideDataLoader and writes to
DailyBarsStore (year-partitioned parquet) plus a trading calendar.

Exit codes:
    0: Success (all assets synced, or dry-run completed)
    2: Argparse error (missing/invalid args)
    4: Config error (missing token, bad universe, date validation failure)
    5: Partial failure (>=1 asset failed but others succeeded)

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from loguru import logger


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off sync-data' command.

    Args:
        argv: Command-line arguments. If None, reads from sys.argv[1:].

    Returns:
        Exit code: 0 success, 2 argparse error, 4 config error, 5 partial failure.
    """
    # --- Argparse (exit code 2) ---
    # Let argparse propagate SystemExit(2) naturally on errors
    parser = _build_argparser()
    args = parser.parse_args(argv)

    # --- Token gate (exit code 4) ---
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        logger.error(
            "TUSHARE_TOKEN environment variable is required; set it before running sync-data"
        )
        return 4

    # --- Universe load (exit code 4) ---
    universe_path = Path(args.universe)
    if not universe_path.exists():
        logger.error(f"Universe file not found: {universe_path}")
        return 4

    try:
        assets = _load_universe(universe_path)
    except Exception as e:
        logger.error(f"Failed to read universe file {universe_path}: {e}")
        return 4

    if not assets:
        logger.error(f"No assets found in universe file: {universe_path}")
        return 4

    # --- Date validation (exit code 4) ---
    start = args.start
    end = args.end
    if start > end:
        logger.error(f"start date ({start}) must be on or before end date ({end})")
        return 4

    # --- Dry-run: print plan, no IO (exit code 0) ---
    store_path = Path(args.store_path)
    if args.dry_run:
        for asset in assets:
            year = start.year
            logger.info(
                f"[dry-run] asset={asset} start={start} end={end} → {store_path}/year={year}/..."
            )
        return 0

    # --- Full sync ---
    return asyncio.run(_sync(assets, start, end, store_path, token))


# ---------------------------------------------------------------------------
# Argparser builder
# ---------------------------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for sync-data CLI."""
    parser = argparse.ArgumentParser(
        prog="trader-off-sync-data",
        description="Sync A-share OHLCV data from Tushare to DailyBarsStore",
    )
    parser.add_argument(
        "--universe",
        required=True,
        type=str,
        help="Path to CSV/parquet file with an 'asset' column",
    )
    parser.add_argument(
        "--start",
        required=True,
        type=_parse_date,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        type=_parse_date,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--store-path",
        type=str,
        default=".quantide/bars/",
        help="Root directory for DailyBarsStore output (default: .quantide/bars/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print sync plan without making network requests or writing files",
    )
    return parser


def _parse_date(date_str: str) -> date:
    """Parse ISO date string for argparse type conversion.

    Raises argparse.ArgumentTypeError on invalid format.
    """
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{date_str}': expected YYYY-MM-DD format")


# ---------------------------------------------------------------------------
# Universe loading
# ---------------------------------------------------------------------------


def _load_universe(path: Path) -> list[str]:
    """Load asset list from a CSV or parquet file.

    The file must contain an 'asset' column. Returns a deduplicated list
    of asset codes.

    Args:
        path: Path to CSV (.csv) or parquet (.parquet) file.

    Returns:
        List of asset code strings.

    Raises:
        ValueError: If the file has no 'asset' column.
        OSError: If the file cannot be read.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pl.read_csv(path)
    elif suffix in (".parquet", ".parq"):
        df = pl.read_parquet(path)
    else:
        # Try CSV first as default
        df = pl.read_csv(path)

    if "asset" not in df.columns:
        raise ValueError(f"Universe file must contain an 'asset' column; got: {df.columns}")

    assets: list[str] = df["asset"].unique().to_list()
    return assets


# ---------------------------------------------------------------------------
# Sync orchestration
# ---------------------------------------------------------------------------


async def _sync(
    assets: list[str],
    start: date,
    end: date,
    store_path: Path,
    token: str,
) -> int:
    """Orchestrate calendar + OHLCV sync for all assets.

    Args:
        assets: List of asset codes.
        start: Start date for the sync window.
        end: End date for the sync window.
        store_path: Root directory for OHLCV output.
        token: Tushare API token.

    Returns:
        Exit code: 0 if all succeed, 5 if any fail.
    """
    # NFR-0100: Lazy function-scope quantide imports
    from quantide.data.fetchers.tushare import fetch_calendar

    # --- Calendar: fetch and write ---
    cal_df = fetch_calendar(start - timedelta(days=30))
    _write_calendar(cal_df)

    # --- Compute count (trading days in range) ---
    trading_count = _compute_trading_count(cal_df, start, end)

    # --- OHLCV: per asset ---
    # NFR-0100: Lazy import of project-internal module (not quantide)
    from trader_off.data.quantide_adapter import QuantideDataLoader

    loader = QuantideDataLoader(token=token)
    failed_count = 0

    for asset in assets:
        try:
            df = await loader.get_daily(asset, end_date=end, count=trading_count)
            if df.height == 0:
                logger.warning(f"Empty result for {asset} — treating as failure")
                failed_count += 1
                continue
            # Filter to user-requested window
            df = df.filter(pl.col("date") >= start)
            # Write year-partitioned parquet
            store_path.mkdir(parents=True, exist_ok=True)
            df.write_parquet(
                str(store_path),
                partition_by=pl.col("date").dt.year(),
            )
        except Exception:
            logger.exception(f"Failed to sync {asset}")
            failed_count += 1

    if failed_count > 0:
        logger.warning(f"Sync completed with {failed_count}/{len(assets)} asset(s) failed")
        return 5

    return 0


def _write_calendar(cal_df) -> None:
    """Write trading calendar DataFrame to .quantide/calendar/calendar.parquet.

    Uses the quantide calendar singleton's save method.

    Args:
        cal_df: pandas DataFrame from fetch_calendar with 'is_open' and 'prev' columns.
    """
    from quantide.data.models.calendar import calendar

    calendar_dir = Path(".quantide/calendar")
    calendar_dir.mkdir(parents=True, exist_ok=True)
    calendar._path = calendar_dir / "calendar.parquet"
    calendar.save(cal_df)


def _compute_trading_count(cal_df, start: date, end: date) -> int:
    """Count trading days between start and end (inclusive) from calendar.

    Args:
        cal_df: pandas DataFrame from fetch_calendar with 'is_open' column
                and DatetimeIndex.
        start: Start date.
        end: End date.

    Returns:
        Number of open trading days in the range. Falls back to
        (end - start).days * 1.5 if no trading days found.
    """
    import pandas as pd

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    open_mask = cal_df["is_open"] == 1
    in_range = (cal_df.index >= start_ts) & (cal_df.index <= end_ts)
    trading_count = int(open_mask[in_range].sum())
    if trading_count == 0:
        # Fallback: use calendar days * 1.5 as upper bound
        trading_count = int((end - start).days * 1.5) or 1
    return trading_count


if __name__ == "__main__":
    sys.exit(main())
