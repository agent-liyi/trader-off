# ADR-0002: ClockPort — Virtual Clock Injection for Scheduler

## Status

Accepted

## Context

The RetrainScheduler (FR-1500, FR-2500) needs to support:
- Testing with virtual/fake clocks (for CI speed and determinism)
- Cron trigger calculations at specific times
- Trading day detection

We evaluated three approaches:

1. **ClockPort injection** (default `lambda: datetime.now(timezone.utc)`)
2. **Hardcoded `datetime.now()`** (not testable)
3. **Monkey-patch system clock** (global state, causes test pollution)

## Decision

We use **ClockPort as a Protocol/interface** that the scheduler receives at construction time.

```python
class ClockPort(Protocol):
    def now(self) -> datetime: ...

# Default implementation
def _default_clock() -> datetime:
    return datetime.now(timezone.utc)
```

`RetrainScheduler.tick()`, `next_cron_fire(base=self._clock.now())`, and `last_full_retrain_date` all use this port.

## Consequences

**Positive:**
- Pure functions are easily testable in isolation
- CI tests run in seconds (no real-time waits for cron)
- Explicit dependency injection makes contracts visible

**Negative:**
- Developers must remember to inject a clock in tests
- Default clock works for production but not for testing edge cases

**Mitigation:**
- `SchedulerConfig.clock` field with default value
- AC-FR1600-04 verifies both croniter and APScheduler return same result
- Unit tests use `unittest.mock.Mock` for clock injection
