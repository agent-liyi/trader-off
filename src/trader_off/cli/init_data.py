"""CLI entry point for init (FR-0100).

Initializes the quantide data directory at the current working directory (default)
or at the path specified by --home. Creates calendar, bars, and db subdirectories
via quantide.data.init_data().

Exit codes:
    0: Success
    2: Argparse error (missing/invalid args)

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off init' command.

    Args:
        argv: Command-line arguments. If None, reads from sys.argv[1:].

    Returns:
        Exit code: 0 success, 2 argparse error.
    """
    parser = _build_argparser()
    args = parser.parse_args(argv)

    # Default to current working directory if --home not specified
    home = Path.cwd() if args.home is None else Path(args.home).expanduser().resolve()

    # NFR-0100: Lazy function-scope quantide import
    from quantide.data import init_data

    init_data(home=home)

    output = {
        "status": "ok",
        "data": {
            "home": str(home),
            "calendar": "created",
            "bars": "created",
            "db": "initialized",
        },
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for init CLI."""
    parser = argparse.ArgumentParser(
        prog="trader-off-init",
        description="Initialize quantide data directory",
    )
    parser.add_argument(
        "--home",
        type=str,
        default=None,
        help="Data root directory (default: current working directory)",
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
