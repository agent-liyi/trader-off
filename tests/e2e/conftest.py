"""Shared e2e fixtures for v0.2.0 test scenarios.

All fixtures use deterministic seed=42 data from tests/fixtures/v0.2.0/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest

# Add src/ to path for subprocess CLI invocations if needed
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "v0.2.0"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Return the path to v0.2.0 fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def ohlcv_data() -> pl.DataFrame:
    """Load the 50-asset × 252-day OHLCV fixture."""
    return pl.read_parquet(FIXTURES_DIR / "ohlcv_50x252.parquet")


@pytest.fixture(scope="session")
def industry_map_df() -> pl.DataFrame:
    """Load the industry map fixture."""
    return pl.read_csv(FIXTURES_DIR / "industry_map.csv")


@pytest.fixture(scope="session")
def industry_map_path() -> Path:
    """Path to the industry map CSV fixture."""
    return FIXTURES_DIR / "industry_map.csv"


@pytest.fixture(scope="session")
def predictions_df() -> pl.DataFrame:
    """Load the predictions fixture (asset, score, rank)."""
    return pl.read_csv(FIXTURES_DIR / "predictions_fixture.csv")


@pytest.fixture(scope="session")
def predictions_path() -> Path:
    """Path to the predictions CSV fixture."""
    return FIXTURES_DIR / "predictions_fixture.csv"


@pytest.fixture(scope="session")
def watchlist_50() -> list[str]:
    """Return the 50-asset watchlist from the fixture."""
    return [f"{i:06d}.SZ" for i in range(1, 51)]
