---
date: 2026-07-25
spec: v0.7.4-001-version-flag
status: confirmed
locked: false
---

# v0.7.4 — version flag for all CLIs — Spec

- **Spec ID**: v0.7.4-001-version-flag
- **Created**: 2026-07-25
- **Status**: Confirmed

> This document describes requirements and boundaries. Observable, assertable pass conditions are in `acceptance.md`.

## User Stories

<a id="us-0010"></a>

### US-0010
story: As a user or automation agent, I want every installed trader-off CLI to report its identity and release version through a consistent flag, so that I can verify the executable version without running the command's normal operation.
priority: P0

## Usage Scenarios

### scenario-0010

After installing trader-off, a user invokes any console command with only `--version`. The command prints its own console-script name and the package runtime version, then exits successfully without requiring the command's normal mandatory arguments.

## Functional Requirements

<a id="fr-0100"></a>

### FR-0100 `--version` on all 15 CLI commands

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

**Tier**: A

Each of the 15 console scripts declared in `pyproject.toml` under `[project.scripts]` shall accept a standalone `--version` flag. Each invocation shall exit with status `0`, write exactly one line to stdout in the form `trader-off-<name> v0.7.4`, including one trailing newline, and write nothing to stderr.

The complete command and output inventory is:

- `trader-off-backtest --version` → `trader-off-backtest v0.7.4`
- `trader-off-optimize --version` → `trader-off-optimize v0.7.4`
- `trader-off-mine-factors --version` → `trader-off-mine-factors v0.7.4`
- `trader-off-scheduler --version` → `trader-off-scheduler v0.7.4`
- `trader-off-sync-data --version` → `trader-off-sync-data v0.7.4`
- `trader-off-init --version` → `trader-off-init v0.7.4`
- `trader-off-stock-list --version` → `trader-off-stock-list v0.7.4`
- `trader-off-check-factor --version` → `trader-off-check-factor v0.7.4`
- `trader-off-paper-trade --version` → `trader-off-paper-trade v0.7.4`
- `trader-off-grid-search --version` → `trader-off-grid-search v0.7.4`
- `trader-off-live --version` → `trader-off-live v0.7.4`
- `trader-off-live-trade --version` → `trader-off-live-trade v0.7.4`
- `trader-off-generate-strategy --version` → `trader-off-generate-strategy v0.7.4`
- `trader-off-status --version` → `trader-off-status v0.7.4`
- `trader-off-server --version` → `trader-off-server v0.7.4`

The version path shall be shared: CLI parsers may register the flag through the common `src/trader_off/cli/_version.py` helper rather than defining independent version strings.

**Boundaries and exclusions**:

- Acceptance covers invocation with `--version` as the only argument. Ordering, precedence, and behavior when it is combined with other arguments are out of scope.
- A short alias such as `-V` is not required.
- Changes to normal command execution, normal command output, or the existing command inventory are out of scope.

---

<a id="fr-0200"></a>

### FR-0200 Release version is `0.7.4`

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

**Tier**: A

The release version shall be `0.7.4` in both version-bearing project files:

- `src/trader_off/__init__.py`: `__version__ = "0.7.4"`
- `pyproject.toml`: `[project].version = "0.7.4"`

The two values shall be equal. `trader_off.__version__` is the runtime source consumed by the shared CLI version helper; `pyproject.toml` carries matching build and distribution metadata. The CLI helper and individual CLI modules shall not maintain an independent hard-coded release version.

**Boundaries and exclusions**:

- Updating historical version references in documentation, fixtures, release notes, or unrelated runtime payloads is out of scope.
- Dynamic generation of `pyproject.toml` metadata from `trader_off.__version__`, or vice versa, is not required.

---

## Non-Functional Requirements

<a id="nfr-0100"></a>

### NFR-0100 Function-scope lazy imports (inherited)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

**Tier**: inherited constraint

The inherited lazy-import boundary remains in force for the 15 CLI entry-point modules changed by this patch: imports from the optional heavyweight `quantide` package shall occur only inside function bodies, never at module scope, class scope, or in a module-level `TYPE_CHECKING` block. This patch does not require standard-library imports, `add_version_argument`, `trader_off.__version__`, or other project-internal imports to move into function scope.

---

## Known Constraints and Exclusions

- The authoritative command inventory for FR-0100 is the set of 15 entries currently declared by `[project.scripts]` in `pyproject.toml`.
- The exact release targeted by this patch is `0.7.4`; support for deriving output for later releases is achieved through the runtime `trader_off.__version__` path but later version bumps are outside this spec.
- The patch adds no requirement to redesign argument parsing or CLI architecture.
- GitHub issue granularity is one issue per functional requirement: one for FR-0100 and one for FR-0200. NFR-0100 remains an inherited constraint and is not a separate feature issue.

## Clarification Log

- **2026-07-25, interactive round 1**: The user confirmed that the 15-command scope is exactly the current `[project.scripts]` inventory; standalone `--version` must return status `0`, exact stdout with one trailing newline, and empty stderr; combinations with other arguments are outside acceptance; both version-bearing files must equal `0.7.4`; lazy-import scope covers optional heavyweight dependencies, with `quantide` as the inherited package boundary; FR-0100 and FR-0200 are tier A and shall remain separate issues.
- All requirements reflect explicit user answers. No inline-discussion thread is open; self quote-check is expected to return exit code 0.
