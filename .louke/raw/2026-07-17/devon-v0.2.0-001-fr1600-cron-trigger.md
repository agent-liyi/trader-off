---
date: 2026-07-17
session: devon-v0.2.0-001-fr1600-cron-trigger
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#44]
status: resolved
---

## Topic
FR-1600 Cron 触发器实现 — `next_cron_fire` 纯函数 (T-3) + `CronTrigger` 集成类。

## Decision

### 实现内容
1. **`src/trader_off/scheduler/cron.py`** (66 stmts, 100% coverage):
   - `next_cron_fire(expr, base, *, backend) -> datetime`: T-3 纯函数，使用 `croniter` 库。排他性语义（返回 base 之后的下一次触发，非包含性）。
   - `CronTrigger` 类：与 `SchedulerConfig` 集成，提供 `should_fire_full` / `should_fire_incremental` / `compute_next_full` / `compute_next_incremental` / `is_trading_day`.
   - `should_fire` 方法使用 `today_start` 方法检测当天 cron 是否到达，而非依赖 `next_cron_fire` 的包含性。

2. **依赖**: `croniter>=2.0,<3.0` 添加到 `pyproject.toml`。

3. **测试**: `tests/unit/scheduler/test_cron.py` (53 tests):
   - T-3 属性测试: 正确性（7 parametrized）、`next_fire >= base`、单调性、时区、确定性、无效表达式、naive datetime、apscheduler backend。
   - AC-FR1600-01: cron 触发时机正确（到达前不触发，到达时/后触发）
   - AC-FR1600-02: 非交易日跳过 + INFO 日志
   - AC-FR1600-03: 全量频率门控（3 < 5 天不触发，5+ 天触发，无历史全量→必触发）
   - AC-FR1600-04: `next_cron_fire` 精确断言

### 关键设计决策
- **排他性语义**: `next_cron_fire` 返回 base **之后**的下一次触发（非包含性）。`CronTrigger.should_fire` 使用 `today_start` 方法计算当天触发时间来判断是否到达。
- **频率门控**: 仅对全量重训应用；增量无频率限制。使用日历日计算，非交易日。

## Tried but abandoned
- **`base - 1s` 包含性方案**: 尝试让 `next_cron_fire` 包含 base 匹配的情况，但对 `*/30` 模式失败（15:00 是合法匹配，却返回 15:00 而非 15:30）。最终采用排他性语义 + `should_fire` 使用 `today_start` 检测。
- **`types-croniter` 作为 mypy 额外依赖**: pre-commit mypy hook 使用旧 Python 版本不兼容。改用 `# type: ignore[import-untyped]`。

## Open questions
- 无
