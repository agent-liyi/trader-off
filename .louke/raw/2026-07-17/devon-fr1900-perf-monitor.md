---
date: 2026-07-17
session: devon-fr1900-perf-monitor
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#47]
status: resolved
---

## Topic
FR-1900 性能衰减检测 — IC-based perf decay detection with Round-2 IC-only lock.

## Decision

### Implementation
- Created `src/trader_off/scheduler/perf_monitor.py` containing:
  - `TriggerDecision` frozen dataclass (interfaces.md §1.7): `should_retrain`, `reason`, `suggested_mode`, `computation_time_sec`, `notes`
  - `detect_perf_decay(recent_ic, *, reference_ic_mean, ic_floor, ic_drop_ratio, window)` — pure function
  - `PerfMonitor(config, ic_history_provider)` class with `trigger_perf_degradation()` method
- Added `PerfMonitorPort` Protocol to `ports.py` with TYPE_CHECKING import to avoid circular deps
- Updated `__init__.py` exports: `PerfMonitor`, `TriggerDecision`, `detect_perf_decay`, `PerfMonitorPort`

### Design choices
- `notes` field is `str` (not `list[str]`) per interfaces.md §1.7
- `suggested_mode` defaults to `"full"` per AC-1/AC-2
- `ic_below_floor` takes priority over `ic_drop_ratio_exceeded`
- Reference IC mean for drop detection: provider called with `2 * ic_window` window, first half used as reference
- No Sharpe fields whatsoever (Round-2 lock)

### Commits
- `agent-liyi/trader-off@37a6621`: feat: green – #47
- `agent-liyi/trader-off@f70b361`: refactor: – #47

## Tried but abandoned
- Initially used string-quoted type `"TriggerDecision"` in port protocol to avoid circular import; switched to TYPE_CHECKING import for cleaner type checking
- Considered `notes: list[str]` per task description but interfaces.md mandates `str`

## Open questions
- None. All 4 ACs covered with 22 unit tests at 100% coverage.
