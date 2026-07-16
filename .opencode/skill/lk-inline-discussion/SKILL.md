---
name: lk-inline-discussion
description: Defines inline-discussion format for structured discussion in spec files. Use when agents need to leave traceable multi-round comments and query discussion status via lk discuss.
license: MIT
compatibility: opencode
metadata:
  audience: agents
  workflow: louke
---

## What I do

Defines the format specification for inline-discussion, when to use it, and the read/write tools.

### When to use inline-discussion?

- Clarifying FR/NFR boundaries with users or other agents
- Reviewing spec coverage, test plans, interfaces, or architecture
- Any multi-round discussion that must be traceable in project docs


## 1. Overview
**Inline Discussion** allows reviewers to initiate or participate in asynchronous discussion directly below specific content in a Markdown file. The entire discussion is nested using Markdown's native **Blockquote** syntax, requiring no additional frontend markup language, ensuring high readability in plain-text environments and friendliness for Git version tracking.

## 2. Core syntax definition

### 2.1 Discussion Node

A discussion node consists of a **Root Comment** and the **Nested Replies** below it.

- **Root comment (starting a new discussion)**: begins with **one** `>` symbol.
- **Reply comment**: for each reply level, **add one** `>` symbol on top of the existing `>` (i.e. add one level of indentation).

### 2.2 Comment line format

Each line of comment must follow this structure:

```markdown
> [indent level] **SpeakerName [status marker]:** comment content
```

| Component | Description |
| :--- | :--- |
| **Indent level** | Composed of consecutive `>` symbols (e.g. `>`, `>>`, `>>>`); the count represents nesting depth. |
| **SpeakerName** | A string wrapped in a pair of `**` (bold), representing the comment author (e.g. `**Sage**`). SpeakerName is case-insensitive (`Sage` / `sage` / `SAGE` are treated as the same speaker), but the original casing is preserved on display, with no case conversion. |
| **Status marker** | **Only allowed on root comment lines**, immediately following the speaker name, wrapped in `[` `]` (e.g. `[RESOLVED]`). Non-root comments (replies) must not contain this marker; the parser should ignore such markers on reply lines. |
| **Separator** | The speaker name (or status marker) must be immediately followed by an English colon `:`, then a single space, then the comment content. |
| **Comment content** | Any Markdown text, supporting basic inline syntax such as `@mentions`, inline code, bold, etc. |

## 3. State machine rules (determining "whether the discussion is complete")

To enable fast filtering in the next round of review, explicit status markers are introduced:

| State | Marker syntax | Triggered by | Description |
| :--- | :--- | :--- | :--- |
| **Open** | **Implicit default** (no marker) | System automatic | If the root comment line has no `[RESOLVED]`, the entire discussion tree is considered unfinished. |
| **Resolved** | `[RESOLVED]` | **Only** the initiator of that discussion (root comment author) | When the initiator is satisfied with the answer, they may edit their **root comment line** to add this marker. Once in effect, the entire discussion tree (including all child replies) is considered "closed" in subsequent reviews. |
| **Reopen** | `[REOPEN]` | Anyone | After the initiator marks it as resolved, someone else reopens it. |

> **Note:** When detecting state, the parser/renderer **only inspects the first-level indented (single `>`) root comment line**. The `[RESOLVED]` string in second-level and deeper nested replies should be treated as plain text, with no state-transition authority.


## 4. Discussion thread boundary definition

How to distinguish two different discussions? The rules are:

- **New thread start**: Whenever the parser encounters a **first-level indented (`>`)** comment line, and it is **not** immediately following another first-level indent as a reply, it is considered to start a brand-new Inline Discussion thread.
- **Thread ownership**: All **higher indent levels (`>>`, `>>>`, etc.)** after a first-level indented line belong to that thread, until the next new first-level indent (`>`) is encountered.


## 5. Standard syntax example

The following example demonstrates the complete syntax structure and the usage of status markers:

```markdown
# Original paragraph (discussion anchored below)

> **Sage [RESOLVED]:** What should happen when depth is zero?
>> **Maestro:** I don't know, need @Aaron's input.
>>> **Aaron:** Treat it as invalid input and return -1.

> **Aaron:** This is another thread, need help with the API.
>> **Sage:** I'll handle this later.
>> (Note: this thread's root comment has no `[RESOLVED]` marker; the system defaults it to `OPEN` state)
```

**Parsing result explanation:**

- **Thread 1**: initiated by `Sage`, status **Resolved (RESOLVED)**. Replies from `Maestro` and `Aaron` use `>>` and `>>>` indentation respectively.
- **Thread 2**: initiated by `Aaron`, root comment has no marker, status **Open (OPEN)**. `Sage`'s reply uses `>>` indentation.
- In Thread 1, Maestro also uses `@Aaron` mention to request Aaron to answer this question.

## 6. How to use inline-discussion

inline-discussion provides tools to find all inline-discussion sessions in a document, as well as various filtering tools.

### Find all discussions

```bash
lk discuss query --file <markdown-file>
```

The output is a JSON array in the following format:

```json
[
  {"thread_id": "T-001", "initiator": "Sage", "status": "RESOLVED", "last_speaker": "Aaron", "reply_count": 2, "snippet": "What should happen when depth is zero?",
   "total_lines": 230, "anchor_line": 45, "anchor_text": "User logs in with email + password. Password must be at least 8 characters.", "root_line": 47, "root_text": "Sage: What should happen when depth is zero?"},
  {"thread_id": "T-002", "initiator": "Aaron", "status": "OPEN", "last_speaker": "Sage", "reply_count": 1, "snippet": "This is another thread, need help with the API."}
]
```

**thread_id**: `T-NNN` format (per-file auto-increment sequence), **does not** contain location/content hash. Positioning is provided by the 5-tuple fields (`total_lines` / `anchor_line` / `anchor_text` / `root_line` / `root_text`); the agent passes them back to the parser when calling reply/edit/set-status for 4-level fallback lookup.

### Session filtering

1. Find all sessions initiated by `<Agent>`:
   ```bash
   lk discuss query --file <markdown-file> --initiator <agent>
   ```
2. Add status filter (`open` / `resolved` / `reopen`):
   ```bash
   lk discuss query --file <markdown-file> --initiator <agent> --status open
   ```
3. Add `--blocker` filter (find Open sessions waiting for a reply from a specific `<Agent>`):
   ```bash
   lk discuss query --file <markdown-file> --blocker <agent> --status open
   ```

### Start a discussion

```bash
lk discuss start --file <markdown-file> --anchor-line <N> --speaker <agent> "<message>"
```

`--anchor-line <N>` is the line number of the content being commented on (the agent obtains it from the `query` output or by reading spec.md itself). `lk` automatically reads that line's content as anchor_text; `<message>` is inserted after the first blank line following that line.

> Note: **No** new `lk discuss anchor` subcommand is added (decided in P1-NEW-2) — `start --anchor-line` is sufficient for the agent to choose an anchor.

### Reply to a session

```bash
lk discuss reply --file <markdown-file> --thread-id <id> \
  --anchor-line <N> --anchor-text "<text>" \
  --root-line <N> --root-text "<text>" \
  --speaker <agent> "<message>"
```

`lk` locates the session via `thread-id`; the 5-tuple positioning fields assist in locating the session even after the file changes. `<message>` is appended to the end of that session.
