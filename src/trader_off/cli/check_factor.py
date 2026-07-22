"""CLI entry point for `trader-off check-factor` (FR-0100).

Evaluates a single factor by name against OHLCV data, computing IC / ICIR /
Rank IC / Rank ICIR and determining validity via |ICIR| threshold.

Outputs JSON to stdout with status, factor name, evaluation metrics, and
validity flag.

Exit codes:
    0 — success (factor found and evaluated, or no valid data)
    1 — factor not found

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_FIXTURE = Path("tests/fixtures/v0.2.0/ohlcv_50x252.parquet")
_DEFAULT_CAPITAL = 1_000_000
_DEFAULT_IC_THRESHOLD = 0.3
_DEFAULT_FORWARD_DAYS = 5


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _create_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ``trader-off check-factor``.

    Returns:
        An argparse.ArgumentParser with FR-0100 parameters configured.
    """
    parser = argparse.ArgumentParser(
        prog="trader-off-check-factor",
        description="Evaluate a single factor against OHLCV data.",
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Factor name (e.g., momentum_5).",
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=_DEFAULT_CAPITAL,
        help=f"Initial capital (default: {_DEFAULT_CAPITAL}).",
    )
    parser.add_argument(
        "--ic-threshold",
        type=float,
        default=_DEFAULT_IC_THRESHOLD,
        help=f"Minimum |ICIR| for valid=true (default: {_DEFAULT_IC_THRESHOLD}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON output format.",
    )
    return parser


# ---------------------------------------------------------------------------
# Data loading (reuses v0.5.2 pattern)
# ---------------------------------------------------------------------------


def _load_ohlcv_data(
    start: str | None = None,
    end: str | None = None,
) -> pl.DataFrame:
    """Load OHLCV data from default fixture or Tushare.

    Priority:
        1. If ``TUSHARE_TOKEN`` env var is set, use QuantideDataLoader
           (function-scope lazy import per NFR-0100).
        2. Otherwise, read from the default v0.2.0 fixture.

    Args:
        start: Start date (YYYY-MM-DD), used for Tushare queries.
        end: End date (YYYY-MM-DD), used for Tushare queries.

    Returns:
        A polars DataFrame with OHLCV columns.
    """
    token = os.environ.get("TUSHARE_TOKEN")
    if token:
        try:
            from trader_off.data.quantide_adapter import QuantideDataLoader
        except ImportError:
            return pl.read_parquet(_DEFAULT_FIXTURE)

        loader = QuantideDataLoader(token=token)
        try:
            import asyncio
            from datetime import date as dt_date

            df = asyncio.run(
                loader.get_daily(asset="000001.SZ", end_date=dt_date.today(), count=252)
            )
            if len(df) == 0:
                return pl.read_parquet(_DEFAULT_FIXTURE)
            return df
        except Exception:
            return pl.read_parquet(_DEFAULT_FIXTURE)

    return pl.read_parquet(_DEFAULT_FIXTURE)


# ---------------------------------------------------------------------------
# Labels computation
# ---------------------------------------------------------------------------


def _compute_labels(
    df: pl.DataFrame,
    forward_days: int = _DEFAULT_FORWARD_DAYS,
) -> pl.DataFrame:
    """Compute N-day forward returns as prediction labels.

    Args:
        df: OHLCV DataFrame with ``asset``, ``date``, ``close`` columns.
        forward_days: Number of days to look forward (default 5).

    Returns:
        DataFrame with added ``label`` column.
    """
    return df.sort(["asset", "date"]).with_columns(
        (pl.col("close").shift(-forward_days).over("asset") / pl.col("close") - 1).alias("label")
    )


def _extract_dates(df: pl.DataFrame) -> list:
    """Extract sorted unique trading dates from the DataFrame."""
    return df["date"].unique().sort().to_list()


# ---------------------------------------------------------------------------
# Factor lookup
# ---------------------------------------------------------------------------


def _find_factor_spec(name: str):
    """Find a FactorSpec by name match.

    Matches via:
        1. Exact match against candidate ``id``.
        2. Compact name match derived by replacing param placeholders
           (e.g., ``_N`` → ``_5``) in the template name.

    Args:
        name: Factor name (e.g., ``momentum_5``, ``vol_20``, ``ep``).

    Returns:
        A FactorSpec if found, or None.
    """
    from trader_off.factor_mining.expression import enumerate_factors

    candidates = enumerate_factors()

    # Pass 1: exact match against candidate ID
    for spec in candidates:
        if spec.id == name:
            return spec

    # Pass 2: compact name match (template name with params substituted)
    for spec in candidates:
        compact = spec.template_name
        for pname, pvalue in spec.params.items():
            compact = compact.replace(f"_{pname}", f"_{pvalue}")
        if compact == name:
            return spec

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Evaluate a single factor and output results as JSON.

    Args:
        argv: Command-line arguments. If None, reads from sys.argv[1:].

    Returns:
        Exit code: 0 (success), 1 (factor not found).
    """
    parser = _create_parser()
    args = parser.parse_args(argv)

    # Step 1: Load OHLCV data
    data = _load_ohlcv_data(start=args.start, end=args.end)

    # Step 2: Compute labels
    labels = _compute_labels(data)
    dates = _extract_dates(data)

    # Step 3: Find factor spec
    spec = _find_factor_spec(args.name)
    if spec is None:
        output = {
            "status": "error",
            "data": {"message": f"factor not found: {args.name}"},
        }
        sys.stdout.write(json.dumps(output) + "\n")
        return 1

    # Step 4: Compute factor values
    factor_series = spec.compute_fn(data)
    factor_values = data.select(["asset", "date"]).with_columns(factor_series.alias("value"))

    # Step 5: Evaluate
    from trader_off.factor_mining.evaluation import evaluate_factor

    ev = evaluate_factor(
        factor_values=factor_values,
        labels=labels.select(["asset", "date", "label"]),
        dates=dates,
    )

    # Step 6: Determine validity
    valid = abs(ev.icir) >= args.ic_threshold
    ic = ev.ic_mean
    icir = ev.icir
    rank_ic = ev.rank_ic_mean
    # rank_icir = rank_ic_mean / rank_ic_std (same formula as ICIR)
    if ev.rank_ic_std == 0.0:
        rank_icir = 0.0
    else:
        rank_icir = ev.rank_ic_mean / ev.rank_ic_std

    # Handle no data case: if IC mean/ICIR are zero and no labels matched
    if len(ev.ic_ts) == 0:
        output_data = {
            "factor": args.name,
            "ic": 0,
            "icir": 0,
            "rank_ic": 0,
            "rank_icir": 0,
            "valid": False,
            "reason": "no valid data",
        }
    else:
        output_data = {
            "factor": args.name,
            "ic": round(float(ic), 3),
            "icir": round(float(icir), 2),
            "rank_ic": round(float(rank_ic), 3),
            "rank_icir": round(float(rank_icir), 2),
            "valid": valid,
        }

    output = {"status": "ok", "data": output_data}
    sys.stdout.write(json.dumps(output) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
