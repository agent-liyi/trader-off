"""Unit tests for v0.4.2-001-console-scripts: [project.scripts] entry points.

Covers AC-FR0100-04, AC-NFR0100-03, AC-FR0100-05, AC-NFR0100-04.
"""

import ast
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
README_MD = REPO_ROOT / "README.md"


# ---------------------------------------------------------------------------
# AC-FR0100-04: pyproject.toml [project.scripts] table validation
# ---------------------------------------------------------------------------


class TestPyprojectScripts:
    EXPECTED_SCRIPTS = {
        "trader-off-backtest": "trader_off.cli.backtest:main",
        "trader-off-optimize": "trader_off.portfolio.cli:main",
        "trader-off-mine-factors": "trader_off.factor_mining.cli:main",
        "trader-off-scheduler": "trader_off.scheduler.cli:main",
        "trader-off-sync-data": "trader_off.cli.sync_data:main",
        "trader-off-init": "trader_off.cli.init_data:main",
        "trader-off-stock-list": "trader_off.cli.stock_list:main",
        "trader-off-grid-search": "trader_off.cli.grid_search:main",
    }

    @pytest.fixture
    def pyproject_data(self) -> dict:
        """Parse pyproject.toml and return the raw dict."""
        with open(PYPROJECT_TOML, "rb") as f:
            return tomllib.load(f)

    def test_project_scripts_table_exists(self, pyproject_data: dict):
        """AC-FR0100-04: [project.scripts] table must exist."""
        project = pyproject_data.get("project", {})
        assert "scripts" in project, "[project.scripts] table is missing"

    def test_project_scripts_has_exactly_8_entries(self, pyproject_data: dict):
        """AC-FR0100-04: [project.scripts] must have exactly 8 entries."""
        scripts = pyproject_data.get("project", {}).get("scripts", {})
        assert len(scripts) == 8, (
            f"Expected 8 entries in [project.scripts], got {len(scripts)}: {scripts}"
        )

    def test_project_scripts_values_are_correct(self, pyproject_data: dict):
        """AC-FR0100-04: entry point values match spec."""
        scripts = pyproject_data.get("project", {}).get("scripts", {})
        for key, expected_value in self.EXPECTED_SCRIPTS.items():
            assert key in scripts, f"Missing entry: {key}"
            assert scripts[key] == expected_value, (
                f"Entry {key!r}: expected {expected_value!r}, got {scripts[key]!r}"
            )


# ---------------------------------------------------------------------------
# AC-NFR0100-03: AST validation of 4 main() function signatures
# ---------------------------------------------------------------------------

_SIGS = {
    "src/trader_off/cli/backtest.py": {
        "line": 20,
        "name": "main",
        "args": [],
        "returns": None,
    },
    "src/trader_off/portfolio/cli.py": {
        "line": 220,
        "name": "main",
        "args": [("argv", "list[str] | None", "None")],
        "returns": "int",
    },
    "src/trader_off/factor_mining/cli.py": {
        "line": 383,
        "name": "main",
        "args": [("argv", "list[str] | None", "None")],
        "returns": "int",
    },
    "src/trader_off/scheduler/cli.py": {
        "line": 445,
        "name": "main",
        "args": [("args", "list[str] | None", "None")],
        "returns": "int",
    },
    "src/trader_off/cli/sync_data.py": {
        "line": 26,
        "name": "main",
        "args": [("argv", "list[str] | None", "None")],
        "returns": "int",
    },
    "src/trader_off/cli/init_data.py": {
        "line": 19,
        "name": "main",
        "args": [("argv", "list[str] | None", "None")],
        "returns": "int",
    },
    "src/trader_off/cli/stock_list.py": {
        "line": 23,
        "name": "main",
        "args": [("argv", "list[str] | None", "None")],
        "returns": "int",
    },
}

_CLI_PATHS = list(_SIGS.keys())
_CLI_IDS = [
    "backtest",
    "portfolio",
    "factor_mining",
    "scheduler",
    "sync_data",
    "init_data",
    "stock_list",
]


def _parse_annotation(node: ast.expr | None) -> str | None:
    """Convert AST annotation node back to a readable string."""
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _parse_annotation(node.left)
        right = _parse_annotation(node.right)
        return f"{left} | {right}"
    if isinstance(node, ast.Subscript):
        base = _parse_annotation(node.value)
        s = _parse_annotation(node.slice)
        return f"{base}[{s}]"
    return ast.unparse(node)


def _find_main_function(filepath: Path) -> tuple[ast.FunctionDef | None, str]:
    """Parse file and return the main() FunctionDef node and source."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node, source
    return None, source


def _params():
    """Build parametrize entries for CLI file tests."""
    return pytest.mark.parametrize(
        "rel_path, expected",
        [(p, _SIGS[p]) for p in _CLI_PATHS],
        ids=_CLI_IDS,
    )


class TestCliSignatures:
    @_params()
    def test_main_function_exists_and_at_correct_line(self, rel_path: str, expected: dict):
        """AC-FR0100-02: main() function exists at expected line number."""
        filepath = REPO_ROOT / rel_path
        func_node, _source = _find_main_function(filepath)
        assert func_node is not None, f"main() not found in {rel_path}"
        assert func_node.lineno == expected["line"], (
            f"main() in {rel_path}: expected line {expected['line']}, got {func_node.lineno}"
        )

    @_params()
    def test_main_function_args_match_expected(self, rel_path: str, expected: dict):
        """AC-FR0100-03: main() function arg annotations match expected."""
        filepath = REPO_ROOT / rel_path
        func_node, _source = _find_main_function(filepath)
        assert func_node is not None, f"main() not found in {rel_path}"

        expected_args = expected["args"]
        actual_args = func_node.args.args
        assert len(actual_args) == len(expected_args), (
            f"main() in {rel_path}: expected {len(expected_args)} args, got {len(actual_args)}"
        )

        for idx, (exp_name, exp_ann, _exp_def) in enumerate(expected_args):
            actual_arg = actual_args[idx]
            assert actual_arg.arg == exp_name, (
                f"main() in {rel_path} arg {idx}: "
                f"expected name {exp_name!r}, got {actual_arg.arg!r}"
            )
            actual_ann = _parse_annotation(actual_arg.annotation)
            assert actual_ann == exp_ann, (
                f"main() in {rel_path} arg {exp_name!r}: "
                f"expected annotation {exp_ann!r}, got {actual_ann!r}"
            )

    @_params()
    def test_main_function_return_annotation_matches_expected(self, rel_path: str, expected: dict):
        """AC-FR0100-03: main() function return annotation matches expected."""
        filepath = REPO_ROOT / rel_path
        func_node, _source = _find_main_function(filepath)
        assert func_node is not None, f"main() not found in {rel_path}"

        exp_returns = expected["returns"]
        actual_returns = _parse_annotation(func_node.returns)

        if exp_returns is None:
            assert actual_returns is None, (
                f"main() in {rel_path}: expected no return annotation, got {actual_returns!r}"
            )
        else:
            assert actual_returns == exp_returns, (
                f"main() in {rel_path}: expected return annotation "
                f"{exp_returns!r}, got {actual_returns!r}"
            )


# ---------------------------------------------------------------------------
# AC-FR0100-05 + AC-NFR0100-04: README.md validation
# ---------------------------------------------------------------------------


class TestReadmeUpdates:
    @pytest.fixture
    def readme_text(self) -> str:
        """Read README.md content."""
        return README_MD.read_text(encoding="utf-8")

    def test_warning_line_removed(self, readme_text: str):
        """AC-NFR0100-02: README warning line about missing console_scripts removed."""
        lines = [
            ln
            for ln in readme_text.splitlines()
            if "没有" in ln and "console_scripts" in ln and "⚠️" in ln
        ]
        assert len(lines) == 0, f"README still contains console_scripts warning: {lines}"

    def test_no_python_m_usage_as_primary(self, readme_text: str):
        """AC-NFR0100-03: at most 1 'python -m trader_off' reference in README."""
        pym_lines = [ln for ln in readme_text.splitlines() if "python -m trader_off" in ln]
        assert len(pym_lines) <= 1, (
            f"Expected ≤1 'python -m' refs, got {len(pym_lines)}: {pym_lines}"
        )

    def test_python_m_fallback_mention_preserved(self, readme_text: str):
        """AC-FR0100-05: README retains 'python -m trader_off' fallback mention."""
        assert "python -m trader_off" in readme_text, (
            "README must retain at least 1 'python -m trader_off' fallback"
        )

    def test_entry_point_names_in_readme(self, readme_text: str):
        """AC-NFR0100-04: README references all 7 entry point names."""
        for name in [
            "trader-off-backtest",
            "trader-off-optimize",
            "trader-off-mine-factors",
            "trader-off-scheduler",
            "trader-off-sync-data",
            "trader-off-init",
            "trader-off-stock-list",
        ]:
            assert name in readme_text, f"README should mention '{name}'"
