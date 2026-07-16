"""LightGBM regression model training (FR-0700).

Provides train_model for training a lightGBM Booster with early stopping
and logging support.
"""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl
from loguru import logger

# Default hyperparameters (NFR-0700)
DEFAULT_PARAMS: dict = {
    "objective": "regression",
    "num_leaves": 63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "n_estimators": 500,
    "early_stopping_rounds": 50,
    "random_state": 42,
    "feature_fraction_seed": 42,
    "bagging_seed": 42,
    "verbose": -1,
}


def _to_numpy(data: pl.DataFrame | pl.Series | np.ndarray) -> np.ndarray:
    """Convert polars DataFrame/Series to numpy array."""
    if isinstance(data, np.ndarray):
        return data
    if isinstance(data, pl.Series):
        return data.to_numpy()
    return data.to_numpy()


def train_model(
    X_train: pl.DataFrame,
    y_train: pl.DataFrame | pl.Series,
    X_valid: pl.DataFrame,
    y_valid: pl.DataFrame | pl.Series,
    params: dict | None = None,
    log_path: Path | str | None = None,
) -> lgb.Booster:
    """Train a lightGBM regression model with early stopping.

    Args:
        X_train: Training feature DataFrame.
        y_train: Training labels (DataFrame with 'label' column or Series).
        X_valid: Validation feature DataFrame.
        y_valid: Validation labels.
        params: LightGBM parameters dict. Merged with DEFAULT_PARAMS.
        log_path: Path to write training log. If None, logs only to loguru.

    Returns:
        Trained lightgbm.Booster with best_iteration applied.
    """
    # Merge with defaults
    merged_params = DEFAULT_PARAMS.copy()
    if params:
        merged_params.update(params)

    # Extract early stopping params before passing to LGBMRegressor
    early_stopping_rounds = merged_params.pop("early_stopping_rounds", 50)
    n_estimators = merged_params.pop("n_estimators", 500)

    # Convert data to numpy arrays
    X_train_np = _to_numpy(X_train)
    y_train_np = _to_numpy(y_train).ravel()
    X_valid_np = _to_numpy(X_valid)
    y_valid_np = _to_numpy(y_valid).ravel()

    # Create and train model
    model = lgb.LGBMRegressor(
        n_estimators=n_estimators,
        **merged_params,
    )

    model.fit(
        X_train_np,
        y_train_np,
        eval_set=[(X_valid_np, y_valid_np)],
        eval_metric="l2",
        callbacks=[lgb.early_stopping(early_stopping_rounds)],
    )

    booster = model.booster_
    best_iteration = model.best_iteration_

    # Log training results
    train_pred = booster.predict(X_train_np, num_iteration=best_iteration)
    train_loss = float(np.mean((train_pred - y_train_np) ** 2))

    logger.info(f"Training complete: best_iteration={best_iteration}, "
                f"final_train_loss={train_loss:.6f}")

    if log_path:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"best_iteration={best_iteration}\n"
            f"final_train_loss={train_loss:.6f}\n"
        )
        logger.info(f"Training log written to {log_path}")

    return booster
