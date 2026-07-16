"""Tests for prediction service (FR-0900)."""

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl
import pytest
from lightgbm import Booster

from trader_off.data.preprocess import StandardScaler
from trader_off.prediction.service import predict

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_history(
    asset: str,
    end_date: date,
    n_days: int,
    seed: int = 42,
) -> pl.DataFrame:
    """Generate fake OHLCV data for n_days ending at end_date."""
    rng = np.random.RandomState(seed + hash(asset) % 10000)
    rows = []
    for i in range(n_days):
        d = end_date - timedelta(days=n_days - 1 - i)
        base = 10.0 + rng.randn() * 2
        rows.append({
            "asset": asset,
            "date": d,
            "open": base * 0.99,
            "high": base * 1.02,
            "low": base * 0.98,
            "close": base,
            "volume": float(1_000_000 + i * 10_000),
            "turnover": 0.02 + rng.rand() * 0.01,
            "adj_factor": 1.0,
        })
    return pl.DataFrame(rows)


async def _fake_get_history(asset: str, end_date: date, count: int = 120) -> pl.DataFrame:
    """Fake async DataLoader.get_history."""
    return _make_ohlcv_history(asset, end_date, count)


def _fake_booster_predict(x: np.ndarray) -> np.ndarray:
    """Return deterministic scores based on first feature column."""
    return x[:, 0].astype(float)


# ---------------------------------------------------------------------------
# test data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scaler() -> StandardScaler:
    """A scaler matching the 15 feature columns."""
    feature_names = [
        "ret_5", "ret_10", "ret_20", "ret_60",
        "vol_10", "vol_20", "vol_60",
        "turnover_5", "turnover_10", "turnover_20",
        "vp_corr_5", "vp_corr_10", "vp_corr_20",
    ]
    mean_ = {f: 0.0 for f in feature_names}
    std_ = {f: 1.0 for f in feature_names}
    return StandardScaler(mean_=mean_, std_=std_, feature_names=feature_names)


@pytest.fixture
def mock_booster() -> MagicMock:
    """A mock lightgbm Booster."""
    booster = MagicMock(spec=Booster)
    booster.predict.side_effect = _fake_booster_predict
    return booster


@pytest.fixture
def mock_loader():
    """A mock DataLoader with fake get_history."""
    loader = MagicMock()
    loader.get_history = MagicMock(side_effect=_fake_get_history)
    return loader


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestPredict:
    """Unit tests for predict."""

    # AC-FR0900-01: returns DataFrame with expected columns and rows
    @pytest.mark.asyncio
    async def test_ac_fr0900_01_returns_dataframe(self, scaler, mock_booster, mock_loader):
        """AC-FR0900-01: predict returns pl.DataFrame with asset, score, rank."""
        watchlist = ["000001.SZ", "000002.SZ"]
        asof = date(2024, 12, 31)

        with patch(
            "trader_off.prediction.service.load_model",
            return_value=MagicMock(
                booster=mock_booster, scaler=scaler,
                feature_names=scaler.feature_names, metadata={},
            ),
        ):
            result = await predict(
                model_version="v1",
                watchlist=watchlist,
                asof_date=asof,
                data_loader=mock_loader,
            )

        assert isinstance(result, pl.DataFrame)
        assert set(result.columns) == {"asset", "score", "rank"}
        assert len(result) == 2
        assert set(result["asset"].to_list()) == set(watchlist)

    # AC-FR0900-02: sorted descending, rank from 1
    @pytest.mark.asyncio
    async def test_ac_fr0900_02_sorted_desc(self, scaler, mock_booster, mock_loader):
        """AC-FR0900-02: result sorted by score descending, rank from 1."""
        watchlist = ["000001.SZ", "000002.SZ"]
        asof = date(2024, 12, 31)

        with patch(
            "trader_off.prediction.service.load_model",
            return_value=MagicMock(
                booster=mock_booster, scaler=scaler,
                feature_names=scaler.feature_names, metadata={},
            ),
        ):
            result = await predict(
                model_version="v1",
                watchlist=watchlist,
                asof_date=asof,
                data_loader=mock_loader,
            )

        scores = result["score"].to_list()
        ranks = result["rank"].to_list()

        # Verify descending order
        assert scores == sorted(scores, reverse=True), f"Scores not sorted descending: {scores}"
        assert ranks == [1, 2], f"Expected ranks [1,2], got {ranks}"

    # AC-FR0900-03: insufficient history → skip + WARNING + predict_skipped.json
    @pytest.mark.asyncio
    async def test_ac_fr0900_03_skip_insufficient(
        self, scaler, mock_booster, tmp_path,
    ):
        """AC-FR0900-03: assets with <120 days history are skipped."""
        watchlist = ["000001.SZ", "000003.SZ"]
        asof = date(2024, 12, 31)

        # Mock loader: 000001 gets 120 days, 000003 gets only 50 days
        mock_loader = MagicMock()

        async def selective_history(asset, end_date, count=120):
            n = 120 if asset == "000001.SZ" else 50
            return _make_ohlcv_history(asset, end_date, n, seed=hash(asset) % 10000)

        mock_loader.get_history = MagicMock(side_effect=selective_history)

        skipped_path = tmp_path / "predict_skipped.json"

        with patch(
            "trader_off.prediction.service.load_model",
            return_value=MagicMock(
                booster=mock_booster, scaler=scaler,
                feature_names=scaler.feature_names, metadata={"max_lookback": 120},
            ),
        ):
            result = await predict(
                model_version="v1",
                watchlist=watchlist,
                asof_date=asof,
                data_loader=mock_loader,
                skipped_path=skipped_path,
            )

        # 000003.SZ should NOT be in result
        assert "000003.SZ" not in result["asset"].to_list()
        assert "000001.SZ" in result["asset"].to_list()
        assert len(result) == 1

        # predict_skipped.json should exist with the skipped asset
        assert skipped_path.exists()
        skipped = json.loads(skipped_path.read_text())
        assert any(r["asset"] == "000003.SZ" for r in skipped)
        assert any("insufficient_history" in r["reason"] for r in skipped)

    # AC-FR0900-04: mock DataLoader call_count == len(watchlist), count=120
    @pytest.mark.asyncio
    async def test_ac_fr0900_04_lookback_120(self, scaler, mock_booster):
        """AC-FR0900-04: DataLoader.get_history called once per asset with count=120."""
        watchlist = ["000001.SZ", "000002.SZ"]
        asof = date(2024, 12, 31)

        mock_loader = MagicMock()
        mock_loader.get_history = MagicMock(side_effect=_fake_get_history)

        with patch(
            "trader_off.prediction.service.load_model",
            return_value=MagicMock(
                booster=mock_booster, scaler=scaler,
                feature_names=scaler.feature_names, metadata={},
            ),
        ):
            await predict(
                model_version="v1",
                watchlist=watchlist,
                asof_date=asof,
                data_loader=mock_loader,
            )

        assert mock_loader.get_history.call_count == len(watchlist)

        # Verify each call used count=120
        for call_args in mock_loader.get_history.call_args_list:
            kwargs = call_args.kwargs
            assert kwargs.get("count") == 120, f"Expected count=120, got {kwargs}"
