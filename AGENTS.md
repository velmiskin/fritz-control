# FritzControl — AI Coding Agent Instructions

## 1. Project Overview & Target Hardware
- **Device:** ESP32-WROOM-32E (4MB Flash, 520KB SRAM, ~100–180KB free RAM in MicroPython heap).
- **Firmware:** MicroPython (v1.20+).
- **Target Router:** AVM FRITZ!Box 6690 Cable (FRITZ!OS 7.50+ / 8.0+).
- **Protocol:** TR-064 over HTTP/HTTPS (SOAP 1.1).
- **Primary Goal:** Automated and manual parental/access control: device discovery, per-device internet WAN blocking/unblocking, timed access (15m, 30m, 1h, custom), weekly schedules, persistent state recovery across reboots, responsive web dashboard, secure remote access via WireGuard.

---

## 2. Core Development Rules (Strictly Enforced)

### Rule 1: One Milestone at a Time + Mandatory Decision Report
- Never implement multiple phases or unrelated features in a single prompt/turn.
- **After completing each feature/milestone:**
  1. Verify the code with tests (mock tests in `tests/` or hardware verification).
  2. Create a new Decision Report in `docs/decisions/DR-XXX-<feature-name>.md` based on `docs/decisions/TEMPLATE.md`.
  3. Update `ROADMAP.md` (check off items and link the Decision Report).
  4. Present the decision summary and verification results to the user before moving to the next task.
- A green CPython mock suite does not imply ESP32 or router acceptance. Report evidence as one of: design only, unit/mock tested, transport tested, or hardware accepted.
- Never state estimated RAM usage, latency, compatibility, or hardware behavior as an observed result. Record the measurement method and tested versions for observed claims.

### Rule 2: MicroPython & Memory Constraints
- Target platform is **MicroPython** on microcontroller hardware.
- **NEVER** import desktop CPython libraries: no `requests`, no `urllib3`, no `xml.etree.ElementTree`, no `lxml`, no `pydantic`.
- Minimize heap allocations:
  - Do NOT load multi-megabyte XML or HTML strings into RAM.
  - Parse SOAP XML using targeted string searches, generators, or tiny stream-based parsers.
  - Serve static web files (`www/`) directly from Flash in chunks (e.g. 1024 bytes) without reading whole files into RAM.
  - Explicitly trigger `gc.collect()` after large network operations.

### Rule 3: Async & Non-Blocking Event Loop
- All I/O (HTTP server, TR-064 requests, timers) must run on `uasyncio`.
- Sockets must be non-blocking with explicit timeouts (`uasyncio.wait_for(...)`).
- A slow router response or dropped packet must NEVER freeze the web UI or background watchdog.

### Rule 4: TR-064 Protocol Authenticity
- **NEVER invent TR-064 services, actions, or XML parameters.**
- All SOAP calls must strictly adhere to official AVM specifications:
  - `urn:dslforum-org:service:Hosts:1` (Device listing, hostname, MAC, IP, online status).
  - `urn:dslforum-org:service:X_AVM-DE_HostFilter:1` (WAN access blocking: `DisallowWANAccessByIP`, `GetWANAccessByIP`).
- Always check the HTTP status code and parse `<detail>` in SOAP Fault responses.
- Router changes take effect asynchronously; always verify device WAN status after executing a block/unblock command.
- Check `docs/references/README.md` and the target router's live SCPD. Optional actions must be capability-detected instead of inferred only from a FRITZ!OS version.
- For unblock operations, distinguish clearing `NewDisallow` from effective `NewWANAccess="granted"`; a filter profile can continue to deny WAN access.

### Rule 5: Security & Reboot Behavior
- Secrets (`config.json`, Wi-Fi credentials, FRITZ!Box passwords) must NEVER be committed to Git or printed in logs/UART console.
- **Fail-safe Reboot Rule:** If ESP32 reboots (power outage, watchdog trip), it must **NEVER** automatically unblock devices. It must restore scheduled timers from persistent storage, synchronize time via NTP, and reconcile the router's actual state before performing any WAN actions.

---

## 3. Directory Layout & Module Responsibilities

```text
FritzControl/
├── docs/
│   ├── decisions/       # Decision Reports (DR-001-..., DR-002-...)
│   │   └── TEMPLATE.md  # Template for all decision reports
│   └── references/      # AVM TR-064 documentation and specs
├── src/                 # Code deployed to ESP32 Flash
│   ├── boot.py          # Early boot, pin initialization, safety checks
│   ├── main.py          # Entrypoint, asyncio loop initialization
│   ├── core/            # System services: config, storage (NVS/JSON), logger, watchdog
│   ├── fritz/           # TR-064 SOAP client, Hosts:1, HostFilter:1 parsers
│   ├── network/         # Wi-Fi manager (STA/AP fallback), NTP client, async HTTP server
│   ├── services/        # Business logic: device_manager, access_manager, scheduler, recovery
│   └── api/             # REST API routes and token/cookie auth
├── www/                 # Frontend assets stored in Flash (HTML, CSS, JS)
├── tests/               # Local Python unit tests and TR-064 mock suite
├── tools/               # Host-side tools for flash, backup, and upload (mpremote, esptool)
├── AGENTS.md            # This instruction file
├── ROADMAP.md           # Progress tracker and milestone checklists
└── config.example.json  # Safe configuration template
```

---

## 4. Verification Workflow for AI Agents
When working on code:
1. Write/modify code in `src/`.
2. Write corresponding tests in `tests/` with mock responses (simulating FRITZ!Box SOAP endpoints).
3. Run tests using `python -m pytest tests/` or custom runner.
4. Document the completed feature in `docs/decisions/DR-XXX-<name>.md`.
5. Check off the corresponding box in `ROADMAP.md`.

For transport, timing, persistence, or memory-sensitive work, CPython unit tests are necessary but insufficient. Add the relevant transport tests and record target-hardware verification, or leave hardware acceptance explicitly pending.
