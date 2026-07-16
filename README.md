# trader-off

基于 [millionaire](https://github.com/zillionare/millionaire) 框架的量化交易策略 —— 使用 lightGBM 构建的短时资产定价模型，预测 A 股个股未来 5 个交易日收益率。

## 概览

- **模型**：lightGBM 回归
- **标签**：未来 5 个交易日收益率
- **数据**：A 股全市场日线（via millionaire 数据模块）
- **集成**：millionaire 回测 Runner

> v0.1.0 开发中，详见 `.louke/project/`。
