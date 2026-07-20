"""Unit tests for portfolio.industry (FR-3200).

AC-FR3200-01: load_industry_map loads CSV and returns {asset: industry} dict
AC-FR3200-02: get_industry returns "UNKNOWN" + WARNING for missing assets
AC-FR3200-03: duplicate assets in map raise IndustryMapConflictError
"""

import io
import tempfile
from pathlib import Path

import pytest
from loguru import logger

from trader_off.utils.exceptions import IndustryMapConflictError


class TestLoadIndustryMap:
    """Tests for load_industry_map function."""

    @pytest.fixture
    def industry_csv_path(self) -> Path:
        """Create a temporary industry map CSV with 50 assets."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("asset,industry\n")
            for i in range(50):
                # 10 different industries, 5 assets each
                industry = [
                    "banking",
                    "real_estate",
                    "technology",
                    "healthcare",
                    "energy",
                    "consumer",
                    "industrial",
                    "materials",
                    "utilities",
                    "telecom",
                ][i % 10]
                f.write(f"stock_{i:03d},{industry}\n")
            path = f.name
        yield Path(path)
        Path(path).unlink()

    @pytest.fixture
    def duplicate_csv_path(self) -> Path:
        """Create a CSV with duplicate asset entries."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("asset,industry\n")
            f.write("stock_001,banking\n")
            f.write("stock_001,technology\n")
            path = f.name
        yield Path(path)
        Path(path).unlink()

    def test_ac_fr3200_01_load_industry_map(self, industry_csv_path):
        """AC-FR3200-01: loads CSV, returns dict of correct length and types."""
        from trader_off.portfolio.industry import load_industry_map

        result = load_industry_map(industry_csv_path)
        assert len(result) == 50
        assert all(isinstance(v, str) for v in result.values())
        assert all(isinstance(k, str) for k in result.keys())

    def test_ac_fr3200_02_unknown_ticker_warning(self):
        """AC-FR3200-02: unknown ticker returns 'UNKNOWN' + WARNING."""
        from trader_off.portfolio.industry import get_industry

        industry_map = {"stock_000": "banking", "stock_001": "technology"}

        stream = io.StringIO()
        handler_id = logger.add(stream, level="WARNING", format="{message}")
        try:
            result = get_industry("stock_999", industry_map)
        finally:
            logger.remove(handler_id)

        assert result == "UNKNOWN"
        assert "UNKNOWN" in stream.getvalue() or "stock_999" in stream.getvalue()

    def test_ac_fr3200_03_duplicate_asset_raises(self, duplicate_csv_path):
        """AC-FR3200-03: duplicate asset in CSV raises IndustryMapConflictError."""
        from trader_off.portfolio.industry import load_industry_map

        with pytest.raises(IndustryMapConflictError, match="duplicate asset"):
            load_industry_map(duplicate_csv_path)

    def test_missing_csv_columns_raises(self, tmp_path):
        """CSV without 'asset' and 'industry' columns raises ValueError."""
        from trader_off.portfolio.industry import load_industry_map

        bad_csv = tmp_path / "bad_industry.csv"
        bad_csv.write_text("ticker,sector\nA,tech\n")

        with pytest.raises(ValueError, match="must have 'asset' and 'industry'"):
            load_industry_map(bad_csv)

    def test_missing_csv_columns_no_header(self, tmp_path):
        """CSV with missing header row raises ValueError."""
        from trader_off.portfolio.industry import load_industry_map

        bad_csv = tmp_path / "no_header.csv"
        bad_csv.write_text("A,tech\nB,finance\n")

        with pytest.raises(ValueError):
            load_industry_map(bad_csv)

    def test_get_industry_known_ticker(self):
        """get_industry returns correct industry for known ticker."""
        from trader_off.portfolio.industry import get_industry

        industry_map = {"stock_000": "banking", "stock_001": "technology"}
        result = get_industry("stock_000", industry_map)
        assert result == "banking"

    def test_get_industry_unknown_ticker_returns_unknown(self):
        """get_industry returns 'UNKNOWN' for unknown ticker without raising."""
        from trader_off.portfolio.industry import get_industry

        industry_map = {"stock_000": "banking"}
        result = get_industry("stock_999", industry_map)
        assert result == "UNKNOWN"

    def test_load_industry_map_file_not_found(self):
        """load_industry_map raises FileNotFoundError for missing file."""
        from pathlib import Path

        from trader_off.portfolio.industry import load_industry_map

        with pytest.raises(FileNotFoundError):
            load_industry_map(Path("/nonexistent/path.csv"))
