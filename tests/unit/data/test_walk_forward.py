"""Tests for walk-forward data splitting (FR-0600)."""

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from trader_off.data.walk_forward import (
    WalkForwardSplit,
    prepare_walk_forward_splits,
)


def make_full_data(
    start_date: date,
    end_date: date,
    assets: list[str] | None = None,
) -> pl.DataFrame:
    """Create full OHLCV data from start_date to end_date.

    Args:
        start_date: First trading day.
        end_date: Last trading day.
        assets: List of asset codes. Defaults to 5 assets.

    Returns:
        DataFrame with asset, date, close columns.
    """
    if assets is None:
        assets = ["A", "B", "C", "D", "E"]

    # Generate all trading days (approximate: all weekdays)
    days: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # Mon-Fri
            days.append(current)
        current += timedelta(days=1)

    data = []
    for asset in assets:
        for i, d in enumerate(days):
            data.append({
                "asset": asset,
                "date": d,
                "open": 10.0 + i * 0.1,
                "high": 12.0 + i * 0.1,
                "low": 9.0 + i * 0.1,
                "close": 11.0 + i * 0.1,
                "volume": 1_000_000.0,
                "turnover": 0.02,
                "adj_factor": 1.0,
            })

    return pl.DataFrame(data, schema={
        "asset": pl.Utf8,
        "date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "turnover": pl.Float64,
        "adj_factor": pl.Float64,
    })


class TestWalkForwardSplits:
    """Unit tests for prepare_walk_forward_splits."""

    # AC-FR0600-01: 7-period split (2018-2024)
    def test_ac_fr0600_01_seven_splits(self, tmp_path):
        """AC-FR0600-01: 7 periods from 2018-2024, each with train/valid/test parquet.

        train: year-3 to year-1, valid: year H1, test: year H2.
        """
        data = make_full_data(
            start_date=date(2015, 1, 1),
            end_date=date(2024, 12, 31),
        )
        output_dir = tmp_path / "splits"

        splits = prepare_walk_forward_splits(
            data=data,
            start_year=2018,
            end_year=2024,
            train_window_years=3,
            output_dir=output_dir,
        )

        # Should have 7 periods (2018 through 2024)
        assert len(splits) == 7, f"Expected 7 splits, got {len(splits)}"

        years = [s.year for s in splits]
        assert years == list(range(2018, 2025))

        for split in splits:
            # Each split should have train/valid/test files
            assert split.train_path.exists(), f"Missing {split.train_path}"
            assert split.valid_path.exists(), f"Missing {split.valid_path}"
            assert split.test_path.exists(), f"Missing {split.test_path}"

            # Read and verify date ranges
            train_df = pl.read_parquet(split.train_path)
            valid_df = pl.read_parquet(split.valid_path)
            test_df = pl.read_parquet(split.test_path)

            assert len(train_df) > 0, f"Empty train for year {split.year}"
            assert len(valid_df) > 0, f"Empty valid for year {split.year}"
            assert len(test_df) > 0, f"Empty test for year {split.year}"

            # Check date ordering: train.max < valid.min ≤ valid.max < test.min ≤ test.max
            train_max = train_df["date"].max()
            valid_min = valid_df["date"].min()
            valid_max = valid_df["date"].max()
            test_min = test_df["date"].min()
            test_max = test_df["date"].max()

            assert train_max < valid_min, (
                f"Year {split.year}: train_max={train_max} >= valid_min={valid_min}"
            )
            assert valid_max <= test_min, (
                f"Year {split.year}: valid_max={valid_max} > test_min={test_min}"
            )

    # AC-FR0600-02: Partial year (data ends mid-year)
    def test_ac_fr0600_02_partial_year(self, tmp_path):
        """AC-FR0600-02: Data ends mid-2020 → test empty + WARNING, no crash."""
        data = make_full_data(
            start_date=date(2015, 1, 1),
            end_date=date(2020, 6, 30),
        )
        output_dir = tmp_path / "splits"

        splits = prepare_walk_forward_splits(
            data=data,
            start_year=2018,
            end_year=2020,
            train_window_years=3,
            output_dir=output_dir,
        )

        # 2020 split should exist
        split_2020 = splits[-1]
        assert split_2020.year == 2020

        # Valid should have data
        valid_df = pl.read_parquet(split_2020.valid_path)
        assert len(valid_df) > 0

        # Test should be empty (no H2 data)
        test_df = pl.read_parquet(split_2020.test_path)
        assert len(test_df) == 0, "Expected empty test set for partial year"
