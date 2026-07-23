---
date: 2026-07-23
spec: v0.7.3-001-qmt-p2-wrappers
status: reviewing
---

# v0.7.3 — qmt-gateway P2 wrappers — Acceptance Criteria

- **Spec ID**: v0.7.3-001-qmt-p2-wrappers
- **Created**: 2026-07-23

> Each requirement has a dedicated section. Every `### AC-N` heading is intentionally undecorated; the canonical identifier is on the next line.

<a id="ac-fr-0100"></a>

## FR-0100 QmtGatewayBroker P2 wrappers (13 methods)

### AC-1
AC-FR0100-01
- **WHEN** `get_version()` is invoked and the gateway returns a successful JSON object
- **THEN** exactly one `GET /api/system/version` request is issued with no query or form data
- **AND** the parsed JSON object is returned unchanged

### AC-2
AC-FR0100-02
- **WHEN** `check_version()` is invoked and the gateway returns a successful JSON object
- **THEN** exactly one `POST /api/system/version/check` request is issued with no query or form data
- **AND** the parsed JSON object is returned unchanged

### AC-3
AC-FR0100-03
- **WHEN** `start_update()` is invoked and the gateway returns `{"code":0,"data":{"task_id":"task-1"}}`
- **THEN** exactly one `POST /api/system/update` request is issued with no query or form data
- **AND** the complete parsed response, including `data.task_id`, is returned unchanged
- **AND** the broker performs no polling or confirmation step

### AC-4
AC-FR0100-04
- **WHEN** `get_update_status("task-1")` is invoked
- **THEN** exactly one `GET /api/system/update/status/task-1` request is issued with no query or form data
- **AND** the parsed JSON object is returned unchanged
- **AND** the broker does not validate or sanitize `task_id`

### AC-5
AC-FR0100-05
- **WHEN** `do_rollback()` is invoked
- **THEN** exactly one `POST /api/system/rollback` request is issued with no query or form data
- **AND** the parsed JSON object is returned unchanged
- **AND** the broker performs no confirmation step

### AC-6
AC-FR0100-06
- **WHEN** `get_autostart()` is invoked and the gateway returns `{"code":0,"data":{"enabled":true}}`
- **THEN** exactly one `GET /api/system/autostart` request is issued with no query or form data
- **AND** the complete parsed JSON object is returned unchanged

### AC-7
AC-FR0100-07
- **WHEN** `set_autostart(True)` is invoked
- **THEN** exactly one `POST /api/system/autostart` request is issued with form field `enabled=True` and no query parameter for `enabled`
- **AND** the parsed JSON object is returned unchanged
- **AND** the broker does not validate or coerce `enabled`

### AC-8
AC-FR0100-08
- **WHEN** `get_port()` is invoked and the gateway returns `{"code":0,"data":{"port":5800}}`
- **THEN** exactly one `GET /api/system/port` request is issued with no query or form data
- **AND** the complete parsed JSON object is returned unchanged

### AC-9
AC-FR0100-09
- **WHEN** `get_firewall()` is invoked and the gateway returns `{"code":0,"data":{"rule_exists":true}}`
- **THEN** exactly one `GET /api/system/firewall` request is issued with no query or form data
- **AND** the complete parsed JSON object is returned unchanged

### AC-10
AC-FR0100-10
- **WHEN** `update_firewall(5800)` is invoked
- **THEN** exactly one `POST /api/system/firewall` request is issued with form field `port=5800` and no JSON body or query parameter for the value
- **AND** the parsed JSON object is returned unchanged
- **AND** the broker does not validate, transform, or confirm the `rules` argument

### AC-11
AC-FR0100-11
- **WHEN** `create_api_key("agent-1")` is invoked and the gateway returns a response whose `data` contains `id`, `name`, `key_prefix`, and one-time `plaintext`
- **THEN** exactly one `POST /api/api-keys` request is issued with form field `name="agent-1"` and no query parameter for `name`
- **AND** the complete parsed response, including `data.plaintext`, is returned unchanged
- **AND** the broker does not persist, encrypt, redact, or log the plaintext as part of this method's required behavior

### AC-12
AC-FR0100-12
- **WHEN** `list_api_keys()` is invoked and the gateway returns a JSON object whose `data` is a list of API-key metadata
- **THEN** exactly one `GET /api/api-keys` request is issued with no query or form data
- **AND** the complete parsed JSON object is returned unchanged

### AC-13
AC-FR0100-13
- **WHEN** `revoke_api_key("key-1")` is invoked
- **THEN** exactly one `DELETE /api/api-keys/key-1` request is issued with no query or form data
- **AND** the parsed JSON object is returned unchanged
- **AND** the broker neither validates `key_id` nor performs a confirmation step

### AC-14
AC-FR0100-14
- **WHEN** any of the 13 methods receives an HTTP status other than 200
- **THEN** it raises `RuntimeError` containing the HTTP status and response text according to inherited `_request` behavior
- **AND** no retry is attempted

### AC-15
AC-FR0100-15
- **WHEN** any of the 13 methods encounters an `httpx.RequestError`, including connection, DNS, or timeout failure
- **THEN** it raises `RuntimeError` according to inherited `_request` behavior
- **AND** no retry is attempted

### AC-16
AC-FR0100-16
- **WHEN** the gateway returns HTTP 200 with valid JSON and a nonzero application-level `code`
- **THEN** the parsed response is returned unchanged rather than converted into a broker exception

### AC-17
AC-FR0100-17
- **WHEN** the public methods of `QmtGatewayBroker` are inspected after the patch
- **THEN** exactly the 13 scoped public methods are newly present: `get_version`, `check_version`, `start_update`, `get_update_status`, `do_rollback`, `get_autostart`, `set_autostart`, `get_port`, `get_firewall`, `update_firewall`, `create_api_key`, `list_api_keys`, and `revoke_api_key`
- **AND** pre-existing public method signatures and their observable request behavior remain unchanged

<a id="ac-nfr-0100"></a>

## NFR-0100 function-scope lazy imports and no new dependencies

### AC-1
AC-NFR0100-01
- **WHEN** the Python AST of `src/trader_off/broker/qmt_gateway.py` is inspected
- **THEN** every third-party import, including every `import httpx`, occurs inside a function body
- **AND** the patch introduces no new module-level third-party import

### AC-2
AC-NFR0100-02
- **WHEN** `pyproject.toml` and the dependency lockfile are compared before and after this patch
- **THEN** no third-party dependency is added for FR-0100
