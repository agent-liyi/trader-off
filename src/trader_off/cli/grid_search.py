"""CLI entry point for grid-search (FR-0100).

Encapsulates quantide.service.grid_search.GridSearch for parameter grid optimization.
Runs backtests in parallel processes, finds best parameters by Sharpe ratio,
and outputs JSON.

Exit codes:
    0: Success
    2: Argparse error (missing/invalid args)
    4: Config file validation failure (file not found, invalid YAML, missing param_space)
    5: GridSearch engine failure (quantide exception)

NFR-0100: All quantide imports are function-scope (lazy), not module-top-level.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from loguru import logger


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off grid-search' command.

    Args:
        argv: Command-line arguments. If None, reads from sys.argv[1:].

    Returns:
        Exit code: 0 success, 2 argparse error, 4 config error, 5 engine failure.
    """
    parser = _build_argparser()
    args = parser.parse_args(argv)

    # --- Config validation (exit code 4) ---
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return 4

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as e:
        logger.error(f"Config validation failed: {e}")
        return 4

    if not config or not isinstance(config, dict):
        logger.error("Config file is empty or not a mapping")
        return 4

    param_space = config.get("param_space", {})
    if not param_space or not isinstance(param_space, dict):
        logger.error("Config must contain a non-empty 'param_space' mapping")
        return 4

    # Build base_config from other YAML keys
    base_config = {k: v for k, v in config.items() if k != "param_space"}
    param_grid = param_space

    # --- Strategy resolution (exit code 4) ---
    try:
        strategy_cls = _resolve_strategy_class(args.strategy)
    except ValueError as e:
        logger.error(f"Strategy resolution failed: {e}")
        return 4

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    # --- Run grid search (exit code 5 on failure) ---
    # NFR-0100: Lazy function-scope quantide import
    from quantide.service.grid_search import GridSearch

    try:
        gs = GridSearch(
            strategy_cls=strategy_cls,
            base_config=base_config,
            param_grid=param_grid,
            start_date=start,
            end_date=end,
            interval="1d",
            initial_cash=args.capital,
            max_workers=args.max_workers,
        )
        results = gs.run()
    except Exception as e:
        logger.error(f"GridSearch engine failed: {e}")
        return 5

    # --- Extract results ---
    if results.empty:
        output: dict[str, Any] = {
            "status": "ok",
            "data": {
                "best": None,
                "completed": 0,
                "errors": 0,
            },
        }
    else:
        completed = len(results)
        best_row = results.iloc[0].to_dict()

        # Identify grid param keys (those in param_grid) vs result keys
        grid_keys = set(param_grid.keys())
        params = {k: best_row[k] for k in grid_keys if k in best_row}
        sharpe = best_row.get("sharpe")
        total_return = best_row.get("total_return")

        output = {
            "status": "ok",
            "data": {
                "best": {
                    "params": params,
                    "sharpe": float(sharpe) if sharpe is not None else None,
                    "total_return": float(total_return) if total_return is not None else None,
                },
                "completed": completed,
                "errors": 0,
            },
        }

    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    return 0


def _resolve_strategy_class(strategy_name: str) -> type:
    """Resolve strategy class from name.

    Args:
        strategy_name: Strategy name (e.g., 'lgbm_top20', 'optimized_topk').

    Returns:
        Strategy class.

    Raises:
        ValueError: If strategy_name is not recognized.
    """
    if strategy_name == "lgbm_top20":
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        return LGBMTop20Strategy
    elif strategy_name == "optimized_topk":
        from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

        return OptimizedTopKStrategy
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")


def _build_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for grid-search CLI."""
    parser = argparse.ArgumentParser(
        prog="trader-off-grid-search",
        description="Grid search for strategy parameter optimization",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to YAML config file with param_space",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        help="Strategy name (e.g., optimized_topk, lgbm_top20)",
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000,
        help="Initial capital (default: 1000000)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of parallel processes (default: 4)",
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
