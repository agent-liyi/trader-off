---
date: 2026-07-23
spec: v0.7.1-001-qmt-p0-wrappers
status: reviewing
---

# v0.7.1 — qmt-gateway P0 wrappers (connection + stock search) — Spec

- **Spec ID**: v0.7.1-001-qmt-p0-wrappers
- **Created**: 2026-07-23
- **Status**: Reviewing

> **Responsibility split**: This document only describes the requirements themselves (FR/NFR descriptions + metadata).
> Acceptance criteria (observable, assertable pass conditions) live in `acceptance.md` so they can grow without bloating spec.
> The test plan (`test-plan.md`) references both spec.md and acceptance.md as inputs.

## User Stories

<a id="us-0010">

### US-0010
story: As a researcher / LLM agent, I want `QmtGatewayBroker` to expose connection probing and stock-search methods, so that I can confirm the gateway is online and look up trading targets before placing orders.
priority: P0

## Usage Scenarios

### scenario-0010

Programmatic flow (non-UI), single-process, mid-frequency on-demand, over LAN to the Windows qmt-gateway (default `:5800`):

1. `broker.get_connection_status()` → confirm `{"connected": True}` before any trade.
2. `broker.search_stocks("平安")` → candidate list `[{symbol, name, market}, ...]`.
3. `broker.get_stock_info(symbol)` → detail dict for the chosen target.
4. (optional) `broker.get_all_stocks()` → full instrument list (large payload; broker passes through, does not paginate).
5. (recovery) `broker.restart_qmt(password)` → restart the gateway service when the connection drops.

## Functional Requirements

> **Format/numbering**: FR codes are 4-digit, zero-padded, starting at 100 in the initial draft (per `.louke/templates/spec.md`). AC reference: `AC-FRXXXX-YY` (see `acceptance.md`). The FR code is the permanent id of the requirement; never reused.

<a id="fr-0100">

### FR-0100 QmtGatewayBroker P0 wrappers (5 methods)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

Extend `src/trader_off/broker/qmt_gateway.py` (`QmtGatewayBroker`, v0.6.0) with 5 new methods wrapping qmt-gateway P0 endpoints. All methods reuse the existing `_get` / `_post` / `_request` helpers (non-200 → `RuntimeError`; network failure → `RuntimeError`), inheriting v0.6.0 error-handling and lazy-import behavior. **No changes to the existing 8 trading methods.**

New methods:

| Method | HTTP | Query params | Return (broker passthrough) |
|---|---|---|---|
| `get_connection_status()` | GET | — | parsed JSON (gateway contract: `{"connected": bool}`) |
| `restart_qmt(password)` | POST | `password` | parsed JSON (gateway restart result) |
| `search_stocks(q)` | GET | `q` | `list[dict]` (gateway contract: items carry `symbol`/`name`/`market`) |
| `get_stock_info(symbol)` | GET | `symbol` | parsed JSON `dict` (gateway-defined keys; broker does not validate schema) |
| `get_all_stocks()` | GET | — | `list[dict]` (full instrument list; broker does not paginate) |

**Boundary / constraints**:

- `restart_qmt` `password` is transmitted via URL query per gateway design; the broker MUST NOT write the query string (including the password) to any local log or file. The inherited `RuntimeError` from `_request` carries `response.text` (body) on non-200 and `str(RequestError)` on network failure — the latter may include the request URL; this is an inherited v0.6.0 behavior, documented here, not newly introduced (story §3.3 risk #2).
- Return shapes for `get_stock_info` / `get_all_stocks` are gateway-defined; the broker is a thin passthrough and does not validate or transform keys. Schema verification is deferred to M-DEV real-gateway comparison (story §3.3 risk #1).
- `get_all_stocks` payload may be large; the broker does not paginate or cache (story §3.3 risk #3).
- Out of scope: modifying the existing 8 trading methods; system management (update/rollback/firewall); API-key management; auction trading; minute-bar download (story §3 Avoid).

---

## Non-Functional Requirements

<a id="nfr-0100">

### NFR-0100 function-scope lazy imports (inherited)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

The 5 new methods reuse `_get` / `_post` (which lazy-import `httpx` inside function bodies via `_get_client` / `_request`). **No new module-level imports** are introduced by this change. `httpx` was already added as a dependency in v0.6.0; v0.7.1 introduces **no new third-party dependency**. This NFR is inherited unchanged from v0.6.0 NFR-0100.

---

## Clarification Log

- **2026-07-23 (Sage, M-SPEC)**: Story `STR-0009` provided EARS-format ACs (AC-01..AC-05) and explicit scope: 5 methods, reuse `_get`/`_post`, no new deps, no caching, no schema validation, `restart_qmt` password via query not locally logged. Risk register (story §3.3) defers endpoint signature/schema verification to M-DEV real-gateway comparison. Per the user's explicit M-SPEC task directive (generate → self-quote-check → create FR-0100 issue → do NOT lock), and given the story is fully specified with no open ambiguities, Sage skipped the interactive questioning round (system prompt Step 1) and proceeded directly to spec + acceptance draft. All FR/NFR items marked `Decided = ✅` based on explicit story content (not silence — see §3.2 silence-is-not-consent rule: the story itself is the user's explicit prior answer).
- **Open inline-discussion threads**: none (no `T-NNN` quotes raised; quote-check expected exit 0).
