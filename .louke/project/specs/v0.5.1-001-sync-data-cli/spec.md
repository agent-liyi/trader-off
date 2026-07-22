---
status: draft
locked: false
---
# v0.5.1 — `trader-off sync-data` CLI (QuantideDataLoader 包装) — Spec

- **Spec ID**: v0.5.1-001-sync-data-cli
- **Created**: 2026-07-22
- **Status**: Draft
- **关联 story**: `.louke/project/specs/v0.5.1-001-sync-data-cli/story.md` (STR-0005)
- **继承基线**:
  - v0.4.1 FR-0100 `QuantideDataLoader.get_daily(asset, end_date, count)` 真 Tushare 通路 (本 spec **不**改签名)
  - v0.4.1 NFR-0100 函数级 lazy import 白名单 `quantide.data.fetchers.tushare.*` (本 spec 延伸至 `cli/sync_data.py`,并新增 `quantide.data.models.calendar.calendar` singleton)
  - v0.4.2 `[project.scripts]` PEP 621 dash-prefix 注册模式 (本 spec 复用 `trader-off-*` 风格)
  - v0.3.0 `DailyBarsStore` 年分区 parquet 契约 (`year=YYYY/part-N.parquet`,schema `{date, asset, ohlc struct, volume, adj_factor}`)

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。验收标准放在 `acceptance.md` 中。测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md` 作为输入。

> **北极星目标**: `export TUSHARE_TOKEN=xxx && trader-off-sync-data --universe universe/a_share_top50.csv --start 2024-01-01 --end 2024-12-31` 一次跑通,产出 v0.3.0 `DailyBarsStore` 全量 OHLCV + `.quantide/calendar/` 日历,供 v0.5.0 `PaperBroker` 在缺数据时一键补齐。`--dry-run` 仅打印计划不落盘。

> **关键约束 (继承 Story §3.2)**:
> - patch ≤ 1 issue;本 spec 拆 FR-0100 / NFR-0100 两条便于追踪
> - TUSHARE_TOKEN 仍经 `os.environ` 注入 (继承 v0.4.1);CLI 输出 / stderr / 日志**禁止** echo token 值
> - 顺序 per-asset 同步 (单进程、串行);**不做** resume / 并行 / scheduler / universe 自动发现 / 数据质量校验
> - CLI exit codes: **0** success / **2** argparse / **4** config error / **5** partial asset failure (≥1 asset 失败但其他成功)
> - 不修改 `QuantideDataLoader` / `get_daily` 签名 (v0.4.1 锁定)

## User Stories

### US-0010

story: 作为一名量化研究员,我希望在本地持有 `TUSHARE_TOKEN` 时,通过 `trader-off-sync-data --universe <CSV/parquet 含 asset 列> --start YYYY-MM-DD --end YYYY-MM-DD [--store-path PATH] [--dry-run]` 一次命令,把指定 universe 的 A 股 OHLCV 落 v0.3.0 `DailyBarsStore`(年分区 parquet `year=YYYY/part-N.parquet`)+ 交易日历落 `.quantide/calendar/calendar.parquet`,从而使 v0.5.0 `PaperBroker` 在缺数据时一键补齐,无需手写 Python 脚本。
priority: P0

## Usage Scenarios

### scenario-0010 happy path (full sync)

1. 开发者设置 `export TUSHARE_TOKEN=xxx`(token 经 `os.environ` 注入,不落盘)。
2. 开发者执行 `trader-off-sync-data --universe universe/a_share_top50.csv --start 2024-01-01 --end 2024-12-31`。
3. CLI 读 universe → 函数级 lazy import `QuantideDataLoader(token=os.environ['TUSHARE_TOKEN'])` → 函数级 lazy import `quantide.data.fetchers.tushare.fetch_calendar` + `quantide.data.models.calendar.calendar`。
4. `fetch_calendar(start - timedelta(days=30))` → `cal_df`;`calendar._path = Path(".quantide/calendar/calendar.parquet"); calendar.save(cal_df)`(落 `.quantide/calendar/`)。
5. 顺序遍历每 asset:`get_daily(asset, end_date=end, count=trading_days_in_range(start, end))`(v0.4.1 公开契约)→ 过滤 `date >= start` → 写 `{store_path}/year=YYYY/part-N.parquet`(默认 `.quantide/bars/`,polars `partition_by` 按 `date.dt.year()`)。
6. 退出码 0;stderr 仅记录进度,无 token 字面值。

### scenario-0020 dry-run (仅打印计划)

1. 同 scenario-0010 + `--dry-run` 启用。
2. CLI 仅 `logger.info("[dry-run] asset=... start=... end=... → target=...")` 打印每个 asset 的计划目标路径。
3. **不**发起任何网络 IO (无 `fetch_calendar` / `get_daily` 调用)、**不**写任何 parquet / 日历文件、`calendar.save` **不**调用。
4. 退出码 0。

### scenario-0030 partial asset failure (继续 + 退出码 5)

1. 同 scenario-0010;universe 含 N 个 asset;其中 K 个 (1 ≤ K < N) 资产同步失败 (网络异常 / Tushare 返回空 / 数据缺失)。
2. 失败的 asset → `logger.exception(...)` + stderr 打印错误信息,继续下一个 asset(不中断)。
3. 成功的 asset → 正常落盘。
4. 最终退出码 5 (`partial failure`);loguru `logger.exception` 调用 ≥ K 次。

### scenario-0040 argparse / config error

1. `trader-off-sync-data` 无 args → argparse 报 "the following arguments are required: --universe, --start, --end" → 退出码 2。
2. `trader-off-sync-data --start invalid-date --end 2024-12-31` → argparse / 日期解析失败 → 退出码 2。
3. `TUSHARE_TOKEN` 未设置 → stderr `"TUSHARE_TOKEN environment variable is required; set it before running sync-data"` → 退出码 4。
4. `--universe` 路径不存在 / 读取失败 / 无 `asset` 列 → 退出码 4。
5. `--start > --end` → 退出码 4。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头,紧接三列元数据表 (Valid / Testable / Decided),再写需求描述;FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100** 一条 P0 FR + **NFR-0100** 一条 NFR;起始 100 间隔 (patch ≤ 1 issue 范围,沿用 v0.4.2 编号策略)。后续 review round 插入 10 间隔位。
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
### FR-0100 `trader-off sync-data` CLI — 封装 `QuantideDataLoader.get_daily()` + 落 `DailyBarsStore` 年分区 parquet + 写 `.quantide/calendar/`

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **新增文件**: `src/trader_off/cli/sync_data.py` (新建,导出 `main(argv=None)`,`if __name__ == "__main__": sys.exit(main())`)。
- **pyproject.toml 注册** (PEP 621 dash-prefix,紧跟 v0.4.2 已注册 entry points 之后,新增 1 行):
  ```toml
  trader-off-sync-data = "trader_off.cli.sync_data:main"
  ```
- **CLI 参数** (argparse,全部 `--kebab-case` 风格,与 v0.4.2 `cli/backtest.py` 一致):
  - `--universe PATH` (required,CSV 或 parquet,文件含 `asset` 列;**不**支持 stdin / glob)
  - `--start DATE` (required,ISO `YYYY-MM-DD`)
  - `--end DATE` (required,ISO `YYYY-MM-DD`)
  - `--store-path PATH` (default `.quantide/bars/`,与 v0.3.0 `daily_bars.connect` 默认对齐)
  - `--dry-run` (flag,启用后仅打印计划,不调网络不落盘)
- **CLI 行为** (按顺序):
  1. **argparse 解析** (退出码 2):args 缺失 / 日期格式错误 → argparse 报 → 退出码 2。
  2. **Token 门控** (退出码 4):读 `os.environ.get('TUSHARE_TOKEN')`;缺失 → `logger.error("TUSHARE_TOKEN environment variable is required; set it before running sync-data")` + stderr 打印 → 退出码 4,**不**发起任何网络 IO,**不** lazy import `quantide.*`。
  3. **Universe 解析** (退出码 4):
     - `--universe` 路径**不**存在 → 退出码 4。
     - CSV 用 `pl.read_csv(path)` / parquet 用 `pl.read_parquet(path)`;读取失败 → 退出码 4。
     - 读取结果**无** `asset` 列 → 退出码 4。
  4. **日期校验** (退出码 4):`start > end` → 退出码 4。
  5. **Calendar 写入 (一次性,函数级 lazy import)**:
     - `from quantide.data.fetchers.tushare import fetch_calendar` (NFR-0100 白名单内,继承 v0.4.1)
     - `from quantide.data.models.calendar import calendar` (NFR-0100 本 spec 新增放行)
     - `cal_df = fetch_calendar(start - timedelta(days=30))` (留 30 天 buffer 以确保覆盖 start 之前的交易日)
     - `Path(".quantide/calendar").mkdir(parents=True, exist_ok=True)`;`calendar._path = Path(".quantide/calendar/calendar.parquet")`;`calendar.save(cal_df)` → 写 `.quantide/calendar/calendar.parquet`(schema 索引 `date`,字段 `is_open` / `prev`)
     - **不**调 `calendar.load(...)` (避免副作用);直接 `save` 以保留 CLI 控制权
  6. **OHLCV 写入 (per asset,顺序遍历)**:
     - 函数级 lazy import `from trader_off.data.quantide_adapter import QuantideDataLoader` (项目内模块,**非** quantide,不在 NFR-0100 白名单约束内,但同样函数级 lazy import 避免模块顶层副作用)
     - `loader = QuantideDataLoader(token=os.environ['TUSHARE_TOKEN'])` (v0.4.1 token 契约:env 优先,**不**显式传 token)
     - 计算 `count = trading_days_in_range(start, end)`:从 `cal_df` 索引中过滤 `is_open == 1` 且 `start <= date <= end`,取 `len()`(或 `(end - start).days * 1.5` 上界兜底)
     - **不** `--dry-run`:对每个 asset:
       - `df = await loader.get_daily(asset, end_date=end, count=count)` (v0.4.1 公开契约,**不**修改签名)
       - `df = df.filter(pl.col("date") >= start)` (裁剪到用户请求窗口)
       - `df.write_parquet(store_path, partition_by=pl.col("date").dt.year())` → 落 `{store_path}/year=YYYY/part-N.parquet`
     - **--dry-run**:仅 `logger.info("[dry-run] asset={a} start={s} end={e} → {store_path}/year={y}/...")`,**不**调 `fetch_calendar` / `get_daily` / `calendar.save`,**不** lazy import `quantide.*`
     - **失败处理**:单 asset 异常 (`get_daily` 抛异常 / 返回空 DataFrame 但 schema 缺失) → `logger.exception(f"Failed to sync {asset}: {e}")` + stderr 打印;继续下一个 asset
  7. **退出码**:
     - **0** = 全部 asset 成功 (含 `--dry-run`)
     - **2** = argparse 失败 (参数缺失 / 日期格式错误)
     - **4** = config error (token 缺失 / universe 路径错 / 无 `asset` 列 / 日期校验失败)
     - **5** = partial failure (≥1 asset 失败但其他成功)
- **数据契约 (落盘格式)**:
  - **OHLCV parquet** (`{store_path}/year=YYYY/part-N.parquet`):
    - 分区文件夹名格式 `year=YYYY` (与 v0.3.0 fixture `partition_key_year=2022/part-0.parquet` 同结构,后续 `daily_bars.connect(store_path, ...)` 可正常读取)
    - schema 严格为 `{date: Date, asset: Utf8, open: Float64, high: Float64, low: Float64, close: Float64, volume: Float64, adj_factor: Float64}` (与 `QuantideDataLoader.OHLCV_SCHEMA` 一致)
    - 列顺序固定 (按 schema 字典序)
  - **Calendar parquet** (`.quantide/calendar/calendar.parquet`):
    - 由 `quantide.data.models.calendar.calendar.save(cal_df)` 写入
    - pandas DataFrame 索引为 `date`,字段 `is_open` / `prev`
- **签名兼容**: `QuantideDataLoader` 类与 `get_daily(asset, end_date, count)` 方法签名零修改 (继承 v0.4.1);CLI 内部适配 (start → count + filter)
- **Token 安全**: CLI 输出 / stderr / 日志**禁止** echo token 值 (继承 v0.4.1 NFR-0100 / Story §3.2 安全条款);traceback 不打印 token
- **out-of-scope** (继承 Story §3.2,显式**不**做):
  - resume / 增量同步 (永远全量覆盖)
  - 并行下载 (顺序 per asset,单进程)
  - cron / scheduler 自动触发 (仅手动 CLI)
  - universe 自动发现 (需显式 `--universe` 路径)
  - calendar 可视化 / 数据质量校验报告 (v0.5.2+)
  - 改 `QuantideDataLoader` / `get_daily` 签名 / 接口 (v0.4.1 锁定)
  - `quantide.data.models.daily_bars.daily_bars` singleton 直接调用 (NFR-0100 白名单**不**放行,OHLCV 改用 polars `write_parquet` + `partition_by` 直接写入年分区文件)

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR,此处省略。

---

<a id="nfr-0100"></a>
### NFR-0100 函数级 lazy import — 白名单延伸至 `cli/sync_data.py` (含 `quantide.data.models.calendar.calendar`)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **隔离承诺 (v0.4.1 / v0.5.0 白名单延伸,本 spec 扩 1 项)**: `src/trader_off/cli/sync_data.py` 模块顶层(含 `import` 块、`from ... import` 块、`if TYPE_CHECKING` 块、模块级 docstring 示例代码、`__all__` 列表)**不**出现 `import quantide` 或 `from quantide ...` 语句。
- 所有 `quantide` 导入必须位于 `def` / `async def` 函数体内;导入时机为首次调用 (如 `main` 函数体内 `from quantide.data.fetchers.tushare import fetch_calendar` + `from quantide.data.models.calendar import calendar`)。
- **业务符号白名单 (本 spec 延伸)**:
  - **允许** import `quantide.data.fetchers.tushare.*` (继承 v0.4.0 / v0.4.1,含 `TushareFetcher` / `fetch_calendar` / `fetch_bars` 等;**不**实际 import,仅白名单允许)
  - **新增放行** `quantide.data.models.calendar.calendar` (本 spec 独有,因 CLI 需显式写 calendar 到 `.quantide/calendar/`;`calendar` 是模块级 singleton,只能 `from quantide.data.models.calendar import calendar`;**不**放行 `Calendar` 类 / `FrameType` / 其他符号)
  - **禁止** import `quantide.service.*` / `quantide.portfolio.*` / `quantide.backtest.*` / `quantide.core.scheduler.*` / `quantide.data.models.daily_bars.*` / `quantide.data.fetchers.<非 tushare>.*` (白名单外)
- **项目内模块 import** (非 quantide,本 NFR 不约束,但建议同样函数级 lazy): `from trader_off.data.quantide_adapter import QuantideDataLoader` (项目内模块,NFR-0100 仅约束 quantide import)
- **验证 1 (模块顶层)**: `grep -rn "^import quantide\|^from quantide" src/trader_off/cli/sync_data.py` 应无匹配
- **验证 2 (非白名单业务符号)**: `grep -rnE "quantide\.(service|portfolio|backtest|core\.scheduler|models\.daily_bars|fetchers\.(?!tushare))" src/trader_off/cli/sync_data.py` 应无匹配 (Perl/PCRE negative lookahead,确保白名单边界严格)
- **验证 3 (白名单内 import 存在性)**: `grep -rn "from quantide" src/trader_off/cli/sync_data.py` 应至少 2 个匹配,内容分别含 `from quantide.data.fetchers.tushare import` 与 `from quantide.data.models.calendar import calendar`
- **验证 4 (AST 校验)**: Python AST 解析(`ast.parse` + 遍历 `ast.ImportFrom` / `ast.Import`)`sync_data.py`,所有 `module == "quantide"` 或 `module.startswith("quantide.")` 的导入节点的祖先链必须含 `FunctionDef` / `AsyncFunctionDef`,无模块顶层 / 类体 / `if TYPE_CHECKING` 块的 import
- **验证 5 (cli/ 目录隔离)**: `grep -rn "^import quantide\|^from quantide" src/trader_off/cli/` 除 `sync_data.py` 函数体内 import 外应无其他模块顶层匹配(即 `cli/__init__.py` / `cli/backtest.py` 仍零 quantide 顶层 import,延续 v0.4.2 隔离承诺)

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|
| 0 (Story M-STORY) | Story §6 Human 确认 | 分流结论 Go / NFR-0100 白名单延伸至 cli/sync_data.py / Out-of-Scope 认同 (M-FOUND 已通过) | ✅ |
| 0 (M-SPEC) | Story §2 vs Task description 白名单差异 | Story §2 称"零冲突"(仅复用 `data.fetchers.tushare.*`);Task description 明确放行 `quantide.data.models.calendar.calendar`。**决策**: 采用 Task description 显式白名单 (`data.fetchers.tushare.*` + `models.calendar.calendar`),因 CLI 需显式调 `calendar.save()` 写 `.quantide/calendar/`;`daily_bars` singleton **不放行**,OHLCV 落盘改用直接 polars `write_parquet` + `partition_by` 写入年分区文件(沿用 DailyBarsStore schema 与 `year=YYYY/part-N.parquet` 命名),后续 `daily_bars.connect(store_path, ...)` 可正常读取 | ✅ |
| 0 (M-SPEC) | Story §2 "get_daily(asset, start, end)" vs 实际签名 `(asset, end_date, count)` | Story §2 行 22 描述 `loader.get_daily(asset, start, end)` 与 v0.4.1 锁定签名 `(asset, end_date, count)` 不一致。**决策**: CLI 沿用 v0.4.1 公开契约 `get_daily(asset, end_date, count)`,内部计算 `count = trading_days_in_range(start, end)` + 调 `get_daily` 后过滤 `date >= start`,**不**扩展 `get_daily` 签名(v0.4.1 锁定)。Spec FR-0100 行为条款 6 记录此决策 | ✅ |
| 0 (M-SPEC) | 退出码 5 (partial asset failure) | Story AC-05 提"最后以非零退出码退出",未指定具体码;Task description 列出 0/2/4 三档。**决策**: 新增退出码 5 = partial failure (≥1 asset 失败但其他成功),与 v0.4.2 `cli/backtest.py` 退出码 5 (engine failure) 同号但语义不同 (此处为 partial asset failure);`main()` 内部维护失败计数器,≥1 则退出码 5 | ✅ |
| 0 (M-SPEC) | per-asset 失败判定 | `loader.get_daily` 失败行为 (v0.4.1 AC-FR0100-06):异常时返回**空 DataFrame**(schema 正确)而非向上抛。**决策**: CLI 判定失败的策略 = `df.height == 0` (空返回即视为失败,记录 + 退出码 5);非空但 schema 缺失 → 视为异常,`logger.exception` + 退出码 5 | ✅ |
| 0 (M-SPEC) | `--start` 到 `--end` 跨多年场景 | `--start 2022-01-01 --end 2024-12-31` 跨 3 年 → `count` 较大,`fetch_calendar` 窗口需足够覆盖。**决策**: `fetch_calendar(start - timedelta(days=30))` (30 天 buffer 即可,因 `count` 由 cal_df 计算,不依赖 buffer);OHLCV 落盘 polars `partition_by=pl.col("date").dt.year()` 自动按年分目录,无需 CLI 手动分年 | ✅ |
