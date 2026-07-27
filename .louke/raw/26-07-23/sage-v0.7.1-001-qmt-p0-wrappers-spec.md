---
date: 2026-07-23
session: sage-v0.7.1-001-qmt-p0-wrappers-spec
agents: [Sage]
spec: v0.7.1-001-qmt-p0-wrappers
related_issues: [#169, #170]
status: open
supersedes: []
---

## Topic
M-SPEC for v0.7.1 patch: generate spec.md + acceptance.md for 5-method QmtGatewayBroker wrapper extension, self-quote-check, create FR-0100 issue, DO NOT lock.

## Decision
- Wrote spec.md (FR-0100 + NFR-0100, both Decided=✅) and acceptance.md (FR-0100: 6 ACs, NFR-0100: 2 ACs).
- Added HTML anchors: spec.md `<a id="fr-0100">`/`<a id="nfr-0100">`/`<a id="us-0010">`; acceptance.md `<a id="ac-fr-0100">`/`<a id="ac-nfr-0100">`.
- Skipped interactive questioning round (system prompt Step 1) per user's explicit task directive (story fully specified with EARS ACs + risk register). Documented in Clarification Log.
- Commits: `1332d8a` (initial draft), `3d94b27` (quote-check fix) on `releases/v0.7.1`.
- quote-check exit 0 (is_ready: True, 0 threads).
- Issues created: FR-0100 → #169 (label Feature), NFR-0100 → #170 (auto-linked by tool).
- Fixed #169 Acceptance Criteria field (was `None`, manually edited to acceptance.md#ac-fr-0100 URL via `gh issue edit`).
- Did NOT run record-lock (per user directive).

## Tried but abandoned
- Initial spec.md used `> **Label:**` blockquote notes (copied from template). The quote-check parser interpreted `> **Responsibility split:**` and `> **Format/numbering:**` as inline-discussion root comments (bold word = speaker name), creating 2 false-positive open threads → exit 1. Fixed by converting blockquotes to plain italic `*Label*:` paragraphs. Lesson: never use `> **Word:**` blockquote syntax in spec.md unless it's an actual inline-discussion thread.
- create-issues tool failed to detect acceptance.md AC section (set Acceptance Criteria=`None` despite `<a id="ac-fr-0100">` anchor present). Root cause unclear (format looks correct). Workaround: manually edited issue body via `gh issue edit`.

## Open questions
- Why did `lk agent sage create-issues` not detect the acceptance.md AC section? Anchor `<a id="ac-fr-0100">` is on its own line above `## FR-0100`. May need tool-side investigation or different anchor placement (same-line? no blank line?).
- NFR-0100 issue #170 was auto-created by the tool. User only asked for FR-0100 issue. Decide whether to close #170 (NFR is inherited, no implementation work) or keep for traceability.
- spec not locked — Lex verify-acceptance / verify-issue / verify-project have NOT run. When ready to lock, run `lk agent sage record-lock --spec v0.7.1-001-qmt-p0-wrappers --confirm`.
