"""Quantide adapter (FR-0100).

Wires QuantideDataLoader to real quantide.data.fetchers.tushare functions
and quantide.data.models.calendar for CN trading calendar support.
Replaces v0.4.0's pandas.bdate_range stub with real Tushare data fetching.

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

import os
from datetime import date

import polars as pl
from loguru import logger


class QuantideDataLoader:
    """Real Tushare data loader with CN trading calendar support.

    Requires TUSHARE_TOKEN environment variable or explicit token argument.
    On fetch errors, returns an empty DataFrame with the correct schema
    rather than raising an exception.

    Attributes:
        _token: The Tushare token used for API access.
    """

    OHLCV_SCHEMA = {
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

    def __init__(self, token: str | None = None):
        """Initialize QuantideDataLoader.

        Args:
            token: Optional explicit Tushare token. If None, reads from
                   TUSHARE_TOKEN environment variable. Raises RuntimeError
                   if neither is available.
        """
        if token is not None:
            self._token: str = token
        else:
            env_token = os.environ.get("TUSHARE_TOKEN")
            if not env_token:
                raise RuntimeError(
                    "TUSHARE_TOKEN environment variable is required for "
                    "QuantideDataLoader; set it before running smoke tests"
                )
            self._token = env_token

    async def get_daily(self, asset: str, end_date: date, count: int = 60) -> pl.DataFrame:
        """Fetch up to ``count`` daily OHLCV rows ending at ``end_date``.

        Uses quantide's TushareFetcher and calendar.get_frames_by_count
        for CN trading calendar-aware date range generation and real data fetch.
        All quantide imports are function-scope (NFR-0100).

        Args:
            asset: Asset code (e.g. "000001.SZ").
            end_date: Latest trading day to include.
            count: Maximum number of trading days to fetch.

        Returns:
            DataFrame with OHLCV schema. May have fewer rows if
            insufficient history exists, or be empty on fetch errors.
        """
        # NFR-0100: Lazy function-scope imports
        from quantide.data.fetchers.tushare import TushareFetcher, fetch_bars

        try:
            # Compute real CN trading dates via calendar
            trade_dates = self._compute_real_trade_dates(end_date, count)

            # Instantiate TushareFetcher for real data access (side-effect)
            _fetcher = TushareFetcher()

            # Fetch bars for all trade dates
            result_df, errors = fetch_bars(trade_dates)

            if errors:
                for err in errors:
                    logger.warning(f"Tushare fetch error: {err}")

            return self._to_polars_ohlcv(result_df, asset, count)

        except Exception as e:
            logger.exception(f"Failed to fetch data for {asset}: {e}")
            return pl.DataFrame(schema=self.OHLCV_SCHEMA)

    def _compute_real_trade_dates(self, end_date: date, count: int) -> list[date]:
        """Compute ``count`` real CN trading days ending at ``end_date``.

        Uses quantide's Calendar.get_frames_by_count to account for
        CN holidays. Replaces v0.4.0's pandas.bdate_range.

        NFR-0100: Import is function-scope, not module-top-level.
        """
        from quantide.data.models.calendar import FrameType, calendar

        raw_dates = calendar.get_frames_by_count(end_date, count, FrameType.DAY)
        # Normalize to date objects
        return [d if isinstance(d, date) else d.date() for d in raw_dates]

    def _to_polars_ohlcv(self, df, asset: str, count: int) -> pl.DataFrame:
        """Convert pandas DataFrame to polars with schema normalization.

        Handles the defensive rename from Tushare column names
        (ts_code, trade_date, vol, amount) to OHLCV schema names
        (asset, date, volume, turnover).

        Args:
            df: pandas DataFrame from fetch_bars.
            asset: Asset code to filter by.
            count: Maximum number of rows to return.

        Returns:
            Polars DataFrame with standardized OHLCV schema.
        """
        if df is None:
            return pl.DataFrame(schema=self.OHLCV_SCHEMA)

        pl_df = pl.from_pandas(df)

        # Defensive rename: ts_code -> asset, trade_date -> date,
        # vol -> volume, amount -> turnover
        rename_map = {}
        if "ts_code" in pl_df.columns:
            rename_map["ts_code"] = "asset"
        if "trade_date" in pl_df.columns:
            rename_map["trade_date"] = "date"
        if "vol" in pl_df.columns:
            rename_map["vol"] = "volume"
        if "amount" in pl_df.columns:
            rename_map["amount"] = "turnover"
        if rename_map:
            pl_df = pl_df.rename(rename_map)

        # Filter by asset
        if "asset" in pl_df.columns:
            pl_df = pl_df.filter(pl.col("asset") == asset)

        # Ensure all required columns exist, filling defaults where needed
        for col_name, col_type in self.OHLCV_SCHEMA.items():
            if col_name not in pl_df.columns:
                if col_name == "adj_factor":
                    pl_df = pl_df.with_columns(pl.lit(1.0).alias("adj_factor"))
                elif col_name == "turnover":
                    pl_df = pl_df.with_columns(pl.lit(0.0).alias("turnover"))
                else:
                    pl_df = pl_df.with_columns(pl.lit(None).cast(col_type).alias(col_name))

        # Limit to requested row count
        pl_df = pl_df.head(count)

        # Select and order columns by schema
        return pl_df.select(list(self.OHLCV_SCHEMA.keys()))
