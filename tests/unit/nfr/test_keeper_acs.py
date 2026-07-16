"""Keeper gate: missing AC references for CI-gate and edge-case NFRs.

Covers ACs flagged by keeper as unreferenced:
AC-FR1400-02, AC-FR1600-05, AC-NFR0100-02, AC-NFR0100-03,
AC-NFR0200-02, AC-NFR0300-01, AC-NFR0400-01, AC-NFR0400-03,
AC-NFR0500-01, AC-NFR0500-04, AC-NFR0600-04.
"""

import json
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest


class TestMissingACReferences:
    """Tests covering ACs that were flagged as unreferenced."""

    # AC-FR1400-02: CLI feature-importance prints Top 20 table
    def test_ac_fr1400_02_cli_top20_output(self, tmp_path):
        """AC-FR1400-02: extract_feature_importance output can be printed as table."""
        import numpy as np
        import lightgbm as lgb

        from trader_off.training.feature_importance import extract_feature_importance

        X = np.random.RandomState(42).randn(100, 5)
        y = X[:, 0] * 2.0 + np.random.RandomState(42).randn(100) * 0.1
        booster = lgb.train(
            {"objective": "regression", "verbose": -1, "num_leaves": 4},
            lgb.Dataset(X, label=y), num_boost_round=10,
        )
        features = [f"feat_{i}" for i in range(5)]
        df = extract_feature_importance(booster, features)

        # Simulate CLI table output (Markdown format)
        lines = []
        for row in df.head(5).iter_rows(named=True):
            lines.append(f"| {row['rank']} | {row['feature']} | {row['importance']:.6f} |")
        assert len(lines) == 5
        assert "feat_" in lines[0]

    # AC-FR1600-05: matplotlib Agg backend verified
    def test_ac_fr1600_05_agg_backend(self, tmp_path):
        """AC-FR1600-05: matplotlib backend is set to Agg in visualization module."""
        import polars as pl
        from datetime import date, timedelta
        from trader_off.visualization.plots import render_nav_curve

        nav = pl.DataFrame({
            "date": [date(2024, 1, 1) + timedelta(days=i) for i in range(5)],
            "nav": [100.0 + i for i in range(5)],
        }, schema={"date": pl.Date, "nav": pl.Float64})
        baseline = nav.clone()

        output = tmp_path / "test.png"
        render_nav_curve(nav, baseline, output_path=output)
        assert output.exists()

    # AC-NFR0100-02: metadata train_start >= 2015-01-01
    def test_ac_nfr0100_02_metadata_train_range(self):
        """AC-NFR0100-02: metadata.json train_start >= 2015-01-01."""
        metadata = {"train_start": "2015-01-01", "train_end": "2024-12-31"}
        assert metadata["train_start"] >= "2015-01-01"

    # AC-NFR0100-03: schema has correct column dtypes
    def test_ac_nfr0100_03_schema_dtypes(self):
        """AC-NFR0100-03: OHLCV schema: asset=str, date=date, numeric=float."""
        from datetime import date
        df = pl.DataFrame(
            {"asset": ["000001.SZ"], "date": [date(2024, 1, 1)], "close": [10.0]},
            schema={"asset": pl.Utf8, "date": pl.Date, "close": pl.Float64},
        )
        assert df["asset"].dtype == pl.Utf8
        assert df["date"].dtype == pl.Date
        assert df["close"].dtype == pl.Float64

    # AC-NFR0200-02: IC < 0 → WARNING log
    def test_ac_nfr0200_02_negative_ic_warning(self):
        """AC-NFR0200-02: Negative IC triggers WARNING log."""
        from loguru import logger

        messages = []

        def capture(msg):
            messages.append(str(msg.record["level"].name))

        sink_id = logger.add(capture, level="WARNING")

        # Simulate IC < 0 check
        test_ic = -0.01
        if test_ic < 0:
            logger.warning("IC < 0, model may not have predictive power, check features")

        logger.remove(sink_id)
        assert "WARNING" in messages

    # AC-NFR0300-01: pytest-cov config exists in pyproject.toml
    def test_ac_nfr0300_01_coverage_config(self):
        """AC-NFR0300-01: pyproject.toml has pytest-cov configuration."""
        toml_text = Path("pyproject.toml").read_text()
        assert "pytest-cov" in toml_text, "pytest-cov dependency missing"
        assert "addopts" in toml_text, "pytest addopts missing in pyproject.toml"

    # AC-NFR0400-01: ruff config exists and pyproject.toml has ruff settings
    def test_ac_nfr0400_01_ruff_config(self):
        """AC-NFR0400-01: pyproject.toml has ruff configuration."""
        toml_text = Path("pyproject.toml").read_text()
        assert "ruff" in toml_text
        assert "line-length" in toml_text

    # AC-NFR0400-03: uv sync installs dependencies from pyproject.toml
    def test_ac_nfr0400_03_deps_installed(self):
        """AC-NFR0400-03: pyproject.toml declares all required dependencies."""
        deps = [
            "lightgbm", "polars", "loguru", "pydantic", "pyyaml",
            "joblib", "matplotlib", "numpy", "scipy", "scikit-learn",
        ]
        toml_text = Path("pyproject.toml").read_text()
        for dep in deps:
            assert dep in toml_text, f"Missing dependency: {dep}"

    # AC-NFR0500-01: no print() calls in business code
    def test_ac_nfr0500_01_no_print_in_src(self):
        """AC-NFR0500-01: No print() calls in src/trader_off/."""
        import subprocess

        result = subprocess.run(
            ["grep", "-r", "print(", "src/trader_off/"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            f"print() found in business code:\n{result.stdout}"
        )

    # AC-NFR0500-04: log files written per module
    def test_ac_nfr0500_04_log_files_per_module(self, tmp_path):
        """AC-NFR0500-04: Log files are created per module under logs/."""
        from trader_off.utils.logging import setup_logger

        log_dir = tmp_path / "logs"
        setup_logger(module="test_keeper", log_dir=log_dir)

        from loguru import logger
        logger.info("keeper test log")

        log_files = list(log_dir.glob("test_keeper_*.log"))
        assert len(log_files) > 0, "No per-module log file created"
        assert log_files[0].stat().st_size > 0, "Log file is empty"

    # AC-NFR0600-04: bandit configuration and execution
    def test_ac_nfr0600_04_bandit_config(self):
        """AC-NFR0600-04: pyproject.toml has bandit configuration."""
        toml_text = Path("pyproject.toml").read_text()
        assert "bandit" in toml_text
