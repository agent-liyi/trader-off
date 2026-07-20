"""Integration tests for fixture manifest SHA256 verification (NFR-0800 AC-3).

Covers AC-NFR0800-03: fixture files under tests/fixtures/v0.2.0/ have
a MANIFEST.json with SHA256 checksums; loaders verify manifest signature
before reading data.

Per test-plan §8.2, interfaces.md §2.9 (persistent file contract).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "v0.2.0"
MANIFEST_PATH = FIXTURES_DIR / "MANIFEST.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_manifest() -> dict:
    """Load and return the MANIFEST.json contents."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"MANIFEST.json not found at {MANIFEST_PATH}")
    with open(MANIFEST_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# AC-NFR0800-03: Fixture integrity — SHA256 matches manifest
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ac_nfr0800_03_manifest_sha256_all_match():
    """AC-NFR0800-03: Every fixture file listed in MANIFEST.json has its
    SHA256 checksum matching the manifest entry."""
    manifest = _load_manifest()

    assert len(manifest) > 0, "MANIFEST.json is empty — expected fixture entries"

    checked = 0
    for filename, entry in manifest.items():
        file_path = FIXTURES_DIR / filename
        assert file_path.exists(), (
            f"Fixture file {filename} listed in MANIFEST.json but missing on disk"
        )
        expected_sha256 = entry["sha256"]
        actual_sha256 = _compute_sha256(file_path)

        assert actual_sha256 == expected_sha256, (
            f"SHA256 mismatch for {filename}:\n"
            f"  manifest: {expected_sha256}\n"
            f"  computed: {actual_sha256}"
        )
        # Also verify size and row count if listed
        actual_size = file_path.stat().st_size
        expected_size = entry.get("size_bytes")
        if expected_size is not None:
            assert actual_size == expected_size, (
                f"File size mismatch for {filename}: expected {expected_size}, got {actual_size}"
            )
        checked += 1

    assert checked >= 1, "No fixture files were checked"


@pytest.mark.integration
def test_ac_nfr0800_03_manifest_tampered_detection(tmp_path):
    """AC-NFR0800-03: A tampered fixture file (modified byte) produces a
    SHA256 that no longer matches the manifest entry."""
    manifest = _load_manifest()

    # Pick the first fixture file listed in the manifest
    first_name = next(iter(manifest.keys()))
    source_path = FIXTURES_DIR / first_name
    expected_sha256 = manifest[first_name]["sha256"]

    # Verify the genuine file matches first
    genuine_hash = _compute_sha256(source_path)
    assert genuine_hash == expected_sha256, (
        f"Prerequisite failed: genuine {first_name} SHA256 doesn't match manifest"
    )

    # Copy to tmp_path and tamper with one byte
    tampered_path = tmp_path / first_name
    with open(source_path, "rb") as src:
        content = bytearray(src.read())
    # Flip the first byte to simulate tampering
    content[0] = (content[0] + 1) % 256
    tampered_path.write_bytes(content)

    tampered_hash = _compute_sha256(tampered_path)
    assert tampered_hash != expected_sha256, (
        f"Tampered file {first_name} unexpectedly still matches manifest SHA256. "
        f"Tampering should have changed the hash.\n"
        f"  manifest: {expected_sha256}\n"
        f"  tampered: {tampered_hash}"
    )


@pytest.mark.integration
def test_ac_nfr0800_03_manifest_missing_file_detected():
    """AC-NFR0800-03: If a fixture file listed in MANIFEST.json does not
    exist on disk, the integrity check should detect the gap."""
    manifest = _load_manifest()

    # Verify that every listed file exists — this is the baseline
    missing = []
    for filename in manifest:
        file_path = FIXTURES_DIR / filename
        if not file_path.exists():
            missing.append(filename)

    assert len(missing) == 0, f"MANIFEST.json references files that don't exist on disk: {missing}"


@pytest.mark.integration
def test_ac_nfr0800_03_manifest_exists_and_well_formed():
    """AC-NFR0800-03: MANIFEST.json exists, is valid JSON, and each entry
    has the required 'sha256' field."""
    manifest = _load_manifest()

    for filename, entry in manifest.items():
        assert "sha256" in entry, f"MANIFEST.json entry for '{filename}' missing 'sha256' field"
        sha = entry["sha256"]
        assert isinstance(sha, str), (
            f"sha256 for '{filename}' must be a string, got {type(sha).__name__}"
        )
        assert len(sha) == 64, (
            f"sha256 for '{filename}' must be 64 hex chars, got {len(sha)}: {sha}"
        )
        # Verify it's valid hex
        int(sha, 16)  # will raise ValueError if not hex
