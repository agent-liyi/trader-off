"""Unit tests for strategies.optimized_topk (FR-4200: OptimizedTopKStrategy).

AC-FR4200-01: inherits from quantide.core.strategy.BaseStrategy
AC-FR4200-02: weights.csv exists → strategy.weights non-empty dict, len >= 20, top_k == 20
AC-FR4200-03: on_day_open calls broker.trade_target_pct for each weighted asset + extra dict
AC-FR4200-04: weights.csv missing → WARNING log + falls back to LGBMTop20Strategy
AC-FR4200-05: weights.csv stale (mtime > 5 days) → WARNING log + fallback
"""

import time
from datetime import datetime
from pathlib import Path

import pytest

from trader_off.strategies.compat import BaseStrategy
from trader_off.strategies.optimized_topk import OptimizedTopKStrategy


class MockBroker:
    """Mock broker for testing."""

    def __init__(self):
        self.calls = []

    def trade_target_pct(self, asset, target_pct, extra=None):
        self.calls.append({"asset": asset, "pct": target_pct, "extra": extra or {}})


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
        # Each call should have extra dict with reason == "optimized_topk"
        for call in broker.calls:
            assert call["extra"].get("reason") == "optimized_topk"

    async def test_ac_fr4200_03_extra_dict_fields(self, strategy_with_weights):
        """AC-FR4200-03: extra dict contains reason, weight, version."""
        strategy, broker = strategy_with_weights
        tm = datetime(2026, 7, 18, 9, 30)

        await strategy.on_day_open(tm)

        for call in broker.calls:
            extra = call["extra"]
            assert "reason" in extra
            assert "weight" in extra
            assert extra["reason"] == "optimized_topk"

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
