# trader-off v0.2.0 — 因子挖掘·再训练调度·组合优化器 — Acceptance Criteria

- **Spec ID**: v0.2.0-001-factor-mining-retrain-optimizer
- **Created**: 2026-07-17
- **继承基线**: `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/acceptance.md` 中 FR-0100~1600 / NFR-0100~0700 的 AC 在本文件中**不重复**;仅通过 v0.1.0 acceptance 引用。

> 中央注册表:spec.md 只保留 FR/NFR 描述与元数据(testability/decided/valid);可观察、可断言的通过条件在本表中。
>
> 编号约定:
> - 每个 FR/NFR 单元内 AC-N 从 1 起,按顺序递增;单元之间不复用。
> - 完整 AC 引用:**AC-FRXXXX-YY**(4 位 FR + 2 位 AC 序号),与 test-plan / issue schema 保持一致。
>
> Lex 阶段 1/2 审查验证:(1) 本表存在;(2) spec.md 每个 FR/NFR 在本表中有对应章节;(3) 每条 AC 可被测试或断言。

---

## 模块 A — 因子挖掘

<a id="ac-fr-0100"></a>
## FR-0100 因子模板库定义

### AC-1
- 给定:调用 `list_templates()`(无参)。
- 当:执行枚举。
- 那么:返回 `list[FactorTemplate]`,长度 ≥ 12(4 类 × ≥3 模板),每个模板含字段:`name, category ∈ {momentum, volatility, volume, fundamental}, fields: list[str], params: dict, formula: str`。
- 断言:`all(isinstance(t, FactorTemplate) for t in result) and len(result) >= 12 and {t.category for t in result} == {"momentum", "volatility", "volume", "fundamental"}`。

### AC-2
- 给定:动量类模板 `momentum_N` 的元数据。
- 当:检查 `params` 字段。
- 那么:含 `N: int_range(5, 60, step=5)` 定义,生成 12 个合法 N 值。
- 断言:`momentum_template.params["N"]` 是 `IntRangeParam` 实例,`min=5, max=60, step=5`,`expanded() == [5,10,15,20,25,30,35,40,45,50,55,60]`。

### AC-3
- 给定:data_loader 不提供 fundamental 列(例如 OHLCV-only fixture)。
- 当:执行 `list_templates()` 并检查 fundamental 类模板行为。
- 那么:fundamental 类模板在枚举候选因子时被跳过(无报错),INFO 日志含 `fundamental templates skipped, no fundamental columns in data`。
- 断言:`enumerate_factors(...)` 返回结果中无 `category == "fundamental"` 的因子。

### AC-4
- 给定:因子挖掘完成。
- 当:检查落盘 `factor_registry/factors.yaml` 头部。
- 那么:含字段 `factor_template_version: "v1"`。
- 断言:`yaml.safe_load(open("factor_registry/factors.yaml"))["factor_template_version"] == "v1"`。

---

<a id="ac-fr-0200"></a>
## FR-0200 表达式引擎 — 参数化枚举

### AC-1
- 给定:1 个模板 `momentum_N`(params: N ∈ {5,10,20,60}) + 1 个模板 `vol_N`(params: N ∈ {10,20,60})。
- 当:调用 `enumerate_factors(templates, param_space)`。
- 那么:返回 `list[FactorSpec]`,长度 = 4 + 3 = 7,每个 `FactorSpec.id` 唯一,格式 `momentum_N_5`, `vol_N_10` 等。
- 断言:`len(result) == 7 and len(set(s.id for s in result)) == 7`。

### AC-2
- 给定:默认模板库 + 默认参数空间。
- 当:执行枚举。
- 那么:返回 ≥ 200 个候选因子。
- 断言:`len(result) >= 200`。

### AC-3
- 给定:非法参数组合(例如 N=0 或 N 为负数)。
- 当:调用 `enumerate_factors`。
- 那么:该组合被跳过,记录到 `invalid_combinations.json`,返回列表中不包含该因子。
- 断言:`all(s for s in result if s.params.get("N", 1) > 0) and Path("invalid_combinations.json").exists()`。

### AC-4
- 给定:`enumerate_factors(templates, param_space)` 输出。
- 当:检查每个 `FactorSpec`。
- 那么:含字段:`id (str)`, `template_name (str)`, `category (str)`, `formula (str)`, `compute_fn (callable)`, `params (dict)`,且 `compute_fn` 可调用(传入 OHLCV DataFrame 返回 factor Series)。
- 断言:`all(callable(s.compute_fn) for s in result) and all(s.formula for s in result)`。

---

<a id="ac-fr-0300"></a>
## FR-0300 因子评估 — IC / ICIR / Rank IC

### AC-1
- 给定:因子值 DataFrame(50 资产 × 100 日,列 asset, date, value)+ 标签 DataFrame(同 shape,列 asset, date, label)。
- 当:调用 `evaluate_factor(factor_values, labels, dates)`。
- 那么:返回 `FactorEvaluation` dataclass,含字段 `ic_ts (pl.DataFrame, 列 date/ic)`, `rank_ic_ts (列 date/rank_ic)`, `ic_mean`, `ic_std`, `icir`, `rank_ic_mean`, `rank_ic_std`, `layered_returns (pl.DataFrame, 列 layer/mean_return, 5 行)`。
- 断言:`isinstance(result, FactorEvaluation) and len(result.layered_returns) == 5 and {"ic", "rank_ic"} <= set(result.ic_ts.columns)`。

### AC-2
- 给定:factor 与 label 完全正相关(同序)。
- 当:调用 `evaluate_factor`。
- 那么:`ic_mean ≈ 1.0`, `rank_ic_mean ≈ 1.0`(误差 < 0.01)。
- 断言:`abs(result.ic_mean - 1.0) < 0.01 and abs(result.rank_ic_mean - 1.0) < 0.01`。

### AC-3
- 给定:factor 与 label 完全负相关(逆序)。
- 当:调用 `evaluate_factor`。
- 那么:`ic_mean ≈ -1.0`。
- 断言:`abs(result.ic_mean - (-1.0)) < 0.01`。

### AC-4
- 给定:某因子值列全部为常数(std=0)。
- 当:调用 `evaluate_factor`。
- 那么:`icir = 0.0`(避免除零)+ WARNING 日志 `factor has zero std, icir set to 0`。
- 断言:`result.icir == 0.0 and "zero std" in caplog.text`。

### AC-5
- 给定:模块 `trader_off.evaluation.ic`。
- 当:执行 `from trader_off.evaluation.ic import ic_pearson, ic_spearman, compute_layered_returns`。
- 那么:3 个函数均从 v0.1.0 复用,无重复实现(import 路径一致)。
- 断言:`inspect.getsourcefile(ic_pearson) == inspect.getsourcefile(<v0.1.0 中的同名函数>)` 或 `hasattr(trader_off.evaluation.ic, "ic_pearson")`。

---

<a id="ac-fr-0400"></a>
## FR-0400 因子选择 — Top-K + Pearson 去冗余

### AC-1
- 给定:30 个 `FactorEvaluation`(icir 各异),`top_k=30, corr_threshold=0.9`。
- 当:调用 `select_factors(...)`。
- 那么:返回 30 个因子,按 icir 降序排列(无冗余剔除)。
- 断言:`len(result) == 30 and all(result[i].icir >= result[i+1].icir for i in range(29))`。

### AC-2
- 给定:50 个因子,其中 5 对的 Pearson 相关系数 > 0.95(完全冗余),`top_k=30, corr_threshold=0.9`。
- 当:调用 `select_factors`。
- 那么:从 50 个因子取前 30 → 冗余处理后保留 25 个(5 对冗余各去 1 个,假设 ICIR 唯一)。
- 断言:`len(result) == 25 and diagnostics.removed_by_redundancy` 长度 == 5。

### AC-3
- 给定:候选总数仅 8 个(小于 top_k=30)。
- 当:调用 `select_factors`。
- 那么:全部保留(8 个),WARNING 日志 `selected fewer than top_k because candidate count < top_k`。
- 断言:`len(result) == 8 and "fewer than top_k" in caplog.text`。

### AC-4
- 给定:某对冗余因子 A、B 的 ICIR 完全相等(差值 < 1e-9)。
- 当:调用 `select_factors`。
- 那么:保留字典序较小的 ID,移除另一个。
- 断言:`(a.id if a.id < b.id else b.id) in result and (a.id if a.id >= b.id else b.id) not in result`。

---

<a id="ac-fr-0500"></a>
## FR-0500 相关性热力图输出

### AC-1
- 给定:精选因子集合(20 个),Pearson 相关矩阵 20×20。
- 当:调用 `render_correlation_heatmap(corr, labels, output_path)`。
- 那么:生成 PNG 文件,尺寸 ≈ 1440×1200(`figsize=(12, 10)` × `dpi=120`),文件大小 > 5KB。
- 断言:`Path(output_path).exists() and Path(output_path).stat().st_size > 5000`。

### AC-2
- 给定:同 AC-1。
- 当:读取 PNG metadata。
- 那么:图像为静态 PNG,使用 `matplotlib` 默认 Agg backend。
- 断言:`matplotlib.image.imread(output_path).shape[:2] == (1200, 1440)`(H × W)。

### AC-3
- 给定:精选因子 ≥ 30 个,密集标签。
- 当:调用 `render_correlation_heatmap`。
- 那么:标签字号自动缩小(`fontsize=6`)以避免重叠。
- 断言:`(fig.axes[0].get_xticklabels()[0].get_fontsize() == 6)` 或日志记录 `densely labeled, font shrunk`。

---

<a id="ac-fr-0600"></a>
## FR-0600 因子注册表持久化

### AC-1
- 给定:因子挖掘完成,≥ 200 候选 + 30 精选。
- 当:检查 `factor_registry/factors.yaml`。
- 那么:文件存在,YAML 含字段 `factor_template_version, generated_at, total_candidates, factors`;`factors` 列表长度 == `total_candidates`。
- 断言:`yaml.safe_load(open("factors.yaml"))["total_candidates"] == len(yaml.safe_load(open("factors.yaml"))["factors"]) >= 200`。

### AC-2
- 给定:同上场景。
- 当:检查 `factor_registry/selected_factors.json`。
- 那么:JSON 含字段 `selected_count, selection_diagnostics, factors`;`factors` 列表长度 == `selected_count`;每个因子含 `id, category, icir, ic_mean, ic_std`。
- 断言:`all("icir" in f for f in json.load(open("selected_factors.json"))["factors"])`。

### AC-3
- 给定:`factor_registry/` 目录不存在。
- 当:执行因子挖掘流水线。
- 那么:目录自动创建(`mkdir -p`),因子文件落盘成功。

### AC-4
- 给定:人工构造一个 `factors.yaml`,删除 `factor_template_version` 字段。
- 当:调用 `load_factor_registry(path)`。
- 那么:抛 `FactorRegistrySchemaError`,message 含 `missing required field: factor_template_version`。
- 断言:`pytest.raises(FactorRegistrySchemaError, match="factor_template_version")`。

---

<a id="ac-fr-0700"></a>
## FR-0700 因子评估报告 — HTML + Markdown

### AC-1
- 给定:30 个精选因子 + 完整 evaluations。
- 当:调用 `render_evaluation_report(evaluations, selected, output_dir)`。
- 那么:返回 dict 含 `html, md, figures_dir` 三个 Path;HTML 与 MD 文件均存在,大小 > 5KB。
- 断言:`all(result[k].exists() and result[k].stat().st_size > 5000 for k in ["html", "md"])`。

### AC-2
- 给定:同 AC-1,读取 HTML 文件。
- 当:解析 HTML 内容。
- 那么:含 `<title>`、`<h1>` 主标题、`<table>` 表格(精选因子 ICIR 排名)、`<img src="figures/...">`(相关性热力图)、Top-1 累计收益图嵌入。
- 断言:`all(s in html_content for s in ["<table>", "<img src=\"figures/correlation_heatmap.png\"", "<img src=\"figures/top_layer_cumret.png\"", "ICIR"])`。

### AC-3
- 给定:同 AC-1。
- 当:解析 Markdown 文件。
- 那么:含 `#` 主标题、ICIR 排名 Markdown 表格(用 `|` 分隔)、精选因子 ID 列表、生成时间戳。
- 断言:`"| icir |" in md_content and "#" in md_content`。

### AC-4
- 给定:HTML 模板使用 `string.Template` 而非 Jinja2(默认无外部依赖)。
- 当:报告生成。
- 那么:无 `jinja2` import 错误,模板正常渲染。
- 断言:`"jinja2" not in sys.modules` 或 `importlib.util.find_spec("jinja2") is None` 时模板仍可生成。

---

<a id="ac-fr-0800"></a>
## FR-0800 因子挖掘 CLI

### AC-1
- 给定:CLI 命令 `trader-off mine-factors --config configs/factor_mining.yaml --start 2020-01-01 --end 2024-12-31 --top-k 30`。
- 当:执行。
- 那么:进程退出码为 0,stdout 含 "枚举了 N 个候选因子"(N ≥ 200)与 "精选 K 个因子"(K ≤ 30)。
- 断言:`result.returncode == 0 and re.search(r"枚举了 (\d+) 个候选因子", result.stdout).group(1) >= 200`。

### AC-2
- 给定:--top-k 默认值未指定。
- 当:CLI 解析。
- 那么:`top_k = 30`。
- 断言:`config.top_k == 30`(pydantic 模型默认值)。

### AC-3
- 给定:配置文件不存在。
- 当:执行 CLI。
- 那么:退出码 4,stderr 含 "ConfigValidationError" 或 "config file not found"。

### AC-4
- 给定:--top-k=30 但候选总数仅 5(数据极少)。
- 当:执行。
- 那么:退出码 3,stdout 含 "精选 K 个因子"(K=5)< 10;WARNING 日志 `fewer than 10 selected factors`。

### AC-5
- 给定:CLI 缺少 `--config` 参数。
- 当:执行。
- 那么:pydantic 校验失败,退出码非 0,stderr 含 "config is required"。

---

<a id="ac-fr-0900"></a>
## FR-0900 精选因子作为 v0.1.0 模型输入

### AC-1
- 给定:`factor_registry/selected_factors.json`(含 30 个精选因子)。
- 当:执行 `trader-off train --factor-registry factor_registry/selected_factors.json`。
- 那么:训练完成,模型目录 `metadata.json` 含字段 `factor_registry_path, factor_template_version, selected_factor_count, feature_names`。
- 断言:`all(k in metadata for k in ["factor_registry_path", "factor_template_version", "selected_factor_count", "feature_names"])` 且 `len(metadata["feature_names"]) == 30`。

### AC-2
- 给定:同上场景。
- 当:读取 `models/<version>/feature_names.json`。
- 那么:内容为精选因子的 ID 列表(如 `["momentum_N_20", "vol_N_20", ...]`),而非 v0.1.0 默认的 15 个固定特征。
- 断言:`json.load(open("feature_names.json")) == [f["id"] for f in selected["factors"]]`。

### AC-3
- 给定:不传 `--factor-registry` 参数。
- 当:执行 `trader-off train`。
- 那么:`metadata.json` 不含 `factor_registry_path` 字段,`feature_names` 为 v0.1.0 默认 15 个特征名(`ret_5, ..., vp_corr_20`)。
- 断言:`"factor_registry_path" not in metadata and len(metadata["feature_names"]) == 15`。

---

## 模块 B — 再训练调度

<a id="ac-fr-1500"></a>
## FR-1500 调度器核心接口与生命周期

### AC-1
- 给定:`RetrainScheduler` 实例化(config, registry, drift, perf, trainer 均为 mock)。
- 当:检查类签名。
- 那么:`start(), stop(), trigger_now(reason, mode), get_status()` 4 个方法均为 async。
- 断言:`all(asyncio.iscoroutinefunction(getattr(RetrainScheduler, m)) for m in ["start", "stop", "trigger_now", "get_status"])`。

### AC-2
- 给定:调度器运行中,触发 2 个重训任务(全量 + 增量),间隔 0s。
- 当:检查 `max_concurrent_tasks=1` 行为。
- 那么:第 2 个任务进入 pending 队列,等待第 1 个完成后才开始(通过 mock trainer 的调用顺序验证)。
- 断言:`len(active_tasks) <= 1 throughout, and both tasks eventually complete`。

### AC-3
- 给定:调度器运行中,调用 `stop()`。
- 当:等待当前 tick 完成。
- 那么:调度器在下一个 tick 退出主循环,`get_status().running == False`。
- 断言:从 `start()` 调用到返回的时间 < 5 秒(mock 调度下)。

### AC-4
- 给定:`RetrainScheduler` 类。
- 当:`import` 时检查依赖。
- 那么:不依赖 `millionaire` 任何符号(模块路径不出现 `quantide`)。
- 断言:`grep -r "quantide\|millionaire" src/trader_off/scheduler/` 无业务依赖(仅 `pyproject.toml` 声明)。

---

<a id="ac-fr-1600"></a>
## FR-1600 Cron 触发器

### AC-1
- 给定:配置 `full_retrain = "0 16 * * 1-5"`,当前时间为交易日 15:59:30。
- 当:调度器 tick 一次。
- 那么:不触发(下一触发时间为 16:00)。
- 断言:`next_trigger_time = datetime(2026, 7, 17, 16, 0, 0)`。

### AC-2
- 给定:配置 `incremental_retrain = "0 16 * * 1-5"`,当前时间为非交易日(周末)。
- 当:调度器 tick 一次。
- 那么:不触发(非交易日),INFO 日志 `cron skipped, not a trading day`。
- 断言:`not triggered and "not a trading day" in caplog.text`。

### AC-3
- 给定:配置 `full_retrain_frequency_days = 5`,上次全量重训为 3 个交易日前。
- 当:cron 触发时刻到达。
- 那么:不触发全量(因为 3 < 5),只触发增量(若配置增量 cron)。
- 断言:`trigger_count["full"] == 0 and trigger_count["incremental"] == 1`。

### AC-4
- 给定:`croniter` 或 `APScheduler` 任意一个可用。
- 当:`import trader_off.scheduler.cron`。
- 那么:无 ImportError,函数 `next_cron_fire(expr, base_time)` 返回正确的下一次触发时间。
- 断言:`next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0)) == datetime(2026, 7, 17, 16, 0)`。

---

<a id="ac-fr-1700"></a>
## FR-1700 PSI 漂移检测

### AC-1
- 给定:`baseline = [1,2,3,4,5,6,7,8,9,10]`, `current = [1,2,3,4,5,6,7,8,9,10]`(同分布)。
- 当:调用 `compute_psi(baseline, current)`。
- 那么:`PSI ≈ 0.0`(误差 < 1e-6,因分箱占比相同)。
- 断言:`abs(result) < 1e-6`。

### AC-2
- 给定:`baseline = [1,2,...,100]`, `current = [50,51,...,150]`(分布完全右移)。
- 当:调用 `compute_psi`。
- 那么:`PSI > 0.5`(显著漂移)。
- 断言:`result > 0.5`。

### AC-3
- 给定:100 个 baseline + 100 个 current 样本,20 个特征列。
- 当:调用 `compute_feature_psi`。
- 那么:返回 DataFrame,长度 == 20,列 `feature, psi, is_drift`;`is_drift = (psi > 0.2)`。
- 断言:`len(result) == 20 and set(result.columns) == {"feature", "psi", "is_drift"}`。

### AC-4
- 给定:某特征 current 列全为 NaN(无样本)。
- 当:调用 `compute_feature_psi`。
- 那么:该特征 `psi = 0.0`,`is_drift = False`,WARNING 日志 `feature X has no samples in current window`。
- 断言:`result.filter(pl.col("feature") == "X")["psi"].item() == 0.0`。

---

<a id="ac-fr-1800"></a>
## FR-1800 KS 漂移检测

### AC-1
- 给定:`baseline = np.random.normal(0, 1, 1000)`, `current = np.random.normal(0, 1, 1000)`(同分布,固定 seed=42)。
- 当:调用 `compute_ks_pvalue`。
- 那么:p 值 > 0.05(不拒绝同分布假设)。
- 断言:`result > 0.05`。

### AC-2
- 给定:`baseline = np.random.normal(0, 1, 1000)`, `current = np.random.normal(2, 1, 1000)`(均值偏移 2σ)。
- 当:调用 `compute_ks_pvalue`。
- 那么:p 值 < 0.001(强烈拒绝同分布)。
- 断言:`result < 0.001`。

### AC-3
- 给定:某特征 baseline 全为 NaN。
- 当:调用 `compute_feature_ks`。
- 那么:该特征 `ks_statistic = 0.0`, `p_value = 1.0`, `is_drift = False`,WARNING 日志。
- 断言:`result.filter(pl.col("feature") == "X").select(["ks_statistic", "p_value", "is_drift"]).row(0) == (0.0, 1.0, False)`。

---

<a id="ac-fr-1900"></a>
## FR-1900 性能衰减检测

### AC-1
- 给定:最近 20 日 IC 时序(均值 0.025,std 0.005),`ic_floor=0.005, ic_drop_ratio=0.3`。
- 当:调用 `trigger_perf_degradation()`。
- 那么:返回 `TriggerDecision(should_retrain=False, reason="ok", suggested_mode="full")`(未跌破阈值)。
- 断言:`decision.should_retrain == False`。

### AC-2
- 给定:最近 20 日 IC 时序均值降至 -0.01(跌破 ic_floor=0.005)。
- 当:调用 `trigger_perf_degradation()`。
- 那么:`should_retrain=True, reason="ic_below_floor", suggested_mode="full"`。
- 断言:`decision.should_retrain and "ic_below_floor" in decision.reason`。

### AC-3
- 给定:当前 20 日 IC 均值 0.025,30 日前为 0.05,`ic_drop_ratio=0.3`(跌幅 50% > 30% 阈值)。
- 当:调用 `trigger_perf_degradation()`。
- 那么:`should_retrain=True, reason="ic_drop_ratio_exceeded"`。
- 断言:`"ic_drop_ratio_exceeded" in decision.reason`。

### AC-4
- 给定:Sharpe 评估开关关闭(默认)。
- 当:调用 `trigger_perf_degradation()`。
- 那么:函数不执行任何子回测,纯基于 IC 计算,耗时 < 1 秒。
- 断言:`decision.computation_time_sec < 1.0 and "sharpe_eval_disabled" in decision.notes`。

---

<a id="ac-fr-2000"></a>
## FR-2000 手动触发 CLI / API

### AC-1
- 给定:CLI 命令 `trader-off retrain trigger --mode full --reason "manual_test"`。
- 当:执行。
- 那么:进程退出码 0,stdout 含 `task_id=<uuid>`,`status=pending`。
- 断言:`re.search(r"task_id=(\S+)", result.stdout) and "status=pending" in result.stdout`。

### AC-2
- 给定:CLI 命令 `trader-off retrain status`。
- 当:调度器运行中或停止后执行。
- 那么:输出最近 10 条任务,每条至少含 `task_id, mode, reason, start_time, end_time, status, new_version`。
- 断言:`len(parse_task_table(result.stdout)) <= 10 and all("task_id" in row for row in ...)`。

### AC-3
- 给定:调度器 API 运行(`run_api=True`,端口 8765)。
- 当:`POST http://localhost:8765/retrain/trigger` with `{"mode": "full", "reason": "api_test"}`。
- 那么:HTTP 200,响应 `{"task_id": "...", "status": "pending"}`。
- 断言:`response.status_code == 200 and "task_id" in response.json()`。

### AC-4
- 给定:API 端口未启动或不在 localhost。
- 当:`POST` 任意 `/retrain/*` 端点。
- 那么:连接拒绝或超时,不暴露任何敏感信息(无内部堆栈)。
- 断言:`response.status_code in (0, connection refused) or "Traceback" not in response.text`。

---

<a id="ac-fr-2100"></a>
## FR-2100 全量重训

### AC-1
- 给定:触发一次全量重训(task 已运行)。
- 当:重训完成。
- 那么:产出 `models/v0.X.Y.<build>/` 目录,含 `model.pkl, scaler.json, dropped_features.json, feature_names.json, metadata.json`。
- 断言:`all((models_dir / f"v{ver}" / fname).exists() for fname in ["model.pkl", "scaler.json", "dropped_features.json", "feature_names.json", "metadata.json"])`。

### AC-2
- 给定:同 AC-1,读取 `models/registry.json`。
- 那么:新追加一条记录,`mode == "full"`,`trigger == "cron_full" | "drift" | "perf_degradation" | "manual"` 之一,含字段 `version, created_at, trigger, mode, task_id, git_commit_sha, metrics`。
- 断言:`registry[-1]["mode"] == "full" and "git_commit_sha" in registry[-1]`。

### AC-3
- 给定:同一 build 号两次全量重训。
- 当:第二次调用 `save_model`。
- 那么:抛 `ModelVersionExistsError`,不覆盖已有模型(继承 v0.1.0 AC-FR0800-03)。

### AC-4
- 给定:全量重训配置 `train_window_years=3`。
- 当:检查训练数据的实际范围。
- 那么:`metadata.json["train_start"] = today - 3 years`,`train_end = today`。
- 断言:`abs((date.fromisoformat(metadata["train_end"]) - date.fromisoformat(metadata["train_start"])).days - 365*3) < 5`。

---

<a id="ac-fr-2200"></a>
## FR-2200 增量重训 (lightGBM refit)

### AC-1
- 给定:已存在全量模型 `v0.2.0.5`,触发增量重训。
- 当:`save_model(...)` 完成。
- 那么:产出 `models/v0.2.0.5.incr1/`,`metadata.json` 含字段 `parent_version="v0.2.0.5", incr_seq=1, refit_iterations > 0`。
- 断言:`metadata["parent_version"] == "v0.2.0.5" and metadata["incr_seq"] == 1`。

### AC-2
- 给定:同 AC-1,验证 lightGBM 使用 `Booster.refit()` 而非 `LGBMRegressor.fit()`。
- 当:mock `lightgbm.Booster.refit`。
- 那么:`Booster.refit.call_count == 1 and LGBMRegressor.fit.call_count == 0`(或 fit 未被调用)。
- 断言:`mock_booster.refit.called and not mock_regressor.fit.called`。

### AC-3
- 给定:增量重训使用 5 个交易日数据(默认)。
- 当:检查实际训练数据范围。
- 那么:`metadata.json["train_start"]` 与 `train_end` 相差 5 个交易日(允许 7 个日历日容差)。
- 断言:`(end - start).days <= 7 and (end - start).days >= 5`。

### AC-4
- 给定:连续 3 次增量重训(incr1, incr2, incr3)。
- 当:检查版本号序列。
- 那么:每次版本号后缀递增,`parent_version` 链正确(incr2.parent = v0.2.0.5, incr3.parent = v0.2.0.5.incr2)。
- 断言:`[r["parent_version"] for r in registry[-3:]] == ["v0.2.0.5", "v0.2.0.5.incr1", "v0.2.0.5.incr2"]`。

---

<a id="ac-fr-2300"></a>
## FR-2300 模型版本管理与保留策略

### AC-1
- 给定:`models/registry.json` 已含 12 个版本,`keep_latest_n=10`。
- 当:调度器启动(或新版本落盘后)。
- 那么:`models/` 下仅剩 10 个版本目录,最旧的 2 个被删除。
- 断言:`len(list(models_dir.iterdir())) == 10 and sorted([d.name for d in models_dir.iterdir()]) == sorted(registry[-10:])`。

### AC-2
- 给定:`keep_pinned_versions = ["v0.2.0.5"]`,registry 已含 12 个版本,该版本不在最新 10 个中。
- 当:GC 执行。
- 那么:`v0.2.0.5` 不被删除,即使超出 `keep_latest_n`。
- 断言:`(models_dir / "v0.2.0.5").exists()`。

### AC-3
- 给定:`keep_full_retrain_only=True`,registry 含 5 个全量 + 8 个增量版本。
- 当:GC 执行(`keep_latest_n=10`,从全量计数)。
- 那么:仅保留最新 10 个**全量**版本,所有增量版本被删除(增量从属于全量)。
- 断言:`all(r["mode"] == "full" for r in registry_kept) and len(kept) == min(10, 5)`。

### AC-4
- 给定:调用 `rollback_to("v0.2.0.3")`。
- 当:执行完成。
- 那么:`models/registry.json["current_version"] == "v0.2.0.3"`,下次 `predict` 默认使用该版本(若 `model_load_mode=lazy`)。
- 断言:`registry["current_version"] == "v0.2.0.3"`。

---

<a id="ac-fr-2400"></a>
## FR-2400 自动部署到预测服务

### AC-1
- 给定:新模型 `v0.2.0.6` 通过验证(`test_ic_mean >= ic_floor=0.005`)。
- 当:调度器完成部署。
- 那么:`registry.json["current_version"] == "v0.2.0.6"`,`logs/deploy.log` 含 `from=v0.2.0.5 to=v0.2.0.6 status=success`。
- 断言:`registry["current_version"] == "v0.2.0.6" and "status=success" in deploy_log_text`。

### AC-2
- 给定:新模型 `v0.2.0.7` 验证失败(`test_ic_mean < ic_floor`)。
- 当:调度器尝试部署。
- 那么:不更新 `current_version`,WARNING 日志 `validation failed, not deploying v0.2.0.7`,模型仍保留在 registry 但不激活。
- 断言:`registry["current_version"] != "v0.2.0.7" and "validation failed" in deploy_log`。

### AC-3
- 给定:`model_load_mode = "hot-reload"`,预测服务运行中,registry 更新。
- 当:watchdog 检测到文件变化(≤ 60s)。
- 那么:预测服务自动重新加载模型,新请求使用 `v0.2.0.6`(无需重启)。
- 断言:在 registry 更新后 ≤ 60s 内,新的 predict 调用使用新版本(通过日志断言)。

### AC-4
- 给定:新模型 `v0.2.0.8` 目录存在但 `model.pkl` 损坏(空文件)。
- 当:预测服务尝试加载。
- 那么:加载失败,ERROR 日志,旧版本保持运行,服务不中断。
- 断言:`current_version` 未变,`ERROR` 级别日志含 `failed to load v0.2.0.8`。

---

<a id="ac-fr-2500"></a>
## FR-2500 调度状态持久化

### AC-1
- 给定:调度器运行中,触发 5 个任务(状态变更 p → r → s/f)。
- 当:检查 `scheduler_state/last_tasks.json`。
- 那么:含 5 条记录,字段 `task_id, mode, reason, status, start_time, end_time, error`。
- 断言:`len(records) == 5 and all(r["task_id"] for r in records)`。

### AC-2
- 给定:调度器正在写 `last_tasks.json` 时被 kill -9。
- 当:重启调度器,读取该文件。
- 那么:文件可正常解析(JSON 完整,无半写入状态),至少最近一次完整的状态变更已落盘。
- 断言:`json.load(open("last_tasks.json"))` 不抛 `JSONDecodeError`。

### AC-3
- 给定:调度器重启(模拟崩溃恢复)。
- 当:启动完成。
- 那么:之前 `running` 状态的任务标记为 `failed`,reason=`"scheduler restart"`,pending 任务保留为 pending。
- 断言:`all(r["status"] in {"pending", "failed"} for r in recovered_tasks)`。

### AC-4
- 给定:并发触发 10 个任务(模拟 10 个协程同时调用 `trigger_now`)。
- 当:检查 `last_tasks.json`。
- 那么:每个 `task_id` 唯一,无重复或丢失;`task_id` 含时间戳 + UUID 后缀。
- 断言:`len(set(r["task_id"] for r in records)) == 10`。

---

<a id="ac-fr-2600"></a>
## FR-2600 漂移判定与重训决策

### AC-1
- 给定:20 个特征中 4 个 PSI > 0.1,2 个 KS p < 0.05(轻度漂移,未达中度阈值)。
- 当:调用 `DriftDetector.evaluate()`。
- 那么:返回 `DriftDecision(should_retrain=False, reason="light_drift", ...)`。
- 断言:`decision.should_retrain == False and "light" in decision.reason`。

### AC-2
- 给定:20 个特征中 1 个 PSI > 0.2,6 个 KS p < 0.05(中度漂移)。
- 当:调用 `DriftDetector.evaluate()`。
- 那么:`should_retrain=True, suggested_mode="incremental", reason="moderate_drift"`。
- 断言:`decision.should_retrain and decision.suggested_mode == "incremental"`。

### AC-3
- 给定:20 个特征中 4 个 PSI > 0.5(重度漂移)。
- 当:调用 `DriftDetector.evaluate()`。
- 那么:`should_retrain=True, suggested_mode="full", reason="strong_drift"`。
- 断言:`decision.suggested_mode == "full" and "strong" in decision.reason`。

### AC-4
- 给定:任意 drift 决策产生。
- 当:检查 `reports/drift_<date>/`。
- 那么:存在 `drift_report.json`(完整 per-feature 统计)与 `drift_summary.csv`(决策汇总)。
- 断言:`(report_dir / "drift_report.json").exists() and (report_dir / "drift_summary.csv").exists()`。

---

<a id="ac-fr-2700"></a>
## FR-2700 调度器 CLI 与配置

### AC-1
- 给定:CLI 命令 `trader-off scheduler start --config configs/scheduler.yaml`。
- 当:执行。
- 那么:进程退出码 0(在测试 mock 调度下),stdout 含 "Scheduler started"。
- 断言:`result.returncode == 0 and "Scheduler started" in result.stdout`。

### AC-2
- 给定:`trader-off scheduler status`(调度器未运行)。
- 当:执行。
- 那么:退出码 0,stdout 显示 `running=False, last_10_tasks=[...]`,不报错。
- 断言:`"running=False" in result.stdout and result.returncode == 0`。

### AC-3
- 给定:配置文件 `scheduler.yaml` 缺失 `cron` 字段。
- 当:加载配置。
- 那么:抛 `ConfigValidationError`,message 含 `cron is required`。
- 断言:`pytest.raises(ConfigValidationError, match="cron is required")`。

### AC-4
- 给定:配置文件含非法 cron 表达式 `"invalid cron"`.
- 当:croniter / APScheduler 解析。
- 那么:抛 `ConfigValidationError`,message 含 cron 解析失败详情。

---

## 模块 C — 组合优化器

<a id="ac-fr-3000"></a>
## FR-3000 协方差估计 — Ledoit-Wolf Shrinkage

### AC-1
- 给定:100 资产 × 252 日收益率 DataFrame(模拟资产相关性结构)。
- 当:调用 `estimate_covariance(returns_df, method="sample")`。
- 那么:返回 `(100, 100)` np.ndarray,对称,正定(最小特征值 > 0)。
- 断言:`result.shape == (100, 100) and np.allclose(result, result.T) and np.linalg.eigvalsh(result).min() > 0`。

### AC-2
- 给定:同 AC-1,`method="ledoit_wolf"`。
- 当:调用。
- 那么:返回的协方差矩阵与 sample 的差异在 Ledoit-Wolf shrinkage 范围内(`||Σ_lw - Σ_sample||_F / ||Σ_sample||_F < 0.5`)。
- 断言:`np.linalg.norm(result - sample_cov, "fro") / np.linalg.norm(sample_cov, "fro") < 0.5`。

### AC-3
- 给定:returns_df 中某资产列全 NaN。
- 当:调用 `estimate_covariance`。
- 那么:该资产被剔除,`assets_dropped.json` 含该资产名,返回的协方差形状 `(N-1, N-1)`。
- 断言:`asset_name in json.load(open("assets_dropped.json")) and result.shape == (99, 99)`。

### AC-4
- 给定:returns_df 仅 20 日(小于最小 30 日阈值)。
- 当:调用。
- 那么:抛 `InsufficientDataError`,message 含 "need at least 30 days"(继承 v0.1.0 AC-FR1200-03)。

---

<a id="ac-fr-3100"></a>
## FR-3100 预期收益输入

### AC-1
- 给定:`predictions.csv` 含 50 行,列 `asset, score, rank`。
- 当:调用 `build_expected_returns(predictions, mode="raw")`。
- 那么:返回 dict,长度 == 50,key 为 asset,value 为 score(原始分数)。
- 断言:`len(result) == 50 and result[asset_0] == predictions.filter(pl.col("asset") == asset_0)["score"].item()`。

### AC-2
- 给定:同 AC-1,`mode="zscore"`。
- 当:调用。
- 那么:返回 z-score 标准化后的分数(mean=0, std=1)。
- 断言:`abs(np.mean(list(result.values()))) < 1e-9 and abs(np.std(list(result.values())) - 1.0) < 1e-6`。

### AC-3
- 给定:`mu` 字典含 50 个资产,`cov` 矩阵仅含 48 个资产(2 个被剔除)。
- 当:优化前调用资产匹配校验。
- 那么:抛 `AssetMismatchError`,message 含缺失资产列表。
- 断言:`pytest.raises(AssetMismatchError, match="missing assets:")`。

---

<a id="ac-fr-3200"></a>
## FR-3200 行业映射接口

### AC-1
- 给定:`configs/industry_map.csv` 含 50 行(列 `asset,industry`)。
- 当:调用 `load_industry_map(path)`。
- 那么:返回 dict,长度 == 50,值 ∈ {banking, real_estate, technology, ...}(一级行业枚举)。
- 断言:`len(result) == 50 and all(isinstance(v, str) for v in result.values())`。

### AC-2
- 给定:行业映射 CSV 缺失某资产(`predictions` 中存在)。
- 当:执行优化流水线。
- 那么:记录到 `assets_without_industry.json`,资产视为独立"未分类"虚拟行业,权重严格 ≤ 0(实际被剔除)。
- 断言:`asset in json.load(open("assets_without_industry.json"))`。

### AC-3
- 给定:行业映射 CSV 含重复行(同一 asset 两次不同 industry)。
- 当:加载。
- 那么:抛 `IndustryMapConflictError`,message 含冲突 asset 与行业列表。
- 断言:`pytest.raises(IndustryMapConflictError, match="duplicate asset")`。

---

<a id="ac-fr-3300"></a>
## FR-3300 满仓约束 (Σw = 1)

### AC-1
- 给定:任意满足 long-only 与 max_weight 约束的优化问题。
- 当:求解完成。
- 那么:返回权重 `|sum(w) - 1.0| <= 1e-6`(满仓)。
- 断言:`abs(weights.sum() - 1.0) < 1e-6`。

### AC-2
- 给定:求解器报告"不可行"(infeasible),如要求 Σw=1 + 所有权重 ≤ 0.001 但 50 个资产。
- 当:返回结果。
- 那么:`weights = None` + `optimizer_report.json["solver_status"] = "infeasible"`,不抛异常。

---

<a id="ac-fr-3400"></a>
## FR-3400 long-only 约束

### AC-1
- 给定:任意优化问题。
- 当:求解完成。
- 那么:所有权重 `w_i >= 0`,数值误差容差 `1e-9`。
- 断言:`all(w >= -1e-9 for w in weights)`。

### AC-2
- 给定:某资产 `mu` 为强负(预期亏损)。
- 当:求解。
- 那么:该资产权重 ≈ 0(被剔除),不出现负权重。
- 断言:`weight[neg_asset] < 1e-6`。

---

<a id="ac-fr-3500"></a>
## FR-3500 行业中性约束

### AC-1
- 给定:5 个行业,基准等权 `B = [0.2, 0.2, 0.2, 0.2, 0.2]`,δ=0.05。
- 当:求解完成。
- 那么:对每个行业 j,`|W_j - B_j| <= 0.05 + 1e-6`。
- 断言:`all(abs(W[j] - 0.2) <= 0.05 + 1e-6 for j in range(5))`。

### AC-2
- 给定:--industry-neutral-tol=0.10(用户放宽)。
- 当:求解。
- 那么:行业偏离上限放宽到 10%(同上 AC 但容差 = 0.10)。
- 断言:`max(abs(W - B)) <= 0.10 + 1e-6`。

### AC-3
- 给定:行业约束导致 infeasible(基准 + δ 区间无交集)。
- 当:求解。
- 那么:返回 infeasible,`optimizer_report.json["solver_status"] = "infeasible"`,不强行求解。

---

<a id="ac-fr-3600"></a>
## FR-3600 个股上限 10% 约束

### AC-1
- 给定:任意优化问题。
- 当:求解完成。
- 那么:所有权重 `w_i <= 0.10 + 1e-9`。
- 断言:`all(w <= 0.10 + 1e-9 for w in weights)`。

### AC-2
- 给定:--max-weight=0.05(用户严格化)。
- 当:求解。
- 那么:所有权重 ≤ 0.05。
- 断言:`all(w <= 0.05 + 1e-9 for w in weights)`。

---

<a id="ac-fr-3700"></a>
## FR-3700 优化求解 — Max Sharpe

### AC-1
- 给定:50 资产,mu 来自 v0.1.0 predict 输出,Σ 来自 Ledoit-Wolf。
- 当:调用优化器。
- 那么:求解状态为 `optimal` 或 `optimal_inaccurate`(cvxpy 状态枚举),`solve_time_sec < 5.0`(默认 fixture 规模)。
- 断言:`decision.solver_status in {"optimal", "optimal_inaccurate"} and decision.solve_time_sec < 5.0`。

### AC-2
- 给定:Sharpe Ratio 解析解 vs 优化解。
- 当:输入接近正定 + mu 与 Σ 已知的小型 fixture(10 资产)。
- 那么:优化 Sharpe 与解析解偏差 < 5%(允许数值误差)。
- 断言:`abs(optimized_sharpe - analytic_sharpe) / analytic_sharpe < 0.05`。

### AC-3
- 给定:cvxpy 不可用(模拟 `ImportError`)。
- 当:优化器调用。
- 那么:自动回退到 `scipy.optimize.SLSQP`,INFO 日志 `cvxpy unavailable, fallback to scipy.optimize.SLSQP`,求解成功。
- 断言:`"cvxpy unavailable" in caplog.text and result.weights is not None`。

### AC-4
- 给定:求解器 max_iterations=1000,tolerance=1e-6。
- 当:检查 CVXPY 配置。
- 那么:求解参数被正确传递(可通过 mock CVXPY 验证 `solver_kwargs["max_iters"] == 1000`)。

---

<a id="ac-fr-3800"></a>
## FR-3800 约束违反检测与报告

### AC-1
- 给定:求解结果 `weights` 满足所有约束。
- 当:调用 `check_constraints(weights, mu, cov, constraints)`。
- 那么:返回 `ConstraintReport`,`violations == []`,所有检查项通过。
- 断言:`all(check.passed for check in report.checks) and report.violations == []`。

### AC-2
- 给定:人工构造违反约束的 `weights`(`sum=0.95` 不满仓,`max=0.12` 超过上限)。
- 当:调用 `check_constraints`。
- 那么:`violations` 列表含 2 项:`{type: "sum_constraint", ...}` 与 `{type: "max_weight", asset: X, actual: 0.12, expected: 0.10, severity: "high"}`。
- 断言:`len(report.violations) == 2 and any(v["type"] == "sum_constraint" for v in report.violations)`。

### AC-3
- 给定:优化完成后,`optimizer_report.json` 落盘。
- 当:读取 JSON。
- 那么:含字段 `sharpe, expected_return, volatility, weights_sum, max_weight, industry_exposures, violations`。
- 断言:`all(k in report for k in ["sharpe", "expected_return", "volatility", "weights_sum", "max_weight", "industry_exposures", "violations"])`。

---

<a id="ac-fr-3900"></a>
## FR-3900 与等权基线对比

### AC-1
- 给定:候选 50 资产,优化 `w_opt` 与等权基线 `w_eq = [0.02] * 50`。
- 当:调用 `compare_to_baseline(w_opt, mu, cov, w_eq)`。
- 那么:返回 `ComparisonReport`,含 `optimized` 与 `equal_weight` 两个 dict,每个含 `expected_return, volatility, sharpe, max_weight, turnover`。
- 断言:`set(report.optimized.keys()) == {"expected_return", "volatility", "sharpe", "max_weight", "turnover"}`。

### AC-2
- 给定:同 AC-1,首次运行(`w_prev = 0`)。
- 那么:`turnover = 0.5`(因 `0.5 * sum(|w_opt - 0|) = 0.5 * sum(w_opt) = 0.5`)。

### AC-3
- 给定:优化后 Sharpe 显著低于等权(如 0.5 vs 1.2)。
- 当:流水线执行。
- 那么:WARNING 日志 `optimized sharpe < baseline, check inputs`,`portfolio_metrics.csv` 中 `delta.sharpe = -0.7`(不阻断流程)。
- 断言:`"optimized sharpe < baseline" in caplog.text and not error raised`。

---

<a id="ac-fr-4000"></a>
## FR-4000 优化结果持久化

### AC-1
- 给定:优化完成。
- 当:检查 `reports/portfolio_<ts>/` 目录。
- 那么:含 `weights.csv, optimizer_report.json, portfolio_metrics.csv, weights_diagnostics.json, assets_dropped.json` 5 个文件,均非空(>100 bytes)。
- 断言:`all((out_dir / f).exists() and (out_dir / f).stat().st_size > 100 for f in ["weights.csv", "optimizer_report.json", "portfolio_metrics.csv", "weights_diagnostics.json", "assets_dropped.json"])`。

### AC-2
- 给定:`weights.csv`。
- 当:读取。
- 那么:列 `asset, weight, sector, mu, in_universe`;`weight` 列 sum ≈ 1.0(误差 < 1e-6)。
- 断言:`pl.read_csv("weights.csv")["weight"].sum() == pytest.approx(1.0, abs=1e-6)`。

### AC-3
- 给定:优化过程中(落盘被中断)。
- 当:流水线启动后立即 kill -9。
- 那么:`reports/portfolio_<ts>/` 目录要么不存在,要么所有文件齐全(无半成品)。通过 atomic rename 保证。

---

<a id="ac-fr-4100"></a>
## FR-4100 优化 CLI

### AC-1
- 给定:CLI 命令 `trader-off optimize --predictions predictions.csv --industry-map configs/industry_map.csv --output reports/portfolio_test/`。
- 当:执行。
- 那么:退出码 0,stdout 含 "Sharpe=" 与 "报告落盘到 reports/portfolio_test/"。
- 断言:`result.returncode == 0 and re.search(r"Sharpe=([\d.]+)", result.stdout)`。

### AC-2
- 给定:--predictions 文件不存在。
- 当:执行。
- 那么:退出码 2,stderr 含 "predictions file not found"。

### AC-3
- 给定:候选资产数 = 3(< 5 阈值)。
- 当:执行。
- 那么:退出码 3,stderr 含 "too few assets (3 < 5)"。

### AC-4
- 给定:--cov-window=30(用户自定义)。
- 当:执行。
- 那么:协方差估计使用最近 30 个交易日(可通过 mock data_loader 验证)。

---

<a id="ac-fr-4200"></a>
## FR-4200 优化器作为 v0.1.0 策略输入 (OptimizedTopKStrategy)

### AC-1
- 给定:`OptimizedTopKStrategy(broker, config)`。
- 当:检查继承关系。
- 那么:是 `quantide.core.strategy.BaseStrategy` 子类(继承 v0.1.0 AC-FR1000-01)。
- 断言:`issubclass(OptimizedTopKStrategy, BaseStrategy)`。

### AC-2
- 给定:`weights.csv` 存在,`config["top_k"]=20`。
- 当:`await strategy.init()`。
- 那么:`strategy.weights` 为非空 dict,长度 ≥ 20,`strategy.top_k == 20`。
- 断言:`len(strategy.weights) >= 20 and strategy.top_k == 20`。

### AC-3
- 给定:当日为交易日 tm,策略已 init。
- 当:`await strategy.on_day_open(tm)`。
- 那么:
  - 对 `weights.csv` 中每只资产调用 `broker.trade_target_pct(asset, weight)`。
  - 对当前持仓但不在 `weights` 中的资产调用 `trade_target_pct(asset, 0)` 清仓。
  - `extra` 参数含 `{reason: "optimized_topk", weight: float, version: str}`。
- 断言:mock broker 验证调用次数与参数。

### AC-4
- 给定:`weights.csv` 不存在(策略降级)。
- 当:`await strategy.init()`。
- 那么:WARNING 日志 `weights.csv missing, falling back to equal-weight top-K behavior`,策略行为退化为 `LGBMTop20Strategy`。

### AC-5
- 给定:`weights.csv` 最后更新时间距今 > 5 个交易日。
- 当:`await strategy.init()`。
- 那么:WARNING 日志 `weights stale (5+ days old), falling back`,策略退化。

---

## Non-Functional Requirements

<a id="ac-nfr-0100"></a>
## NFR-0100 性能预算 (P95 Latency)

### AC-1
- 给定:fixture(50 资产 × 252 日)+ 完整因子挖掘流水线。
- 当:执行 e2e 计时(`time.perf_counter()` 包裹 `trader-off mine-factors` 调用)。
- 那么:wall time ≤ 600 秒(P95 在 fixture 上)。
- 断言:`elapsed < 600`。

### AC-2
- 给定:fixture(4000 资产 × 60 日,精选 30 因子)。
- 当:执行 `trader-off predict`。
- 那么:wall time ≤ 5 秒(P95)。
- 断言:`elapsed < 5`。

### AC-3
- 给定:fixture(1 年回测窗口,50 资产,Max Sharpe 优化)。
- 当:执行 `trader-off backtest --strategy optimized_topk`。
- 那么:wall time ≤ 600 秒(含优化时间)。
- 断言:`elapsed < 600`。

### AC-4
- 给定:任何上述流水线。
- 当:`psutil.Process().memory_info().rss` 监控。
- 那么:内存峰值 ≤ 16 GB。
- 断言:`peak_memory_gb < 16`。

### AC-5
- 给定:5 个交易日的增量数据 + 已训练全量模型。
- 当:触发增量重训。
- 那么:wall time ≤ 60 秒。
- 断言:`elapsed < 60`。

---

<a id="ac-nfr-0200"></a>
## NFR-0200 单元测试覆盖率 ≥ 97%

### AC-1
- 给定:执行 `pytest --cov=trader_off --cov-report=term-missing`。
- 当:CI 运行测试。
- 那么:报告最后一行 `TOTAL` 覆盖率 ≥ 97%。
- 断言:`parse_total_coverage(output) >= 97`。

---

<a id="ac-nfr-0300"></a>
## NFR-0300 Mutation Testing ≥ 80% (mutmut)

### AC-1
- 给定:`mutmut run --paths-to-mutate src/trader_off/factor_mining/ src/trader_off/scheduler/ src/trader_off/portfolio/`。
- 当:执行完成。
- 那么:mutation score ≥ 80%(通过 `mutmut results` 命令读取)。
- 断言:`parse_mutation_score(output) >= 80`。

---

<a id="ac-nfr-0400"></a>
## NFR-0400 文档同步与 ADR

### AC-1
- 给定:`docs/adr/` 目录。
- 当:列出文件。
- 那么:含 `0001-optimizer-cvxpy-scipy.md`、`0002-scheduler-persistence.md`、`0003-factor-dsl-approach.md` 至少 3 个 ADR。
- 断言:`len(list((project_root / "docs" / "adr").glob("*.md"))) >= 3`。

### AC-2
- 给定:每个 ADR 文件。
- 当:解析 frontmatter 或首段。
- 那么:含 `Status`(Proposed/Accepted/Superseded)、`Context`、`Decision`、`Consequences` 四个章节。
- 断言:`all(s in adr_text for s in ["## Status", "## Context", "## Decision", "## Consequences"])`。

### AC-3
- 给定:执行 `python scripts/check_docs_sync.py`。
- 当:扫描 `architecture.md` 与 `interfaces.md` 中的模块/类引用。
- 那么:所有引用在代码中真实存在,无悬空引用。

---

<a id="ac-nfr-0500"></a>
## NFR-0500 代码风格与异步约定 (继承 v0.1.0)

### AC-1
- 给定:执行 `ruff check trader_off/`。
- 那么:0 个 error,line length ≤ 100 检查通过(继承 v0.1.0 AC-NFR0400-01)。

### AC-2
- 给定:`RetrainScheduler.start/stop/trigger_now/get_status` 方法签名。
- 那么:全部为 `async def`(继承 v0.1.0 AC-NFR0400-02)。

### AC-3
- 给定:`pyproject.toml`。
- 当:`uv sync` 执行。
- 那么:依赖成功安装,新增依赖 `cvxpy>=1.5`、`apscheduler>=3.10`、`mutmut>=2.0`、`pytest-benchmark>=4.0`(可能)、`griffe>=0.40` 或 `mkdocstrings>=0.24`。
- 断言:`uv pip list | grep -E "^(cvxpy|apscheduler|mutmut)\s"` 全部存在。

---

<a id="ac-nfr-0600"></a>
## NFR-0600 日志规范 (继承 v0.1.0)

### AC-1
- 给定:业务代码 `trader_off/`(非测试)。
- 当:`grep -r "print(" trader_off/factor_mining/ trader_off/scheduler/ trader_off/portfolio/`。
- 那么:无 `print` 调用,全部使用 `logger.info/warning/error`(继承 v0.1.0 AC-NFR0500-01)。

### AC-2
- 给定:执行任意因子挖掘/调度/优化。
- 当:完成。
- 那么:日志格式 `{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}`(继承 v0.1.0 AC-NFR0500-02)。

### AC-3
- 给定:`logs/` 目录。
- 当:三个模块分别运行后。
- 那么:`logs/factor_mining_*.log`、`logs/scheduler_*.log`、`logs/portfolio_*.log` 三个文件均存在且非空。

---

<a id="ac-nfr-0700"></a>
## NFR-0700 安全审查 (继承 v0.1.0)

### AC-1
- 给定:项目源码 `trader_off/`。
- 当:`grep -rE "(api_key|password|token|secret)\s*=\s*['\"]" trader_off/`。
- 那么:无 hard-coded credential 匹配项(继承 v0.1.0 AC-NFR0600-01)。

### AC-2
- 给定:所有文件 IO 函数(load/save 模型、registry、scheduler_state)。
- 当:检查实现。
- 那么:路径经过 `pathlib.Path.resolve()` 校验,逃逸 → `PathTraversalError`(继承 v0.1.0 AC-NFR0600-02)。

### AC-3
- 给定:YAML 加载代码(因子注册表、配置)。
- 当:`grep -r "yaml.load(" trader_off/`。
- 那么:无 `yaml.load` 调用,全部使用 `yaml.safe_load`。
- 断言:`grep_count == 0`。

### AC-4
- 给定:调度器 API 服务(FR-2000)。
- 当:默认启动。
- 那么:仅监听 127.0.0.1,外部访问失败(连接拒绝)。
- 断言:`socket.connect(("1.2.3.4", 8765))` 失败(若测主机有公网 IP);`socket.connect(("127.0.0.1", 8765))` 成功。

### AC-5
- 给定:执行 `bandit -r trader_off/factor_mining/ trader_off/scheduler/ trader_off/portfolio/ -ll`。
- 那么:报告无 HIGH 级 issue(继承 v0.1.0 AC-NFR0600-04)。

---

<a id="ac-nfr-0800"></a>
## NFR-0800 数据可重现性 (继承 v0.1.0)

### AC-1
- 给定:任意 lightGBM 训练调用(全量或增量)。
- 当:检查 params。
- 那么:`random_state=42`, `feature_fraction_seed=42`, `bagging_seed=42`(继承 v0.1.0 AC-NFR0700-01)。

### AC-2
- 给定:因子挖掘 / 调度 / 优化完成后的 `metadata.json` 或 `optimizer_report.json`。
- 当:读取。
- 那么:含字段 `git_commit_sha`(7-40 位 hex)、`python_version`、`package_versions`、`random_state`、`config_snapshot`。
- 断言:`all(k in metadata for k in ["git_commit_sha", "python_version", "package_versions", "random_state", "config_snapshot"])`。

### AC-3
- 给定:fixture 数据 `tests/fixtures/v0.2.0/`。
- 当:读取 `MANIFEST.json`。
- 那么:含每个 fixture 文件的 SHA256 校验和,运行测试时自动校验完整性。
- 断言:`hashlib.sha256(open(p, "rb").read()).hexdigest() == manifest[name]`。

---

<a id="ac-nfr-0900"></a>
## NFR-0900 调度可靠性与并发安全

### AC-1
- 给定:并发触发 10 个任务(10 个协程同时调用 `trigger_now`)。
- 当:调度器运行中。
- 那么:同一时刻活跃任务 ≤ 1(`max_concurrent_tasks=1`),FIFO 队列。
- 断言:`max_concurrent_observed == 1`。

### AC-2
- 给定:调度器运行中,模拟 kill -9,重启。
- 当:读取 `last_tasks.json`。
- 那么:之前 `running` 任务标记为 `failed`,`pending` 任务保留。
- 断言:`all(r["status"] in {"pending", "failed"} for r in recovered)`。

### AC-3
- 给定:`models/registry.json` 含 5 个不同 build 号。
- 当:模拟同一 `task_id` 重试触发。
- 那么:不产生重复训练(由 build 号唯一性 + 触发前检查保证)。
- 断言:`registry_version_count == 5`(未增加)。

---

<a id="ac-nfr-1000"></a>
## NFR-1000 向后兼容 — v0.1.0 模型/策略仍可用

### AC-1
- 给定:v0.1.0 已序列化的模型目录 `models/20260101_120000/`(从 v0.1.0 仓库复制)。
- 当:在 v0.2.0 环境中调用 `load_model(version="20260101_120000")`。
- 那么:成功加载,返回 `ModelArtifact`,无 `metadata` 字段缺失错误。
- 断言:`isinstance(artifact, ModelArtifact) and artifact.booster is not None`。

### AC-2
- 给定:v0.1.0 fixture 模型。
- 当:用 v0.2.0 `predict(model_version="20260101_120000", watchlist=[...])`。
- 那么:返回的 DataFrame schema 与 v0.1.0 一致(`asset, score, rank`)。
- 断言:`set(predict_df.columns) == {"asset", "score", "rank"}`。

### AC-3
- 给定:v0.1.0 CLI 命令 `trader-off train|predict|backtest|feature-importance`。
- 当:在 v0.2.0 环境中执行(无 v0.2.0 新参数)。
- 那么:所有命令正常工作,行为与 v0.1.0 一致。
- 断言:`subprocess.run(["trader-off", "feature-importance", "--model", "..."]).returncode == 0`。

### AC-4
- 给定:v0.1.0 策略类 `LGBMTop20Strategy`。
- 当:在 v0.2.0 中 import。
- 那么:无 deprecation warning,仍可实例化并运行。
- 断言:`from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy` 成功,`issubclass(LGBMTop20Strategy, BaseStrategy)` 为 True。
