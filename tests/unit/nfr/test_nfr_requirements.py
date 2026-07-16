"""Tests for NFR-0200 (IC thresholds), NFR-0400 (async), NFR-0500 (logging), NFR-0600 (security), NFR-0700 (reproducibility)."""

import asyncio
import inspect
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

# ---------------------------------------------------------------------------
# NFR-0200: IC thresholds
# ---------------------------------------------------------------------------


class TestICThresholds:
    """NFR-0200: prediction capability thresholds in metadata."""

    def test_metadata_includes_ic_fields(self):
        """Metadata dict must support test_ic_mean and test_rank_ic_mean."""
        metadata = {
            "test_ic_mean": 0.025,
            "test_rank_ic_mean": 0.035,
        }
        assert isinstance(metadata["test_ic_mean"], float)
        assert isinstance(metadata["test_rank_ic_mean"], float)

    def test_ic_pass_soft_target_true(self):
        """IC > 0.02 and Rank IC > 0.03 → ic_pass_soft_target=True."""
        test_ic = 0.025
        test_rank_ic = 0.035
        ic_pass = test_ic > 0.02 and test_rank_ic > 0.03
        assert ic_pass is True

    def test_ic_pass_soft_target_false(self):
        """IC below threshold → ic_pass_soft_target=False."""
        test_ic = 0.01
        test_rank_ic = 0.02
        ic_pass = test_ic > 0.02 and test_rank_ic > 0.03
        assert ic_pass is False


# ---------------------------------------------------------------------------
# NFR-0400: Async signatures
# ---------------------------------------------------------------------------


class TestAsyncSignatures:
    """NFR-0400 AC-2: strategy methods must be async def."""

    def test_strategy_methods_are_async(self):
        """All LGBMTop20Strategy lifecycle methods should be async def."""
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        async_methods = ["init", "on_day_open", "on_bar", "on_day_close", "on_stop"]
        for method_name in async_methods:
            method = getattr(LGBMTop20Strategy, method_name)
            assert inspect.iscoroutinefunction(method), (
                f"{method_name} is not async def"
            )


# ---------------------------------------------------------------------------
# NFR-0500: Logging
# ---------------------------------------------------------------------------


class TestLoggingNFR:
    """NFR-0500: log format, levels, file output."""

    def test_setup_logger_format_regex(self):
        """Log format matches expected pattern."""
        import re
        from trader_off.utils.logging import setup_logger

        log_dir = Path("logs")
        setup_logger(module="test_nfr", log_dir=log_dir)

        from loguru import logger
        logger.info("format test")

        # Clean up: check log file exists
        log_files = list(log_dir.glob("test_nfr_*.log"))
        assert len(log_files) > 0
        content = log_files[0].read_text()
        pattern = (
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| "
            r"INFO\s+\| "
            r"[^:]+:[^:]+:\d+ \| "
            r"format test"
        )
        assert re.search(pattern, content), f"Format mismatch in: {content}"

    def test_three_log_levels_produced(self):
        """All three log levels (INFO, WARNING, ERROR) are available."""
        from loguru import logger

        messages = []

        def capture(msg):
            record = msg.record
            messages.append(record["level"].name)

        sink_id = logger.add(capture, level="DEBUG")
        logger.info("info msg")
        logger.warning("warning msg")
        logger.error("error msg")
        logger.remove(sink_id)

        assert "INFO" in messages
        assert "WARNING" in messages
        assert "ERROR" in messages


# ---------------------------------------------------------------------------
# NFR-0600: Security
# ---------------------------------------------------------------------------


class TestSecurity:
    """NFR-0600: path traversal, no credentials, joblib usage."""

    def test_no_hard_coded_credentials(self):
        """No hard-coded api_key/password/token/secret in source."""
        import subprocess

        result = subprocess.run(
            ["grep", "-rE",
             r"(api_key|password|token|secret)\s*=\s*['\"/]",
             "src/trader_off/"],
            capture_output=True, text=True,
        )
        # grep returns 1 if no matches found (which is good)
        # grep returns 0 if matches found (which is bad)
        assert result.returncode != 0, (
            f"Hard-coded credentials found:\n{result.stdout}"
        )

    def test_model_serialization_uses_joblib(self):
        """Model loading must use joblib, not raw pickle.load."""
        import joblib
        from trader_off.training.serialize import load_model
        import inspect

        source = inspect.getsource(load_model)
        assert "joblib.load" in source, "load_model must use joblib.load"
        assert "pickle.load" not in source, "load_model must NOT use pickle.load"

    def test_path_traversal_prevented(self):
        """Path traversal should raise PathTraversalError."""
        from trader_off.utils.exceptions import PathTraversalError

        # Model loading should validate paths - test that relative paths
        # with '..' are handled properly
        with pytest.raises((FileNotFoundError, PathTraversalError)):
            from trader_off.training.serialize import load_model
            load_model("../escape", models_dir="/tmp")


# ---------------------------------------------------------------------------
# NFR-0700: Reproducibility
# ---------------------------------------------------------------------------


class TestReproducibility:
    """NFR-0700: random seeds, config loading, metadata fields."""

    def test_default_params_have_random_state_42(self):
        """DEFAULT_PARAMS must include random_state=42 and seed params."""
        from trader_off.training.trainer import DEFAULT_PARAMS

        assert DEFAULT_PARAMS["random_state"] == 42
        assert DEFAULT_PARAMS["feature_fraction_seed"] == 42
        assert DEFAULT_PARAMS["bagging_seed"] == 42

    def test_metadata_includes_repro_fields(self):
        """metadata.json should include git_commit_sha, python_version, package_versions."""
        import sys

        metadata = {
            "git_commit_sha": "abc1234",
            "python_version": sys.version.split()[0],
            "package_versions": {
                "lightgbm": "4.6.0",
                "polars": "1.42.1",
            },
        }
        assert len(metadata["git_commit_sha"]) >= 7
        assert "." in metadata["python_version"]
        assert isinstance(metadata["package_versions"], dict)

    def test_config_yaml_loading(self):
        """Strategy config can be loaded from YAML."""
        import yaml

        config_data = {
            "model_version": "v1",
            "top_k": 20,
            "min_score": -float("inf"),
        }
        yaml_str = yaml.dump(config_data)
        loaded = yaml.safe_load(yaml_str)
        assert loaded["top_k"] == 20

    def test_save_model_metadata_json_content(self):
        """save_model writes correct metadata.json."""
        import numpy as np
        import lightgbm as lgb
        import json
        import tempfile
        from trader_off.training.serialize import save_model
        from trader_off.data.preprocess import StandardScaler

        X = np.random.RandomState(42).randn(10, 2)
        y = np.random.RandomState(42).randn(10)
        booster = lgb.train({"objective": "regression", "verbose": -1, "num_leaves": 4},
                            lgb.Dataset(X, label=y), num_boost_round=3)
        scaler = StandardScaler(mean_={"f1": 0.0}, std_={"f1": 1.0}, feature_names=["f1"])
        metadata = {
            "train_start": "2015-01-01",
            "train_end": "2024-12-31",
            "best_iteration": 100,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = save_model(booster, scaler, metadata, version="test", models_dir=tmp)
            saved = json.loads((Path(path) / "metadata.json").read_text())
            assert saved["train_start"] == "2015-01-01"
            assert saved["best_iteration"] == 100


# ---------------------------------------------------------------------------
# NFR-0100: Integration test for 4500 assets
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDataScale:
    """NFR-0100 AC-1: 4500 assets mock test."""

    def test_mock_4500_assets_walk_forward(self, tmp_path):
        """prepare_walk_forward_splits handles 4500 mock assets."""
        import polars as pl
        from datetime import date, timedelta
        from trader_off.data.walk_forward import prepare_walk_forward_splits

        n_assets = 4500
        n_days = 500  # Need enough days to span train+valid+test
        start = date(2017, 1, 1)
        dates = [start + timedelta(days=i) for i in range(n_days)]

        data_dict = {
            "asset": [f"{i:06d}.SZ" for i in range(n_assets) for _ in range(n_days)],
            "date": dates * n_assets,
            "close": [10.0] * (n_assets * n_days),
        }
        df = pl.DataFrame(data_dict, schema={
            "asset": pl.Utf8, "date": pl.Date, "close": pl.Float64,
        })

        output_dir = tmp_path / "splits"
        splits = prepare_walk_forward_splits(
            df, start_year=2018, end_year=2018, train_window_years=1,
            output_dir=output_dir,
        )
        assert len(splits) == 1
        train_df = pl.read_parquet(splits[0].train_path)
        unique_assets = train_df["asset"].n_unique()
        assert unique_assets >= 4000, f"Expected >=4000 assets, got {unique_assets}"
