---
date: 2026-07-23
session: prism-v0.7.3-001-mdev-r2
agents: [Prism]
spec: v0.7.3-001-qmt-p2-wrappers
related_issues: [#177]
status: resolved
---

## Topic
M-DEV R2 fast-track review of v0.7.3 P2 wrappers (2 commits: d2dacd06 + d7d0eec).

## Decision
**REJECT** — 1 blocker found.

**Blocker**: `update_firewall` in `src/trader_off/broker/qmt_gateway.py:447` sends form field `"rules"` instead of spec-mandated `"port"`, and JSON-encodes the value with `json.dumps()` against the spec directive "passes argument unchanged / performs no conversion". The test at line 622 validates the wrong behavior.

**Not blockers** (pre-existing across entire test file, not from this patch):
- 46 ac-missing findings (the entire file has no AC references — project convention)
- 11 mock-overuse findings (httpx mock is the established project pattern)
- 1 hardcoded-secret at line 64 (test fixture placeholder `api_key="secret123"`)

**Suggestions**: `list_api_keys` return type `list[dict]` should be `dict`; test mock shape inconsistent with AC-12; lazy `import json` inside `update_firewall` unnecessary if blocker fix removes json.dumps.

## Tried but abandoned
- Considered flagging `set_autostart` bool→string conversion as "coercion" — decided it's standard HTTP form encoding, not against spec spirit.
- Considered flagging `json_body` param in `_post`/`_request` as unused — decided it's reasonable future-proofing consistent with `form_data`.

## Open questions
None. Blocker is clear, fix is straightforward: change `form_data={"rules": _json.dumps(rules)}` to `form_data={"port": rules}` and update test assertion.
