"""Unit tests for factor mining CLI (FR-0800).

Tests the `trader-off mine-factors` command: argument parsing, exit codes, and
pipeline orchestration. The actual factor mining pipeline steps are mocked to
avoid real computation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Module under test (will fail initially — Red phase)
from trader_off.factor_mining import cli as factor_mining_cli


class TestMineFactorsCLIArgs:
    """Argument parsing tests (AC-FR0800-02, AC-FR0800-05)."""

    # ------------------------------------------------------------------
    # AC-FR0800-05: Missing --config
    # ------------------------------------------------------------------
    def test_ac_fr0800_05_missing_config_exits_nonzero(self, capsys):
        """AC-FR0800-05: Missing --config → exit non-zero, stderr
        contains 'config is required'."""
        with pytest.raises(SystemExit) as exc_info:
            factor_mining_cli.main(argv=[])
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "config" in captured.err.lower()

    # ------------------------------------------------------------------
    # AC-FR0800-02: --top-k default
    # ------------------------------------------------------------------
    def test_ac_fr0800_02_top_k_default(self):
        """AC-FR0800-02: --top-k defaults to 30 when not specified."""
        parser = factor_mining_cli._create_parser()
        # Provide --config so args parse successfully
        args = parser.parse_args(["--config", "dummy.yaml"])
        assert args.top_k == 30


class TestMineFactorsCLIErrors:
    """Error path tests (AC-FR0800-03)."""

    # ------------------------------------------------------------------
    # AC-FR0800-03: Config file not found
    # ------------------------------------------------------------------
    def test_ac_fr0800_03_config_not_found_exit_4(self, capsys, tmp_path):
        """AC-FR0800-03: Non-existent config file → exit code 4,
        stderr contains 'config file not found'."""
        nonexistent = tmp_path / "nonexistent.yaml"
        # File must not exist

        result = factor_mining_cli.main(
            argv=[
                "--config",
                str(nonexistent),
            ]
        )

        assert result == 4
        captured = capsys.readouterr()
        assert (
            "config file not found" in captured.err.lower()
            or "config file not found" in captured.out.lower()
        ), f"Expected error message, got out={captured.out!r} err={captured.err!r}"


class TestMineFactorsCLISuccess:
    """Happy path tests with mocked pipeline (AC-FR0800-01)."""

    def _make_mock_candidate(self, i: int):
        """Create a mock FactorSpec for test."""
        spec = MagicMock()
        spec.id = f"momentum_N_{i}"
        spec.template_name = "momentum_N"
        spec.category = "momentum"
        spec.formula = f"close[t]/close[t-{i}]-1"
        spec.compute_fn = MagicMock()
        spec.params = {"N": i}
        return spec

    def _make_mock_evaluation(self, i: int):
        """Create a mock FactorEvaluation for test."""
        ev = MagicMock()
        ev.ic_mean = 0.05 - i * 0.001
        ev.ic_std = 0.1
        ev.icir = (0.05 - i * 0.001) / 0.1
        ev.rank_ic_mean = 0.04
        ev.rank_ic_std = 0.08
        return ev

    # ------------------------------------------------------------------
    # AC-FR0800-01: Full success path
    # ------------------------------------------------------------------
    @patch("trader_off.factor_mining.cli.Path.mkdir")
    @patch("trader_off.factor_mining.cli.logger")
    @patch("trader_off.factor_mining.cli.yaml")
    def test_ac_fr0800_01_success_path(
        self,
        mock_yaml,
        mock_logger,
        mock_mkdir,
        capsys,
        tmp_path,
    ):
        """AC-FR0800-01: Full mine-factors pipeline → exit 0, stdout
        contains '枚举了 N 个候选因子' and '精选 K 个因子'."""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")

        # Mock config load
        mock_yaml.safe_load.return_value = {
            "start": "2020-01-01",
            "end": "2024-12-31",
        }

        # Create mock candidates and evaluations
        num_candidates = 200
        mock_candidates = [self._make_mock_candidate(i) for i in range(num_candidates)]
        mock_evaluations = [self._make_mock_evaluation(i) for i in range(num_candidates)]
        mock_selected = mock_candidates[:30]

        # Patch pipeline functions on the module where they are used
        with (
            patch.object(factor_mining_cli, "list_templates", return_value=[]),
            patch.object(factor_mining_cli, "enumerate_factors", return_value=mock_candidates),
            patch.object(factor_mining_cli, "evaluate_factor", side_effect=mock_evaluations),
            patch.object(
                factor_mining_cli,
                "select_factors",
                return_value=(mock_selected, MagicMock()),
            ),
            patch.object(
                factor_mining_cli,
                "save_factor_registry",
                return_value=(Path("/tmp/factors.yaml"), Path("/tmp/selected.json")),
            ),
        ):
            result = factor_mining_cli.main(
                argv=[
                    "--config",
                    str(config_path),
                    "--top-k",
                    "30",
                    "--output",
                    str(tmp_path / "out"),
                    "--registry-dir",
                    str(tmp_path / "registry"),
                ]
            )

        assert result == 0, f"Expected exit 0, got {result}"
        captured = capsys.readouterr()
        assert "枚举了" in captured.out, f"stdout: {captured.out}"
        assert "精选" in captured.out, f"stdout: {captured.out}"
        import re

        match = re.search(r"枚举了 (\d+) 个候选因子", captured.out)
        assert match is not None, f"Expected count pattern, got: {captured.out}"
        assert int(match.group(1)) >= 200

    # ------------------------------------------------------------------
    # AC-FR0800-04: Too few candidates (< 10 selected)
    # ------------------------------------------------------------------
    @patch("trader_off.factor_mining.cli.Path.mkdir")
    @patch("trader_off.factor_mining.cli.logger")
    @patch("trader_off.factor_mining.cli.yaml")
    def test_ac_fr0800_04_few_selected_exit_3(
        self,
        mock_yaml,
        mock_logger,
        mock_mkdir,
        capsys,
        tmp_path,
    ):
        """AC-FR0800-04: top-k=30 but only 5 candidates →
        exit code 3, stdout contains selected count < 10,
        WARNING 'fewer than 10 selected factors'."""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")

        mock_yaml.safe_load.return_value = {
            "start": "2020-01-01",
            "end": "2024-12-31",
        }

        num_candidates = 5
        mock_candidates = [self._make_mock_candidate(i) for i in range(num_candidates)]
        mock_evaluations = [self._make_mock_evaluation(i) for i in range(num_candidates)]
        mock_selected = mock_candidates[:5]

        with (
            patch.object(factor_mining_cli, "list_templates", return_value=[]),
            patch.object(factor_mining_cli, "enumerate_factors", return_value=mock_candidates),
            patch.object(factor_mining_cli, "evaluate_factor", side_effect=mock_evaluations),
            patch.object(
                factor_mining_cli,
                "select_factors",
                return_value=(mock_selected, MagicMock()),
            ),
            patch.object(
                factor_mining_cli,
                "save_factor_registry",
                return_value=(Path("/tmp/factors.yaml"), Path("/tmp/selected.json")),
            ),
        ):
            result = factor_mining_cli.main(
                argv=[
                    "--config",
                    str(config_path),
                    "--top-k",
                    "30",
                    "--output",
                    str(tmp_path / "out"),
                    "--registry-dir",
                    str(tmp_path / "registry"),
                ]
            )

        assert result == 3, f"Expected exit 3, got {result}"
        captured = capsys.readouterr()
        assert "精选" in captured.out, f"stdout: {captured.out}"
        # Verify selected count is 5 (< 10)
        import re

        match = re.search(r"精选 (\d+) 个因子", captured.out)
        assert match is not None
        selected_count = int(match.group(1))
        assert selected_count == 5
        assert selected_count < 10

    def test_load_config_reads_yaml(self, tmp_path):
        """_load_config reads and parses YAML config file."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\ntop_k: 30\n")

        result = factor_mining_cli._load_config(config_path)

        assert result["start"] == "2020-01-01"
        assert result["end"] == "2024-12-31"
        assert result["top_k"] == 30

    def test_evaluation_exception_skips_factor(self, tmp_path):
        """Exception during factor evaluation is caught and logged."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")

        # Mock evaluate_factor to raise for all candidates
        mock_spec = MagicMock()
        mock_spec.id = "bad_factor"

        with (
            patch.object(factor_mining_cli, "list_templates", return_value=[]),
            patch.object(factor_mining_cli, "enumerate_factors", return_value=[mock_spec]),
            patch.object(
                factor_mining_cli, "evaluate_factor", side_effect=RuntimeError("eval failed")
            ),
            patch.object(factor_mining_cli, "select_factors", return_value=([], MagicMock())),
            patch.object(
                factor_mining_cli, "save_factor_registry", return_value=tmp_path / "factors.yaml"
            ),
        ):
            # Should not raise, but returns 3 (no factors evaluated)
            result = factor_mining_cli._run_pipeline(
                MagicMock(
                    config=config_path, top_k=30, corr_threshold=0.9, output=None, registry_dir=None
                )
            )

            assert result == 3

    def test_validate_config_not_found(self, tmp_path):
        """_validate_config returns 4 when config file does not exist."""
        nonexistent = tmp_path / "nonexistent.yaml"
        result = factor_mining_cli._validate_config(nonexistent)
        assert result == 4

    def test_validate_config_success(self, tmp_path):
        """_validate_config returns None when config file exists."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\n")
        result = factor_mining_cli._validate_config(config_path)
        assert result is None

    def test_run_with_custom_output_dir(self, tmp_path):
        """CLI with custom --output directory."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")
        output_dir = tmp_path / "custom_output"

        with (
            patch.object(factor_mining_cli, "list_templates", return_value=[]),
            patch.object(factor_mining_cli, "enumerate_factors", return_value=[]),
            patch.object(factor_mining_cli, "select_factors", return_value=([], MagicMock())),
        ):
            result = factor_mining_cli.main(
                argv=[
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_dir),
                ]
            )

        assert result == 3  # No factors evaluated

    def test_run_pipeline_creates_directories(self, tmp_path):
        """_run_pipeline creates output and registry directories."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")
        output_dir = tmp_path / "cli_output"
        registry_dir = tmp_path / "cli_registry"

        with (
            patch.object(factor_mining_cli, "list_templates", return_value=[]),
            patch.object(factor_mining_cli, "enumerate_factors", return_value=[]),
            patch.object(factor_mining_cli, "select_factors", return_value=([], MagicMock())),
        ):
            factor_mining_cli._run_pipeline(
                MagicMock(
                    config=config_path,
                    top_k=30,
                    corr_threshold=0.9,
                    output=output_dir,
                    registry_dir=registry_dir,
                )
            )

        assert output_dir.exists()
        assert registry_dir.exists()
