---
date: 2026-07-25
spec: v0.7.4-001-version-flag
status: confirmed
---

# v0.7.4 — version flag for all CLIs — Acceptance Criteria

- **Spec ID**: v0.7.4-001-version-flag
- **Created**: 2026-07-25

> Each requirement has a dedicated section. Every `### AC-N` heading is intentionally undecorated; the canonical identifier is on the next line.

<a id="ac-fr-0100"></a>

## FR-0100 `--version` on all 15 CLI commands

### AC-1
AC-FR0100-01
- **GIVEN** the package is installed with the 15 console scripts declared by `pyproject.toml` `[project.scripts]`
- **WHEN** each command is invoked in a subprocess with `--version` as its only argument
- **THEN** all 15 subprocesses exit with status `0`, write the exact expected bytes to stdout, and write no bytes to stderr:
  - `trader-off-backtest` → `trader-off-backtest v0.7.4\n`
  - `trader-off-optimize` → `trader-off-optimize v0.7.4\n`
  - `trader-off-mine-factors` → `trader-off-mine-factors v0.7.4\n`
  - `trader-off-scheduler` → `trader-off-scheduler v0.7.4\n`
  - `trader-off-sync-data` → `trader-off-sync-data v0.7.4\n`
  - `trader-off-init` → `trader-off-init v0.7.4\n`
  - `trader-off-stock-list` → `trader-off-stock-list v0.7.4\n`
  - `trader-off-check-factor` → `trader-off-check-factor v0.7.4\n`
  - `trader-off-paper-trade` → `trader-off-paper-trade v0.7.4\n`
  - `trader-off-grid-search` → `trader-off-grid-search v0.7.4\n`
  - `trader-off-live` → `trader-off-live v0.7.4\n`
  - `trader-off-live-trade` → `trader-off-live-trade v0.7.4\n`
  - `trader-off-generate-strategy` → `trader-off-generate-strategy v0.7.4\n`
  - `trader-off-status` → `trader-off-status v0.7.4\n`
  - `trader-off-server` → `trader-off-server v0.7.4\n`

### AC-2
AC-FR0100-02
- **GIVEN** the 15 command names listed in AC-FR0100-01
- **WHEN** `[project.scripts]` in `pyproject.toml` is parsed
- **THEN** its key set contains exactly those 15 names, and every one of those installed entry points satisfies AC-FR0100-01

### AC-3
AC-FR0100-03
- **GIVEN** any of the 15 commands has command-specific required arguments or normally performs file, network, server, scheduler, trading, or data-processing work
- **WHEN** it is invoked with only `--version`
- **THEN** it satisfies AC-FR0100-01 without reporting missing required arguments and without entering its normal operation

<a id="ac-fr-0200"></a>

## FR-0200 Release version is `0.7.4`

### AC-1
AC-FR0200-01
- **WHEN** `src/trader_off/__init__.py` is loaded and `pyproject.toml` is parsed
- **THEN** `trader_off.__version__ == "0.7.4"`
- **AND** `pyproject.toml` `[project].version == "0.7.4"`
- **AND** the two values are equal

### AC-2
AC-FR0200-02
- **WHEN** `src/trader_off/cli/_version.py` and the 15 CLI entry-point modules are inspected
- **THEN** the shared version formatter obtains the runtime version from `trader_off.__version__`
- **AND** none of those files defines an independent hard-coded `"0.7.4"` version value

<a id="ac-nfr-0100"></a>

## NFR-0100 Function-scope lazy imports (inherited)

### AC-1
AC-NFR0100-01
- **GIVEN** the Python source modules targeted by the 15 `[project.scripts]` entry points
- **WHEN** their abstract syntax trees are inspected for `import quantide` and `from quantide...` nodes
- **THEN** every such node has a `FunctionDef` or `AsyncFunctionDef` ancestor
- **AND** no such node occurs at module scope, class scope, or solely under a module-level `TYPE_CHECKING` branch

### AC-2
AC-NFR0100-02
- **WHEN** imports added for the shared CLI version behavior are inspected
- **THEN** module-scope imports of standard-library modules, `trader_off.cli._version.add_version_argument`, or `trader_off.__version__` do not violate NFR-0100
- **AND** no new module-scope import from `quantide` is introduced by this patch
