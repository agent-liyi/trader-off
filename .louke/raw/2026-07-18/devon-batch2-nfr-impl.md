---
date: 2026-07-18
session: devon-v0.2.0-001-batch2-nfr-impl
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#70, #71, #72, #77, #78]
status: resolved
---

## Topic: Implement NFR batch 2 (NFR-0200, 0300, 0400, 0900, 1000)

## Decision

### NFR-0200 (#70) - Coverage tooling
- Added `[tool.coverage]` config to pyproject.toml with branch=true, parallel=true
- Added unit tests in `tests/unit/nfr/test_nfr_0200_coverage.py` (5 tests)
- Commit: `6192b2a`

### NFR-0300 (#71) - Mutation testing
- Added `mutmut>=2.0` to dev dependency group in pyproject.toml
- Created `scripts/run_mutation_tests.sh` (executable script with usage docs)
- Added unit tests in `tests/unit/nfr/test_nfr_0300_mutmut.py` (5 tests)
- Commit: `9a68741`

### NFR-0400 (#72) - ADR docs + docs sync
- Created `docs/adr/0001-cvxpy-scipy-fallback.md` (ADR for cvxpy+scipy fallback)
- Created `docs/adr/0002-clock-port.md` (ADR for ClockPort injection)
- Created `docs/adr/0003-trainer-port.md` (ADR for TrainerPort decoupling)
- Created `docs/adr/0004-v010-compat.md` (ADR for v0.1.0 backward compat)
- Created `scripts/check_docs_sync.py` (detects drift between arch doc and code)
- Added unit tests in `tests/unit/nfr/test_nfr_0400_docs_sync.py` (9 tests)
- Commit: `f96f1c0`

### NFR-0900 (#77) - Scheduler reliability
- Fixed `UnicodeDecodeError` not being caught in `state.py` load_state()
- Added unit tests in `tests/unit/nfr/test_nfr_0900_scheduler_reliability.py` (9 tests):
  - Concurrent trigger_now() unique task IDs
  - Concurrent trigger serialized per max_concurrent
  - State corruption (garbage JSON, missing file, binary garbage)
  - Double start() idempotent
  - stop() before start() graceful no-op
- Commit: `1bfa9f8`

### NFR-1000 (#78) - v0.1.0 backward compat
- Added unit tests in `tests/unit/nfr/test_nfr_1000_v010_compat.py` (8 tests):
  - v0.2.0 round-trip save/load
  - v0.1.0 format model loading
  - v0.1.0 version format detection
  - OptimizedTopKStrategy fallback on missing/stale weights.csv
- Commit: `a4879e6`

## Coverage Status

- Total coverage after batch: 93.39%
- Pre-existing coverage (before my changes): 93.38%
- My changes did NOT negatively impact coverage (added 36 new tests)
- Per-module coverage varies: some modules at 85-88% (scheduler/registry.py, strategies/lgbm_top20.py, scheduler/cli.py)

## Test Summary

- Total unit tests: 622 passed
- New tests added: 36 (5+5+9+9+8)
- Baseline tests: 586

## Open Questions

1. **Coverage < 97%**: Total coverage is 93.39%, below the 97% target in NFR-0200 AC. This was a pre-existing gap (baseline was 93.38%). Per-module coverage varies, with some modules at 85-88%. The instruction says "DO NOT modify module code to inflate coverage" — so this gap remains for Archer/Keeper to address.

2. **mutmut full sweep**: Did NOT run full mutation sweep (would take hours). Only verified configuration is valid via unit tests.
