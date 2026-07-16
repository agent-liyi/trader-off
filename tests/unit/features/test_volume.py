"""Tests for volume feature computation (FR-0300)."""

from datetime import date, timedelta

import polars as pl
from loguru import logger

from trader_off.features.volume import compute_volume_features

# Store log messages for test assertion
_log_messages: list[str] = []


def _capture_sink(message):
    """Loguru sink that captures WARNING messages for test assertions."""
    record = message.record
    if record["level"].name == "WARNING":
        _log_messages.append(str(message).strip())


class TestComputeVolumeFeatures:
    """Unit tests for compute_volume_features."""

    # AC-FR0300-1: Column presence check
    def test_ac_fr0300_01_columns(self, five_assets_60_days):
        """AC-FR0300-1: Output must contain turnover_5/10/20 and vp_corr_5/10/20."""
        result = compute_volume_features(five_assets_60_days)

        expected_cols = {
            "turnover_5", "turnover_10", "turnover_20",
            "vp_corr_5", "vp_corr_10", "vp_corr_20",
        }
        assert expected_cols.issubset(set(result.columns)), (
            f"Missing columns: {expected_cols - set(result.columns)}"
        )

        for col in expected_cols:
            assert result[col].dtype == pl.Float64, (
                f"Column {col} dtype is {result[col].dtype}"
            )

        assert len(result) == len(five_assets_60_days)

    # AC-FR0300-2: Turnover missing → NaN + WARNING
    def test_ac_fr0300_02_turnover_missing_warn(self):
        """AC-FR0300-2: Turnover all NaN for asset A → all vol cols NaN + WARNING."""
        # Add a capture sink for this test
        _log_messages.clear()
        sink_id = logger.add(_capture_sink, level="WARNING")

        try:
            # Asset A: 60 rows with turnover=NaN. Asset B: normal data.
            start_date = date(2024, 1, 1)
            data = []
            for asset in ["A", "B"]:
                for i in range(60):
                    d = start_date + timedelta(days=i)
                    base_price = 10.0 + i * 0.1 + (ord(asset) - ord("A")) * 2.0
                    turnover = None if asset == "A" else (0.02 + (i % 10) * 0.001)
                    data.append({
                        "asset": asset,
                        "date": d,
                        "open": base_price,
                        "high": base_price * 1.02,
                        "low": base_price * 0.98,
                        "close": base_price * (1.0 + 0.005 * (i % 5)),
                        "volume": 1_000_000.0 + i * 10_000,
                        "turnover": turnover,
                        "adj_factor": 1.0,
                    })
            ohlcv = pl.DataFrame(data, schema={
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

            result = compute_volume_features(ohlcv)

            volume_cols = [
                "turnover_5", "turnover_10", "turnover_20",
                "vp_corr_5", "vp_corr_10", "vp_corr_20",
            ]
            asset_a = result.filter(pl.col("asset") == "A")
            for col_name in volume_cols:
                null_count = asset_a[col_name].null_count()
                assert null_count == 60, (
                    f"Column {col_name} for asset A: expected 60 NaN, got {null_count}"
                )

            # Check WARNING log via captured messages
            assert len(_log_messages) > 0, "No WARNING messages captured"
            assert any("turnover missing for asset=A" in msg for msg in _log_messages), (
                f"'turnover missing for asset=A' not found in: {_log_messages}"
            )
        finally:
            logger.remove(sink_id)
