"""QuantideFetcherAdapter: bridge quantide.data.fetchers.tushare to DataLoader.

FR-0100: Adapter class wrapping quantide.data.fetchers.tushare.fetch_bars(),
exposing async get_daily(asset, end_date, count) matching DataLoader's contract.
NFR-0100: All quantide imports are function-scope (lazy); no top-level imports.
"""

from datetime import date

import polars as pl
from loguru import logger

# OHLCV schema matching DataLoader's expected output (§1.1)
_OHLCV_SCHEMA: dict[str, pl.DataType] = {
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


class QuantideFetcherAdapter:
    """Adapter wrapping quantide.data.fetchers.tushare.fetch_bars for DataLoader.

    Translates DataLoader.get_history(asset, end_date, count) pipeline:
    1. Compute N trading dates backwards from end_date (via quantide Calendar)
    2. Call fetch_bars(dates)
    3. Filter by asset
    4. Return polars DataFrame with standardized OHLCV schema
    """

    async def get_daily(
        self,
        asset: str,
        end_date: date,
        count: int = 120,
    ) -> pl.DataFrame:
        """Fetch up to `count` daily OHLCV rows ending at `end_date` for `asset`.

        Args:
            asset: Asset code (e.g. "000001.SZ").
            end_date: Latest trading day to include.
            count: Maximum number of trading days to fetch (default 120).

        Returns:
            Polars DataFrame with columns: asset, date, open, high, low,
            close, volume, turnover, adj_factor. May have fewer rows if
            insufficient history exists. Returns empty DataFrame on errors.
        """
        dates = self._compute_trade_dates(end_date, count)
        if not dates:
            return self._empty_ohlcv()

        try:
            df, errors = self._fetch_bars_for_dates(dates)
        except Exception:
            logger.exception("fetch_bars raised an unexpected exception")
            return self._empty_ohlcv()

        if errors:
            for err in errors:
                logger.warning(f"fetch_bars error: {err}")

        if df is None or len(df) == 0:
            return self._empty_ohlcv()

        result = self._to_polars_ohlcv(df)

        # Filter by asset
        result = result.filter(pl.col("asset") == asset)

        return result

    def _compute_trade_dates(self, end_date: date, count: int) -> list[date]:
        """Compute up to `count` trading dates going backwards from `end_date`.

        Uses quantide Calendar (function-scope import per NFR-0100).

        Args:
            end_date: Anchor date.
            count: Number of trading days to look back.

        Returns:
            List of trading dates in chronological order, ending at or before
            end_date. May return fewer than `count` if calendar history is
            shorter.
        """
        from quantide.core.enums import FrameType
        from quantide.data.models.calendar import calendar

        return calendar.get_frames_by_count(end_date, count, FrameType.DAY)

    def _fetch_bars_for_dates(self, dates: list[date]):
        """Call quantide fetch_bars with function-scope lazy import (NFR-0100).

        Args:
            dates: List of trading dates to fetch.

        Returns:
            Tuple of (pd.DataFrame, list[list]) from fetch_bars.
        """
        from quantide.data.fetchers.tushare import fetch_bars

        return fetch_bars(dates)

    def _to_polars_ohlcv(self, df) -> pl.DataFrame:
        """Convert pandas DataFrame from fetch_bars to polars OHLCV schema.

        Maps amount → turnover, adds adj_factor defaulting to 1.0,
        and ensures consistent column ordering and types.

        Args:
            df: pandas DataFrame from fetch_bars with columns:
                date, asset, open, high, low, close, volume, amount.

        Returns:
            Polars DataFrame with standardized OHLCV schema.
        """
        pdf = df.copy()

        # Map amount to turnover
        if "amount" in pdf.columns:
            pdf = pdf.rename(columns={"amount": "turnover"})
        else:
            pdf["turnover"] = 0.0

        # Add adj_factor if not present
        if "adj_factor" not in pdf.columns:
            pdf["adj_factor"] = 1.0

        # Select and order columns to match OHLCV schema
        cols = [
            "asset",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "adj_factor",
        ]
        pdf = pdf[cols]

        return pl.from_pandas(pdf, schema_overrides=_OHLCV_SCHEMA)

    @staticmethod
    def _empty_ohlcv() -> pl.DataFrame:
        """Return an empty DataFrame with the correct OHLCV schema."""
        return pl.DataFrame(schema=_OHLCV_SCHEMA)
