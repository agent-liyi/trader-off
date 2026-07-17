"""Unit tests for ModelRegistry — FR-2300 model version management and retention policy.

AC coverage:
- AC-FR2300-01: GC with keep_latest_n
- AC-FR2300-02: Pinned versions survive GC
- AC-FR2300-03: keep_full_retrain_only
- AC-FR2300-04: rollback_to updates current_version
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trader_off.scheduler.registry import ModelRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    version: str,
    *,
    mode: str = "full",
    incr_seq: int | None = None,
    parent_version: str | None = None,
) -> dict:
    """Create a minimal registry entry dict for test setup."""
    return {
        "version": version,
        "created_at": datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC).isoformat(),
        "trigger": "manual" if mode == "incremental" else "cron_full",
        "mode": mode,
        "task_id": f"T-{version}",
        "git_commit_sha": "abc1234567",
        "metrics": {"test_ic_mean": 0.02, "test_rank_ic_mean": 0.03},
        "parent_version": parent_version,
        "incr_seq": incr_seq,
        "refit_iterations": 50 if mode == "incremental" else None,
    }


def _write_registry(
    path: Path,
    entries: list[dict],
    *,
    current_version: str | None = None,
    pinned_versions: list[str] | None = None,
) -> None:
    """Write a registry.json file to disk."""
    data: dict = {
        "entries": entries,
        "current_version": current_version,
        "pinned_versions": pinned_versions or [],
        "schema_version": 2,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _make_model_dir(models_dir: Path, version: str) -> Path:
    """Create a minimal model directory for a version."""
    d = models_dir / version
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.pkl").touch()
    (d / "metadata.json").touch()
    return d


# ---------------------------------------------------------------------------
# AC-FR2300-01: GC with keep_latest_n
# ---------------------------------------------------------------------------


class TestGcKeepLatest:
    """AC-FR2300-01: keep_latest_n=10, oldest 2 of 12 deleted."""

    def test_gc_deletes_oldest_beyond_keep_n(self, tmp_path: Path):
        """AC-FR2300-01: 12 versions, keep_latest_n=10 → 2 oldest deleted."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        for i in range(1, 13):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v))
            _make_model_dir(models_dir, v)

        _write_registry(registry_path, entries, current_version="v0.2.0.12")

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=10)
        deleted = reg.gc()

        assert len(deleted) == 2
        assert "v0.2.0.1" in deleted
        assert "v0.2.0.2" in deleted
        for i in range(3, 13):
            assert (models_dir / f"v0.2.0.{i}").exists(), f"v0.2.0.{i} should exist"
        assert not (models_dir / "v0.2.0.1").exists()
        assert not (models_dir / "v0.2.0.2").exists()

    def test_gc_keeps_all_when_under_limit(self, tmp_path: Path):
        """GC does nothing when version count <= keep_latest_n."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        for i in range(1, 6):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v))
            _make_model_dir(models_dir, v)

        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=10)
        deleted = reg.gc()

        assert deleted == []
        for i in range(1, 6):
            assert (models_dir / f"v0.2.0.{i}").exists()

    def test_gc_preserves_registry_integrity_after_delete(self, tmp_path: Path):
        """Registry file is updated after GC, removed entries are gone."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        for i in range(1, 13):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v))
            _make_model_dir(models_dir, v)

        _write_registry(registry_path, entries, current_version="v0.2.0.12")

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=10)
        reg.gc()

        # Re-read registry from disk
        data = json.loads(registry_path.read_text())
        remaining = [e["version"] for e in data["entries"]]
        assert len(remaining) == 10
        assert "v0.2.0.1" not in remaining
        assert "v0.2.0.2" not in remaining

    def test_gc_never_deletes_current_version_even_if_beyond_limit(self, tmp_path: Path):
        """AC-FR2300 constraint: GC must never delete the current version."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        for i in range(1, 12):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v))
            _make_model_dir(models_dir, v)

        # v0.2.0.1 is current, but keep_latest_n=3 would normally delete it
        _write_registry(registry_path, entries, current_version="v0.2.0.1")

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=3)
        deleted = reg.gc()

        assert "v0.2.0.1" not in deleted
        assert (models_dir / "v0.2.0.1").exists(), "current version must survive GC"


# ---------------------------------------------------------------------------
# AC-FR2300-02: Pinned versions
# ---------------------------------------------------------------------------


class TestGcPinnedVersions:
    """AC-FR2300-02: Pinned versions survive GC even if beyond keep_latest_n."""

    def test_pinned_version_not_deleted(self, tmp_path: Path):
        """AC-FR2300-02: v0.2.0.5 pinned and not in latest 10 → survives GC."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        for i in range(1, 13):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v))
            _make_model_dir(models_dir, v)
        # Mark v0.2.0.5 as pinned (it's the 5th oldest, not in latest 10 if sorted
        # from oldest to newest... wait. v0.2.0.5 is actually v0.2.0.5 which is
        # among the oldest when there are 12 versions v0.2.0.1 .. v0.2.0.12.
        # With keep_latest_n=10, v0.2.0.1 and v0.2.0.2 would be deleted.
        # v0.2.0.5 is within the latest 10. Let me make it not in latest 10.

        # Use keep_latest_n=3 so that v0.2.0.1 through v0.2.0.9 are beyond limit
        _write_registry(
            registry_path,
            entries,
            current_version="v0.2.0.12",
            pinned_versions=["v0.2.0.3"],
        )

        reg = ModelRegistry(
            registry_path,
            models_dir,
            keep_latest_n=3,
            keep_pinned_versions=["v0.2.0.3"],
        )
        deleted = reg.gc()

        assert "v0.2.0.3" not in deleted
        assert (models_dir / "v0.2.0.3").exists()
        # v0.2.0.1 and v0.2.0.2 should be deleted (not pinned)
        assert not (models_dir / "v0.2.0.1").exists()

    def test_multiple_pinned_versions_all_survive(self, tmp_path: Path):
        """Multiple pinned versions all survive GC."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        for i in range(1, 13):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v))
            _make_model_dir(models_dir, v)

        _write_registry(
            registry_path,
            entries,
            current_version="v0.2.0.12",
            pinned_versions=["v0.2.0.2", "v0.2.0.4", "v0.2.0.6"],
        )

        reg = ModelRegistry(
            registry_path,
            models_dir,
            keep_latest_n=3,
            keep_pinned_versions=["v0.2.0.2", "v0.2.0.4", "v0.2.0.6"],
        )
        deleted = reg.gc()

        for pinned in ["v0.2.0.2", "v0.2.0.4", "v0.2.0.6"]:
            assert pinned not in deleted, f"pinned {pinned} should not be deleted"
            assert (models_dir / pinned).exists()


# ---------------------------------------------------------------------------
# AC-FR2300-03: keep_full_retrain_only
# ---------------------------------------------------------------------------


class TestGcFullRetrainOnly:
    """AC-FR2300-03: When keep_full_retrain_only=True, only count full versions."""

    def test_incremental_versions_deleted_with_full_only(self, tmp_path: Path):
        """AC-FR2300-03: 5 full + 8 incremental, keep_latest_n=10 → all incremental deleted."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        # 5 full versions
        for i in range(1, 6):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v, mode="full"))
            _make_model_dir(models_dir, v)
        # 8 incremental versions
        for i in range(1, 9):
            v = f"v0.2.0.1.incr{i}"
            entries.append(
                _make_entry(v, mode="incremental", incr_seq=i, parent_version="v0.2.0.1")
            )
            _make_model_dir(models_dir, v)

        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        reg = ModelRegistry(
            registry_path,
            models_dir,
            keep_latest_n=10,
            keep_full_retrain_only=True,
        )
        deleted = reg.gc()

        # All incremental should be deleted (8 of them)
        incr_deleted = [d for d in deleted if "incr" in d]
        assert len(incr_deleted) == 8
        # Only 5 full versions, all should survive since 5 <= 10
        full_survivors = [
            d.name for d in models_dir.iterdir() if d.is_dir() and "incr" not in d.name
        ]
        assert len(full_survivors) == 5

    def test_full_only_keeps_only_full_within_limit(self, tmp_path: Path):
        """Full versions beyond keep_latest_n are still deleted even with full_only."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = []
        for i in range(1, 16):
            v = f"v0.2.0.{i}"
            entries.append(_make_entry(v, mode="full"))
            _make_model_dir(models_dir, v)

        _write_registry(registry_path, entries, current_version="v0.2.0.15")

        reg = ModelRegistry(
            registry_path,
            models_dir,
            keep_latest_n=5,
            keep_full_retrain_only=True,
        )
        deleted = reg.gc()

        assert len(deleted) == 10
        # 15 full, keep 5 → delete 10
        for i in range(1, 11):
            assert f"v0.2.0.{i}" in deleted
        for i in range(11, 16):
            assert (models_dir / f"v0.2.0.{i}").exists()

    def test_full_only_with_mixed_does_not_count_incremental(self, tmp_path: Path):
        """With keep_latest_n=3, 2 full + 5 incremental → only 2 full kept, all incr deleted."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [
            _make_entry("v0.2.0.1", mode="full"),
            _make_entry("v0.2.0.2", mode="full"),
        ]
        _make_model_dir(models_dir, "v0.2.0.1")
        _make_model_dir(models_dir, "v0.2.0.2")
        for i in range(1, 6):
            v = f"v0.2.0.1.incr{i}"
            entries.append(
                _make_entry(v, mode="incremental", incr_seq=i, parent_version="v0.2.0.1")
            )
            _make_model_dir(models_dir, v)

        _write_registry(registry_path, entries, current_version="v0.2.0.2")

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=3, keep_full_retrain_only=True)
        deleted = reg.gc()

        incr_deleted = [d for d in deleted if "incr" in d]
        assert len(incr_deleted) == 5
        # Both full survive (2 <= 3)
        assert "v0.2.0.1" not in deleted
        assert "v0.2.0.2" not in deleted


# ---------------------------------------------------------------------------
# AC-FR2300-04: rollback_to
# ---------------------------------------------------------------------------


class TestRollback:
    """AC-FR2300-04: rollback_to updates current_version."""

    def test_rollback_to_existing_version(self, tmp_path: Path):
        """AC-FR2300-04: rollback_to("v0.2.0.3") sets current_version to that."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [_make_entry(f"v0.2.0.{i}") for i in range(1, 6)]
        for i in range(1, 6):
            _make_model_dir(models_dir, f"v0.2.0.{i}")

        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        reg = ModelRegistry(registry_path, models_dir)
        reg.rollback_to("v0.2.0.3")

        assert reg.current() == "v0.2.0.3"
        # Check persisted
        data = json.loads(registry_path.read_text())
        assert data["current_version"] == "v0.2.0.3"

    def test_rollback_to_nonexistent_raises(self, tmp_path: Path):
        """Rollback to a non-existent version raises ValueError."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [_make_entry("v0.2.0.1"), _make_entry("v0.2.0.2")]
        for v in ["v0.2.0.1", "v0.2.0.2"]:
            _make_model_dir(models_dir, v)

        _write_registry(registry_path, entries, current_version="v0.2.0.2")

        reg = ModelRegistry(registry_path, models_dir)
        with pytest.raises(ValueError, match="not found"):
            reg.rollback_to("v0.2.0.99")


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    """list_versions returns sorted version strings."""

    def test_list_versions_sorted(self, tmp_path: Path):
        """list_versions returns versions in sorted order (oldest first)."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [
            _make_entry("v0.2.0.10"),
            _make_entry("v0.2.0.2"),
            _make_entry("v0.2.0.1"),
            _make_entry("v0.2.0.5"),
        ]
        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir)
        versions = reg.list_versions()

        assert versions == ["v0.2.0.1", "v0.2.0.2", "v0.2.0.5", "v0.2.0.10"]

    def test_list_versions_with_v010_timestamp_format(self, tmp_path: Path):
        """list_versions handles v0.1.0 timestamp format and orders correctly."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [
            _make_entry("20250101_120000"),  # v0.1.0 format - oldest
            _make_entry("20260715_080000"),  # v0.1.0 format
            _make_entry("v0.2.0.1"),  # v0.2.0 format - newest
        ]
        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir)
        versions = reg.list_versions()

        assert versions == [
            "20250101_120000",
            "20260715_080000",
            "v0.2.0.1",
        ]

    def test_list_versions_mixed_incremental(self, tmp_path: Path):
        """list_versions correctly orders incremental versions."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [
            _make_entry("v0.2.0.5"),
            _make_entry("v0.2.0.5.incr1"),
            _make_entry("v0.2.0.5.incr2"),
            _make_entry("v0.2.0.3"),
        ]
        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir)
        versions = reg.list_versions()

        assert versions == [
            "v0.2.0.3",
            "v0.2.0.5",
            "v0.2.0.5.incr1",
            "v0.2.0.5.incr2",
        ]


# ---------------------------------------------------------------------------
# current
# ---------------------------------------------------------------------------


class TestCurrent:
    """current() returns the current_version."""

    def test_current_returns_version(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [_make_entry("v0.2.0.1")]
        _write_registry(registry_path, entries, current_version="v0.2.0.1")

        reg = ModelRegistry(registry_path, models_dir)
        assert reg.current() == "v0.2.0.1"

    def test_current_returns_none_when_not_set(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [_make_entry("v0.2.0.1")]
        _write_registry(registry_path, entries, current_version=None)

        reg = ModelRegistry(registry_path, models_dir)
        assert reg.current() is None

    def test_current_returns_none_for_empty_registry(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        _write_registry(registry_path, [], current_version=None)

        reg = ModelRegistry(registry_path, models_dir)
        assert reg.current() is None


# ---------------------------------------------------------------------------
# get_entry
# ---------------------------------------------------------------------------


class TestGetEntry:
    """get_entry returns the entry for a given version."""

    def test_get_entry_existing(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [_make_entry("v0.2.0.1", mode="full")]
        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir)
        entry = reg.get_entry("v0.2.0.1")

        assert entry is not None
        assert entry["version"] == "v0.2.0.1"
        assert entry["mode"] == "full"

    def test_get_entry_nonexistent(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        _write_registry(registry_path, [])

        reg = ModelRegistry(registry_path, models_dir)
        assert reg.get_entry("v0.2.0.99") is None


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


class TestAppend:
    """append adds a new entry to the registry."""

    def test_append_adds_entry(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)

        reg = ModelRegistry(registry_path, models_dir)
        reg.append(_make_entry("v0.2.0.1"))

        assert len(reg.list_versions()) == 1
        assert reg.get_entry("v0.2.0.1") is not None

    def test_append_persists_to_disk(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)

        reg = ModelRegistry(registry_path, models_dir)
        reg.append(_make_entry("v0.2.0.1"))

        # Reload from disk
        reg2 = ModelRegistry(registry_path, models_dir)
        assert len(reg2.list_versions()) == 1
        assert reg2.list_versions() == ["v0.2.0.1"]


# ---------------------------------------------------------------------------
# Version ordering correctness
# ---------------------------------------------------------------------------


class TestVersionOrdering:
    """Confirm both version formats sort correctly."""

    def test_v020_format_ordering(self, tmp_path: Path):
        """v0.2.0 format: v0.2.0.3 < v0.2.0.5 < v0.2.0.5.incr1 < v0.2.0.10."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [
            _make_entry("v0.2.0.10"),
            _make_entry("v0.2.0.5.incr1"),
            _make_entry("v0.2.0.5"),
            _make_entry("v0.2.0.3"),
        ]
        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir)
        versions = reg.list_versions()

        assert versions == [
            "v0.2.0.3",
            "v0.2.0.5",
            "v0.2.0.5.incr1",
            "v0.2.0.10",
        ]

    def test_mixed_format_ordering(self, tmp_path: Path):
        """v0.1.0 timestamps sort before v0.2.0 semver versions."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [
            _make_entry("v0.2.0.1"),  # newest format
            _make_entry("20250901_120000"),
            _make_entry("20240101_000000"),  # oldest timestamp
            _make_entry("20260715_120000"),
        ]
        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir)
        versions = reg.list_versions()

        assert versions == [
            "20240101_000000",
            "20250901_120000",
            "20260715_120000",
            "v0.2.0.1",
        ]


# ---------------------------------------------------------------------------
# GC edge cases
# ---------------------------------------------------------------------------


class TestGcEdgeCases:
    """Edge cases for GC behavior."""

    def test_gc_empty_registry(self, tmp_path: Path):
        """GC on empty registry returns empty list."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        _write_registry(registry_path, [])

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=10)
        deleted = reg.gc()
        assert deleted == []

    def test_gc_removes_directories_that_are_not_in_registry(self, tmp_path: Path):
        """GC also cleans up orphan directories not in the registry."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [_make_entry("v0.2.0.1")]
        _make_model_dir(models_dir, "v0.2.0.1")
        _make_model_dir(models_dir, "v0.2.0.99")  # looks like a version but not in registry

        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=5)
        deleted = reg.gc()

        # v0.2.0.99 should be cleaned up as orphan
        assert "v0.2.0.99" in deleted
        assert not (models_dir / "v0.2.0.99").exists()
        assert (models_dir / "v0.2.0.1").exists()

    def test_gc_keeps_non_model_directories(self, tmp_path: Path):
        """GC does not delete directories that don't look like model versions."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        entries = [_make_entry("v0.2.0.1")]
        _make_model_dir(models_dir, "v0.2.0.1")
        other_dir = models_dir / "configs"
        other_dir.mkdir(parents=True, exist_ok=True)
        (other_dir / "test.txt").touch()

        _write_registry(registry_path, entries)

        reg = ModelRegistry(registry_path, models_dir, keep_latest_n=10)
        reg.gc()

        assert other_dir.exists(), "Non-model directories should not be touched"


# ---------------------------------------------------------------------------
# Registry not exists yet (lazy creation)
# ---------------------------------------------------------------------------


class TestLazyRegistry:
    """ModelRegistry handles non-existent registry.json gracefully."""

    def test_empty_when_registry_missing(self, tmp_path: Path):
        """When registry.json doesn't exist, list_versions returns empty."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        reg = ModelRegistry(registry_path, models_dir)
        assert reg.list_versions() == []
        assert reg.current() is None

    def test_append_creates_registry_if_missing(self, tmp_path: Path):
        """append creates the registry file if it doesn't exist."""
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"

        reg = ModelRegistry(registry_path, models_dir)
        reg.append(_make_entry("v0.2.0.1"))

        assert registry_path.exists()
        assert len(reg.list_versions()) == 1
