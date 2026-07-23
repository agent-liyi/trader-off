"""CLI entry point for `trader-off server` (FR-0200).

Launches the FastAPI REST server (FR-0100) via uvicorn programmatically.

NFR-0100: uvicorn and fastapi are imported at function scope (lazy).
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_argparser():
    """Build the argument parser for ``trader-off server``.

    Returns:
        An argparse.ArgumentParser with --port, --host, --json.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="trader-off-server",
        description="Start the trader-off REST API server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit startup info as a JSON line for agent parsing.",
    )
    return parser


# ---------------------------------------------------------------------------
# Startup JSON emitter (AC-FR0200-03)
# ---------------------------------------------------------------------------


def _emit_startup_json(host: str, port: int, stdout: TextIO | None = None) -> None:
    """Emit a single startup JSON line for agent parsing.

    Args:
        host: Server host address.
        port: Server port number.
        stdout: Output stream (defaults to sys.stdout).
    """
    if stdout is None:
        stdout = sys.stdout

    payload = {
        "status": "ok",
        "data": {"host": host, "port": port},
    }
    stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stdout.flush()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and launch the uvicorn server.

    Args:
        argv: Optional argument list (for testing). Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 on successful launch.
    """
    parser = _build_argparser()
    args = parser.parse_args(argv)

    # Emit startup JSON line before launching (--json flag)
    if args.json:
        _emit_startup_json(args.host, args.port)

    # NFR-0100: Lazy function-scope imports
    import uvicorn

    from trader_off.api.server import create_app

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)

    return 0


if __name__ == "__main__":
    sys.exit(main())
