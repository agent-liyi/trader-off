"""Unit tests for generate_strategy CLI — FR-0100.

Covers: argparse exit 2, dry-run output, file creation, JSON output,
existing file skip/dedup, template content verification.
"""

from __future__ import annotations

import json

import pytest

from trader_off.cli.generate_strategy import (
    _camel_to_snake,
    _dedup_filename,
    _generate_code,
    main,
)

# ---------------------------------------------------------------------------
# CamelCase → snake_case
# ---------------------------------------------------------------------------


class TestCamelToSnake:
    """Unit tests for _camel_to_snake helper."""

    def test_simple_camel(self):
        """Simple CamelCase → snake_case."""
        assert _camel_to_snake("MyStrategy") == "my_strategy"

    def test_multi_word(self):
        """Multi-word CamelCase."""
        assert _camel_to_snake("MomentumReversion") == "momentum_reversion"

    def test_acronym(self):
        """Acronym LGBMTop20 → lgbm_top20."""
        assert _camel_to_snake("LGBMTop20") == "lgbm_top20"

    def test_optimized_topk(self):
        """OptimizedTopK → optimized_top_k."""
        assert _camel_to_snake("OptimizedTopK") == "optimized_top_k"

    def test_single_word(self):
        """Single word stays lowercase."""
        assert _camel_to_snake("Strategy") == "strategy"

    def test_already_snake(self):
        """Already snake_case stays unchanged."""
        assert _camel_to_snake("my_strategy") == "my_strategy"


# ---------------------------------------------------------------------------
# Filename deduplication
# ---------------------------------------------------------------------------


class TestDedupFilename:
    """Unit tests for _dedup_filename helper."""

    def test_no_conflict(self, tmp_path):
        """No existing file → returns original name."""
        target = tmp_path / "momentum_reversion.py"
        result = _dedup_filename(target)
        assert result == target

    def test_one_conflict(self, tmp_path):
        """File exists → suffix with _1."""
        target = tmp_path / "momentum_reversion.py"
        target.write_text("")
        result = _dedup_filename(target)
        assert result == tmp_path / "momentum_reversion_1.py"

    def test_multiple_conflicts(self, tmp_path):
        """Multiple files exist → find next available suffix."""
        (tmp_path / "momentum_reversion.py").write_text("")
        (tmp_path / "momentum_reversion_1.py").write_text("")
        result = _dedup_filename(target=tmp_path / "momentum_reversion.py")
        assert result == tmp_path / "momentum_reversion_2.py"

    def test_partial_suffix_match(self, tmp_path):
        """Suffix collision with unrelated files doesn't confuse dedup."""
        (tmp_path / "momentum_reversion.py").write_text("")
        (tmp_path / "momentum_reversion_1.py").write_text("")
        (tmp_path / "momentum_reversion_other.py").write_text("")
        result = _dedup_filename(target=tmp_path / "momentum_reversion.py")
        assert result == tmp_path / "momentum_reversion_2.py"


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


class TestGenerateCode:
    """Unit tests for _generate_code function."""

    def test_class_name_in_output(self):
        """Generated code contains the correct class name."""
        code = _generate_code("MomentumReversion", author="tester", description="Test strategy")
        assert "class MomentumReversion(BaseStrategy)" in code

    def test_module_docstring_has_description(self):
        """Module docstring includes the description."""
        code = _generate_code("MomentumReversion", author="tester", description="My desc")
        assert "My desc" in code

    def test_module_docstring_has_author(self):
        """Module docstring includes author."""
        code = _generate_code("MomentumReversion", author="tester", description="Test strategy")
        assert "tester" in code

    def test_module_docstring_has_date(self):
        """Module docstring includes generation date."""
        from datetime import date

        code = _generate_code("MomentumReversion", author="tester", description="Test strategy")
        assert str(date.today()) in code

    def test_import_from_compat(self):
        """Generated code imports BaseStrategy from compat."""
        code = _generate_code("MomentumReversion", author="tester", description="Test strategy")
        assert "from trader_off.strategies.compat import BaseStrategy" in code

    def test_imports_logger(self):
        """Generated code imports loguru logger."""
        code = _generate_code("MomentumReversion", author="tester", description="Test strategy")
        assert "from loguru import logger" in code

    def test_imports_datetime(self):
        """Generated code imports datetime."""
        code = _generate_code("MomentumReversion", author="tester", description="Test strategy")
        assert "from datetime import datetime" in code

    def test_has_5_methods(self):
        """Generated code has exactly 5 methods: __init__ + 4 lifecycle."""
        code = _generate_code("MyStrat", author="a", description="d")
        # Count "def " lines that are methods (not super().__init__ calls etc)
        method_defs = [
            line
            for line in code.splitlines()
            if line.strip().startswith("def ") or line.strip().startswith("async def ")
        ]
        assert len(method_defs) == 5, f"Expected 5 methods, got {len(method_defs)}"

    def test_method_names(self):
        """Generated code contains all 5 expected method names."""
        code = _generate_code("MyStrat", author="a", description="d")
        assert "def __init__" in code
        assert "async def on_day_open" in code
        assert "async def on_bar" in code
        assert "async def on_day_close" in code
        assert "async def on_stop" in code

    def test_methods_have_debug_logs(self):
        """Each method body has a logger.debug line."""
        code = _generate_code("MyStrat", author="a", description="d")
        class_name = "MyStrat"
        assert f'logger.debug("{class_name}.__init__ called")' in code
        assert f'logger.debug("{class_name}.on_day_open called")' in code
        assert f'logger.debug("{class_name}.on_bar called")' in code
        assert f'logger.debug("{class_name}.on_day_close called")' in code
        assert f'logger.debug("{class_name}.on_stop called")' in code

    def test_init_calls_super(self):
        """__init__ calls super().__init__(broker, config)."""
        code = _generate_code("MyStrat", author="a", description="d")
        assert "super().__init__(broker, config)" in code

    def test_default_author(self):
        """Default author is 'trader-off'."""
        code = _generate_code("MyStrat", description="d")
        assert "trader-off" in code

    def test_default_description(self):
        """Default description is 'Generated strategy'."""
        code = _generate_code("MyStrat", author="a")
        assert "Generated strategy" in code


# ---------------------------------------------------------------------------
# CLI: argparse (exit 2)
# ---------------------------------------------------------------------------


class TestArgparseExit2:
    """FR-0100: argparse failures → exit code 2."""

    def test_missing_name_exits_2(self):
        """Missing --name → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2

    def test_unknown_arg_exits_2(self):
        """Unknown flag → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--name", "Test", "--unknown"])
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# CLI: dry-run output
# ---------------------------------------------------------------------------


class TestDryRun:
    """FR-0100: --dry-run prints generated code to stdout."""

    def test_dry_run_prints_code(self, capsys):
        """--dry-run prints generated code to stdout."""
        exit_code = main(["--name", "MyStrategy", "--dry-run"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "class MyStrategy(BaseStrategy)" in captured.out

    def test_dry_run_exit_code_zero(self, capsys):
        """--dry-run exits with 0."""
        exit_code = main(["--name", "MyStrategy", "--dry-run"])
        assert exit_code == 0

    def test_dry_run_no_json(self, capsys):
        """--dry-run (without --json) prints code, not JSON."""
        exit_code = main(["--name", "MyStrategy", "--dry-run"])
        captured = capsys.readouterr()
        assert exit_code == 0
        # Should NOT be valid JSON with status/data
        try:
            data = json.loads(captured.out.strip())
            # If it's valid JSON, it shouldn't have "status": "ok"
            assert data.get("status") != "ok", "dry-run without --json should not output JSON"
        except json.JSONDecodeError:
            # Not JSON at all — this is expected for dry-run without --json
            pass

    def test_dry_run_with_json_outputs_json(self, capsys):
        """--dry-run --json prints JSON with generated code content."""
        exit_code = main(["--name", "MyStrategy", "--dry-run", "--json"])
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert "code" in output["data"]
        assert "class MyStrategy(BaseStrategy)" in output["data"]["code"]

    def test_dry_run_does_not_write_file(self, tmp_path):
        """--dry-run does NOT create any file on disk."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--dry-run",
                "--output-dir",
                str(strategies_dir),
            ]
        )
        assert exit_code == 0
        files = list(strategies_dir.glob("*.py"))
        assert len(files) == 0, f"dry-run should not write files, found: {files}"


# ---------------------------------------------------------------------------
# CLI: file creation
# ---------------------------------------------------------------------------


class TestFileCreation:
    """FR-0100: writing strategy file to output-dir."""

    def test_file_created_in_output_dir(self, tmp_path):
        """File written to output-dir with correct name."""
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert exit_code == 0
        expected_file = tmp_path / "my_strategy.py"
        assert expected_file.exists()

    def test_file_content_has_class(self, tmp_path):
        """Written file contains the correct class definition."""
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert exit_code == 0
        content = (tmp_path / "my_strategy.py").read_text()
        assert "class MyStrategy(BaseStrategy)" in content

    def test_file_content_has_imports(self, tmp_path):
        """Written file has correct imports."""
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert exit_code == 0
        content = (tmp_path / "my_strategy.py").read_text()
        assert "from trader_off.strategies.compat import BaseStrategy" in content
        assert "from loguru import logger" in content

    def test_json_output_on_success(self, tmp_path, capsys):
        """Successful file creation prints JSON to stdout."""
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--output-dir",
                str(tmp_path),
            ]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert output["data"]["class"] == "MyStrategy"
        assert output["data"]["methods"] == 5
        assert output["data"]["file"].endswith("my_strategy.py")

    def test_existing_file_dedup(self, tmp_path):
        """When file exists, creates with numeric suffix."""
        # Pre-create the file
        (tmp_path / "my_strategy.py").write_text("# existing")
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert exit_code == 0
        # Should create my_strategy_1.py
        assert (tmp_path / "my_strategy_1.py").exists()
        # Original untouched
        assert (tmp_path / "my_strategy.py").read_text() == "# existing"

    def test_existing_file_json_path(self, tmp_path, capsys):
        """JSON output reflects the dedup filename."""
        (tmp_path / "my_strategy.py").write_text("# existing")
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--output-dir",
                str(tmp_path),
            ]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["file"].endswith("my_strategy_1.py")


# ---------------------------------------------------------------------------
# CLI: --json flag behavior
# ---------------------------------------------------------------------------


class TestJsonFlag:
    """FR-0100: --json flag for JSON output per v0.5.4 standard."""

    def test_json_output_structure(self, tmp_path, capsys):
        """--json produces valid JSON with status/data/file/class/methods."""
        exit_code = main(
            [
                "--name",
                "MyStrategy",
                "--output-dir",
                str(tmp_path),
                "--json",
            ]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert "status" in output
        assert output["status"] == "ok"
        assert "data" in output
        assert "file" in output["data"]
        assert "class" in output["data"]
        assert "methods" in output["data"]


# ---------------------------------------------------------------------------
# CLI: author and description
# ---------------------------------------------------------------------------


class TestAuthorAndDescription:
    """FR-0100: --author and --description flags."""

    def test_custom_author(self, capsys):
        """--author flag overrides default."""
        exit_code = main(["--name", "Test", "--author", "Alice", "--dry-run"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Alice" in captured.out

    def test_custom_description(self, capsys):
        """--description flag overrides default."""
        exit_code = main(["--name", "Test", "--description", "Custom desc", "--dry-run"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Custom desc" in captured.out

    def test_default_author_is_trader_off(self, capsys):
        """Default author is 'trader-off'."""
        exit_code = main(["--name", "Test", "--dry-run"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "trader-off" in captured.out

    def test_default_description_is_generated_strategy(self, capsys):
        """Default description is 'Generated strategy'."""
        exit_code = main(["--name", "Test", "--dry-run"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Generated strategy" in captured.out


# ---------------------------------------------------------------------------
# CLI: return type
# ---------------------------------------------------------------------------


class TestReturnType:
    """FR-0100: main() returns int."""

    def test_main_returns_int_dry_run(self):
        """main() returns int for dry-run."""
        result = main(["--name", "Test", "--dry-run"])
        assert isinstance(result, int)

    def test_main_returns_int_file_creation(self, tmp_path):
        """main() returns int for file creation."""
        result = main(["--name", "Test", "--output-dir", str(tmp_path)])
        assert isinstance(result, int)
