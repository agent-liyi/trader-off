# trader-off

> A 股量化研究 + 回测平台，基于 [millionaire/quantide](https://github.com/zillionare/millionaire)。

## 功能

- **因子挖掘**：从 13 个模板（动量 / 波动率 / 成交量 / 基本面）展开 373 个候选因子，按 IC 排名精选
- **训练预测**：LightGBM 训练 + 模型推理 + 版本管理
- **策略评估**：IC / Rank IC / 分层回测
- **交易策略**：`LGBMTop20`、`OptimizedTopK`（接 quantide 策略框架）
- **历史回测**：委托 quantide 引擎（真实撮合 / 手续费 / T+1 / 记账），取真数据或本地 fixture
- **纸交易**：仿真交易，同一份策略代码跑回测和纸交易
- **组合优化**：cvxpy Max Sharpe（long-only / 满仓 / 行业中性 / 个股上限）
- **数据同步**：从 tuShare 拉 A 股日线到本地 DailyBarsStore
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

### 数据同步

```bash
trader-off-sync-data \
    --universe watchlist.csv \
    --start 2026-01-01 \
    --end 2026-07-22
```

从 tuShare 拉取 OHLCV 数据写入本地 DailyBarsStore（年分区 parquet）。需 `TUSHARE_TOKEN`。支持 `--dry-run`（不拉数据，仅打印计划）。

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
