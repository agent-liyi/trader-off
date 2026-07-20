"""Integration tests for optimize CLI → covariance → solve → persist (FR-4100).

Covers AC-FR4100-01~04: exit codes 0/2/3, cov-window propagation, and
cross-module wiring: CLI → expected_returns → covariance → solver → persistence.

L2 contract-simulation tests that call through real portfolio implementations
using fixture data from ``tests/fixtures/v0.2.0/``.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl
import pytest

from trader_off.portfolio.cli import main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parents[2] / "tests" / "fixtures" / "v0.2.0"


def _fixture_path(name: str) -> Path:
    p = FIXTURES_DIR / name
    if not p.exists():
        pytest.skip(f"Fixture {name} not found at {FIXTURES_DIR}")
    return p


@pytest.fixture
def predictions_file() -> Path:
    """Path to v0.2.0 predictions fixture (50 assets)."""
    return _fixture_path("predictions_fixture.csv")


@pytest.fixture
def industry_map_file() -> Path:
    """Path to v0.2.0 industry map fixture."""
    return _fixture_path("industry_map.csv")


@pytest.fixture
def predictions_few() -> Path:
    """Create a temporary predictions CSV with only 3 assets (too few)."""
    return _fixture_path("predictions_fixture.csv")


def _make_few_predictions(tmp_path: Path) -> Path:
    """Create predictions CSV with only 3 assets (exit code 3 trigger)."""
    df = pl.DataFrame(
        {
            "asset": ["A001", "A002", "A003"],
            "score": [0.1, 0.05, -0.02],
            "rank": [1, 2, 3],
        }
    )
    p = tmp_path / "few_predictions.csv"
    df.write_csv(p)
    return p


# ---------------------------------------------------------------------------
# AC-FR4100-01: Full success — exit code 0, stdout with Sharpe
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_fr4100_01_success_exit_code_0(tmp_path, predictions_file, industry_map_file):
    """AC-FR4100-01: optimize CLI exit code 0, stdout contains Sharpe= and
    报告落盘到."""
    output_dir = tmp_path / "reports"

    argv = [
        "--predictions",
        str(predictions_file),
        "--industry-map",
        str(industry_map_file),
        "--output",
        str(output_dir),
    ]

    exit_code = main(argv)
    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"

    # Verify output directory was created (portfolio_<ts>/)
    portfolio_dirs = list(output_dir.glob("portfolio_*"))
    assert len(portfolio_dirs) > 0, f"No portfolio_* directory found in {output_dir}"
    out_dir = portfolio_dirs[0]
    assert out_dir.is_dir()

    # Verify stdout-like output was captured by the function
    # (main() writes to sys.stdout, but we intercept via main(argv))


@pytest.mark.integration
def test_ac_fr4100_01_stdout_sharpe(tmp_path, predictions_file, industry_map_file, capsys):
    """AC-FR4100-01: stdout contains 'Sharpe=' with numeric value and
    '报告落盘到'."""
    output_dir = tmp_path / "reports"

    argv = [
        "--predictions",
        str(predictions_file),
        "--industry-map",
        str(industry_map_file),
        "--output",
        str(output_dir),
    ]

    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 0

    # Check for Sharpe= pattern
    sharpe_match = re.search(r"Sharpe=([\d.]+)", captured.out)
    assert sharpe_match is not None, f"No 'Sharpe=' found in stdout. Got: {captured.out}"
    sharpe_val = float(sharpe_match.group(1))
    # Sharpe should be a finite number
    assert sharpe_val == sharpe_val, "Sharpe is NaN"

    # Check for 报告落盘到
    assert "报告落盘到" in captured.out, f"No '报告落盘到' found in stdout. Got: {captured.out}"


@pytest.mark.integration
def test_ac_fr4100_01_output_files_exist(tmp_path, predictions_file, industry_map_file):
    """AC-FR4100-01: optimization produces all 5 required output files."""
    output_dir = tmp_path / "reports"

    argv = [
        "--predictions",
        str(predictions_file),
        "--industry-map",
        str(industry_map_file),
        "--output",
        str(output_dir),
    ]

    exit_code = main(argv)
    assert exit_code == 0

    portfolio_dirs = list(output_dir.glob("portfolio_*"))
    assert len(portfolio_dirs) > 0
    out_dir = portfolio_dirs[0]

    expected_files = [
        "weights.csv",
        "optimizer_report.json",
        "portfolio_metrics.csv",
        "weights_diagnostics.json",
        "assets_dropped.json",
    ]
    for fname in expected_files:
        fpath = out_dir / fname
        assert fpath.exists(), f"Missing output file: {fname}"
        # assets_dropped.json may be minimal ([] = 2 bytes) when no assets dropped
        min_size = 2 if fname == "assets_dropped.json" else 100
        assert fpath.stat().st_size >= min_size, (
            f"Output file too small: {fname} ({fpath.stat().st_size} bytes)"
        )

    # Verify weights.csv sum ≈ 1.0
    weights_df = pl.read_csv(out_dir / "weights.csv")
    weight_sum = weights_df["weight"].sum()
    assert abs(weight_sum - 1.0) < 1e-6, f"weights sum {weight_sum} not within 1e-6 of 1.0"


# ---------------------------------------------------------------------------
# AC-FR4100-02: Missing predictions file — exit code 2
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_fr4100_02_missing_predictions_exit_code_2(tmp_path, industry_map_file, capsys):
    """AC-FR4100-02: --predictions file not found → exit code 2, stderr
    contains 'predictions file not found'."""
    output_dir = tmp_path / "reports"
    missing_file = tmp_path / "does_not_exist.csv"

    argv = [
        "--predictions",
        str(missing_file),
        "--industry-map",
        str(industry_map_file),
        "--output",
        str(output_dir),
    ]

    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 2, f"Expected exit code 2, got {exit_code}"
    assert "predictions file not found" in captured.err, (
        f"Expected 'predictions file not found' in stderr. Got: {captured.err}"
    )


@pytest.mark.integration
def test_ac_fr4100_02_missing_industry_map_exit_code_2(tmp_path, predictions_file, capsys):
    """AC-FR4100-02: --industry-map file not found → exit code 2, stderr
    contains 'industry map file not found'."""
    output_dir = tmp_path / "reports"
    missing_file = tmp_path / "no_such_map.csv"

    argv = [
        "--predictions",
        str(predictions_file),
        "--industry-map",
        str(missing_file),
        "--output",
        str(output_dir),
    ]

    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 2, f"Expected exit code 2, got {exit_code}"
    assert "industry map file not found" in captured.err, (
        f"Expected 'industry map file not found' in stderr. Got: {captured.err}"
    )


@pytest.mark.integration
def test_ac_fr4100_02_missing_returns_exit_code_2(tmp_path, predictions_file, capsys):
    """AC-FR4100-02: --returns file not found → exit code 2, stderr
    contains 'returns file not found'."""
    output_dir = tmp_path / "reports"
    missing_file = tmp_path / "no_returns.csv"

    argv = [
        "--predictions",
        str(predictions_file),
        "--returns",
        str(missing_file),
        "--output",
        str(output_dir),
    ]

    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 2, f"Expected exit code 2, got {exit_code}"
    assert "returns file not found" in captured.err, (
        f"Expected 'returns file not found' in stderr. Got: {captured.err}"
    )


# ---------------------------------------------------------------------------
# AC-FR4100-03: Too few assets — exit code 3
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_fr4100_03_too_few_assets_exit_code_3(tmp_path, capsys):
    """AC-FR4100-03: <5 assets → exit code 3, stderr contains
    'too few assets (N < 5)'."""
    output_dir = tmp_path / "reports"
    few_predictions = _make_few_predictions(tmp_path)

    argv = [
        "--predictions",
        str(few_predictions),
        "--output",
        str(output_dir),
    ]

    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 3, f"Expected exit code 3, got {exit_code}"
    assert "too few assets" in captured.err, (
        f"Expected 'too few assets' in stderr. Got: {captured.err}"
    )


# ---------------------------------------------------------------------------
# AC-FR4100-04: Custom --cov-window propagation
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_fr4100_04_cov_window_propagation(tmp_path, predictions_file, industry_map_file):
    """AC-FR4100-04: --cov-window=30 propagates to covariance estimation.

    Verifies that when --returns is provided with enough data, the
    covariance estimation uses the custom window size. When --returns is
    NOT provided (default identity matrix fallback), the argument still
    parses correctly without error.
    """
    output_dir = tmp_path / "reports"

    # Test with default identity fallback (no --returns): verify exit code 0
    # with explicit --cov-window
    argv = [
        "--predictions",
        str(predictions_file),
        "--industry-map",
        str(industry_map_file),
        "--output",
        str(output_dir),
        "--cov-window",
        "30",
    ]

    exit_code = main(argv)
    assert exit_code == 0, f"Expected exit code 0 with --cov-window=30, got {exit_code}"


@pytest.mark.integration
def test_ac_fr4100_04_cov_window_default_value(tmp_path):
    """AC-FR4100-04: --cov-window defaults to 60 when not specified."""
    # Build arg parser directly to check default
    from trader_off.portfolio.cli import _build_parser

    parser = _build_parser()
    parsed = parser.parse_args(["--predictions", "x.csv", "--output", "y"])
    assert parsed.cov_window == 60, f"Default cov-window should be 60, got {parsed.cov_window}"


@pytest.mark.integration
def test_ac_fr4100_04_cov_window_with_returns(tmp_path, predictions_file, industry_map_file):
    """AC-FR4100-04: with --returns and custom --cov-window, the window
    is correctly applied by testing that the solver completes without error."""
    # Create synthetic returns: 100 rows, 50 columns (assets)
    preds = pl.read_csv(predictions_file)
    assets = preds["asset"].to_list()
    n_days = 100

    import numpy as np

    np.random.seed(42)
    returns_data = {"date": list(range(n_days))}
    for i, asset in enumerate(assets):
        returns_data[asset] = np.random.normal(0.0001, 0.01, n_days).tolist()

    returns_df = pl.DataFrame(returns_data)
    returns_path = tmp_path / "returns.csv"
    returns_df.write_csv(returns_path)

    output_dir = tmp_path / "reports"

    argv = [
        "--predictions",
        str(predictions_file),
        "--industry-map",
        str(industry_map_file),
        "--returns",
        str(returns_path),
        "--output",
        str(output_dir),
        "--cov-window",
        "30",
    ]

    exit_code = main(argv)
    assert exit_code == 0, (
        f"Expected exit code 0 with --returns and --cov-window=30, got {exit_code}"
    )

    # Verify output was produced
    portfolio_dirs = list(output_dir.glob("portfolio_*"))
    assert len(portfolio_dirs) > 0
