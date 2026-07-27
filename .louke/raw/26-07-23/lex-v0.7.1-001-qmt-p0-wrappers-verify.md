---
date: 2026-07-23
session: lex-v0.7.1-001-qmt-p0-wrappers-verify
agents: [Lex]
spec: v0.7.1-001-qmt-p0-wrappers
related_issues: [#169, #170]
project: #23
status: open
supersedes: []
---

## Topic
Three-stage verification of spec v0.7.1-001-qmt-p0-wrappers: spec review, issue schema validation, and project association.

## Decision

### Stage 1: Spec Review — PASS
- verify-acceptance L1-L5: all 5 checks passed (exit 0)
- Semantic review: all 8 ACs assertable with observable metrics, FR/NFR faithful to story STR-0009
- quote-check --check-ready: exit 0 (no prior unresolved threads)

### Stage 2: Issue Verification — 1 BLOCKER
- verify-issue tool reports L5/L7 failures for both issues, but manual review confirms anchors exist in both files. Tool likely has anchor detection bug (reports "declared FR anchors: []" despite `<a id="fr-0100">` and `<a id="nfr-0100">` present).
- **Issue #169 (FR-0100)**: All 8 checks pass on manual review. Title, Requirement ID, Spec Link, anchor, AC URL all correct.
- **Issue #170 (NFR-0100)**: L7 BLOCKER. AC field is literal `None` but acceptance.md contains `<a id="ac-nfr-0100">` with 2 ACs (AC-NFR0100-01, AC-NFR0100-02). Sage must update #170 AC field to `acceptance.md#ac-nfr-0100` since ACs are already written and assertable.
- Blocker quote T-001 added at spec.md anchor_line=70

### Stage 3: Project Association — PASS
- verify-project exit 0
- Both issues (#169, #170) are associated with Project #23 (trader-off-v0.7.1)

## Tried but abandoned
- Reading verify_issue_schema.py source to debug anchor detection — external directory access denied
- Running verify-issue with --branch releases/v0.7.1 — same false negatives
- Using gh API direct fetch confirmed anchors exist identically in both local and GitHub versions

## Open questions
- Root cause of verify-issue anchor detection failure: tool says "declared FR anchors: []" but `<a id="fr-0100">` clearly present in both local and remote spec.md. Possible regex mismatch in louke 0.10.0 version.
- Sage needs to fix Issue #170 AC field and potentially re-run verify-issue
