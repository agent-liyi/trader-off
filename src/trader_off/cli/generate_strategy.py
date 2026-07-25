"""CLI entry point for generate-strategy (FR-0100).

Generates a new strategy class file from a template, with all lifecycle
methods implemented. Supports dry-run, JSON output, and pre-built strategy
templates (double-ma, momentum, multi-factor).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from trader_off.cli._version import add_version_argument

_TEMPLATES = {
    "double-ma": {
        "description": "双均线策略 (fast/slow MA 金叉买入，死叉卖出)",
        "params": ["fast", "slow"],
        "imports": "import polars as pl\n",
        "init_body": "self._fast: int = config.get('fast', 5)\nself._slow: int = config.get('slow', 20)",
        "on_day_open_body": (
            "df = self.datafeed.get_bars(self.assets, lookback=self._slow + 1)\n"
            "fast_ma = df.group_by('asset').agg(pl.col('close').tail(self._fast).mean().alias('fast'))\n"
            "slow_ma = df.group_by('asset').agg(pl.col('close').tail(self._slow).mean().alias('slow'))\n"
            "for asset in self.assets:\n"
            "    f_val = fast_ma.filter(pl.col('asset') == asset)['fast'].item()\n"
            "    s_val = slow_ma.filter(pl.col('asset') == asset)['slow'].item()\n"
            "    if f_val > s_val:\n"
            "        await self.broker.trade_target_pct(asset, 1.0 / len(self.assets))\n"
            "    else:\n"
            "        await self.broker.trade_target_pct(asset, 0.0)"
        ),
    },
    "momentum": {
        "description": "动量反转策略 (过去 N 日收益率排名，买入 Top K)",
        "params": ["lookback", "top_k"],
        "imports": "import polars as pl\n",
        "init_body": "self._lookback: int = config.get('lookback', 20)\nself._top_k: int = config.get('top_k', 10)",
        "on_day_open_body": (
            "df = self.datafeed.get_bars(self.assets, lookback=self._lookback)\n"
            "returns = df.group_by('asset').agg(\n"
            "    (pl.col('close').last() / pl.col('close').first() - 1).alias('ret')\n"
            ").sort('ret', descending=True)\n"
            "top_assets = returns.head(self._top_k)['asset'].to_list()\n"
            "for asset in self.assets:\n"
            "    if asset in top_assets:\n"
            "        await self.broker.trade_target_pct(asset, 1.0 / self._top_k)\n"
            "    else:\n"
            "        await self.broker.trade_target_pct(asset, 0.0)"
        ),
    },
    "multi-factor": {
        "description": "多因子策略 (momentum + volatility z-score 综合排名)",
        "params": ["lookback", "top_k", "mom_weight", "vol_weight"],
        "imports": "import polars as pl\n",
        "init_body": (
            "self._lookback: int = config.get('lookback', 20)\n"
            "self._top_k: int = config.get('top_k', 10)\n"
            "self._w_mom: float = config.get('mom_weight', 0.5)\n"
            "self._w_vol: float = config.get('vol_weight', -0.3)"
        ),
        "on_day_open_body": (
            "df = self.datafeed.get_bars(self.assets, lookback=self._lookback)\n"
            "mom = df.group_by('asset').agg(\n"
            "    (pl.col('close').last() / pl.col('close').first() - 1).alias('raw')\n"
            ")\n"
            "vol = df.group_by('asset').agg(\n"
            "    pl.col('close').std().alias('raw')\n"
            ")\n"
            "for s in (mom, vol):\n"
            "    s = s.with_columns(((pl.col('raw') - pl.col('raw').mean()) / pl.col('raw').std()).alias('z'))\n"
            "scores = mom.with_columns(pl.col('z') * self._w_mom)\n"
            "scores = scores.join(vol.select('asset', pl.col('z') * self._w_vol).rename({'z': 'score'}), on='asset', how='left', suffix='_v')\n"
            "scores = scores.with_columns((pl.col('z') + pl.col('score')).alias('total'))\n"
            "top_assets = scores.sort('total', descending=True).head(self._top_k)['asset'].to_list()\n"
            "for asset in self.assets:\n"
            "    if asset in top_assets:\n"
            "        await self.broker.trade_target_pct(asset, 1.0 / self._top_k)\n"
            "    else:\n"
            "        await self.broker.trade_target_pct(asset, 0.0)"
        ),
    },
}


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'to generate-strategy' command."""
    parser = _build_argparser()
    args = parser.parse_args(argv)

    name: str = args.name
    author: str = args.author
    description: str = args.description
    template: str | None = args.template
    output_dir: Path = Path(args.output_dir)
    dry_run: bool = args.dry_run
    json_output: bool = args.json

    if template and template not in _TEMPLATES:
        sys.stderr.write(f"Unknown template: {template}. Available: {list(_TEMPLATES.keys())}\n")
        return 2

    code = _generate_code(name, author=author, description=description, template=template)

    if dry_run:
        if json_output:
            _print_json(name=name, code=code, template=template)
        else:
            sys.stdout.write(code)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _camel_to_snake(name) + ".py"
    filepath = _dedup_filename(output_dir / filename)
    filepath.write_text(code, encoding="utf-8")
    _print_json(name=name, filepath=filepath, template=template)
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for generate-strategy CLI."""
    parser = argparse.ArgumentParser(
        prog="to generate-strategy",
        description="Generate a trader-off strategy class from a template",
    )
    add_version_argument(parser, "generate-strategy")
    parser.add_argument("--name", required=True, type=str, help="Strategy class name")
    parser.add_argument("--author", default="trader-off", type=str, help="Author name")
    parser.add_argument("--description", default="Generated strategy", type=str, help="Strategy description")
    parser.add_argument("--template", type=str, choices=list(_TEMPLATES.keys()), default=None,
                        help="Pre-built strategy template (double-ma, momentum, multi-factor)")
    parser.add_argument("--output-dir", default="src/trader_off/strategies/", type=str, help="Output directory")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Print generated code to stdout")
    parser.add_argument("--json", action="store_true", default=False, help="JSON output")
    return parser


def _camel_to_snake(name: str) -> str:
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower()


def _dedup_filename(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suffix, parent = target.stem, target.suffix, target.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _generate_code(
    class_name: str,
    *,
    author: str = "trader-off",
    description: str = "Generated strategy",
    template: str | None = None,
) -> str:
    """Generate strategy class source code from a template.

    Args:
        class_name: Strategy class name (CamelCase).
        author: Author name for the module docstring.
        description: Strategy description.
        template: Pre-built template name or None for skeleton.

    Returns:
        Python source code as a string.
    """
    today = str(date.today())

    if template and template in _TEMPLATES:
        t = _TEMPLATES[template]
        init_lines = t["init_body"].strip().split("\n")
        init_body = "\n        ".join(init_lines)

        on_day_lines = ['pass  # strategy logic above']
        on_day_lines.extend(t["on_day_open_body"].strip().split("\n"))
        on_day_body = "\n        ".join(on_day_lines)

        imports = (
            "from datetime import datetime\n"
            + t["imports"]
            + "\nfrom loguru import logger\n\nfrom trader_off.strategies.compat import BaseStrategy\n"
        )
    else:
        init_body = f'logger.debug("{class_name}.__init__ called")'
        on_day_body = f'logger.debug(f"{class_name}.on_day_open called at {{tm}}")'
        imports = (
            "from datetime import datetime\n\n"
            "from loguru import logger\n\n"
            "from trader_off.strategies.compat import BaseStrategy\n"
        )

    code = f'''"""{class_name} strategy.

Generated on {today} by {author}.
Description: {description}
"""

{imports}

class {class_name}(BaseStrategy):
    """{description}."""

    def __init__(self, broker, config: dict | None = None):
        super().__init__(broker, config)
        {init_body}

    async def on_day_open(self, tm: datetime) -> None:
        {on_day_body}

    async def on_bar(self, tm: datetime, quote: dict | None = None, frame_type=None) -> None:
        pass

    async def on_day_close(self, tm: datetime) -> None:
        pass

    async def on_stop(self) -> None:
        logger.debug(f"{class_name}.on_stop called")
'''
    return code


def _print_json(
    *,
    name: str,
    filepath: Path | None = None,
    code: str | None = None,
    template: str | None = None,
) -> None:
    data: dict = {"class": name, "methods": 5}
    if filepath is not None:
        data["file"] = str(filepath)
    if code is not None:
        data["code"] = code
    if template:
        data["template"] = template

    output = {"status": "ok", "data": data}
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    sys.exit(main())
