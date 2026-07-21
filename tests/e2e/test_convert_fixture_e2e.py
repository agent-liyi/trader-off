"""E2E test for FR-0300: convert_fixture_to_quantide script.

Covers:
    AC-FR0300-01: exit code 0, year-partitioned parquet output
    AC-FR0300-02: column schema verification
        (date, asset, open, high, low, close, volume, adj_factor)
    AC-FR0300-03: row count matches input, date range preserved
    AC-FR0300-08: idempotent (re-run produces same output)

Per test-plan §6.5: happy path only. Uses ohlcv_10x60.parquet fixture.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import polars as pl
import pytest

FIXTURES_E2E = Path(__file__).parent / "fixtures"
OHLCV_10X60 = FIXTURES_E2E / "ohlcv_10x60.parquet"
EXPECTED_COLUMNS = {
    "date",
    "asset",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjust",
    "up_limit",
    "down_limit",
}


@pytest.mark.e2e
class TestConvertFixtureE2E:
    """E2E test for FR-0300: fixture conversion to quantide DailyBarsStore."""

    def test_convert_ohlcv_10x60_happy_path(self, tmp_path: Path):
        """AC-FR0300-01, AC-FR0300-02, AC-FR0300-03:
        Convert ohlcv_10x60.parquet → year-partitioned DailyBarsStore.

        Verifies:
          - Exit code 0
          - Year-partitioned parquet files created under daily_bars_store/
          - Columns: date, asset, open, high, low, close, volume, adj_factor
          - Row count matches input (600 = 10 assets × 60 days)
          - Dates are sorted within each partition
          - No NaN in critical numeric columns (open, high, low, close, volume, adj_factor)
        """
        t0 = time.perf_counter()

        output_root = tmp_path / "v0.3.0"
        assert not OHLCV_10X60.exists() or OHLCV_10X60.exists()  # precondition

        # Read source fixture to establish ground truth
        source_df = pl.read_parquet(OHLCV_10X60)
        source_row_count = len(source_df)
        source_assets = source_df["asset"].n_unique()
        source_date_min = source_df["date"].min()
        source_date_max = source_df["date"].max()

        # --- Execute conversion ---
        result = subprocess.run(
            [
                sys.executable,
                "scripts/convert_fixture_to_quantide.py",
                "--fixture",
                "ohlcv_10x60",
                "--output-root",
                str(output_root),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # AC-FR0300-01: exit code 0
        assert result.returncode == 0, (
            f"Convert failed with exit {result.returncode}: stderr={result.stderr}"
        )

        # AC-FR0300-01: daily_bars_store/ created with year-partitioned parquet files
        store_path = output_root / "daily_bars_store"
        assert store_path.exists(), f"daily_bars_store not created at {store_path}"
        assert store_path.is_dir()

        parquet_files = sorted(store_path.rglob("part-0.parquet"))
        assert len(parquet_files) >= 1, f"No part-0.parquet files found in {store_path}"

        # --- Verify each partition ---
        total_rows = 0
        partition_dates: list[pl.DataFrame] = []

        for pq_path in parquet_files:
            # Verify partition_key_year=YYYY directory naming
            parent_name = pq_path.parent.name
            assert parent_name.startswith("partition_key_year="), (
                f"Partition dir '{parent_name}' does not follow 'partition_key_year=YYYY' naming"
            )

            df = pl.read_parquet(pq_path)

            # AC-FR0300-02: column schema
            actual_cols = set(df.columns)
            assert actual_cols == EXPECTED_COLUMNS, (
                f"Column mismatch: expected {sorted(EXPECTED_COLUMNS)}, got {sorted(actual_cols)}"
            )

            # AC-FR0300-02: open, high, low, close, volume, adjust are Float64
            numeric_cols = [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "adjust",
                "up_limit",
                "down_limit",
            ]
            for col in numeric_cols:
                assert df.schema[col] == pl.Float64, (
                    f"Column '{col}' has type {df.schema[col]}, expected Float64"
                )
            # Date column is Date type with no nulls
            assert df.schema["date"] == pl.Date
            assert df["date"].null_count() == 0, f"date column has nulls in {pq_path}"
            assert df.schema["asset"] == pl.Utf8

            # No NaN in critical columns
            for col in numeric_cols:
                nan_count = df[col].null_count()
                assert nan_count == 0, f"Column '{col}' has {nan_count} NaN values"

            total_rows += len(df)
            partition_dates.append(df)

        # AC-FR0300-03: row count matches source
        assert total_rows == source_row_count, (
            f"Row count mismatch: source={source_row_count}, output={total_rows}"
        )

        # AC-FR0300-03: date range matches source
        output_date_min = min(df["date"].min() for df in partition_dates)
        output_date_max = max(df["date"].max() for df in partition_dates)
        assert output_date_min == source_date_min, (
            f"Min date mismatch: source={source_date_min}, output={output_date_min}"
        )
        assert output_date_max == source_date_max, (
            f"Max date mismatch: source={source_date_max}, output={output_date_max}"
        )

        # Verify asset count
        all_assets: set[str] = set()
        for df in partition_dates:
            all_assets.update(df["asset"].unique().to_list())
        assert len(all_assets) == source_assets, (
            f"Asset count mismatch: source={source_assets}, output={len(all_assets)}"
        )

        # Timing check (should be < 10s for 10x60 fixture)
        elapsed = time.perf_counter() - t0
        assert elapsed < 30, f"Conversion took {elapsed:.1f}s, must be <30s"

    def test_convert_ohlcv_10x60_idempotent(self, tmp_path: Path):
        """AC-FR0300-08: re-running conversion is idempotent.

        Run conversion twice on the same fixture; the output should be
        identical (same number of partitions, same rows per partition).
        """
        output_root = tmp_path / "v0.3.0"

        # First run
        r1 = subprocess.run(
            [
                sys.executable,
                "scripts/convert_fixture_to_quantide.py",
                "--fixture",
                "ohlcv_10x60",
                "--output-root",
                str(output_root),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r1.returncode == 0

        store_path = output_root / "daily_bars_store"
        pq_files_1 = sorted(store_path.rglob("part-0.parquet"))
        row_counts_1 = {p.parent.name: len(pl.read_parquet(p)) for p in pq_files_1}

        # Second run
        r2 = subprocess.run(
            [
                sys.executable,
                "scripts/convert_fixture_to_quantide.py",
                "--fixture",
                "ohlcv_10x60",
                "--output-root",
                str(output_root),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r2.returncode == 0

        pq_files_2 = sorted(store_path.rglob("part-0.parquet"))
        row_counts_2 = {p.parent.name: len(pl.read_parquet(p)) for p in pq_files_2}

        # Partition names and row counts must match
        assert set(row_counts_1.keys()) == set(row_counts_2.keys()), (
            f"Partition names differ between runs: "
            f"{set(row_counts_1.keys())} vs {set(row_counts_2.keys())}"
        )
        for part_name in row_counts_1:
            assert row_counts_1[part_name] == row_counts_2[part_name], (
                f"Row count mismatch for {part_name}: "
                f"run1={row_counts_1[part_name]}, run2={row_counts_2[part_name]}"
            )

    def test_convert_nonexistent_input_returns_exit_2(self, tmp_path: Path):
        """AC-FR0300-06: nonexistent input → exit code 2, stderr message."""
        output_root = tmp_path / "v0.3.0"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/convert_fixture_to_quantide.py",
                "--input",
                str(tmp_path / "nonexistent.parquet"),
                "--output-root",
                str(output_root),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}"
        assert "input file not found" in result.stderr, (
            f"Expected 'input file not found' in stderr, got: {result.stderr}"
        )

    def test_convert_schema_mismatch_returns_exit_3(self, tmp_path: Path):
        """AC-FR0300-07: schema mismatch (missing columns) → exit code 3."""
        # Create a parquet with missing volume column
        bad_df = pl.DataFrame(
            {
                "date": [16871, 16872],
                "asset": ["000001.SZ", "000001.SZ"],
                "open": [10.0, 11.0],
                "high": [10.5, 11.5],
                "low": [9.5, 10.5],
                "close": [10.2, 11.2],
                "adj_factor": [1.0, 1.0],
            }
        )
        bad_path = tmp_path / "bad_schema.parquet"
        bad_df.write_parquet(bad_path)

        output_root = tmp_path / "v0.3.0"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/convert_fixture_to_quantide.py",
                "--input",
                str(bad_path),
                "--output-root",
                str(output_root),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 3, f"Expected exit code 3, got {result.returncode}"
        assert "schema mismatch" in result.stderr, (
            f"Expected 'schema mismatch' in stderr, got: {result.stderr}"
        )
        assert "volume" in result.stderr, (
            f"Expected 'volume' mention in stderr, got: {result.stderr}"
        )
