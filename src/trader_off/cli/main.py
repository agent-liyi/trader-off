"""Unified CLI entry point: ``to <command> [args...]``.

Dispatches to the per-command ``main()`` functions with lazy imports so
startup stays fast (heavy deps like lightgbm are only loaded when the
subcommand that needs them actually runs).
"""

from __future__ import annotations

import importlib
import sys

from trader_off import __version__

PROG = "to"

# subcommand -> (module path, description)
_COMMANDS: dict[str, tuple[str, str]] = {
    "backtest": ("trader_off.cli.backtest", "策略回测"),
    "optimize": ("trader_off.portfolio.cli", "组合优化"),
    "mine-factors": ("trader_off.factor_mining.cli", "因子挖掘"),
    "scheduler": ("trader_off.scheduler.cli", "调度重训"),
    "sync-data": ("trader_off.cli.sync_data", "数据同步"),
    "init": ("trader_off.cli.init_data", "初始化数据目录"),
    "stock-list": ("trader_off.cli.stock_list", "股票列表"),
    "check-factor": ("trader_off.cli.check_factor", "因子有效性检查"),
    "paper-trade": ("trader_off.cli.paper_trade", "纸交易"),
    "grid-search": ("trader_off.cli.grid_search", "参数寻优"),
    "live": ("trader_off.cli.live", "实时行情"),
    "live-trade": ("trader_off.cli.live_trade", "实盘交易"),
    "generate-strategy": ("trader_off.cli.generate_strategy", "生成策略"),
    "status": ("trader_off.cli.status", "全局状态"),
    "server": ("trader_off.cli.server", "REST API 服务"),
    "update": ("trader_off.cli.update", "版本更新检查"),
}


def _print_help(file=None) -> None:
    """Print the top-level help text."""
    out = file if file is not None else sys.stdout
    width = max(len(name) for name in _COMMANDS)
    lines = [
        f"usage: {PROG} <command> [args...]",
        "",
        f"trader-off unified CLI (v{__version__})",
        "",
        "commands:",
        *(f"  {name:<{width}}  {desc}" for name, (_mod, desc) in _COMMANDS.items()),
        "",
        f"Run '{PROG} <command> --help' for command-specific options.",
    ]
    print("\n".join(lines), file=out)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``to`` command.

    Args:
        argv: Optional argument list (excluding the program name).
              Defaults to ``sys.argv[1:]``.

    Returns:
        Exit code: 0 on success, 2 on unknown command, otherwise the
        subcommand's own exit code.
    """
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return 0
    if args[0] in ("-V", "--version"):
        sys.stdout.write(f"{PROG} (trader-off) v{__version__}\n")
        return 0

    command, rest = args[0], args[1:]
    entry = _COMMANDS.get(command)
    if entry is None:
        sys.stderr.write(f"{PROG}: unknown command '{command}'\n")
        _print_help(file=sys.stderr)
        return 2

    module_path, _desc = entry
    module = importlib.import_module(module_path)
    result = module.main(rest)
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
