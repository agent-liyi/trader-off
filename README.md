# trader-off

> millionaire/quantide 命令行封装。涵盖回测、纸交易、实盘交易、REST API、网格寻优、数据同步。

## 功能

- **REST API server**（v0.7.0）：FastAPI 服务，15 端点暴露所有 CLI，agent 通过 HTTP+JSON 调用
- **因子挖掘**：从 13 个模板展开 373 候选因子，IC 排名精选
- **参数寻优**：网格搜索策略参数，多进程并行回测，Sharpe 排名选最优
- **策略回测**：委托 quantide 引擎（真实撮合 / 手续费 / T+1 / 记账）
- **纸交易**：仿真交易，同一份策略代码跑回测和纸交易
- **组合优化**：cvxpy Max Sharpe（long-only / 满仓 / 行业中性 / 个股上限）
- **数据同步**：从 tuShare 拉 A 股日线到本地 DailyBarsStore
- **股票列表**：获取 A 股列表，支持按交易所/状态过滤
- **实时行情**：quantide LiveQuote 订阅，需 qmt-gateway
- **实盘交易**：通过 qmt-gateway 执行实盘交易（30 个 QmtGatewayBroker 方法）
- **调度重训**：定时检测漂移 → 自动重训练 → 部署

## 安装

```bash
git clone https://github.com/agent-liyi/trader-off
cd trader-off
uv sync   # Python 3.13+

# 可选——把二进制 link 到系统 PATH（全局可用）
bash scripts/install.sh
```

`scripts/install.sh` 把统一入口 `to` symlink 到 `/usr/local/bin`。之后任何路径都可以直接 `to backtest --help`。

可选——真实 A 股数据：
```bash
export TUSHARE_TOKEN=<your_token_from_tushare.pro>
```

## 使用

所有命令支持 `--json` 输出，agent 友好。统一入口 `to` 通过 `[project.scripts]` 注册，全局可用。

### REST API server（v0.7.0）

启动 FastAPI 服务，通过 HTTP 暴露所有 CLI 命令：

```bash
to server --port 8000    # 默认 localhost:8000
```

Agent 可通过 HTTP 调用（如 `POST /backtest`），请求体是 JSON，返回也是 JSON。需要 `--port 8000`（默认）避开 qmt-gateway 的 5800。

### 因子挖掘

```bash
to mine-factors --config factor_defs.yaml \
    --top-k 30 \
    --corr-threshold 0.9 \
    --output reports/factor_mining/
```

### 组合优化

```bash
to optimize \
    --predictions predictions.csv \
    --industry-map industry.csv \
    --returns returns_history.csv \
    --output reports/portfolio/ \
    --max-position 0.10 --industry-neutral
```

### 回测

```bash
to backtest \
    --model v1 --strategy optimized_topk \
    --start 2024-01-02 --end 2024-12-31 \
    --capital 1000000
```

输出 `reports/backtest_<ts>/nav_<ts>.parquet`、`positions_<ts>.parquet`、`summary.json`。

### 纸交易

```bash
to paper-trade \
    --strategy optimized_topk \
    --universe watchlist.csv \
    --capital 1000000
```

输出 `reports/paper_trade_<ts>/`：仿真 NAV、持仓、交易记录。需 `TUSHARE_TOKEN`。

### 参数寻优

```bash
to grid-search --config params.yaml \
    --strategy optimized_topk \
    --start 2024-01-01 --end 2024-12-31 \
    --capital 1000000
```

`params.yaml` 定义参数空间：
```yaml
param_space:
  top_k: [10, 20, 30]
  rebalance_days: [5, 10, 20]
```
多进程并行跑回测，按 Sharpe 排名输出最优参数。

### 数据同步

```bash
to sync-data \
    --universe watchlist.csv \
    --start 2026-01-01 \
    --end 2026-07-22
```

从 tuShare 拉取 OHLCV 数据写入本地 DailyBarsStore（年分区 parquet）。需 `TUSHARE_TOKEN`。支持 `--dry-run`（不拉数据，仅打印计划）。

### 初始化

```bash
to init                    # 在当前目录下初始化（./data/...）
to init --home .quantide   # 初始化到 .quantide/
to init --home /path/to/data  # 指定数据根目录
```

在当前目录创建日历、行情、数据库子目录（`data/calendar.parquet`、`data/bars/daily/` 等）。需要 `TUSHARE_TOKEN`。

### 股票列表

```bash
to stock-list                          # 获取全部股票列表
to stock-list --exchange SSE           # 按交易所过滤 (SSE/SZSE/BSE)
to stock-list --status L               # 按状态过滤 (L=上市/D=退市/P=暂停)
to stock-list --exchange SSE --json    # JSON 输出
```

从 tuShare 获取 A 股列表，返回 JSON 含 `ts_code` / `name`。需 `TUSHARE_TOKEN`。

### 因子有效性检查

```bash
to check-factor --name momentum_5 --start 2024-01-02 --end 2024-12-31
to check-factor --name momentum_5 --start 2024-01-02 --end 2024-12-31 --json
to check-factor --name vol_20 --start 2024-01-02 --end 2024-12-31 --ic-threshold 0.5
```

评估单个因子，输出 IC/ICIR/Rank IC/Rank ICIR 及有效性判定。支持 `--json` 输出。

### 实时行情

```bash
to live --status                                           # 查看状态
to live --start --assets 000001.SZ,600000.SH              # 订阅
to live --stop                                            # 停止
```

通过 quantide LiveQuote 订阅实时行情，需 qmt-gateway。

### 实盘交易

```bash
to live-trade \
    --strategy optimized_topk \
    --universe watchlist.csv \
    --capital 1000000
```

实盘交易（需 qmt-gateway 部署）。通过 qmt-gateway HTTP API 执行买卖、查询持仓/订单/成交。支持 `--json` JSON 输出。

### 生成策略

```bash
to generate-strategy --name MyStrategy --dry-run              # 预览骨架
to generate-strategy --name MyMA --template double-ma         # 双均线策略
to generate-strategy --name Mom --template momentum           # 动量反转策略
to generate-strategy --name MF --template multi-factor        # 多因子策略
```

生成 quantide BaseStrategy 子类。带 `--template` 时 `on_day_open` 中已填好因子计算 + 调仓逻辑，可直接回测。

### 调度

```bash
to scheduler start --config scheduler.yaml
to scheduler status
to scheduler retrain trigger --model-version v2
```

### 状态

```bash
to status              # 全局状态（JSON：version/data_source/models/scheduler）
to status data         # 检查本地行情数据
to status models       # 检查因子/模型产物
to status scheduler    # 检查调度进程
```

### 自更新

```bash
to update              # git pull + uv sync + 重新 link `to`
```

> 兼容：`uv run python -m trader_off.<path>` 仍可用。

## 输出示例

`summary.json`：
```json
{
  "annualized_return": 0.182,
  "sharpe_ratio": 1.43,
  "sortino_ratio": 2.01,
  "max_drawdown": -0.087,
  "drawdown_duration_days": 18,
  "win_rate": 0.55,
  "total_trades": 234,
  "avg_turnover": 0.18
}
```

## 数据来源

| 来源 | 触发条件 |
|---|---|
| 真实 A 股（quantide TushareFetcher）| `TUSHARE_TOKEN` 已设 |
| Fixture `tests/fixtures/v0.2.0/ohlcv_50x252.parquet` | 无 token / 单元测试 |
| 自备 parquet | 自己有数据，按 `DailyBarsStore` schema 转换 |

## 许可

版本历史与发布：https://github.com/agent-liyi/trader-off/releases
