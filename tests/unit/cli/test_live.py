"""Tests for live CLI — FR-0100.

Covers: argparse exit 2, happy path JSON output for --start/--stop/--status,
function-scope lazy import, no-gateway error handling.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Will fail until live.py is created (Red phase)
from trader_off.cli.live import main  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_live_quote():
    """Create a mock LiveQuote singleton instance."""
    mock = MagicMock()
    mock.is_running = False
    mock.mode = None
    return mock


# ---------------------------------------------------------------------------
# Exit code 2: Argparse errors
# ---------------------------------------------------------------------------


class TestArgparseExit2:
    """FR-0100: argparse failures → exit code 2."""

    def test_unknown_arg_exits_2(self):
        """Unknown flag → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--unknown"])
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# --status (default)
# ---------------------------------------------------------------------------


class TestStatus:
    """FR-0100: --status (default) → JSON output with running flag."""

    def test_status_not_running_default(self, mock_live_quote, capsys):
        """Default (no flags) should check status — not running."""
        mock_live_quote.is_running = False
        mock_live_quote.mode = None

        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            exit_code = main([])

        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert output["data"]["running"] is False

    def test_status_running_explicit(self, mock_live_quote, capsys):
        """--status flag when running."""
        mock_live_quote.is_running = True
        mock_live_quote.mode = "gateway"

        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            exit_code = main(["--status"])

        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["running"] is True


# ---------------------------------------------------------------------------
# --start
# ---------------------------------------------------------------------------


class TestStart:
    """FR-0100: --start → start LiveQuote singleton, return JSON."""

    def test_start_success(self, mock_live_quote, capsys):
        """--start calls LiveQuote.start() and returns running status."""
        mock_live_quote.is_running = False

        def start_side_effect():
            mock_live_quote.is_running = True
            mock_live_quote.mode = "gateway"

        mock_live_quote.start.side_effect = start_side_effect

        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            exit_code = main(["--start"])

        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert output["data"]["running"] is True
        assert output["data"]["connected"] is True
        mock_live_quote.start.assert_called_once()

    def test_start_with_assets(self, mock_live_quote, capsys):
        """--start with --assets includes assets in output."""
        mock_live_quote.is_running = True

        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            exit_code = main(["--start", "--assets", "000001.SZ,600000.SH"])

        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["assets"] == ["000001.SZ", "600000.SH"]


# ---------------------------------------------------------------------------
# --stop
# ---------------------------------------------------------------------------


class TestStop:
    """FR-0100: --stop → stop LiveQuote, return JSON."""

    def test_stop_success(self, mock_live_quote, capsys):
        """--stop calls LiveQuote.stop() and returns stopped status."""
        mock_live_quote.is_running = True

        def stop_side_effect():
            mock_live_quote.is_running = False

        mock_live_quote.stop.side_effect = stop_side_effect

        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            exit_code = main(["--stop"])

        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert output["data"]["running"] is False
        mock_live_quote.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Gateway error handling
# ---------------------------------------------------------------------------


class TestGatewayError:
    """FR-0100: no qmt-gateway → error JSON with code 4, exit 4."""

    def test_start_no_gateway(self, capsys):
        """--start when LiveQuote constructor fails → error JSON, exit 4."""
        with patch(
            "quantide.service.livequote.LiveQuote",
            side_effect=RuntimeError("set gateway_base_url in config"),
        ):
            exit_code = main(["--start"])

        captured = capsys.readouterr()
        assert exit_code == 4
        output = json.loads(captured.out.strip())
        assert output["status"] == "error"
        assert output["code"] == 4
        assert "set gateway_base_url in config" in output["message"]

    def test_status_no_gateway(self, capsys):
        """Default status when LiveQuote is unavailable → error JSON, exit 4."""
        with patch(
            "quantide.service.livequote.LiveQuote",
            side_effect=RuntimeError("set gateway_base_url in config"),
        ):
            exit_code = main([])

        captured = capsys.readouterr()
        assert exit_code == 4
        output = json.loads(captured.out.strip())
        assert output["status"] == "error"
        assert output["code"] == 4

    def test_stop_no_gateway(self, capsys):
        """--stop when LiveQuote is unavailable → error JSON, exit 4."""
        with patch(
            "quantide.service.livequote.LiveQuote",
            side_effect=RuntimeError("set gateway_base_url in config"),
        ):
            exit_code = main(["--stop"])

        captured = capsys.readouterr()
        assert exit_code == 4
        output = json.loads(captured.out.strip())
        assert output["status"] == "error"
        assert output["code"] == 4


# ---------------------------------------------------------------------------
# --json flag compatibility
# ---------------------------------------------------------------------------


class TestJsonFlag:
    """FR-0100: --json flag accepted for compatibility (output is always JSON)."""

    def test_json_flag_output(self, mock_live_quote, capsys):
        """--json flag produces valid JSON output."""
        mock_live_quote.is_running = False

        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            exit_code = main(["--status", "--json"])

        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"


# ---------------------------------------------------------------------------
# NFR-0100: function-scope lazy import
# ---------------------------------------------------------------------------


class TestNFR0100:
    """NFR-0100: quantide imports are function-scope only in live.py."""

    def test_no_top_level_quantide_import(self):
        """Module-level does NOT import quantide eagerly."""
        import ast

        source = Path("src/trader_off/cli/live.py").read_text()
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("quantide"), (
                        f"Module-level import of quantide found: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.module is None or not node.module.startswith("quantide"), (
                    f"Module-level import of quantide found: {node.module}"
                )

    def test_whitelisted_import_only(self):
        """Only quantide.service.livequote.LiveQuote is imported (allowlist)."""
        source = Path("src/trader_off/cli/live.py").read_text()

        # Banned quantide submodules
        banned = [
            "quantide.data",
            "quantide.portfolio",
            "quantide.backtest",
            "quantide.core.scheduler",
            "quantide.config",
        ]
        for b in banned:
            assert b not in source, f"Banned quantide import found: {b}"

        # Must contain the whitelisted import
        assert "quantide.service.livequote" in source, (
            "Missing whitelisted import: quantide.service.livequote"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """FR-0100: edge cases for live CLI."""

    def test_main_returns_int(self, mock_live_quote):
        """main() return type is int."""
        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            result = main([])
        assert isinstance(result, int)

    def test_empty_assets_returns_empty_list(self, mock_live_quote, capsys):
        """--assets with empty string results in empty list."""
        mock_live_quote.is_running = True

        with patch("quantide.service.livequote.LiveQuote", return_value=mock_live_quote):
            exit_code = main(["--start", "--assets", ""])

        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["assets"] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
