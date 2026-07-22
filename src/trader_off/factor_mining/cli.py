"""CLI entry point for `trader-off mine-factors` (FR-0800).

Parses command-line arguments, validates inputs, orchestrates the factor
mining pipeline (templates → enumerate → evaluate → select → save → report),
and returns exit codes per acceptance criteria.

Exit codes:
    0 — success
    3 — fewer than 10 selected factors
    4 — config file missing or schema validation error
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import yaml  # type: ignore[import-untyped]

from trader_off.factor_mining.evaluation import evaluate_factor
from trader_off.factor_mining.expression import DEFAULT_PARAM_SPACE, enumerate_factors
from trader_off.factor_mining.registry import save_factor_registry
from trader_off.factor_mining.selection import select_factors
from trader_off.factor_mining.templates import list_templates

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

# ---------------------------------------------------------------------------
# Logger setup (reuses v0.1.0 pattern)
# ---------------------------------------------------------------------------
try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _create_parser() -> ArgumentParser:
    """Build the argument parser for ``trader-off mine-factors``.

    Returns:
        An argparse.ArgumentParser with all FR-0800 parameters configured.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="trader-off mine-factors",
        description="Mine alpha factors from OHLCV data.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Config YAML path (required).",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD). Falls back to config value.",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD). Falls back to config or today.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=30,
        help="Number of top factors to select (default: 30).",
    )
    parser.add_argument(
        "--corr-threshold",
        type=float,
        default=0.9,
        help="Pearson correlation threshold for redundancy removal (default: 0.9).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for reports. Defaults to reports/factor_mining_<ts>/.",
    )
    parser.add_argument(
        "--registry-dir",
        type=Path,
        default=None,
        help="Registry directory. Defaults to factor_registry/.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help=(
            "Path to OHLCV parquet fixture. Defaults to tests/fixtures/v0.2.0/ohlcv_50x252.parquet."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def _validate_config(config_path: Path) -> int | None:
    """Check that the config file exists and is readable.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Exit code 4 if config is missing, or None to continue.
    """
    if not config_path.exists():
        logger.error(f"config file not found: {config_path}")
        sys.stderr.write(f"ConfigValidationError: config file not found: {config_path}\n")
        return 4
    return None


def _load_config(config_path: Path) -> dict:
    """Load and return the YAML config.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Parsed config dict.
    """
    with open(config_path) as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Data loading (Bug 3 fix)
# ---------------------------------------------------------------------------

_DEFAULT_FIXTURE = Path("tests/fixtures/v0.2.0/ohlcv_50x252.parquet")


def _load_ohlcv_data(
    fixture_path: Path | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pl.DataFrame:
    """Load OHLCV data from fixture or Tushare.

    Priority:
        1. If ``fixture_path`` is provided, read from that parquet file.
        2. If ``TUSHARE_TOKEN`` env var is set, use QuantideDataLoader to
           fetch data from Tushare (function-scope lazy import per NFR-0100).
        3. Otherwise, read from the default v0.2.0 fixture.

    Args:
        fixture_path: Optional override path to a parquet fixture file.
        start: Start date (YYYY-MM-DD), used for Tushare queries.
        end: End date (YYYY-MM-DD), used for Tushare queries.

    Returns:
        A polars DataFrame with OHLCV columns (asset, date, open, high, low,
        close, volume, turnover, etc.).
    """
    if fixture_path is not None:
        return pl.read_parquet(fixture_path)

    token = os.environ.get("TUSHARE_TOKEN")
    if token:
        # NFR-0100: function-scope lazy import
        try:
            from quantide.data.fetchers.tushare import (
                QuantideDataLoader,  # type: ignore[import-not-found]
            )
        except ImportError:
            logger.warning("QuantideDataLoader not available, falling back to fixture")
            return pl.read_parquet(_DEFAULT_FIXTURE)

        loader = QuantideDataLoader(token=token)
        df = loader.get_daily(start_date=start, end_date=end)
        if df is None or len(df) == 0:
            logger.warning("Tushare returned empty data, falling back to fixture")
            return pl.read_parquet(_DEFAULT_FIXTURE)
        return df

    return pl.read_parquet(_DEFAULT_FIXTURE)


def _compute_labels(
    df: pl.DataFrame,
    forward_days: int = 5,
) -> pl.DataFrame:
    """Compute N-day forward returns as prediction labels.

    Computes label = close[t+N] / close[t] - 1 for each asset, sorted by date.
    The last ``forward_days`` rows per asset will have null labels.

    Args:
        df: OHLCV DataFrame with ``asset``, ``date``, ``close`` columns.
        forward_days: Number of days to look forward (default 5).

    Returns:
        DataFrame with added ``label`` column.
    """
    return df.sort(["asset", "date"]).with_columns(
        (pl.col("close").shift(-forward_days).over("asset") / pl.col("close") - 1).alias("label")
    )


def _build_factor_values(
    df: pl.DataFrame,
    factor_series: pl.Series,
) -> pl.DataFrame:
    """Build a factor_values DataFrame for evaluate_factor.

    Extracts asset and date from the input DataFrame and pairs them with the
    computed factor values.

    Args:
        df: OHLCV DataFrame with ``asset``, ``date`` columns.
        factor_series: Factor values as a polars Series, aligned with ``df``.

    Returns:
        DataFrame with columns ``asset``, ``date``, ``value``.
    """
    result = df.select(["asset", "date"]).with_columns(factor_series.alias("value"))
    return result


def _extract_dates(df: pl.DataFrame) -> list:
    """Extract sorted unique trading dates from the DataFrame.

    Args:
        df: DataFrame with a ``date`` column.

    Returns:
        List of unique date objects sorted ascending.
    """
    dates = df["date"].unique().sort().to_list()
    return dates


def _run_pipeline(args: Namespace) -> int:
    """Execute the full factor mining pipeline and return an exit code.

    Steps:
        1. Load OHLCV data (fixture or Tushare)
        2. List templates
        3. Enumerate candidate factors
        4. Evaluate each candidate with actual data
        5. Select top-K factors (ICIR ranking + Pearson de-redundancy)
        6. Save factor registry
        7. Print summary to stdout

    Args:
        args: Parsed command-line arguments (argparse.Namespace).

    Returns:
        Exit code: 0 success, 3 <10 selected.
    """
    config = _load_config(args.config)
    start = args.start or config.get("start")
    end = args.end or config.get("end")

    # -- Parse outputs paths --
    now_ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output or Path(f"reports/factor_mining_{now_ts}")
    registry_dir = args.registry_dir or Path("factor_registry")
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_dir.mkdir(parents=True, exist_ok=True)

    # -- Step 1: Load OHLCV data --
    fixture_path: Path | None = getattr(args, "fixture", None)
    data = _load_ohlcv_data(fixture_path=fixture_path, start=start, end=end)
    logger.info(f"loaded {len(data)} rows of OHLCV data")

    # -- Step 1.5: Compute labels (forward returns) --
    labels = _compute_labels(data)
    dates = _extract_dates(data)
    logger.info(f"{len(dates)} trading dates, labels computed")

    # -- Step 2: Templates --
    templates = list_templates()
    logger.info(f"{len(templates)} factor templates loaded")

    # -- Step 3: Enumerate candidates --
    candidates = enumerate_factors(templates, DEFAULT_PARAM_SPACE)
    logger.info(f"enumerated {len(candidates)} candidate factors")

    # -- Step 4: Evaluate each candidate --
    eval_errors = 0
    evaluations = []
    for spec in candidates:
        try:
            # Compute factor values using the spec's compute_fn
            factor_series = spec.compute_fn(data)
            factor_values = _build_factor_values(data, factor_series)
            # Evaluate the factor
            ev = evaluate_factor(
                factor_values=factor_values,
                labels=labels.select(["asset", "date", "label"]),
                dates=dates,
            )
            evaluations.append(ev)
        except Exception as exc:
            logger.warning(f"skipping {spec.id}: {exc}")
            eval_errors += 1
            continue

    if eval_errors > 0:
        logger.warning(f"{eval_errors} factor(s) failed evaluation")

    if len(evaluations) == 0:
        logger.warning("no factors could be evaluated")
        return 3

    # -- Step 5: Select top-K --
    selected, diagnostics = select_factors(
        evaluations=evaluations,
        factor_specs=candidates,
        top_k=args.top_k,
        corr_threshold=args.corr_threshold,
    )

    # -- Step 6: Save registry --
    save_factor_registry(
        specs=candidates,
        out_path=registry_dir / "registry.parquet",
    )

    # -- Step 7: Summary output --
    sys.stdout.write(f"枚举了 {len(candidates)} 个候选因子\n")
    sys.stdout.write(f"精选 {len(selected)} 个因子\n")
    if len(selected) < 10:
        logger.warning("fewer than 10 selected factors")
        return 3

    return 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _run(args: Namespace) -> int:
    """Top-level run function: validate config, then run pipeline.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code per FR-0800 spec.
    """
    exit_code = _validate_config(args.config)
    if exit_code is not None:
        return exit_code

    return _run_pipeline(args)


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, validate, and orchestrate the factor mining pipeline.

    Args:
        argv: Optional argument list (useful for testing).  Defaults to
              ``sys.argv[1:]``.

    Returns:
        Exit code: 0 (success), 3 (<10 sel), 4 (config error).
    """
    parser = _create_parser()
    args = parser.parse_args(argv)
    return _run(args)
