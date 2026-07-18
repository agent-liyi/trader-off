---
date: 2026-07-17
session: archer-v0.2.0-001-testplan
agents: [Archer]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: []
status: resolved
supersedes: []
---

## Topic

M-TESTPLAN Phase 1 for v0.2.0 (factor mining + retrain scheduler + portfolio optimizer):
produce test-plan.md covering 45 FR/NFR units / 159 ACs, decide test framework,
layering, ground truth, external-dependency strategy, and update project.toml [e2e].

## Decision

- Test framework: pytest (unchanged, `project.toml [meta].test_framework = "pytest"`).
- test-plan.md written at `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/test-plan.md`,
  modeled on v0.1.0 plan structure (§1 stance / §2 env / §3 ground truth / §6 layered
  external deps / §8 per-module layer map / §9 AC coverage map / §10 v0.2.0-specific
  anti-patterns + M-SPEC concern inheritance / §11 checklist).
- Coverage: 159/159 ACs mapped. Layers: ~110 unit (Devon), ~45 integration (Shield,
  14 files), ~10 e2e (4 files, scenario-0010~0050 happy paths), 5 perf (NFR-0100),
  10 CI gates (coverage ≥97%, mutmut ≥80%, ruff, bandit, grep×2, docs-sync, manifest, perf).
- Key v0.2.0 design decisions in plan:
  - Virtual clock injection (T-1) as testability requirement for scheduler; no real
    `time.sleep` waits in default layers (anti-pattern #9).
  - kill -9 crash-recovery tests must run scheduler in a subprocess (anti-pattern #10).
  - cvxpy default path tested with cvxpy installed in CI; scipy fallback tested via
    simulated ImportError (FR-3700 Round-2 lock).
  - FR-1900 IC-only: tests must assert absence of `sharpe` field + `ic_only` note.
  - All write paths (models/, scheduler_state/, reports/, factor_registry/) must be
    configurable to tmp_path (T-4) to prevent fixture leakage.
  - 4 testability requirements (T-1 clock, T-2 TrainerPort, T-3 next_cron_fire,
    T-4 configurable output dirs) forwarded to Stage 2 interfaces.md.
- project.toml [e2e] updated: paths = ["tests/e2e", "tests/perf"],
  run = "uv run pytest tests/e2e tests/perf -m e2e -v" (removed global --timeout=90
  because full-pipeline e2e budget is 600s; per-test @pytest.mark.timeout instead).
  [integration] unchanged. [meta].test_framework unchanged.
- Validator: `lk agent archer validate-test-plan --spec v0.2.0-001-factor-mining-retrain-optimizer`
  → "test-plan OK" (exit 0); author-result.json verdict=pass.

## Tried but abandoned

- Keeping global `--timeout=90` in [e2e].run: rejected — kills the 600s scenario-0050
  capstone; replaced with per-test timeout markers.
- Putting perf tests under tests/e2e/ only: rejected — spec NFR-0100 explicitly names
  `tests/perf/baselines.json`; honored spec location and added tests/perf to [e2e].paths.
- Listing all 159 ACs with full assertion detail in §8 (v0.1.0 style): rejected as too
  verbose and duplicative of acceptance.md; used FR-granularity planning map instead
  (CI enforces real closure via ci-scan).

## Open questions

- Stage 2 (M-ARCH) must land T-1~T-4 in interfaces.md and mark cross-module interfaces
  with the `modules` column; §8.2 integration list is the expected baseline.
- Whether APScheduler vs croniter is final (spec allows both; FR-1600 AC-4 only pins
  `next_cron_fire` semantics) — Stage 2 architecture decision (ADR-002 territory).
- tests/perf/baselines.json initial values need first CI run to calibrate (5% drift
  tolerance is tracking-only, not a gate).
