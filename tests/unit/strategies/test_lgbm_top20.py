"""Tests for LGBMTop20Strategy (FR-1000).

Uses FakeBroker from conftest.py instead of MagicMock for broker,
addressing Prism mock-overuse findings.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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

    # AC-FR1000-01: Inheritance
    def test_ac_fr1000_01_inheritance(self):
        """AC-FR1000-01: LGBMTop20Strategy is a subclass of BaseStrategy."""
        assert issubclass(LGBMTop20Strategy, BaseStrategy), (
            "LGBMTop20Strategy must inherit from BaseStrategy"
        )

    # AC-FR1000-02: init loads model
    @pytest.mark.asyncio
    async def test_ac_fr1000_02_init_loads_model(
        self,
        fake_broker,
        sample_config,
    ):
        """AC-FR1000-02: await init() loads model, sets top_k=20."""
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
        assert strategy.model is not None

    # AC-FR1000-03: on_day_open trades
    @pytest.mark.asyncio
    async def test_ac_fr1000_03_on_day_open_trades(
        self,
        fake_broker,
        sample_config,
    ):
        """AC-FR1000-03: on_day_open calls predict, trades target weight."""
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

    # AC-FR1000-04: extra dict in orders
    @pytest.mark.asyncio
    async def test_ac_fr1000_04_extra_snapshot(
        self,
        fake_broker,
        sample_config,
    ):
        """AC-FR1000-04: extra dict contains reason/score/rank/model_version."""
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

        # Check extra dict via FakeBroker call records
        assert len(fake_broker.calls) == 1
        extra = fake_broker.calls[0].get("extra", {})
        assert extra.get("reason") == "lgbm_top20"
        assert extra.get("score") == 0.10
        assert extra.get("rank") == 1
        assert extra.get("model_version") == "v1"

    # AC-FR1000-05: config loaded from YAML
    def test_ac_fr1000_05_config_loading(self, fake_broker, tmp_path):
        """AC-FR1000-05: YAML config correctly loaded into strategy attributes."""
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
