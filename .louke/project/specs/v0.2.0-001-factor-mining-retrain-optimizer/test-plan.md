# trader-off v0.2.0 — 因子挖掘·再训练调度·组合优化器 — Test Plan

- **Spec ID**: v0.2.0-001-factor-mining-retrain-optimizer
- **Created**: 2026-07-17
- **Related spec**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/spec.md`
- **Related acceptance**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/acceptance.md`
- **Related interfaces**: `.louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/interfaces.md`（断言依据，见 §6.6；Stage 2 / M-ARCH 产出后闭环）
- **继承基线**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/test-plan.md`（v0.1.0 测试立场、目录布局、Ground Truth 隔离规则仍生效）
- **Test framework**: pytest（`project.toml [meta].test_framework = "pytest"`，本阶段不变更）

> **AC 编号约定**：本计划中 AC 引用统一使用 `AC-FRXXXX-YY` / `AC-NFRXXXX-YY` 格式（4 位 FR 编号 + 2 位 AC 序号，零填充）。例如 FR-0100 的第 1 条 AC 记为 `AC-FR0100-01`。CI 通过 `lk agent archer ci-scan` 扫描 `tests/` 下测试代码 docstring 中的 AC 引用，校验「每个 AC ≥1 个测试引用，每个测试 ≥1 个 AC 引用」（见 §7）。

---

## 1. 立场与边界

### 1.1. 黑盒声明

本测试计划只声明**可从系统外部观察**的测试方法。可观察对象限于：

- 公共 API / SDK 接口（`list_templates`、`enumerate_factors`、`evaluate_factor`、`select_factors`、`compute_psi`、`compute_feature_ks`、`estimate_covariance`、`build_expected_returns`、`check_constraints`、`compare_to_baseline`、`RetrainScheduler` 公开方法等）
- CLI 端点（`trader-off mine-factors` / `scheduler start|stop|status|list-tasks` / `retrain trigger|status|cancel` / `optimize` / `deploy`，以及 v0.1.0 继承的 `train|predict|backtest|feature-importance`）
- REST API 端点（`POST /retrain/trigger`、`GET /retrain/status`、`POST /retrain/cancel/{task_id}`，默认仅 127.0.0.1:8765）
- 持久化数据文件（`factor_registry/*.yaml|json`、`models/registry.json`、`models/v*/`、`scheduler_state/*.json|jsonl|parquet`、`reports/factor_mining_<ts>/*`、`reports/drift_<ts>/*`、`reports/portfolio_<ts>/*`）
- 结构化日志条目（loguru INFO / WARNING / ERROR，关键词断言）
- 可被 matplotlib 读取的静态图表文件（PNG）
- 进程退出码 / stdout / stderr

### 1.2. 非可观察对象（测试不直接依赖）

- lightGBM 内部 Booster 树结构细节（仅通过公开属性与 `refit` 调用事实观察）
- cvxpy / scipy 求解器内部迭代状态（仅通过 `weights_diagnostics.json` 的 `solver_status / solve_time_sec / iterations` 出口观察）
- APScheduler / croniter 内部调度状态机（仅通过 `next_cron_fire` 返回值与触发事实观察）
- `RetrainScheduler` 内部 asyncio 队列与锁的实现细节（仅通过公开方法 `get_status()`、`trigger_now()` 返回值与 `scheduler_state/` 落盘文件观察）
- 中间 DataFrame 结构、内部缓存、私有方法

> **可观察契约**：任何 AC 验证所需的内部状态，必须由实现层通过 dump / log / 持久化文件 / 公开属性提供观察出口。这是 **interfaces.md** 的职责——若某 AC 需观察内部状态，interfaces.md 必须有对应出口（见 §6.6）。本计划已识别 v0.2.0 的 4 个关键可测试性需求（§6.7），Stage 2 必须落入 interfaces.md。

### 1.3. 作弊模式（CI 强制拦截）

| #   | 作弊模式                | 典型症状                                       |
| --- | ----------------------- | ---------------------------------------------- |
| 1   | 改断言迁就实现          | spec 说「抛异常」，测试改成「返回 False」       |
| 2   | 用 skip 逃避验证        | `pytest.skip` 写「见 e2e」但 e2e 从不编写        |
| 3   | 断言降级                | `assert issubclass(X, Exception)` 而非真正提交并捕获 |
| 4   | try/except: pass        | 异常路径被吞掉                                  |
| 5   | 过度 mock               | mock 框架核心（调度循环/求解器/漂移判定），测的是 mock 行为 |
| 6   | Ground truth 用实现自身 | 期望值 = 被测实现的输出                          |
| 7   | 硬编码期望值            | `assert psi == 0.23` 仅为当前实现凑数            |
| 8   | 平凡通过                | `assert True` / `assert 1 == 1`                 |

v0.2.0 特有作弊变体（CI 与 review 重点关注，详见 §10.1）：

| #   | 变体                     | 典型症状                                                     |
| --- | ------------------------ | ------------------------------------------------------------ |
| 9   | 真实时钟等待             | `time.sleep(65)` 等 cron 触发；断言依赖 `datetime.now()`      |
| 10  | 自杀式 kill -9           | 在 pytest 进程内 `os.kill(os.getpid(), SIGKILL)` 模拟崩溃     |
| 11  | 求解器数值脆性           | `assert weights == [0.1, 0.05, ...]` 精确相等，跨平台即 flake |
| 12  | fixture 泄漏             | `scheduler_state/`、`models/`、`reports/` 写到仓库根目录共享   |
| 13  | 异步泄漏                 | 测试结束遗留 dangling task / 未关闭 aiohttp session           |

### 1.4. 防护措施（CI 检查 + PR 流程）

1. **AC 强制溯源**
   - 每个测试函数 docstring 第一行必须包含 `AC-FRXXXX-YY`（4 位 FR + 2 位 AC 序号）
   - CI 扫描 `tests/`，校验：每个测试引用 ≥1 个 AC；每个 AC 被 ≥1 个测试引用
   - 任一检查失败阻断合并

2. **断言禁忌**（CI 静态检查，违规阻断合并）
   - 禁止 `assert True` / `assert 1` / `assert <obj> is not None` 作为唯一断言
   - 禁止 `try: ... except: pass` 包裹被测代码
   - 禁止无 issue 链接的 `pytest.skip` / `@pytest.mark.skip`
   - 禁止在 unit / integration / e2e 默认层中使用真实 `time.sleep()` 等待调度事件（L3 除外）；等待必须用 `asyncio.wait_for` + 虚拟时钟或 `asyncio.Event`

3. **测试变更分类**（PR 描述必填）
   - [ ] 新增 AC（链接 acceptance.md commit）
   - [ ] Spec 变更（链接 spec commit）
   - [ ] 修复 flake / 环境问题（链接 issue）
   - **禁止类**：「实现行为与 spec 不符 → 改测试」直接 review 拒绝

4. **可测试性兜底**（若某 AC 无法测试）
   - 不通过 mock 内部强行通过
   - 登记为框架侧可测试性需求，请求实现层增加公开装配点（v0.2.0 已识别 4 项，见 §6.7）
   - 解决前标记该 AC 为「blocked by testability gap」

### 1.5. 测试分工

- **单元测试**：由**实现者**（Devon）编写，随实现一起在 R-G-R 中提交
- **集成测试**：由**测试负责人**（Shield）编写，覆盖 interfaces.md 定义的跨模块接口契约
- **E2E / 性能测试**：由**测试负责人**（Shield）编写，e2e 仅覆盖面向用户的 happy path；性能预算（NFR-0100）在 e2e 层计时
- **Ground Truth（§3）**：由**未参与被测实现**的独立开发者或**第三方库**提供
- **Review 归属**：所有测试变更由测试负责人 review；Ground Truth 脚本变更需重点 review 其与对应 AC 的语义一致性

---

## 2. 测试环境

### 2.1. 目录布局

```
tests/
├── unit/                    # 单元测试；镜像源文件目录结构
│   ├── factor_mining/       # FR-0100~0700（模板/枚举/评估/选择/热力图/注册表/报告）
│   ├── scheduler/           # FR-1500~2600（core/cron/drift/perf/registry/state/decision）
│   ├── portfolio/           # FR-3000~4000（协方差/mu/行业/约束/求解/校验/对比/落盘）
│   ├── strategies/          # FR-4200 OptimizedTopKStrategy（沿用 v0.1.0 目录）
│   └── nfr/                 # NFR 单元级 AC（异步签名/日志格式/路径校验/随机种子）
├── integration/             # 集成测试；验证跨模块接口契约（见 §8.2）
├── e2e/                     # 端到端场景测试（仅 happy path，见 §6.5 / §8.3）
│   ├── test_factor_mining_e2e.py
│   ├── test_scheduler_retrain_e2e.py
│   ├── test_optimize_e2e.py
│   └── test_full_pipeline_e2e.py
├── perf/                    # 性能预算测试（NFR-0100，打 e2e marker，见 §8.3）
│   ├── test_perf_budgets.py
│   └── baselines.json       # 性能基准记录（允许 5% 浮动，spec NFR-0100）
├── fixtures/
│   └── v0.2.0/              # 版本化 fixture + MANIFEST.json（NFR-0800 AC-3）
├── assets/                  # 单元测试用小型合成数据
└── ground_truth/            # 独立参考实现；禁止 import trader_off.*（见 §3.2）
```

> - 单元测试与 E2E 使用不同数据（按时间/场景分离）防止过拟合
> - E2E **禁止** mock 框架内部实现（如需 mock，应改写 AC）
> - E2E **禁止**依赖框架私有 API
> - 所有写盘测试（`factor_registry/`、`models/`、`scheduler_state/`、`reports/`、`logs/`）必须使用 `tmp_path` 或 `monkeypatch.chdir(tmp_path)` 隔离，禁止落到仓库根目录（防 fixture 泄漏，§10.1 #12）

### 2.2. 命名约定

- 文件：`test_<scenario>__<subscenario>.py`
- 函数：`test_ac_<id>_<subscenario>`，例如 `test_ac_fr1700_01_same_distribution`
- 每个测试函数 docstring 第一行：`"""AC-FR1700-01: 描述"""`（CI 溯源锚点）
- pytest marker：
  - `@pytest.mark.integration`：集成测试（`tests/integration/`）
  - `@pytest.mark.e2e`：端到端与性能测试（`tests/e2e/`、`tests/perf/`）
  - `@pytest.mark.slow`：耗时 > 30s 的用例（配合 `pytest-timeout` 单测级超时）
  - 异步用例：`asyncio_mode = "auto"`（继承 v0.1.0 `pyproject.toml` 配置），无需逐函数标注

### 2.3. 执行

- **离线**：测试不依赖网络（数据 pinned 到 fixture / assets）；unit 与 e2e 默认层用 `pytest-socket` 禁用网络（L3 除外）
- **执行顺序**：unit（快）→ integration → e2e / perf（慢）
- **CI**：每次 push 运行全套（L3 除外）
- **隔离**：集成与 e2e 使用 pytest marker 避免与单元测试混跑
  - 默认：`uv run pytest tests/unit -q --cov=trader_off`（CI 默认 + 覆盖率，NFR-0200 ≥97%）
  - 集成：`uv run pytest tests/integration -m integration -v`（`project.toml [integration].run`）
  - E2E + 性能：`uv run pytest tests/e2e tests/perf -m e2e -v`（`project.toml [e2e].run`，本阶段同步更新，见 §6.5）
  - 超时策略：全局不再设 `--timeout=90`（全链路 e2e 预算 600s，见 §6.5）；每个 e2e/perf 用例用 `@pytest.mark.timeout(<预算>)` 单测级声明

### 2.4. 测试数据

本项目有外部数据依赖（A 股日线行情、行业映射、v0.1.0 模型 artifact），需离线 fixture。

- **来源**：合成生成（确定性脚本生成虚拟股票 OHLCV + turnover + 行业映射 + 预测分数；固定随机种子 42）
- **可复现**：每次 CI 运行产出一致结果（固定种子、固定日期范围、固定资产生成规则）
- **版本化 fixture**（`tests/fixtures/v0.2.0/`，NFR-0800 AC-3）：
  - `ohlcv_50x252.parquet`：50 只虚拟股票 × 252 个交易日完整 OHLCV + turnover（scenario-0050 / 模块 e2e 主 fixture）
  - `ohlcv_4000x60.parquet`：4000 资产 × 60 日（NFR-0100 AC-2 predict ≤5s 性能 fixture，合成稀疏数据）
  - `industry_map.csv`：50 资产 → 10 个一级行业（FR-3200 / 优化 e2e）
  - `predictions_fixture.csv`：列 `asset, score, rank`（FR-3100 / 优化 e2e 输入）
  - `v010_model/`：v0.1.0 已序列化模型目录（`20260101_120000` 格式，NFR-1000 兼容性测试用，从 v0.1.0 仓库复制并冻结）
  - `fundamental_columns.parquet`：含 PE/PB/ROE/营收增速列的可选 fixture（FR-0100 fundamental 模板启用路径）
  - `MANIFEST.json`：每个文件的 SHA256 校验和 + 生成参数 + 生成时间；CI 校验完整性
- **仓内小数据**：`tests/assets/`（单元测试用小型构造数据，如 10 资产 × 30 日）
- **敏感数据**：不提交；本项目无真实凭证需求（NFR-0700）
- **fixture 生成脚本**：`tests/fixtures/v0.2.0/gen_fixture.py`，记录生成参数；重新生成必须同步更新 `MANIFEST.json`

### 2.5. 测试工具链

| 工具               | 版本约束        | 用途                                                     |
| ------------------ | --------------- | -------------------------------------------------------- |
| pytest             | >= 8.0          | 测试框架主框架（继承 v0.1.0）                             |
| pytest-cov         | >= 5.0          | 覆盖率收集（NFR-0200 ≥97%）                               |
| pytest-asyncio     | >= 0.23         | 异步调度器 / 策略 / API 测试（FR-1500/2000/4200）          |
| pytest-mock        | >= 3.12         | mock TrainerPort / broker / cvxpy ImportError 仿真        |
| pytest-timeout     | >= 2.3          | e2e/perf 单测级超时（替代全局 `--timeout=90`）             |
| pytest-socket      | >= 0.7          | 禁用网络（unit/e2e 默认层离线保证）                        |
| polars             | >= 1.0          | 测试数据构造与断言（与生产一致）                            |
| numpy              | >= 1.26         | 数值断言 / Ground Truth 参考实现                           |
| scipy              | >= 1.13         | Ground Truth：IC pearson/spearman、KS 参考                 |
| scikit-learn       | >= 1.3          | LedoitWolf 参考实现（FR-3000 Ground Truth）                |
| lightgbm           | >= 4.3          | 训练 / refit 测试（FR-2100/2200）                          |
| cvxpy              | >= 1.5          | 优化求解默认路径（FR-3700；CI 必装，fallback 路径单独仿真） |
| apscheduler        | >= 3.10         | cron 触发（FR-1600；或 croniter，Stage 2 定稿）            |
| aiohttp            | >= 3.9          | 调度器 REST API 测试客户端（FR-2000）                      |
| matplotlib         | >= 3.7          | 可视化测试（FR-0500/0700，Agg backend）                    |
| loguru             | >= 0.7          | 日志断言（caplog）                                        |
| psutil             | >= 5.9          | 内存峰值监控（NFR-0100 AC-4）                              |
| mutmut             | >= 2.0          | Mutation testing（NFR-0300 ≥80%）                          |
| bandit             | >= 1.7          | 安全扫描（NFR-0700 AC-5）                                  |
| ruff               | >= 0.5          | lint / 风格检查（NFR-0500）                                |
| pydantic           | >= 2.7          | CLI / 配置校验测试                                         |
| pyyaml             | >= 6.0          | 因子注册表 / 配置加载（`yaml.safe_load` only）             |

> 新增运行时依赖（`cvxpy`、`apscheduler`、`aiohttp`、`psutil`）与开发依赖（`mutmut`）由 Devon 在 Stage 2 / R-G-R 阶段落入 `pyproject.toml`（NFR-0500 AC-3 验证 `uv sync` 后全部可 import）。pytest 插件配置继承 v0.1.0 `pyproject.toml [tool.pytest.ini_options]`，仅需确认 `e2e` / `integration` / `slow` marker 已注册（v0.1.0 已注册）。

---

## 3. Ground Truth 方法

本项目涉及金融计算正确性（IC/ICIR/PSI/KS/协方差/Max Sharpe/绩效指标），需 Ground Truth 验证，禁止硬编码期望值。

### 3.1. 通用原则

所有 Ground Truth 由**独立来源**在测试运行时计算：

| 计算类型                                              | 独立来源                                                                 |
| ----------------------------------------------------- | ------------------------------------------------------------------------ |
| IC / Rank IC（FR-0300）                               | **第三方库**：`scipy.stats.pearsonr` / `spearmanr`（继承 v0.1.0 `ic_ref.py`） |
| PSI（FR-1700）                                        | **手算脚本**：`tests/ground_truth/psi_ref.py` 用纯 numpy 独立实现分箱 + Σ(p-q)·ln(p/q) |
| KS（FR-1800）                                         | **数据本身**：已知分布（同分布 / 均值偏移 2σ，seed=42）的 p 值区间断言      |
| 协方差（FR-3000）                                     | **第三方库 + 性质断言**：`numpy.cov` 作 sample 参考；LW 路径断言对称 / 正定 / 收缩距离等数学性质（不断言具体数值） |
| Max Sharpe（FR-3700 AC-2）                            | **手算脚本**：`tests/ground_truth/max_sharpe_ref.py` 闭式解（无约束 `w* ∝ Σ⁻¹μ` 归一化），10 资产小 fixture 对比偏差 < 5% |
| 等权基线指标（FR-3900）                               | **手算脚本**：`mu^T w`、`sqrt(w^T Σ w)`、`0.5·Σ|w-w_prev|` 纯 numpy 重算   |
| cron 下次触发（FR-1600 AC-4）                         | **第三方库**：`croniter.croniter(expr, base).get_next(datetime)` 直接作参考 |
| 因子公式（FR-0100/0200 抽样）                         | **手算脚本**：对 `momentum_N`、`vol_N` 等基础模板用小型 close 序列手算期望值 |
| 简单规则（交易日判定、非法参数跳过、缺失行业处理）     | **数据本身**：测试数据集为唯一真相源                                      |

> 核心设计：Ground Truth 是**可重算的脚本**，而非文档固定值。测试运行时同一数据 + Ground Truth 脚本计算后与框架输出对比。

### 3.2. Ground Truth 隔离（强制规则，继承 v0.1.0）

为防止「期望值 = 被测实现输出」的循环验证（§1.3 作弊 #6）：

1. **代码位置**：所有 Ground Truth 脚本存放于 `tests/ground_truth/`（unit/e2e 共享）
2. **导入禁忌**：`tests/ground_truth/**/*.py` **禁止** `import trader_off.*`（含子模块）；CI 静态检查违规阻断合并
3. **允许依赖**：仅标准库 + 测试数据文件 + 约定的第三方库（numpy / scipy / polars / scikit-learn / croniter 作为算法参考实现）
4. **数据访问**：直接从 `tests/assets/` / `tests/fixtures/v0.2.0/` 读数据文件，**不**通过框架 SDK
5. **Review 归属**：Ground Truth 脚本变更由测试负责人 review，重点校验与对应 AC 的语义一致性

---

## 4. 测试范围

本测试计划覆盖 spec.md 中所有 Valid / Testable / Decided 全绿的 FR/NFR（共 45 项，159 条 AC）。

| Valid | Testable | Decided |
| ----- | -------- | ------- |
| ✅    | ✅       | ✅      |

覆盖矩阵：模块 A（FR-0100~0900，9 项，36 AC）+ 模块 B（FR-1500~2700，13 项，51 AC）+ 模块 C（FR-3000~4200，13 项，41 AC）+ NFR（NFR-0100~1000，10 项，31 AC）= **159 AC 全覆盖**。

v0.1.0 已锁定的 FR-0100~1600 / NFR-0100~0700 不在本计划重复覆盖；其回归保障由 NFR-1000 向后兼容集成测试（§8.2）+ v0.1.0 既有测试套件继续承担。

---

## 5. 验收标准

1. 单元测试覆盖率 ≥97%（行覆盖，`pytest-cov`，NFR-0200）
2. interfaces.md 中定义的每个跨模块接口契约至少有 1 个集成测试（happy + 关键错误/边界路径）
   > **跨模块接口** = interfaces.md 中 `modules` 列列出 ≥2 个模块的条目（Archer 在 Stage 2 从 architecture.md 模块边界标注，Shield 据此清单编写，不自行推断）
3. Stories 与 Spec 中的 5 个用户场景（scenario-0010~0050）由 e2e happy path 完全覆盖并通过
4. 所有 159 条 AC 有对应测试覆盖（AC 引用闭环，`lk agent archer ci-scan` 强制）
5. §6 外部依赖分层测试：L1/L2 默认 CI 通过；L3 在对应环境可运行
6. Mutation testing 得分 ≥80%（mutmut，NFR-0300，作用于 `factor_mining/`、`scheduler/`、`portfolio/` 三模块）
7. 性能预算全部满足（NFR-0100：因子挖掘 ≤600s、全量训练 ≤300s、增量重训 ≤60s、预测 ≤5s、回测 ≤600s、漂移检测 ≤30s、内存峰值 ≤16GB）

---

## 6. 外部依赖分层测试

本项目有外部依赖：A 股日线行情（millionaire `quantide.data.fetchers` / v0.1.0 `data_loader` 抽象）、**系统时钟**（cron / 漂移检测每日 09:00 / 调度 tick）、cvxpy 求解器（可选）、aiohttp 网络栈（调度器 API）、matplotlib 渲染环境。

### 6.1. 三大约束

| #   | 约束                                  | 后果                                                         |
| --- | ------------------------------------- | ------------------------------------------------------------ |
| C1  | 测试环境无法连生产依赖（真实行情 DB）  | CI / 跨平台开发机无法跑真实 fetcher 路径                      |
| C2  | 无法等待真实时间                       | cron 16:00 触发、每日 09:00 漂移检测、跨 5 交易日全量重训节奏均不可真实等待 |
| C3  | 不能 mock 框架内部实现                 | 替换/patch 调度循环、漂移判定、求解器包装会绕过被测行为，违反黑盒 |

> §2 离线数据环境无法让带外部依赖的路径跑起来——本节正是为此存在。**v0.2.0 与 v0.1.0 的最大差异是 C2**：调度器是时间驱动系统，必须引入虚拟时钟。

### 6.2. 立场：可控替换 vs Mock

- **可替换外部依赖**（可控）：壁钟（系统时钟）、外部服务（fetcher 行情源）、远程 API、cvxpy 求解器（仅 ImportError 仿真）— 这些是被测框架的**外部依赖**，可用确定性替身替换
- **不可 mock 内部实现**：因子枚举 / IC 评估 / Top-K 选择 / PSI-KS 判定 / 漂移决策编排 / 调度循环 / 版本 GC / 约束建模 / 后验校验 — 这些是**被测对象**，不得 mock

> **边界铁律**：任何情况下不得替换/绕过框架自身关键实现以「让测试通过」。若测试发现必须绕过才能通过，说明 AC 可观察性设计有误；应修订 interfaces/acceptance，而非在测试侧打补丁。

**v0.2.0 边界判定**（在 v0.1.0 基础上新增）：

| 组件                                   | 判定       | 测试处理方式                                                     |
| -------------------------------------- | ---------- | ---------------------------------------------------------------- |
| `quantide.data.fetchers` / data_loader | 外部依赖   | fixture 支撑的 DataLoader 替身（L1/L2）                           |
| 系统时钟                               | 外部依赖   | **虚拟时钟注入**（`now_fn` / Clock port，见 §6.7 T-1）            |
| `TrainerPort`（包装 v0.1.0 train_model）| 外部 port  | 调度器**单元**测试用 mock 记录调用；**集成**测试用真实 train_model |
| `ModelRegistry` / `DriftDetector` / `PerfMonitor` | 被测对象（作为 port 注入） | 调度器 core 单测可替换为记录型替身；自身行为由各自 FR 的单测覆盖 |
| lightGBM `Booster.refit`               | 外部库     | 不 mock；仅 FR-2200 AC-2 按 AC 显式要求用 mock 验证「调用了 refit 而非 fit」 |
| cvxpy                                  | 外部库     | 不 mock；仅 FR-3700 AC-3/AC-4 按 AC 显式要求仿真 ImportError / 验证 solver kwargs |
| aiohttp（调度器 API）                  | 外部依赖   | 集成测试用 aiohttp test client 起真实 app（localhost），不 mock 路由 |
| `BacktestBroker` / `BacktestRunner`    | 被测框架   | 单测 mock broker 接口（仅验证调用）；E2E 用真实组件 + fixture      |
| `BaseStrategy` 生命周期                | 被测对象   | 不得 mock                                                         |

### 6.3. 三层测试金字塔

按保真度/成本/速度分三层，各层覆盖的 AC 不重叠，marker 严格区分运行时机。

| 层 | 名称           | 时钟         | 速度   | 覆盖                                                       | 默认运行       |
| -- | -------------- | ------------ | ------ | ---------------------------------------------------------- | -------------- |
| L1 | 确定性仿真     | 虚拟时钟     | 秒级   | 大部分业务 AC（因子/评估/选择/PSI/KS/协方差/约束/求解/策略） | ✅ CI 默认     |
| L2 | 契约仿真       | 虚拟时钟     | 秒级   | 跨模块接口契约 AC（CLI/调度↔训练/部署↔预测/优化↔策略/API）   | ✅ CI 默认     |
| L3 | 真实环境冒烟   | 真实日历     | 真实   | 真实 fetcher 全市场单次冒烟（继承 v0.1.0 `test_real_fetcher.py`）| ❌ nightly/手动 |

- **L1 确定性仿真**：用虚拟时钟 + fixture DataLoader 替换「时间推进」与「外部行情数据源」，跑通 cron 触发、漂移检测、重训、优化等业务周期
- **L2 契约仿真**：启动遵循同协议的替身（fixture DataLoader、aiohttp test server、tmp_path 文件系统）；框架与替身交互
- **L3 真实环境冒烟**：真实日历 + 真实 fetcher，单次往返冒烟；默认 deselect，仅在有真实依赖环境运行（v0.2.0 不新增 L3，继承 v0.1.0 既有 1 个）

> 任何 L3 测试**必须**打对应 marker（替代 §1.4 的 skip）；不得用无 issue 链接的 skip 逃避 L3。

### 6.4. 测试基础设施责任契约

定义各替身组件的**职责 + 外部可观察边界**，供测试工程师实现。**不规定内部实现细节**。

| 组件               | 职责（外部）                                          | 边界（不实现）                              |
| ------------------ | ----------------------------------------------------- | ------------------------------------------- |
| 虚拟时钟           | 给定「当前时间」+ 可快进（按秒/按交易日步进）          | 不实现 cron 解析 / 跨日结算逻辑              |
| DataLoader 替身    | 按资产 + 日期范围从 fixture 返回 OHLCV / fundamental  | 不实现特征计算 / 业务规则                    |
| 记录型 Trainer 替身| 记录 `train(mode, ...)` 调用次数、顺序、参数           | 不实现真实训练（集成测试用真实 train_model） |
| Mock Broker（单测）| 记录 `trade_target_pct` 调用次数与参数                 | 不实现真实撮合（E2E 用真实 BacktestBroker）  |
| aiohttp test client| 对真实 app 发 HTTP 请求（localhost）                  | 不 mock 路由 / 不绕过 pydantic 校验          |
| 崩溃编排器         | 在**子进程**中运行调度器 → SIGKILL → 重启 → 检查状态   | 不在 pytest 进程内自杀（§10.1 #10）          |
| 回测编排器         | 组装替身 + 推进时间                                    | 不代框架执行业务                             |

### 6.5. E2E 测试计划（Shield 编写）

> **本节是 Shield（M-E2E）的关键输入。** v0.2.0 有 5 个用户场景，映射为 4 个 e2e 文件 + 1 个性能文件。e2e 仅覆盖 happy path；边界/错误/异常路径全部路由到集成测试（§8.2）。

| e2e 文件                              | 场景              | 覆盖 AC（happy path 主断言）                                                                 | 运行预算                |
| ------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------- | ----------------------- |
| `tests/e2e/test_factor_mining_e2e.py` | scenario-0010     | AC-FR0800-01（CLI 退出码 0 + stdout）、AC-FR0600-01/02（注册表落盘）、AC-FR0700-01/02（HTML/MD 报告）| ≤600s（NFR-0100 AC-1）  |
| `tests/e2e/test_scheduler_retrain_e2e.py` | scenario-0020+0030 | AC-FR2700-01（scheduler start）、AC-FR2100-01/02（全量重训落盘 + registry）、AC-FR2400-01（自动部署）、AC-FR2600-04（漂移报告落盘）| ≤300s（虚拟时钟加速） |
| `tests/e2e/test_optimize_e2e.py`      | scenario-0040     | AC-FR4100-01（CLI 退出码 0 + Sharpe 输出）、AC-FR4000-01/02（5 产物 + weights sum=1）、AC-FR3800-03（report 字段）、AC-FR3900-01（基线对比）| ≤120s |
| `tests/e2e/test_full_pipeline_e2e.py` | scenario-0050     | AC-FR0900-01（train --factor-registry 元数据）、AC-FR4200-02（策略加载 weights）、全链路 wall time ≤600s + 内存 ≤16GB（NFR-0100 AC-3/AC-4）| ≤600s |
| `tests/perf/test_perf_budgets.py`     | NFR-0100 全项     | AC-NFR0100-01（因子挖掘 ≤600s）、AC-NFR0100-02（预测 ≤5s，4000 资产 fixture）、AC-NFR0100-03（回测 ≤600s）、AC-NFR0100-04（内存 ≤16GB，psutil）、AC-NFR0100-05（增量重训 ≤60s）| 各预算 +10% 超时上限 |

**统一约束**：

- 所有 e2e 用 `@pytest.mark.e2e`；perf 用例额外 `@pytest.mark.slow` + `@pytest.mark.timeout(<预算+10%>)`
- 调度器 e2e 使用**虚拟时钟**（注入 `now_fn`），将 cron 16:00 / 漂移 09:00 / 5 交易日节奏压缩到秒级；禁止真实等待（§10.1 #9）
- 全链路 e2e 使用 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet`；训练参数缩小（`n_estimators` 降低）以满足 600s 预算，但**不**修改业务逻辑路径
- 无外部依赖：`pytest-socket` 禁用网络；断言无真实 fetcher 调用
- 所有落盘到 `tmp_path`（`factor_registry/`、`models/`、`scheduler_state/`、`reports/`、`logs/` 均通过配置指向临时目录）

**host-project e2e 执行契约**（`project.toml [e2e]`，本阶段同步更新以纳入 `tests/perf/` 并移除全局 90s 超时）：

```toml
[e2e]
paths = ["tests/e2e", "tests/perf"]
run = "uv run pytest tests/e2e tests/perf -m e2e -v"
# 无需 start/ready/teardown：e2e 纯进程内 pytest，不启动外部服务
# 超时由各用例 @pytest.mark.timeout 单测级声明（全链路 660s，模块 e2e 按预算）
```

**host-project integration 执行契约**（`project.toml [integration]`，已存在，本阶段不变更）：

```toml
[integration]
paths = ["tests/integration"]
run = "uv run pytest tests/integration -m integration -v"
```

### 6.6. 断言依据 — 与 interfaces.md 闭环

测试断言**只能**落在 interfaces.md 定义的外部可观察出口上：

- 持久化文件 schema（`factor_registry/factors.yaml`、`selected_factors.json`、`models/registry.json`、`models/v*/metadata.json`、`scheduler_state/last_tasks.json`、`cron_fire_log.jsonl`、`drift_history.parquet`、`reports/*/`)
- API / 函数返回值字段（`FactorEvaluation`、`SelectionDiagnostics`、`DriftDecision`、`TriggerDecision`、`ConstraintReport`、`ComparisonReport`、`SchedulerStatus`、`RetrainTask`）
- CLI 退出码 / stdout / stderr（FR-0800/2000/2700/4100 各自退出码语义）
- REST API 响应（`{task_id}` / `{active_tasks, last_10_tasks}` / `{cancelled: bool}`）
- 结构化日志条目（loguru 关键词：`fundamental templates skipped`、`cron skipped, not a trading day`、`cvxpy unavailable, fallback to scipy.optimize.SLSQP`、`validation failed, not deploying`、`weights.csv missing, falling back` 等）
- 公开属性（`booster.num_trees()`、`registry["current_version"]`、`decision.solver_status`）

> 若某 AC 所需状态在 interfaces.md 中**无**对应可观察出口，这是可观察性缺口；应修订 interfaces/acceptance 增加出口，而非在测试侧窥探内部状态。

### 6.7. 可测试性需求（Stage 2 必须落入 interfaces.md）

以下 4 项是 v0.2.0 测试成立的前提，属于框架侧公开装配点，**Stage 2（M-ARCH）必须在 interfaces.md 中定义为契约**：

| #   | 需求                     | 动机（哪些 AC 依赖）                                              | 期望契约形态                                              |
| --- | ------------------------ | ----------------------------------------------------------------- | --------------------------------------------------------- |
| T-1 | 虚拟时钟注入 port        | FR-1500/1600/2500/2600 全部调度 AC；e2e 时间压缩                   | `RetrainScheduler` 构造或配置接受 `now_fn: Callable[[], datetime]`（或等价 Clock protocol），默认真实时钟 |
| T-2 | 调度器 port 注入         | FR-1500 AC-1/AC-2（mock trainer 验证串行）                         | 构造函数注入 `trainer: TrainerPort`（spec 已定义），TrainerPort 为公开 protocol |
| T-3 | `next_cron_fire` 纯函数  | FR-1600 AC-4（cron 解析正确性）                                    | `next_cron_fire(expr: str, base: datetime) -> datetime`（spec 已定义签名） |
| T-4 | 配置驱动的落盘根目录     | 全部写盘 AC 的 tmp_path 隔离（§2.1）                               | 所有 CLI / 调度器配置支持 `--output` / `state_dir` / `models_dir` / `registry_dir` 覆盖，禁止硬编码仓库根路径 |

---

## 7. CI 门禁

```bash
lk agent archer ci-scan \
  --acceptance .louke/project/specs/v0.2.0-001-factor-mining-retrain-optimizer/acceptance.md \
  --tests tests/
```

校验项：

- **AC 引用闭环**（每个 AC ≥1 测试，每个测试 ≥1 AC）—— `lk agent archer check-acs`
- **反模式静态扫描**（§1.3：无 `assert True`、无 `try/except:pass`、无无链接 skip、无默认层真实 `time.sleep` 等待调度事件）
- **覆盖率 ≥97%** —— `uv run pytest tests/unit --cov=trader_off --cov-report=term-missing`，`TOTAL` 行 ≥97%（NFR-0200）
- **Mutation ≥80%** —— `mutmut run`（作用于 `src/trader_off/factor_mining/`、`src/trader_off/scheduler/`、`src/trader_off/portfolio/`，NFR-0300）
- **Ground Truth 隔离**（§3.2：`tests/ground_truth/` 不 import `trader_off.*`）
- **fixture 完整性** —— `tests/fixtures/v0.2.0/MANIFEST.json` SHA256 校验（NFR-0800 AC-3）
- **安全扫描** —— `bandit -r trader_off/factor_mining/ trader_off/scheduler/ trader_off/portfolio/ -ll`，无 HIGH 级 issue（NFR-0700 AC-5）
- **lint** —— `ruff check trader_off/`，0 error（NFR-0500 AC-1）
- **凭证扫描** —— grep 无 hard-coded credential（NFR-0700 AC-1）；`yaml.load` 禁用扫描（NFR-0700 AC-3）
- **文档同步** —— `python scripts/check_docs_sync.py`（NFR-0400 AC-3）
- **性能预算** —— `tests/perf/test_perf_budgets.py` 全项通过（NFR-0100）

**CI 排除规则**（覆盖率）：`if __name__ == "__main__"` 块、纯数据 fixture、第三方 wrapper 类、cvxpy/scipy 求解器内部代码（只测我们包装的接口，NFR-0200）。

---

## 8. 分层测试计划（按模块）

> 下表为测试规划：每个 FR 映射到测试层与命名模式。详细断言逻辑见 `acceptance.md` 对应章节，本计划不重复断言细节（避免与 `check_acs.py` 反向生成的覆盖率矩阵重复）。CI 通过 docstring 中的 `AC-FRXXXX-YY` 引用强制闭环。状态列：`planned` = 本计划规划，待 Devon/Shield 编写。

### 8.1. 单元测试（Devon 编写，L1 确定性仿真）

#### 模块 A — 因子挖掘（`tests/unit/factor_mining/`）

| FR      | AC 数 | 测试函数命名模式              | 断言要点（详见 acceptance.md）                              | 状态    |
| ------- | ----- | ----------------------------- | ----------------------------------------------------------- | ------- |
| FR-0100 | 4     | `test_ac_fr0100_0[1-4]_*`     | 模板枚举 ≥12 / int_range 展开 / fundamental 跳过 + INFO / 版本头 v1 | planned |
| FR-0200 | 4     | `test_ac_fr0200_0[1-4]_*`     | 枚举数量与唯一 id / 默认 ≥200 / 非法组合跳过 + 落盘 / FactorSpec 字段可调用 | planned |
| FR-0300 | 5     | `test_ac_fr0300_0[1-5]_*`     | FactorEvaluation 字段 / 完全正相关 IC≈1 / 负相关 IC≈-1 / std=0 → icir=0+WARNING / v0.1.0 函数复用 | planned |
| FR-0400 | 4     | `test_ac_fr0400_0[1-4]_*`     | ICIR 降序 / 冗余剔除计数 / 候选 <top_k 全保留+WARNING / ICIR 平局字典序 | planned |
| FR-0500 | 3     | `test_ac_fr0500_0[1-3]_*`     | PNG 存在且 >5KB / 尺寸 1200×1440 / 密集标签字号降级          | planned |
| FR-0600 | 4     | `test_ac_fr0600_0[1-4]_*`     | yaml 字段 + 总数一致 / json 字段 / 目录自动创建 / 缺字段抛 SchemaError | planned |
| FR-0700 | 4     | `test_ac_fr0700_0[1-4]_*`     | 返回 3 个 Path 且非空 / HTML 含 table+img / MD 含表格 / 无 jinja2 依赖 | planned |

#### 模块 B — 再训练调度（`tests/unit/scheduler/`）

| FR      | AC 数 | 测试函数命名模式              | 断言要点                                                     | 状态    |
| ------- | ----- | ----------------------------- | ------------------------------------------------------------ | ------- |
| FR-1500 | 4     | `test_ac_fr1500_0[1-4]_*`     | 4 方法均 async / 并发 2 任务串行（mock TrainerPort）/ stop <5s / 无 quantide 依赖 | planned |
| FR-1600 | 4     | `test_ac_fr1600_0[1-4]_*`     | 下一触发时间（虚拟时钟）/ 非交易日跳过 + INFO / 频率门控 3<5 不触发全量 / `next_cron_fire` 正确性 | planned |
| FR-1700 | 4     | `test_ac_fr1700_0[1-4]_*`     | 同分布 PSI≈0 / 右移 PSI>0.5 / 批量 20 特征列结构 / 全 NaN → psi=0+WARNING | planned |
| FR-1800 | 3     | `test_ac_fr1800_0[1-3]_*`     | 同分布 p>0.05 / 偏移 2σ p<0.001 / 全 NaN → (0.0, 1.0, False)+WARNING | planned |
| FR-1900 | 4     | `test_ac_fr1900_0[1-4]_*`     | 未跌破不触发 / 跌破 ic_floor 触发 / 跌幅 ≥30% 触发 / **无 sharpe 字段 + ic_only 标注 + <1s**（Round-2 锁定，§10.2） | planned |
| FR-2300 | 4     | `test_ac_fr2300_0[1-4]_*`     | keep_latest_n=10 GC / pinned 不删 / full_only 只留全量 / rollback 更新 current_version | planned |
| FR-2500 | 2*    | `test_ac_fr2500_01_*` / `test_ac_fr2500_04_*` | 任务记录字段齐全 / 并发 10 触发 task_id 唯一（*AC-2/AC-3 崩溃恢复路由到集成 §8.2） | planned |
| FR-2600 | 4     | `test_ac_fr2600_0[1-4]_*`     | 轻度不触发 / 中度增量 / 重度全量 / drift_report.json + drift_summary.csv 落盘 | planned |

#### 模块 C — 组合优化器（`tests/unit/portfolio/`）

| FR      | AC 数 | 测试函数命名模式              | 断言要点                                                     | 状态    |
| ------- | ----- | ----------------------------- | ------------------------------------------------------------ | ------- |
| FR-3000 | 4     | `test_ac_fr3000_0[1-4]_*`     | sample 对称正定 / LW 收缩距离 <0.5 / 全 NaN 列剔除 + 落盘 / <30 日抛 InsufficientDataError | planned |
| FR-3100 | 3     | `test_ac_fr3100_0[1-3]_*`     | raw 原分 / zscore 标准化 / 资产不一致抛 AssetMismatchError    | planned |
| FR-3200 | 3     | `test_ac_fr3200_0[1-3]_*`     | 加载 50 行 / 缺失行业记录 + 剔除 / 重复行抛 IndustryMapConflictError | planned |
| FR-3300 | 2     | `test_ac_fr3300_0[1-2]_*`     | Σw=1（1e-6）/ infeasible 返回 None + solver_status           | planned |
| FR-3400 | 2     | `test_ac_fr3400_0[1-2]_*`     | w≥-1e-9 / 负 mu 资产权重 ≈0                                   | planned |
| FR-3500 | 3     | `test_ac_fr3500_0[1-3]_*`     | 行业偏离 ≤δ / tol 覆盖生效 / 行业约束 infeasible              | planned |
| FR-3600 | 2     | `test_ac_fr3600_0[1-2]_*`     | w≤0.10 / --max-weight=0.05 生效                               | planned |
| FR-3700 | 4     | `test_ac_fr3700_0[1-4]_*`     | solver_status optimal + <5s / 解析解偏差 <5%（Ground Truth）/ **cvxpy ImportError → scipy 回退 + INFO**（§10.2）/ solver kwargs 传递 | planned |
| FR-3800 | 3     | `test_ac_fr3800_0[1-3]_*`     | 全通过 violations==[] / 人工违反检出 2 项 / report 字段齐全   | planned |
| FR-3900 | 3     | `test_ac_fr3900_0[1-3]_*`     | ComparisonReport 字段 / 首次 turnover=0.5 / Sharpe 低于基线 WARNING 不阻断 | planned |
| FR-4000 | 2*    | `test_ac_fr4000_01_*` / `test_ac_fr4000_02_*` | 5 产物非空 / weights.csv sum≈1.0（*AC-3 原子性路由到集成 §8.2） | planned |

#### 策略与 NFR 单元级（`tests/unit/strategies/`、`tests/unit/nfr/`）

| FR/NFR  | AC 数 | 测试函数命名模式              | 断言要点                                                     | 状态    |
| ------- | ----- | ----------------------------- | ------------------------------------------------------------ | ------- |
| FR-4200 | 5     | `test_ac_fr4200_0[1-5]_*`     | BaseStrategy 子类 / init 加载 weights / on_day_open 调仓 + 清仓 + extra / weights 缺失降级 WARNING / 陈旧 >5 日降级 | planned |
| NFR-0500| 1     | `test_ac_nfr0500_02_*`        | 调度器 4 方法 + 策略生命周期均 `async def`                    | planned |
| NFR-0600| 1     | `test_ac_nfr0600_02_*`        | 日志格式正则匹配（继承 v0.1.0）                               | planned |
| NFR-0700| 1     | `test_ac_nfr0700_02_*`        | 路径越界抛 PathTraversalError                                 | planned |
| NFR-0800| 2     | `test_ac_nfr0800_0[1-2]_*`    | random_state=42 三种子 / metadata 含 5 个可重现性字段          | planned |

### 8.2. 集成测试（Shield 编写，L2 契约仿真）

集成测试覆盖跨模块接口契约（happy + 关键错误/边界路径）。模块边界以 architecture.md（Stage 2）为准；下表为预期的跨模块契约集成测试范围，Stage 2 将以 interfaces.md `modules` 列为准最终确认：

| 集成测试文件                                | 跨模块链路                                  | 覆盖 AC                                                       | 状态    |
| ------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------- | ------- |
| `tests/integration/test_factor_mining_cli.py` | CLI → 枚举 → 评估 → 选择 → 落盘              | AC-FR0800-01~05（退出码 0/2/3/4 + stdout + pydantic 校验）     | planned |
| `tests/integration/test_train_with_registry.py` | 因子注册表 → v0.1.0 train → 模型元数据      | AC-FR0900-01/02/03（精选因子输入 / feature_names 同步 / 回退兼容）| planned |
| `tests/integration/test_retrain_cli_api.py` | retrain CLI + aiohttp API → 调度器          | AC-FR2000-01~04（trigger/status/cancel + localhost 绑定）      | planned |
| `tests/integration/test_retrain_full.py`    | 调度器 → train_model → save_model → registry | AC-FR2100-01~04（5 文件 / registry 记录 / 版本冲突 / 3 年窗口）| planned |
| `tests/integration/test_retrain_incremental.py` | 调度器 → refit → 增量版本链                 | AC-FR2200-01~04（incr 目录 / refit 调用事实 / 5 日窗口 / 版本链）| planned |
| `tests/integration/test_deploy.py`          | registry 更新 → 预测服务加载（lazy/hot）     | AC-FR2400-01~04（部署成功 / 验证失败不部署 / hot-reload ≤60s / 损坏模型保留旧版）| planned |
| `tests/integration/test_scheduler_cli.py`   | scheduler CLI → 配置加载 → 状态输出          | AC-FR2700-01~04（start/status/缺 cron 字段/非法 cron 表达式）  | planned |
| `tests/integration/test_scheduler_resilience.py` | 子进程调度器 → SIGKILL → 重启恢复         | AC-FR2500-02/03、AC-NFR0900-01~03（原子写 / running→failed / 并发 ≤1 / task_id 幂等）| planned |
| `tests/integration/test_optimize_cli.py`    | optimize CLI → 协方差 → 求解 → 落盘          | AC-FR4100-01~04（退出码 0/2/3 + cov-window 覆盖）              | planned |
| `tests/integration/test_persistence_atomic.py` | 优化落盘 → 中断 → 原子性                    | AC-FR4000-03（无半成品目录）                                   | planned |
| `tests/integration/test_fixture_manifest.py` | fixture 版本化 → SHA256 校验                | AC-NFR0800-03                                                  | planned |
| `tests/integration/test_v010_compat.py`     | v0.1.0 模型/策略/CLI → v0.2.0 环境          | AC-NFR1000-01~04（旧模型加载 / predict schema / 旧 CLI / 旧策略）| planned |
| `tests/integration/test_log_files.py`       | 三模块运行 → 日志文件落盘                    | AC-NFR0600-03（factor_mining/scheduler/portfolio 日志文件存在）| planned |
| `tests/integration/test_api_security.py`    | 调度器 API 网络绑定                          | AC-NFR0700-04（默认仅 127.0.0.1，外部连接拒绝）                | planned |

> 集成测试使用 fixture 支撑的 DataLoader 替身 + 虚拟时钟（L2），不连真实行情 DB、不真实等待。崩溃恢复测试一律在**子进程**中执行 SIGKILL（§10.1 #10）。

### 8.3. E2E / 性能测试（Shield 编写）

见 §6.5。4 个 e2e 文件覆盖 scenario-0010~0050 happy path；1 个 perf 文件覆盖 NFR-0100 全部 5 条性能 AC。e2e 层同时覆盖 AC-NFR0600-03 的日志文件断言（模块真实运行后检查 `logs/`）。

---

## 9. AC 覆盖映射总表

> 下表确认 159 条 AC 全部有测试覆盖规划。CI 通过 `lk agent archer ci-scan` 扫描测试代码中的 `AC-FRXXXX-YY` 引用强制闭环，本表为规划依据（非反向生成的覆盖率矩阵）。

| FR/NFR    | AC 数 | 覆盖层                        | 状态    |
| --------- | ----- | ----------------------------- | ------- |
| FR-0100   | 4     | unit                          | planned |
| FR-0200   | 4     | unit                          | planned |
| FR-0300   | 5     | unit                          | planned |
| FR-0400   | 4     | unit                          | planned |
| FR-0500   | 3     | unit                          | planned |
| FR-0600   | 4     | unit + e2e(01/02)             | planned |
| FR-0700   | 4     | unit + e2e(01/02)             | planned |
| FR-0800   | 5     | integration + e2e(01)         | planned |
| FR-0900   | 3     | integration + e2e(01)         | planned |
| FR-1500   | 4     | unit                          | planned |
| FR-1600   | 4     | unit                          | planned |
| FR-1700   | 4     | unit                          | planned |
| FR-1800   | 3     | unit                          | planned |
| FR-1900   | 4     | unit                          | planned |
| FR-2000   | 4     | integration                   | planned |
| FR-2100   | 4     | integration + e2e(01/02)      | planned |
| FR-2200   | 4     | integration                   | planned |
| FR-2300   | 4     | unit                          | planned |
| FR-2400   | 4     | integration + e2e(01)         | planned |
| FR-2500   | 4     | unit(01/04) + integration(02/03) | planned |
| FR-2600   | 4     | unit + e2e(04)                | planned |
| FR-2700   | 4     | integration + e2e(01)         | planned |
| FR-3000   | 4     | unit                          | planned |
| FR-3100   | 3     | unit                          | planned |
| FR-3200   | 3     | unit                          | planned |
| FR-3300   | 2     | unit                          | planned |
| FR-3400   | 2     | unit                          | planned |
| FR-3500   | 3     | unit                          | planned |
| FR-3600   | 2     | unit                          | planned |
| FR-3700   | 4     | unit                          | planned |
| FR-3800   | 3     | unit + e2e(03)                | planned |
| FR-3900   | 3     | unit + e2e(01)                | planned |
| FR-4000   | 3     | unit(01/02) + integration(03) + e2e(01/02) | planned |
| FR-4100   | 4     | integration + e2e(01)         | planned |
| FR-4200   | 5     | unit + e2e(02)                | planned |
| NFR-0100  | 5     | perf（e2e marker）            | planned |
| NFR-0200  | 1     | CI gate（coverage ≥97%）      | planned |
| NFR-0300  | 1     | CI gate（mutmut ≥80%）        | planned |
| NFR-0400  | 3     | CI gate（ADR + docs sync）    | planned |
| NFR-0500  | 3     | unit(02) + CI gate(01/03)     | planned |
| NFR-0600  | 3     | unit(02) + integration(03) + CI gate(01) | planned |
| NFR-0700  | 5     | unit(02) + integration(04) + CI gate(01/03/05) | planned |
| NFR-0800  | 3     | unit(01/02) + integration(03) | planned |
| NFR-0900  | 3     | integration                   | planned |
| NFR-1000  | 4     | integration                   | planned |
| **合计**  | **159** | —                           | **159/159 全覆盖** |

**测试函数统计（规划）**：

- 单元测试函数：约 110 个（模块 A ~30、模块 B ~30、模块 C ~35、策略/NFR ~15）
- 集成测试函数：约 45 个（14 个文件，含崩溃恢复与 v0.1.0 兼容）
- E2E 测试函数：约 10 个（4 文件，happy path）
- 性能测试函数：5 个（NFR-0100 全项）
- CI 门禁项：10 个（覆盖率/mutation/ruff×2/bandit/grep×2/docs-sync/manifest/perf，非测试函数，由 CI 配置强制）

---

## 10. v0.2.0 特有反模式与风险继承

### 10.1. v0.2.0 特有测试反模式（review + CI 重点关注）

| #   | 反模式                   | 症状                                                          | 正确做法                                                     |
| --- | ------------------------ | ------------------------------------------------------------- | ------------------------------------------------------------ |
| 9   | 真实时钟等待             | `time.sleep(65)` 等 cron；断言 `datetime.now()` 派生值         | 虚拟时钟注入（T-1）+ `asyncio.wait_for` + `asyncio.Event`；cron 断言基于固定 base_time |
| 10  | 自杀式 kill -9           | pytest 进程内 `os.kill(os.getpid(), SIGKILL)`                  | 子进程运行调度器（`subprocess` / `multiprocessing`），父进程发 SIGKILL 后重启新子进程验证恢复 |
| 11  | 求解器数值脆性           | 精确断言权重向量；跨平台/跨求解器 flake                        | 容差断言（spec 给定 1e-6/1e-9）；断言约束满足与 solver_status，不断言中间迭代 |
| 12  | fixture 泄漏             | `scheduler_state/`、`models/`、`reports/` 落仓库根，测试间串扰 | 全部写盘路径经配置指向 `tmp_path`（T-4）；每个用例独立临时目录 |
| 13  | 异步泄漏                 | dangling task / 未关闭 aiohttp session / event loop 警告       | `pytest-asyncio` auto 模式 + 显式 `await scheduler.stop()`；API 测试用 aiohttp test client 上下文管理器 |
| 14  | 调度器内部过 mock        | 在 FR-2600 测试中 mock DriftDetector 自身                      | mock 只发生在 port 边界（TrainerPort/data_loader/时钟）；DriftDetector 是被测对象 |
| 15  | 性能断言污染             | 在负载不均的 CI runner 上硬断言单次 wall time 致 flake         | 预算按 spec 硬上限断言（fixture 规模受控）；趋势漂移用 `baselines.json` ±5% 记录，不作门禁 |
| 16  | 版本号时序假设           | 断言「下一个 build 号是 6」                                    | 断言唯一性 / 单调递增 / parent_version 链正确，不断言绝对编号 |
| 17  | mutation 感知弱化        | 为让 mutmut 存活而写弱断言                                     | 禁止；mutation <80% 时补强断言而非放宽（NFR-0300 门禁）         |

### 10.2. M-SPEC 风险/决策继承（影响测试设计）

| 来源                     | 内容                                                         | 对测试的影响                                                   |
| ------------------------ | ------------------------------------------------------------ | -------------------------------------------------------------- |
| M-SPEC waiver            | `lk agent lex verify-project` 误报（gh `item-list` limit=30），45/45 issue 实际已链接 Project #5 | 工具层误报，**对测试无影响**；仅记录可追溯性，CI 不依赖该命令的此检查项 |
| FR-1900 Round-2 锁定     | 性能衰减**仅评估在线 IC**，不评估 Sharpe                      | 测试必须断言 `not hasattr(decision, "sharpe")` 且 `"ic_only" in decision.notes`；**禁止**编写任何期待 Sharpe 监控字段的测试 |
| FR-3700 Round-2 锁定     | 默认 cvxpy + ECOS，ImportError 时自动回退 scipy SLSQP         | CI 环境**必装 cvxpy**（默认路径）；回退路径通过仿真 ImportError 单测覆盖（AC-FR3700-03）；两条路径都必须产出合法权重 |
| v0.1.0 冻结契约          | v0.1.0 模型目录格式（`YYYYMMDD_HHMMSS`）与 v0.2.0 新格式（`v{major}.{minor}.{build}`）并存 | NFR-1000 兼容测试使用**真实 v0.1.0 序列化 fixture 模型**（`tests/fixtures/v0.2.0/v010_model/`），禁止用 v0.2.0 代码现造「伪 v0.1.0 模型」 |
| 平台约束                 | Windows 不在 v0.2.0 范围（APScheduler 行为差异）               | CI 仅 Linux/macOS；不断言 Windows 特定行为                      |
| Lex 已解决项             | 模块 A/C 头部 FR 范围修正、FR-3200 表头 `Decessed` 笔误修正     | 机械修正，对测试无影响                                          |

### 10.3. 上游（Sage）阻塞项

**无。** 全部 45 个 FR/NFR、159 条 AC 均可观察、可断言、可分层覆盖；4 个可测试性需求（§6.7 T-1~T-4）属于 Stage 2 interfaces.md 设计职责，不需要 Sage 修订 spec/acceptance。

---

## 11. 评审清单

- [x] 测试策略覆盖主要风险（金融计算正确性、时间驱动调度、并发与崩溃恢复、求解器数值容差、外部数据依赖、性能预算、向后兼容）
- [x] 每个 AC 可追溯到测试代码（§9 总表 159/159 + §8 分模块表，CI 强制闭环）
- [x] test-plan 不维护具体测试清单 / 覆盖率矩阵（覆盖由 `check_acs.py` 反向生成；§8/§9 为规划映射）
- [x] 反模式 CI 门禁已启用（§1.3 + §7，含 v0.2.0 特有变体 §10.1）
- [x] 测试数据来源可复现（§2.4 fixture 合成，种子 42，MANIFEST.json 版本化）
- [x] tests/ 布局已文档化（§2.1）
- [x] §3 Ground Truth 方法已文档化（PSI/Max Sharpe/IC/协方差独立参考实现）
- [x] §6 外部依赖分层测试已文档化（虚拟时钟 / DataLoader 替身 / cvxpy 边界 / aiohttp 边界）
- [x] interfaces.md 与 test-plan 闭环（§6.6 断言依据 + §6.7 可测试性需求，Stage 2 产出后最终闭环）
- [x] interfaces.md 跨模块接口标注 `modules` 列并纳入集成覆盖（Stage 2 产出；§8.2 为预期清单）
- [x] e2e 范围限于 happy path（边界/错误/异常路由到集成测试 §8.2）
