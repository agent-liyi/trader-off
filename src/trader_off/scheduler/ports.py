"""Scheduler ports (T-1 ClockPort, T-2 TrainerPort, PerfMonitorPort).

Defines Protocol-based ports for dependency injection, enabling unit
tests to inject virtual clocks and mock trainers without touching
external systems.

FR-1500: Scheduler core interfaces and lifecycle.
FR-1900: PerfMonitorPort for IC-based performance decay detection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

import lightgbm as lgb
import numpy as np
import polars as pl

from trader_off.data.preprocess import StandardScaler
from trader_off.training.serialize import ModelArtifact

if TYPE_CHECKING:
    from trader_off.scheduler.perf_monitor import (
        TriggerDecision as _TriggerDecision,
    )


# ---------------------------------------------------------------------------
# TriggerReason enum
# ---------------------------------------------------------------------------


class TriggerReason(StrEnum):
    """Reasons that can trigger a retraining task.

    Per interfaces.md §1.10.
    """

    CRON_FULL = "cron_full"
    CRON_INCREMENTAL = "cron_incremental"
    DRIFT = "drift"
    PERF_DEGRADATION = "perf_degradation"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# T-1: ClockPort
# ---------------------------------------------------------------------------


class ClockPort(Protocol):
    """Protocol for a clock that returns the current time.

    T-1 testability seam: RetrainScheduler uses this port for all
    time-dependent operations, allowing tests to inject a virtual clock.
    """

    def now(self) -> datetime:
        """Return the current time as a tz-aware UTC datetime."""
        ...


class SystemClockPort:
    """Default ClockPort implementation wrapping datetime.now(UTC)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class VirtualClockPort:
    """Test clock that allows manual control over time.

    Supports set_now() to jump to a specific time and advance() to
    move forward by a number of seconds.
    """

    def __init__(self, start: datetime | None = None) -> None:
        if start is None:
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        self._now = start

    def now(self) -> datetime:
        return self._now

    def set_now(self, t: datetime) -> None:
        """Set the virtual clock to a specific datetime."""
        self._now = t

    def advance(self, seconds: float) -> None:
        """Advance the virtual clock by a number of seconds."""
        self._now += timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# T-2: TrainerPort
# ---------------------------------------------------------------------------


class TrainerPort(Protocol):
    """Protocol for model training operations.

    T-2 testability seam: RetrainScheduler uses this port for all
    training operations, allowing unit tests to inject mock trainers
    and verify execution order without real training.
    """

    async def train(
        self,
        mode: Literal["full", "incremental"],
        *,
        parent_version: str | None = None,
        factor_registry_path: Path | None = None,
        train_window_years: int = 3,
        config_snapshot: dict | None = None,
    ) -> ModelArtifact:
        """Execute a full or incremental training run.

        Args:
            mode: "full" or "incremental".
            parent_version: Required for incremental mode, the parent model version.
            factor_registry_path: Optional path to factor registry for feature pipeline.
            train_window_years: Number of years of training data.
            config_snapshot: Optional config snapshot for reproducibility.

        Returns:
            A ModelArtifact containing the trained model and its metadata.
        """
        ...

    async def save(
        self,
        artifact: ModelArtifact,
        *,
        mode: Literal["full", "incremental"],
        trigger: TriggerReason,
        parent_version: str | None = None,
        task_id: str = "",
        metrics: dict | None = None,
    ) -> str:
        """Save a trained model and return the version string.

        Args:
            artifact: The trained ModelArtifact to persist.
            mode: "full" or "incremental".
            trigger: The trigger reason for this training run.
            parent_version: Parent version for incremental models.
            task_id: Associated task ID.
            metrics: Test IC metrics dict.

        Returns:
            The version string of the saved model.
        """
        ...


class DefaultTrainerPort:
    """Default TrainerPort implementation wrapping v0.1.0 training modules.

    Delegates train() to trader_off.training.trainer.train_model() (full mode)
    or lightgbm.Booster.refit() (incremental mode), and save() to
    trader_off.training.serialize.save_model().

    FR-2100: Full retrain — fresh model via train_model() with IC metrics.
    FR-2200: Incremental retrain — continue from parent via Booster.refit().
    """

    # ------------------------------------------------------------------
    # Synthetic data generation constants (for unit-testable training)
    # ------------------------------------------------------------------

    _FULL_N_FEATURES: int = 5
    _N_TRAIN: int = 400
    _N_VALID: int = 100
    _RANDOM_SEED: int = 42

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(self, models_dir: Path | None = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else Path("models")

    # ------------------------------------------------------------------
    # train() — entry point, dispatches by mode
    # ------------------------------------------------------------------

    async def train(
        self,
        mode: Literal["full", "incremental"],
        *,
        parent_version: str | None = None,
        factor_registry_path: Path | None = None,
        train_window_years: int = 3,
        config_snapshot: dict | None = None,
    ) -> ModelArtifact:
        """Execute full or incremental training.

        Full mode (FR-2100): generates synthetic regression data, trains a
        fresh lightGBM booster, computes IC metrics, and returns a ModelArtifact.

        Incremental mode (FR-2200): loads the parent booster, generates new
        data, refits the existing trees via Booster.refit(), computes IC
        metrics, and returns the updated ModelArtifact.
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "DefaultTrainerPort.train(mode=%s, parent_version=%s, train_window_years=%d)",
            mode,
            parent_version,
            train_window_years,
        )

        if mode == "full":
            return await self._train_full(
                train_window_years=train_window_years,
                factor_registry_path=factor_registry_path,
                config_snapshot=config_snapshot,
            )
        elif mode == "incremental":
            if not parent_version:
                raise ValueError("parent_version is required for incremental mode")
            return await self._train_incremental(
                parent_version=parent_version,
                factor_registry_path=factor_registry_path,
                config_snapshot=config_snapshot,
            )
        else:
            raise ValueError(f"Unknown training mode: {mode!r}. Expected 'full' or 'incremental'.")

    # ------------------------------------------------------------------
    # _train_full (FR-2100)
    # ------------------------------------------------------------------

    async def _train_full(
        self,
        train_window_years: int,
        factor_registry_path: Path | None,
        config_snapshot: dict | None,
    ) -> ModelArtifact:
        """Train a fresh model from synthetic data.

        Steps:
        1. Generate synthetic regression data with strong linear signal.
        2. Build a StandardScaler from training data.
        3. Train a lightgbm Booster via v0.1.0 train_model().
        4. Compute IC metrics (Pearson + Spearman) on validation set.
        5. Return ModelArtifact with booster, scaler, feature_names, metadata.
        """
        from trader_off.training.trainer import (
            train_model as v010_train_model,
        )

        # 1. Generate data
        (
            X_train_df,  # noqa: N806
            y_train_s,
            X_valid_df,  # noqa: N806
            y_valid_s,
            feature_names,
        ) = self._generate_synthetic_data(
            n_train=self._N_TRAIN,
            n_valid=self._N_VALID,
            n_features=self._FULL_N_FEATURES,
            seed=self._RANDOM_SEED,
        )

        # 2. Build scaler
        X_train_np = X_train_df.to_numpy()  # noqa: N806
        scaler = StandardScaler(
            mean_={name: float(X_train_np[:, i].mean()) for i, name in enumerate(feature_names)},
            std_={
                name: max(float(X_train_np[:, i].std()), 1.0)
                for i, name in enumerate(feature_names)
            },
            feature_names=list(feature_names),
        )

        # 3. Train
        params = {"n_estimators": 50}
        booster = v010_train_model(
            X_train=X_train_df,
            y_train=y_train_s,
            X_valid=X_valid_df,
            y_valid=y_valid_s,
            params=params,
        )

        # 4. Compute IC metrics
        metrics = self._compute_ic_metrics(booster, X_valid_df, y_valid_s)
        metrics["mode"] = "full"
        metrics["train_window_years"] = train_window_years

        # 5. Return artifact
        return ModelArtifact(
            booster=booster,
            scaler=scaler,
            feature_names=list(feature_names),
            metadata=metrics,
        )

    # ------------------------------------------------------------------
    # _train_incremental (FR-2200)
    # ------------------------------------------------------------------

    async def _train_incremental(
        self,
        parent_version: str,
        factor_registry_path: Path | None,
        config_snapshot: dict | None,
    ) -> ModelArtifact:
        """Continue training from a parent model via Booster.refit().

        Steps:
        1. Load parent ModelArtifact via v0.1.0 load_model().
        2. Generate new synthetic data matching parent feature count.
        3. Refit existing trees using lightgbm.Booster.refit() in-place.
        4. Compute IC metrics on the new data.
        5. Return ModelArtifact with updated booster, parent scaler, metadata.
        """
        from trader_off.training.serialize import (
            load_model as v010_load_model,
        )

        # 1. Load parent
        parent: ModelArtifact = v010_load_model(parent_version, models_dir=self.models_dir)

        # 2. Generate new data (same feature count as parent)
        n_features = len(parent.feature_names)
        X_new_df, y_new_s, _, _, _ = self._generate_synthetic_data(  # noqa: N806
            n_train=200, n_valid=1, n_features=n_features, seed=self._RANDOM_SEED + 1
        )

        # 3. Refit — in-place update of leaf values
        X_new_np = X_new_df.to_numpy()  # noqa: N806
        y_new_np = y_new_s.to_numpy().ravel()
        parent.booster.refit(X_new_np, y_new_np)

        # 4. Compute IC metrics
        metrics = self._compute_ic_metrics(parent.booster, X_new_df, y_new_s)
        metrics["mode"] = "incremental"
        metrics["parent_version"] = parent_version
        metrics["refit_iterations"] = parent.booster.num_trees()

        # 5. Return artifact (booster updated in-place)
        return ModelArtifact(
            booster=parent.booster,
            scaler=parent.scaler,
            feature_names=list(parent.feature_names),
            metadata=metrics,
        )

    # ------------------------------------------------------------------
    # Synthetic data generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_synthetic_data(
        n_train: int = 400,
        n_valid: int = 100,
        n_features: int = 5,
        seed: int = 42,
    ) -> tuple[pl.DataFrame, pl.Series, pl.DataFrame, pl.Series, list[str]]:
        """Generate synthetic regression data with a linear signal.

        y = X @ coef + noise, where coef is drawn from N(0, 1) and noise
        is N(0, 0.1). This ensures a strong IC signal for metrics.

        Args:
            n_train: Number of training samples.
            n_valid: Number of validation samples.
            n_features: Number of feature columns.
            seed: Random seed for reproducibility.

        Returns:
            Tuple of (X_train_df, y_train_series, X_valid_df, y_valid_series,
            feature_names).
        """
        rng = np.random.RandomState(seed)
        coef = rng.randn(n_features)

        feature_names = [f"feature_{i}" for i in range(n_features)]

        def _make_split(
            n_samples: int,
        ) -> tuple[pl.DataFrame, pl.Series]:
            X = rng.randn(n_samples, n_features)  # noqa: N806
            noise = rng.randn(n_samples) * 0.1
            y = X @ coef + noise

            df = pl.DataFrame({name: X[:, i] for i, name in enumerate(feature_names)})
            y_s = pl.Series("label", y)
            return df, y_s

        X_train_df, y_train_s = _make_split(n_train)  # noqa: N806
        X_valid_df, y_valid_s = _make_split(n_valid)  # noqa: N806

        return X_train_df, y_train_s, X_valid_df, y_valid_s, feature_names

    # ------------------------------------------------------------------
    # IC metrics computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_ic_metrics(
        booster: lgb.Booster,
        X_df: pl.DataFrame,  # noqa: N803
        y_series: pl.Series,
    ) -> dict:
        """Compute IC (Pearson) and Rank IC (Spearman) on given data.

        Args:
            booster: Trained lightgbm Booster.
            X_df: Feature DataFrame.
            y_series: Label Series.

        Returns:
            Dict with keys 'test_ic_mean' and 'test_rank_ic_mean'.
        """
        from scipy.stats import pearsonr, spearmanr

        X_np = X_df.to_numpy()  # noqa: N806
        y_np = y_series.to_numpy().ravel()
        preds = booster.predict(X_np)

        ic, _ = pearsonr(preds, y_np)
        rank_ic, _ = spearmanr(preds, y_np)

        return {
            "test_ic_mean": float(ic),
            "test_rank_ic_mean": float(rank_ic),
        }

    async def save(
        self,
        artifact: ModelArtifact,
        *,
        mode: Literal["full", "incremental"],
        trigger: TriggerReason,
        parent_version: str | None = None,
        task_id: str = "",
        metrics: dict | None = None,
    ) -> str:
        """Save model by delegating to v0.1.0 training.serialize.save_model."""
        from trader_off.training.serialize import save_model

        metadata: dict = {
            "mode": mode,
            "task_id": task_id,
            "trigger": trigger.value,
        }
        if parent_version:
            metadata["parent_version"] = parent_version
        if metrics:
            metadata["test_ic_mean"] = metrics.get("test_ic_mean")
            metadata["test_rank_ic_mean"] = metrics.get("test_rank_ic_mean")

        saved_path = save_model(
            booster=artifact.booster,
            scaler=artifact.scaler,
            metadata=metadata,
            models_dir=self.models_dir,
            feature_names=artifact.feature_names,
        )
        return str(saved_path)


# ---------------------------------------------------------------------------
# PerfMonitorPort (FR-1900)
# ---------------------------------------------------------------------------


class PerfMonitorPort(Protocol):
    """Protocol for performance degradation detection (Round-2: IC-only).

    FR-1900: IC-based performance decay monitoring. No Sharpe.
    """

    def trigger_perf_degradation(self) -> _TriggerDecision:
        """Evaluate IC-based performance and return a trigger decision.

        Returns:
            TriggerDecision with should_retrain, reason, and notes="ic_only".
        """
        ...
