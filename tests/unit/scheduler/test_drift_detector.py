"""Unit tests for FR-2600: drift detection and retrain decision.

AC coverage: AC-FR2600-01 (light drift), AC-FR2600-02 (moderate drift →
incremental), AC-FR2600-03 (strong drift → full), AC-FR2600-04 (report
output — per-feature stats in DriftDecision).
"""

from __future__ import annotations

import polars as pl
import pytest

from trader_off.scheduler.core import SchedulerConfig

# ---------------------------------------------------------------------------
# Helpers — build mock PSI / KS DataFrames
# ---------------------------------------------------------------------------


def _make_psi_df(
    n_features: int = 20,
    high_count: int = 0,
    high_psi: float = 0.25,
    mid_count: int = 0,
    mid_psi: float = 0.15,
    low_psi: float = 0.03,
) -> pl.DataFrame:
    """Build a PSI result DataFrame with controlled drift counts.

    Args:
        n_features: Total number of features.
        high_count: Number of features with PSI above threshold.
        high_psi: PSI value for 'high' features.
        mid_count: Number of features with PSI in moderate range.
        mid_psi: PSI value for 'mid' features.
        low_psi: PSI value for remaining features.

    Returns:
        DataFrame with columns: feature, psi, is_drift.
    """
    records = []
    idx = 0
    for i in range(high_count):
        records.append({"feature": f"f_{idx}", "psi": high_psi, "is_drift": True})
        idx += 1
    for i in range(mid_count):
        records.append({"feature": f"f_{idx}", "psi": mid_psi, "is_drift": True})
        idx += 1
    remaining = n_features - idx
    for i in range(remaining):
        records.append({"feature": f"f_{idx}", "psi": low_psi, "is_drift": False})
        idx += 1
    return pl.DataFrame(records)


def _make_ks_df(
    n_features: int = 20,
    drift_count: int = 0,
    drift_pvalue: float = 0.01,
    ok_pvalue: float = 0.5,
) -> pl.DataFrame:
    """Build a KS result DataFrame with controlled drift counts.

    Args:
        n_features: Total number of features.
        drift_count: Number of features with p-value below threshold.
        drift_pvalue: P-value for 'drift' features.
        ok_pvalue: P-value for non-drift features.

    Returns:
        DataFrame with columns: feature, ks_statistic, p_value, is_drift.
    """
    records = []
    for i in range(drift_count):
        records.append(
            {
                "feature": f"f_{i}",
                "ks_statistic": 0.45,
                "p_value": drift_pvalue,
                "is_drift": True,
            }
        )
    for i in range(drift_count, n_features):
        records.append(
            {
                "feature": f"f_{i}",
                "ks_statistic": 0.08,
                "p_value": ok_pvalue,
                "is_drift": False,
            }
        )
    return pl.DataFrame(records)


# ---------------------------------------------------------------------------
# AC-FR2600-01: Light drift (not triggered)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2600_01_light_drift():
    """AC-FR2600-01: 4 features PSI>0.1, 2 KS p<0.05 → should_retrain=False, light_drift."""
    from trader_off.scheduler.drift.detector import DriftDetector

    config = SchedulerConfig(psi_threshold=0.2, ks_pvalue_threshold=0.05, psi_strong=0.5)

    # 4 features with PSI between 0.1 and 0.2, 16 below 0.1
    # 2 features with KS p < 0.05, 18 above 0.05
    def mock_psi(*args, **kwargs):
        return _make_psi_df(
            n_features=20,
            mid_count=4,
            mid_psi=0.15,
            low_psi=0.03,
        )

    def mock_ks(*args, **kwargs):
        return _make_ks_df(n_features=20, drift_count=2, drift_pvalue=0.03)

    detector = DriftDetector(config, psi_fn=mock_psi, ks_fn=mock_ks)
    decision = detector.evaluate()

    assert decision.should_retrain is False
    assert "light" in decision.reason


# ---------------------------------------------------------------------------
# AC-FR2600-02: Moderate drift → incremental retrain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2600_02_moderate_drift_incremental():
    """AC-FR2600-02: 1 PSI>0.2 + 6 KS p<0.05 → should_retrain=True, mode=incremental."""
    from trader_off.scheduler.drift.detector import DriftDetector

    config = SchedulerConfig(psi_threshold=0.2, ks_pvalue_threshold=0.05, psi_strong=0.5)

    # 1 feature with PSI > 0.2, 19 below
    # 6 features with KS p < 0.05
    def mock_psi(*args, **kwargs):
        return _make_psi_df(
            n_features=20,
            high_count=1,
            high_psi=0.25,
            low_psi=0.03,
        )

    def mock_ks(*args, **kwargs):
        return _make_ks_df(n_features=20, drift_count=6, drift_pvalue=0.02)

    detector = DriftDetector(config, psi_fn=mock_psi, ks_fn=mock_ks)
    decision = detector.evaluate()

    assert decision.should_retrain is True
    assert decision.suggested_mode == "incremental"
    assert "moderate" in decision.reason


@pytest.mark.unit
def test_ac_fr2600_02_moderate_drift_ks_only():
    """AC-FR2600-02 variant: only KS drift (5 features < 0.05) triggers moderate."""
    from trader_off.scheduler.drift.detector import DriftDetector

    config = SchedulerConfig(psi_threshold=0.2, ks_pvalue_threshold=0.05, psi_strong=0.5)

    def mock_psi(*args, **kwargs):
        return _make_psi_df(n_features=20, low_psi=0.03)

    def mock_ks(*args, **kwargs):
        return _make_ks_df(n_features=20, drift_count=5, drift_pvalue=0.02)

    detector = DriftDetector(config, psi_fn=mock_psi, ks_fn=mock_ks)
    decision = detector.evaluate()

    assert decision.should_retrain is True
    assert decision.suggested_mode == "incremental"


# ---------------------------------------------------------------------------
# AC-FR2600-03: Strong drift → full retrain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2600_03_strong_drift_full():
    """AC-FR2600-03: 4 PSI>0.5 → should_retrain=True, mode=full, strong_drift."""
    from trader_off.scheduler.drift.detector import DriftDetector

    config = SchedulerConfig(psi_threshold=0.2, ks_pvalue_threshold=0.05, psi_strong=0.5)

    # 4 features with PSI > 0.5
    def mock_psi(*args, **kwargs):
        return _make_psi_df(
            n_features=20,
            high_count=4,
            high_psi=0.55,
            low_psi=0.03,
        )

    def mock_ks(*args, **kwargs):
        return _make_ks_df(n_features=20, drift_count=0)

    detector = DriftDetector(config, psi_fn=mock_psi, ks_fn=mock_ks)
    decision = detector.evaluate()

    assert decision.should_retrain is True
    assert decision.suggested_mode == "full"
    assert "strong" in decision.reason


# ---------------------------------------------------------------------------
# No trigger case (ok)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2600_no_drift_ok():
    """FR-2600: No drift → should_retrain=False, reason=ok."""
    from trader_off.scheduler.drift.detector import DriftDetector

    config = SchedulerConfig(psi_threshold=0.2, ks_pvalue_threshold=0.05, psi_strong=0.5)

    def mock_psi(*args, **kwargs):
        return _make_psi_df(n_features=20, low_psi=0.02)

    def mock_ks(*args, **kwargs):
        return _make_ks_df(n_features=20, drift_count=0)

    detector = DriftDetector(config, psi_fn=mock_psi, ks_fn=mock_ks)
    decision = detector.evaluate()

    assert decision.should_retrain is False
    assert decision.reason == "ok"


# ---------------------------------------------------------------------------
# AC-FR2600-04: per_feature_stats DataFrame
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2600_04_per_feature_stats():
    """AC-FR2600-04: DriftDecision contains per_feature_stats with merged PSI+KS data."""
    from trader_off.scheduler.drift.detector import DriftDetector

    config = SchedulerConfig(psi_threshold=0.2, ks_pvalue_threshold=0.05, psi_strong=0.5)

    def mock_psi(*args, **kwargs):
        return _make_psi_df(n_features=5, high_count=1, high_psi=0.25, low_psi=0.03)

    def mock_ks(*args, **kwargs):
        return _make_ks_df(n_features=5, drift_count=2, drift_pvalue=0.02)

    detector = DriftDetector(config, psi_fn=mock_psi, ks_fn=mock_ks)
    decision = detector.evaluate()

    # per_feature_stats should be a DataFrame with merged columns
    stats = decision.per_feature_stats
    assert isinstance(stats, pl.DataFrame)
    assert len(stats) == 5
    # Should contain PSI and KS columns
    assert "psi" in stats.columns
    assert "p_value" in stats.columns or "ks_statistic" in stats.columns


# ---------------------------------------------------------------------------
# Priority: strong > moderate > light
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr2600_priority_strong_wins_over_moderate():
    """FR-2600: When both strong and moderate conditions are met, strong wins (full mode)."""
    from trader_off.scheduler.drift.detector import DriftDetector

    config = SchedulerConfig(psi_threshold=0.2, ks_pvalue_threshold=0.05, psi_strong=0.5)

    # Both strong PSI (>0.5, 3 features) and moderate KS (6 < 0.05)
    def mock_psi(*args, **kwargs):
        return _make_psi_df(
            n_features=20,
            high_count=3,
            high_psi=0.55,
            low_psi=0.03,
        )

    def mock_ks(*args, **kwargs):
        return _make_ks_df(n_features=20, drift_count=6, drift_pvalue=0.02)

    detector = DriftDetector(config, psi_fn=mock_psi, ks_fn=mock_ks)
    decision = detector.evaluate()

    assert decision.should_retrain is True
    assert decision.suggested_mode == "full"
    assert "strong" in decision.reason
