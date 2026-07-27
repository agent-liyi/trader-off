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

_DUAL_IMPORT = (
    "try:\n"
    "    from quantide.core.strategy import BaseStrategy\n"
    "except ImportError:\n"
    "    try:\n"
    "        from trader_off.strategies.compat import BaseStrategy\n"
    "    except ImportError:\n"
    "        from abc import ABC\n"
    "        class BaseStrategy(ABC):\n"
    '            """Minimal stub — quantide/trader-off not installed."""\n'
    "            def __init__(self, broker, config=None):\n"
    "                self.broker = broker\n"
    "                self.config = config or {}\n"
    "            async def on_day_open(self, tm): pass\n"
    "            async def on_bar(self, tm, quote=None, frame_type=None): pass\n"
    "            async def on_day_close(self, tm): pass\n"
    "            async def on_stop(self): pass\n"
)

_TEMPLATES = {
    "double-ma": {
        "description": "双均线金叉死叉策略 — 基于 on_bar + FrameType.DAY",
        "params": ["fast", "slow", "symbol", "invest"],
        "imports": "",
        "init_body": (
            "self.fast_window: int = int(self.config.get('fast', 5))\n"
            "self.slow_window = int(self.config.get('slow', 10))\n"
            "self.symbol = self.config.get('symbol', '000001.SZ')\n"
            "self.invest_amount = float(self.config.get('invest', 100000))\n"
        ),
        "on_bar_body": (
            "if frame_type != FrameType.DAY:\n"
            "    return\n"
            "count = self.slow_window + 5\n"
            "hist = self.get_history(self.symbol, count, tm, '1d')\n"
            "if len(hist) < self.slow_window + 2:\n"
            "    return\n"
            "closes = hist['close'].to_numpy()\n"
            "curr_fast = closes[-self.fast_window:].mean()\n"
            "curr_slow = closes[-self.slow_window:].mean()\n"
            "prev_fast = closes[-(self.fast_window + 1):-1].mean()\n"
            "prev_slow = closes[-(self.slow_window + 1):-1].mean()\n"
            "pos = self.broker.positions.get(self.symbol)\n"
            "shares = pos.shares if pos else 0\n"
            "if prev_fast <= prev_slow and curr_fast > curr_slow:\n"
            "    if shares == 0:\n"
            "        self.log(f'{self.symbol} Golden Cross at {tm}')\n"
            "        await self.broker.buy_amount(self.symbol, self.invest_amount, price=0, order_time=tm)\n"
            "elif prev_fast >= prev_slow and curr_fast < curr_slow:\n"
            "    if shares > 0:\n"
            "        self.log(f'{self.symbol} Death Cross at {tm}')\n"
            "        await self.broker.sell(self.symbol, shares, price=0, order_time=tm)\n"
        ),
    },
    "momentum": {
        "description": "动量反转策略 — N 日收益率排序买入 top_k 只",
        "params": ["lookback", "top_k", "invest"],
        "imports": "",
        "init_body": (
            "self.lookback: int = int(self.config.get('lookback', 20))\n"
            "self.top_k = int(self.config.get('top_k', 5))\n"
            "self.invest_amount = float(self.config.get('invest', 100000))\n"
        ),
        "on_bar_body": (
            "if frame_type != FrameType.DAY:\n"
            "    return\n"
            "universe = self.config.get('universe', [])\n"
            "if not universe:\n"
            "    return\n"
            "returns = {}\n"
            "for sym in universe:\n"
            "    hist = self.get_history(sym, self.lookback, tm, '1d')\n"
            "    if len(hist) < 2:\n"
            "        continue\n"
            "    c = hist['close'].to_numpy()\n"
            "    returns[sym] = c[-1] / c[0] - 1\n"
            "ranked = sorted(returns.items(), key=lambda kv: -kv[1])[:self.top_k]\n"
            "top_set = {sym for sym, _ in ranked}\n"
            "for sym in universe:\n"
            "    pos = self.broker.positions.get(sym)\n"
            "    shares = pos.shares if pos else 0\n"
            "    if sym in top_set and shares == 0:\n"
            "        await self.broker.buy_amount(sym, self.invest_amount, price=0, order_time=tm)\n"
            "    elif sym not in top_set and shares > 0:\n"
            "        await self.broker.sell(sym, shares, price=0, order_time=tm)\n"
        ),
    },
    "multi-factor": {
        "description": "多因子策略 — momentum + volatility z-score 综合排名",
        "params": ["lookback", "top_k", "invest", "mom_weight", "vol_weight"],
        "imports": "",
        "init_body": (
            "self.lookback: int = int(self.config.get('lookback', 20))\n"
            "self.top_k = int(self.config.get('top_k', 5))\n"
            "self.invest_amount = float(self.config.get('invest', 100000))\n"
            "self.w_mom = float(self.config.get('mom_weight', 0.5))\n"
            "self.w_vol = float(self.config.get('vol_weight', -0.3))\n"
        ),
        "on_bar_body": (
            "if frame_type != FrameType.DAY:\n"
            "    return\n"
            "universe = self.config.get('universe', [])\n"
            "if not universe:\n"
            "    return\n"
            "scores = {}\n"
            "for sym in universe:\n"
            "    hist = self.get_history(sym, self.lookback, tm, '1d')\n"
            "    if len(hist) < 2:\n"
            "        continue\n"
            "    c = hist['close'].to_numpy()\n"
            "    mom = c[-1] / c[0] - 1\n"
            "    vol = c.std()\n"
            "    scores[sym] = round(self.w_mom * mom + self.w_vol * vol, 4)\n"
            "ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:self.top_k]\n"
            "top_set = {sym for sym, _ in ranked}\n"
            "for sym in universe:\n"
            "    pos = self.broker.positions.get(sym)\n"
            "    shares = pos.shares if pos else 0\n"
            "    if sym in top_set and shares == 0:\n"
            "        await self.broker.buy_amount(sym, self.invest_amount, price=0, order_time=tm)\n"
            "    elif sym not in top_set and shares > 0:\n"
            "        await self.broker.sell(sym, shares, price=0, order_time=tm)\n"
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

        on_bar_lines = t["on_bar_body"].strip().split("\n")
        on_bar_body = "\n        ".join(on_bar_lines)

        imports = (
            "import datetime\n"
            "from typing import Any, Dict\n\n"
            + t["imports"]
            + "\nfrom quantide.core.enums import FrameType\n"
            "from quantide.core.strategy import BaseStrategy\n"
        )
    else:
        init_body = f'logger.debug("{class_name}.__init__ called")'
        on_day_body = f'logger.debug(f"{class_name}.on_day_open called at {{tm}}")'
        imports = (
            "from datetime import datetime\n\n"
            "from loguru import logger\n\n"
            + _DUAL_IMPORT
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
''' + (f"""
    async def init(self):
        self.log(f"{class_name} Initialized")

    async def on_day_open(self, tm: datetime.datetime):
        pass

    async def on_bar(self, tm: datetime.datetime, quote: Dict[str, Any], frame_type: FrameType):
        {on_bar_body}

    async def on_day_close(self, tm: datetime.datetime):
        pass

    async def on_stop(self):
        self.log(f"{class_name} stopped")
""" if template else f"""
    async def on_day_open(self, tm: datetime) -> None:
        {on_day_body}

    async def on_bar(self, tm: datetime, quote: dict | None = None, frame_type=None) -> None:
        pass

    async def on_day_close(self, tm: datetime) -> None:
        pass

    async def on_stop(self) -> None:
        logger.debug(f"{class_name}.on_stop called")
""")

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
