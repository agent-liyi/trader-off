# v0.5.2 — 因子挖掘 CLI 修复 + save 契约升级 — Acceptance Criteria

- **Spec ID**: v0.5.2-001-factor-mining-cli-fix
- **Created**: 2026-07-22
- **继承基线**: v0.2.0 FR-0800 退出码 0/3/4 / FR-0300 evaluate_factor / FR-0400 select_factors;v0.2.0 FR-0600 因子注册表(本 spec 升级 `save` 契约);v0.4.1 FR-0100 QuantideDataLoader 真数据通路;v0.4.1 / v0.5.1 NFR-0100 函数级 lazy import 白名单。本文件仅定义 v0.5.2 新增 FR / NFR 的 AC。

> 中央注册表: spec.md 只保留 FR/NFR 描述与元数据 (testability/decided/valid);可观察、可断言的通过条件在本表中。
>
> 编号约定:
> - 每个 FR/NFR 单元内 AC-N 从 1 起,按顺序递增;单元之间不复用
> - 完整 AC 引用: **AC-FRXXXX-YY** (4 位 FR + 2 位 AC 序号),与 test-plan / issue schema 保持一致
> - 标题层级: `## FR-XXXX {title}` 为 level-2;`### AC-N` 为 level-3 (其后同一行**不**接任何文字,canonical ID 写在下一行)
>
> Lex 阶段 1/2 审查验证: (1) 本表存在; (2) spec.md 每个 FR/NFR 在本表中有对应章节; (3) 每条 AC 可被测试或断言。
>
> EARS 句式关键词约定: `WHEN` (触发条件) / `WHILE` (持续状态) / `WHERE` (前置条件) / `IF ... THEN` (条件分支) / `THE 系统 SHALL ...` (系统行为)。

---

<a id="ac-fr-0100"></a>
## FR-0100 修复 `trader-off mine-factors` 4 个 bug + 升级 `save_factor_registry` 契约 (out_dir → out_path: File)

### AC-1

AC-FR0100-01

- **WHEN** CLI 处理每个候选 spec 时调用 `evaluate_factor`
- **THEN** 系统 SHALL 真实调用 `evaluate_factor(factor_values, labels, dates)`,把返回的 `FactorEvaluation` 实例 append 到 `evaluations` 列表;**不**使用 `evaluate_factor.__wrapped__` hack(原 bug: 返回函数对象而非评估结果)
- **断言**:
  - 给定: `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 存在;universe 含 fixture 中的 50 个 asset;`--top-k 30`;`enumerate_factors` 产生 N ≥ 200 候选
  - 当: `trader-off-mine-factors --config config.yaml --start 2022-01-01 --end 2022-12-31 --registry-path /tmp/registry/factors.yaml` 执行 (无 TUSHARE_TOKEN)
  - 那么:
    - `evaluations` 列表长度 = N (所有候选均有评估结果,**不**为 0)
    - `evaluations[i]` 是 `FactorEvaluation` 实例 (可用 `isinstance(evaluations[i], FactorEvaluation)` 断言)
    - `evaluations[i].icir` 是 `float` (非函数对象,**不**触发 `AttributeError`)
    - `select_factors` 调用**不**抛 `AttributeError: 'function' object has no attribute 'icir'`
- **对应 EARS**: Story §2 AC-03

### AC-2

AC-FR0100-02

- **WHEN** `TUSHARE_TOKEN` 缺失时 CLI 启动
- **THEN** 系统 SHALL 读 `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` (50 资产 × 252 日) 作为 OHLCV 来源,计算 factor values + labels,**不**发起任何网络 IO,**不**实例化 `TushareFetcher` / `fetch_calendar` / `fetch_bars`
- **断言**:
  - 给定: `os.environ` 中无 `TUSHARE_TOKEN`;fixture parquet 存在
  - 当: CLI 完整链路执行
  - 那么:
    - `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` 被 polars `read_parquet` 加载,行数 = 50 × 252 = 12600 (与 `MANIFEST.json` 一致)
    - `quantide.data.fetchers.tushare.TushareFetcher` **未被**实例化 (可用 `unittest.mock.patch("quantide.data.fetchers.tushare.TushareFetcher")` + `assert_not_called()` 验证)
    - `quantide.data.fetchers.tushare.fetch_calendar` **未被**调用 (mock 验证)
    - `quantide.data.fetchers.tushare.fetch_bars` **未被**调用 (mock 验证)
    - `pl.read_parquet` 调用**至少** 1 次
    - 退出码 = 0 (评估 + select 成功时)
- **对应 EARS**: Story §2 AC-01

### AC-3

AC-FR0100-03

- **WHEN** `TUSHARE_TOKEN` 存在时 CLI 启动
- **THEN** 系统 SHALL 函数级 lazy import `QuantideDataLoader(token=os.environ['TUSHARE_TOKEN'])`,对 fixture 中的 50 个 asset 顺序调 `await loader.get_daily(asset, end_date=end, count=...)` (v0.4.1 公开契约,token 经 env 注入)
- **断言**:
  - 给定: `os.environ['TUSHARE_TOKEN'] = "fake-token-for-test"`;fixture 存在
  - 当: CLI 完整链路执行,monkeypatch `TushareFetcher` / `fetch_calendar` / `fetch_bars` 返回固定 OHLCV mock
  - 那么:
    - `QuantideDataLoader` 实例化**至少** 1 次 (`QuantideDataLoader.__init__` 调用)
    - `loader.get_daily(asset, end_date=end, count=N)` 对每个 asset 调用**一次**(共 50 次);`N >= 1`
    - `TushareFetcher` mock 实例化**至少** 1 次 (真实路径被走到)
    - 退出码 = 0 (mock 路径下评估成功)
    - **不**在 stderr / stdout / log 中出现 token 字面值 (`"fake-token-for-test"` 不在 captured output 中)
- **对应 EARS**: Story §2 AC-02

### AC-4

AC-FR0100-04

- **WHEN** CLI 计算 labels
- **THEN** 系统 SHALL 从 close 价格计算 forward returns,默认 5 日:`label[t] = close[t+5] / close[t] - 1`,在数据范围最后 5 日填 NaN;输出 `pl.DataFrame` 列 `{asset: Utf8, date: Date, label: Float64}`
- **断言**:
  - 给定: 50 × 252 fixture 加载后
  - 当: CLI 计算 labels
  - 那么:
    - labels DataFrame 行数 = 50 × 252
    - labels 列严格包含 `asset` / `date` / `label` (3 列,类型正确)
    - 对任一 asset,`label[t] == close[t+5] / close[t] - 1` (抽样验证 10 个非末尾日期)
    - 数据末尾 5 个日期的 `label` 为 NaN (或被评估时跳过,继承 v0.2.0 FR-0300 语义)
- **对应 EARS**: Story §2 AC-03 (labels 子条款)

### AC-5

AC-FR0100-05

- **WHEN** registry 保存
- **THEN** 系统 SHALL 按新契约写入 `save_factor_registry(specs, out_path: Path, fmt=...)` (新签名,`out_path` 是完整文件路径,**不**是目录),创建 `out_path.parent` if missing,返回 `out_path`
- **断言**:
  - 给定: `selected_specs` (5 个 FactorSpec)
  - 当: `save_factor_registry(selected_specs, out_path=tmp_path / "registry" / "factors.yaml", fmt="yaml")` 调用
  - 那么:
    - `out_path` 文件存在 (非目录),`out_path.stat().st_size > 0`
    - `out_path` 后缀为 `.yaml`
    - `out_path.parent` 目录被自动创建 (即使原先不存在)
    - 返回值 = `out_path` (与传入参数相同)
    - 旧契约 `save_factor_registry(specs, out_dir: Path)` (传目录) 仍可被旧测试调用,但**新代码路径**不传目录
  - 给定: `save_factor_registry(selected_specs, out_path=tmp_path / "registry" / "factors.json", fmt="json")` 调用
  - 那么:
    - `out_path` 后缀为 `.json`,文件存在,内容为 valid JSON
- **对应 EARS**: Story §2 AC-05

### AC-6

AC-FR0100-06

- **WHEN** `load_factor_registry(path)` 被传入文件路径
- **THEN** 系统 SHALL 正确打开文件 (非目录),解析 YAML/JSON,返回 `dict`;**不**把目录当文件
- **断言**:
  - 给得: `save_factor_registry(...)` 已生成 `factors.yaml`
  - 当: `load_factor_registry(registry_yaml_path)` 调用
  - 那么:
    - 返回 `dict` 含 `factor_template_version` / `total_candidates` / `factors` (继承 v0.2.0 FR-0600 schema)
    - `len(data["factors"]) == data["total_candidates"]`
  - 给定: 传入**目录**路径 (旧 API 残留用法)
  - 当: `load_factor_registry(registry_dir_path)` 调用
  - 那么: 抛 `IsADirectoryError` 或 `FactorRegistrySchemaError` 或 `NotADirectoryError` (**不**静默当文件打开;原 bug 已修)
- **对应 EARS**: Story §2 AC-05 (read-back 子条款)

### AC-7

AC-FR0100-07

- **WHEN** CLI 完整链路执行成功且精选因子 ≥ 10
- **THEN** 系统 SHALL 退出码 = **0**,stdout 含「枚举了 N 个候选因子」「精选 K 个因子」「registry 落盘到 <path>」,registry 文件被落盘到 `--registry-path` 指定路径
- **断言**:
  - 给定: 50 × 252 fixture 加载成功;候选数 ≥ 200
  - 当: `trader-off-mine-factors --config config.yaml --start 2022-01-01 --end 2022-12-31 --registry-path /tmp/test/factors.yaml` 执行
  - 那么:
    - 退出码 = 0
    - `/tmp/test/factors.yaml` 文件存在
    - `load_factor_registry(Path("/tmp/test/factors.yaml"))` 返回的 `total_candidates` ≥ 200
    - stdout 含 `枚举了 \d+ 个候选因子` (regex)
    - stdout 含 `精选 \d+ 个因子` (regex,K ≥ 10)
- **对应 EARS**: 任务描述 Exit code 0

### AC-8

AC-FR0100-08

- **WHEN** 精选因子 < 10 个
- **THEN** 系统 SHALL 退出码 = **3**,`logger.warning("fewer than 10 selected factors")`,registry 文件仍落盘(继承 v0.2.0 FR-0800 既有语义)
- **断言**:
  - 给定: 候选数 = 5 (人为构造,例如 fixture 数据范围过窄或 param_space 缩减)
  - 当: `trader-off-mine-factors --config config.yaml --top-k 30 ...` 执行
  - 那么:
    - 退出码 = 3
    - registry 文件仍**被**落盘 (即使 selected < 10,产物可用)
    - log 含 `fewer than 10 selected factors` (regex / loguru 验证)
    - stdout 含 `精选 5 个因子` (regex)
- **对应 EARS**: 任务描述 Exit code 3 (沿用 v0.2.0)

### AC-9

AC-FR0100-09

- **WHEN** config 文件不存在
- **THEN** 系统 SHALL 退出码 = **4**,stderr 含 `config file not found`
- **断言**:
  - 给定: `--config /tmp/nonexistent.yaml`,文件不存在
  - 当: CLI 执行
  - 那么:
    - 退出码 = 4
    - stderr (或 stdout) 含 `config file not found` 关键词 (case-insensitive)
- **对应 EARS**: 任务描述 Exit code 4 (沿用 v0.2.0)

### AC-10

AC-FR0100-10

- **WHEN** 所有候选因子的 `evaluate_factor` 抛异常(例如 schema 校验失败、compute_fn 返回类型错误、数据列缺失)
- **THEN** 系统 SHALL 记录到 stderr + loguru `logger.exception`,**不**中断遍历,最终退出码 = **5** (新增 = evaluation failure)
- **断言**:
  - 给定: 候选数 ≥ 200;monkeypatch `evaluate_factor` 使其对**所有** spec 抛 `RuntimeError("evaluate failed")`
  - 当: CLI 完整链路执行
  - 那么:
    - 退出码 = 5
    - loguru `logger.exception` 调用**至少** 1 次 (记录至少 1 个 spec 的失败原因)
    - **不**抛未捕获异常(所有 evaluate 异常被 CLI 内部捕获)
    - registry 文件**不**被落盘 (selected 为空,落盘无意义;**或**落空 registry 含 0 factors,**允许**两种行为中任一种,由实现选择;**不**强制)
  - 给定: 50% 候选 evaluate 成功,50% 失败
  - 那么:
    - 退出码 = 0 (有成功 evaluate → select → 走通)
    - loguru `logger.exception` 调用**至少** 1 次 (记录失败 specs)
- **对应 EARS**: 任务描述 Exit code 5 (新增)

---

<a id="ac-nfr-0100"></a>
## NFR-0100 函数级 lazy import — 沿用 v0.4.1 / v0.5.1 白名单 (`quantide.data.fetchers.tushare.*` + `quantide.data.models.calendar.calendar`)

### AC-1

AC-NFR0100-01

- **WHEN** 验证 `src/trader_off/factor_mining/cli.py` 模块顶层
- **THEN** 系统 SHALL 无 `import quantide` / `from quantide ...` 语句 (模块顶层零 quantide import)
- **断言**:
  - 给定: `src/trader_off/factor_mining/cli.py` 源文件
  - 当: `grep -rn "^import quantide\|^from quantide" src/trader_off/factor_mining/cli.py` 执行 (使用 `^` 锚定行首,过滤 import 行)
  - 那么: 无匹配 (grep 退出码 `1`,stdout 为空)。该断言覆盖模块顶部 import 块、`if TYPE_CHECKING` 块、模块级 docstring。

### AC-2

AC-NFR0100-02

- **WHEN** 验证 `cli.py` 业务符号白名单边界
- **THEN** 系统 SHALL **无** `quantide.service.*` / `quantide.portfolio.*` / `quantide.backtest.*` / `quantide.core.scheduler.*` / `quantide.data.models.daily_bars.*` / `quantide.data.fetchers.<非 tushare>.*` 的 import;白名单内**仅**允许 `quantide.data.fetchers.tushare.*` 与 `quantide.data.models.calendar.calendar`
- **断言**:
  - 给定: `cli.py` 源文件
  - 当: `grep -rnE "quantide\.(service|portfolio|backtest|core\.scheduler|models\.daily_bars|fetchers\.(?!tushare))" src/trader_off/factor_mining/cli.py` 执行 (Perl/PCRE negative lookahead)
  - 那么: 无匹配 (grep 退出码 `1`,stdout 为空)。本 spec 内 cli.py **不**直接 import quantide(经 `quantide_adapter` 间接),白名单约束作为回归保护存在;**不**放行 `Calendar` 类 / `FrameType` / `daily_bars` singleton / 其他子模块。

### AC-3

AC-NFR0100-03

- **WHEN** Python AST 解析 `cli.py`
- **THEN** 系统 SHALL 验证所有 `quantide` 导入节点的祖先链含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 quantide import
- **断言**:
  - 给定: `ast.parse(Path("src/trader_off/factor_mining/cli.py").read_text())` 后遍历 `ast.ImportFrom` / `ast.Import` 节点
  - 当: 对每个 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点,沿 `ast.walk` 反向追溯父节点(`ast.FunctionDef` / `ast.AsyncFunctionDef` / `ast.ClassDef` / `ast.If` 测试是否为 `TYPE_CHECKING`)
  - 那么: **所有** quantide import 节点的最近函数祖先存在,且**不**位于 `if TYPE_CHECKING` 块内或类体内。断言失败若任一 import 出现在模块顶层 / 类体 / TYPE_CHECKING 块。

### AC-4

AC-NFR0100-04

- **WHEN** 验证 `src/trader_off/data/quantide_adapter.py` 隔离持续
- **THEN** 系统 SHALL 模块顶层仍零 quantide import(继承 v0.4.1 NFR-0100);本 patch **不**修改 `quantide_adapter.py`,作为白名单边界封口点
- **断言**:
  - 给定: `src/trader_off/data/quantide_adapter.py` 源文件
  - 当: `grep -rn "^import quantide\|^from quantide" src/trader_off/data/quantide_adapter.py` 执行
  - 那么: 无匹配 (grep 退出码 `1`,stdout 为空)。quantide 导入**仅**出现在 `get_daily` / `_compute_real_trade_dates` 函数体内(继承 v0.4.1 AC-NFR0100-01)。

### AC-5

AC-NFR0100-05

- **WHEN** 验证 `src/trader_off/cli/` 目录的集成层隔离(本 patch **不**修改 `cli/sync_data.py`,仅回归检查)
- **THEN** 系统 SHALL `cli/__init__.py` / `cli/backtest.py` 仍无模块顶层 `import quantide` / `from quantide ...`;`cli/sync_data.py` 的 quantide import **仅**出现在函数体内(延续 v0.4.2 / v0.5.1 隔离承诺)
- **断言**:
  - 给定: `src/trader_off/cli/` 目录所有 `.py` 文件
  - 当: `grep -rn "^import quantide\|^from quantide" src/trader_off/cli/` 执行
  - 那么: **无**模块顶层 `^import quantide` / `^from quantide` 匹配(grep 退出码 `1`,stdout 为空);`sync_data.py` 函数体内 import 仍 ≥ 2 个 `from quantide` 匹配(回归 v0.5.1 AC-NFR0100-02)。
