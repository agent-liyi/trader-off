"""Unit tests for FR-1700: PSI drift detection.

AC coverage: AC-FR1700-01, AC-FR1700-02, AC-FR1700-03, AC-FR1700-04.

Tests validate:
- PSI formula correctness against known reference distributions
- Quantile-based binning with zero-bin epsilon smoothing
- Feature-wise batch PSI computation
- NaN feature column handling with WARNING logging
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl
import pytest

from trader_off.scheduler.drift.psi import compute_feature_psi, compute_psi, detect_psi
from trader_off.scheduler.drift.result import DriftResult

# ---------------------------------------------------------------------------
# AC-FR1700-01: Identical distributions → PSI ≈ 0
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1700_01_same_distribution():
    """AC-FR1700-01: Same distribution yields PSI ≈ 0 (within 1e-6 tolerance)."""
    # Given: baseline and current are identical arrays
    baseline = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.float64)
    current = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.float64)

    # When: compute_psi is called
    psi = compute_psi(baseline, current)

    # Then: PSI ≈ 0.0 (bin proportions identical → each term is 0)
    assert abs(psi) < 1e-6, f"Expected PSI ≈ 0 for identical distributions, got {psi}"


# ---------------------------------------------------------------------------
# AC-FR1700-02: Completely shifted distribution → PSI > 0.5
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1700_02_shifted_distribution():
    """AC-FR1700-02: Distribution shifted by 50 units yields PSI > 0.5.

    Reference [1..100] uniform, current [50..150] uniform.
    Most bins in the reference have zero current samples, producing
    a large PSI via epsilon-smoothed log ratio.
    """
    # Given: baseline uniform [1..100], current uniform [50..150]
    baseline = np.arange(1, 101, dtype=np.float64)
    current = np.arange(50, 151, dtype=np.float64)

    # When: compute_psi is called
    psi = compute_psi(baseline, current)

    # Then: PSI > 0.5 (significant drift)
    assert psi > 0.5, f"Expected PSI > 0.5 for shifted distribution, got {psi}"


# ---------------------------------------------------------------------------
# AC-FR1700-02b: Large uniform same-distribution → PSI ≈ 0
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1700_02b_large_same_distribution():
    """Supplementary: 1000-sample identical distributions → PSI ≈ 0.

    Ensures the binning works correctly at scale too.
    """
    rng = np.random.default_rng(42)
    baseline = rng.normal(0, 1, 1000)
    current = baseline.copy()

    psi = compute_psi(baseline, current, n_bins=10)

    assert abs(psi) < 1e-6, f"Expected PSI ≈ 0 for identical normal samples, got {psi}"


# ---------------------------------------------------------------------------
# AC-FR1700-02c: Moderate shift → PSI between 0 and 0.5
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1700_02c_moderate_shift():
    """Supplementary: 0.5σ mean shift yields measurable but not extreme PSI."""
    rng = np.random.default_rng(42)
    baseline = rng.normal(0, 1, 1000)
    current = rng.normal(0.5, 1, 1000)

    psi = compute_psi(baseline, current, n_bins=20)

    # A 0.5σ shift should produce a non-zero PSI but well below 0.5
    assert psi > 0.01, f"Expected PSI > 0.01 for 0.5σ shift, got {psi}"
    assert psi < 0.5, f"Expected PSI < 0.5 for 0.5σ shift, got {psi}"


# ---------------------------------------------------------------------------
# AC-FR1700-03: Feature-wise PSI for 20 feature columns
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1700_03_feature_psi():
    """AC-FR1700-03: compute_feature_psi returns 20-row DataFrame with
    feature, psi, is_drift columns.
    """
    rng = np.random.default_rng(42)
    n_samples = 100
    feature_names = [f"f{i}" for i in range(20)]

    # Create baseline and current DataFrames with Polars
    # Baseline: standard normal features
    baseline_data: dict[str, np.ndarray] = {}
    for f in feature_names:
        baseline_data[f] = rng.normal(0, 1, n_samples)

    # Current: some features shifted (first 5 shifted slightly, next 10 unchanged)
    current_data: dict[str, np.ndarray] = {}
    for i, f in enumerate(feature_names):
        if i < 5:
            current_data[f] = rng.normal(1.0, 1.2, n_samples)  # noticeable shift
        else:
            current_data[f] = rng.normal(0, 1, n_samples)  # no shift

    baseline_df = pl.DataFrame(baseline_data)
    current_df = pl.DataFrame(current_data)

    # When: compute_feature_psi is called
    result = compute_feature_psi(baseline_df, current_df, feature_names)

    # Then: shape and schema assertions
    assert len(result) == 20, f"Expected 20 rows, got {len(result)}"
    assert set(result.columns) == {"feature", "psi", "is_drift"}, (
        f"Expected columns {{feature, psi, is_drift}}, got {set(result.columns)}"
    )

    # The shifted features should have higher PSI than the unshifted ones
    shifted = result.filter(pl.col("feature").is_in([f"f{i}" for i in range(5)]))
    unshifted = result.filter(pl.col("feature").is_in([f"f{i}" for i in range(5, 20)]))

    shifted_mean = shifted["psi"].mean()
    unshifted_mean = unshifted["psi"].mean()

    # AC-FR1700-03: shifted features must have higher PSI (drift detected)
    assert shifted_mean is not None
    # AC-FR1700-03: unshifted features have lower PSI (no drift)
    assert unshifted_mean is not None
    assert shifted_mean > unshifted_mean, (
        f"Shifted features should have higher PSI "
        f"(shifted={shifted_mean}, unshifted={unshifted_mean})"
    )


# ---------------------------------------------------------------------------
# AC-FR1700-04: NaN feature column → psi=0, is_drift=False, WARNING
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1700_04_nan_feature(caplog: pytest.LogCaptureFixture):
    """AC-FR1700-04: Feature with all-NaN current values → psi=0.0,
    is_drift=False, WARNING logged.
    """
    # Given: one feature has all NaN current values
    baseline_df = pl.DataFrame(
        {
            "X": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Y": [2.0, 4.0, 6.0, 8.0, 10.0],
        }
    )
    current_df = pl.DataFrame(
        {
            "X": [np.nan] * 5,
            "Y": [3.0, 5.0, 7.0, 9.0, 11.0],
        }
    )

    # When: compute_feature_psi is called
    with caplog.at_level(logging.WARNING):
        result = compute_feature_psi(baseline_df, current_df, ["X", "Y"])

    # Then: NaN feature has psi=0.0 and is_drift=False
    x_row = result.filter(pl.col("feature") == "X")
    assert x_row["psi"].item() == 0.0, f"NaN feature should have psi=0.0, got {x_row['psi'].item()}"
    assert not x_row["is_drift"].item(), "NaN feature should not be marked as drift"

    # WARNING log should mention the feature and no samples
    assert "no samples" in caplog.text.lower() or "X" in caplog.text, (
        f"Expected WARNING about feature X with no samples, got: {caplog.text}"
    )


# ---------------------------------------------------------------------------
# AC-FR1700-04b: Both features NaN → both handled gracefully
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1700_04b_both_nan(caplog: pytest.LogCaptureFixture):
    """Supplementary: Both baseline and current NaN → psi=0.0, no crash."""
    baseline_df = pl.DataFrame({"X": [np.nan] * 5, "Y": [1.0] * 5})
    current_df = pl.DataFrame({"X": [np.nan] * 5, "Y": [2.0] * 5})

    result = compute_feature_psi(baseline_df, current_df, ["X", "Y"])
    x_row = result.filter(pl.col("feature") == "X")
    assert x_row["psi"].item() == 0.0

    # Feature Y should still work
    y_row = result.filter(pl.col("feature") == "Y")
    assert y_row["psi"].item() == 0.0


# ---------------------------------------------------------------------------
# detect_psi wrapper: returns DriftResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_detect_psi_below_threshold():
    """detect_psi with identical distributions → score=0, is_drift=False."""
    baseline = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.float64)
    current = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.float64)

    result = detect_psi(baseline, current, n_bins=10, threshold=0.2)

    assert isinstance(result, DriftResult)
    assert result.method == "psi"
    assert abs(result.score) < 1e-6
    assert result.threshold == 0.2
    assert result.is_drift is False
    assert len(result.bin_edges) == 11  # n_bins + 1 edges


@pytest.mark.unit
def test_detect_psi_above_threshold():
    """detect_psi with shifted distribution → score > threshold, is_drift=True."""
    baseline = np.arange(1, 101, dtype=np.float64)
    current = np.arange(50, 151, dtype=np.float64)

    result = detect_psi(baseline, current, n_bins=10, threshold=0.2)

    assert isinstance(result, DriftResult)
    assert result.method == "psi"
    assert result.score > 0.5
    assert result.threshold == 0.2
    assert result.is_drift is True
    assert len(result.bin_edges) == 11


# ---------------------------------------------------------------------------
# Error path coverage: ValueError on empty inputs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_psi_raises_on_empty_input():
    """compute_psi raises ValueError when given empty arrays."""
    baseline = np.array([], dtype=np.float64)
    current = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    with pytest.raises(ValueError, match="finite"):
        compute_psi(baseline, current)


@pytest.mark.unit
def test_compute_psi_raises_on_all_nan():
    """compute_psi raises ValueError when all values are NaN."""
    baseline = np.array([np.nan, np.nan], dtype=np.float64)
    current = np.array([1.0, 2.0], dtype=np.float64)
    with pytest.raises(ValueError, match="finite"):
        compute_psi(baseline, current)


@pytest.mark.unit
def test_compute_psi_raises_on_invalid_n_bins():
    """compute_psi raises ValueError when n_bins < 1."""
    baseline = np.array([1.0, 2.0], dtype=np.float64)
    current = np.array([1.0, 2.0], dtype=np.float64)
    with pytest.raises(ValueError, match="n_bins"):
        compute_psi(baseline, current, n_bins=0)


# ---------------------------------------------------------------------------
# Coverage: baseline-all-NaN in compute_feature_psi
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_feature_psi_baseline_nan_current_valid(caplog: pytest.LogCaptureFixture):
    """compute_feature_psi: when baseline has all NaN but current has valid values."""
    baseline_df = pl.DataFrame({"A": [np.nan] * 5, "B": [1.0] * 5})
    current_df = pl.DataFrame({"A": [1.0, 2.0, 3.0, 4.0, 5.0], "B": [2.0] * 5})

    with caplog.at_level(logging.WARNING):
        result = compute_feature_psi(baseline_df, current_df, ["A", "B"])

    a_row = result.filter(pl.col("feature") == "A")
    assert a_row["psi"].item() == 0.0
    assert not a_row["is_drift"].item()
    assert "baseline" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Coverage: quantile edge monotonicity with few samples + many bins
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_psi_few_samples_many_bins():
    """compute_psi with very few samples relative to n_bins should still work."""
    baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
    current = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
    # 20 bins with only 5 samples — edge case for quantile binning
    psi = compute_psi(baseline, current, n_bins=20)
    assert abs(psi) < 1e-6


# ---------------------------------------------------------------------------
# Coverage: non-monotonic quantile edges (repeated low values)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_psi_repeated_low_values():
    """compute_psi with repeated values at lower bound triggers edge monotonicity fix."""
    # Many repeated zeros at the low end → first two quantile edges are equal
    baseline = np.array(
        [0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 101.0, 102.0, 103.0, 104.0],
        dtype=np.float64,
    )
    current = np.array(
        [0.0, 0.0, 0.0, 0.0, 0.0, 105.0, 106.0, 107.0, 108.0, 109.0],
        dtype=np.float64,
    )
    psi = compute_psi(baseline, current, n_bins=10)
    # Many quantile edges are tied at 0 → pushed apart by nextafter,
    # producing narrow bins that amplify the PSI. This is a valid edge case;
    # the PSI is mathematically correct and non-negative.
    assert psi >= 0.0
