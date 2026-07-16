# lightGBM 短时 A 股定价模型 — Architecture Design

- **Spec ID**: v0.1.0-001-lgbm-asset-pricing
- **Created**: 2026-07-16
- **Related spec**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/spec.md`
- **Related test-plan**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/test-plan.md`
- **Related interfaces**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/interfaces.md`

> 本文是 Devon 实现的唯一架构依据。模块边界、依赖方向、技术选型与权衡均在本文锁定；interfaces.md 定义外部可观察契约，二者共同构成 dev/test 闭环。

---

## 1. 系统概览

### 1.1. 组件关系图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        trader-off (本项目)                          │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐     │
│  │ features │   │  labels  │   │   data   │   │  training    │     │
│  │ 动量/波动 │   │ 5日收益  │   │loader/   │   │ LGBM训练/    │     │
│  │ 率/成交量 │   │ 涨跌停   │   │split/    │   │ 序列化       │     │
│  └────┬─────┘   └────┬─────┘   │preprocess│   └──────┬───────┘     │
│       │              │         └────┬─────┘          │             │
│       │              │              │                │             │
│       └──────────────┴──────┬───────┴────────────────┘             │
│                             ▼                                      │
│                      ┌──────────────┐        ┌──────────────┐      │
│                      │  prediction  │───────▶│  strategies  │      │
│                      │  预测服务    │        │ LGBMTop20    │      │
│                      └──────┬───────┘        └──────┬───────┘      │
│                             │                       │              │
│                             │              ┌────────▼────────┐     │
│                             │              │    backtest     │     │
│                             │              │ runner/metrics  │     │
│                             │              └────┬───────┬────┘     │
│                             │                   │        │          │
│              ┌──────────────┼───────────────────┘        │          │
│              ▼              ▼                            ▼          │
│      ┌────────────┐  ┌───────────┐              ┌──────────────┐   │
│      │ evaluation │  │importance │              │visualization │   │
│      │IC/分层     │  │特征重要性 │              │ 3 PNG 图表   │   │
│      └────────────┘  └───────────┘              └──────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            cli  (train / predict / backtest / fi)           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  utils (logging / exceptions / config / security)           │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ 适配器/继承
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  millionaire 框架 (外部依赖)                        │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ quantide.core. │  │ quantide.    │  │ quantide.data.fetchers │  │
│  │ strategy.      │  │ service.     │  │  (A 股日线行情源)       │  │
│  │ BaseStrategy   │  │ base_broker. │  │                        │  │
│  └────────────────┘  │ Broker       │  └────────────────────────┘  │
│                      └──────────────┘                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  BacktestRunner  (回测编排引擎)                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2. 端到端数据流

```
raw OHLCV (fetcher/DataLoader)
   │
   ├─[训练]──▶ features.compute_* ──▶ data.fit_scaler_and_impute ──▶ labels.build_labels
   │                                                                    │
   │            data.prepare_walk_forward_splits ◀─────────────────────┘
   │                    │
   │                    ▼
   │            training.train_model ──▶ training.save_model ──▶ models/<version>/
   │                                                                    │
   └─[预测]──▶ features.compute_* ──▶ data.transform(scaler) ──▶ booster.predict
                ▲                                                        │
                │                                                        ▼
   prediction.predict(model_version, watchlist, asof_date) ◀──── predictions[asset,score,rank]
                │
   [回测]       ▼
   strategies.LGBMTop20Strategy.on_day_open ──▶ broker.trade_target_pct
                │
                ▼
   BacktestRunner (millionaire) ──▶ positions/trades/nav parquet
                │
                ├──▶ backtest.compute_performance_metrics ──▶ summary.json
                ├──▶ evaluation.evaluate_predictions ──▶ prediction_quality.csv, layered_returns.csv
                ├──▶ importance.extract_feature_importance ──▶ feature_importance.csv
                └──▶ visualization.render_* ──▶ figures/*.png
```

---

## 模块划分

> 本节是 interfaces.md `modules` 列的权威来源。Shield 据此判定跨模块接口（≥2 模块 → 集成测试覆盖）。

### 2.1. 模块清单与职责

| # | 模块路径                        | 职责                                          | 实现 FR/NFR              |
| - | ------------------------------- | --------------------------------------------- | ------------------------ |
| 1 | `trader_off.features`           | 动量/波动率/成交量特征计算（15 个指标）        | FR-0100, FR-0200, FR-0300|
| 2 | `trader_off.labels`             | 未来 5 日收益率标签构建、涨跌停过滤、标签统计  | FR-0500                  |
| 3 | `trader_off.data`               | 数据加载适配器、walk-forward 切分、标准化/缺失值 | FR-0400, FR-0600, NFR-0100|
| 4 | `trader_off.training`           | lightGBM 训练、模型序列化与版本管理            | FR-0700, FR-0800         |
| 5 | `trader_off.prediction`         | 预测服务（加载模型→算特征→打分→排序）          | FR-0900                  |
| 6 | `trader_off.strategies`         | LGBMTop20Strategy（继承 BaseStrategy）         | FR-1000                  |
| 7 | `trader_off.backtest`           | 回测编排、绩效指标计算                         | FR-1100, FR-1200         |
| 8 | `trader_off.evaluation`         | IC/Rank IC/分层收益评估                        | FR-1300                  |
| 9 | `trader_off.importance`         | 特征重要性提取                                 | FR-1400                  |
| 10| `trader_off.visualization`      | 3 个静态 PNG 图表渲染                          | FR-1600                  |
| 11| `trader_off.cli`                | CLI 入口（train/predict/backtest/feature-importance）| FR-0700/0900/1100/1400 |
| 12| `trader_off.utils`              | 日志、异常、配置、安全（路径校验/反序列化白名单）| NFR-0500, NFR-0600, NFR-0700 |

### 2.2. 包目录结构

```
trader_off/
├── __init__.py
├── features/
│   ├── __init__.py            # 导出 compute_momentum/volatility/volume_features
│   ├── momentum.py            # FR-0100
│   ├── volatility.py          # FR-0200
│   └── volume.py              # FR-0300
├── labels/
│   ├── __init__.py            # 导出 build_labels, compute_label_stats
│   └── builder.py             # FR-0500
├── data/
│   ├── __init__.py            # 导出 DataLoader, prepare_walk_forward_splits, fit_scaler_and_impute, transform
│   ├── loader.py              # DataLoader 适配器（封装 quantide.data.fetchers）NFR-0100/FR-0900
│   ├── splits.py              # FR-0600
│   └── preprocess.py          # FR-0400
├── training/
│   ├── __init__.py            # 导出 train_model, save_model, load_model, ModelArtifact
│   ├── trainer.py             # FR-0700
│   └── model_io.py            # FR-0800
├── prediction/
│   ├── __init__.py            # 导出 predict
│   └── service.py             # FR-0900
├── strategies/
│   ├── __init__.py            # 导出 LGBMTop20Strategy
│   └── lgbm_top20.py          # FR-1000
├── backtest/
│   ├── __init__.py            # 导出 run_backtest, compute_performance_metrics
│   ├── runner.py              # FR-1100
│   └── metrics.py             # FR-1200
├── evaluation/
│   ├── __init__.py            # __all__ = [ic_pearson, ic_spearman, compute_layered_returns, evaluate_predictions, PredictionQualityReport]
│   ├── ic.py                  # FR-1300 纯函数
│   └── report.py              # FR-1300
├── importance/
│   ├── __init__.py            # 导出 extract_feature_importance
│   └── extractor.py           # FR-1400
├── visualization/
│   ├── __init__.py            # 导出 render_nav_curve, render_ic_timeseries, render_feature_importance
│   └── render.py              # FR-1600
├── cli/
│   ├── __init__.py            # main() 入口分发
│   ├── train.py               # FR-0700/0800 CLI
│   ├── predict.py             # FR-0900 CLI
│   ├── backtest.py            # FR-1100 CLI
│   └── feature_importance.py  # FR-1400 CLI
└── utils/
    ├── __init__.py
    ├── logging.py             # setup_logger (NFR-0500)
    ├── exceptions.py          # 全部自定义异常
    ├── config.py              # 配置加载（CLI > yaml > 默认）NFR-0700
    └── security.py            # 路径校验 + joblib 白名单 (NFR-0600)
```

### 2.3. 依赖关系（调用方向）

> 箭头 `A ──▶ B` 表示 A 依赖（调用）B。依赖单向，禁止循环。

```
cli ──▶ training, prediction, backtest, importance, data, utils
backtest ──▶ strategies, evaluation, importance, visualization, data, utils
strategies ──▶ prediction, training(model_io), data(loader), utils
prediction ──▶ training(model_io), features, data(preprocess), data(loader), utils
training ──▶ data(preprocess), labels, utils
data ──▶ features, utils
evaluation ──▶ utils
importance ──▶ utils
visualization ──▶ importance, utils
utils ──▶ (无内部依赖，仅第三方)
```

**层次约束**：
- `utils` 是最底层，不依赖任何 `trader_off` 内部模块
- `features` / `labels` 是纯计算层，仅依赖 `utils`
- `data` 依赖 `features`（特征计算用于预测时按需调用）
- `cli` 是最顶层编排层，可依赖所有业务模块
- **禁止反向依赖**：`features` 不得依赖 `training`；`strategies` 不得依赖 `backtest`

---

## 3. 技术选型

### 3.1. 运行时依赖

| 依赖          | 版本约束     | 用途                              | License    |
| ------------- | ------------ | --------------------------------- | ---------- |
| python        | >= 3.11      | 运行时（async/await、typing）      | PSF        |
| polars        | >= 1.0       | 数据处理（OHLCV、特征、标签）       | MIT        |
| lightgbm      | >= 4.3       | 回归模型训练/预测                  | MIT        |
| numpy         | >= 1.26      | 数值计算                           | BSD-3      |
| loguru        | >= 0.7       | 结构化日志                         | MIT        |
| pydantic      | >= 2.7       | CLI 参数校验                       | MIT        |
| joblib        | >= 1.4       | 模型序列化（安全反序列化）          | BSD-3      |
| matplotlib    | >= 3.7       | 静态图表（Agg backend）            | PSF        |
| millionaire   | >= 0.1       | 回测框架（BaseStrategy/Broker/fetchers）| 待确认     |
| pyyaml        | >= 6.0       | 配置文件解析                       | MIT        |

### 3.2. 开发时依赖

| 依赖            | 版本约束     | 用途                              |
| --------------- | ------------ | --------------------------------- |
| pytest          | >= 8.0       | 测试框架                           |
| pytest-cov      | >= 5.0       | 覆盖率                             |
| pytest-asyncio  | >= 0.23      | 异步测试                           |
| pytest-mock     | >= 3.12      | mock                               |
| pytest-timeout  | >= 2.3       | e2e 超时保护（AC-FR1500-02）       |
| pytest-socket   | >= 0.7       | 禁网断言（AC-FR1500-03）           |
| scipy           | >= 1.13       | Ground Truth IC 参考               |
| ruff            | >= 0.5       | lint / 风格                        |
| bandit          | >= 1.7       | 安全扫描                           |

### 3.3. 工具链

| 工具   | 用途                          |
| ------ | ----------------------------- |
| uv     | 包管理（pyproject.toml）       |
| ruff   | lint + format（line length 100）|
| pytest | 测试运行（asyncio_mode=auto）   |
| bandit | 安全扫描（-ll，无 HIGH）        |

---

## 4. 关键权衡

### 4.1. polars vs pandas

| 维度     | 决策：polars                          | 放弃：pandas                       |
| -------- | ------------------------------------- | ---------------------------------- |
| 解决问题 | 大规模 A 股全市场（4000+ 股）特征计算性能 | —                                  |
| 优势     | 惰性求值、内存效率、一致 Float64 dtype、rolling 原生支持 | 生态最大、第三方库兼容性最好       |
| 风险     | 部分 ML 库期望 pandas（lightGBM 需 to_numpy 转换）；社区小于 pandas | 慢、内存高                         |
| 缓解     | 训练/预测时统一 `df.to_numpy()` 喂 lightGBM；polars 表达式覆盖全部 rolling 需求 | —                                  |

### 4.2. async 策略方法

| 维度     | 决策：async def（init/on_day_open/on_bar/on_day_close/on_stop）| 放弃：同步方法                     |
| -------- | ----------------------------------------------------------- | ---------------------------------- |
| 解决问题 | 与 millionaire `BaseStrategy` 签名一致（NFR-0400 强制）       | —                                  |
| 优势     | 框架兼容、未来可扩展异步 IO（实盘数据拉取）                   | 简单、无需 pytest-asyncio           |
| 风险     | 测试复杂度增加；event loop 管理                              | 不兼容 BaseStrategy，回测无法注入   |
| 缓解     | pytest-asyncio `asyncio_mode=auto`；策略内 IO 用 await       | —                                  |

### 4.3. 模型版本管理策略

| 维度     | 决策：时间戳目录 `models/<YYYYMMDD_HHMMSS>/`，禁止覆盖       | 放弃：单文件覆盖 / 语义版本        |
| -------- | ----------------------------------------------------------- | --------------------------------- |
| 解决问题 | 多版本共存、可复现、防误覆盖                                 | —                                 |
| 优势     | 简单直观、目录隔离 scaler/metadata                           | 语义清晰                          |
| 风险     | 无语义信息（不知哪版最优）；目录膨胀                          | 覆盖丢失历史                      |
| 缓解     | metadata.json 记录 IC 指标供人工选版；定期清理               | —                                 |

### 4.4. Scaler 绑定到模型版本

| 维度     | 决策：scaler.json 与 model.pkl 同目录，推理时复用不重算      | 放弃：推理时重算 / 全局 scaler     |
| -------- | ----------------------------------------------------------- | --------------------------------- |
| 解决问题 | 防止 train-serving skew（训练/预测标准化不一致）             | —                                 |
| 优势     | 保证一致性、可复现                                           | 灵活                              |
| 风险     | scaler 与模型强耦合，换模型必须换 scaler                     | skew 风险                         |
| 缓解     | `load_model` 返回 `ModelArtifact` 含 scaler，predict 强制使用 | —                                 |

### 4.5. lightGBM early stopping

| 维度     | 决策：验证集 early stopping（best_iteration），保存 best booster | 放弃：固定 n_estimators 跑满      |
| -------- | ------------------------------------------------------------ | --------------------------------- |
| 解决问题 | 防过拟合、自动选树数                                          | —                                 |
| 优势     | 自适应、泛化更好                                              | 简单                              |
| 风险     | 需验证集；可能过早停止                                        | 过拟合                            |
| 缓解     | `early_stopping_rounds=50`；train.log 记录 best_iteration    | —                                 |

### 4.6. walk-forward 滚动切分

| 维度     | 决策：按年滚动，3 年训练窗 / H1 验证 / H2 测试               | 放弃：单次 train/test 切分         |
| -------- | ----------------------------------------------------------- | --------------------------------- |
| 解决问题 | 减少单窗口过拟合、模拟真实滚动投资                            | —                                 |
| 优势     | 时序完整、多期评估                                            | 快                                |
| 风险     | 计算量大（7 期 × 全市场）                                     | 过拟合                            |
| 缓解     | 每期独立 parquet 便于单期单测；e2e 用小 fixture               | —                                 |

### 4.7. matplotlib Agg backend

| 维度     | 决策：`matplotlib.use("Agg")`，静态 PNG                      | 放弃：plotly/bokeh 交互式          |
| -------- | ----------------------------------------------------------- | --------------------------------- |
| 解决问题 | CI/Docker 无 X server 生成图表                               | —                                 |
| 优势     | 无 GUI 依赖、确定性强                                         | 交互体验好                        |
| 风险     | 无交互；中文字体需 fallback                                   | 体积大、CI 难                     |
| 缓解     | 字体 fallback（SimHei/Noto Sans CJK SC），缺失降级英文 + WARNING | —                                 |

### 4.8. joblib + 白名单反序列化

| 维度     | 决策：joblib.load + 类型白名单（仅 Booster + 自定义 dataclass）| 放弃：pickle.load                  |
| -------- | ----------------------------------------------------------- | --------------------------------- |
| 解决问题 | 防反序列化任意对象攻击（NFR-0600）                            | —                                 |
| 优势     | 安全                                                        | 灵活                              |
| 风险     | 白名单需维护                                                | 任意代码执行风险                  |
| 缓解     | 白名单集中管理；加载后类型断言                               | —                                 |

### 4.9. DataLoader 适配器（隔离 millionaire fetcher）

| 维度     | 决策：`DataLoader` 抽象层封装 `quantide.data.fetchers`        | 放弃：直接调 fetcher              |
| -------- | ----------------------------------------------------------- | --------------------------------- |
| 解决问题 | 测试环境可注入 fixture 替身（C1 约束）                        | —                                 |
| 优势     | 解耦、可测试                                                 | 少一层                            |
| 风险     | 额外抽象层                                                   | 直接但不可测                      |
| 缓解     | 适配层薄（仅转发 + schema 校验）                              | —                                 |

---

## 5. millionaire 集成架构

### 5.1. 集成方式

trader-off 通过**继承 + 适配器**两种方式接入 millionaire：

1. **继承**：`LGBMTop20Strategy` 继承 `quantide.core.strategy.BaseStrategy`，实现其生命周期回调。
2. **适配器**：`DataLoader` 封装 `quantide.data.fetchers`，提供统一 `get_history(asset, end_date, count)` 接口，便于测试注入替身。
3. **注入**：回测时由 `cli.backtest` 构造 `BacktestBroker`（millionaire 提供）+ `LGBMTop20Strategy` + DataLoader，注入 `BacktestRunner`。

### 5.2. 生命周期映射

```
BacktestRunner 驱动每日循环:
  for each trading_day in [start, end]:
      await strategy.on_day_open(tm)     # ← LGBMTop20 调 predict → broker.trade_target_pct
      ... 撮合 (millionaire 内部) ...
      await strategy.on_bar(...)          # ← LGBMTop20 不实现（noop）
      await strategy.on_day_close(...)    # ← LGBMTop20 不实现（noop）
  await strategy.on_stop()                # ← 释放模型引用
```

**init 阶段**：`LGBMTop20Strategy.__init__(broker, config)` → `await init()` 加载模型（`load_model`）、读配置（top_k/min_score）、初始化持仓缓存。

**on_day_open 阶段**：
1. 调用 `predict(model_version, watchlist, tm.date())` 获取 `DataFrame[asset, score, rank]`
2. 取 rank ≤ top_k 且 score ≥ min_score 的标的为目标持仓
3. 对目标持仓调 `broker.trade_target_pct(asset, 1/top_k, extra={...})`
4. 对非目标的现有持仓调 `broker.trade_target_pct(asset, 0, extra={...})` 清仓

### 5.3. 边界判定（与 test-plan §6.2 一致）

| millionaire 组件                      | 性质       | 测试处理                                  |
| ------------------------------------- | ---------- | ----------------------------------------- |
| `quantide.data.fetchers`（行情源）     | 外部依赖   | DataLoader 替身（fixture parquet）替换     |
| `BacktestBroker.trade_target_pct`     | 框架接口   | 单测 mock 记录调用；e2e 用真实 BacktestBroker |
| `BacktestRunner`（撮合/调度）          | 被测框架   | 不 mock，e2e 用真实 Runner + fixture 数据  |
| `BaseStrategy`（生命周期）             | 被测基类   | 不 mock，LGBMTop20 真实继承               |

### 5.4. 配置文件

`config/strategy/lgbm_top20.yaml`（FR-1000）：
```yaml
model_version: "v1"      # 必填，对应 models/<version>/
top_k: 20                # 必填，Top-K 等权
min_score: -inf          # 可选，低于该分数不买入，默认 -inf
```

---

## 6. 数据流详图

### 6.1. 训练管线流程

```
cli.train --config configs/train.yaml
  │
  ├─▶ config.load(yaml) ──▶ 合并 CLI > yaml > 默认
  │
  ├─▶ DataLoader.get_history(start, end) ──▶ raw OHLCV DataFrame
  │
  ├─▶ prepare_walk_forward_splits(data, start_year, end_year, train_window=3)
  │       └─▶ 每期输出 train_<year>.parquet / valid_<year>.parquet / test_<year>.parquet
  │
  ├─▶ for each roll:
  │     ├─▶ features.compute_momentum/volatility/volume_features(ohlcv) ──▶ X
  │     ├─▶ labels.build_labels(close_df, horizon=5, filter_limit_up_down) ──▶ y
  │     ├─▶ data.fit_scaler_and_impute(X_train) ──▶ scaler, dropped_features.json
  │     ├─▶ data.transform(X_valid, scaler) ──▶ X_valid_scaled
  │     ├─▶ training.train_model(X_train, y_train, X_valid, y_valid, params) ──▶ booster
  │     └─▶ training.save_model(booster, scaler, metadata, version) ──▶ models/<version>/
  │
  └─▶ importance.extract_feature_importance(booster, feature_names) ──▶ feature_importance.csv
```

### 6.2. 预测流程

```
predict(model_version, watchlist, asof_date)
  │
  ├─▶ training.load_model(model_version) ──▶ ModelArtifact(booster, scaler, feature_names, metadata)
  │
  ├─▶ for asset in watchlist:
  │     └─▶ DataLoader.get_history(asset, asof_date, count=120) ──▶ ohlcv
  │            └─▶ 不足 120 日 ──▶ 记 predict_skipped.json + WARNING，跳过
  │
  ├─▶ features.compute_*(ohlcv) ──▶ X
  ├─▶ data.transform(X, scaler) ──▶ X_scaled（按 feature_names 对齐列序）
  ├─▶ booster.predict(X_scaled) ──▶ scores
  │
  └─▶ 排序：score 降序，rank 从 1 ──▶ DataFrame[asset, score, rank]
```

### 6.3. 回测流程

```
cli.backtest --model <version> --strategy lgbm_top20 --start --end --capital
  │
  ├─▶ 构造 BacktestBroker(capital)
  ├─▶ 构造 LGBMTop20Strategy(broker, config)
  ├─▶ 构造 DataLoader（fetcher 适配）
  │
  ├─▶ BacktestRunner.run(strategy, broker, data_loader, start, end)
  │       └─▶ 每日 await strategy.on_day_open(tm) → broker.trade_target_pct
  │       └─▶ 输出 positions_<ts>.parquet / trades_<ts>.parquet / nav_<ts>.parquet
  │
  ├─▶ backtest.compute_performance_metrics(nav_df) ──▶ summary.json
  ├─▶ evaluation.evaluate_predictions(predictions, labels) ──▶ prediction_quality.csv, layered_returns.csv
  ├─▶ importance.extract_feature_importance ──▶ feature_importance.csv
  └─▶ visualization.render_* ──▶ figures/nav_curve.png, ic_timeseries.png, feature_importance_top20.png
```

---

## 7. 错误处理

### 7.1. 自定义异常体系

所有异常定义于 `trader_off/utils/exceptions.py`，继承 `Exception`。

| 异常                          | 触发场景                          | 对应 FR/NFR    | 测试 AC               |
| ----------------------------- | --------------------------------- | -------------- | --------------------- |
| `InsufficientDataError`       | nav < 30 日，绩效计算中止          | FR-1200        | AC-FR1200-03          |
| `ModelVersionExistsError`     | save_model 到已存在 version 目录   | FR-0800        | AC-FR0800-03          |
| `PathTraversalError`          | 文件 IO 路径逃逸允许目录           | NFR-0600       | AC-NFR0600-02         |
| `VisualizationDependencyError`| matplotlib 缺失                    | FR-1600        | AC-FR1600-04          |
| `DataSchemaError`             | OHLCV schema 校验失败              | NFR-0100       | AC-NFR0100-04         |
| `ConfigValidationError`       | CLI 参数 pydantic 校验失败         | NFR-0600       | AC-FR1100-03          |
| `FeatureNameMismatchError`    | 推理时特征列序与训练不一致         | FR-0900        | （内部防护）           |

### 7.2. 错误传播策略

- **可恢复**（数据缺失、涨跌停过滤、IC 异常）：记 WARNING 日志，继续处理，不抛异常
- **不可恢复**（模型加载失败、schema 不匹配、路径越界）：抛对应异常，CLI 退出码非 0，stderr 输出错误信息
- **安全相关**（反序列化白名单失败）：抛 `SecurityError`（`Exception` 子类），立即中止

---

## 8. 配置与可重现性

### 8.1. 配置优先级（NFR-0700）

```
CLI 参数  >  --config <yaml>  >  默认值
```

`utils.config.load_config(cli_args, yaml_path)` 合并三层，CLI 显式参数覆盖 yaml，yaml 覆盖默认。

### 8.2. 随机性控制（NFR-0700）

lightGBM 训练参数固定种子：
- `random_state=42`
- `feature_fraction_seed=42`
- `bagging_seed=42`
- 可通过 `--seed` 覆盖

fixture 数据生成固定种子 42（`tests/assets/gen_fixture.py`）。

### 8.3. metadata.json 可重现性字段（NFR-0700）

```json
{
  "git_commit_sha": "<7-40 hex>",
  "python_version": "3.11.x",
  "package_versions": {"lightgbm": "...", "polars": "...", "millionaire": "..."},
  "train_start": "2015-01-01",
  "train_end": "2024-12-31",
  "params": {"num_leaves": 63, "learning_rate": 0.05, ...},
  "best_iteration": <int>,
  "test_ic_mean": <float>,
  "test_rank_ic_mean": <float>,
  "ic_pass_soft_target": <bool>
}
```

---

## 9. FR 引用表

| FR/NFR    | 主实现模块                        | 关键接口（详见 interfaces.md）              |
| --------- | --------------------------------- | ------------------------------------------- |
| FR-0100   | features.momentum                 | `compute_momentum_features`                 |
| FR-0200   | features.volatility               | `compute_volatility_features`               |
| FR-0300   | features.volume                   | `compute_volume_features`                   |
| FR-0400   | data.preprocess                   | `fit_scaler_and_impute`, `transform`, `scaler.json`, `dropped_features.json` |
| FR-0500   | labels.builder                    | `build_labels`, `compute_label_stats`, `label_stats.json`, `limit_up_down_filter.json` |
| FR-0600   | data.splits                       | `prepare_walk_forward_splits`, `train/valid/test_<year>.parquet` |
| FR-0700   | training.trainer                  | `train_model`, `train.log`                  |
| FR-0800   | training.model_io                 | `save_model`, `load_model`, `ModelArtifact`, `models/<version>/*` |
| FR-0900   | prediction.service                | `predict`, `predict_skipped.json`           |
| FR-1000   | strategies.lgbm_top20             | `LGBMTop20Strategy`                         |
| FR-1100   | backtest.runner                   | CLI `backtest`, `positions/trades/nav_<ts>.parquet`, `summary.json` |
| FR-1200   | backtest.metrics                  | `compute_performance_metrics`, `InsufficientDataError` |
| FR-1300   | evaluation.ic / evaluation.report | `evaluate_predictions`, `PredictionQualityReport`, `ic_pearson`, `ic_spearman`, `compute_layered_returns` |
| FR-1400   | importance.extractor              | `extract_feature_importance`, CLI `feature-importance` |
| FR-1500   | (e2e 测试)                        | `tests/e2e/test_lgbm_pipeline.py`           |
| FR-1600   | visualization.render              | `render_nav_curve`, `render_ic_timeseries`, `render_feature_importance`, `VisualizationDependencyError` |
| NFR-0100  | data.loader                       | `DataLoader`, schema 校验                    |
| NFR-0200  | training.model_io                 | `metadata.json` IC 字段                      |
| NFR-0300  | (CI 门禁)                         | `pytest --cov` TOTAL≥95%                     |
| NFR-0400  | strategies / utils.config         | async 签名, `pyproject.toml` 依赖            |
| NFR-0500  | utils.logging                     | `setup_logger`, 日志格式, `logs/*.log`       |
| NFR-0600  | utils.security                    | 路径校验, joblib 白名单, `bandit`            |
| NFR-0700  | utils.config / training           | `random_state=42`, 配置优先级, metadata 字段 |
