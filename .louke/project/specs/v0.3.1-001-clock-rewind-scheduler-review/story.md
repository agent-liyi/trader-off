---
date: 2026-07-21
spec: v0.3.1-001-clock-rewind-scheduler-review
status: draft
---

# STR-0002: v0.3.1 patch — ClockRewind fixture fix + scheduler decoupling review

## 0. 原始输入
> v0.3.1 patch（一句话）：修复 v0.3.0 MVP 推迟的两项 —— (1) `ohlcv_10x60` fixture 起始 2024-01-02 触发的 ClockRewind，让 2 个 e2e 重新启用；(2) 兑现 v0.3.0 spec NFR-0100 backlog note，对 cron 触发器迁移到 `quantide.core.scheduler.SchedulerManager` 出具决策文档。
## 1. 用户与场景 (Who & Where)
- **Who**：量化研究员（承接 v0.3.0 STR-0001，单一开发者；规模/频次/网络继承 v0.3.0 §1.1）。
- **Where**：CLI（`pytest tests/e2e/test_real_backtest_e2e.py`）+ 本地 docs；仅桌面/服务器，无 UI。

## 2. 功能与价值 (What & Why)

### 2.1 功能描述 (What)
**FR-0100（ClockRewind fixture 修复）**：调整 `tests/fixtures/v0.3.0/daily_bars_store/`（含 calendar_store）的 10×60 fixture 起始日期，使 quantide `calendar.day_shift(start, -1)` 返回前一日而非同日 —— 消除 `BacktestBroker.set_clock` 的 ClockRewind，重新启用 v0.3.0 中 2 个被 skip 的 e2e。修复方式二选一（M-DEV 决）：(a) 起始前移到 2023-12-29（calendar 含前一天）；(b) convert 脚本或测试 setup inline 注入 2024 年前预热日。

**FR-0200（Scheduler decoupling 复审）**：交付决策文档（`.louke/project/decisions/v0.3.1-scheduler-review.md`），评估三种去向：**(M) migrate** 到 `quantide.core.scheduler.SchedulerManager` / **(S) stay-isolated** 保留 apscheduler / **(P) partial** 仅复用 timezone/singleton。仅 verdict 为 (M)/(P) 时落地代码；为 (S) 时只交报告 + 更新历史，零代码改动。

### 2.2 快乐路径 (Happy Path)
1. FR-0100：定位 fixture 起始 → 改 convert 脚本/重生 fixture → 取消 2 个 `@pytest.mark.skip` → `pytest tests/e2e/test_real_backtest_e2e.py -v` 全绿
2. FR-0200：读 `quantide.core.scheduler.SchedulerManager` 源码 → 比对 `src/trader_off/scheduler/` 触发器用法 → 出具 verdict → 写报告 + 同步 v0.4.0 backlog

### 2.3 问题陈述与目标 (Why)
- **问题**：v0.3.0 MVP 留 2 项尾巴 —— (1) 2 个 ClockRewind e2e 被 skip；(2) spec NFR-0100 行 292 backlog note 写明 "v0.4.0 起单独 spec 评估 cron 触发器迁移"，未启动评估。
- **北极星**：e2e 零 skip（除 lgbm_top20+预训练模型那 7 个保留 v0.4.0）+ scheduler 议题有书面 verdict。
- **可观测**：`pytest tests/e2e/test_real_backtest_e2e.py -v` 9 passed / 0 skipped（当前 7/2）；决策文档落盘。

### 2.4 功能需求（EARS 格式）
| 编号  | EARS 句式 | 说明 |
| :---- | :-------- | :--- |
| AC-01 | `WHEN run_backtest 在 ohlcv_10x60 fixture 上执行, THE 系统 SHALL 不再触发 ClockRewind（日历前移或 inline 预热使 day_shift(start,-1) 返回前一日）` | FR-0100 核心 |
| AC-02 | `WHEN test_run_backtest_real_summary_keys 被执行, THE 系统 SHALL 取消 @pytest.mark.skip 并通过真实回测断言` | 重新启用 |
| AC-03 | `WHEN test_run_backtest_nav_curve_is_real 被执行, THE 系统 SHALL 取消 @pytest.mark.skip 并验证 NAV 来自 quantide 非 np.random` | 重新启用 |
| AC-04 | `IF FR-0100 选 (a), THE 系统 SHALL 同步更新 convert_fixture_to_quantide.py 默认参数与 history.md` | 文档同步 |
| AC-05 | `WHEN 复审报告产出, THE 系统 SHALL 给出明确 verdict（M/S/P）并附证据：quantide SchedulerManager 接口对比 + trader-off scheduler 调用清单 + 隔离承诺影响评估` | FR-0200 交付 |
| AC-06 | `IF verdict=(M)/(P), THE 系统 SHALL 在 v0.3.1 落地最小代码改动且保持 AC-FR1500-04 隔离承诺不破（scheduler 不直接 import quantide 业务符号——仅 pyproject.toml 声明依赖）` | 迁移兜底 |
| AC-07 | `IF verdict=(S), THE 系统 SHALL 仅交付决策文档 + 更新 history.md/v0.4.0 backlog，scheduler 代码零改动` | 隔离兜底 |

## 3. 完整性 (Completeness)

### 3.1 Adopt / Avoid
| 类型 | 来源 | 内容 | 理由 |
| :--- | :--- | :--- | :--- |
| Adopt | quantide `core/scheduler.py` 源码（已读） | `SchedulerManager` = `@singleton` 包装 `BackgroundScheduler`，暴露 `init/start/stop/add_job/add_listener` | FR-0200 评估有事实基础 |
| Adopt | `.louke/raw/2026-07-21/shield-v0.3.0-skip-e2e-tests.md` | 根因 = fixture 起始 2024-01-02 + calendar 不含 2023 年预热日 → `day_shift(2024-01-02,-1)==2024-01-02` | 修复方向有证据 |
| Avoid | 同 raw 第 3 个 skip `test_run_backtest_with_custom_store_path` | 同 ClockRewind 根因，FR-0100 修复后**一并重新启用**（自然副作用，非显式 scope） | 防 scope creep |

### 3.2 Out-of-Scope
- [ ] 不接入 tushare / grid_search / walk-forward / polars-talib / qfq/hfq（v0.4.0+）
- [ ] 不修 v0.3.0 M-SECURITY 4 条 low 项（path passthrough / rmtree / spec drift / Calendar tushare fallback）
- [ ] 不重新启用 lgbm_top20 + 预训练模型相关 7 个 e2e skip —— 缺模型 pipeline
- [ ] FR-0200 verdict=(S) 时不改 scheduler 代码；(M)/(P) 时**仅**做最小迁移，禁止顺手 refactor

### 3.3 约束条件
- **技术**：Python ≥ 3.13（继承 v0.3.0）；quantide 通过 git URL 依赖；AC-FR1500-04 隔离是底线。
- **组织**：patch ≤ 1-2 issue；FR-0200 报告 ≤ 1 页 markdown。
## 4. 必要性与冲突 (Necessity & Conflict)

### 4.1 必要性
| FR | 论证 |
| -- | ---- |
| FR-0100 | **必要** —— 跳过 2 个核心真实回测 e2e，stack 不完整；不修则"真实回测"承诺在 e2e 层面只验证 7/9 |
| FR-0200 | **必要** —— spec NFR-0100 行 292 backlog note 已书面承诺评估；本 patch 启动该评估 |

### 4.2 冲突
| v0.3.0 决策 | 是否冲突 | 说明 |
| ---------- | -------- | ---- |
| **NFR-0100 / AC-FR1500-04 scheduler 隔离** | ⚠️ **条件性** | verdict=(M) 时将 `import quantide.core.scheduler` —— **违反 v0.2.0 AC-FR1500-04**；须先放宽隔离条款（spec.md 显式记录新边界），否则 (M) 不可行 |
| **v0.3.0 fixture 转换链路 (FR-0500)** | ❌ | FR-0100 沿用同一 convert 脚本，仅调默认参数或加 inline 预热 |
| **v0.3.0 AC-11 调度器隔离 EARS** | ⚠️ **条件性** | 同上；verdict=(M)/(P) 时 AC-11 需改写为"仅复用 quantide 调度框架，不耦合业务符号" |
**结论**：FR-0100 无冲突 Go；FR-0200 verdict=(S) 零冲突，(M)/(P) 需在 spec.md 追加 NFR-0101。Human 决策点：先看 verdict 草稿再裁决。

## 5. 方案疑议（A/B Advisory，非决策）
- **FR-0100**：无替代。修复方式 (a)/(b) 等价，让 M-DEV 在 M-FOUND 阶段根据 calendar 体积与 CI 缓存影响选（建议 (a)，与 50×252 fixture 对齐 2023 年窗口）。
- **FR-0200**：**有边界提示**。Agent **倾向 verdict=(S)** —— v0.2.0 AC-FR1500-04 分层理由（trader-off=α 平台 / quantide=执行引擎）仍成立；`SchedulerManager` 仅是 apscheduler 单例封装，未提供 trader-off 急需的"交易日历感知 cron"；迁移收益小 + 破分层成本大。**Agent 不替用户决策**，仅提示此倾向 + 证据，最终 verdict 由 Human 裁决。
- **说明**：verdict=(S) 不引入新 NFR，隔离承诺沿用 v0.2.0；(M)/(P) 需追加 NFR-0101 并同步更新 v0.3.0 acceptance.md AC-11。

## 6. 分流结论与门禁 (Gate)
- **分流结论**：**Go**（Agent 建议）
- **理由**：FR-0100 风险小、价值明确（恢复 e2e 覆盖）；FR-0200 是决策文档 + 条件性代码改动，工作量可控；(S) 路径与 v0.3.0 架构零冲突。
- **Human 确认**（仅决策点）：
  - [ ] 分流结论认同（**Go**）
  - [ ] **FR-0200 verdict 草案裁决（M/S/P）— 必填**
  - [ ] 若 (M)/(P)：NFR-0101 放宽隔离条款的 spec.md 追加认同
  - [ ] Out-of-Scope 认同
- **Backlog**：**Go → 进入 M-FOUND**

## 7. 可追溯种子 (Traceability)
- **Story ID**：`STR-0002`
- **创建时间**：`2026-07-21T00:00:00Z`
- **Spec ID**：`v0.3.1-001-clock-rewind-scheduler-review`
- **关联 Issue（待填充）**：`#待创建`（建议拆 2 个：`FR-0100 fixture fix` + `FR-0200 scheduler review`）
- **继承基线**：v0.3.0 STR-0001 + spec NFR-0100 行 292 backlog note；v0.2.0 AC-FR1500-04（条件性继承——verdict=(M)/(P) 时放宽）

---

*—— 本故事由 M-STORY Agent 于 2026-07-21 生成；经 Human 确认后：Go → 进入 M-FOUND。*
