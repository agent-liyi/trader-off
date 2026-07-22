"""CLI entry point for live (FR-0100).

Subscribes to real-time market quotes via quantide's LiveQuote websocket
connection to qmt-gateway.

Exit codes:
    0: Success
    2: Argparse error
    4: Config error (qmt-gateway not available)

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off-live' command.

    Args:
        argv: Command-line arguments. If None, reads from sys.argv[1:].

    Returns:
        Exit code: 0 success, 2 argparse error, 4 config error.
    """
    parser = _build_argparser()
    args = parser.parse_args(argv)

    # Default to --status if no action flag is set
    if not args.start and not args.stop:
        return _handle_status()
    elif args.start:
        return _handle_start(args)
    else:
        return _handle_stop()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_status() -> int:
    """Check if LiveQuote is running and output JSON status.

    Returns:
        0 on success, 4 if LiveQuote is unavailable (no gateway).
    """
    lq = _get_live_quote()
    if lq is None:
        return 4

    output = {
        "status": "ok",
        "data": {
            "running": lq.is_running,
        },
    }
    _write_json(output)
    return 0


def _handle_start(args) -> int:
    """Start live quote subscription and output JSON status.

    Args:
        args: Parsed argparse namespace with assets attribute.

    Returns:
        0 on success, 4 if LiveQuote is unavailable (no gateway).
    """
    lq = _get_live_quote()
    if lq is None:
        return 4

    assets = _parse_assets(args.assets)
    lq.start()

    output = {
        "status": "ok",
        "data": {
            "running": lq.is_running,
            "assets": assets,
            "connected": lq.is_running,
        },
    }
    _write_json(output)
    return 0


def _handle_stop() -> int:
    """Stop live quote subscription and output JSON status.

    Returns:
        0 on success, 4 if LiveQuote is unavailable (no gateway).
    """
    lq = _get_live_quote()
    if lq is None:
        return 4

    lq.stop()

    output = {
        "status": "ok",
        "data": {
            "running": lq.is_running,
        },
    }
    _write_json(output)
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(data: dict) -> None:
    """Write a dict as JSON to stdout with a trailing newline.

    Args:
        data: Dictionary to serialize and write.
    """
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def _get_live_quote():
    """Lazily import and instantiate LiveQuote singleton.

    NFR-0100: This function is the sole entry point for quantide imports.

    Returns:
        LiveQuote instance on success, or None if the gateway is unavailable.

    Side effects:
        Writes error JSON to stdout when LiveQuote is unavailable.
    """
    try:
        # NFR-0100: Lazy function-scope quantide import
        from quantide.service.livequote import LiveQuote

        return LiveQuote()
    except Exception as e:
        output = {
            "status": "error",
            "code": 4,
            "message": f"qmt-gateway not available: {e}",
        }
        _write_json(output)
        return None


def _parse_assets(assets_str: str | None) -> list[str]:
    """Parse comma-separated asset string into a list.

    Args:
        assets_str: Comma-separated stock codes (e.g. "000001.SZ,600000.SH")
                    or None/empty string.

    Returns:
        List of trimmed asset code strings. Empty list if input is None or empty.
    """
    if not assets_str:
        return []
    return [a.strip() for a in assets_str.split(",") if a.strip()]


def _build_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for live CLI."""
    parser = argparse.ArgumentParser(
        prog="trader-off-live",
        description="Real-time market quote subscription via quantide LiveQuote",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        default=False,
        help="Start live quote subscription",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        default=False,
        help="Stop live quote subscription",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        default=False,
        help="Check if live quote is running (default if no subcommand)",
    )
    parser.add_argument(
        "--assets",
        type=str,
        default=None,
        help="Comma-separated stock codes to subscribe (e.g. 000001.SZ,600000.SH)",
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
