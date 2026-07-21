---
date: 2026-07-21
spec: v0.4.1-001-real-tushare-integration
status: draft
---

# STR-0003: v0.4.1 patch — wire QuantideDataLoader to real Tushare + CN trading calendar

## 0. 原始输入
> v0.4.1 patch（一句话）：把 v0.4.0 留尾的 `QuantideDataLoader` 真正接通 Tushare 真数据 —— 通过 `quantide.data.fetchers.tushare.TushareFetcher`（含 `TUSHARE_TOKEN` 环境变量门控）做真实抓取，并用 `quantide.data.models.calendar.Calendar.get_frames_by_count()` 替换 `pandas.bdate_range` 的交易日近似；最后 3 支股票 × 60 交易日做一次 end-to-end smoke。

## 1. 用户与场景 (Who & Where)
- **Who**：量化研究员（继承 STR-0001/0002，单一开发者）。
- **Where**：本地 CLI（`pytest tests/smoke/test_real_tushare_smoke.py`）+ `BacktestRunner.run`；桌面/服务器，**无 UI**；token 经 `os.environ['TUSHARE_TOKEN']` 注入，不落盘。

## 2. 功能与价值 (What & Why)

### 2.1 功能描述 (What)
- **FR-0100（真 Tushare + 日历接通）**：在 `src/trader_off/data/quantide_adapter.py` 内：
  1. `QuantideDataLoader.__init__(token=None)`；缺省时懒读 `os.environ.get('TUSHARE_TOKEN')`，缺失抛 `RuntimeError`（不静默退化）。
  2. 函数级 lazy import 实例化 `TushareFetcher(token=...)`（NFR-0100 沿用）。
  3. 用 `fetcher.fetch_calendar(epoch)` + `Calendar.get_frames_by_count(end_date, count, FrameType.DAY)` 反推真实交易日，**替换** `pandas.bdate_range`。
  4. 调 `fetch_bars(dates)` 走原路径（兼容 v0.4.0 契约）。
- **FR-0200（end-to-end smoke）**：新增 `tests/smoke/test_real_tushare_smoke.py` —— 拉 3 支股票（`000001.SZ` / `600519.SH` / `000858.SZ`）× 60 交易日 → 落 v0.3.0 `DailyBarsStore` → `BacktestRunner.run(...)` → 断言 NAV 曲线非空。Token 缺失则 `pytest.skip`；CI 用 mock `TushareFetcher` 跑同一断言。

### 2.2 快乐路径 (Happy Path)
1. `export TUSHARE_TOKEN=xxx && pytest tests/smoke/test_real_tushare_smoke.py -v` → 3 stocks fetched → DailyBarsStore 落盘 → BacktestRunner → NAV 非空
2. CI（无 token）：同文件改用 mock TushareFetcher → 全绿

### 2.3 问题陈述与目标 (Why)
- **问题**：v0.4.0 `QuantideDataLoader` 只跑通函数级 mock —— (a) 未实例化 `TushareFetcher`，(b) `pandas.bdate_range` 不识别 CN 假期。
- **北极星**：用户本地用真 token 一次跑通 3 stocks × 60 日 end-to-end，NAV 非空即视为"真数据通路打通"。

### 2.4 功能需求（EARS 格式）
| 编号 | EARS 句式 | 说明 |
| :--- | :-------- | :--- |
| AC-01 | `WHEN QuantideDataLoader(token=None) AND TUSHARE_TOKEN 未设置, THE 系统 SHALL 抛 RuntimeError 且不发起任何网络 IO` | Token 门控 |
| AC-02 | `WHEN TUSHARE_TOKEN 已设置, THE 系统 SHALL 实例化 TushareFetcher 并用 fetch_calendar + Calendar.get_frames_by_count(end_date, count, DAY) 反推真实交易日` | 日历接通 |
| AC-03 | `WHILE 反推交易日, THE 系统 SHALL 不再调用 pandas.bdate_range` | 替换约束 |
| AC-04 | `WHEN 真实交易日列表就绪, THE 系统 SHALL 调用 fetch_bars(dates) 并返回 polars OHLCV DataFrame` | 沿用契约 |
| AC-05 | `WHEN smoke test 启动 AND env TUSHARE_TOKEN 缺失, THE 系统 SHALL pytest.skip 且 CI 用 mock TushareFetcher 走同一断言` | CI 兼容 |
| AC-06 | `WHEN smoke test 启动 AND env TUSHARE_TOKEN 存在, THE 系统 SHALL 拉 3 stocks × 60 交易日 → 写 DailyBarsStore → BacktestRunner.run → NAV 非空` | E2E 核心 |

## 3. 完整性 (Completeness)

### 3.1 Adopt / Avoid
| 类型 | 来源 | 内容 | 理由 |
| :--- | :--- | :--- | :--- |
| Adopt | `TushareFetcher`（已读） | `__init__(token=...)` + `fetch_calendar(epoch)` | FR-0100 真通路 |
| Adopt | `Calendar.get_frames_by_count(date, count, FrameType.DAY)` | 反推 `count` 个真实交易日（CN 假期剔除） | FR-0100 日历精度 |
| Avoid | v0.4.0 `pandas.bdate_range` 路径 | 移除 `_compute_trade_dates` 的 bdate_range 调用 | 防双路径漂移 |

### 3.2 Out-of-Scope
- [ ] 不做 `trader_off data sync` CLI 命令
- [ ] 不接入真实 scheduler 触发数据同步
- [ ] 不做 calendar 可视化 / 前端展示
- [ ] 不做 token 管理（刷新 / 轮换 / 加密落盘）；只读 `os.environ`

### 3.3 约束条件
- **技术**：Python ≥ 3.13；quantide 通过 git URL 依赖；TushareFetcher / Calendar import 仍函数级 lazy（NFR-0100 沿用）。
- **安全**：Token **永不**落盘 —— 测试输出禁止 echo token；smoke 落盘产物不含 token；`.env*` gitignore。
- **组织**：patch ≤ 1 issue；smoke 输出落 `tests/smoke/output/`（gitignore）。

## 4. 必要性与冲突 (Necessity & Conflict)

### 4.1 必要性
| FR | 论证 |
| -- | ---- |
| FR-0100 | **必要** —— v0.4.0 spec FR-0100 行 63 明文"不实例化 TushareFetcher / 不用 TUSHARE_TOKEN / 不发网络 IO"；v0.4.1 兑现 |
| FR-0200 | **必要** —— 单测仅 mock，"真数据通路"未经验证；smoke test 补完 |

### 4.2 冲突
| 既有决策 | 冲突 | 说明 |
| -------- | :--: | ---- |
| **v0.4.0 NFR-0100（lazy import + 业务符号白名单）** | ⚠️ 局部 | 白名单放行 `data.fetchers.tushare.*`；新增 `data.models.calendar.*` 同属 `data.*`，白名单内零冲突；spec 需显式声明 `TushareFetcher.__init__(token)` 属行 63 反向补充 |
| **v0.4.0 FR-0100 行 63（不实例化/不用 token/不发网络）** | ✅ 继承覆盖 | v0.4.1 显式反转；该条款改 Valid=❌ + 备注"v0.4.1 起执行真接入" |
| **v0.3.0 FR-1/FR-2 + v0.3.0/0.3.1 隔离承诺** | ❌ | FR-0200 复用 `BacktestRunner.run()`；本 patch 仅 `quantide_adapter.py` 内新增 import，不污染其他模块 |

**结论**：**Go**；唯一需在 v0.4.1 spec.md 显式记录"v0.4.0 FR-0100 行 63 反转 + NFR-0100 白名单延伸至 `quantide.data.models.calendar.*`"，无新增隔离条款。Human 决策点：行 63 反转认同。

## 5. 方案疑议（A/B Advisory，非决策）
- **无 A/B 疑议**。v0.4.1 是 v0.4.0 留尾兑现，路径单一。TushareFetcher 实例化 vs 模块级 `fetch_bars` 二选一已在 v0.4.0 spec 锁定为后者，本 patch 不重开。
- Agent 不替用户决策 token 注入方式（env vs CLI flag）；用户已确认 env 模式。

## 6. 分流结论与门禁 (Gate)
- **分流结论**：**Go**（Agent 建议）
- **理由**：FR-0100 兑现 v0.4.0 留尾，路径明确（lazy import + Calendar + TushareFetcher 均为 quantide 已有 API）；FR-0200 复用 v0.3.0 BacktestRunner，零下游风险。
- **Human 确认**（仅决策点）：
  - [ ] 分流结论认同（**Go**）
  - [ ] v0.4.0 FR-0100 行 63 反转 + NFR-0100 白名单延伸（calendar）认同
  - [ ] Out-of-Scope 认同
- **Backlog**：**Go → 进入 M-FOUND**

## 7. 可追溯种子 (Traceability)
- **Story ID**：`STR-0003` · **创建时间**：`2026-07-21T00:00:00Z`
- **Spec ID**：`v0.4.1-001-real-tushare-integration` · **关联 Issue**：`#待创建`
- **继承基线**：v0.4.0 STR + spec FR-0100 / NFR-0100（局部反转）；v0.3.0 STR-0001
*—— 本故事由 M-STORY Agent 于 2026-07-21 生成；经 Human 确认后：Go → 进入 M-FOUND。*
