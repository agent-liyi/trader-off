---
status: draft
locked: false
---
# v0.5.2 — 因子挖掘 CLI 修复 + save 契约升级 — Spec

- **Spec ID**: v0.5.2-001-factor-mining-cli-fix
- **Created**: 2026-07-22
- **Status**: Draft
- **关联 story**: `.louke/project/specs/v0.5.2-001-factor-mining-cli-fix/story.md` (STR-0006)
- **继承基线**:
  - v0.2.0 FR-0800 `trader-off mine-factors` CLI 退出码 0/3/4 契约 (本 spec **不**改 exit code 0/3/4 语义,新增 exit code 5 = evaluation failure)
  - v0.2.0 FR-0300 `evaluate_factor(factor_values, labels, dates) -> FactorEvaluation` 公开契约 (本 spec **不**改签名)
  - v0.2.0 FR-0400 `select_factors(evaluations, factor_specs, top_k, corr_threshold) -> (selected, diagnostics)` 公开契约 (本 spec **不**改签名)
  - v0.2.0 FR-0600 因子注册表持久化 (本 spec **覆盖** `save(out_dir)->file` 旧契约,升级为 `save(out_path: file)` 新契约)
  - v0.4.1 `QuantideDataLoader.get_daily(asset, end_date, count)` 真 Tushare 通路 (本 spec 复用其 lazy import 模式)
  - v0.4.1 NFR-0100 函数级 lazy import 白名单 `quantide.data.fetchers.tushare.*` (本 spec 沿用)
  - v0.5.1 NFR-0100 增量放行 `quantide.data.models.calendar.calendar` (本 spec 沿用)
  - v0.3.0 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` fixture 契约 (本 spec 复用)

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。验收标准放在 `acceptance.md` 中。测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。

> **北极星目标**: 修复 v0.4.1 demo 暴露的 `trader-off mine-factors` 4 个 bug,使 fixture 路径(无 token)和真实 token 路径(有 token)均能跑通最小 evaluate/select 闭环:数据加载 → factor values 计算 → labels (forward returns) → `evaluate_factor` 真实调用 → `select_factors` 按 ICIR 选择 → save registry 到文件 → 退出码正确。同步升级 `save_factor_registry` 契约,从 `out_dir: Directory` 改为 `out_path: File`,消除「把目录当 registry 文件」歧义。

> **关键约束 (继承 Story §3.2 / §5)**:
> - patch ≤ 1 issue;本 spec 拆 FR-0100 / NFR-0100 两条便于追踪
> - 4 bug 必同时修复,缺一即回归;**不**做部分修复 + 留尾
> - 退出码 0/3/4 沿用 v0.2.0 FR-0800;**新增** exit code 5 = evaluation failure (与 v0.4.2 `cli/backtest.py` 退出码 5 编号复用,语义不同)
> - save 契约**升级**(Human 已选):`save_factor_registry(specs, out_path: Path, *, fmt)` `out_path` 改为完整文件路径(含文件名 + 扩展名),**不**接受目录;同步迁移所有 callers / tests
> - 沿用 v0.4.1 函数级 lazy import 白名单 (`quantide.data.fetchers.tushare.*` + v0.5.1 增量 `quantide.data.models.calendar.calendar`)
> - Fixture 路径 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` (50 资产 × 252 日);`TUSHARE_TOKEN` 缺失时 fallback 到该 fixture
> - Python ≥ 3.13;`pytest` 测试框架 (继承 project.toml)

## User Stories

### US-0010

story: 作为一名量化研究员,我在本地持有 `TUSHARE_TOKEN` 时(或无 token 仅用 fixture 时),希望通过 `trader-off-mine-factors --config <yaml> [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--top-k N] [--corr-threshold F] [--output <dir>] [--registry-path <file>]` 一次命令,从 OHLCV 数据(真实或 fixture)枚举 ≥200 候选因子、evaluate 每个候选、select top-K 因子、按 ICIR 排序、保存到 `registry_path` 指定的文件,并返回 0/3/4/5 退出码,从而让 v0.4.1 demo 卡住的 evaluate 闭环真正跑通,registry 落盘文件可被 v0.1.0 `train_model` 直接消费。

priority: P0

## Usage Scenarios

### scenario-0010 happy path — fixture 路径 (TUSHARE_TOKEN 缺失)

1. 开发者**不**设置 `TUSHARE_TOKEN`,执行 `trader-off-mine-factors --config configs/factor_mining.yaml --start 2022-01-01 --end 2022-12-31 --registry-path factor_registry/factors.yaml`。
2. CLI 读 config → 函数级 lazy import `trader_off.data.quantide_adapter.QuantideDataLoader` (项目内模块,不在 NFR-0100 白名单约束内,但同样函数级 lazy import 以保留 token-less fallback 灵活性)。
3. CLI 检测 `TUSHARE_TOKEN` 缺失 → 直接读 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` (50 资产 × 252 日) 作为 OHLCV 来源 (不发起网络 IO,不实例化 `TushareFetcher`)。
4. CLI 从 close 价格计算 labels (forward returns,默认 5 日:`close[t+5] / close[t] - 1`)。
5. CLI 调 `enumerate_factors(...)` → ≥200 候选因子;逐个调 `spec.compute_fn(ohlcv_df)` 算 factor values;逐个调 `evaluate_factor(factor_values, labels, dates)` 生成真实 `FactorEvaluation`(而非 `evaluate_factor.__wrapped__` 函数对象)→ append 到 `evaluations` 列表。
6. CLI 调 `select_factors(evaluations=evaluations, factor_specs=candidates, top_k=args.top_k, corr_threshold=args.corr_threshold)` → 真实按 ICIR 排序 + Pearson 去冗余(无 `function.icir` AttributeError)。
7. CLI 调 `save_factor_registry(specs=selected, out_path=Path("factor_registry/factors.yaml"), fmt="yaml")` → 落新契约下的文件 (创建 parent dir if missing)。
8. 退出码 0;stdout 打印「枚举了 N 个候选因子」「精选 K 个因子」「registry 落盘到 <path>」。

### scenario-0020 happy path — 真实 token 路径 (TUSHARE_TOKEN 存在)

1. 开发者 `export TUSHARE_TOKEN=xxx`,执行同 scenario-0010 命令。
2. CLI 检测 `TUSHARE_TOKEN` 存在 → 函数级 lazy import `QuantideDataLoader(token=os.environ['TUSHARE_TOKEN'])` → 对 fixture parquet 中的 50 个资产顺序调 `await loader.get_daily(asset, end_date=end, count=...)` (v0.4.1 公开契约,token 经 `os.environ` 注入)。
3. CLI 合并 50 个资产的 OHLCV → 计算 labels → 走 scenario-0010 step 5-8 同路径。
4. 退出码 0;**不** echo token 值(继承 v0.4.1 NFR-0100 安全条款)。

### scenario-0030 evaluation failure → exit code 5

1. fixture / 真实数据加载成功,但所有(或几乎所有)候选因子的 `evaluate_factor` 抛异常(例如 `compute_fn` 引用缺失列导致 schema validation 失败)。
2. CLI 捕获异常 → `logger.exception(f"evaluation failed for {spec.id}: {exc}")` + stderr 打印;**继续**遍历剩余候选(不中断)。
3. 评估成功数 < 候选总数 → 至少 1 条 `logger.exception` 调用。
4. 退出码 5 (= evaluation failure);**不**返回 0(因为 evaluate 闭环未完成)。

### scenario-0040 config error → exit code 4

1. `trader-off-mine-factors --config /tmp/nonexistent.yaml ...` → config 不存在 → 退出码 4,stderr 含 `"config file not found"`。
2. 沿用 v0.2.0 FR-0800 既有行为;**不**新增额外 config 校验。

### scenario-0050 few selected (<10) → exit code 3

1. 同 scenario-0010 路径,但候选总数 < 10 (例如 fixture 数据范围过窄,候选枚举返回 5 个)。
2. 评估成功 → 精选数 = 5 < 10 → `logger.warning("fewer than 10 selected factors")` → 退出码 3;registry 文件仍落盘。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表 (Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100** 一条 P0 FR + **NFR-0100** 一条 NFR;起始 100 间隔 (patch ≤ 1 issue 范围,沿用 v0.4.2 / v0.5.1 编号策略)。后续 review round 插入 10 间隔位。
>
> **必读**: FR-XXXX 是该需求唯一 ID,**禁止删除**既有 ID;若 FR 需废弃,改表内 Valid=❌ 并在 Clarification Log 解释。
>
> 引用约定 (AC): 验收标准用 `AC-FRXXXX-YY` 格式 (4 位 FR + 2 位 AC),见 `acceptance.md`。
>
> **元数据表 (3 列)**:
> - Valid (原 yaml `valid`): ✅ = 仍生效,❌ = 已废弃
> - Testable (原 yaml `testability`): ✅ = 可测试/可断言,⚠️ {原因} = 存保留意见
> - Decided (原 yaml `resolved`): ✅ = 用户已确认,⚠️ = 待澄清,❌ = 用户明确拒绝

---

<a id="fr-0100"></a>
### FR-0100 修复 `trader-off mine-factors` 4 个 bug + 升级 `save_factor_registry` 契约 (out_dir → out_path: File)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **Bug 1 (evaluate_factor 调用)**: 替换 `cli.py:180-185` 的 `ev = evaluate_factor.__wrapped__` hack(返回函数对象而非结果)→ 改为**真实调用** `evaluate_factor(factor_values, labels, dates)`,把返回的 `FactorEvaluation` append 到 `evaluations` 列表。
- **Bug 2 (select_factors 类型)**: 修复 select_factors 收到的 `function` 对象触发 `function.icir AttributeError` → 通过 Bug 1 修复后,`evaluations` 列表含真实 `FactorEvaluation` 实例,`select_factors` 按 ICIR 排序 + Pearson 去冗余 正常返回 (无 AttributeError)。
- **Bug 3 (CLI 数据加载)**:
  - **数据来源** (二选一):
    - **Fixture 路径** (TUSHARE_TOKEN 缺失): 直接读 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` (50 资产 × 252 日,继承 v0.2.0 e2e fixture 契约;SHA256 见 `tests/fixtures/v0.2.0/MANIFEST.json`)。**不**发起网络 IO,**不**实例化 `TushareFetcher`。
    - **真实路径** (TUSHARE_TOKEN 存在): 函数级 lazy import `from trader_off.data.quantide_adapter import QuantideDataLoader` (项目内模块,不在 NFR-0100 白名单约束内,但同样函数级 lazy import 保持与 fixture 路径的隔离);`QuantideDataLoader(token=os.environ['TUSHARE_TOKEN'])` → 对 fixture 中 50 个 asset 顺序调 `await loader.get_daily(asset, end_date=end, count=...)` (v0.4.1 公开契约,token 经 `os.environ` 注入)。
  - **Labels 计算**: 从 close 价格算 forward returns,默认 5 日:`label[t] = close[t+5] / close[t] - 1`,在数据范围最后 5 日填 NaN (评估时跳过,继承 v0.1.0 label 契约);输出 `pl.DataFrame` 列 `asset, date, label`。
  - **Factor values 计算**: 对每个候选 `spec` 调 `spec.compute_fn(ohlcv_df)` 返回 `pl.Series`,重命名 `value` 列 → 构造 `pl.DataFrame` 列 `asset, date, value`(per spec,遍历所有候选)。
  - **Dates 列表**: 从 ohlcv_df 的 `date` 列去重排序后转 `list[date]`(交易日序列)。
- **Bug 4 (save 契约)**:
  - **新签名**: `save_factor_registry(specs: list[FactorSpec], out_path: Path, *, fmt: Literal["yaml", "json"] = "yaml") -> Path`
    - 参数名 `out_dir` → `out_path` (语义从「目录」改为「完整文件路径」,含文件名 + 扩展名)
    - `out_path` 是**文件路径** (如 `factor_registry/factors.yaml`),**不**接受目录
    - 函数内部 `out_path.parent.mkdir(parents=True, exist_ok=True)` 创建父目录(继承 v0.2.0 自动建目录能力)
    - 文件名沿用 `{stem}.yaml` / `{stem}.json` (由调用方传入 `out_path` 决定,函数**不**硬编码 `factors{ext}`)
    - 返回值 = `out_path`(原样返回,与旧契约返回值类型一致)
  - **load 契约** (零修改): `load_factor_registry(path: Path) -> dict` 仍只接受**文件路径**,**不**接受目录;`_load_raw_data` 内 `with open(path)` 行为不变。
  - **同步迁移**: 旧契约 `out_dir` 参数移除;所有 callers (`cli.py:203`、测试用例) 同步更新为传入完整文件路径;**不**保留双签名兼容(Story §6 Human 已选「修改 save 契约」)。
- **CLI 参数** (argparse,与 v0.2.0 兼容 + 新增 1 个):
  - `--config PATH` (required,YAML 配置文件路径,继承 v0.2.0 FR-0800)
  - `--start DATE` (optional,ISO `YYYY-MM-DD`,fallback 到 config 或今天)
  - `--end DATE` (optional,ISO `YYYY-MM-DD`,fallback 到 config 或今天)
  - `--top-k N` (int,default 30,继承 v0.2.0)
  - `--corr-threshold F` (float,default 0.9,继承 v0.2.0)
  - `--output DIR` (Path,output 报告目录,default `reports/factor_mining_<ts>/`,继承 v0.2.0)
  - `--registry-path FILE` (Path,**新增**;registry 文件完整路径,default `factor_registry/factors.yaml`;**取代**旧 `--registry-dir`)
- **退出码** (沿用 v0.2.0 + 新增 1 个):
  - **0** = 成功(精选因子 ≥ 10 个)
  - **3** = 精选因子 < 10 个(沿用 v0.2.0 FR-0800 既有语义)
  - **4** = config 文件不存在(沿用 v0.2.0 FR-0800 既有语义)
  - **5** = **新增** evaluation failure(所有候选 evaluate 均失败 / 数据加载失败导致 evaluate 闭环未完成)
  - 注: argparse 参数缺失仍由 argparse 自身报 SystemExit(2),**不**新增 2 退出码
- **数据契约**:
  - **Fixture 路径** 输入: `tests/fixtures/v0.2.0/ohlcv_50x252.parquet`,schema `{date: Date, asset: Utf8, open: Float64, high: Float64, low: Float64, close: Float64, volume: Float64, turnover: Float64, adj_factor: Float64}` (与 v0.2.0 fixture 契约一致)
  - **真实路径** 输入: `QuantideDataLoader.OHLCV_SCHEMA` 同 schema(继承 v0.4.1)
  - **Labels 输出**: `pl.DataFrame` 列 `{asset: Utf8, date: Date, label: Float64}` (与 v0.1.0 label 契约一致)
  - **Factor values 输出**: per spec `pl.DataFrame` 列 `{asset: Utf8, date: Date, value: Float64}`
- **签名兼容**:
  - `evaluate_factor(factor_values, labels, dates) -> FactorEvaluation` 签名**零修改** (继承 v0.2.0 FR-0300)
  - `select_factors(evaluations, factor_specs, top_k, corr_threshold) -> tuple[list[FactorSpec], SelectionDiagnostics]` 签名**零修改** (继承 v0.2.0 FR-0400)
  - `QuantideDataLoader` 类与 `get_daily(asset, end_date, count)` 方法签名**零修改** (继承 v0.4.1)
  - `load_factor_registry(path: Path) -> dict` 签名**零修改**
  - `save_factor_registry` 签名**修改**: `out_dir: Path` → `out_path: Path`;返回值不变
- **out-of-scope** (继承 Story §3.2,显式**不**做):
  - 训练→预测→评估→选择的完整数据流水线(沿用 v0.2.0 FR-0900 既有边界)
  - 新 factor template / 新 evaluation metric(沿用 v0.2.0 模板库)
  - 并行/重试/scheduler/数据质量平台(沿用 v0.5.1 边界)
  - 改 `QuantideDataLoader` / `get_daily` 签名 (v0.4.1 锁定)
  - 双签名 save 兼容(Story §6 Human 已选「修改 save 契约」,不保留 `out_dir` 入参)
  - `--start` / `--end` 实际裁剪 evaluate 范围(本 spec 用整个 fixture / 真实数据范围)

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR,此处省略。

---

<a id="nfr-0100"></a>
### NFR-0100 函数级 lazy import — 沿用 v0.4.1 / v0.5.1 白名单 (`quantide.data.fetchers.tushare.*` + `quantide.data.models.calendar.calendar`)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **隔离承诺 (继承 v0.4.1 / v0.5.1 白名单)**: `src/trader_off/factor_mining/cli.py` 模块顶层(含 `import` 块、`from ... import` 块、`if TYPE_CHECKING` 块、模块级 docstring 示例代码、`__all__` 列表)**不**出现 `import quantide` 或 `from quantide ...` 语句。
- 所有 `quantide` 导入必须位于 `def` / `async def` 函数体内;导入时机为首次调用(本 spec 实际**不**直接 import quantide,而是 lazy import 项目内 `trader_off.data.quantide_adapter.QuantideDataLoader`,该 adapter 内部已按 v0.4.1 函数级 lazy quantide 导入,白名单边界在 `quantide_adapter.py` 内已封口)。
- **业务符号白名单 (本 spec 沿用 v0.4.1 + v0.5.1 增量)**:
  - **允许** import `quantide.data.fetchers.tushare.*` (继承 v0.4.0 / v0.4.1;含 `TushareFetcher` / `fetch_calendar` / `fetch_bars` 等;**不**实际 import,仅白名单允许)
  - **允许** import `quantide.data.models.calendar.calendar` (v0.5.1 增量放行;**不**实际 import,仅白名单允许)
  - **禁止** import `quantide.service.*` / `quantide.portfolio.*` / `quantide.backtest.*` / `quantide.core.scheduler.*` / `quantide.data.models.daily_bars.*` / `quantide.data.fetchers.<非 tushare>.*` (白名单外)
- **项目内模块 import** (非 quantide,本 NFR **不**约束,但**建议**同样函数级 lazy): `from trader_off.data.quantide_adapter import QuantideDataLoader` (项目内模块,NFR-0100 仅约束 quantide import;建议函数级以保留 token-less fallback 灵活性,实际代码视实现选择)
- **验证 1 (模块顶层)**: `grep -rn "^import quantide\|^from quantide" src/trader_off/factor_mining/cli.py` 应无匹配
- **验证 2 (非白名单业务符号)**: `grep -rnE "quantide\.(service|portfolio|backtest|core\.scheduler|models\.daily_bars|fetchers\.(?!tushare))" src/trader_off/factor_mining/cli.py` 应无匹配 (Perl/PCRE negative lookahead)
- **验证 3 (AST 校验)**: Python AST 解析(`ast.parse` + 遍历 `ast.ImportFrom` / `ast.Import`)`cli.py`,所有 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点的祖先链必须含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 import (本 spec 内 cli.py **不**直接 import quantide,此验证作为回归保护)
- **验证 4 (cli/ 目录隔离)**: `grep -rn "^import quantide\|^from quantide" src/trader_off/cli/` 除 `sync_data.py` 函数体内 import 外应无其他模块顶层匹配(`cli/__init__.py` / `cli/backtest.py` 仍零 quantide 顶层 import,延续 v0.4.2 / v0.5.1 隔离承诺)
- **验证 5 (quantide_adapter 隔离持续)**: `src/trader_off/data/quantide_adapter.py` 模块顶层仍零 quantide import(继承 v0.4.1 NFR-0100 AC-3);本 patch **不**修改 `quantide_adapter.py`,作为白名单边界封口点。

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|
| 0 (Story M-STORY) | Story §6 Human 确认 | 分流结论 Go / save 契约修改方案 / Out-of-Scope 认同 (M-FOUND 已通过) | ✅ |
| 0 (M-SPEC) | 任务描述 4 bug 拆 1 FR vs 拆 4 FR | 任务描述列出「1 FR + 1 NFR」,4 bug 紧耦合(必须同时修复才能让 CLI 跑通 evaluate 闭环)。**决策**: 合并为单条 FR-0100,4 bug 各开 AC (AC-1/2/3/4/5/6/7/8 覆盖);避免 FR 碎片化,issue 仍为 1 条 | ✅ |
| 0 (M-SPEC) | save 契约 `out_dir` → `out_path` 影响范围 | 现有 callers: `cli.py:203`、`tests/unit/factor_mining/test_registry.py` (10+ 处)、`tests/integration/test_train_with_registry.py` (3 处)、`tests/e2e/test_factor_mining_e2e.py` (1 处)。**决策**: 全仓同步迁移到 `out_path` 完整文件路径;**不**保留 `out_dir` 双签名(Story §6 Human 已选「修改 save 契约」);迁移说明写入 FR-0100 描述「同步迁移」条款与 Clarification Log | ✅ |
| 0 (M-SPEC) | fixture 路径与真实 token 路径的 lazy import 边界 | 任务描述要求「QuantideDataLoader (function-scope lazy) 加载 OHLCV」。**决策**: cli.py 函数级 lazy import `from trader_off.data.quantide_adapter import QuantideDataLoader`(项目内,不在 NFR-0100 白名单约束);`quantide_adapter.py` 内部已按 v0.4.1 NFR-0100 封口所有 quantide import;cli.py 模块顶层保持零 quantide import。NFR-0100 AC-3 (AST 校验) 作为回归保护,即便 cli.py 后续误加 quantide import 也会被 Lex stage 1 拦下 | ✅ |
| 0 (M-SPEC) | 退出码 5 触发条件 | Story §2 仅说「CLI 返回 0 或既有退出码」,未指定 5。**决策**: exit code 5 = evaluation failure(所有候选 evaluate 均失败 / 数据加载失败导致 evaluate 闭环未完成),与 v0.4.2 `cli/backtest.py` 退出码 5 编号复用,语义不同;CLI 内部维护「evaluate 全部失败」计数器,所有候选均失败 → 退出码 5(在 select_factors 之前返回);**不**新增 6 = data load failure(数据加载失败视为 evaluation failure 的一种) | ✅ |
| 0 (M-SPEC) | labels forward returns 默认窗口 | 任务描述说「compute labels (forward returns) from close prices」,未指定窗口。**决策**: 默认 N=5 日(`label[t] = close[t+5] / close[t] - 1`),与 v0.1.0 FR-0100 既有 label 契约一致(继承 v0.1.0 / v0.2.0);CLI **不**暴露 `--label-window` 参数(沿用默认 5 日),避免 spec 膨胀;评估时缺失日期 (数据末尾 5 日) 跳过,继承 v0.2.0 FR-0300「缺失日期跳过」语义 | ✅ |
| 0 (M-SPEC) | NFR-0100 沿用 v0.4.1 + v0.5.1 白名单 | 任务描述显式要求「same as v0.5.1」。**决策**: 沿用 v0.4.1 的 `quantide.data.fetchers.tushare.*` + v0.5.1 增量的 `quantide.data.models.calendar.calendar`;本 spec 实际不直接 import quantide(经 `quantide_adapter` 间接),白名单约束作为回归保护存在;**不**新增 `trader_off.data.quantide_adapter` 符号约束(NFR 仅约束 quantide) | ✅ |
| 0 (M-SPEC) | `--registry-dir` vs `--registry-path` 命名 | 旧 CLI 参数 `--registry-dir` 接受目录;新 CLI 参数接受文件路径。**决策**: 改名为 `--registry-path`(语义清晰,避免「dir」误导);旧 `--registry-dir` **不**保留 alias(Story §6 Human 已选「修改 save 契约」,全仓同步);default 值 = `factor_registry/factors.yaml`(与 v0.2.0 FR-0800 `factor_registry/factors.yaml` 既有产物对齐) | ✅ |
