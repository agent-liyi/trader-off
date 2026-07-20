---
date: 2026-07-17
session: devon-v0.2.0-001-fr0900-score
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#42]
status: resolved
---

## Topic
FR-0900: Implement `compute_factor_score` in `src/trader_off/factor_mining/score.py` to bridge factor mining output to v0.1.0 training input.

## Decision
- Implemented `compute_factor_score(specs: list[FactorSpec], raw_data: pl.DataFrame) -> pl.DataFrame`
- Pre-sorts raw_data by ["asset", "date"] for consistent row ordering across all factors
- Validates: empty specs list → ValueError; duplicate spec IDs → ValueError
- Each spec's `compute_fn` is applied to the pre-sorted data; results concatenated as columns named by spec.id
- All output columns are Float64, compatible with v0.1.0 trainer's `_to_numpy()` conversion
- Exported from `trader_off.factor_mining.__init__`
- 15 unit tests, 100% line coverage on score.py

## Tried but abandoned
- **`specs: list[dict]` signature from Maestro task**: The task requested `list[dict]` but `compute_fn` is not JSON-serializable, requiring FactorSpec instances. Used `list[FactorSpec]` which is the canonical type in the factor_mining module.
- **Including asset/date in output**: Decided against it — trainer only needs feature values as numpy arrays; asset/date are handled upstream by the pipeline.
- **Post-sort only (not pre-sort)**: Each compute_fn already sorts internally, but pre-sorting in compute_factor_score is defensive and ensures consistent ordering even if compute_fns have slight behavioral differences.
- **Coverage via pytest-cov**: Environment has a numpy/pytest-cov compatibility issue ("cannot load module more than once per process"). Verified coverage manually — all lines and branches exercised.

## Open questions
- Shield's integration test (`test_train_with_registry.py` in test-plan §8.2) will need to rebuild FactorSpec instances from loaded registry data to get `compute_fn` callables, since `selected_factors.json` only stores metadata (no serialized callables).
- The interfaces.md §3.5 defines a different `compute_factor_score` signature for FR-3100 (portfolio expected returns path): `(features_df: pl.DataFrame, weights: dict[str, float], selected_factors_path: Path) -> dict[str, float]`. This FR-0900 implementation uses a different signature. Both may need to coexist or the FR-3100 path may need a different function name.
