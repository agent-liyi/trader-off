---
date: 2026-07-17
session: devon-v0.2.0-001-fr1700-psi
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#45]
status: resolved
---

## Topic
FR-1700: PSI 漂移检测 (Population Stability Index drift detection)

## Decision

### Files created
- `src/trader_off/scheduler/drift/__init__.py` — package init, exports DriftResult
- `src/trader_off/scheduler/drift/result.py` — DriftResult dataclass (method, score, threshold, is_drift, bin_edges)
- `src/trader_off/scheduler/drift/psi.py` — compute_psi, compute_feature_psi, detect_psi
- `tests/unit/scheduler/test_psi.py` — 15 tests covering all 4 ACs + edge cases

### Implementation details
- PSI formula: `sum((p_i - q_i) * ln(p_i / q_i))` with quantile-based binning from reference
- Zero-bin handling: epsilon smoothing with re-normalization
- Bin edges: `np.quantile` on reference with strict monotonicity enforcement via `np.nextafter` loop
- NaN handling in compute_feature_psi: polars treats np.nan as valid float64 (not null), so we filter via `np.isfinite` after `drop_nulls()`
- Degenerate case: all baseline values identical → PSI = 0 (zero variance)
- detect_psi wraps compute_psi with threshold comparison → DriftResult

### AC coverage (4/4)
- AC-FR1700-01: Same distribution → PSI ≈ 0 (< 1e-6) ✓
- AC-FR1700-02: Shifted [1..100] → [50..150] → PSI > 0.5 ✓ (computed: ~6.4)
- AC-FR1700-03: 20 feature columns → DataFrame(feature, psi, is_drift) ✓
- AC-FR1700-04: All-NaN current → psi=0.0, is_drift=False, WARNING ✓

### Test metrics
- 15 tests, all pass
- Coverage: 100% (76/76 statements across 3 files in drift package)
- Source LOC (psi.py): 63 statements
- Green commit: agent-liyi/trader-off@34fdb88

### Reference values verified
- AC-1: baseline=[1..10], current=[1..10] → PSI ≈ 0 (< 1e-6)
- AC-2: baseline=[1..100], current=[50..150], n_bins=10 → PSI ≈ 6.4
  - First 5 bins: ~10 reference samples each, ~0 current samples
  - (0.1 - ε) * ln(0.1/ε) ≈ 1.15 per bin × 5 ≈ 5.75
  - Last bin: p≈0.1, q≈0.5 → (0.1-0.5)*ln(0.1/0.5) ≈ 0.644
  - Total ≈ 6.4 > 0.5 ✓

## Tried but abandoned

### Polars NaN handling
- Initially used `drop_nulls()` only → missed NaN because polars treats np.nan as valid Float64
- Fixed by chaining `np.isfinite()` filter after `to_numpy()`

### Only fixing edges[1] for monotonicity
- Original `edges[1] = np.nextafter(edges[0], ...)` only fixed first pair
- Multiple consecutive tied quantile edges (e.g. 50%+ data at same value) broke np.digitize
- Fixed by looping over all consecutive pairs: `for i in range(1, len(edges))`

### All-baseline-identical edge case
- With constant baseline (e.g. [2.0]*5), all quantile edges collapse to one value
- np.digitize fails with "not monotonic" error
- Added early return: `if np.allclose(baseline, baseline[0]): return 0.0`

## Open questions
- None for FR-1700. KS drift detection (FR-1800) and DriftDetector (FR-2600) are separate issues.
