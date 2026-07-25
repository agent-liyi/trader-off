"""Shared CLI utilities."""

import argparse

from trader_off import __version__


def add_version_argument(parser: argparse.ArgumentParser, name: str) -> None:
    """Add a `--version` argument to an argparse parser.

    The argument is a flag that prints "trader-off-<name> v<version>" and exits.
    """
    parser.add_argument(
        "--version",
        action="version",
        version=f"trader-off-{name} v{__version__}",
    )
