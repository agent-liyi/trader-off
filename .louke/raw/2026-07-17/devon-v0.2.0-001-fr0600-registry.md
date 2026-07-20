---
date: 2026-07-17
session: devon-v0.2.0-001-fr0600-registry
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#39]
status: resolved
supersedes: []
---

## Topic
FR-0600: 因子注册表持久化 — `save_factor_registry` / `load_factor_registry` with YAML/JSON formats, atomic write, and schema validation.

## Decision
Implemented `trader_off.factor_mining.registry` module with:
- `save_factor_registry(specs, out_dir, *, fmt="yaml"|"json") -> Path`
- `load_factor_registry(path) -> dict`
- `FactorRegistrySchemaError(ValueError)`

Refactored internals:
- `_spec_to_base_dict(spec)` — shared factor serialization
- `_atomic_write(content, target, tmp_dir, suffix)` — reusable atomic write
- `_load_raw_data(path)` / `_validate_registry_schema(data)` — separated concerns

### Key design decisions:
1. **Function signatures**: Followed Maestro's simplified two-function API rather than interfaces.md's three-function version (save_factor_registry + separate save_selected_factors). Combined both YAML and JSON output into single function with `fmt` parameter.
2. **Return type**: `load_factor_registry` returns `dict` (not `list[FactorSpec]`) because FactorSpec has non-serializable `compute_fn` (Callable).
3. **Atomic write**: `tempfile.mkstemp` in same directory + `os.replace` for atomic rename. Temp file cleanup on error.
4. **Schema validation**: Validates top-level fields (`factor_template_version`, `factors`) and per-factor fields (`id`, `category`, `template`, `params`, `formula`).

### Tool conflict resolved:
- `ruff UP017` wants `datetime.UTC` but `mypy` (pre-commit v1.18.1) doesn't recognize it.
- Resolution: Kept `datetime.now(timezone.utc)` with `# noqa: UP017` comment.
- Also added `# type: ignore[import-untyped]` on `import yaml` for mypy.

### Commits:
- `0a7f850` feat: green – #39 – implement factor registry persistence with atomic write and schema validation
- `23ececf` refactor: #39 – extract _spec_to_base_dict, _atomic_write, _validate_registry_schema helpers
- `0036c2b` refactor: #39 – export save/load_factor_registry and FactorRegistrySchemaError from factor_mining package

### AC coverage:
- AC-FR0600-01: YAML format with correct schema fields (6 tests)
- AC-FR0600-02: JSON format with correct schema fields (4 tests)
- AC-FR0600-03: Auto-create directory (3 tests)
- AC-FR0600-04: Schema validation on load (7 tests)
- Additional: atomic write, round-trip, edge cases (8 tests)
- Total: 28 tests, 228 LOC implementation, 466 LOC tests

## Tried but abandoned
- `from datetime import UTC, datetime` — ruff auto-fixed to this but mypy rejected it
- `datetime.UTC` (module attribute) — same mypy issue
- Single `save_factor_registry` with optional evaluation params — overcomplicated; kept simple

## Open questions
- interfaces.md specifies three functions (save_factor_registry, load_factor_registry, save_selected_factors) but Maestro provided two-function API. Consider aligning interfaces.md in a future spec update.
- `load_factor_registry` returns `dict` instead of `list[FactorSpec]` — downstream consumers will need to reconstruct FactorSpec from dicts.
- The JSON format defaults `icir`, `ic_mean`, `ic_std` to 0.0 — when saving selected factors with actual evaluations, a separate function or extended parameters may be needed.
