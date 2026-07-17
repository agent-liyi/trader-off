"""Unit tests for deploy.py — FR-2400 automatic model deployment.

AC coverage:
- AC-FR2400-01: Successful deploy after validation (metrics >= ic_floor).
- AC-FR2400-02: Validation failure blocks deployment (metrics < ic_floor).
- AC-FR2400-03: Hot-reload polling detects registry change (watch_registry).
- AC-FR2400-04: Atomic pointer swap — registry protected from corrupt load.
"""

from __future__ import annotations

import asyncio
import json
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
        "created_at": "2026-07-17T12:00:00Z",
        "trigger": "cron_full" if mode == "full" else "manual",
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
) -> None:
    """Write a registry.json file to disk."""
    data: dict = {
        "entries": entries,
        "current_version": current_version,
        "pinned_versions": [],
        "schema_version": 2,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _make_model_dir(models_dir: Path, version: str) -> Path:
    """Create a minimal model directory for a version."""
    d = models_dir / version
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.pkl").write_bytes(b"dummy_model_data")
    (d / "metadata.json").write_text("{}")
    return d


def _make_registry(tmp_path: Path, current_version: str, *versions: str) -> ModelRegistry:
    """Create a ModelRegistry with given versions and current_version."""
    models_dir = tmp_path / "models"
    registry_path = models_dir / "registry.json"

    entries = []
    for v in versions:
        entries.append(_make_entry(v))
        _make_model_dir(models_dir, v)

    _write_registry(registry_path, entries, current_version=current_version)

    return ModelRegistry(registry_path, models_dir)


# ---------------------------------------------------------------------------
# AC-FR2400-01: deploy_model success
# ---------------------------------------------------------------------------


class TestDeployModelSuccess:
    """AC-FR2400-01: deploy_model succeeds when test_ic_mean >= ic_floor."""

    def test_deploy_updates_current_version(self, tmp_path: Path):
        """AC-FR2400-01: registry current_version is updated after successful deploy."""
        from trader_off.scheduler.deploy import deploy_model

        registry = _make_registry(tmp_path, "v0.2.0.5", "v0.2.0.5", "v0.2.0.6")
        assert registry.current() == "v0.2.0.5"

        result = deploy_model(
            registry,
            "v0.2.0.6",
            metrics={"test_ic_mean": 0.025, "test_rank_ic_mean": 0.035},
            ic_floor=0.005,
        )

        assert result is True
        assert registry.current() == "v0.2.0.6"

    def test_deploy_writes_deploy_log(self, tmp_path: Path):
        """AC-FR2400-01: deploy.log is written with from/to/status on success."""
        from trader_off.scheduler.deploy import deploy_model

        logs_dir = tmp_path / "logs"
        registry = _make_registry(tmp_path, "v0.2.0.5", "v0.2.0.5", "v0.2.0.6")

        deploy_model(
            registry,
            "v0.2.0.6",
            metrics={"test_ic_mean": 0.03},
            ic_floor=0.005,
            logs_dir=logs_dir,
        )

        deploy_log = logs_dir / "deploy.log"
        assert deploy_log.exists(), "deploy.log should be created"
        log_text = deploy_log.read_text()
        assert "from=v0.2.0.5" in log_text
        assert "to=v0.2.0.6" in log_text
        assert "status=success" in log_text

    def test_deploy_with_ic_equal_to_floor(self, tmp_path: Path):
        """AC-FR2400-01: Exact boundary — test_ic_mean == ic_floor passes validation."""
        from trader_off.scheduler.deploy import deploy_model

        registry = _make_registry(tmp_path, "v0.2.0.5", "v0.2.0.5", "v0.2.0.6")

        result = deploy_model(
            registry,
            "v0.2.0.6",
            metrics={"test_ic_mean": 0.005, "test_rank_ic_mean": 0.01},
            ic_floor=0.005,
        )

        assert result is True
        assert registry.current() == "v0.2.0.6"

    def test_deploy_returns_true_and_persists_immediately(self, tmp_path: Path):
        """AC-FR2400-01: After deploy_model returns True, disk state matches."""
        from trader_off.scheduler.deploy import deploy_model

        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.5"), _make_entry("v0.2.0.6")]
        _make_model_dir(models_dir, "v0.2.0.5")
        _make_model_dir(models_dir, "v0.2.0.6")
        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        registry = ModelRegistry(registry_path, models_dir)

        result = deploy_model(
            registry,
            "v0.2.0.6",
            metrics={"test_ic_mean": 0.03},
            ic_floor=0.005,
        )

        assert result is True
        # Re-read from disk — change must be persisted
        data = json.loads(registry_path.read_text())
        assert data["current_version"] == "v0.2.0.6"


# ---------------------------------------------------------------------------
# AC-FR2400-02: deploy_model validation failure
# ---------------------------------------------------------------------------


class TestDeployModelValidationFailure:
    """AC-FR2400-02: deploy_model returns False when test_ic_mean < ic_floor."""

    def test_deploy_blocked_by_low_ic(self, tmp_path: Path):
        """AC-FR2400-02: test_ic_mean below floor returns False, does not change version."""
        from trader_off.scheduler.deploy import deploy_model

        registry = _make_registry(tmp_path, "v0.2.0.6", "v0.2.0.6", "v0.2.0.7")

        result = deploy_model(
            registry,
            "v0.2.0.7",
            metrics={"test_ic_mean": 0.001, "test_rank_ic_mean": 0.002},
            ic_floor=0.005,
        )

        assert result is False
        assert registry.current() == "v0.2.0.6", "current_version must NOT change"
        assert registry.current() != "v0.2.0.7"

    def test_deploy_logs_warning_on_validation_failure(self, tmp_path: Path, caplog):
        """AC-FR2400-02: WARNING log emitted when validation fails."""
        import logging

        from trader_off.scheduler.deploy import deploy_model

        registry = _make_registry(tmp_path, "v0.2.0.6", "v0.2.0.6", "v0.2.0.7")

        with caplog.at_level(logging.WARNING):
            deploy_model(
                registry,
                "v0.2.0.7",
                metrics={"test_ic_mean": 0.0},
                ic_floor=0.005,
            )

        assert "validation failed" in caplog.text, (
            f"Expected WARNING 'validation failed' in log, got: {caplog.text}"
        )
        assert "v0.2.0.7" in caplog.text, (
            f"Expected WARNING mentioning v0.2.0.7, got: {caplog.text}"
        )

    def test_deploy_missing_test_ic_mean_defaults_to_zero(self, tmp_path: Path):
        """Metrics dict without test_ic_mean treated as 0.0 and fails validation."""
        from trader_off.scheduler.deploy import deploy_model

        registry = _make_registry(tmp_path, "v0.2.0.6", "v0.2.0.6", "v0.2.0.7")

        result = deploy_model(
            registry,
            "v0.2.0.7",
            metrics={},  # no test_ic_mean key
            ic_floor=0.005,
        )

        assert result is False
        assert registry.current() == "v0.2.0.6"

    def test_deploy_does_not_write_success_log_on_failure(self, tmp_path: Path):
        """AC-FR2400-02: deploy.log is NOT written on validation failure."""
        from trader_off.scheduler.deploy import deploy_model

        logs_dir = tmp_path / "logs"
        registry = _make_registry(tmp_path, "v0.2.0.6", "v0.2.0.6", "v0.2.0.7")

        deploy_model(
            registry,
            "v0.2.0.7",
            metrics={"test_ic_mean": 0.0},
            ic_floor=0.005,
            logs_dir=logs_dir,
        )

        deploy_log = logs_dir / "deploy.log"
        assert not deploy_log.exists(), "deploy.log should NOT be written on validation failure"


# ---------------------------------------------------------------------------
# AC-FR2400-03: watch_registry hot-reload polling
# ---------------------------------------------------------------------------


class TestWatchRegistry:
    """AC-FR2400-03: watch_registry polls registry.json and calls on_change."""

    @pytest.mark.asyncio
    async def test_watch_detects_version_change(self, tmp_path: Path):
        """AC-FR2400-03: on_change is called when current_version changes in registry."""
        from trader_off.scheduler.deploy import watch_registry

        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.5"), _make_entry("v0.2.0.6")]
        _make_model_dir(models_dir, "v0.2.0.5")
        _make_model_dir(models_dir, "v0.2.0.6")
        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        changes: list[str] = []

        async def on_change():
            data = json.loads(registry_path.read_text())
            changes.append(data.get("current_version", "none"))

        # Start watch in background with very short poll interval
        watch_task = asyncio.ensure_future(
            watch_registry(registry_path, on_change, poll_interval_sec=0.05)
        )

        try:
            # Wait for initial poll to settle
            await asyncio.sleep(0.1)

            # Update registry to simulate a deploy
            _write_registry(registry_path, entries, current_version="v0.2.0.6")
            await asyncio.sleep(0.15)

            assert len(changes) >= 1, "on_change should have been called at least once"
            assert changes[-1] == "v0.2.0.6", "on_change should see the new version"
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_watch_no_change_no_callback(self, tmp_path: Path):
        """AC-FR2400-03: on_change is NOT called when current_version stays the same."""
        from trader_off.scheduler.deploy import watch_registry

        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.5")]
        _make_model_dir(models_dir, "v0.2.0.5")
        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        call_count = 0

        async def on_change():
            nonlocal call_count
            call_count += 1

        watch_task = asyncio.ensure_future(
            watch_registry(registry_path, on_change, poll_interval_sec=0.05)
        )

        try:
            # Wait through several poll cycles with no registry change
            await asyncio.sleep(0.2)

            # on_change should NOT be called because version never changes after
            # the first detection. But the FIRST poll when last_version is None
            # should NOT trigger on_change either.
            assert call_count == 0, "on_change should NOT be called when version is stable"
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_watch_handles_missing_registry_gracefully(self, tmp_path: Path):
        """AC-FR2400-03: watch_registry does not crash when registry file is missing."""
        from trader_off.scheduler.deploy import watch_registry

        registry_path = tmp_path / "nonexistent" / "registry.json"

        async def on_change():
            pass  # Should never be called

        watch_task = asyncio.ensure_future(
            watch_registry(registry_path, on_change, poll_interval_sec=0.05)
        )

        try:
            await asyncio.sleep(0.15)
            # The watcher should still be alive (not crashed)
            assert not watch_task.done(), "watch_registry should survive missing file"
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_watch_sync_callback(self, tmp_path: Path):
        """AC-FR2400-03: watch_registry supports synchronous callbacks too."""
        from trader_off.scheduler.deploy import watch_registry

        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.5"), _make_entry("v0.2.0.6")]
        _make_model_dir(models_dir, "v0.2.0.5")
        _make_model_dir(models_dir, "v0.2.0.6")
        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        changes: list[str] = []

        def on_change():
            data = json.loads(registry_path.read_text())
            changes.append(data.get("current_version", "none"))

        watch_task = asyncio.ensure_future(
            watch_registry(registry_path, on_change, poll_interval_sec=0.05)
        )

        try:
            await asyncio.sleep(0.1)
            _write_registry(registry_path, entries, current_version="v0.2.0.6")
            await asyncio.sleep(0.15)

            assert len(changes) >= 1
            assert changes[-1] == "v0.2.0.6"
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# AC-FR2400-04: Atomic pointer swap / failure safety
# ---------------------------------------------------------------------------


class TestDeployFailureSafety:
    """AC-FR2400-04: Deploy must be atomic and not leave prediction service broken."""

    def test_deploy_rollback_to_is_atomic(self, tmp_path: Path):
        """AC-FR2400-04: Registry's rollback_to uses atomic write (temp+rename).

        Even if the process crashes between temp write and rename, the
        original registry.json is intact.
        """
        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.5"), _make_entry("v0.2.0.8")]
        _make_model_dir(models_dir, "v0.2.0.5")
        _make_model_dir(models_dir, "v0.2.0.8")
        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        registry = ModelRegistry(registry_path, models_dir)

        # Verify no .tmp file was left behind (normal atomic write cleanup)
        registry.rollback_to("v0.2.0.8")

        # tmp file should NOT persist after successful write
        tmp_path_file = registry_path.with_suffix(".json.tmp")
        assert not tmp_path_file.exists(), "tmp file should be cleaned up after atomic write"

        # Current version should be updated
        assert registry.current() == "v0.2.0.8"

        # Original data was replaced atomically — no corruption
        new_data = json.loads(registry_path.read_text())
        assert new_data["current_version"] == "v0.2.0.8"

    def test_validation_failure_leaves_registry_unchanged(self, tmp_path: Path):
        """AC-FR2400-04: When validation fails, current_version stays on old model."""
        from trader_off.scheduler.deploy import deploy_model

        registry = _make_registry(tmp_path, "v0.2.0.5", "v0.2.0.5", "v0.2.0.8")

        # Deploying v0.2.0.8 (model dir exists but metrics fail)
        result = deploy_model(
            registry,
            "v0.2.0.8",
            metrics={"test_ic_mean": -0.01},  # below floor
            ic_floor=0.005,
        )

        assert result is False
        assert registry.current() == "v0.2.0.5", (
            "Old version must remain active when deploy is rejected"
        )

    def test_deploy_keeps_old_entry_in_registry(self, tmp_path: Path):
        """AC-FR2400-04: Failed deploy does not remove old version from registry entries."""
        from trader_off.scheduler.deploy import deploy_model

        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.5"), _make_entry("v0.2.0.8")]
        _make_model_dir(models_dir, "v0.2.0.5")
        _make_model_dir(models_dir, "v0.2.0.8")
        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        registry = ModelRegistry(registry_path, models_dir)

        deploy_model(
            registry,
            "v0.2.0.8",
            metrics={"test_ic_mean": -0.01},
            ic_floor=0.005,
        )

        # Both versions should still be in the registry
        assert registry.get_entry("v0.2.0.5") is not None
        assert registry.get_entry("v0.2.0.8") is not None
        assert len(registry.list_versions()) == 2

    def test_deploy_success_atomic_pointer_swap(self, tmp_path: Path):
        """AC-FR2400-01: Deploy changes ONLY current_version, not entries."""
        from trader_off.scheduler.deploy import deploy_model

        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.5"), _make_entry("v0.2.0.6")]
        _make_model_dir(models_dir, "v0.2.0.5")
        _make_model_dir(models_dir, "v0.2.0.6")
        _write_registry(registry_path, entries, current_version="v0.2.0.5")

        registry = ModelRegistry(registry_path, models_dir)

        result = deploy_model(
            registry,
            "v0.2.0.6",
            metrics={"test_ic_mean": 0.03},
            ic_floor=0.005,
        )

        assert result is True
        assert registry.current() == "v0.2.0.6"
        # Both versions still listed
        assert len(registry.list_versions()) == 2
        assert registry.get_entry("v0.2.0.5") is not None
        assert registry.get_entry("v0.2.0.6") is not None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestDeployEdgeCases:
    """Additional edge cases for deploy_model."""

    def test_first_deploy_when_current_is_none(self, tmp_path: Path):
        """Deploy works when no previous version is deployed (current is None)."""
        from trader_off.scheduler.deploy import deploy_model

        models_dir = tmp_path / "models"
        registry_path = models_dir / "registry.json"
        entries = [_make_entry("v0.2.0.1")]
        _make_model_dir(models_dir, "v0.2.0.1")
        _write_registry(registry_path, entries, current_version=None)

        registry = ModelRegistry(registry_path, models_dir)
        assert registry.current() is None

        logs_dir = tmp_path / "logs"
        result = deploy_model(
            registry,
            "v0.2.0.1",
            metrics={"test_ic_mean": 0.04},
            ic_floor=0.005,
            logs_dir=logs_dir,
        )

        assert result is True
        assert registry.current() == "v0.2.0.1"

        # deploy.log should handle None gracefully
        deploy_log = logs_dir / "deploy.log"
        log_text = deploy_log.read_text()
        assert "status=success" in log_text

    def test_deploy_log_appends_multiple_entries(self, tmp_path: Path):
        """Multiple deploys append to the same deploy.log."""
        from trader_off.scheduler.deploy import deploy_model

        logs_dir = tmp_path / "logs"
        entries = [_make_entry(f"v0.2.0.{i}") for i in range(1, 5)]

        for i, v in enumerate(["v0.2.0.1", "v0.2.0.2", "v0.2.0.3"]):
            models_dir = tmp_path / f"run_{i}" / "models"
            registry_path = models_dir / "registry.json"
            for j, e in enumerate(entries):
                _make_model_dir(models_dir, e["version"])
            _write_registry(
                registry_path,
                entries,
                current_version=f"v0.2.0.{i}" if i > 0 else None,
            )

            registry = ModelRegistry(registry_path, models_dir)
            deploy_model(
                registry,
                v,
                metrics={"test_ic_mean": 0.03},
                ic_floor=0.005,
                logs_dir=logs_dir,
            )

        deploy_log = logs_dir / "deploy.log"
        lines = deploy_log.read_text().strip().split("\n")
        assert len(lines) == 3, "All three deploys should be logged"
        for line in lines:
            assert "status=success" in line
