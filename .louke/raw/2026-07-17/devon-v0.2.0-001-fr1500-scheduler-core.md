---
date: 2026-07-17
session: devon-v0.2.0-001-fr1500-scheduler-core
agents: [Devon]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: [#43]
status: resolved
supersedes: []
---

## Topic
FR-1500 调度器核心接口与生命周期 — Module B 起点，建立 ports 基础设施 + RetrainScheduler 骨架。

## Decision

### 创建文件
- `src/trader_off/scheduler/__init__.py` — 公共 API 导出
- `src/trader_off/scheduler/ports.py` — ClockPort/SystemClockPort/VirtualClockPort (T-1) + TrainerPort/DefaultTrainerPort (T-2) + TriggerReason StrEnum
- `src/trader_off/scheduler/core.py` — SchedulerConfig/SchedulerStatus/RetrainTask/RetrainScheduler
- `tests/unit/scheduler/__init__.py`
- `tests/unit/scheduler/test_core.py` — 16 个测试覆盖所有 AC + T-1/T-2

### 关键设计决策
1. **TriggerReason 移至 ports.py**：因为 TrainerPort 协议签名引用它，避免循环导入。
2. **唤醒机制**：start() 主循环使用 `_wake_event` 通知，当 trigger_now 入队任务时唤醒循环，避免依赖 tick_interval 延迟。
3. **并发模型**：`_process_pending_task` 获取锁弹出任务后释放锁，再 await trainer。`_run_task` 在 finally 中唤醒循环处理后续任务。
4. **mypy 配置**：在 `pyproject.toml` 添加 `[tool.mypy]`，限制文件范围为 `scheduler/` 避免预存文件报错。
5. **DefaultTrainerPort.train() 骨架**：FR-1500 范围抛出 NotImplementedError，真实数据加载、特征工程由 FR-2100/2200 完成。

### `_sleep_with_stop_check` 实现
使用 `asyncio.ensure_future` + `asyncio.wait` 等待 `_stop_event` 和 `_wake_event` 两者之一，超时以 tick_interval 作为兜底。

## Tried but abandoned

1. **`asyncio.wait_for(self._stop_event.wait(), timeout=seconds)`** — 简单但不能响应新任务入队。
2. **`asyncio.Condition`** — 更通用但引入额外复杂度，两个 Event 足够。
3. **`await scheduler.start()` 在测试中阻塞** — 测试改为 `asyncio.create_task(scheduler.start())` 后台运行。
4. **CloudPort 作为 `@runtime_checkable` Protocol** — 引入多余复杂度和 mypy 警告。

## Open questions

1. `core.py:247` (`_active_tasks >= max_concurrent_tasks` 分支) 未覆盖 — 当前 `_run_task` 同步阻塞循环，需后续 FR 改为 `asyncio.create_task` 启动后台任务才能触发此分支。
2. `ports.py:171-184` (DefaultTrainerPort.train NotImplementedError) — FR-2100/2200 实现真实数据加载+训练时覆盖。
3. FR-1600 (Cron) 需要 `next_cron_fire` 纯函数 — 需引入 `croniter` 依赖（architecture.md §3.1 已规划）。
4. SchedulerConfig 中 dataclass 的 `Literal` 类型在 pydantic 校验场景可能需要验证逻辑。

## Metrics
- AC 覆盖: 4/4 (AC-FR1500-01~04)
- T-1 (ClockPort) + T-2 (TrainerPort) testability seams 已验证
- 测试数: 16
- 覆盖率: 97%
- 源码行数: ~560 (3 modules)
- 提交哈希: `1ba0883`
