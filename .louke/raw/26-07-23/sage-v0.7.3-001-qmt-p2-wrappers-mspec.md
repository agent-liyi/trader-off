---
date: 2026-07-23
session: sage-v0.7.3-001-qmt-p2-wrappers-mspec
agents: [Sage]
spec: v0.7.3-001-qmt-p2-wrappers
related_issues: [#177, #178]
status: resolved
supersedes: []
---

## Topic
M-SPEC clarification for qmt-gateway P2 system-management and API-key wrappers.

## Decision
- User selected current `zillionare/qmt-gateway` `main` as authoritative when Story endpoint paths and payload locations conflicted with upstream.
- Canonical endpoints use `/api/system/*` and `/api/api-keys`.
- Upstream form fields are used for autostart, firewall port, and API-key name.
- Scoped signature `update_firewall(rules)` is retained; its argument is passed unchanged as upstream form field `port`.
- Responses are parsed-JSON thin passthrough; no input validation, confirmation gate, retries, response-schema validation, or application-level code interpretation.
- Generated and committed `spec.md` and `acceptance.md`; quote-check passed with zero threads.
- `lk agent sage create-issues` unexpectedly created both FR #177 and NFR #178, despite the requested FR-only issue scope.
- `record-lock` was not run.

## Tried but abandoned
- Story short endpoints such as `/version`, `/check_version`, and `/api_key` were rejected after checking upstream source and documentation.
- JSON-body `rules` for firewall was rejected because current upstream accepts form field `port`.

## Open questions
- Maestro/user may need to decide whether unintended NFR issue #178 should be closed or otherwise corrected. Sage did not mutate it without explicit instruction.
