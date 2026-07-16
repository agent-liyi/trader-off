"""Feature standardization and missing value handling (FR-0400).

Provides fit_scaler_and_impute and transform functions for z-score
standardization with forward-fill imputation by asset.
"""

from dataclasses import dataclass, field

import polars as pl
from loguru import logger


@dataclass
class StandardScaler:
    """Z-score scaler parameters (per-feature mean and std).

    Attributes:
        mean_: Per-feature mean values.
        std_: Per-feature standard deviation values.
        feature_names: List of feature names in order.
    """

    mean_: dict[str, float] = field(default_factory=dict)
    std_: dict[str, float] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)


def fit_scaler_and_impute(
    X_train: pl.DataFrame,  # noqa: N803
) -> tuple[pl.DataFrame, StandardScaler, list[str]]:
    """Fit a z-score scaler on training data with forward-fill imputation.

    Processing order:
    1. Forward-fill NaN values within each asset group
    2. Fill remaining NaN with 0
    3. Drop columns that are entirely NaN
    4. Compute z-score: (x - mean) / std for each remaining feature column

    Args:
        X_train: DataFrame with asset, date columns plus feature columns.

    Returns:
        Tuple of (transformed_df, scaler, dropped_features).
    """
    # Identify feature columns (exclude asset, date)
    key_cols = {"asset", "date"}
    all_cols = set(X_train.columns)
    feature_cols = sorted(all_cols - key_cols)

    # Step 1: Forward fill within each asset group
    df = X_train.sort(["asset", "date"])
    for col in feature_cols:
        df = df.with_columns(
            pl.col(col).fill_null(strategy="forward").over("asset").alias(col)
        )

    # Step 2: Remaining NaN → 0
    df = df.fill_null(0.0)

    # Step 3: Drop all-NaN columns (after fill, these are all-0 columns)
    # But we also check original data for columns that were entirely NaN
    # before any fill (these would become all-0 after step 2)
    dropped_features: list[str] = []
    kept_features: list[str] = []
    for col in feature_cols:
        # Check if original column was all NaN
        if X_train[col].null_count() == len(X_train):
            dropped_features.append(col)
            logger.info(f"Dropping all-NaN feature: {col}")
        else:
            kept_features.append(col)

    # Remove dropped columns
    if dropped_features:
        df = df.drop(dropped_features)

    # Step 4: Z-score
    scaler = StandardScaler()
    z_cols = []
    for col in kept_features:
        col_mean = df[col].mean()
        col_std = df[col].std()
        # Handle case where std is 0 (constant column)
        if col_std is None or col_std == 0.0:
            col_std = 1.0
        scaler.mean_[col] = col_mean
        scaler.std_[col] = col_std
        scaler.feature_names.append(col)
        z_cols.append(((pl.col(col) - col_mean) / col_std).alias(col))

    df = df.with_columns(z_cols)

    return df, scaler, dropped_features


def transform(X: pl.DataFrame, scaler: StandardScaler) -> pl.DataFrame:  # noqa: N803
    """Apply a fitted scaler to transform data.

    Uses the saved mean and std from training. Features not in the scaler
    are passed through unchanged.

    Args:
        X: DataFrame to transform.
        scaler: Fitted StandardScaler from fit_scaler_and_impute.

    Returns:
        Transformed DataFrame with z-score normalized feature columns.
    """
    result = X

    for col in scaler.feature_names:
        if col in result.columns:
            col_mean = scaler.mean_[col]
            col_std = scaler.std_[col]
            result = result.with_columns(
                ((pl.col(col) - col_mean) / col_std).alias(col)
            )

    return result
