---
date: 2026-07-23
spec: v0.7.2-001-qmt-p1-wrappers
status: reviewing
---

# v0.7.2 — qmt-gateway P1 wrappers (minutes download + quote/auction status) — Spec

- **Spec ID**: v0.7.2-001-qmt-p1-wrappers
- **Created**: 2026-07-23
- **Status**: Reviewing

*Responsibility split*: This document only describes the requirements themselves (FR/NFR descriptions + metadata). Acceptance criteria (observable, assertable pass conditions) live in `acceptance.md` so they can grow without bloating spec. The test plan (`test-plan.md`) references both spec.md and acceptance.md as inputs.

## User Stories

<a id="us-0010">

### US-0010
story: As a researcher / LLM agent, I want `QmtGatewayBroker` to expose minutes-download and quote/auction-status methods, so that I can pull historical minute bars and check market-data readiness before placing orders — closing the loop "probe → search → download minutes → check quote/auction → trade".
priority: P0

## Usage Scenarios

### scenario-0010

Programmatic flow (non-UI), single-process, mid-frequency on-demand, over LAN to the Windows qmt-gateway (default `:5800`):

1. `broker.get_connection_status()` → confirm `{"connected": True}` (v0.7.1).
2. `broker.get_quote_status()` → confirm WebSocket quote subscription is ready.
3. `broker.download_minutes(dates=["2026-07-22", "2026-07-23"])` → gateway starts an async job, returns a dict containing `job_id`.
4. `broker.get_minutes_job(job_id)` → poll the download progress dict until complete (caller controls polling interval/timeout; broker does not poll).
5. `broker.get_auction_status()` → check call-auction matching state (pre-open / pre-close).
6. Proceed to place orders via v0.6.0 trading methods.

## Functional Requirements

*Format/numbering*: FR codes are 4-digit, zero-padded, starting at 100 in the initial draft (per `.louke/templates/spec.md`). AC reference: `AC-FRXXXX-YY` (see `acceptance.md`). The FR code is the permanent id of the requirement; never reused.

<a id="fr-0100">

### FR-0100 QmtGatewayBroker P1 wrappers (4 methods)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

Extend `src/trader_off/broker/qmt_gateway.py` (`QmtGatewayBroker`, v0.6.0 + v0.7.1) with 4 new methods wrapping qmt-gateway P1 endpoints. All methods reuse the existing `_get` / `_post` / `_request` helpers (non-200 → `RuntimeError`; network failure → `RuntimeError`), inheriting v0.6.0 error-handling and lazy-import behavior. **No changes to the existing 13 methods** (8 trading v0.6.0 + 5 P0 v0.7.1).

New methods:

| Method | HTTP | Path / Query | Return (broker passthrough) |
|---|---|---|---|
| `get_minutes_job(job_id)` | GET | path `/minutes_job/{job_id}` | parsed JSON `dict` (download progress) |
| `download_minutes(dates)` | POST | query `dates` (list) | parsed JSON `dict` containing `job_id` |
| `get_quote_status()` | GET | — | parsed JSON `dict` (WebSocket quote subscription state) |
| `get_auction_status()` | GET | — | parsed JSON `dict` (call-auction matching state) |

**Boundary / constraints**:

- `get_minutes_job` interpolates `job_id` into the URL path (`f"/minutes_job/{job_id}"`); the broker is a thin passthrough and does not validate or sanitize `job_id` (consistent with v0.7.1's passthrough of `symbol` / `q`). The gateway contract for the progress dict is deferred to M-DEV real-gateway comparison (story §4 risk #1).
- `download_minutes` passes `dates` (a list) as a query param via the inherited `_post` → `params={"dates": dates}`; the broker does not serialize, batch, or validate the list. For large `dates` lists the URL may exceed gateway limits — the broker passes through as-is and the story (§4 risk #2) recommends callers batch externally; the broker does not enforce batching.
- `download_minutes` is an async job: the broker returns the full gateway JSON response (thin passthrough, same as all other methods), which contains `job_id`. The broker does **not** poll, does **not** impose a timeout, and does **not** extract/transform the `job_id` — the caller controls polling via `get_minutes_job` (story §3 constraint; §4 risk #3).
- Return shapes for `get_quote_status` / `get_auction_status` are gateway-defined; the broker is a thin passthrough and does not validate or transform keys. Schema verification deferred to M-DEV (story §4 risk #1).
- Out of scope: modifying the existing 13 methods; system management; API-key management (P2 → v0.7.3); caching; retry; polling loops; date validation (story §3 Avoid).

---

## Non-Functional Requirements

<a id="nfr-0100">

### NFR-0100 function-scope lazy imports (inherited)

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

The 4 new methods reuse `_get` / `_post` (which lazy-import `httpx` inside function bodies via `_get_client` / `_request`). **No new module-level imports** are introduced by this change. `httpx` was already added as a dependency in v0.6.0; v0.7.2 introduces **no new third-party dependency**. This NFR is inherited unchanged from v0.6.0 / v0.7.1 NFR-0100.

---

## Clarification Log

- **2026-07-23 (Sage, M-SPEC)**: Story `STR-0010` provided EARS-format ACs (AC-01..AC-04) and explicit scope: 4 methods, reuse `_get`/`_post`, no new deps, no caching/retry/polling, `download_minutes` is async (broker returns job_id, caller polls), `dates` passed as query (story §4 risk #2). Risk register (story §4) defers endpoint signature/schema verification to M-DEV real-gateway comparison. Per the user's explicit M-SPEC task directive (generate → self-quote-check → create FR-0100 issue → do NOT lock), and given the story is fully specified with no open ambiguities, Sage skipped the interactive questioning round (system prompt Step 1) and proceeded directly to spec + acceptance draft — consistent with the v0.7.1 precedent in this project. All FR/NFR items marked `Decided = ✅` based on explicit story content (not silence — see §3.2 silence-is-not-consent rule: the story itself is the user's explicit prior answer).
- **Interpretation note**: Story §3 says "broker 仅返 job_id" for `download_minutes`. Sage interprets this as a responsibility-scope statement (broker returns the gateway's job-initiation response containing `job_id`, and does not poll), consistent with the thin-passthrough pattern shared by all 13 existing methods — not as an instruction to extract `job_id` out of the response. The full gateway JSON dict is returned unchanged.
- **Open inline-discussion threads**: none (no `T-NNN` quotes raised; quote-check expected exit 0).
