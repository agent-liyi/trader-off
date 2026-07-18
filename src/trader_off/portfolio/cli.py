"""Portfolio optimization CLI — `trader-off optimize` (FR-4100).

Exit codes:
    0 — success
    2 — predictions file not found or invalid
    3 — too few assets (<5 threshold)
    4 — configuration/parameter error
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import numpy as np
import polars as pl
from loguru import logger

from trader_off.portfolio.baseline import compare_to_baseline
from trader_off.portfolio.constraints import OptimizerConstraints
from trader_off.portfolio.covariance import estimate_covariance
from trader_off.portfolio.expected_returns import build_expected_returns
from trader_off.portfolio.industry import load_industry_map
from trader_off.portfolio.persistence import save_portfolio_results
from trader_off.portfolio.solver import solve_max_sharpe


class OptimizeArgs(NamedTuple):
    """Parsed arguments for the optimize subcommand."""

    predictions: Path
    industry_map: Path | None
    returns: Path | None
    output: Path
    max_position: float
    cov_window: int
    top_k: int
    industry_neutral: bool
    industry_neutral_tol: float


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ``trader-off optimize``."""
    parser = argparse.ArgumentParser(
        prog="trader-off optimize",
        description="Run maximum-Sharpe portfolio optimization.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Path to predictions CSV (asset, score, rank).",
    )
    parser.add_argument(
        "--industry-map",
        type=Path,
        default=None,
        help="Path to industry map CSV (asset, industry).",
    )
    parser.add_argument(
        "--returns",
        type=Path,
        default=None,
        help="Path to historical returns CSV for covariance estimation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for reports.",
    )
    parser.add_argument(
        "--max-position",
        type=float,
        default=0.10,
        help="Maximum weight per asset (default: 0.10).",
    )
    parser.add_argument(
        "--cov-window",
        type=int,
        default=60,
        help="Number of trading days for covariance estimation (default: 60).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of top assets to select (default: 20).",
    )
    parser.add_argument(
        "--industry-neutral",
        action="store_true",
        default=True,
        help="Enforce industry neutral constraints.",
    )
    parser.add_argument(
        "--industry-neutral-tol",
        type=float,
        default=0.05,
        help="Industry neutral tolerance (default: 0.05).",
    )
    return parser


def _validate_args(args: OptimizeArgs) -> int | None:
    """Validate CLI arguments and return exit code or None to continue."""
    if not args.predictions.exists():
        logger.error(f"predictions file not found: {args.predictions}")
        sys.stderr.write(f"Error: predictions file not found: {args.predictions}\n")
        return 2

    if args.industry_map is not None and not args.industry_map.exists():
        logger.error(f"industry map file not found: {args.industry_map}")
        sys.stderr.write(f"Error: industry map file not found: {args.industry_map}\n")
        return 2

    if args.returns is not None and not args.returns.exists():
        logger.error(f"returns file not found: {args.returns}")
        sys.stderr.write(f"Error: returns file not found: {args.returns}\n")
        return 2

    return None


def _load_predictions(path: Path) -> pl.DataFrame:
    """Load and validate predictions CSV."""
    df = pl.read_csv(path)
    required_cols = {"asset", "score", "rank"}
    if not required_cols.issubset(set(df.columns)):
        raise ValueError(f"predictions CSV must have columns: {required_cols}")
    return df


def _run_optimization(args: OptimizeArgs) -> int:
    """Execute the portfolio optimization pipeline."""
    now_ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = args.output / f"portfolio_{now_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load predictions
    predictions = _load_predictions(args.predictions)
    tickers = predictions["asset"].to_list()

    if len(tickers) < 5:
        logger.error(f"too few assets ({len(tickers)} < 5)")
        sys.stderr.write(f"Error: too few assets ({len(tickers)} < 5)\n")
        return 3

    # Build expected returns
    mu_dict = build_expected_returns(predictions, mode="raw")

    # Load industry map
    industry_map = None
    if args.industry_map is not None:
        industry_map = load_industry_map(args.industry_map)

    # Estimate covariance
    if args.returns is not None:
        returns_df = pl.read_csv(args.returns)
        # Use only the most recent cov_window trading days
        if args.cov_window and args.cov_window < len(returns_df):
            returns_df = returns_df.tail(args.cov_window)
        cov = estimate_covariance(returns_df, method="ledoit_wolf")
    else:
        n = len(tickers)
        cov = 0.0001 * np.eye(n)

    # Build constraints
    constraints = OptimizerConstraints(
        sum_to_one=True,
        long_only=True,
        max_weight=args.max_position,
        industry_neutral=args.industry_neutral and industry_map is not None,
        industry_neutral_tol=args.industry_neutral_tol,
    )

    # Solve
    solver_result = solve_max_sharpe(
        mu=mu_dict,
        cov=cov,
        assets=tickers,
        constraints=constraints,
        industry_map=industry_map,
    )

    # Compute baseline comparison
    if solver_result.weights is not None:
        comparison = compare_to_baseline(solver_result.weights, mu_dict, cov)
        opt_sharpe = comparison.optimized["sharpe"]
        eq_sharpe = comparison.equal_weight["sharpe"]
    else:
        opt_sharpe = 0.0
        eq_sharpe = 0.0

    # Save results
    if solver_result.weights is not None:
        weights_dict = dict(zip(tickers, solver_result.weights.tolist()))
    else:
        weights_dict = {}

    save_portfolio_results(
        weights=weights_dict,
        tickers=tickers,
        mu=mu_dict,
        cov=cov,
        out_dir=out_dir,
        solver_result=solver_result,
        constraint_report=None,
    )

    # Output summary (stdout, CLI convention)
    sys.stdout.write(f"Sharpe={opt_sharpe:.4f} (baseline={eq_sharpe:.4f})\n")
    sys.stdout.write(f"报告落盘到 {out_dir}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the optimize CLI.

    Args:
        argv: Optional argument list (useful for testing). Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 success, 2 file not found, 3 too few assets, 4 config error.
    """
    parser = _build_parser()
    parsed = parser.parse_args(argv)

    args = OptimizeArgs(
        predictions=parsed.predictions,
        industry_map=parsed.industry_map,
        returns=parsed.returns,
        output=parsed.output,
        max_position=parsed.max_position,
        cov_window=parsed.cov_window,
        top_k=parsed.top_k,
        industry_neutral=parsed.industry_neutral,
        industry_neutral_tol=parsed.industry_neutral_tol,
    )

    exit_code = _validate_args(args)
    if exit_code is not None:
        return exit_code

    return _run_optimization(args)


if __name__ == "__main__":
    import sys

    sys.exit(main())
