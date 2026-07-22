"""Tests for init_data CLI — FR-0100.

Covers: argparse exit 2, happy path JSON output, --home,
function-scope lazy import.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Will fail until init_data.py is created (Red phase)
from trader_off.cli.init_data import main  # noqa: E402

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
# Happy path: JSON output + exit 0
# ---------------------------------------------------------------------------


class TestHappyPath:
    """FR-0100: successful init → JSON output, exit 0."""

    @pytest.fixture
    def mock_init_data(self):
        """Mock quantide.data.init_data to avoid real side effects."""
        with patch("quantide.data.init_data") as mock:
            yield mock

    def test_default_home_json_output(self, mock_init_data, tmp_path, monkeypatch):
        """Default home (.quantide/) — JSON output with correct fields."""
        monkeypatch.chdir(tmp_path)
        exit_code = main([])
        assert exit_code == 0
        mock_init_data.assert_called_once()

    def test_home_flag_json_output(self, mock_init_data, tmp_path):
        """--home flag sets custom home — JSON output."""
        home_path = tmp_path / "my_data"
        exit_code = main(["--home", str(home_path)])
        assert exit_code == 0
        mock_init_data.assert_called_once_with(home=home_path)

    def test_home_flag_accepts_any_string(self, mock_init_data):
        """--home accepts any string value without argparse type error."""
        exit_code = main(["--home", "/tmp/test_home"])
        assert exit_code == 0
        mock_init_data.assert_called_once()

    def test_json_output_structure(self, mock_init_data, tmp_path, monkeypatch, capsys):
        """Verify JSON output structure has status, data fields."""
        monkeypatch.chdir(tmp_path)
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert "status" in output
        assert output["status"] == "ok"
        assert "data" in output
        assert "home" in output["data"]

    def test_json_output_home_absolute(self, mock_init_data, tmp_path, capsys):
        """JSON data.home is absolute path."""
        home_path = tmp_path / "abs_data"
        exit_code = main(["--home", str(home_path)])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["home"] == str(home_path.resolve())

    def test_json_output_has_created_fields(self, mock_init_data, tmp_path, monkeypatch, capsys):
        """JSON data has calendar, bars, db fields."""
        monkeypatch.chdir(tmp_path)
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert "calendar" in output["data"]
        assert "bars" in output["data"]
        assert "db" in output["data"]


# ---------------------------------------------------------------------------
# Function-scope lazy import
# ---------------------------------------------------------------------------


class TestLazyImport:
    """FR-0100 / NFR-0100: quantide imports are function-scope only."""

    def test_no_quantide_import_at_module_level(self):
        """Module-level does NOT import quantide eagerly."""
        import ast

        source = Path("src/trader_off/cli/init_data.py").read_text()
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


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """FR-0100: edge cases for init CLI."""

    @pytest.fixture
    def mock_init_data(self):
        with patch("quantide.data.init_data") as mock:
            yield mock

    def test_main_returns_int(self, mock_init_data, tmp_path, monkeypatch):
        """main() return type is int."""
        monkeypatch.chdir(tmp_path)
        result = main([])
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


class TestEntryPoint:
    """FR-0100: module-level entry point works."""

    @pytest.fixture
    def mock_init_data(self):
        with patch("quantide.data.init_data") as mock:
            yield mock

    def test_main_is_callable(self, mock_init_data, tmp_path, monkeypatch):
        """Smoke: import succeeds and main is callable."""
        monkeypatch.chdir(tmp_path)
        result = main([])
        assert isinstance(result, int)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
