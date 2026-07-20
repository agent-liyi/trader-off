---
date: 2026-07-20
session: shield-v0.2.0-001-batch5-crosscutting
agents: [Shield]
spec: v0.2.0-001-factor-mining-retrain-optimizer
related_issues: []
status: resolved
supersedes: []
---

## Topic
M-E2E Batch 5 — cross-cutting integration tests covering fixture manifest verification (NFR-0800 AC-3), per-module log file outputs (NFR-0600 AC-3), and scheduler API localhost-only binding (NFR-0700 AC-4).

## Decision

### Test files written
1. `tests/integration/test_fixture_manifest.py` — 4 tests
2. `tests/integration/test_log_files.py` — 6 tests
3. `tests/integration/test_api_security.py` — 6 tests

Total: 16 integration tests, all pass, lint clean.
Commit: `4c8a600`

### Key decisions
- **fixture manifest**: Read MANIFEST.json directly, compute SHA256 for each listed file, compare. Tampered detection test copies fixture to tmp_path, flips a byte, verifies hash mismatch. Missing file detection iterates all manifest entries and asserts existence. Well-formed test verifies JSON structure and 64-char hex SHA256 fields.
- **log files**: Used `setup_logger(module, log_dir, format)` from `utils/logging.py`. Verified per-module log file naming (`{module}_YYYY-MM-DD.log`), content contains initialization message, structured format regex match, auto-creation of non-existent log dir, JSON format emits valid JSON lines, ValueError on invalid format argument, and multiple module calls don't interfere.
- **api_security**: Started real aiohttp API server on random port bound to 127.0.0.1. Verified localhost connectivity succeeds (raw TCP + HTTP /health). Verified non-loopback IP connection fails (used `socket.gethostbyname_ex` to get machine's non-loopback IPs). Public IP test uses RFC 5737 TEST-NET-1 (192.0.2.1) which is guaranteed unroutable. Explicit 0.0.0.0 bind test with OS-permission skip fallback. Config-level assertions for default api_host=="127.0.0.1" and run_app signature default.

## Tried but abandoned
- **1.1.1.1 for public IP test**: Originally used `1.1.1.1` as the "external" IP to test rejection. But on this macOS environment, `socket.create_connection(("1.1.1.1", port))` actually succeeded (likely VPN/local proxy intercept). Switched to `192.0.2.1` (RFC 5737 TEST-NET-1) with a skip fallback if even that is reachable.
- **socket.timeout alias**: Used `socket.timeout` in exception handler, ruff UP041 flagged it. Changed to `TimeoutError` (builtin in 3.11+).

## Open questions
- None.
