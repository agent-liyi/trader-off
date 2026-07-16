---
date: 2026-07-16
session: devon-v0.1.0-001-batch1-features
agents: [Devon]
spec: v0.1.0-001-lgbm-asset-pricing
related_issues: [#6, #7, #8, #9]
status: resolved
---

## Topic
Batch 1: Project scaffold + Feature engineering (FR-0100 ~ FR-0400). R-G-R TDD for momentum, volatility, volume features, and scaler/imputation.

## Decision

### Project scaffold
- Created `pyproject.toml` with all dependencies (lightgbm, polars, loguru, pydantic, pyyaml, joblib, matplotlib, scipy, pytest, etc.)
- Created all 12 package modules under `src/trader_off/`
- Created utils: `exceptions.py` (5 custom exceptions) and `logging.py` (setup_logger)
- Created test infrastructure: conftest.py with `five_assets_60_days` and `single_asset_ohlcv` fixtures

### FR-0100 Momentum (commit ce4f21c)
- `compute_momentum_features(ohlcv_df: pl.DataFrame) -> pl.DataFrame`
- ret_5, ret_10, ret_20, ret_60 using `close.shift(N)` with `over("asset")`
- **AC-2 workaround**: Original AC says 5 close values produce ret_5[-1] = 0.4, but shift(5) needs 6 rows. Fixed test to use 6 close values [10,11,9,12,14,14].

### FR-0200 Volatility (commit 1e25107)
- `compute_volatility_features(ohlcv_df: pl.DataFrame) -> pl.DataFrame`
- vol_10, vol_20, vol_60 using rolling_std of daily_returns
- Used `min_samples` (not deprecated `min_periods`) for polars >= 1.21
- **AC-2 workaround**: Arithmetic progression 100..110 does NOT produce constant returns. Fixed to use geometric progression 100*1.01^i.

### FR-0300 Volume (commit 36ac6a2)
- `compute_volume_features(ohlcv_df: pl.DataFrame) -> pl.DataFrame`
- turnover_5/10/20 via rolling_mean, vp_corr_5/10/20 via rolling_corr
- Assets with all-NaN turnover: vp_corr columns also nullified (not just turnover cols)
- **loguru capture**: caplog doesn't capture loguru by default. Used custom loguru sink with message list.

### FR-0400 Scaler (commit 0941b47)
- `StandardScaler` dataclass with mean_, std_, feature_names
- `fit_scaler_and_impute`: forward-fill by asset → 0-fill → drop all-NaN cols → z-score
- `transform`: apply saved scaler params without re-fitting
- Line 85 (zero-std guard) covered by `test_constant_column_zero_std`

### Utils tests (commit 894d5ae)
- 5 exception class tests
- 3 logging setup tests (format, file creation, dir creation)

## Tried but abandoned
- **caplog for loguru**: pytest's built-in `caplog` fixture doesn't capture loguru messages. Tried capsys (pytest capture intercepts before capsys sees it). Settled on custom loguru sink with message list.
- **5-value ret_5 test**: The AC-2 math is inconsistent with the spec formula `close[t]/close[t-N]-1`. Kept the formula and adjusted test data to 6 rows.

## Open questions
- millionaire framework dependency: not yet installed; will be needed for FR-1000 strategies
- The AC-FR0100-2 test fixture size (5 vs 6 values) may need upstream correction in acceptance.md
- The AC-FR0200-2 arithmetic progression issue may need upstream correction
