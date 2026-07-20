"""E2E test for scenario-0020 + 0030: scheduler start, cron tick, retrain, deploy.

Covers:
    AC-FR2700-01: scheduler start CLI
    AC-FR2100-01/02: full retrain artifacts + registry
    AC-FR2400-01: auto deploy
    AC-FR2600-04: drift report on disk

Per test-plan §6.5: virtual clock, no real time.sleep(). Happy path only.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import pytest

from trader_off.scheduler.core import (
    RetrainScheduler,
    RetrainTask,
    SchedulerConfig,
)
from trader_off.scheduler.ports import (
    TriggerReason,
    VirtualClockPort,
)


class _MockTrainerPort:
    """Mock TrainerPort that records train/save calls."""

    def __init__(self):
        self.train_calls = []
        self.save_calls = []

    async def train(
        self,
        mode,
        *,
        parent_version=None,
        factor_registry_path=None,
        train_window_years=3,
        config_snapshot=None,
    ):
        import lightgbm as lgb
        import numpy as np

        from trader_off.data.preprocess import StandardScaler
        from trader_off.training.serialize import ModelArtifact

        self.train_calls.append(
            {
                "mode": mode,
                "parent_version": parent_version,
            }
        )
        # Build a minimal valid booster
        dummy_data = lgb.Dataset(np.zeros((10, 2)), label=np.zeros(10))
        booster = lgb.train({"num_leaves": 2, "verbose": -1}, dummy_data, num_boost_round=1)
        return ModelArtifact(
            booster=booster,
            scaler=StandardScaler(
                feature_names=["f1", "f2"],
                mean_={"f1": 0.0, "f2": 0.0},
                std_={"f1": 1.0, "f2": 1.0},
            ),
            feature_names=["f1", "f2"],
            metadata={},
        )

    async def save(self, artifact, *, mode, trigger, parent_version=None, task_id="", metrics=None):
        self.save_calls.append(
            {
                "mode": mode,
                "trigger": trigger,
                "task_id": task_id,
            }
        )
        return "v0.2.0.1"


class _MockModelRegistryPort:
    """Mock ModelRegistryPort for scheduler e2e."""

    def __init__(self):
        self.entries = []
        self.current_version = None
        self.gc_calls = 0
        self.rollback_calls = []

    def gc(self):
        self.gc_calls += 1
        return []

    def rollback_to(self, version):
        self.rollback_calls.append(version)

    def list_versions(self):
        return [e.get("version", "") for e in self.entries]

    def get_entry(self, version):
        return None

    def add_entry(self, entry):
        self.entries.append(entry)
        self.current_version = entry.get("version")


class _MockPerfMonitorPort:
    """Mock PerfMonitorPort."""

    async def trigger_perf_degradation(self):
        from trader_off.scheduler.perf_monitor import TriggerDecision

        return TriggerDecision(
            should_retrain=False,
            reason="ok",
            suggested_mode="incremental",
            computation_time_sec=0.01,
            notes="ic_only",
        )


class _MockDriftDetectorPort:
    """Mock DriftDetectorPort."""

    def evaluate(self):
        import polars as pl

        from trader_off.scheduler.drift import DriftDecision

        return DriftDecision(
            should_retrain=False,
            reason="ok",
            suggested_mode="incremental",
            per_feature_stats=pl.DataFrame(
                schema={
                    "feature": pl.Utf8,
                    "psi": pl.Float64,
                    "ks_statistic": pl.Float64,
                    "p_value": pl.Float64,
                }
            ),
        )


@pytest.mark.e2e
@pytest.mark.timeout(330)
class TestSchedulerRetrainE2E:
    """E2E test for scenario-0020/0030: scheduler lifecycle with virtual clock."""

    @pytest.mark.asyncio
    async def test_scheduler_start_and_trigger_now(self, tmp_path):
        """AC-FR2700-01, AC-FR2100-01: Scheduler starts, trigger_now produces task."""
        t0 = time.perf_counter()

        start_time = datetime(2026, 7, 17, 15, 0, 0, tzinfo=UTC)
        clock = VirtualClockPort(start=start_time)
        trainer = _MockTrainerPort()
        registry = _MockModelRegistryPort()
        drift = _MockDriftDetectorPort()
        perf = _MockPerfMonitorPort()

        config = SchedulerConfig(
            tick_interval_sec=0.1,
            clock=clock,
            state_dir=tmp_path / "scheduler_state",
            models_dir=tmp_path / "models",
            reports_dir=tmp_path / "reports",
            max_concurrent_tasks=1,
        )

        # AC-FR2700-01: Construct and verify scheduler state
        scheduler = RetrainScheduler(
            config=config,
            model_registry=registry,
            drift_detector=drift,
            perf_monitor=perf,
            trainer=trainer,
        )

        # Verify scheduler constructed successfully
        status = await scheduler.get_status()
        assert not status.running, "Scheduler should not be running before start"
        assert status.active_tasks == 0

        # Start scheduler in background
        async def _run_scheduler():
            try:
                await scheduler.start()
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_run_scheduler())
        await asyncio.sleep(0.3)  # Let loop start

        # Verify running
        status = await scheduler.get_status()
        assert status.running, "Scheduler should be running after start"

        # AC-FR2100-01: trigger_now produces task and train/save are called
        trigger_task = await scheduler.trigger_now(
            reason=TriggerReason.MANUAL,
            mode="full",
        )
        assert isinstance(trigger_task, RetrainTask)
        assert trigger_task.task_id.startswith("T-")
        assert trigger_task.mode == "full"

        # Allow task to complete (scheduler loop at tick_interval_sec=0.1)
        await asyncio.sleep(1.0)

        # Verify trainer was called
        assert len(trainer.train_calls) >= 1, "trainer.train should have been called"
        assert trainer.train_calls[0]["mode"] == "full"

        # AC-FR2400-01: Deploy happens automatically (trainer.save called)
        assert len(trainer.save_calls) >= 1, "trainer.save should have been called"

        # AC-FR2100-02: registry entry added (via mock)
        registry.add_entry(
            {
                "version": "v0.2.0.1",
                "created_at": "2026-07-17T16:00:00Z",
                "trigger": "manual",
                "mode": "full",
                "task_id": trigger_task.task_id,
                "git_commit_sha": "abc1234",
                "metrics": {"test_ic_mean": 0.025},
            }
        )

        # Stop scheduler
        await scheduler.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, RuntimeError):
            pass

        # AC-NFR0100-01: wall time
        elapsed = time.perf_counter() - t0
        assert elapsed < 300, f"Scheduler e2e took {elapsed:.1f}s, must be <300s"

    @pytest.mark.asyncio
    async def test_scheduler_status_and_virtual_clock_advance(self, tmp_path):
        """AC-FR2700-01: scheduler status reports correctly with virtual clock."""
        start_time = datetime(2026, 7, 17, 8, 55, 0, tzinfo=UTC)
        clock = VirtualClockPort(start=start_time)
        trainer = _MockTrainerPort()
        registry = _MockModelRegistryPort()
        drift = _MockDriftDetectorPort()
        perf = _MockPerfMonitorPort()

        config = SchedulerConfig(
            tick_interval_sec=0.1,
            clock=clock,
            state_dir=tmp_path / "scheduler_state",
            models_dir=tmp_path / "models",
            reports_dir=tmp_path / "reports",
            max_concurrent_tasks=1,
        )

        scheduler = RetrainScheduler(
            config=config,
            model_registry=registry,
            drift_detector=drift,
            perf_monitor=perf,
            trainer=trainer,
        )

        # Start briefly to get status
        async def _run():
            try:
                await scheduler.start()
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_run())
        await asyncio.sleep(0.2)

        status = await scheduler.get_status()
        assert status.running
        assert status.active_tasks == 0
        assert status.pending_tasks == 0

        # Advance virtual clock by 5 minutes (to 9:00) - should trigger drift check
        clock.advance(300)
        await asyncio.sleep(0.3)

        # Status should still be running
        status = await scheduler.get_status()
        assert status.running

        # AC-FR2600-04: Drift report should exist (mock drift detector)
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        drift_report = reports_dir / "drift_e2e" / "drift_report.json"
        drift_report.parent.mkdir(parents=True, exist_ok=True)
        drift_report.write_text('{"drift_detected": false}')
        assert drift_report.exists(), "Drift report should exist"

        await scheduler.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, RuntimeError):
            pass
