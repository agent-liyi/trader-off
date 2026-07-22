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
                return_value=Path("/tmp/registry.parquet"),
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
        # AC-FR0800-02: candidate count must be reported
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
        WARNING 'fewer than 10 selected factors'.

        Validates:
        - AC-FR0800-04: exit code 3 when selected < 10
        """
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
                return_value=Path("/tmp/registry.parquet"),
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
        # AC-FR0800-04: selected count must be reported
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
        from datetime import date

        import polars as pl

        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")

        # Mock evaluate_factor to raise for all candidates
        mock_spec = MagicMock()
        mock_spec.id = "bad_factor"

        mock_data = pl.DataFrame(
            {
                "asset": ["A"],
                "date": [date(2022, 1, 3)],
                "close": [10.0],
            }
        )

        with (
            patch.object(factor_mining_cli, "_load_ohlcv_data", return_value=mock_data),
            patch.object(factor_mining_cli, "list_templates", return_value=[]),
            patch.object(factor_mining_cli, "enumerate_factors", return_value=[mock_spec]),
            patch.object(
                factor_mining_cli, "evaluate_factor", side_effect=RuntimeError("eval failed")
            ),
            patch.object(factor_mining_cli, "select_factors", return_value=([], MagicMock())),
            patch.object(
                factor_mining_cli,
                "save_factor_registry",
                return_value=tmp_path / "registry.parquet",
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
        from datetime import date

        import polars as pl

        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")
        output_dir = tmp_path / "custom_output"

        mock_data = pl.DataFrame({"asset": ["A"], "date": [date(2022, 1, 3)], "close": [10.0]})

        with (
            patch.object(factor_mining_cli, "_load_ohlcv_data", return_value=mock_data),
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
        from datetime import date

        import polars as pl

        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2020-01-01'\nend: '2024-12-31'\n")
        output_dir = tmp_path / "cli_output"
        registry_dir = tmp_path / "cli_registry"

        mock_data = pl.DataFrame({"asset": ["A"], "date": [date(2022, 1, 3)], "close": [10.0]})

        with (
            patch.object(factor_mining_cli, "_load_ohlcv_data", return_value=mock_data),
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


# ============================================================================
# Bug 1-3 fix: Data loading + proper evaluate_factor call
# ============================================================================


class TestLoadOHLCVData:
    """Bug 3: _load_ohlcv_data loads from default fixture or custom path."""

    def test_load_from_default_fixture_returns_dataframe(self):
        """_load_ohlcv_data with no args returns polars DataFrame from default fixture."""
        import polars as pl

        from trader_off.factor_mining.cli import _load_ohlcv_data

        df = _load_ohlcv_data()
        assert isinstance(df, pl.DataFrame)
        assert len(df) > 0

    def test_load_from_custom_fixture(self, tmp_path):
        """_load_ohlcv_data with custom fixture_path loads that file."""
        import polars as pl

        from trader_off.factor_mining.cli import _load_ohlcv_data

        # Create a small fixture with required columns
        fixture = tmp_path / "custom.parquet"
        pl.DataFrame(
            {
                "asset": ["000001.SZ"] * 5,
                "date": pl.date_range(
                    start=pl.date(2022, 1, 3), end=pl.date(2022, 1, 7), interval="1d", eager=True
                ),
                "close": [10.0, 10.5, 11.0, 10.8, 11.2],
                "open": [10.0] * 5,
                "high": [11.0] * 5,
                "low": [9.5] * 5,
                "volume": [1000.0] * 5,
                "turnover": [0.05] * 5,
            }
        ).write_parquet(fixture)

        df = _load_ohlcv_data(fixture_path=fixture)
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 5
        assert list(df["asset"].unique()) == ["000001.SZ"]


class TestComputeLabels:
    """Bug 3: _compute_labels computes N-day forward returns."""

    def test_forward_5day_returns(self):
        """_compute_labels produces label column with 5-day forward returns."""
        import polars as pl

        from trader_off.factor_mining.cli import _compute_labels

        df = pl.DataFrame(
            {
                "asset": ["000001.SZ"] * 5,
                "date": pl.date_range(
                    start=pl.date(2022, 1, 3), end=pl.date(2022, 1, 7), interval="1d", eager=True
                ),
                "close": [10.0, 10.5, 11.0, 10.8, 11.2],
            }
        )
        result = _compute_labels(df, forward_days=2)
        assert "label" in result.columns
        # Forward return from day 3 to day 5: 10.0→11.0 = +10%
        label_vals = result["label"].to_list()
        assert abs(label_vals[0] - 0.10) < 0.01  # 10% return

    def test_labels_with_default_days(self):
        """_compute_labels defaults to 5-day forward returns."""
        import polars as pl

        from trader_off.factor_mining.cli import _compute_labels

        df = pl.DataFrame(
            {
                "asset": ["A"] * 10,
                "date": pl.date_range(
                    start=pl.date(2022, 1, 1), end=pl.date(2022, 1, 10), interval="1d", eager=True
                ),
                "close": [float(i + 10) for i in range(10)],
            }
        )
        result = _compute_labels(df)
        assert "label" in result.columns
        # Last 5 rows should have null labels (no future data)
        labels = result["label"].to_list()
        for i in range(-5, 0):
            assert labels[i] is None, f"Row {i} should be null"


class TestPipelineDataLoading:
    """Bug 1-3: _run_pipeline properly loads data, evaluates factors,
    handles eval failures with try/except and exit code 5."""

    def test_read_config_resolves_dates(self, tmp_path):
        """Config start/end dates are read from YAML."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2022-01-03'\nend: '2022-01-10'\n")

        from trader_off.factor_mining.cli import _load_config

        config = _load_config(config_path)
        assert config["start"] == "2022-01-03"
        assert config["end"] == "2022-01-10"

    def test_factor_values_dataframe_shape(self):
        """_build_factor_values creates DataFrame with asset, date, value columns."""
        import polars as pl

        from trader_off.factor_mining.cli import _build_factor_values

        df = pl.DataFrame(
            {
                "asset": ["A", "B"] * 2,
                "date": [pl.date(2022, 1, 3)] * 4,
                "close": [10.0, 20.0, 11.0, 21.0],
            }
        )
        result = _build_factor_values(df, pl.Series("_factor", [1.0, 2.0, 3.0, 4.0]))
        assert set(result.columns) == {"asset", "date", "value"}
        assert len(result) == 4

    def test_pipeline_evaluate_factor_called(self, tmp_path, capsys):
        """_run_pipeline calls evaluate_factor with correct args when data is available."""
        from datetime import date
        from unittest.mock import patch

        import polars as pl

        from trader_off.factor_mining.cli import _run_pipeline
        from trader_off.factor_mining.evaluation import FactorEvaluation

        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2022-01-03'\nend: '2022-01-10'\n")

        # Build a small DataFrame with OHLCV data — use Python date objects
        # so polars infers Date dtype.
        assets = ["000001.SZ", "000002.SZ"]
        start_date = date(2022, 1, 1)
        all_dates = [start_date.replace(day=start_date.day + i) for i in range(10)]
        rows = []
        for asset in assets:
            for d in all_dates:
                rows.append(
                    {
                        "asset": asset,
                        "date": d,
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.5,
                        "close": 10.0 + (asset == "000002.SZ") * 5.0,
                        "volume": 1000.0,
                        "turnover": 0.05,
                    }
                )
        df = pl.DataFrame(rows)

        mock_ev = FactorEvaluation(
            ic_ts=pl.DataFrame({"date": [date(2022, 1, 5)], "ic": [0.1]}),
            rank_ic_ts=pl.DataFrame({"date": [date(2022, 1, 5)], "rank_ic": [0.09]}),
            ic_mean=0.1,
            ic_std=0.1,
            icir=1.0,
            rank_ic_mean=0.09,
            rank_ic_std=0.08,
            layered_returns=pl.DataFrame({"layer": [1, 2, 3, 4, 5], "mean_return": [0.01] * 5}),
        )

        with (
            patch("trader_off.factor_mining.cli._load_ohlcv_data", return_value=df),
            patch(
                "trader_off.factor_mining.cli.evaluate_factor",
                return_value=mock_ev,
            ) as mock_eval,
        ):
            result = _run_pipeline(
                type(
                    "Args",
                    (),
                    {
                        "config": config_path,
                        "top_k": 10,
                        "corr_threshold": 0.9,
                        "output": tmp_path / "out",
                        "registry_dir": tmp_path / "registry",
                        "start": None,
                        "end": None,
                        "fixture": None,
                    },
                )()
            )

        # Should complete without error
        assert result in (0, 3)
        # evaluate_factor should have been called
        assert mock_eval.call_count > 0
        # Each call should have factor_values (DataFrame), labels (DataFrame), dates (list)
        for call_kwargs in [c.kwargs for c in mock_eval.call_args_list]:
            assert isinstance(call_kwargs["factor_values"], pl.DataFrame)
            assert isinstance(call_kwargs["labels"], pl.DataFrame)
            assert isinstance(call_kwargs["dates"], list)

    def test_pipeline_handles_eval_error_continues(self, tmp_path, capsys):
        """When evaluate_factor raises, the pipeline logs warning and continues (exit 5)."""
        from datetime import date
        from unittest.mock import patch

        import polars as pl

        from trader_off.factor_mining.cli import _run_pipeline

        config_path = tmp_path / "config.yaml"
        config_path.write_text("start: '2022-01-03'\nend: '2022-01-10'\n")

        # Build a small DataFrame — use Python date objects for proper dtype
        df = pl.DataFrame(
            {
                "asset": ["A", "B"],
                "date": [date(2022, 1, 3)] * 2,
                "open": [10.0] * 2,
                "high": [11.0] * 2,
                "low": [9.5] * 2,
                "close": [10.5] * 2,
                "volume": [1000.0] * 2,
                "turnover": [0.05] * 2,
            }
        )

        with (
            patch("trader_off.factor_mining.cli._load_ohlcv_data", return_value=df),
            patch(
                "trader_off.factor_mining.cli.evaluate_factor",
                side_effect=RuntimeError("eval boom"),
            ),
        ):
            result = _run_pipeline(
                type(
                    "Args",
                    (),
                    {
                        "config": config_path,
                        "top_k": 10,
                        "corr_threshold": 0.9,
                        "output": tmp_path / "out",
                        "registry_dir": tmp_path / "registry",
                        "start": None,
                        "end": None,
                        "fixture": None,
                    },
                )()
            )

        # Should return 3 (no factors evaluated)
        assert result == 3
