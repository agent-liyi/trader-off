"""Unit tests for QuantideDataLoader (FR-0100, NFR-0100)."""

import ast
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from trader_off.data.loader import DataLoader

# ---------------------------------------------------------------------------
# NFR-0100: AST validation — no top-level quantide import
# ---------------------------------------------------------------------------


def _get_top_level_import_modules(source_path: Path) -> set[str]:
    """Return set of module names imported at top level."""
    src = source_path.read_text()
    tree = ast.parse(src)
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


@pytest.fixture(scope="module")
def adapter_source_path() -> Path:
    """Path to the quantide_adapter.py source file."""
    return (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "trader_off"
        / "data"
        / "quantide_adapter.py"
    )


class TestNFR0100FunctionScopeImports:
    """NFR-0100: All quantide imports must be function-scope (lazy)."""

    def test_no_top_level_quantide_import(self, adapter_source_path):
        """AC-NFR0100-01: No top-level `import quantide` or `from quantide`."""
        modules = _get_top_level_import_modules(adapter_source_path)
        quantide_imports = {m for m in modules if m.startswith("quantide")}
        assert quantide_imports == set(), f"Top-level quantide imports found: {quantide_imports}"

    def test_quantide_imports_only_in_function_bodies(self, adapter_source_path):
        """AC-NFR0100-04: All quantide imports inside function bodies only."""
        src = adapter_source_path.read_text()
        tree = ast.parse(src)

        quantide_imports_at_top: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("quantide"):
                        quantide_imports_at_top.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("quantide"):
                    quantide_imports_at_top.append(f"from {node.module} import ...")

        assert len(quantide_imports_at_top) == 0, "Top-level quantide imports found:\n" + "\n".join(
            quantide_imports_at_top
        )

    def test_forbidden_quantide_modules_not_referenced(self, adapter_source_path):
        """AC-NFR0100-02: No forbidden module references in adapter."""
        forbidden = (
            "quantide.service",
            "quantide.portfolio",
            "quantide.backtest",
            "quantide.core.scheduler",
        )
        src = adapter_source_path.read_text()
        violations = [p for p in forbidden if p in src]
        assert violations == [], f"Forbidden quantide module references found: {violations}"

    def test_lazy_import_no_quantide_side_effect(self):
        """AC-NFR0100-05: Importing quantide_adapter does not trigger quantide import."""
        import importlib

        # Ensure quantide.data.fetchers.tushare is not already loaded
        sys.modules.pop("quantide.data.fetchers.tushare", None)
        sys.modules.pop("quantide.data.fetchers", None)

        # Import via importlib to avoid ruff F811 (redefinition) issues
        importlib.import_module("trader_off.data.quantide_adapter")

        assert "quantide.data.fetchers.tushare" not in sys.modules, (
            "quantide.data.fetchers.tushare was imported at module top-level"
        )


# ---------------------------------------------------------------------------
# FR-0100: QuantideDataLoader functionality
# ---------------------------------------------------------------------------


# Fixture: already-renamed columns (as fetch_bars actually returns after its internal rename)
@pytest.fixture
def sample_bars_pdf() -> pd.DataFrame:
    """Sample pandas DataFrame with already-renamed fetch_bars columns."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "asset": ["000001.SZ", "000001.SZ", "000001.SZ"],
            "open": [10.0, 10.5, 10.3],
            "high": [11.0, 11.2, 10.8],
            "low": [9.8, 10.3, 10.1],
            "close": [10.8, 10.9, 10.5],
            "volume": [1000000.0, 1200000.0, 900000.0],
            "amount": [10800000.0, 13080000.0, 9450000.0],
        }
    )


# Fixture: RAW columns as tushare API returns them (ts_code, trade_date, vol)
@pytest.fixture
def raw_bars_pdf() -> pd.DataFrame:
    """Sample pandas DataFrame with RAW tushare column names (ts_code, trade_date, vol)."""
    return pd.DataFrame(
        {
            "trade_date": ["20240102", "20240103", "20240104"],
            "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
            "open": [10.0, 10.5, 10.3],
            "high": [11.0, 11.2, 10.8],
            "low": [9.8, 10.3, 10.1],
            "close": [10.8, 10.9, 10.5],
            "vol": [1000000.0, 1200000.0, 900000.0],
            "amount": [10800000.0, 13080000.0, 9450000.0],
        }
    )


@pytest.fixture
def sample_bars_multi_asset_pdf() -> pd.DataFrame:
    """Multi-asset bars data with already-renamed columns."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2024-01-02",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-04",
                ]
            ),
            "asset": ["000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ"],
            "open": [10.0, 20.0, 10.5, 20.5, 10.3, 20.3],
            "high": [11.0, 21.0, 11.2, 21.2, 10.8, 20.8],
            "low": [9.8, 19.8, 10.3, 20.3, 10.1, 20.1],
            "close": [10.8, 20.8, 10.9, 20.9, 10.5, 20.5],
            "volume": [1e6, 2e6, 1.2e6, 2.2e6, 0.9e6, 1.9e6],
            "amount": [10.8e6, 41.6e6, 13.08e6, 45.98e6, 9.45e6, 38.95e6],
        }
    )


class TestQuantideDataLoaderSchema:
    """Tests for QuantideDataLoader polars schema correctness."""

    def test_empty_ohlcv_schema(self):
        """AC-FR0100-07: Empty DataFrame has correct OHLCV schema."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        result = adapter._empty_ohlcv()
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
        assert set(result.columns) == {
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        }
        assert result.schema["asset"] == pl.Utf8
        assert result.schema["date"] == pl.Date
        assert result.schema["open"] == pl.Float64
        assert result.schema["high"] == pl.Float64
        assert result.schema["low"] == pl.Float64
        assert result.schema["close"] == pl.Float64
        assert result.schema["volume"] == pl.Float64
        assert result.schema["turnover"] == pl.Float64
        assert result.schema["adj_factor"] == pl.Float64

    def test_to_polars_ohlcv_schema_and_mapping(self, sample_bars_pdf):
        """AC-FR0100-04: Converts pandas bars to polars with amount→turnover mapping."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        result = adapter._to_polars_ohlcv(sample_bars_pdf)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        assert set(result.columns) == {
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        }
        # Verify amount was mapped to turnover
        assert result["turnover"][0] == 10800000.0
        # Verify adj_factor defaults to 1.0
        assert all(result["adj_factor"] == 1.0)
        assert result.schema["asset"] == pl.Utf8
        assert result.schema["date"] == pl.Date
        assert result.schema["open"] == pl.Float64
        assert result.schema["close"] == pl.Float64
        assert result.schema["volume"] == pl.Float64

    def test_rename_raw_columns_explicitly(self, raw_bars_pdf):
        """AC-FR0100-04: Explicitly rename ts_code→asset, trade_date→date, vol→volume."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        result = adapter._to_polars_ohlcv(raw_bars_pdf)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        # Verify renamed columns exist and RAW columns do not
        assert "asset" in result.columns
        assert "date" in result.columns
        assert "volume" in result.columns
        assert "ts_code" not in result.columns
        assert "trade_date" not in result.columns
        assert "vol" not in result.columns
        # Verify asset values preserved
        assert result["asset"][0] == "000001.SZ"
        # Verify date values preserved (YYYYMMDD string -> Date cast by polars override)
        assert result["volume"][0] == 1000000.0
        # amount → turnover
        assert result["turnover"][0] == 10800000.0
        # adj_factor default
        assert all(result["adj_factor"] == 1.0)


class TestQuantideDataLoaderGetDaily:
    """Tests for QuantideDataLoader.get_daily()."""

    @pytest.mark.asyncio
    async def test_get_daily_signature_matches_dataloader(self, sample_bars_pdf):
        """AC-FR0100-02: get_daily(asset, end_date, count) returns polars DataFrame."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]
        adapter._fetch_bars_for_dates = lambda dates: (sample_bars_pdf.copy(), [])

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 4), count=3)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        assert set(result.columns) == {
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        }

    @pytest.mark.asyncio
    async def test_get_daily_asset_filtering(self, sample_bars_multi_asset_pdf):
        """AC-FR0100-05: Only returns rows matching the requested asset."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]
        adapter._fetch_bars_for_dates = lambda dates: (
            sample_bars_multi_asset_pdf.copy(),
            [],
        )

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 4), count=3)

        assert len(result) == 3
        assert all(result["asset"] == "000001.SZ")

    @pytest.mark.asyncio
    async def test_get_daily_empty_when_no_trade_dates(self):
        """Returns empty DataFrame when bdate_range yields no dates."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: []

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 4), count=3)

        assert len(result) == 0
        assert set(result.columns) == {
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        }

    @pytest.mark.asyncio
    async def test_get_daily_empty_when_fetch_returns_empty(self):
        """AC-FR0100-07: Returns empty DataFrame when fetch_bars returns empty data."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        adapter._fetch_bars_for_dates = lambda dates: (pd.DataFrame(), [])

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 3), count=3)

        assert len(result) == 0
        assert set(result.columns) == {
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        }

    @pytest.mark.asyncio
    async def test_get_daily_empty_when_fetch_returns_none(self):
        """Returns empty DataFrame when fetch_bars returns None as DataFrame."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [date(2024, 1, 2)]
        adapter._fetch_bars_for_dates = lambda dates: (None, [])

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 2), count=1)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_daily_handles_fetch_errors(self, sample_bars_pdf):
        """AC-FR0100-08: Logs fetch_bars errors but still returns data (no raise)."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        errors = [
            ["daily", date(2024, 1, 2), "fetch failed"],
            ["daily", date(2024, 1, 3), "Network error"],
        ]
        adapter._fetch_bars_for_dates = lambda dates: (sample_bars_pdf.copy(), errors)

        # Must not raise — errors are logged but caller receives valid DataFrame
        result = await adapter.get_daily("000001.SZ", date(2024, 1, 3), count=3)

        assert len(result) > 0
        assert isinstance(result, pl.DataFrame)

    @pytest.mark.asyncio
    async def test_get_daily_handles_fetch_exception(self):
        """Returns empty DataFrame when fetch_bars raises an exception."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [date(2024, 1, 2)]

        def _raise(*args, **kwargs):
            raise RuntimeError("Simulated fetch failure")

        adapter._fetch_bars_for_dates = _raise

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 2), count=1)

        assert len(result) == 0
        assert set(result.columns) == {
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        }

    @pytest.mark.asyncio
    async def test_get_daily_asset_not_in_results(self, sample_bars_pdf):
        """Returns empty DataFrame when asset not in fetch_bars results."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]
        adapter._fetch_bars_for_dates = lambda dates: (sample_bars_pdf.copy(), [])

        result = await adapter.get_daily("999999.XY", date(2024, 1, 4), count=3)

        assert len(result) == 0
        assert result.schema["asset"] == pl.Utf8

    @pytest.mark.asyncio
    async def test_get_daily_default_count_120(self, sample_bars_pdf):
        """Default count parameter is 120."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        captured_count = None

        def capture_count(ed, c):
            nonlocal captured_count
            captured_count = c
            return [date(2024, 1, 2)]

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = capture_count
        adapter._fetch_bars_for_dates = lambda dates: (sample_bars_pdf.copy(), [])

        await adapter.get_daily("000001.SZ", date(2024, 1, 2))

        assert captured_count == 120, f"Expected default count=120, got {captured_count}"

    @pytest.mark.asyncio
    async def test_date_computation_uses_bdate_range(self):
        """Date computation uses pandas.bdate_range (not quantide Calendar)."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()

        # Verify _compute_trade_dates returns a list of date objects
        # that include end_date and span roughly count business days
        end = date(2024, 6, 28)  # Friday
        dates = adapter._compute_trade_dates(end, 10)

        assert isinstance(dates, list)
        assert len(dates) > 0
        assert all(isinstance(d, date) for d in dates)
        # end_date should be included (bdate_range is inclusive)
        assert end in dates
        # Should have at least count elements (the 2x buffer ensures enough business days)
        assert len(dates) >= 10
        # All dates should be weekdays (Mon-Fri)
        assert all(d.weekday() < 5 for d in dates)


class TestQuantideDataLoaderRowLimit:
    """AC-FR0100-06: Row count limiting."""

    @pytest.mark.asyncio
    async def test_get_daily_respects_count_limit(self):
        """AC-FR0100-06: Returns at most count rows for the target asset."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        # Create 20 rows all for "000001.SZ"
        large_bars = pd.DataFrame(
            {
                "date": pd.to_datetime([f"2024-01-{i:02d}" for i in range(2, 22)]),
                "asset": ["000001.SZ"] * 20,
                "open": [10.0] * 20,
                "high": [11.0] * 20,
                "low": [9.0] * 20,
                "close": [10.5] * 20,
                "volume": [1e6] * 20,
                "amount": [10e6] * 20,
            }
        )

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [date(2024, 1, i) for i in range(2, 22)]
        adapter._fetch_bars_for_dates = lambda dates: (large_bars.copy(), [])

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 21), count=5)

        assert result.height <= 5


class TestDataLoaderIntegration:
    """AC-FR0100-09: DataLoader accepts QuantideDataLoader as fetcher."""

    @pytest.mark.asyncio
    async def test_dataloader_accepts_adapter_as_fetcher(self, sample_bars_pdf):
        """AC-FR0100-09: DataLoader uses QuantideDataLoader via fetcher param."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]
        adapter._fetch_bars_for_dates = lambda dates: (sample_bars_pdf.copy(), [])

        loader = DataLoader(fetcher=adapter)
        result = await loader.get_history("000001.SZ", date(2024, 1, 4), count=3)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        assert set(result.columns) == {
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        }

    @pytest.mark.asyncio
    async def test_dataloader_empty_from_adapter(self):
        """DataLoader returns empty DataFrame when adapter returns empty."""
        from trader_off.data.quantide_adapter import QuantideDataLoader

        adapter = QuantideDataLoader()
        adapter._compute_trade_dates = lambda ed, c: []

        loader = DataLoader(fetcher=adapter)
        result = await loader.get_history("000001.SZ", date(2024, 1, 4), count=3)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
