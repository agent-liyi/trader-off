"""Factor registry persistence — save/load parquet (FR-0600).

Provides parquet-based save/load for factor registry files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from trader_off.factor_mining.expression import FactorSpec
from trader_off.factor_mining.templates import FACTOR_TEMPLATE_VERSION


class FactorRegistrySchemaError(ValueError):
    """Schema validation error when loading a factor registry file.

    Raised when required fields are missing or have invalid types.

    Note: In the parquet-based implementation, this is kept for backward
    compatibility; current parquet format does not need schema validation.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _spec_to_base_dict(spec: FactorSpec) -> dict:
    """Convert a FactorSpec to a serializable dict with common fields."""
    return {
        "id": spec.id,
        "category": spec.category,
        "template": spec.template_name,
        "params": spec.params,
        "formula": spec.formula,
    }


# ---------------------------------------------------------------------------
# save_factor_registry
# ---------------------------------------------------------------------------


def save_factor_registry(
    specs: list[FactorSpec],
    out_path: Path,
) -> Path:
    """Save factor specs to a single parquet registry file.

    Creates the parent directory of ``out_path`` if it does not exist
    (recursively). The parquet file contains one row per FactorSpec with
    columns: id, category, template, params (JSON string), formula,
    factor_template_version, generated_at.

    Args:
        specs: FactorSpec instances to persist.
        out_path: Output file path for the parquet file (e.g.
            ``factor_registry/registry.parquet``).

    Returns:
        The ``out_path`` of the written file.

    Raises:
        OSError: If the file system operations fail.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).strftime(  # noqa: UP017
        "%Y-%m-%dT%H:%M:%SZ"
    )

    if not specs:
        df = pl.DataFrame(
            schema={
                "id": pl.Utf8,
                "category": pl.Utf8,
                "template": pl.Utf8,
                "params": pl.Utf8,
                "formula": pl.Utf8,
                "factor_template_version": pl.Utf8,
                "generated_at": pl.Utf8,
            }
        )
    else:
        rows = []
        for spec in specs:
            base = _spec_to_base_dict(spec)
            base["params"] = json.dumps(base["params"])
            base["factor_template_version"] = FACTOR_TEMPLATE_VERSION
            base["generated_at"] = generated_at
            rows.append(base)
        df = pl.DataFrame(rows)

    df.write_parquet(out_path)
    return out_path


# ---------------------------------------------------------------------------
# load_factor_registry
# ---------------------------------------------------------------------------


def load_factor_registry(path: Path) -> pl.DataFrame:
    """Load a factor registry parquet file.

    Args:
        path: Path to the registry parquet file (e.g.
            ``factor_registry/registry.parquet``).

    Returns:
        A polars DataFrame with one row per factor spec. Columns include
        id, category, template, params (JSON string), formula,
        factor_template_version, generated_at.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    return pl.read_parquet(path)
