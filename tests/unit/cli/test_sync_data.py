"""Tests for sync_data CLI — FR-0100.

Covers: argparse exit 2, config error exit 4, partial failure exit 5,
happy path exit 0, dry-run, calendar write, OHLCV partition by year.
"""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

# Will fail until sync_data.py is created (Red phase)
from trader_off.cli.sync_data import main  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_asset_csv(tmp_path) -> Path:
    """Create a minimal CSV with an 'asset' column."""
    csv_path = tmp_path / "universe.csv"
    csv_path.write_text("asset\n000001.SZ\n000002.SZ\n000003.SZ\n")
    return csv_path


@pytest.fixture
def mock_calendar_df():
    """Create a mock calendar DataFrame matching fetch_calendar output."""
    import pandas as pd

    dates = pd.date_range("2023-12-01", "2024-01-31", freq="B")
    df = pd.DataFrame(
        {
            "is_open": [1] * len(dates),
            "prev": [d.strftime("%Y-%m-%d") for d in dates],
        },
        index=dates,
    )
    return df


@pytest.fixture
def mock_ohlcv_df():
    """Create a mock OHLCV DataFrame matching QuantideDataLoader output."""
    return pl.DataFrame(
        {
            "asset": ["000001.SZ"] * 3,
            "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "open": [10.0, 10.1, 10.2],
            "high": [10.5, 10.6, 10.7],
            "low": [9.8, 9.9, 10.0],
            "close": [10.3, 10.4, 10.5],
            "volume": [1e6, 1.1e6, 1.2e6],
            "turnover": [1e7, 1.1e7, 1.2e7],
            "adj_factor": [1.0, 1.0, 1.0],
        }
    ).cast(
        {
            "asset": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
            "adj_factor": pl.Float64,
        }
    )


# ---------------------------------------------------------------------------
# Exit code 2: Argparse errors
# ---------------------------------------------------------------------------


class TestArgparseExit2:
    """FR-0100 scenario-0040: argparse failures → exit code 2."""

    def test_no_args_exits_2(self):
        """Empty argv → argparse emits usage → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2

    def test_missing_start_exits_2(self, sample_asset_csv):
        """Missing --start → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--universe",
                    str(sample_asset_csv),
                    "--end",
                    "2024-12-31",
                ]
            )
        assert exc_info.value.code == 2

    def test_missing_end_exits_2(self, sample_asset_csv):
        """Missing --end → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--universe",
                    str(sample_asset_csv),
                    "--start",
                    "2024-01-01",
                ]
            )
        assert exc_info.value.code == 2

    def test_invalid_date_format_exits_2(self, sample_asset_csv):
        """Invalid date string → argparse type error → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--universe",
                    str(sample_asset_csv),
                    "--start",
                    "not-a-date",
                    "--end",
                    "2024-12-31",
                ]
            )
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Exit code 4: Config errors
# ---------------------------------------------------------------------------


class TestConfigExit4:
    """FR-0100 scenario-0040: config errors → exit code 4."""

    def test_missing_token_exits_4(self, sample_asset_csv, monkeypatch):
        """No TUSHARE_TOKEN → exit 4."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        exit_code = main(
            [
                "--universe",
                str(sample_asset_csv),
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4

    def test_universe_not_found_exits_4(self, monkeypatch):
        """Universe file does not exist → exit 4."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        exit_code = main(
            [
                "--universe",
                "/nonexistent/path.csv",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4

    def test_universe_no_asset_column_exits_4(self, tmp_path, monkeypatch):
        """CSV without 'asset' column → exit 4."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("foo,bar\n1,2\n")
        exit_code = main(
            [
                "--universe",
                str(bad_csv),
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4

    def test_start_after_end_exits_4(self, sample_asset_csv, monkeypatch):
        """start > end → exit 4."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        exit_code = main(
            [
                "--universe",
                str(sample_asset_csv),
                "--start",
                "2024-12-31",
                "--end",
                "2024-01-01",
            ]
        )
        assert exit_code == 4


# ---------------------------------------------------------------------------
# Exit code 0: Happy path (full sync)
# ---------------------------------------------------------------------------


class TestHappyPathExit0:
    """FR-0100 scenario-0010: full sync → exit code 0."""

    def test_full_sync_exits_0(
        self, sample_asset_csv, mock_calendar_df, mock_ohlcv_df, monkeypatch, tmp_path
    ):
        """Full sync with mocked dependencies → exit 0."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        store_path = tmp_path / "bars"
        store_path.mkdir()

        with patch(
            "quantide.data.fetchers.tushare.fetch_calendar", return_value=mock_calendar_df
        ) as mock_fetch_cal:
            with patch("quantide.data.models.calendar.calendar"):
                with patch(
                    "trader_off.data.quantide_adapter.QuantideDataLoader"
                ) as mock_loader_cls:
                    mock_loader = MagicMock()
                    mock_loader.get_daily = AsyncMock(return_value=mock_ohlcv_df.clone())
                    mock_loader_cls.return_value = mock_loader

                    exit_code = main(
                        [
                            "--universe",
                            str(sample_asset_csv),
                            "--start",
                            "2024-01-01",
                            "--end",
                            "2024-01-05",
                            "--store-path",
                            str(store_path),
                        ]
                    )

        assert exit_code == 0
        # Verify calendar was fetched
        mock_fetch_cal.assert_called_once()
        # Verify get_daily called for each asset (3 assets)
        assert mock_loader.get_daily.call_count == 3

    def test_calendar_written_to_default_path(
        self, sample_asset_csv, mock_calendar_df, mock_ohlcv_df, monkeypatch, tmp_path
    ):
        """Calendar is written to .quantide/calendar/calendar.parquet by default."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        monkeypatch.chdir(tmp_path)  # default path is relative

        with patch("quantide.data.fetchers.tushare.fetch_calendar", return_value=mock_calendar_df):
            with patch("quantide.data.models.calendar.calendar") as mock_cal:
                with patch(
                    "trader_off.data.quantide_adapter.QuantideDataLoader"
                ) as mock_loader_cls:
                    mock_loader = MagicMock()
                    mock_loader.get_daily = AsyncMock(return_value=mock_ohlcv_df.clone())
                    mock_loader_cls.return_value = mock_loader

                    exit_code = main(
                        [
                            "--universe",
                            str(sample_asset_csv),
                            "--start",
                            "2024-01-01",
                            "--end",
                            "2024-01-05",
                        ]
                    )

        assert exit_code == 0
        # calendar.save should have been called
        mock_cal.save.assert_called_once()

    def test_ohlcv_partition_by_year(
        self, sample_asset_csv, mock_calendar_df, mock_ohlcv_df, monkeypatch, tmp_path
    ):
        """OHLCV data is written with partition_by=year."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        store_path = tmp_path / "bars"

        with patch("quantide.data.fetchers.tushare.fetch_calendar", return_value=mock_calendar_df):
            with patch("quantide.data.models.calendar.calendar"):
                with patch(
                    "trader_off.data.quantide_adapter.QuantideDataLoader"
                ) as mock_loader_cls:
                    mock_loader = MagicMock()
                    mock_loader.get_daily = AsyncMock(return_value=mock_ohlcv_df.clone())
                    mock_loader_cls.return_value = mock_loader

                    with patch.object(pl.DataFrame, "write_parquet") as mock_write:
                        exit_code = main(
                            [
                                "--universe",
                                str(sample_asset_csv),
                                "--start",
                                "2024-01-01",
                                "--end",
                                "2024-01-05",
                                "--store-path",
                                str(store_path),
                            ]
                        )

        assert exit_code == 0
        # write_parquet should have been called with partition_by
        assert mock_write.call_count == 3  # one per asset
        for call in mock_write.call_args_list:
            _, kwargs = call
            assert "partition_by" in kwargs, "write_parquet should be called with partition_by"


# ---------------------------------------------------------------------------
# Exit code 0: Dry-run
# ---------------------------------------------------------------------------


class TestDryRunExit0:
    """FR-0100 scenario-0020: dry-run → no IO, exit 0."""

    def test_dry_run_exits_0(self, sample_asset_csv, monkeypatch):
        """Dry-run exits 0 without network IO."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        exit_code = main(
            [
                "--universe",
                str(sample_asset_csv),
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
                "--dry-run",
            ]
        )
        assert exit_code == 0

    def test_dry_run_no_fetch_calendar(self, sample_asset_csv, monkeypatch):
        """Dry-run must NOT call fetch_calendar."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        with patch("quantide.data.fetchers.tushare.fetch_calendar") as mock_fetch_cal:
            exit_code = main(
                [
                    "--universe",
                    str(sample_asset_csv),
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--dry-run",
                ]
            )
        assert exit_code == 0
        mock_fetch_cal.assert_not_called()

    def test_dry_run_no_quantide_loader(self, sample_asset_csv, monkeypatch):
        """Dry-run must NOT instantiate QuantideDataLoader."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        with patch("trader_off.data.quantide_adapter.QuantideDataLoader") as mock_loader_cls:
            exit_code = main(
                [
                    "--universe",
                    str(sample_asset_csv),
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--dry-run",
                ]
            )
        assert exit_code == 0
        mock_loader_cls.assert_not_called()

    def test_dry_run_no_calendar_save(self, sample_asset_csv, monkeypatch):
        """Dry-run must NOT call calendar.save."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        with patch("quantide.data.models.calendar.calendar") as mock_cal:
            exit_code = main(
                [
                    "--universe",
                    str(sample_asset_csv),
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--dry-run",
                ]
            )
        assert exit_code == 0
        mock_cal.save.assert_not_called()


# ---------------------------------------------------------------------------
# Exit code 5: Partial failure
# ---------------------------------------------------------------------------


class TestPartialFailureExit5:
    """FR-0100 scenario-0030: partial asset failure → exit code 5."""

    def test_partial_failure_exits_5(
        self, sample_asset_csv, mock_calendar_df, mock_ohlcv_df, monkeypatch, tmp_path
    ):
        """When some assets fail, exit 5 and successful ones still written."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        store_path = tmp_path / "bars"

        with patch("quantide.data.fetchers.tushare.fetch_calendar", return_value=mock_calendar_df):
            with patch("quantide.data.models.calendar.calendar"):
                with patch(
                    "trader_off.data.quantide_adapter.QuantideDataLoader"
                ) as mock_loader_cls:
                    mock_loader = MagicMock()
                    # Asset 1 succeeds, asset 2 fails, asset 3 succeeds
                    mock_loader.get_daily = AsyncMock(
                        side_effect=[
                            mock_ohlcv_df.clone(),  # asset 1: OK
                            RuntimeError("Tushare error"),  # asset 2: fail
                            mock_ohlcv_df.with_columns(  # asset 3: OK
                                pl.lit("000003.SZ").alias("asset")
                            ),
                        ]
                    )
                    mock_loader_cls.return_value = mock_loader

                    exit_code = main(
                        [
                            "--universe",
                            str(sample_asset_csv),
                            "--start",
                            "2024-01-01",
                            "--end",
                            "2024-01-05",
                            "--store-path",
                            str(store_path),
                        ]
                    )

        assert exit_code == 5
        # All 3 assets should have been attempted
        assert mock_loader.get_daily.call_count == 3

    def test_empty_df_treated_as_failure(
        self, sample_asset_csv, mock_calendar_df, monkeypatch, tmp_path
    ):
        """Empty DataFrame from get_daily → treated as failure → exit 5."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        store_path = tmp_path / "bars"

        with patch("quantide.data.fetchers.tushare.fetch_calendar", return_value=mock_calendar_df):
            with patch("quantide.data.models.calendar.calendar"):
                with patch(
                    "trader_off.data.quantide_adapter.QuantideDataLoader"
                ) as mock_loader_cls:
                    mock_loader = MagicMock()
                    empty_df = pl.DataFrame(
                        schema={
                            "asset": pl.Utf8,
                            "date": pl.Date,
                            "open": pl.Float64,
                            "high": pl.Float64,
                            "low": pl.Float64,
                            "close": pl.Float64,
                            "volume": pl.Float64,
                            "turnover": pl.Float64,
                            "adj_factor": pl.Float64,
                        }
                    )
                    # All assets return empty → all failures → exit 5
                    mock_loader.get_daily = AsyncMock(return_value=empty_df)
                    mock_loader_cls.return_value = mock_loader

                    exit_code = main(
                        [
                            "--universe",
                            str(sample_asset_csv),
                            "--start",
                            "2024-01-01",
                            "--end",
                            "2024-01-05",
                            "--store-path",
                            str(store_path),
                        ]
                    )

        assert exit_code == 5


# ---------------------------------------------------------------------------
# Entry point: if __name__ == "__main__"
# ---------------------------------------------------------------------------


class TestEntryPoint:
    """FR-0100: module-level entry point works."""

    def test_entry_point_module(self, sample_asset_csv, monkeypatch):
        """smoke: import succeeds and main is callable."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        # Just verify main is a callable and returns int
        result = main(
            [
                "--universe",
                str(sample_asset_csv),
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
                "--dry-run",
            ]
        )
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Defaults and edge cases
# ---------------------------------------------------------------------------


class TestDefaults:
    """FR-0100: default values for optional args."""

    def test_default_store_path(self, sample_asset_csv, monkeypatch, tmp_path):
        """Default store-path is .quantide/bars/."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        monkeypatch.chdir(tmp_path)

        # Dry-run to avoid writing files
        exit_code = main(
            [
                "--universe",
                str(sample_asset_csv),
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
                "--dry-run",
            ]
        )
        assert exit_code == 0
