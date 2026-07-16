# lightGBM 短时 A 股定价模型 — Interface Contracts

- **Spec ID**: v0.1.0-001-lgbm-asset-pricing
- **Created**: 2026-07-16
- **Related architecture**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/architecture.md`
- **Related test-plan**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/test-plan.md`

> 本文是 Devon 写测试、Shield 写断言的**唯一契约来源**。仅定义外部可观察契约（数据 schema、函数签名、CLI、文件格式、日志、异常），不含内部实现细节。
>
> **`modules` 列约定**：每条接口标注实现/消费模块。标注 ≥2 个模块的为**跨模块接口**，Shield 必须为其编写集成测试（test-plan §5.2）。

---

## 1. 数据 Schema

### 1.1. 输入 OHLCV DataFrame（fetcher / DataLoader 输出）

| 列           | dtype    | 说明                         | 必填 |
| ------------ | -------- | ---------------------------- | ---- |
| `asset`      | Utf8     | 资产代码（如 `000001.SZ`）   | ✅   |
| `date`       | Date     | 交易日期                     | ✅   |
| `open`       | Float64  | 开盘价                       | ✅   |
| `high`       | Float64  | 最高价                       | ✅   |
| `low`        | Float64  | 最低价                       | ✅   |
| `close`      | Float64  | 收盘价                       | ✅   |
| `volume`     | Float64  | 成交量                       | ✅   |
| `turnover`   | Float64  | 成交额/换手率                | ✅   |
| `adj_factor` | Float64  | 复权因子                     | ✅   |
| `limit_up`   | Boolean  | 涨停标记（fetcher 提供时）   | ⬜   |
| `limit_down` | Boolean  | 跌停标记（fetcher 提供时）   | ⬜   |

- **modules**: `data.loader`（实现）→ `features`, `labels`, `prediction.service`（消费）
- 缺 `limit_up`/`limit_down` 时跳过涨跌停过滤并打 WARNING（FR-0500）

### 1.2. 特征输出 DataFrame（FR-0100/0200/0300 合并）

| 列               | dtype    | 来源 FR  |
| ---------------- | -------- | -------- |
| `asset`          | Utf8     | (键)     |
| `date`           | Date     | (键)     |
| `ret_5`          | Float64  | FR-0100  |
| `ret_10`         | Float64  | FR-0100  |
| `ret_20`         | Float64  | FR-0100  |
| `ret_60`         | Float64  | FR-0100  |
| `vol_10`         | Float64  | FR-0200  |
| `vol_20`         | Float64  | FR-0200  |
| `vol_60`         | Float64  | FR-0200  |
| `turnover_5`     | Float64  | FR-0300  |
| `turnover_10`    | Float64  | FR-0300  |
| `turnover_20`    | Float64  | FR-0300  |
| `vp_corr_5`      | Float64  | FR-0300  |
| `vp_corr_10`     | Float64  | FR-0300  |
| `vp_corr_20`     | Float64  | FR-0300  |

- **modules**: `features`（实现）→ `data.preprocess`, `prediction.service`, `cli.train`（消费）

### 1.3. 标签 DataFrame（FR-0500）

| 列       | dtype    | 说明                       |
| -------- | -------- | -------------------------- |
| `asset`  | Utf8     | 资产代码                   |
| `date`   | Date     | 交易日期                   |
| `label`  | Float64  | 未来 5 日收益率，末尾/停牌/涨跌停为 NaN |

- **modules**: `labels`（实现）→ `training.trainer`, `cli.train`（消费）

### 1.4. 预测输出 DataFrame（FR-0900）

| 列       | dtype    | 说明                          |
| -------- | -------- | ----------------------------- |
| `asset`  | Utf8     | 资产代码                      |
| `score`  | Float64  | 模型预测分数                  |
| `rank`   | Int32    | 排名（score 降序，从 1 开始） |

- **modules**: `prediction.service`（实现）→ `strategies.lgbm_top20`, `cli.predict`（消费）

### 1.5. 净值 DataFrame（FR-1200 输入）

| 列       | dtype    |
| -------- | -------- |
| `date`   | Date     |
| `nav`    | Float64  |

- **modules**: `backtest.runner`（实现）→ `backtest.metrics`, `visualization.render`（消费）

### 1.6. 特征重要性 DataFrame（FR-1400）

| 列           | dtype    | 说明                      |
| ------------ | -------- | ------------------------- |
| `feature`    | Utf8     | 特征名                    |
| `importance` | Float64  | gain 重要性               |
| `rank`       | Int32    | 排名（降序，从 1 开始）   |

- **modules**: `importance.extractor`（实现）→ `cli.feature_importance`, `visualization.render`（消费）

### 1.7. PredictionQualityReport dataclass（FR-1300）

```python
@dataclass
class PredictionQualityReport:
    ic_ts: pl.DataFrame          # 列: date(Date), ic(Float64)
    rank_ic_ts: pl.DataFrame     # 列: date(Date), rank_ic(Float64)
    ic_mean: float
    ic_std: float
    rank_ic_mean: float
    rank_ic_std: float
    layered_returns: pl.DataFrame  # 列: layer(Int32, 1..5), mean_return(Float64)，5 行
```

- **modules**: `evaluation.report`（实现）→ `backtest.runner`, `cli.backtest`, `visualization.render`（消费）

### 1.8. ModelArtifact dataclass（FR-0800）

```python
@dataclass
class ModelArtifact:
    booster: "lightgbm.Booster"
    scaler: "StandardScaler"        # 自定义 dataclass，含 mean_/std_ 字段
    feature_names: list[str]
    metadata: dict
```

- **modules**: `training.model_io`（实现）→ `prediction.service`, `strategies.lgbm_top20`, `cli.train`（消费）

### 1.9. StandardScaler dataclass（FR-0400）

```python
@dataclass
class StandardScaler:
    mean_: dict[str, float]     # 每特征均值
    std_: dict[str, float]      # 每特征标准差
    feature_names: list[str]    # 特征顺序
```

- **modules**: `data.preprocess`（实现）→ `training.model_io`, `prediction.service`（消费）

---

## 2. 持久化文件 Schema

### 2.1. 模型目录 `models/<version>/`（FR-0800）

| 文件                    | 格式    | 内容                                                        |
| ----------------------- | ------- | ----------------------------------------------------------- |
| `model.pkl`             | joblib  | 序列化的 `lightgbm.Booster`                                 |
| `scaler.json`           | JSON    | `{"mean_": {...}, "std_": {...}, "feature_names": [...]}`   |
| `dropped_features.json` | JSON    | `["feature_name", ...]`（全 NaN 被剔除的特征）              |
| `feature_names.json`    | JSON    | `["ret_5", "ret_10", ...]`（推理时列序依据）                |
| `metadata.json`         | JSON    | 见 §2.2                                                     |

- `version` 默认 `YYYYMMDD_HHMMSS`（15 字符，`len==15 and version[8]=="_"`），可 `--version` 指定
- 重复 version → `ModelVersionExistsError`
- **modules**: `training.model_io`（实现）→ `prediction.service`, `strategies`, `cli`（消费）

### 2.2. metadata.json（FR-0800 / NFR-0200 / NFR-0700）

```json
{
  "train_time": "2026-07-16T12:00:00Z",
  "train_start": "2015-01-01",
  "train_end": "2024-12-31",
  "params": {"objective": "regression", "num_leaves": 63, "learning_rate": 0.05,
             "n_estimators": 500, "random_state": 42, ...},
  "best_iteration": 120,
  "test_ic_mean": 0.025,
  "test_rank_ic_mean": 0.035,
  "ic_pass_soft_target": true,
  "git_commit_sha": "abc1234",
  "python_version": "3.11.5",
  "package_versions": {"lightgbm": "4.3.0", "polars": "1.0.0", "millionaire": "0.1.0"}
}
```

- **modules**: `training.model_io`（实现）→ `cli.train`, 测试断言（消费）

### 2.3. 回测报告目录 `reports/backtest_<ts>/`（FR-1100/1200/1300/1400/1600）

| 文件                          | 格式    | 内容                                  |
| ----------------------------- | ------- | ------------------------------------- |
| `summary.json`                | JSON    | 绩效指标（见 §2.4）                   |
| `positions_<ts>.parquet`      | parquet | 持仓序列                              |
| `trades_<ts>.parquet`         | parquet | 交易记录                              |
| `nav_<ts>.parquet`            | parquet | 净值曲线（§1.5）                      |
| `prediction_quality.csv`      | CSV     | 每日 IC / Rank IC（列 date, ic, rank_ic）|
| `layered_returns.csv`         | CSV     | 5 层收益（列 layer, mean_return）     |
| `feature_importance.csv`      | CSV     | §1.6                                  |
| `figures/nav_curve.png`       | PNG     | 净值曲线图                            |
| `figures/ic_timeseries.png`   | PNG     | IC 时序图                             |
| `figures/feature_importance_top20.png` | PNG | 特征重要性 Top 20 条形图            |

- **modules**: `backtest.runner`（实现）→ `evaluation`, `importance`, `visualization`（消费落盘）

### 2.4. summary.json（FR-1200）

```json
{
  "annualized_return": 0.15,
  "sharpe_ratio": 1.2,
  "max_drawdown": -0.15,
  "win_rate": 0.52,
  "total_trades": 120,
  "avg_turnover": 0.3
}
```

### 2.5. 其他落盘文件

| 文件                          | 格式 | 触发 FR  | 内容                                          |
| ----------------------------- | ---- | -------- | --------------------------------------------- |
| `label_stats.json`            | JSON | FR-0500  | `{mean, std, min, p1, p99, max}`              |
| `limit_up_down_filter.json`   | JSON | FR-0500  | `[{"asset", "date", "reason"}, ...]`          |
| `dropped_features.json`       | JSON | FR-0400  | `["feature", ...]`                            |
| `predict_skipped.json`        | JSON | FR-0900  | `[{"asset", "reason"}, ...]`                  |
| `train.log`                   | text | FR-0700  | 含 `best_iteration=<int>`, `final_train_loss=<float>` |
| `logs/<module>_*.log`         | text | NFR-0500 | 每模块一个日志文件                            |

---

## 3. 公共 API（函数签名）

> `modules` 列：`实现模块 → 消费模块`。≥2 模块 = 跨模块（Shield 集成测试覆盖）。

### 3.1. 特征工程（FR-0100/0200/0300）

| 函数                                   | 签名                                                                       | 返回                                  | FR       | AC                       | modules                                    |
| -------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------- | -------- | ------------------------ | ------------------------------------------ |
| `compute_momentum_features`            | `(ohlcv: pl.DataFrame) -> pl.DataFrame`                                    | §1.2（ret_* 列）                       | FR-0100  | AC-FR0100-01/02/03       | features → data, prediction, cli           |
| `compute_volatility_features`          | `(ohlcv: pl.DataFrame) -> pl.DataFrame`                                    | §1.2（vol_* 列）                       | FR-0200  | AC-FR0200-01/02/03       | features → data, prediction, cli           |
| `compute_volume_features`              | `(ohlcv: pl.DataFrame) -> pl.DataFrame`                                    | §1.2（turnover_*/vp_corr_* 列）        | FR-0300  | AC-FR0300-01/02          | features → data, prediction, cli           |

- 模块路径：`trader_off.features.momentum` / `.volatility` / `.volume`
- 纯函数，无副作用，按 `asset` 分组计算

### 3.2. 标签构建（FR-0500）

| 函数                 | 签名                                                                                | 返回            | FR      | AC                       | modules                       |
| -------------------- | ----------------------------------------------------------------------------------- | --------------- | ------- | ------------------------ | ----------------------------- |
| `build_labels`       | `(close_df: pl.DataFrame, horizon: int = 5, filter_limit_up_down: bool = True) -> pl.DataFrame` | §1.3            | FR-0500 | AC-FR0500-01/02/03/04    | labels → training, cli        |
| `compute_label_stats`| `(labels: pl.DataFrame) -> dict`                                                    | `{mean,std,min,p1,p99,max}` | FR-0500 | AC-FR0500-05             | labels → cli                  |

- 模块路径：`trader_off.labels.builder`
- `build_labels`：`label = close[t+5]/close[t]-1`，末尾 5 个 NaN；停牌/涨跌停置 NaN

### 3.3. 数据处理（FR-0400/0600, NFR-0100）

| 函数 / 类                         | 签名                                                                       | 返回                | FR/NFR    | AC                       | modules                              |
| --------------------------------- | -------------------------------------------------------------------------- | ------------------- | --------- | ------------------------ | ------------------------------------ |
| `DataLoader`                      | `__init__(self, fetcher=None)`；`async get_history(self, asset, end_date, count=120) -> pl.DataFrame` | §1.1 OHLCV          | NFR-0100  | AC-NFR0100-01/02/04      | data.loader → prediction, splits, strategies |
| `prepare_walk_forward_splits`     | `(data: pl.DataFrame, start_year: int, end_year: int, train_window_years: int = 3, output_dir: Path = None) -> list[Split]` | `Split` 列表 + parquet | FR-0600   | AC-FR0600-01/02          | data.splits → cli                    |
| `fit_scaler_and_impute`           | `(X_train: pl.DataFrame) -> tuple[pl.DataFrame, StandardScaler, list[str]]` | (transformed_df, scaler, dropped) | FR-0400   | AC-FR0400-01/03          | data.preprocess → training, cli      |
| `transform`                       | `(X: pl.DataFrame, scaler: StandardScaler) -> pl.DataFrame`                | 标准化后的 X        | FR-0400   | AC-FR0400-02             | data.preprocess → prediction, cli    |

- `Split` dataclass：`{year: int, train_path: Path, valid_path: Path, test_path: Path}`
- `fit_scaler_and_impute`：前向填充（按 asset 分组）→ 剩余填 0 → z-score → 剔除全 NaN 列
- **DataLoader** 是跨模块核心适配器：封装 `quantide.data.fetchers`，测试可注入 fixture 替身

### 3.4. 训练与序列化（FR-0700/0800）

| 函数 / 类          | 签名                                                                       | 返回                | FR      | AC                       | modules                              |
| ------------------ | -------------------------------------------------------------------------- | ------------------- | ------- | ------------------------ | ------------------------------------ |
| `train_model`      | `(X_train: pl.DataFrame, y_train: pl.DataFrame, X_valid: pl.DataFrame, y_valid: pl.DataFrame, params: dict = None) -> lightgbm.Booster` | Booster             | FR-0700 | AC-FR0700-01/02/03/04    | training.trainer → model_io, cli     |
| `save_model`       | `(booster, scaler: StandardScaler, metadata: dict, version: str, models_dir: Path = "models") -> Path` | 模型目录 Path       | FR-0800 | AC-FR0800-01/02/03       | training.model_io → cli              |
| `load_model`       | `(version: str, models_dir: Path = "models") -> ModelArtifact`             | §1.8 ModelArtifact  | FR-0800 | AC-FR0800-04             | training.model_io → prediction, strategies, cli |

- 模块路径：`trader_off.training.trainer` / `trader_off.training.model_io`
- `train_model` 默认 params（NFR-0700）：`objective=regression, num_leaves=63, learning_rate=0.05, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5, n_estimators=500, early_stopping_rounds=50, random_state=42, feature_fraction_seed=42, bagging_seed=42`
- `save_model`：version 已存在 → `ModelVersionExistsError`；默认 version = `datetime.now().strftime("%Y%m%d_%H%M%S")`

### 3.5. 预测服务（FR-0900）

| 函数       | 签名                                                                       | 返回            | FR      | AC                       | modules                              |
| ---------- | -------------------------------------------------------------------------- | --------------- | ------- | ------------------------ | ------------------------------------ |
| `predict`  | `(model_version: str, watchlist: list[str], asof_date: date, data_loader: DataLoader = None) -> pl.DataFrame` | §1.4            | FR-0900 | AC-FR0900-01/02/03/04    | prediction.service → strategies, cli |

- 模块路径：`trader_off.prediction.service`
- 缺失行情资产 → 记 `predict_skipped.json` + WARNING，不出现在结果
- lookback = 120 交易日（从 metadata 读 max lookback）

### 3.6. 策略集成（FR-1000）

| 类 / 方法                          | 签名                                                                       | FR      | AC                       | modules                              |
| ---------------------------------- | -------------------------------------------------------------------------- | ------- | ------------------------ | ------------------------------------ |
| `LGBMTop20Strategy(BaseStrategy)`  | `__init__(self, broker: Broker, config: dict)`                              | FR-1000 | AC-FR1000-01             | strategies → backtest, cli           |
| `LGBMTop20Strategy.init`           | `async def init(self) -> None`                                              | FR-1000 | AC-FR1000-02/05          | 同上                                 |
| `LGBMTop20Strategy.on_day_open`    | `async def on_day_open(self, tm: datetime) -> None`                         | FR-1000 | AC-FR1000-03/04          | 同上                                 |
| `LGBMTop20Strategy.on_bar`         | `async def on_bar(self, ...) -> None`                                       | FR-1000 | AC-NFR0400-02            | 同上                                 |
| `LGBMTop20Strategy.on_day_close`   | `async def on_day_close(self, ...) -> None`                                 | FR-1000 | AC-NFR0400-02            | 同上                                 |
| `LGBMTop20Strategy.on_stop`        | `async def on_stop(self) -> None`                                           | FR-1000 | —                        | 同上                                 |

- 模块路径：`trader_off.strategies.lgbm_top20`
- `on_day_open`：调 `predict` → 目标持仓 `broker.trade_target_pct(asset, 1/top_k, extra={...})` → 非目标清仓 `trade_target_pct(asset, 0, extra={...})`
- `extra` dict：`{"reason": "lgbm_top20", "score": float, "rank": int, "model_version": str}`
- 配置：`config/strategy/lgbm_top20.yaml` → `model_version, top_k=20, min_score=-inf`
- 属性：`self.model`（Booster）, `self.top_k`, `self.min_score`, `self.model_version`

### 3.7. 回测与绩效（FR-1100/1200）

| 函数 / 类          | 签名                                                                       | 返回                | FR      | AC                       | modules                              |
| ------------------ | -------------------------------------------------------------------------- | ------------------- | ------- | ------------------------ | ------------------------------------ |
| `run_backtest`     | `(model_version: str, strategy_name: str, start: date, end: date, capital: float, config: dict = None) -> BacktestResult` | BacktestResult | FR-1100 | AC-FR1100-01/02/03       | backtest.runner → strategies, evaluation, visualization, cli |
| `compute_performance_metrics` | `(nav: pl.DataFrame) -> dict`                                   | §2.4 dict           | FR-1200 | AC-FR1200-01/02/03       | backtest.metrics → runner, cli       |

- `BacktestResult` dataclass：`{summary: dict, positions: pl.DataFrame, trades: pl.DataFrame, nav: pl.DataFrame, report_dir: Path}`
- `compute_performance_metrics`：纯函数；nav < 30 行 → `InsufficientDataError`（message 含 "need at least 30 days"）
- `max_drawdown` = `min over t of (nav[t] - max(nav[0:t+1])) / max(nav[0:t+1])`

### 3.8. 预测能力评估（FR-1300）

| 函数 / 类                    | 签名                                                                       | 返回                | FR      | AC                       | modules                              |
| ---------------------------- | -------------------------------------------------------------------------- | ------------------- | ------- | ------------------------ | ------------------------------------ |
| `evaluate_predictions`       | `(predictions: pl.DataFrame, labels: pl.DataFrame) -> PredictionQualityReport` | §1.7            | FR-1300 | AC-FR1300-01/02/04       | evaluation.report → backtest, cli    |
| `ic_pearson`                 | `(pred: pl.Series, label: pl.Series) -> float`                             | float ∈ [-1,1]      | FR-1300 | AC-FR1300-02/03          | evaluation.ic → report               |
| `ic_spearman`                | `(pred: pl.Series, label: pl.Series) -> float`                             | float ∈ [-1,1]      | FR-1300 | AC-FR1300-02/03          | evaluation.ic → report               |
| `compute_layered_returns`    | `(predictions: pl.DataFrame, labels: pl.DataFrame, n_layers: int = 5) -> pl.DataFrame` | 列 layer, mean_return | FR-1300 | AC-FR1300-01/03 | evaluation.ic → report               |

- 模块路径：`trader_off.evaluation.ic` / `trader_off.evaluation.report`
- `__all__ = ["ic_pearson", "ic_spearman", "compute_layered_returns", "evaluate_predictions", "PredictionQualityReport"]`
- `ic_pearson` / `ic_spearman` / `compute_layered_returns` 为纯函数

### 3.9. 特征重要性（FR-1400）

| 函数                        | 签名                                                                       | 返回            | FR      | AC                       | modules                              |
| --------------------------- | -------------------------------------------------------------------------- | --------------- | ------- | ------------------------ | ------------------------------------ |
| `extract_feature_importance`| `(booster: lightgbm.Booster, feature_names: list[str]) -> pl.DataFrame`    | §1.6            | FR-1400 | AC-FR1400-01/03          | importance.extractor → cli, visualization |

- 空 booster → 空 DataFrame（列名保留）+ INFO 日志 "feature_importance empty, no trees trained"

### 3.10. 可视化（FR-1600）

| 函数                        | 签名                                                                       | 返回            | FR      | AC                       | modules                              |
| --------------------------- | -------------------------------------------------------------------------- | --------------- | ------- | ------------------------ | ------------------------------------ |
| `render_nav_curve`          | `(nav_df: pl.DataFrame, baseline_df: pl.DataFrame, output_path: Path, figsize: tuple = (10,6), dpi: int = 120) -> Path` | PNG Path | FR-1600 | AC-FR1600-01             | visualization.render → backtest, cli  |
| `render_ic_timeseries`      | `(ic_df: pl.DataFrame, output_path: Path, figsize: tuple = (10,6), dpi: int = 120) -> Path` | PNG Path | FR-1600 | AC-FR1600-02             | 同上                                 |
| `render_feature_importance` | `(importance_df: pl.DataFrame, top_k: int = 20, output_path: Path, figsize: tuple = (10,6), dpi: int = 120) -> Path` | PNG Path | FR-1600 | AC-FR1600-03             | 同上                                 |

- 模块路径：`trader_off.visualization.render`
- 缺 matplotlib → `VisualizationDependencyError`（message 含 "matplotlib is required for visualization, install via `uv add matplotlib`"）
- `matplotlib.use("Agg")` 在导入 pyplot 前设置；`figures/` 不存在自动创建

### 3.11. 工具（NFR-0500/0600/0700）

| 函数 / 类              | 签名                                                  | 返回        | NFR      | AC                       | modules          |
| ---------------------- | ----------------------------------------------------- | ----------- | -------- | ------------------------ | ---------------- |
| `setup_logger`         | `(module: str, log_dir: Path = "logs") -> None`       | None        | NFR-0500 | AC-NFR0500-02/03/04      | utils.logging    |
| `validate_path`        | `(path: Path, allowed_roots: list[Path]) -> Path`     | 校验后 Path | NFR-0600 | AC-NFR0600-02            | utils.security   |
| `safe_load_model_file` | `(path: Path, allowed_types: tuple = (...)) -> object`| 反序列化对象| NFR-0600 | AC-NFR0600-03            | utils.security   |
| `load_config`          | `(cli_args: dict, yaml_path: Path = None) -> dict`    | 合并配置    | NFR-0700 | AC-NFR0700-02            | utils.config     |

- `setup_logger`：日志格式 `{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}`，输出 stdout + `logs/<module>_*.log`
- `validate_path`：路径逃逸 → `PathTraversalError`
- `safe_load_model_file`：用 `joblib.load` 非 `pickle.load`；白名单仅 `lightgbm.Booster` + 自定义 dataclass

---

## 4. CLI 接口

### 4.1. `trader-off train`（FR-0700/0800, NFR-0700）

```
trader-off train --config <yaml> [--version <str>] [--start-year <int>] [--end-year <int>]
                 [--loss <regression_l2|regression|quantile>] [--alpha <float>] [--seed <int>]
                 [--num-leaves <int>] [--learning-rate <float>] [--n-estimators <int>]
```

| 参数            | 类型  | 默认             | 校验                  | AC              |
| --------------- | ----- | ---------------- | --------------------- | --------------- |
| `--config`      | path  | —                | 必填，yaml 存在       | AC-FR0700-05    |
| `--version`     | str   | 时间戳 15 字符   | `len==15, [8]=="_"`   | AC-FR0800-02    |
| `--start-year`  | int   | 2018             | ≥ 2015                | —               |
| `--end-year`    | int   | 当前年           | > start-year          | —               |
| `--loss`        | str   | regression_l2    | enum                  | AC-FR0700-02    |
| `--seed`        | int   | 42               | ≥ 0                   | AC-NFR0700-01   |
| `--num-leaves`  | int   | 63               | CLI 覆盖 yaml         | AC-NFR0700-02   |

- 退出码 0 = 成功；输出 `models/<version>/`
- **modules**: `cli.train` → `data, training, importance`

### 4.2. `trader-off predict`（FR-0900）

```
trader-off predict --model <version> --watchlist <csv> --date <YYYY-MM-DD>
```

| 参数           | 类型 | 校验                          | AC              |
| -------------- | ---- | ----------------------------- | --------------- |
| `--model`      | str  | 必填，version 目录存在        | AC-FR0900-01    |
| `--watchlist`  | path | 必填，CSV 列 `asset,frame_type`| AC-FR0900-01    |
| `--date`       | date | 必填                          | AC-FR0900-01    |

- 输出 `predictions_<date>.csv`（§1.4）
- **modules**: `cli.predict` → `prediction`

### 4.3. `trader-off backtest`（FR-1100）

```
trader-off backtest --model <version> --strategy <lgbm_top20> --start <YYYY-MM-DD>
                    --end <YYYY-MM-DD> --capital <float> [--config <yaml>]
```

| 参数         | 类型   | 校验                                  | AC              |
| ------------ | ------ | ------------------------------------- | --------------- |
| `--model`    | str    | 必填                                  | AC-FR1100-01    |
| `--strategy` | str    | 必填，enum `[lgbm_top20]`             | AC-FR1100-01    |
| `--start`    | date   | 必填                                  | AC-FR1100-01    |
| `--end`      | date   | 必填，> start                         | AC-FR1100-01    |
| `--capital`  | float  | 必填，> 0；缺失 → pydantic 报错       | AC-FR1100-03    |

- 退出码 0 = 成功；stdout 含 "Backtest finished"
- 输出 `reports/backtest_<ts>/`（§2.3）
- **modules**: `cli.backtest` → `backtest, strategies, evaluation, importance, visualization`

### 4.4. `trader-off feature-importance`（FR-1400）

```
trader-off feature-importance --model <version> [--top-k 20]
```

| 参数       | 类型 | 默认 | 校验                  | AC              |
| ---------- | ---- | ---- | --------------------- | --------------- |
| `--model`  | str  | —    | 必填，version 目录存在| AC-FR1400-02    |
| `--top-k`  | int  | 20   | > 0                   | AC-FR1400-02    |

- stdout 打印 Top-K 特征表格（Markdown / 纯文本）
- **modules**: `cli.feature_importance` → `importance`

---

## 5. millionaire 接口契约

### 5.1. BaseStrategy 继承契约

| 方法          | millionaire 签名（基类）                  | trader-off 实现                | 性质     |
| ------------- | ----------------------------------------- | ------------------------------ | -------- |
| `init`        | `async def init(self) -> None`            | 加载模型、读配置、初始化缓存    | 重写     |
| `on_day_open` | `async def on_day_open(self, tm) -> None` | 调 predict + broker 调仓       | 重写     |
| `on_bar`      | `async def on_bar(self, ...) -> None`     | noop                            | 重写（空）|
| `on_day_close`| `async def on_day_close(self, ...) -> None`| noop                           | 重写（空）|
| `on_stop`     | `async def on_stop(self) -> None`         | 释放模型引用                    | 重写     |

- **modules**: `strategies`（实现）← `millionaire.quantide.core.strategy`（基类）

### 5.2. Broker 接口（trader-off 消费）

| 方法                  | 签名                                                       | 用途                          |
| --------------------- | ---------------------------------------------------------- | ----------------------------- |
| `trade_target_pct`    | `trade_target_pct(self, asset: str, pct: float, extra: dict = None) -> None` | 调仓到目标百分比              |

- **modules**: `strategies`（消费）← `millionaire.quantide.service.base_broker.Broker`（实现）
- 单测 mock broker 记录调用次数/参数；e2e 用真实 `BacktestBroker`

### 5.3. 数据 fetcher 接口（trader_off 适配）

| 方法                | 签名                                                       | 用途                          |
| ------------------- | ---------------------------------------------------------- | ----------------------------- |
| `DataLoader.get_history` | `async get_history(self, asset: str, end_date: date, count: int = 120) -> pl.DataFrame` | 取 asset 在 end_date 前 count 日行情 |

- **modules**: `data.loader`（适配实现）← `millionaire.quantide.data.fetchers`（被封装）
- 测试注入 fixture 支撑的 DataLoader 替身（返回 parquet 数据）

### 5.4. BacktestRunner 注入契约

```python
BacktestRunner(
    strategy=LGBMTop20Strategy(broker, config),
    broker=BacktestBroker(capital),       # millionaire 提供
    data_loader=DataLoader(fetcher),       # trader_off 适配
    start=date, end=date,
)
runner.run()  # 驱动每日 on_day_open → 撮合 → 输出 parquet
```

- **modules**: `backtest.runner`（编排）← `millionaire.BacktestRunner`（引擎）

---

## 6. 跨模块接口清单（Shield 集成测试依据）

> 下表汇总所有 `modules` 标注 ≥2 的接口，Shield 必须为每条编写集成测试（happy + 关键错误/边界）。

| # | 接口                              | 跨模块链路                                          | 覆盖 AC                                   |
| - | --------------------------------- | --------------------------------------------------- | ----------------------------------------- |
| 1 | `compute_momentum_features`       | features → data.preprocess, prediction, cli         | AC-FR0100-01/02/03                        |
| 2 | `compute_volatility_features`     | features → data.preprocess, prediction, cli         | AC-FR0200-01/02/03                        |
| 3 | `compute_volume_features`         | features → data.preprocess, prediction, cli         | AC-FR0300-01/02                           |
| 4 | `build_labels`                    | labels → training, cli                              | AC-FR0500-01/02/03/04                     |
| 5 | `fit_scaler_and_impute`           | data.preprocess → training, cli                     | AC-FR0400-01/03                           |
| 6 | `transform`                       | data.preprocess → prediction, cli                   | AC-FR0400-02                              |
| 7 | `prepare_walk_forward_splits`     | data.splits → cli                                   | AC-FR0600-01/02                           |
| 8 | `train_model`                     | training.trainer → model_io, cli                    | AC-FR0700-01/02/03/04/05                  |
| 9 | `save_model`                      | training.model_io → cli                             | AC-FR0800-01/02/03                        |
| 10| `load_model`                      | training.model_io → prediction, strategies, cli     | AC-FR0800-04                              |
| 11| `predict`                         | prediction.service → strategies, cli                | AC-FR0900-01/02/03/04                     |
| 12| `DataLoader.get_history`          | data.loader → prediction, splits, strategies        | AC-NFR0100-01/02/04, AC-FR0900-04         |
| 13| `LGBMTop20Strategy` 全生命周期    | strategies → backtest.runner, cli                    | AC-FR1000-01/02/03/04/05                  |
| 14| `run_backtest`                    | backtest.runner → strategies, evaluation, viz, cli  | AC-FR1100-01/02/03                        |
| 15| `compute_performance_metrics`     | backtest.metrics → runner, cli                      | AC-FR1200-01/02/03                        |
| 16| `evaluate_predictions`            | evaluation.report → backtest, cli                   | AC-FR1300-01/02/04                        |
| 17| `extract_feature_importance`      | importance → cli, visualization                     | AC-FR1400-01/02/03                        |
| 18| `render_nav_curve`                | visualization → backtest, cli                       | AC-FR1600-01                              |
| 19| `render_ic_timeseries`            | visualization → backtest, cli                       | AC-FR1600-02                              |
| 20| `render_feature_importance`       | visualization → backtest, cli                       | AC-FR1600-03                              |
| 21| `setup_logger`                    | utils.logging → all modules                         | AC-NFR0500-02/03/04                       |
| 22| `validate_path`                   | utils.security → training, prediction, backtest     | AC-NFR0600-02                             |
| 23| `safe_load_model_file`            | utils.security → training.model_io                  | AC-NFR0600-03                             |
| 24| `load_config`                     | utils.config → cli, training                        | AC-NFR0700-02                             |

---

## 7. 异常接口

| 异常                          | 模块               | 触发条件                          | 关联 AC          |
| ----------------------------- | ------------------ | --------------------------------- | ---------------- |
| `InsufficientDataError`       | utils.exceptions   | nav < 30 日                       | AC-FR1200-03     |
| `ModelVersionExistsError`     | utils.exceptions   | save_model version 已存在         | AC-FR0800-03     |
| `PathTraversalError`          | utils.exceptions   | 文件 IO 路径逃逸                   | AC-NFR0600-02    |
| `VisualizationDependencyError`| utils.exceptions   | matplotlib 缺失                   | AC-FR1600-04     |
| `DataSchemaError`             | utils.exceptions   | OHLCV schema 校验失败             | AC-NFR0100-04    |
| `ConfigValidationError`       | utils.exceptions   | CLI pydantic 校验失败             | AC-FR1100-03     |

---

## 8. 三方闭环：AC → interfaces → test-plan

每条 AC 的断言依据均落在本文定义的可观察出口上；每个出口在 test-plan 中有对应测试覆盖。

| FR/NFR    | AC 数 | interfaces 出口（本文）            | test-plan 覆盖（§8/§9）         |
| --------- | ----- | ---------------------------------- | ------------------------------- |
| FR-0100   | 3     | §3.1 + §1.2                        | §8.1 unit                       |
| FR-0200   | 3     | §3.1 + §1.2                        | §8.1 unit                       |
| FR-0300   | 2     | §3.1 + §1.2                        | §8.1 unit                       |
| FR-0400   | 3     | §3.3 + §2.1/2.5                    | §8.1 unit                       |
| FR-0500   | 5     | §3.2 + §2.5                        | §8.1 unit                       |
| FR-0600   | 2     | §3.3 + §2.3                        | §8.1 unit                       |
| FR-0700   | 5     | §3.4 + §2.5                        | §8.1 unit(4) + integ(1)         |
| FR-0800   | 4     | §3.4 + §2.1/2.2 + §1.8             | §8.1 unit                       |
| FR-0900   | 4     | §3.5 + §2.5 + §1.4                 | §8.1 unit                       |
| FR-1000   | 5     | §3.6 + §5.1/5.2                    | §8.1 unit(async)                |
| FR-1100   | 3     | §4.3 + §2.3                        | §8.2 integration                |
| FR-1200   | 3     | §3.7 + §2.4 + §7                   | §8.1 unit                       |
| FR-1300   | 4     | §3.8 + §1.7 + §2.3                 | §8.1 unit(3) + integ(1)         |
| FR-1400   | 3     | §3.9 + §1.6 + §4.4                 | §8.1 unit(2) + integ(1)         |
| FR-1500   | 3     | §4.3 + §2.3                        | §6.5 / §8.3 e2e                 |
| FR-1600   | 5     | §3.10 + §2.3 + §7                  | §8.1 unit                       |
| NFR-0100  | 4     | §3.3(DataLoader) + §1.1            | §8.1 unit(3) + integ L3(1)      |
| NFR-0200  | 3     | §2.2                               | §8.1 unit                       |
| NFR-0300  | 1     | (CI 门禁)                          | §9 CI gate                      |
| NFR-0400  | 3     | §3.6(async) + §3.1 技术选型        | §8.1 unit(1) + CI gate(2)       |
| NFR-0500  | 4     | §3.11 + §2.5                       | §8.1 unit(3) + CI gate(1)       |
| NFR-0600  | 4     | §3.11 + §7                         | §8.1 unit(2) + CI gate(2)       |
| NFR-0700  | 3     | §3.4(params) + §3.11 + §2.2        | §8.1 unit(2) + integ(1)         |
| **合计** | **79**| **全部 AC 有出口**                  | **79/79 全覆盖**                 |

> 闭环校验：interfaces.md 每个外部出口 → test-plan 至少 1 个测试方法（§8/§9）。test-plan 不发明新观察方法；若测试需某出口而 interfaces 未定义，先修订 interfaces。
