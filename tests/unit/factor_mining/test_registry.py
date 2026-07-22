"""Unit tests for factor registry persistence — save/load parquet (FR-0600).

Adapted for Bug 4 fix: save_factor_registry now emits a single
``registry.parquet`` file; load_factor_registry reads it back.
"""

from __future__ import annotations

import json
from datetime import datetime

import polars as pl
import pytest

from trader_off.factor_mining.expression import FactorSpec, enumerate_factors
from trader_off.factor_mining.templates import (
    FACTOR_TEMPLATE_VERSION,
    FactorTemplate,
    IntRangeParam,
)

# ---------------------------------------------------------------------------
# Fixtures — reusable FactorSpec list
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_specs() -> list[FactorSpec]:
    """A small set of FactorSpecs for testing save/load round-trips."""
    t = FactorTemplate(
        name="momentum_N",
        category="momentum",
        fields=["close"],
        params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
        formula="close[t]/close[t-{N}]-1",
    )
    return enumerate_factors([t], {"N": [5, 10, 20]})


@pytest.fixture
def many_specs() -> list[FactorSpec]:
    """A larger set (≥200) for candidate count checks."""
    return enumerate_factors()


# ============================================================================
# save_factor_registry — parquet format
# ============================================================================


class TestSaveFactorRegistryParquet:
    """save_factor_registry writes a single .parquet file with correct schema.

    Replaces AC-FR0600-01 (YAML) and AC-FR0600-02 (JSON).
    """

    def test_save_to_parquet_file_exists(self, sample_specs, tmp_path):
        """File exists at out_path with .parquet suffix."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "registry.parquet"
        result = save_factor_registry(sample_specs, out_path)
        assert result == out_path
        assert out_path.exists()
        assert out_path.suffix == ".parquet"
        assert out_path.stat().st_size > 0

    def test_parquet_contains_required_columns(self, sample_specs, tmp_path):
        """Parquet contains id, category, template, params, formula,
        factor_template_version, generated_at."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "registry.parquet"
        save_factor_registry(sample_specs, out_path)

        df = pl.read_parquet(out_path)
        required = {
            "id",
            "category",
            "template",
            "params",
            "formula",
            "factor_template_version",
            "generated_at",
        }
        assert required.issubset(set(df.columns))

    def test_parquet_factor_template_version(self, sample_specs, tmp_path):
        """factor_template_version column matches FACTOR_TEMPLATE_VERSION."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "registry.parquet"
        save_factor_registry(sample_specs, out_path)

        df = pl.read_parquet(out_path)
        assert all(df["factor_template_version"].to_list())
        assert df["factor_template_version"][0] == FACTOR_TEMPLATE_VERSION

    def test_parquet_generated_at_is_iso8601_utc(self, sample_specs, tmp_path):
        """generated_at column contains ISO 8601 UTC timestamps."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "registry.parquet"
        save_factor_registry(sample_specs, out_path)

        df = pl.read_parquet(out_path)
        ts = df["generated_at"][0]
        assert isinstance(ts, str)
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_parquet_specs_round_trip(self, sample_specs, tmp_path):
        """save + read: all factor IDs are preserved."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "registry.parquet"
        save_factor_registry(sample_specs, out_path)

        df = pl.read_parquet(out_path)
        saved_ids = set(df["id"].to_list())
        original_ids = {s.id for s in sample_specs}
        assert saved_ids == original_ids

        # Spot-check params (stored as JSON string)
        for row in df.iter_rows(named=True):
            orig = next(s for s in sample_specs if s.id == row["id"])
            stored_params = json.loads(row["params"])
            assert stored_params == orig.params

    def test_parquet_empty_specs(self, tmp_path):
        """Empty specs list produces a file with zero rows."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "empty.parquet"
        save_factor_registry([], out_path)

        df = pl.read_parquet(out_path)
        assert len(df) == 0

    def test_parquet_auto_create_parent_dir(self, sample_specs, tmp_path):
        """Auto-creates parent directories when they don't exist."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "nested" / "deep" / "registry.parquet"
        assert not out_path.parent.exists()

        save_factor_registry(sample_specs, out_path)
        assert out_path.exists()

    def test_parquet_existing_dir_no_error(self, sample_specs, tmp_path):
        """Saving into an existing directory works without error."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "existing" / "registry.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        result = save_factor_registry(sample_specs, out_path)
        assert result.exists()

    def test_parquet_params_serialized_as_json_string(self, sample_specs, tmp_path):
        """params column stores parameter dicts as JSON strings."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "with_params.parquet"
        save_factor_registry(sample_specs, out_path)

        df = pl.read_parquet(out_path)
        for row in df.iter_rows(named=True):
            params_str = row["params"]
            params_dict = json.loads(params_str)
            assert isinstance(params_dict, dict)

    def test_parquet_many_specs_count(self, many_specs, tmp_path):
        """Many specs (≥200) produces correct row count."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "many.parquet"
        save_factor_registry(many_specs, out_path)

        df = pl.read_parquet(out_path)
        assert len(df) == len(many_specs)
        assert len(df) >= 200

    def test_parquet_overwrite_existing_file(self, sample_specs, tmp_path):
        """Saving to same path twice overwrites without error."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "registry.parquet"
        p1 = save_factor_registry(sample_specs, out_path)

        import time

        time.sleep(0.01)
        p2 = save_factor_registry(sample_specs, out_path)
        assert p1 == p2

    def test_parquet_factor_has_all_fields(self, sample_specs, tmp_path):
        """Each row has non-empty id, category, template, formula fields."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = tmp_path / "registry.parquet"
        save_factor_registry(sample_specs, out_path)

        df = pl.read_parquet(out_path)
        for row in df.iter_rows(named=True):
            for field in ("id", "category", "template", "formula", "params"):
                assert row[field], f"Field '{field}' is empty for {row['id']}"


# ============================================================================
# load_factor_registry — parquet format
# ============================================================================


class TestLoadFactorRegistryParquet:
    """load_factor_registry reads parquet and returns a polars DataFrame."""

    def test_load_parquet_returns_dataframe(self, sample_specs, tmp_path):
        """Returns a polars DataFrame after save."""
        from trader_off.factor_mining.registry import (
            load_factor_registry,
            save_factor_registry,
        )

        out_path = save_factor_registry(sample_specs, tmp_path / "test.parquet")
        result = load_factor_registry(out_path)
        assert isinstance(result, pl.DataFrame)

    def test_load_parquet_has_all_specs(self, sample_specs, tmp_path):
        """After round-trip, DataFrame has one row per spec."""
        from trader_off.factor_mining.registry import (
            load_factor_registry,
            save_factor_registry,
        )

        out_path = save_factor_registry(sample_specs, tmp_path / "test.parquet")
        df = load_factor_registry(out_path)
        assert len(df) == len(sample_specs)

    def test_load_nonexistent_parquet_raises(self, tmp_path):
        """Loading a nonexistent parquet file raises FileNotFoundError."""
        from trader_off.factor_mining.registry import load_factor_registry

        missing = tmp_path / "does_not_exist.parquet"
        with pytest.raises(FileNotFoundError):
            load_factor_registry(missing)

    def test_round_trip_parquet(self, sample_specs, tmp_path):
        """Save to parquet, load back, verify all factor IDs match."""
        from trader_off.factor_mining.registry import (
            load_factor_registry,
            save_factor_registry,
        )

        out_path = save_factor_registry(sample_specs, tmp_path / "test.parquet")
        df = load_factor_registry(out_path)

        loaded_ids = set(df["id"].to_list())
        original_ids = {s.id for s in sample_specs}
        assert loaded_ids == original_ids


# ============================================================================
# FactorRegistrySchemaError — backward-compatible exception class
# ============================================================================


class TestFactorRegistrySchemaError:
    """FactorRegistrySchemaError remains as backward-compatible exception
    class (no longer raised by parquet load)."""

    def test_exception_is_subclass_of_exception(self):
        """FactorRegistrySchemaError is a subclass of Exception."""
        from trader_off.factor_mining.registry import FactorRegistrySchemaError

        assert issubclass(FactorRegistrySchemaError, Exception)

    def test_exception_message_preserved(self):
        """FactorRegistrySchemaError preserves the message string."""
        from trader_off.factor_mining.registry import FactorRegistrySchemaError

        msg = "missing required field: factor_template_version"
        exc = FactorRegistrySchemaError(msg)
        assert str(exc) == msg
        assert exc.args[0] == msg
