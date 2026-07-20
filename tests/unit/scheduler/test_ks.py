"""Unit tests for FR-1800: KS drift detection.

AC coverage: AC-FR1800-01, AC-FR1800-02, AC-FR1800-03.

Tests validate:
- KS two-sample test using scipy.stats.ks_2samp
- P-value behavior for identical vs shifted distributions
- Feature-wise batch KS computation
- NaN feature column handling with WARNING logging
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl
import pytest
from scipy import stats

from trader_off.scheduler.drift.result import DriftResult

# ---------------------------------------------------------------------------
# Ground Truth helper
# ---------------------------------------------------------------------------


def _scipy_ks_pvalue(baseline: np.ndarray, current: np.ndarray) -> float:
    """Reference: scipy.stats.ks_2samp p-value (Ground Truth)."""
    result = stats.ks_2samp(baseline, current)
    return float(result.pvalue)


def _scipy_ks_statistic(baseline: np.ndarray, current: np.ndarray) -> float:
    """Reference: scipy.stats.ks_2samp statistic (Ground Truth)."""
    result = stats.ks_2samp(baseline, current)
    return float(result.statistic)


# ---------------------------------------------------------------------------
# AC-FR1800-01: Same distribution → p-value > 0.05
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1800_01_same_distribution():
    """AC-FR1800-01: Two samples from same distribution (seed=42) → p-value > 0.05.

    Uses scipy.stats.ks_2samp as Ground Truth reference.
    """
    from trader_off.scheduler.drift.ks import compute_ks_pvalue

    rng = np.random.default_rng(42)
    baseline = rng.normal(0, 1, 1000)
    current = rng.normal(0, 1, 1000)

    p_value = compute_ks_pvalue(baseline, current)
    ref_p_value = _scipy_ks_pvalue(baseline, current)

    # Should match scipy reference
    assert p_value == pytest.approx(ref_p_value, rel=1e-10), (
        f"compute_ks_pvalue({p_value}) should match scipy reference ({ref_p_value})"
    )

    # p-value > 0.05: cannot reject null hypothesis of same distribution
    assert p_value > 0.05, f"Expected p-value > 0.05 for same distribution, got {p_value}"


# ---------------------------------------------------------------------------
# AC-FR1800-02: Mean shift 2σ → p-value < 0.001
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1800_02_shifted_distribution():
    """AC-FR1800-02: Mean shifted by 2σ → p-value < 0.001.

    The KS test should strongly reject the null hypothesis when
    distributions differ significantly.
    """
    from trader_off.scheduler.drift.ks import compute_ks_pvalue

    rng = np.random.default_rng(42)
    baseline = rng.normal(0, 1, 1000)
    current = rng.normal(2, 1, 1000)

    p_value = compute_ks_pvalue(baseline, current)
    ref_p_value = _scipy_ks_pvalue(baseline, current)

    # Should match scipy reference
    assert p_value == pytest.approx(ref_p_value, rel=1e-10), (
        f"compute_ks_pvalue({p_value}) should match scipy reference ({ref_p_value})"
    )

    # p-value < 0.001: strongly reject same-distribution null hypothesis
    assert p_value < 0.001, f"Expected p-value < 0.001 for 2σ shift, got {p_value}"


# ---------------------------------------------------------------------------
# AC-FR1800-02b: Additional shift scenarios for coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1800_02b_moderate_shift():
    """Supplementary: Small shift (0.2σ, N=100) → p-value between 0.001 and 0.5.

    With smaller sample size, the KS test is less powerful and yields a
    moderate p-value for a weak signal.
    """
    from trader_off.scheduler.drift.ks import compute_ks_pvalue

    rng = np.random.default_rng(42)
    baseline = rng.normal(0, 1, 100)
    current = rng.normal(0.2, 1, 100)

    p_value = compute_ks_pvalue(baseline, current)
    ref_p_value = _scipy_ks_pvalue(baseline, current)

    assert p_value == pytest.approx(ref_p_value, rel=1e-10)
    assert p_value > 0.001, f"Small shift with N=100 should not be as extreme, got {p_value}"
    assert p_value < 0.5, f"Small shift should still be somewhat detectable, got {p_value}"


@pytest.mark.unit
def test_ac_fr1800_02c_exact_same_arrays():
    """Supplementary: Exactly identical arrays → p-value = 1.0."""
    from trader_off.scheduler.drift.ks import compute_ks_pvalue

    baseline = np.arange(1, 101, dtype=np.float64)
    current = np.arange(1, 101, dtype=np.float64)

    p_value = compute_ks_pvalue(baseline, current)
    ref_p_value = _scipy_ks_pvalue(baseline, current)

    assert p_value == pytest.approx(ref_p_value, rel=1e-10)
    assert p_value == pytest.approx(1.0, abs=1e-9), (
        f"Identical arrays should give p-value ≈ 1.0, got {p_value}"
    )


# ---------------------------------------------------------------------------
# AC-FR1800-03: Full NaN baseline → ks_statistic=0.0, p_value=1.0, WARNING
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1800_03_nan_baseline(caplog: pytest.LogCaptureFixture):
    """AC-FR1800-03: Feature with all-NaN baseline → ks_statistic=0.0,
    p_value=1.0, is_drift=False, WARNING logged.
    """
    from trader_off.scheduler.drift.ks import compute_feature_ks

    baseline_df = pl.DataFrame(
        {
            "X": [np.nan] * 5,
            "Y": [2.0, 4.0, 6.0, 8.0, 10.0],
        }
    )
    current_df = pl.DataFrame(
        {
            "X": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Y": [3.0, 5.0, 7.0, 9.0, 11.0],
        }
    )

    with caplog.at_level(logging.WARNING):
        result = compute_feature_ks(baseline_df, current_df, ["X", "Y"])

    # Validate result schema
    assert set(result.columns) == {"feature", "ks_statistic", "p_value", "is_drift"}, (
        f"Expected columns {{feature, ks_statistic, p_value, is_drift}}, got {set(result.columns)}"
    )

    # NaN baseline feature X should have (0.0, 1.0, False)
    x_row = result.filter(pl.col("feature") == "X")
    assert x_row["ks_statistic"].item() == 0.0, (
        f"NaN baseline should have ks_statistic=0.0, got {x_row['ks_statistic'].item()}"
    )
    assert x_row["p_value"].item() == 1.0, (
        f"NaN baseline should have p_value=1.0, got {x_row['p_value'].item()}"
    )
    assert not x_row["is_drift"].item(), "NaN baseline should not be marked as drift"

    # WARNING log should be present
    assert "no samples" in caplog.text.lower() or "X" in caplog.text, (
        f"Expected WARNING about feature X with no samples, got: {caplog.text}"
    )


# ---------------------------------------------------------------------------
# AC-FR1800-03b: Current all NaN feature
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1800_03b_nan_current(caplog: pytest.LogCaptureFixture):
    """Supplementary: Feature with all-NaN current values → handled gracefully."""
    from trader_off.scheduler.drift.ks import compute_feature_ks

    baseline_df = pl.DataFrame(
        {
            "A": [1.0, 2.0, 3.0, 4.0, 5.0],
            "B": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    current_df = pl.DataFrame(
        {
            "A": [np.nan] * 5,
            "B": [1.5, 2.5, 3.5, 4.5, 5.5],
        }
    )

    with caplog.at_level(logging.WARNING):
        result = compute_feature_ks(baseline_df, current_df, ["A", "B"])

    a_row = result.filter(pl.col("feature") == "A")
    assert a_row["ks_statistic"].item() == 0.0
    assert a_row["p_value"].item() == 1.0
    assert not a_row["is_drift"].item()

    assert "no samples" in caplog.text.lower() or "A" in caplog.text


# ---------------------------------------------------------------------------
# AC-FR1800-03c: Both baseline and current NaN
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1800_03c_both_nan(caplog: pytest.LogCaptureFixture):
    """Supplementary: Both baseline and current all NaN → handled gracefully."""
    from trader_off.scheduler.drift.ks import compute_feature_ks

    baseline_df = pl.DataFrame({"X": [np.nan] * 5, "Y": [1.0] * 5})
    current_df = pl.DataFrame({"X": [np.nan] * 5, "Y": [2.0] * 5})

    result = compute_feature_ks(baseline_df, current_df, ["X", "Y"])

    x_row = result.filter(pl.col("feature") == "X")
    assert x_row["ks_statistic"].item() == 0.0
    assert x_row["p_value"].item() == 1.0
    assert not x_row["is_drift"].item()

    # Feature Y should still compute properly
    y_row = result.filter(pl.col("feature") == "Y")
    assert y_row["ks_statistic"].item() >= 0.0
    assert 0.0 <= y_row["p_value"].item() <= 1.0


# ---------------------------------------------------------------------------
# detect_ks wrapper: returns DriftResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_detect_ks_below_threshold():
    """detect_ks with identical distributions → high p-value, is_drift=False.

    When p-value > threshold, distributions are considered not drifted.
    """
    from trader_off.scheduler.drift.ks import detect_ks

    rng = np.random.default_rng(42)
    reference = rng.normal(0, 1, 1000)
    current = rng.normal(0, 1, 1000)

    result = detect_ks(reference, current, threshold=0.05)

    assert isinstance(result, DriftResult)
    assert result.method == "ks"
    assert result.score >= 0.0  # KS statistic is always ≥ 0
    assert result.threshold == 0.05
    # For same distribution, p-value > 0.05 → not drift
    assert result.is_drift is False
    # KS uses no bin_edges — set to empty list
    assert isinstance(result.bin_edges, list)


@pytest.mark.unit
def test_detect_ks_above_threshold():
    """detect_ks with shifted distribution → low p-value, is_drift=True.

    When p-value < threshold, drift is detected.
    """
    from trader_off.scheduler.drift.ks import detect_ks

    rng = np.random.default_rng(42)
    reference = rng.normal(0, 1, 1000)
    current = rng.normal(2, 1, 1000)

    result = detect_ks(reference, current, threshold=0.05)

    assert isinstance(result, DriftResult)
    assert result.method == "ks"
    assert result.score >= 0.0
    assert result.threshold == 0.05
    # For 2σ shift, p-value < 0.001 < 0.05 → drift
    assert result.is_drift is True


@pytest.mark.unit
def test_detect_ks_custom_threshold():
    """detect_ks with tiny shift and permissive threshold → not detected as drift."""
    from trader_off.scheduler.drift.ks import detect_ks

    rng = np.random.default_rng(42)
    reference = rng.normal(0, 1, 30)
    current = rng.normal(0, 1, 30)

    # Same distribution with small N → p-value should be well above 0.001
    result = detect_ks(reference, current, threshold=0.001)

    assert result.method == "ks"
    assert result.threshold == 0.001
    # Same distribution → p-value >> 0.001
    assert result.is_drift is False


# ---------------------------------------------------------------------------
# compute_feature_ks: batch feature KS computation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_feature_ks_batch():
    """compute_feature_ks returns correct schema for multiple features."""
    from trader_off.scheduler.drift.ks import compute_feature_ks

    rng = np.random.default_rng(42)
    n_samples = 100
    feature_names = [f"f{i}" for i in range(10)]

    baseline_data: dict[str, np.ndarray] = {}
    current_data: dict[str, np.ndarray] = {}
    for i, f in enumerate(feature_names):
        baseline_data[f] = rng.normal(0, 1, n_samples)
        if i < 3:
            current_data[f] = rng.normal(2, 1, n_samples)  # large shift
        else:
            current_data[f] = rng.normal(0, 1, n_samples)  # no shift

    baseline_df = pl.DataFrame(baseline_data)
    current_df = pl.DataFrame(current_data)

    result = compute_feature_ks(baseline_df, current_df, feature_names)

    assert len(result) == 10
    assert set(result.columns) == {"feature", "ks_statistic", "p_value", "is_drift"}

    # Shifted features should have drift=True (p-value < 0.05)
    shifted = result.filter(pl.col("feature").is_in([f"f{i}" for i in range(3)]))
    unshifted = result.filter(pl.col("feature").is_in([f"f{i}" for i in range(3, 10)]))

    assert all(shifted["is_drift"].to_list()), "Shifted features should be marked as drift"
    # Not all unshifted features may avoid drift due to random chance, but
    # the p-values should be much higher on average
    shifted_p = shifted["p_value"].mean()
    unshifted_p = unshifted["p_value"].mean()
    # AC-FR1800-02: shifted features must have lower p-values (drift detected)
    assert shifted_p is not None
    # AC-FR1800-01: unshifted features must have higher p-values (no drift)
    assert unshifted_p is not None
    assert shifted_p < unshifted_p, (
        f"Shifted features should have lower p-values "
        f"(shifted mean p={shifted_p}, unshifted mean p={unshifted_p})"
    )


# ---------------------------------------------------------------------------
# Error path coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_ks_pvalue_raises_on_empty_input():
    """compute_ks_pvalue raises ValueError when given empty arrays."""
    from trader_off.scheduler.drift.ks import compute_ks_pvalue

    baseline = np.array([], dtype=np.float64)
    current = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    with pytest.raises(ValueError, match="finite"):
        compute_ks_pvalue(baseline, current)


@pytest.mark.unit
def test_compute_ks_pvalue_raises_on_all_nan():
    """compute_ks_pvalue raises ValueError when all values are NaN."""
    from trader_off.scheduler.drift.ks import compute_ks_pvalue

    baseline = np.array([np.nan, np.nan], dtype=np.float64)
    current = np.array([1.0, 2.0], dtype=np.float64)
    with pytest.raises(ValueError, match="finite"):
        compute_ks_pvalue(baseline, current)


@pytest.mark.unit
def test_compute_feature_ks_empty_feature_cols():
    """compute_feature_ks with empty feature list returns empty DataFrame."""
    from trader_off.scheduler.drift.ks import compute_feature_ks

    baseline_df = pl.DataFrame({"A": [1.0]})
    current_df = pl.DataFrame({"A": [1.0]})

    result = compute_feature_ks(baseline_df, current_df, [])

    assert len(result) == 0
    assert set(result.columns) == {"feature", "ks_statistic", "p_value", "is_drift"}


@pytest.mark.unit
def test_detect_ks_raises_on_empty_input():
    """detect_ks raises ValueError when given empty arrays."""
    from trader_off.scheduler.drift.ks import detect_ks

    reference = np.array([], dtype=np.float64)
    current = np.array([1.0, 2.0], dtype=np.float64)
    with pytest.raises(ValueError, match="finite"):
        detect_ks(reference, current)


@pytest.mark.unit
def test_detect_ks_raises_on_all_nan():
    """detect_ks raises ValueError when all values are NaN."""
    from trader_off.scheduler.drift.ks import detect_ks

    reference = np.array([np.nan, np.nan], dtype=np.float64)
    current = np.array([1.0, 2.0], dtype=np.float64)
    with pytest.raises(ValueError, match="finite"):
        detect_ks(reference, current)
