"""Unit tests for QuantideFetcherAdapter (FR-0100, NFR-0100)."""

import ast
from datetime import date
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from trader_off.data.loader import DataLoader

# ---------------------------------------------------------------------------
# NFR-0100: AST validation — no top-level quantide import
# ---------------------------------------------------------------------------


def _get_top_level_import_nodes(source_path: Path) -> list[ast.stmt]:
    """Parse source file and return top-level statements."""
    src = source_path.read_text()
    tree = ast.parse(src)
    return tree.body


def _get_top_level_import_modules(source_path: Path) -> set[str]:
    """Return set of module names imported at top level."""
    nodes = _get_top_level_import_nodes(source_path)
    modules: set[str] = set()
    for node in nodes:
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
        """Verify quantide_adapter.py has no top-level `import quantide.*`."""
        modules = _get_top_level_import_modules(adapter_source_path)
        quantide_imports = {m for m in modules if m.startswith("quantide")}
        assert quantide_imports == set(), f"Top-level quantide imports found: {quantide_imports}"

    def test_quantide_imports_only_in_function_bodies(self, adapter_source_path):
        """Verify all quantide imports occur inside function bodies, not top-level."""
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
        """Verify forbidden modules (service, portfolio, backtest, core.scheduler)
        are NOT referenced anywhere in the adapter."""
        forbidden = (
            "quantide.service",
            "quantide.portfolio",
            "quantide.backtest",
            "quantide.core.scheduler",
        )
        src = adapter_source_path.read_text()
        violations = [p for p in forbidden if p in src]
        assert violations == [], f"Forbidden quantide module references found: {violations}"


# ---------------------------------------------------------------------------
# FR-0100: QuantideFetcherAdapter functionality
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_bars_pdf() -> pd.DataFrame:
    """Create a sample pandas DataFrame mimicking fetch_bars output."""
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


@pytest.fixture
def sample_bars_multi_asset_pdf() -> pd.DataFrame:
    """Create multi-asset bars data mimicking fetch_bars output."""
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


class TestQuantideFetcherAdapterSchema:
    """Tests for QuantideFetcherAdapter polars schema correctness."""

    def test_empty_ohlcv_schema(self):
        """Returns empty DataFrame with correct OHLCV schema when no data."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
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
        """Converts pandas bars to polars with amount->turnover and adj_factor=1.0."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
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
        # Verify all types
        assert result.schema["asset"] == pl.Utf8
        assert result.schema["date"] == pl.Date
        assert result.schema["open"] == pl.Float64
        assert result.schema["close"] == pl.Float64
        assert result.schema["volume"] == pl.Float64


class TestQuantideFetcherAdapterGetDaily:
    """Tests for QuantideFetcherAdapter.get_daily()."""

    @pytest.mark.asyncio
    async def test_get_daily_signature_matches_dataloader(self, sample_bars_pdf):
        """get_daily(asset, end_date, count) returns polars DataFrame."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()

        # Monkey-patch internal methods
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
        """Only returns rows matching the requested asset."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
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
        """Returns empty DataFrame when no trade dates are found."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
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
        """Returns empty DataFrame when fetch_bars returns empty data."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
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
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
        ]
        adapter._fetch_bars_for_dates = lambda dates: (None, [])

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 2), count=1)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_daily_handles_fetch_errors(self, sample_bars_pdf):
        """Logs errors from fetch_bars but still returns available data."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        errors = [
            ["daily", date(2024, 1, 2), "Data fetch failed"],
            ["daily", date(2024, 1, 3), "Network error"],
        ]
        adapter._fetch_bars_for_dates = lambda dates: (sample_bars_pdf.copy(), errors)

        result = await adapter.get_daily("000001.SZ", date(2024, 1, 3), count=3)

        # Should still return data even with errors
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_daily_handles_fetch_exception(self):
        """Returns empty DataFrame when fetch_bars raises an exception."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
        adapter._compute_trade_dates = lambda ed, c: [
            date(2024, 1, 2),
        ]

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
        """Returns empty DataFrame when asset is not in fetch_bars results."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
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
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        captured_count = None

        def capture_count(ed, c):
            nonlocal captured_count
            captured_count = c
            return [date(2024, 1, 2)]

        adapter = QuantideFetcherAdapter()
        adapter._compute_trade_dates = capture_count
        adapter._fetch_bars_for_dates = lambda dates: (sample_bars_pdf.copy(), [])

        await adapter.get_daily("000001.SZ", date(2024, 1, 2))

        assert captured_count == 120, f"Expected default count=120, got {captured_count}"

    @pytest.mark.asyncio
    async def test_date_computation_uses_calendar(self, monkeypatch):
        """Date computation delegates to quantide Calendar.get_frames_by_count."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()

        # Create a mock calendar and replace the real one's method
        expected_dates = [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]
        call_record = {}

        def mock_compute_trade_dates(ed, n):
            call_record["end_date"] = ed
            call_record["count"] = n
            return expected_dates

        # Monkey-patch the instance method with our mock
        adapter._compute_trade_dates = mock_compute_trade_dates
        adapter._fetch_bars_for_dates = lambda dates: (pd.DataFrame(), [])

        await adapter.get_daily("000001.SZ", date(2024, 1, 4), count=3)

        assert call_record["end_date"] == date(2024, 1, 4)
        assert call_record["count"] == 3


class TestDataLoaderIntegration:
    """Verify DataLoader can accept QuantideFetcherAdapter as fetcher."""

    @pytest.mark.asyncio
    async def test_dataloader_accepts_adapter_as_fetcher(self, sample_bars_pdf):
        """DataLoader uses QuantideFetcherAdapter via the fetcher parameter."""
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
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
        from trader_off.data.quantide_adapter import QuantideFetcherAdapter

        adapter = QuantideFetcherAdapter()
        adapter._compute_trade_dates = lambda ed, c: []

        loader = DataLoader(fetcher=adapter)
        result = await loader.get_history("000001.SZ", date(2024, 1, 4), count=3)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
