# lightGBM 短时 A 股定价模型 — Test Plan

- **Spec ID**: v0.1.0-001-lgbm-asset-pricing
- **Created**: 2026-07-16
- **Related acceptance**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/acceptance.md`
- **Related spec**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/spec.md`
- **Related interfaces**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/interfaces.md`（断言依据，见 §6.6；Stage 2 产出后闭环）
- **Test framework**: pytest（`project.toml [meta].test_framework = "pytest"`）

> **AC 编号约定**：本计划中 AC 引用统一使用 `AC-FRXXXX-YY` / `AC-NFRXXXX-YY` 格式（4 位 FR 编号 + 2 位 AC 序号，零填充）。例如 FR-0100 的第 1 条 AC 记为 `AC-FR0100-01`。CI 通过正则 `\bAC-((?:FR|NFR)\d{4})-(\d{2})\b` 扫描 `tests/` 下测试代码，校验「每个 AC ≥1 个测试引用，每个测试 ≥1 个 AC 引用」（见 §7）。

---

## 1. 立场与边界

### 1.1. 黑盒声明

本测试计划只声明**可从系统外部观察**的测试方法。可观察对象限于：

- 公共 API / SDK 接口（`compute_momentum_features`、`predict`、`train_model`、`compute_performance_metrics`、`evaluate_predictions` 等）
- CLI 端点（`trader-off train` / `predict` / `backtest` / `feature-importance`）
- 持久化数据文件（`models/<version>/*.json|pkl`、`reports/backtest_<ts>/*.json|csv|parquet|png`）
- 结构化日志条目（loguru INFO / WARNING / ERROR，关键词断言）
- 可被 matplotlib 读取的静态图表文件（PNG）

### 1.2. 非可观察对象（测试不直接依赖）

- lightGBM 内部 Booster 树结构细节（仅通过 `num_trees()` / `feature_importance()` / `best_score` 等公开属性观察）
- millionaire 框架内部的撮合 / 调度状态机（`BacktestRunner` 的内部队列、registry）
- 中间 DataFrame 结构（策略持仓缓存等内部状态变量）

> **可观察契约**：任何 AC 验证所需的内部状态，必须由实现层通过 dump / log / 持久化文件 / 公开属性提供观察出口。这是 **interfaces.md** 的职责——若某 AC 需观察内部状态，interfaces.md 必须有对应出口（见 §6.6）。本计划中标注为 unit 的纯函数测试，其断言全部落在函数返回值与落盘文件上。

### 1.3. 作弊模式（CI 强制拦截）

| #   | 作弊模式                | 典型症状                                       |
| --- | ----------------------- | ---------------------------------------------- |
| 1   | 改断言迁就实现          | spec 说「抛异常」，测试改成「返回 False」       |
| 2   | 用 skip 逃避验证        | `pytest.skip` 写「见 e2e」但 e2e 从不编写        |
| 3   | 断言降级                | `assert issubclass(X, Exception)` 而非真正提交并捕获 |
| 4   | try/except: pass        | 异常路径被吞掉                                  |
| 5   | 过度 mock               | mock 框架核心（撮合/规则），测的是 mock 行为     |
| 6   | Ground truth 用实现自身 | 期望值 = 被测实现的输出                          |
| 7   | 硬编码期望值            | `assert result == 0.15` 仅为当前实现凑数         |
| 8   | 平凡通过                | `assert True` / `assert 1 == 1`                 |

### 1.4. 防护措施（CI 检查 + PR 流程）

1. **AC 强制溯源**
   - 每个测试函数 docstring 第一行必须包含 `AC-FRXXXX-YY`（4 位 FR + 2 位 AC 序号）
   - CI 扫描 `tests/`，校验：每个测试引用 ≥1 个 AC；每个 AC 被 ≥1 个测试引用
   - 任一检查失败阻断合并

2. **断言禁忌**（CI 静态检查，违规阻断合并）
   - 禁止 `assert True` / `assert 1` / `assert <obj> is not None` 作为唯一断言
   - 禁止 `try: ... except: pass` 包裹被测代码
   - 禁止无 issue 链接的 `pytest.skip` / `@pytest.mark.skip`

3. **测试变更分类**（PR 描述必填）
   - [ ] 新增 AC（链接 acceptance.md commit）
   - [ ] Spec 变更（链接 spec commit）
   - [ ] 修复 flake / 环境问题（链接 issue）
   - **禁止类**：「实现行为与 spec 不符 → 改测试」直接 review 拒绝

4. **可测试性兜底**（若某 AC 无法测试）
   - 不通过 mock 内部强行通过
   - 登记为框架侧可测试性需求，请求实现层增加公开装配点
   - 解决前标记该 AC 为「blocked by testability gap」

### 1.5. 测试分工

- **单元测试**：由**实现者**（Devon）编写，随实现一起在 R-G-R 中提交
- **集成测试**：由**测试负责人**（Shield）编写，覆盖 interfaces.md 定义的跨模块接口契约
- **E2E 测试**：由**测试负责人**（Shield）编写，仅覆盖面向用户的 happy path
- **Ground Truth（§3）**：由**未参与被测实现**的独立开发者或**第三方库**提供
- **Review 归属**：所有测试变更由测试负责人 review；Ground Truth 脚本变更需重点 review 其与对应 AC 的语义一致性

---

## 2. 测试环境

### 2.1. 目录布局

```
tests/
├── unit/                 # 单元测试；镜像源文件目录结构
│   ├── features/         # FR-0100/0200/0300/0400
│   ├── labels/           # FR-0500
│   ├── splits/           # FR-0600
│   ├── training/         # FR-0700
│   ├── model_io/         # FR-0800
│   ├── predict/          # FR-0900
│   ├── strategy/         # FR-1000
│   ├── metrics/          # FR-1200
│   ├── evaluation/       # FR-1300
│   ├── importance/       # FR-1400
│   ├── viz/              # FR-1600
│   └── nfr/              # NFR-0200/0400/0500/0600/0700
├── integration/          # 集成测试；验证跨模块接口契约
├── e2e/                  # 端到端场景测试（仅 happy path）
│   ├── test_lgbm_pipeline.py
│   └── fixtures/         # 离线 fixture 数据（10 股 × 60 日）
├── assets/               # 离线、可复现测试数据
└── ground_truth/         # 独立参考实现；禁止 import trader_off.*（见 §3.2）
```

> - 单元测试与 E2E 使用不同数据（按时间/场景分离）防止过拟合
> - E2E **禁止** mock 框架内部实现（如需 mock，应改写 AC）
> - E2E **禁止**依赖框架私有 API

### 2.2. 命名约定

- 文件：`test_<scenario>__<subscenario>.py`
- 函数：`test_ac_<id>_<subscenario>`，例如 `test_ac_fr0100_01_columns_and_dtype`
- 每个测试函数 docstring 第一行：`"""AC-FR0100-01: 描述"""`（CI 溯源锚点）
- pytest marker：`@pytest.mark.asyncio`（异步策略方法）、`@pytest.mark.integration`（集成）、`@pytest.mark.e2e`（端到端）、`@pytest.mark.slow`（超时保护）

### 2.3. 执行

- **离线**：测试不依赖网络（数据 pinned 到 fixture / assets）
- **执行顺序**：unit（快）→ integration → e2e（慢）
- **CI**：每次 push 运行全套
- **隔离**：集成与 e2e 使用 pytest marker 避免与单元测试混跑
  - 默认：`pytest tests/unit -q`（CI 默认 + 覆盖率）
  - 集成：`pytest tests/integration -m "integration" -q`
  - E2E：`pytest tests/e2e -m "e2e" -q`
  - 全量：`pytest -m "not integration_real" -q`（排除需真实 fetcher 的 L3）

### 2.4. 测试数据

本项目有外部数据依赖（A 股日线行情、millionaire fetcher），需离线 fixture。

- **来源**：合成生成（确定性脚本生成 10 只虚拟股票 × 60 个交易日的 OHLCV + turnover + adj_factor + limit_up/limit_down）
- **可复现**：每次 CI 运行产出一致结果（固定随机种子 42，固定日期范围）
- **仓内小数据**：`tests/e2e/fixtures/`（E2E 用）、`tests/assets/`（单元测试用小型构造数据）
- **敏感数据**：不提交；真实行情仅在 `@pytest.mark.integration` 集成测试中使用（默认 CI 跳过）
- **版本快照**：fixture 生成脚本 `tests/assets/gen_fixture.py` 记录生成参数与时间，CI 校验 manifest

### 2.5. 测试工具链

| 工具               | 版本约束        | 用途                                   |
| ------------------ | --------------- | -------------------------------------- |
| pytest             | >= 8.0          | 测试框架主框架                          |
| pytest-cov         | >= 5.0          | 覆盖率收集（NFR-0300 ≥95%）             |
| pytest-asyncio     | >= 0.23         | 异步策略方法测试（FR-1000 `async def`）  |
| pytest-mock        | >= 3.12         | mock millionaire broker / fetcher       |
| polars             | >= 1.0          | 测试数据构造与断言（与生产一致）         |
| numpy              | >= 1.26         | 数值断言                                |
| scipy              | >= 1.13         | Ground Truth：IC pearson/spearman 参考  |
| lightgbm           | >= 4.3          | 训练/预测测试                           |
| matplotlib         | >= 3.7          | 可视化测试（FR-1600，Agg backend）       |
| loguru             | >= 0.7          | 日志断言（caplog）                      |
| bandit             | >= 1.7          | 安全扫描（NFR-0600）                    |
| ruff               | >= 0.5          | lint / 风格检查（NFR-0400）             |
| pydantic           | >= 2.7          | CLI 参数校验测试                        |
| joblib             | >= 1.4          | 模型序列化测试（FR-0800）               |

> 上述依赖由 Devon 在 `pyproject.toml` 的 `[project.dependencies]` 与 `[tool.uv.dev-dependencies]` 中落地（Stage 2 / R-G-R 阶段）。pytest 插件配置写在 `pyproject.toml [tool.pytest.ini_options]`：`asyncio_mode = "auto"`、`markers = [...]`、`addopts = "--strict-markers"`。

---

## 3. Ground Truth 方法

本项目涉及金融计算正确性（动量/波动率/IC/夏普/最大回撤/分层收益），需 Ground Truth 验证，禁止硬编码期望值。

### 3.1. 通用原则

所有 Ground Truth 由**独立来源**在测试运行时计算：

| 计算类型                                              | 独立来源                                                                 |
| ----------------------------------------------------- | ------------------------------------------------------------------------ |
| 特征计算（动量 ret_N、波动率 vol_N、换手率、量价相关） | **手算脚本**：`tests/ground_truth/feat_ref.py` 用纯 numpy/polars 独立实现  |
| 标签计算（label = close[t+5]/close[t]-1）              | **数据本身**：小型 close 序列手算期望值                                   |
| 评估指标（IC / Rank IC / 分层收益）                    | **第三方库**：`scipy.stats.pearsonr` / `spearmanr` 作为 IC 参考           |
| 绩效指标（年化 / 夏普 / 最大回撤 / 胜率）              | **手算脚本**：`tests/ground_truth/metrics_ref.py` 独立实现滚动最大回撤     |
| 简单规则（涨跌停过滤、缺失值处理）                     | **数据本身**：测试数据集为唯一真相源                                      |

> 核心设计：Ground Truth 是**可重算的脚本**，而非文档固定值。测试运行时同一数据 + Ground Truth 脚本计算后与框架输出对比。

### 3.2. Ground Truth 隔离（强制规则）

为防止「期望值 = 被测实现输出」的循环验证（§1.3 作弊 #6）：

1. **代码位置**：所有 Ground Truth 脚本存放于 `tests/ground_truth/`（unit/e2e 共享）
2. **导入禁忌**：`tests/ground_truth/**/*.py` **禁止** `import trader_off.*`（含子模块）；CI 静态检查违规阻断合并
3. **允许依赖**：仅标准库 + 测试数据文件 + 约定的第三方库（numpy / scipy / polars 作为算法参考实现）
4. **数据访问**：直接从 `tests/assets/` / `tests/e2e/fixtures/` 读数据文件，**不**通过框架 SDK
5. **Review 归属**：Ground Truth 脚本变更由测试负责人 review，重点校验与对应 AC 的语义一致性

---

## 4. 测试范围

本测试计划覆盖 spec.md 中所有 Valid / Testable / Decided 全绿的 FR/NFR（共 23 项，79 条 AC）。

| Valid | Testable | Decided |
| ----- | -------- | ------- |
| ✅    | ✅       | ✅      |

覆盖矩阵：FR-0100 ~ FR-1600（16 项，57 条 AC）+ NFR-0100 ~ NFR-0700（7 项，22 条 AC）= **79 AC 全覆盖**。

---

## 5. 验收标准

1. 单元测试覆盖率 ≥95%（行覆盖，`pytest-cov`，NFR-0300）
2. interfaces.md 中定义的每个跨模块接口契约至少有 1 个集成测试（happy + 关键错误/边界路径）
   > **跨模块接口** = interfaces.md 中 `modules` 列列出 ≥2 个模块的条目（Archer 从 architecture.md 模块边界标注，Shield 据此清单编写，不自行推断）
3. Stories 与 Spec 中的用户场景由 e2e happy path 完全覆盖并通过
4. 所有 FR 有对应测试覆盖（AC 引用闭环）
5. §6 外部依赖分层测试：L1/L2 默认 CI 通过；L3 在对应环境可运行

---

## 6. 外部依赖分层测试

本项目有外部依赖：A 股日线行情（millionaire `quantide.data.fetchers`）、系统时钟、matplotlib 渲染环境。

### 6.1. 三大约束

| #   | 约束                                  | 后果                                             |
| --- | ------------------------------------- | ------------------------------------------------ |
| C1  | 测试环境无法连生产依赖（真实行情 DB）  | CI / 跨平台开发机无法跑真实 fetcher 路径          |
| C2  | 无法等待真实时间                       | 跨日 / 跨周策略周期测试不可行（回测需虚拟日历推进）|
| C3  | 不能 mock 框架内部实现                 | 替换/patch 框架自身撮合/规则会绕过被测行为，违反黑盒 |

> §2 离线数据环境无法让带外部依赖的路径跑起来——本节正是为此存在。

### 6.2. 立场：可控替换 vs Mock

- **可替换外部依赖**（可控）：壁钟（系统时钟）、外部服务（fetcher 行情源）、远程 API — 这些是被测框架的**外部依赖**，可用确定性替身替换
- **不可 mock 内部实现**：框架自身的特征计算、标签构建、训练、IC 计算、绩效指标 — 这些是**被测对象**，不得 mock

> **边界铁律**：任何情况下不得替换/绕过框架自身关键实现以「让测试通过」。若测试发现必须绕过才能通过，说明 AC 可观察性设计有误；应修订 interfaces/acceptance，而非在测试侧打补丁。

**millionaire 边界判定**：
- `quantide.data.fetchers`（行情数据源）= **外部依赖** → 用 fixture 支撑的 DataLoader 替身替换（L1）
- `BacktestBroker.trade_target_pct` / `BacktestRunner` 撮合调度 = **被测框架** → 单元测试中 mock broker 接口（仅验证调用次数/参数），但 E2E 中使用真实 `BacktestBroker` + fixture 数据（不 mock 撮合）
- `BaseStrategy` 生命周期（init/on_day_open/on_stop）= **被测对象** → 不得 mock

### 6.3. 三层测试金字塔

按保真度/成本/速度分三层，各层覆盖的 AC 不重叠，marker 严格区分运行时机。

| 层 | 名称           | 时钟         | 速度   | 覆盖                          | 默认运行       |
| -- | -------------- | ------------ | ------ | ----------------------------- | -------------- |
| L1 | 确定性仿真     | 虚拟日历     | 秒级   | 大部分业务 AC（特征/标签/训练/指标/IC） | ✅ CI 默认     |
| L2 | 契约仿真       | 虚拟日历     | 秒级   | 跨模块接口契约 AC（predict↔strategy↔backtest）| ✅ CI 默认 |
| L3 | 真实环境冒烟   | 真实日历     | 真实   | 真实 fetcher 全市场（≥4000 资产）单次冒烟 | ❌ nightly/手动 |

- **L1 确定性仿真**：用确定性替身替换「时间推进」与「外部行情数据源」，跑通若干交易日业务周期
- **L2 契约仿真**：启动遵循同协议的替身服务（fixture 支撑的 fetcher）；框架与替身交互
- **L3 真实环境冒烟**：真实日历 + 真实依赖，单次往返冒烟（≤1 轮回测）；默认 deselect，仅在有真实依赖环境运行

> 任何 L3 测试**必须**打对应 marker（替代 §1.4 的 skip）；不得用无 issue 链接的 skip 逃避 L3。

### 6.4. 测试基础设施责任契约

定义各替身组件的**职责 + 外部可观察边界**，供测试工程师实现。**不规定内部实现细节**。

| 组件               | 职责（外部）                              | 边界（不实现）                          |
| ------------------ | ----------------------------------------- | --------------------------------------- |
| DataLoader 替身    | 按资产 + 日期范围从 fixture 返回 OHLCV    | 不实现特征计算/业务规则                  |
| 虚拟日历           | 给定「当前日期」+ 可快进                   | 不实现跨日结算逻辑                       |
| Mock Broker（单测）| 记录 `trade_target_pct` 调用次数与参数     | 不实现真实撮合（E2E 用真实 BacktestBroker）|
| 回测编排器         | 组装替身 + 推进时间                        | 不代框架执行业务                         |

### 6.5. E2E 测试计划（FR-1500，Shield 编写）

> **本节是 Shield（M-E2E）的关键输入。** FR-1500 定义了端到端流程，必须 1 个 e2e 测试覆盖完整链路。

**测试文件**：`tests/e2e/test_lgbm_pipeline.py`

**覆盖 AC**：`AC-FR1500-01` / `AC-FR1500-02` / `AC-FR1500-03`

**完整链路步骤**（≥5 个断言步骤）：

1. **Fixture 加载**：从 `tests/e2e/fixtures/` 加载 10 只虚拟股票 × 60 个交易日 OHLCV（含 turnover / adj_factor / limit_up / limit_down）。注入 DataLoader 替身替换 `quantide.data.fetchers`。
2. **train**：执行 `trader-off train --config configs/train.e2e.yaml`（fixture 数据 + 缩小参数：`n_estimators=50, early_stopping_rounds=10` 以满足 ≤60s）→ 断言 `models/<version>/` 目录存在且含 5 个必需文件（`model.pkl, scaler.json, dropped_features.json, feature_names.json, metadata.json`）。
3. **predict**：执行 `trader-off predict --model <version> --watchlist tests/e2e/fixtures/watchlist.csv --date <fixture 末日>` → 断言输出 `predictions_<date>.csv` 含 `asset, score, rank` 三列、按 score 降序、rank 从 1 开始。
4. **backtest**：执行 `trader-off backtest --model <version> --strategy lgbm_top20 --start <fixture 起日> --end <fixture 末日> --capital 1000000` → 使用真实 `BacktestBroker` + fixture 数据（**不 mock 撮合**）。
5. **报告校验**：断言 `reports/backtest_<ts>/` 下存在 `summary.json`（含 `annualized_return, sharpe_ratio, max_drawdown, win_rate, total_trades, avg_turnover` 全部必需字段）、`prediction_quality.csv`、`layered_returns.csv`、`positions_<ts>.parquet`、`trades_<ts>.parquet`、`nav_<ts>.parquet`，以及 `figures/` 下 3 个 PNG。

**运行时约束**：
- 运行命令：`pytest tests/e2e/test_lgbm_pipeline.py -m e2e -v`
- 耗时 ≤ 60 秒（`AC-FR1500-02`：用 `@pytest.mark.slow` + `pytest-timeout` 或 `time.perf_counter()` 断言 wall time < 60s）
- **无外部依赖**：fixture 数据离线，断言无 `requests.get` / `httpx` 等网络调用（`AC-FR1500-03`：可用 `pytest-socket` 禁用网络或 monkeypatch socket）

**Fixture 策略**：
- `tests/e2e/fixtures/ohlcv_10x60.parquet`：10 只股票（`000001.SZ` ~ `000010.SZ`）× 60 个交易日（如 2024-01-02 ~ 2024-03-28），列：`asset, date, open, high, low, close, volume, turnover, adj_factor, limit_up, limit_down`
- `tests/e2e/fixtures/watchlist.csv`：列 `asset,frame_type`，10 行
- `tests/e2e/fixtures/baseline_nav.parquet`：沪深 300 基准净值（用于 FR-1600 nav_curve 对比；合成数据）
- `configs/train.e2e.yaml`：缩小参数配置（保证 ≤60s）

**百万富翁组件 mock 边界**（E2E 中）：
- ✅ 替换 `quantide.data.fetchers` → DataLoader 替身（读 fixture parquet）
- ❌ 不 mock `BacktestBroker` / `BacktestRunner` 撮合（用真实组件 + fixture 数据）
- ❌ 不 mock `LGBMTop20Strategy` 业务逻辑（用真实策略类）
- ❌ 不 mock lightGBM 训练（用真实 LGBMRegressor + 缩小参数）

**host-project e2e 执行契约**（Stage 2 写入 `project.toml [e2e]`，供 Shield/CI 读取）：

```toml
[e2e]
cwd = "."
paths = ["tests/e2e", "tests/e2e/fixtures", "configs/train.e2e.yaml"]
run = "pytest tests/e2e -m e2e -v --timeout=90"
# 无需 start/ready/teardown：e2e 纯进程内 pytest，不启动外部服务
```

> 注：`[e2e]` section 将在 Stage 2（M-ARCH）正式写入 `project.toml`。此处为规划说明。

### 6.6. 断言依据 — 与 interfaces.md 闭环

测试断言**只能**落在 interfaces.md 定义的外部可观察出口上：

- 持久化文件 schema（`models/<version>/*`、`reports/backtest_<ts>/*`）
- API / 函数返回值字段（`predict` 返回 `asset,score,rank`；`compute_performance_metrics` 返回 dict 键集）
- CLI 退出码 / stdout / stderr
- 结构化日志条目（loguru 关键词）
- 公开属性（`booster.num_trees()`、`booster.best_score`、`artifact.feature_names`）

> 若某 AC 所需状态在 interfaces.md 中**无**对应可观察出口，这是可观察性缺口；应修订 interfaces/acceptance 增加出口，而非在测试侧窥探内部状态。

---

## 7. CI 门禁

```bash
lk agent archer ci-scan \
  --acceptance .louke/project/specs/v0.1.0-001-lgbm-asset-pricing/acceptance.md \
  --tests tests/
```

校验项：
- **AC 引用闭环**（每个 AC ≥1 测试，每个测试 ≥1 AC）—— `lk agent archer check-acs --acceptance ... --tests tests/`
- **反模式静态扫描**（§1.3：无 `assert True`、无 `try/except:pass`、无无链接 skip）—— `check_assertions.py`
- **覆盖率 ≥95%** —— `pytest --cov=trader_off --cov-report=term-missing`，`TOTAL` 行 ≥95%（NFR-0300）
- **Ground Truth 隔离**（§3.2：`tests/ground_truth/` 不 import `trader_off.*`）
- **安全扫描** —— `bandit -r trader_off/ -ll`，无 HIGH 级 issue（NFR-0600）
- **lint** —— `ruff check trader_off/`，0 error（NFR-0400）

**CI 排除规则**（覆盖率）：`if __name__ == "__main__"` 块、纯数据 fixture、第三方 wrapper 类（millionaire 框架对象）。

---

## 8. 分层测试计划（按模块）

> 下表为测试规划：每条 AC 映射到测试函数命名模式与所属层。详细断言逻辑见 `acceptance.md` 对应章节，本计划不重复断言细节（避免与 check_acs.py 反向生成的覆盖率矩阵重复）。CI 通过 docstring 中的 `AC-FRXXXX-YY` 引用强制闭环。

### 8.1. 单元测试（Devon 编写，L1 确定性仿真）

#### FR-0100 特征工程 — 动量类指标

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0100-01    | `test_ac_fr0100_01_columns_and_dtype`     | 返回列 ⊇ `[ret_5,ret_10,ret_20,ret_60]`，dtype Float64 |
| AC-FR0100-02    | `test_ac_fr0100_02_ret5_value`            | close=[10,11,9,12,14] → `ret_5[-1]==0.4`（误差<1e-9）|
| AC-FR0100-03    | `test_ac_fr0100_03_short_history_nan`     | 30 日数据 → `ret_60` 全 NaN，不抛异常              |

#### FR-0200 特征工程 — 波动率类指标

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0200-01    | `test_ac_fr0200_01_columns_dtype`         | `vol_10,vol_20,vol_60` Float64                    |
| AC-FR0200-02    | `test_ac_fr0200_02_zero_std`              | 等差 close → 常数收益 → `vol_10[-1]==0.0`          |
| AC-FR0200-03    | `test_ac_fr0200_03_min_periods`           | 11 日 → `vol_10[0:9]` NaN，`vol_10[10]` 有值       |

#### FR-0300 特征工程 — 成交量类指标

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0300-01    | `test_ac_fr0300_01_columns`               | `turnover_5/10/20, vp_corr_5/10/20` 列存在         |
| AC-FR0300-02    | `test_ac_fr0300_02_turnover_missing_warn` | turnover 全 NaN → 6 列全 NaN + WARNING `turnover missing for asset=A` |

#### FR-0400 特征标准化与缺失值处理

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0400-01    | `test_ac_fr0400_01_forward_fill_by_asset` | f2 列 NaN → 按 asset 分组前向填充（取同 asset 上一行）|
| AC-FR0400-02    | `test_ac_fr0400_02_transform_reuses_scaler`| `transform` 不重新 fit，`scaler.mean_/std_` 不变   |
| AC-FR0400-03    | `test_ac_fr0400_03_dropped_features`      | 全 NaN 列 → `dropped_features.json` 含该特征名      |

#### FR-0500 标签构建 — 未来 5 日收益率

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0500-01    | `test_ac_fr0500_01_label_formula`         | `label[0]=0.5, label[4]≈0.3571`（误差<1e-6）       |
| AC-FR0500-02    | `test_ac_fr0500_02_tail_nan`              | 最后 5 个 label 为 NaN                            |
| AC-FR0500-03    | `test_ac_fr0500_03_halt_nan`              | close[7] NaN → label[2] NaN                       |
| AC-FR0500-04    | `test_ac_fr0500_04_limit_up_filter`       | limit_up=True → label NaN + `limit_up_down_filter.json` 含记录 |
| AC-FR0500-05    | `test_ac_fr0500_05_label_stats`           | `label_stats.json` 含 `mean,std,min,p1,p99,max`   |

#### FR-0600 训练数据准备 — 滚动 walk-forward

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0600-01    | `test_ac_fr0600_01_seven_splits`          | 7 期切分，每期 3 parquet，`train.max<valid.min<test.max` |
| AC-FR0600-02    | `test_ac_fr0600_02_partial_year`          | end=2020-06-30 → test 空文件 + WARNING，不抛异常   |

#### FR-0700 模型训练 — lightGBM 回归

| AC              | 测试函数                                  | 层     | 断言要点                                       |
| --------------- | ----------------------------------------- | ------ | ---------------------------------------------- |
| AC-FR0700-01    | `test_ac_fr0700_01_returns_booster`       | unit   | `booster.num_trees()>0`                        |
| AC-FR0700-02    | `test_ac_fr0700_02_objective`             | unit   | `params["objective"]` ∈ {regression, regression_l2} |
| AC-FR0700-03    | `test_ac_fr0700_03_early_stopping`        | unit   | best_iteration<150，n_estimators 未跑满 500     |
| AC-FR0700-04    | `test_ac_fr0700_04_train_log`             | unit   | `train.log` 含 `best_iteration` 与 `final_train_loss` |
| AC-FR0700-05    | `test_ac_fr0700_05_cli_params`            | integration | CLI `train --config` 默认参数 + yaml 覆盖生效   |

#### FR-0800 模型序列化与版本管理

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0800-01    | `test_ac_fr0800_01_save_files`            | 5 个文件存在                                      |
| AC-FR0800-02    | `test_ac_fr0800_02_default_version_format`| `len(version)==15 and version[8]=="_"`            |
| AC-FR0800-03    | `test_ac_fr0800_03_version_exists_error`  | 重复 version → `ModelVersionExistsError`          |
| AC-FR0800-04    | `test_ac_fr0800_04_load_artifact`         | `ModelArtifact` 字段非空（booster/scaler/feature_names/metadata）|

#### FR-0900 预测服务

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR0900-01    | `test_ac_fr0900_01_returns_dataframe`     | 返回 `asset,score,rank` 3 列 2 行                 |
| AC-FR0900-02    | `test_ac_fr0900_02_sorted_desc`           | score 降序，`rank==[1,2]`                          |
| AC-FR0900-03    | `test_ac_fr0900_03_skip_insufficient`     | 缺失行情资产不在结果中 + `predict_skipped.json` + WARNING |
| AC-FR0900-04    | `test_ac_fr0900_04_lookback_120`          | mock DataLoader，`call_count==len(watchlist)`，count=120 |

#### FR-1000 策略集成 — LGBMTop20Strategy（async，pytest-asyncio）

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR1000-01    | `test_ac_fr1000_01_inheritance`           | `issubclass(LGBMTop20Strategy, BaseStrategy)`     |
| AC-FR1000-02    | `test_ac_fr1000_02_init_loads_model`      | `await init()` → model 非空 Booster，`top_k==20`  |
| AC-FR1000-03    | `test_ac_fr1000_03_on_day_open_trades`    | mock broker，predict 调用 1 次，目标 `trade_target_pct(asset,1/20)`，非目标清仓 |
| AC-FR1000-04    | `test_ac_fr1000_04_extra_snapshot`        | `extra` 含 `reason/score/rank/model_version`      |
| AC-FR1000-05    | `test_ac_fr1000_05_config_loading`        | yaml → `model_version/top_k/min_score` 正确加载   |

#### FR-1200 回测报告 — 绩效指标

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR1200-01    | `test_ac_fr1200_01_keys`                  | 返回 dict 含 6 键，类型 float/int                 |
| AC-FR1200-02    | `test_ac_fr1200_02_max_drawdown`          | [100,110,105,120,115] → `max_drawdown≈-0.0455`（Ground Truth 独立计算）|
| AC-FR1200-03    | `test_ac_fr1200_03_insufficient_data`     | 10 行 → `InsufficientDataError`（message 含 "30 days"）|

#### FR-1300 预测能力评估

| AC              | 测试函数                                  | 层     | 断言要点                                       |
| --------------- | ----------------------------------------- | ------ | ---------------------------------------------- |
| AC-FR1300-01    | `test_ac_fr1300_01_report_fields`         | unit   | `PredictionQualityReport` 含 ic_ts/rank_ic_ts/均值标准差/layered_returns |
| AC-FR1300-02    | `test_ac_fr1300_02_ic_range`              | unit   | ic_ts 行数==date 唯一数，ic∈[-1,1]（scipy 参考）|
| AC-FR1300-03    | `test_ac_fr1300_03_imports`               | unit   | `__all__` 含 `ic_pearson,ic_spearman,compute_layered_returns` |
| AC-FR1300-04    | `test_ac_fr1300_04_csv_output`            | integration | `prediction_quality.csv` + `layered_returns.csv` 落盘 |

#### FR-1400 特征重要性分析

| AC              | 测试函数                                  | 层     | 断言要点                                       |
| --------------- | ----------------------------------------- | ------ | ---------------------------------------------- |
| AC-FR1400-01    | `test_ac_fr1400_01_extract_sorted`        | unit   | 20 行，`importance` 降序，rank 从 1             |
| AC-FR1400-02    | `test_ac_fr1400_02_cli_top20`             | integration | CLI 打印 Top 20 表格                           |
| AC-FR1400-03    | `test_ac_fr1400_03_empty_booster`         | unit   | 空 booster → 空 DataFrame + INFO 日志，不抛异常 |

#### FR-1600 可视化输出

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-FR1600-01    | `test_ac_fr1600_01_nav_curve_png`         | PNG 存在，size>1024，`imread` 可读，尺寸 1200×720 |
| AC-FR1600-02    | `test_ac_fr1600_02_ic_timeseries_png`     | PNG 存在 + axhline 均值参考线 + loguru 记录       |
| AC-FR1600-03    | `test_ac_fr1600_03_feature_importance_png`| `barh` 横向条形，20 特征，size>1024               |
| AC-FR1600-04    | `test_ac_fr1600_04_missing_dep_error`     | 缺 matplotlib → `VisualizationDependencyError`    |
| AC-FR1600-05    | `test_ac_fr1600_05_agg_backend`           | `matplotlib.get_backend()=="agg"`，无警告         |

#### NFR-0100 数据规模与时间范围

| AC              | 测试函数                                  | 层          | 断言要点                                       |
| --------------- | ----------------------------------------- | ----------- | ---------------------------------------------- |
| AC-NFR0100-01   | `test_ac_nfr0100_01_mock_4500_assets`     | unit        | mock 4500 资产，predict/walk-forward 完成不异常 |
| AC-NFR0100-02   | `test_ac_nfr0100_02_real_fetcher_4000`    | integration(L3) | `@pytest.mark.integration`，真实 fetcher，`len(assets)>=4000` |
| AC-NFR0100-03   | `test_ac_nfr0100_03_train_range`          | unit        | `metadata.json` train_start≥2015-01-01         |
| AC-NFR0100-04   | `test_ac_nfr0100_04_schema`               | unit        | 列集合⊇9 字段 + dtype；limit_up/limit_down bool |

#### NFR-0200 预测能力阈值

| AC              | 测试函数                                  | 断言要点                                          |
| --------------- | ----------------------------------------- | ------------------------------------------------- |
| AC-NFR0200-01   | `test_ac_nfr0200_01_metadata_ic_fields`   | `test_ic_mean`/`test_rank_ic_mean` 存在且 float   |
| AC-NFR0200-02   | `test_ac_nfr0200_02_negative_ic_warning`  | IC<0 → WARNING 关键词                              |
| AC-NFR0200-03   | `test_ac_nfr0200_03_soft_target_pass`     | IC>0.02 & Rank IC>0.03 → `ic_pass_soft_target==True` |

#### NFR-0400 代码风格与异步约定

| AC              | 测试函数 / 门禁                           | 层     | 断言要点                                       |
| --------------- | ----------------------------------------- | ------ | ---------------------------------------------- |
| AC-NFR0400-01   | CI gate: `ruff check trader_off/`         | CI     | 0 error，line length≤100                        |
| AC-NFR0400-02   | `test_ac_nfr0400_02_async_signatures`     | unit   | `init/on_day_open/on_bar/on_day_close/on_stop` 均 `async def` |
| AC-NFR0400-03   | CI gate: `uv sync`                        | CI     | 依赖安装成功，含 lightgbm/polars/loguru/pytest/millionaire/matplotlib |

#### NFR-0500 日志规范

| AC              | 测试函数 / 门禁                           | 层     | 断言要点                                       |
| --------------- | ----------------------------------------- | ------ | ---------------------------------------------- |
| AC-NFR0500-01   | CI gate: `ruff rule T201` / grep           | CI     | `trader_off/` 无 `print`（测试代码除外）         |
| AC-NFR0500-02   | `test_ac_nfr0500_02_log_format`           | unit   | caplog 正则匹配 `{time}\|{level}\|{name}:{function}:{line}\|{message}` |
| AC-NFR0500-03   | `test_ac_nfr0500_03_log_levels`           | unit   | 日志含 INFO/WARNING/ERROR 三种 level            |
| AC-NFR0500-04   | `test_ac_nfr0500_04_log_files`            | unit   | `logs/train_*.log` 等文件存在且行数>0            |

#### NFR-0600 安全审查

| AC              | 测试函数 / 门禁                           | 层     | 断言要点                                       |
| --------------- | ----------------------------------------- | ------ | ---------------------------------------------- |
| AC-NFR0600-01   | CI gate: grep credentials                 | CI     | 无 hard-coded credential（除 fixture）          |
| AC-NFR0600-02   | `test_ac_nfr0600_02_path_traversal`       | unit   | 路径越界 → `PathTraversalError`                 |
| AC-NFR0600-03   | `test_ac_nfr0600_03_joblib_whitelist`     | unit   | 用 `joblib.load` 非 `pickle.load`；类型白名单校验 |
| AC-NFR0600-04   | CI gate: `bandit -r trader_off/ -ll`      | CI     | 无 HIGH 级 issue                                |

#### NFR-0700 数据可重现性

| AC              | 测试函数                                  | 层          | 断言要点                                       |
| --------------- | ----------------------------------------- | ----------- | ---------------------------------------------- |
| AC-NFR0700-01   | `test_ac_nfr0700_01_random_state`         | unit        | `random_state/feature_fraction_seed/bagging_seed==42` |
| AC-NFR0700-02   | `test_ac_nfr0700_02_cli_override`         | integration | `--num-leaves 31` 覆盖 yaml（mock LGBMRegressor 验参）|
| AC-NFR0700-03   | `test_ac_nfr0700_03_metadata_repro`       | unit        | `metadata.json` 含 `git_commit_sha/python_version/package_versions` |

### 8.2. 集成测试（Shield 编写，L2 契约仿真）

集成测试覆盖 interfaces.md 中 `modules` 列跨 ≥2 模块的接口契约（happy + 关键错误/边界路径）。模块边界以 architecture.md（Stage 2）为准；此处先列出预期的跨模块契约集成测试范围：

| 集成测试文件                       | 跨模块链路                                  | 覆盖 AC                                   |
| ---------------------------------- | ------------------------------------------- | ----------------------------------------- |
| `tests/integration/test_train_pipeline.py` | 特征→标准化→标签→walk-forward→训练→序列化 | AC-FR0700-05, AC-FR0800-01~04（端到端训练落盘）|
| `tests/integration/test_predict_service.py`| 序列化→加载→预测→落盘                      | AC-FR0900-01~04（真实模型加载 + DataLoader 替身）|
| `tests/integration/test_backtest_cli.py`   | 策略→broker→BacktestRunner→报告            | AC-FR1100-01~03（CLI 退出码/输出文件/参数校验）|
| `tests/integration/test_eval_output.py`   | 回测→IC 评估→CSV 落盘                      | AC-FR1300-04                              |
| `tests/integration/test_feature_importance_cli.py` | 训练→特征重要性→CLI 打印          | AC-FR1400-02                              |
| `tests/integration/test_cli_override.py`  | CLI→config→训练参数                        | AC-NFR0700-02                             |
| `tests/integration/test_real_fetcher.py`  | 真实 fetcher 全市场                        | AC-NFR0100-02（`@pytest.mark.integration`，L3，默认跳过）|

> 集成测试使用 fixture 支撑的 DataLoader 替身（L2），不连真实行情 DB。`test_real_fetcher.py` 为唯一 L3 测试，打 `@pytest.mark.integration`，CI 默认 deselect。

### 8.3. E2E 测试（Shield 编写，L1 完整链路）

见 §6.5。单文件 `tests/e2e/test_lgbm_pipeline.py`，覆盖 `AC-FR1500-01/02/03`，完整链路 train→predict→backtest→报告，≤60s，无外部依赖。

---

## 9. AC 覆盖映射总表

> 下表确认 79 条 AC 全部有测试覆盖。CI 通过 `check_acs.py` 扫描测试代码中的 `AC-FRXXXX-YY` 引用强制闭环，本表为规划依据（非反向生成的覆盖率矩阵）。

| FR/NFR    | AC 数 | 覆盖层              | 测试函数命名模式                  |
| --------- | ----- | ------------------- | --------------------------------- |
| FR-0100   | 3     | unit                | `test_ac_fr0100_0[1-3]_*`         |
| FR-0200   | 3     | unit                | `test_ac_fr0200_0[1-3]_*`         |
| FR-0300   | 2     | unit                | `test_ac_fr0300_0[1-2]_*`         |
| FR-0400   | 3     | unit                | `test_ac_fr0400_0[1-3]_*`         |
| FR-0500   | 5     | unit                | `test_ac_fr0500_0[1-5]_*`         |
| FR-0600   | 2     | unit                | `test_ac_fr0600_0[1-2]_*`         |
| FR-0700   | 5     | unit(4) + integration(1) | `test_ac_fr0700_0[1-5]_*`    |
| FR-0800   | 4     | unit                | `test_ac_fr0800_0[1-4]_*`         |
| FR-0900   | 4     | unit                | `test_ac_fr0900_0[1-4]_*`         |
| FR-1000   | 5     | unit(async)         | `test_ac_fr1000_0[1-5]_*`         |
| FR-1100   | 3     | integration         | `test_ac_fr1100_0[1-3]_*`         |
| FR-1200   | 3     | unit                | `test_ac_fr1200_0[1-3]_*`         |
| FR-1300   | 4     | unit(3) + integration(1) | `test_ac_fr1300_0[1-4]_*`    |
| FR-1400   | 3     | unit(2) + integration(1) | `test_ac_fr1400_0[1-3]_*`    |
| FR-1500   | 3     | e2e                 | `test_ac_fr1500_0[1-3]_*`         |
| FR-1600   | 5     | unit                | `test_ac_fr1600_0[1-5]_*`         |
| NFR-0100  | 4     | unit(3) + integration/L3(1) | `test_ac_nfr0100_0[1-4]_*`  |
| NFR-0200  | 3     | unit                | `test_ac_nfr0200_0[1-3]_*`        |
| NFR-0300  | 1     | CI gate             | `pytest --cov` TOTAL≥95%          |
| NFR-0400  | 3     | unit(1) + CI gate(2)| `test_ac_nfr0400_02_*` + ruff/uv  |
| NFR-0500  | 4     | unit(3) + CI gate(1)| `test_ac_nfr0500_0[2-4]_*` + ruff |
| NFR-0600  | 4     | unit(2) + CI gate(2)| `test_ac_nfr0600_0[2-3]_*` + grep/bandit |
| NFR-0700  | 3     | unit(2) + integration(1) | `test_ac_nfr0700_0[1-3]_*`   |
| **合计** | **79**| —                   | **79/79 全覆盖**                   |

**测试函数统计**：
- 单元测试函数：约 60 个（含 5 个 async 策略测试）
- 集成测试函数：约 12 个（含 1 个 L3 真实 fetcher，默认跳过）
- E2E 测试函数：3 个（同文件，≤60s）
- CI 门禁项：6 个（覆盖率/ruff×2/uv/grep/bandit，非测试函数，由 CI 配置强制）

---

## 10. 评审清单

- [x] 测试策略覆盖主要风险（金融计算正确性、外部数据依赖、异步策略、可视化环境）
- [x] 每个 AC 可追溯到测试代码（§9 总表 + §8 分模块表，CI 强制闭环）
- [x] test-plan 不维护具体测试清单 / 覆盖率矩阵（覆盖率由 check_acs.py 反向生成）
- [x] 反模式 CI 门禁已启用（§1.3 + §7）
- [x] 测试数据来源可复现（§2.4 fixture 合成，种子 42）
- [x] tests/ 布局已文档化（§2.1）
- [x] §3 Ground Truth 方法已文档化（金融计算需独立参考实现）
- [x] §6 外部依赖分层测试已文档化（millionaire fetcher/broker 边界判定）
- [ ] interfaces.md 与 test-plan 闭环（Stage 2 产出后补勾：每个外部出口有测试覆盖）
- [ ] interfaces.md 跨模块接口标注 `modules` 列并纳入集成覆盖（Stage 2）
- [x] e2e 范围限于 happy path（边界/错误/异常路由到集成测试）
