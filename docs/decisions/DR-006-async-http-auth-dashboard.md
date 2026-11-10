# Decision Report: [DR-006] Async HTTP, Authentication & Dashboard

**Date:** 2026-11-10
**Status:** Accepted
**Author:** AI Agent & Engineering Team
**Related Milestone/Feature:** Phase 4 — Web Server & Dashboard UI
**Evidence Level:** Hardware accepted
**Tested Versions:** Python 3.15.2; MicroPython 1.29.0 ESP32_GENERIC; FRITZ!Box 6690 Cable, FRITZ!OS 8.25

---

## 1. Context & Problem Statement

The ESP32 dashboard must remain responsive during slow clients without loading
static assets or unbounded requests into the limited heap. Mutating WAN routes
must not be exposed before authentication and CSRF controls exist.

## 2. Technical Decision

- Accept one HTTP/1.1 request per connection with a whole-operation timeout,
  1 KiB line limits, 8 KiB total headers, and an 8 KiB body limit.
- Reject duplicate headers, request transfer encoding, malformed lengths,
  unsupported methods and non-ASCII protocol framing.
- Stream static files from Flash in 1 KiB chunks and emit explicit
  `Content-Length`; never materialize a full asset.
- Use an in-memory random session token in an HttpOnly, SameSite=Strict cookie.
  Require a separate random CSRF token for every mutating authenticated route.
- Hash the configured admin password immediately, compare digests in constant
  time, cap active sessions, and expire them by monotonic time.
- Refuse default, placeholder, short or empty web admin passwords.

## 3. Resource & Hardware Impact (ESP32 Constraints)

Request and file buffers are bounded. Each connection is an independent
`uasyncio` task, while router calls remain sequential to bound socket and heap use.
Sessions are capped at four by default and are not persisted across reboot.

## 4. Security & Fault Tolerance

Responses include `nosniff`, explicit length and closed connections. Dynamic
responses default to `no-store`. Authentication tokens and passwords are never
logged. HTTP remains LAN-only until the documented WireGuard phase; TLS is not
misrepresented as available.

## 5. Verification & Testing Results

Unit tests cover bounded request parsing, duplicate/malformed/oversized inputs,
security response headers, password policy, login, cookie/Bearer lookup, CSRF,
expiry and session cleanup.

Full host result after this milestone: **108 tests passed** on Python 3.15.2.

The API/dashboard milestone adds authenticated device discovery, timed block,
verified unblock, timer status and persistent schedule routes. All mutations
require the session cookie plus CSRF token. Static routes are exact allowlisted
paths, preventing traversal. The responsive single-page UI provides login,
device controls, timers and a weekly blocking editor without a framework.

Final host result: **114 tests passed** on Python 3.15.2.

Hardware acceptance deployed source, assets and the ignored configuration to the
ESP32 on COM3. The application connected to Wi-Fi, synchronized NTP, completed
empty-state recovery, opened the scheduler gate and listened on port 80. The
read-only `dashboard_probe` retrieved streamed HTML, logged in, read status,
timers and schedules, and enumerated all 33 router Hosts entries without issuing
any WAN mutation. Recovery and trusted clock both reported ready.

Live testing exposed three MicroPython-specific constraints and drove fixes:

- response bodies are streamed in 1 KiB chunks;
- HTTP timeout handling no longer references a missing global `TimeoutError`;
- Hosts discovery uses one-entry pages with GC before/after every HTTP response,
  preventing heap fragmentation and keeping other endpoints serviceable.

After the complete 33-device probe, stopping the event loop and running
`gc.collect()` reported 57,520 bytes free. This is a post-workload point
measurement, not a peak allocation measurement. The app was soft-reset and
restarted successfully afterward.

## 6. Alternatives Considered & Trade-offs

A third-party MicroPython web framework was rejected to keep heap use and parser
behavior explicit. Persistent sessions were rejected because reboot should
invalidate browser authority. Basic authentication was rejected because it
offers no independent CSRF token or logout semantics.

## 7. Next Steps

Proceed to Phase 5 session hardening and WireGuard documentation after user UI
acceptance. Do not expose port 80 directly to the public internet.

## 8. Traceability

- Roadmap: Phase 4.
- Modules: `src/net/http_server.py`, `src/api/auth.py`, `src/api/routes.py`,
  `src/main.py`, `www/`.
- Tests: `tests/test_http_server.py`, `tests/test_auth.py`,
  `tests/test_routes.py`.
- Hardware/read-only acceptance: `tools/dashboard_probe.py`.
