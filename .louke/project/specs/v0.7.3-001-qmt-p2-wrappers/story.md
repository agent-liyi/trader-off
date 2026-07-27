---
date: 2026-07-23
spec: v0.7.3-001-qmt-p2-wrappers
status: draft
---
# STR-0011: v0.7.3 — qmt-gateway P2 包装补全（系统管理 + API key）

## 0. 原始输入
> Complete qmt-gateway wrapping — add P2 system management + API key methods to QmtGatewayBroker.

## 1. 用户与场景
- 研究员 / LLM agent（运维/凭据管理），程序化调用 `QmtGatewayBroker`（非 UI）；单机单进程，低频运维；经局域网到 Windows qmt-gateway（默认 :5800）。
- 前置：v0.6.0 (8) + v0.7.1 (5) + v0.7.2 (4) = 17 方法就位。

## 2. 功能与价值 (What & Why)
v0.7.1 §3 / v0.7.2 §3 显式将系统管理（version/update/rollback/autostart/port/firewall）与 API key 管理划入 Out-of-Scope 待 P2 承接；本版补 13 方法，闭环"探活→运维网关（版本/更新/防火墙）→凭据管理（建/查/吊销）→交易"。
- **快乐路径（运维）**：`get_version()` → `check_version()` → `start_update()` → 轮询 `get_update_status(task_id)` → 失败 `do_rollback()`。
- **快乐路径（凭据）**：管理员 `create_api_key("agent-1")` 取 key → `list_api_keys()` 审计 → `revoke_api_key(key_id)` 吊销。
- **FR-0100**：`src/trader_off/broker/qmt_gateway.py` 新增 13 方法，复用既有 `_get`/`_post`/`_request`。**NFR-0100**：继承 function-scope 懒加载；无新依赖。

### EARS
| # | 句式 |
|---|---|
| AC-01 | `WHEN 调用 get_version(), THE 系统 SHALL GET /version 返回网关版本 dict` |
| AC-02 | `WHEN 调用 check_version(), THE 系统 SHALL POST /check_version 返回版本比对结果 dict` |
| AC-03 | `WHEN 调用 start_update(), THE 系统 SHALL POST /start_update 返回 {"task_id":str}` |
| AC-04 | `WHEN 调用 get_update_status(task_id), THE 系统 SHALL GET /update_status/{task_id} 返回进度 dict` |
| AC-05 | `WHEN 调用 do_rollback(), THE 系统 SHALL POST /do_rollback 回滚到上一版本返回结果 dict` |
| AC-06 | `WHEN 调用 get_autostart(), THE 系统 SHALL GET /autostart 返回 {"enabled":bool}` |
| AC-07 | `WHEN 调用 set_autostart(enabled), THE 系统 SHALL POST /set_autostart?enabled= 设置开机自启` |
| AC-08 | `WHEN 调用 get_port(), THE 系统 SHALL GET /port 返回 {"port":int}` |
| AC-09 | `WHEN 调用 get_firewall(), THE 系统 SHALL GET /firewall 返回规则 list` |
| AC-10 | `WHEN 调用 update_firewall(rules), THE 系统 SHALL POST /update_firewall 写入新规则` |
| AC-11 | `WHEN 调用 create_api_key(name), THE 系统 SHALL POST /api_key?name= 返回 {"key":str,"id":str}` |
| AC-12 | `WHEN 调用 list_api_keys(), THE 系统 SHALL GET /api_keys 返回 key 列表 list[dict]` |
| AC-13 | `WHEN 调用 revoke_api_key(key_id), THE 系统 SHALL DELETE /api_key/{key_id} 返回吊销结果` |

## 3. 竞品与边界
- **Adopt**：复用 v0.6.0 `_get`/`_post`/`_request` 错误处理（非 200 抛 RuntimeError）与签名风格。
- **Avoid / Out-of-Scope**：不改既有 17 方法、不引新依赖、不做缓存/重试；不做 qmt-gateway 之外的系统服务（系统服务管理 / 网关部署 / 鉴权提供方）；token 不本地加密存储（broker 透传，由调用方管生命周期）。
- **约束**：Python ≥3.13；`set_autostart`/`create_api_key` 参数走 query（网关设计）；`revoke_api_key` 无 DELETE 专用 helper，M-DEV 决定走 `_request("DELETE", …)` 或新增 `_delete`。

## 4. 风险与假设
| # | 假设 / 风险 | 验证 / 应对 |
|---|---|---|
| 1 | 假设：13 端点签名/返回结构与 qmt-gateway 文档一致 | M-DEV 真机对照 |
| 2 | 风险：`start_update`/`do_rollback` 是破坏性操作（高） | broker 透传不预校验；文档强警告 + 调用方二次确认 |
| 3 | 风险：`revoke_api_key` 误调致 agent 失凭据（中） | broker 不缓存；调用方自管 key 生命周期 |
| 4 | 假设：`update_firewall` 不会断连 broker 主机（需网关侧放行） | 文档提示先 `get_firewall` 备份 |

## 5. 必要性与冲突
- **已实现？** 否——`qmt_gateway.py` 现 17 方法（grep 无 version/update/autostart/port/firewall/api_key），v0.7.1 §3 + v0.7.2 §3 显式划入 P2 待本版承接。
- **相抵触？** 否——补齐非替换。**结论**：新建。

## 6. 方案疑议 + 门禁
- **疑议**：无。13 端点为网关既定 P2，无更优替代；`update`/`rollback`/DELETE 经 HTTP 是网关侧设计，不替其改方案。
- **分流结论**：Go（Agent 建议）——增量明确、复用 helper、破坏性操作风险已识别（文档警示）。
- **Human 确认**：[ ] 分流结论认同；[ ] §6 无异议免裁。**Backlog 登记**：Go → 进入 M-FOUND。
- **追溯**：`STR-0011` · `2026-07-23T00:00:00Z` · spec `v0.7.3-001-qmt-p2-wrappers` · Issue `#待创建`
*—— M-STORY Agent 于 2026-07-23 生成；待 Human 确认 Go 后进入 M-FOUND。*