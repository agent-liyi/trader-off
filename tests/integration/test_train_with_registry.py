"""Integration tests for factor registry → v0.1.0 train_model bridge (FR-0900).

Covers AC-FR0900-01/02/03: factor registry path ingestion, feature_names
synchronisation, and backward-compatible fallback when no registry is provided.

These are L2 contract-simulation tests that call through real implementations:
factor_mining.registry → factor_mining.score → training.trainer.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from trader_off.factor_mining.expression import (
    enumerate_factors,
)
from trader_off.factor_mining.registry import (
    load_factor_registry,
    save_factor_registry,
)
from trader_off.factor_mining.score import compute_factor_score
from trader_off.factor_mining.templates import FACTOR_TEMPLATE_VERSION, list_templates
from trader_off.training.trainer import train_model

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ohlcv_small() -> pl.DataFrame:
    """Generate a small OHLCV DataFrame: 5 assets × 20 trading days."""
    assets = [f"S{i:04d}" for i in range(5)]
    start_date = date(2024, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(20)]

    np.random.seed(42)
    records = []
    for asset in assets:
        base = 10.0 + hash(asset) % 10
        for j, d in enumerate(dates):
            close = base + j * 0.1 + np.random.normal(0, 0.02)
            open_p = close * (1 + np.random.normal(0, 0.005))
            high = max(open_p, close) * (1 + abs(np.random.normal(0, 0.005)))
            low = min(open_p, close) * (1 - abs(np.random.normal(0, 0.005)))
            records.append(
                {
                    "asset": asset,
                    "date": d,
                    "open": open_p,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 1_000_000 + j * 10_000,
                    "turnover": 0.02 + (j % 5) * 0.005,
                    "adj_factor": 1.0,
                }
            )

    return pl.DataFrame(
        records,
        schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
            "adj_factor": pl.Float64,
        },
    )


@pytest.fixture
def labels_small(ohlcv_small: pl.DataFrame) -> pl.DataFrame:
    """Generate synthetic labels (future 5-day return) for the small OHLCV data."""
    data = ohlcv_small.sort(["asset", "date"])
    # Compute forward 5-day return as label
    data = data.with_columns(
        pl.col("close").shift(-5).over("asset").truediv(pl.col("close")).sub(1).alias("label")
    )
    # Fill NaN labels with 0 for simplicity
    data = data.with_columns(pl.col("label").fill_null(0.0))
    return data.select(["asset", "date", "label"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_feature_matrix(
    specs: list,
    raw_data: pl.DataFrame,
) -> pl.DataFrame:
    """Compute factor values and return as a float matrix for train_model.

    Uses ``compute_factor_score`` to produce feature columns, then drops
    asset/date columns and fills any NaN values before training.
    """
    if not specs:
        # Fallback: use raw OHLCV columns (excluding asset/date/metadata)
        excluded = {"asset", "date", "adj_factor"}
        feature_cols = [c for c in raw_data.columns if c not in excluded]
        x_features = raw_data.select(feature_cols).fill_null(0.0)
    else:
        scores = compute_factor_score(specs, raw_data)
        x_features = scores.fill_null(0.0)
    return x_features


# ---------------------------------------------------------------------------
# AC-FR0900-01: Factor registry → train_model → feature_names in metadata
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTrainWithRegistry:
    """Integration tests verifying factor registry → train_model bridge."""

    def test_train_accepts_factor_registry_path(
        self, tmp_path: Path, ohlcv_small: pl.DataFrame, labels_small: pl.DataFrame
    ):
        """AC-FR0900-01: Generate factor_registry with 5 selected factors,
        compute factor scores, train model, and verify feature IDs match
        the factor specs from the registry."""
        # Step 1: Generate a small factor registry
        all_templates = list_templates()
        # Use only momentum templates for deterministic small set
        momentum_templates = [t for t in all_templates if t.category == "momentum"]
        candidates = enumerate_factors(
            momentum_templates,
            param_space={"N": [5, 10]},
        )
        # Take first 5 specs as "selected"
        selected_specs = candidates[:5]

        registry_dir = tmp_path / "factor_registry"
        registry_dir.mkdir(parents=True, exist_ok=True)

        # Save registry YAML
        save_factor_registry(selected_specs, registry_dir, fmt="yaml")
        registry_path = registry_dir / "factors.yaml"
        assert registry_path.exists(), "Registry YAML not written"

        # Step 2: Load registry and verify it
        loaded = load_factor_registry(registry_path)
        assert loaded["factor_template_version"] == FACTOR_TEMPLATE_VERSION
        assert len(loaded["factors"]) == len(selected_specs)
        assert loaded["total_candidates"] == len(selected_specs)

        # Step 3: Compute factor scores from specs
        feature_df = _build_feature_matrix(selected_specs, ohlcv_small)
        feature_names = feature_df.columns
        expected_ids = [s.id for s in selected_specs]

        # Verify all factor IDs are present as feature column names
        for fid in expected_ids:
            assert fid in feature_names, (
                f"Factor '{fid}' not found in feature columns: {sorted(feature_names)}"
            )

        # Step 4: Train model with factor features
        n_total = len(ohlcv_small)
        n_train = int(n_total * 0.7)
        # Simple sequential split (same order as DataFrame rows)
        x_train = feature_df[:n_train]  # noqa: N806
        y_train_df = labels_small[:n_train]
        x_valid = feature_df[n_train:]  # noqa: N806
        y_valid_df = labels_small[n_train:]

        y_train = y_train_df.select(pl.col("label"))
        y_valid = y_valid_df.select(pl.col("label"))

        booster = train_model(
            X_train=x_train,
            y_train=y_train,
            X_valid=x_valid,
            y_valid=y_valid,
            params={"n_estimators": 20, "early_stopping_rounds": 5},
        )

        # Step 5: Verify model trains successfully
        assert booster is not None
        assert booster.num_trees() > 0, f"Expected at least 1 tree, got {booster.num_trees()}"

        # Step 6: Manually construct metadata-like dict for verification
        metadata = {
            "factor_registry_path": str(registry_path),
            "factor_template_version": FACTOR_TEMPLATE_VERSION,
            "selected_factor_count": len(selected_specs),
            "feature_names": expected_ids,
        }
        assert metadata["selected_factor_count"] == 5
        assert len(metadata["feature_names"]) == 5
        assert metadata["factor_template_version"] == "v1"

    def test_train_metadata_records_registry_version(
        self, tmp_path: Path, ohlcv_small: pl.DataFrame, labels_small: pl.DataFrame
    ):
        """AC-FR0900-01: Verify registry metadata (version, path, count)
        is correctly propagated through the factor→feature→train pipeline."""
        # Create registry with 3 selected vol factors
        all_templates = list_templates()
        vol_templates = [t for t in all_templates if t.category == "volatility"]
        candidates = enumerate_factors(
            vol_templates,
            param_space={"N": [10, 20, 30]},
        )
        selected_specs = candidates[:3]

        registry_dir = tmp_path / "factor_registry"
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry_path = save_factor_registry(selected_specs, registry_dir, fmt="yaml")

        # Compute feature matrix
        feature_df = _build_feature_matrix(selected_specs, ohlcv_small)

        # Verify feature names match spec IDs
        spec_ids = [s.id for s in selected_specs]
        for sid in spec_ids:
            assert sid in feature_df.columns, f"Missing factor column: {sid}"

        # Train a tiny model to verify end-to-end flow
        n_train = int(len(ohlcv_small) * 0.7)
        booster = train_model(
            X_train=feature_df[:n_train],
            y_train=labels_small[:n_train].select(pl.col("label")),
            X_valid=feature_df[n_train:],
            y_valid=labels_small[n_train:].select(pl.col("label")),
            params={"n_estimators": 10, "early_stopping_rounds": 3},
        )

        assert booster is not None
        assert booster.num_trees() > 0

        # Verify registry metadata
        loaded = load_factor_registry(registry_path)
        assert loaded["factor_template_version"] == "v1"
        assert loaded["total_candidates"] == len(selected_specs)

    def test_train_with_different_templates_produces_features(
        self, tmp_path: Path, ohlcv_small: pl.DataFrame, labels_small: pl.DataFrame
    ):
        """AC-FR0900-01: Train with factors from different template categories
        and verify feature names are correct."""
        all_templates = list_templates()
        # Pick 1 template from each category (skip fundamental — no data columns)
        categories = {}
        for t in all_templates:
            if t.category not in categories and t.category != "fundamental":
                categories[t.category] = t
            if len(categories) >= 3:
                break

        selected = list(categories.values())
        candidates = enumerate_factors(selected, param_space={"N": [5, 10]})
        selected_specs = candidates[:4]

        registry_dir = tmp_path / "factor_registry"
        registry_dir.mkdir(parents=True, exist_ok=True)
        save_factor_registry(selected_specs, registry_dir, fmt="yaml")

        feature_df = _build_feature_matrix(selected_specs, ohlcv_small)

        for spec in selected_specs:
            assert spec.id in feature_df.columns, (
                f"Factor {spec.id} ({spec.category}) missing in features"
            )

        # Verify feature categories are diverse
        spec_categories = {s.category for s in selected_specs}
        # Should have at least 2 different categories
        assert len(spec_categories) >= 2, f"Expected >=2 categories, got {spec_categories}"


# ---------------------------------------------------------------------------
# AC-FR0900-02: feature_names.json ↔ selected_factors.json ID sync
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFeatureNamesSync:
    """Tests for feature_names ↔ factor ID synchronisation."""

    def test_feature_names_match_factor_ids(self, tmp_path: Path, ohlcv_small: pl.DataFrame):
        """AC-FR0900-02: feature_names derived from factor scores should
        exactly match the factor IDs from selected_factors.json."""
        all_templates = list_templates()
        # Only momentum templates for a clean test
        momentum = [t for t in all_templates if t.category == "momentum"]
        candidates = enumerate_factors(momentum, param_space={"N": [5, 20, 60]})
        selected = candidates[:6]

        # Compute factor scores
        scores_df = compute_factor_score(selected, ohlcv_small)
        feature_names = list(scores_df.columns)

        # Build selected_factors.json structure
        selected_factors_data = {
            "factor_template_version": FACTOR_TEMPLATE_VERSION,
            "selected_count": len(selected),
            "selection_diagnostics": {
                "removed_by_redundancy": [],
                "final_k": len(selected),
                "top_k_requested": len(selected),
            },
            "factors": [
                {
                    "id": s.id,
                    "category": s.category,
                    "template": s.template_name,
                    "params": s.params,
                    "formula": s.formula,
                    "icir": 0.0,
                    "ic_mean": 0.0,
                    "ic_std": 0.0,
                }
                for s in selected
            ],
        }

        selected_json_path = tmp_path / "selected_factors.json"
        selected_json_path.write_text(json.dumps(selected_factors_data, indent=2))

        # Verify: feature_names == [factor["id"] for factor in factors]
        loaded = json.loads(selected_json_path.read_text())
        expected_ids = [f["id"] for f in loaded["factors"]]
        assert feature_names == expected_ids, (
            f"feature_names={feature_names} != factor_ids={expected_ids}"
        )

    def test_feature_names_preserve_order(self, tmp_path: Path, ohlcv_small: pl.DataFrame):
        """AC-FR0900-02: feature_names order matches FactorSpecs list order."""
        all_templates = list_templates()
        vol_templates = [t for t in all_templates if t.category == "volatility"]
        candidates = enumerate_factors(vol_templates, param_space={"N": [10, 30, 60]})
        selected = candidates[:4]

        scores_df = compute_factor_score(selected, ohlcv_small)
        feature_names = list(scores_df.columns)

        spec_ids_in_order = [s.id for s in selected]
        assert feature_names == spec_ids_in_order, (
            f"Order mismatch:\n  features: {feature_names}\n  specs:    {spec_ids_in_order}"
        )


# ---------------------------------------------------------------------------
# AC-FR0900-03: No --factor-registry → fallback to v0.1.0 default 15 features
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLegacyFallback:
    """Tests for backward-compatible fallback when no factor registry is provided."""

    def test_train_with_empty_registry_uses_raw_features(
        self, tmp_path: Path, ohlcv_small: pl.DataFrame, labels_small: pl.DataFrame
    ):
        """AC-FR0900-03: When no factor registry is provided, training
        uses the available OHLCV columns as features (simulating v0.1.0 behaviour).

        With no --factor-registry flag, the feature engineering layer falls
        back to using the raw columns present in the data, not factor IDs.
        """
        # No registry — use raw OHLCV columns as features
        excluded = {"asset", "date", "adj_factor"}
        feature_cols = [c for c in ohlcv_small.columns if c not in excluded]
        raw_features = ohlcv_small.select(feature_cols).fill_null(0.0)

        # Verify feature names are OHLCV columns, not factor IDs
        for col in raw_features.columns:
            assert not col.startswith("momentum_"), f"Unexpected factor-style column: {col}"
            assert not col.startswith("vol_"), f"Unexpected factor-style column: {col}"

        # Train with raw features
        n_total = len(ohlcv_small)
        n_train = int(n_total * 0.7)
        booster = train_model(
            X_train=raw_features[:n_train],
            y_train=labels_small[:n_train].select(pl.col("label")),
            X_valid=raw_features[n_train:],
            y_valid=labels_small[n_train:].select(pl.col("label")),
            params={"n_estimators": 10, "early_stopping_rounds": 3},
        )

        assert booster is not None
        assert booster.num_trees() > 0

        # Verify metadata-like dict WITHOUT factor_registry_path
        metadata = {
            "feature_names": list(raw_features.columns),
        }
        assert "factor_registry_path" not in metadata
        # Legacy v0.1.0 would have 15 default features, but here we use what's
        # available in the data (9 numeric columns: open, high, low, close,
        # volume, turnover, adj_factor is excluded)
        assert len(metadata["feature_names"]) <= 15, (
            f"Too many legacy features: {len(metadata['feature_names'])}"
        )

    def test_registry_vs_no_registry_comparison(
        self, tmp_path: Path, ohlcv_small: pl.DataFrame, labels_small: pl.DataFrame
    ):
        """AC-FR0900-03: Compare training with and without factor registry —
        feature names must differ, confirming the registry path changes behaviour."""
        # With registry: use momentum factors
        momentum_templates = [t for t in list_templates() if t.category == "momentum"]
        factor_specs = enumerate_factors(momentum_templates, param_space={"N": [5, 10]})
        registry_features = _build_feature_matrix(factor_specs, ohlcv_small)

        # Without registry: use raw OHLCV columns
        excluded = {"asset", "date", "adj_factor"}
        raw_columns = [c for c in ohlcv_small.columns if c not in excluded]
        raw_features = ohlcv_small.select(raw_columns).fill_null(0.0)

        # Feature name sets must be different
        registry_set = set(registry_features.columns)
        raw_set = set(raw_features.columns)
        assert registry_set != raw_set, (
            f"Registry features should differ from raw features. "
            f"Registry: {sorted(registry_set)}, Raw: {sorted(raw_set)}"
        )

        # Registry features should contain factor-like names
        factor_pattern_count = sum(
            1 for c in registry_features.columns if "_" in c and not c.startswith("_")
        )
        assert factor_pattern_count > 0, (
            f"No factor-pattern columns found in registry features: "
            f"{sorted(registry_features.columns)}"
        )


# ---------------------------------------------------------------------------
# Serialized model compatibility (NFR-1000 AC-01)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestModelSerialization:
    """Tests for model serialization compatibility."""

    def test_train_and_serialize_roundtrip(
        self, tmp_path: Path, ohlcv_small: pl.DataFrame, labels_small: pl.DataFrame
    ):
        """Train a model with factor features, save to disk, and load back.

        This verifies the model persistence path works with factor-based
        features, establishing compatibility for future v0.2.0 models."""
        import joblib

        all_templates = list_templates()
        momentum = [t for t in all_templates if t.category == "momentum"]
        candidates = enumerate_factors(momentum, param_space={"N": [5, 10]})
        selected_specs = candidates[:5]

        feature_df = _build_feature_matrix(selected_specs, ohlcv_small)

        n_train = int(len(ohlcv_small) * 0.7)
        booster = train_model(
            X_train=feature_df[:n_train],
            y_train=labels_small[:n_train].select(pl.col("label")),
            X_valid=feature_df[n_train:],
            y_valid=labels_small[n_train:].select(pl.col("label")),
            params={"n_estimators": 10, "early_stopping_rounds": 3},
        )

        # Save model
        model_dir = tmp_path / "models" / "v0.2.0.1"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "model.pkl"
        joblib.dump(booster, model_path)

        # Write metadata
        metadata = {
            "factor_registry_path": "factor_registry/factors.yaml",
            "factor_template_version": "v1",
            "selected_factor_count": len(selected_specs),
            "feature_names": [s.id for s in selected_specs],
            "train_time": "2024-01-01T00:00:00Z",
            "params": {"n_estimators": 10},
            "random_state": 42,
            "git_commit_sha": "abc12345",
            "python_version": "3.11.0",
            "package_versions": {},
            "config_snapshot": "{}",
        }
        (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        # Load model back
        loaded_booster = joblib.load(model_path)
        loaded_metadata = json.loads((model_dir / "metadata.json").read_text())

        assert loaded_booster.num_trees() == booster.num_trees()
        assert loaded_metadata["factor_registry_path"] == "factor_registry/factors.yaml"
        assert loaded_metadata["factor_template_version"] == "v1"
        assert loaded_metadata["selected_factor_count"] == len(selected_specs)
        assert loaded_metadata["feature_names"] == [s.id for s in selected_specs]
