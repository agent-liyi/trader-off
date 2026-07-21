#!/usr/bin/env python3
"""Convert trader-off OHLCV fixture parquet to quantide DailyBarsStore format.

FR-0300: Produces year-partitioned parquet files under tests/fixtures/v0.3.0/daily_bars_store/
with flat columns: date, asset, open, high, low, close, volume, adj_factor.

Usage:
    python scripts/convert_fixture_to_quantide.py [--fixture all|ohlcv_50x252|ohlcv_10x60]
    python scripts/convert_fixture_to_quantide.py --input <path> [--output-root <path>]
"""

import argparse
import shutil
import sys
from pathlib import Path

import polars as pl
from loguru import logger

REQUIRED_COLUMNS = {"date", "asset", "open", "high", "low", "close", "volume", "adj_factor"}
OUTPUT_COLUMNS = ["date", "asset", "open", "high", "low", "close", "volume", "adj_factor"]
EXCLUDED_COLUMNS = {"turnover", "limit_up", "limit_down"}

DEFAULT_OUTPUT_ROOT = "tests/fixtures/v0.3.0"
FIXTURES_V020 = Path("tests/fixtures/v0.2.0")
FIXTURES_E2E = Path("tests/e2e/fixtures")


def validate_schema(df: pl.DataFrame) -> None:
    """Validate that the input DataFrame has all required OHLCV columns.

    Raises:
        SystemExit(3): If schema is invalid.
    """
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        sys.stderr.write(f"schema mismatch: missing columns {sorted(missing)}\n")
        sys.exit(3)


def convert_parquet(input_path: Path, output_root: Path) -> None:
    """Convert a single OHLCV parquet file to year-partitioned DailyBarsStore format.

    Args:
        input_path: Path to input OHLCV parquet.
        output_root: Root directory for output (daily_bars_store/ created inside).
    """
    if not input_path.exists():
        sys.stderr.write(f"input file not found: {input_path}\n")
        sys.exit(2)

    df = pl.read_parquet(input_path)
    validate_schema(df)

    # Select and rename columns for quantide format
    out = df.select(OUTPUT_COLUMNS)

    store_path = output_root / "daily_bars_store"

    # Idempotent: clear existing output directory
    if store_path.exists():
        shutil.rmtree(store_path)
    store_path.mkdir(parents=True, exist_ok=True)

    # Partition by year
    years = out["date"].dt.year().unique().sort().to_list()

    for year in years:
        year_df = out.filter(pl.col("date").dt.year() == year)
        partition_dir = store_path / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        year_df.write_parquet(
            partition_dir / "part-0.parquet",
            compression="lz4",
        )

    n_rows = len(out)
    n_assets = out["asset"].n_unique()
    logger.info(
        f"Converted {n_rows} rows × {n_assets} assets "
        f"from {input_path} to {store_path} "
        f"(year-partitioned, {len(years)} partitions)"
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert OHLCV fixture to quantide DailyBarsStore format"
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Single input parquet file path",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(DEFAULT_OUTPUT_ROOT),
        help="Root directory for output (default: tests/fixtures/v0.3.0)",
    )
    parser.add_argument(
        "--source-version",
        choices=["v0.2.0", "v0.3.0"],
        default="v0.2.0",
        help="Source fixture version (default: v0.2.0)",
    )
    parser.add_argument(
        "--fixture",
        choices=["ohlcv_50x252", "ohlcv_10x60", "all"],
        default="all",
        help="Fixture to convert (default: all)",
    )

    args = parser.parse_args()

    if args.input:
        convert_parquet(args.input, args.output_root)
        return

    fixtures_to_convert: list[Path] = []
    if args.fixture in ("ohlcv_50x252", "all"):
        fixtures_to_convert.append(FIXTURES_V020 / "ohlcv_50x252.parquet")
    if args.fixture in ("ohlcv_10x60", "all"):
        fixtures_to_convert.append(FIXTURES_E2E / "ohlcv_10x60.parquet")

    for fixture_path in fixtures_to_convert:
        if not fixture_path.exists():
            sys.stderr.write(f"input file not found: {fixture_path}\n")
            sys.exit(2)
        convert_parquet(fixture_path, args.output_root)


if __name__ == "__main__":
    main()
