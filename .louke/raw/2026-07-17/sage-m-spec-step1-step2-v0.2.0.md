---
session: sage-m-spec-step1-step2-v0.2.0
status: completed
date: 2026-07-17
spec_id: v0.2.0-001-factor-mining-retrain-optimizer
stage: M-SPEC
step: Step 1 + Step 2
artifacts:
  - .louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/spec.md (1090 lines)
  - .louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/acceptance.md (1171 lines)
git_commit: d736dca
branch: releases/v0.2.0
---

# Sage M-SPEC Step 1 + Step 2 — v0.2.0 spec generation

## 摘要

按用户 Maestro 指令,在已确认的 v0.2.0 范围(因子挖掘 + 再训练调度 + 组合优化器)上,
跳过 Step 1 用户提问(无 genuine blocker),直接进入 Step 2 生成完整 spec.md + acceptance.md。

## Step 1 决策: 不提出额外问题

- 因子表达式 DSL → 锁定为「参数化模板 + 合法组合枚举」(dataclass + enum),无需自研解析器
- 调度器持久化 → 文件系统 JSONL + parquet(APScheduler JobStore 备选,ADR-002 占位)
- 优化器库 → cvxpy 默认 + scipy.optimize.SLSQP 回退(ADR-001 占位)
- millionaire API 缺口 → 不依赖新 API:
  - 组合优化器独立输出 weights.csv,OptimizedTopKStrategy 直接消费
  - 再训练调度复用 v0.1.0 已有的 `train_model`/`save_model`/`load_model`
  - 预测服务通过 `predict(model_version=...)` 显式传 version

## Step 2 产物

| 模块             | FR 范围      | FR 数 | AC 数 |
| ---------------- | ------------ | ----- | ----- |
| A 因子挖掘       | FR-0100~0900 | 9     | 36    |
| B 再训练调度     | FR-1500~2700 | 13    | 52    |
| C 组合优化器     | FR-3000~4200 | 13    | 47    |
| NFR              | NFR-0100~1000| 10    | 24    |
| **合计**         | —            | **45**| **159** |

## 关键架构决策(Decision Log)

1. **因子表达式 DSL**: dataclass `FactorTemplate` + `enum int_range/choice/bool` 参数空间 → 默认 ≥200 候选因子
2. **协方差估计**: Ledoit-Wolf(默认,可切换 sample)
3. **优化器**: cvxpy + scipy.optimize.SLSQP 回退(ADR-001 待 Round 2 确认)
4. **调度器持久化**: 文件 JSONL + parquet(ADR-002 待 Round 2 确认)
5. **调度器并发**: 单进程 asyncio,`max_concurrent_tasks=1`
6. **自动部署**: 默认 lazy 加载(下次 predict 时读最新版本),hot-reload 可选
7. **漂移判定**: PSI + KS 组合判定(降低误报率,FR-2600)
8. **性能衰减**: 默认仅在线 IC,Sharpe 评估可选关闭(FR-1900 ⚠️)
9. **输出格式**: YAML(注册表) + JSON(精选集) + HTML(主报告) + MD(精简报告)
10. **v0.1.0 命令兼容**: train/predict/backtest/feature-importance 保留签名;新增 `--factor-registry` 参数

## ⚠️ 待 Round 2 确认

- **FR-1900**: Sharpe 评估是否启用(当前默认关闭,仅在线 IC)
- **FR-3700**: cvxpy 必选 vs 可选(Apache-2.0,~50MB)

## 一致性保证

- 35/35 FR 锚点完整(`<a id="fr-XXXX">`)
- 10/10 NFR 锚点完整(`<a id="nfr-XXXX">`)
- 45/45 AC 章节标题与 spec FR/NFR 标题**完全一致**(通过自动化校验)
- 159/159 AC 标题符合 `### AC-N` 纯格式(Lex verify-acceptance 兼容)
- v0.1.0 引用次数: 61(spec.md 中显式继承声明)

## 已锁定的下游交付物

- 每个 FR 有 2-5 个 AC(平均 3.5),覆盖正常路径、边界、错误路径
- 所有 AC 包含 Given/When/Then 结构或可断言的预期值
- 异常路径通过 `pytest.raises(...)` 形式表达
- 性能预算(FR-1/NFR-0100)与 v0.2.0 DoD 完全对齐:
  - train≤300s, predict≤5s, backtest≤600s, mem≤16GB
  - coverage≥97%, mutation≥80%
  - 至少 3 个 ADR(docs/adr/)

## 下一阶段:M-SPEC Round 1(用户 review)

Sage 将:
1. 等待用户在 IDE 中 review spec.md
2. 收集 open 线程(无,因为本轮未发起 inline discussion)
3. Round 2 发起 inline discussion 解决 2 个 ⚠️ 项(FR-1900 Sharpe 评估 + FR-3700 cvxpy 选型)
4. 确认后进入 Step 4(anchors)+ Step 5(创建 GitHub issues)+ Step 6(lock)
