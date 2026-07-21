"""Unit tests for QuantideDataLoader (FR-0100, NFR-0100).

Tests cover:
- Token gating (AC-FR0100-01, AC-FR0100-05)
- Real TushareFetcher + fetch_calendar integration (AC-FR0100-02, AC-FR0100-04)
- No pandas.bdate_range usage (AC-FR0100-03)
- Error handling (AC-FR0100-06)
- Function-scope lazy imports (AC-NFR0100-01 through AC-NFR0100-05)
- No quantide.data.models.calendar / quantide.core.enums imports allowed
"""

import ast
import io
import tokenize
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Module under test
from trader_off.data.quantide_adapter import QuantideDataLoader


def _make_calendar_df(dates: list[date]) -> pd.DataFrame:
    """Create a mock fetch_calendar DataFrame with given open trading dates."""
    all_dates = pd.date_range(start=min(dates) - timedelta(days=7), end=max(dates), freq="D")
    rows = []
    for d in all_dates:
        d_date = d.date()
        is_open = 1 if d_date in dates else 0
        prev_date = d_date - timedelta(days=1)
        rows.append({"is_open": is_open, "prev": prev_date})
    cal_df = pd.DataFrame(rows, index=pd.Index([d.date() for d in all_dates], name="date"))
    return cal_df


# ---------------------------------------------------------------------------
# FR-0100 AC-1: Token gate — missing token raises RuntimeError
# ---------------------------------------------------------------------------


class TestTokenGate:
    """AC-FR0100-01: TUSHARE_TOKEN missing → RuntimeError."""

    def test_missing_token_raises_runtime_error(self, monkeypatch):
        """WHEN TUSHARE_TOKEN is not set in env AND no explicit token
        THEN QuantideDataLoader() raises RuntimeError."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        with pytest.raises(
            RuntimeError,
            match="TUSHARE_TOKEN environment variable is required",
        ):
            QuantideDataLoader()

    def test_missing_token_no_network_io(self, monkeypatch):
        """WHEN TUSHARE_TOKEN is not set THEN no quantide imports occur."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        with patch("quantide.data.fetchers.tushare.TushareFetcher") as mock_fetcher:
            with pytest.raises(RuntimeError):
                QuantideDataLoader()
            mock_fetcher.assert_not_called()


# ---------------------------------------------------------------------------
# FR-0100 AC-5: Explicit token bypasses env
# ---------------------------------------------------------------------------


class TestExplicitToken:
    """AC-FR0100-05: explicit token argument takes precedence."""

    def test_explicit_token_bypasses_env(self, monkeypatch):
        """WHEN explicit token is provided THEN env is not read."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        loader = QuantideDataLoader(token="explicit-token")
        assert loader._token == "explicit-token"

    def test_explicit_token_no_runtime_error(self, monkeypatch):
        """WHEN explicit token provided without env THEN no RuntimeError."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        # Should not raise
        loader = QuantideDataLoader(token="explicit-token")
        assert loader._token == "explicit-token"

    def test_env_token_used_when_no_explicit(self, monkeypatch):
        """WHEN no explicit token AND TUSHARE_TOKEN in env THEN env value is used."""
        monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
        loader = QuantideDataLoader()
        assert loader._token == "env-token"


# ---------------------------------------------------------------------------
# FR-0100 AC-2, AC-4: TushareFetcher + Calendar integration
# ---------------------------------------------------------------------------


class TestGetDailyIntegration:
    """AC-FR0100-02 & AC-FR0100-04: get_daily calls fetch_calendar + fetch_bars."""

    @pytest.fixture
    def loader_with_token(self, monkeypatch):
        """Provide a QuantideDataLoader with a test token."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        return QuantideDataLoader()

    @pytest.mark.asyncio
    async def test_get_daily_calls_fetch_calendar(self, loader_with_token):
        """WHEN get_daily is called THEN fetch_calendar is invoked."""
        end_date = date(2024, 1, 31)
        count = 60
        trade_dates = [end_date]

        with patch("quantide.data.fetchers.tushare.fetch_calendar") as mock_fetch_cal:
            mock_fetch_cal.return_value = _make_calendar_df(trade_dates)

            with patch("quantide.data.fetchers.tushare.fetch_bars") as mock_fetch_bars:
                mock_df = self._make_mock_pandas_df()
                mock_fetch_bars.return_value = (mock_df, [])

                await loader_with_token.get_daily("000001.SZ", end_date, count)

            mock_fetch_cal.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_daily_calls_fetch_bars(self, loader_with_token):
        """WHEN get_daily is called THEN fetch_bars is invoked with trade dates."""
        end_date = date(2024, 1, 31)
        trade_dates = [end_date]

        with patch(
            "quantide.data.fetchers.tushare.fetch_calendar",
            return_value=_make_calendar_df(trade_dates),
        ):
            with patch("quantide.data.fetchers.tushare.fetch_bars") as mock_fetch_bars:
                mock_df = self._make_mock_pandas_df()
                mock_fetch_bars.return_value = (mock_df, [])

                await loader_with_token.get_daily("000001.SZ", end_date, 60)

                mock_fetch_bars.assert_called_once_with(trade_dates)

    @pytest.mark.asyncio
    async def test_get_daily_instantiates_tushare_fetcher(self, loader_with_token):
        """WHEN get_daily is called THEN TushareFetcher is instantiated."""
        end_date = date(2024, 1, 31)

        with patch(
            "quantide.data.fetchers.tushare.fetch_calendar",
            return_value=_make_calendar_df([end_date]),
        ):
            with patch(
                "quantide.data.fetchers.tushare.fetch_bars",
                return_value=(self._make_mock_pandas_df(), []),
            ):
                with patch("quantide.data.fetchers.tushare.TushareFetcher") as mock_fetcher_cls:
                    mock_fetcher = MagicMock()
                    mock_fetcher_cls.return_value = mock_fetcher

                    await loader_with_token.get_daily("000001.SZ", end_date, 60)

            mock_fetcher_cls.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_daily_returns_correct_schema(self, loader_with_token):
        """WHEN get_daily succeeds THEN DataFrame has the expected OHLCV schema."""
        end_date = date(2024, 1, 31)

        with patch(
            "quantide.data.fetchers.tushare.fetch_calendar",
            return_value=_make_calendar_df([end_date]),
        ):
            with patch("quantide.data.fetchers.tushare.fetch_bars") as mock_fetch_bars:
                mock_df = self._make_mock_pandas_df()
                mock_fetch_bars.return_value = (mock_df, [])

                result = await loader_with_token.get_daily("000001.SZ", end_date, 60)

        expected_columns = {
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
        assert set(result.columns) == expected_columns
        assert result.height >= 1

    @pytest.mark.asyncio
    async def test_get_daily_respects_count_limit(self, loader_with_token):
        """WHEN get_daily is called THEN returned rows <= count."""
        count = 60
        trade_dates = [date(2024, 6, 1) + timedelta(days=i) for i in range(count)]

        with patch(
            "quantide.data.fetchers.tushare.fetch_calendar",
            return_value=_make_calendar_df(trade_dates),
        ):
            with patch("quantide.data.fetchers.tushare.fetch_bars") as mock_fetch_bars:
                mock_df = self._make_mock_pandas_df(rows=count)
                mock_fetch_bars.return_value = (mock_df, [])

                result = await loader_with_token.get_daily("000001.SZ", date(2024, 1, 31), count)

        assert result.height <= count

    @staticmethod
    def _make_mock_pandas_df(rows: int = 60):
        """Create a mock pandas DataFrame simulating Tushare fetch_bars output."""
        import pandas as pd

        dates = pd.date_range("2024-01-01", periods=rows, freq="B")
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * rows,
                "trade_date": dates,
                "open": [10.0 + i * 0.1 for i in range(rows)],
                "high": [10.5 + i * 0.1 for i in range(rows)],
                "low": [9.5 + i * 0.1 for i in range(rows)],
                "close": [10.2 + i * 0.1 for i in range(rows)],
                "vol": [1000000 + i * 1000 for i in range(rows)],
                "amount": [10000000.0 + i * 5000 for i in range(rows)],
            }
        )


# ---------------------------------------------------------------------------
# FR-0100 AC-3: No pandas.bdate_range
# ---------------------------------------------------------------------------


class TestNoBDateRange:
    """AC-FR0100-03: quantide_adapter.py must not use pandas.bdate_range."""

    def test_no_bdate_range_in_source(self):
        """WHEN inspecting quantide_adapter.py THEN no bdate_range call exists
        in executable code (docstrings may reference it for context)."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        content = src_path.read_text()
        # Check: no active bdate_range usage — strip docstrings/strings first
        tokens = tokenize.generate_tokens(io.StringIO(content).readline)
        code_only = []
        for tok in tokens:
            # Skip comments and strings
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                code_only.append(tok.string)
        code_text = " ".join(code_only)
        assert "bdate_range" not in code_text, (
            "bdate_range found in quantide_adapter.py code — "
            "should use Calendar.get_frames_by_count instead"
        )

    def test_no_bdate_range_ast(self):
        """WHEN parsing quantide_adapter.py AST THEN no pd.bdate_range call."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        tree = ast.parse(src_path.read_text())

        has_bdate_range = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "bdate_range":
                    has_bdate_range = True
                    break

        assert not has_bdate_range, (
            "bdate_range call found in quantide_adapter.py AST — "
            "should use Calendar.get_frames_by_count instead"
        )


# ---------------------------------------------------------------------------
# FR-0100 AC-6: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """AC-FR0100-06: fetch errors return empty DataFrame without raising."""

    @pytest.fixture
    def loader_with_token(self, monkeypatch):
        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        return QuantideDataLoader()

    @pytest.mark.asyncio
    async def test_fetch_bars_error_returns_empty_df(self, loader_with_token):
        """WHEN fetch_bars raises THEN get_daily returns empty DataFrame."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_calendar",
            return_value=_make_calendar_df([date(2024, 1, 31)]),
        ):
            with patch(
                "quantide.data.fetchers.tushare.fetch_bars",
                side_effect=RuntimeError("network down"),
            ):
                result = await loader_with_token.get_daily("000001.SZ", date(2024, 1, 31), 60)

        expected_columns = {
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
        assert set(result.columns) == expected_columns
        assert result.height == 0

    @pytest.mark.asyncio
    async def test_fetch_bars_returns_errors_logs_warning(self, loader_with_token):
        """WHEN fetch_bars returns errors THEN warning is logged but no exception."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_calendar",
            return_value=_make_calendar_df([date(2024, 1, 31)]),
        ):
            with patch("quantide.data.fetchers.tushare.fetch_bars") as mock_fetch:
                mock_df = self._make_mock_pandas_df(rows=1)
                mock_fetch.return_value = (
                    mock_df,
                    [["ts_code", "invalid"]],
                )

                # Should not raise
                result = await loader_with_token.get_daily("000001.SZ", date(2024, 1, 31), 60)

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

    @staticmethod
    def _make_mock_pandas_df(rows: int = 1):
        import pandas as pd

        dates = pd.date_range("2024-01-01", periods=rows, freq="B")
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * rows,
                "trade_date": dates,
                "open": [10.0] * rows,
                "high": [10.5] * rows,
                "low": [9.5] * rows,
                "close": [10.2] * rows,
                "vol": [1000000] * rows,
                "amount": [10000000.0] * rows,
            }
        )


# ---------------------------------------------------------------------------
# NFR-0100 AC-1: No module-top-level quantide imports
# ---------------------------------------------------------------------------


class TestNFR0100ModuleTopLevel:
    """AC-NFR0100-01: quantide_adapter.py must have zero module-top-level quantide imports."""

    def test_no_top_level_quantide_import(self):
        """WHEN grepping for module-top-level ^import quantide|^from quantide THEN no match."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        content = src_path.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Only flag lines that start at column 0 (module top level)
            if not line or line[0] in (" ", "\t"):
                continue
            if stripped.startswith("import quantide") or stripped.startswith("from quantide"):
                assert False, f"Line {i}: module-top-level quantide import found: {stripped!r}"

    def test_no_top_level_quantide_import_ast(self):
        """WHEN parsing AST THEN all quantide imports are inside functions."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        tree = ast.parse(src_path.read_text())

        # Walk Import and ImportFrom nodes
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "quantide" or alias.name.startswith("quantide."):
                        assert self._is_inside_function(node, tree), (
                            f"quantide import '{alias.name}' found at module top level"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module == "quantide" or node.module.startswith("quantide.")
                ):
                    assert self._is_inside_function(node, tree), (
                        f"quantide from-import '{node.module}' found at module top level"
                    )

    @staticmethod
    def _is_inside_function(node: ast.AST, tree: ast.AST) -> bool:
        """Check if a node is inside a FunctionDef or AsyncFunctionDef."""
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                if child is node:
                    current = parent
                    while current is not None:
                        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            return True
                        # Walk up
                        for p in ast.walk(tree):
                            for c in ast.iter_child_nodes(p):
                                if c is current:
                                    current = p
                                    break
                            else:
                                continue
                            break
                        else:
                            break
                    return False
        return False


# ---------------------------------------------------------------------------
# NFR-0100 AC-2: Function-scope quantide imports exist
# ---------------------------------------------------------------------------


class TestNFR0100FunctionScopeImports:
    """AC-NFR0100-02: quantide_adapter.py must have >=2 function-scope quantide imports."""

    def test_at_least_two_quantide_imports(self):
        """WHEN grepping for 'from quantide' THEN >=2 matches (TushareFetcher + fetch_calendar)."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        content = src_path.read_text()
        lines = [line for line in content.split("\n") if "from quantide" in line]

        assert len(lines) >= 2, (
            f"Expected at least 2 function-scope quantide imports, got {len(lines)}: {lines}"
        )

    def test_tushare_fetcher_import_present(self):
        """WHEN checking imports THEN TushareFetcher import is present."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        content = src_path.read_text()
        assert "TushareFetcher" in content, "quantide_adapter.py must import TushareFetcher"

    def test_fetch_calendar_import_present(self):
        """WHEN checking imports THEN fetch_calendar import is present."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        content = src_path.read_text()
        assert "fetch_calendar" in content, (
            "quantide_adapter.py must import fetch_calendar from quantide"
        )


# ---------------------------------------------------------------------------
# NFR-0100 AC-4: Business symbol whitelist — no non-data quantide imports
# ---------------------------------------------------------------------------


class TestNFR0100BusinessSymbolWhitelist:
    """AC-NFR0100-04: no quantide.service/portfolio/backtest/core imports,
    AND no quantide.data.models.calendar or quantide.core.enums imports."""

    def test_no_non_whitelist_quantide_imports(self):
        """WHEN grepping for banned quantide.* submodules THEN no matches."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        content = src_path.read_text()

        banned_patterns = [
            "quantide.service",
            "quantide.portfolio",
            "quantide.backtest",
            "quantide.core.scheduler",
            "quantide.data.models.calendar",
            "quantide.core.enums",
        ]
        for pattern in banned_patterns:
            assert pattern not in content, f"Banned quantide import found: {pattern}"

    def test_no_calendar_or_frame_type_import(self):
        """WHEN checking imports THEN no Calendar/FrameType from quantide.data.models.calendar."""
        src_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "trader_off"
            / "data"
            / "quantide_adapter.py"
        )
        content = src_path.read_text()
        assert "quantide.data.models.calendar" not in content, (
            "quantide.data.models.calendar import is forbidden; use fetch_calendar instead"
        )
        assert "quantide.core.enums" not in content, (
            "quantide.core.enums import is forbidden; use fetch_calendar instead"
        )


# ---------------------------------------------------------------------------
# NFR-0100 AC-5: Integration layer isolation
# ---------------------------------------------------------------------------


class TestNFR0100IntegrationIsolation:
    """AC-NFR0100-05: No other data/ modules have top-level quantide imports."""

    def test_no_top_level_quantide_in_other_data_modules(self):
        """WHEN checking all src/trader_off/data/*.py THEN only quantide_adapter has quantide."""
        data_dir = Path(__file__).resolve().parents[3] / "src" / "trader_off" / "data"
        for py_file in data_dir.glob("*.py"):
            if py_file.name == "quantide_adapter.py":
                continue  # This file is allowed
            content = py_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip()
                if stripped.startswith("import quantide") or stripped.startswith("from quantide"):
                    assert False, (
                        f"{py_file.name} line {i}: top-level quantide import: {stripped!r}"
                    )
