"""Dataclasses for drift detection results.

FR-1700: PSI drift detection result type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DriftResult:
    """Result of a single drift detection method.

    Fields:
        method: The detection method used (e.g. "psi", "ks").
        score: The computed drift score (PSI value, KS statistic, etc.).
        threshold: The threshold used to determine drift.
        is_drift: Whether the score exceeds the threshold.
        bin_edges: Bin edges used for computation (n_bins + 1 edges for PSI).
    """

    method: Literal["psi", "ks"]
    score: float
    threshold: float
    is_drift: bool
    bin_edges: list[float]
