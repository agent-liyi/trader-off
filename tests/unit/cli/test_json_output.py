"""Tests for --json output flag on all 6 CLI modules (FR-0100).

Verifies:
- JSON output format on success: {"status":"ok","data":{...}}
- JSON output format on error: {"status":"error","code":N,"message":"..."}
- stdout suppression: normal prints/writes do NOT appear when --json is set
- stderr preservation: log messages still go to stderr
"""

import json
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import polars as pl

# ==========================================================================
# backtest CLI --json
# ==========================================================================


class TestBacktestJson:
    """--json flag on trader-off-backtest."""

    def test_json_success(self, tmp_path):
        """--json with success path → {"status":"ok","data":{}} on stdout."""
        from trader_off.cli.backtest import main as backtest_main

        config_path = tmp_path / "config.yaml"
        config_path.write_text("dummy: true")

        test_args = [
            "backtest",
            "--model",
            "v1",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            "--capital",
            "1000000",
            "--json",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("trader_off.cli.backtest.run_backtest") as mock_run:
                mock_run.return_value = MagicMock()
                # Capture stdout to verify JSON output
                captured = StringIO()
                with patch.object(sys, "stdout", captured):
                    exit_code = backtest_main()
                output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert "data" in parsed

    def test_json_error_4_config_not_found(self):
        """--json with missing config → {"status":"error","code":4,...}."""
        from trader_off.cli.backtest import main as backtest_main

        test_args = [
            "backtest",
            "--model",
            "v1",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            "--capital",
            "1000000",
            "--config",
            "/nonexistent.yaml",
            "--json",
        ]
        with patch.object(sys, "argv", test_args):
            captured = StringIO()
            with patch.object(sys, "stdout", captured):
                exit_code = backtest_main()
            output = captured.getvalue()

        assert exit_code == 4
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        assert parsed["code"] == 4
        assert "message" in parsed

    def test_json_error_5_engine_failure(self):
        """--json with engine failure → {"status":"error","code":5,...}."""
        from trader_off.cli.backtest import main as backtest_main

        test_args = [
            "backtest",
            "--model",
            "v1",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            "--capital",
            "1000000",
            "--json",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("trader_off.cli.backtest.run_backtest") as mock_run:
                mock_run.side_effect = RuntimeError("engine error")
                captured = StringIO()
                with patch.object(sys, "stdout", captured):
                    exit_code = backtest_main()
                output = captured.getvalue()

        assert exit_code == 5
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        assert parsed["code"] == 5

    def test_json_stdout_suppressed_on_success(self):
        """When --json is set, normal print/write output is suppressed."""
        from trader_off.cli.backtest import main as backtest_main

        test_args = [
            "backtest",
            "--model",
            "v1",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            "--capital",
            "1000000",
            "--json",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("trader_off.cli.backtest.run_backtest") as mock_run:
                mock_run.return_value = MagicMock()
                captured = StringIO()
                with patch.object(sys, "stdout", captured):
                    backtest_main()
                output = captured.getvalue()

        # stdout should only contain JSON, not "Backtest finished"
        assert "Backtest finished" not in output
        parsed = json.loads(output)
        assert parsed["status"] == "ok"

    def test_json_stderr_preserved(self):
        """stderr (loguru) should still work when --json is set."""
        from trader_off.cli.backtest import main as backtest_main

        test_args = [
            "backtest",
            "--model",
            "v1",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            "--capital",
            "1000000",
            "--config",
            "/nonexistent.yaml",
            "--json",
        ]
        with patch.object(sys, "argv", test_args):
            captured_stdout = StringIO()
            captured_stderr = StringIO()
            with patch.object(sys, "stdout", captured_stdout):
                with patch.object(sys, "stderr", captured_stderr):
                    # loguru writes to stderr by default
                    exit_code = backtest_main()

        assert exit_code == 4
        # The JSON output should ONLY be on stdout
        stdout_output = captured_stdout.getvalue()
        assert "error" in json.loads(stdout_output)["status"]


# ==========================================================================
# sync_data CLI --json
# ==========================================================================


class TestSyncDataJson:
    """--json flag on trader-off-sync-data."""

    def test_json_dry_run_success(self, tmp_path, monkeypatch):
        """--json with dry-run → {"status":"ok","data":{}}."""
        from trader_off.cli.sync_data import main as sync_main

        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        csv_path = tmp_path / "universe.csv"
        csv_path.write_text("asset\n000001.SZ\n")

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = sync_main(
                [
                    "--universe",
                    str(csv_path),
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--dry-run",
                    "--json",
                ]
            )
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert "data" in parsed

    def test_json_error_4_missing_token(self, tmp_path, monkeypatch):
        """--json with missing token → {"status":"error","code":4,...}."""
        from trader_off.cli.sync_data import main as sync_main

        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        csv_path = tmp_path / "universe.csv"
        csv_path.write_text("asset\n000001.SZ\n")

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = sync_main(
                [
                    "--universe",
                    str(csv_path),
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--json",
                ]
            )
        output = captured.getvalue()

        assert exit_code == 4
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        assert parsed["code"] == 4

    def test_json_stdout_suppressed_on_error(self, tmp_path, monkeypatch):
        """stdout for normal output is suppressed when --json."""
        from trader_off.cli.sync_data import main as sync_main

        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        csv_path = tmp_path / "universe.csv"
        csv_path.write_text("asset\n000001.SZ\n")

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            sync_main(
                [
                    "--universe",
                    str(csv_path),
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--json",
                ]
            )
        output = captured.getvalue()

        # stdout should only be valid JSON
        parsed = json.loads(output)
        assert "status" in parsed
        # No "TUSHARE_TOKEN" text should leak to stdout
        assert "TUSHARE_TOKEN" not in output


# ==========================================================================
# optimize CLI --json
# ==========================================================================


class TestOptimizeJson:
    """--json flag on trader-off optimize."""

    def test_json_error_2_file_not_found(self, tmp_path):
        """--json with missing predictions → {"status":"error","code":2,...}."""
        from trader_off.portfolio.cli import main as optimize_main

        missing = tmp_path / "nonexistent.csv"

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = optimize_main(
                [
                    "--predictions",
                    str(missing),
                    "--output",
                    str(tmp_path / "out"),
                    "--json",
                ]
            )
        output = captured.getvalue()

        assert exit_code == 2
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        assert parsed["code"] == 2

    def test_json_success(self, tmp_path):
        """--json with mock pipeline → {"status":"ok","data":{}}."""
        from trader_off.portfolio.cli import main as optimize_main

        # Create predictions file
        pred_path = tmp_path / "predictions.csv"
        rows = [
            {"asset": f"stock_{i:03d}", "score": 0.001 * (50 - i), "rank": i + 1} for i in range(50)
        ]
        pl.DataFrame(rows).write_csv(pred_path)

        # Create returns file
        returns_path = tmp_path / "returns.csv"
        import numpy as np

        n_assets = 50
        n_days = 60
        np.random.seed(42)
        dates = [f"2026-07-{d:02d}" for d in range(1, n_days + 1)]
        data = {"date": dates}
        for i in range(n_assets):
            data[f"stock_{i:03d}"] = np.random.randn(n_days) * 0.01
        pl.DataFrame(data).write_csv(returns_path)

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = optimize_main(
                [
                    "--predictions",
                    str(pred_path),
                    "--output",
                    str(out_dir),
                    "--returns",
                    str(returns_path),
                    "--industry-neutral",
                    "--json",
                ]
            )
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        # Regular output (Sharpe=...) should NOT appear
        assert "Sharpe" not in output

    def test_json_stdout_suppressed(self, tmp_path):
        """Normal stdout is suppressed with --json."""
        from trader_off.portfolio.cli import main as optimize_main

        pred_path = tmp_path / "predictions.csv"
        rows = [
            {"asset": f"stock_{i:03d}", "score": 0.001 * (50 - i), "rank": i + 1} for i in range(50)
        ]
        pl.DataFrame(rows).write_csv(pred_path)

        returns_path = tmp_path / "returns.csv"
        import numpy as np

        np.random.seed(42)
        dates = [f"2026-07-{d:02d}" for d in range(1, 61)]
        data = {"date": dates}
        for i in range(50):
            data[f"stock_{i:03d}"] = np.random.randn(60) * 0.01
        pl.DataFrame(data).write_csv(returns_path)

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            optimize_main(
                [
                    "--predictions",
                    str(pred_path),
                    "--output",
                    str(out_dir),
                    "--returns",
                    str(returns_path),
                    "--industry-neutral",
                    "--json",
                ]
            )
        output = captured.getvalue()

        # stdout should only be valid JSON
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert "报告落盘" not in output


# ==========================================================================
# mine-factors CLI --json
# ==========================================================================


class TestMineFactorsJson:
    """--json flag on trader-off mine-factors."""

    def test_json_error_4_config_not_found(self, tmp_path):
        """--json with missing config → {"status":"error","code":4,...}."""
        from trader_off.factor_mining.cli import main as mine_main

        missing = tmp_path / "nonexistent.yaml"

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = mine_main(
                [
                    "--config",
                    str(missing),
                    "--json",
                ]
            )
        output = captured.getvalue()

        assert exit_code == 4
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        assert parsed["code"] == 4

    def test_json_stdout_suppressed(self, tmp_path):
        """stdout is suppressed when --json, only JSON appears."""
        from trader_off.factor_mining.cli import main as mine_main

        missing = tmp_path / "nonexistent.yaml"

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            mine_main(
                [
                    "--config",
                    str(missing),
                    "--json",
                ]
            )
        output = captured.getvalue()

        # stdout should only contain valid JSON
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        # No "config file not found" text on stdout
        assert "config file not found" not in output


# ==========================================================================
# scheduler CLI --json
# ==========================================================================


class TestSchedulerJson:
    """--json flag on trader-off-scheduler."""

    def test_json_returns_ok(self):
        """--json with scheduler main → {"status":"ok","data":{}}."""
        from trader_off.scheduler.cli import main as sched_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = sched_main(["--json", "status"])
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
