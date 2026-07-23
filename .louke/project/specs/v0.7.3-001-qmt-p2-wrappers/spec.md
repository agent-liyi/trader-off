---
date: 2026-07-23
spec: v0.7.3-001-qmt-p2-wrappers
status: reviewing
locked: false
---

# v0.7.3 — qmt-gateway P2 wrappers (system management + API keys) — Spec

- **Spec ID**: v0.7.3-001-qmt-p2-wrappers
- **Created**: 2026-07-23
- **Status**: Reviewing

> This document describes requirements and boundaries. Observable pass conditions are in `acceptance.md`.

## User Stories

<a id="us-0010"></a>

### US-0010
story: As a researcher or LLM agent performing operations and credential management, I want `QmtGatewayBroker` to expose qmt-gateway system-management and API-key operations, so that I can programmatically inspect and maintain the gateway and manage credentials before trading.
priority: P1

## Usage Scenarios

### scenario-0010

A caller operating over a LAN against the Windows qmt-gateway uses `get_version()` and `check_version()`, starts an update with `start_update()`, polls with `get_update_status(task_id)`, and invokes `do_rollback()` if recovery is required. The caller, not the broker, controls polling, timeout, and confirmation of destructive operations.

### scenario-0020

An authenticated administrator creates a credential with `create_api_key(name)`, audits metadata with `list_api_keys()`, securely records the one-time plaintext returned by the gateway, and later revokes it with `revoke_api_key(key_id)`.

## Functional Requirements

<a id="fr-0100"></a>

### FR-0100 QmtGatewayBroker P2 wrappers (13 methods)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

Extend `src/trader_off/broker/qmt_gateway.py` (`QmtGatewayBroker`) with exactly 13 public methods wrapping the current upstream `zillionare/qmt-gateway` system-management and API-key endpoints. Endpoint paths and payload locations below were reconciled against upstream `main` (`qmt_gateway/apis/system.py`, `qmt_gateway/apis/api_keys.py`, and `docs/api.md`) after the user explicitly chose the upstream contract over conflicting short paths and query/body assumptions in Story `STR-0011`.

| Method | HTTP | Path | Request data | Return |
|---|---|---|---|---|
| `get_version()` | GET | `/api/system/version` | none | parsed JSON `dict`, unchanged |
| `check_version()` | POST | `/api/system/version/check` | none | parsed JSON `dict`, unchanged |
| `start_update()` | POST | `/api/system/update` | none | parsed JSON `dict`, unchanged; upstream success data contains `task_id` |
| `get_update_status(task_id)` | GET | `/api/system/update/status/{task_id}` | `task_id` interpolated into path | parsed JSON `dict`, unchanged |
| `do_rollback()` | POST | `/api/system/rollback` | none | parsed JSON `dict`, unchanged |
| `get_autostart()` | GET | `/api/system/autostart` | none | parsed JSON `dict`, unchanged |
| `set_autostart(enabled)` | POST | `/api/system/autostart` | form field `enabled` | parsed JSON `dict`, unchanged |
| `get_port()` | GET | `/api/system/port` | none | parsed JSON `dict`, unchanged |
| `get_firewall()` | GET | `/api/system/firewall` | none | parsed JSON `dict`, unchanged |
| `update_firewall(rules)` | POST | `/api/system/firewall` | form field `port=rules` | parsed JSON `dict`, unchanged |
| `create_api_key(name)` | POST | `/api/api-keys` | form field `name` | parsed JSON `dict`, unchanged; plaintext appears only in the creation response |
| `list_api_keys()` | GET | `/api/api-keys` | none | parsed JSON `dict`, unchanged; upstream `data` is a metadata list without plaintext/hash |
| `revoke_api_key(key_id)` | DELETE | `/api/api-keys/{key_id}` | `key_id` interpolated into path | parsed JSON `dict`, unchanged |

**Compatibility note for `update_firewall`**:

- The public method name and single parameter remain `update_firewall(rules)` as explicitly scoped by the user.
- Current upstream does not accept a rule collection or JSON body; it accepts one form field named `port`. Therefore this wrapper passes the `rules` argument unchanged as the value of form field `port`. The broker performs no conversion or validation. A future richer firewall-rules API is out of scope.

**Behavior and boundaries**:

- All 13 methods are thin wrappers: they return parsed gateway JSON unchanged and do not validate response schemas or interpret a nonzero JSON `code` when HTTP status is 200.
- `enabled`, `task_id`, `rules`, `name`, and `key_id` are passed through without broker-side type, emptiness, format, or range validation.
- `start_update`, `do_rollback`, `update_firewall`, and `revoke_api_key` add no broker-side confirmation gate. The caller is responsible for authorization and confirmation before invoking destructive operations.
- The inherited HTTP behavior applies uniformly: a non-200 response or network failure raises `RuntimeError`; the broker does not retry.
- Form payload support must preserve existing query-based wrappers. Internal helper changes are allowed only as necessary to send form data and DELETE requests; helper design is an implementation decision.
- Existing public methods must retain their signatures and observable behavior.
- System-management and API-key endpoints require an authenticated upstream session according to the current upstream contract; this FR adds no new authentication flow or session-cookie management. Existing broker authentication/header behavior remains unchanged.

**Out of scope**:

- Gateway deployment, Windows service management, upstream API changes, caching, retries, polling loops, timeouts beyond inherited client behavior, response transformation, local API-key storage/encryption, automatic key rotation, caller confirmation UI, and broader firewall-rule modeling.
- Changing existing wrapper methods or introducing new third-party dependencies.

---

## Non-Functional Requirements

<a id="nfr-0100"></a>

### NFR-0100 function-scope lazy imports and no new dependencies

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

The 13 new methods and any helper extension preserve the inherited function-scope lazy-import policy. No new module-level third-party import is introduced in `qmt_gateway.py`, and this patch adds no third-party dependency to project manifests or the lockfile. Existing `httpx` usage remains lazy and is reused for all HTTP methods and payload forms.

---

## Clarification Log

- **2026-07-23, round 1**: The user confirmed JSON thin-passthrough responses; no broker-side input validation; no confirmation gate for destructive operations; inherited `RuntimeError` behavior with no retries; and one GitHub Issue for FR-0100 only.
- **2026-07-23, upstream reconciliation**: Sage checked `zillionare/qmt-gateway` `main`. The upstream API uses `/api/system/*` and `/api/api-keys`, not Story short paths; `enabled`, `port`, and `name` are form fields. The user explicitly selected the upstream contract. For the scoped `update_firewall(rules)` signature, `rules` is passed as upstream form field `port` without transformation.
- All requirements in this draft reflect explicit user answers. No inline-discussion thread is open; self quote-check is expected to return exit code 0.
