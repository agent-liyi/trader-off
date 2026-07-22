# v0.4.2 patch — `[project.scripts]` console_scripts — Acceptance Criteria

- **Spec ID**: v0.4.2-001-console-scripts
- **Created**: 2026-07-21

> 中央注册表：spec.md 只保留 FR/NFR 描述与元数据（testability / decided / valid）；可观察、可断言的通过条件在本表中。
>
> 编号约定：
> - 每个 FR/NFR 单元内 AC-N 从 1 起，按顺序递增；单元之间不复用
> - 完整 AC 引用：**AC-FRXXXX-YY**（4 位 FR + 2 位 AC 序号），与 test-plan / issue schema 保持一致
> - 标题层级：`## FR-XXXX {title}` 为 level-2；`### AC-N` 为 level-3（其后同一行**不**接任何文字，canonical ID 写在下一行）
>
> Lex 阶段 1/2 审查验证：(1) 本表存在；(2) spec.md 每个 FR/NFR 在本表中有对应章节；(3) 每条 AC 可被测试或断言。
>
> EARS 句式关键词约定：`WHEN`（触发条件）/ `WHILE`（持续状态）/ `WHERE`（前置条件）/ `IF ... THEN`（条件分支）/ `THE 系统 SHALL ...`（系统行为）。

---

<a id="ac-fr-0100"></a>
## FR-0100 `[project.scripts]` 4 entry points — `trader-off-*` 直接可用

### AC-1

AC-FR0100-01

- **WHEN** `uv sync` 在仓库根目录执行完毕
- **THEN** 系统 SHALL 在 `.venv/bin/` 下生成 4 个可执行 entry point（PEP 621 dash-prefix）：`trader-off-backtest` / `trader-off-optimize` / `trader-off-mine-factors` / `trader-off-scheduler`；`uv.lock` 不出现依赖漂移警告（仅 `[project.scripts]` 表新增，dependencies 零变化）
- **断言**:
  - 给定：`pyproject.toml` 含 `[project.scripts]` 表 4 行 entry point 定义；工作目录干净。
  - 当：`uv sync` 执行完毕（exit 0）。
  - 那么：`.venv/bin/trader-off-backtest` / `.venv/bin/trader-off-optimize` / `.venv/bin/trader-off-mine-factors` / `.venv/bin/trader-off-scheduler` 4 个文件**全部存在**，且 `os.access(path, os.X_OK)` 为真（可执行位设置）。
  - 断言：`Path(".venv/bin/trader-off-backtest").is_file() and os.access(".venv/bin/trader-off-backtest", os.X_OK)` 等 4 条全部成立。
  - 旁证：`uv lock --check` exit 0（lockfile 无漂移；如 uv 报锁漂移则记录到 Clarification Log 并以 uv 行为为准）。
- **对应 EARS**: Story §2.4 AC-01。

### AC-2

AC-FR0100-02

- **WHEN** 用户执行 `trader-off-backtest --help`（通过 `uv run` 或 `.venv/bin/` 直接调用）
- **THEN** 系统 SHALL 解析为 `trader_off.cli.backtest:main` 入口，exit 0，stdout 含 argparse help 文本（`--model` / `--strategy` / `--start` / `--end` / `--capital` / `--config`）
- **断言**:
  - 给定：`uv sync` 已完成（AC-FR0100-01 通过）。
  - 当：`uv run trader-off-backtest --help` 执行。
  - 那么：进程 exit code `== 0`；stdout 含 `--model`、`--strategy`、`--start`、`--end`、`--capital`、`--config` 6 个 argparse 参数标记；stderr 为空。
  - 断言：`result.returncode == 0 and all(tok in result.stdout for tok in ["--model", "--strategy", "--start", "--end", "--capital", "--config"])`。
- **对应 EARS**: Story §2.4 AC-02。

### AC-3

AC-FR0100-03

- **WHEN** 用户执行其余 3 个 entry point 的 `--help`（`trader-off-optimize` / `trader-off-mine-factors` / `trader-off-scheduler`）
- **THEN** 系统 SHALL 每个都 exit 0，并分别解析到 `trader_off.portfolio.cli:main` / `trader_off.factor_mining.cli:main` / `trader_off.scheduler.cli:main`；scheduler entry point 应暴露 `start/stop/status/retrain trigger` 4 个子命令（v0.3.1 FR-0100 继承）
- **断言**:
  - 给定：`uv sync` 已完成。
  - 当：依次执行 `uv run trader-off-optimize --help` / `uv run trader-off-mine-factors --help` / `uv run trader-off-scheduler --help`。
  - 那么：3 个调用 exit code 全部 `== 0`；scheduler help 文本含子命令标记 `start`、`stop`、`status`、`retrain trigger`（其余子命令关键词若实际实现有差异，以源码为准，但 4 个 v0.3.1 子命令必须仍可访问）。
  - 断言：`all(rc == 0 for rc in [rc_optimize, rc_mine, rc_scheduler]) and all(t in scheduler_help for t in ["start", "stop", "status", "retrain trigger"])`。
- **对应 EARS**: Story §2.4 AC-02（4 entry 全覆盖）。

### AC-4

AC-FR0100-04

- **WHEN** 检查 `pyproject.toml` 内容
- **THEN** 系统 SHALL 含 `[project.scripts]` 表且 4 个 entry point 映射字符串严格匹配：`trader-off-backtest = "trader_off.cli.backtest:main"` / `trader-off-optimize = "trader_off.portfolio.cli:main"` / `trader-off-mine-factors = "trader_off.factor_mining.cli:main"` / `trader-off-scheduler = "trader_off.scheduler.cli:main"`
- **断言**:
  - 给定：`pyproject.toml` 源文件。
  - 当：解析 TOML 后读 `[project.scripts]` 表。
  - 那么：表项数量 `== 4`；key/value 字符串与上述 4 行**逐字一致**（允许空白格式差异但 value 字符串必须一致）。
  - 断言：`toml.load("pyproject.toml")["project"]["scripts"] == {"trader-off-backtest": "trader_off.cli.backtest:main", "trader-off-optimize": "trader_off.portfolio.cli:main", "trader-off-mine-factors": "trader_off.factor_mining.cli:main", "trader-off-scheduler": "trader_off.scheduler.cli:main"}`。

### AC-5

AC-FR0100-05

- **WHEN** 检查 README 修改
- **THEN** 系统 SHALL 删除 L35 "⚠️ 没有 console_scripts" 警告行，且 5 处 `python -m trader_off.<path>` 替换为对应 `trader-off-*` 调用
- **断言**:
  - 给定：`README.md` 源文件。
  - 当：`grep -n "⚠️ 没有 console_scripts" README.md` 与 `grep -cn "python -m trader_off" README.md` 执行。
  - 那么：警告行匹配 `== 0`；`python -m trader_off` 出现次数（作为**主推**用法计数）`== 0`（允许兜底/迁移说明段落保留 1 处提及，per NFR-0100 README 兜底条款）。
  - 断言：`grep_count("⚠️ 没有 console_scripts", README.md) == 0 and grep_count("python -m trader_off", README.md) <= 1`（≤1 表示最多保留 1 处兜底提及）。

---

<a id="ac-nfr-0100"></a>
## NFR-0100 向后兼容 — 原 `python -m trader_off.<path>` 仍可用，4 个 `main(argv)` 签名不变

### AC-1

AC-NFR0100-01

- **WHEN** `git diff` 在 4 个 CLI 模块文件上执行（baseline 为本 patch 前）
- **THEN** 系统 SHALL 4 个文件全部 git diff 为空（`src/trader_off/cli/backtest.py` / `src/trader_off/portfolio/cli.py` / `src/trader_off/factor_mining/cli.py` / `src/trader_off/scheduler/cli.py`），证明 4 个 `main(argv)` 函数体未被修改
- **断言**:
  - 给定：当前 git 工作树包含本 patch 待提交的改动（仅 `pyproject.toml` + `README.md`）。
  - 当：`git diff -- src/trader_off/cli/backtest.py src/trader_off/portfolio/cli.py src/trader_off/factor_mining/cli.py src/trader_off/scheduler/cli.py` 执行。
  - 那么：stdout 为空（4 个 CLI 文件零代码改动）。
  - 断言：`subprocess.run(["git", "diff", "--", ...4 paths], capture_output=True).stdout == b""`。

### AC-2

AC-NFR0100-02

- **WHEN** 执行 `python -m trader_off.<path> --help`（4 条命令）
- **THEN** 系统 SHALL 4 条全部 exit 0，stdout 含与 `trader-off-*` 等价的 argparse help 文本；scheduler 子命令 `start/stop/status/retrain trigger` 仍可访问（v0.3.1 FR-0100 继承）
- **断言**:
  - 给定：Python ≥ 3.13 + venv 已激活（与 `uv sync` 后 `.venv` 一致）。
  - 当：依次执行 `python -m trader_off.cli.backtest --help` / `python -m trader_off.portfolio.cli --help` / `python -m trader_off.factor_mining.cli --help` / `python -m trader_off.scheduler.cli --help`。
  - 那么：4 条 exit code 全部 `== 0`；scheduler help 含 `start` / `stop` / `status` / `retrain trigger` 4 子命令标记。
  - 断言：`all(rc == 0 for rc in [rc_backtest, rc_portfolio, rc_factor, rc_scheduler]) and all(t in scheduler_m_help for t in ["start", "stop", "status", "retrain trigger"])`。
- **对应 EARS**: Story §2.4 AC-03。

### AC-3

AC-NFR0100-03

- **WHEN** 检查 4 个 `main(argv)` 签名
- **THEN** 系统 SHALL 签名与本 patch 前**逐字一致**：`cli/backtest.py:20` 为 `def main():`；`portfolio/cli.py:220` 为 `def main(argv: list[str] | None = None) -> int:`；`factor_mining/cli.py:239` 为 `def main(argv: list[str] | None = None) -> int:`；`scheduler/cli.py:445` 为 `def main(args: list[str] | None = None) -> int:`
- **断言**:
  - 给定：4 个 CLI 源文件。
  - 当：`grep -n "^def main" src/trader_off/cli/backtest.py src/trader_off/portfolio/cli.py src/trader_off/factor_mining/cli.py src/trader_off/scheduler/cli.py` 执行。
  - 那么：返回 4 行匹配，行号与上述严格对应；签名模式分别匹配 `^def main\(\):` / `^def main\(argv: list\[str\] \| None = None\) -> int:$` / 同上 / `^def main\(args: list\[str\] \| None = None\) -> int:$`。
  - 断言：自定义 Python 脚本 `python scripts/check_cli_signatures.py`（M-DEV 阶段可即时生成）exit 0；脚本对 4 个文件做 AST 校验，确认 `FunctionDef.name == "main"` 且参数注解一致。

### AC-4

AC-NFR0100-04

- **WHEN** 检查 README 内容（兜底提及保留）
- **THEN** 系统 SHALL **至少保留 1 处**对 `python -m trader_off.<path>` 的引用（Out-of-Scope / 故障迁移说明 / 兼容性兜底段落任一），防止用户误以为该路径已被删除
- **断言**:
  - 给定：`README.md` 源文件。
  - 当：`grep -c "python -m trader_off" README.md` 执行。
  - 那么：计数 `>= 1`（与 AC-FR0100-05 的"≤1 主推用法消除"互补：主推用法清零，但兜底提及保留）。
  - 断言：`grep_count("python -m trader_off", README.md) >= 1`（≥1 表示兜底提及必须保留）。

---

## No Acceptance

无（本 spec 所有 FR/NFR 均有 AC 覆盖）。
