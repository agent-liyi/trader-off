"""Industry map loading and lookup (FR-3200).

Provides `load_industry_map` for reading industry classification from CSV,
and `get_industry` for safe lookup with fallback to "UNKNOWN".
"""

import csv
from pathlib import Path

from loguru import logger

from trader_off.utils.exceptions import IndustryMapConflictError


def load_industry_map(path: Path) -> dict[str, str]:
    """Load industry classification map from a CSV file.

    The CSV must have ``asset`` and ``industry`` columns. Each asset
    must appear at most once.

    Args:
        path: Path to the industry map CSV.

    Returns:
        Dict mapping each asset ticker to its industry name.

    Raises:
        IndustryMapConflictError: If any asset appears more than once
            with different industry assignments.
        FileNotFoundError: If the file does not exist.
    """
    result: dict[str, str] = {}
    seen: dict[str, str] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if (
            reader.fieldnames is None
            or "asset" not in reader.fieldnames
            or "industry" not in reader.fieldnames
        ):
            raise ValueError("CSV must have 'asset' and 'industry' columns")

        for row in reader:
            asset = row["asset"].strip()
            industry = row["industry"].strip()

            if asset in seen and seen[asset] != industry:
                raise IndustryMapConflictError(
                    f"duplicate asset: {asset}, industries: [{seen[asset]}, {industry}]"
                )
            seen[asset] = industry
            result[asset] = industry

    logger.info("Loaded industry map with {} assets from {}", len(result), path)
    return result


def get_industry(ticker: str, industry_map: dict[str, str]) -> str:
    """Look up a ticker's industry, returning "UNKNOWN" if not found.

    Args:
        ticker: Asset ticker to look up.
        industry_map: Dict from load_industry_map.

    Returns:
        Industry name, or ``"UNKNOWN"`` if the ticker is not in the map.
        A WARNING is logged when the ticker is unknown.
    """
    if ticker in industry_map:
        return industry_map[ticker]

    logger.warning("Unknown industry for ticker: {}", ticker)
    return "UNKNOWN"
