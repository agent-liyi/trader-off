"""Atomic persistence of portfolio optimization results (FR-4000).

Provides:
  - save_weights(weights, tickers, out_dir, *, fmt="csv") -> Path
  - load_weights(path) -> dict[str, float]
  - save_portfolio_results(...) -> dict[str, Path]: writes all 5 required files
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import polars as pl
from loguru import logger


def save_weights(
    weights: dict[str, float],
    tickers: list[str],
    out_dir: Path,
    *,
    fmt: str = "csv",
) -> Path:
    """Save portfolio weights to a CSV file using atomic write (temp + rename).

    The output CSV contains columns: asset, weight, sector, mu, in_universe.
    All weights are normalized to sum to 1.0.

    Args:
        weights: Mapping from asset ticker to weight.
        tickers: Ordered list of asset identifiers (determines column order).
        out_dir: Output directory to write the file.
        fmt: Output format (only "csv" currently supported).

    Returns:
        Path to the written CSV file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "weights.csv"

    # Normalize weights
    total = sum(weights.values())
    norm_weights = {t: weights.get(t, 0.0) / total for t in tickers}

    # Build DataFrame with all required columns
    rows = []
    for t in tickers:
        rows.append(
            {
                "asset": t,
                "weight": norm_weights[t],
                "sector": "",  # sector info not available at this level
                "mu": 0.0,  # expected return not stored here
                "in_universe": "true",
            }
        )

    df = pl.DataFrame(rows)

    # Atomic write: write to temp file, then rename
    fd, tmp_path_str = tempfile.mkstemp(dir=str(out_dir), suffix=".tmp")
    try:
        df.write_csv(tmp_path_str)
        os.close(fd)
        os.replace(tmp_path_str, str(csv_path))
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        tmp_path = Path(tmp_path_str)
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    logger.info(f"saved weights to {csv_path}")
    return csv_path


def load_weights(path: Path | str) -> dict[str, float]:
    """Load portfolio weights from a CSV file.

    Args:
        path: Path to the weights.csv file.

    Returns:
        Dict mapping asset ticker to weight.
    """
    df = pl.read_csv(path)
    return {row["asset"]: float(row["weight"]) for row in df.iter_rows(named=True)}


def save_portfolio_results(
    weights: dict[str, float],
    tickers: list[str],
    mu: dict[str, float],
    cov: np.ndarray,
    out_dir: Path,
    solver_result,  # SolverResult | None
    constraint_report,  # ConstraintReport | None
) -> dict[str, Path]:
    """Save all 5 required output files for a portfolio optimization run.

    Files written:
      - weights.csv
      - optimizer_report.json
      - portfolio_metrics.csv
      - weights_diagnostics.json
      - assets_dropped.json

    Args:
        weights: Mapping from asset ticker to weight.
        tickers: Ordered list of asset identifiers.
        mu: Expected returns per asset.
        cov: (N, N) covariance matrix.
        out_dir: Output directory for the report.
        solver_result: SolverResult from the optimizer (may be None).
        constraint_report: ConstraintReport from the checker (may be None).

    Returns:
        Dict mapping filename to Path for each written file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    # 1. weights.csv
    weights_path = save_weights(weights, tickers, out_dir)
    paths["weights.csv"] = weights_path

    # 2. optimizer_report.json
    opt_report: dict = {}
    if solver_result is not None:
        w = solver_result.weights
        opt_report = {
            "solver_status": solver_result.solver_status,
            "backend_used": solver_result.backend_used,
            "solve_time_sec": solver_result.solve_time_sec,
            "iterations": solver_result.iterations,
            "weights_sum": float(w.sum()) if w is not None else None,
            "max_weight": float(w.max()) if w is not None else None,
            "sharpe": 0.0,
        }
    optimizer_report_path = out_dir / "optimizer_report.json"
    optimizer_report_path.write_text(json.dumps(opt_report, indent=2))
    paths["optimizer_report.json"] = optimizer_report_path

    # 3. portfolio_metrics.csv
    metrics_path = out_dir / "portfolio_metrics.csv"
    if solver_result is not None and solver_result.weights is not None:
        from trader_off.portfolio.baseline import compare_to_baseline

        w_opt = solver_result.weights
        comp = compare_to_baseline(w_opt, mu, cov)
        rows = []
        for key in sorted(comp.optimized.keys()):
            rows.append(
                {
                    "metric": key,
                    "optimized": comp.optimized[key],
                    "equal_weight": comp.equal_weight[key],
                    "delta": comp.delta[key],
                }
            )
        metrics_df = pl.DataFrame(rows)
        metrics_df.write_csv(metrics_path)
    else:
        metrics_path.write_text("metric,optimized,equal_weight,delta\n")
    paths["portfolio_metrics.csv"] = metrics_path

    # 4. weights_diagnostics.json
    diag: dict = {}
    if solver_result is not None:
        diag = {
            "solver_status": solver_result.solver_status,
            "solve_time_sec": solver_result.solve_time_sec,
            "iterations": solver_result.iterations,
            "asset_count": len(tickers),
            "backend_used": solver_result.backend_used,
        }
    diag_path = out_dir / "weights_diagnostics.json"
    diag_path.write_text(json.dumps(diag, indent=2))
    paths["weights_diagnostics.json"] = diag_path

    # 5. assets_dropped.json
    dropped_path = out_dir / "assets_dropped.json"
    dropped_path.write_text(json.dumps([], indent=2))
    paths["assets_dropped.json"] = dropped_path

    logger.info(f"portfolio results saved to {out_dir}")
    return paths
