# trader-off v0.1.0 — lightGBM 短时 A 股定价模型 — Acceptance Criteria

- **Spec ID**: v0.1.0-001-lgbm-asset-pricing
- **Created**: 2026-07-16

> 中央注册表：spec.md 只保留 FR/NFR 描述与元数据（testability/decided/valid）；可观察、可断言的通过条件在本表中。
>
> 编号约定：
> - 每个 FR/NFR 单元内 AC-N 从 1 起，按顺序递增；单元之间不复用。
> - 完整 AC 引用：**AC-FRXXXX-YY**（4 位 FR + 2 位 AC 序号），与 test-plan / issue schema 保持一致。
>
> Lex 阶段 1/2 审查验证：(1) 本表存在；(2) spec.md 每个 FR/NFR 在本表中有对应章节；(3) 每条 AC 可被测试或断言。

## FR-0100 特征工程 — 动量类指标

### AC-1
- 输入：60 个交易日的 OHLCV 数据 + 5 只虚拟股票 fixture。
- 当：调用 `compute_momentum_features(ohlcv_df)`。
- 那么：返回的 DataFrame 必须包含列 `ret_5, ret_10, ret_20, ret_60`，dtype 均为 `Float64`，长度等于输入行数。
- 断言：`out.columns` ⊇ `[ret_5, ret_10, ret_20, ret_60]` 且对应 dtype 校验通过。

### AC-2
- 给定：资产 A 的 close 序列（5 个值 [10, 11, 9, 12, 14]），调用 `compute_momentum_features`。
- 当：检查 `ret_5` 列最后一个值。
- 那么：`ret_5[-1] == 14/10 - 1 = 0.4`（误差 < 1e-9）。
- 断言：`assert abs(df["ret_5"].to_list()[-1] - 0.4) < 1e-9`。

### AC-3
- 给定：资产 B 只有 30 个交易日的数据。
- 当：调用 `compute_momentum_features`。
- 那么：`ret_60` 列全部为 NaN，不抛异常。
- 断言：`df.filter(pl.col("asset") == "B")["ret_60"].null_count() == 30`。

---

## FR-0200 特征工程 — 波动率类指标

### AC-1
- 输入：60 个交易日的 OHLCV 数据。
- 当：调用 `compute_volatility_features(ohlcv_df)`。
- 那么：返回 DataFrame 含 `vol_10, vol_20, vol_60`，dtype 均为 `Float64`。

### AC-2
- 给定：资产 A 的 close 序列（11 个等差值 100, 101, ..., 110），其日收益为常数 0.01。
- 当：调用 `compute_volatility_features`。
- 那么：`vol_10[-1] == 0.0`（标准差为零）。
- 断言：`abs(df["vol_10"].to_list()[-1]) < 1e-9`。

### AC-3
- 给定：资产 A 的 close 序列只有 11 个交易日（[100, 101, 102, ..., 110]），可产生 10 个日收益。
- 当：调用 `compute_volatility_features`。
- 那么：`vol_10[0:9]` 全部为 NaN（min_periods=10 需要 10 个 return），`vol_10[10]` 有值。
- 断言：前 10 个值为 None，第 11 个值非空。

---

## FR-0300 特征工程 — 成交量类指标

### AC-1
- 输入：60 个交易日的 OHLCV 数据（含 turnover、volume、close 列）。
- 当：调用 `compute_volume_features(ohlcv_df)`。
- 那么：返回 DataFrame 含 `turnover_5, turnover_10, turnover_20, vp_corr_5, vp_corr_10, vp_corr_20`。

### AC-2
- 给定：资产 A 的 turnover 列前 20 个值全部为 NaN。
- 当：调用 `compute_volume_features`。
- 那么：资产 A 的 `turnover_5, turnover_10, turnover_20, vp_corr_5, vp_corr_10, vp_corr_20` 全部为 NaN。
- 断言：`df.filter(pl.col("asset") == "A").select([pl.col(c).null_count().alias(c) for c in volume_cols])` 每列均等于 60。
- 同时：loguru 日志中存在 WARNING 级记录，关键词 `turnover missing for asset=A`。

---

## FR-0400 特征标准化与缺失值处理

### AC-1
- 给定：训练特征 DataFrame `X_train`（100 行 × 5 列，列名 `asset, f1, f2, f3, f4`），其中第 3 行 `f2` 列有 NaN（资产 A 在 t=2 时 f2 缺失，但 `asset` 列完整）。
- 当：调用 `fit_scaler_and_impute(X_train)`。
- 那么：返回的 transformed DataFrame 中：
  - 第 3 行的 `f2` 被前向填充（取同一 asset 第 2 行的 f2 值，按 asset 分组的 forward fill）；若仍为 NaN 则填 0。
  - 整列若全 NaN，则该列被剔除（不出现在结果中）。
- 断言：`df.filter(pl.col("asset") == "A").filter(pl.col("date") == t2)["f2"]` 等于 `df.filter(pl.col("asset") == "A").filter(pl.col("date") == t1)["f2"]`（按 asset 分组的前向填充）。

### AC-2
- 给定：上一步训练得到的 scaler。
- 当：调用 `transform(X_test, scaler)`。
- 那么：使用训练期保存的 mean/std 转换，不重新 fit。
- 断言：`scaler.mean_` 与 `scaler.std_` 字段在两次调用之间不变（同一对象引用）。

### AC-3
- 给定：训练数据中某特征列全为 NaN。
- 当：调用 `fit_scaler_and_impute`。
- 那么：训练结束后，`dropped_features.json` 中包含该特征名；模型训练时该特征被排除。

---

## FR-0500 标签构建 — 未来 5 日收益率

### AC-1
- 给定：资产 A 的 close 序列（10 个交易日，close = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]）。
- 当：调用 `build_labels(close_df, horizon=5)`。
- 那么：`label[t] = close[t+5] / close[t] - 1`：
  - `label[0] = 15/10 - 1 = 0.5`
  - `label[4] = 19/14 - 1 ≈ 0.3571`
- 断言：误差 < 1e-6。

### AC-2
- 同上场景。
- 当：检查最后 5 个值。
- 那么：`label[5..9]` 全部为 NaN（无 t+5 数据）。
- 断言：`df["label"].to_list()[5:] == [None, None, None, None, None]`。

### AC-3
- 给定：资产 A 的 close 序列中第 7 个值为 NaN（停牌）。
- 当：调用 `build_labels`。
- 那么：`label[2]` 为 NaN（因 close[7] 不可用）。

### AC-4
- 给定：资产 A 第 3 个交易日的原始数据含 `limit_up=True`（涨停）。
- 当：调用 `build_labels(..., filter_limit_up_down=True)`。
- 那么：`label[3]`（如可计算）变为 NaN，且 `limit_up_down_filter.json` 含记录 `{"asset": "A", "date": "...", "reason": "limit_up"}`。
- 断言：`df.filter(pl.col("asset") == "A").filter(pl.col("date") == t3)["label"].is_null()` 且 JSON 文件含对应记录。

### AC-5
- 给定：1000 只资产 × 500 个交易日的标签。
- 当：调用 `compute_label_stats(labels)`。
- 那么：`label_stats.json` 含 `mean, std, min, p1, p99, max` 字段，且值在合理范围（如 A 股 5 日收益 mean 接近 0）。

---

## FR-0600 训练数据准备 — 滚动 walk-forward

### AC-1
- 给定：完整行情数据 2015-01-01 至 2024-12-31。
- 当：调用 `prepare_walk_forward_splits(data, start_year=2018, end_year=2024, train_window_years=3)`。
- 那么：生成 7 期切分（每年 1 期），每期输出 3 个 parquet：
  - `train_<year>.parquet`：覆盖 `year-3` 至 `year-1`
  - `valid_<year>.parquet`：覆盖 `year` H1
  - `test_<year>.parquet`：覆盖 `year` H2
- 断言：所有 parquet 文件存在，且 `train.max(date) < valid.min(date) < test.max(date)`。

### AC-2
- 给定：数据截止 2020-06-30。
- 当：调用 `prepare_walk_forward_splits(end_year=2020)`。
- 那么：2020 年的 valid 集可生成但 test 集为空文件 + WARNING 日志，不抛异常。

---

## FR-0700 模型训练 — lightGBM 回归

### AC-1
- 给定：训练集 DataFrame（1000 行 × 20 列 + label 列）+ 验证集。
- 当：调用 `train_model(X_train, y_train, X_valid, y_valid, params=default_params)`。
- 那么：返回 `lightgbm.Booster` 对象，且 `booster.num_trees() > 0`。

### AC-2
- 给定：传入 `loss="regression_l2"`（默认）。
- 当：检查 booster 参数。
- 那么：`booster.params["objective"] == "regression"`（L2 等价）或 `"regression_l2"`。

### AC-3
- 给定：验证集 loss 在第 100 轮后开始单调上升。
- 当：训练完成。
- 那么：训练在 best_iteration（< 150）处停止，模型保存为 best_iteration 的 booster，`n_estimators` 未跑满 500。
- 断言：`booster.best_score["valid_0"]["l2"]` 对应轮次 < 150。

### AC-4
- 给定：默认超参数 dict。
- 当：调用 `train_model(...)`。
- 那么：`train.log` 中至少包含一行记录 `best_iteration=<int>` 和 `final_train_loss=<float>`。

### AC-5
- 给定：CLI 命令 `trader-off train --config configs/train.yaml`。
- 当：执行训练。
- 那么：`num_leaves=63, learning_rate=0.05, n_estimators=500` 等默认参数生效，且 yaml 中的覆盖参数生效。

---

## FR-0800 模型序列化与版本管理

### AC-1
- 给定：训练完成后。
- 当：调用 `save_model(booster, scaler, metadata, version="20260101_120000")`。
- 那么：`models/20260101_120000/` 目录下存在：`model.pkl, scaler.json, dropped_features.json, feature_names.json, metadata.json`。
- 断言：`all(Path(...).exists() for p in required_files)`。

### AC-2
- 给定：未指定 `--version` 参数。
- 当：执行训练。
- 那么：`version` 默认值为 `YYYYMMDD_HHMMSS` 格式（15 字符串：8 位日期 + 1 位下划线 + 6 位时间），可通过 `datetime.now().strftime("%Y%m%d_%H%M%S")` 验证格式。
- 断言：`len(version) == 15 and version[8] == "_"`。

### AC-3
- 给定：目录 `models/20260101_120000/` 已存在。
- 当：调用 `save_model(..., version="20260101_120000")`。
- 那么：抛出 `ModelVersionExistsError` 异常，不覆盖已有模型。

### AC-4
- 给定：已保存的模型目录。
- 当：调用 `load_model(version="20260101_120000")`。
- 那么：返回 `ModelArtifact` dataclass，包含字段：`booster: Booster, scaler: StandardScaler, feature_names: list[str], metadata: dict`。
- 断言：`isinstance(artifact, ModelArtifact)` 且所有字段非空。

---

## FR-0900 预测服务

### AC-1
- 给定：已训练模型版本 `v1`、watchlist = `["000001.SZ", "000002.SZ"]`、`asof_date = 2024-12-31`。
- 当：调用 `predict("v1", ["000001.SZ", "000002.SZ"], date(2024, 12, 31))`。
- 那么：返回 `pl.DataFrame`，含 `asset, score, rank` 三列，共 2 行。

### AC-2
- 同 AC-1 场景。
- 当：检查输出排序。
- 那么：DataFrame 按 `score` 降序排列，`rank` 列从 1 开始递增（1, 2）。
- 断言：`df["score"].is_sorted(descending=True)` 且 `df["rank"].to_list() == [1, 2]`。

### AC-3
- 给定：资产 "000003.SZ" 在 asof_date 前 120 日内无行情数据。
- 当：调用 `predict(...)`。
- 那么：返回的 DataFrame 中不含 "000003.SZ"；`predict_skipped.json` 含 `{"asset": "000003.SZ", "reason": "insufficient_history"}`；日志 WARNING。

### AC-4
- 给定：训练时最大 lookback = 120。
- 当：调用 `predict(...)`。
- 那么：内部通过 `quantide.data.fetchers`（或本项目注入的 DataLoader 抽象层）读取每个资产 120 个交易日的行情，可通过 mock DataLoader.get_history 验证调用次数。
- 断言：`mock_loader.get_history.call_count == len(watchlist)` 且每次调用的 `count` 参数等于 120。

---

## FR-1000 策略集成 — LGBMTop20Strategy

### AC-1
- 给定：策略类定义。
- 当：检查继承关系。
- 那么：`LGBMTop20Strategy` 是 `quantide.core.strategy.BaseStrategy` 的子类。
- 断言：`issubclass(LGBMTop20Strategy, BaseStrategy)`。

### AC-2
- 给定：实例化策略 `strategy = LGBMTop20Strategy(broker, config)`。
- 当：调用 `await strategy.init()`。
- 那么：`strategy.model` 属性为非空 `Booster` 对象，且 `strategy.top_k == 20`。

### AC-3
- 给定：当日为 `tm = datetime(2024, 12, 31, 9, 30)`。
- 当：调用 `await strategy.on_day_open(tm)`。
- 那么：
  - 调用 `predict(...)` 一次获取目标股票列表。
  - 对目标中的每只股票调用 `broker.trade_target_pct(asset, 1/top_k)`。
  - 对非目标中的现有持仓调用 `trade_target_pct(asset, 0)` 清仓。
- 断言：通过 mock broker 验证调用次数与参数。

### AC-4
- 同 AC-3 场景。
- 当：检查下单时的 `extra` 参数。
- 那么：`extra` dict 至少包含键：`reason="lgbm_top20", score=<float>, rank=<int>, model_version=<str>`。

### AC-5
- 给定：配置文件 `config/strategy/lgbm_top20.yaml` 含 `model_version=v1, top_k=20, min_score=0.01`。
- 当：策略实例化。
- 那么：`self.model_version == "v1"`、`self.top_k == 20`、`self.min_score == 0.01`。
- 断言：3 个属性均从 yaml 正确加载。

---

## FR-1100 millionaire 回测接入

### AC-1
- 给定：CLI 命令 `trader-off backtest --model v1 --strategy lgbm_top20 --start 2023-01-01 --end 2023-12-31 --capital 1000000`。
- 当：执行。
- 那么：进程退出码为 0，stdout 含 "Backtest finished"。

### AC-2
- 同 AC-1 场景，回测完成后。
- 当：检查输出目录。
- 那么：`reports/backtest_<ts>/` 下存在：`summary.json, positions_<ts>.parquet, trades_<ts>.parquet, nav_<ts>.parquet`。
- 断言：所有文件存在且非空（parquet 行数 > 0）。

### AC-3
- 给定：CLI 命令缺少 `--capital` 参数。
- 当：执行。
- 那么：pydantic 校验失败，退出码非 0，stderr 含 "capital is required"。

---

## FR-1200 回测报告 — 绩效指标

### AC-1
- 给定：净值曲线 DataFrame（252 行 × 2 列：date, nav）。
- 当：调用 `compute_performance_metrics(nav_df)`。
- 那么：返回 dict 含键：`annualized_return, sharpe_ratio, max_drawdown, win_rate, total_trades, avg_turnover`。
- 断言：`set(result.keys()) == required_keys`，且全部为 float 或 int 类型。

### AC-2
- 给定：净值序列 [100, 110, 105, 120, 115]。
- 当：调用 `compute_performance_metrics`。
- 那么：最大回撤路径为 110 → 105（peak=110, trough=105），`max_drawdown = (105 - 110) / 110 ≈ -0.0455`。
- 断言：`abs(result["max_drawdown"] - (-0.0454545...)) < 1e-6`。
- 实现要求：`max_drawdown` 按 (nav[t] - max(nav[0:t+1])) / max(nav[0:t+1]) 在所有 t 上取最小值。

### AC-3
- 给定：净值 DataFrame 仅 10 行。
- 当：调用 `compute_performance_metrics`。
- 那么：抛出 `InsufficientDataError`，message 含 "need at least 30 days"。

---

## FR-1300 预测能力评估

### AC-1
- 给定：predictions DataFrame（1000 行 × 3 列：date, asset, score）+ labels DataFrame（1000 行 × 2 列：date, asset, label）。
- 当：调用 `evaluate_predictions(predictions, labels)`。
- 那么：返回 `PredictionQualityReport` dataclass，含字段：
  - `ic_ts: pl.DataFrame`（列 date, ic）
  - `rank_ic_ts: pl.DataFrame`（列 date, rank_ic）
  - `ic_mean, ic_std, rank_ic_mean, rank_ic_std: float`
  - `layered_returns: pl.DataFrame`（列 layer, mean_return，5 行）

### AC-2
- 给定：`predictions` 与 `labels` 在 (date, asset) 上完全对齐。
- 当：调用 `evaluate_predictions`。
- 那么：`ic_ts` 的行数等于 `predictions["date"].n_unique()`，且每行 ic 值在 [-1, 1] 之间。

### AC-3
- 给定：模块 `trader_off.evaluation`。
- 当：执行 `from trader_off.evaluation import ic_pearson, ic_spearman, compute_layered_returns`。
- 那么：3 个函数均可导入，无 ImportError。
- 断言：`__all__` 包含这 3 个函数名。

### AC-4
- 给定：评估完成后。
- 当：检查输出文件。
- 那么：`prediction_quality.csv` 与 `layered_returns.csv` 均落盘到 `reports/backtest_<ts>/`。

---

## FR-1400 特征重要性分析

### AC-1
- 给定：已训练的 booster（含 20 个特征的训练数据）。
- 当：调用 `extract_feature_importance(booster, feature_names)`。
- 那么：返回 DataFrame 含列 `feature, importance, rank`，按 importance 降序排列，rank 从 1 开始。
- 断言：`len(df) == 20` 且 `df["importance"].is_sorted(descending=True)`。

### AC-2
- 给定：CLI 命令 `trader-off feature-importance --model v1`。
- 当：执行。
- 那么：stdout 输出 Top 20 特征表格（Markdown 或纯文本格式），含 feature 名与 importance 值。

### AC-3
- 给定：booster 为空（未训练）。
- 当：调用 `extract_feature_importance`。
- 那么：返回空 DataFrame（列名仍存在），INFO 日志 "feature_importance empty, no trees trained"，不抛异常。

---

## FR-1500 e2e 端到端流程

### AC-1
- 给定：测试文件 `tests/e2e/test_lgbm_pipeline.py`。
- 当：执行 `pytest tests/e2e/test_lgbm_pipeline.py -v`。
- 那么：1 个 e2e 测试全部通过（至少 5 个断言步骤：fixture 加载、train、predict、backtest、报告校验）。

### AC-2
- 同 AC-1 场景。
- 当：测试运行。
- 那么：耗时 ≤ 60 秒（fixture 数据规模有限）。
- 断言：测试 wall time < 60s。

### AC-3
- 给定：e2e 测试。
- 当：检查 fixture 文件。
- 那么：`tests/e2e/fixtures/` 目录下存在离线数据（10 只股票 × 60 日），无需访问数据库或网络。
- 断言：fixture 文件存在且无 `requests.get`、`httpx` 等网络调用。

---

## FR-1600 可视化输出

### AC-1
- 给定：回测完成，净值数据 `nav.parquet` 存在。
- 当：调用 `render_nav_curve(nav_df, baseline_df, output_path="reports/.../figures/nav_curve.png")`。
- 那么：生成 PNG 文件，文件存在且 `matplotlib.image.imread` 可读取，宽高匹配 `figsize=(10, 6)` × `dpi=120`（1200×720 像素）。
- 断言：`Path(output_path).exists() and Path(output_path).stat().st_size > 1024`（非空 PNG）。

### AC-2
- 给定：回测完成，`prediction_quality.csv` 含 IC 与 Rank IC 时序。
- 当：调用 `render_ic_timeseries(ic_df, output_path="reports/.../figures/ic_timeseries.png")`。
- 那么：生成 PNG 文件，含 IC 与 Rank IC 双折线 + 均值参考线（matplotlib axhline）。
- 断言：`"ic_timeseries.png" in os.listdir(figures_dir)` 且 loguru 记录 "render_ic_timeseries done"。

### AC-3
- 给定：训练完成，`feature_importance.csv` 存在。
- 当：调用 `render_feature_importance(importance_df, top_k=20, output_path="reports/.../figures/feature_importance_top20.png")`。
- 那么：生成 PNG 文件，为横向条形图（matplotlib `barh`），含 Top 20 特征。
- 断言：`len(plot_data) == 20`，且输出文件大小 > 1024 bytes。

### AC-4
- 给定：未安装 matplotlib 的环境（`import matplotlib` 抛 `ImportError`）。
- 当：调用任意 render_* 函数。
- 那么：抛 `VisualizationDependencyError`，message 含 "matplotlib is required for visualization, install via `uv add matplotlib`"。
- 标注：本 AC 用于保证缺依赖时给出可操作的错误提示，不静默失败。

### AC-5
- 给定：CI / Docker 容器中无 X server。
- 当：执行可视化生成。
- 那么：使用 `matplotlib.use("Agg")` 在导入 pyplot 之前设置 backend，stdout 不出现 "Matplotlib is currently using agg" 警告。
- 断言：`import matplotlib; matplotlib.get_backend().lower() == "agg"`。

---

## NFR-0100 数据规模与时间范围

### AC-1
- 给定：单元测试场景（CI 默认运行，无外部依赖）。
- 当：通过 mock DataLoader 返回 4500 个虚拟资产（任意可配置数字 ≥ 4000）。
- 那么：`predict(...)` 与 `prepare_walk_forward_splits(...)` 能在 mock 数据上正常完成（不抛异常且产出 parquet 文件）。
- 断言：`mock_loader.assets == [f"{i:06d}.SZ" for i in range(4500)]`，且 parquet 文件行数符合预期。

### AC-2
- 给定：集成测试场景（手动运行，需要真实 fetcher 与数据库接入）。
- 当：从 `quantide.data.fetchers` 加载 A 股全市场日线。
- 那么：资产数量 ≥ 4000。
- 断言：`len(assets) >= 4000`。
- 标注：本 AC 标记为 `@pytest.mark.integration`，默认 CI 跳过（`pytest -m "not integration"`），仅在带 `--integration` 参数或本地开发时手动运行。

### AC-3
- 给定：训练数据时间范围。
- 当：检查 `metadata.json["train_start"]` 与 `train_end`。
- 那么：`train_start >= "2015-01-01"` 且 `train_end` 等于训练当日。

### AC-4
- 给定：原始行情 DataFrame 的 schema。
- 当：调用 schema 校验。
- 那么：列集合 ⊇ `{asset, date, open, high, low, close, volume, turnover, adj_factor}`，且 dtype 符合预期（asset=str, date=date, 数值列=float）。
- 当 fetcher 提供涨跌停字段时，列集合还必须 ⊇ `{limit_up, limit_down}`，dtype=bool（参考 FR-0500）。

---

## NFR-0200 预测能力阈值（学术参考线）

### AC-1
- 给定：测试集上的 IC 与 Rank IC 计算结果。
- 当：训练完成后检查 `metadata.json["test_ic_mean"]` 与 `test_rank_ic_mean`。
- 那么：这两个字段存在且为 float 类型（即使未达到 0.02/0.03 阈值也要记录）。

### AC-2
- 给定：测试集 IC 均值 < 0。
- 当：训练完成。
- 那么：loguru 打印 WARNING 级日志："IC < 0, model may not have predictive power, check features"。
- 断言：日志中含此关键词。

### AC-3
- 给定：IC > 0.02 与 Rank IC > 0.03。
- 当：训练完成。
- 那么：`metadata.json["ic_pass_soft_target"]` 为 True。

---

## NFR-0300 单元测试覆盖率

### AC-1
- 给定：执行 `pytest --cov=trader_off --cov-report=term-missing`。
- 当：CI 运行测试。
- 那么：报告最后一行 `TOTAL` 的覆盖率为 ≥ 95%。
- 断言：从输出中解析 `TOTAL\s+(\d+)%` ≥ 95。

---

## NFR-0400 代码风格与异步约定

### AC-1
- 给定：项目源码。
- 当：执行 `ruff check trader_off/`（或 flake8）。
- 那么：0 个 error，含 line length ≤ 100 检查通过。

### AC-2
- 给定：`LGBMTop20Strategy` 类。
- 当：检查方法签名。
- 那么：`init, on_day_open, on_bar, on_day_close, on_stop` 全部为 `async def`（与 BaseStrategy 一致）。

### AC-3
- 给定：`pyproject.toml`。
- 当：执行 `uv sync`。
- 那么：依赖成功安装，包含 `lightgbm, polars, loguru, pytest, millionaire, matplotlib` 等。其中 `matplotlib` 因 FR-1600 可视化输出新增；`lightgbm, polars, loguru, pytest, millionaire` 为原有依赖。
- 断言：`uv pip list | grep -E "^(lightgbm|polars|loguru|pytest|millionaire|matplotlib)\s"` 全部存在且非空版本号。

---

## NFR-0500 日志规范

### AC-1
- 给定：项目源码中所有 `print` 调用。
- 当：执行 `ruff rule T201` 或 `grep -r "print(" trader_off/`。
- 那么：无业务代码使用 `print`，全部使用 `logger.info/warning/error`。
- 断言：业务目录 `trader_off/` 下 `print` 出现次数 == 0（测试代码除外）。

### AC-2
- 给定：日志配置 `setup_logger()`。
- 当：执行任意训练/预测/回测。
- 那么：日志格式为 `{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}`。
- 断言：从 stdout 抓取日志行，正则匹配格式。

### AC-3
- 给定：训练/预测/回测执行。
- 当：完成。
- 那么：每个阶段都有 INFO 级进度日志；数据缺失或 IC 异常有 WARNING；模型加载失败有 ERROR。
- 断言：日志文件中含 3 种 level。

### AC-4
- 给定：`logs/` 目录。
- 当：训练/预测/回测完成。
- 那么：每个模块对应一个 log 文件（如 `logs/train_*.log`、`logs/predict_*.log`、`logs/backtest_*.log`）。
- 断言：文件存在且行数 > 0。

---

## NFR-0600 安全审查

### AC-1
- 给定：项目源码。
- 当：执行 `grep -rE "(api_key|password|token|secret)\s*=\s*['\"]" trader_off/`。
- 那么：无 hard-coded credential 匹配项（除测试 fixture）。

### AC-2
- 给定：所有文件 IO 函数。
- 当：检查实现。
- 那么：传入路径必须经过 `pathlib.Path.resolve()` 校验，确保在 `models_dir` 或 `reports_dir` 之下，否则抛 `PathTraversalError`。

### AC-3
- 给定：模型加载代码。
- 当：检查实现。
- 那么：使用 `joblib.load(...)` 而非 `pickle.load(...)`；且对反序列化对象做类型白名单校验（只允许 `lightgbm.Booster` 与自定义 dataclass）。

### AC-4
- 给给定：项目源码。
- 当：执行 `bandit -r trader_off/ -ll`。
- 那么：报告无 HIGH 级 issue；CI 中此命令必须通过。

---

## NFR-0700 数据可重现性

### AC-1
- 给定：默认训练调用。
- 当：检查 lightGBM 训练参数。
- 那么：`params["random_state"] == 42`；`params["feature_fraction_seed"] == 42`；`params["bagging_seed"] == 42`。

### AC-2
- 给定：CLI 命令 `trader-off train --config configs/train.yaml --num-leaves 31`。
- 当：执行。
- 那么：`num_leaves == 31`（CLI 覆盖 yaml），其它参数从 yaml 加载。
- 断言：通过 mock lightGBM.LGBMRegressor 验证传入的 `num_leaves` 参数。

### AC-3
- 给定：训练完成。
- 当：读取 `metadata.json`。
- 那么：含字段：`git_commit_sha`（7-40 位 hex）、`python_version`（如 `3.11.5`）、`package_versions`（dict，键如 `lightgbm, polars, millionaire`）。
