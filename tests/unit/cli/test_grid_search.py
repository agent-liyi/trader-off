"""Tests for grid_search CLI — FR-0100.

Covers: argparse exit 2, config validation exit 4, happy path JSON output
with best-by-Sharpe, --json flag, function-scope lazy import,
GridSearch engine failure exit 5.

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Will fail until grid_search.py is created (Red phase)
from trader_off.cli.grid_search import main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_config_yaml(tmp_path) -> Path:
    """Create a valid grid search config YAML file with param_space."""
    config_path = tmp_path / "grid_config.yaml"
    config_path.write_text(
        """
param_space:
  top_k: [10, 20, 30]
  rebalance_days: [5, 10]
  ic_threshold: [0.05, 0.1]
"""
    )
    return config_path


@pytest.fixture
def mock_grid_search_df() -> pd.DataFrame:
    """Return a mock DataFrame representing GridSearch.run() output.

    Sorted by sharpe descending; best row is sharpe=1.5.
    """
    return pd.DataFrame(
        {
            "sharpe": [1.5, 1.2, 0.9, 0.8, 0.5, 0.3],
            "total_return": [0.35, 0.30, 0.20, 0.15, 0.10, 0.05],
            "top_k": [30, 20, 20, 30, 10, 10],
            "rebalance_days": [10, 10, 5, 5, 5, 10],
            "ic_threshold": [0.10, 0.10, 0.10, 0.10, 0.05, 0.05],
            "portfolio_id": ["pf_1", "pf_2", "pf_3", "pf_4", "pf_5", "pf_6"],
        }
    )


@pytest.fixture
def mock_grid_search(mock_grid_search_df):
    """Mock quantide.service.grid_search.GridSearch to return known results."""
    mock_instance = MagicMock()
    mock_instance.run.return_value = mock_grid_search_df

    with patch("quantide.service.grid_search.GridSearch", return_value=mock_instance) as mock_cls:
        yield mock_cls, mock_instance


@pytest.fixture
def common_args(valid_config_yaml) -> list[str]:
    """Return common CLI arguments for happy path tests."""
    return [
        "--config",
        str(valid_config_yaml),
        "--strategy",
        "optimized_topk",
        "--start",
        "2024-01-01",
        "--end",
        "2024-12-31",
    ]


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

    def test_missing_config_exits_2(self):
        """Missing required --config → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--strategy", "lgbm_top20", "--start", "2024-01-01", "--end", "2024-12-31"])
        assert exc_info.value.code == 2

    def test_missing_strategy_exits_2(self, valid_config_yaml):
        """Missing required --strategy → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                ]
            )
        assert exc_info.value.code == 2

    def test_missing_start_exits_2(self, valid_config_yaml):
        """Missing required --start → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "lgbm_top20",
                    "--end",
                    "2024-12-31",
                ]
            )
        assert exc_info.value.code == 2

    def test_missing_end_exits_2(self, valid_config_yaml):
        """Missing required --end → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "lgbm_top20",
                    "--start",
                    "2024-01-01",
                ]
            )
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Exit code 4: Config validation errors
# ---------------------------------------------------------------------------


class TestConfigValidationExit4:
    """FR-0100: config file errors → exit code 4."""

    def test_missing_config_file_exits_4(self):
        """Non-existent config file path → exit code 4."""
        exit_code = main(
            [
                "--config",
                "/nonexistent/config.yaml",
                "--strategy",
                "lgbm_top20",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4

    def test_invalid_yaml_exits_4(self, tmp_path):
        """Invalid YAML syntax → exit code 4."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("::: invalid yaml :::")
        exit_code = main(
            [
                "--config",
                str(bad_yaml),
                "--strategy",
                "lgbm_top20",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4

    def test_missing_param_space_exits_4(self, tmp_path):
        """Config YAML without param_space → exit code 4."""
        no_param = tmp_path / "no_param.yaml"
        no_param.write_text("other_key: value\n")
        exit_code = main(
            [
                "--config",
                str(no_param),
                "--strategy",
                "lgbm_top20",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4

    def test_empty_param_space_exits_4(self, tmp_path):
        """Config YAML with empty param_space → exit code 4."""
        empty_param = tmp_path / "empty_param.yaml"
        empty_param.write_text("param_space: {}\n")
        exit_code = main(
            [
                "--config",
                str(empty_param),
                "--strategy",
                "lgbm_top20",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4


# ---------------------------------------------------------------------------
# Exit code 5: GridSearch engine failure
# ---------------------------------------------------------------------------


class TestGridSearchFailureExit5:
    """FR-0100: GridSearch.run() raises → exit code 5."""

    def test_run_exception_exits_5(self, valid_config_yaml):
        """GridSearch.run() raises RuntimeError → exit code 5."""
        mock_instance = MagicMock()
        mock_instance.run.side_effect = RuntimeError("engine failure")

        with patch("quantide.service.grid_search.GridSearch", return_value=mock_instance):
            exit_code = main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "optimized_topk",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                ]
            )
        assert exit_code == 5


# ---------------------------------------------------------------------------
# Happy path: JSON output + exit 0
# ---------------------------------------------------------------------------


class TestHappyPath:
    """FR-0100: successful grid search → JSON output, exit 0."""

    def test_json_output_structure(self, mock_grid_search, common_args, capsys):
        """JSON output has status=ok, data with best/completed/errors."""
        exit_code = main(common_args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert "data" in output
        assert "best" in output["data"]
        assert "completed" in output["data"]
        assert "errors" in output["data"]

    def test_best_is_highest_sharpe(self, mock_grid_search, common_args, capsys):
        """Best result is the row with highest Sharpe ratio."""
        exit_code = main(common_args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        best = output["data"]["best"]
        assert best["sharpe"] == 1.5
        assert best["total_return"] == 0.35

    def test_best_params_contain_grid_keys(self, mock_grid_search, common_args, capsys):
        """Best params dict includes grid parameters (top_k, etc.)."""
        exit_code = main(common_args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        params = output["data"]["best"]["params"]
        assert "top_k" in params
        assert "rebalance_days" in params
        assert "ic_threshold" in params

    def test_completed_count_matches_combinations(self, mock_grid_search, common_args, capsys):
        """completed equals number of param combinations (2 × 2 × 2 = 8? no, 3 × 2 × 2 = 12)."""
        exit_code = main(common_args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        # 3 top_k × 2 rebalance_days × 2 ic_threshold = 12 combos
        # But the mock df has only 6 rows; completed should come from df len
        assert output["data"]["completed"] == 6

    def test_errors_is_zero_on_success(self, mock_grid_search, common_args, capsys):
        """errors field is 0 when all backtests succeed."""
        exit_code = main(common_args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["errors"] == 0

    def test_json_flag_produces_json(self, mock_grid_search, valid_config_yaml, capsys):
        """--json flag still produces valid JSON output."""
        exit_code = main(
            [
                "--config",
                str(valid_config_yaml),
                "--strategy",
                "optimized_topk",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
                "--json",
            ]
        )
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"

    def test_strategy_lgbm_top20(self, valid_config_yaml, mock_grid_search_df, capsys):
        """--strategy lgbm_top20 resolves correctly."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_grid_search_df

        with patch(
            "quantide.service.grid_search.GridSearch", return_value=mock_instance
        ) as mock_cls:
            exit_code = main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "lgbm_top20",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                ]
            )

        assert exit_code == 0
        # Verify GridSearch was called with correct strategy_cls
        call_kwargs = mock_cls.call_args.kwargs
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        assert call_kwargs["strategy_cls"] == LGBMTop20Strategy

    def test_strategy_optimized_topk(self, valid_config_yaml, mock_grid_search_df, capsys):
        """--strategy optimized_topk resolves correctly."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_grid_search_df

        with patch(
            "quantide.service.grid_search.GridSearch", return_value=mock_instance
        ) as mock_cls:
            exit_code = main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "optimized_topk",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                ]
            )

        assert exit_code == 0
        call_kwargs = mock_cls.call_args.kwargs
        from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

        assert call_kwargs["strategy_cls"] == OptimizedTopKStrategy

    def test_capital_default(self, mock_grid_search, common_args):
        """Default --capital is 1_000_000."""
        mock_cls, _ = mock_grid_search
        main(common_args)
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["initial_cash"] == 1_000_000

    def test_max_workers_default(self, mock_grid_search, common_args):
        """Default --max-workers is 4."""
        mock_cls, _ = mock_grid_search
        main(common_args)
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["max_workers"] == 4

    def test_custom_capital(self, valid_config_yaml, mock_grid_search_df):
        """--capital flag overrides default."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_grid_search_df

        with patch(
            "quantide.service.grid_search.GridSearch", return_value=mock_instance
        ) as mock_cls:
            exit_code = main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "optimized_topk",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--capital",
                    "500000",
                ]
            )

        assert exit_code == 0
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["initial_cash"] == 500000.0

    def test_custom_max_workers(self, valid_config_yaml, mock_grid_search_df):
        """--max-workers flag overrides default."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_grid_search_df

        with patch(
            "quantide.service.grid_search.GridSearch", return_value=mock_instance
        ) as mock_cls:
            exit_code = main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "optimized_topk",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                    "--max-workers",
                    "8",
                ]
            )

        assert exit_code == 0
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["max_workers"] == 8

    def test_unknown_strategy_exits_4(self, valid_config_yaml):
        """Unknown --strategy value → exit code 4."""
        exit_code = main(
            [
                "--config",
                str(valid_config_yaml),
                "--strategy",
                "nonexistent_strategy",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
            ]
        )
        assert exit_code == 4


# ---------------------------------------------------------------------------
# Function-scope lazy import (NFR-0100)
# ---------------------------------------------------------------------------


class TestLazyImport:
    """FR-0100 / NFR-0100: quantide imports are function-scope only."""

    def test_no_quantide_import_at_module_level(self):
        """Module-level does NOT import quantide eagerly."""
        import ast

        source = Path("src/trader_off/cli/grid_search.py").read_text()
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
    """FR-0100: edge cases for grid-search CLI."""

    def test_main_returns_int(self, valid_config_yaml, mock_grid_search_df):
        """main() return type is int."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_grid_search_df

        with patch("quantide.service.grid_search.GridSearch", return_value=mock_instance):
            result = main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "optimized_topk",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                ]
            )
        assert isinstance(result, int)

    def test_empty_df_returns_completed_zero(self, valid_config_yaml, capsys):
        """GridSearch.run() returns empty DataFrame → completed=0, best=None."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = pd.DataFrame()

        with patch("quantide.service.grid_search.GridSearch", return_value=mock_instance):
            exit_code = main(
                [
                    "--config",
                    str(valid_config_yaml),
                    "--strategy",
                    "optimized_topk",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-12-31",
                ]
            )

        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["data"]["completed"] == 0
        assert output["data"]["best"] is None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


class TestEntryPoint:
    """FR-0100: module-level entry point works."""

    def test_main_is_callable(self):
        """Smoke: import succeeds and main is callable."""
        assert callable(main)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
