"""Model serialization and version management (FR-0800).

Provides save_model and load_model for persisting lightGBM models
with scaler, feature names, and metadata to a versioned directory.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import lightgbm as lgb
from loguru import logger

from trader_off.data.preprocess import StandardScaler
from trader_off.utils.exceptions import ModelVersionExistsError


@dataclass
class ModelArtifact:
    """Container for a loaded model and its associated artifacts.

    Attributes:
        booster: Trained lightgbm Booster.
        scaler: Fitted StandardScaler for feature normalization.
        feature_names: Ordered list of feature names used during training.
        metadata: Training metadata dict (params, dates, IC metrics, etc.).
    """

    booster: lgb.Booster
    scaler: StandardScaler
    feature_names: list[str]
    metadata: dict


def _generate_version() -> str:
    """Generate default version string in YYYYMMDD_HHMMSS format."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_model(
    booster: lgb.Booster,
    scaler: StandardScaler,
    metadata: dict,
    version: str | None = None,
    models_dir: Path | str = "models",
    dropped_features: list[str] | None = None,
    feature_names: list[str] | None = None,
) -> Path:
    """Save a trained model and its artifacts to a versioned directory.

    Creates models/<version>/ with:
    - model.pkl: joblib-serialized Booster
    - scaler.json: mean_ and std_ from StandardScaler
    - dropped_features.json: list of dropped feature names
    - feature_names.json: ordered list of feature names
    - metadata.json: training metadata dict

    Args:
        booster: Trained lightgbm Booster.
        scaler: Fitted StandardScaler.
        metadata: Training metadata dict.
        version: Version string. Auto-generated if None (YYYYMMDD_HHMMSS).
        models_dir: Root directory for model storage.
        dropped_features: List of feature names dropped during preprocessing.
        feature_names: Ordered list of feature names.

    Returns:
        Path to the model version directory.

    Raises:
        ModelVersionExistsError: If the version directory already exists.
    """
    if version is None:
        version = _generate_version()

    if dropped_features is None:
        dropped_features = []
    if feature_names is None:
        feature_names = []

    models_dir = Path(models_dir)
    model_dir = models_dir / version

    if model_dir.exists():
        raise ModelVersionExistsError(
            f"Model version '{version}' already exists at {model_dir}"
        )

    model_dir.mkdir(parents=True, exist_ok=False)

    # Serialize booster (use joblib for safe deserialization)
    joblib.dump(booster, model_dir / "model.pkl")

    # Serialize scaler
    scaler_data = {
        "mean_": scaler.mean_,
        "std_": scaler.std_,
        "feature_names": scaler.feature_names,
    }
    (model_dir / "scaler.json").write_text(json.dumps(scaler_data, indent=2))

    # Serialize dropped features
    (model_dir / "dropped_features.json").write_text(
        json.dumps(dropped_features, indent=2)
    )

    # Serialize feature names
    (model_dir / "feature_names.json").write_text(
        json.dumps(feature_names, indent=2)
    )

    # Serialize metadata
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    logger.info(f"Model saved to {model_dir} (version={version})")
    return model_dir


def load_model(
    version: str,
    models_dir: Path | str = "models",
) -> ModelArtifact:
    """Load a trained model and its artifacts from a versioned directory.

    Args:
        version: Version string identifying the model directory.
        models_dir: Root directory for model storage.

    Returns:
        ModelArtifact with booster, scaler, feature_names, and metadata.

    Raises:
        FileNotFoundError: If the version directory or required files are missing.
    """
    models_dir = Path(models_dir)
    model_dir = models_dir / version

    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    # Load booster (joblib for safe deserialization)
    booster = joblib.load(model_dir / "model.pkl")
    if not isinstance(booster, lgb.Booster):
        raise TypeError(f"Expected lightgbm.Booster, got {type(booster)}")

    # Load scaler
    scaler_data = json.loads((model_dir / "scaler.json").read_text())
    scaler = StandardScaler(
        mean_=scaler_data["mean_"],
        std_=scaler_data["std_"],
        feature_names=scaler_data["feature_names"],
    )

    # Load feature names
    feature_names = json.loads((model_dir / "feature_names.json").read_text())

    # Load metadata
    metadata = json.loads((model_dir / "metadata.json").read_text())

    logger.info(f"Model loaded from {model_dir} (version={version})")
    return ModelArtifact(
        booster=booster,
        scaler=scaler,
        feature_names=feature_names,
        metadata=metadata,
    )
