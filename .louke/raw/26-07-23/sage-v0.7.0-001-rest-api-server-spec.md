---
date: 2026-07-23
session: sage-v0.7.0-001-rest-api-server-spec
agents: [Sage]
spec: v0.7.0-001-rest-api-server
related_issues: ["#164", "#165", "#166"]
status: open
supersedes: []
---

## Topic
M-SPEC for v0.7.0 REST API server (FastAPI wrapping 14 CLI internal functions). Generate spec.md + acceptance.md, resolve quotes, create GitHub issues. Explicitly told NOT to record-lock.

## Decision
- spec.md + acceptance.md written at .louke/project/specs/v0.7.0-001-rest-api-server/ (2 FR + 1 NFR).
- 4 Step-1 questions resolved with user (all "Recommended"): (1) execution model = run_in_executor + sync response, no job-id/polling; (2) error envelope = AC-02 shape {"status":"error","code":N,"message":"..."} (delta from CLI --json data-wrapper); (3) GET/POST = /api/health + /status + /stock-list GET, rest POST; (4) schema scope = envelope + key params in spec, full schema deferred to interfaces.md.
- 2 inline-discussion quotes resolved with user: exit-code→HTTP mapping completed (0→200,1→500,3→422,other→500 on top of 2→422,4→400,5→500); --json startup shape = {"status":"ok","data":{"host":"<host>","port":<port>}}.
- Port default = 8000 (Human ruling on story §6; qmt-gateway v0.6.0 occupies :5800).
- scheduler/api.py NOT migrated; coexists (story §6 secondary).
- "14 functions" reconciled to 12 function endpoints + /api/health = 13 endpoints; import-existence verification deferred to M-DEV (story Risk #1, Devon).
- Anchors added (us-0010/us-0020/fr-0100/fr-0200/nfr-0100 in spec; ac-fr-0100/ac-fr-0200/ac-nfr-0100 in acceptance).
- quote-check exit 0 (is_ready: True, 2/2 threads resolved).
- Issues created + linked to Project #22: FR-0100→#164, FR-0200→#165, NFR-0100→#166 (label Feature).
- record-lock NOT run (per user instruction).

## Tried but abandoned
- Initial spec used template `>` blockquote notes ("Responsibility split"/"Format convention"/"Metadata fields"); lk discuss parser misread them as discussion threads (T-001/T-002/T-003 with bogus initiator names). Fixed by converting those notes to plain bold-lead paragraphs (no `>`). Lesson: inline-discussion reserves `>` blockquotes exclusively; never use `>` for non-discussion notes in spec files.
- Considered asking about the "14" endpoint count as a quote; instead reconciled to user-provided inventory (12+health=13) and logged it, since the user had explicitly enumerated endpoints.

## Open questions
- project.toml [.louke/project/project.toml] still shows version="v0.5.3" / project="trader-off-v0.5.3" while we are on releases/v0.7.0; project_id=22 is correct and issue linking succeeded. Stale version field is a Scout concern, flagged for follow-up but non-blocking.
- Lock not recorded (user deferred). spec is quote-clean + issues created; next stage (Lex verify / M-ARCH) can proceed, but formal lock awaits explicit record-lock --confirm.
- Per-endpoint request JSON schemas deferred to interfaces.md (Prism) — FR-0100 spec only carries envelope + representative params.
