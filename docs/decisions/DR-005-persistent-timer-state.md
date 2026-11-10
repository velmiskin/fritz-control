# Decision Report: [DR-005] Persistent State & Trusted Time Foundations

**Date:** 2026-11-10
**Status:** Accepted
**Author:** AI Agent & Engineering Team
**Related Milestone/Feature:** Phase 3 — persistent active timer state and trusted UTC
**Evidence Level:** Unit tested; live ESP32 DNS/NTP accepted; hardware persistence acceptance pending
**Tested Versions:** Python 3.15.2; MicroPython 1.29.0 ESP32_GENERIC

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
- Resolve configured NTP hostnames through a bounded asynchronous DNS A query;
  no blocking `getaddrinfo()` or `ntptime` call is used.
- Exchange NTPv4 packets over a non-blocking UDP socket with explicit timeout,
  retry count and cooperative polling. Validate leap status, mode, stratum and
  the echoed originate token before accepting the transmit timestamp.
- Keep the RTC in UTC. Convert NTP time independently of the port-specific
  MicroPython epoch and support the NTP era rollover after 2036.
- Require trusted synchronized time and readable timer storage before changing
  router state. Persist a timer only after the router verifies the blocked state.
- When persistence fails after a verified block, leave the device blocked and
  surface an explicit reconciliation error; never compensate by unblocking.
- For unblocking, verify effective WAN access first and remove the timer second.
  A cleanup failure leaves a stale blocked record, which is safer than losing a
  still-blocked timer.
- Keep the scheduler WAN-inert until recovery explicitly opens its gate. Model
  weekly policies as non-overlapping local-time blocking intervals, with Monday
  as day zero and a fixed configured UTC offset.
- Give active timers priority over weekly allow periods. When a timer expires
  during a weekly block, delete only its record and keep WAN blocked, avoiding a
  transient unblock.

## 3. Resource & Hardware Impact (ESP32 Constraints)

- State input is bounded to 8 KiB before JSON parsing and to 64 timer entries.
- Serialization temporarily allocates one bounded JSON string. No DOM or desktop
  library is used.
- Unchanged state produces no Flash write. A changed state writes one temporary
  file and uses rename operations for recovery boundaries.
- Storage writes are synchronous and must later be kept outside latency-sensitive
  HTTP request handling. DNS and NTP sockets are non-blocking and yield to
  `uasyncio` between attempts.

## 4. Security & Fault Tolerance

- The state contains no Wi-Fi or router credentials.
- Invalid IPv4 values, duplicate devices, unsupported schema versions, invalid
  times and non-blocked state are rejected.
- Missing storage means no known active timers. Corrupt existing storage raises
  an error so recovery can remain fail-closed and leave router state unchanged.
- DNS/NTP packets must match their random query/token, source endpoint and
  protocol invariants. RTC is updated only after the complete response validates.
- Timed access rejects unsynchronized clocks, corrupt storage, invalid durations,
  unverified router changes and durations outside 60 seconds through 7 days.

## 5. Verification & Testing Results

- Commands: `python -m pytest tests/` and
  `python -m compileall -q src tools tests`.
- Tests cover missing state, deterministic round trips, write suppression,
  normalization, previous-version backup, corrupt-primary fallback, rejection
  of corrupt/unsafe data, and restoration after a simulated atomic-replace
  failure.
- Full host result after the access-manager milestone: **81 tests passed** on
  Python 3.15.2.
- Full host result after the scheduler milestone: **90 tests passed** on Python
  3.15.2.
- NTP tests cover DNS A parsing, hostname resolution, matching request tokens,
  bounded retry/timeout behavior, UTC RTC conversion and leap-day handling.
- Access-manager tests cover block-before-persist ordering, trusted-time and
  storage gates, router failures, persistence failures, verified unblocking and
  duration bounds.
- Scheduler tests cover weekday/timezone calculation, interval validation, the
  closed recovery gate, due timers, timer/policy precedence, suppression of
  redundant router calls and retry after unverified changes.
- `python tools/hardware_ntp.py COM3 --config config.json` connected the target
  ESP32 to Wi-Fi, resolved the configured NTP hostname through the interface DNS
  server, accepted a stratum-2 response, and set the RTC to 2026 UTC. Observed
  free heap after `gc.collect()` was 97,360 bytes before connection and 96,832
  bytes after synchronization. The staging directory and temporary config were
  removed. Hardware Flash/power-cut verification remains pending.

## 6. Alternatives Considered & Trade-offs

- NVS was deferred because variable-length timer records and host-side testing
  are simpler with bounded JSON. JSON costs a small bounded allocation.
- Returning an empty state on corruption was rejected because it loses evidence
  required for safe recovery.
- Persisting an `allowed` state was rejected because reboot recovery must never
  infer permission to unblock from stale storage.
- MicroPython's blocking `ntptime` helper was rejected because a stalled DNS or
  UDP request must not freeze the future web UI and watchdog tasks.
- Applying the configured timezone offset to RTC was rejected; UTC avoids DST
  ambiguity and local conversion belongs at the API/UI boundary.

## 7. Next Steps

Implement recovery. It must synchronize time and reconcile every stored timer
with actual router WAN state before opening the scheduler gate.

## 8. Traceability

- Roadmap: Phase 3, `src/core/storage.py`, `src/net/ntp.py`,
  `src/services/access_manager.py`, `src/services/scheduler.py`.
- Tests: `tests/test_storage.py`, `tests/test_ntp.py`,
  `tests/test_access_manager.py`, `tests/test_scheduler.py`.
- NTP hardware runner: `tools/hardware_ntp.py`; device script:
  `tests/hardware/phase3_ntp.py`.
