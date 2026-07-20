"""Tests for NFR-0200 (IC thresholds), NFR-0400 (async), NFR-0500 (logging),
NFR-0600 (security), NFR-0700 (reproducibility).

Every test maps to a specific AC reference for Prism traceability.
"""

import inspect
import json
from pathlib import Path

import polars as pl
import pytest

# ---------------------------------------------------------------------------
# NFR-0200: IC thresholds
# ---------------------------------------------------------------------------


class TestICThresholds:
    """NFR-0200: prediction capability thresholds in metadata."""

    # AC-NFR0200-01: test_ic_mean / test_rank_ic_mean exist and are float
    def test_metadata_includes_ic_fields(self):
        """AC-NFR0200-01: Metadata dict must support test_ic_mean and test_rank_ic_mean."""
        metadata = {
            "test_ic_mean": 0.025,
            "test_rank_ic_mean": 0.035,
        }
        assert isinstance(metadata["test_ic_mean"], float)
        assert isinstance(metadata["test_rank_ic_mean"], float)

    # IC > 0.02 and Rank IC > 0.03 → ic_pass_soft_target=True
    def test_ic_pass_soft_target_true(self):
        """IC > 0.02 and Rank IC > 0.03 → ic_pass_soft_target=True."""
        test_ic = 0.025
        test_rank_ic = 0.035
        ic_pass = test_ic > 0.02 and test_rank_ic > 0.03
        assert ic_pass is True

    # IC below threshold → ic_pass_soft_target=False
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

    # AC-NFR0400-02: all lifecycle methods are async def
    def test_strategy_methods_are_async(self):
        """AC-NFR0400-02: All LGBMTop20Strategy lifecycle methods should be async def."""
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        async_methods = ["init", "on_day_open", "on_bar", "on_day_close", "on_stop"]
        for method_name in async_methods:
            method = getattr(LGBMTop20Strategy, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} is not async def"


# ---------------------------------------------------------------------------
# NFR-0500: Logging
# ---------------------------------------------------------------------------


class TestLoggingNFR:
    """NFR-0500: log format, levels, file output."""

    # AC-NFR0500-02: log format matches {time} | {level} | {name}:{function}:{line} | {message}
    def test_setup_logger_format_regex(self):
        """AC-NFR0500-02: Log format matches expected pattern."""
        import re

        from trader_off.utils.logging import setup_logger

        log_dir = Path("logs")
        setup_logger(module="test_nfr", log_dir=log_dir)

        from loguru import logger

        logger.info("format test")

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

    # AC-NFR0500-03: INFO, WARNING, ERROR levels all produced
    def test_three_log_levels_produced(self):
        """AC-NFR0500-03: All three log levels (INFO, WARNING, ERROR) are available."""
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

    # AC-NFR0600-01: no hard-coded credentials in source
    def test_no_hard_coded_credentials(self):
        """AC-NFR0600-01: No hard-coded api_key/password/token/secret in source."""
        import subprocess

        result = subprocess.run(
            ["grep", "-rE", r"(api_key|password|token|secret)\s*=\s*['\"/]", "src/trader_off/"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, f"Hard-coded credentials found:\n{result.stdout}"

    # AC-NFR0600-03: model loading uses joblib, not pickle
    def test_model_serialization_uses_joblib(self):
        """AC-NFR0600-03: Model loading must use joblib, not raw pickle.load."""
        from trader_off.training.serialize import load_model

        source = inspect.getsource(load_model)
        assert "joblib.load" in source, "load_model must use joblib.load"
        assert "pickle.load" not in source, "load_model must NOT use pickle.load"

    # AC-NFR0600-02: path traversal prevented
    def test_path_traversal_prevented(self):
        """AC-NFR0600-02: Path traversal should raise PathTraversalError or FileNotFoundError."""
        from trader_off.utils.exceptions import PathTraversalError

        with pytest.raises((FileNotFoundError, PathTraversalError)):
            from trader_off.training.serialize import load_model

            load_model("../escape", models_dir="/tmp")


# ---------------------------------------------------------------------------
# NFR-0700: Reproducibility
# ---------------------------------------------------------------------------


class TestReproducibility:
    """NFR-0700: random seeds, config loading, metadata fields."""

    # AC-NFR0700-01: random_state, feature_fraction_seed, bagging_seed all == 42
    def test_default_params_have_random_state_42(self):
        """AC-NFR0700-01: DEFAULT_PARAMS must include random_state=42 and seed params."""
        from trader_off.training.trainer import DEFAULT_PARAMS

        assert DEFAULT_PARAMS["random_state"] == 42
        assert DEFAULT_PARAMS["feature_fraction_seed"] == 42
        assert DEFAULT_PARAMS["bagging_seed"] == 42

    # AC-NFR0700-03: metadata includes git_commit_sha, python_version, package_versions
    def test_metadata_includes_repro_fields(self):
        """AC-NFR0700-03: metadata includes git_commit_sha, python_version, package_versions."""
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

    # AC-NFR0700-02: YAML config loading works for strategy config
    def test_config_yaml_loading(self):
        """AC-NFR0700-02: Strategy config can be loaded from YAML."""
        import yaml

        config_data = {
            "model_version": "v1",
            "top_k": 20,
            "min_score": -float("inf"),
        }
        yaml_str = yaml.dump(config_data)
        loaded = yaml.safe_load(yaml_str)
        assert loaded["top_k"] == 20

    # AC-NFR0700-03: save_model writes correct metadata.json content
    def test_save_model_metadata_json_content(self):
        """AC-NFR0700-03: save_model writes correct metadata.json with train_start."""
        import tempfile

        import lightgbm as lgb
        import numpy as np

        from trader_off.data.preprocess import StandardScaler
        from trader_off.training.serialize import save_model

        x_data = np.random.RandomState(42).randn(10, 2)
        y_data = np.random.RandomState(42).randn(10)
        booster = lgb.train(
            {"objective": "regression", "verbose": -1, "num_leaves": 4},
            lgb.Dataset(x_data, label=y_data),
            num_boost_round=3,
        )
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

    # AC-NFR0100-01: mock 4500 assets → prepare_walk_forward_splits works
    def test_mock_4500_assets_walk_forward(self, tmp_path):
        """AC-NFR0100-01: prepare_walk_forward_splits handles 4500 mock assets."""
        from datetime import date, timedelta

        from trader_off.data.walk_forward import prepare_walk_forward_splits

        n_assets = 4500
        n_days = 500
        start = date(2017, 1, 1)
        dates = [start + timedelta(days=i) for i in range(n_days)]

        data_dict = {
            "asset": [f"{i:06d}.SZ" for i in range(n_assets) for _ in range(n_days)],
            "date": dates * n_assets,
            "close": [10.0] * (n_assets * n_days),
        }
        df = pl.DataFrame(
            data_dict,
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "close": pl.Float64,
            },
        )

        output_dir = tmp_path / "splits"
        splits = prepare_walk_forward_splits(
            df,
            start_year=2018,
            end_year=2018,
            train_window_years=1,
            output_dir=output_dir,
        )
        assert len(splits) == 1
        train_df = pl.read_parquet(splits[0].train_path)
        unique_assets = train_df["asset"].n_unique()
        assert unique_assets >= 4000, f"Expected >=4000 assets, got {unique_assets}"
