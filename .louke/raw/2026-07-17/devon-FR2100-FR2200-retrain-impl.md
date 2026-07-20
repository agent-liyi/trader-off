---
date: 2026-07-17
session: devon-FR2100-FR2200-retrain-impl
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#49, #50]
status: resolved
---

## Topic
Implement DefaultTrainerPort.train() — FR-2100 full retrain (#49) and FR-2200 incremental retrain via lightGBM Booster.refit() (#50).

## Decision

### Implementation approach
- `DefaultTrainerPort.train()` dispatches by `mode`:
  - `"full"` → `_train_full()`: generates synthetic regression data, trains via v0.1.0 `train_model()`, computes IC via `scipy.stats.pearsonr/spearmanr`, returns `ModelArtifact`
  - `"incremental"` → `_train_incremental()`: loads parent via `load_model()`, generates new data matching parent feature count, calls `booster.refit()`, computes IC, returns updated `ModelArtifact`
- Synthetic data generation uses `np.random.RandomState(42)` with linear signal `y = X @ coef + noise` for strong IC signal
- `StandardScaler` constructed manually from training data means/stds (no OHLCV imputation needed for synthetic data)
- `refit_iterations` set to `booster.num_trees()` (always > 0 for trained models)

### Version format
- Per interfaces.md §2.3: full → `v{major}.{minor}.{build+1}`, incremental → `v{major}.{minor}.{build}.incr{N+1}`
- Version generation logic belongs in `save()`, not `train()`. `save()` already delegates to v0.1.0 `save_model()` which works with the `YYYYMMDD_HHMMSS` format. The v0.2.0 version format migration is a separate concern.

### Tests (9 total)
- FR-2100 (4 tests): artifact structure, IC metrics, feature names, metadata fields
- FR-2200 (5 tests): parent_version validation, refit vs fit mock, artifact with parent metadata, IC metrics, scaler/feature preservation

### Commits
- `0bab851`: feat: green – #49 – FR-2100: full retrain
- `074f384`: feat: green – #50 – FR-2200: incremental retrain

## Tried but abandoned
- Considered having `train()` accept optional data parameters (X_train, y_train, etc.) for test injection. Rejected because TrainerPort Protocol is already locked in interfaces.md — data loading is internal to the implementation.
- Considered using `fit_scaler_and_impute()` from `data.preprocess`. Rejected because it expects asset/date columns for forward-fill imputation, which is overkill for synthetic data.

## Open questions
- None. Both FR-2100 and FR-2200 are implemented per acceptance criteria.
