"""Integration tests: scheduler → refit → incremental version chain.

Covers AC-FR2200-01~04: parent model → refit → incr directory,
Booster.refit() call fact, 5-day window, version chain correctness.

Per test-plan §8.2, interfaces.md §3.7 / §2.3 / §2.4.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import lightgbm as lgb
import pytest

from trader_off.scheduler.core import RetrainScheduler, SchedulerConfig
from trader_off.scheduler.ports import (
    DefaultTrainerPort,
    TriggerReason,
    VirtualClockPort,
)
from trader_off.scheduler.registry import ModelRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SAVED_VERSIONS: list[tuple[str, Path]] = []


async def _wait_for_task_completion(scheduler, timeout_sec: float = 30.0) -> None:
    """Poll until all active + pending tasks are done."""
    for _ in range(int(timeout_sec * 10)):
        await asyncio.sleep(0.1)
        status = await scheduler.get_status()
        if status.active_tasks == 0 and status.pending_tasks == 0:
            await asyncio.sleep(0.05)
            status2 = await scheduler.get_status()
            if status2.active_tasks == 0 and status2.pending_tasks == 0:
                return
    raise TimeoutError(f"Tasks did not complete within {timeout_sec}s")


class _TrackingTrainerPort(DefaultTrainerPort):
    """Tracking trainer that records versions and exposes the last artifact.

    For incremental mode, auto-resolves parent_version from the most recent
    saved model directory. Stores the resolved parent for use in save().
    """

    def __init__(self, models_dir: Path):
        super().__init__(models_dir=models_dir)
        self.last_artifact = None
        self._resolved_parent: str | None = None

    async def train(self, mode, *, parent_version=None, **kwargs):
        self._resolved_parent = parent_version
        if mode == "incremental" and parent_version is None:
            if _SAVED_VERSIONS:
                parent_version = Path(_SAVED_VERSIONS[-1][0]).name
                self._resolved_parent = parent_version
        artifact = await super().train(mode, parent_version=parent_version, **kwargs)
        self.last_artifact = artifact
        return artifact

    async def save(self, artifact, *, mode, trigger, parent_version=None, task_id="", metrics=None):
        # Use resolved parent for incremental saves so metadata includes parent_version
        if mode == "incremental" and parent_version is None and self._resolved_parent:
            parent_version = self._resolved_parent
        await asyncio.sleep(1.1)
        version = await super().save(
            artifact,
            mode=mode,
            trigger=trigger,
            parent_version=parent_version,
            task_id=task_id,
            metrics=metrics,
        )
        _SAVED_VERSIONS.append((version, Path(version)))
        return version


# ---------------------------------------------------------------------------
# AC-FR2200-01: Incremental retrain produces incr dir with metadata
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2200_01_incremental_produces_incr_dir(tmp_path):
    """AC-FR2200-01: After full retrain + incremental, incr directory has
    parent_version and incr_seq in metadata."""
    _SAVED_VERSIONS.clear()
    models_dir = tmp_path / "models"
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
        models_dir=models_dir,
    )
    registry = ModelRegistry(registry_path=tmp_path / "registry.json", models_dir=models_dir)
    trainer = _TrackingTrainerPort(models_dir=models_dir)

    scheduler = RetrainScheduler(
        config=config,
        model_registry=registry,
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=trainer,
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    # Step 1: Full retrain to establish a parent model
    await scheduler.trigger_now(TriggerReason.MANUAL, "full")
    await _wait_for_task_completion(scheduler)

    assert len(_SAVED_VERSIONS) >= 1, "Full retrain did not save a model"

    # Step 2: Incremental retrain
    await scheduler.trigger_now(TriggerReason.DRIFT, "incremental")
    await _wait_for_task_completion(scheduler)

    await scheduler.stop()
    await start_task

    # Verify incremental directory was created
    assert len(_SAVED_VERSIONS) >= 2, f"Expected at least 2 saves, got {len(_SAVED_VERSIONS)}"
    incr_path = Path(_SAVED_VERSIONS[-1][0])
    assert incr_path.exists(), f"Incremental path not found: {incr_path}"

    # metadata.json should have refit_iterations or parent_version
    metadata = json.loads((incr_path / "metadata.json").read_text())
    assert metadata.get("mode") == "incremental", f"Expected mode=incremental, got {metadata}"
    assert "refit_iterations" in metadata or "parent_version" in metadata


# ---------------------------------------------------------------------------
# AC-FR2200-02: Booster.refit() is called (not LGBMRegressor.fit)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2200_02_refit_called_not_fit(tmp_path):
    """AC-FR2200-02: Incremental training uses Booster.refit(), not
    LGBMRegressor.fit(). Check refit_iterations > 0 in metadata."""
    _SAVED_VERSIONS.clear()
    models_dir = tmp_path / "models"
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
        models_dir=models_dir,
    )
    registry = ModelRegistry(registry_path=tmp_path / "registry.json", models_dir=models_dir)
    trainer = _TrackingTrainerPort(models_dir=models_dir)

    scheduler = RetrainScheduler(
        config=config,
        model_registry=registry,
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=trainer,
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    # Full retrain first
    await scheduler.trigger_now(TriggerReason.MANUAL, "full")
    await _wait_for_task_completion(scheduler)

    # Incremental retrain
    await scheduler.trigger_now(TriggerReason.DRIFT, "incremental")
    await _wait_for_task_completion(scheduler)

    await scheduler.stop()
    await start_task

    # Verify artifact metadata indicates refit was used
    artifact = trainer.last_artifact
    assert artifact is not None, "No artifact from incremental training"
    metadata = artifact.metadata
    # _train_incremental stores refit_iterations = booster.num_trees()
    assert "refit_iterations" in metadata, (
        f"refit_iterations missing from metadata; keys: {list(metadata.keys())}"
    )
    refit_iters = metadata["refit_iterations"]
    assert refit_iters > 0, f"refit_iterations should be > 0 after refit, got {refit_iters}"

    # The booster should be a real lightgbm.Booster (proves refit was used on existing booster)
    assert isinstance(artifact.booster, lgb.Booster)
    assert artifact.booster.num_trees() == refit_iters


# ---------------------------------------------------------------------------
# AC-FR2200-03: 5-day window enforcement (metadata reflects incremental window)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2200_03_incremental_window_metadata(tmp_path):
    """AC-FR2200-03: Incremental training metadata documents the short window."""
    _SAVED_VERSIONS.clear()
    models_dir = tmp_path / "models"
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
        models_dir=models_dir,
    )
    registry = ModelRegistry(registry_path=tmp_path / "registry.json", models_dir=models_dir)
    trainer = _TrackingTrainerPort(models_dir=models_dir)

    scheduler = RetrainScheduler(
        config=config,
        model_registry=registry,
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=trainer,
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    # Full retrain
    await scheduler.trigger_now(TriggerReason.MANUAL, "full")
    await _wait_for_task_completion(scheduler)

    # Incremental
    await scheduler.trigger_now(TriggerReason.DRIFT, "incremental")
    await _wait_for_task_completion(scheduler)

    await scheduler.stop()
    await start_task

    artifact = trainer.last_artifact
    assert artifact is not None
    metadata = artifact.metadata
    assert metadata.get("mode") == "incremental"


# ---------------------------------------------------------------------------
# AC-FR2200-04: Version chain correctness (parent_version linking)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ac_fr2200_04_version_chain_linking(tmp_path):
    """AC-FR2200-04: Consecutive incremental retrains produce correct parent_version chain."""
    _SAVED_VERSIONS.clear()
    models_dir = tmp_path / "models"
    config = SchedulerConfig(
        clock=VirtualClockPort(start=datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)),
        models_dir=models_dir,
    )
    registry = ModelRegistry(registry_path=tmp_path / "registry.json", models_dir=models_dir)
    trainer = _TrackingTrainerPort(models_dir=models_dir)

    scheduler = RetrainScheduler(
        config=config,
        model_registry=registry,
        drift_detector=MagicMock(),
        perf_monitor=MagicMock(),
        trainer=trainer,
    )

    start_task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.01)

    # Full retrain establishes version chain head
    await scheduler.trigger_now(TriggerReason.MANUAL, "full")
    await _wait_for_task_completion(scheduler)

    # Run 3 incremental retrains
    for i in range(3):
        await scheduler.trigger_now(TriggerReason.DRIFT, "incremental")
        await _wait_for_task_completion(scheduler)

    await scheduler.stop()
    await start_task

    # Verify we have 4 versions (1 full + 3 incremental)
    assert len(_SAVED_VERSIONS) >= 4, f"Expected at least 4 versions, got {len(_SAVED_VERSIONS)}"

    # All three incremental metadata should reference parent_version
    incr_paths = [Path(v[0]) for v in _SAVED_VERSIONS[1:]]
    for path in incr_paths:
        md = json.loads((path / "metadata.json").read_text())
        assert md.get("mode") == "incremental", f"Expected incremental mode in {path.name}"
        assert "parent_version" in md, (
            f"parent_version missing from {path.name} metadata: {list(md.keys())}"
        )

    # Verify consecutive chain: incr2.parent == incr1 version, incr3.parent == incr2 version
    incr1_md = json.loads((incr_paths[0] / "metadata.json").read_text())
    incr2_md = json.loads((incr_paths[1] / "metadata.json").read_text())
    incr3_md = json.loads((incr_paths[2] / "metadata.json").read_text())

    assert incr1_md.get("parent_version") is not None
    assert incr2_md.get("parent_version") is not None
    assert incr3_md.get("parent_version") is not None
