---
status: draft
---
# v0.4.2 patch — `[project.scripts]` console_scripts — Spec

- **Spec ID**: v0.4.2-001-console-scripts
- **Created**: 2026-07-21
- **Status**: Draft
- **关联 story**: `.louke/project/specs/v0.4.2-001-console-scripts/story.md` (STR-0004)
- **关联基线**:
  - v0.4.1 README L35 已知 DX 短板 ("⚠️ 没有 console_scripts")
  - v0.3.1 FR-0100 (scheduler `main(argv)` 收子命令 `start/stop/status/retrain trigger`) — 本 patch 不动 scheduler 签名

> **职责切分**: 本文档只描述需求本身 (FR/NFR 描述 + 元数据)。
> 验收标准放在 `acceptance.md` 中。
> 测试计划 (`test-plan.md`) 同时引用本文件与 `acceptance.md`。

> **北极星目标**: `uv sync` 之后，4 个 `trader-off-*` entry point 直接可用，无需 `uv run python -m trader_off.<path>`；原 `python -m` 调用路径保持不变（向后兼容兜底）。
>
> **关键约束**:
> - patch ≤ 1 issue；仅修改 `pyproject.toml` (+4 行 `[project.scripts]`) + README 替换 5 处 `python -m` + 删 1 行警告；**不写新代码**
> - 不引入新依赖；不修 `factor_mining/cli.py` bug；不动 scheduler 签名（v0.3.1 FR-0100）
> - 不重命名为单词命令（`trader-off backtest` 风格）—— v0.4.3+ 再议

## User Stories

### US-0010

story: 作为一名量化研究员，我希望 `uv sync` 后能直接执行 `trader-off-backtest --help`、`trader-off-optimize --help`、`trader-off-mine-factors --help`、`trader-off-scheduler status`（v0.3.1 子命令照旧），而无需 `uv run python -m trader_off.<path>`，从而消除 README L35 已知 DX 短板；原 `python -m` 路径作为兜底保持可用。
priority: P0

## Usage Scenarios

### scenario-0010 happy path

1. 开发者执行 `uv sync` → `.venv/bin/` 生成 4 个 entry point（PEP 621 dash-prefix）：`trader-off-backtest` / `trader-off-optimize` / `trader-off-mine-factors` / `trader-off-scheduler`。
2. 开发者执行 `trader-off-backtest --help` → exit 0，stdout 含 argparse help 文本。
3. 开发者执行 `trader-off-scheduler status` → 沿用 v0.3.1 `start/stop/status/retrain trigger` 子命令分派。
4. 开发者执行 `python -m trader_off.cli.backtest --help` → 仍可用（NFR-0100 兜底）。

## Functional Requirements

> **格式约定 (必读)**: 每个 FR 单元以三级标题 + 空格 + `FR-XXXX`(大写、4 位补零)+ {标题} 开头，紧接三列元数据表 (Valid / Testable / Decided)，再写需求描述；FR 之间用 `---` 分隔。
>
> **编号约定 (必读)**: 本 spec 使用 **FR-0100** 一条 P0 FR + **NFR-0100** 一条 NFR；起始 100 间隔（patch ≤ 1 issue 范围，不预留扩展位）。
>
> **元数据表 (3 列)**:
> - Valid (原 yaml `valid`): ✅ = 仍生效，❌ = 已废弃
> - Testable (原 yaml `testability`): ✅ = 可测试/可断言，⚠️ {原因} = 存保留意见
> - Decided (原 yaml `resolved`): ✅ = 用户已确认，⚠️ = 待澄清，❌ = 用户明确拒绝

---

<a id="fr-0100"></a>
### FR-0100 `[project.scripts]` 4 entry points — `trader-off-*` 直接可用

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **改动文件**：`pyproject.toml`（仅此一处）+ `README.md`（替换 5 处 `python -m trader_off.<path>` 为 `trader-off-*` + 删除 L35 警告行）。
- **`pyproject.toml` 新增表**（PEP 621 dash-prefix，紧跟 `[project]` 块之后，build backend 仍 `setuptools.build_meta`）：
  ```toml
  [project.scripts]
  trader-off-backtest     = "trader_off.cli.backtest:main"
  trader-off-optimize     = "trader_off.portfolio.cli:main"
  trader-off-mine-factors = "trader_off.factor_mining.cli:main"
  trader-off-scheduler    = "trader_off.scheduler.cli:main"
  ```
- **entry point 映射**（4 个 `main()` 全部已存在，零开发成本）：
  - `trader-off-backtest` → `src/trader_off/cli/backtest.py:20` `main()`
  - `trader-off-optimize` → `src/trader_off/portfolio/cli.py:220` `main(argv)`
  - `trader-off-mine-factors` → `src/trader_off/factor_mining/cli.py:239` `main(argv)`
  - `trader-off-scheduler` → `src/trader_off/scheduler/cli.py:445` `main(args)`
- **验证（smoke，4 次 `--help` 即可）**：
  - `uv sync` 退出码 0，无 `uv.lock` 漂移警告（仅 `[project.scripts]` 表新增，dependencies 零变化）。
  - `.venv/bin/trader-off-{backtest,optimize,mine-factors,scheduler}` 4 个文件存在且可执行（`os.access(..., os.X_OK)` 为真）。
  - `uv run trader-off-backtest --help` exit 0，stdout 含 `--model` / `--strategy` / `--start` / `--end` / `--capital` / `--config` 等 argparse help 文本。
  - `uv run trader-off-scheduler --help` exit 0，stdout 含 `start/stop/status/retrain trigger` 4 个子命令（v0.3.1 FR-0100 签名保持）。
- **README 同步**：
  - L35 警告行 "⚠️ 没有 console_scripts" 删除。
  - README 中 5 处 `python -m trader_off.<path>` 替换为对应 `trader-off-*` 调用（保留 `python -m` 在 Out-of-Scope / 迁移说明中作为兜底提及，符合 NFR-0100）。
- **out-of-scope**（继承 Story §3.1，**不**做）：
  - 不引入单词命令重命名（`trader-off backtest` 空格风格）—— v0.4.3+ 再议。
  - 不修改 `factor_mining/cli.py` bug（独立 scope）。
  - 不修 v0.3.0 security low / v0.3.3 调仓完善（各自分别 scope）。
  - 不引入新依赖；**不写新代码**（仅 `pyproject.toml` + README 文本替换）。

---

## Non-Functional Requirements

> **必读**: NFR 格式与编号规则同 FR，此处省略。

<a id="nfr-0100"></a>
### NFR-0100 向后兼容 — 原 `python -m trader_off.<path>` 仍可用，4 个 `main(argv)` 签名不变

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

- **核心约束**：本 patch **不删不改** `src/trader_off/cli/backtest.py:20` / `src/trader_off/portfolio/cli.py:220` / `src/trader_off/factor_mining/cli.py:239` / `src/trader_off/scheduler/cli.py:445` 共 4 个 `main(argv)` 函数体；其参数签名（`main()` / `main(argv)` / `main(args)`）与现有 `argparse` 行为 100% 保留。
- **理由（继承 Story §4.1）**：
  - v0.3.1 spec 已确立 scheduler `main(argv)` 收子命令（`start/stop/status/retrain trigger`）的公开契约，本 patch 不破坏。
  - 外部 cron / 文档 / CI 脚本可能依赖 `python -m trader_off.<path>` 路径（兜底价值）。
- **验证 1（main 函数签名保留）**：
  - `git diff` 在 `src/trader_off/cli/backtest.py` / `src/trader_off/portfolio/cli.py` / `src/trader_off/factor_mining/cli.py` / `src/trader_off/scheduler/cli.py` 4 个文件上**为空**（仅 `pyproject.toml` + `README.md` 修改）。
  - `grep -n "^def main" src/trader_off/cli/backtest.py src/trader_off/portfolio/cli.py src/trader_off/factor_mining/cli.py src/trader_off/scheduler/cli.py` 返回 4 行匹配，行号与 Story §4.1 列出的源文件:行号一致。
- **验证 2（`python -m` 路径可用）**：4 条 `python -m trader_off.<path> --help` 调用全部 exit 0：
  - `python -m trader_off.cli.backtest --help`
  - `python -m trader_off.portfolio.cli --help`
  - `python -m trader_off.factor_mining.cli --help`
  - `python -m trader_off.scheduler.cli --help`（scheduler 子命令 `start/stop/status/retrain trigger` 仍可访问）
- **README 兜底提及**：README 中**至少保留 1 处**对 `python -m trader_off.<path>` 的引用（如 Out-of-Scope / 故障迁移说明），不让用户产生"已被彻底移除"的错觉。
- **out-of-scope**（**不**做）：
  - 不在 `main(argv)` 函数体内新增 `try/except RuntimeError` 兜底（保持 v0.3.1 现有实现）。
  - 不为 `python -m` 路径添加 `console_scripts` 反向入口（无需，重复）。

---

## Clarification Log

> Record questions raised during user review, Sage/Lex replies, reasons for deprecated requirements, and any decisions that affect FR/NFR table status.

| Round | Source | Question / Decision | Status |
|---|---|---|---|
| 0 (Story M-STORY) | Story §2.1 / §5 | dash-prefix vs 单词命令（`trader-off backtest`）— Agent 不替用户决策命名风格，用户已确认 dash (Story §5)；v0.4.3+ 再议单词命令重命名 | ✅ |
| 0 (Story M-STORY) | Story §4.2 冲突表 | v0.3.1 FR-0100 scheduler `main(argv)` 签名 — NFR-0100 显式保留；本 patch 不动 scheduler 子命令分派 | ✅ |
| 0 (Story M-STORY) | Story §4.2 冲突表 | v0.4.1 README L35 警告 — 本 patch 删除该行（FR-0100 README 同步条款）；v0.4.1 NFR-0100 lazy import + token 不落盘 — 仅增 `[project.scripts]` 表，零新 import/网络路径，零冲突 | ✅ |
| 0 (M-SPEC) | 本 spec | **scheduler subcommand 完整性**：scheduler CLI 必须保留 `start/stop/status/retrain trigger` 4 个子命令（v0.3.1 FR-0100 继承），FR-0100 验证条款与 NFR-0100 验证 2 双重覆盖 | ✅ |
| 0 (M-SPEC) | 本 spec | **patch 边界**：仅 `pyproject.toml` + `README.md` 两个文件修改；4 个 `cli/*.py` 文件 git diff 为空（零代码改动）；`uv.lock` 因 `[project.scripts]` 不影响依赖图应零漂移（若 uv 报 lock 漂移，以 uv 行为为准并在 Clarification Log 记录） | ✅ |
