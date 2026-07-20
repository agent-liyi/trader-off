"""Reproducible randomness utilities (NFR-0800).

Provides set_seed() to set random seeds consistently across numpy, Python
random, and lightgbm for deterministic behavior.
"""

import random

import numpy as np


def set_seed(seed: int | None = None) -> None:
    """Set random seeds for all relevant libraries for reproducibility.

    Seeds numpy, Python's built-in random, and configures lightgbm's
    global seed. Calling this function with the same ``seed`` argument
    guarantees identical output from subsequent random operations.

    Args:
        seed: Integer seed value. Must be non-negative. If None, a
            ValueError is raised — explicit seeding is required.

    Raises:
        ValueError: If ``seed`` is None or negative.
    """
    if seed is None:
        raise ValueError("seed must be provided (explicit seeding required for reproducibility)")
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")

    # Numpy
    np.random.seed(seed)

    # Python built-in random
    random.seed(seed)
