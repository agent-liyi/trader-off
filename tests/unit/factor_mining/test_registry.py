"""Unit tests for factor registry persistence — save/load YAML/JSON (FR-0600).

Covers:
    AC-FR0600-01: save YAML factor registry with correct schema fields.
    AC-FR0600-02: save JSON factor registry with correct schema fields.
    AC-FR0600-03: auto-create output directory when missing.
    AC-FR0600-04: schema validation on load — missing required field raises
        FactorRegistrySchemaError.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
import yaml  # type: ignore[import-untyped]

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
    """A larger set (≥200) for AC-FR0600-01 total_candidates check."""
    return enumerate_factors()


# ---------------------------------------------------------------------------
# AC-FR0600-01: YAML format — schema fields and data integrity
# ---------------------------------------------------------------------------


class TestSaveFactorRegistryYAML:
    """AC-FR0600-01: save_factor_registry(fmt="yaml") writes a valid YAML file
    with factor_template_version, generated_at, total_candidates, and factors
    where len(factors) == total_candidates.
    """

    def test_ac_fr0600_01_yaml_file_exists(self, sample_specs, tmp_path):
        """AC-FR0600-01: Save with fmt="yaml" produces an existing file."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        assert out_path.exists(), f"Expected {out_path} to exist"
        assert out_path.suffix == ".yaml", f"Expected .yaml suffix, got {out_path.suffix}"

    def test_ac_fr0600_01_yaml_top_level_fields(self, sample_specs, tmp_path):
        """AC-FR0600-01: YAML file contains factor_template_version, generated_at,
        total_candidates, factors at top level."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        with open(out_path) as f:
            data = yaml.safe_load(f)

        assert "factor_template_version" in data, "Missing factor_template_version"
        assert data["factor_template_version"] == FACTOR_TEMPLATE_VERSION
        assert "generated_at" in data, "Missing generated_at"
        assert "total_candidates" in data, "Missing total_candidates"
        assert "factors" in data, "Missing factors"

    def test_ac_fr0600_01_total_candidates_matches_factors_len(self, many_specs, tmp_path):
        """AC-FR0600-01: total_candidates equals len(factors) and both ≥200."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(many_specs, tmp_path, fmt="yaml")
        with open(out_path) as f:
            data = yaml.safe_load(f)

        assert data["total_candidates"] >= 200, (
            f"Expected ≥200 candidates, got {data['total_candidates']}"
        )
        assert data["total_candidates"] == len(data["factors"]), (
            f"total_candidates ({data['total_candidates']}) != len(factors) "
            f"({len(data['factors'])})"
        )

    def test_ac_fr0600_01_yaml_factor_entry_fields(self, sample_specs, tmp_path):
        """AC-FR0600-01: Each factor entry has id, category, template, params, formula."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        with open(out_path) as f:
            data = yaml.safe_load(f)

        for factor in data["factors"]:
            for field in ("id", "category", "template", "params", "formula"):
                assert field in factor, f"Factor entry missing field: {field}"

    def test_ac_fr0600_01_yaml_generated_at_is_iso8601_utc(self, sample_specs, tmp_path):
        """AC-FR0600-01: generated_at is an ISO 8601 UTC timestamp string."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        with open(out_path) as f:
            data = yaml.safe_load(f)

        ts = data["generated_at"]
        assert isinstance(ts, str), f"generated_at must be str, got {type(ts)}"
        # Should be parseable as ISO 8601 UTC
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None, "generated_at must be timezone-aware"

    def test_ac_fr0600_01_yaml_round_trip_integrity(self, sample_specs, tmp_path):
        """AC-FR0600-01: After save + load, factor IDs and params are preserved."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        with open(out_path) as f:
            data = yaml.safe_load(f)

        saved_ids = {f["id"] for f in data["factors"]}
        original_ids = {s.id for s in sample_specs}
        assert saved_ids == original_ids, f"Mismatch: saved={saved_ids}, original={original_ids}"

        # Spot-check params
        for factor in data["factors"]:
            orig = next(s for s in sample_specs if s.id == factor["id"])
            assert factor["params"] == orig.params, (
                f"Params mismatch for {factor['id']}: "
                f"saved={factor['params']}, original={orig.params}"
            )


# ---------------------------------------------------------------------------
# AC-FR0600-02: JSON format — schema fields
# ---------------------------------------------------------------------------


class TestSaveFactorRegistryJSON:
    """AC-FR0600-02: save_factor_registry(fmt="json") writes a valid JSON file
    with selected_count, selection_diagnostics, and factors where each factor
    has id, category, icir, ic_mean, ic_std.
    """

    def test_ac_fr0600_02_json_file_exists(self, sample_specs, tmp_path):
        """AC-FR0600-02: Save with fmt="json" produces an existing file."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="json")
        assert out_path.exists(), f"Expected {out_path} to exist"
        assert out_path.suffix == ".json", f"Expected .json suffix, got {out_path.suffix}"

    def test_ac_fr0600_02_json_top_level_fields(self, sample_specs, tmp_path):
        """AC-FR0600-02: JSON contains factor_template_version, selected_count,
        selection_diagnostics, and factors."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="json")
        with open(out_path) as f:
            data = json.load(f)

        assert "factor_template_version" in data, "Missing factor_template_version"
        assert data["factor_template_version"] == FACTOR_TEMPLATE_VERSION
        assert "selected_count" in data, "Missing selected_count"
        assert "selection_diagnostics" in data, "Missing selection_diagnostics"
        assert "factors" in data, "Missing factors"

    def test_ac_fr0600_02_selected_count_matches_factors_len(self, sample_specs, tmp_path):
        """AC-FR0600-02: selected_count equals len(factors)."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="json")
        with open(out_path) as f:
            data = json.load(f)

        assert data["selected_count"] == len(data["factors"]), (
            f"selected_count ({data['selected_count']}) != len(factors) ({len(data['factors'])})"
        )

    def test_ac_fr0600_02_json_factor_has_ic_fields(self, sample_specs, tmp_path):
        """AC-FR0600-02: Each factor in JSON has id, category plus icir, ic_mean, ic_std."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="json")
        with open(out_path) as f:
            data = json.load(f)

        for factor in data["factors"]:
            for field in ("id", "category", "icir", "ic_mean", "ic_std"):
                assert field in factor, f"JSON factor entry missing field: {field}"


# ---------------------------------------------------------------------------
# AC-FR0600-03: Auto-create output directory
# ---------------------------------------------------------------------------


class TestSaveFactorRegistryAutoCreateDir:
    """AC-FR0600-03: When out_dir does not exist, it is auto-created."""

    def test_ac_fr0600_03_auto_create_dir_yaml(self, sample_specs, tmp_path):
        """AC-FR0600-03: Non-existent out_dir is created for YAML save."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_dir = tmp_path / "nested" / "deep" / "factor_registry"
        assert not out_dir.exists(), "Test precondition: out_dir must not exist"

        out_path = save_factor_registry(sample_specs, out_dir, fmt="yaml")
        assert out_dir.exists(), f"Expected {out_dir} to be auto-created"
        assert out_path.exists(), f"Expected {out_path} to exist"

    def test_ac_fr0600_03_auto_create_dir_json(self, sample_specs, tmp_path):
        """AC-FR0600-03: Non-existent out_dir is created for JSON save."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_dir = tmp_path / "registry_json" / "subdir"
        assert not out_dir.exists(), "Test precondition: out_dir must not exist"

        out_path = save_factor_registry(sample_specs, out_dir, fmt="json")
        assert out_dir.exists(), f"Expected {out_dir} to be auto-created"
        assert out_path.exists(), f"Expected {out_path} to exist"

    def test_ac_fr0600_03_existing_dir_no_error(self, sample_specs, tmp_path):
        """AC-FR0600-03: Saving into an existing directory works without error."""
        from trader_off.factor_mining.registry import save_factor_registry

        # Pre-create directory
        out_dir = tmp_path / "existing_dir"
        out_dir.mkdir(parents=True, exist_ok=True)
        assert out_dir.exists()

        out_path = save_factor_registry(sample_specs, out_dir, fmt="yaml")
        assert out_path.exists()


# ---------------------------------------------------------------------------
# AC-FR0600-04: Schema validation on load
# ---------------------------------------------------------------------------


class TestLoadFactorRegistrySchemaValidation:
    """AC-FR0600-04: load_factor_registry validates required fields and
    raises FactorRegistrySchemaError on missing factor_template_version."""

    def test_ac_fr0600_04_missing_factor_template_version(self, tmp_path):
        """AC-FR0600-04: Loading a factors.yaml with missing
        factor_template_version raises FactorRegistrySchemaError."""
        from trader_off.factor_mining.registry import (
            FactorRegistrySchemaError,
            load_factor_registry,
        )

        # Write a yaml file manually missing the required field
        bad_yaml = tmp_path / "bad_factors.yaml"
        bad_yaml.write_text(yaml.dump({"total_candidates": 10, "factors": [{"id": "test"}]}))

        with pytest.raises(FactorRegistrySchemaError, match="factor_template_version"):
            load_factor_registry(bad_yaml)

    def test_ac_fr0600_04_missing_factors_field(self, tmp_path):
        """AC-FR0600-04: Loading a YAML file with missing 'factors' field
        raises FactorRegistrySchemaError."""
        from trader_off.factor_mining.registry import (
            FactorRegistrySchemaError,
            load_factor_registry,
        )

        bad_yaml = tmp_path / "no_factors.yaml"
        bad_yaml.write_text(
            yaml.dump(
                {
                    "factor_template_version": "v1",
                    "generated_at": "2026-07-17T10:00:00Z",
                    "total_candidates": 0,
                }
            )
        )

        with pytest.raises(FactorRegistrySchemaError, match="factors"):
            load_factor_registry(bad_yaml)

    def test_ac_fr0600_04_valid_file_loads_successfully(self, sample_specs, tmp_path):
        """AC-FR0600-04: A valid file loads without error and returns the dict."""
        from trader_off.factor_mining.registry import (
            load_factor_registry,
            save_factor_registry,
        )

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        data = load_factor_registry(out_path)

        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert data["total_candidates"] == len(sample_specs)
        assert len(data["factors"]) == len(sample_specs)

    def test_ac_fr0600_04_load_nonexistent_file(self, tmp_path):
        """AC-FR0600-04: Loading a non-existent file raises FileNotFoundError."""
        from trader_off.factor_mining.registry import load_factor_registry

        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError):
            load_factor_registry(missing)

    def test_ac_fr0600_04_load_invalid_yaml(self, tmp_path):
        """AC-FR0600-04: Loading a malformed YAML file raises yaml.YAMLError."""
        from trader_off.factor_mining.registry import load_factor_registry

        invalid = tmp_path / "invalid.yaml"
        invalid.write_text(": bad: yaml: :::")

        with pytest.raises((yaml.YAMLError, ValueError)):
            load_factor_registry(invalid)

    def test_ac_fr0600_04_load_non_dict_root(self, tmp_path):
        """AC-FR0600-04: Loading a YAML file whose root is not a dict
        raises FactorRegistrySchemaError."""
        from trader_off.factor_mining.registry import (
            FactorRegistrySchemaError,
            load_factor_registry,
        )

        list_yaml = tmp_path / "list.yaml"
        list_yaml.write_text(yaml.dump([1, 2, 3]))

        with pytest.raises(FactorRegistrySchemaError):
            load_factor_registry(list_yaml)

    def test_ac_fr0600_04_load_json_missing_required_field(self, tmp_path):
        """AC-FR0600-04: Loading a JSON file missing required fields
        raises FactorRegistrySchemaError."""
        from trader_off.factor_mining.registry import (
            FactorRegistrySchemaError,
            load_factor_registry,
        )

        bad_json = tmp_path / "bad_factors.json"
        bad_json.write_text(json.dumps({"factors": []}))

        with pytest.raises(FactorRegistrySchemaError):
            load_factor_registry(bad_json)


# ---------------------------------------------------------------------------
# Atomic write — prevent partial files
# ---------------------------------------------------------------------------


class TestSaveFactorRegistryAtomicWrite:
    """Atomic write: file is written to temp then renamed, preventing
    partial or corrupted output files."""

    def test_atomic_write_does_not_leave_temp_file(self, sample_specs, tmp_path):
        """After a successful save, no .tmp or .partial files remain in out_dir."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")

        # No temporary files left behind
        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 1, f"Expected only 1 file, found {len(remaining)}: {remaining}"
        assert remaining[0] == out_path

    def test_atomic_write_produces_valid_file(self, sample_specs, tmp_path):
        """After atomic write, the output file is immediately valid and parseable."""
        from trader_off.factor_mining.registry import save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="json")
        assert out_path.stat().st_size > 0, "File must be non-empty"

        with open(out_path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert len(data["factors"]) == len(sample_specs)


# ---------------------------------------------------------------------------
# Edge cases and round-trips
# ---------------------------------------------------------------------------


class TestLoadFactorRegistryRoundTrip:
    """Round-trip: save → load → verify data integrity."""

    def test_round_trip_yaml(self, sample_specs, tmp_path):
        """Save to YAML, load back, verify all factor IDs match."""
        from trader_off.factor_mining.registry import load_factor_registry, save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        data = load_factor_registry(out_path)

        loaded_ids = {f["id"] for f in data["factors"]}
        original_ids = {s.id for s in sample_specs}
        assert loaded_ids == original_ids

    def test_round_trip_json(self, sample_specs, tmp_path):
        """Save to JSON, load back, verify all factor IDs match."""
        from trader_off.factor_mining.registry import load_factor_registry, save_factor_registry

        out_path = save_factor_registry(sample_specs, tmp_path, fmt="json")
        data = load_factor_registry(out_path)

        loaded_ids = {f["id"] for f in data["factors"]}
        original_ids = {s.id for s in sample_specs}
        assert loaded_ids == original_ids

    def test_empty_specs_list(self, tmp_path):
        """Saving an empty specs list produces a file with total_candidates=0."""
        from trader_off.factor_mining.registry import load_factor_registry, save_factor_registry

        out_path = save_factor_registry([], tmp_path, fmt="yaml")
        data = load_factor_registry(out_path)

        assert data["total_candidates"] == 0
        assert data["factors"] == []

    def test_overwrite_existing_file(self, sample_specs, tmp_path):
        """Saving to same path twice overwrites without error."""
        from trader_off.factor_mining.registry import save_factor_registry

        p1 = save_factor_registry(sample_specs, tmp_path, fmt="yaml")
        original_mtime = p1.stat().st_mtime

        import time

        time.sleep(0.01)  # ensure mtime differences on fast filesystems
        p2 = save_factor_registry(sample_specs, tmp_path, fmt="yaml")

        assert p1 == p2, "Second save should use the same path"
        assert p2.stat().st_mtime >= original_mtime, "File should be updated"


# ---------------------------------------------------------------------------
# FactorRegistrySchemaError
# ---------------------------------------------------------------------------


class TestFactorRegistrySchemaError:
    """FactorRegistrySchemaError is a proper exception class."""

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
