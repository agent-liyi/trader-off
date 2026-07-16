"""Walk-forward data splitting (FR-0600).

Splits time-series data into rolling train/valid/test periods by year.
- Train: past train_window_years (e.g. year-3 to year-1)
- Valid: first half of the target year (H1)
- Test: second half of the target year (H2)
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl
from loguru import logger


@dataclass
class WalkForwardSplit:
    """A single walk-forward split period.

    Attributes:
        year: The target year for this split.
        train_path: Path to training data parquet.
        valid_path: Path to validation data parquet.
        test_path: Path to test data parquet.
    """

    year: int
    train_path: Path
    valid_path: Path
    test_path: Path


def prepare_walk_forward_splits(
    data: pl.DataFrame,
    start_year: int,
    end_year: int,
    train_window_years: int = 3,
    output_dir: Path | str | None = None,
) -> list[WalkForwardSplit]:
    """Generate rolling walk-forward train/valid/test splits.

    For each year Y in [start_year, end_year]:
    - Train: data from Y-train_window_years to Y-1 (inclusive)
    - Valid: Y-01-01 to Y-06-30
    - Test:  Y-07-01 to Y-12-31

    Args:
        data: OHLCV DataFrame with at minimum an asset and date column.
        start_year: First year to generate splits for.
        end_year: Last year to generate splits for (inclusive).
        train_window_years: Number of past years used for training.
        output_dir: Directory to write parquet files. If None, uses
            current directory.

    Returns:
        List of WalkForwardSplit objects, one per year.
    """
    if output_dir is None:
        output_dir = Path(".")
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    splits: list[WalkForwardSplit] = []

    for year in range(start_year, end_year + 1):
        train_start = date(year - train_window_years, 1, 1)
        train_end = date(year - 1, 12, 31)
        valid_start = date(year, 1, 1)
        valid_end = date(year, 6, 30)
        test_start = date(year, 7, 1)
        test_end = date(year, 12, 31)

        # Filter data for each period
        train_df = data.filter(
            (pl.col("date") >= train_start) & (pl.col("date") <= train_end)
        )
        valid_df = data.filter(
            (pl.col("date") >= valid_start) & (pl.col("date") <= valid_end)
        )
        test_df = data.filter(
            (pl.col("date") >= test_start) & (pl.col("date") <= test_end)
        )

        # Handle partial years
        if len(test_df) == 0:
            logger.warning(
                f"No test data for year {year} (data may end before H2). "
                f"Writing empty test parquet."
            )

        # Write parquet files
        train_path = output_dir / f"train_{year}.parquet"
        valid_path = output_dir / f"valid_{year}.parquet"
        test_path = output_dir / f"test_{year}.parquet"

        train_df.write_parquet(train_path)
        valid_df.write_parquet(valid_path)
        test_df.write_parquet(test_path)

        logger.info(
            f"Year {year}: train={len(train_df)} rows, "
            f"valid={len(valid_df)} rows, test={len(test_df)} rows"
        )

        splits.append(WalkForwardSplit(
            year=year,
            train_path=train_path,
            valid_path=valid_path,
            test_path=test_path,
        ))

    return splits
