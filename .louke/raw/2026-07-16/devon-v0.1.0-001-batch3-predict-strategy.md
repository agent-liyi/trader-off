---
date: 2026-07-16
session: devon-v0.1.0-001-batch3-predict-strategy
agents: [Devon]
spec: v0.1.0-001-lgbm-asset-pricing
related_issues: [#14, #15]
status: resolved
---

## Topic
Batch 3: Prediction service (FR-0900) and LGBMTop20Strategy (FR-1000) with millionaire compat shim.

## Decision

### FR-0900 Prediction (commit 67b6d55)
- `predict(model_version, watchlist, asof_date, data_loader=None, ...) -> pl.DataFrame`
- Async function using await data_loader.get_history()
- Loads model via load_model, applies scaler (z-score), calls booster.predict
- Skips assets with <120 days history → predict_skipped.json + WARNING
- Sorts by score descending, assigns rank from 1

### DataLoader abstraction (in data/loader.py)
- Created minimal DataLoader class with async get_history(asset, end_date, count)
- Pluggable: tests inject Mock, production wraps millionaire fetcher
- Default returns empty DataFrame with correct schema

### FR-1000 Strategy (commit 1141951)
- `LGBMTop20Strategy(BaseStrategy)` — inherits from compat shim
- async init(): loads model via load_model
- async on_day_open(tm): calls predict, rebalances to top_k equal weight
- extra dict: {reason, score, rank, model_version} on each trade
- Config: model_version, top_k=20, min_score=-inf, watchlist
- Config YAML: configs/strategy/lgbm_top20.yaml

### millionaire compat shim (strategies/compat.py)
- try/except ImportError on quantide package
- Fallback: stub BaseStrategy with async lifecycle methods (init, on_day_open, on_bar, on_day_close, on_stop)
- Fallback: stub Broker ABC with abstract trade_target_pct
- Real millionaire classes used if installed

## Tried but abandoned
- Mocking predict at strategy module level failed (local imports). Fixed by patching at source module (trader_off.prediction.service.predict).

## Open questions
- DataLoader real implementation needs millionaire fetcher integration
- Coverage at 90% — predict edge cases and compat shim stubs not fully covered
- Strategy needs portfolio universe (watchlist) config — currently must be set explicitly
