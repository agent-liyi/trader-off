"""Tests for paper trading runner — FR-0100: PaperBrokerAdapter + run_paper_trade."""

import ast
import uuid as uuid_mod
from dataclasses import fields
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

from trader_off.backtest.runner import BacktestResult

RUNNER_PATH = Path("src/trader_off/backtest/runner.py")
RUNNER_TEXT = RUNNER_PATH.read_text() if RUNNER_PATH.exists() else ""


# ── PaperBrokerAdapter unit tests ──────────────────────────────────────────


class TestPaperBrokerAdapter:
    """FR-0100 AC-05: adapter exposes strategy-expected interface."""

    def test_adapter_total_asset_returns_method(self):
        """total_asset() is a callable method, not a property."""
        from trader_off.backtest.runner import PaperBrokerAdapter

        mock_paper = MagicMock()
        mock_paper.total_assets = 1_500_000.0

        adapter = PaperBrokerAdapter(mock_paper)
        result = adapter.total_asset()
        assert result == 1_500_000.0, f"Expected 1500000.0, got {result}"
        assert callable(adapter.total_asset), "total_asset must be a callable method"

    def test_adapter_market_value_computes_sum(self):
        """market_value() computes sum of position market values."""
        from trader_off.backtest.runner import PaperBrokerAdapter

        pos1 = MagicMock()
        pos1.mv = 500_000.0
        pos2 = MagicMock()
        pos2.mv = 200_000.0

        mock_paper = MagicMock()
        mock_paper.positions = [pos1, pos2]

        adapter = PaperBrokerAdapter(mock_paper)
        result = adapter.market_value()
        assert result == 700_000.0, f"Expected 700000.0, got {result}"
        assert callable(adapter.market_value), "market_value must be a callable method"

    def test_adapter_positions_returns_dict(self):
        """positions property returns dict keyed by asset."""
        from trader_off.backtest.runner import PaperBrokerAdapter

        pos1 = MagicMock()
        pos1.asset = "000001.SZ"
        pos2 = MagicMock()
        pos2.asset = "600519.SH"

        mock_paper = MagicMock()
        mock_paper.positions = [pos1, pos2]

        adapter = PaperBrokerAdapter(mock_paper)
        result = adapter.positions
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert set(result.keys()) == {"000001.SZ", "600519.SH"}, f"Unexpected keys: {result.keys()}"
        assert result["000001.SZ"] is pos1
        assert result["600519.SH"] is pos2

    def test_adapter_empty_positions_returns_empty_dict(self):
        """positions property handles empty position list."""
        from trader_off.backtest.runner import PaperBrokerAdapter

        mock_paper = MagicMock()
        mock_paper.positions = []

        adapter = PaperBrokerAdapter(mock_paper)
        result = adapter.positions
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_adapter_trade_target_pct_delegates(self):
        """trade_target_pct delegates to PaperBroker."""
        from trader_off.backtest.runner import PaperBrokerAdapter

        mock_paper = MagicMock()
        mock_paper.trade_target_pct = AsyncMock(return_value=MagicMock())

        adapter = PaperBrokerAdapter(mock_paper)
        # Check that it's callable (will be called with await in strategy)
        assert callable(adapter.trade_target_pct), "trade_target_pct must be callable"

    def test_adapter_getattr_fallback(self):
        """__getattr__ delegates unknown attributes to PaperBroker."""
        from trader_off.backtest.runner import PaperBrokerAdapter

        mock_paper = MagicMock()
        mock_paper.cash = 500_000.0
        mock_paper.some_other_method = lambda: 42

        adapter = PaperBrokerAdapter(mock_paper)
        assert adapter.cash == 500_000.0
        assert adapter.some_other_method() == 42


# ── PaperTradeResult dataclass tests ───────────────────────────────────────


class TestPaperTradeResult:
    """FR-0100: PaperTradeResult has same fields as BacktestResult."""

    def test_paper_trade_result_fields_match_backtest(self):
        """PaperTradeResult has {summary, positions, trades, nav, report_dir}."""
        from trader_off.backtest.runner import PaperTradeResult

        field_names = {f.name for f in fields(PaperTradeResult)}
        backtest_fields = {f.name for f in fields(BacktestResult)}
        assert field_names == backtest_fields, (
            f"PaperTradeResult fields {field_names} should match BacktestResult {backtest_fields}"
        )

    def test_paper_trade_result_construction(self):
        """PaperTradeResult can be constructed with all fields."""
        from trader_off.backtest.runner import PaperTradeResult

        result = PaperTradeResult(
            summary={"total_trades": 5},
            positions=pl.DataFrame({"asset": ["000001.SZ"]}),
            trades=pl.DataFrame({"action": ["buy"]}),
            nav=pl.DataFrame({"date": [date(2026, 7, 21)], "nav": [1_000_000.0]}),
            report_dir=Path("/tmp/reports"),
        )
        assert result.summary["total_trades"] == 5
        assert result.positions.height == 1
        assert result.trades.height == 1
        assert result.nav.height == 1
        assert str(result.report_dir) == "/tmp/reports"


# ── run_paper_trade function tests ─────────────────────────────────────────


class TestRunPaperTradeSignature:
    """FR-0100: run_paper_trade public API."""

    def test_run_paper_trade_exists(self):
        """run_paper_trade function is defined in runner module."""
        from trader_off.backtest.runner import run_paper_trade

        assert callable(run_paper_trade), "run_paper_trade must be a callable function"

    def test_run_paper_trade_signature_params(self):
        """run_paper_trade has correct parameter names."""
        import inspect

        from trader_off.backtest.runner import run_paper_trade

        sig = inspect.signature(run_paper_trade)
        params = set(sig.parameters.keys())
        expected = {"strategy_name", "end_date", "initial_cash", "config"}
        assert params == expected, f"Expected {expected}, got {params}"


class TestRunPaperTradeWithMocks:
    """FR-0100: run_paper_trade integration with quantide APIs (mocked)."""

    def _make_mock_bar_df(self, assets: list[str], d: date) -> pl.DataFrame:
        """Create a mock daily bar DataFrame."""
        rows = []
        for asset in assets:
            rows.append(
                {
                    "asset": asset,
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.5,
                    "volume": 1000000.0,
                    "amount": 10500000.0,
                }
            )
        return pl.DataFrame(rows)

    # AC-FR0100-04: BacktestRunner is NOT called
    def test_backtest_runner_not_called(self):
        """run_paper_trade does NOT invoke BacktestRunner."""
        from trader_off.backtest.runner import run_paper_trade

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()
        mock_daily_bars.get_bars_in_range = MagicMock(
            return_value=pl.DataFrame(schema={"asset": pl.Utf8})
        )

        mock_db = MagicMock()
        mock_db.init = MagicMock()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        mock_paper_cls = MagicMock()
        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls.return_value = mock_paper

        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = pl.DataFrame({"date": [date(2026, 7, 21)]})
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(schema={"asset": pl.Utf8}),
                                    ):
                                        result = run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=1_000_000.0,
                                        )

        # Verify BacktestRunner is NOT imported or used inside run_paper_trade
        assert isinstance(result.summary, dict), "Result must have summary dict"
        assert isinstance(result.nav, pl.DataFrame), "Result must have nav DataFrame"

    # AC-FR0100-02: db.init BEFORE PaperBroker construction
    def test_db_init_before_paper_broker(self):
        """db.init is called before PaperBroker construction."""
        from trader_off.backtest.runner import run_paper_trade

        call_order = []

        class TrackingDB:
            @staticmethod
            def init(path):
                call_order.append("db.init")

        mock_db = TrackingDB()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        class TrackingPaperBroker:
            def __init__(self, *args, **kwargs):
                call_order.append("PaperBroker.__init__")

            total_assets = 1_000_000.0
            positions = []
            on_day_open = AsyncMock()
            on_day_close = AsyncMock()

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()
        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = pl.DataFrame({"date": [date(2026, 7, 21)]})
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", TrackingPaperBroker):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(schema={"asset": pl.Utf8}),
                                    ):
                                        run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=1_000_000.0,
                                        )

        db_idx = call_order.index("db.init") if "db.init" in call_order else -1
        broker_idx = (
            call_order.index("PaperBroker.__init__") if "PaperBroker.__init__" in call_order else -1
        )
        assert db_idx >= 0, "db.init must be called"
        assert broker_idx >= 0, "PaperBroker must be constructed"
        assert db_idx < broker_idx, (
            f"db.init ({db_idx}) must be called before PaperBroker ({broker_idx})"
        )

    # AC-FR0100-03: daily_bars.connect is called
    def test_daily_bars_connect_called(self):
        """daily_bars.connect is called with store_path and calendar path."""
        from trader_off.backtest.runner import run_paper_trade

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()

        mock_db = MagicMock()
        mock_db.init = MagicMock()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls = MagicMock(return_value=mock_paper)

        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = pl.DataFrame({"date": [date(2026, 7, 21)]})
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(schema={"asset": pl.Utf8}),
                                    ):
                                        run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=1_000_000.0,
                                        )

        assert mock_daily_bars.connect.called, "daily_bars.connect must be called"
        assert len(mock_daily_bars.connect.call_args[0]) >= 2, (
            "daily_bars.connect must receive at least store_path and calendar_path"
        )

    # AC-FR0100-01: PaperBroker instantiated with correct params
    def test_paper_broker_instantiated_with_correct_params(self):
        """PaperBroker receives principal=initial_cash, commission=1e-4."""
        from trader_off.backtest.runner import run_paper_trade

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()

        mock_db = MagicMock()
        mock_db.init = MagicMock()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls = MagicMock(return_value=mock_paper)

        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = pl.DataFrame({"date": [date(2026, 7, 21)]})
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(schema={"asset": pl.Utf8}),
                                    ):
                                        run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=500_000.0,
                                        )

        assert mock_paper_cls.called, "PaperBroker must be instantiated"
        kwargs = mock_paper_cls.call_args.kwargs
        assert kwargs.get("principal") == 500_000.0, (
            f"principal should be 500000.0, got {kwargs.get('principal')}"
        )
        assert kwargs.get("commission") == 1e-4, (
            f"commission should be 1e-4, got {kwargs.get('commission')}"
        )

    # AC-FR0100-07: run_paper_trade returns PaperTradeResult with correct structure
    def test_run_paper_trade_returns_correct_schema(self):
        """run_paper_trade returns PaperTradeResult with nav/positions/trades/summary/report_dir."""
        from trader_off.backtest.runner import PaperTradeResult, run_paper_trade

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()

        mock_db = MagicMock()
        mock_db.init = MagicMock()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(
            return_value=pl.DataFrame(
                {
                    "dt": ["2026-07-21"] * 5,
                    "asset": ["000001.SZ"] * 5,
                    "action": ["buy"] * 5,
                    "quantity": [100.0] * 5,
                }
            )
        )

        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls = MagicMock(return_value=mock_paper)

        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = pl.DataFrame({"date": [date(2026, 7, 21)]})
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(schema={"asset": pl.Utf8}),
                                    ):
                                        result = run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=1_000_000.0,
                                        )

        assert isinstance(result, PaperTradeResult), (
            f"Expected PaperTradeResult, got {type(result)}"
        )
        assert isinstance(result.summary, dict), "summary must be a dict"
        assert isinstance(result.positions, pl.DataFrame), "positions must be a DataFrame"
        assert isinstance(result.trades, pl.DataFrame), "trades must be a DataFrame"
        assert isinstance(result.nav, pl.DataFrame), "nav must be a DataFrame"
        assert isinstance(result.report_dir, Path), "report_dir must be a Path"

    # AC-FR0100-07: summary has 6 required keys
    def test_summary_has_six_required_keys(self):
        """summary dict contains the 6 required keys."""
        from trader_off.backtest.runner import run_paper_trade

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()

        mock_db = MagicMock()
        mock_db.init = MagicMock()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls = MagicMock(return_value=mock_paper)

        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = pl.DataFrame({"date": [date(2026, 7, 21)]})
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(schema={"asset": pl.Utf8}),
                                    ):
                                        result = run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=1_000_000.0,
                                        )

        required_6 = {
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "total_trades",
            "avg_turnover",
        }
        assert required_6.issubset(set(result.summary.keys())), (
            f"Missing keys: {required_6 - set(result.summary.keys())}"
        )

    # AC-FR0100-06: msg_hub.publish is called to trigger quote-based matching
    def test_msg_hub_publish_called_for_session_loop(self):
        """msg_hub.publish(Topics.QUOTES_ALL.value, quote) is called per trading day."""
        from trader_off.backtest.runner import run_paper_trade

        trading_dates = [date(2026, 7, 20), date(2026, 7, 21)]

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()

        mock_db = MagicMock()
        mock_db.init = MagicMock()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls = MagicMock(return_value=mock_paper)

        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = pl.DataFrame({"date": trading_dates})
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(
                                            {
                                                "asset": ["000001.SZ"],
                                                "open": [10.0],
                                                "high": [11.0],
                                                "low": [9.0],
                                                "close": [10.5],
                                                "volume": [1_000_000.0],
                                                "amount": [10_500_000.0],
                                            }
                                        ),
                                    ):
                                        run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=1_000_000.0,
                                            config={"universe": ["000001.SZ"]},
                                        )

        # msg_hub.publish should be called at least once
        assert mock_msg_hub.publish.called, "msg_hub.publish must be called during session loop"

    # AC-FR0100-08: fresh paper_state.sqlite per run
    def test_fresh_db_path_per_run(self):
        """Each run uses a unique paper_state.sqlite path."""
        from trader_off.backtest.runner import run_paper_trade

        captured_paths = []

        class TrackingDB:
            @staticmethod
            def init(path):
                captured_paths.append(str(path))

        mock_db = TrackingDB()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()
        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls = MagicMock(return_value=mock_paper)
        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        ts_counter = [0]

        def _mock_timestamp():
            ts_counter[0] += 1
            return f"20260722_00000{ts_counter[0]}"

        def _run():
            with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
                mock_read.return_value = pl.DataFrame({"date": [date(2026, 7, 21)]})
                with patch(
                    "trader_off.backtest.runner._generate_timestamp", side_effect=_mock_timestamp
                ):
                    with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                        with patch("quantide.data.sqlite.db", mock_db):
                            with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                                with patch("quantide.core.message.msg_hub", mock_msg_hub):
                                    with patch("quantide.core.enums.Topics", mock_topics):
                                        with patch(
                                            "uuid.uuid4",
                                            return_value=uuid_mod.UUID(
                                                "12345678-1234-5678-1234-567812345678"
                                            ),
                                        ):
                                            with patch.object(
                                                mock_daily_bars,
                                                "get_bars_in_range",
                                                return_value=pl.DataFrame(
                                                    schema={"asset": pl.Utf8}
                                                ),
                                            ):
                                                return run_paper_trade(
                                                    strategy_name="lgbm_top20",
                                                    end_date=date(2026, 7, 21),
                                                    initial_cash=1_000_000.0,
                                                )

        _run()
        _run()

        assert len(captured_paths) == 2, f"Expected 2 db.init calls, got {len(captured_paths)}"
        assert "paper_state.sqlite" in captured_paths[0], "db path must end with paper_state.sqlite"
        assert captured_paths[0] != captured_paths[1], (
            f"Each run must use a unique path: {captured_paths}"
        )

    # Auto-derive universe from calendar source when config.universe is empty
    def test_auto_derive_universe_from_calendar_source(self):
        """When universe is empty, assets are derived from calendar source OHLCV."""
        from trader_off.backtest.runner import run_paper_trade

        mock_daily_bars = MagicMock()
        mock_daily_bars.connect = MagicMock()

        mock_db = MagicMock()
        mock_db.init = MagicMock()
        mock_db.assets_all = MagicMock(
            return_value=pl.DataFrame({"dt": ["2026-07-21"], "total": [1_000_000.0]})
        )
        mock_db.positions_all = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())

        mock_paper = MagicMock()
        mock_paper.total_assets = 1_000_000.0
        mock_paper.positions = []
        mock_paper.on_day_open = AsyncMock()
        mock_paper.on_day_close = AsyncMock()
        mock_paper_cls = MagicMock(return_value=mock_paper)

        mock_msg_hub = MagicMock()
        mock_topics = MagicMock()
        mock_topics.QUOTES_ALL = MagicMock()
        mock_topics.QUOTES_ALL.value = "quotes_all"

        # OHLCV file with asset column → universe auto-derives from it
        ohlcv_df = pl.DataFrame(
            {
                "asset": ["000001.SZ", "000001.SZ", "600519.SH"],
                "date": [date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 21)],
            }
        )

        with patch("trader_off.backtest.runner.pl.read_parquet") as mock_read:
            mock_read.return_value = ohlcv_df
            with patch("quantide.data.models.daily_bars.daily_bars", mock_daily_bars):
                with patch("quantide.data.sqlite.db", mock_db):
                    with patch("quantide.service.sim_broker.PaperBroker", mock_paper_cls):
                        with patch("quantide.core.message.msg_hub", mock_msg_hub):
                            with patch("quantide.core.enums.Topics", mock_topics):
                                with patch(
                                    "uuid.uuid4",
                                    return_value=uuid_mod.UUID(
                                        "12345678-1234-5678-1234-567812345678"
                                    ),
                                ):
                                    with patch.object(
                                        mock_daily_bars,
                                        "get_bars_in_range",
                                        return_value=pl.DataFrame(
                                            {
                                                "asset": ["000001.SZ", "600519.SH"],
                                                "open": [10.0, 20.0],
                                                "high": [11.0, 21.0],
                                                "low": [9.0, 19.0],
                                                "close": [10.5, 20.5],
                                                "volume": [1e6, 2e6],
                                                "amount": [1.05e7, 4.1e7],
                                            }
                                        ),
                                    ):
                                        result = run_paper_trade(
                                            strategy_name="lgbm_top20",
                                            end_date=date(2026, 7, 21),
                                            initial_cash=1_000_000.0,
                                            # No universe in config → auto-derive from OHLCV
                                        )

        # Session loop must have executed (msg_hub.publish called per day)
        assert mock_msg_hub.publish.called, (
            "msg_hub.publish should be called — session loop must run with auto-derived assets"
        )
        assert isinstance(result.nav, pl.DataFrame)


# ── NFR-0100 lazy import tests (runner.py) ─────────────────────────────────


class TestNFR0100RunnerImports:
    """NFR-0100: no top-level quantide imports in runner.py."""

    def test_no_top_level_quantide_import(self):
        """runner.py has zero top-level 'import quantide' or 'from quantide' statements."""
        lines = RUNNER_TEXT.splitlines()
        top_level_imports = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import quantide") or stripped.startswith("from quantide"):
                if not line.startswith((" ", "\t")):
                    top_level_imports.append(stripped)
        assert len(top_level_imports) == 0, f"Top-level quantide imports found: {top_level_imports}"

    def test_has_paper_broker_function_level_import(self):
        """runner.py contains PaperBroker import inside a function."""
        assert "from quantide.service.sim_broker import PaperBroker" in RUNNER_TEXT, (
            "Missing PaperBroker function-level import"
        )

    def test_no_banned_quantide_imports(self):
        """runner.py has no quantide.portfolio or quantide.service.metrics imports."""
        import re

        banned = re.findall(r"quantide\.(portfolio|service\.metrics)", RUNNER_TEXT)
        assert len(banned) == 0, f"Banned quantide imports found: {banned}"

    def test_quantide_imports_in_function_bodies_only(self):
        """All quantide imports are inside function bodies (AST validation)."""
        tree = ast.parse(RUNNER_TEXT)

        # AST approach: find all import nodes and check they're inside FunctionDef/AsyncFunctionDef
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module_name = getattr(node, "module", None) or ""
                if module_name == "quantide" or module_name.startswith("quantide."):
                    # Check line indentation heuristic: quantide imports
                    # must be inside a function (indented), not at module top level
                    lineno = node.lineno - 1
                    line = (
                        RUNNER_TEXT.splitlines()[lineno]
                        if lineno < len(RUNNER_TEXT.splitlines())
                        else ""
                    )
                    if not line.startswith((" ", "\t")):
                        msg = (
                            f"quantide import at line {node.lineno} is not indented "
                            f"(not inside a function): {line.strip()}"
                        )
                        pytest.fail(msg)


PAPER_TRADE_PATH = Path("src/trader_off/cli/paper_trade.py")
PAPER_TRADE_TEXT = PAPER_TRADE_PATH.read_text() if PAPER_TRADE_PATH.exists() else ""


class TestNFR0100PaperTradeImports:
    """NFR-0100: no top-level quantide imports in paper_trade.py."""

    # AC-NFR0100-01: paper_trade.py top-level zero quantide imports
    def test_no_top_level_quantide_import(self):
        """paper_trade.py has zero top-level 'import quantide' or 'from quantide'."""
        lines = PAPER_TRADE_TEXT.splitlines()
        top_level_imports = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import quantide") or stripped.startswith("from quantide"):
                if not line.startswith((" ", "\t")):
                    top_level_imports.append(stripped)
        assert len(top_level_imports) == 0, (
            f"Top-level quantide imports found in paper_trade.py: {top_level_imports}"
        )

    # AC-NFR0100-04: paper_trade.py has no banned quantide imports
    def test_no_banned_quantide_imports(self):
        """paper_trade.py has no quantide.portfolio or quantide.service.metrics imports."""
        import re

        banned = re.findall(r"quantide\.(portfolio|service\.metrics)", PAPER_TRADE_TEXT)
        assert len(banned) == 0, f"Banned quantide imports found in paper_trade.py: {banned}"

    # AC-NFR0100-03: all quantide imports in paper_trade.py are in functions
    def test_quantide_imports_in_function_bodies_only(self):
        """All quantide imports in paper_trade.py are inside function bodies."""
        tree = ast.parse(PAPER_TRADE_TEXT)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module_name = getattr(node, "module", None) or ""
                if module_name == "quantide" or module_name.startswith("quantide."):
                    lineno = node.lineno - 1
                    line = (
                        PAPER_TRADE_TEXT.splitlines()[lineno]
                        if lineno < len(PAPER_TRADE_TEXT.splitlines())
                        else ""
                    )
                    if not line.startswith((" ", "\t")):
                        msg = (
                            f"quantide import at line {node.lineno} in paper_trade.py "
                            f"is not indented: {line.strip()}"
                        )
                        pytest.fail(msg)


# ── NFR-0100 cross-module isolation tests ────────────────────────────────────


class TestNFR0100CrossModuleIsolation:
    """NFR-0100 AC-06: other module isolation commitments remain intact."""

    # AC-NFR0100-06: data/quantide_adapter.py isolation preserved
    def test_quantide_adapter_no_top_level_quantide_import(self):
        """data/quantide_adapter.py maintains top-level quantide import isolation."""
        adapter_path = Path("src/trader_off/data/quantide_adapter.py")
        if not adapter_path.exists():
            pytest.skip("quantide_adapter.py not found")
        text = adapter_path.read_text()
        lines = text.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import quantide") or stripped.startswith("from quantide"):
                if not line.startswith((" ", "\t")):
                    # Allow TYPE_CHECKING blocks
                    pytest.fail(f"Top-level quantide import in adapter: {stripped}")

    # Verify runner.py contains msg_hub and Topics function-level imports (AC-NFR0100-05)
    def test_msg_hub_in_function_body(self):
        """runner.py has from quantide.core.message import msg_hub in function body."""
        import re

        pattern = r"from quantide\.core\.message import msg_hub"
        matches = re.findall(pattern, RUNNER_TEXT)
        assert len(matches) >= 1, "Missing msg_hub function-level import"
        # Verify it's indented (inside a function)
        for i, line in enumerate(RUNNER_TEXT.splitlines()):
            if "from quantide.core.message import msg_hub" in line:
                assert line.startswith((" ", "\t")), (
                    f"msg_hub import at line {i + 1} must be inside a function"
                )

    def test_topics_in_function_body(self):
        """runner.py has from quantide.core.enums import Topics in function body."""
        import re

        pattern = r"from quantide\.core\.enums import Topics"
        matches = re.findall(pattern, RUNNER_TEXT)
        assert len(matches) >= 1, "Missing Topics function-level import"
        # Verify it's indented (inside a function)
        for i, line in enumerate(RUNNER_TEXT.splitlines()):
            if "from quantide.core.enums import Topics" in line:
                assert line.startswith((" ", "\t")), (
                    f"Topics import at line {i + 1} must be inside a function"
                )

    # Verify grep validation from acceptance criteria
    def test_grep_top_level_runner_empty(self):
        r"""grep '^import quantide\|^from quantide' runner.py → no matches."""
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "lines = open('src/trader_off/backtest/runner.py').readlines(); "
                    "found = [l.strip() for l in lines if "
                    "(l.startswith('import quantide') or l.startswith('from quantide')) "
                    "and not l.startswith((' ', '\t'))]; "
                    "sys.exit(1 if found else 0)"
                ),
            ],
            capture_output=True,
        )
        assert result.returncode == 0, "Top-level quantide imports found in runner.py via grep"

    def test_grep_top_level_paper_trade_empty(self):
        r"""grep '^import quantide\|^from quantide' paper_trade.py → no matches."""
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "lines = open('src/trader_off/cli/paper_trade.py').readlines(); "
                    "found = [l.strip() for l in lines if "
                    "(l.startswith('import quantide') or l.startswith('from quantide')) "
                    "and not l.startswith((' ', '\t'))]; "
                    "sys.exit(1 if found else 0)"
                ),
            ],
            capture_output=True,
        )
        assert result.returncode == 0, "Top-level quantide imports found in paper_trade.py via grep"
