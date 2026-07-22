"""CLI entry point for trader-off status (FR-0200).

Provides a global status overview and subcommands for inspecting data,
models, and scheduler state. Always outputs JSON.

Subcommands:
    (none) : global status with version, data_source, models, scheduler
    data   : check .quantide/bars/ directory for OHLCV data
    models : check factor_registry/ for factor parquet files
    scheduler : check if scheduler process is running
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _global_status(data: dict) -> dict:
    """Return the global status payload."""
    data.update(
        {
            "version": "v0.5.4",
            "models": _check_models(),
            "scheduler": _check_scheduler(),
        }
    )
    if "data_source" not in data:
        data["data_source"] = "fixture"
    return {"status": "ok", "data": data}


def _status_data() -> dict:
    """Check .quantide/bars/ directory status.

    Returns:
        Dict with data_source and file count info.
    """
    bars_dir = Path(".quantide/bars")
    if not bars_dir.exists():
        return {"status": "ok", "data": {"data_source": "none"}}

    try:
        parquet_files = list(bars_dir.glob("*.parquet"))
        file_count = len(parquet_files)

        # Try to scan the first parquet for date range and asset count
        date_min = None
        date_max = None
        asset_count = 0
        if parquet_files:
            import polars as pl

            try:
                df = pl.read_parquet(parquet_files[0])
                asset_count = df["asset"].n_unique() if "asset" in df.columns else 0
                if "date" in df.columns:
                    dates = df["date"].sort()
                    if len(dates) > 0:
                        date_min = str(dates[0])
                        date_max = str(dates[-1])
            except Exception:
                pass

        return {
            "status": "ok",
            "data": {
                "data_source": "fixture",
                "file_count": file_count,
                "asset_count": asset_count,
                "date_min": date_min,
                "date_max": date_max,
            },
        }
    except Exception:
        return {"status": "ok", "data": {"data_source": "none"}}


def _check_models() -> list:
    """Return model list for global status.

    Returns empty list (dedicated per-model inspection is in ``status models``).
    """
    return []


def _status_models() -> dict:
    """Check factor_registry/ directory for parquet files.

    Returns:
        Dict with models list (parquet filenames).
    """
    registry_dir = Path("factor_registry")
    if not registry_dir.exists():
        return {"status": "ok", "data": {"models": []}}

    try:
        parquet_files = sorted(p.name for p in registry_dir.glob("*.parquet"))
        return {"status": "ok", "data": {"models": parquet_files}}
    except Exception:
        return {"status": "ok", "data": {"models": []}}


def _status_scheduler() -> dict:
    """Check if the scheduler process is running.

    Returns:
        Dict with scheduler status.
    """
    return {"status": "ok", "data": {"scheduler": _check_scheduler()}}


def _check_scheduler() -> str:
    """Check if the scheduler process is running via PID file.

    Returns:
        "running" or "stopped".
    """
    pid_file = Path("scheduler_state/.pid")
    if not pid_file.exists():
        return "stopped"

    try:
        pid = int(pid_file.read_text().strip())
        import os

        os.kill(pid, 0)  # Signal 0 tests if process exists
        return "running"
    except (OSError, ValueError):
        return "stopped"


def main(args: list[str] | None = None) -> int:
    """CLI entry for 'trader-off status' command.

    Args:
        args: Optional command-line arguments. If None or empty, prints
              global status.

    Returns:
        Exit code: 0 on success, non-zero on error.
    """
    if args is None:
        args = []

    try:
        subcommand = args[0] if args else None
    except IndexError:
        subcommand = None

    if subcommand is None:
        result = _global_status({})
    elif subcommand == "data":
        result = _status_data()
    elif subcommand == "models":
        result = _status_models()
    elif subcommand == "scheduler":
        result = _status_scheduler()
    else:
        result = {
            "status": "error",
            "code": 2,
            "message": f"Unknown subcommand: {subcommand}",
        }
        sys.stdout.write(json.dumps(result))
        return 2

    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
