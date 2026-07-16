"""DataLoader abstraction (NFR-0100).

Provides a DataLoader interface for fetching historical OHLCV data.
Abstracts over millionaire's quantide.data.fetchers so tests can
inject fixture-backed replacements.
"""

from datetime import date

import polars as pl
from loguru import logger


class DataLoader:
    """Abstract data loader for fetching historical OHLCV data.

    Real implementation wraps millionaire's quantide.data.fetchers.
    Tests can inject mock DataLoader instances returning fixture data.
    """

    def __init__(self, fetcher=None):
        """Initialize DataLoader.

        Args:
            fetcher: Optional millionaire fetcher instance.
                If None, uses quantide.data.fetchers when available.
        """
        self._fetcher = fetcher

    async def get_history(
        self,
        asset: str,
        end_date: date,
        count: int = 120,
    ) -> pl.DataFrame:
        """Fetch up to `count` daily OHLCV rows ending at `end_date`.

        Args:
            asset: Asset code (e.g. "000001.SZ").
            end_date: Latest trading day to include.
            count: Maximum number of trading days to fetch.

        Returns:
            DataFrame with §1.1 OHLCV schema. May have fewer rows
            if insufficient history exists.
        """
        if self._fetcher is not None:
            # Use injected fetcher (production path via millionaire)
            raw = await self._fetcher.get_daily(asset, end_date, count)
            return pl.DataFrame(raw)

        logger.warning(
            f"No fetcher configured for DataLoader. "
            f"Returning empty DataFrame for {asset}."
        )
        return pl.DataFrame(
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "turnover": pl.Float64,
                "adj_factor": pl.Float64,
            }
        )
