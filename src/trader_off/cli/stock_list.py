"""CLI entry point for stock-list (FR-0200).

Fetches A-share stock list from tushare via quantide's fetch_stock_list and
outputs JSON with optional exchange/status filtering.

Exit codes:
    0: Success
    1: No data / fetch error
    2: Argparse error

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

import argparse
import json
import sys
from typing import Any

# Exchange suffix → exchange code mapping
_EXCHANGE_SUFFIX_MAP: dict[str, str] = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off stock-list' command.

    Args:
        argv: Command-line arguments. If None, reads from sys.argv[1:].

    Returns:
        Exit code: 0 success, 1 fetch error, 2 argparse error.
    """
    parser = _build_argparser()
    args = parser.parse_args(argv)

    # NFR-0100: Lazy function-scope quantide import
    from quantide.data.fetchers.tushare import fetch_stock_list

    df = fetch_stock_list()

    if df is None or df.empty:
        output = {"status": "error", "data": {"message": "No stock list data available"}}
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        return 1

    # Derive exchange from asset code suffix (.SH → SSE, .SZ → SZSE, .BJ → BSE)
    df = df.copy()
    df["exchange"] = df["asset"].apply(_derive_exchange)
    # Derive status from delist_date (NaN → L listed, date present → D delisted)
    if "delist_date" in df.columns:
        df["status"] = df["delist_date"].apply(lambda x: "D" if _is_valid_date(x) else "L")
    else:
        df["status"] = "L"

    # Apply exchange filter
    if args.exchange:
        df = df[df["exchange"] == args.exchange]

    # Apply status filter
    if args.status:
        df = df[df["status"] == args.status]

    stocks: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        stocks.append(
            {
                "ts_code": str(row["asset"]),
                "name": str(row["name"]),
            }
        )

    output = {
        "status": "ok",
        "data": {
            "count": len(stocks),
            "exchange": args.exchange or "",
            "status": args.status or "",
            "stocks": stocks,
        },
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    return 0


def _derive_exchange(asset: str) -> str:
    """Derive exchange from asset code suffix.

    Args:
        asset: Asset code like "000001.SZ" or "600000.SH".

    Returns:
        Exchange code: "SSE", "SZSE", "BSE", or empty string if unknown.
    """
    suffix = str(asset).split(".")[-1] if "." in str(asset) else ""
    return _EXCHANGE_SUFFIX_MAP.get(suffix, "")


def _is_valid_date(value: Any) -> bool:
    """Check whether a value represents a valid delist_date (not None, not NaT).

    Args:
        value: The delist_date value from the DataFrame.

    Returns:
        True if value is a valid date, False for None/NaN/NaT.
    """
    if value is None:
        return False
    # pandas NaT evaluates != itself, None is already handled above
    return value == value


def _build_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for stock-list CLI."""
    parser = argparse.ArgumentParser(
        prog="trader-off-stock-list",
        description="Fetch A-share stock list from tushare",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default=None,
        help="Filter by exchange (SSE, SZSE, BSE)",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filter by status (L=listed, D=delisted, P=suspended)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON output (always enabled; this flag is accepted for compatibility)",
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
