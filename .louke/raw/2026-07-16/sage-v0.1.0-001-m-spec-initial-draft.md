---
date: 2026-07-16
session: sage-v0.1.0-001-m-spec-initial-draft
agents: [Sage]
spec: v0.1.0-001-lgbm-asset-pricing
status: resolved
related_issues: []
supersedes: []
---

## Topic

执行 M-SPEC 阶段 Step 1（首轮提问）+ Step 2（生成 spec.md / acceptance.md 草稿）。

## Decision

### millionaire 框架 API 调研结果（已核实）

- 策略基类：`quantide.core.strategy.BaseStrategy` ✅ 与 story.md 一致
- Broker 接口：`quantide.service.base_broker.Broker`（包含 buy/sell/buy_amount/sell_amount/trade_target_pct）
- FrameType：`quantide.core.enums.FrameType`，DAY = "1d"
- 生命周期：`init` → `on_start` → `on_day_open` / `on_bar` / `on_day_close` → `on_stop`，全部 async
- 数据助手：`quantide.data.helper.train_test_split`（时间序列切分）、`qfq_adjustment` / `hfq_adjustment`
- Runner：通过 BacktestRunner 注入 broker + strategy（具体在 `quantide.core.runtime` 中）
- 框架状态：millionaire 当前仍在 architectural refactoring，但 strategy.py / base_broker.py / enums.py / helper.py API 已稳定可依赖

### Round 1 用户问答（6 条）

- 特征工程：MVP 最小集（动量/波动率/成交量约 15 个指标）
- 时序切分：滚动 walk-forward（每年滚动，train=过去 3 年）
- 交易规则：Long-only Top 20 等权
- 阈值：学术参考线（IC>0.02, Rank IC>0.03，软目标）
- 预测触发：**on_day_open**（用户回答，与 story.md 中 on_day_close 不一致）
- 分层回测：需要 5 层回测

### story.md 纠错记录

| 项目 | story.md | spec.md | 原因 |
|---|---|---|---|
| 预测触发回调 | on_day_close | on_day_open | 用户明确选择，语义等价（基于昨日收盘数据），但在 init 时预计算特征 |
| 特征工程 | 仅列三类 | 15 个具体指标 | 提问后明确范围 |
| 交易规则 | top/bottom 分位数 | Long-only Top 20 | 提问后明确 |

### 生成产物

- `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/spec.md`（422 行，22 个 FR/NFR）
- `.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/acceptance.md`（510 行，73 条 AC）
- 提交：`5ac1fb7 spec: initial draft (Sage Step 1+2)` 已推送到 `releases/v0.1.0`

### 编号约定

- FR 起始 FR-0100，步长 100：FR-0100、FR-0200 … FR-1500（共 15 个 FR）
- NFR 起始 NFR-0100，步长 100：NFR-0100 … NFR-0700（共 7 个 NFR）
- 后续 review 插入按 10 步长（FR-0110 在 FR-0100 和 FR-0200 之间）
- AC 编号 AC-1, AC-2...，每个 FR 内部从 1 起递增

## Tried but abandoned

- ❌ 在 spec.md 中写测试用例 → 违反职责切分（spec 只写 FR/NFR 描述，测试属于 test-plan）
- ❌ 在 acceptance.md 中用 `### AC-1 (...)` 带后缀格式 → 违反 Lex `verify-acceptance` 的纯标题要求
- ❌ 用 prose 而非标题/表格组织 FR → 违反模板格式约定

## Open questions (for next round)

- 用户是否同意 on_day_open 与 story.md 的不一致？（已记录于 Decision Log，但需要在 IDE review 时确认）
- IC/Rank IC 阈值为软目标但需要在 metadata.json 中记录「是否通过」标志（已在 NFR-0200 AC-3 中定义）
- walk-forward 切分是否需要 CLI 参数来覆盖默认 3 年窗口（已在 FR-0600 中设计为隐式）
- `trader-off` CLI 入口是否需要遵循 millionaire 的 `quantide` CLI 风格？还是独立 typer/click？（保持中立，让 Archer 决定）
- 数据来源：默认依赖 millionaire 的 `quantide.data.fetchers`，但具体哪个 fetcher 用于 A 股日线（fetcher 是 tushare / akshare / qmt 等）需要后续在 architecture.md 阶段由 Prism 决定
