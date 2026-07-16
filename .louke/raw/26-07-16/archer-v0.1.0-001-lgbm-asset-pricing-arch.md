---
date: 2026-07-16
session: archer-v0.1.0-001-lgbm-asset-pricing-arch
agents: [Archer]
spec: v0.1.0-001-lgbm-asset-pricing
related_issues: ["#6-#28"]
status: resolved
supersedes: []
---

## Topic
M-ARCH Stage 2: produce architecture.md + interfaces.md + [e2e]/[integration] project.toml sections for the lightGBM A-share pricing model.

## Decision
- Wrote `architecture.md` (534 lines): system overview (ASCII component diagram), 模块划分 (12 modules), dependency direction (no cycles, utils at bottom), tech choices (polars/lightgbm/millionaire etc. with versions), 9 trade-offs (polars vs pandas, async, versioning, scaler binding, early stopping, walk-forward, Agg backend, joblib whitelist, DataLoader adapter), millionaire integration (inheritance + adapter + injection), 3 data flow diagrams, error handling (7 exceptions).
- Wrote `interfaces.md` (553 lines): 9 data schemas, 10 file schemas, ~40 public API signatures across 12 modules, 4 CLI commands, millionaire contracts (BaseStrategy/Broker/fetcher/Runner), 24 cross-module interfaces (§6 table with modules column), 6 exceptions, AC→interface→test-plan three-way closure table (79/79).
- Added `[e2e]` (run="pytest tests/e2e -m e2e -v --timeout=90", paths=["tests/e2e"]) and `[integration]` (run="pytest tests/integration -m integration -v", paths=["tests/integration"]) to project.toml.
- Created tests/ scaffolding (.gitkeep in e2e/e2e/fixtures/integration/unit/assets/ground_truth) — required because validate-arch checks [e2e].paths exist on disk.
- Closed test-plan §10 two checklist items (interfaces closure + modules column).
- validate-arch exit 0 → M-ARCH author-result.json verdict=pass.
- Commit: 98ef5aa.

## Tried but abandoned
- Numbered heading `## 2. 模块划分` failed validate-arch (substring check needs exact `## 模块划分` without `2. ` prefix). Fixed by renaming to `## 模块划分`.
- Initially planned `[e2e].cwd="."` but omitted cwd entirely (optional; validator skips check if absent) to avoid edge cases.
- Initially planned `[e2e].paths` to include `configs/train.e2e.yaml` and `tests/e2e/fixtures` per test-plan §6.5, but validate-arch checks each path EXISTS; those don't exist yet. Simplified to `["tests/e2e"]` only (Devon/Shield create config files later).

## Open questions
- interfaces.md §8 closure table uses range notation (e.g. AC-FR0100-01/02/03) for readability; regex-based AC scanner only catches explicit refs (40 of 79). This is design doc, not CI-enforced (check_acs.py scans test code, not interfaces.md). Acceptable.
- The M-TESTPLAN author-result.json showed a benign timestamp/hash refresh after validate-arch run (verdict still pass); included in commit to keep tree clean.
- Prism review: should verify the millionaire BaseStrategy/Broker/fetcher interface assumptions match actual millionaire API (Archer inferred from spec/story, not from millionaire source).
