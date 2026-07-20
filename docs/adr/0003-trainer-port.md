# ADR-0003: TrainerPort — Decoupling Scheduler from Training

## Status

Accepted

## Context

The RetrainScheduler must call training logic without directly importing the `trader_off.training` module, to:
- Keep the scheduler module independently testable
- Support mock trainers in unit tests without real training
- Allow future替换 of training implementation

We evaluated two approaches:

1. **TrainerPort Protocol + DefaultTrainerPort wrapper**
2. **Direct `from trader_off.training import train_model` call**

## Decision

We define a **TrainerPort Protocol** that the scheduler uses:

```python
class TrainerPort(Protocol):
    async def train_full(self, config: dict) -> str: ...
    async def train_incremental(self, config: dict) -> str: ...

# Default implementation wraps v0.1.0 train_model
class DefaultTrainerPort:
    async def train_full(self, config: dict) -> str:
        return await asyncio.to_thread(train_model, **config)
```

Scheduler tests use `unittest.mock.AsyncMock` as TrainerPort substitute.

## Consequences

**Positive:**
- Scheduler module does not depend on `trader_off.training` directly
- Unit tests run in <1s without actually training models
- Clear interface contract documented in Protocol

**Negative:**
- One additional abstraction layer to maintain
- Protocol method set must stay in sync with v0.1.0 `train_model` signature

**Mitigation:**
- `TrainerPort` is a `Protocol` (runtime duck-typing compatible)
- Mock trainer verifies call counts and arguments
- Integration tests verify the `DefaultTrainerPort` wrapper works
