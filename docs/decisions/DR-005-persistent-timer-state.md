# Decision Report: [DR-005] Persistent Timer State Foundation

**Date:** 2026-11-10
**Status:** Accepted
**Author:** AI Agent & Engineering Team
**Related Milestone/Feature:** Phase 3 — persistent active timer state
**Evidence Level:** Unit tested; hardware persistence acceptance pending
**Tested Versions:** Python 3.15.2; MicroPython API compatibility designed for 1.29.0

---

## 1. Context & Problem Statement

Active access timers must survive an ESP32 reboot without ever causing an
unverified automatic unblock. Flash writes must be bounded and avoided when the
logical state has not changed. Interrupted writes or corrupt JSON must not be
interpreted as an empty, safe-to-unblock state.

## 2. Technical Decision

- Store a versioned JSON document containing at most 64 active timers and cap it
  at 8 KiB.
- Persist only `state="blocked"` records with a validated IPv4 address and
  integer `blocked_at`/`unblock_at` epochs. Allowed or ambiguous states are
  rejected.
- Normalize entries by IP and skip Flash writes when the primary state is
  already identical.
- Write a temporary file, sync it, move the previous primary to `.bak`, then
  rename the temporary file into place. Restore the primary if the last rename
  fails.
- Load the primary first and fall back to the previous valid backup. If files
  exist but neither validates, raise `StorageError`; never silently return an
  empty state.
- Keep storage passive. It records facts but performs no router operation;
  recovery will later reconcile time and actual WAN state before any action.

## 3. Resource & Hardware Impact (ESP32 Constraints)

- State input is bounded to 8 KiB before JSON parsing and to 64 timer entries.
- Serialization temporarily allocates one bounded JSON string. No DOM or desktop
  library is used.
- Unchanged state produces no Flash write. A changed state writes one temporary
  file and uses rename operations for recovery boundaries.
- No network I/O or event-loop blocking is introduced by this storage-only step.
  Writes are synchronous and must later be kept outside latency-sensitive HTTP
  request handling.

## 4. Security & Fault Tolerance

- The state contains no Wi-Fi or router credentials.
- Invalid IPv4 values, duplicate devices, unsupported schema versions, invalid
  times and non-blocked state are rejected.
- Missing storage means no known active timers. Corrupt existing storage raises
  an error so recovery can remain fail-closed and leave router state unchanged.

## 5. Verification & Testing Results

- Commands: `python -m pytest tests/` and
  `python -m compileall -q src tools tests`.
- Tests cover missing state, deterministic round trips, write suppression,
  normalization, previous-version backup, corrupt-primary fallback, rejection
  of corrupt/unsafe data, and restoration after a simulated atomic-replace
  failure.
- Full host result: **64 tests passed** on Python 3.15.2.
- Hardware Flash/power-cut verification has not yet been performed.

## 6. Alternatives Considered & Trade-offs

- NVS was deferred because variable-length timer records and host-side testing
  are simpler with bounded JSON. JSON costs a small bounded allocation.
- Returning an empty state on corruption was rejected because it loses evidence
  required for safe recovery.
- Persisting an `allowed` state was rejected because reboot recovery must never
  infer permission to unblock from stale storage.

## 7. Next Steps

Implement NTP synchronization and an access manager that writes a blocked timer
only after router-side blocking has been verified. Recovery must reconcile the
stored state, trusted time, and actual router WAN state before unblocking.

## 8. Traceability

- Roadmap: Phase 3, `src/core/storage.py`.
- Tests: `tests/test_storage.py`.
