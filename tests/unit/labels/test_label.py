"""Tests for label construction (FR-0500)."""

import json
from datetime import date, timedelta

import polars as pl
import pytest

from trader_off.labels.builder import build_labels, compute_label_stats


class TestBuildLabels:
    """Unit tests for build_labels."""

    @pytest.fixture
    def ten_close_asset_a(self) -> pl.DataFrame:
        """Asset A with 10 close values [10..19] and date column."""
        close_values = [10.0 + i for i in range(10)]
        start_date = date(2024, 1, 1)
        data = []
        for i, close_val in enumerate(close_values):
            d = start_date + timedelta(days=i)
            data.append(
                {
                    "asset": "A",
                    "date": d,
                    "close": close_val,
                }
            )
        return pl.DataFrame(
            data,
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "close": pl.Float64,
            },
        )

    # AC-FR0500-01: Label formula correctness
    def test_ac_fr0500_01_label_formula(self, ten_close_asset_a):
        """AC-FR0500-01: label[t] = close[t+5]/close[t] - 1.

        close=[10..19]: label[0]=15/10-1=0.5, label[4]=19/14-1≈0.3571.
        """
        result = build_labels(ten_close_asset_a, horizon=5)

        labels = result["label"].to_list()
        assert abs(labels[0] - 0.5) < 1e-6, f"label[0]={labels[0]}, expected 0.5"
        assert abs(labels[4] - (19.0 / 14.0 - 1.0)) < 1e-6, (
            f"label[4]={labels[4]}, expected ~0.3571"
        )
        assert result.columns == ["asset", "date", "label"]

    # AC-FR0500-02: Last 5 labels are NaN
    def test_ac_fr0500_02_tail_nan(self, ten_close_asset_a):
        """AC-FR0500-02: Last 5 labels (indices 5..9) are NaN (no t+5 data)."""
        result = build_labels(ten_close_asset_a, horizon=5)

        labels = result["label"].to_list()
        tail = labels[5:]
        assert tail == [None, None, None, None, None], f"Expected last 5 NaN, got {tail}"

    # AC-FR0500-03: NaN close causes NaN label
    def test_ac_fr0500_03_halt_nan(self):
        """AC-FR0500-03: close[7] is NaN → label[2] is NaN."""
        close_values = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, None, 18.0, 19.0]
        start_date = date(2024, 1, 1)
        data = []
        for i, close_val in enumerate(close_values):
            d = start_date + timedelta(days=i)
            data.append(
                {
                    "asset": "A",
                    "date": d,
                    "close": close_val,
                }
            )
        ohlcv = pl.DataFrame(
            data,
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "close": pl.Float64,
            },
        )

        result = build_labels(ohlcv, horizon=5)

        labels = result["label"].to_list()
        assert labels[2] is None, f"label[2]={labels[2]}, expected None (halt)"

    # limit_up filter
    def test_limit_up_filter(self, tmp_path):
        """limit_up=True at t=3 → label[3] NaN + file record."""
        close_values = [10.0 + i for i in range(10)]
        limit_up_values = [False] * 10
        limit_up_values[3] = True  # 4th day has limit_up

        start_date = date(2024, 1, 1)
        data = []
        for i, close_val in enumerate(close_values):
            d = start_date + timedelta(days=i)
            data.append(
                {
                    "asset": "A",
                    "date": d,
                    "close": close_val,
                    "limit_up": limit_up_values[i],
                }
            )
        ohlcv = pl.DataFrame(
            data,
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "close": pl.Float64,
                "limit_up": pl.Boolean,
            },
        )

        output_dir = tmp_path / "label_output"
        output_dir.mkdir()
        filter_path = output_dir / "limit_up_down_filter.json"

        result = build_labels(
            ohlcv, horizon=5, filter_limit_up_down=True, filter_output_path=filter_path
        )

        # label[3] should be NaN (limit_up filter applied)
        labels = result["label"].to_list()
        assert labels[3] is None, f"label[3]={labels[3]}, expected None (limit_up)"

        # Check filter file
        assert filter_path.exists(), "limit_up_down_filter.json not created"
        records = json.loads(filter_path.read_text())
        assert len(records) == 1
        assert records[0]["asset"] == "A"
        assert records[0]["reason"] == "limit_up"

    # Label statistics
    def test_label_stats(self, tmp_path):
        """compute_label_stats returns {mean, std, min, p1, p99, max}."""
        # Simple labels with known stats
        label_values = [0.01, 0.02, -0.01, 0.03, 0.0, -0.02, 0.015, 0.025, -0.005, 0.01]
        start_date = date(2024, 1, 1)
        data = []
        for i, label in enumerate(label_values):
            d = start_date + timedelta(days=i)
            data.append({"asset": "A", "date": d, "label": label})
        labels_df = pl.DataFrame(
            data,
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "label": pl.Float64,
            },
        )

        stats_path = tmp_path / "label_stats.json"
        result = compute_label_stats(labels_df, output_path=stats_path)

        assert "mean" in result
        assert "std" in result
        assert "min" in result
        assert "p1" in result
        assert "p99" in result
        assert "max" in result
        assert isinstance(result["mean"], float)

        # p1 should be near -0.02, p99 near 0.03
        assert result["p1"] <= result["mean"] <= result["p99"]
        assert result["min"] <= result["p1"]
        assert result["p99"] <= result["max"]

        # File should exist
        assert stats_path.exists()
        saved = json.loads(stats_path.read_text())
        assert saved.keys() == result.keys()


class TestLabelSkippedFilter:
    """Test that limit_up/down filter is skipped when columns are missing."""

    def test_skip_filter_when_columns_missing(self, tmp_path):
        """Limit filter skipped when limit_up/limit_down columns missing."""
        close_values = [10.0 + i for i in range(10)]
        start_date = date(2024, 1, 1)
        data = []
        for i, close_val in enumerate(close_values):
            d = start_date + timedelta(days=i)
            data.append({"asset": "A", "date": d, "close": close_val})
        ohlcv = pl.DataFrame(
            data,
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "close": pl.Float64,
            },
        )

        result = build_labels(ohlcv, horizon=5, filter_limit_up_down=True)

        # Should still compute labels (no crash)
        assert "label" in result.columns
        assert len(result) == 10
