---
date: 2026-07-17
session: archer-v0.2.0-001-march-design
agents: [Archer]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: []
status: resolved
---

## Topic
v0.2.0 M-ARCH Phase 2: produce architecture.md + interfaces.md for the factor mining / retrain scheduler / portfolio optimizer trilogy. Carry over M-TESTPLAN testability requirements T-1~T-4 and M-SPEC Round-2 locks (FR-1900 IC-only, FR-3700 cvxpy+scipy fallback).

## Decision

### Modules (28 declared, single-line responsibility each)

**Module A — factor_mining (7 sub-modules):**
1. `templates` — FactorTemplate registry + IntRangeParam/ChoiceParam/BoolParam
2. `expression` — `enumerate_factors` 纯函数，≥200 个 FactorSpec
3. `evaluation` — `evaluate_factor` → FactorEvaluation（复用 v0.1.0 evaluation.ic）
4. `selection` — Top-K + Pearson 去冗余 → SelectionDiagnostics
5. `viz` — 相关性热力图 + HTML/MD 评估报告
6. `registry` — factor_registry/*.yaml|json 落盘 + schema 校验
7. `score` — `compute_factor_score`（portfolio expected_returns 备选路径）
8. `cli` — `trader-off mine-factors` CLI

**Module B — scheduler (10 sub-modules):**
1. `ports` — TrainerPort / ClockPort / ModelRegistryPort / DriftDetectorPort / PerfMonitorPort（T-1/T-2）
2. `core` — RetrainScheduler 主类
3. `cron` — `next_cron_fire` 纯函数（T-3）
4. `drift.psi` — PSI 漂移检测
5. `drift.ks` — KS 漂移检测
6. `drift.detector` — DriftDetector 编排 → DriftDecision
7. `perf_monitor` — PerfMonitor + TriggerDecision（Round-2 IC-only 锁定）
8. `registry` — ModelRegistry + GC + rollback
9. `deploy` — 自动部署（lazy/hot-reload）
10. `state` — 原子写 + 恢复
11. `api` — aiohttp REST（localhost only）
12. `cli` — scheduler/retrain CLI

**Module C — portfolio (8 sub-modules):**
1. `covariance` — Ledoit-Wolf / sample 协方差
2. `expected_returns` — `build_expected_returns` (raw/zscore)
3. `industry` — 行业映射 + 缺失行业兜底
4. `constraints` — OptimizerConstraints dataclass
5. `solver` — `solve_max_sharpe`（cvxpy 默认 → scipy SLSQP fallback，Round-2 锁定）
6. `check` — `check_constraints` + ConstraintReport
7. `baseline` — `compare_to_baseline` + ComparisonReport
8. `persistence` — `write_portfolio_outputs` 原子落盘
9. `cli` — `trader-off optimize` CLI

**Strategies:** `OptimizedTopKStrategy` (BaseStrategy 子类) + fallback LGBMTop20Strategy (v0.1.0 保留)

### Tech stack decisions

- **Optimizer backend**：cvxpy>=1.5 + ECOS 默认；ImportError 时 fallback `scipy.optimize.minimize(method="SLSQP")`，INFO 日志 `"cvxpy unavailable, fallback to scipy.optimize.SLSQP"`（Round-2 锁定）
- **Cron parser**：**croniter>=2.0 主路径**（`next_cron_fire` 纯函数）；APScheduler>=3.10 列为已装依赖（满足 NFR-0500 AC-3 "uv pip list" 检查），但 **不** 作为默认 tick loop 引擎
- **Clock injection（T-1）**：`ClockPort` Protocol + `SystemClockPort`（默认，包 `datetime.now(timezone.utc)`）+ `VirtualClockPort`（测试用，可 set_now/advance）
- **TrainerPort（T-2）**：`TrainerPort` Protocol + `DefaultTrainerPort`（包装 v0.1.0 training.trainer + training.model_io）
- **Parquet I/O**：pyarrow>=14.0 显式后端（drift_history.parquet + fixture 互操作）
- **Hot-reload**：默认 polling 60s；watchdog>=4.0 可选 hot-reload（默认不启用）
- **V0.1.0 兼容**：`load_model(version)` 正则识别 `^\d{8}_\d{6}$` (v0.1.0) vs `^v\d+\.\d+\.\d+(\.incr\d+)?$` (v0.2.0)；v0.1.0 CLI 签名保持；LGBMTop20Strategy 不删除
- **OptimizedTopKStrategy fallback**：`weights.csv` 缺失或陈旧 (>5 交易日) → WARNING + fallback LGBMTop20Strategy

### Three-way closure

| Layer | Coverage |
| --- | --- |
| acceptance (159 AC) → interfaces exits | 100% (interfaces §1-7 全部覆盖) |
| interfaces exits → test-plan coverage | 100% (test-plan §9 总表确认 159/159) |
| cross-module (≥2 modules) interfaces → integration test coverage | 26 cross-module interfaces 全部在 test-plan §8.2 集成测试文件中覆盖 |

### T-1~T-4 落地

| # | 契约位置 | 签名 sketch |
|---|---|---|
| T-1 | interfaces §3.6 `ClockPort` | `now(self) -> datetime`（tz-aware UTC）；注入 `SchedulerConfig.clock` |
| T-2 | interfaces §3.6 `TrainerPort` | `async train(mode, parent_version, ...) -> ModelArtifact`；`async save(artifact, mode, trigger, ...) -> str` |
| T-3 | interfaces §3.8 `next_cron_fire` | `(expr: str, base: datetime, *, backend="croniter"\|"apscheduler") -> datetime`（纯函数，无副作用） |
| T-4 | interfaces §1.8 `SchedulerConfig.{state_dir, models_dir, reports_dir}` + CLI `--output`/`--registry-dir` | 全部写盘路径可配置 |

### project.toml

**无变更**（与 M-TESTPLAN 锁定状态一致）：
- `[e2e]`: paths=["tests/e2e","tests/perf"]，run=`uv run pytest tests/e2e tests/perf -m e2e -v`（无 start/ready/teardown —— 项目无外部服务启动）
- `[integration]`: paths=["tests/integration"]，run=`uv run pytest tests/integration -m integration -v`
- `[meta].test_framework`: "pytest"
- 新增物理目录：`tests/perf/`（空目录占位，Shield 在 M-E2E 阶段填充）

## Tried but abandoned

1. **修改 pyproject.toml 直接追加 v0.2.0 依赖**：放弃。Archer agent 权限仅允许写 `.pre-commit-config.yaml` 与 spec 文档，不允许写 `pyproject.toml`。改为在 architecture.md §3.5 列出"Devon 在 R-G-R 阶段必须执行的 pyproject.toml 变更清单"（version 0.1.0→0.2.0；追加 cvxpy/apscheduler/croniter/aiohttp/psutil/pyarrow/watchdog 运行时依赖；追加 mutmut/pytest-benchmark/mkdocstrings/griffe 开发依赖）。

2. **使用 APScheduler AsyncIOScheduler 作为调度器后端**：放弃。APScheduler JobStore 持久化与 `scheduler_state/` 文件持久化重复；引入 SQLAlchemy 重依赖；virtual clock 注入困难（spec FR-1600 同时接受 croniter 或 APScheduler，但 AC-FR1600-04 只测 `next_cron_fire` 纯函数行为，不绑定具体 backend）。改为 croniter 主路径 + APScheduler 列入依赖满足 NFR-0500 AC-3 但不在主路径调用。

3. **把 OptimizedTopKStrategy 放在 portfolio 模块**：放弃。spec FR-4200 明示模块路径 `trader_off.strategies.optimized_topk`，策略层与 portfolio 层解耦（策略只读 weights.csv，不深入 portfolio 内部实现）。fallback LGBMTop20Strategy 也保留在 strategies/。

4. **pyarrow 默认落盘后端**：放弃强制。polars 1.0 原生 parquet 已能写多数场景。pyarrow 作为显式 backend 用于：drift_history.parquet（长期历史，写入频率低但需要显式 schema）+ fixture 互操作（v0.1.0 fixture 可能由 pandas/pyarrow 生成）。

5. **Author-result.json hash 强制等于 M-TESTPLAN review hash**：放弃。validator (`lk agent archer validate-arch`) 调 `write_stage_result` 自动计算当前 bundle hash（含 architecture.md + interfaces.md，新加入），与 M-TESTPLAN 时的 bundle（只有 spec/acceptance/test-plan）hash 必然不同。参考 v0.1.0 M-ARCH history：M-TESTPLAN hashes (`2587bafedd...`, `3e55e1cdfdb...`) 与 M-ARCH hashes (`0a66db880d...`) 完全不同，但 advance gate 正常通过。advance gate 实际校验的是"author-result hash == review-result hash"（同一 bundle 内一致），而非跨 stage 一致。

## Open questions

- 无。全部 spec/acceptance 决策已锁定；4 个可测试性需求（T-1~T-4）已在 interfaces.md 中落地；3 个跨 stage 关注点（FR-1900 IC-only / FR-3700 cvxpy+scipy / v0.1.0 兼容）已在 interfaces 与 architecture 中显式编码；M-TESTPLAN 159/159 AC 全部有对应接口出口 + 测试覆盖。
