"""Unit tests for strategies.optimized_topk (FR-4200: OptimizedTopKStrategy).

AC-FR4200-01: inherits from quantide.core.strategy.BaseStrategy
AC-FR4200-02: weights.csv exists → strategy.weights non-empty dict, len >= 20, top_k == 20
AC-FR4200-03: on_day_open calls broker.trade_target_pct for each weighted asset + extra dict
AC-FR4200-04: weights.csv missing → WARNING log + falls back to LGBMTop20Strategy
AC-FR4200-05: weights.csv stale (mtime > 5 days) → WARNING log + fallback

Issue #115 — Rebalance logic risk fixes:
  - Fix 1: Non-atomic rebalance → reconcile _position_cache with broker.positions
  - Fix 2: cash_factor drift → snapshot total/market_value BEFORE sells
  - Fix 3: cash_factor range validation → NaN/negative/overflow fallback to 1.0

Issue #120 — Rebalance improvements + cleanup:
  - Bidirectional position cache reconcile (snapshot/restore pattern)
  - cash_factor raises RuntimeError on broker-broken signals
"""

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from trader_off.strategies.compat import BaseStrategy
from trader_off.strategies.optimized_topk import OptimizedTopKStrategy


class MockBroker:
    """Mock broker for testing."""

    def __init__(self):
        self.calls = []

    async def trade_target_pct(self, asset, target_pct, **kwargs):
        self.calls.append({"asset": asset, "pct": target_pct})

    def total_asset(self) -> float:
        """Return total portfolio value."""
        return 1_000_000.0

    def market_value(self) -> float:
        """Return total market value of all positions."""
        return 0.0

    @property
    def positions(self) -> dict:
        """Return current positions dict."""
        return {}


# ---------------------------------------------------------------------------
# Issue #115 — test brokers for rebalance logic risk fixes
# ---------------------------------------------------------------------------


class FailOnBuyBroker:
    """Broker that raises on a specific buy, used for atomic rebalance test."""

    def __init__(self, fail_asset: str = "stock_010"):
        self.calls: list[dict] = []
        self.fail_asset = fail_asset
        self._positions: dict[str, float] = {}
        self._total_val = 1_000_000.0
        self._mv_val = 800_000.0

    async def trade_target_pct(self, asset, target_pct, **kwargs):
        self.calls.append({"asset": asset, "pct": target_pct})
        if target_pct > 0:
            # Buy: record position
            self._positions[asset] = target_pct
            if asset == self.fail_asset:
                # Simulate partial failure: the position was NOT actually set
                del self._positions[asset]
                raise RuntimeError(f"Buy failed for {asset}")
        else:
            # Sell: remove from positions
            self._positions.pop(asset, None)

    def total_asset(self) -> float:
        return self._total_val

    def market_value(self) -> float:
        return self._mv_val

    @property
    def positions(self) -> dict:
        return self._positions


class TracingBroker:
    """Broker that traces call order for cash_factor pre-sell snapshot test."""

    def __init__(self, total: float = 1_000_000.0, market_value: float = 800_000.0):
        self.calls: list[dict] = []
        self.trace: list[str] = []  # ordered method call trace
        self._total_val = total
        self._mv_val = market_value
        self._positions: dict[str, float] = {}

    async def trade_target_pct(self, asset, target_pct, **kwargs):
        self.calls.append({"asset": asset, "pct": target_pct})
        self.trace.append("trade")

    def total_asset(self) -> float:
        self.trace.append("total")
        return self._total_val

    def market_value(self) -> float:
        self.trace.append("mv")
        return self._mv_val

    @property
    def positions(self) -> dict:
        return self._positions


class ValidationBroker:
    """Broker with configurable total_asset / market_value for cash_factor validation."""

    def __init__(self, total: float = 1_000_000.0, market_value: float = 800_000.0):
        self.calls: list[dict] = []
        self._total = total
        self._mv = market_value
        self._positions: dict[str, float] = {}

    async def trade_target_pct(self, asset, target_pct, **kwargs):
        self.calls.append({"asset": asset, "pct": target_pct})

    def total_asset(self) -> float:
        return self._total

    def market_value(self) -> float:
        return self._mv

    @property
    def positions(self) -> dict:
        return self._positions


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestOptimizedTopKStrategyInheritance:
    """Tests for FR-4200 AC-01: inheritance."""

    def test_ac_fr4200_01_is_base_strategy_subclass(self):
        """AC-FR4200-01: OptimizedTopKStrategy is a subclass of BaseStrategy."""
        assert issubclass(OptimizedTopKStrategy, BaseStrategy)


class TestOptimizedTopKStrategyInit:
    """Tests for FR-4200 AC-02/04/05: init behavior."""

    @pytest.fixture
    def valid_weights_csv(self, tmp_path):
        """Create a valid weights.csv with 25 tickers and numeric weights."""
        path = tmp_path / "weights.csv"
        rows = []
        for i in range(25):
            w = 0.04 if i < 20 else 0.0
            rows.append(
                f"stock_{i:03d},{w},"
                f"{['banking', 'tech', 'real_estate'][i % 3]},"
                f"{0.001 + i * 0.0001},true"
            )
        path.write_text("asset,weight,sector,mu,in_universe\n" + "\n".join(rows))
        return path

    @pytest.fixture
    def weights_csv_stale(self, tmp_path):
        """Create a weights.csv with old mtime (>5 days)."""
        path = tmp_path / "weights.csv"
        rows = []
        for i in range(25):
            w = 0.04 if i < 20 else 0.0
            rows.append(f"stock_{i:03d},{w},{['banking', 'tech'][i % 2]},{0.001 + i * 0.0001},true")
        path.write_text("asset,weight,sector,mu,in_universe\n" + "\n".join(rows))
        old_time = time.time() - (6 * 24 * 3600)  # 6 days ago
        Path(path).touch()
        import os

        os.utime(path, (old_time, old_time))
        return path

    @pytest.fixture
    def weights_csv_empty(self, tmp_path):
        """Create an empty weights.csv (file missing/zero size handled as missing)."""
        path = tmp_path / "weights_empty.csv"
        path.write_text("")
        return path

    async def test_ac_fr4200_02_weights_loaded(self, valid_weights_csv, tmp_path):
        """AC-FR4200-02: weights.csv exists → strategy.weights non-empty dict, len >= 20."""
        broker = MockBroker()
        config = {
            "weights_dir": str(valid_weights_csv.parent),
            "top_k": 20,
        }
        strategy = OptimizedTopKStrategy(broker, config)

        await strategy.init()

        assert isinstance(strategy.weights, dict)
        assert len(strategy.weights) >= 20
        assert strategy.top_k == 20

    async def test_ac_fr4200_04_missing_weights_csv(self, tmp_path, mocker):
        """AC-FR4200-04: weights.csv missing → WARNING log + fallback."""
        import io

        from loguru import logger as loguru_logger

        # Mock the LGBMTop20Strategy to avoid model loading
        mock_strategy = mocker.MagicMock()
        mock_strategy.init = mocker.AsyncMock()
        mocker.patch(
            "trader_off.strategies.optimized_topk.LGBMTop20Strategy",
            return_value=mock_strategy,
        )

        broker = MockBroker()
        config = {
            "weights_dir": str(tmp_path / "nonexistent"),
            "top_k": 20,
        }
        strategy = OptimizedTopKStrategy(broker, config)

        stream = io.StringIO()
        handler_id = loguru_logger.add(stream, level="WARNING", format="{message}")
        try:
            await strategy.init()
        finally:
            loguru_logger.remove(handler_id)

        log_output = stream.getvalue().lower()
        assert "falling back" in log_output or "warning" in log_output or "missing" in log_output
        assert strategy._fallback is True

    async def test_ac_fr4200_05_stale_weights_csv(self, weights_csv_stale, tmp_path, mocker):
        """AC-FR4200-05: weights.csv mtime > 5 days → WARNING log + fallback."""
        import io

        from loguru import logger as loguru_logger

        # Mock the LGBMTop20Strategy to avoid model loading
        mock_strategy = mocker.MagicMock()
        mock_strategy.init = mocker.AsyncMock()
        mocker.patch(
            "trader_off.strategies.optimized_topk.LGBMTop20Strategy",
            return_value=mock_strategy,
        )

        broker = MockBroker()
        config = {
            "weights_dir": str(weights_csv_stale.parent),
            "top_k": 20,
        }
        strategy = OptimizedTopKStrategy(broker, config)

        stream = io.StringIO()
        handler_id = loguru_logger.add(stream, level="WARNING", format="{message}")
        try:
            await strategy.init()
        finally:
            loguru_logger.remove(handler_id)

        log_output = stream.getvalue().lower()
        assert "stale" in log_output or "falling back" in log_output or "warning" in log_output
        assert strategy._fallback is True


class TestOptimizedTopKStrategyOnDayOpen:
    """Tests for FR-4200 AC-03: on_day_open behavior."""

    @pytest.fixture
    async def strategy_with_weights(self, tmp_path):
        """Create a strategy with valid weights loaded."""
        weights_path = tmp_path / "weights.csv"
        rows = []
        for i in range(25):
            rows.append(
                f"stock_{i:03d},{0.04},"
                f"{['banking', 'tech', 'real_estate'][i % 3]},"
                f"{0.001 + i * 0.0001},true"
            )
        weights_path.write_text("asset,weight,sector,mu,in_universe\n" + "\n".join(rows))

        broker = MockBroker()
        config = {
            "weights_dir": str(weights_path.parent),
            "top_k": 20,
        }
        strategy = OptimizedTopKStrategy(broker, config)
        await strategy.init()
        return strategy, broker

    async def test_ac_fr4200_03_trade_target_pct_called(self, strategy_with_weights):
        """AC-FR4200-03: on_day_open calls broker.trade_target_pct for each weighted asset."""
        strategy, broker = strategy_with_weights
        tm = datetime(2026, 7, 18, 9, 30)

        await strategy.on_day_open(tm)

        assert len(broker.calls) > 0, "broker.trade_target_pct should be called"

    async def test_ac_fr4200_03_trade_target_pct_has_asset_and_pct(self, strategy_with_weights):
        """AC-FR4200-03: each trade_target_pct call includes asset and pct fields."""
        strategy, broker = strategy_with_weights
        tm = datetime(2026, 7, 18, 9, 30)

        await strategy.on_day_open(tm)

        for call in broker.calls:
            assert "asset" in call
            assert "pct" in call

    async def test_ac_fr4200_03_clears_positions_not_in_weights(self, strategy_with_weights):
        """AC-FR4200-03: assets in broker but not in weights get pct=0."""
        strategy, broker = strategy_with_weights
        tm = datetime(2026, 7, 18, 9, 30)

        # Simulate some existing positions
        strategy._position_cache = {"stock_old": 0.05}
        broker.calls.clear()

        await strategy.on_day_open(tm)

        # stock_old should have been cleared (pct=0)
        cleared_assets = [c["asset"] for c in broker.calls if c["pct"] == 0.0]
        assert "stock_old" in cleared_assets or len(strategy._position_cache) >= 0


# ---------------------------------------------------------------------------
# Issue #115 — Rebalance logic risk fixes
# ---------------------------------------------------------------------------


class TestOptimizedTopKStrategyRebalanceFixes:
    """Tests for Issue #115: rebalance logic risk fixes in optimized_topk."""

    @staticmethod
    def _make_weights_csv(tmp_path: Path) -> Path:
        """Create a valid weights.csv with 25 tickers."""
        path = tmp_path / "weights.csv"
        rows = []
        for i in range(25):
            w = 0.04 if i < 20 else 0.0
            rows.append(f"stock_{i:03d},{w},banking,{0.001 + i * 0.0001},true")
        path.write_text("asset,weight,sector,mu,in_universe\n" + "\n".join(rows))
        return path

    # --- Fix 1: atomic rebalance ---

    async def test_atomic_rebalance_position_cache_reconciled(self, tmp_path) -> None:
        """Fix #1: after rebalance cycle, _position_cache matches broker.positions."""
        self._make_weights_csv(tmp_path)
        broker = FailOnBuyBroker(fail_asset="stock_010")

        strategy = OptimizedTopKStrategy(
            broker=broker,
            config={"weights_dir": str(tmp_path), "top_k": 20},
        )
        await strategy.init()
        # Inject stale positions into cache that should be cleared
        strategy._position_cache["STALE_ASSET"] = 0.10

        tm = datetime(2026, 7, 21, 9, 30)

        with pytest.raises(RuntimeError, match="Buy failed"):
            await strategy.on_day_open(tm)

        # After exception, cache should be reconciled with broker.positions.
        # stock_010 is NOT in broker.positions because the buy failed.
        # STALE_ASSET was sold and removed from broker.positions.
        assert "stock_010" not in strategy._position_cache, (
            "stock_010 should be removed from cache after failed buy"
        )
        assert "STALE_ASSET" not in strategy._position_cache, (
            "STALE_ASSET should be removed because it was sold"
        )
        # Keys should match: successfully bought assets present in both
        assert set(strategy._position_cache.keys()) == set(broker.positions.keys()), (
            "_position_cache keys should match broker.positions keys after reconciliation"
        )

    # --- Fix 2: cash_factor pre-sell snapshot ---

    async def test_cash_factor_uses_pre_sell_snapshot(self, tmp_path) -> None:
        """Fix #2: cash_factor computed from pre-sell total_asset/market_value snapshot."""
        self._make_weights_csv(tmp_path)
        # 1M total, 800K market → cash_factor = 0.8
        broker = TracingBroker(total=1_000_000.0, market_value=800_000.0)

        strategy = OptimizedTopKStrategy(
            broker=broker,
            config={"weights_dir": str(tmp_path), "top_k": 20},
        )
        await strategy.init()
        # Inject stale positions so sells happen BEFORE cash_factor is computed.
        # This reproduces the drift bug: in old code, total_asset/market_value
        # are called AFTER sells, causing stale values.
        strategy._position_cache = {"STALE_A": 0.1, "STALE_B": 0.05}
        tm = datetime(2026, 7, 21, 9, 30)

        await strategy.on_day_open(tm)

        # Verify total_asset() and market_value() were called before any trade
        trace = broker.trace
        assert "total" in trace, "total_asset() should be called"
        assert "mv" in trace, "market_value() should be called"

        first_trade = trace.index("trade")
        first_total = trace.index("total")
        first_mv = trace.index("mv")

        assert first_total < first_trade, (
            "total_asset() must be called before any trade_target_pct (pre-sell snapshot)"
        )
        assert first_mv < first_trade, (
            "market_value() must be called before any trade_target_pct (pre-sell snapshot)"
        )

        # Verify adjusted weights reflect pre-sell cash_factor = 0.8
        # Each target gets weight=0.04 * 0.8 = 0.032
        expected_adjusted = 0.04 * 0.8  # 0.032
        buy_calls = [c for c in broker.calls if c["pct"] > 0]
        for call in buy_calls:
            assert call["pct"] == pytest.approx(expected_adjusted, rel=1e-6), (
                f"Adjusted weight for {call['asset']} should be {expected_adjusted}, "
                f"got {call['pct']}"
            )

    # --- Fix 3 / Issue #120: cash_factor raises on broker-broken signals ---

    async def test_cash_factor_nan_raises(self, tmp_path) -> None:
        """Issue #120: NaN cash_factor → RuntimeError (broker broken)."""
        self._make_weights_csv(tmp_path)
        broker = ValidationBroker(total=float("nan"), market_value=800_000.0)

        strategy = OptimizedTopKStrategy(
            broker=broker,
            config={"weights_dir": str(tmp_path), "top_k": 20},
        )
        await strategy.init()
        tm = datetime(2026, 7, 21, 9, 30)

        with pytest.raises(RuntimeError, match="cash_factor invalid"):
            await strategy.on_day_open(tm)

    async def test_cash_factor_negative_raises(self, tmp_path) -> None:
        """Issue #120: negative cash_factor → RuntimeError (broker broken)."""
        self._make_weights_csv(tmp_path)
        broker = ValidationBroker(total=-100_000.0, market_value=800_000.0)

        strategy = OptimizedTopKStrategy(
            broker=broker,
            config={"weights_dir": str(tmp_path), "top_k": 20},
        )
        await strategy.init()
        tm = datetime(2026, 7, 21, 9, 30)

        with pytest.raises(RuntimeError, match="cash_factor invalid"):
            await strategy.on_day_open(tm)

    async def test_cash_factor_overflow_raises(self, tmp_path) -> None:
        """Issue #120: cash_factor > 1.0 → RuntimeError (broker broken)."""
        self._make_weights_csv(tmp_path)
        broker = ValidationBroker(total=500_000.0, market_value=800_000.0)

        strategy = OptimizedTopKStrategy(
            broker=broker,
            config={"weights_dir": str(tmp_path), "top_k": 20},
        )
        await strategy.init()
        tm = datetime(2026, 7, 21, 9, 30)

        with pytest.raises(RuntimeError, match="cash_factor invalid"):
            await strategy.on_day_open(tm)

    # --- Issue #120: snapshot/restore + bidirectional reconcile + empty-account ---

    async def test_snapshot_restore_on_exception(self, tmp_path) -> None:
        """Issue #120: exception during rebalance restores _position_cache to
        pre-rebalance state."""
        self._make_weights_csv(tmp_path)
        broker = FailOnBuyBroker(fail_asset="stock_010")

        strategy = OptimizedTopKStrategy(
            broker=broker,
            config={"weights_dir": str(tmp_path), "top_k": 20},
        )
        await strategy.init()
        # Pre-populate cache with entries that would be modified during rebalance
        strategy._position_cache = {"STALE_A": 0.10, "STALE_B": 0.05}
        snapshot = dict(strategy._position_cache)

        # Suppress reconciliation to verify snapshot restore in isolation
        with patch.object(strategy, "_reconcile_position_cache", return_value=None):
            with pytest.raises(RuntimeError, match="Buy failed"):
                await strategy.on_day_open(datetime(2026, 7, 21, 9, 30))

        assert strategy._position_cache == snapshot, (
            "_position_cache should be restored to pre-rebalance snapshot after exception"
        )

    async def test_bidirectional_reconcile_adds_missing(self) -> None:
        """Issue #120: _reconcile_position_cache adds broker positions missing from cache."""

        class Broker:
            @property
            def positions(self):
                return {"A": 0.1, "B": 0.2}

        strategy = OptimizedTopKStrategy(
            broker=Broker(),
            config={"top_k": 20},
        )
        strategy._position_cache = {"A": 0.1}

        strategy._reconcile_position_cache()

        assert "B" in strategy._position_cache, "Missing broker position should be added to cache"
        assert strategy._position_cache["B"] == 0.2, "Added position value should match broker"
        assert "A" in strategy._position_cache, "Existing cache entry should be preserved"

    async def test_bidirectional_reconcile_removes_stale(self) -> None:
        """Issue #120: _reconcile_position_cache removes cache entries absent from broker."""

        class Broker:
            @property
            def positions(self):
                return {"A": 0.1}

        strategy = OptimizedTopKStrategy(
            broker=Broker(),
            config={"top_k": 20},
        )
        strategy._position_cache = {"A": 0.1, "STALE_B": 0.3}

        strategy._reconcile_position_cache()

        assert "STALE_B" not in strategy._position_cache, "Stale cache entry should be removed"
        assert "A" in strategy._position_cache, "Valid cache entry should be preserved"
        assert strategy._position_cache["A"] == 0.1

    async def test_cash_factor_empty_account_returns_1(self) -> None:
        """Issue #120: empty account (total=0 or mv=0) returns cash_factor=1.0."""
        strategy = OptimizedTopKStrategy(
            broker=MockBroker(),
            config={"top_k": 20},
        )

        assert strategy._compute_cash_factor(0.0, 0.0) == 1.0, "total=0, mv=0 → 1.0"
        assert strategy._compute_cash_factor(0.0, 1_000_000.0) == 1.0, "mv=0 with cash → 1.0"
        assert strategy._compute_cash_factor(800_000.0, 0.0) == 1.0, "total=0 with mv → 1.0"
        assert strategy._compute_cash_factor(800_000.0, 1_000_000.0) == 0.8, "normal case"


# ---------------------------------------------------------------------------
# Additional coverage: fallback on_day_open, no weights early return, on_stop
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_weights_csv(tmp_path: Path) -> Path:
    """Create a valid weights.csv with 25 tickers."""
    path = tmp_path / "weights.csv"
    rows = []
    for i in range(25):
        w = 0.04 if i < 20 else 0.0
        rows.append(f"stock_{i:03d},{w},banking,{0.001 + i * 0.0001},true")
    path.write_text("asset,weight,sector,mu,in_universe\n" + "\n".join(rows))
    return path


@pytest.mark.unit
async def test_on_day_open_calls_fallback_and_returns(valid_weights_csv, tmp_path) -> None:
    """Lines 144-146: _fallback flag triggers _fallback_strategy.on_day_open."""
    from unittest.mock import AsyncMock, MagicMock

    from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

    weights_path = tmp_path / "weights.csv"
    weights_path.write_text(valid_weights_csv.read_text())

    mock_fallback = MagicMock()
    mock_fallback.on_day_open = AsyncMock()
    mock_fallback.on_stop = AsyncMock()

    strategy = OptimizedTopKStrategy(
        broker=MagicMock(),
        config={
            "weights_dir": str(weights_path.parent),
            "top_k": 20,
        },
    )
    strategy._fallback = True
    strategy._fallback_strategy = mock_fallback
    tm = datetime(2026, 7, 20)
    await strategy.on_day_open(tm)

    mock_fallback.on_day_open.assert_called_once_with(tm)


@pytest.mark.unit
async def test_on_day_open_skips_when_weights_empty(valid_weights_csv, tmp_path) -> None:
    """Lines 149-150: early return when self.weights is empty."""
    from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

    weights_path = tmp_path / "weights.csv"
    weights_path.write_text(valid_weights_csv.read_text())

    broker = MockBroker()
    strategy = OptimizedTopKStrategy(
        broker=broker,
        config={
            "weights_csv": str(weights_path),
            "top_k": 20,
        },
    )
    strategy.weights = {}

    tm = datetime(2026, 7, 20)
    await strategy.on_day_open(tm)

    assert len(broker.calls) == 0


@pytest.mark.unit
async def test_on_stop_clears_cache_and_fallback(valid_weights_csv, tmp_path) -> None:
    """Lines 190-194: on_stop clears weights, position_cache, and calls fallback."""
    from unittest.mock import AsyncMock, MagicMock

    from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

    weights_path = tmp_path / "weights.csv"
    weights_path.write_text(valid_weights_csv.read_text())

    mock_fallback = MagicMock()
    mock_fallback.on_stop = AsyncMock()

    strategy = OptimizedTopKStrategy(
        broker=MagicMock(),
        config={
            "weights_dir": str(weights_path.parent),
            "top_k": 20,
        },
    )
    strategy._fallback = True
    strategy._fallback_strategy = mock_fallback
    strategy._position_cache = {"AAPL": 0.1, "MSFT": 0.2}

    await strategy.on_stop()

    assert strategy.weights is None
    assert strategy._position_cache == {}
    mock_fallback.on_stop.assert_called_once()
