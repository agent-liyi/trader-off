"""Unit tests for FR-0200: `trader-off server` CLI entry point.

Covers AC-FR0200-01 through AC-FR0200-05.
Tests argparse setup, default values, --json output, and lazy imports.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# AC-FR0200-02: Default port is 8000
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefaultPort:
    """AC-FR0200-02: Default port is 8000 (NOT 5800)."""

    def test_default_port_is_8000(self):
        """--port default value is 8000."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args([])
        assert args.port == 8000, f"Expected default port 8000, got {args.port}"

    def test_default_port_not_5800(self):
        """--port default is NOT 5800 (qmt-gateway port conflict resolution)."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args([])
        assert args.port != 5800, "Default port must not be 5800 (qmt-gateway conflict)"


# ---------------------------------------------------------------------------
# AC-FR0200-04: Default host is 127.0.0.1
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefaultHost:
    """AC-FR0200-04: Default host is 127.0.0.1."""

    def test_default_host_is_localhost(self):
        """--host default value is 127.0.0.1."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args([])
        assert args.host == "127.0.0.1", f"Expected default host 127.0.0.1, got {args.host}"


# ---------------------------------------------------------------------------
# AC-FR0200-03: --json emits startup JSON
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJsonFlag:
    """AC-FR0200-03: --json flag emits startup JSON line."""

    def test_json_flag_is_boolean(self):
        """--json is a store_true flag."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args(["--json"])
        assert args.json is True

    def test_json_default_is_false(self):
        """--json defaults to False."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args([])
        assert args.json is False


# ---------------------------------------------------------------------------
# AC-FR0200-01: CLI parses --port and --host
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCustomArgs:
    """AC-FR0200-01: Custom --port and --host are parsed correctly."""

    def test_custom_port(self):
        """--port 8888 sets port to 8888."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args(["--port", "8888"])
        assert args.port == 8888

    def test_custom_host(self):
        """--host 0.0.0.0 sets host to 0.0.0.0."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args(["--host", "0.0.0.0"])
        assert args.host == "0.0.0.0"

    def test_combined_args(self):
        """Multiple args are parsed correctly together."""
        from trader_off.cli.server import _build_argparser

        parser = _build_argparser()
        args = parser.parse_args(["--port", "9999", "--host", "0.0.0.0", "--json"])
        assert args.port == 9999
        assert args.host == "0.0.0.0"
        assert args.json is True


# ---------------------------------------------------------------------------
# AC-FR0200-03: --json output shape
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJsonStartupOutput:
    """AC-FR0200-03: --json emits {"status":"ok","data":{"host":"...","port":N}}."""

    def test_json_output_shape(self, capsys):
        """--json prints the expected startup JSON to stdout before launching."""
        from trader_off.cli.server import main

        with patch("uvicorn.run") as mock_run:
            exit_code = main(["--json"])
            captured = capsys.readouterr()

        # uvicorn.run should be called (server still launches after JSON output)
        mock_run.assert_called_once()

        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert "data" in output
        assert output["data"]["host"] == "127.0.0.1"
        assert output["data"]["port"] == 8000
        assert exit_code == 0

    def test_json_output_with_custom_port(self, capsys):
        """--json with --port shows the custom port."""
        from trader_off.cli.server import main

        with patch("uvicorn.run"):
            exit_code = main(["--json", "--port", "9000"])
            captured = capsys.readouterr()

        output = json.loads(captured.out.strip())
        assert output["data"]["port"] == 9000
        assert exit_code == 0


# ---------------------------------------------------------------------------
# AC-FR0200-01: main() launches uvicorn programmatically
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUvicornLaunch:
    """AC-FR0200-01: uvicorn is launched programmatically (not subprocess)."""

    def test_uvicorn_run_called_with_correct_args(self):
        """uvicorn.run(app, host=..., port=...) is called."""
        from trader_off.cli.server import main

        with patch("uvicorn.run") as mock_run:
            exit_code = main(["--port", "8000", "--host", "127.0.0.1"])

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 8000
        assert exit_code == 0

    def test_uvicorn_not_called_as_subprocess(self):
        """uvicorn is imported and called directly, not via subprocess."""
        from trader_off.cli.server import main

        with (
            patch("uvicorn.run") as mock_run,
            patch("subprocess.run") as mock_sp_run,
        ):
            main(["--port", "8000"])
            # subprocess.run should not be called for uvicorn
            mock_run.assert_called_once()
            # The main function itself should not use subprocess
            mock_sp_run.assert_not_called()


# ---------------------------------------------------------------------------
# AC-FR0200-05 / NFR-0100: Lazy imports for fastapi and uvicorn
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLazyImports:
    """AC-FR0200-05: uvicorn/fastapi imported at function scope, not module level."""

    def test_no_uvicorn_import_at_module_level_in_cli_server(self):
        """uvicorn is NOT imported at top level of cli/server.py."""
        server_path = REPO_ROOT / "src" / "trader_off" / "cli" / "server.py"
        source = server_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "uvicorn", (
                        "uvicorn must not be imported at module level in cli/server.py"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module == "uvicorn" or (node.module and node.module.startswith("uvicorn")):
                    pytest.fail("uvicorn must not be imported at module level in cli/server.py")

    def test_no_fastapi_import_at_module_level_in_api_server(self):
        """fastapi is NOT imported at top level of api/server.py."""
        server_path = REPO_ROOT / "src" / "trader_off" / "api" / "server.py"
        source = server_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "fastapi", (
                        "fastapi must not be imported at module level in api/server.py"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module == "fastapi" or (node.module and node.module.startswith("fastapi")):
                    pytest.fail("fastapi must not be imported at module level in api/server.py")

    def test_no_uvicorn_import_at_module_level_in_api_server(self):
        """uvicorn is NOT imported at top level of api/server.py."""
        server_path = REPO_ROOT / "src" / "trader_off" / "api" / "server.py"
        source = server_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "uvicorn", (
                        "uvicorn must not be imported at module level in api/server.py"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module == "uvicorn" or (node.module and node.module.startswith("uvicorn")):
                    pytest.fail("uvicorn must not be imported at module level in api/server.py")


# ---------------------------------------------------------------------------
# AC-NFR0100-02: Dependencies in pyproject.toml
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDependencies:
    """AC-NFR0100-02: fastapi and uvicorn in pyproject.toml dependencies."""

    def test_fastapi_in_dependencies(self):
        """fastapi>=0.115,<1.0 is in project.dependencies."""
        import tomllib

        pyproject = REPO_ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        deps = data["project"]["dependencies"]
        assert any("fastapi" in d for d in deps), f"fastapi not found in dependencies: {deps}"

    def test_uvicorn_in_dependencies(self):
        """uvicorn[standard]>=0.34,<1.0 is in project.dependencies."""
        import tomllib

        pyproject = REPO_ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        deps = data["project"]["dependencies"]
        assert any("uvicorn" in d for d in deps), f"uvicorn not found in dependencies: {deps}"
