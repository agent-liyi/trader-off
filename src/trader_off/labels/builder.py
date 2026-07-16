"""Label construction: future 5-day return labels (FR-0500).

build_labels: label[t] = close[t+horizon] / close[t] - 1.
compute_label_stats: mean, std, min, p1, p99, max of non-NaN labels.
"""

import json
from pathlib import Path

import polars as pl
from loguru import logger


def build_labels(
    close_df: pl.DataFrame,
    horizon: int = 5,
    filter_limit_up_down: bool = True,
    filter_output_path: Path | str | None = None,
) -> pl.DataFrame:
    """Build future N-day return labels from close price data.

    Computes label[t] = close[t+horizon] / close[t] - 1, grouped by asset.
    Labels where t+horizon exceeds available data or close[t+horizon] is NaN
    are set to NaN.

    Args:
        close_df: DataFrame with at minimum asset, date, close columns.
                  May optionally include limit_up and limit_down (Boolean).
        horizon: Number of days to look forward. Defaults to 5.
        filter_limit_up_down: If True and limit_up/limit_down columns exist,
            nullify labels where either is True and write filter records.
        filter_output_path: Path to write limit_up_down_filter.json.
            Only used when filtering occurs.

    Returns:
        DataFrame with columns: asset, date, label (Float64).
    """
    result = close_df.sort(["asset", "date"]).select(["asset", "date", "close"])

    # Compute label = close[t+horizon] / close[t] - 1
    result = result.with_columns(
        (pl.col("close").shift(-horizon) / pl.col("close") - 1.0)
        .over("asset")
        .alias("label")
    )

    # Apply limit up/down filter if requested and columns exist
    if filter_limit_up_down:
        limit_cols = _find_limit_columns(close_df)
        if limit_cols:
            filter_records = []
            for col_name in limit_cols:
                # Get the raw limit column aligned with result
                limit_series = close_df.sort(["asset", "date"])[col_name]
                # Nullify labels where limit is True
                mask = limit_series.to_list()
                for i, is_limited in enumerate(mask):
                    if is_limited:
                        filter_records.append({
                            "asset": result["asset"][i],
                            "date": str(result["date"][i]),
                            "reason": col_name,
                        })
                # Set label to None where limit flag is True
                result = result.with_columns(
                    pl.when(limit_series)
                    .then(pl.lit(None, dtype=pl.Float64))
                    .otherwise(pl.col("label"))
                    .alias("label")
                )

            # Deduplicate filter records by (asset, date)
            seen = set()
            unique_records = []
            for r in filter_records:
                key = (r["asset"], r["date"])
                if key not in seen:
                    seen.add(key)
                    unique_records.append(r)

            if unique_records and filter_output_path:
                filter_output_path = Path(filter_output_path)
                filter_output_path.parent.mkdir(parents=True, exist_ok=True)
                filter_output_path.write_text(json.dumps(unique_records, indent=2))
                logger.info(f"Limit filter records written to {filter_output_path}")
        else:
            logger.warning("limit_up/limit_down columns not found, "
                           "skipping limit filter")

    return result.select(["asset", "date", "label"])


def _find_limit_columns(df: pl.DataFrame) -> list[str]:
    """Find limit_up and/or limit_down columns in the DataFrame."""
    found = []
    for col in ["limit_up", "limit_down"]:
        if col in df.columns:
            found.append(col)
    return found


def compute_label_stats(
    labels: pl.DataFrame,
    output_path: Path | str | None = None,
) -> dict[str, float]:
    """Compute summary statistics of label distribution.

    Args:
        labels: DataFrame with a 'label' column (Float64). NaN values ignored.
        output_path: If provided, write stats as JSON to this path.

    Returns:
        Dict with keys: mean, std, min, p1, p99, max.
    """
    label_col = labels["label"].drop_nulls()

    mean_val = label_col.mean()
    std_val = label_col.std()

    # Percentiles: min, p1, p99, max
    if len(label_col) == 0:
        stats = {
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "p1": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    else:
        sorted_vals = label_col.sort()
        n = len(sorted_vals)
        stats = {
            "mean": mean_val,
            "std": std_val,
            "min": sorted_vals[0],
            "p1": _percentile(sorted_vals, 1),
            "p99": _percentile(sorted_vals, 99),
            "max": sorted_vals[-1],
        }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(stats, indent=2))
        logger.info(f"Label stats written to {output_path}")

    return stats


def _percentile(sorted_vals: pl.Series, pct: int) -> float:
    """Compute approximate percentile from sorted values."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    idx = int(round((pct / 100.0) * (n - 1)))
    idx = max(0, min(idx, n - 1))
    return sorted_vals[idx]
