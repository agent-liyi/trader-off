---
name: lk-reserve-memory
description: When finishing a louke agent work session that produced decisions, abandoned options, or open questions, save a raw session note for later distillation into wiki knowledge.
license: MIT
compatibility: opencode
metadata:
  audience: agents
  workflow: louke
---

## What I do

I guide you to save a raw session memory file after each louke agent work session. Raw notes preserve trial-and-error and unresolved questions so that Librarian can later distill them into wiki knowledge.

## When to use me

- End of any agent work session
- The session produced non-trivial decisions
- The session tried options that were abandoned
- The session leaves open questions for the next round

## Where to write

```
.louke/raw/{yy-mm-dd}/{session-id}.md
```

- `yy-mm-dd` = session date
- `session-id` = `{agent}-{spec-id-or-phase}-{topic}`
  - Example: `devon-v0.1-001-task-impl`

## File format

Required frontmatter:

```markdown
---
date: 2026-06-27
session: devon-v0.1-001-task-impl
agents: [Devon, Prism]
spec: v0.1-001-init-adopt-mode
related_issues: [#142, #143]
status: resolved | superseded | open
supersedes: []
---
```

Required sections:

```markdown
## Topic {what was being decided}
## Decision {conclusion, commands/files/specs}
## Tried but abandoned {rejected options and why}
## Open questions {left for next round}
```

## Rules

1. `status` is required. Empty means `open`.
2. Raw notes do not go into git.
3. Do not mix raw notes with wiki content.
4. Write before returning results, but do not block the main flow.
5. When superseding another session, add `superseded-by` to the old entry.

## Mistakes to avoid

- Saving raw notes under git
- Leaving `status` empty
- Writing wiki-style summaries instead of raw decision history
