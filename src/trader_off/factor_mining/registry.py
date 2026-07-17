"""Factor registry persistence — save/load YAML and JSON (FR-0600).

Provides atomic write for factor registry files with schema validation on load.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]

from trader_off.factor_mining.expression import FactorSpec
from trader_off.factor_mining.templates import FACTOR_TEMPLATE_VERSION


class FactorRegistrySchemaError(ValueError):
    """Schema validation error when loading a factor registry file.

    Raised when required fields are missing or have invalid types.
    """


_REQUIRED_TOP_FIELDS: set[str] = {"factor_template_version", "factors"}
_REQUIRED_FACTOR_FIELDS: set[str] = {"id", "category", "template", "params", "formula"}


# ---------------------------------------------------------------------------
# save_factor_registry
# ---------------------------------------------------------------------------


def save_factor_registry(
    specs: list[FactorSpec],
    out_dir: Path,
    *,
    fmt: Literal["yaml", "json"] = "yaml",
) -> Path:
    """Save factor specs to a YAML or JSON registry file with atomic write.

    Creates ``out_dir`` if it does not exist (recursively). The file is first
    written to a temporary file in the same directory, then atomically renamed
    to the target path to prevent partial writes.

    Args:
        specs: FactorSpec instances to persist.
        out_dir: Output directory for the registry file.
        fmt: File format — ``"yaml"`` or ``"json"``.

    Returns:
        Path to the written registry file.

    Schema (YAML):
        ``factor_template_version``, ``generated_at`` (ISO 8601 UTC),
        ``total_candidates``, ``factors`` (list of dict with id, category,
        template, params, formula).

    Schema (JSON):
        ``factor_template_version``, ``selected_count``,
        ``selection_diagnostics``, ``factors`` (list of dict with id,
        category, icir, ic_mean, ic_std, plus extended fields).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = ".yaml" if fmt == "yaml" else ".json"
    target = out_dir / f"factors{ext}"

    generated_at = datetime.now(timezone.utc).strftime(  # noqa: UP017
        "%Y-%m-%dT%H:%M:%SZ"
    )

    if fmt == "yaml":
        payload: dict = {
            "factor_template_version": FACTOR_TEMPLATE_VERSION,
            "generated_at": generated_at,
            "total_candidates": len(specs),
            "factors": [
                {
                    "id": s.id,
                    "category": s.category,
                    "template": s.template_name,
                    "params": s.params,
                    "formula": s.formula,
                }
                for s in specs
            ],
        }
        serialized = yaml.safe_dump(
            payload, allow_unicode=True, default_flow_style=False, sort_keys=False
        )
    else:
        payload = {
            "factor_template_version": FACTOR_TEMPLATE_VERSION,
            "selected_count": len(specs),
            "selection_diagnostics": {
                "removed_by_redundancy": [],
                "final_k": len(specs),
                "top_k_requested": len(specs),
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
                for s in specs
            ],
        }
        serialized = json.dumps(payload, indent=2, ensure_ascii=False)

    # Atomic write: write to temp file in same directory, then rename.
    fd, tmp_path = tempfile.mkstemp(dir=str(out_dir), prefix=".factors_", suffix=ext)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
        os.replace(tmp_path, target)
    except BaseException:
        # Clean up temp file on any error
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return target


# ---------------------------------------------------------------------------
# load_factor_registry
# ---------------------------------------------------------------------------


def load_factor_registry(path: Path) -> dict:
    """Load a factor registry file with schema validation.

    Supports both YAML (``.yaml`` / ``.yml``) and JSON (``.json``) formats.
    Auto-detects format from file extension.

    Args:
        path: Path to the registry file (``factors.yaml`` or ``factors.json``).

    Returns:
        Parsed registry as a dict. Contains top-level fields
        ``factor_template_version``, ``factors``, and format-specific fields
        (``generated_at``, ``total_candidates`` for YAML;
        ``selected_count``, ``selection_diagnostics`` for JSON).

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        FactorRegistrySchemaError: If schema validation fails (missing
            required fields, wrong types).
        yaml.YAMLError: If the YAML file is malformed.
        json.JSONDecodeError: If the JSON file is malformed.
    """
    if not path.exists():
        raise FileNotFoundError(f"Registry file not found: {path}")

    suffix = path.suffix.lower()

    try:
        with open(path, encoding="utf-8") as f:
            if suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            elif suffix == ".json":
                data = json.load(f)
            else:
                raise FactorRegistrySchemaError(
                    f"Unsupported file format: {suffix}. Expected .yaml, .yml, or .json"
                )
    except (yaml.YAMLError, json.JSONDecodeError):
        raise
    except FactorRegistrySchemaError:
        raise

    # Validate root type
    if not isinstance(data, dict):
        raise FactorRegistrySchemaError(f"Registry root must be a dict, got {type(data).__name__}")

    # Validate required top-level fields
    missing_top = _REQUIRED_TOP_FIELDS - set(data.keys())
    if missing_top:
        raise FactorRegistrySchemaError(f"missing required field: {sorted(missing_top)[0]}")

    # Validate factors field
    factors = data["factors"]
    if not isinstance(factors, list):
        raise FactorRegistrySchemaError(f"'factors' must be a list, got {type(factors).__name__}")

    # Validate each factor entry
    for i, factor in enumerate(factors):
        if not isinstance(factor, dict):
            raise FactorRegistrySchemaError(
                f"factors[{i}] must be a dict, got {type(factor).__name__}"
            )
        missing_factor = _REQUIRED_FACTOR_FIELDS - set(factor.keys())
        if missing_factor:
            raise FactorRegistrySchemaError(
                f"factors[{i}] missing required field: {sorted(missing_factor)[0]}"
            )

    return data
