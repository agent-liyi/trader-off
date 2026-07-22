"""Tests for trader-off status command (FR-0200).

Subcommands:
- status (default): global status JSON
- status data: check .quantide/bars/ directory
- status models: check factor_registry/ directory
- status scheduler: check scheduler running state
"""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import polars as pl

# ==========================================================================
# Global status (no subcommand)
# ==========================================================================


class TestStatusGlobal:
    """trader-off status → JSON with version, data_source, models, scheduler."""

    def test_global_status_output(self):
        """trader-off status outputs valid JSON with expected keys."""
        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main([])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        data = parsed["data"]
        assert "version" in data
        assert "data_source" in data
        assert "models" in data
        assert "scheduler" in data

    def test_global_status_version(self):
        """The version field is present and non-empty."""
        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main([])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert isinstance(parsed["data"]["version"], str)
        assert len(parsed["data"]["version"]) > 0


# ==========================================================================
# status data
# ==========================================================================


class TestStatusData:
    """trader-off status data → data source info."""

    def test_data_no_directory(self, tmp_path, monkeypatch):
        """When .quantide/bars/ doesn't exist → {"data_source":"none"}."""
        monkeypatch.chdir(tmp_path)

        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main(["data"])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["data_source"] == "none"

    def test_data_with_directory(self, tmp_path, monkeypatch):
        """When .quantide/bars/ exists with parquet files → scan and report."""
        monkeypatch.chdir(tmp_path)
        bars_dir = Path(".quantide/bars")
        bars_dir.mkdir(parents=True)

        # Create a sample parquet file
        df = pl.DataFrame(
            {
                "asset": ["000001.SZ", "000002.SZ"],
                "date": ["2024-01-02", "2024-01-02"],
                "close": [10.0, 20.0],
            }
        )
        df.write_parquet(bars_dir / "year=2024.parquet")

        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main(["data"])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        data = parsed["data"]
        assert data["data_source"] == "fixture"
        assert data["file_count"] >= 1


# ==========================================================================
# status models
# ==========================================================================


class TestStatusModels:
    """trader-off status models → factor registry info."""

    def test_models_no_directory(self, tmp_path, monkeypatch):
        """When factor_registry/ doesn't exist → empty models list."""
        monkeypatch.chdir(tmp_path)

        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main(["models"])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["models"] == []

    def test_models_with_files(self, tmp_path, monkeypatch):
        """When factor_registry/ has parquet files → list them."""
        monkeypatch.chdir(tmp_path)
        registry_dir = Path("factor_registry")
        registry_dir.mkdir(parents=True)
        (registry_dir / "registry.parquet").touch()
        (registry_dir / "factor_001.parquet").touch()

        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main(["models"])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert len(parsed["data"]["models"]) == 2


# ==========================================================================
# status scheduler
# ==========================================================================


class TestStatusScheduler:
    """trader-off status scheduler → scheduler running state."""

    def test_scheduler_stopped(self):
        """Default: scheduler is stopped."""
        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main(["scheduler"])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["scheduler"] == "stopped"


# ==========================================================================
# No subcommand arg count
# ==========================================================================


class TestStatusInvalidArgs:
    """Invalid subcommands."""

    def test_unknown_subcommand(self):
        """Unknown subcommand should still return a valid JSON error."""
        from trader_off.cli.status import main as status_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = status_main(["invalid_cmd"])
        output = captured.getvalue()

        assert exit_code != 0
        parsed = json.loads(output)
        assert parsed["status"] == "error"
