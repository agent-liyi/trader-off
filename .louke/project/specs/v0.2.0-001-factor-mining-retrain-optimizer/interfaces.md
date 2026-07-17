# Interfaces — trader-off v0.2.0 — 因子挖掘·再训练调度·组合优化器 — 契约文档

- **Spec ID**: v0.2.0-001-factor-mining-retrain-optimizer
- **Created**: 2026-07-17
- **Related spec**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/spec.md`
- **Related acceptance**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/acceptance.md`
- **Related test-plan**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/test-plan.md`
- **Related architecture**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/architecture.md`
- **继承基线**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/interfaces.md`（v0.1.0 数据 schema / CLI / API 全部保留；本文仅定义 v0.2.0 新增与变更部分）

> 本文是 Devon 写测试、Shield 写断言的**唯一契约来源**。仅定义外部可观察契约（数据 schema、函数签名、CLI、文件格式、日志、异常），不含内部实现细节。
>
> **`modules` 列约定**：每条接口标注实现/消费模块。标注 ≥2 个模块的为**跨模块接口**，Shield 必须为其编写集成测试（test-plan §5.2 + §8.2）。
>
> **M-ARCH 来源依据**：本文档基于 spec.md（已 lock）+ acceptance.md（159 条 AC）+ test-plan.md（159/159 覆盖）+ architecture.md（模块边界）。`# TODO` 无残留；所有 AC 已有对应出口。

## Scope

### In scope（外部可观察契约）

- **Data Schema**（§1）：v0.2.0 新增 dataclass / DataFrame / 业务枚举
- **持久化文件 Schema**（§2）：v0.2.0 新增 7 类落盘文件
- **公共 API 函数签名**（§3）：v0.2.0 新增 4 类接口（factor_mining / scheduler / drift-perf-registry-deploy / portfolio + T-1~T-4）
- **CLI 接口**（§4）：v0.2.0 新增 5 个子命令 + v0.1.0 保留 4 个
- **REST API**（§5.4）：scheduler 触发/状态查询
- **外部框架继承/注入契约**（§5）：TrainerPort / ClockPort / BaseStrategy / Broker
- **异常接口**（§7）：v0.2.0 新增异常

### Out of scope（不属于本接口契约）

- 内部实现细节（类层级、状态机、缓存策略、数据库选择）
- cvxpy / scipy 求解器内部迭代
- APScheduler JobStore / croniter 内部解析（仅 `next_cron_fire` 是契约）
- lightGBM 内部 Booster 树结构
- millionaire 框架内部撮合/调度状态机
- 中间 DataFrame 内部结构
- `asyncio.Lock` / FIFO 队列实现细节（仅通过 `trigger_now` / `get_status` / `last_tasks.json` 观察）

---

## 1. 数据 Schema

### 1.1. FactorTemplate dataclass（FR-0100）

```python
@dataclass(frozen=True)
class FactorTemplate:
    name: str                  # 模板名，如 "momentum_N"
    category: Literal["momentum", "volatility", "volume", "fundamental"]
    fields: list[str]          # 公式中引用的字段，如 ["close", "open", "high", "low", "volume"]
    params: dict[str, Param]   # 参数空间，Param 为 IntRangeParam | ChoiceParam | BoolParam
    formula: str               # 人类可读的公式字符串，如 "close[t]/close[t-N]-1"
```

| 字段        | dtype / 类型                            | 说明                              |
| ----------- | --------------------------------------- | --------------------------------- |
| `name`      | `str`                                   | 模板名（唯一）                     |
| `category`  | `Literal["momentum","volatility","volume","fundamental"]` | 4 类枚举                    |
| `fields`    | `list[str]`                             | OHLCV/fundamental 列名             |
| `params`    | `dict[str, Param]`                       | 参数定义（IntRange/Choice/Bool）   |
| `formula`   | `str`                                   | 公式模板（含占位符）              |

- **modules**: `factor_mining.templates`（实现）→ `factor_mining.expression`, `factor_mining.cli`（消费）
- 关联 AC：`AC-FR0100-01`, `AC-FR0100-02`

### 1.2. Param 类族（FR-0100/0200）

```python
@dataclass(frozen=True)
class IntRangeParam:
    name: str
    min: int
    max: int
    step: int = 1
    def expanded(self) -> list[int]: ...   # 纯函数，输出 [min, min+step, ..., max]

@dataclass(frozen=True)
class ChoiceParam:
    name: str
    choices: list[str | int | float]

@dataclass(frozen=True)
class BoolParam:
    name: str
    def expanded(self) -> list[bool]: ...   # [False, True]
```

- **modules**: `factor_mining.templates`（实现）→ `factor_mining.expression`（消费）
- 关联 AC：`AC-FR0100-02`, `AC-FR0200-01`

### 1.3. FactorSpec dataclass（FR-0200）

```python
@dataclass(frozen=True)
class FactorSpec:
    id: str                                   # 唯一 id，如 "momentum_N_5"
    template_name: str                        # 模板名
    category: Literal["momentum", "volatility", "volume", "fundamental"]
    formula: str                              # 完整公式（参数已展开）
    compute_fn: Callable[[pl.DataFrame], pl.Series]  # 输入 OHLCV DataFrame，返回 factor Series（按 asset+date 对齐）
    params: dict[str, int | str | float | bool]  # 展开后的参数值
```

| 字段          | dtype / 类型                            | 说明                              |
| ------------- | --------------------------------------- | --------------------------------- |
| `id`          | `str`                                   | 模板名+参数序列化（唯一）          |
| `template_name` | `str`                                 | 模板名                            |
| `category`    | `Literal[...]`                          | 类别                              |
| `formula`     | `str`                                   | 展开后的完整公式                  |
| `compute_fn`  | `Callable[[pl.DataFrame], pl.Series]`   | 可调用，输入 OHLCV 输出 factor   |
| `params`      | `dict[str, ...]`                        | 已展开的参数                     |

- **modules**: `factor_mining.expression`（实现）→ `factor_mining.evaluation`, `factor_mining.selection`, `factor_mining.registry`, `training.trainer`（消费）
- 关联 AC：`AC-FR0200-04`, `AC-FR0900-02`

### 1.4. FactorEvaluation dataclass（FR-0300）

```python
@dataclass(frozen=True)
class FactorEvaluation:
    ic_ts: pl.DataFrame        # 列: date(Date), ic(Float64)
    rank_ic_ts: pl.DataFrame   # 列: date(Date), rank_ic(Float64)
    ic_mean: float
    ic_std: float
    icir: float                # = ic_mean / ic_std; 若 std==0 则 0.0 + WARNING
    rank_ic_mean: float
    rank_ic_std: float
    layered_returns: pl.DataFrame  # 列: layer(Int32, 1..5), mean_return(Float64)，5 行
```

- **modules**: `factor_mining.evaluation`（实现）→ `factor_mining.selection`, `factor_mining.viz`（消费）
- 关联 AC：`AC-FR0300-01/02/03/04/05`

### 1.5. SelectionDiagnostics dataclass（FR-0400）

```python
@dataclass(frozen=True)
class SelectionDiagnostics:
    removed_by_redundancy: list[str]   # 被去冗余移除的因子 id 列表
    final_k: int                       # 最终精选因子数
    top_k_requested: int               # 用户请求的 top_k
```

- **modules**: `factor_mining.selection`（实现）→ `factor_mining.registry`, `factor_mining.cli`（消费）
- 关联 AC：`AC-FR0400-01/02/03/04`

### 1.6. DriftDecision dataclass（FR-2600）

```python
@dataclass(frozen=True)
class DriftDecision:
    should_retrain: bool
    reason: Literal["ok", "light_drift", "moderate_drift", "strong_drift"]
    suggested_mode: Literal["full", "incremental"]
    per_feature_stats: pl.DataFrame  # 列: feature(Utf8), psi(Float64), ks_statistic(Float64), p_value(Float64)
```

- **modules**: `scheduler.drift.detector`（实现）→ `scheduler.core`（消费）
- 关联 AC：`AC-FR2600-01/02/03/04`

### 1.7. TriggerDecision dataclass（FR-1900，Round-2 锁定 IC-only）

```python
@dataclass(frozen=True)
class TriggerDecision:
    should_retrain: bool
    reason: Literal["ok", "ic_below_floor", "ic_drop_ratio_exceeded"]
    suggested_mode: Literal["full", "incremental"]
    computation_time_sec: float      # 应 <1.0（无 Sharpe 子回测开销）
    notes: str                       # 必含 "ic_only"（Round-2 锁定标识）
```

- **modules**: `scheduler.perf_monitor`（实现）→ `scheduler.core`（消费）
- 关联 AC：`AC-FR1900-01/02/03/04`
- **Round-2 锁定**：`TriggerDecision` **不包含** `sharpe` 字段；`notes` 字段必含 `"ic_only"`；测试断言 `not hasattr(decision, "sharpe") and "ic_only" in decision.notes`（AC-FR1900-04）

### 1.8. SchedulerConfig dataclass（FR-1500/2700）

```python
@dataclass
class SchedulerConfig:
    # 调度器
    tick_interval_sec: float = 1.0
    max_concurrent_tasks: int = 1
    trading_calendar: Literal["data_loader", "exchange_calendar"] = "data_loader"
    # 虚拟时钟注入（T-1）
    clock: ClockPort = field(default_factory=lambda: SystemClockPort())

    # Cron（FR-1600）
    full_retrain_cron: str = "0 16 * * 1-5"
    incremental_retrain_cron: str = "0 16 * * 1-5"
    full_retrain_frequency_days: int = 5
    drift_check_cron: str = "0 9 * * 1-5"

    # 漂移阈值（FR-2600）
    psi_threshold: float = 0.2
    ks_pvalue_threshold: float = 0.05
    psi_strong: float = 0.5
    min_drift_features_incremental: int = 5
    min_drift_features_full: int = 3

    # 性能衰减阈值（FR-1900）
    ic_floor: float = 0.005
    ic_drop_ratio: float = 0.3
    ic_window: int = 20

    # 保留策略（FR-2300）
    keep_latest_n: int = 10
    keep_pinned_versions: list[str] = field(default_factory=list)
    keep_full_retrain_only: bool = True

    # 部署（FR-2400）
    model_load_mode: Literal["lazy", "hot-reload"] = "lazy"

    # API（FR-2000）
    run_api: bool = False
    api_host: str = "127.0.0.1"   # 默认 localhost（NFR-0700 AC-4 强制）
    api_port: int = 8765

    # 持久化（T-4：可配置落盘根目录）
    state_dir: Path = Path("scheduler_state")
    models_dir: Path = Path("models")
    reports_dir: Path = Path("reports")
```

- **modules**: `scheduler.core`（实现）→ `scheduler.cli`, `tests/integration`（消费）
- 关联 AC：`AC-FR1500-01`, `AC-FR2700-01/02/03/04`, `AC-FR1900-02`（ic_floor）, `AC-FR2300-01`（keep_latest_n）

### 1.9. SchedulerStatus dataclass（FR-1500）

```python
@dataclass(frozen=True)
class SchedulerStatus:
    running: bool
    next_trigger_time: datetime | None  # 下一次 cron 触发时间（含 mode）
    next_trigger_mode: Literal["full", "incremental"] | None
    active_tasks: int                  # 当前活跃任务数（应 ≤ max_concurrent_tasks）
    pending_tasks: int                 # FIFO 队列中等待任务数
    last_full_retrain_date: date | None
    last_incremental_retrain_date: date | None
```

- **modules**: `scheduler.core`（实现）→ `scheduler.cli`, `scheduler.api`（消费）
- 关联 AC：`AC-FR1500-01`（get_status）

### 1.10. RetrainTask dataclass（FR-1500/2500）

```python
@dataclass
class RetrainTask:
    task_id: str                       # "T-<ts>-<uuid8>"
    mode: Literal["full", "incremental"]
    reason: TriggerReason              # TriggerReason 枚举
    parent_version: str | None         # 增量时为父版本号
    status: Literal["pending", "running", "success", "failed"]
    start_time: datetime | None
    end_time: datetime | None
    error: str | None
    new_version: str | None            # 完成后填入
    metrics: dict | None               # {"test_ic_mean": ..., "test_rank_ic_mean": ...}

class TriggerReason(str, Enum):
    CRON_FULL = "cron_full"
    CRON_INCREMENTAL = "cron_incremental"
    DRIFT = "drift"
    PERF_DEGRADATION = "perf_degradation"
    MANUAL = "manual"
```

- **modules**: `scheduler.core`（实现）→ `scheduler.api`, `scheduler.state`, `scheduler.cli`（消费）
- 关联 AC：`AC-FR1500-01/02`, `AC-FR2000-01/02`, `AC-FR2500-01/04`, `AC-NFR0900-01`

### 1.11. ModelRegistryEntry（FR-2300，registry.json 内元素）

```python
@dataclass(frozen=True)
class ModelRegistryEntry:
    version: str                       # "v{major}.{minor}.{build}[.incr{N}]"
    created_at: datetime               # ISO 8601 UTC
    trigger: Literal["cron_full", "cron_incremental", "drift", "perf_degradation", "manual"]
    mode: Literal["full", "incremental"]
    task_id: str
    git_commit_sha: str                # 7-40 hex
    metrics: dict                      # {"test_ic_mean": ..., "test_rank_ic_mean": ...}
    parent_version: str | None         # 增量时为父版本
    incr_seq: int | None               # 增量编号
    refit_iterations: int | None       # lightGBM Booster.refit 实际轮数
```

- **modules**: `scheduler.registry`（实现）→ `prediction.service`, `cli.train`, `cli.predict`（消费）
- 关联 AC：`AC-FR2100-02`, `AC-FR2200-01/04`, `AC-FR2300-04`, `AC-FR2400-01/02`

### 1.12. OptimizerConstraints dataclass（FR-3300~3600）

```python
@dataclass(frozen=True)
class OptimizerConstraints:
    sum_to_one: bool = True            # Σw=1（FR-3300；内置）
    long_only: bool = True             # w>=0（FR-3400；内置）
    max_weight: float = 0.10           # 单股权重上限（FR-3600；可配）
    industry_neutral: bool = True
    industry_neutral_tol: float = 0.05 # δ（FR-3500；可配）
    industry_benchmark: dict[str, float] | None = None  # {industry: weight}，默认 None → 等权
```

- **modules**: `portfolio.constraints`（实现）→ `portfolio.solver`, `portfolio.check`, `portfolio.cli`（消费）
- 关联 AC：`AC-FR3300-01`, `AC-FR3400-01`, `AC-FR3500-01/02`, `AC-FR3600-01/02`

### 1.13. SolverResult dataclass（FR-3700/3300/3800）

```python
@dataclass(frozen=True)
class SolverResult:
    weights: np.ndarray | None         # 长度 N，None 表示 infeasible
    solver_status: Literal["optimal", "optimal_inaccurate", "infeasible", "unbounded", "solver_error"]
    backend_used: Literal["cvxpy", "scipy"]   # 实际使用的 backend（回退时记录）
    solve_time_sec: float
    iterations: int
    dual_vars: dict | None             # cvxpy 对偶变量；scipy 可能为 None
    diagnostics: dict                  # {"max_iterations": 1000, "tolerance": 1e-6, ...}
```

- **modules**: `portfolio.solver`（实现）→ `portfolio.check`, `portfolio.persistence`, `portfolio.cli`（消费）
- 关联 AC：`AC-FR3700-01/02/03/04`, `AC-FR3300-02`, `AC-FR3500-03`

### 1.14. ConstraintReport dataclass（FR-3800）

```python
@dataclass(frozen=True)
class CheckResult:
    check_name: str
    passed: bool
    actual: float | str
    expected: float | str
    tolerance: float

@dataclass(frozen=True)
class ConstraintViolation:
    type: Literal["sum_constraint", "max_weight", "long_only", "industry_neutral"]
    asset_or_industry: str | None
    expected: float
    actual: float
    severity: Literal["low", "high"]

@dataclass(frozen=True)
class ConstraintReport:
    checks: list[CheckResult]
    violations: list[ConstraintViolation]
```

- **modules**: `portfolio.check`（实现）→ `portfolio.persistence`, `portfolio.cli`（消费）
- 关联 AC：`AC-FR3800-01/02/03`

### 1.15. ComparisonReport dataclass（FR-3900）

```python
@dataclass(frozen=True)
class ComparisonReport:
    optimized: dict[str, float]    # {"expected_return": ..., "volatility": ..., "sharpe": ..., "max_weight": ..., "turnover": ...}
    equal_weight: dict[str, float]
    delta: dict[str, float]        # optimized - equal_weight
```

- **modules**: `portfolio.baseline`（实现）→ `portfolio.persistence`, `portfolio.cli`（消费）
- 关联 AC：`AC-FR3900-01/02/03`

### 1.16. 因子评估输入 DataFrame（FR-0300）

| 列         | dtype    | 说明                       |
| ---------- | -------- | -------------------------- |
| `asset`    | Utf8     | 资产代码                   |
| `date`     | Date     | 交易日                     |
| `value`    | Float64  | 因子值                     |

- **modules**: 用户/测试（构造）→ `factor_mining.evaluation`（消费）

### 1.17. 标签输入 DataFrame（FR-0300，复用 v0.1.0 §1.3）

继承 v0.1.0 `trader_off.interfaces §1.3`：`asset / date / label`（label 为未来 5 日收益率）。

- **modules**: 用户/测试 → `factor_mining.evaluation`
- 关联 AC：`AC-FR0300-01`

### 1.18. 协方差输入 DataFrame（FR-3000，宽表）

| 列                    | dtype    | 说明                       |
| --------------------- | -------- | -------------------------- |
| `date`                | Date     | 交易日                     |
| `<asset_1>`           | Float64  | asset_1 当日收益率         |
| `<asset_2>`           | Float64  | asset_2 当日收益率         |
| ...                   | Float64  | 每个资产一列              |

- **modules**: 用户/测试 → `portfolio.covariance`
- 关联 AC：`AC-FR3000-01/02/03`

### 1.19. 漂移检测输入 DataFrame（FR-1700/1800）

| 列              | dtype    | 说明                       |
| --------------- | -------- | -------------------------- |
| `asset`         | Utf8     | 资产代码                   |
| `date`          | Date     | 交易日                     |
| `<feature_1>`   | Float64  | 特征 1 值                  |
| `<feature_2>`   | Float64  | 特征 2 值                  |
| ...             | Float64  | 每个特征一列              |

- **modules**: 用户/测试 → `scheduler.drift.psi`, `scheduler.drift.ks`
- 关联 AC：`AC-FR1700-03`, `AC-FR1800-02`

### 1.20. 预测输入 DataFrame（FR-3100，复用 v0.1.0 §1.4）

继承 v0.1.0 §1.4：`asset / score / rank`。

- **modules**: 用户/测试（predictions_<date>.csv）→ `portfolio.expected_returns`
- 关联 AC：`AC-FR3100-01/02/03`

### 1.21. 行业映射 CSV（FR-3200）

```
asset,industry
000001.SZ,banking
000002.SZ,real_estate
...
```

- **modules**: 用户/测试（configs/industry_map.csv）→ `portfolio.industry`
- 关联 AC：`AC-FR3200-01/02/03`

---

## 2. 持久化文件 Schema

### 2.1. `factor_registry/factors.yaml`（FR-0600）

```yaml
factor_template_version: "v1"
generated_at: "2026-07-17T10:00:00Z"
total_candidates: 245
factors:
  - id: "momentum_N_5"
    category: "momentum"
    template: "momentum_N"
    params: {N: 5}
    formula: "close[t]/close[t-5]-1"
  - id: "vol_N_10"
    category: "volatility"
    template: "vol_N"
    params: {N: 10}
    formula: "std(daily_returns, 10)"
  # ... 共 total_candidates 条
```

| 字段                       | 类型      | 说明                                       |
| -------------------------- | --------- | ------------------------------------------ |
| `factor_template_version`  | `str`     | 模板库版本（固定 `"v1"`）                   |
| `generated_at`             | `str` (ISO 8601) | 生成时间戳 UTC                       |
| `total_candidates`         | `int`     | 候选因子总数（≥200）                       |
| `factors`                  | `list[dict]` | 因子列表，长度 == total_candidates       |
| `factors[].id`             | `str`     | 唯一 id                                    |
| `factors[].category`       | `str`     | 4 类别枚举                                 |
| `factors[].template`       | `str`     | 模板名                                     |
| `factors[].params`         | `dict`    | 已展开的参数                                |
| `factors[].formula`        | `str`     | 完整公式                                   |

- **modules**: `factor_mining.registry`（实现）→ `cli.train` (--factor-registry), `tests/integration`（消费）
- 关联 AC：`AC-FR0600-01/04`
- `FactorRegistrySchemaError` 触发：`factor_template_version` 字段缺失（AC-FR0600-04）

### 2.2. `factor_registry/selected_factors.json`（FR-0600/0900）

```json
{
  "factor_template_version": "v1",
  "selected_count": 28,
  "selection_diagnostics": {
    "removed_by_redundancy": ["momentum_N_10", "vol_N_10"],
    "final_k": 28,
    "top_k_requested": 30
  },
  "factors": [
    {
      "id": "momentum_N_20",
      "category": "momentum",
      "template": "momentum_N",
      "params": {"N": 20},
      "formula": "close[t]/close[t-20]-1",
      "icir": 0.85,
      "ic_mean": 0.03,
      "ic_std": 0.035,
      "rank_ic_mean": 0.04,
      "rank_ic_std": 0.038,
      "layered_top_minus_bottom": 0.012
    }
  ]
}
```

| 字段                                  | 类型      | 说明                            |
| ------------------------------------- | --------- | ------------------------------- |
| `factor_template_version`             | `str`     | 模板库版本                       |
| `selected_count`                      | `int`     | 精选因子数                       |
| `selection_diagnostics`               | `dict`    | `SelectionDiagnostics` 序列化     |
| `factors[].id`                        | `str`     | 因子 id                          |
| `factors[].category`                  | `str`     | 类别                            |
| `factors[].template`                  | `str`     | 模板名                          |
| `factors[].params`                    | `dict`    | 参数                            |
| `factors[].formula`                   | `str`     | 公式                            |
| `factors[].icir` / `ic_mean` / `ic_std` | `float` | IC 指标                         |
| `factors[].rank_ic_mean` / `rank_ic_std` | `float` | Rank IC 指标                  |
| `factors[].layered_top_minus_bottom`  | `float`   | 5 层 top-bottom 收益差           |

- **modules**: `factor_mining.registry`（实现）→ `cli.train --factor-registry`, `factor_mining.score`, `tests/integration`（消费）
- 关联 AC：`AC-FR0600-02`, `AC-FR0900-01/02`

### 2.3. `models/registry.json`（FR-2100/2200/2300/2400，扩展 v0.1.0）

```json
[
  {
    "version": "v0.2.0.5",
    "created_at": "2026-07-17T16:00:00Z",
    "trigger": "cron_full",
    "mode": "full",
    "task_id": "T-20260717-001",
    "git_commit_sha": "abc1234567",
    "metrics": {"test_ic_mean": 0.025, "test_rank_ic_mean": 0.035},
    "parent_version": null,
    "incr_seq": null,
    "refit_iterations": null
  },
  {
    "version": "v0.2.0.5.incr1",
    "created_at": "2026-07-17T16:00:00Z",
    "trigger": "drift",
    "mode": "incremental",
    "task_id": "T-20260717-002",
    "git_commit_sha": "abc1234567",
    "metrics": {"test_ic_mean": 0.024, "test_rank_ic_mean": 0.034},
    "parent_version": "v0.2.0.5",
    "incr_seq": 1,
    "refit_iterations": 50
  }
]
```

顶级额外字段（与数组并列）：
```json
{
  "current_version": "v0.2.0.5.incr1",
  "pinned_versions": ["v0.2.0.5"],
  "schema_version": 2
}
```

| 字段                                  | 类型      | 说明                                       |
| ------------------------------------- | --------- | ------------------------------------------ |
| `[].version`                          | `str`     | `v{major}.{minor}.{build}[.incr{N}]`        |
| `[].created_at`                       | `str` (ISO 8601 UTC) | 创建时间                            |
| `[].trigger`                          | `str` (枚举) | 触发类型（5 种）                          |
| `[].mode`                             | `str`     | `"full"` / `"incremental"`                   |
| `[].task_id`                          | `str`     | 关联任务 id（唯一）                         |
| `[].git_commit_sha`                   | `str` (7-40 hex) | 可重现性                              |
| `[].metrics`                          | `dict`    | IC 指标                                    |
| `[].parent_version`                   | `str \| null` | 增量时为父版本号                       |
| `[].incr_seq`                         | `int \| null` | 增量编号                              |
| `[].refit_iterations`                 | `int \| null` | lightGBM Booster.refit 实际轮数        |
| 顶级 `current_version`                | `str`     | 当前部署版本（deploy 时更新）                |
| 顶级 `pinned_versions`                | `list[str]` | 钉住保留的版本                            |
| 顶级 `schema_version`                 | `int`     | schema 版本（=2，v0.2.0）                    |

- **modules**: `scheduler.registry`（实现）→ `prediction.service`, `scheduler.deploy`, `cli.train`, `cli.predict`, `tests/integration`（消费）
- 关联 AC：`AC-FR2100-02`, `AC-FR2200-01/04`, `AC-FR2300-04`, `AC-FR2400-01/02/03/04`
- **v0.1.0 兼容**：v0.1.0 的 `models/<YYYYMMDD_HHMMSS>/` 目录结构不受影响；本文档 `load_model(version)` 自动识别两种格式（详见 architecture §5.1）

### 2.4. `models/<version>/metadata.json`（FR-2100/2200，扩展 v0.1.0 §2.2）

继承 v0.1.0 §2.2 全部字段 + v0.2.0 新增：

```json
{
  "train_time": "2026-07-17T16:00:00Z",
  "train_start": "2023-07-17",
  "train_end": "2026-07-17",
  "params": {"objective": "regression", "num_leaves": 63, "learning_rate": 0.05,
             "n_estimators": 500, "random_state": 42, ...},
  "best_iteration": 120,
  "test_ic_mean": 0.025,
  "test_rank_ic_mean": 0.035,
  "git_commit_sha": "abc1234567",
  "python_version": "3.11.5",
  "package_versions": {"lightgbm": "4.3.0", "polars": "1.0.0", "cvxpy": "1.5.x",
                       "scipy": "1.13.x", "apscheduler": "3.10.x"},
  "random_state": 42,
  "config_snapshot": "...",
  "factor_registry_path": "factor_registry/selected_factors.json",
  "factor_template_version": "v1",
  "selected_factor_count": 28,
  "feature_names": ["momentum_N_20", "vol_N_20", ...],
  "parent_version": "v0.2.0.5",
  "incr_seq": 1,
  "refit_iterations": 50
}
```

| 新增字段                       | 类型      | 必含（条件）                              | 关联 AC          |
| ------------------------------ | --------- | ----------------------------------------- | ---------------- |
| `factor_registry_path`         | `str`     | 当使用 `--factor-registry` 时            | AC-FR0900-01     |
| `factor_template_version`      | `str`     | 同上                                       | AC-FR0900-01     |
| `selected_factor_count`        | `int`     | 同上                                       | AC-FR0900-01     |
| `feature_names`                | `list[str]` | 始终含（回退时为 v0.1.0 默认 15 个）     | AC-FR0900-01/03  |
| `parent_version`               | `str \| None` | 增量重训时                              | AC-FR2200-01     |
| `incr_seq`                     | `int \| None` | 增量重训时                              | AC-FR2200-01     |
| `refit_iterations`             | `int \| None` | 增量重训时                              | AC-FR2200-01     |
| `random_state`                 | `int`     | 始终含（=42，NFR-0800）                    | AC-NFR0800-01    |
| `config_snapshot`              | `str`     | 始终含                                     | AC-NFR0800-02    |

- **modules**: `training.model_io`（实现，v0.1.0 模块）→ `prediction.service`, `cli.train`, `tests/integration`（消费）
- 关联 AC：`AC-FR0900-01/02/03`, `AC-FR2100-04`, `AC-FR2200-01/02/03`, `AC-NFR0800-02`

### 2.5. `scheduler_state/` 目录（FR-2500）

| 文件                          | 格式      | 内容                                                   | 写入时机             | AC                |
| ----------------------------- | --------- | ------------------------------------------------------ | -------------------- | ----------------- |
| `last_tasks.json`             | JSON      | 最近 N（默认 100）条 task 列表（`RetrainTask[]`）        | 状态变更 p→r→s/f 即时 | AC-FR2500-01/02/04 |
| `cron_fire_log.jsonl`         | JSONL     | 每行 `{timestamp, mode, triggered: bool, reason}`       | 每次 cron tick       | （观察用）         |
| `drift_history.parquet`       | parquet   | 每日 drift 检测结果长期历史                              | 每次 drift 评估       | （观察用）         |
| `invalid_combinations.json`   | JSON      | 因子枚举时非法参数组合                                    | 枚举时               | AC-FR0200-03      |

`last_tasks.json` 元素结构 = `RetrainTask`（§1.10），原子写入（temp + rename）。

- **modules**: `scheduler.state`（实现）→ `scheduler.core`, `tests/integration/test_scheduler_resilience.py`（消费）
- 关联 AC：`AC-FR2500-01/02/03/04`, `AC-NFR0900-01/02/03`, `AC-FR0200-03`

### 2.6. `reports/drift_<date>/`（FR-2600）

| 文件                  | 格式 | 内容                                                            |
| --------------------- | ---- | --------------------------------------------------------------- |
| `drift_report.json`   | JSON | 完整 per-feature PSI/KS：`[{feature, psi, ks_statistic, p_value, is_drift}, ...]` |
| `drift_summary.csv`   | CSV  | 决策汇总：`should_retrain, suggested_mode, reason, drift_feature_count` |

- **modules**: `scheduler.drift.detector`（实现）→ `tests/unit/scheduler`, `tests/integration`（消费）
- 关联 AC：`AC-FR2600-04`

### 2.7. `reports/portfolio_<ts>/`（FR-4000）

| 文件                          | 格式    | 内容                                                  | 关联 AC          |
| ----------------------------- | ------- | ----------------------------------------------------- | ---------------- |
| `weights.csv`                 | CSV     | 列 `asset, weight, sector, mu, in_universe`           | AC-FR4000-02     |
| `optimizer_report.json`       | JSON    | `ConstraintReport` + `SolverResult` 序列化            | AC-FR3800-03     |
| `portfolio_metrics.csv`       | CSV     | 列 `metric, optimized, equal_weight, delta`           | AC-FR3900-01     |
| `weights_diagnostics.json`    | JSON    | `{solver_status, solve_time_sec, iterations, dual_vars, asset_count, backend_used}` | AC-FR4000-01 |
| `assets_dropped.json`         | JSON    | 被剔除的资产（行业缺失 / 协方差 NaN）                  | AC-FR3000-03     |

- **modules**: `portfolio.persistence`（实现）→ `tests/integration`, `tests/e2e`, `strategies.optimized_topk`（消费）
- 关联 AC：`AC-FR3000-03`, `AC-FR3800-03`, `AC-FR3900-01`, `AC-FR4000-01/02/03`

### 2.8. `reports/factor_mining_<ts>/`（FR-0500/0700）

| 文件                            | 格式    | 内容                                                  | 关联 AC          |
| ------------------------------- | ------- | ----------------------------------------------------- | ---------------- |
| `evaluation_report.html`        | HTML    | 主报告（IC 时序图 + ICIR 表 + 相关性热力图嵌入 + Top-1 累计收益图）| AC-FR0700-01/02  |
| `evaluation_report.md`          | MD      | 精简版（ICIR 表 + 精选因子 ID 列表）                  | AC-FR0700-03     |
| `figures/correlation_heatmap.png` | PNG   | 相关性热力图（figsize=(12,10), dpi=120, RdBu_r）       | AC-FR0500-01/02  |
| `figures/top_layer_cumret.png`   | PNG    | Top-1 层累计收益曲线                                  | AC-FR0700-02     |

- **modules**: `factor_mining.viz`（实现）→ `tests/unit/factor_mining`, `tests/e2e`（消费）
- 关联 AC：`AC-FR0500-01/02/03`, `AC-FR0700-01/02/03/04`

### 2.9. 共享落盘文件（继承 v0.1.0 + 新增）

| 文件                          | 格式 | 触发 FR/NFR | 内容                                          |
| ----------------------------- | ---- | ----------- | --------------------------------------------- |
| `label_stats.json`            | JSON | v0.1.0       | `{mean, std, min, p1, p99, max}`              |
| `limit_up_down_filter.json`   | JSON | v0.1.0       | `[{"asset", "date", "reason"}, ...]`          |
| `dropped_features.json`       | JSON | v0.1.0       | `["feature", ...]`                            |
| `predict_skipped.json`        | JSON | v0.1.0       | `[{"asset", "reason"}, ...]`                  |
| `assets_dropped.json`         | JSON | FR-3000/3200 | 优化器剔除的资产                              |
| `assets_without_industry.json`| JSON | FR-3200      | 缺失行业映射的资产                             |
| `train.log`                   | text | v0.1.0       | 训练日志                                       |
| `logs/factor_mining_*.log`    | text | NFR-0600     | factor_mining 模块日志                        |
| `logs/scheduler_*.log`        | text | NFR-0600     | scheduler 模块日志                            |
| `logs/portfolio_*.log`        | text | NFR-0600     | portfolio 模块日志                            |
| `logs/deploy.log`             | text | FR-2400      | 部署日志：`from=<v>, to=<v>, status=<success|failure>, elapsed=<sec>` |

---

## 3. 公共 API（函数签名）

> `modules` 列：`实现模块 → 消费模块`。≥2 模块 = 跨模块（Shield 集成测试覆盖）。

### 3.1. 因子模板与表达式引擎（FR-0100/0200）

| 函数 / 类                                | 签名                                                                                  | 返回                       | FR       | AC                       | modules                                                        |
| ---------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------- | -------- | ------------------------ | --------------------------------------------------------------- |
| `list_templates`                         | `() -> list[FactorTemplate]`                                                          | ≥12 个模板（4 类 × ≥3）     | FR-0100  | AC-FR0100-01             | factor_mining.templates → expression, cli                      |
| `IntRangeParam.expanded`                 | `(self) -> list[int]`                                                                 | [min..max] 整数列表        | FR-0100  | AC-FR0100-02             | factor_mining.templates → expression                           |
| `ChoiceParam` (dataclass)                | `(name: str, choices: list)`                                                          | (无方法，访问 choices)      | FR-0100  | AC-FR0100-02             | factor_mining.templates → expression                           |
| `BoolParam.expanded`                     | `(self) -> list[bool]`                                                                | `[False, True]`             | FR-0100  | AC-FR0100-02             | factor_mining.templates → expression                           |
| `enumerate_factors`                      | `(templates: list[FactorTemplate], param_space: dict[str, list]) -> list[FactorSpec]` | ≥200 个 FactorSpec         | FR-0200  | AC-FR0200-01/02/03/04    | factor_mining.expression → evaluation, selection, registry, cli |

- 模块路径：`trader_off.factor_mining.templates` / `trader_off.factor_mining.expression`
- `enumerate_factors` 为**纯函数**；非法参数组合 → `invalid_combinations.json` + 跳过，不抛异常
- `compute_fn` 输入：`pl.DataFrame` (OHLCV/fundamental) → 输出 `pl.Series` (按 asset+date 对齐)

### 3.2. 因子评估（FR-0300）

| 函数 / 类                | 签名                                                                                                       | 返回                       | FR       | AC                       | modules                                                  |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- | -------------------------- | -------- | ------------------------ | --------------------------------------------------------- |
| `evaluate_factor`        | `(factor_values: pl.DataFrame, labels: pl.DataFrame, dates: list[date]) -> FactorEvaluation`                | §1.4 FactorEvaluation      | FR-0300  | AC-FR0300-01/02/03/04    | factor_mining.evaluation → selection, viz                 |

- 模块路径：`trader_off.factor_mining.evaluation`
- 复用 v0.1.0 `trader_off.evaluation.ic.ic_pearson / ic_spearman / compute_layered_returns`（AC-FR0300-05）
- 缺失日期（如停牌）跳过该日，不抛异常，记录到 `evaluation_skipped_dates.json`
- `ic_std == 0` → `icir = 0.0` + WARNING `"factor has zero std, icir set to 0"`（AC-FR0300-04）

### 3.3. 因子选择（FR-0400）

| 函数                  | 签名                                                                                                                      | 返回                                          | FR       | AC                       | modules                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | -------- | ------------------------ | -------------------------------------------------------------- |
| `select_factors`      | `(evaluations: list[FactorEvaluation], factor_specs: list[FactorSpec], top_k: int = 30, corr_threshold: float = 0.9) -> tuple[list[FactorSpec], SelectionDiagnostics]` | (selected, diagnostics)                       | FR-0400  | AC-FR0400-01/02/03/04    | factor_mining.selection → registry, cli                       |

- 模块路径：`trader_off.factor_mining.selection`
- 候选 < top_k → 全部保留 + WARNING（AC-FR0400-03）
- ICIR 平局（差值 <1e-9）→ 保留字典序较小者（AC-FR0400-04）

### 3.4. 因子注册表（FR-0600）

| 函数                       | 签名                                                                                  | 返回                       | FR       | AC                       | modules                                                  |
| -------------------------- | ------------------------------------------------------------------------------------- | -------------------------- | -------- | ------------------------ | --------------------------------------------------------- |
| `save_factor_registry`     | `(factors: list[FactorSpec], registry_dir: Path, generated_at: datetime) -> tuple[Path, Path]` | (yaml_path, json_path)     | FR-0600  | AC-FR0600-01/02/03       | factor_mining.registry → cli, training                    |
| `load_factor_registry`     | `(path: Path) -> dict`                                                                 | 注册表 dict                  | FR-0600  | AC-FR0600-04             | factor_mining.registry → cli.train, integration          |
| `save_selected_factors`    | `(selected: list[FactorSpec], evaluations: list[FactorEvaluation], diagnostics: SelectionDiagnostics, registry_dir: Path) -> Path` | selected_factors.json Path | FR-0600  | AC-FR0600-02             | factor_mining.registry → cli, training                    |

- 模块路径：`trader_off.factor_mining.registry`
- `load_factor_registry`：缺 `factor_template_version` → `FactorRegistrySchemaError("missing required field: factor_template_version")`（AC-FR0600-04）
- 路径解析后 `validate_path` 校验（NFR-0700）

### 3.5. 可视化（FR-0500/0700）

| 函数                          | 签名                                                                                                                       | 返回                          | FR       | AC                       | modules                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------- | -------- | ------------------------ | --------------------------------------------------------- |
| `render_correlation_heatmap`  | `(corr_matrix: np.ndarray, labels: list[str], output_path: Path, figsize: tuple = (12, 10), dpi: int = 120) -> Path`       | PNG Path                       | FR-0500  | AC-FR0500-01/02/03       | factor_mining.viz → cli                                   |
| `render_evaluation_report`    | `(evaluations: list[FactorEvaluation], selected: list[FactorSpec], output_dir: Path) -> dict[str, Path]`                    | `{html, md, figures_dir}`     | FR-0700  | AC-FR0700-01/02/03/04    | factor_mining.viz → cli                                   |
| `compute_factor_score`        | `(features_df: pl.DataFrame, weights: dict[str, float], selected_factors_path: Path) -> dict[str, float]`                   | `{asset: score}`              | FR-3100  | AC-FR3100-01（备选路径）  | factor_mining.score → portfolio.expected_returns          |

- 模块路径：`trader_off.factor_mining.viz`, `trader_off.factor_mining.score`
- `matplotlib.use("Agg")` 在 import pyplot 前设置（v0.1.0 沿袭）
- 中文字体 fallback（v0.1.0 NFR-0500）
- `render_evaluation_report` 默认用 `string.Template`，无 jinja2 依赖（AC-FR0700-04）

### 3.6. 调度器端口（T-1 / T-2 / FR-1500）

> **T-1 虚拟时钟**：ClockPort 是 `Protocol`，默认实现包 `datetime.now(timezone.utc)`。
> **T-2 TrainerPort**：协议，默认实现包装 v0.1.0 `training.trainer.train_model` / `training.model_io.save_model`。

```python
class ClockPort(Protocol):
    def now(self) -> datetime:
        """返回 tz-aware UTC datetime。"""
        ...

class SystemClockPort:
    """ClockPort 默认实现：包 datetime.now(timezone.utc)。"""
    def now(self) -> datetime: ...

class VirtualClockPort:
    """测试用：可手动 set_now / advance。"""
    def __init__(self, start: datetime | None = None): ...
    def now(self) -> datetime: ...
    def set_now(self, t: datetime) -> None: ...
    def advance(self, seconds: float) -> None: ...

class TrainerPort(Protocol):
    async def train(self, mode: Literal["full", "incremental"], *, parent_version: str | None = None,
                    factor_registry_path: Path | None = None, train_window_years: int = 3,
                    config_snapshot: dict | None = None) -> ModelArtifact:
        """执行全量或增量训练，返回训练好的 artifact。"""
        ...

    async def save(self, artifact: ModelArtifact, *, mode: Literal["full", "incremental"],
                   trigger: TriggerReason, parent_version: str | None = None,
                   task_id: str, metrics: dict) -> str:
        """保存模型到 models_dir，返回 version 字符串。"""
        ...

class DefaultTrainerPort:
    """TrainerPort 默认实现：包装 v0.1.0 training.trainer + training.model_io。"""
    def __init__(self, models_dir: Path = Path("models")): ...

class ModelRegistryPort(Protocol):
    def gc(self) -> list[str]: ...            # 返回被清理的版本列表
    def rollback_to(self, version: str) -> None: ...
    def list_versions(self) -> list[str]: ...
    def get_entry(self, version: str) -> ModelRegistryEntry | None: ...

class DriftDetectorPort(Protocol):
    def evaluate(self) -> DriftDecision: ...

class PerfMonitorPort(Protocol):
    def trigger_perf_degradation(self) -> TriggerDecision: ...
```

- 模块路径：`trader_off.scheduler.ports`
- 关联 AC：`AC-FR1500-01/02/03/04`（trainer mock 串行）, `AC-FR1600-01/02/03`（cron + clock）, `AC-FR2500-*`, `AC-FR2600-*`, `AC-FR1900-*`
- 关联 testability AC（T-1/T-2/T-3）：见 architecture §4.3 / §4.5 / test-plan §6.7

### 3.7. RetrainScheduler 核心（FR-1500/2500/2600）

| 方法 / 类                                | 签名                                                                                                                       | FR       | AC                       | modules                                                                 |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------ | ------------------------------------------------------------------------ |
| `RetrainScheduler.__init__`              | `(config: SchedulerConfig, model_registry: ModelRegistryPort, drift_detector: DriftDetectorPort, perf_monitor: PerfMonitorPort, trainer: TrainerPort)` | FR-1500  | AC-FR1500-01/04          | scheduler.core → ports                                                    |
| `RetrainScheduler.start`                 | `async def start(self) -> None`                                                                                            | FR-1500  | AC-FR1500-03             | scheduler.core → cron/drift/perf/state/deploy                            |
| `RetrainScheduler.stop`                  | `async def stop(self) -> None`                                                                                              | FR-1500  | AC-FR1500-03             | scheduler.core                                                            |
| `RetrainScheduler.trigger_now`           | `async def trigger_now(self, reason: TriggerReason, mode: Literal["full", "incremental"]) -> RetrainTask`                  | FR-1500/2000 | AC-FR1500-01, AC-FR2000-01 | scheduler.core → trainer + registry                                       |
| `RetrainScheduler.get_status`            | `async def get_status(self) -> SchedulerStatus`                                                                             | FR-1500  | AC-FR1500-01             | scheduler.core                                                            |
| `RetrainScheduler.run_task`              | `async def run_task(self, task: RetrainTask) -> RetrainTask`                                                                 | FR-1500/2500 | AC-FR1500-02, AC-FR2500-* | scheduler.core → trainer, registry, deploy, state                       |

- 模块路径：`trader_off.scheduler.core`
- 全部 4 个公开方法为 `async def`（AC-FR1500-01）
- 同一时刻 ≤1 任务在跑（`asyncio.Lock` + `max_concurrent_tasks`）；FIFO 队列（NFR-0900 AC-1）
- `RetrainScheduler` 不直接 import `quantide.*`（AC-FR1500-04：单测可独立运行）

### 3.8. Cron 解析器（FR-1600，T-3 纯函数）

| 函数              | 签名                                                                          | 返回            | FR       | AC                       | modules                                  |
| ----------------- | ----------------------------------------------------------------------------- | --------------- | -------- | ------------------------ | ----------------------------------------- |
| `next_cron_fire`  | `(expr: str, base: datetime, *, backend: Literal["croniter", "apscheduler"] = "croniter") -> datetime` | 下次触发时间（tz-aware） | FR-1600  | AC-FR1600-04             | scheduler.cron → scheduler.core           |

- 模块路径：`trader_off.scheduler.cron`
- **纯函数**（T-3）：无副作用；不读文件系统；不读环境变量；不调真实时间
- 默认 backend = `"croniter"`；可切 `"apscheduler"`（备选，仅满足 NFR-0500 AC-3 必装依赖的 swap-in 空间）
- AC-FR1600-04 断言：`next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0)) == datetime(2026, 7, 17, 16, 0)`

### 3.9. PSI 漂移检测（FR-1700）

| 函数                  | 签名                                                                                                                    | 返回            | FR       | AC                       | modules                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------- | --------------- | -------- | ------------------------ | ----------------------------------------- |
| `compute_psi`         | `(baseline: np.ndarray, current: np.ndarray, n_bins: int = 10, epsilon: float = 1e-6) -> float`                          | PSI ∈ [0, ∞)    | FR-1700  | AC-FR1700-01/02          | scheduler.drift.psi → detector           |
| `compute_feature_psi` | `(baseline_df: pl.DataFrame, current_df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame`                        | 列 `feature, psi, is_drift` | FR-1700  | AC-FR1700-03/04          | scheduler.drift.psi → detector           |

- 模块路径：`trader_off.scheduler.drift.psi`
- `is_drift = (psi > psi_threshold)`；全 NaN 特征 → `psi=0.0, is_drift=False` + WARNING（AC-FR1700-04）

### 3.10. KS 漂移检测（FR-1800）

| 函数                 | 签名                                                                                                          | 返回                                  | FR       | AC                       | modules                                  |
| -------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------- | -------- | ------------------------ | ----------------------------------------- |
| `compute_ks_pvalue`  | `(baseline: np.ndarray, current: np.ndarray) -> float`                                                          | p-value ∈ [0, 1]                       | FR-1800  | AC-FR1800-01/02          | scheduler.drift.ks → detector            |
| `compute_feature_ks` | `(baseline_df: pl.DataFrame, current_df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame`              | 列 `feature, ks_statistic, p_value, is_drift` | FR-1800  | AC-FR1800-03             | scheduler.drift.ks → detector            |

- 模块路径：`trader_off.scheduler.drift.ks`
- 全 NaN 特征 → `(0.0, 1.0, False)` + WARNING（AC-FR1800-03）

### 3.11. DriftDetector 编排（FR-2600）

| 类 / 方法                          | 签名                                                                                  | FR       | AC                       | modules                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------- | -------- | ------------------------ | ---------------------------------------------- |
| `DriftDetector.__init__`           | `(config: SchedulerConfig, psi_fn: Callable = compute_feature_psi, ks_fn: Callable = compute_feature_ks)` | FR-2600  | AC-FR2600-01             | scheduler.drift.detector → core               |
| `DriftDetector.evaluate`           | `(self) -> DriftDecision`                                                              | FR-2600  | AC-FR2600-01/02/03/04    | scheduler.drift.detector → core, persistence  |

- 模块路径：`trader_off.scheduler.drift.detector`
- 决策规则（AC-FR2600-01/02/03）：
  - 轻度（PSI>0.1 特征数 ∈ [3, 5) 且 KS p<0.05 特征数 < 5）→ `should_retrain=False, reason="light_drift"`
  - 中度（PSI>0.2 特征数 ≥ 1 OR KS p<0.05 特征数 ≥ 5）→ `should_retrain=True, suggested_mode="incremental", reason="moderate_drift"`
  - 重度（PSI>0.5 特征数 ≥ 3）→ `should_retrain=True, suggested_mode="full", reason="strong_drift"`
- 每次 evaluate 输出 `reports/drift_<date>/{drift_report.json, drift_summary.csv}`（AC-FR2600-04）

### 3.12. PerfMonitor 性能衰减（FR-1900，Round-2 IC-only 锁定）

| 类 / 方法                          | 签名                                                                                  | FR       | AC                       | modules                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------- | -------- | ------------------------ | ---------------------------------------------- |
| `PerfMonitor.__init__`             | `(config: SchedulerConfig, ic_history_provider: Callable[[int], list[float]])`         | FR-1900  | AC-FR1900-01             | scheduler.perf_monitor → core                  |
| `trigger_perf_degradation`         | `(self) -> TriggerDecision`                                                            | FR-1900  | AC-FR1900-01/02/03/04    | scheduler.perf_monitor → core                  |

- 模块路径：`trader_off.scheduler.perf_monitor`
- **Round-2 锁定**（AC-FR1900-04）：
  - 仅 IC，**不评估 Sharpe**
  - `TriggerDecision.notes` 必含 `"ic_only"`
  - 不存在 `sharpe` 字段（`hasattr(decision, "sharpe") == False`）
  - `computation_time_sec < 1.0`（无子回测开销）

### 3.13. ModelRegistry 版本管理（FR-2300）

| 类 / 方法                          | 签名                                                                                  | FR       | AC                       | modules                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------- | -------- | ------------------------ | ---------------------------------------------- |
| `ModelRegistry.__init__`           | `(registry_path: Path, models_dir: Path, *, keep_latest_n: int = 10, keep_pinned_versions: list[str] = None, keep_full_retrain_only: bool = True)` | FR-2300  | AC-FR2300-01/02/03/04    | scheduler.registry → core                      |
| `ModelRegistry.append`             | `(entry: ModelRegistryEntry) -> None`                                                  | FR-2300  | AC-FR2300-01             | scheduler.registry → core                      |
| `ModelRegistry.gc`                 | `() -> list[str]`  # 返回被清理的版本                                                  | FR-2300  | AC-FR2300-01/02/03       | scheduler.registry → core                      |
| `ModelRegistry.rollback_to`        | `(version: str) -> None`                                                                | FR-2300  | AC-FR2300-04             | scheduler.registry → core, prediction          |
| `ModelRegistry.list_versions`      | `() -> list[str]`                                                                       | FR-2300  | AC-FR2300-01             | scheduler.registry → core                      |
| `ModelRegistry.get_entry`          | `(version: str) -> ModelRegistryEntry \| None`                                         | FR-2300  | AC-FR2300-01             | scheduler.registry → core                      |

- 模块路径：`trader_off.scheduler.registry`
- `gc`：按 `keep_latest_n` / `keep_pinned_versions` / `keep_full_retrain_only` 清理（AC-FR2300-01/02/03）

### 3.14. 部署（FR-2400）

| 函数                       | 签名                                                                                       | FR       | AC                       | modules                                       |
| -------------------------- | ------------------------------------------------------------------------------------------ | -------- | ------------------------ | ---------------------------------------------- |
| `deploy_model`             | `(registry: ModelRegistryPort, new_version: str, *, metrics: dict, ic_floor: float) -> bool` | FR-2400  | AC-FR2400-01/02          | scheduler.deploy → prediction, registry        |
| `watch_registry`           | `(registry_path: Path, on_change: Callable[[], None], *, poll_interval_sec: float = 60.0)`  | FR-2400  | AC-FR2400-03             | scheduler.deploy → prediction                  |

- 模块路径：`trader_off.scheduler.deploy`
- 验证失败（`test_ic_mean < ic_floor`）→ 不更新 `current_version`，WARNING 日志 `"validation failed, not deploying <v>"`（AC-FR2400-02）
- 加载失败（版本目录缺失/损坏）→ 保留旧版本 + ERROR 日志（AC-FR2400-04）
- `model_load_mode="hot-reload"` 时启用 `watch_registry`（默认 polling 60s，spec FR-2400 锁定）
- 部署记录写入 `logs/deploy.log`（FR-2400）

### 3.15. 调度状态持久化（FR-2500）

| 函数                | 签名                                                                                | FR       | AC                       | modules                                       |
| ------------------- | ----------------------------------------------------------------------------------- | -------- | ------------------------ | ---------------------------------------------- |
| `save_state`        | `(state_dir: Path, tasks: list[RetrainTask]) -> None`  # atomic write                | FR-2500  | AC-FR2500-01/02          | scheduler.state → core                          |
| `load_state`        | `(state_dir: Path) -> list[RetrainTask]`                                             | FR-2500  | AC-FR2500-03             | scheduler.state → core                          |
| `recover_tasks`     | `(tasks: list[RetrainTask]) -> list[RetrainTask]`  # running → failed("scheduler restart") | FR-2500  | AC-FR2500-03             | scheduler.state → core                          |
| `append_cron_log`   | `(state_dir: Path, entry: dict) -> None`  # append JSONL                              | FR-2500  | （观察）                  | scheduler.state → core                          |
| `append_drift_history` | `(state_dir: Path, drift_record: dict) -> None`  # append parquet (pyarrow backend) | FR-2500  | （观察）                  | scheduler.state → core                          |

- 模块路径：`trader_off.scheduler.state`
- 原子写：`temp_path.write_text(json.dumps(...))` + `temp_path.replace(target_path)`（NFR-0900 AC-2）

### 3.16. 协方差估计（FR-3000）

| 函数                  | 签名                                                                                                       | 返回            | FR       | AC                       | modules                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------- | --------------- | -------- | ------------------------ | ----------------------------------------- |
| `estimate_covariance` | `(returns_df: pl.DataFrame, method: Literal["sample", "ledoit_wolf"] = "ledoit_wolf") -> np.ndarray`       | (N, N) 协方差   | FR-3000  | AC-FR3000-01/02/03/04    | portfolio.covariance → solver, check     |

- 模块路径：`trader_off.portfolio.covariance`
- `<30` 日 → 抛 `InsufficientDataError("need at least 30 days")`（AC-FR3000-04）
- 全 NaN 列 → 剔除 + 写入 `assets_dropped.json`（AC-FR3000-03）

### 3.17. 预期收益（FR-3100）

| 函数                      | 签名                                                                                              | 返回                       | FR       | AC                       | modules                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------- | -------- | ------------------------ | --------------------------------------------------------- |
| `build_expected_returns`  | `(predictions: pl.DataFrame, mode: Literal["raw", "zscore"] = "raw") -> dict[str, float]`        | `{asset: mu}`               | FR-3100  | AC-FR3100-01/02          | portfolio.expected_returns → solver                       |

- 模块路径：`trader_off.portfolio.expected_returns`
- 资产不一致 → `AssetMismatchError("missing assets: [...]")`（AC-FR3100-03）
- zscore 模式：`mu = (score - mean) / std`

### 3.18. 行业映射（FR-3200）

| 函数                  | 签名                                                  | 返回                       | FR       | AC                       | modules                                                  |
| --------------------- | ----------------------------------------------------- | -------------------------- | -------- | ------------------------ | --------------------------------------------------------- |
| `load_industry_map`   | `(path: Path) -> dict[str, str]`                      | `{asset: industry}`        | FR-3200  | AC-FR3200-01/02/03       | portfolio.industry → solver, persistence                  |

- 模块路径：`trader_off.portfolio.industry`
- 重复行 → `IndustryMapConflictError("duplicate asset: <asset>, industries: [<ind1>, <ind2>]")`（AC-FR3200-03）
- 缺失行业 → 写入 `assets_without_industry.json` + WARNING；视为独立"未分类"虚拟行业（AC-FR3200-02）

### 3.19. 求解器（FR-3700）

| 函数                | 签名                                                                                                                                       | 返回                | FR       | AC                       | modules                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------- | -------- | ------------------------ | --------------------------------------------------------- |
| `solve_max_sharpe`  | `(mu: dict[str, float], cov: np.ndarray, assets: list[str], constraints: OptimizerConstraints, *, backend: Literal["auto", "cvxpy", "scipy"] = "auto", max_iterations: int = 1000, tolerance: float = 1e-6) -> SolverResult` | SolverResult       | FR-3700  | AC-FR3700-01/02/03/04    | portfolio.solver → check, persistence, cli               |

- 模块路径：`trader_off.portfolio.solver`
- `backend="auto"`：检测 `cvxpy` 是否可导入 → 否则 fallback `scipy.optimize.SLSQP`（AC-FR3700-03，Round-2 锁定）
- `backend="cvxpy"`：cvxpy 缺失 → `ImportError`（显式）
- `backend="scipy"`：强制 SLSQP（无需 cvxpy）
- `solver_status ∈ {"optimal", "optimal_inaccurate", "infeasible", "unbounded", "solver_error"}`
- `infeasible` 不抛异常，返回 `weights=None`

### 3.20. 约束校验（FR-3800）

| 函数                | 签名                                                                                                                            | 返回                  | FR       | AC                       | modules                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------------- | -------- | ------------------------ | ----------------------------------------- |
| `check_constraints` | `(weights: np.ndarray, assets: list[str], mu: dict[str, float], cov: np.ndarray, constraints: OptimizerConstraints, industry_map: dict[str, str] | None, industry_benchmark: dict[str, float] | None) -> ConstraintReport` | ConstraintReport | FR-3800 | AC-FR3800-01/02/03    | portfolio.check → persistence, cli       |

- 模块路径：`trader_off.portfolio.check`
- 数值容差：`long_only` 1e-9 / `sum_to_one` 1e-6 / `max_weight` 1e-9 / `industry_neutral` 1e-6

### 3.21. 基线对比（FR-3900）

| 函数                  | 签名                                                                                                                                       | 返回                  | FR       | AC                       | modules                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------- | -------- | ------------------------ | ----------------------------------------- |
| `compare_to_baseline` | `(weights_opt: np.ndarray, assets: list[str], mu: dict[str, float], cov: np.ndarray, baseline_weights: np.ndarray | None = None, w_prev: np.ndarray | None = None) -> ComparisonReport` | ComparisonReport | FR-3900 | AC-FR3900-01/02/03    | portfolio.baseline → persistence, cli    |

- 模块路径：`trader_off.portfolio.baseline`
- 默认 `baseline_weights = np.full(N, 1/N)`（`equal_weight`）
- 首次 `w_prev = None` → `w_prev = np.zeros(N)` → `turnover = 0.5 * sum(|w_opt - 0|) = 0.5 * sum(w_opt) = 0.5`（AC-FR3900-02）
- `optimized.sharpe < equal_weight.sharpe - 1e-4` → WARNING `"optimized sharpe < baseline, check inputs"`（AC-FR3900-03）

### 3.22. 优化结果持久化（FR-4000）

| 函数                       | 签名                                                                                                                                                                                            | 返回          | FR       | AC                       | modules                                       |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | -------- | ------------------------ | ---------------------------------------------- |
| `write_portfolio_outputs`  | `(output_dir: Path, weights: pl.DataFrame, constraint_report: ConstraintReport, comparison_report: ComparisonReport, solver_result: SolverResult, assets_dropped: list[str], industry_map: dict[str, str] | None = None) -> dict[str, Path]` | `{weights_csv, optimizer_report_json, portfolio_metrics_csv, weights_diagnostics_json, assets_dropped_json}` | FR-4000 | AC-FR4000-01/02/03 | portfolio.persistence → strategies.optimized_topk, tests/e2e |

- 模块路径：`trader_off.portfolio.persistence`
- 原子写：先写 `tmp/` 临时目录 → 全部就绪后 `tmp.rename(output_dir)`（AC-FR4000-03）
- 路径校验：`validate_path(output_dir, allowed_roots=[Path("reports/")])`（NFR-0700）

### 3.23. OptimizedTopKStrategy（FR-4200）

| 类 / 方法                                       | 签名                                                                                       | FR       | AC                       | modules                                                                                |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------ | -------- | ------------------------ | --------------------------------------------------------------------------------------- |
| `OptimizedTopKStrategy(BaseStrategy)`           | `__init__(self, broker: Broker, config: dict)`                                              | FR-4200  | AC-FR4200-01             | strategies.optimized_topk → backtest.runner, portfolio, strategies.lgbm_top20 (fallback) |
| `OptimizedTopKStrategy.init`                    | `async def init(self) -> None`                                                              | FR-4200  | AC-FR4200-02/04/05       | 同上                                                                                    |
| `OptimizedTopKStrategy.on_day_open`             | `async def on_day_open(self, tm) -> None`                                                   | FR-4200  | AC-FR4200-03             | strategies → broker (trade_target_pct)                                                  |
| `OptimizedTopKStrategy.on_stop`                 | `async def on_stop(self) -> None`                                                           | FR-4200  | （内部）                  | strategies                                                                              |

- 模块路径：`trader_off.strategies.optimized_topk`
- `init` 行为：
  - 加载 `weights_path` 配置（默认 `reports/portfolio_latest/weights.csv`）
  - 若文件不存在 → WARNING `"weights.csv missing, falling back to equal-weight top-K behavior"` + 实例化 `LGBMTop20Strategy` 作为代理（AC-FR4200-04）
  - 若文件陈旧（mtime 距今 > 5 个交易日）→ WARNING `"weights stale (5+ days old), falling back"` + 同上 fallback（AC-FR4200-05）
- `on_day_open`：调 `broker.trade_target_pct(asset, weight, extra={"reason": "optimized_topk", "weight": float, "version": str})`，对当前持仓但不在 weights 中的资产调 `trade_target_pct(asset, 0, ...)` 清仓

### 3.24. 公共工具（继承 v0.1.0 + 新增）

| 函数 / 类              | 签名                                                                                          | NFR      | AC                       | modules          |
| ---------------------- | --------------------------------------------------------------------------------------------- | -------- | ------------------------ | ---------------- |
| `setup_logger` (继承) | `(module: str, log_dir: Path = "logs") -> None`                                                | NFR-0600 | AC-NFR0600-02/03         | utils.logging    |
| `validate_path` (继承)| `(path: Path, allowed_roots: list[Path]) -> Path`                                              | NFR-0700 | AC-NFR0700-02            | utils.security   |
| `safe_load_model_file` (继承)| `(path: Path, allowed_types: tuple = (...)) -> object`                                   | NFR-0700 | AC-NFR0700-03            | utils.security   |
| `load_config` (继承)  | `(cli_args: dict, yaml_path: Path = None) -> dict`                                              | NFR-0800 | AC-NFR0800-02            | utils.config     |
| `validate_cron_expr`  | `(expr: str) -> None`  # 抛 `ConfigValidationError` 含 cron 解析失败详情                          | FR-2700  | AC-FR2700-04             | utils.config / scheduler.cron |

---

## 4. CLI 接口

### 4.1. `trader-off mine-factors`（FR-0800，新增）

```
trader-off mine-factors --config <yaml> [--start <YYYY-MM-DD>] [--end <YYYY-MM-DD>]
                         [--top-k <int>] [--corr-threshold <float>] [--output <dir>]
                         [--registry-dir <dir>]
```

| 参数                | 类型    | 默认值                            | 校验                       | AC              |
| ------------------- | ------- | --------------------------------- | -------------------------- | --------------- |
| `--config`          | path    | —                                 | 必填，yaml 存在（AC-FR0800-05） | AC-FR0800-05    |
| `--start`           | date    | config 默认                        | —                          | —               |
| `--end`             | date    | today                              | > start                    | —               |
| `--top-k`           | int     | 30                                | > 0                        | AC-FR0800-02    |
| `--corr-threshold`  | float   | 0.9                               | ∈ (0, 1)                   | —               |
| `--output`          | path    | `reports/factor_mining_<ts>/`      | 路径可写（T-4）             | —               |
| `--registry-dir`    | path    | `factor_registry/`                 | 路径可写（T-4）             | —               |

- 退出码：`0` 成功 / `2` 候选 < 10 / `3` 精选 < 10 / `4` 配置缺失或 schema 校验失败
- stdout：含 `"枚举了 N 个候选因子"` 与 `"精选 K 个因子"`
- **modules**: `cli.mine_factors` → `factor_mining.{templates,expression,evaluation,selection,viz,registry}`
- 关联 AC：`AC-FR0800-01/02/03/04/05`

### 4.2. `trader-off scheduler`（FR-2700，新增）

```
trader-off scheduler start --config <yaml>
trader-off scheduler stop
trader-off scheduler status
trader-off scheduler list-tasks [--limit <int>]
```

| 子命令         | 参数                | 退出码                       | AC              |
| -------------- | ------------------- | ---------------------------- | --------------- |
| `start`        | `--config <yaml>`   | `0` 成功 / `4` 配置失败       | AC-FR2700-01/03 |
| `stop`         | （无参）             | `0` 成功 / `1` 未运行         | —               |
| `status`       | （无参）             | `0` 总是                      | AC-FR2700-02    |
| `list-tasks`   | `--limit <int>` 默认 10 | `0` 成功                  | —               |

- `start` 行为：构造 `SchedulerConfig` + 5 个 ports + `RetrainScheduler` → `await scheduler.start()`（前台阻塞）
- `stop`：发送 SIGTERM（daemon 模式）/ 直接调 `await scheduler.stop()`（前台模式）
- `status` 输出含 `running, next_trigger_time, next_trigger_mode, active_tasks, pending_tasks, last_10_tasks`（AC-FR2700-02）
- 配置文件缺 `cron` 字段 → `ConfigValidationError("cron is required")`（AC-FR2700-03）
- 非法 cron 表达式 → `ConfigValidationError("invalid cron: ...")`（AC-FR2700-04）
- **modules**: `cli.scheduler` → `scheduler.{core, ports, cron, api}`

### 4.3. `trader-off retrain`（FR-2000，新增）

```
trader-off retrain trigger --mode <full|incremental> [--reason <str>] [--config <yaml>]
trader-off retrain status
trader-off retrain cancel --task-id <id>
```

| 子命令     | 参数                          | 退出码                       | AC              |
| ---------- | ----------------------------- | ---------------------------- | --------------- |
| `trigger`  | `--mode` 必填, `--reason` 可选 | `0` / `1` 配置缺失           | AC-FR2000-01    |
| `status`   | —                             | `0`                          | AC-FR2000-02    |
| `cancel`   | `--task-id` 必填              | `0` 成功 / `2` task_id 不存在 | —               |

- `trigger` 输出：`task_id=<uuid>`, `status=pending`（AC-FR2000-01）
- `status` 输出：最近 10 条任务（AC-FR2000-02）
- 调度器未运行 → 退出码 1 + stderr 含 `"scheduler not running"`
- **modules**: `cli.retrain` → `scheduler.{core, api}`

### 4.4. `trader-off optimize`（FR-4100，新增）

```
trader-off optimize --predictions <csv> --industry-map <csv>
                    [--config <yaml>] [--baseline <equal_weight|json_path>]
                    [--output <dir>] [--cov-window <int>] [--max-weight <float>]
                    [--industry-neutral-tol <float>]
```

| 参数                    | 类型    | 默认值                       | 校验                     | AC              |
| ----------------------- | ------- | ---------------------------- | ------------------------ | --------------- |
| `--predictions`         | path    | —                            | 必填，CSV 存在           | AC-FR4100-02    |
| `--industry-map`        | path    | —                            | 必填，CSV 存在           | AC-FR4100-01    |
| `--config`              | path    | —                            | 可选                      | —               |
| `--baseline`            | str/path | `equal_weight`              | enum 或 path             | —               |
| `--output`              | path    | `reports/portfolio_<ts>/`     | 路径可写（T-4）           | —               |
| `--cov-window`          | int     | 60                           | ≥ 30                     | AC-FR4100-04    |
| `--max-weight`          | float   | 0.10                         | ∈ (0, 1]                 | —               |
| `--industry-neutral-tol`| float   | 0.05                         | ≥ 0                      | —               |

- 退出码：`0` 成功 / `2` 输入缺失或 schema 校验失败 / `3` 资产 < 5 / `4` 协方差非正定
- stdout：含 `"Sharpe=X.YZ"` 与 `"报告落盘到 <path>"`（AC-FR4100-01）
- **modules**: `cli.optimize` → `portfolio.{covariance, expected_returns, industry, constraints, solver, check, baseline, persistence}`

### 4.5. `trader-off deploy`（FR-2400，新增）

```
trader-off deploy --version <str> [--config <yaml>]
```

| 参数         | 类型 | 必填 | 校验                            | AC              |
| ------------ | ---- | ---- | ------------------------------- | --------------- |
| `--version`  | str  | ✅   | version 存在于 registry.json     | AC-FR2400（CLI） |

- 退出码：`0` 成功 / `2` version 不存在
- 写 `logs/deploy.log`
- **modules**: `cli.deploy` → `scheduler.deploy` + `scheduler.registry`

### 4.6. `trader-off train`（v0.1.0 保留 + 新增 `--factor-registry`，FR-0900）

```
trader-off train --config <yaml> [--version <str>] [--start-year <int>] [--end-year <int>]
                 [--factor-registry <path>]    # v0.2.0 新增（可选）
                 [--loss <...>] [--alpha <...>] [--seed <int>] [--num-leaves <int>] ...
```

- **新增参数** `--factor-registry <path>`：传入时走精选因子特征工程；未传时回退 v0.1.0 默认 15 维特征（AC-FR0900-03）
- 退出码 / 行为不变
- **modules**: `cli.train` → `training.trainer, factor_mining.registry`（新增消费）
- 关联 AC：`AC-FR0900-01/02/03`, `AC-FR2100-01/02/03/04`

### 4.7. `trader-off predict`（v0.1.0 保留）

```
trader-off predict --model <version> --watchlist <csv> --date <YYYY-MM-DD>
```

- `--model` 接受两种版本格式（v0.1.0 `YYYYMMDD_HHMMSS` 或 v0.2.0 `v{major}.{minor}.{build}[.incr{N}]`）
- 退出码 / 行为不变
- **modules**: `cli.predict` → `prediction.service` → `training.model_io.load_model`（v0.1.0 模块扩展双格式识别）
- 关联 AC：`AC-NFR1000-02`

### 4.8. `trader-off backtest`（v0.1.0 保留 + 新增 strategy）

```
trader-off backtest --model <version> --strategy <lgbm_top20|optimized_topk>
                    --start <date> --end <date> --capital <float> [--config <yaml>]
```

- `--strategy` 新增 `optimized_topk` 选项
- 退出码 / 行为不变
- **modules**: `cli.backtest` → `backtest.runner, strategies.{lgbm_top20, optimized_topk}`

### 4.9. `trader-off feature-importance`（v0.1.0 保留）

```
trader-off feature-importance --model <version> [--top-k 20]
```

- 不变

---

## 5. 外部框架契约（继承 v0.1.0 + 新增）

### 5.1. BaseStrategy 继承契约（v0.1.0 §5.1，扩展）

| 方法             | millionaire 签名                              | trader-off 实现                                      | 性质       |
| ---------------- | --------------------------------------------- | ---------------------------------------------------- | ---------- |
| `init`           | `async def init(self) -> None`                 | OptimizedTopKStrategy: load weights.csv / fallback  | 重写       |
| `on_day_open`    | `async def on_day_open(self, tm) -> None`      | OptimizedTopKStrategy: trade_target_pct              | 重写       |
| `on_bar`         | `async def on_bar(self, ...) -> None`          | noop                                                  | 重写（空）|
| `on_day_close`   | `async def on_day_close(self, ...) -> None`   | noop                                                  | 重写（空）|
| `on_stop`        | `async def on_stop(self) -> None`              | release weights ref                                   | 重写       |

- **modules**: `strategies.optimized_topk`（实现）← `millionaire.quantide.core.strategy.BaseStrategy`（基类）

### 5.2. Broker 接口（v0.1.0 §5.2，继承）

| 方法                | 签名                                                                       | 用途                          |
| ------------------- | -------------------------------------------------------------------------- | ----------------------------- |
| `trade_target_pct`  | `trade_target_pct(self, asset: str, pct: float, extra: dict = None) -> None` | 调仓到目标百分比              |

- **modules**: `strategies.optimized_topk`（消费）← `millionaire.quantide.service.base_broker.Broker`（实现）

### 5.3. DataLoader 接口（v0.1.0 §5.3，继承）

| 方法                | 签名                                                                       | 用途                          |
| ------------------- | -------------------------------------------------------------------------- | ----------------------------- |
| `DataLoader.get_history` | `async get_history(self, asset: str, end_date: date, count: int = 120) -> pl.DataFrame` | 取 asset 在 end_date 前 count 日行情 |

- **modules**: `data.loader`（适配）← `millionaire.quantide.data.fetchers`（被封装）

### 5.4. REST API（FR-2000，aiohttp）

| 端点                                | 方法 | 请求体                                       | 响应                                            | AC              |
| ----------------------------------- | ---- | -------------------------------------------- | ----------------------------------------------- | --------------- |
| `POST /retrain/trigger`             | POST | `{"mode": "full"\|"incremental", "reason": str}` | `{"task_id": str, "status": "pending"}`         | AC-FR2000-03    |
| `GET /retrain/status`               | GET  | —                                            | `{"active_tasks": int, "last_10_tasks": [...]}` | —               |
| `POST /retrain/cancel/{task_id}`    | POST | —                                            | `{"cancelled": bool}`                            | —               |
| `GET /health`                       | GET  | —                                            | `{"status": "ok"}`                              | —               |

- **默认绑定** `127.0.0.1:8765`（NFR-0700 AC-4 强制；外部访问需 `--api-host 0.0.0.0`）
- 异常不暴露内部堆栈（AC-FR2000-04）
- **modules**: `scheduler.api`（实现）← `aiohttp` 测试客户端（消费）

---

## 6. 跨模块接口清单（Shield 集成测试依据）

> 下表汇总所有 `modules` 标注 ≥2 的接口，Shield 必须为每条编写集成测试（happy + 关键错误/边界）。`tests/integration/` 文件已在 test-plan §8.2 中按本表预期分组。

| #  | 接口契约                                          | 跨模块链路                                                          | 覆盖 AC                                                           | 集成测试文件                                                |
| -- | ------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| 1  | `enumerate_factors`                               | factor_mining.expression → evaluation, selection, registry, cli     | AC-FR0200-01/02/03/04                                            | `tests/integration/test_factor_mining_cli.py`                |
| 2  | `evaluate_factor`（复用 evaluation.ic）            | factor_mining.evaluation → evaluation.ic (v0.1.0)                    | AC-FR0300-05                                                      | `tests/unit/factor_mining/test_evaluation.py`（单测足够）       |
| 3  | `selected_factors.json` 落盘 → cli.train           | factor_mining.registry → cli.train → training.trainer                | AC-FR0900-01/02/03                                                | `tests/integration/test_train_with_registry.py`              |
| 4  | `RetrainScheduler`（含 ClockPort + TrainerPort）   | scheduler.core ← ports ← training.trainer + training.model_io       | AC-FR1500-01/02/03/04, AC-NFR0900-01                              | `tests/integration/test_retrain_full.py`                     |
| 5  | `next_cron_fire`（纯函数 T-3）                      | scheduler.cron → scheduler.core                                     | AC-FR1600-04                                                      | `tests/unit/scheduler/test_cron.py`（单测足够）                |
| 6  | `DriftDetector.evaluate`                           | scheduler.drift.detector → scheduler.core                            | AC-FR2600-01/02/03/04                                            | `tests/unit/scheduler/test_drift_detector.py`（单测足够）     |
| 7  | `PerfMonitor.trigger_perf_degradation`（IC-only）  | scheduler.perf_monitor → scheduler.core                              | AC-FR1900-01/02/03/04（Round-2 锁定）                              | `tests/unit/scheduler/test_perf_monitor.py`（单测足够）       |
| 8  | `ModelRegistry.gc / rollback_to`                  | scheduler.registry → training.model_io (load_model + version 目录)   | AC-FR2300-01/02/03/04                                            | `tests/integration/test_deploy.py`                            |
| 9  | `deploy_model + watch_registry`                    | scheduler.deploy → prediction.service (lazy/hot-reload)              | AC-FR2400-01/02/03/04                                            | `tests/integration/test_deploy.py`                            |
| 10 | `scheduler.api`（aiohttp，localhost only）          | scheduler.api → scheduler.core                                       | AC-FR2000-03/04, AC-NFR0700-04                                    | `tests/integration/test_retrain_cli_api.py` + `test_api_security.py` |
| 11 | `last_tasks.json` 持久化 + 恢复 + 原子写            | scheduler.state → scheduler.core                                     | AC-FR2500-01/02/03/04, AC-NFR0900-02/03                          | `tests/integration/test_scheduler_resilience.py`              |
| 12 | `mine-factors` CLI 端到端                          | cli.mine_factors → factor_mining 全链路                              | AC-FR0800-01/02/03/04/05                                          | `tests/integration/test_factor_mining_cli.py`                |
| 13 | `solve_max_sharpe`（cvxpy → scipy fallback）       | portfolio.solver → portfolio.constraints + utils                    | AC-FR3700-01/02/03/04                                            | `tests/unit/portfolio/test_solver.py`（fallback 单测足够）     |
| 14 | `build_expected_returns` ← predictions             | portfolio.expected_returns → prediction.service                      | AC-FR3100-01/02/03                                                | `tests/unit/portfolio/test_expected_returns.py`（单测足够）    |
| 15 | `estimate_covariance`（Ledoit-Wolf）                | portfolio.covariance → sklearn + utils                                | AC-FR3000-01/02/03/04                                            | `tests/unit/portfolio/test_covariance.py`（单测足够）          |
| 16 | `check_constraints + compare_to_baseline`          | portfolio.check + baseline → portfolio.persistence                   | AC-FR3800-01/02/03, AC-FR3900-01/02/03                            | `tests/unit/portfolio/test_check_baseline.py`                |
| 17 | `write_portfolio_outputs` 原子落盘                  | portfolio.persistence → reports/portfolio_<ts>/                     | AC-FR4000-01/02/03                                                | `tests/integration/test_persistence_atomic.py`               |
| 18 | `optimize` CLI                                     | cli.optimize → portfolio 全链路                                       | AC-FR4100-01/02/03/04                                            | `tests/integration/test_optimize_cli.py`                     |
| 19 | `OptimizedTopKStrategy` 完整生命周期                | strategies.optimized_topk → portfolio (weights.csv) + backtest + strategies.lgbm_top20 (fallback) | AC-FR4200-01/02/03/04/05                            | `tests/unit/strategies/test_optimized_topk.py` + e2e         |
| 20 | `train --factor-registry` 接入                     | cli.train → training.trainer → factor_mining.registry                | AC-FR0900-01/02/03                                                | `tests/integration/test_train_with_registry.py`              |
| 21 | `scheduler start|status` CLI                       | cli.scheduler → scheduler.core + config                              | AC-FR2700-01/02/03/04                                            | `tests/integration/test_scheduler_cli.py`                    |
| 22 | `retrain trigger|status|cancel` CLI                | cli.retrain → scheduler.core                                          | AC-FR2000-01/02                                                  | `tests/integration/test_retrain_cli_api.py`                  |
| 23 | `deploy` CLI                                       | cli.deploy → scheduler.deploy + scheduler.registry                   | AC-FR2400（CLI）                                                  | `tests/integration/test_deploy.py`                            |
| 24 | v0.1.0 模型加载兼容性                              | training.model_io.load_model(v0.1.0 version) → prediction            | AC-NFR1000-01/02                                                  | `tests/integration/test_v010_compat.py`                      |
| 25 | v0.1.0 CLI 不变性                                  | cli.{train,predict,backtest,feature-importance} 签名                  | AC-NFR1000-03                                                    | `tests/integration/test_v010_compat.py`                      |
| 26 | v0.1.0 LGBMTop20Strategy 可用                      | strategies.lgbm_top20 → BaseStrategy                                 | AC-NFR1000-04                                                    | `tests/integration/test_v010_compat.py`                      |

---

## 7. 异常接口

继承 v0.1.0 异常 + v0.2.0 新增：

| 异常                              | 模块               | 触发条件                                     | 关联 AC          |
| --------------------------------- | ------------------ | -------------------------------------------- | ---------------- |
| `InsufficientDataError`（继承）   | utils.exceptions   | 协方差 < 30 日 / nav < 30 日                  | AC-FR3000-04     |
| `ModelVersionExistsError`（继承） | utils.exceptions   | save_model version 已存在                     | AC-FR0800-03     |
| `PathTraversalError`（继承）      | utils.exceptions   | 文件 IO 路径逃逸                              | AC-NFR0700-02    |
| `VisualizationDependencyError`(继承)| utils.exceptions | matplotlib 缺失                              | AC-FR1600-04     |
| `DataSchemaError`（继承）         | utils.exceptions   | OHLCV schema 校验失败                        | AC-NFR0100-04    |
| `ConfigValidationError`（继承）   | utils.exceptions   | CLI / yaml pydantic 校验失败 / 非法 cron 表达式 | AC-FR2700-03/04, AC-FR0800-05 |
| `FactorRegistrySchemaError`       | factor_mining.registry | 因子注册表缺必填字段                        | AC-FR0600-04     |
| `AssetMismatchError`              | portfolio.expected_returns | mu 与 Σ 资产集合不一致               | AC-FR3100-03     |
| `IndustryMapConflictError`        | portfolio.industry | 行业映射 CSV 含重复 asset                     | AC-FR3200-03     |
| `OptimizerError`（基类）          | portfolio.solver   | 优化器总入口异常                               | （内部防护）       |
| `TrainerPortError`                | scheduler.ports    | TrainerPort 包装 trainer 异常                 | （内部防护）       |
| `ClockPortError`                  | scheduler.ports    | ClockPort 实现错误                            | （内部防护）       |
| `DriftDecisionError`              | scheduler.drift.detector | 配置非法                                 | （内部防护）       |

---

## 8. 三方闭环：AC → interfaces → test-plan

每条 AC 的断言依据均落在本文定义的可观察出口上；每个出口在 test-plan 中有对应测试覆盖。下表确认 159 条 AC 的 closure。

| FR/NFR    | AC 数 | interfaces 出口（本文）                                  | test-plan 覆盖（§8/§9）              |
| --------- | ----- | -------------------------------------------------------- | ----------------------------------- |
| FR-0100   | 4     | §3.1 + §1.1/1.2                                          | §8.1 unit                          |
| FR-0200   | 4     | §3.1 + §1.3 + §2.5(invalid_combinations.json)             | §8.1 unit                          |
| FR-0300   | 5     | §3.2 + §1.4                                              | §8.1 unit                          |
| FR-0400   | 4     | §3.3 + §1.5                                              | §8.1 unit                          |
| FR-0500   | 3     | §3.5 + §2.8                                              | §8.1 unit                          |
| FR-0600   | 4     | §3.4 + §2.1/2.2                                          | §8.1 unit(3) + integ(1)             |
| FR-0700   | 4     | §3.5 + §2.8                                              | §8.1 unit                          |
| FR-0800   | 5     | §4.1                                                     | §8.2 integ                         |
| FR-0900   | 3     | §4.6 + §2.4                                              | §8.2 integ                         |
| FR-1500   | 4     | §3.6/3.7 + §1.8/1.9/1.10                                 | §8.1 unit(2) + integ(2)            |
| FR-1600   | 4     | §3.8 + §1.8                                              | §8.1 unit                          |
| FR-1700   | 4     | §3.9                                                     | §8.1 unit                          |
| FR-1800   | 3     | §3.10                                                    | §8.1 unit                          |
| FR-1900   | 4     | §3.12 + §1.7（Round-2 IC-only 锁定）                      | §8.1 unit                          |
| FR-2000   | 4     | §4.3 + §5.4                                              | §8.2 integ                         |
| FR-2100   | 4     | §3.7 + §2.3 + §2.4                                       | §8.2 integ                         |
| FR-2200   | 4     | §3.7 + §2.3 + §2.4                                       | §8.2 integ                         |
| FR-2300   | 4     | §3.13 + §2.3                                             | §8.1 unit(3) + integ(1)            |
| FR-2400   | 4     | §3.14 + §2.3 + §2.9(deploy.log)                          | §8.2 integ                         |
| FR-2500   | 4     | §3.15 + §2.5                                             | §8.1 unit(2) + integ(2)            |
| FR-2600   | 4     | §3.11 + §1.6 + §2.6                                      | §8.1 unit                          |
| FR-2700   | 4     | §4.2 + §1.8                                              | §8.2 integ                         |
| FR-3000   | 4     | §3.16 + §2.7(assets_dropped.json)                         | §8.1 unit                          |
| FR-3100   | 3     | §3.17 + §1.20                                            | §8.1 unit                          |
| FR-3200   | 3     | §3.18 + §1.21                                            | §8.1 unit                          |
| FR-3300   | 2     | §3.19 + §1.12                                            | §8.1 unit                          |
| FR-3400   | 2     | §3.19 + §1.12                                            | §8.1 unit                          |
| FR-3500   | 3     | §3.19 + §1.12                                            | §8.1 unit                          |
| FR-3600   | 2     | §3.19 + §1.12                                            | §8.1 unit                          |
| FR-3700   | 4     | §3.19 + §1.13                                            | §8.1 unit                          |
| FR-3800   | 3     | §3.20 + §1.14 + §2.7                                      | §8.1 unit(2) + e2e(1)              |
| FR-3900   | 3     | §3.21 + §1.15 + §2.7                                      | §8.1 unit(2) + e2e(1)              |
| FR-4000   | 3     | §3.22 + §2.7                                              | §8.1 unit(2) + integ(1)            |
| FR-4100   | 4     | §4.4                                                     | §8.2 integ                         |
| FR-4200   | 5     | §3.23 + §5.1                                              | §8.1 unit(4) + e2e(1)              |
| NFR-0100  | 5     | §6.5 e2e 文件 + psutil                                    | §8.3 perf（e2e marker）             |
| NFR-0200  | 1     | (CI 门禁：coverage ≥97%)                                  | §7 CI gate                         |
| NFR-0300  | 1     | (CI 门禁：mutmut ≥80%)                                    | §7 CI gate                         |
| NFR-0400  | 3     | (ADR + docs sync，CI 门禁)                                | §7 CI gate                         |
| NFR-0500  | 3     | §3.24 + §4 全部 CLI + §3.7(async)                          | §8.1 unit(2) + CI gate(1)          |
| NFR-0600  | 3     | §3.24 + §2.9                                              | §8.1 unit(1) + integ(1) + CI gate(1)|
| NFR-0700  | 5     | §3.24 + §7 + §5.4(api_host=127.0.0.1)                      | §8.1 unit(1) + integ(1) + CI gate(3)|
| NFR-0800  | 3     | §2.4(metadata 5 字段) + §3.24(load_config)                 | §8.1 unit(2) + integ(1)            |
| NFR-0900  | 3     | §1.8(max_concurrent_tasks) + §2.5 + §3.15(atomic write)    | §8.2 integ                         |
| NFR-1000  | 4     | §4.6/4.7/4.8/4.9 + §5.1                                   | §8.2 integ                         |
| **合计** | **159** | **全部 AC 有出口**                                       | **159/159 全覆盖**                  |

> **闭环校验**：interfaces.md 每个外部出口 → test-plan 至少 1 个测试方法（§8/§9）。test-plan 不发明新观察方法；若测试需某出口而 interfaces 未定义，先修订 interfaces。

---

## 9. M-TESTPLAN 可测试性需求（T-1~T-4）落地清单

| #   | 需求                        | 实现位置（interfaces.md）            | 签名                                                |
| --- | --------------------------- | ------------------------------------ | --------------------------------------------------- |
| T-1 | 虚拟时钟注入 port           | §3.6 `ClockPort` / `SystemClockPort` / `VirtualClockPort` | `now(self) -> datetime`；注入 `SchedulerConfig.clock` |
| T-2 | 调度器 port 注入 TrainerPort | §3.6 `TrainerPort` / `DefaultTrainerPort`              | `async train(...) -> ModelArtifact`；`async save(...) -> str` |
| T-3 | `next_cron_fire` 纯函数      | §3.8 `next_cron_fire`                 | `(expr: str, base: datetime, *, backend="croniter" \| "apscheduler") -> datetime` |
| T-4 | 配置驱动的落盘根目录         | §1.8 `SchedulerConfig.{state_dir, models_dir, reports_dir}` + §4 CLI `--output` / `--registry-dir` 参数 | 全部写盘路径可配置；无硬编码仓库根 |
