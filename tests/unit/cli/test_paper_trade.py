"""Tests for paper_trade CLI with --json flag (FR-0100).

The paper_trade CLI is a minimal module created for the v0.5.4 agent CLI.
It currently provides a stub that can be extended later.
"""

import json
import sys
from io import StringIO
from unittest.mock import patch


class TestPaperTradeJson:
    """--json flag on trader-off-paper-trade."""

    def test_json_success(self, tmp_path):
        """--json with basic args → {"status":"ok","data":{}}."""
        from trader_off.cli.paper_trade import main as paper_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = paper_main(
                [
                    "--strategy",
                    "optimized_topk",
                    "--universe",
                    str(tmp_path),
                    "--capital",
                    "1000000",
                    "--json",
                ]
            )
        output = captured.getvalue()

        assert exit_code == 0
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
        assert "data" in parsed

    def test_json_error_4_missing_universe(self, tmp_path):
        """Missing universe file → {"status":"error","code":4,...}."""
        from trader_off.cli.paper_trade import main as paper_main

        missing = tmp_path / "nonexistent.csv"

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            exit_code = paper_main(
                [
                    "--strategy",
                    "optimized_topk",
                    "--universe",
                    str(missing),
                    "--capital",
                    "1000000",
                    "--json",
                ]
            )
        output = captured.getvalue()

        assert exit_code == 4
        parsed = json.loads(output)
        assert parsed["status"] == "error"
        assert parsed["code"] == 4

    def test_json_stdout_suppressed(self, tmp_path):
        """Normal print output is suppressed when --json is set."""
        from trader_off.cli.paper_trade import main as paper_main

        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            paper_main(
                [
                    "--strategy",
                    "optimized_topk",
                    "--universe",
                    str(tmp_path),
                    "--capital",
                    "1000000",
                    "--json",
                ]
            )
        output = captured.getvalue()

        # stdout should only be valid JSON
        parsed = json.loads(output)
        assert parsed["status"] == "ok"
