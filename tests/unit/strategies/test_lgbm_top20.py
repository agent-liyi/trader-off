"""Tests for LGBMTop20Strategy (FR-1000).

Uses FakeBroker from conftest.py instead of MagicMock for broker,
addressing Prism mock-overuse findings.

Issue #115 — Rebalance logic risk fixes:
  - Fix 1: Non-atomic rebalance → reconcile _position_cache with broker.positions
  - Fix 2: cash_factor drift → snapshot total/market_value BEFORE sells
  - Fix 3: cash_factor range validation → NaN/negative/overflow fallback to 1.0
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest
import yaml

from trader_off.strategies.compat import BaseStrategy
from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy


@pytest.fixture
def sample_config() -> dict:
    """Sample strategy config dict."""
    return {
        "model_version": "v1",
        "top_k": 20,
        "min_score": -float("inf"),
    }


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestLGBMTop20Strategy:
    """Unit tests for LGBMTop20Strategy."""

    # Inheritance
    def test_inheritance(self):
        """LGBMTop20Strategy is a subclass of BaseStrategy."""
        assert issubclass(LGBMTop20Strategy, BaseStrategy), (
            "LGBMTop20Strategy must inherit from BaseStrategy"
        )

    # init loads model
    @pytest.mark.asyncio
    async def test_init_loads_model(
        self,
        fake_broker,
        sample_config,
    ):
        """await init() loads model, sets top_k=20."""
        strategy = LGBMTop20Strategy(fake_broker, sample_config)

        with patch(
            "trader_off.training.serialize.load_model",
            # mock-overuse: ModelArtifact requires Booster (C++ object)
            return_value=MagicMock(  # noqa: F841
                booster=MagicMock(),  # noqa: F841
                scaler=MagicMock(),  # noqa: F841
                feature_names=["f1"],
                metadata={},
            ),
        ):
            await strategy.init()

        assert strategy.top_k == 20

    # on_day_open trades
    @pytest.mark.asyncio
    async def test_on_day_open_trades(
        self,
        fake_broker,
        sample_config,
    ):
        """on_day_open calls predict, trades target weight."""
        strategy = LGBMTop20Strategy(fake_broker, sample_config)
        strategy.model = MagicMock()  # mock-overuse: Booster requires C++ lib
        strategy.model_version = "v1"
        strategy.top_k = 2
        strategy.min_score = -float("inf")
        strategy.watchlist = ["000001.SZ", "000002.SZ"]

        import polars as pl

        mock_result = pl.DataFrame(
            {
                "asset": ["000001.SZ", "000002.SZ"],
                "score": [0.10, 0.05],
                "rank": [1, 2],
            }
        )

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await strategy.on_day_open(datetime(2024, 12, 31, 9, 30))

        # Verify via FakeBroker call records
        assert len(fake_broker.calls) == 2

        assets_called = [c["asset"] for c in fake_broker.calls]
        assert "000001.SZ" in assets_called
        assert "000002.SZ" in assets_called

    # trade call verification
    @pytest.mark.asyncio
    async def test_trade_target_pct_called_with_correct_params(
        self,
        fake_broker,
        sample_config,
    ):
        """trade_target_pct is called with correct asset and weight."""
        strategy = LGBMTop20Strategy(fake_broker, sample_config)
        strategy.model = MagicMock()  # mock-overuse: Booster requires C++ lib
        strategy.model_version = "v1"
        strategy.top_k = 2
        strategy.min_score = -float("inf")
        strategy.watchlist = ["000001.SZ"]

        import polars as pl

        mock_result = pl.DataFrame(
            {
                "asset": ["000001.SZ"],
                "score": [0.10],
                "rank": [1],
            }
        )

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await strategy.on_day_open(datetime(2024, 12, 31, 9, 30))

        # Check trade_target_pct was called with correct params
        assert len(fake_broker.calls) == 1
        call = fake_broker.calls[0]
        assert call["asset"] == "000001.SZ"
        assert call["pct"] == 0.5  # 1/top_k = 1/2

    # config loaded from YAML
    def test_config_loading(self, fake_broker, tmp_path):
        """YAML config correctly loaded into strategy attributes."""
        config_path = tmp_path / "lgbm_top20.yaml"
        config_data = {
            "model_version": "v1",
            "top_k": 20,
            "min_score": 0.01,
        }
        config_path.write_text(yaml.dump(config_data))

        loaded = yaml.safe_load(config_path.read_text())

        strategy = LGBMTop20Strategy(
            broker=fake_broker,
            config=loaded,
        )

        assert strategy.model_version == "v1"
        assert strategy.top_k == 20
        assert strategy.min_score == 0.01


# ---------------------------------------------------------------------------
# Missing lines coverage: watchlist empty, no predictions, clear stale positions
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.unit
async def test_on_day_open_skips_when_watchlist_empty(
    fake_broker,
    sample_config,
) -> None:
    """Lines 80-81: on_day_open returns early when watchlist is empty."""
    from unittest.mock import AsyncMock, patch

    from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

    strategy = LGBMTop20Strategy(
        broker=fake_broker,
        config={**sample_config, "watchlist": []},
    )
    strategy.model = MagicMock()
    strategy.watchlist = []

    tm = datetime(2026, 7, 20)

    with patch("trader_off.prediction.service.predict", new_callable=AsyncMock) as mock_predict:
        await strategy.on_day_open(tm)
        mock_predict.assert_not_called()


@pytest.mark.unit
async def test_on_day_open_skips_when_predictions_empty(
    fake_broker,
    sample_config,
) -> None:
    """Lines 91-92: on_day_open returns early when predict returns empty list."""
    from unittest.mock import AsyncMock, patch

    import polars as pl

    from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

    strategy = LGBMTop20Strategy(broker=fake_broker, config=sample_config)
    strategy.model = MagicMock()
    strategy.watchlist = ["ASSET_A"]
    tm = datetime(2026, 7, 20)

    with patch(
        "trader_off.prediction.service.predict",
        new_callable=AsyncMock,
        return_value=pl.DataFrame({"asset": [], "score": [], "rank": []}),
    ):
        await strategy.on_day_open(tm)
        assert len(fake_broker.calls) == 0


@pytest.mark.unit
async def test_on_day_open_clears_stale_positions(
    fake_broker,
    sample_config,
) -> None:
    """Lines 120-130: assets in cache but not in targets are closed out."""
    from unittest.mock import AsyncMock, patch

    import polars as pl

    from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

    strategy = LGBMTop20Strategy(broker=fake_broker, config=sample_config)
    strategy.model = MagicMock()
    strategy.watchlist = ["ASSET_A"]
    strategy._position_cache = {"STALE_ASSET": 0.5, "ACTIVE_ASSET": 0.3}

    tm = datetime(2026, 7, 20)
    predictions_df = pl.DataFrame(
        {
            "asset": ["ACTIVE_ASSET"],
            "score": [0.05],
            "rank": [1],
        }
    )

    with patch(
        "trader_off.prediction.service.predict",
        new_callable=AsyncMock,
        return_value=predictions_df,
    ):
        await strategy.on_day_open(tm)

    stale_clears = [c for c in fake_broker.calls if c["asset"] == "STALE_ASSET" and c["pct"] == 0.0]
    assert len(stale_clears) == 1


# ---------------------------------------------------------------------------
# Issue #115 — Rebalance logic risk fix tests for LGBMTop20Strategy
# ---------------------------------------------------------------------------


class FailOnBuyBroker:
    """Broker that raises on a specific buy, used for atomic rebalance test."""

    def __init__(self, fail_asset: str = "ASSET_B"):
        self.calls: list[dict] = []
        self.fail_asset = fail_asset
        self._positions: dict[str, float] = {}
        self._total_val = 1_000_000.0
        self._mv_val = 800_000.0

    async def trade_target_pct(self, asset, target_pct, **kwargs):
        self.calls.append({"asset": asset, "pct": target_pct})
        if target_pct > 0:
            self._positions[asset] = target_pct
            if asset == self.fail_asset:
                del self._positions[asset]
                raise RuntimeError(f"Buy failed for {asset}")
        else:
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
        self.trace: list[str] = []
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


class TestLGBMTop20RebalanceFixes:
    """Tests for Issue #115: rebalance logic risk fixes in lgbm_top20."""

    @staticmethod
    def _make_predictions(assets: list[str]) -> pl.DataFrame:
        """Create a predictions DataFrame with scored assets."""
        data = {
            "asset": assets,
            "score": [0.10 - i * 0.01 for i in range(len(assets))],
            "rank": list(range(1, len(assets) + 1)),
        }
        return pl.DataFrame(data)

    @staticmethod
    def _make_strategy(broker, top_k: int = 3) -> LGBMTop20Strategy:
        """Create a strategy instance with pre-set state (no init needed)."""
        strategy = LGBMTop20Strategy(
            broker=broker,
            config={"model_version": "v1", "top_k": top_k},
        )
        strategy.model = MagicMock()
        strategy.model_version = "v1"
        strategy.top_k = top_k
        strategy.min_score = -float("inf")
        strategy.watchlist = ["ASSET_A", "ASSET_B", "ASSET_C", "ASSET_D"]
        return strategy

    # --- Fix 1: atomic rebalance ---

    @pytest.mark.asyncio
    async def test_atomic_rebalance_position_cache_reconciled(self) -> None:
        """Fix #1: after rebalance, _position_cache matches broker.positions."""
        broker = FailOnBuyBroker(fail_asset="ASSET_B")
        strategy = self._make_strategy(broker, top_k=3)
        # Inject stale position
        strategy._position_cache = {"STALE_ASSET": 0.5}

        predictions = self._make_predictions(["ASSET_A", "ASSET_B", "ASSET_C"])
        tm = datetime(2026, 7, 21, 9, 30)

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=predictions,
        ):
            with pytest.raises(RuntimeError, match="Buy failed"):
                await strategy.on_day_open(tm)

        # After exception, cache reconciled with broker.positions
        assert "ASSET_B" not in strategy._position_cache, (
            "ASSET_B should be removed from cache after failed buy"
        )
        assert "STALE_ASSET" not in strategy._position_cache, (
            "STALE_ASSET should be removed because it was sold"
        )
        assert set(strategy._position_cache.keys()) == set(broker.positions.keys()), (
            "_position_cache keys should match broker.positions keys after reconciliation"
        )

    # --- Fix 2: cash_factor pre-sell snapshot ---

    @pytest.mark.asyncio
    async def test_cash_factor_uses_pre_sell_snapshot(self) -> None:
        """Fix #2: cash_factor computed from pre-sell total_asset/market_value."""
        broker = TracingBroker(total=1_000_000.0, market_value=800_000.0)
        strategy = self._make_strategy(broker, top_k=3)
        # Inject stale positions so sells happen FIRST, triggering the drift bug
        strategy._position_cache = {"STALE_X": 0.1, "STALE_Y": 0.05}

        predictions = self._make_predictions(["ASSET_A", "ASSET_B", "ASSET_C"])
        tm = datetime(2026, 7, 21, 9, 30)

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=predictions,
        ):
            await strategy.on_day_open(tm)

        trace = broker.trace
        first_trade = trace.index("trade")
        first_total = trace.index("total")
        first_mv = trace.index("mv")

        assert first_total < first_trade, (
            "total_asset() before any trade_target_pct (pre-sell snapshot)"
        )
        assert first_mv < first_trade, (
            "market_value() before any trade_target_pct (pre-sell snapshot)"
        )

        # With top_k=3, equal weight = 1/3 ≈ 0.3333
        # cash_factor = 800K/1M = 0.8, adjusted_weight = 0.3333 * 0.8 ≈ 0.266667
        expected_weight = (1.0 / 3) * 0.8
        buy_calls = [c for c in broker.calls if c["pct"] > 0]
        for call in buy_calls:
            assert call["pct"] == pytest.approx(expected_weight, rel=1e-6), (
                f"Adjusted weight should be {expected_weight}, got {call['pct']}"
            )

    # --- Fix 3 / Issue #120: cash_factor raises on broker-broken signals ---

    @pytest.mark.asyncio
    async def test_cash_factor_nan_raises(self) -> None:
        """Issue #120: NaN cash_factor → RuntimeError (broker broken)."""
        broker = ValidationBroker(total=float("nan"), market_value=800_000.0)
        strategy = self._make_strategy(broker, top_k=3)

        predictions = self._make_predictions(["ASSET_A", "ASSET_B", "ASSET_C"])
        tm = datetime(2026, 7, 21, 9, 30)

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=predictions,
        ):
            with pytest.raises(RuntimeError, match="cash_factor invalid"):
                await strategy.on_day_open(tm)

    @pytest.mark.asyncio
    async def test_cash_factor_negative_raises(self) -> None:
        """Issue #120: negative cash_factor → RuntimeError (broker broken)."""
        broker = ValidationBroker(total=-100_000.0, market_value=800_000.0)
        strategy = self._make_strategy(broker, top_k=3)

        predictions = self._make_predictions(["ASSET_A", "ASSET_B", "ASSET_C"])
        tm = datetime(2026, 7, 21, 9, 30)

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=predictions,
        ):
            with pytest.raises(RuntimeError, match="cash_factor invalid"):
                await strategy.on_day_open(tm)

    @pytest.mark.asyncio
    async def test_cash_factor_overflow_raises(self) -> None:
        """Issue #120: cash_factor > 1.0 → RuntimeError (broker broken)."""
        broker = ValidationBroker(total=500_000.0, market_value=800_000.0)
        strategy = self._make_strategy(broker, top_k=3)

        predictions = self._make_predictions(["ASSET_A", "ASSET_B", "ASSET_C"])
        tm = datetime(2026, 7, 21, 9, 30)

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=predictions,
        ):
            with pytest.raises(RuntimeError, match="cash_factor invalid"):
                await strategy.on_day_open(tm)

    # --- Issue #120: snapshot/restore + bidirectional reconcile + empty-account ---

    @pytest.mark.asyncio
    async def test_snapshot_restore_on_exception(self) -> None:
        """Issue #120: exception during rebalance restores _position_cache to
        pre-rebalance state."""
        broker = FailOnBuyBroker(fail_asset="ASSET_B")
        strategy = self._make_strategy(broker, top_k=3)
        # Pre-populate cache
        strategy._position_cache = {"STALE_X": 0.10, "STALE_Y": 0.05}
        snapshot = dict(strategy._position_cache)

        predictions = self._make_predictions(["ASSET_A", "ASSET_B", "ASSET_C"])
        tm = datetime(2026, 7, 21, 9, 30)

        with patch(
            "trader_off.prediction.service.predict",
            new_callable=AsyncMock,
            return_value=predictions,
        ):
            # Suppress reconciliation to verify snapshot restore in isolation
            with patch.object(strategy, "_reconcile_position_cache", return_value=None):
                with pytest.raises(RuntimeError, match="Buy failed"):
                    await strategy.on_day_open(tm)

        assert strategy._position_cache == snapshot, (
            "_position_cache should be restored to pre-rebalance snapshot after exception"
        )

    @pytest.mark.asyncio
    async def test_bidirectional_reconcile_adds_missing(self) -> None:
        """Issue #120: _reconcile_position_cache adds broker positions missing from cache."""

        class Broker:
            @property
            def positions(self):
                return {"A": 0.1, "B": 0.2}

        strategy = LGBMTop20Strategy(
            broker=Broker(),
            config={"top_k": 20},
        )
        strategy._position_cache = {"A": 0.1}

        strategy._reconcile_position_cache()

        assert "B" in strategy._position_cache, "Missing broker position should be added to cache"
        assert strategy._position_cache["B"] == 0.2, "Added position value should match broker"
        assert "A" in strategy._position_cache, "Existing cache entry should be preserved"

    @pytest.mark.asyncio
    async def test_bidirectional_reconcile_removes_stale(self) -> None:
        """Issue #120: _reconcile_position_cache removes cache entries absent from broker."""

        class Broker:
            @property
            def positions(self):
                return {"A": 0.1}

        strategy = LGBMTop20Strategy(
            broker=Broker(),
            config={"top_k": 20},
        )
        strategy._position_cache = {"A": 0.1, "STALE_B": 0.3}

        strategy._reconcile_position_cache()

        assert "STALE_B" not in strategy._position_cache, "Stale cache entry should be removed"
        assert "A" in strategy._position_cache, "Valid cache entry should be preserved"
        assert strategy._position_cache["A"] == 0.1

    @pytest.mark.asyncio
    async def test_cash_factor_empty_account_returns_1(self) -> None:
        """Issue #120: empty account (total=0 or mv=0) returns cash_factor=1.0."""
        strategy = LGBMTop20Strategy(
            broker=MagicMock(),
            config={"top_k": 20},
        )

        assert strategy._compute_cash_factor(0.0, 0.0) == 1.0, "total=0, mv=0 → 1.0"
        assert strategy._compute_cash_factor(0.0, 1_000_000.0) == 1.0, "mv=0 with cash → 1.0"
        assert strategy._compute_cash_factor(800_000.0, 0.0) == 1.0, "total=0 with mv → 1.0"
        assert strategy._compute_cash_factor(800_000.0, 1_000_000.0) == 0.8, "normal case"
