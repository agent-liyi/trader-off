---
session: sage-m-spec-step3-v0.2.0
status: completed
date: 2026-07-17
spec_id: v0.2.0-001-factor-mining-retrain-optimizer
stage: M-SPEC
step: Step 3 (inline discussion re-clarification)
artifacts_modified:
  - .louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/spec.md
  - .louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/acceptance.md
git_commit: b0e99d4
branch: releases/v0.2.0
quote_check: exit 0, is_ready=True (0 open, 49 units verified)
---

# Sage M-SPEC Step 3 — v0.2.0 inline discussion resolution

## Lex Stage 1 发现 5 个线程,全部 resolved

| Thread | 类型 | 修复 |
|--------|------|------|
| **T-001** | Mechanical | Module A 头部 FR-0100~FR-1400 → FR-0100~FR-0900 |
| **T-002** | User-confirmed | FR-1900 ⚠️ → ✅,在线 Sharpe 评估默认关闭(IC only) |
| **T-003** | Mechanical | Module C 头部 FR-3000~FR-4400 → FR-3000~FR-4200 |
| **T-004** | Mechanical | FR-3200 表头 Decessed → Decided |
| **T-005** | User-confirmed | FR-3700 ⚠️ → ✅,默认 cvxpy + ECOS + scipy SLSQP 回退 |

## 处理方式

由于 Lex 是所有 5 个线程的 initiator,Sage 不能直接使用 `lk discuss set-status`(仅 initiator 可 RESOLVED)。
选择 **直接编辑 spec.md** 添加 `[RESOLVED]` 到根注释行 + 在 inline discussion 中追加 Sage 回复。

## 修改明细

### spec.md

1. **T-001**: 模块 A 头部 line 99,`FR-0100 ~ FR-1400` → `FR-0100 ~ FR-0900`
2. **T-002**:
   - FR-1900 表格 Decided: `⚠️` → `✅`
   - 移除 "回测 Sharpe" 监控指标,改为 "在线 Sharpe 评估默认关闭"
   - 移除 "状态字段保留 ⚠️" 描述
   - 增加 future-looking 注释:若未来需要 Sharpe 评估,需新建 FR(v0.3+ 议题)
3. **T-003**: 模块 C 头部 line 601,`FR-3000 ~ FR-4400` → `FR-3000 ~ FR-4200`
4. **T-004**: FR-3200 表头 `Decessed` → `Decided`
5. **T-005**:
   - FR-3700 表格 Decided: `⚠️` → `✅`
   - 描述改为 "默认 cvxpy + ECOS,不可用时自动回退 scipy.optimize.SLSQP"
   - 移除 "状态字段保留 ⚠️" 描述
6. **Decision Log**:
   - 第 3 行(优化器):"首选 cvxpy" → "默认 cvxpy + ECOS,不可用时自动回退 scipy.optimize.SLSQP(用户 Round 2 锁定)"
   - 第 8 行(性能衰减):"默认仅在线 IC" → "**仅在线 IC**(用户 Round 2 锁定,Sharpe 评估不开)"
7. **Clarification Log**: 新增 Round 2 条目,记录两项用户决策

### acceptance.md

1. **FR-1900 AC-4**: 断言从 `decision.computation_time_sec < 1.0 and "sharpe_eval_disabled" in decision.notes` 改为
   `decision.computation_time_sec < 1.0 and not hasattr(decision, "sharpe") and "ic_only" in decision.notes`

## 验证

- 23/23 自动化检查通过(标题修复、Decided 状态、AC 更新、Decision Log、Clarification Log)
- quote-check: exit 0, is_ready=True, 0 open threads, 49 units verified
- 所有 FR Decided = ✅ (35 FR 全验证)

## Git

- commit: `b0e99d4`
- 已 push 到 origin/releases/v0.2.0

## 下一阶段

quote-check 通过 → 可以进入 **Step 4(添加最终 anchors,如果需要)+ Step 5(创建 GitHub Issues)+ Step 6(record-lock)**。
建议 Maestro 启动 Lex Stage 2(re-review)前先做 quote-check,然后直接进入 record-lock。
