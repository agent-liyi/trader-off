---
date: 2026-07-23
spec: v0.7.2-001-qmt-p1-wrappers
status: draft
---
# STR-0010: v0.7.2 — qmt-gateway P1 包装补全（分钟线下载 + 行情/竞价状态）

## 0. 原始输入
> Extend QmtGatewayBroker (v0.6.0/v0.7.1) to wrap qmt-gateway P1 APIs: minutes data download + quote/auction status.

## 1. 用户与场景
- 研究员 / LLM agent，程序化调用 `QmtGatewayBroker`（非 UI）；单机单进程，中频按需；经局域网到 Windows qmt-gateway（默认 :5800）。
- 前置：v0.6.0 8 交易方法 + v0.7.1 5 连接/查询方法已就位（共 13 方法）。

## 2. 功能与价值 (What & Why)
v0.7.1 故事明确将"分钟线下载、集合竞价"列为 Out-of-Scope；本版补 4 方法，闭环"探活→查标的→拉历史分钟线→查行情/竞价就绪→下单"。
- **快乐路径**：`get_connection_status()` 在线 → `get_quote_status()` 行情就绪 → `download_minutes(dates)` 起 job → `get_minutes_job(job_id)` 轮询完成 → 下单。
- **FR-0100**：`src/trader_off/broker/qmt_gateway.py` 新增 4 方法，复用既有 `_get`/`_post`。**NFR-0100**：继承 function-scope 懒加载；无新依赖。

### EARS
| # | 句式 |
|---|---|
| AC-01 | `WHEN 调用 get_minutes_job(job_id), THE 系统 SHALL GET /minutes_job/{job_id} 返回下载进度 dict` |
| AC-02 | `WHEN 调用 download_minutes(dates), THE 系统 SHALL POST /download_minutes?dates= 返回 {job_id}` |
| AC-03 | `WHEN 调用 get_quote_status(), THE 系统 SHALL GET /quote_status 返回 WebSocket 行情订阅状态 dict` |
| AC-04 | `WHEN 调用 get_auction_status(), THE 系统 SHALL GET /auction_status 返回集合竞价撮合状态 dict` |

## 3. 竞品与边界
- **Adopt**：复用 v0.6.0 `_get`/`_post`/`_request` 错误处理（非 200 抛 RuntimeError）与签名风格。
- **Avoid / Out-of-Scope**：不改既有 13 方法、不引新依赖、不做缓存/重试；不做系统管理、API key 管理（P2 → v0.7.3）。
- **约束**：Python ≥3.13；`download_minutes` 为异步 job，broker 仅返 job_id，轮询策略交调用方。

## 4. 风险与假设
| # | 假设 / 风险 | 验证 / 应对 |
|---|---|---|
| 1 | 假设：4 端点签名/返回结构与 qmt-gateway 文档一致 | M-DEV 真机对照 |
| 2 | 风险：`download_minutes` 大 dates 列表可能超长 URL（低） | 透传 query；文档标注建议分批 |
| 3 | 风险：job 轮询无超时上限致 agent 挂起（低） | broker 不内置轮询，调用方自控 |

## 5. 必要性与冲突
- **已实现？** 否——`qmt_gateway.py` 现 13 方法（grep 无 minutes/quote_status/auction），v0.7.1 story §3 显式将其划入 Out-of-Scope 待本版承接。
- **相抵触？** 否——补齐非替换，与 v0.6.0 / v0.7.1 互补。**结论**：新建。

## 6. 方案疑议 + 门禁
- **疑议**：无。4 端点为网关既定 P1，无更优替代。
- **分流结论**：Go（Agent 建议）——增量小、复用 helper、风险可控。
- **Human 确认**：[ ] 分流结论认同；[ ] §6 无异议免裁。**Backlog 登记**：Go → 进入 M-FOUND。
- **追溯**：`STR-0010` · `2026-07-23T00:00:00Z` · spec `v0.7.2-001-qmt-p1-wrappers` · Issue `#待创建`
*—— M-STORY Agent 于 2026-07-23 生成；待 Human 确认 Go 后进入 M-FOUND。*
