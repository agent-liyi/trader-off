---
date: 2026-07-22
session: sage-v0.5.4-001-agent-cli-input-blocked
agents: [Sage]
spec: v0.5.4-001-agent-cli
related_issues: []
status: open
supersedes: []
---

## Topic M-SPEC input validation and first-round clarification

## Decision
- M-SPEC is blocked before draft generation because `.louke/project/specs/v0.5.4-001-agent-cli/story.md` does not exist.
- `.louke/project/project.toml` still identifies v0.5.3, Project #14, spec `v0.5.3-001-backtest-on-real`, and branch `releases/v0.5.3`; Scout must update it for v0.5.4 and Project #15.
- User chose to repair these inputs before Sage continues.
- JSON contracts should freeze per-command data fields and status view schemas.
- Success exits 0; error envelope has `code: 4` and process exits 4.
- For existing CLIs without `--json`, only file outputs are guaranteed unchanged; terminal output and exit behavior are not required to remain unchanged.
- Missing status resources are represented as successful empty/stopped state; probe failures use the error envelope.
- Create two GitHub issues, one per FR; NFR is inherited by both.

## Tried but abandoned
- Drafting solely from the prompt was offered but rejected because the user chose to repair the formal inputs first.

## Open questions
- Await creation of story.md and correction of project.toml.
- Exact field names/types/nullability for each of the six existing CLI `data` payloads and all status views still need to be supplied or confirmed from the repaired story.
