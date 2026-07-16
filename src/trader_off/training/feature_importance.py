"""Feature importance extraction (FR-1400).

Extracts feature importance scores from a trained lightGBM booster
using gain-based importance.
"""

import lightgbm as lgb
import polars as pl
from loguru import logger


def extract_feature_importance(
    booster: lgb.Booster,
    feature_names: list[str],
) -> pl.DataFrame:
    """Extract feature importance from a trained lightGBM booster.

    Uses importance_type='gain' and returns a DataFrame sorted by
    importance descending.

    Args:
        booster: Trained lightgbm Booster.
        feature_names: List of feature names in training order.

    Returns:
        DataFrame with columns: feature, importance, rank.
        Empty DataFrame if no trees have been trained.
    """
    try:
        num_trees = booster.num_trees()
    except Exception:
        num_trees = 0

    if num_trees == 0:
        logger.info("feature_importance empty, no trees trained")
        return pl.DataFrame(
            schema={"feature": pl.Utf8, "importance": pl.Float64, "rank": pl.Int32},
        )

    # Get importance values
    importances = booster.feature_importance(importance_type="gain")

    # Align with feature names
    n_feats = len(feature_names)
    imp_list = []
    for i in range(n_feats):
        imp_list.append({
            "feature": feature_names[i] if i < len(feature_names) else f"f_{i}",
            "importance": float(importances[i]) if i < len(importances) else 0.0,
        })

    df = pl.DataFrame(imp_list)
    df = df.sort("importance", descending=True)
    df = df.with_columns(
        pl.int_range(1, len(df) + 1, dtype=pl.Int32).alias("rank")
    )

    return df
