"""CLI entry point for update (self-update).

Fetches latest code from git, reinstalls dependencies, and re-links binaries.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from trader_off import __version__
from trader_off.cli._version import add_version_argument

REPO_HINT = "https://github.com/agent-liyi/trader-off.git"


def _git(*args: str, repo_dir: Path) -> subprocess.CompletedProcess:
    """Run git command and return result."""
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )


def _update(repo_dir: Path) -> dict:
    """Pull latest code and reinstall."""
    # Step 1: stash local changes
    _git("stash", repo_dir=repo_dir)

    # Step 2: pull latest
    pull = _git("pull", "origin", "main", repo_dir=repo_dir)
    if pull.returncode != 0:
        return {"status": "error", "code": 4, "message": f"git pull failed: {pull.stderr}"}

    old_version = __version__
    # Step 3: reinstall deps
    uv = subprocess.run(
        ["uv", "sync"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if uv.returncode != 0:
        return {"status": "error", "code": 5, "message": f"uv sync failed: {uv.stderr}"}

    # Step 4: re-link binaries via install script
    install_script = repo_dir / "scripts" / "install.sh"
    if install_script.exists():
        subprocess.run(["bash", str(install_script)], capture_output=True, text=True)

    return {
        "status": "ok",
        "data": {
            "old_version": old_version,
            "new_version": "see `to <command> --version`",
            "pull_output": pull.stdout[-200:] if pull.stdout else "",
        },
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry for 'trader-off update'."""
    parser = argparse.ArgumentParser(
        prog="to update",
        description="Update trader-off from git (pull + uv sync + relink)",
    )
    add_version_argument(parser, "update")
    parser.add_argument(
        "--repo-dir",
        type=str,
        default=None,
        help="Path to trader-off repo (default: auto-detect from this file's location)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    repo_dir = Path(args.repo_dir) if args.repo_dir else Path(__file__).parent.parent.parent.resolve()

    result = _update(repo_dir)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0 if result["status"] == "ok" else 4
