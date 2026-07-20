"""Tests for batched feature computation used by the prediction pipeline.

These tests verify the vectorized feature computation path that processes
all assets in a single pass (vs per-asset sequential computation).
"""

import time
from datetime import date, timedelta

import numpy as np
import polars as pl

from trader_off.features.momentum import compute_momentum_features
from trader_off.features.volatility import compute_volatility_features
from trader_off.features.volume import compute_volume_features


def _make_ohlcv_fixture(
    n_assets: int, n_days: int, seed: int = 42
) -> tuple[pl.DataFrame, list[str]]:
    """Generate synthetic OHLCV fixture for testing."""
    rng = np.random.RandomState(seed)
    assets = [f"{i:06d}.SZ" for i in range(n_assets)]
    base_date = date(2024, 6, 28)
    rows = []
    for asset_idx, asset in enumerate(assets):
        base_price = rng.uniform(5, 100)
        for d in range(n_days):
            day_date = base_date - timedelta(days=n_days - 1 - d)
            close = base_price * (1.0 + rng.randn() * 0.02)
            rows.append(
                {
                    "asset": asset,
                    "date": day_date,
                    "open": close * 0.99,
                    "high": close * 1.02,
                    "low": close * 0.98,
                    "close": close,
                    "volume": rng.uniform(1e6, 1e8),
                    "turnover": rng.uniform(0.01, 0.05),
                    "adj_factor": 1.0,
                }
            )
    return pl.DataFrame(rows), assets


class TestBatchedFeatureComputation:
    """Verify batched (vectorized) feature computation produces correct results."""

    def test_batched_features_match_per_asset(self):
        """Batched feature computation yields identical results to per-asset computation.

        This is a correctness property: computing features on the full concatenated
        DataFrame (with .over("asset") partitioning) must produce the same values
        as computing per-asset and concatenating the results.
        """
        n_assets = 50
        n_days = 60
        fixture_df, assets = _make_ohlcv_fixture(n_assets, n_days)

        # Per-asset computation (reference)
        per_asset_results = {}
        for asset in assets:
            hist = fixture_df.filter(pl.col("asset") == asset).sort("date")
            hist = compute_momentum_features(hist)
            hist = compute_volatility_features(hist)
            hist = compute_volume_features(hist)
            latest = hist.sort("date").tail(1)
            per_asset_results[asset] = {c: latest[c][0] for c in latest.columns}

        # Batched computation
        combined = compute_momentum_features(fixture_df)
        combined = compute_volatility_features(combined)
        combined = compute_volume_features(combined)
        latest_batched = (
            combined.sort(["asset", "date"]).group_by("asset", maintain_order=True).last()
        )

        # Compare
        for asset in assets:
            ref = per_asset_results[asset]
            batched_row = latest_batched.filter(pl.col("asset") == asset).to_dicts()[0]

            # Compare all feature columns (exclude asset/date keys)
            feature_cols = [c for c in ref if c not in ("asset", "date")]
            for col in feature_cols:
                ref_val = ref[col]
                batch_val = batched_row[col]
                # NaN comparison
                if ref_val is None or (isinstance(ref_val, float) and np.isnan(ref_val)):
                    assert batch_val is None or (
                        isinstance(batch_val, float) and np.isnan(batch_val)
                    )
                else:
                    assert abs(ref_val - batch_val) < 1e-10, (
                        f"{asset}/{col}: {ref_val} vs {batch_val}"
                    )

    def test_batched_computation_scales_sublinear(self):
        """Batched computation scales better than O(n_assets) per-asset computation.

        For 200 assets, batched should be at least 3x faster than per-asset.
        This validates that the batched approach actually provides a speedup.
        """
        n_assets_small = 50
        n_days = 60
        fixture_small, assets_small = _make_ohlcv_fixture(n_assets_small, n_days, seed=1)

        n_assets_large = 200
        fixture_large, assets_large = _make_ohlcv_fixture(n_assets_large, n_days, seed=2)

        # Per-asset for small
        t0 = time.perf_counter()
        for asset in assets_small:
            hist = fixture_small.filter(pl.col("asset") == asset).sort("date")
            compute_momentum_features(hist)
            compute_volatility_features(hist)
            compute_volume_features(hist)
        t_per_asset_small = time.perf_counter() - t0

        # Per-asset for large (extrapolated from small via scaling)
        # t_per_asset_large ≈ t_per_asset_small * (n_assets_large / n_assets_small)
        t_per_asset_large_est = t_per_asset_small * (n_assets_large / n_assets_small)

        # Batched for large
        t0 = time.perf_counter()
        combined = compute_momentum_features(fixture_large)
        combined = compute_volatility_features(combined)
        combined = compute_volume_features(combined)
        _ = combined.sort(["asset", "date"]).group_by("asset", maintain_order=True).last()
        t_batched_large = time.perf_counter() - t0

        speedup = t_per_asset_large_est / t_batched_large
        assert speedup >= 3.0, (
            f"Batched should be ≥3x faster than per-asset for {n_assets_large} assets, "
            f"got {speedup:.1f}x "
            f"(per-asset est: {t_per_asset_large_est:.4f}s, batched: {t_batched_large:.4f}s)"
        )

    def test_batched_latest_row_per_asset(self):
        """group_by('asset').last() correctly extracts the latest (most recent) row.

        The latest row is defined by the maximum date per asset.
        """
        n_assets = 10
        n_days = 30
        fixture_df, assets = _make_ohlcv_fixture(n_assets, n_days)

        combined = compute_momentum_features(fixture_df)
        combined = compute_volatility_features(combined)
        combined = compute_volume_features(combined)

        latest = combined.sort(["asset", "date"]).group_by("asset", maintain_order=True).last()

        assert len(latest) == n_assets
        for asset in assets:
            asset_latest = latest.filter(pl.col("asset") == asset)
            assert len(asset_latest) == 1
            max_date = asset_latest["date"][0]

            # Verify max_date is indeed the maximum date for this asset
            asset_all_dates = fixture_df.filter(pl.col("asset") == asset)["date"]
            assert max_date == max(asset_all_dates.to_list())
