# Decision Report: [DR-006] Async HTTP, Authentication & Dashboard

**Date:** 2026-11-10
**Status:** Accepted (HTTP/auth foundation; API/dashboard acceptance pending)
**Author:** AI Agent & Engineering Team
**Related Milestone/Feature:** Phase 4 — Web Server & Dashboard UI
**Evidence Level:** Unit tested
**Tested Versions:** Python 3.15.2; MicroPython hardware acceptance pending

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
`uasyncio` task, but the future integration will keep router calls sequential.
Sessions are capped at four by default and are not persisted across reboot.

## 4. Security & Fault Tolerance

Responses include `nosniff`, explicit length and closed connections. Dynamic
responses default to `no-store`. Authentication tokens and passwords are never
logged. HTTP remains LAN-only until the documented WireGuard phase; TLS is not
misrepresented as available.

## 5. Verification & Testing Results

Unit tests cover bounded request parsing, duplicate/malformed/oversized inputs,
security response headers, password policy, login, cookie/Bearer lookup, CSRF,
expiry and session cleanup. API, frontend and ESP32 hardware verification remain
pending in the next Phase 4 step.

Full host result after this milestone: **108 tests passed** on Python 3.15.2.

## 6. Alternatives Considered & Trade-offs

A third-party MicroPython web framework was rejected to keep heap use and parser
behavior explicit. Persistent sessions were rejected because reboot should
invalidate browser authority. Basic authentication was rejected because it
offers no independent CSRF token or logout semantics.

## 7. Next Steps

Add authenticated REST routes, the streamed dashboard assets and application
entrypoint integration, then deploy to ESP32 for LAN acceptance.

## 8. Traceability

- Roadmap: Phase 4.
- Modules: `src/net/http_server.py`, `src/api/auth.py`.
- Tests: `tests/test_http_server.py`, `tests/test_auth.py`.
