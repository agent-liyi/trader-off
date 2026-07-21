---
locked: true
locked-at: 2026-07-21T06:59:25Z
locked-by: lk agent sage record-lock
---
# v0.3.1 patch — ClockRewind fixture fix + scheduler decoupling review — Spec

- **Spec ID**: v0.3.1-001-clock-rewind-scheduler-review
- **Created**: 2026-07-21
- **Status**: Draft

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。
> 验收标准 (可观察、可断言的通过条件) 放在 `acceptance.md` 中。
> 测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。

## User Stories

### US-0010

story: 作为一名量化研究员，我希望 v0.3.0 MVP 推迟的两项尾巴在 v0.3.1 patch 中得到处置 ——(1) `ohlcv_10x60` fixture 触发的 ClockRewind 消除、2 个核心 e2e 重新启用；(2) v0.3.0 spec NFR-0100 行 292 backlog note 中承诺的 cron 触发器迁移评估落地、产出书面 verdict 与相应代码改动——使 e2e 真实回测覆盖完整、scheduler 议题有据可依。
priority: P0

## Usage Scenarios

### scenario-0010

1. 开发者执行 `python scripts/convert_fixture_to_quantide.py` —— 默认参数下，ohlcv_10x60 fixture 输出的 `tests/fixtures/v0.3.0/daily_bars_store/` 中日期最早一日已前移到 2023-12-29（或更早），使 quantide `calendar.day_shift(start, -1)` 返回真实前一日。
2. `tests/e2e/test_real_backtest_e2e.py` 中 2 个（自然覆盖 3 个，per story §3.1 Avoid）`@pytest.mark.skip` 被移除，`pytest tests/e2e/test_real_backtest_e2e.py -v` 全绿，0 skipped（除 lgbm_top20+预训练模型那 7 个保留 v0.4.0）。
3. 交付 `.louke/project/decisions/v0.3.1-scheduler-review.md`，verdict=(M) Migrate 至 `quantide.core.scheduler.SchedulerManager`；`src/trader_off/scheduler/` 通过**函数级 lazy import** 引入 `SchedulerManager`，模块顶层不出现 `import quantide`，且不引入 quantide 业务符号（仅复用调度框架）。
4. `history.md` 同步更新：v0.3.1 行说明本 patch 的 FR-0100 + FR-0200 落地结论 + NFR-0101 隔离条款放宽；v0.4.0 backlog 清掉 scheduler 复审条目。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表 (Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100 / FR-0200** 两条 P0 FR + **NFR-0101 / NFR-0200** 两条 NFR;起始草案 100/200 间隔,首次复审后按 10 插入(预留扩展位)。4 位补零,锁定后不改 ID,deprecated 时 Valid=❌ + 备注。
>
> **必读**: FR-XXXX 是该需求唯一 ID,**禁止删除**既有 ID;若 FR 需废弃,改表内 Valid=❌ 并在 Clarification Log 解释。
>
> 引用约定 (AC): 验收标准用 `AC-FRXXXX-YY` 格式 (4 位 FR + 2 位 AC),见 `acceptance.md`。
>
> **元数据表 (3 列)**:
> - Valid (原 yaml `valid`): ✅ = 仍生效,❌ = 已废弃
> - Testable (原 yaml `testability`): ✅ = 可测试/可断言,⚠️ {原因} = 存保留意见
> - Decided (原 yaml `resolved`): ✅ = 用户已确认,⚠️ = 待澄清,❌ = 用户明确拒绝

<a id="fr-0100"></a>
### FR-0100 ClockRewind fixture 修复 — 移除 2（自然 3）个 e2e skip

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 修复方式（用户决策 2026-07-21，选项 a）：**修改 `scripts/convert_fixture_to_quantide.py` 默认参数**，使 `ohlcv_10x60` fixture 输出的 `tests/fixtures/v0.3.0/daily_bars_store/` 中最早一日前移到 2023-12-29 或更早（calendar 含 2023-12-29 前一日即可）。同步更新脚本默认值与 `history.md` 变更说明。
- 触发链路验证：`quantide calendar.day_shift(start, -1)` 对 `ohlcv_10x60` fixture 的 `start_date` 返回真实前一日（`start_date - 1 day`），而非同日；`BacktestBroker.set_clock` 不抛 `ClockRewind` 异常。
- 重新启用：`tests/e2e/test_real_backtest_e2e.py` 中 `@pytest.mark.skip` 行被删除：
  - `test_run_backtest_real_summary_keys`（line 54-64）
  - `test_run_backtest_nav_curve_is_real`（line 158-165）
  - `test_run_backtest_with_custom_store_path`（line 269-277，自然覆盖，per story §3.1 Avoid）
- `pytest tests/e2e/test_real_backtest_e2e.py -v` 退出码 0，9 passed / 0 skipped（与 7 个保留 v0.4.0 的 lgbm_top20 skip 互不相关，e2e/perf 全局计数不计）。
- 文档同步：`history.md` 新增 v0.3.1 行，说明 fixture 起始前移、3 个 e2e unskip；引用 `tests/fixtures/v0.3.0/daily_bars_store/` 起始日期变更。
- **不**修改 `quantide` 源码（上游重构通过 compat shim 隔离，v0.3.0 NFR-0200 仍生效）。
- **不**修改 `src/trader_off/backtest/{runner,metrics}.py` 与 v0.3.0 FR-0500 runner.py 注入路径；本 FR 仅动 fixture 转换脚本与测试 skip 标记。

---

<a id="fr-0200"></a>
### FR-0200 Scheduler decoupling migration — verdict (M) Migrate to `quantide.core.scheduler.SchedulerManager`

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 决策结论（用户决策 2026-07-21）：verdict = **(M) Migrate** 至 `quantide.core.scheduler.SchedulerManager`。
- **隔离承诺**（用户重新解读 AC-FR1500-04）：放宽 v0.3.0 NFR-0100 的"模块顶层零 `import quantide`"硬约束，改为**函数级 lazy import** + **零业务符号导入**：
  - `import quantide.core.scheduler` 必须出现在 `def`/`async def` 函数体内，模块文件顶层（含类体、`__init__.py`、`TYPE_CHECKING`）**不**出现。
  - 业务符号白名单：仅允许 `quantide.core.scheduler.SchedulerManager`（含其子符号，如 `init/start/stop/add_job/add_listener`）；**禁止** import `quantide.service.*` / `quantide.portfolio.*` / `quantide.data.*` 等业务模块。
  - `pyproject.toml` 声明 `quantide` git URL 依赖（v0.3.0 FR-0200 已完成，零改动）。
- 落地范围：`src/trader_off/scheduler/` 下识别 cron 触发器（当前 `croniter` 后端）的调用点，封装一个薄适配层（如 `QuantideSchedulerAdapter`），函数体内 `from quantide.core.scheduler import SchedulerManager`；通过 `SchedulerManager.init/start/stop/add_job` 替换原 apscheduler 风格的启动路径。
- 决策文档：交付 `.louke/project/decisions/v0.3.1-scheduler-review.md`（≤1 页 markdown），含：
  - 证据：(a) `quantide.core.scheduler.SchedulerManager` 接口清单（已读源码，`init/start/stop/add_job/add_listener` 5 个方法）；(b) `trader-off scheduler` 调用清单（grep `apscheduler|BackgroundScheduler` 位置 + 行数）；(c) 隔离承诺影响评估（函数级 lazy import vs 模块顶层 import 的可测性差异）。
  - 结论：verdict=(M)；迁移路径：croniter → `SchedulerManager`；副作用：NFR-0100 隔离条款改写 → NFR-0101；`history.md` / v0.4.0 backlog 同步。
- **不**做顺手 refactor：禁止借机修改 scheduler 模块其他文件（`api.py` / `cli.py` / `state.py` 等），除非为落地 (M) 必须。
- **不**改 `croniter` 路径的单元测试断言（保持 `next_cron_fire` 纯函数 + `Literal["croniter","apscheduler"]` 接口稳定）；(M) 落地由集成测试与 `tests/integration/test_scheduler_resilience.py` 中新加 AC 覆盖。

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR,此处省略。

<a id="nfr-0101"></a>
### NFR-0101 调度器隔离改写 — 函数级 lazy import + 零业务符号 (继承 v0.2.0 AC-FR1500-04，**替代** v0.3.0 NFR-0100)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 替代 v0.3.0 spec.md NFR-0100（"模块顶层零 `import quantide`"）；v0.3.0 NFR-0100 自本 spec 锁定起对该 scheduler 模块失效，但 `src/trader_off/backtest/` / `src/trader_off/strategies/` 等其他模块的隔离承诺仍由 v0.3.0 NFR-0200 约束。
- 验证 1（模块顶层）：`grep -rn "^import quantide\|^from quantide" src/trader_off/scheduler/` 应**无**匹配（不含 `pyproject.toml`）。
- 验证 2（业务符号）：`grep -rn "quantide\\.\\(service\\|portfolio\\|data\\|backtest\\)" src/trader_off/scheduler/` 应无匹配。
- 验证 3（函数级 import 存在性）：`grep -rn "from quantide.core.scheduler" src/trader_off/scheduler/` 至少 1 个匹配（证明实际接入了 `SchedulerManager`），且全部匹配行缩进位于 `def`/`async def` 函数体内（Python AST 校验或行上下文人工审核）。
- v0.2.0 AC-FR1500-04 的"`src/trader_off/scheduler/` 不出现 quantide 业务 import"语义保持通过；"模块顶层零 import"语义被本 NFR 替代。
- `tests/integration/test_scheduler_resilience.py` 新增至少 1 条 AC 验证：`SchedulerManager` 通过 lazy import 被实例化，`SchedulerManager.init()` 调用栈中无模块顶层 import 副作用。

---

<a id="nfr-0200"></a>
### NFR-0200 Compat shim 模式保留 (trader-off 不直接 import quantide) — 继承 v0.3.0


| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 继承 v0.3.0 NFR-0200：`trader_off.strategies.compat.BaseStrategy` 通过 `try/except ImportError` 解析 quantide 或 fallback stub。
- 验证：`grep -rn "import quantide" src/trader_off/backtest/ src/trader_off/strategies/lgbm_top20.py src/trader_off/strategies/optimized_topk.py` 应**仅**在 `src/trader_off/strategies/compat.py` 内出现 import 语句。
- 本 spec 不修改 compat.py；FR-0200 的 (M) 落地只动 `src/trader_off/scheduler/`，与 compat 层无交叉。

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|---|
| 0 (Story) | M-STORY §5 | FR-0100 修复方式 (a) vs (b)：建议 (a) 与 50×252 fixture 对齐 2023 年窗口 | ⚠️ [M-SPEC 锁定] |
| 0 (Story) | M-STORY §5 | FR-0200 verdict：Agent 倾向 (S) Stay-isolated | ⚠️ [Human 决策必填] |
| 1 (User 2026-07-21) | M-SPEC Step 1 | **FR-0100 决策 = option (a)** — 修改 `convert_fixture_to_quantide.py` 默认起始日期（或重生 fixture） | ✅ |
| 1 (User 2026-07-21) | M-SPEC Step 1 | **FR-0200 verdict = (M) Migrate** — 迁移至 `quantide.core.scheduler.SchedulerManager` | ✅ |
| 1 (User 2026-07-21) | M-SPEC Step 1 | **隔离承诺重新解读**：保留 AC-FR1500-04 语义，但实现改为函数级 lazy import + 零业务符号 import；模块顶层仍零 `import quantide` | ✅ |
| 1 (User 2026-07-21) | M-SPEC Step 1 | **FR-0200 落地范围**：croniter → `SchedulerManager` 适配；禁止顺手 refactor scheduler 其他模块 | ✅ |
| 1 (User 2026-07-21) | M-SPEC Step 1 | **story §3.1 Avoid 第 3 个 skip**（`test_run_backtest_with_custom_store_path`）— 同 ClockRewind 根因，FR-0100 修复后自然覆盖；显式纳入 AC 但不作为独立 FR | ✅ |
| 1 (M-SPEC) | 本 spec | **NFR-0100 → NFR-0101 改写**：v0.3.0 NFR-0100 被本 spec NFR-0101 替代（仅限 scheduler 模块），其他模块隔离由 v0.3.0 NFR-0200 约束 | ✅ |
| 2 (M-DEV 2026-07-21) | Devon | **FR-0100 实施偏差 (a)→(b)**：spec 正文第 54 行写入选项 (a) "修改 convert_fixture_to_quantide.py"，实际实施为选项 (b) "修改 _generate_inline_calendar() 在 runner.py 中前置合成前一天"；选择 (b) 的理由：根本原因在于 `runner.py` 中的 inline calendar 生成（`calendar.day_shift(start, -1)` 需要前一日历条目），而非 fixture 转换脚本；(b) 更简洁，不要求改变上游 fixture 数据，在 calendar 层修复而非数据层。| ✅
