---
date: 2026-07-20
session: maestro-v0.2.0-001-m-e2e-advance
agents: [Maestro, Keeper]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: []
status: open
supersedes: []
---

## Topic
M-E2E holdpoint 收尾：Keeper gate 重跑 + 豁免生效后推进到 M-BUGFIX。

## Decision
- Keeper gate 重跑（不带 skip）仍 REJECT：唯一阻断项为 AC Trace FAIL（archer ci-scan 报 128 个 AC 未在 tests/e2e + tests/perf 引用）。
- 该阻断项与 waiver.json（2026-07-20T03:32:30Z, role=human）完全一致：e2e/perf 设计上只覆盖 happy-path 31/159 AC，其余由 unit+integration 覆盖。
- 指示 Keeper 以 `--skip-ac-trace` 重跑 gate → PASS（exit 0，8 个 commit-message medium 非阻断，anti-pattern PASS，R-G-R 0 findings）。gate-result.json verdict=pass @03:56:06Z。
- `lk agent maestro advance --stage M-E2E` 内部重跑 gate（无 skip 选项）仍 REJECT；按工具提示用 `--force` 推进：waiver accepted → M-BUGFIX。

## Tried but abandoned
- 直接 advance（不带 --force）：被内部 gate 重跑挡住。工具自身提示 --force 为豁免场景的正轨。

## Open questions
- M-BUGFIX 无任何 open bug issue（20 个 open issue 全是 FR/NFR Feature 跟踪票）→ 是否直接进入 M-SECURITY（Judge 审计，project.toml security_audit=enabled）待用户确认。
- 8 个 commit message format medium findings（devon/shield 前缀格式）未处理，非阻断。
- 工具改进点：keeper gate / maestro advance 不识别 waiver.json，需手工 --skip-ac-trace / --force，建议反馈给 lk 工具维护者。
- 会话前半段：agent 模型配置统一为 kimi-for-coding/k3 ×5 + deepseek/deepseek-v4-pro ×8（MiniMax-M2.7 超时不可用已移除）；改动未提交。
