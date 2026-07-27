---
date: 2026-07-23
session: devon-v0.7.3-001-qmt-p2-wrappers
agents: [Devon]
spec: v0.7.3-001-qmt-p2-wrappers
related_issues: [#177]
status: resolved
---

## Topic
Add 13 P2 methods to QmtGatewayBroker following the thin-passthrough pattern.

## Decision
- Extended `_post()` and `_request()` to accept optional `json_body: dict | None = None` parameter.
  - Only passes `json` to `client.request()` when `json_body is not None` to avoid breaking existing tests.
- Added 13 public methods:
  - System management (10): get_version, check_version, start_update, get_update_status,
    do_rollback, get_autostart, set_autostart, get_port, get_firewall, update_firewall
  - API key management (3): create_api_key, list_api_keys, revoke_api_key
- Wrote 14 unit tests (2 for set_autostart covering enabled/disabled).
- Total test count: 46 passed (32 existing + 14 new).
- Commit: 2dacd0678072a25fcc2731491833428ca8b4fe48
- Branch: releases/v0.7.3, pushed via force-with-lease (amend after pre-commit reformatting).

## Tried but abandoned
- Initially passed `json_body` as `json=json_body` unconditionally in `_request()`, which caused
  all existing tests to fail because they assert `params=None` only (no `json` kwarg appeared).
  Fixed by conditionally adding `json` only when `json_body is not None`.

## Open questions
- None.
