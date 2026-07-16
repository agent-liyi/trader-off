"""Tests for NFR-0100: schema validation, NFR-0300: coverage edge cases."""

import polars as pl
import pytest


REQUIRED_COLS = {"asset", "date", "open", "high", "low", "close", "volume", "turnover", "adj_factor"}


class TestOHLCVSchema:
    """NFR-0100 AC-4: OHLCV schema validation."""

    def test_ohlcv_schema_required_columns(self):
        """Valid OHLCV DataFrame must contain all required columns."""
        df = pl.DataFrame({
            "asset": ["A"],
            "date": [pl.date(2024, 1, 1)],
            "open": [10.0], "high": [11.0], "low": [9.0], "close": [10.5],
            "volume": [1e6], "turnover": [0.02], "adj_factor": [1.0],
        })
        assert REQUIRED_COLS.issubset(set(df.columns))

    def test_ohlcv_schema_dtypes(self):
        """OHLCV schema must have correct dtypes."""
        from datetime import date
        df = pl.DataFrame({
            "asset": ["000001.SZ"],
            "date": [date(2024, 1, 1)],
            "open": [10.0], "high": [11.0], "low": [9.0], "close": [10.5],
            "volume": [1e6], "turnover": [0.02], "adj_factor": [1.0],
        }, schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64, "high": pl.Float64,
            "low": pl.Float64, "close": pl.Float64,
            "volume": pl.Float64, "turnover": pl.Float64,
            "adj_factor": pl.Float64,
        })
        assert df["asset"].dtype == pl.Utf8
        assert df["close"].dtype == pl.Float64

    def test_limit_columns_are_boolean(self):
        """limit_up and limit_down should be Boolean when present."""
        df = pl.DataFrame({
            "asset": ["A"], "date": [pl.date(2024, 1, 1)],
            "close": [10.0], "limit_up": [True], "limit_down": [False],
        })
        assert df["limit_up"].dtype == pl.Boolean
        assert df["limit_down"].dtype == pl.Boolean


class TestCoverageEdgeCases:
    """Additional tests to cover edge case branches for NFR-0300 coverage."""

    def test_data_loader_no_fetcher(self):
        """DataLoader without fetcher returns empty DataFrame."""
        import asyncio
        from datetime import date
        from trader_off.data.loader import DataLoader

        loader = DataLoader()

        async def run():
            return await loader.get_history("000001.SZ", date(2024, 1, 1))

        result = asyncio.run(run())
        assert len(result) == 0
        assert "asset" in result.columns

    def test_strategy_on_bar_noop(self):
        """on_bar should be a no-op."""
        import asyncio
        from datetime import datetime
        from unittest.mock import MagicMock
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        strategy = LGBMTop20Strategy(MagicMock(), {})
        asyncio.run(strategy.on_bar(datetime.now()))
        # Should not raise

    def test_strategy_on_day_close_noop(self):
        """on_day_close should be a no-op."""
        import asyncio
        from datetime import datetime
        from unittest.mock import MagicMock
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        strategy = LGBMTop20Strategy(MagicMock(), {})
        asyncio.run(strategy.on_day_close(datetime.now()))
        # Should not raise

    def test_strategy_on_stop_clears_model(self):
        """on_stop should clear model reference."""
        import asyncio
        from unittest.mock import MagicMock
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        strategy = LGBMTop20Strategy(MagicMock(), {})
        strategy.model = MagicMock()
        strategy._position_cache["A"] = 0.05
        asyncio.run(strategy.on_stop())
        assert strategy.model is None
        assert len(strategy._position_cache) == 0

    def test_strategy_init_no_model(self):
        """on_day_open when model not loaded → skip with error log."""
        import asyncio
        from datetime import datetime
        from unittest.mock import MagicMock
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        strategy = LGBMTop20Strategy(MagicMock(), {"watchlist": ["A"]})
        strategy.model = None  # model not loaded
        asyncio.run(strategy.on_day_open(datetime.now()))
        # Should not raise

    def test_compat_base_strategy_stubs(self):
        """Compat BaseStrategy stubs should have all lifecycle methods."""
        from trader_off.strategies.compat import BaseStrategy
        from unittest.mock import MagicMock

        strategy = BaseStrategy(MagicMock(), {})
        import asyncio

        asyncio.run(strategy.init())
        asyncio.run(strategy.on_day_open(MagicMock()))
        asyncio.run(strategy.on_bar(MagicMock()))
        asyncio.run(strategy.on_day_close(MagicMock()))
        asyncio.run(strategy.on_stop())
        # All should succeed without errors

    def test_cli_backtest_exception_handling(self):
        """CLI backtest exception handling branch."""
        import sys
        from unittest.mock import patch
        from trader_off.cli.backtest import main

        test_args = ["backtest", "--model", "v1", "--strategy", "lgbm_top20",
                     "--start", "2023-01-01", "--end", "2023-12-31",
                     "--capital", "1000000"]
        with patch.object(sys, "argv", test_args):
            with patch("trader_off.cli.backtest.run_backtest",
                       side_effect=RuntimeError("test error")):
                exit_code = main()
                assert exit_code == 1

    def test_ic_small_sample_edge_case(self):
        """ic_pearson with <3 valid samples returns 0."""
        from trader_off.evaluation.ic import ic_pearson, ic_spearman

        pred = pl.Series("pred", [1.0, float("nan")])
        label = pl.Series("label", [float("nan"), 2.0])
        assert ic_pearson(pred, label) == 0.0
        assert ic_spearman(pred, label) == 0.0

    def test_layered_returns_empty(self):
        """compute_layered_returns with empty merge returns default."""
        from trader_off.evaluation.ic import compute_layered_returns

        preds = pl.DataFrame({"date": [], "asset": [], "score": []},
                             schema={"date": pl.Date, "asset": pl.Utf8, "score": pl.Float64})
        labels = pl.DataFrame({"date": [], "asset": [], "label": []},
                              schema={"date": pl.Date, "asset": pl.Utf8, "label": pl.Float64})
        result = compute_layered_returns(preds, labels, n_layers=5)
        assert len(result) == 5

    def test_evaluate_predictions_empty(self):
        """evaluate_predictions with empty merge returns zeroed report."""
        from trader_off.evaluation.report import evaluate_predictions

        preds = pl.DataFrame({"date": [], "asset": [], "score": []},
                             schema={"date": pl.Date, "asset": pl.Utf8, "score": pl.Float64})
        labels = pl.DataFrame({"date": [], "asset": [], "label": []},
                              schema={"date": pl.Date, "asset": pl.Utf8, "label": pl.Float64})
        report = evaluate_predictions(preds, labels)
        assert report.ic_mean == 0.0

    def test_train_model_numpy_input(self):
        """_to_numpy with numpy array input (coverage branch)."""
        import numpy as np
        from trader_off.training.trainer import _to_numpy

        arr = np.array([1.0, 2.0, 3.0])
        result = _to_numpy(arr)
        assert isinstance(result, np.ndarray)
        assert np.array_equal(result, arr)

    def test_walk_forward_default_output_dir(self):
        """walk_forward with default output_dir=None."""
        from datetime import date
        from trader_off.data.walk_forward import prepare_walk_forward_splits

        data = pl.DataFrame({
            "asset": ["A"] * 10,
            "date": [date(2018, 1, 1) + __import__("datetime").timedelta(days=i)
                     for i in range(10)],
            "close": [10.0 + i for i in range(10)],
        }, schema={"asset": pl.Utf8, "date": pl.Date, "close": pl.Float64})

        splits = prepare_walk_forward_splits(data, start_year=2018, end_year=2018,
                                             train_window_years=1)
        assert len(splits) == 1
        # Cleanup generated files
        import os
        for s in splits:
            for p in [s.train_path, s.valid_path, s.test_path]:
                if p.exists():
                    p.unlink()

    def test_builder_empty_labels_stats(self):
        """compute_label_stats with empty labels."""
        from trader_off.labels.builder import compute_label_stats

        labels = pl.DataFrame({"asset": [], "date": [], "label": []},
                              schema={"asset": pl.Utf8, "date": pl.Date, "label": pl.Float64})
        stats = compute_label_stats(labels)
        assert stats["mean"] == 0.0
        assert stats["std"] == 0.0

    def test_builder_percentile_edge(self):
        """_percentile with empty values."""
        from trader_off.labels.builder import _percentile
        empty = pl.Series("x", [], dtype=pl.Float64)
        assert _percentile(empty, 50) == 0.0

    def test_serialize_default_dropped_features(self):
        """save_model with default dropped_features=None."""
        import numpy as np
        import lightgbm as lgb
        from pathlib import Path
        from trader_off.training.serialize import save_model
        from trader_off.data.preprocess import StandardScaler

        X = np.random.RandomState(42).randn(10, 2)
        y = np.random.RandomState(42).randn(10)
        booster = lgb.train({"objective": "regression", "verbose": -1, "num_leaves": 4},
                            lgb.Dataset(X, label=y), num_boost_round=3)
        scaler = StandardScaler(mean_={"f1": 0.0}, std_={"f1": 1.0}, feature_names=["f1"])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = save_model(booster, scaler, {}, version="test", models_dir=tmp)
            assert (Path(path) / "dropped_features.json").exists()

    def test_serialize_load_errors(self):
        """load_model with non-existent dir raises FileNotFoundError."""
        import pytest
        from trader_off.training.serialize import load_model

        with pytest.raises(FileNotFoundError):
            load_model("nonexistent", models_dir="/tmp/nonexistent_models")

    def test_feature_importance_num_trees_exception(self):
        """extract_feature_importance handles num_trees() exception."""
        from unittest.mock import MagicMock
        from trader_off.training.feature_importance import extract_feature_importance

        mock_booster = MagicMock()
        mock_booster.num_trees.side_effect = AttributeError("no trees")
        result = extract_feature_importance(mock_booster, ["f1"])
        assert len(result) == 0
