# trader-off v0.1.0 — lightGBM 短时 A 股定价模型 — Spec

- **Spec ID**: v0.1.0-001-lgbm-asset-pricing
- **Created**: 2026-07-16
- **Status**: Draft
- **关联 PRD/story**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/story.md`

> **职责切分**: 本文档只描述需求本身（FR/NFR 描述 + 元数据）。
> 验收标准（可观察、可断言的通过条件）放在 `acceptance.md` 中。
> 测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。

## User Stories

### US-0010
story: 作为一名量化研究员，我希望能够基于 A 股日线数据训练一个 lightGBM 模型来预测个股未来 5 个交易日的收益率，并将预测信号接入 millionaire 回测系统，以便评估该模型在历史数据上的表现，并可视化回测结果与预测能力。
priority: P0

## Usage Scenarios

### scenario-0010 训练并回测

1. 量化研究员在本地执行 `trader-off train --config configs/train.yaml`，触发特征工程、标签构建、模型训练。
2. 训练完成后，模型被序列化到 `models/<version>/model.pkl`，并写入 `models/<version>/metadata.json`（含训练时间、数据范围、超参数、IC 指标）。
3. 量化研究员执行 `trader-off backtest --model models/<version> --strategy lgbm_top20 --start 2023-01-01 --end 2024-12-31`，启动回测。
4. 回测结束后生成两份报告：
   - `reports/backtest_<ts>/summary.json`（年化、夏普、最大回撤、胜率）
   - `reports/backtest_<ts>/prediction_quality.csv`（每日 IC、Rank IC、5 层分组收益）

### scenario-0020 预测服务（CLI 评分）

1. 量化研究员准备一个 watchlist CSV（列：`asset,frame_type`），执行 `trader-off predict --model models/<version> --watchlist watchlist.csv --date 2024-12-31`。
2. 预测服务读取当日及历史行情，计算特征，调用模型，输出 `predictions_<date>.csv`（列：`asset,score,rank`），按分数降序排列。

## Functional Requirements

> **格式约定（必读）**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`（大写、4 位补零）+ {标题} 开头，紧接三列元数据表（Valid / Testable / Decided），再写需求描述；FR 之间用 `---` 分隔。
>
> **编号约定（必读）**: FR 编码为 **4 位**，首轮草稿按 **100 起步、步长 100** 编号（FR-0100, FR-0200, …）；后续 review 按 10 步长插入；二轮后改为连续编号。

---

<a id="fr-0100"></a>
### FR-0100 特征工程 — 动量类指标

> **Lex** [RESOLVED]: PRD 覆盖缺口：story.md line 19 明确「支持扩展自定义特征」，但 spec FR-0100/0200/0300 仅定义固定的 15 个指标，无任何可扩展性 FR（如特征注册表、插件接口）。建议补充可扩展性 FR 或在排除项中明确 v0.1.0 不支持自定义特征扩展。


| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 依据日线 OHLCV 数据，按资产（asset）分组计算 N 日动量特征：N ∈ {5, 10, 20, 60}。
- 公式：`ret_N = close[t] / close[t-N] - 1`。
- 输出列名固定为 `ret_5`, `ret_10`, `ret_20`, `ret_60`。
- 每个特征必须有 schema 校验（dtype=float64），缺失值（NaN）保留为 NaN，由下游缺失值处理器统一处理。

---

<a id="fr-0200"></a>
### FR-0200 特征工程 — 波动率类指标

> **Lex** [RESOLVED]: AC-FR0200-3 数值不一致：给定 close 序列仅 10 个交易日，则 daily_returns 最多 9 个非空值。vol_10 使用 min_periods=10 (FR-0200 规定 min_periods=N)，在 9 个非空值上无法产出非空结果，故 vol_10[9] 应为 NaN 而非「有值」。建议将 fixture 改为 11 个交易日（10 个收益），或调整期望。



| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 依据日线收益率序列，按资产分组计算 N 日波动率：N ∈ {10, 20, 60}。
- 公式：`vol_N = std(daily_returns, N)`，其中 daily_returns = close[t]/close[t-1] - 1。
- 输出列名固定为 `vol_10`, `vol_20`, `vol_60`。
- 计算时使用 polars 的 rolling std（min_periods=N），保证前 N-1 个值为 NaN。

---

<a id="fr-0300"></a>
### FR-0300 特征工程 — 成交量类指标

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 计算 N 日平均换手率与量价相关性：N ∈ {5, 10, 20}。
- 平均换手率：`turnover_N = mean(turnover, N)`，列名 `turnover_5`, `turnover_10`, `turnover_20`。
- 量价相关性：`volume_price_corr_N = rolling_corr(volume, close, N)`，列名 `vp_corr_5`, `vp_corr_10`, `vp_corr_20`。
- 当 `turnover` 字段缺失或全为 NaN 时，相关列全部填 NaN 并打 WARNING 日志（不影响其他资产计算）。

---

<a id="fr-0400"></a>
### FR-0400 特征标准化与缺失值处理

> **Lex** [RESOLVED]: AC-FR0400-1 逻辑问题：AC 称「第 2 行 asset 列有 NaN」并测试前向填充，但 FR-0400 规定前向填充「按 asset 分组」。若 asset 列本身为 NaN，则分组键未定义，fill_null(forward) 行为不可预期。应改为某个特征列为 NaN（而非 asset 列）来测试前向填充。



| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 缺失值处理策略：先用前向填充（按 asset 分组、`fill_null(strategy="forward")`），剩余缺失值用 0 填充。
- 标准化：训练集上对每个特征做 z-score（保存均值与标准差到 `scaler.json`），预测时使用相同的 scaler 参数。
- scaler 参数必须序列化（`scaler.json`），版本与模型绑定（同一目录存放），不得在推理时重新计算。
- 输入数据全部缺失（整列 NaN）的特征必须从数据集中剔除，并记录到 `dropped_features.json`。

---

<a id="fr-0500"></a>
### FR-0500 标签构建 — 未来 5 日收益率

> **Lex** [RESOLVED]: 涨跌停阈值 0.095 域正确性问题：A 股涨跌停规则因板块而异——主板 10%、创业板/科创板 20%、ST 股 5%。固定阈值 0.095 会误过滤创业板/科创板的正常波动（9.5% < 20% 限价），且无法捕获 ST 股 5% 涨跌停。建议按 asset 元数据（板块/ST 标记）动态判定限价，或在 Constraints 中明确 v0.1.0 仅处理主板 10% 限价并记录假设。



| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 标签 `label = close[t+5] / close[t] - 1`，按 asset 分组向后位移。
- 当 `t+5` 不存在（数据末尾）或 `close[t+5]` 为 NaN（停牌/退市），该样本标签记为 NaN，训练时由 lightGBM 通过 `init_score` 或样本权重机制跳过（不删除样本以保留时序完整性）。
- 标签分布统计（mean、std、min、p1、p99、max）必须输出到 `label_stats.json` 用于回归诊断。
- 涨跌停板过滤：使用数据源（fetcher）返回的 `limit_up` / `limit_down` 布尔字段（列名 `limit_up`, `limit_down`，dtype=bool）作为过滤依据。当 `limit_up=True` 或 `limit_down=True` 时将该样本标签置为 NaN，记录到 `limit_up_down_filter.json`。若 fetcher 不提供这两个字段，则跳过该过滤步骤并打 WARNING 日志（由 Archer 在 implementation 阶段确认 fetcher 能力）。

---

<a id="fr-0600"></a>
### FR-0600 训练数据准备 — 滚动 walk-forward

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 切分策略：滚动 walk-forward。窗口定义：
  - 训练集：每期使用过去 3 个完整年度（如 2018-2020）
  - 验证集：当期上半年（如 2021H1）
  - 测试集：当期下半年（如 2021H2）
- 每一期（roll）必须输出独立的训练/验证/测试 parquet 文件（命名 `train_<year>.parquet` 等），便于复现与单元测试。
- 默认起始年份与结束年份通过 `--start-year` 与 `--end-year` CLI 参数传入。
- 调用 millionaire 的 `quantide.data.helper.train_test_split` 助手时仅使用其实现参考，不强制走其接口（因为本系统需要按年滚动）。

---

<a id="fr-0700"></a>
### FR-0700 模型训练 — lightGBM 回归

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 算法：lightGBM 回归器（`lightgbm.LGBMRegressor`）。
- 默认损失函数：`regression_l2`（L2）；可通过 `--loss` 参数切换为 `regression`（L1）或 `quantile`（需配合 `--alpha`）。
- 默认超参数：
  - `objective=regression`
  - `num_leaves=63`
  - `learning_rate=0.05`
  - `feature_fraction=0.8`
  - `bagging_fraction=0.8`
  - `bagging_freq=5`
  - `n_estimators=500`
  - `early_stopping_rounds=50`
- 训练时使用验证集做 early stopping；最终模型以 best_iteration 重新训练或直接保存 best_iteration 的 booster。
- 训练日志（loss、best_iteration）必须写入 `train.log`，使用 loguru。

---

<a id="fr-0800"></a>
### FR-0800 模型序列化与版本管理

> **Lex** [RESOLVED]: AC-FR0800-2 事实错误：version 默认格式 YYYYMMDD_HHMMSS（如 20260101_120000）共 15 个字符（8 位日期 + 1 个下划线 + 6 位时间），AC 写「13 位字符串」不正确，应改为 15 位。



| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 模型目录结构：
  ```
  models/<version>/
    model.pkl            # joblib 序列化的 Booster
    scaler.json          # 标准化参数
    dropped_features.json
    feature_names.json   # 特征顺序（保证推理时列序一致）
    metadata.json        # 训练时间、数据范围、超参数、IC 指标
  ```
- `version` 默认值为时间戳 `YYYYMMDD_HHMMSS`，可通过 `--version` 显式指定。
- 模型加载提供 `load_model(version: str) -> ModelArtifact` 接口，返回包含 booster、scaler、feature_names 的 dataclass。
- 重复训练到相同 version 必须失败并报错（防止覆盖）。

---

<a id="fr-0900"></a>
### FR-0900 预测服务

> **Lex** [RESOLVED]: AC-FR0900-4 一致性问题：predict 服务是独立函数 (FR-0900 签名 predict(model_version, watchlist, asof_date))，数据来源为 quantide.data.fetchers (见 NFR-0100 AC-1、FR-1100)，并不经过 broker。AC 中 mock broker.get_history 与设计不符，应改为 mock fetcher / data loader。



| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 入口：`predict(model_version: str, watchlist: list[str], asof_date: date) -> pl.DataFrame`。
- 行为：
  1. 加载指定版本的模型与 scaler。
  2. 根据 `asof_date` 读取每只资产在该日及之前 N 个交易日的行情（N = 训练时所需的最大 lookback，默认 120）。
  3. 计算特征（FR-0100/0200/0300）并应用 scaler。
  4. 调用 booster 预测分数。
  5. 输出 DataFrame，列：`asset, score, rank`，按 score 降序排列，rank 从 1 开始。
- 缺失行情的资产必须记录到 `predict_skipped.json` 且不出现在结果 DataFrame 中，并打 WARNING 日志。
- CLI 入口：`trader-off predict ...`（参数见 scenario-0020）。

---

<a id="fr-1000"></a>
### FR-1000 策略集成 — LGBMTop20Strategy

> **Lex** [RESOLVED]: 内部一致性问题：Decision Log (line 406) 称选 on_day_open 后「需要在 init 中预计算特征」，但 FR-1000 init() 描述仅为「加载模型、读取预测配置、初始化持仓缓存」，未提及特征预计算；且 on_day_open 调用 predict 服务 (FR-0900) 时由 predict 内部计算特征。建议澄清：删除 Decision Log 中「预计算特征」表述，或在 FR-1000 init 中补充特征预计算需求。



| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 策略类继承 `quantide.core.strategy.BaseStrategy`（millionaire 框架的策略基类）。
- 类名：`LGBMTop20Strategy`，完整路径：`trader_off.strategies.lgbm_top20.LGBMTop20Strategy`。
- 生命周期覆盖：
  - `init()`：加载模型、读取预测配置（top_k=20）、初始化持仓缓存。
  - `on_day_open(tm)`：调用预测服务（FR-0900），获取今日的目标持仓列表，生成目标仓位权重（等权 1/top_k），通过 `broker.trade_target_pct` 调仓。
  - `on_stop()`：释放模型引用（允许 GC 回收）。
- 在 on_day_open 中下单时，必须通过 `extra` 参数记录决策快照：`{"reason": "lgbm_top20", "score": float, "rank": int, "model_version": str}`，便于事后归因。
- 配置文件：`config/strategy/lgbm_top20.yaml`，至少包含 `model_version`、`top_k`、`min_score`（可选，低于该分数不买入，默认 -inf）。

---

<a id="fr-1100"></a>
### FR-1100 millionaire 回测接入

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- CLI 入口：`trader-off backtest --model <version> --strategy lgbm_top20 --start <YYYY-MM-DD> --end <YYYY-MM-DD> --capital <float>`。
- 回测引擎：使用 millionaire 的 BacktestRunner，注入：
  - `broker = BacktestBroker`（继承 `quantide.service.base_broker.Broker`）
  - `strategy = LGBMTop20Strategy(broker, config)`
  - 数据源：使用 `quantide.data.fetchers` 提供的 A 股日线 fetcher（具体实现由 millionaire 框架提供，本项目不重写）。
- 回测结束时输出：
  - 持仓序列 `positions_<ts>.parquet`
  - 交易记录 `trades_<ts>.parquet`
  - 净值曲线 `nav_<ts>.parquet`
- 回测结果汇总到 `reports/backtest_<ts>/summary.json`。

---

<a id="fr-1200"></a>
### FR-1200 回测报告 — 绩效指标

> **Lex** [RESOLVED]: AC-FR1200-2 计算错误：净值序列 [100,110,105,120,115] 中 105 出现在 120 之前，不构成从 120 到 105 的回撤。正确最大回撤应为 (105-110)/110 = -0.0455（从 110 到 105），而非 AC 所写的 -0.125。建议修正期望值与断言。



| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 输出 `summary.json`，至少包含：
  - `annualized_return`: float（年化收益率）
  - `sharpe_ratio`: float（年化夏普比率，无风险利率 = 0）
  - `max_drawdown`: float（最大回撤，负数，例如 -0.15 表示 -15%）
  - `win_rate`: float（日度胜率）
  - `total_trades`: int（总交易次数）
  - `avg_turnover`: float（日均换手率）
- 指标计算函数 `compute_performance_metrics(nav: pl.DataFrame) -> dict` 必须为纯函数，可独立单元测试。
- 净值数据不足 30 个交易日时必须抛出 `InsufficientDataError` 并中止报告生成。

---

<a id="fr-1300"></a>
### FR-1300 预测能力评估

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 评估函数 `evaluate_predictions(predictions: pl.DataFrame, labels: pl.DataFrame) -> PredictionQualityReport`，输入预测与真实标签（按 asset + date 对齐），输出：
  - `ic_ts`: DataFrame，列 `date, ic`（每日 Pearson IC）
  - `rank_ic_ts`: DataFrame，列 `date, rank_ic`（每日 Spearman Rank IC）
  - `ic_mean`, `ic_std`, `rank_ic_mean`, `rank_ic_std`：float
  - `layered_returns`: DataFrame，列 `layer, mean_return`（5 层回测的平均收益）
- IC 计算函数必须为纯函数，并提供 `__all__` 导出 `ic_pearson`、`ic_spearman`、`compute_layered_returns`。
- IC / Rank IC 时间序列结果写入 `prediction_quality.csv`；5 层回测结果写入 `layered_returns.csv`。

---

<a id="fr-1400"></a>
### FR-1400 特征重要性分析

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 训练完成后，从 booster 提取 `model.feature_importance(importance_type='gain')`，按降序排列。
- 输出 `feature_importance.csv`，列 `feature, importance, rank`。
- 提供 CLI：`trader-off feature-importance --model <version>`，控制台打印 Top 20 特征表格。
- 当 booster 为空或无特征时（如空模型），输出空 CSV 并打 INFO 日志，不报错。

---

<a id="fr-1500"></a>
### FR-1500 e2e 端到端流程

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 必须提供 1 个 e2e 测试 `tests/e2e/test_lgbm_pipeline.py`，覆盖完整链路：
  1. 准备 fixture 数据（10 只虚拟股票 × 60 个交易日，从 fixtures 加载）。
  2. 执行 `train` → 生成模型目录。
  3. 执行 `predict` → 生成 predictions。
  4. 执行 `backtest` → 生成 reports。
  5. 断言 reports 目录存在且 `summary.json` 含全部必需字段。
- e2e 测试运行时间 ≤ 60 秒。
- e2e 测试可在 CI 中无外部依赖运行（使用 fixture 数据）。

---

<a id="fr-1600"></a>
### FR-1600 可视化输出

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 回测结束后必须生成 3 个静态图表（PNG 格式），输出到 `reports/backtest_<ts>/figures/`：
  1. `nav_curve.png`：净值曲线图。X 轴为日期，Y 轴为组合净值（含 baseline 沪深 300 净值曲线作为对比，至少一个对比基准）。
  2. `ic_timeseries.png`：IC 时间序列图。X 轴为日期，Y 轴为每日 IC（Pearson）和 Rank IC（Spearman）双折线，含 IC 均值参考线。
  3. `feature_importance_top20.png`：特征重要性 Top 20 横向条形图。Y 轴为特征名，X 轴为 importance（gain），按重要性降序。
- 实现库：使用 `matplotlib`（>= 3.7），禁止引入 plotly / bokeh / dash 等交互式可视化库（v0.1.0 仅静态输出）。
- 图表必须使用 `Agg` backend（无 GUI 渲染），保证 CI / Docker 容器中可生成。
- 图表像素尺寸默认 `figsize=(10, 6)`、`dpi=120`，可通过 `--figsize` 与 `--dpi` CLI 参数覆盖。
- 输出目录 `figures/` 不存在时自动创建。
- 中文字体：在容器/CI 中通过 `matplotlib.font_manager` 注册 fallback 字体（`SimHei` / `Noto Sans CJK SC`），缺失时降级为英文标签并打 WARNING 日志。

---

## Non-Functional Requirements

<a id="nfr-0100"></a>
### NFR-0100 数据规模与时间范围

> **Lex** [RESOLVED]: AC-NFR0100-1 可测试性冲突：该 AC 要求从真实 fetcher 加载并断言资产数 >= 4000，但 Constraints 明确「测试环境使用 fixture 数据」，FR-1500 e2e 仅用 10 只股票。此 AC 无法在 CI（无外部依赖）中验证。建议明确该 AC 为集成环境专用，或改为 mock fetcher 返回 >=4000 资产的单元测试。




| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 数据集必须覆盖 A 股全市场（约 4000+ 只股票）。
- 训练数据时间范围默认 2015-01-01 至训练当日（向前回溯 3 年作为单期训练窗口）。
- 行情频率：日线（1d），对应 `FrameType.DAY`。
- 数据字段必须包含：`asset, date, open, high, low, close, volume, turnover, adj_factor`。

---

<a id="nfr-0200"></a>
### NFR-0200 预测能力阈值（学术参考线）

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 测试集上：
  - IC（Pearson）均值 > 0.02 视为「有预测能力」，作为软目标记录到 `metadata.json`。
  - Rank IC（Spearman）均值 > 0.03 视为「有预测能力」，作为软目标。
- 不作为强制通过条件（模型可能因市场状态未达到），但若完全为 0 或为负，必须打 WARNING 日志提示用户检查特征工程。

---

<a id="nfr-0300"></a>
### NFR-0300 单元测试覆盖率

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 单元测试覆盖率必须 ≥ 95%（行覆盖）。
- 使用 `pytest-cov` 收集覆盖率，CI 中必须显示 `TOTAL` 行 ≥ 95%。
- 排除规则：`if __name__ == "__main__"` 块、纯数据 fixture、第三方 wrapper 类（如 millionaire 框架对象）。

---

<a id="nfr-0400"></a>
### NFR-0400 代码风格与异步约定

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 严格遵循 PEP8，line length ≤ 100。
- 优先使用 `async/await`，策略类中所有 IO 方法（`init`、`on_day_open`、`on_bar`、`on_day_close`、`on_stop`）必须为 async（与 `BaseStrategy` 签名一致）。
- 使用 `uv` 作为包管理工具，`pyproject.toml` 维护依赖。
- Python 版本 ≥ 3.11。

---

<a id="nfr-0500"></a>
### NFR-0500 日志规范

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 统一使用 `loguru.logger`。
- 日志格式：`{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}`。
- INFO 级：训练/预测/回测进度。
- WARNING 级：数据缺失、涨跌停过滤、IC 异常。
- ERROR 级：模型加载失败、数据 schema 不匹配。
- 日志同时输出到 stdout 和 `logs/<module>.log`。

---

<a id="nfr-0600"></a>
### NFR-0600 安全审查

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- 启用 M-SECURITY 阶段审查（`security_audit = "enabled"` in project.toml）。
- 必须满足：
  - 无 hard-coded credentials（token、password、api_key）。
  - 文件 IO 必须校验路径（防止 path traversal）。
  - 模型反序列化使用 joblib + 白名单（不允许 pickle.load 直接加载任意对象）。
  - CLI 输入必须经过 pydantic 校验（参数类型、范围、长度）。
- 提交前必须运行 `bandit -r trader_off/` 并消除所有 HIGH 级 issue。

---

<a id="nfr-0700"></a>
### NFR-0700 数据可重现性

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- lightGBM 训练必须设置 `random_state=42`（默认值，可通过 `--seed` 覆盖）。
- 所有 CLI 命令必须支持 `--config <yaml>` 参数，配置覆盖优先级：CLI 参数 > config 文件 > 默认值。
- 训练结束后，`metadata.json` 必须记录完整的 `git_commit_sha`、`python_version`、`package_versions`。

---

## Constraints and Assumptions

### 假设
- 用户已通过 uv 安装 millionaire 框架（`uv pip install millionaire` 或 git 依赖）。
- 测试环境使用 fixture 数据，不依赖真实数据库。
- 真实数据接入 millionaire 的 `quantide.data.fetchers` 后即可生效，本项目不修改 fetcher 实现。

### 约束
- 模型只支持日线（`FrameType.DAY`）一种频率，分钟线 / 周线 / 月线均不在 v0.1.0 范围内。
- 策略只支持 long-only（A 股融券受限），不做空。
- 策略只支持 Top-K 等权，不支持市值加权、行业中性、风险平价等高级组合构建。
- 模型类型只支持 lightGBM（regression 家族），XGBoost / NN / Transformer 不在 v0.1.0 范围。

### 排除项（v0.1.0 明确不做）
- 实盘交易对接（v0.2+）。
- 因子挖掘自动化（v0.2+）。
- 分钟线 / 高频信号（v0.3+）。
- 组合优化器（v0.4+）。
- 模型再训练调度（v0.2+）。
- 自定义特征扩展 / 特征注册表（v0.2+）。v0.1.0 特征集固定为 FR-0100/0200/0300 定义的 15 个指标。

> **Lex** [RESOLVED] (T-010): PRD 覆盖缺口：story.md 多处提到「可视化回测结果与预测能力」(line 13、69) 及「绩效分析面板」(line 38)。经 Sage Round 1 澄清：v0.1.0 范围扩展为生成 3 个静态图表（净值曲线、IC 时序、特征重要性 Top 20），详见新增 FR-1600。


---

## Decision Log（决策说明）

| 决策项 | story.md 描述 | spec.md 采纳 | 原因 |
|---|---|---|---|
| 预测触发回调 | `on_day_close` | `on_day_open` | 经 Sage 与用户澄清（Round 1），用户选择 `on_day_open`，语义上等价（基于昨日收盘数据生成今日开盘前决策）。特征计算由预测服务（FR-0900）在 `on_day_open` 调用时按需执行，策略 `init` 仅负责加载模型与配置。 |
| 特征范围 | 仅列「动量/波动率/成交量」三类 | 明确为 15 个具体指标 | Sage 提问后用户选定 MVP 最小集，便于 e2e 测试与后续扩展。 |
| 切分策略 | 未指定 | 滚动 walk-forward | 用户选择，避免单一窗口过拟合。 |
| 交易规则 | top/bottom 分位数 | Long-only Top 20 等权 | 用户选择，A 股融券受限，简化 v0.1.0。 |
| 评估阈值 | 未指定 | IC>0.02, Rank IC>0.03（学术参考线） | 用户选择，作为软目标记录。 |

---

## Clarification Log

- 2026-07-16 Round 1（已关闭）：
  - Q1: 特征工程具体范围？A: MVP 最小集（15 个指标）。
  - Q2: 时序切分策略？A: 滚动 walk-forward。
  - Q3: 交易规则？A: Long-only Top 20 等权。
  - Q4: 评估阈值？A: IC>0.02, Rank IC>0.03。
  - Q5: 预测触发回调？A: on_day_open（与 story.md 不一致，已记录于 Decision Log）。
  - Q6: 分层回测？A: 需要 5 层。

- 2026-07-16 Round 2 / Lex Stage 1（已全部 RESOLVED，9 个 inline threads + T-010）：
  - **T-001（FR-0100 自定义特征扩展）**：Lex 指 v0.1.0 未覆盖自定义特征扩展。Sage 在排除项追加「自定义特征扩展 / 特征注册表（v0.2+）。v0.1.0 特征集固定为 FR-0100/0200/0300 定义的 15 个指标。」
  - **T-002（FR-0200 AC-3 数值不一致）**：Lex 指出 10 个 close → 9 个 returns，vol_10[9] 应为 NaN。Sage 将 AC-3 fixture 改为 11 个交易日（产生 10 个 returns）。
  - **T-003（FR-0400 AC-1 逻辑问题）**：Lex 指出 asset 列不能为 NaN。Sage 将 AC-1 改为「第 3 行 f2 列有 NaN（asset 列完整）」，按 asset 分组的前向填充。
  - **T-004（FR-0500 涨跌停阈值）**：Lex 指出 0.095 单一阈值不覆盖创业板/科创板 20% 与 ST 5%。Sage Round 1 与用户确认改用 fetcher 提供的 limit_up/limit_down 布尔字段，FR-0500 描述已修改。
  - **T-005（FR-0800 AC-2 字符数）**：Lex 修正 YYYYMMDD_HHMMSS 为 15 字符。Sage 已修正 AC-2 为「15 字符串」，新增断言 `len(version) == 15 and version[8] == "_"`。
  - **T-006（FR-0900 AC-4 数据来源）**：Lex 指出 predict 不通过 broker 拿数据。Sage 已将「mock broker.get_history」改为「mock DataLoader.get_history」。
  - **T-007（FR-1000 init 预计算特征）**：Lex 指出 Decision Log 与 FR-1000 init 描述不一致。Sage 删除 Decision Log 中「预计算特征」表述，改为「特征计算由预测服务（FR-0900）在 on_day_open 调用时按需执行」。
  - **T-008（FR-1200 AC-2 max_drawdown）**：Lex 修正期望值为 -0.0455（peak=110, trough=105）。Sage 已修正并补充实现要求「按 (nav[t] - max(nav[0:t+1])) / max(nav[0:t+1]) 在所有 t 上取最小值」。
  - **T-009（NFR-0100 AC-1 测试性冲突）**：Lex 指出 ≥4000 资产断言无法在 CI 中验证。Sage 将 AC-1 拆分为 mock 单元测试（4500 虚拟资产）+ `@pytest.mark.integration` 集成测试；原 AC-2/AC-3 顺延为 AC-3/AC-4；AC-4 增加了 limit_up/limit_down 字段要求。
  - **T-010（PRD 可视化覆盖缺口）**：Lex 指出 story.md 提到「可视化」与「绩效分析面板」但 spec 未覆盖。Sage Round 1 与用户确认新增 FR-1600 可视化输出（3 个静态 PNG：净值曲线、IC 时序、特征重要性 Top 20，使用 matplotlib + Agg backend）。
