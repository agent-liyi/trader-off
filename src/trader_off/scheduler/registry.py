"""Model version management and retention policy (FR-2300).

Provides ModelRegistry for tracking model versions, performing garbage
collection based on retention policy, and rollback to prior versions.

Supports both v0.2.0 (v{major}.{minor}.{build}[.incr{N}]) and v0.1.0
(YYYYMMDD_HHMMSS) version formats.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------

# v0.1.0 timestamp: YYYYMMDD_HHMMSS (e.g., 20260715_120000)
_RE_V010 = re.compile(r"^\d{8}_\d{6}$")

# v0.2.0 semver-ish: v{major}.{minor}.{build}[.incr{N}]
# Examples: v0.2.0, v0.2.0.5, v0.2.0.5.incr1
_RE_V020 = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\.(\d+)(?:\.incr(\d+))?$")

# Fallback for v{major}.{minor}.{build} (3 parts, e.g., v0.2.0)
_RE_V020_SHORT = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _parse_version_key(version: str) -> tuple:
    """Parse a version string into a comparable key tuple.

    v0.1.0 timestamps sort before v0.2.0 semver versions. Within each
    format, versions are ordered naturally.

    Args:
        version: Version string in either v0.1.0 or v0.2.0 format.

    Returns:
        A tuple suitable for sorting. v0.1.0 formats get prefix 0;
        v0.2.0 formats get prefix 1, followed by their numeric parts.
    """
    if _RE_V010.match(version):
        # Parse as datetime for correct ordering
        try:
            dt = datetime.strptime(version, "%Y%m%d_%H%M%S")
            return (0, dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
        except ValueError:
            # Fallback: treat as plain string comparison
            return (0, version)

    m = _RE_V020.match(version)
    if m:
        parts = [int(g) for g in m.groups() if g is not None]
        return (1, *parts)

    m = _RE_V020_SHORT.match(version)
    if m:
        parts = [int(g) for g in m.groups()]
        return (1, *parts)

    # Unknown format: fall back to string ordering with prefix 2
    logger.warning(f"Unknown version format: {version!r}, using string ordering")
    return (2, version)


def _is_model_version_dir(name: str) -> bool:
    """Check if a directory name looks like a model version."""
    return bool(_RE_V010.match(name) or _RE_V020.match(name) or _RE_V020_SHORT.match(name))


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------


class ModelRegistry:
    """Manages model versions, retention, GC, and rollback.

    Persists state to a JSON registry file (registry.json) that contains
    an array of version entries plus metadata (current_version,
    pinned_versions, schema_version).

    Attributes:
        registry_path: Path to the registry.json file.
        models_dir: Root directory containing model version subdirectories.
        keep_latest_n: Number of latest versions to retain during GC.
        keep_pinned_versions: Versions that are exempt from deletion.
        keep_full_retrain_only: If True, only full-retrain versions count
            toward keep_latest_n; all incremental versions are deleted.
    """

    def __init__(
        self,
        registry_path: Path,
        models_dir: Path,
        *,
        keep_latest_n: int = 10,
        keep_pinned_versions: list[str] | None = None,
        keep_full_retrain_only: bool = True,
    ) -> None:
        self.registry_path = Path(registry_path)
        self.models_dir = Path(models_dir)
        self.keep_latest_n = keep_latest_n
        self.keep_pinned_versions: list[str] = list(keep_pinned_versions or [])
        self.keep_full_retrain_only = keep_full_retrain_only

        # Ensure models_dir exists
        self.models_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal: load / save
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Load the registry JSON, returning the full data dict.

        Returns an empty registry structure if the file does not exist.
        """
        if not self.registry_path.exists():
            return {
                "entries": [],
                "current_version": None,
                "pinned_versions": [],
                "schema_version": 2,
            }
        return json.loads(self.registry_path.read_text())

    def _save(self, data: dict) -> None:
        """Atomically write the registry data to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.registry_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_versions(self) -> list[str]:
        """Return all version strings sorted from oldest to newest.

        Both v0.1.0 (YYYYMMDD_HHMMSS) and v0.2.0 (v{major}.{minor}.{build})
        formats are supported. v0.1.0 timestamps sort before v0.2.0 versions.

        Returns:
            Sorted list of version strings.
        """
        data = self._load()
        versions = [e["version"] for e in data["entries"]]
        versions.sort(key=_parse_version_key)
        return versions

    def current(self) -> str | None:
        """Return the currently active (deployed) version, or None.

        Returns:
            The current version string, or None if no version is deployed.
        """
        data = self._load()
        return data.get("current_version")

    def get_entry(self, version: str) -> dict | None:
        """Return the registry entry for a specific version.

        Args:
            version: Version string to look up.

        Returns:
            The entry dict if found, None otherwise.
        """
        data = self._load()
        for entry in data["entries"]:
            if entry.get("version") == version:
                return entry
        return None

    def append(self, entry: dict) -> None:
        """Add a new version entry to the registry.

        Args:
            entry: A dict containing at least 'version', 'mode', etc.
        """
        data = self._load()
        data["entries"].append(entry)
        self._save(data)

    def rollback_to(self, version: str) -> None:
        """Set the current (deployed) version to a prior version.

        Args:
            version: Target version to roll back to.

        Raises:
            ValueError: If the target version is not found in the registry.
        """
        data = self._load()
        existing = {e["version"] for e in data["entries"]}
        if version not in existing:
            raise ValueError(f"Version {version!r} not found in registry, cannot rollback")
        data["current_version"] = version
        self._save(data)
        logger.info(f"Rolled back current version to {version}")

    def gc(self) -> list[str]:
        """Perform garbage collection based on retention policy.

        Deletes model version directories that exceed keep_latest_n
        (respecting pinned versions and keep_full_retrain_only).
        Also removes orphan directories that look like model versions
        but are not in the registry.

        The current version is never deleted, even if it would otherwise
        fall outside the retention window.

        Returns:
            List of deleted version strings.
        """
        data = self._load()
        entries: list[dict] = data["entries"]
        if not entries:
            logger.info("GC: registry is empty, nothing to clean")
            return []

        current_version: str | None = data.get("current_version")
        pinned: set[str] = set(data.get("pinned_versions") or []) | set(self.keep_pinned_versions)

        indexed = self._index_entries(entries)
        keep_set = self._compute_keep_set(indexed, current_version, pinned)
        to_delete = self._collect_versions_to_delete(indexed, keep_set, entries)
        deleted = self._delete_version_dirs(to_delete)

        # Update registry: remove deleted entries, persist
        entries_kept = [e for e in entries if e["version"] not in to_delete]
        data["entries"] = entries_kept
        self._save(data)

        logger.info(f"GC complete: deleted {len(deleted)} versions, {len(entries_kept)} remaining")
        return deleted

    # ------------------------------------------------------------------
    # GC helpers
    # ------------------------------------------------------------------

    def _index_entries(self, entries: list[dict]) -> list[tuple[tuple, dict]]:
        """Sort registry entries from oldest to newest by version key."""
        indexed = [(_parse_version_key(e["version"]), e) for e in entries]
        indexed.sort(key=lambda x: x[0])
        return indexed

    def _compute_keep_set(
        self,
        indexed: list[tuple[tuple, dict]],
        current_version: str | None,
        pinned: set[str],
    ) -> set[str]:
        """Compute the set of version strings that should survive GC."""
        if self.keep_full_retrain_only:
            full_entries = [(k, e) for k, e in indexed if e.get("mode") == "full"]
            keep_count = min(self.keep_latest_n, len(full_entries))
            keep_set = {e["version"] for _, e in full_entries[-keep_count:]}
        else:
            keep_count = min(self.keep_latest_n, len(indexed))
            keep_set = {e["version"] for _, e in indexed[-keep_count:]}

        if current_version:
            keep_set.add(current_version)
        keep_set |= pinned
        return keep_set

    def _collect_versions_to_delete(
        self,
        indexed: list[tuple[tuple, dict]],
        keep_set: set[str],
        entries: list[dict],
    ) -> set[str]:
        """Collect versions to delete (registry entries + orphan dirs)."""
        to_delete: set[str] = set()
        for _, entry in indexed:
            v = entry["version"]
            if v not in keep_set:
                if self.keep_full_retrain_only or entry.get("mode") != "full":
                    to_delete.add(v)

        # Find orphan directories (exist on disk but not in registry)
        registry_versions = {e["version"] for e in entries}
        if self.models_dir.exists():
            for d in self.models_dir.iterdir():
                if d.is_dir() and _is_model_version_dir(d.name) and d.name not in registry_versions:
                    to_delete.add(d.name)

        return to_delete

    def _delete_version_dirs(self, to_delete: set[str]) -> list[str]:
        """Delete version directories from disk. Returns list of successfully deleted names."""
        deleted: list[str] = []
        for v in sorted(to_delete, key=_parse_version_key):
            model_dir = self.models_dir / v
            if model_dir.exists():
                try:
                    shutil.rmtree(model_dir)
                    deleted.append(v)
                    logger.info(f"GC: deleted model version {v}")
                except OSError as exc:
                    logger.error(f"GC: failed to delete {v}: {exc}")
        return deleted
