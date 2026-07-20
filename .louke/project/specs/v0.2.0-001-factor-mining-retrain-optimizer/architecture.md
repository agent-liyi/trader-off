# trader-off v0.2.0 — 因子挖掘·再训练调度·组合优化器 — Architecture Design

- **Spec ID**: v0.2.0-001-factor-mining-retrain-optimizer
- **Created**: 2026-07-17
- **Related spec**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/spec.md`
- **Related acceptance**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/acceptance.md`
- **Related test-plan**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/test-plan.md`
- **Related interfaces**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/interfaces.md`
- **继承基线**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/architecture.md`（v0.1.0 模块/技术栈仍生效；本文仅定义 v0.2.0 新增与变更部分）

> 本文是 Devon 实现的唯一架构依据（与 interfaces.md 共同锁定）。模块边界、依赖方向、技术选型与权衡均在本文锁定。
>
> **M-ARCH 来源依据**：本架构基于 spec.md（已 lock, `spec.md.lock` 存在） + Sage M-SPEC 锁定的 Round-2 决策（FR-1900 IC-only、FR-3700 cvxpy+scipy 回退）+ test-plan §6.7 四个可测试性需求（T-1~T-4）。

---

## 1. 系统概览

### 1.1. 组件关系图

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       trader-off v0.2.0（本项目）                             │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │           模块 A — 因子挖掘 (trader_off.factor_mining)               │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │   │
│  │  │templates │→│enumerate │→│evaluate  │→│ select   │→│ heatmap/ │    │   │
│  │  │          │ │_factors  │ │_factor   │ │ _factors │ │ report   │    │   │
│  │  └──────────┘ └──────────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘    │   │
│  │                                  │             │            │          │   │
│  │                                  ▼             ▼            ▼          │   │
│  │                            ┌──────────────────────────┐               │   │
│  │                            │ factor_registry/*.yaml|json            │   │
│  │                            └──────────────────────────┘               │   │
│  └──────────────────────────────────┬───────────────────────────────────┘   │
│                                     │ (selected_factors.json)               │
│                                     ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │           模块 B — 再训练调度 (trader_off.scheduler)                  │   │
│  │                                                                       │   │
│  │  ┌──────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐                │   │
│  │  │   core   │←─│  cron   │  │  drift   │  │  perf    │                │   │
│  │  │Retrain   │  │ tick +  │  │ PSI/KS + │  │ monitor  │                │   │
│  │  │Scheduler │  │ next_   │  │ DriftD   │  │ (IC only)│                │   │
│  │  │ + ports  │  │ cron_   │  │ ecisor   │  │ TriggerD │                │   │
│  │  └────┬─────┘  │ fire    │  └────┬─────┘  └────┬─────┘                │   │
│  │       │        └─────────┘       │             │                      │   │
│  │       │                          │             │                      │   │
│  │       ▼                          ▼             ▼                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────────────────┐    │   │
│  │  │ registry │  │   api    │  │  ports (注入)                     │    │   │
│  │  │ (model   │  │ aiohttp  │  │  TrainerPort / ClockPort /        │    │   │
│  │  │ versions)│  │ localhost│  │  ModelRegistryPort /              │    │   │
│  │  └──────────┘  └──────────┘  │  DriftDetectorPort /              │    │   │
│  │                              │  PerfMonitorPort                  │    │   │
│  │                              └──────────────────────────────────┘    │   │
│  └──────────────────────────────────┬───────────────────────────────────┘   │
│                                     │ (TrainerPort 调用)                     │
│                                     ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                  v0.1.0 模块（继承，不修改）                          │   │
│  │  trader_off.training.trainer/model_io  →  models/v*/ + registry.json │   │
│  │  trader_off.prediction.service          →  predict(model_version,..) │   │
│  │  trader_off.data.loader                 →  DataLoader (替身可注入)   │   │
│  │  trader_off.evaluation.ic               →  ic_pearson/spearman (复用)│   │
│  │  trader_off.features.*                  →  15 维固定特征 (回退路径)  │   │
│  └──────────────────────────────────┬───────────────────────────────────┘   │
│                                     │ (predictions_<date>.csv)              │
│                                     ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │           模块 C — 组合优化器 (trader_off.portfolio)                 │   │
│  │  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐      │   │
│  │  │expected │→│covariance│→│ industry│→│constraints│→│ solver   │      │   │
│  │  │_returns │ │(LW/sample)│ │  map    │ │ (Σw=1,    │ │ Max      │      │   │
│  │  │         │ │          │ │         │ │ long-only │ │ Sharpe   │      │   │
│  │  │         │ │          │ │         │ │ neutral,  │ │ cvxpy →  │      │   │
│  │  │         │ │          │ │         │ │ max=0.10) │ │ scipy    │      │   │
│  │  └─────────┘ └──────────┘ └─────────┘ └─────┬────┘ └────┬─────┘      │   │
│  │                                              │            │            │   │
│  │                                              ▼            ▼            │   │
│  │                                       ┌────────────┐ ┌────────────┐   │   │
│  │                                       │ check_     │ │ compare_   │   │   │
│  │                                       │ constraints│ │ to_baseline│   │   │
│  │                                       └────────────┘ └────────────┘   │   │
│  └──────────────────────────────────┬───────────────────────────────────┘   │
│                                     │ (reports/portfolio_<ts>/)             │
│                                     ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │         策略层 (trader_off.strategies) — 新增 optimized_topk         │   │
│  │                                                                       │   │
│  │  OptimizedTopKStrategy(BaseStrategy)                                  │   │
│  │   - init: load weights.csv (≥5d 老 → 降级 LGBMTop20Strategy)         │   │
│  │   - on_day_open: broker.trade_target_pct(asset, weight)              │   │
│  │   - fallback: LGBMTop20Strategy (v0.1.0 不变)                        │   │
│  └──────────────────────────────────┬───────────────────────────────────┘   │
│                                     │ (BacktestRunner 编排)                  │
│                                     ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │       cli (v0.2.0 新增 + v0.1.0 保留)                                │   │
│  │  新增: mine-factors / scheduler {start,stop,status,list-tasks} /      │   │
│  │        retrain {trigger,status,cancel} / optimize / deploy            │   │
│  │  保留: train / predict / backtest / feature-importance (v0.1.0 签名) │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │       utils (v0.1.0 继承) — logging / exceptions / config / security  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │ 继承 / 适配
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                 millionaire 框架 (外部依赖,继承 v0.1.0 集成方式)            │
│  quantide.core.strategy.BaseStrategy / quantide.service.base_broker.Broker   │
│  quantide.data.fetchers / BacktestRunner                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2. 端到端数据流（scenario-0050 全链路）

```
OHLCV (fetcher/DataLoader)
   │
   ├─[因子挖掘]──▶ factor_mining.enumerate_factors (≥200 候选)
   │                  │
   │                  ▼
   │             factor_mining.evaluate_factor (IC/ICIR/Rank IC)
   │                  │
   │                  ▼
   │             factor_mining.select_factors (Top-K + 去冗余)
   │                  │
   │                  ▼
   │             factor_registry/factors.yaml + selected_factors.json
   │
   ├─[训练 v0.1.0 + 精选因子]──▶ trader_off.training.train_model
   │                              (--factor-registry → feature pipeline 只算精选因子)
   │                                       │
   │                                       ▼
   │                              training.save_model → models/v0.X.Y.<build>/
   │                              training.model_io  → models/registry.json
   │
   ├─[预测 v0.1.0]──▶ trader_off.prediction.predict
   │                  (model_version="latest" → registry.json["current_version"])
   │                                       │
   │                                       ▼
   │                          predictions_<date>.csv  →  portfolio.expected_returns
   │
   ├─[优化]──▶ portfolio.covariance (Ledoit-Wolf shrinkage)
   │           portfolio.industry_map
   │           portfolio.solver (Max Sharpe, cvxpy → scipy fallback)
   │           portfolio.check_constraints + compare_to_baseline
   │                                       │
   │                                       ▼
   │                reports/portfolio_<ts>/weights.csv (+ 4 关联文件)
   │
   ├─[回测]──▶ strategies.OptimizedTopKStrategy
   │           (broker.trade_target_pct → BacktestRunner)
   │                                       │
   │                                       ▼
   │                reports/backtest_<ts>/summary.json + parquet 系列
   │
   └─[重训循环，模块 B 异步]──▶ scheduler.trigger_now (cron/drift/perf/manual)
                                  │
                                  ▼
                         TrainerPort.train (full / incremental refit)
                                  │
                                  ▼
                         training.save_model → 更新 registry.json
                                  │
                                  ▼
                         deploy: prediction.predict lazy-loads latest
```

---

## 模块划分

> 本节是 interfaces.md `modules` 列的权威来源。Shield 据此判定跨模块接口（≥2 模块 → 集成测试覆盖）。

### 2.1. 新增模块清单与职责（v0.2.0）

| #  | 模块路径                                    | 职责（单行）                                                  | 实现 FR/NFR              | 层次      |
| -- | ------------------------------------------- | ------------------------------------------------------------- | ------------------------ | --------- |
| 1  | `trader_off.factor_mining.templates`        | 因子模板注册表（4 类 ≥12 模板）+ 参数化枚举                     | FR-0100, FR-0200         | 纯计算    |
| 2  | `trader_off.factor_mining.evaluation`       | IC / ICIR / Rank IC / 分层收益评估（复用 v0.1.0 evaluation.ic）| FR-0300                  | 纯计算    |
| 3  | `trader_off.factor_mining.selection`        | Top-K + Pearson 去冗余 + 字典序 tiebreak                        | FR-0400                  | 纯计算    |
| 4  | `trader_off.factor_mining.viz`              | 相关性热力图 PNG + HTML/MD 评估报告                              | FR-0500, FR-0700         | 纯渲染    |
| 5  | `trader_off.factor_mining.registry`         | 因子注册表持久化（YAML/JSON）+ schema 校验                     | FR-0600                  | 持久化    |
| 6  | `trader_off.factor_mining.cli`              | `trader-off mine-factors` CLI（pydantic + 退出码 0/2/3/4）       | FR-0800                  | CLI       |
| 7  | `trader_off.factor_mining.score`            | 精选因子加权合成得分（供 portfolio.expected_returns 备选输入）  | FR-3100 (备选路径)        | 纯计算    |
| 8  | `trader_off.scheduler.core`                 | RetrainScheduler 主类 + 端口注入 + 状态持久化                  | FR-1500, FR-2500, FR-2600 | 编排      |
| 9  | `trader_off.scheduler.cron`                 | next_cron_fire 纯函数 + cron 配置 + 交易日过滤                   | FR-1600                  | 纯计算    |
| 10 | `trader_off.scheduler.drift.psi`            | PSI 漂移检测（等频分箱 + epsilon 防 log0）                     | FR-1700                  | 纯计算    |
| 11 | `trader_off.scheduler.drift.ks`             | KS 漂移检测（scipy.stats.ks_2samp + NaN 兜底）                  | FR-1800                  | 纯计算    |
| 12 | `trader_off.scheduler.drift.detector`       | DriftDetector 编排 PSI/KS → DriftDecision（light/moderate/strong）| FR-2600                  | 编排      |
| 13 | `trader_off.scheduler.perf_monitor`         | PerfMonitor + trigger_perf_degradation（IC-only，Round-2 锁定）| FR-1900                  | 纯计算    |
| 14 | `trader_off.scheduler.ports`                | TrainerPort / ClockPort / ModelRegistryPort / DriftDetectorPort / PerfMonitorPort | FR-1500                  | 接口      |
| 15 | `trader_off.scheduler.registry`             | ModelRegistry + 版本 GC（keep_latest_n/pinned/full_only）+ rollback | FR-2300                  | 持久化    |
| 16 | `trader_off.scheduler.deploy`               | 验证后自动部署（lazy/hot-reload）+ deploy.log + 损坏模型回退      | FR-2400                  | 编排      |
| 17 | `trader_off.scheduler.api`                  | aiohttp REST 应用（localhost only）+ trigger/status/cancel       | FR-2000                  | 接口      |
| 18 | `trader_off.scheduler.cli`                  | scheduler / retrain CLI（pydantic + 退出码）                    | FR-2000, FR-2700         | CLI       |
| 19 | `trader_off.portfolio.covariance`           | Ledoit-Wolf / 样本协方差 + assets_dropped 落盘                  | FR-3000                  | 纯计算    |
| 20 | `trader_off.portfolio.expected_returns`     | build_expected_returns（raw / zscore）+ asset 一致性校验         | FR-3100                  | 纯计算    |
| 21 | `trader_off.portfolio.industry`             | load_industry_map + IndustryMapConflictError + 未分类虚拟行业    | FR-3200                  | 纯计算    |
| 22 | `trader_off.portfolio.constraints`          | OptimizerConstraints dataclass（Σw=1 / long-only / 中性 / max-weight）| FR-3300~3600             | 数据      |
| 23 | `trader_off.portfolio.solver`               | solve_max_sharpe（cvxpy ECOS 默认 → scipy SLSQP fallback）        | FR-3700                  | 编排      |
| 24 | `trader_off.portfolio.check`                | check_constraints 后验校验 + ConstraintReport                    | FR-3800                  | 纯计算    |
| 25 | `trader_off.portfolio.baseline`             | compare_to_baseline + 等权基线                                  | FR-3900                  | 纯计算    |
| 26 | `trader_off.portfolio.persistence`          | reports/portfolio_<ts>/ 5 产物原子落盘                            | FR-4000                  | 持久化    |
| 27 | `trader_off.portfolio.cli`                  | `trader-off optimize` CLI（pydantic + 退出码 0/2/3/4）            | FR-4100                  | CLI       |
| 28 | `trader_off.strategies.optimized_topk`      | OptimizedTopKStrategy（继承 BaseStrategy；降级 LGBMTop20Strategy）| FR-4200                  | 策略      |

### 2.2. 继承模块（v0.1.0 不变，仅作为依赖消费）

| #  | 模块路径                            | v0.2.0 角色                                       |
| -- | ----------------------------------- | ------------------------------------------------- |
| 1  | `trader_off.features`               | v0.1.0 固定 15 维特征回退路径（无 --factor-registry）|
| 2  | `trader_off.training.trainer`       | 全量/增量训练由 TrainerPort 包装调用                |
| 3  | `trader_off.training.model_io`      | 模型加载必须兼容 v0.1.0 `YYYYMMDD_HHMMSS` 目录      |
| 4  | `trader_off.prediction.service`     | predict(model_version=...) 接受两种版本格式         |
| 5  | `trader_off.data.loader`            | DataLoader 替身注入（fixture parquet）             |
| 6  | `trader_off.evaluation.ic`          | ic_pearson / ic_spearman / compute_layered_returns |
| 7  | `trader_off.strategies.lgbm_top20`  | 保留为 fallback；OptimizedTopKStrategy 降级时调用   |
| 8  | `trader_off.backtest.runner`        | BacktestRunner 编排 OptimizedTopKStrategy 生命周期 |
| 9  | `trader_off.utils.{logging,exceptions,config,security}` | 不变                                       |

### 2.3. 包目录结构

```
trader_off/
├── __init__.py
├── features/                          # v0.1.0（继承）
├── labels/                            # v0.1.0（继承）
├── data/                              # v0.1.0（继承）
├── training/                          # v0.1.0（继承）
├── prediction/                        # v0.1.0（继承）
├── backtest/                          # v0.1.0（继承）
├── evaluation/                        # v0.1.0（继承）
├── importance/                        # v0.1.0（继承）
├── visualization/                     # v0.1.0（继承）
├── strategies/
│   ├── __init__.py
│   ├── lgbm_top20.py                  # v0.1.0 保留（FR-4200 fallback）
│   └── optimized_topk.py              # v0.2.0 新增 (FR-4200)
├── factor_mining/                     # v0.2.0 新增
│   ├── __init__.py                    # 导出 list_templates, enumerate_factors, evaluate_factor, select_factors, FactorTemplate, FactorSpec, FactorEvaluation, SelectionDiagnostics, FactorRegistrySchemaError
│   ├── templates.py                   # FactorTemplate, IntRangeParam, ChoiceParam, BoolParam (FR-0100)
│   ├── expression.py                  # enumerate_factors (FR-0200)
│   ├── evaluation.py                  # FactorEvaluation, evaluate_factor (FR-0300)
│   ├── selection.py                   # select_factors, SelectionDiagnostics (FR-0400)
│   ├── viz.py                         # render_correlation_heatmap, render_evaluation_report (FR-0500/0700)
│   ├── registry.py                    # save_factor_registry, load_factor_registry, FactorRegistrySchemaError (FR-0600)
│   ├── score.py                       # compute_factor_score (FR-3100 备选)
│   └── cli.py                         # mine-factors CLI (FR-0800)
├── scheduler/                         # v0.2.0 新增
│   ├── __init__.py                    # 导出 RetrainScheduler, next_cron_fire, DriftDetector, PerfMonitor, ModelRegistry, DriftDecision, TriggerDecision
│   ├── ports.py                       # TrainerPort / ClockPort / ModelRegistryPort / DriftDetectorPort / PerfMonitorPort (FR-1500/T-1/T-2)
│   ├── core.py                        # RetrainScheduler + SchedulerConfig + SchedulerStatus + RetrainTask + TriggerReason (FR-1500/2500/2600)
│   ├── cron.py                        # next_cron_fire + 交易日过滤 (FR-1600/T-3)
│   ├── state.py                       # atomic write + 恢复 (FR-2500)
│   ├── drift/
│   │   ├── __init__.py                # 导出 compute_psi/ks, DriftDetector, DriftDecision
│   │   ├── psi.py                     # compute_psi, compute_feature_psi (FR-1700)
│   │   ├── ks.py                      # compute_ks_pvalue, compute_feature_ks (FR-1800)
│   │   └── detector.py                # DriftDetector.evaluate → DriftDecision (FR-2600)
│   ├── perf_monitor.py                # PerfMonitor + TriggerDecision (FR-1900)
│   ├── registry.py                    # ModelRegistry + GC + rollback (FR-2300)
│   ├── deploy.py                      # deploy_model + watch_registry (FR-2400)
│   ├── api.py                         # create_app(aiohttp) (FR-2000)
│   └── cli.py                         # scheduler / retrain CLI (FR-2000/2700)
├── portfolio/                         # v0.2.0 新增
│   ├── __init__.py                    # 导出 solve_max_sharpe, estimate_covariance, build_expected_returns, OptimizerConstraints
│   ├── covariance.py                  # estimate_covariance (FR-3000)
│   ├── expected_returns.py            # build_expected_returns (FR-3100)
│   ├── industry.py                    # load_industry_map + IndustryMapConflictError (FR-3200)
│   ├── constraints.py                 # OptimizerConstraints dataclass (FR-3300~3600)
│   ├── solver.py                      # solve_max_sharpe (FR-3700)
│   ├── check.py                       # check_constraints + ConstraintReport (FR-3800)
│   ├── baseline.py                    # compare_to_baseline + ComparisonReport (FR-3900)
│   ├── persistence.py                 # write_portfolio_outputs 原子落盘 (FR-4000)
│   └── cli.py                         # optimize CLI (FR-4100)
├── cli/                               # v0.1.0（继承）；v0.2.0 新增子命令注册
│   ├── __init__.py                    # main() 入口分发 + 新增 5 个子命令
│   ├── train.py                       # v0.1.0 + 新增 --factor-registry (FR-0900)
│   ├── predict.py                     # v0.1.0（接受 v1/v2 版本格式）
│   ├── backtest.py                    # v0.1.0 + 新增 --strategy optimized_topk
│   ├── feature_importance.py          # v0.1.0
│   ├── mine_factors.py                # v0.2.0 新增 (FR-0800)
│   ├── scheduler.py                   # v0.2.0 新增 (FR-2700)
│   ├── retrain.py                     # v0.2.0 新增 (FR-2000)
│   ├── optimize.py                    # v0.2.0 新增 (FR-4100)
│   └── deploy.py                      # v0.2.0 新增 (FR-2400)
└── utils/                             # v0.1.0（继承）
    ├── logging.py                     # NFR-0600
    ├── exceptions.py                  # 新增 PortfolioError, SchedulerError, FactorMiningError 等
    ├── config.py                      # NFR-0800 配置优先级
    └── security.py                    # NFR-0700 路径校验 + joblib 白名单
```

### 2.4. 依赖关系（调用方向）

> 箭头 `A ──▶ B` 表示 A 依赖（调用）B。依赖单向，禁止循环。

```
cli ──▶ factor_mining, scheduler, portfolio, training, prediction, backtest, data, utils
backtest ──▶ strategies, portfolio(weight files), evaluation, importance, visualization, data, utils
strategies.optimized_topk ──▶ strategies.lgbm_top20 (fallback), portfolio (weights.csv), prediction, training(model_io), data(loader), utils
strategies.lgbm_top20 ──▶ prediction, training(model_io), data(loader), utils
portfolio.cli ──▶ portfolio.{covariance, expected_returns, industry, constraints, solver, check, baseline, persistence}
portfolio.solver ──▶ portfolio.{constraints}, utils
portfolio.cli ──▶ prediction.service (read predictions.csv)
factor_mining.cli ──▶ factor_mining.{templates, expression, evaluation, selection, viz, registry}
factor_mining.evaluation ──▶ evaluation.ic (v0.1.0 reuse), utils
factor_mining.score ──▶ factor_mining.registry (selected_factors.json), features, utils
scheduler.cli ──▶ scheduler.{core, api}
scheduler.core ──▶ scheduler.{cron, drift.detector, perf_monitor, registry, deploy, state, ports}, utils
scheduler.core ──▶ training.trainer (via TrainerPort), training.model_io (via ModelRegistryPort)
scheduler.deploy ──▶ prediction.service (lazy/hot-reload trigger)
scheduler.api ──▶ scheduler.core (handler delegates)
training (v0.1.0) ──▶ factor_mining.registry (when --factor-registry provided), data(preprocess), labels, utils
prediction (v0.1.0) ──▶ training(model_io), features, data(preprocess), data(loader), utils
data ──▶ features, utils
utils ──▶ (no internal deps)
```

**层次约束**（继承并扩展 v0.1.0 规则）：
- `utils` 是最底层，不依赖任何 `trader_off` 内部模块
- `features` / `labels` / `evaluation.ic` 是纯计算层，仅依赖 `utils`
- `data` 依赖 `features`（预测时按需调用）
- `factor_mining` / `portfolio` 是 v0.2.0 新增的两个业务模块集合，可依赖 `features` / `evaluation.ic` / `utils`，不得依赖 `training` / `prediction`（通过 ports 解耦）
- `scheduler` 通过 ports 与 `training` / `prediction` 解耦；调度器本身不直接 import `quantide.*`（FR-1500 AC-4 强制）
- `strategies` 是策略层，可依赖 portfolio 落盘结果与 prediction，但不得依赖 portfolio 的内部实现
- `cli` 是最顶层编排层，可依赖所有业务模块
- **禁止反向依赖**：`features` 不得依赖 `factor_mining`；`prediction` 不得依赖 `portfolio`

---

## 3. 技术选型

### 3.1. 运行时依赖（v0.2.0 新增部分）

| 依赖              | 版本约束      | 用途                                            | License      | 引入理由（FR/NFR）              |
| ----------------- | ------------- | ----------------------------------------------- | ------------ | ------------------------------- |
| `cvxpy`           | `>=1.5,<2.0`  | Max Sharpe 凸优化建模（默认 ECOS backend）         | Apache-2.0   | FR-3700（Round-2 锁定默认）       |
| `scipy`           | `>=1.13,<2.0` | SLSQP 求解器 fallback + KS 检验 + LedoitWolf 参考  | BSD-3        | FR-3700 fallback / FR-1800 / v0.1.0 |
| `apscheduler`     | `>=3.10,<4.0` | CronTrigger 备选解析（FR-1600 AC-4「二者其一」）；满足 NFR-0500 AC-3 必装 | MIT          | FR-1600 / NFR-0500 AC-3         |
| `croniter`        | `>=2.0,<3.0`  | next_cron_fire 主解析器（轻量纯函数友好）          | MIT          | FR-1600 / T-3（test-plan §6.7）  |
| `aiohttp`         | `>=3.9,<4.0`  | scheduler REST API（localhost only）              | Apache-2.0   | FR-2000                          |
| `psutil`          | `>=5.9,<6.0`  | NFR-0100 AC-4 内存峰值监控                         | BSD-3        | NFR-0100 AC-4                    |
| `pyarrow`         | `>=14.0,<18.0`| parquet 落盘后端（drift_history / fixture 读）+ 显式 schema 控制 | Apache-2.0 | FR-2500（drift_history.parquet）  |
| `watchdog`        | `>=4.0,<6.0`  | 可选 hot-reload 文件监听（默认不启用，polling 60s） | Apache-2.0   | FR-2400 hot-reload 可选          |
| `pydantic`        | `>=2.7,<3.0`  | CLI / 配置校验（继承 v0.1.0）                     | MIT          | v0.1.0 + 新 CLI 子命令           |
| `polars`          | `>=1.0,<2.0`  | 数据处理（继承 v0.1.0）                           | MIT          | v0.1.0                           |
| `lightgbm`        | `>=4.3,<5.0`  | 训练 / refit（继承 v0.1.0）                       | MIT          | v0.1.0 / FR-2100/2200            |
| `numpy`           | `>=1.26,<3.0` | 数值计算（继承 v0.1.0）                           | BSD-3        | v0.1.0                           |
| `loguru`          | `>=0.7,<1.0`  | 结构化日志（继承 v0.1.0）                         | MIT          | NFR-0600                          |
| `pyyaml`          | `>=6.0,<7.0`  | 因子注册表 / 配置加载                             | MIT          | FR-0600 / NFR-0700               |
| `scikit-learn`    | `>=1.3,<2.0`  | LedoitWolf shrinkage + StandardScaler（继承 v0.1.0）| BSD-3        | FR-3000 / v0.1.0                 |
| `joblib`          | `>=1.4,<2.0`  | 模型序列化（继承 v0.1.0）                          | BSD-3        | v0.1.0 NFR-0700                  |
| `matplotlib`      | `>=3.7,<4.0`  | 相关性热力图 + 评估报告（继承 v0.1.0）              | PSF          | FR-0500/0700 / v0.1.0            |
| `millionaire`     | `>=0.1`       | BacktestRunner / BaseStrategy / Broker / fetchers | 待确认       | v0.1.0 集成（不变）               |

### 3.2. 开发时依赖（v0.2.0 新增部分）

| 依赖                | 版本约束       | 用途                                                |
| ------------------- | -------------- | --------------------------------------------------- |
| `mutmut`            | `>=2.0,<3.0`   | Mutation testing（NFR-0300 ≥80%）                    |
| `pytest-benchmark`  | `>=4.0,<5.0`   | NFR-0100 性能基准（perftest 钩子）                   |
| `mkdocstrings`      | `>=0.24,<1.0`  | API 文档自动生成（NFR-0400 / ADR-001）                |
| `griffe`            | `>=0.40,<1.0`  | mkdocstrings 后端依赖（NFR-0400）                    |

> v0.1.0 已有的 dev 依赖（pytest, pytest-cov, pytest-asyncio, pytest-mock, pytest-timeout, pytest-socket, ruff, bandit）继承不变。

### 3.3. 工具链

| 工具       | 用途                                              | 继承/新增 |
| ---------- | ------------------------------------------------- | --------- |
| `uv`       | 包管理（pyproject.toml，NFR-0500 AC-3 必装）       | 继承      |
| `ruff`     | lint + format（line length 100）                    | 继承      |
| `pytest`   | 测试运行（asyncio_mode=auto）                       | 继承      |
| `bandit`   | 安全扫描（-ll，无 HIGH，NFR-0700 AC-5）             | 继承      |
| `mutmut`   | mutation testing（NFR-0300）                        | 新增      |
| `mkdocs`   | 文档站点（NFR-0400，可选）                          | 新增      |

### 3.4. 关键 pytest 插件配置

继承 v0.1.0 配置 + 新增 `slow` / `mutation` marker（如需）：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "e2e: end-to-end tests",
    "integration: integration tests requiring external dependencies",
    "slow: slow-running tests (>30s, requires timeout marker)",
]
addopts = "--strict-markers"
```

### 3.5. pyproject.toml 版本与依赖变更清单（Devon 在 R-G-R 阶段执行）

> Archer 不直接修改 `pyproject.toml`（按 agent 权限约定），但列出 v0.2.0 必须的变更清单，作为 Devon 的执行依据：

1. `version`: `"0.1.0"` → `"0.2.0"`
2. `dependencies` 追加：`cvxpy`, `apscheduler`, `croniter`, `aiohttp`, `psutil`, `pyarrow`, `watchdog`
3. `[project.optional-dependencies.dev]` 追加：`mutmut`, `pytest-benchmark`, `mkdocstrings`, `griffe`

---

## 4. 关键权衡

### 4.1. cvxpy 默认 + scipy SLSQP fallback（FR-3700，Round-2 锁定）

| 维度     | 决策：cvxpy + ECOS 默认，SLSQP 自动 fallback              | 放弃：仅用 cvxpy                 | 放弃：仅用 scipy SLSQP              |
| -------- | --------------------------------------------------------- | ------------------------------- | ----------------------------------- |
| 解决问题 | 凸优化建模自然（`cp.Problem(cp.Maximize, ...)`）+ 零依赖兜底 | —                               | —                                   |
| 优势     | 表达力强；环境差异下不退化；cvxpy Apache-2.0 友好          | 单一求解路径，调试简单          | 无 cvxpy ~50MB 安装体积             |
| 风险     | 安装体积 + cvxpy 解析开销；fallback 数值精度略低           | cvxpy 缺失即崩溃（无兜底）      | 二次规划建模笨拙，求解慢 / 易失败   |
| 缓解     | ImportError 仿真测试（AC-FR3700-03）；fallback 用 SLSQP 默认参数 + 1000 iter | —                               | —                                   |

**fallback 触发机制**：`trader_off.portfolio.solver` 启动时 `try: import cvxpy; HAS_CVXPY = True; except ImportError: HAS_CVXPY = False`。决策时根据 flag 选择 backend；INFO 日志 "cvxpy unavailable, fallback to scipy.optimize.SLSQP"（与 AC-FR3700-03 锁定）。

### 4.2. APScheduler vs croniter（FR-1600 / T-3）

| 维度     | 决策：**`croniter` 主路径**（`next_cron_fire` 纯函数）；`APScheduler` 列为已装依赖（NFR-0500 AC-3），但**不**作为默认 tick loop 引擎 | 放弃：APScheduler AsyncIOScheduler 全套          | 放弃：自写 cron 解析器                 |
| -------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | --------------------------------------- |
| 解决问题 | cron 解析轻量 + 纯函数可测（T-3 必须）                                                                                       | —                                               | —                                       |
| 优势     | croniter ~50KB、无 asyncio 耦合；APScheduler 装但不强制使用，保留 swap-in 空间；零自研解析器风险                         | 开箱即用，与 APScheduler JobStore 集成          | 零依赖                                  |
| 风险     | croniter 与 APScheduler CronTrigger 行为差异需测试（同一 expr 结果一致）                                                  | JobStore 持久化与 `scheduler_state/` 文件持久化重复；引入 SQLAlchemy 依赖；virtual clock 注入困难 | 正确性风险（闰年/夏令时等边界）        |
| 缓解     | `next_cron_fire` 接口签名固定，内部实现可换；测试用 `croniter` 作为 Ground Truth 参考实现 | —                                              | —                                       |

**结论**：默认 `croniter` 实现 `next_cron_fire`；APScheduler 不被业务路径调用，仅满足 NFR-0500 AC-3 的「必装」要求并保留扩展点。

### 4.3. 虚拟时钟注入 vs 真实时钟（T-1）

| 维度     | 决策：ClockPort 注入（默认 `lambda: datetime.now(timezone.utc)`）            | 放弃：硬编码 `datetime.now()`           | 放弃：Monkey-patch 系统时钟             |
| -------- | ----------------------------------------------------------------------------- | --------------------------------------- | --------------------------------------- |
| 解决问题 | 测试可注入虚拟时钟，e2e 加速（cron 16:00 → 秒级），FR-1500/1600/2500/2600 可测 | —                                       | —                                       |
| 优势     | 显式契约，可观察；devon 实现无需关心测试；与 asyncio 兼容                    | 简单                                    | 全局生效                                |
| 风险     | 漏注入 → 真实时钟；多模块都需注入                              | 不可测 / 必须真实等待                  | 测试间相互污染；CI flake                |
| 缓解     | `SchedulerConfig.clock` 字段强制提供；未传则 fallback 默认（无 clock 注入的开发体验）| —                                       | —                                       |

**契约**（见 interfaces §3.x）：`ClockPort.now() -> datetime`（aware, UTC）。`RetrainScheduler` 内部 `tick` / `next_cron_fire(base=self._clock.now())` / `last_full_retrain_date = self._clock.now()` 均通过此 port。

### 4.4. 调度器持久化：文件系统 vs APScheduler JobStore

| 维度     | 决策：文件系统（`scheduler_state/*.json|jsonl|parquet`）+ atomic write | 放弃：APScheduler JobStore（SQLAlchemy + DB） |
| -------- | ----------------------------------------------------------------------- | ----------------------------------------------- |
| 解决问题 | 简单可调试、版本控制友好、atomic rename 保护半写入                       | —                                               |
| 优势     | 无 DB 依赖；JSON/JSONL 易 diff；与 NFR-0900 AC-2 原子性诉求对齐          | 集群就绪                                       |
| 风险     | 单机；目录膨胀需 GC                                                       | 引入 SQLAlchemy 重依赖；JobStore 语义与我们的 task lifecycle 不同 |
| 缓解     | `scheduler_state/drift_history.parquet` 走 pyarrow 长期归档；FR-2300 GC 策略类比清理 | — |

### 4.5. TrainerPort 注入 vs 直接调用 v0.1.0 train_model（T-2）

| 维度     | 决策：TrainerPort 协议 + 默认实现 `DefaultTrainerPort` 包 v0.1.0 `train_model`/`save_model` | 放弃：直接 `from trader_off.training import train_model`（在 scheduler 内） |
| -------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 解决问题 | 单测可注入 mock trainer 验证串行；scheduler 模块不直接耦合 training 模块                  | —                                                                          |
| 优势     | 模块边界清晰；可独立单元测试调度器逻辑                                                    | 少一层抽象                                                                 |
| 风险     | 协议需维护（method 集合与 v0.1.0 签名一致）                                              | 调度器测试必须真实训练，无法快速验证                                         |
| 缓解     | `TrainerPort` 是 `Protocol` 类，单测用 `unittest.mock.AsyncMock` 替身                       | —                                                                          |

### 4.6. hot-reload：watchdog vs polling

| 维度     | 决策：**默认 polling 60s**（与 spec FR-2400 锁定一致）                                | 放弃：watchdog 默认启用                          |
| -------- | ------------------------------------------------------------------------------------- | ------------------------------------------------ |
| 解决问题 | 零额外进程；简单可调试；预测服务无需后台线程                                          | —                                                |
| 优势     | 跨平台一致；CPU 几乎为零                                                              | 文件变化即时响应                                  |
| 风险     | 最坏 60s 延迟                                                                         | watchdog 多平台差异；额外进程/线程管理           |
| 缓解     | `model_load_mode="hot-reload"` 时启用 watchdog（可选）；watchdog 包含为依赖但不默认调用 | —                                                |

### 4.7. 模型版本格式共存：v0.1.0 vs v0.2.0（NFR-1000）

| 维度     | 决策：**两种格式并存**：`load_model(version: str)` 通过正则自动识别        | 放弃：迁移 v0.1.0 模型到新格式             |
| -------- | -------------------------------------------------------------------------- | ------------------------------------------- |
| 解决问题 | v0.1.0 已序列化的模型（`models/<YYYYMMDD_HHMMSS>/`）仍能被加载             | —                                           |
| 优势     | 零迁移成本；向后兼容测试可断言旧模型 + 新 predict 链路                    | 目录统一                                    |
| 风险     | 目录结构两种风格混存；需要正则区分（`^\d{8}_\d{6}$` vs `^v\d+\.\d+\.\d+(\.incr\d+)?$`）| —                                       |
| 缓解     | `load_model` 内部先尝试 v0.2.0 格式，失败则尝试 v0.1.0；NFR-1000 AC-1/AC-2 用真实 v0.1.0 fixture 验证 | — |

### 4.8. pyarrow for parquet I/O

| 维度     | 决策：pyarrow 显式后端（用于 `drift_history.parquet` + fixture 读取）                  | 放弃：polars 原生 parquet（无 pyarrow）                |
| -------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------ |
| 解决问题 | 显式 schema 控制；与可能由 pandas 生成的 v0.1.0 fixture 兼容；`pd.read_parquet` 与 `pyarrow` 兼容性更稳定 | —                                                      |
| 优势     | schema 跨版本可复现；fixture 兼容性好                                              | 少一个依赖                                             |
| 风险     | pyarrow ~30MB 安装体积                                                              | polars 写 parquet 在某些版本对 nullable schema 有微差异 |
| 缓解     | `pyarrow>=14.0,<18.0` pin；polars 写 parquet 仍可用，但显式 `engine="pyarrow"` 时走 pyarrow | —                                                      |

> polars 1.0 默认 parquet 引擎在多数场景无需 pyarrow，但 fixture 互操作与 schema 稳定性要求 pyarrow。

### 4.9. OptimizedTopKStrategy fallback 行为

| 维度     | 决策：`weights.csv` 缺失或陈旧（>5 交易日）→ 降级为 LGBMTop20Strategy 行为       | 放弃：直接抛错                              | 放弃：始终用优化器结果，忽略陈旧数据            |
| -------- | --------------------------------------------------------------------------------- | ------------------------------------------- | ----------------------------------------------- |
| 解决问题 | 调度未跑 / 优化失败时，策略仍可工作（容错）                                       | —                                           | —                                               |
| 优势     | 业务连续性；与 v0.1.0 LGBMTop20Strategy 共存                                      | 简单                                        | 严格遵守优化结果                                  |
| 风险     | 行为切换可能掩盖优化失败（需 WARNING 日志）                                       | 生产挂掉                                    | 优化结果过期仍用，引入预测风险                   |
| 缓解     | WARNING 日志：`weights.csv missing, falling back to equal-weight top-K behavior` / `weights stale (5+ days old), falling back`（AC-FR4200-04/05） | — | — |

### 4.10. 调度器并发模型：单任务串行

| 维度     | 决策：`max_concurrent_tasks=1`（可配置但默认 1）                                     | 放弃：多任务并发                            |
| -------- | ------------------------------------------------------------------------------------ | ------------------------------------------- |
| 解决问题 | 训练是 CPU/GPU 密集型，并发反而降低效率；单任务串行最简单可控                       | —                                           |
| 优势     | asyncio.Lock 保护状态变更；状态机清晰                                               | 高吞吐                                      |
| 风险     | 任务积压；冷启动延迟                                                                 | 资源争用；锁复杂度                           |
| 缓解     | FIFO 队列（pending_tasks）；触发时刻记录；NFR-0900 AC-1 断言活跃 ≤1                | —                                           |

---

## 5. v0.1.0 向后兼容集成

### 5.1. 模型加载双格式（`load_model` 行为表）

| `version` 参数格式                | 识别方式                                        | 行为                                            |
| --------------------------------- | ----------------------------------------------- | ----------------------------------------------- |
| `20260101_120000`（v0.1.0 15 字符）| `len==15 and version[8]=="_"` 正则              | 读取 v0.1.0 目录结构；metadata 缺字段填 None     |
| `v0.2.0.5`（v0.2.0 新格式）        | `^v\d+\.\d+\.\d+(\.incr\d+)?$` 正则             | 读取 v0.2.0 目录；metadata 必有新增字段          |
| 其他                              | 抛 `ModelVersionExistsError` / `FileNotFoundError` | 不静默 fallback（避免误导）                  |

> 实现位置：`trader_off/training/model_io.py`（v0.1.0 模块，仅在内部追加格式识别逻辑，外部签名不变）。

### 5.2. CLI 命令签名保持

| CLI 命令                       | v0.1.0 签名                                                       | v0.2.0 变更                                      |
| ------------------------------ | ----------------------------------------------------------------- | ------------------------------------------------ |
| `trader-off train`             | 同 v0.1.0（必填参数、退出码、--config）                            | 新增可选 `--factor-registry <path>`（FR-0900）    |
| `trader-off predict`           | 同 v0.1.0（`--model` 接受两种版本格式）                            | 无破坏性变更                                     |
| `trader-off backtest`          | 同 v0.1.0（`--strategy` 接受 `lgbm_top20` 与 `optimized_topk`）    | 新增 `optimized_topk` 选项                       |
| `trader-off feature-importance`| 同 v0.1.0                                                          | 无变更                                          |

### 5.3. LGBMTop20Strategy 保留

- `trader_off.strategies.lgbm_top20.LGBMTop20Strategy` 不删除、不修改
- `OptimizedTopKStrategy` 在 `weights.csv` 缺失/陈旧时 fallback 为其行为（import + 复用其 `on_day_open` 逻辑或子类化）
- NFR-1000 AC-4 断言：v0.1.0 `LGBMTop20Strategy` 仍可 import + 实例化 + 运行，无 deprecation warning

---

## 6. 数据流详图

### 6.1. 因子挖掘流水线

```
cli.mine-factors --config configs/factor_mining.yaml --start 2020-01-01 --end 2024-12-31 --top-k 30
  │
  ├─▶ config.load(yaml) ──▶ 合并 CLI > yaml > 默认（utils.config）
  │
  ├─▶ factor_mining.templates.list_templates() → list[FactorTemplate]
  │       └─▶ 4 类 × ≥3 模板 + dataclass 校验
  │
  ├─▶ factor_mining.expression.enumerate_factors(templates, param_space)
  │       ├─▶ 遍历 (template, params) 组合
  │       ├─▶ 非法组合 → invalid_combinations.json + 跳过
  │       └─▶ ≥200 个 FactorSpec
  │
  ├─▶ factor_mining.evaluation.evaluate_factor(spec, factors_df, labels_df, dates)
  │       ├─▶ 复用 v0.1.0 evaluation.ic.ic_pearson / ic_spearman / compute_layered_returns
  │       └─▶ list[FactorEvaluation]
  │
  ├─▶ factor_mining.selection.select_factors(evaluations, specs, top_k=30, corr_threshold=0.9)
  │       ├─▶ ICIR 降序排序
  │       ├─▶ Pearson 相关矩阵 |corr|>0.9 视为冗余
  │       └─▶ (selected_specs, SelectionDiagnostics)
  │
  ├─▶ factor_mining.registry.save_factor_registry(...)
  │       ├─▶ factor_registry/factors.yaml (≥200)
  │       └─▶ factor_registry/selected_factors.json
  │
  ├─▶ factor_mining.viz.render_correlation_heatmap(...)
  │       └─▶ reports/factor_mining_<ts>/figures/correlation_heatmap.png
  │
  └─▶ factor_mining.viz.render_evaluation_report(...)
          ├─▶ reports/factor_mining_<ts>/evaluation_report.html
          ├─▶ reports/factor_mining_<ts>/evaluation_report.md
          └─▶ reports/factor_mining_<ts>/figures/top_layer_cumret.png
```

### 6.2. 调度器触发流水线（cron 触发示例）

```
trader-off scheduler start --config configs/scheduler.yaml
  │
  ├─▶ config.load(yaml) ──▶ SchedulerConfig（pydantic 校验）
  │
  ├─▶ 构造 ports:
  │       ClockPort       = lambda: datetime.now(timezone.utc) （默认；测试可注入虚拟时钟 T-1）
  │       TrainerPort     = DefaultTrainerPort(training.trainer, training.model_io)
  │       ModelRegistryPort = ModelRegistry(models_dir, keep_latest_n, ...)
  │       DriftDetectorPort  = DriftDetector(psi_threshold=0.2, ks_pvalue_threshold=0.05)
  │       PerfMonitorPort    = PerfMonitor(ic_floor=0.005, ic_drop_ratio=0.3)
  │
  ├─▶ RetrainScheduler.start() ──▶ 启动 async tick loop（默认 tick=1s）
  │
  │   每 tick:
  │     ├─▶ cron 检查:
  │     │     for cron_expr in [full_retrain, incremental_retrain]:
  │     │       next = next_cron_fire(cron_expr, base=clock.now())  ← 纯函数（T-3）
  │     │       if clock.now() >= next and is_trading_day(clock.now()):
  │     │         if mode == "full" and (today - last_full) >= full_retrain_frequency_days:
  │     │           enqueue(TriggerReason.CRON_FULL, "full")
  │     │         elif mode == "incremental":
  │     │           enqueue(TriggerReason.CRON_INCREMENTAL, "incremental")
  │     │
  │     ├─▶ drift 检查（如 drift_check_cron 命中）:
  │     │     decision = DriftDetector.evaluate(baseline, current)
  │     │     if decision.should_retrain:
  │     │       enqueue(TriggerReason.DRIFT, decision.suggested_mode)
  │     │     reports/drift_<date>/{drift_report.json, drift_summary.csv}
  │     │
  │     └─▶ perf 检查（每日 16:30）:
  │           decision = PerfMonitor.trigger_perf_degradation()
  │           if decision.should_retrain:
  │             enqueue(TriggerReason.PERF_DEGRADATION, decision.suggested_mode)
  │
  │   任务执行（asyncio.Lock 串行）:
  │     ├─▶ build task_id = "T-<ts>-<uuid8>"
  │     ├─▶ state.append(last_tasks.json, atomic write)
  │     ├─▶ trainer.train(mode=full|incremental, parent_version, features=selected_factors or 15 default)
  │     │     └─▶ DefaultTrainerPort.train → trader_off.training.trainer.train_model + refit
  │     ├─▶ trainer.save(version=v{major}.{minor}.{build}[.incr{N}], metadata=...)
  │     │     └─▶ models/v0.X.Y.<build>/ + registry.json append
  │     ├─▶ if metadata.test_ic_mean >= ic_floor:
  │     │     deploy.deploy_model(version) ──▶ registry.current_version = new
  │     ├─▶ state.append(last_tasks.json, status=success|failed)
  │     └─▶ gc_registry() ──▶ 按 keep_latest_n/pinned/full_only 清理
  │
  └─▶ stop() ──▶ 等待当前任务完成，退出 loop
```

### 6.3. 组合优化流水线

```
trader-off optimize --predictions predictions_<date>.csv --industry-map configs/industry_map.csv --output reports/portfolio_<ts>/
  │
  ├─▶ config.load(yaml) ──▶ OptimizerConstraints（pydantic 校验）
  │
  ├─▶ portfolio.expected_returns.build_expected_returns(predictions, mode="raw|zscore")
  │       └─▶ dict[asset, mu] + 与协方差资产集合一致性校验（AssetMismatchError）
  │
  ├─▶ portfolio.covariance.estimate_covariance(returns_df, method="ledoit_wolf")
  │       ├─▶ sklearn.covariance.LedoitWolf → Σ
  │       ├─▶ 剔除全 NaN 资产 → assets_dropped.json
  │       └─▶ <30 日 → InsufficientDataError
  │
  ├─▶ portfolio.industry.load_industry_map(path)
  │       ├─▶ 重复 asset → IndustryMapConflictError
  │       ├─▶ 缺失 industry → assets_without_industry.json + 虚拟"未分类"行业
  │       └─▶ dict[asset, industry]
  │
  ├─▶ portfolio.solver.solve_max_sharpe(mu, Σ, constraints, backend="auto|cvxpy|scipy")
  │       ├─▶ 构造 cvxpy.Problem：Maximize(mu^T w) s.t. (w^T Σ w) <= 1, Σw=1, w>=0, w<=max_w, 行业中性
  │       │     或 fallback scipy.optimize.minimize(method="SLSQP") with same constraints
  │       └─▶ SolverResult(weights, solver_status, solve_time_sec, iterations, dual_vars)
  │
  ├─▶ portfolio.check.check_constraints(weights, mu, Σ, constraints)
  │       └─▶ ConstraintReport(violations=[])
  │
  ├─▶ portfolio.baseline.compare_to_baseline(weights_opt, mu, Σ, w_eq)
  │       └─▶ ComparisonReport(optimized={...}, equal_weight={...}, deltas)
  │
  └─▶ portfolio.persistence.write_portfolio_outputs(out_dir, ...)
          ├─▶ 写入临时目录 tmp/
          ├─▶ 5 产物：weights.csv, optimizer_report.json, portfolio_metrics.csv, weights_diagnostics.json, assets_dropped.json
          └─▶ atomic rename tmp/ → reports/portfolio_<ts>/
```

### 6.4. OptimizedTopKStrategy 策略生命周期

```
BacktestRunner.run(strategy=OptimizedTopKStrategy(broker, config), broker, data_loader, start, end)
  │
  ├─▶ await strategy.init():
  │       ├─▶ load weights.csv from reports/portfolio_latest/
  │       ├─▶ if 缺失 → WARNING + fallback import LGBMTop20Strategy
  │       ├─▶ if 陈旧 (>5d) → WARNING + fallback
  │       └─▶ self.weights = {asset: weight}, self.top_k = config["top_k"]
  │
  ├─▶ for each trading_day:
  │       await strategy.on_day_open(tm):
  │         ├─▶ target_assets = set(weights.keys())
  │         ├─▶ current_assets = set(broker.current_holdings)
  │         ├─▶ for asset in target_assets:
  │         │     broker.trade_target_pct(asset, weights[asset], extra={reason, weight, version})
  │         └─▶ for asset in current_assets - target_assets:
  │               broker.trade_target_pct(asset, 0, extra={reason, weight: 0, version})
  │
  └─▶ await strategy.on_stop():
          └─▶ 释放 self.weights, self.model_version 引用
```

---

## 7. 错误处理

### 7.1. 自定义异常体系（新增部分）

继承 v0.1.0 异常 + v0.2.0 新增：

| 异常                              | 触发场景                                  | 对应 FR/NFR    | 测试 AC                |
| --------------------------------- | ----------------------------------------- | -------------- | ---------------------- |
| `FactorRegistrySchemaError`       | factors.yaml 缺必填字段                   | FR-0600        | AC-FR0600-04           |
| `DriftDecisionError`              | DriftDetector 配置非法                    | FR-2600        | （内部防护）            |
| `TrainerPortError`                | TrainerPort 包装 trainer 异常             | FR-1500        | （内部防护）            |
| `ClockPortError`                  | ClockPort 实现错误                         | FR-1500        | （内部防护）            |
| `OptimizerError`                  | 优化器总入口异常基类                       | FR-3700        | （内部防护）            |
| `AssetMismatchError`              | mu 与 Σ 资产集合不一致                     | FR-3100        | AC-FR3100-03           |
| `IndustryMapConflictError`        | 行业映射 CSV 含重复 asset                  | FR-3200        | AC-FR3200-03           |
| `InsufficientDataError`（继承）   | nav < 30 / 协方差 < 30 日                  | FR-1200/FR-3000 | AC-FR3000-04           |
| `ConfigValidationError`（继承）   | CLI / yaml pydantic 校验失败               | NFR-0700       | AC-FR2700-03/04 等     |
| `PathTraversalError`（继承）      | 文件 IO 路径逃逸                          | NFR-0700       | AC-NFR0700-02          |

### 7.2. 错误传播策略

- **可恢复**（数据缺失、停牌、IC 异常、漂移告警、GARCH fallback）：记 WARNING 日志 + 继续处理
- **不可恢复**（schema 不匹配、路径越界、协方差奇异、求解 infeasible、版本冲突）：抛对应异常 + CLI 退出码非 0 + stderr 输出错误
- **Solver infeasible**（FR-3300 AC-2 / FR-3500 AC-3）：不抛异常，返回 `SolverResult(weights=None, solver_status="infeasible")`，写入 `optimizer_report.json["solver_status"]`

---

## 8. 配置与可重现性

### 8.1. 配置优先级（NFR-0800）

```
CLI 参数  >  --config <yaml>  >  默认值
```

`utils.config.load_config(cli_args, yaml_path)` 合并三层。三个 v0.2.0 新增 CLI 各自 `--config`：
- `trader-off mine-factors --config configs/factor_mining.yaml`
- `trader-off scheduler start --config configs/scheduler.yaml`
- `trader-off optimize --config configs/optimizer.yaml`
- `trader-off retrain trigger` 使用 scheduler 配置（无需独立 config）

### 8.2. 随机性控制（NFR-0800 继承）

- lightGBM：`random_state=42, feature_fraction_seed=42, bagging_seed=42`
- 因子挖掘：无随机性（参数化枚举是确定性的）
- 漂移 PSI/KS：无随机性（分箱 + scipy）
- 优化 cvxpy/scipy：固定求解器种子
- fixture 生成：`seed=42`（test-plan §2.4）

### 8.3. 落盘 metadata.json 可重现性字段（v0.2.0 新增）

在 v0.1.0 字段基础上，新增 `optimizer_report.json` / `metadata.json` 必含字段：
- `git_commit_sha`（7-40 位 hex）
- `python_version`
- `package_versions`（含 cvxpy / apscheduler / croniter / aiohttp / pyarrow / psutil）
- `random_state`（=42）
- `config_snapshot`（本次运行 yaml 完整内容）

### 8.4. fixture 版本化（NFR-0800 AC-3）

- 路径：`tests/fixtures/v0.2.0/`
- `MANIFEST.json` 含每个文件 SHA256 + 生成参数 + 时间
- 测试运行时自动校验；失配 → 测试失败（fixture 损坏信号）

---

## 9. 跨模块接口摘要（Shield 集成测试依据）

> 完整列表见 `interfaces.md §6`；下表为高优先级跨模块契约（≥2 模块）。

| #  | 接口契约                                    | 跨模块链路                                                       | 覆盖 AC                                                       |
| -- | ------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------- |
| 1  | `enumerate_factors` + `evaluate_factor`     | factor_mining ← evaluation.ic (v0.1.0)                            | AC-FR0300-05                                                  |
| 2  | `select_factors` 输出 `selected_factors.json` | factor_mining → training（--factor-registry）                    | AC-FR0900-01/02/03                                            |
| 3  | `compute_factor_score`                      | factor_mining.score → portfolio.expected_returns (备选路径)        | AC-FR3100（备选路径）                                          |
| 4  | `RetrainScheduler` (含 ClockPort/TrainerPort) | scheduler.core ← ports ← training/data                            | AC-FR1500-01/02/03, AC-NFR0900-01                              |
| 5  | `next_cron_fire`                            | scheduler.cron → scheduler.core（T-3 纯函数）                       | AC-FR1600-04                                                  |
| 6  | `DriftDetector.evaluate → DriftDecision`     | scheduler.drift.detector → scheduler.core                          | AC-FR2600-01/02/03                                            |
| 7  | `PerfMonitor.trigger_perf_degradation`      | scheduler.perf_monitor → scheduler.core                            | AC-FR1900-01/02/03/04（Round-2 IC-only 锁定）                  |
| 8  | `ModelRegistry.gc / rollback_to`            | scheduler.registry → training.model_io                             | AC-FR2300-01/02/03/04                                         |
| 9  | `deploy.deploy_model + watch_registry`      | scheduler.deploy → prediction.service (lazy/hot-reload)           | AC-FR2400-01/02/03/04                                         |
| 10 | `scheduler.api.create_app`（aiohttp）        | scheduler.api → scheduler.core                                    | AC-FR2000-03/04 + AC-NFR0700-04                               |
| 11 | `last_tasks.json` 持久化 + 恢复              | scheduler.state → scheduler.core                                   | AC-FR2500-01/02/03/04, AC-NFR0900-02/03                       |
| 12 | `solve_max_sharpe` (cvxpy → scipy)           | portfolio.solver → portfolio.constraints + utils                   | AC-FR3700-01/02/03/04                                          |
| 13 | `build_expected_returns` ← predictions       | portfolio.expected_returns → prediction.service                    | AC-FR3100-01/02/03                                            |
| 14 | `estimate_covariance` (LW/sample)            | portfolio.covariance → sklearn + utils                             | AC-FR3000-01/02/03/04                                          |
| 15 | `OptimizedTopKStrategy` 完整生命周期          | strategies.optimized_topk → portfolio (weights.csv) + backtest + strategies.lgbm_top20 (fallback) | AC-FR4200-01/02/03/04/05                                       |
| 16 | `check_constraints` + `compare_to_baseline`  | portfolio.check / portfolio.baseline → portfolio.persistence       | AC-FR3800-01/02/03, AC-FR3900-01/02/03                        |
| 17 | `write_portfolio_outputs` 原子落盘            | portfolio.persistence → reports/portfolio_<ts>/                   | AC-FR4000-01/02/03                                             |
| 18 | `train --factor-registry` 接入               | cli.train → training.trainer → factor_mining.registry              | AC-FR0900-01/02/03, AC-NFR1000-01/02/03                       |
| 19 | `mine-factors` CLI                           | cli.mine_factors → factor_mining 全链路                            | AC-FR0800-01/02/03/04/05                                       |
| 20 | `scheduler start|status` CLI                  | cli.scheduler → scheduler.core + config                            | AC-FR2700-01/02/03/04                                          |
| 21 | `retrain trigger|status|cancel` CLI           | cli.retrain → scheduler.api + scheduler.core                       | AC-FR2000-01/02                                               |
| 22 | `optimize` CLI                                | cli.optimize → portfolio 全链路                                    | AC-FR4100-01/02/03/04                                          |
| 23 | `deploy` CLI                                  | cli.deploy → scheduler.deploy                                      | AC-FR2400（CLI 入口）                                           |

---

## 10. FR / NFR → 模块映射

| FR/NFR    | 主实现模块                                                  | 关键接口（详见 interfaces.md）                                |
| --------- | ----------------------------------------------------------- | ------------------------------------------------------------- |
| FR-0100   | factor_mining.templates                                     | `list_templates`, `FactorTemplate`, `IntRangeParam`            |
| FR-0200   | factor_mining.expression                                    | `enumerate_factors`, `FactorSpec`                              |
| FR-0300   | factor_mining.evaluation                                    | `evaluate_factor`, `FactorEvaluation`                          |
| FR-0400   | factor_mining.selection                                     | `select_factors`, `SelectionDiagnostics`                       |
| FR-0500   | factor_mining.viz                                           | `render_correlation_heatmap`                                  |
| FR-0600   | factor_mining.registry                                      | `save_factor_registry`, `load_factor_registry`                |
| FR-0700   | factor_mining.viz                                           | `render_evaluation_report`                                    |
| FR-0800   | factor_mining.cli                                           | `mine-factors` CLI                                            |
| FR-0900   | training.trainer + cli.train                                | `train --factor-registry`, `metadata.json` 新增字段            |
| FR-1500   | scheduler.core + scheduler.ports                            | `RetrainScheduler`, `ClockPort`, `TrainerPort`, `ModelRegistryPort` |
| FR-1600   | scheduler.cron                                              | `next_cron_fire`, `SchedulerConfig.cron`                      |
| FR-1700   | scheduler.drift.psi                                         | `compute_psi`, `compute_feature_psi`                          |
| FR-1800   | scheduler.drift.ks                                          | `compute_ks_pvalue`, `compute_feature_ks`                     |
| FR-1900   | scheduler.perf_monitor                                      | `PerfMonitor`, `trigger_perf_degradation`, `TriggerDecision`  |
| FR-2000   | scheduler.api + scheduler.cli                               | `create_app`, `retrain trigger|status|cancel` CLI + REST       |
| FR-2100   | scheduler.core → TrainerPort → training.trainer              | `TrainerPort.train(mode="full")`, `models/registry.json`        |
| FR-2200   | scheduler.core → TrainerPort → training.trainer (refit)     | `TrainerPort.train(mode="incremental", parent_version=...)`    |
| FR-2300   | scheduler.registry                                          | `ModelRegistry`, `rollback_to`                                |
| FR-2400   | scheduler.deploy                                            | `deploy_model`, `watch_registry`, `deploy.log`                |
| FR-2500   | scheduler.state + scheduler.core                            | `last_tasks.json`, `cron_fire_log.jsonl`, `drift_history.parquet` |
| FR-2600   | scheduler.drift.detector                                    | `DriftDetector.evaluate`, `DriftDecision`                     |
| FR-2700   | scheduler.cli                                               | `scheduler start|stop|status|list-tasks` CLI                   |
| FR-3000   | portfolio.covariance                                        | `estimate_covariance`                                         |
| FR-3100   | portfolio.expected_returns                                  | `build_expected_returns`                                      |
| FR-3200   | portfolio.industry                                          | `load_industry_map`                                           |
| FR-3300   | portfolio.constraints                                       | `OptimizerConstraints.sum_to_one`                             |
| FR-3400   | portfolio.constraints                                       | `OptimizerConstraints.long_only`                              |
| FR-3500   | portfolio.constraints                                       | `OptimizerConstraints.industry_neutral_tol`                   |
| FR-3600   | portfolio.constraints                                       | `OptimizerConstraints.max_weight`                             |
| FR-3700   | portfolio.solver                                            | `solve_max_sharpe(backend="auto|cvxpy|scipy")`                 |
| FR-3800   | portfolio.check                                             | `check_constraints`, `ConstraintReport`                       |
| FR-3900   | portfolio.baseline                                          | `compare_to_baseline`, `ComparisonReport`                     |
| FR-4000   | portfolio.persistence                                       | `write_portfolio_outputs`（atomic rename）                      |
| FR-4100   | portfolio.cli                                               | `optimize` CLI                                                |
| FR-4200   | strategies.optimized_topk                                   | `OptimizedTopKStrategy` + fallback `LGBMTop20Strategy`         |
| NFR-0100  | （测试/CI）                                                 | `tests/perf/test_perf_budgets.py`                             |
| NFR-0200  | （CI 门禁）                                                 | `pytest --cov` TOTAL ≥97%                                     |
| NFR-0300  | （CI 门禁）                                                 | `mutmut run` on 3 modules ≥80%                                |
| NFR-0400  | （文档）                                                    | `docs/adr/0001-optimizer-cvxpy-scipy.md` 等 3 个 ADR            |
| NFR-0500  | utils.logging + pyproject.toml                              | `async/await`, line length ≤100, `uv` 包管理                  |
| NFR-0600  | utils.logging                                               | loguru 格式, `logs/<module>_*.log`                            |
| NFR-0700  | utils.security + utils.config                               | 路径校验, joblib 白名单, `bandit -ll`, NFR-0700 AC-4 localhost  |
| NFR-0800  | utils.config + metadata.json                                | `random_state=42`, metadata 5 字段, fixture MANIFEST.json       |
| NFR-0900  | scheduler.core + scheduler.state                            | max_concurrent=1, asyncio.Lock, atomic write, 恢复策略         |
| NFR-1000  | training.model_io (load_model) + cli.train + strategies     | 双版本格式识别, v0.1.0 模型加载, v0.1.0 CLI 不变, LGBMTop20 保留 |

---

## 11. ADR 候选清单（NFR-0400）

| #   | 标题                                            | 关联 FR/NFR    | 状态      |
| --- | ----------------------------------------------- | -------------- | --------- |
| 1   | 优化器求解库选型（cvxpy + scipy fallback）       | FR-3700        | Accepted  |
| 2   | 调度器持久化方案（文件 JSONL + parquet）         | FR-2500        | Accepted  |
| 3   | 因子表达式 DSL 选型（参数化模板）                | FR-0100/0200   | Accepted  |
| 4   | 虚拟时钟注入 vs 真实时钟                         | FR-1500/T-1    | Accepted（Stage 2 新增）|
| 5   | 模型版本双格式共存                                | NFR-1000       | Accepted（Stage 2 新增）|

---

## 12. 实施里程碑（Devon 视角）

> 不属于架构本身，但帮助 Devon 理解 M-ARCH 后的落地顺序。

1. **基础脚手架**：`pyproject.toml` 依赖追加（§3.5）+ `utils/exceptions.py` 新增异常 + `tests/fixtures/v0.2.0/` fixture 生成脚本
2. **模块 A**：`factor_mining.templates` → `expression` → `evaluation` → `selection` → `viz` → `registry` → `cli`
3. **模块 C**：`portfolio.covariance` → `expected_returns` → `industry` → `constraints` → `solver`（cvxpy + scipy fallback）→ `check` → `baseline` → `persistence` → `cli`
4. **模块 B**：`scheduler.cron`（T-3 先做）→ `scheduler.ports`（T-1/T-2）→ `scheduler.drift.{psi,ks,detector}` → `scheduler.perf_monitor` → `scheduler.state` → `scheduler.registry` → `scheduler.deploy` → `scheduler.core` → `scheduler.api` → `scheduler.cli`
5. **策略层**：`strategies.optimized_topk`（含 fallback LGBMTop20Strategy）
6. **CLI 注册**：`cli/__init__.py` main() 分发 + 5 个新子命令
7. **v0.1.0 兼容补丁**：`training/model_io.load_model` 双格式识别（无需新增函数）
8. **ADR 与文档**：`docs/adr/0001-0005.md` + 文档同步检查脚本 `scripts/check_docs_sync.py`
