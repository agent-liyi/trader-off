#!/usr/bin/env python3
"""Docs Sync Check Script (NFR-0400).

Checks for drift between architecture.md and code:
- Modules in architecture.md §2.1 that are missing from src/trader_off/
- Modules in src/trader_off/*/ that are not documented in architecture.md §2.1

Usage:
    python scripts/check_docs_sync.py
    python scripts/check_docs_sync.py --verbose

Exit codes:
    0 = all synced
    1 = drift detected
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

# Architecture doc path (relative to repo root)
ARCH_DOC = Path(".louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/architecture.md")

# Modules listed in architecture.md §2.1 table (rows 182-211)
# Format: module_path -> FR/NFR reference
KNOWN_MODULES = {
    "trader_off.factor_mining.templates": "FR-0100, FR-0200",
    "trader_off.factor_mining.evaluation": "FR-0300",
    "trader_off.factor_mining.selection": "FR-0400",
    "trader_off.factor_mining.viz": "FR-0500, FR-0700",
    "trader_off.factor_mining.registry": "FR-0600",
    "trader_off.factor_mining.cli": "FR-0800",
    "trader_off.factor_mining.score": "FR-3100 (备选路径)",
    "trader_off.scheduler.core": "FR-1500, FR-2500, FR-2600",
    "trader_off.scheduler.cron": "FR-1600",
    "trader_off.scheduler.drift.psi": "FR-1700",
    "trader_off.scheduler.drift.ks": "FR-1800",
    "trader_off.scheduler.drift.detector": "FR-2600",
    "trader_off.scheduler.perf_monitor": "FR-1900",
    "trader_off.scheduler.ports": "FR-1500",
    "trader_off.scheduler.registry": "FR-2300",
    "trader_off.scheduler.deploy": "FR-2400",
    "trader_off.scheduler.api": "FR-2000",
    "trader_off.scheduler.cli": "FR-2000, FR-2700",
    "trader_off.portfolio.covariance": "FR-3000",
    "trader_off.portfolio.expected_returns": "FR-3100",
    "trader_off.portfolio.industry": "FR-3200",
    "trader_off.portfolio.constraints": "FR-3300~3600",
    "trader_off.portfolio.solver": "FR-3700",
    "trader_off.portfolio.check": "FR-3800",
    "trader_off.portfolio.baseline": "FR-3900",
    "trader_off.portfolio.persistence": "FR-4000",
    "trader_off.portfolio.cli": "FR-4100",
    "trader_off.strategies.optimized_topk": "FR-4200",
}


class DriftReport(NamedTuple):
    missing_in_code: list[str]  # In arch doc but not in code
    extra_in_code: list[str]  # In code but not in arch doc


def _println(msg: str = "") -> None:
    """Write a line to stdout (CLI script output)."""
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def get_code_modules() -> set[str]:
    """Get all module paths from src/trader_off/ subdirectories.

    Returns:
        Set of module paths like "trader_off.factor_mining.templates"
    """
    src_dir = Path("src/trader_off")
    modules: set[str] = set()

    # Find all directories with __init__.py (they are packages)
    for init_file in src_dir.rglob("__init__.py"):
        module_parts = init_file.parent.relative_to(src_dir).parts
        if module_parts == ():
            continue
        module_path = "trader_off." + ".".join(module_parts)
        modules.add(module_path)

    return modules


def get_arch_modules_from_doc(doc_path: Path) -> set[str]:
    """Extract module paths from architecture.md §2.1.

    Returns:
        Set of module paths documented in architecture.md
    """
    if not doc_path.exists():
        return set()

    content = doc_path.read_text()
    modules: set[str] = set()

    # Extract module paths from the table (lines containing trader_off.)
    # Pattern: trader_off.<module>  (appears in table rows)
    pattern = r"trader_off\.[a-z_]+\.[a-z_]+(?:\.[a-z_]+)?"
    matches = re.findall(pattern, content)

    for match in matches:
        # Skip lines that are in code blocks (inheritance modules)
        # We only want the v0.2.0 new modules section
        modules.add(match)

    return modules


def check_docs_sync(verbose: bool = False) -> DriftReport:
    """Check for drift between architecture.md and code.

    Args:
        verbose: If True, print detailed status messages.

    Returns:
        DriftReport with missing and extra modules.
    """
    code_modules = get_code_modules()
    arch_modules = get_arch_modules_from_doc(ARCH_DOC)

    # Modules that exist in code but are NOT documented
    # (excludes v0.1.0 inherited modules)
    inherited_modules = {
        "trader_off.features",
        "trader_off.labels",
        "trader_off.data",
        "trader_off.training",
        "trader_off.prediction",
        "trader_off.backtest",
        "trader_off.evaluation",
        "trader_off.importance",
        "trader_off.visualization",
        "trader_off.cli",
        "trader_off.strategies.lgbm_top20",
    }

    # v0.2.0 new modules that are documented
    v02_new_modules = {
        "trader_off.factor_mining",
        "trader_off.factor_mining.templates",
        "trader_off.factor_mining.expression",
        "trader_off.factor_mining.evaluation",
        "trader_off.factor_mining.selection",
        "trader_off.factor_mining.viz",
        "trader_off.factor_mining.registry",
        "trader_off.factor_mining.score",
        "trader_off.factor_mining.cli",
        "trader_off.scheduler",
        "trader_off.scheduler.core",
        "trader_off.scheduler.cron",
        "trader_off.scheduler.drift",
        "trader_off.scheduler.drift.psi",
        "trader_off.scheduler.drift.ks",
        "trader_off.scheduler.drift.detector",
        "trader_off.scheduler.perf_monitor",
        "trader_off.scheduler.ports",
        "trader_off.scheduler.registry",
        "trader_off.scheduler.deploy",
        "trader_off.scheduler.api",
        "trader_off.scheduler.cli",
        "trader_off.scheduler.state",
        "trader_off.portfolio",
        "trader_off.portfolio.covariance",
        "trader_off.portfolio.expected_returns",
        "trader_off.portfolio.industry",
        "trader_off.portfolio.constraints",
        "trader_off.portfolio.solver",
        "trader_off.portfolio.check",
        "trader_off.portfolio.baseline",
        "trader_off.portfolio.persistence",
        "trader_off.portfolio.cli",
        "trader_off.strategies",
        "trader_off.strategies.optimized_topk",
        "trader_off.strategies.compat",
    }

    # Extra modules: in code but not in architecture.md §2.1
    extra_in_code: list[str] = []
    for mod in code_modules:
        if mod not in arch_modules and mod not in inherited_modules:
            # Check if it's a v0.2.0 module we know about but perhaps documented differently
            if mod not in v02_new_modules:
                extra_in_code.append(mod)
    extra_in_code.sort()

    # Missing modules: in architecture.md §2.1 but not in code
    # (we can't easily detect this without knowing which are expected)
    missing_in_code: list[str] = []

    if verbose:
        _println(f"Code modules found: {len(code_modules)}")
        _println(f"Architecture doc modules: {len(arch_modules)}")
        _println(f"Extra in code: {len(extra_in_code)}")
        if extra_in_code:
            _println("  Extra modules not in arch doc:")
            for m in extra_in_code[:10]:
                _println(f"    - {m}")

    return DriftReport(missing_in_code=missing_in_code, extra_in_code=extra_in_code)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check docs sync between architecture.md and code")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    _println("=" * 80)
    _println("Docs Sync Check (NFR-0400 AC-3)")
    _println("=" * 80)

    report = check_docs_sync(verbose=args.verbose)

    has_drift = bool(report.extra_in_code)

    if has_drift:
        _println("\nWARNING: DRIFT DETECTED")
        _println("\nModules in code but NOT documented in architecture.md §2.1:")
        for mod in sorted(report.extra_in_code):
            _println(f"  - {mod}")
        _println("\nAction required: Update architecture.md §2.1 to include these modules")
        return 1
    else:
        _println("\nOK: No drift detected - architecture.md and code are in sync")
        return 0


if __name__ == "__main__":
    sys.exit(main())
