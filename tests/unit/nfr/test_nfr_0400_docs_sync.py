"""Tests for NFR-0400: ADR documentation and docs sync.

AC-NFR0400-01: ADR files exist with Status, Context, Decision, Consequences.
AC-NFR0400-02: scripts/check_docs_sync.py exists and detects drift.
AC-NFR0400-03: scripts/check_docs_sync.py can be invoked without error.
"""

from pathlib import Path


class TestADRDocs:
    """NFR-0400: ADR documentation."""

    def test_adr_directory_exists(self):
        """AC-NFR0400-01: docs/adr/ directory exists."""
        adr_dir = Path("docs/adr")
        assert adr_dir.exists(), "docs/adr/ directory not found"
        assert adr_dir.is_dir(), "docs/adr/ is not a directory"

    def test_minimum_adrs_exist(self):
        """AC-NFR0400-01: At least 3 ADR files exist as per AC."""
        adr_dir = Path("docs/adr")
        md_files = list(adr_dir.glob("*.md"))
        assert len(md_files) >= 3, f"Expected >= 3 ADR files, found {len(md_files)}"

    def test_adr_has_required_sections(self):
        """AC-NFR0400-01: Each ADR has Status, Context, Decision, Consequences."""
        adr_dir = Path("docs/adr")
        required_sections = ["## Status", "## Context", "## Decision", "## Consequences"]

        md_files = list(adr_dir.glob("*.md"))
        assert len(md_files) > 0, "No ADR .md files found"

        for adr_file in md_files:
            content = adr_file.read_text()
            for section in required_sections:
                assert section in content, f"{adr_file.name} missing section: {section}"

    def test_cvxpyscipy_adr_exists(self):
        """AC-NFR0400-01: ADR for cvxpy+scipy fallback exists."""
        adr_path = Path("docs/adr/0001-cvxpy-scipy-fallback.md")
        assert adr_path.exists(), "0001-cvxpy-scipy-fallback.md not found"
        content = adr_path.read_text()
        assert "cvxpy" in content.lower()
        assert "scipy" in content.lower()


class TestDocsSyncScript:
    """NFR-0400: docs sync check script."""

    def test_check_docs_sync_script_exists(self):
        """AC-NFR0400-02: scripts/check_docs_sync.py exists."""
        script_path = Path("scripts/check_docs_sync.py")
        assert script_path.exists(), "scripts/check_docs_sync.py not found"
        assert script_path.stat().st_size > 0, "scripts/check_docs_sync.py is empty"

    def test_check_docs_sync_is_executable(self):
        """AC-NFR0400-02: scripts/check_docs_sync.py is executable."""
        import os

        script_path = Path("scripts/check_docs_sync.py")
        assert os.access(script_path, os.X_OK), "scripts/check_docs_sync.py is not executable"

    def test_check_docs_sync_runs_without_error(self):
        """AC-NFR0400-03: scripts/check_docs_sync.py can be invoked without error."""
        import subprocess

        result = subprocess.run(
            ["python", "scripts/check_docs_sync.py"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should run without error (exit code 0 or 1 is fine - 1 means drift found)
        assert result.returncode in (0, 1), f"Script failed: {result.stderr}"

    def test_check_docs_sync_mentions_nfr0400(self):
        """AC-NFR0400-03: scripts/check_docs_sync.py mentions NFR-0400."""
        script_path = Path("scripts/check_docs_sync.py")
        content = script_path.read_text()
        assert "NFR-0400" in content, "Script does not mention NFR-0400"

    def test_adr_script_has_docstring(self):
        """AC-NFR0400-03: scripts/check_docs_sync.py has proper docstring."""
        script_path = Path("scripts/check_docs_sync.py")
        content = script_path.read_text()
        assert '"""' in content, "Script missing docstring"
