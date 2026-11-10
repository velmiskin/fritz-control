# Decision Report: [DR-004] TR-064 Transport Hardening & ESP32 Smoke Validation

**Date:** 2026-11-10  
**Status:** Accepted  
**Author:** AI Agent & Engineering Team  
**Related Milestone/Feature:** Phase 2.5 — TR-064 Transport, Semantics & Hardware Acceptance  
**Evidence Level:** Transport tested; ESP32 smoke tested; live SCPD and block/unblock verified
**Tested Versions:** Python 3.15.2; MicroPython 1.29.0 ESP32_GENERIC; FRITZ!Box 6690 Cable, FRITZ!OS 8.25

---

## 1. Context & Problem Statement

The first TR-064 implementation passed service-level mocks but buffered complete
responses without a limit, calculated HTTP lengths from characters instead of
UTF-8 bytes, accepted ambiguous WAN states, built unescaped XML, and did not
exercise the HTTP transport. `use_ssl=true` selected a TLS port while still
opening plain TCP. The deployment tools also composed shell commands from user
arguments.

## 2. Technical Decision

- Limit SOAP responses to 16 KiB by default and SCPD documents to 32 KiB.
  Validate status/header framing and support bounded Content-Length, chunked and
  connection-close bodies.
- Apply a whole-request timeout in addition to individual asynchronous I/O
  timeouts. Invalid UTF-8, premature EOF, malformed status/headers and oversized
  bodies fail with `TR064Error`.
- Generate byte-accurate request lengths and reject CR/LF in request targets or
  headers.
- Parse Digest challenges with quoted commas, require MD5 plus optional
  `qop=auth`, preserve `opaque`, generate a fresh cnonce and reject a second 401.
- Escape XML text/attributes, accept namespace prefixes while parsing, and
  validate action names, parameter names and IPv4 addresses without desktop-only
  libraries.
- Define success as the requested `NewDisallow` value plus the effective
  `NewWANAccess` value. Clearing the override while a filter profile still denies
  access returns `verified=false` with `filter_profile_denied`.
- Fetch and parse live SCPD action lists before optional Hosts/HostFilter calls.
- Require the target IPv4 address twice in the host-side block and allow CLI;
  verify both the override flag and effective WAN state after every change.
- Reject HTTPS configuration explicitly. MicroPython 1.29 supports a TLS context,
  but the project has not yet defined certificate trust, time prerequisites or
  measured TLS heap use on this board.
- Rename the project package `network/` to `net/` because `network` is a built-in
  MicroPython module and cannot reliably act as the project package.
- Add a non-blocking STA Wi-Fi manager with explicit failure, timeout and
  application-level reconnect behavior.
- Replace shell-based flash/deploy commands with argument lists. Deployment now
  includes static assets, verifies uploaded paths and offers a dry run; flashing
  requires an explicit confirmation.

## 3. Resource & Hardware Impact (ESP32 Constraints)

- Responses are still materialized because service parsers consume text, but the
  allocation is bounded before reading. Chunk lists and their final duplicate
  join allocation were removed.
- Hardware smoke environment: ESP32-WROOM class board, `ESP32_GENERIC`,
  MicroPython 1.29.0, candidate modules loaded from `/phase25_smoke`.
- Observed after `gc.collect()` in the final smoke run:
  - before candidate imports: 146,624 bytes free;
  - after imports: 122,176 bytes free;
  - after XML, capability, Digest and async body checks: 116,800 bytes free.
- These are point observations from a staging run, not peak-production metrics.
  Wi-Fi was inactive and no TLS or router socket was opened.
- The staging directory was removed after the test; existing deployed firmware
  files were not overwritten.

## 4. Security & Fault Tolerance

- Missing/invalid WAN state and `WANAccess="error"` never default to allowed.
- Router passwords remain confined to Digest computation and are not logged.
- XML and HTTP header injection paths are rejected or escaped.
- HTTPS is not silently downgraded to plain TCP.
- Flash erase is guarded by an exact-port confirmation unless `--yes` is used.
- Wi-Fi errors do not include SSID passwords.

## 5. Verification & Testing Results

- Commands:
  - `python -m pytest`
  - `python -m compileall -q src tools tests`
  - `python tools/deploy.py --dry-run`
  - `python tools/hardware_smoke.py COM3`
  - `python tools/router_probe.py --host 192.168.178.1`
- Host result: **54 tests passed** on Python 3.15.2.
- Wire-level tests use a real local asyncio TCP server for Digest retry, UTF-8
  Content-Length, chunked responses, HTTP 500 SOAP Faults, malformed/oversized
  responses and timeouts.
- ESP32 result: import, XML escaping, SCPD parsing, IPv4 validation, Digest
  generation, bounded async body reading and explicit HTTPS rejection passed.
- Router result: the read-only project probe reached a FRITZ!Box 6690 Cable with
  FRITZ!OS 8.25 over port 49000. HostFilter advertised 10 actions and Hosts
  advertised 21; every action required by the current services was present.
- The initial isolated smoke kept Wi-Fi inactive and used no credential file.
  A later Phase 1 acceptance run temporarily staged the ignored configuration,
  connected the ESP32 to Wi-Fi, authenticated to the router, and completed
  read-only Hosts discovery. The staging directory was removed afterward.
- That live run exposed an unavailable `iso-8859-1` codec in MicroPython 1.29.0.
  HTTP response headers now use strict ASCII decoding and reject unexpected
  octets instead of depending on an optional codec.
- An authenticated attempt for the explicitly selected `192.168.178.30` was
  initially rejected because `admin` was not the hidden automatically generated
  FRITZ!Box username. The public AVM login endpoint identified the hidden last
  user and the ignored local configuration was corrected; neither username nor
  password is recorded in the repository.
- Before the authorised operation, `192.168.178.30` reported
  `disallow=false`, `wan_access=granted`. `DisallowWANAccessByIP` was sent once.
  A transient incomplete verification response exposed an asynchronous-state
  race; the retry loop now tolerates invalid intermediate states while remaining
  fail-closed. Independent and project-client reads then both confirmed
  `disallow=true`, `wan_access=denied`.
- After separate explicit user authorization, the allow operation was sent for
  the same address. Five immediate reads returned an incomplete transient state;
  a subsequent authenticated read confirmed `disallow=false` and
  `wan_access=granted`. The CLI verification window was therefore increased to
  ten attempts while preserving fail-closed handling of invalid responses.
- Phase 1 discovery, Phase 2 WAN control and the Phase 2.5 acceptance gates are
  complete on the target ESP32/router combination.

## 6. Alternatives Considered & Trade-offs

- Unbounded streaming XML parsing would reduce peak allocations further but add
  substantial parser complexity for small SOAP responses. Bounded materialization
  is the current compromise.
- Opportunistic TLS with certificate checks disabled was rejected because it
  would misrepresent confidentiality as authenticated transport.
- Keeping `network/` and manipulating `sys.path` was rejected because import
  behavior would remain fragile and board-dependent.
- Parallel batch requests remain rejected due to ESP32 socket and heap limits.

## 7. Next Steps

Begin the Phase 3 scheduling and reboot-recovery milestone, preserving the rule
that recovery must never unblock devices before time synchronization and router
state reconciliation.

## 8. Traceability

- Roadmap: Phase 2.5.
- Specifications: `docs/references/README.md`.
- Hardware smoke runner: `tools/hardware_smoke.py`; device script: `tests/hardware/phase25_smoke.py`.
- Hardware discovery runner: `tools/hardware_discovery.py`; device script:
  `tests/hardware/phase1_discovery.py`.
- Router probe: `tools/router_probe.py`.
- Live router SCPD paths: `/hostsSCPD.xml` and `/x_hostfilterSCPD.xml`.
