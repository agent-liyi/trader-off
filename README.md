# trader-off

> millionaire/quantide 命令行封装。涵盖回测、纸交易、网格寻优、数据同步、实时行情。

## 功能

- **因子挖掘**：从 13 个模板展开 373 候选因子，IC 排名精选
- **参数寻优**：网格搜索策略参数，多进程并行回测，Sharpe 排名选最优
- **策略回测**：委托 quantide 引擎（真实撮合 / 手续费 / T+1 / 记账）
- **纸交易**：仿真交易，同一份策略代码跑回测和纸交易
- **组合优化**：cvxpy Max Sharpe（long-only / 满仓 / 行业中性 / 个股上限）
- **数据同步**：从 tuShare 拉 A 股日线到本地 DailyBarsStore
- **股票列表**：获取 A 股列表，支持按交易所/状态过滤
- **实时行情**：quantide LiveQuote 订阅，需 qmt-gateway
- **调度重训**：定时检测漂移 → 自动重训练 → 部署

## 安装

```bash
git clone https://github.com/agent-liyi/trader-off
cd trader-off
uv sync   # Python 3.13+
```

可选——真实 A 股数据：
```bash
export TUSHARE_TOKEN=<your_token_from_tushare.pro>
```

## 使用

CLI 通过 `[project.scripts]` 注册，全局可用：

### 因子挖掘

```bash
trader-off-mine-factors --config factor_defs.yaml \
    --top-k 30 \
    --corr-threshold 0.9 \
    --output reports/factor_mining/
```

### 组合优化

```bash
trader-off-optimize \
    --predictions predictions.csv \
    --industry-map industry.csv \
    --returns returns_history.csv \
    --output reports/portfolio/ \
    --max-position 0.10 --industry-neutral
```

### 回测

```bash
trader-off-backtest \
    --model v1 --strategy optimized_topk \
    --start 2024-01-02 --end 2024-12-31 \
    --capital 1000000
```

输出 `reports/backtest_<ts>/nav_<ts>.parquet`、`positions_<ts>.parquet`、`summary.json`。

### 纸交易

```bash
trader-off-paper-trade \
    --strategy optimized_topk \
    --universe watchlist.csv \
    --capital 1000000
```

输出 `reports/paper_trade_<ts>/`：仿真 NAV、持仓、交易记录。需 `TUSHARE_TOKEN`。

### 参数寻优

```bash
trader-off-grid-search --config params.yaml \
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
trader-off-sync-data \
    --universe watchlist.csv \
    --start 2026-01-01 \
    --end 2026-07-22
```

从 tuShare 拉取 OHLCV 数据写入本地 DailyBarsStore（年分区 parquet）。需 `TUSHARE_TOKEN`。支持 `--dry-run`（不拉数据，仅打印计划）。

### 初始化

```bash
trader-off init                    # 初始化数据目录 .quantide/
trader-off init --home /path/to/data  # 指定数据根目录
```

初始化日历、行情、数据库子目录。

### 股票列表

```bash
trader-off-stock-list                          # 获取全部股票列表
trader-off-stock-list --exchange SSE           # 按交易所过滤 (SSE/SZSE/BSE)
trader-off-stock-list --status L               # 按状态过滤 (L=上市/D=退市/P=暂停)
trader-off-stock-list --exchange SSE --json    # JSON 输出
```

从 tuShare 获取 A 股列表，返回 JSON 含 `ts_code` / `name`。需 `TUSHARE_TOKEN`。

### 因子有效性检查

```bash
trader-off-check-factor --name momentum_5 --start 2024-01-02 --end 2024-12-31
trader-off-check-factor --name momentum_5 --start 2024-01-02 --end 2024-12-31 --json
trader-off-check-factor --name vol_20 --start 2024-01-02 --end 2024-12-31 --ic-threshold 0.5
```

评估单个因子，输出 IC/ICIR/Rank IC/Rank ICIR 及有效性判定。支持 `--json` 输出。

### 实时行情

```bash
trader-off-live --status                                           # 查看状态
trader-off-live --start --assets 000001.SZ,600000.SH              # 订阅
trader-off-live --stop                                            # 停止
```

通过 quantide LiveQuote 订阅实时行情，需 qmt-gateway。

### 生成策略

```bash
trader-off-generate-strategy --name MyStrategy --dry-run           # 预览
trader-off-generate-strategy --name MomentumReversion              # 生成到 src/trader_off/strategies/
```

生成 quantide BaseStrategy 子类（init/on_day_open/on_bar/on_day_close/on_stop）。

### 调度

```bash
trader-off-scheduler start --config scheduler.yaml
trader-off-scheduler status
trader-off-scheduler retrain trigger --model-version v2
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
