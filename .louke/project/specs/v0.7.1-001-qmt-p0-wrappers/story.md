---
date: 2026-07-23
spec: v0.7.1-001-qmt-p0-wrappers
status: draft
---
# STR-0009: v0.7.1 — qmt-gateway P0 包装补全（连接管理 + 股票查询）

## 0. 原始输入
> Extend QmtGatewayBroker (v0.6.0) to wrap qmt-gateway P0 APIs: connection management + stock search.

## 1. 用户与场景
- 研究员 / LLM agent，程序化调用 `QmtGatewayBroker` 方法（非 UI）；单机单进程，中频按需；经局域网到 Windows qmt-gateway（默认 :5800）。

## 2. 功能与价值 (What & Why)
v0.6.0 的 QmtGatewayBroker 仅包装 8 个交易端点（asset/positions/orders/trades/buy/sell/cancel/principal），缺连接探活与标的检索，agent 无法交易前确认在线、也难按名/符号查标的。本版补 5 方法，闭环"探活→查标的→下单"。
- **快乐路径**：`get_connection_status()` 确认在线 → `search_stocks("平安")` 取候选 → `get_stock_info(symbol)` 取详情下单。
- **FR-0100**：`src/trader_off/broker/qmt_gateway.py` 新增 5 方法，复用既有 `_get`/`_post`。**NFR-0100**：继承 function-scope 懒加载；httpx 已由 v0.6.0 引入，无新依赖。

### EARS
| # | 句式 |
|---|---|
| AC-01 | `WHEN 调用 get_connection_status(), THE 系统 SHALL GET /connection_status 返回 {"connected":bool}` |
| AC-02 | `WHEN 调用 restart_qmt(password), THE 系统 SHALL POST /restart_qmt?password= 返回重启结果` |
| AC-03 | `WHEN 调用 search_stocks(q), THE 系统 SHALL GET /search_stocks?q= 返回 list[{symbol,name,market}]` |
| AC-04 | `WHEN 调用 get_stock_info(symbol), THE 系统 SHALL GET /stock_info?symbol= 返回详情 dict` |
| AC-05 | `WHEN 调用 get_all_stocks(), THE 系统 SHALL GET /all_stocks 返回全部标的列表` |

## 3. 竞品与边界
- **Adopt**：复用 v0.6.0 `_get`/`_post`/`_request` 错误处理（非 200 抛 RuntimeError）与签名风格。
- **Avoid / Out-of-Scope**：不改既有 8 方法、不引新依赖、不做缓存；不做系统管理（update/rollback/firewall）、API key 管理、集合竞价、分钟线下载。
- **约束**：Python ≥3.13；`restart_qmt` 的 password 经 query 传递（网关设计），勿记入访问日志。

## 4. 风险与假设
| # | 假设 / 风险 | 验证 / 应对 |
|---|---|---|
| 1 | 假设：5 端点签名/返回结构与 qmt-gateway 文档一致 | M-DEV 真机对照 |
| 2 | 风险：`restart_qmt` password 走 query 可能进日志（中） | 不本地日志化 query；文档标注 |
| 3 | 风险：`all_stocks` 返回体较大（低） | 直透传，broker 层不分页 |

## 5. 必要性与冲突
- **已实现？** 否——`qmt_gateway.py`（v0.6.0）仅 8 交易方法（源码 `:71-184`，spec v0.6.0 FR-0100），无连接/查询方法。
- **相抵触？** 否——补齐非替换，与 v0.6.0 / v0.7.0 互补。**结论**：新建。

## 6. 方案疑议 + 门禁
- **疑议**：无。5 端点为网关既定 P0，无更优替代；password 经 query 为网关侧设计，不替其改方案。
- **分流结论**：Go（Agent 建议）——增量小、复用 helper、风险可控。
- **Human 确认**：[ ] 分流结论认同；[ ] §6 无异议免裁。**Backlog 登记**：Go → 进入 M-FOUND。
- **追溯**：`STR-0009` · `2026-07-23T00:00:00Z` · spec `v0.7.1-001-qmt-p0-wrappers` · Issue `#待创建`
*—— M-STORY Agent 于 2026-07-23 生成；待 Human 确认 Go 后进入 M-FOUND。*
