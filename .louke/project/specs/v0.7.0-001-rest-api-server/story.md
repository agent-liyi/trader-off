---
date: 2026-07-22
spec: v0.7.0-001-rest-api-server
status: draft
---

# STR-0008: v0.7.0 — RESTful API server（FastAPI 包装 14 个 CLI 内部函数）

## 0. 原始输入
> Provide a RESTful API server that exposes all 14 existing CLI internal functions as HTTP endpoints, so agents can call trader-off via HTTP+JSON instead of shell subcommands.

## 1. 用户与场景 (Who & Where)
- **主要角色**：量化研究员 / LLM agent（程序化调用，非人类点击 UI）。
- **次要角色**：无（本地单机，无多用户协作）。
- **用户规模**：单一开发者 / 单 agent，本地进程。
- **使用频次**：中频（agent 任务驱动，按需触发回测 / 同步 / 挖因子等）。
- **网络环境**：本地稳定环回（localhost），无弱网。
- **终端类型**：HTTP 客户端（curl / httpx / agent tool），非浏览器。
- **适配要求**：仅本机；默认 `127.0.0.1:5800`。

## 2. 功能与价值 (What & Why)
v0.5.4 已让所有 CLI 支持 `--json`（subprocess 可解析），但 agent 经 shell 子进程调用不稳（编码 / 退出码 / 超时难控）。本版起一个 FastAPI 进程，直接 import 并调用 14 个 CLI 内部函数，以 HTTP+JSON 暴露，agent 走 HTTP 更稳、更标准。
- **快乐路径**：1) `trader-off server --port 5800` 启动；2) agent `POST /backtest {...}`；3) 服务直接调内部函数，返回 `{"status":"ok","data":{...}}`，与 `--json` 契约一致。

### 2.1 功能需求（EARS）
| # | 句式 |
|---|---|
| AC-01 | `WHEN agent 发起 POST /{endpoint}, THE 系统 SHALL 调用对应 CLI 内部函数并返回与 --json 一致的 JSON` |
| AC-02 | `WHEN 内部函数抛错, THE 系统 SHALL 返回 {"status":"error","code":N,"message":"..."} 且 HTTP 状态码映射退出码（4→400, 5→500, 2→422）` |
| AC-03 | `WHEN 用户执行 trader-off server --port N --host H, THE 系统 SHALL 以 uvicorn 启动 FastAPI 监听 H:N` |
| AC-04 | `WHILE server 运行, THE 系统 SHALL 复用 function-scope 懒加载（NFR-0100），不在模块顶层 import 重依赖` |
| AC-05 | `WHERE --json 传入 server 命令, THE 系统 SHALL 以 JSON 行输出启动信息供 agent 解析` |

### 2.2 FR / NFR
- **FR-0100**：`src/trader_off/api/server.py` — FastAPI app，14+ 端点包装现有内部函数；JSON 与 `--json` 一致；graceful 错误处理。
- **FR-0200**：`src/trader_off/cli/server.py` — `trader-off server` 入口；参数 `--port` / `--host` / `--json`。
- **NFR-0100**：继承 function-scope 懒加载；新增 `fastapi>=0.115,<1.0` + `uvicorn[standard]>=0.34,<1.0`。
- **北极星目标**：agent 不再依赖 subprocess 即可完成一次回测 / 同步闭环。
- **可观测指标**：agent 调用失败率低于 subprocess 方案；端点单测覆盖对齐现有 CLI。

## 3. 竞品与边界 (Scope & Competition)
- **Adopt**：v0.5.4 `--json` 的 `{"status","data"}` / `{"status","error"}` 契约与退出码语义（复用 `cli/_json_output.py`）；`scheduler/api.py` 的 localhost-only + 错误中间件吞 traceback 模式。
- **Avoid**：不改 14 个内部函数签名 / 行为（仅包装）；不引入新业务逻辑。
- **Out-of-Scope**：鉴权 / 认证 / 限流 / 生产部署 / TLS / 多实例。明确不做。
- **约束**：Python ≥3.13；仅 127.0.0.1；新依赖锁 major 上限。

## 4. 风险与假设 (Risk & Assumption)
| # | 假设 | 验证 / 负责人 |
|---|---|---|
| 1 | 14 个内部函数可被直接 import 且无 argparse 副作用 | M-DEV 逐模块核对 / Devon |
| 2 | HTTP JSON 与 `--json` 输出逐字段等价（含 data schema） | 端点 vs CLI 对照测试 |
| 3 | agent 本机调用，无并发 / 鉴权需求 | Human 确认 Out-of-Scope |
| # | 风险 | 影响 / 应对 |
| 1 | 长任务（回测 / 同步）阻塞 uvicorn 事件循环 | 高；`run_in_executor` 或 job-id 轮询 |
| 2 | 端口 5800 与 qmt-gateway 默认端口冲突（见 §6） | 中；换端口或文档约束 |
| 3 | 懒加载致首次请求冷启动慢 | 低；可接受，日志可观测 |

## 5. 必要性与冲突 (Necessity & Conflict)
- **已实现？** 部分——`scheduler/api.py`（aiohttp, :8765）已暴露 retrain 的 4 个端点，但仅限调度器，非全部 14 个 CLI 函数；不可复用为统一入口。
- **相抵触？** 否——v0.5.4 `--json`（subprocess 路径）与本版（in-process HTTP 路径）为并行的两条 agent 集成通道，互补不替换。
- **结论**：新建（证据：`pyproject.toml:36-45` 9 个 console scripts；`scheduler/api.py:1-53` 局部 HTTP；无 `src/trader_off/api/` 目录）。

## 6. 方案疑议（A/B Advisory，非决策）
- **状态**：有疑议（端口冲突）。
- **建议**：💡 默认端口 `5800` 与 v0.6.0 `QmtGatewayBroker` 默认 `base_url=http://localhost:5800`（spec v0.6.0 FR-0100/FR-0200）撞端口。典型部署（Mac 研究员跑 trader-off server + 远端 Windows 跑 qmt-gateway）不冲突；但同机混跑会冲突。建议默认改 `5801`/`8000`，或文档强制分机。最终由 Human 裁决，Agent 不自动改。
- **次要点**：是否把 `scheduler/api.py` 的 4 个 aiohttp 端点迁入新 FastAPI server 统一入口？本故事按"不迁、二者共存"处理；如要统一需另开故事。

## 7. 分流结论与门禁 (Gate)
- **分流结论**：Go（Agent 建议）——4W 清晰、复用 v0.5.4 契约、风险可控。
- **Human 确认**：[ ] 分流结论认同；[ ] §6 端口冲突建议裁决。
- **Backlog 登记**：Go → 进入 M-FOUND。

## 8. 可追溯种子 (Traceability)
- **Story ID**：`STR-0008`
- **创建时间**：`2026-07-22T00:00:00Z`
- **关联 Issue**：`#待创建`
- **关联 Spec ID**：`v0.7.0-001-rest-api-server`

*—— M-STORY Agent 于 2026-07-22 生成；待 Human 确认 Go 后进入 M-FOUND。*
