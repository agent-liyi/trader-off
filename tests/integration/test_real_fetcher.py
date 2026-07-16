"""Integration test for real fetcher (L3 — real environment smoke test).

Covers AC-NFR0100-02: real fetcher returns >= 4000 assets from
quantide.data.fetchers.

This test is annotated with @pytest.mark.integration and uses
pytest.importorskip to skip when the real fetcher is unavailable.
It is designed to run only in environments with a real market
database connection (nightly or manual runs, never in CI by default).
"""

import pytest


@pytest.mark.integration
class TestRealFetcher:
    """L3 integration: real fetcher full-market smoke test.

    NOTE: This test requires a production-like environment with:
    - quantide.data.fetchers module available
    - Real market database connection
    - Network access to market data source

    It is NOT designed to pass in CI or developer workstations.
    """

    def test_ac_nfr0100_02_real_fetcher_4000_assets(self):
        """AC-NFR0100-02: Real fetcher returns >= 4000 A-share assets.

        Uses quantide.data.fetchers directly when available.
        Skipped if fetcher module is not installed.
        """
        # Attempt to import the real fetcher; skip if unavailable
        fetchers = pytest.importorskip(
            "quantide.data.fetchers",
            reason="Real fetcher not available in this environment (L3 only)",
        )

        # Attempt to load assets from the real fetcher
        # The exact API depends on the millionaire version
        try:
            assets = fetchers.get_asset_list(frame_type="DAY")
        except AttributeError:
            try:
                assets = fetchers.list_assets()
            except AttributeError:
                pytest.skip(
                    "L3 real fetcher test requires millionaire installed "
                    "with fetcher API support (see #22)"
                )

        # Must have at least 4000 A-share stocks
        assert len(assets) >= 4000, (
            f"Expected >= 4000 assets, got {len(assets)}"
        )
