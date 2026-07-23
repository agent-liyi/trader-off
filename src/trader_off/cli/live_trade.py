"""CLI entry point for live trading via qmt-gateway (FR-0200).

NFR-0100: QmtGatewayBroker is imported at function scope (lazy import).

Exit codes:
    0: Success
    2: Missing required arg (argparse)
    3: Universe file not found or invalid
    4: Gateway connection failure
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from loguru import logger


def _echo(text: str = "") -> None:
    """Write text to stdout followed by newline (CLI output helper)."""
    sys.stdout.write(text + "\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off-live-trade' command.

    Args:
        argv: Optional argument list (for testing). Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 on success.
    """
    parser = argparse.ArgumentParser(
        description="Run live trading via qmt-gateway",
        exit_on_error=False,
    )
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument("--universe", required=True, type=Path, help="CSV file with asset column")
    parser.add_argument(
        "--gateway-url",
        default="http://localhost:5800",
        help="qmt-gateway service URL",
    )
    parser.add_argument(
        "--gateway-api-key",
        default=None,
        help="qmt-gateway API key",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000,
        help="Initial capital (default: 1,000,000)",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output JSON to stdout",
    )

    try:
        args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    except argparse.ArgumentError:
        return 2
    except SystemExit:
        return 2

    # Validate universe file
    universe_path = args.universe
    if not universe_path.exists():
        logger.error(f"Universe file not found: {universe_path}")
        return 3

    # Load universe assets
    try:
        with open(universe_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows or not reader.fieldnames or "asset" not in reader.fieldnames:
                logger.error("Universe CSV must have an 'asset' column")
                return 3
            assets = [row["asset"].strip() for row in rows if row.get("asset", "").strip()]
            if not assets:
                logger.error("Universe CSV contains no assets")
                return 3
    except (OSError, csv.Error) as e:
        logger.error(f"Failed to read universe file: {e}")
        return 3

    # Resolve API key: CLI arg takes precedence over env var
    api_key = args.gateway_api_key or os.environ.get("QMT_GATEWAY_KEY")

    # NFR-0100: lazy import QmtGatewayBroker
    from trader_off.broker.qmt_gateway import QmtGatewayBroker

    broker = QmtGatewayBroker(base_url=args.gateway_url, api_key=api_key)

    try:
        broker.set_principal(args.capital)

        account = broker.get_account()
        positions = broker.get_positions()
        orders = broker.get_orders()
        trades = broker.get_trades()
    except RuntimeError as e:
        logger.error(f"Gateway connection failed: {e}")
        return 4

    summary = {
        "strategy": args.strategy,
        "capital": args.capital,
        "universe": str(universe_path),
        "assets": assets,
        "gateway_url": args.gateway_url,
        "account": account,
        "positions": positions,
        "orders": orders,
        "trades": trades,
    }

    if args.json_output:
        _echo(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        _print_text_summary(summary)

    logger.info("Live trade session completed")
    return 0


def _print_text_summary(summary: dict) -> None:
    """Print a human-readable text summary.

    Args:
        summary: Dict with strategy, capital, account, positions, orders, trades.
    """
    _echo("=" * 50)
    _echo("Live Trade Summary")
    _echo("=" * 50)
    _echo(f"  Strategy:       {summary['strategy']}")
    _echo(f"  Capital:        {summary['capital']:,.2f}")
    _echo(f"  Gateway URL:    {summary['gateway_url']}")
    _echo(f"  Universe:       {summary['universe']}")
    _echo(f"  Assets ({len(summary['assets'])}):      {', '.join(summary['assets'][:5])}")
    if len(summary["assets"]) > 5:
        _echo(f"                  ... and {len(summary['assets']) - 5} more")
    _echo("-" * 50)
    account = summary["account"]
    _echo("  Account:")
    for key, val in account.items():
        _echo(f"    {key}: {val}")
    _echo(f"  Positions:      {len(summary['positions'])} holding(s)")
    for pos in summary["positions"]:
        _echo(f"    {pos.get('symbol', '?')}: {pos}")
    _echo(f"  Orders:         {len(summary['orders'])} order(s)")
    for order in summary["orders"]:
        _echo(f"    {order.get('qtoid', '?')}: {order}")
    _echo(f"  Trades:         {len(summary['trades'])} trade(s)")
    for trade in summary["trades"]:
        _echo(f"    {trade.get('qtoid', '?')}: {trade}")
    _echo("=" * 50)


if __name__ == "__main__":
    sys.exit(main())
