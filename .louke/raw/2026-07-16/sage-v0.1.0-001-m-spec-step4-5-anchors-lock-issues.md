---
date: 2026-07-16
session: sage-v0.1.0-001-m-spec-step4-5-anchors-lock-issues
agents: [Sage]
spec: v0.1.0-001-lgbm-asset-pricing
status: resolved
related_issues: ["#6", "#7", "#8", "#9", "#10", "#11", "#12", "#13", "#14", "#15", "#16", "#17", "#18", "#19", "#20", "#21", "#22", "#23", "#24", "#25", "#26", "#27", "#28"]
supersedes: []
---

## Topic

Sage Step 4（添加 HTML anchors + record-lock）+ Step 5（创建 GitHub issues）。

## Decision

### Step 4 — HTML Anchors

- spec.md：添加 23 个 `<a id="fr-XXXX"></a>` / `<a id="nfr-XXXX"></a>` 锚点（FR-0100~FR-1600 + NFR-0100~NFR-0700）
- acceptance.md：添加 23 个 `<a id="ac-fr-XXXX"></a>` / `<a id="ac-nfr-XXXX"></a>` 锚点（与 spec.md 一一对应）
- commit: `c8b7053` (anchors) + `1b4dc0c` (lock metadata)

### Step 4 — record-lock

- 命令：`lk agent sage record-lock --spec v0.1.0-001-lgbm-asset-pricing --confirm`
- 5 个机械检查全部 PASS（L1 文件存在、L2 FR/NFR 章节对应、L3 AC 编号连续、L4 AC 内容非空、L5 反向覆盖）
- exit code: 0
- 输出："all 16 FR issues linked to https://github.com/users/agent-liyi/projects/3" + "locked: true"
- spec.md frontmatter 写入 `locked: true`、`locked-at: 2026-07-16T08:37:02Z`、`locked-by: lk agent sage record-lock`

### Step 5 — GitHub Issues

- 第一轮 `create-issues` 失败：仓库没有 `Feature` label，`--label Feature` 被 gh 拒绝且 stderr 被吞掉（lk 工具的 bug）
- 修复：用 `gh label create Feature --color 0e8a16 --description "Feature requirement from spec"` 创建 label
- 第二轮成功创建 23 个 issue：
  - FR-0100 ~ FR-1500 → #6 ~ #20（15 个 FR，已在第一轮因超时部分创建）
  - FR-1600 → #21（第二轮新增）
  - NFR-0100 ~ NFR-0700 → #22 ~ #28（7 个 NFR，第二轮新增）

### Issue Body Schema

每个 issue body 包含：
- `### Requirement ID`: FR-XXXX 或 NFR-XXXX
- `### Spec Link`: `https://github.com/agent-liyi/trader-off/blob/releases/v0.1.0/.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/spec.md#fr-XXXX`
- `### Acceptance Criteria`: `https://github.com/agent-liyi/trader-off/blob/releases/v0.1.0/.louke/project/specs/v0.1.0-001-lgbm-asset-pricing/acceptance.md#ac-fr-XXXX`
- Label: `Feature`（创建于仓库）

### Project Association

- 所有 23 个 issue 都已关联到 Project `trader-off-v0.1.0`（即 project_id = https://github.com/users/agent-liyi/projects/3）
- Project status 字段：所有 issue 当前 status = "Todo"

### 最终状态

- quote-check exit 0, is_ready: True ✅
- 23 个 issue 全部已创建并 link 到 Project #3 ✅
- spec.md `locked: true` ✅
- 全部 push 到 `releases/v0.1.0`

## Tried but abandoned

- ❌ 第一轮 `create-issues` 在 `--label Feature` 上失败：错误信息被 `stderr=subprocess.DEVNULL` 吞掉
- ❌ 手动重跑 `create-issues` 超时（120s）：因为串行创建 23 个 issue + 23 个 project item-add 调用，每次 ~3-5s

## Open questions (for next round)

- Project status 全部为 "Todo"，是否需要 Lex Stage 2 之后分配具体 status（In Progress / Done）？
- issue 创建过程中被超时中断，第一批 15 个 FR 已通过 `record-lock` 自动 link 到 project；第二批 8 个（FR-1600 + 7 NFR）通过 `create-issues` link。两条路径都成功但应该统一。
- M-SPEC 阶段已完成，等待 Lex Stage 2（verify-issue + verify-project）以及后续的 M-ARCH 阶段（Prism）。
