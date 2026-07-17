# trader-off v0.2.0 — 因子挖掘·再训练调度·组合优化器 — Spec

- **Spec ID**: v0.2.0-001-factor-mining-retrain-optimizer
- **Created**: 2026-07-17
- **Status**: Draft
- **关联 PRD/story**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/story.md`
- **继承基线**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/{spec,acceptance,interfaces}.md`（v0.1.0 模型/策略/接口契约仍生效）

> **职责切分**: 本文档只描述需求本身（FR/NFR 描述 + 元数据）。
> 验收标准（可观察、可断言的通过条件）放在 `acceptance.md` 中。
> 测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。
>
> **继承策略**: v0.1.0 已锁定的 FR-0100~1600 / NFR-0100~0700 视为「冻结契约」,本文件不重复定义其内容,仅在必要处通过「参见 v0.1.0」引用。NFR-0500/0600/0700 在本文件中**重申**为 v0.2.0 的全局约定,以确保跨版本一致性。

## User Stories

### US-0010 持续进化的量化系统
story: 作为一名量化研究员,我希望系统能够自动从因子模板库中挖掘有效因子、定期再训练模型以适应市场变化、并基于最新预测自动生成满足风险约束的最优投资组合,从而把单次训练的静态模型升级为持续进化的量化系统,降低手工维护成本。
priority: P0

### US-0020 因子挖掘自动化
story: 作为一名量化研究员,我希望基于动量/波动率/成交量/基本面 4 类模板库,通过参数化组合自动生成数百个候选因子并按 IC/ICIR/Rank IC 系统化评估、自动剔除冗余、产出可解释的精选因子集与评估报告,从而替代手工逐个构造特征的繁琐过程。
priority: P0

### US-0030 自动再训练与稳健部署
story: 作为一名量化研究员,我希望模型在数据漂移(PSI/KS)、性能衰减(IC/Sharpe 下降)、或定时计划(Cron)触发下自动重训(全量或增量),并通过版本管理与自动部署机制确保预测服务始终运行在最新已验证模型上,且支持回滚。
priority: P0

### US-0040 风险可控的组合优化
story: 作为一名投资经理,我希望基于模型预测得分,通过最大化 Sharpe Ratio 并满足 long-only、行业中性、个股上限 10% 等约束,自动得到最优权重,并提供与等权基线的对比与约束违反检查报告,从而把原始预测信号转化为可投资、可审计的投资组合。
priority: P0

## Usage Scenarios

### scenario-0010 因子挖掘 CLI

1. 量化研究员准备行情数据(已在 `data_loader` 抽象层就绪),执行 `trader-off mine-factors --config configs/factor_mining.yaml --start 2020-01-01 --end 2024-12-31`。
2. 系统按 4 类模板(动量/波动率/成交量/基本面)枚举候选因子(默认生成 ≥200 个),逐个计算 IC/ICIR/Rank IC。
3. 系统按 ICIR 降序取 Top-K(K 默认 30),剔除 Pearson 相关系数 > 0.9 的冗余因子。
4. 落盘 3 个产物:
   - `factor_registry/factors.yaml`: 全部候选因子表达式注册表(≥200 条)。
   - `factor_registry/selected_factors.json`: 精选因子集(含 ICIR、Pearson 矩阵)。
   - `reports/factor_mining_<ts>/evaluation_report.html`: 含 IC 时序图、ICIR 排名表、相关性热力图、Top-K 分组收益曲线。

### scenario-0020 再训练调度 — Cron 触发

1. 系统管理员配置 `configs/scheduler.yaml`,指定:
   - 全量重训 cron:`0 16 * * 1-5`(每个交易日 16:00,即收盘后)
   - 增量重训 cron:`0 16 * * 1-5`(每日,与全量共享)
   - 重训频率:全量每 5 个交易日触发 1 次,增量每日触发
2. 启动调度器:`trader-off scheduler start --config configs/scheduler.yaml`。
3. 触发时刻到达时,调度器自动调用 `train_model`(v0.1.0 接口)进行全量或增量重训,产出新版本 `models/v0.X.Y.<build>/`(与 v0.1.0 模型目录结构完全一致)。
4. 重训完成后,调度器自动:
   - 更新 `models/registry.json`(版本注册表,保留最近 N=10 个版本)
   - 触发预测服务 `predict` 接口的 latest-version reload(可选 REST 钩子或下一次 lazy load)
5. 输出调度日志到 `logs/scheduler.log`,含每条任务的触发类型、版本号、耗时、是否成功。

### scenario-0030 再训练调度 — 漂移触发

1. 每日 09:00(开盘前),调度器对最新一日的输入特征数据(来自 data_loader)运行漂移检测器:
   - PSI:对比最近 30 个交易日特征分布 vs 训练集基准分布;阈值默认 0.2,触发即记录告警。
   - KS:对每个特征执行 `scipy.stats.ks_2samp(baseline, recent)`,p 值 < 0.05 视为分布显著不同。
2. 当任一特征的 PSI > 0.2 或 KS p-value < 0.05 的特征数 ≥ 5(可配置),调度器触发增量重训。
3. 漂移检测报告输出到 `reports/drift_<ts>/drift_report.json`(逐特征 PSI/KS 值)与 `drift_summary.csv`(触发决策汇总)。

### scenario-0040 组合优化 CLI

1. 量化研究员执行 `trader-off optimize --predictions predictions_<date>.csv --industry-map configs/industry_map.csv --constraints configs/optimizer.yaml --baseline equal_weight --output reports/portfolio_<ts>/`。
2. 优化器:
   - 读取预测得分作为预期收益 `mu`
   - 用最近 60 个交易日收益率估算协方差矩阵(Ledoit-Wolf shrinkage,默认)
   - 求解 Max Sharpe:`max (mu^T w) / sqrt(w^T Σ w)`,subject to: long-only、Σw=1、|w_i| ≤ 0.1、每个行业权重偏离行业基准 ≤ 5%。
3. 输出 4 类文件到 `reports/portfolio_<ts>/`:
   - `weights.csv`:最优权重表(`asset, weight, sector`)
   - `optimizer_report.json`:Sharpe、波动率、行业暴露、约束违反检查
   - `portfolio_metrics.csv`:与等权基线的对比(年化收益、波动率、Sharpe、最大回撤、换手率)
   - `weights_diagnostics.json`:求解状态、对偶变量、迭代次数

### scenario-0050 端到端 v0.2.0 全链路

1. 准备 fixture 数据(≥50 只虚拟股票 × 252 个交易日 × 完整 OHLCV)。
2. 执行 `mine-factors` → 生成因子注册表与精选因子集(确保 ≥10 个精选因子)。
3. 执行 `trader-off train` (v0.1.0 接口,使用精选因子作为输入) → 生成模型。
4. 执行 `trader-off predict` → 生成预测。
5. 执行 `optimize` → 生成组合权重。
6. 执行 `trader-off backtest`(v0.1.0 接口,使用新策略 `OptimizedTopKStrategy`)→ 生成回测报告。
7. 整个链路 wall time ≤ 600 秒,内存峰值 ≤ 16 GB。

## Functional Requirements

> **格式约定(必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表(Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定(必读)**: 本次草稿按 **100 起步、步长 100** 编号(FR-0100, FR-0200, …);后续 review 按 10 步长插入(FR-0110);二轮后改为连续编号。
>
> **继承说明**: v0.1.0 已锁定的 FR-0100~1600 与 NFR-0100~0700 不重复定义。本文件新增 FR 覆盖 v0.2.0 三大模块;继承的 NFR 在本章末尾以 `NFR-XXXX 重申/继承` 形式存在,以避免重复。

---

### 模块 A — 因子挖掘 (FR-0100 ~ FR-0900)

> **Lex [RESOLVED]:** 【阻塞】模块A头部FR范围不准确：第99行声明模块A覆盖FR-0100~FR-1400，但实际只定义了FR-0100~FR-0900（9个FR），FR-1000至FR-1400不存在。请Sage修正范围声明为FR-0100~FR-0900或补充缺失的FR。
>> **Sage:** 已修正:模块 A 头部范围由 `FR-0100 ~ FR-1400` 改为 `FR-0100 ~ FR-0900`(实际定义 9 个 FR,无缺失)。模块 B 头部已声明 `FR-1500 ~ FR-2700`,模块 C 头部声明 `FR-3000 ~ FR-4400`(待 T-003 修正)。Mechanical fix,无新增 FR。


<a id="fr-0100"></a>
### FR-0100 因子模板库定义

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 提供 4 类因子模板注册表(`trader_off.factor_mining.templates`),每类至少 3 个具体模板:
  - **动量类**:`momentum_N`(close[t]/close[t-N]-1,N ∈ {5,10,20,60})、`excess_momentum_N`(动量 - 同期市场平均动量)、`momentum_accel_N`(动量 N - 动量 2N)。
  - **波动率类**:`vol_N`(std(daily_returns, N),N ∈ {10,20,60})、`amplitude_N`((high-low)/close,rolling N)、`atr_N`(N 日平均真实波幅)。
  - **成交量类**:`volume_change_N`(volume / volume.shift(N) - 1,N ∈ {5,10,20})、`turnover_N`(mean(turnover, N),N ∈ {5,10,20})、`vp_corr_N`(rolling corr(volume, close, N))。
  - **基本面组合类**(当 data_loader 提供 fundamental 列时启用):`ep`(1/PE)、`bp`(1/PB)、`roe`、`revenue_growth`。缺失时跳过并打 INFO 日志(不报错)。
- 模板以 dataclass 形式注册:`FactorTemplate(name: str, category: str, fields: list[str], params: dict, formula: str)`,支持运行时枚举。
- 全部模板通过 `list_templates() -> list[FactorTemplate]` 公开枚举接口。
- 模板库版本号 `factor_template_version = "v1"`,写入 `factor_registry/factors.yaml` 头部,确保可追溯。

---

<a id="fr-0200"></a>
### FR-0200 表达式引擎 — 参数化枚举

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 对每个模板,按预定义参数空间自动展开为具体因子表达式。例:`momentum_N` 模板 + 参数空间 `N ∈ {5,10,20,60}` → 产出 `momentum_5, momentum_10, momentum_20, momentum_60` 共 4 个具体因子。
- 参数空间定义在 `trader_off.factor_mining.param_space`,支持 `int_range`、`choice`、`bool` 三种类型,例:
  - `int_range("N", 5, 60, step=5)` 生成 [5, 10, ..., 60]
  - `choice("field", ["close", "open", "high", "low", "volume"])` 生成 5 个候选
- 引擎输出 `list[FactorSpec]`,每个 `FactorSpec` 含字段:`id`(模板名+参数序列化,如 `momentum_N_5`)、`template_name`、`category`、`formula`(字符串表达式,可读)、`compute_fn`(可调用对象)。
- 引擎函数签名:`enumerate_factors(templates: list[FactorTemplate], param_space: dict) -> list[FactorSpec]`,为纯函数。
- 引擎对每个 `(template, params)` 组合做合法性校验(如 N > 0、field ∈ 合法字段集合),非法组合记录到 `invalid_combinations.json` 并跳过(不抛异常)。
- 默认总候选因子数 ≥ 200 个(由默认模板 + 默认参数空间自然产生)。

---

<a id="fr-0300"></a>
### FR-0300 因子评估 — IC / ICIR / Rank IC

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 评估函数 `evaluate_factor(factor_values: pl.DataFrame, labels: pl.DataFrame, dates: list[date]) -> FactorEvaluation`,输入:
  - `factor_values`: 列 `asset, date, value`(每只资产每日的因子值)
  - `labels`: 列 `asset, date, label`(未来 N 日真实收益,默认 N=5,与 v0.1.0 label 复用)
  - `dates`: 评估涉及的交易日列表
- 输出 `FactorEvaluation` dataclass,字段:
  - `ic_ts`: pl.DataFrame,列 `date, ic`(每日 Pearson IC)
  - `rank_ic_ts`: pl.DataFrame,列 `date, rank_ic`(每日 Spearman Rank IC)
  - `ic_mean`, `ic_std`: float
  - `icir`: float = `ic_mean / ic_std`(若 std == 0 则记 0.0 + WARNING)
  - `rank_ic_mean`, `rank_ic_std`: float
  - `layered_returns`: pl.DataFrame,列 `layer, mean_return`(5 层平均收益)
- 复用 v0.1.0 的 `ic_pearson`、`ic_spearman`、`compute_layered_returns` 函数(`trader_off.evaluation.ic`),通过 import 复用,不在本模块重复实现。
- IC / ICIR 为按日时间序列聚合,缺失日期(如停牌)跳过该日(不抛异常,记录到 `evaluation_skipped_dates.json`)。
- 评估函数为纯函数,支持批量调用(对每个 `FactorSpec` 一次)。

---

<a id="fr-0400"></a>
### FR-0400 因子选择 — Top-K + Pearson 去冗余

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 选择算法:`select_factors(evaluations: list[FactorEvaluation], factor_specs: list[FactorSpec], top_k: int = 30, corr_threshold: float = 0.9) -> list[FactorSpec]`。
- 步骤:
  1. 按 `icir` 降序排序所有候选因子。
  2. 取前 `top_k` 个候选(默认 30)进入「精选池」。
  3. 在精选池内计算两两 Pearson 相关系数(|corr| > 0.9 即视为冗余)。
  4. 冗余处理:按 ICIR 排名保留更高者,移除其余;若 ICIR 相等(差值 < 1e-9)保留 `factor_spec.id` 字典序较小的。
- 至少 10 个精选因子(若候选总数 < 10 则全部保留并打 WARNING)。
- 函数返回精选因子列表,同时返回 `SelectionDiagnostics` dataclass:`{removed_by_redundancy: list[str], final_k: int, top_k_requested: int}`。

---

<a id="fr-0500"></a>
### FR-0500 相关性热力图输出

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 在精选因子集合上计算 Pearson 相关矩阵 `M[i, j] = corr(factor_i, factor_j)`,形状 `[k, k]`。
- 调用 `render_correlation_heatmap(corr_matrix: np.ndarray, labels: list[str], output_path: Path) -> Path`,使用 matplotlib `imshow` 或 `pcolormesh` 渲染为 PNG。
- PNG 输出到 `reports/factor_mining_<ts>/figures/correlation_heatmap.png`,尺寸默认 `figsize=(12, 10)`、`dpi=120`。
- 颜色映射:发散色图 `RdBu_r`,中心 0 值用白色,值域固定 [-1, 1]。
- 单元格标注:显示 2 位小数的相关系数(可选,密度高时降级为 1 位)。
- 中文字体处理继承 v0.1.0 NFR-0500/FR-1600:`matplotlib.use("Agg")` + fallback 字体 + 缺失时打 WARNING。

---

<a id="fr-0600"></a>
### FR-0600 因子注册表持久化

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 因子挖掘完成后,输出两个文件到 `factor_registry/`:
  - `factors.yaml`:全部候选因子注册表(≥200 条),结构:
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
      - ...
    ```
  - `selected_factors.json`:精选因子集 + 元数据:
    ```json
    {
      "selected_count": 28,
      "selection_diagnostics": {"removed_by_redundancy": [...], "final_k": 28, "top_k_requested": 30},
      "factors": [
        {"id": "momentum_N_20", "category": "momentum", "icir": 0.85, "ic_mean": 0.03, "ic_std": 0.035, ...},
        ...
      ]
    }
    ```
- YAML 序列化使用 `pyyaml`(v0.1.0 已包含);JSON 使用 stdlib `json`。
- `factor_registry/` 目录不存在时自动创建。
- 文件格式支持反向加载:`load_factor_registry(path: Path) -> dict` 可读取并校验 schema(必填字段缺失 → 抛 `FactorRegistrySchemaError`)。

---

<a id="fr-0700"></a>
### FR-0700 因子评估报告 — HTML + Markdown

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 输出 `reports/factor_mining_<ts>/evaluation_report.html`(主报告),至少包含:
  - **IC 时序图**:每个精选因子的 IC 时间序列折线图(子图网格,默认 4 列)。
  - **ICIR 排名表**:精选因子按 ICIR 降序的 HTML 表格(列:id、category、ic_mean、ic_std、icir、rank_ic_mean、layered_top_minus_bottom)。
  - **相关性热力图**:`figures/correlation_heatmap.png` 嵌入(用 `<img>` 标签,相对路径)。
  - **5 层分组收益**:精选因子 Top-1 层的累计收益曲线(`figures/top_layer_cumret.png`,自动生成)。
  - **元数据**:生成时间、数据范围、候选总数、精选数、模板版本号。
- 同时输出 Markdown 版本 `evaluation_report.md`(精简版,不含图像,纯表格 + 文本)。
- HTML 模板使用 `string.Template` 或 Jinja2(若项目已包含 Jinja2 依赖);无外部模板依赖时回退到 `string.Template`。
- 报告生成函数 `render_evaluation_report(evaluations: list[FactorEvaluation], selected: list[FactorSpec], output_dir: Path) -> dict[str, Path]`,返回 `{html, md, figures_dir}`。
- 中文字体处理继承 FR-0500 与 v0.1.0 FR-1600。

---

<a id="fr-0800"></a>
### FR-0800 因子挖掘 CLI

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- CLI 入口:`trader-off mine-factors --config <yaml> [--start <YYYY-MM-DD>] [--end <YYYY-MM-DD>] [--top-k <int>] [--corr-threshold <float>] [--output <dir>]`。
- 必填参数:`--config`(配置文件路径,含 data_loader、param_space 引用)。
- 可选参数默认值:
  - `--top-k`: 30
  - `--corr-threshold`: 0.9
  - `--output`: `reports/factor_mining_<ts>/`
- 退出码:
  - 0: 成功(精选因子 ≥ 10 个)
  - 2: 候选因子总数 < 10(数据不足)
  - 3: 精选因子 < 10(冗余过多,打 WARNING)
  - 4: 配置文件不存在或 schema 校验失败
- stdout 输出关键进度:「枚举了 N 个候选因子」「精选 K 个因子」「报告落盘到 <path>」。
- CLI 参数通过 pydantic 校验,缺失或类型错误抛 `ConfigValidationError`(与 v0.1.0 AC-FR1100-03 一致)。

---

<a id="fr-0900"></a>
### FR-0900 精选因子作为 v0.1.0 模型输入

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- `trader-off train` (v0.1.0 FR-0700/0800) 支持 `--factor-registry <path>` 参数,从精选因子集 `selected_factors.json` 加载精选因子列表。
- 训练特征工程阶段只计算精选因子对应的特征列(而非 v0.1.0 FR-0100/0200/0300 的全部 15 个固定指标)。
- 训练模型目录的 `metadata.json` 必须记录:
  - `factor_registry_path`: 使用的因子注册表路径
  - `factor_template_version`: 模板版本号(来自 FR-0100)
  - `selected_factor_count`: 精选因子数
  - `feature_names`: 精选因子名列表(替代 v0.1.0 固定 15 个特征名)
- v0.1.0 FR-0800 的 `feature_names.json` 同步更新为精选因子名(而非 v0.1.0 的固定 15 维)。
- 若未传入 `--factor-registry`,`trader-off train` 回退到 v0.1.0 默认行为(全部 15 个固定特征),保持向后兼容。

---

### 模块 B — 再训练调度 (FR-1500 ~ FR-2700)

<a id="fr-1500"></a>
### FR-1500 调度器核心接口与生命周期

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模块路径:`trader_off.scheduler.core`,核心类 `RetrainScheduler`。
- 初始化:`RetrainScheduler(config: SchedulerConfig, model_registry: ModelRegistry, drift_detector: DriftDetector, perf_monitor: PerfMonitor, trainer: TrainerPort)`。
- 公开方法:
  - `start() -> None`:启动调度循环(异步),阻塞直到 `stop()`。
  - `stop() -> None`:优雅停止,等待当前任务完成。
  - `trigger_now(reason: TriggerReason, mode: Literal["full", "incremental"]) -> RetrainTask`:手动触发立即重训,返回任务句柄(含 task_id)。
  - `get_status() -> SchedulerStatus`:返回当前调度器状态(下一触发时间、最近一次触发、活跃任务数)。
- 调度循环:每秒(可配置 tick_interval,默认 1s)检查 cron 队列与漂移队列,满足条件即触发任务。
- 任务调度:同一时刻最多 1 个重训任务在跑(并发安全由 `asyncio.Lock` 保护),新触发请求进入 FIFO 队列。
- 调度器状态可在异常退出后恢复(见 FR-2500 持久化)。
- 类 `RetrainScheduler` 不直接依赖 millionaire 框架,可独立单测(monkey-patch 各 Port)。

---

<a id="fr-1600"></a>
### FR-1600 Cron 触发器

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 配置 `SchedulerConfig.cron`:
  - `full_retrain`: cron 表达式字符串,默认 `0 16 * * 1-5`(每个交易日 16:00)
  - `incremental_retrain`: cron 表达式字符串,默认 `0 16 * * 1-5`
  - `full_retrain_frequency_days`: int,默认 5(每 5 个交易日触发一次全量)
- 实现:`croniter` 库解析下次触发时间,或使用 `APScheduler`(`BlockingScheduler` 或 `AsyncIOScheduler`)作为底层。
- 选型:`APScheduler` v3.x(基于 asyncio,与项目 async 风格一致);备选 `croniter` + 自定义调度循环(更轻量,但需手写 tick loop)。
- 触发判定逻辑(伪代码):
  ```
  if now >= next_cron_fire_time:
      if mode == "full" and (today - last_full_retrain_date) >= full_retrain_frequency_days:
          trigger("cron_full")
      elif mode == "incremental":
          trigger("cron_incremental")
  ```
- 交易日判定:使用 v0.1.0 data_loader 的交易日历(或独立的 trading_calendar 模块),非交易日跳过 cron 触发并打 INFO 日志。

---

<a id="fr-1700"></a>
### FR-1700 PSI 漂移检测

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模块路径:`trader_off.scheduler.drift.psi`。
- 函数 `compute_psi(baseline: np.ndarray, current: np.ndarray, n_bins: int = 10, epsilon: float = 1e-6) -> float`。
- 算法:将 baseline 与 current 各自分箱为 `n_bins`(默认 10)等频分箱,计算每个分箱的占比 `p_baseline`、`p_current`,然后:
  ```
  PSI = Σ (p_current_i - p_baseline_i) * ln(p_current_i / p_baseline_i)
  ```
- 当分箱占比为 0 时使用 `epsilon` 替换避免 log(0)。
- 阈值(可配置):`psi_threshold = 0.2`(行业标准);PSI > 0.2 视为显著漂移。
- 批量接口:`compute_feature_psi(baseline_df: pl.DataFrame, current_df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame`,返回列 `feature, psi, is_drift`(bool)。
- baseline:训练集每个特征的分箱边界;current:最近 N 日(默认 30)的同特征分布;两者均按资产池聚合(全市场统计,非单资产)。

---

<a id="fr-1800"></a>
### FR-1800 KS 漂移检测

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模块路径:`trader_off.scheduler.drift.ks`。
- 函数 `compute_ks_pvalue(baseline: np.ndarray, current: np.ndarray) -> float`,内部调用 `scipy.stats.ks_2samp(baseline, current)`。
- 阈值(可配置):`ks_pvalue_threshold = 0.05`(显著性水平 5%);p < 0.05 视为分布显著不同。
- 批量接口:`compute_feature_ks(baseline_df: pl.DataFrame, current_df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame`,返回列 `feature, ks_statistic, p_value, is_drift`(bool, p_value < threshold)。
- 当 baseline 或 current 全为 NaN 时,该特征记 `is_drift = False` + WARNING 日志(避免假阳性)。
- PSI 与 KS 是互补指标:PSI 关注分布形状变化,KS 关注整体分布差异;两者均显著才视为强漂移(见 FR-2600 组合判定)。

---

> **Lex [RESOLVED]:** 【阻塞-已知⚠️】FR-1900 Decided字段标记为⚠️，等待Round 2用户确认：在线Sharpe评估是否启用（当前默认关闭，仅评估在线IC）。Clarification Log（line 1089）已记录此事项。Sage需在Round 2获取用户确认后将Decided更新为✅（确认采纳当前默认值）或调整方案。
>> **Sage:** 用户已 Round 2 确认：「仅 IC 不评估 Sharpe」(IC only, no Sharpe)。已做以下修改:
>>> 1. Decided 字段由 ⚠️ 改为 ✅。
>>> 2. 移除「回测 Sharpe」作为监控指标(在线 Sharpe 评估默认关闭)。
>>> 3. 移除「状态字段保留 ⚠️」的描述,改为已锁定的 IC-only 决策。
>>>> 4. acceptance.md FR-1900 AC-4 已更新:断言改为 `not hasattr(decision, "sharpe") and "ic_only" in decision.notes`,验证 Sharpe 字段缺失且标注 ic_only。
>>> 5. Clarification Log 新增 Round 2 决策条目。

<a id="fr-1900"></a>
### FR-1900 性能衰减检测

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模块路径:`trader_off.scheduler.perf_monitor`。
- 监控指标(每日评估,**仅在线 IC**):
  - **在线 IC**:最近 20 个交易日的预测-真实收益 Pearson IC 均值。
  - **在线 Rank IC**:最近 20 个交易日的 Spearman Rank IC 均值。
- 在线 Sharpe 评估**默认关闭**:用户已确认 IC 检测预测能力衰减已足够,不引入子回测成本(避免每日子回测额外 ~60s 开销)。
- 数据来源:每日收盘后调用 `predict(model_version="latest", watchlist=universe, asof_date=today)` 生成预测,与次日开盘后实际收益对齐计算 IC。
- 衰减判定(可配置):
  - `ic_floor`: float,默认 0.005。IC 跌破此值视为失效。
  - `ic_drop_ratio`: float,默认 0.3(30%)。IC 较 30 日前下降 ≥ 30% 视为衰减。
- 触发:`trigger_perf_degradation()` 返回 `TriggerDecision(reason="perf_degradation", suggested_mode="full"|"incremental")`。
- 若未来需要回测 Sharpe 评估(成本敏感型场景),需新建 FR 提出,通过 v0.3+ 议题处理;本 FR 仅覆盖 IC-only 路径。

---

<a id="fr-2000"></a>
### FR-2000 手动触发 CLI / API

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- CLI 入口:
  - `trader-off retrain trigger --mode <full|incremental> [--reason <str>]`。
  - `trader-off retrain status`:显示当前活跃任务、历史最近 10 条任务(`task_id, mode, reason, start_time, end_time, status, new_version`)。
  - `trader-off retrain cancel --task-id <id>`:取消一个 pending/running 任务(running 任务等待当前 epoch 完成后中断,不强制 kill)。
- API 接口(异步,可选 REST 钩子):
  - `POST /retrain/trigger` body `{mode, reason}` 返回 `{task_id}`。
  - `GET /retrain/status` 返回 `{active_tasks, last_10_tasks}`。
  - `POST /retrain/cancel/{task_id}` 返回 `{cancelled: bool}`。
- REST 框架:轻量 `aiohttp` 应用(`trader_off.scheduler.api`),运行在独立端口(默认 8765),与调度循环共享进程;生产可拆为独立进程(配置项 `run_api: bool` 默认 False)。
- 手动触发的任务也必须经过与自动触发相同的审计与版本管理流程。

---

<a id="fr-2100"></a>
### FR-2100 全量重训

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 复用 v0.1.0 FR-0700 `train_model` + FR-0800 `save_model` 全量训练与序列化接口。
- 全量重训使用最近 `train_window_years`(默认 3,与 v0.1.0 FR-0600 一致)的数据。
- 重训完成后,新模型目录 `models/v0.X.Y.<build>/` 包含 v0.1.0 FR-0800 §2.1 全部文件:
  - `model.pkl, scaler.json, dropped_features.json, feature_names.json, metadata.json`。
- 版本号格式:`v{current_major}.{current_minor}.{build}`(与 v0.1.0 不同,v0.1.0 是 YYYYMMDD_HHMMSS);`build` 默认从 1 起递增,同一 major.minor 下唯一。
- 全量重训触发后,在 `models/registry.json` 中追加一条记录:
  ```json
  {
    "version": "v0.2.0.5",
    "created_at": "2026-07-17T16:00:00Z",
    "trigger": "cron_full" | "drift" | "perf_degradation" | "manual",
    "mode": "full",
    "task_id": "T-20260717-001",
    "git_commit_sha": "...",
    "metrics": {"test_ic_mean": 0.025, "test_rank_ic_mean": 0.035}
  }
  ```

---

<a id="fr-2200"></a>
### FR-2200 增量重训 (lightGBM refit)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 复用 v0.1.0 `train_model` 接口,但通过 `--init-model <version>` 参数加载已有模型作为初始 booster。
- lightGBM 增量重训使用 `lightgbm.Booster` 的 `refit(data, label, ...)` 方法(基于已有树结构继续训练,而非重新建树)。
- 增量数据范围:仅使用最近 N 个交易日(默认 5)的最新数据,加上已训练模型的最近样本(可选 warm-start 模式)。
- `n_estimators`:增量训练上限 100(全量默认 500),`learning_rate`:增量训练可略高(默认 0.1)。
- 增量重训产出版本号格式:`v{current_major}.{current_minor}.{build}.incr{N}`(如 `v0.2.0.5.incr3`),明确标注增量版次。
- 增量版的 `metadata.json` 额外字段:`parent_version`(父模型版本号,用于追溯)、`incr_seq`(本次增量编号,从 1 起)、`refit_iterations`(实际 refit 轮数)。

---

<a id="fr-2300"></a>
### FR-2300 模型版本管理与保留策略

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 版本注册表:`models/registry.json`,数组形式,每条记录格式见 FR-2100。
- 保留策略:
  - `keep_latest_n`: 默认 10,仅保留最近 N 个版本(按 `created_at` 降序)。
  - `keep_pinned_versions`: list[str],默认空数组;被钉住的版本永远保留(用于回滚)。
  - `keep_full_retrain_only`: bool,默认 True;若 True,增量版本过期后会被清理,只保留全量版本。
- 清理动作:调度器启动时(`start()` 末尾)与每次新版本落盘后,触发 GC,删除超出保留策略的模型目录(连同 `model.pkl, scaler.json, ...` 一起删除)。
- 回滚 API:`rollback_to(version: str) -> None`,将 `models/latest` 符号链接(若存在)指向目标版本,否则更新 `models/registry.json` 中 `current_version` 字段。
- `models/latest` 是软链/指针文件,指向当前部署版本;读取 `latest` 等价于读取 `registry.json["current_version"]`。

---

<a id="fr-2400"></a>
### FR-2400 自动部署到预测服务

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 重训通过验证后(默认验证条件:`test_ic_mean >= ic_floor`(FR-1900)),调度器自动更新 `models/registry.json["current_version"]` 为新版本号。
- 预测服务的版本加载机制:支持两种模式(配置项 `model_load_mode`):
  - **lazy** (默认):预测服务每次启动时读取 `registry.json["current_version"]`,加载最新版。
  - **hot-reload** (可选):预测服务运行中监听 `models/registry.json` 文件变化(`watchdog` 或 polling 默认 60s),自动重新加载模型。
- 部署失败处理:若新模型加载失败(版本目录缺失、文件损坏),预测服务保留旧版本并打 ERROR 日志,不中断服务。
- CLI:`trader-off deploy --version <str>` 手动触发部署(可选,通常自动)。
- 部署记录写入 `logs/deploy.log`,含:时间戳、from_version、to_version、status(success/failure)、耗时。

---

<a id="fr-2500"></a>
### FR-2500 调度状态持久化

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 持久化目录:`scheduler_state/`(项目根或配置指定),存储:
  - `last_tasks.json`:最近 N(N 默认 100)条任务的状态(`task_id, mode, reason, status, start_time, end_time, error`)。
  - `cron_fire_log.jsonl`:每次 cron 触发的记录(append-only,JSONL 格式),字段:`{timestamp, mode, triggered: bool, reason}`。
  - `drift_history.parquet`:每日漂移检测结果(PSI/KS 长期历史,供趋势分析)。
- 持久化时机:
  - 任务状态变更(p → r → s/f)时即时写入 `last_tasks.json`(atomic write:`temp file + rename`)。
  - 调度器启动时读取 `last_tasks.json`,恢复 pending/running 任务列表(running 任务标记为 failed + "scheduler restart" reason,因为未完成)。
- 并发安全:所有写操作通过 `asyncio.Lock` 保护,避免多写竞争。
- 断电恢复测试:模拟 kill -9,重启后调度器能从 `last_tasks.json` 恢复,无重复触发同一任务(由 `task_id` 唯一性保证)。

---

<a id="fr-2600"></a>
### FR-2600 漂移判定与重训决策

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 漂移检测由 `DriftDetector.evaluate() -> DriftDecision` 统一编排:
  ```python
  @dataclass
  class DriftDecision:
      should_retrain: bool
      reason: str
      suggested_mode: Literal["full", "incremental"]
      per_feature_stats: pl.DataFrame  # feature, psi, ks_statistic, p_value
  ```
- 决策规则(可配置):
  - **轻度漂移**(PSI > 0.1 或 KS p < 0.05 的特征数 ≥ 3 且 < 5):不触发重训,仅打 WARNING。
  - **中度漂移**(PSI > 0.2 的特征数 ≥ 1,或 KS p < 0.05 的特征数 ≥ 5):触发**增量**重训。
  - **重度漂移**(PSI > 0.5 的特征数 ≥ 3):触发**全量**重训。
- 漂移检测频率:每日 09:00(开盘前),通过 cron 配置(`scheduler.yaml` 中 `drift_check_cron`)。
- 检测结果输出到 `reports/drift_<date>/`:
  - `drift_report.json`:完整 per-feature PSI/KS 数值。
  - `drift_summary.csv`:是否触发重训 + 触发模式 + 原因。

---

<a id="fr-2700"></a>
### FR-2700 调度器 CLI 与配置

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- CLI 入口族:
  - `trader-off scheduler start --config <yaml>`:启动调度器(前台阻塞)。
  - `trader-off scheduler stop`:发送 SIGTERM,优雅停止(仅当 scheduler 以 daemon 模式运行时有效)。
  - `trader-off scheduler status`:打印调度器状态(下一触发、活跃任务、最近 10 条任务)。
  - `trader-off scheduler list-tasks [--limit N]`:列出历史任务。
- 配置文件 `configs/scheduler.yaml`(pydantic 校验):
  ```yaml
  scheduler:
    tick_interval_sec: 1
    max_concurrent_tasks: 1
    trading_calendar: "data_loader"  # 或独立 "exchange_calendar" 模块
  cron:
    full_retrain: "0 16 * * 1-5"
    incremental_retrain: "0 16 * * 1-5"
    full_retrain_frequency_days: 5
    drift_check_cron: "0 9 * * 1-5"
  drift:
    psi_threshold: 0.2
    ks_pvalue_threshold: 0.05
    psi_strong: 0.5
    ks_pvalue_strong: 0.01
    min_drift_features_incremental: 5
    min_drift_features_full: 3
  perf:
    ic_floor: 0.005
    ic_drop_ratio: 0.3
    ic_window: 20
  retention:
    keep_latest_n: 10
    keep_full_retrain_only: true
  deploy:
    model_load_mode: "lazy"  # 或 "hot-reload"
  api:
    run_api: false
    api_port: 8765
  ```
- 配置文件不存在或 schema 校验失败 → 抛 `ConfigValidationError`(与 v0.1.0 一致),退出码 4。

---

> **Lex [RESOLVED]:** 【阻塞】模块C头部FR范围不准确：第592行声明模块C覆盖FR-3000~FR-4400，但实际只定义了FR-3000~FR-4200（13个FR），FR-4300与FR-4400不存在。请Sage修正范围声明为FR-3000~FR-4200或补充缺失的FR。
>> **Sage:** 已修正:模块 C 头部范围由 `FR-3000 ~ FR-4400` 改为 `FR-3000 ~ FR-4200`(实际定义 13 个 FR,无缺失)。Mechanical fix。


### 模块 C — 组合优化器 (FR-3000 ~ FR-4200)

<a id="fr-3000"></a>
### FR-3000 协方差估计 — Ledoit-Wolf Shrinkage

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 函数 `estimate_covariance(returns_df: pl.DataFrame, method: Literal["sample", "ledoit_wolf"] = "ledoit_wolf") -> np.ndarray`,输入:
  - `returns_df`: 列 `asset, date, return`(每日收益率),资产为 columns,日期为 rows 的宽表。
  - 输出:形状 `(N_assets, N_assets)` 的协方差矩阵 `Σ`。
- Ledoit-Wolf 实现:可使用 `sklearn.covariance.LedoitWolf`(项目已依赖 scikit-learn);也可使用 `sklearn.covariance.ShrunkCovariance` + 自定义 shrinkage 强度。
- 默认 shrinkage 强度:由 `LedoitWolf` 自动估计(`assume_centered=False`)。
- 输入校验:若 `returns_df` 中某资产列全 NaN,该资产从协方差估计中剔除(并记录到 `assets_dropped.json`)。
- 最小样本数:历史窗口 < 30 个交易日 → 抛 `InsufficientDataError`(与 v0.1.0 FR-1200 一致)。
- 历史窗口默认 60 个交易日,可通过 `--cov-window` 配置。

---

<a id="fr-3100"></a>
### FR-3100 预期收益输入

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 输入来源:
  - **首选**:v0.1.0 `predict(...)` 输出(`predictions_<date>.csv`),列 `asset, score, rank`,直接作为预期收益 `mu = score`(或可选 `mu = zscore(score)` 标准化)。
  - **备选**:精选因子加权合成得分(由 `selected_factors.json` 提供每个因子的权重,通过 `compute_factor_score(features_df, weights)` 计算)。
- 函数 `build_expected_returns(predictions: pl.DataFrame, mode: Literal["raw", "zscore"] = "raw") -> dict[str, float]`,返回 `{asset: mu}`。
- 输入校验:资产数量与协方差矩阵的资产集合必须一致(`set(mu.keys()) == set(cov_assets)`);不一致 → 抛 `AssetMismatchError`。
- 数据缺失:预测中缺失的资产自动剔除(记录到 `assets_dropped.json`),不抛异常。

---

<a id="fr-3200"></a>
### FR-3200 行业映射接口

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

> **Lex [RESOLVED]:** 【阻塞】元数据表头拼写错误：第631行的表头 Decessed 应为 Decided。此拼写错误导致quote-check工具无法正确解析Decided字段（yaml.resolved返回空字符串），需Sage修正。
>> **Sage:** 已修正:`Decessed` → `Decided`。Mechanical fix。


- 配置文件 `configs/industry_map.csv`(pydantic 校验 schema):
  ```
  asset,industry
  000001.SZ,banking
  000002.SZ,real_estate
  ...
  ```
- 行业层级(v0.2.0 默认):一级行业(申万一级,约 30 个);未来可扩展多级。
- 函数 `load_industry_map(path: Path) -> dict[str, str]`,返回 `{asset: industry}`。
- 行业基准权重:默认等权(每个行业 `1/N_industries`);可通过 `--industry-benchmark` 参数覆盖为自定义 JSON。
- 缺失行业映射的资产:记录到 `assets_without_industry.json` + WARNING;在行业中性约束中视为独立"未分类"虚拟行业(权重上限严格 ≤ 0)。

---

<a id="fr-3300"></a>
### FR-3300 满仓约束 (Σw = 1)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 优化变量:`w ∈ R^N`,N 为候选资产数。
- 约束:`Σ_i w_i = 1`(所有权重之和为 1,无杠杆)。
- 这是 hard constraint,任何不满足 Σw=1 的解视为非法。
- 求解器内置该约束,不作为 CLI 参数暴露。

---

<a id="fr-3400"></a>
### FR-3400 long-only 约束

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 约束:`w_i >= 0` 对所有 i。
- 不允许做空(继承 v0.1.0 Constraints,与 A 股融券受限假设一致)。
- 求解器内置该约束。

---

<a id="fr-3500"></a>
### FR-3500 行业中性约束

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 行业中性定义为:**每个行业的组合权重偏离该行业基准权重 ≤ δ**。
- 公式:对每个行业 `j`,令 `W_j = Σ_{i ∈ industry_j} w_i`,`B_j` 为该行业基准权重,则:
  ```
  -delta_j <= W_j - B_j <= delta_j
  ```
- 默认 δ = 0.05(5%);可通过 `--industry-neutral-tol` 调整。
- 行业基准 `B_j` 默认等权(`1/N_industries`),可被 `--industry-benchmark` 覆盖。
- 行业分类来自 FR-3200。
- 当某行业偏离超过 δ 时,触发约束违反告警(见 FR-3700)。

---

<a id="fr-3600"></a>
### FR-3600 个股上限 10% 约束

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

> **Lex [RESOLVED]:** 【阻塞-已知⚠️】FR-3700 Decided字段标记为⚠️，等待Round 2用户确认：优化器求解库cvxpy是必装还是可选（当前默认cvxpy + scipy回退）。需确认cvxpy许可证Apache-2.0与安装体积~50MB是否可接受。Clarification Log（line 1090）已记录此事项。Sage需在Round 2获取用户确认后更新Decided字段。
>> **Sage:** 用户已 Round 2 确认「默认 cvxpy + scipy 回退」。已做以下修改:
>>> 1. Decided 字段由 ⚠️ 改为 ✅。
>>> 2. 描述改为已锁定的 cvxpy + ECOS 默认 + scipy.optimize.SLSQP 回退(移除 ⚠️ 备注)。
>>> 3. Decision Log 第 3 行更新措辞("首选 cvxpy" → "默认 cvxpy + scipy 回退")。
>>> 4. Clarification Log 新增 Round 2 决策条目(详见文末)。
>>> 5. acceptance.md FR-3700 AC-1/AC-3/AC-4 描述已含 cvxpy 默认与 scipy 回退,无需调整。


- 约束:`w_i <= 0.10` 对所有 i(单只个股权重不超过 10%)。
- 默认值 0.10,可通过 `--max-weight` 参数调整(范围 (0, 1])。
- 这是 hard constraint,超限视为非法。
- 求解器内置该约束。

---

<a id="fr-3700"></a>
### FR-3700 优化求解 — Max Sharpe

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 目标函数:Maximize Sharpe Ratio
  ```
  max_w (mu^T w - r_f) / sqrt(w^T Σ w)
  ```
  其中 `r_f` 默认 0(无风险利率,可配置),`Σ` 来自 FR-3000,`mu` 来自 FR-3100。
- 求解方法选择(用户已 Round 2 锁定):
  - **默认**:cvxpy + ECOS 求解器(凸优化专用库,自然支持二次规划约束建模,许可证 Apache-2.0 友好)。需要 `pip install cvxpy`(~50MB 安装体积可接受)。
  - **自动回退**:当 `import cvxpy` 抛 `ImportError` 时,自动切换到 `scipy.optimize.minimize`(SLSQP 方法,继承 v0.1.0 已有的 scipy 依赖),并打 INFO 日志 `"cvxpy unavailable, fallback to scipy.optimize.SLSQP"`。
- cvxpy 转换:Max Sharpe 等价于求解:
  ```
  min_w -mu^T w
  s.t. w^T Σ w <= 1
       Σw = 1, w >= 0, w_i <= 0.10, 行业中性约束
  ```
  (通过变量缩放 κ 处理,标准技巧;也可用 `cp.Problem(cp.Maximize(...), [...])` 直接建模)
- 求解器配置:
  - `solver`: cvxpy 默认 `ECOS`(无 cvxpy 时 SLSQP)。
  - `max_iterations`: 默认 1000。
  - `tolerance`: 默认 1e-6。

---

<a id="fr-3800"></a>
### FR-3800 约束违反检测与报告

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 函数 `check_constraints(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray, constraints: OptimizerConstraints) -> ConstraintReport`,对求解结果做后验校验。
- 检查项:
  - **long-only**: `min(weights) >= -1e-9`(允许数值误差)。
  - **满仓**:`abs(sum(weights) - 1.0) <= 1e-6`。
  - **个股上限**:`max(weights) <= max_weight + 1e-9`。
  - **行业中性**:对每个行业 `j`,`|W_j - B_j| <= delta_j + 1e-6`。
- 任一检查失败 → 在 `ConstraintReport.violations` 数组中追加 `{type, asset_or_industry, expected, actual, severity}`。
- 输出 `optimizer_report.json`(落盘到 `reports/portfolio_<ts>/`),含:
  ```json
  {
    "sharpe": 1.85,
    "expected_return": 0.12,
    "volatility": 0.065,
    "weights_sum": 1.0,
    "max_weight": 0.0998,
    "industry_exposures": {"banking": 0.083, "real_estate": 0.075, ...},
    "violations": []
  }
  ```

---

<a id="fr-3900"></a>
### FR-3900 与等权基线对比

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 基线定义:`equal_weight` — 组合中所有资产权重均为 `1/N`(当 top_k=20 时,每个为 0.05;当候选资产为 N 时,每个为 1/N)。
- 函数 `compare_to_baseline(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray, baseline_weights: np.ndarray = None) -> ComparisonReport`。
- 计算指标(预测/理论值,基于 mu 与 Σ):
  - `expected_return`: `mu^T w`
  - `volatility`: `sqrt(w^T Σ w)`
  - `sharpe`: `expected_return / volatility`(无风险利率 0)
  - `max_weight`: `max(w)`
  - `turnover`: `0.5 * sum(|w - w_prev|)`(首次运行时 w_prev = 0,turnover = 0.5)
- 输出 `portfolio_metrics.csv`,列 `metric, optimized, equal_weight, delta`。
- 若优化后 Sharpe 不高于等权基线(± 1e-4 容差),打 WARNING 日志(`"optimized sharpe < baseline, check inputs"`),但不报错。

---

<a id="fr-4000"></a>
### FR-4000 优化结果持久化

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 输出目录:`reports/portfolio_<ts>/`,由 CLI `--output` 指定(默认时间戳)。
- 产物清单:
  - `weights.csv`:列 `asset, weight, sector, mu, in_universe`(bool,是否在 universe 中)。
  - `optimizer_report.json`:见 FR-3800。
  - `portfolio_metrics.csv`:见 FR-3900。
  - `weights_diagnostics.json`:`{solver_status, solve_time_sec, iterations, dual_vars, asset_count}`。
  - `assets_dropped.json`:被剔除的资产(行业缺失、协方差 NaN 等)。
- 落盘原子性:先写到临时目录,所有文件生成完毕后 rename 到目标目录(防止半成品被消费)。
- 文件格式与命名与 v0.1.0 FR-1100/1200 风格一致(便于复用工具)。

---

<a id="fr-4100"></a>
### FR-4100 优化 CLI

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- CLI 入口:`trader-off optimize --predictions <csv> --industry-map <csv> [--constraints <yaml>] [--baseline <equal_weight|json_path>] [--output <dir>] [--cov-window <int>] [--max-weight <float>] [--industry-neutral-tol <float>]`。
- 必填:`--predictions`、`--industry-map`。
- 可选默认值:
  - `--baseline`: `equal_weight`
  - `--output`: `reports/portfolio_<ts>/`
  - `--cov-window`: 60
  - `--max-weight`: 0.10
  - `--industry-neutral-tol`: 0.05
- 退出码:
  - 0: 成功
  - 2: 输入文件缺失或 schema 校验失败
  - 3: 资产数量 < 5(优化无意义)
  - 4: 协方差矩阵非正定(尽管 Ledoit-Wolf 通常能保证)
- pydantic 校验所有参数,失败抛 `ConfigValidationError`(与 v0.1.0 一致)。
- stdout 输出关键进度:「加载 N 个资产」「协方差矩阵估计完成(方法=ledoit_wolf)」「求解完成(Sharpe=X.YZ, 耗时 N 秒)」「报告落盘到 <path>」。

---

<a id="fr-4200"></a>
### FR-4200 优化器作为 v0.1.0 策略输入 (OptimizedTopKStrategy)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 新策略类 `OptimizedTopKStrategy`,继承 `quantide.core.strategy.BaseStrategy`(与 v0.1.0 `LGBMTop20Strategy` 同基类)。
- 模块路径:`trader_off.strategies.optimized_topk`。
- 生命周期:
  - `init()`:加载优化器最新输出(`reports/portfolio_latest/weights.csv`)、读取 top_k 配置(默认 20)。
  - `on_day_open(tm)`:读取今日权重 → 对比当前持仓 → 通过 `broker.trade_target_pct(asset, weight)` 调仓。
  - `on_stop()`:释放资源。
- extra 参数记录:`{"reason": "optimized_topk", "weight": float, "version": <portfolio_ts>}`。
- 配置 `config/strategy/optimized_topk.yaml`:`{weights_path, top_k, min_weight}`。
- 当 `weights.csv` 不存在或 `last_updated` 距今 > 5 个交易日 → 打 WARNING 日志,降级使用 LGBMTop20Strategy 行为(等权 Top-K)。
- v0.1.0 的 `LGBMTop20Strategy` 保持不变,作为 fallback。

---

## Non-Functional Requirements

<a id="nfr-0100"></a>
### NFR-0100 性能预算 (P95 Latency)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

| 阶段                | 预算       | 测量方式                              |
| ------------------- | ---------- | ------------------------------------- |
| 单次因子挖掘(含评估)| ≤ 600 秒   | 50 资产 × 252 日 fixture,e2e 计时   |
| 单次全量训练流水线  | ≤ 300 秒   | 含因子计算 + 训练,e2e 计时           |
| 单次增量重训(refit) | ≤ 60 秒    | 5 个交易日增量数据                    |
| 单次预测(全候选因子)| ≤ 5 秒     | 4000 资产 × 最新一日,e2e 计时        |
| 单次回测(含优化)    | ≤ 600 秒   | 1 年回测窗口 + Max Sharpe 优化      |
| 单次漂移检测        | ≤ 30 秒    | 全特征 PSI + KS                       |
| 内存峰值            | ≤ 16 GB    | psutil 监控训练+预测+回测全过程       |

- 性能测试通过 `@pytest.mark.benchmark` 或 `tests/perf/` 自定义 timing harness 测量。
- 性能预算不通过 → CI 阻断合并(参考 v0.1.0 DoD)。
- 性能基准记录在 `tests/perf/baselines.json`,允许 5% 浮动。

---

<a id="nfr-0200"></a>
### NFR-0200 单元测试覆盖率 ≥ 97%

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 单元测试覆盖率必须 ≥ 97%(行覆盖,v0.2.0 比 v0.1.0 的 95% 提高 2 个百分点,反映 DoD 升级)。
- 使用 `pytest-cov` 收集覆盖率,CI 中必须显示 `TOTAL` 行 ≥ 97%。
- 排除规则继承 v0.1.0:`if __name__ == "__main__"` 块、纯数据 fixture、第三方 wrapper 类。
- 新增的排除项:CVXPY / scipy 求解器内部代码(只测我们包装的接口)。

---

<a id="nfr-0300"></a>
### NFR-0300 Mutation Testing ≥ 80% (mutmut)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 使用 `mutmut` 2.x 对 `trader_off/factor_mining/`、`trader_off/scheduler/`、`trader_off/portfolio/` 三个新模块运行 mutation testing。
- Mutation score ≥ 80%(杀死的 mutation / 总 mutation)。
- 配置 `pyproject.toml`:
  ```toml
  [tool.mutmut]
  paths_to_mutate = ["src/trader_off/factor_mining/", "src/trader_off/scheduler/", "src/trader_off/portfolio/"]
  backup = false
  runner = "uv run pytest tests/unit/{factor_mining,scheduler,portfolio} -x --no-cov"
  ```
- CI 中 mutation score < 80% → 阻断合并。
- Mutation 工具链变更需更新 `pyproject.toml` 与 CI 脚本。

---

<a id="nfr-0400"></a>
### NFR-0400 文档同步与 ADR

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- API 文档自动生成:使用 `griffe` 或 `mkdocstrings`(决策见 ADR-001)。
- 至少 3 个 ADR 存放于 `docs/adr/`,以 markdown 格式:
  - **ADR-001**: cvxpy vs scipy.optimize 求解器选型(关联 FR-3700)。
  - **ADR-002**: 调度器持久化方案(内存 vs APScheduler JobStore,关联 FR-2500)。
  - **ADR-003**: 因子表达式 DSL 选型(参数化模板 vs 自研解析器,关联 FR-0100/0200)。
- 每个 ADR 包含:标题、状态(Proposed/Accepted/Superseded)、上下文、决策、后果(参考 [MADR](https://adr.github.io/madr/) 模板)。
- `architecture.md` / `interfaces.md` / `docs/` 三者必须一致;不一致时以 `architecture.md` 为权威源。
- 文档同步检查脚本:`scripts/check_docs_sync.py`,CI 中运行,任何引用了不存在的 API/模块名 → 失败。

---

<a id="nfr-0500"></a>
### NFR-0500 代码风格与异步约定 (继承 v0.1.0)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 严格遵循 PEP8,line length ≤ 100(继承 v0.1.0 NFR-0400)。
- 优先使用 `async/await`,调度器、API、IO 方法必须 async。
- 使用 `uv` 作为包管理工具,`pyproject.toml` 维护依赖。
- Python 版本 ≥ 3.11。
- ruff + bandit 继承 v0.1.0 配置(`select = ["E", "F", "W", "I", "N", "UP", "T201"]`)。

---

<a id="nfr-0600"></a>
### NFR-0600 日志规范 (继承 v0.1.0)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 统一使用 `loguru.logger`。
- 日志格式:`{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}`。
- INFO 级:因子挖掘进度、调度触发、训练/预测/优化完成。
- WARNING 级:漂移告警、性能衰减、约束违反、IC 异常。
- ERROR 级:模型加载失败、协方差奇异、求解不收敛。
- 日志同时输出到 stdout 和 `logs/<module>.log`。
- 新增模块日志文件:`logs/factor_mining_*.log`、`logs/scheduler_*.log`、`logs/portfolio_*.log`。

---

<a id="nfr-0700"></a>
### NFR-0700 安全审查 (继承 v0.1.0)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 启用 M-SECURITY 阶段审查(`security_audit = "enabled"` in project.toml,继承 v0.1.0)。
- 必须满足:
  - 无 hard-coded credentials(token、password、api_key)。
  - 文件 IO 必须校验路径(防止 path traversal)。
  - 模型反序列化使用 joblib + 白名单(不允许 pickle.load 直接加载任意对象)。
  - CLI 输入必须经过 pydantic 校验(参数类型、范围、长度)。
  - YAML 加载使用 `yaml.safe_load`,禁止 `yaml.load`。
  - 调度器 API (FR-2000) 默认仅监听 localhost(127.0.0.1),外部访问需显式 `--api-host 0.0.0.0`(并打 WARNING)。
- 提交前必须运行 `bandit -r trader_off/` 并消除所有 HIGH 级 issue。

---

<a id="nfr-0800"></a>
### NFR-0800 数据可重现性 (继承 v0.1.0)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 所有随机性来源必须设置 `random_state=42`(lightGBM、特征抽样、数据切分等)。
- 每次重训/挖掘/优化的输出 `metadata.json` 必须记录:
  - `git_commit_sha`(7-40 位 hex)
  - `python_version`(如 `3.11.5`)
  - `package_versions`(dict,含 lightgbm、polars、cvxpy、scipy、apscheduler 等新增依赖)
  - `random_state`(42)
  - `config_snapshot`(本次运行时的完整 yaml 内容快照)
- 所有 CLI 命令必须支持 `--config <yaml>` 参数,配置覆盖优先级:CLI 参数 > config 文件 > 默认值。
- fixture 数据版本化管理:`tests/fixtures/v0.2.0/` 与代码版本绑定,fixture 文件 SHA256 校验和写入 `tests/fixtures/v0.2.0/MANIFEST.json`。

---

<a id="nfr-0900"></a>
### NFR-0900 调度可靠性与并发安全

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 调度器同一时刻最多 1 个重训任务在跑(`max_concurrent_tasks=1`,可配置)。
- 任务状态变更(p → r → s/f)通过 `asyncio.Lock` 保护。
- 持久化文件使用 atomic write(临时文件 + rename),避免半写入状态。
- 调度器异常退出(kill -9 或 OOM)后重启,能恢复 pending 任务列表,标记 running 中断的任务为 failed。
- 任务幂等性:同一 task_id 重试不会触发两次实际训练(由 `models/registry.json` 中的 version 唯一性保证)。
- 集成测试:`tests/integration/test_scheduler_resilience.py`,模拟 kill -9 → 重启 → 验证任务状态正确恢复。

---

<a id="nfr-1000"></a>
### NFR-1000 向后兼容 — v0.1.0 模型/策略仍可用

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- v0.1.0 的 16 个 FR + 7 个 NFR 全部继承,`trader_off` 包结构不变。
- v0.1.0 已序列化的模型(`models/<YYYYMMDD_HHMMSS>/`)仍能被 `load_model(...)` 加载,即使没有 v0.2.0 新增字段(`factor_template_version`、`selected_factor_count`)。
- v0.1.0 的 `LGBMTop20Strategy` 保留,不删除。
- v0.1.0 的 `trader-off train|predict|backtest|feature-importance` CLI 命令保留;新增命令不修改原有命令的签名。
- 向后兼容性集成测试:`tests/integration/test_v010_compat.py`,加载 v0.1.0 fixture 模型 + 用 v0.2.0 代码 predict,断言输出 schema 一致。

---

## Constraints and Assumptions

### 假设

- 用户已通过 uv 安装 millionaire 框架(`uv pip install millionaire`)。
- 测试环境使用 fixture 数据,不依赖真实数据库;真实数据接入 millionaire 的 `quantide.data.fetchers` 后即可生效。
- v0.2.0 部署在 Linux/macOS,Windows 不在 v0.2.0 范围内(APScheduler 在 Windows 上的行为可能略有差异)。
- 单机部署,不考虑分布式调度(多机调度为 v0.3+ 议题)。
- 基本面数据(v0.2.0 第 4 类因子)由外部数据源提供,本项目不实现 fetcher;缺失时自动跳过该类因子。
- cvxpy 求解器在目标平台可用(cvxpy 安装体积较大,若不可用自动回退到 scipy.optimize.SLSQP,见 FR-3700)。

### 约束

- 仅支持日线(`FrameType.DAY`)频率,分钟线 / 周线 / 月线不在 v0.2.0 范围(继承 v0.1.0 约束)。
- 调度器仅支持 A 股交易日历(沪深 3000+ 资产),不支持 24×7 加密资产或外汇。
- 组合优化器仅支持 long-only(继承 v0.1.0 Constraints),不做空。
- 协方差估计仅支持样本协方差 + Ledoit-Wolf shrinkage,因子风险模型为 v0.3+ 议题。
- 优化器仅支持 Max Sharpe,不支持最小方差 / Risk Parity / Black-Litterman 等其他目标(为 v0.3+ 议题)。

### 排除项(v0.2.0 明确不做)

- 实盘交易对接(沿用 v0.1.0 排除项)。
- 分钟线 / 高频信号(继承 v0.1.0 排除项)。
- 因子风险模型 / 多级行业分类 / Black-Litterman 等高级组合构建(为 v0.3+ 议题)。
- 分布式调度 / 多机协调(为 v0.3+ 议题)。
- 实盘监控 / A/B 测试框架 / 自动回滚触发(为 v0.3+ 议题)。
- 因子非线性变换 / 自动特征交叉(本版本仅支持参数化模板枚举)。

---

## Decision Log(决策说明)

| 决策项 | story.md / 用户描述 | spec.md 采纳 | 原因 |
|---|---|---|---|
| 因子表达式 DSL | 模板 + 参数化枚举 | dataclass `FactorTemplate` + `enum int_range/choice/bool` 参数空间 | 避免自研解析器,降低 v0.2.0 实现复杂度;同时保留 v0.3+ 升级到完整 DSL 的扩展点 |
| 协方差估计 | 简单协方差(Ledoit-Wolf 备选) | **默认 Ledoit-Wolf**(可通过 `--cov-method sample` 切换) | Ledoit-Wolf 是无偏 + 收缩的稳健默认,样本协方差在 N 大时表现良好但小样本不稳定;提供两种以备灵活 |
| 优化器求解库 | 未指定 | **默认 cvxpy + ECOS**,不可用时自动回退 scipy.optimize.SLSQP(用户 Round 2 锁定) | cvxpy 自然支持二次规划约束建模,许可证 Apache-2.0 友好,~50MB 体积可接受;SLSQP 作为零依赖兜底;ADR-001 详述 |
| 调度器持久化 | 调度状态 | 文件系统 JSONL + parquet(`scheduler_state/`),APScheduler JobStore 备选 | 文件系统持久化简单可调试,APScheduler JobStore 更"开箱即用"但需 SQLAlchemy;ADR-002 详述 |
| 调度器并发模型 | 未指定 | 单进程 asyncio,`max_concurrent_tasks=1` | 训练是 GPU/CPU 密集型,并发反而降低效率;单任务串行最简单可控 |
| 自动部署触发 | 重训通过验证后自动部署 | 默认 lazy 加载(下次 predict 时读取最新版本);可选 hot-reload | lazy 模式零侵入,hot-reload 需要 watchdog 进程增加复杂度;默认优先简洁 |
| 漂移检测组合 | PSI / KS 分别检测 | 组合判定:PSI + KS 同时显著才视为强漂移 | 单一指标容易误报,组合判定降低误报率;FR-2600 详述 |
| 性能衰减监控 | 在线 IC / Sharpe | **仅在线 IC**(用户 Round 2 锁定,Sharpe 评估不开) | 子回测 Sharpe 成本不必要(每日子回测 ~60s 开销),在线 IC 已能反映预测能力衰减 |
| 因子挖掘输出格式 | YAML / JSON / HTML / MD | YAML(注册表) + JSON(精选集) + HTML(主报告) + MD(精简报告) | YAML/JSON 便于程序消费,HTML/MD 便于人读 |
| v0.1.0 命令兼容性 | 继承 | `train`/`predict`/`backtest`/`feature-importance` 命令保留;新增 `--factor-registry` 参数 | 不破坏现有用户脚本;新参数可选 |

---

## Clarification Log

- 2026-07-17 Sage Step 1(本轮):经审阅用户已锁定的细节与 story.md,**未提出额外问题**。所有 v0.2.0 决策已通过 story.md + 用户追加说明覆盖,无 genuine blocker:
  - 因子表达式 DSL → 锁定为「参数化模板 + 合法组合枚举」(不需要自研解析器)
  - 调度器持久化 → 采用文件 JSONL + parquet 持久化(详见 Decision Log 与 ADR-002 占位)
  - 优化器库选型 → 锁定 cvxpy + scipy.optimize 回退(详见 Decision Log 与 ADR-001 占位)
  - millionaire API 缺口 → 不依赖新 API:组合优化器输出权重落盘,再训练调度复用 v0.1.0 已有 `train_model`/`save_model`/`load_model`,预测服务通过 `predict(model_version, ...)` 显式传 version
  - 性能衰减监控的 Sharpe 评估 → 默认关闭(FR-1900 ⚠️ 字段保留,Round 2 确认)

- 待 Round 2 进一步确认的 ⚠️ 项(状态 ⚠️):
  - **FR-1900 在线 Sharpe 评估是否启用**:当前默认关闭,仅评估在线 IC。Round 2 与用户确认是否需要子回测 Sharpe(成本 +60s/日),或仅 IC 已足够。
  - **FR-3700 优化器求解库(cvxpy 必选 vs 可选)**:当前默认 cvxpy + scipy 回退,Round 2 与用户最终确认 cvxpy 是否必装(许可证 Apache-2.0,体积 ~50MB)。

- 2026-07-17 Sage Round 2(Step 3):用户确认两项 Round 2 待澄清项,均采纳 spec.md 中已记录的默认方案,**无需调整设计**:
  - **FR-1900 在线 Sharpe 评估** → 用户确认「仅 IC 不评估 Sharpe」。理由:IC 检测预测能力衰减已足够,子回测 Sharpe 评估成本不必要(每日子回测额外 ~60s 开销)。已移除 FR-1900 中的 Sharpe 监控指标描述,Decided 字段由 ⚠️ 升至 ✅。acceptance.md AC-4 更新为验证"无 Sharpe 字段 + ic_only 注释"。
  - **FR-3700 优化器求解库选型** → 用户确认「默认 cvxpy + scipy.optimize.SLSQP 回退」。理由:cvxpy 表达力强(凸优化建模自然)、许可证 Apache-2.0 友好,~50MB 安装体积可接受。Decided 字段由 ⚠️ 升至 ✅。详见 Decision Log 第 3 行已更新。
