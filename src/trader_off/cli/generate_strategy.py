"""CLI entry point for generate-strategy (FR-0100).

Generates a new strategy class file from a template, with all lifecycle
methods implemented as async stubs. Supports dry-run and JSON output.

Exit codes:
    0: Success (file written or dry-run completed)
    2: Argparse error (missing/invalid args)
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off-generate-strategy' command.

    Args:
        argv: Command-line arguments. If None, reads from sys.argv[1:].

    Returns:
        Exit code: 0 success, 2 argparse error.
    """
    parser = _build_argparser()
    args = parser.parse_args(argv)

    name: str = args.name
    author: str = args.author
    description: str = args.description
    output_dir: Path = Path(args.output_dir)
    dry_run: bool = args.dry_run
    json_output: bool = args.json

    code = _generate_code(name, author=author, description=description)

    if dry_run:
        if json_output:
            _print_json(name=name, code=code)
        else:
            sys.stdout.write(code)
        return 0

    # Write file
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _camel_to_snake(name) + ".py"
    filepath = _dedup_filename(output_dir / filename)

    filepath.write_text(code, encoding="utf-8")

    _print_json(name=name, filepath=filepath)
    return 0


# ---------------------------------------------------------------------------
# Argparser builder
# ---------------------------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for generate-strategy CLI."""
    parser = argparse.ArgumentParser(
        prog="trader-off-generate-strategy",
        description="Generate a trader-off strategy class from a template",
    )
    parser.add_argument(
        "--name",
        required=True,
        type=str,
        help="Strategy class name (e.g., MomentumReversion)",
    )
    parser.add_argument(
        "--author",
        default="trader-off",
        type=str,
        help="Author name (default: trader-off)",
    )
    parser.add_argument(
        "--description",
        default="Generated strategy",
        type=str,
        help="Strategy description (default: 'Generated strategy')",
    )
    parser.add_argument(
        "--output-dir",
        default="src/trader_off/strategies/",
        type=str,
        help="Output directory (default: src/trader_off/strategies/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print generated code to stdout instead of writing file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON output (per v0.5.4 standard)",
    )
    return parser


# ---------------------------------------------------------------------------
# Name conversion
# ---------------------------------------------------------------------------


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case.

    Inserts an underscore before each uppercase letter (except the first)
    and lowercases everything. Runs of uppercase letters (acronyms) are
    treated as a single word.

    Args:
        name: A CamelCase or snake_case string.

    Returns:
        snake_case version of the input.

    Examples:
        >>> _camel_to_snake("MyStrategy")
        'my_strategy'
        >>> _camel_to_snake("LGBMTop20")
        'lgbm_top20'
    """
    # Insert underscore between lowercase→uppercase transitions, and
    # between uppercase runs followed by lowercase (acronym boundary)
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower()


# ---------------------------------------------------------------------------
# Filename deduplication
# ---------------------------------------------------------------------------


def _dedup_filename(target: Path) -> Path:
    """Return a unique filename by appending a numeric suffix if target exists.

    Args:
        target: The desired file path.

    Returns:
        A Path that does not yet exist.
    """
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    parent = target.parent

    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Code generation template
# ---------------------------------------------------------------------------


def _generate_code(
    class_name: str,
    *,
    author: str = "trader-off",
    description: str = "Generated strategy",
) -> str:
    """Generate strategy class source code from a template.

    Args:
        class_name: Strategy class name (CamelCase).
        author: Author name for the module docstring.
        description: Strategy description.

    Returns:
        Python source code as a string.
    """
    today = str(date.today())

    template = f'''"""{class_name} strategy.

Generated on {today} by {author}.
Description: {description}
"""

from datetime import datetime

from loguru import logger

from trader_off.strategies.compat import BaseStrategy


class {class_name}(BaseStrategy):
    """{description}."""

    def __init__(self, broker, config: dict | None = None):
        """Initialize the strategy.

        Args:
            broker: Broker instance for order execution.
            config: Configuration dict.
        """
        super().__init__(broker, config)
        logger.debug("{class_name}.__init__ called")

    async def on_day_open(self, tm: datetime) -> None:
        """Called at the start of each trading day.

        Args:
            tm: Current datetime.
        """
        logger.debug("{class_name}.on_day_open called")

    async def on_bar(
        self,
        tm: datetime,
        quote: dict | None = None,
        frame_type=None,
    ) -> None:
        """Called on each bar/period update.

        Args:
            tm: Current bar timestamp.
            quote: Quote data dict keyed by asset.
            frame_type: Bar frame type.
        """
        logger.debug("{class_name}.on_bar called")

    async def on_day_close(self, tm: datetime) -> None:
        """Called at the end of each trading day.

        Args:
            tm: Current datetime.
        """
        logger.debug("{class_name}.on_day_close called")

    async def on_stop(self) -> None:
        """Called when backtest/trading ends for cleanup."""
        logger.debug("{class_name}.on_stop called")
'''
    return template


# ---------------------------------------------------------------------------
# JSON output helpers
# ---------------------------------------------------------------------------


def _print_json(
    *,
    name: str,
    filepath: Path | None = None,
    code: str | None = None,
) -> None:
    """Print JSON output to stdout.

    Args:
        name: Strategy class name.
        filepath: Path where the file was written (None in dry-run mode).
        code: Generated code string (for dry-run JSON output).
    """
    import json

    data: dict = {"class": name, "methods": 5}
    if filepath is not None:
        data["file"] = str(filepath)
    if code is not None:
        data["code"] = code

    output = {"status": "ok", "data": data}
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    sys.exit(main())
