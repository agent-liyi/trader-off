# trader-off

> A 股量化研究 + 回测平台，基于 [millionaire/quantide](https://github.com/zillionare/millionaire)。

## 功能

- **因子挖掘**：13 个模板（momentum / volatility / volume / fundamental）→ 373 候选因子 → IC 评估 → 注册
- **特征工程**：动量 / 波动率 / 成交量（polars）
- **标签构建**：未来 N 日收益率
- **训练**：LightGBM 训练 + joblib 序列化
- **预测**：模型推理 + 版本管理
- **评估**：IC / Rank IC / 分层回测
- **策略**：`LGBMTop20` / `OptimizedTopK`（接 quantide `BaseStrategy`）
- **回测**：委托 `quantide.BacktestRunner` + `BacktestBroker`（真实撮合 / 手续费 / T+1 / 记账）
- **指标**：委托 `quantide.service.metrics`（Sharpe / Sortino / 回撤持续期 / 基准对比）
- **组合优化**：cvxpy Max Sharpe（long-only / 满仓 / 行业中性 / 个股 ≤10%）
- **调度**：croniter + `quantide.SchedulerManager`（漂移检测 → 重训练 → 部署）
- **可视化**：静态 PNG 图表（IC 分布 / 因子重要性 / 分层回测）

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

### 数据获取（v0.4.1）

```python
import asyncio
from datetime import date
from trader_off.data.quantide_adapter import QuantideDataLoader

loader = QuantideDataLoader()
df = asyncio.run(loader.get_daily("000001.SZ", date(2026, 7, 17), count=60))
print(df)
```

### 因子挖掘（v0.2.0 模块级可用）

```python
from trader_off.factor_mining.templates import list_templates
from trader_off.factor_mining.expression import enumerate_factors, DEFAULT_PARAM_SPACE

templates = list_templates()  # 13 个
candidates = enumerate_factors(templates, DEFAULT_PARAM_SPACE)  # 373 候选
```

或通过 CLI：
```bash
uv run trader-off-mine-factors --help
```

### 组合优化

```bash
uv run trader-off-optimize \
    --predictions predictions.csv \
    --industry-map industry.csv \
    --returns returns_history.csv \
    --output reports/portfolio/ \
    --max-position 0.10 --industry-neutral
```

### 回测

```bash
uv run trader-off-backtest \
    --model v1 --strategy optimized_topk \
    --start 2024-01-02 --end 2024-12-31 \
    --capital 1000000
```

输出 `reports/backtest_<ts>/nav_<ts>.parquet`、`positions_<ts>.parquet`、`summary.json`。

### 调度

```bash
uv run trader-off-scheduler start --config scheduler.yaml
uv run trader-off-scheduler status
uv run trader-off-scheduler retrain trigger --model-version v2
```

> 兼容：仍可通过 `python -m trader_off.<path>` 调用（如 `python -m trader_off.cli.backtest --help`）。

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
