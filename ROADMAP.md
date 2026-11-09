# FritzControl — Development Roadmap & Progress Tracker

Every milestone must end with code verification, test passing, and a completed **Decision Report** in `docs/decisions/`.

---

## Progress Overview

| Phase | Description | Status | Decision Report |
|---|---|---|---|
| **Phase 0** | Project Structure, Environment & Agent Rules | 🟢 Completed | [DR-000](docs/decisions/DR-000-project-setup-and-agent-framework.md) |
| **Phase 0.1** | Development Workflow & Evidence Hardening | 🟢 Completed | [DR-003](docs/decisions/DR-003-development-workflow-and-evidence.md) |
| **Phase 1** | TR-064 Core & Device Discovery (`Hosts:1`) | 🟡 Mock-Tested | [DR-001](docs/decisions/DR-001-tr064-soap-client-and-device-discovery.md) |
| **Phase 2** | WAN Block / Unblock (`HostFilter:1`) | 🟡 Mock-Tested | [DR-002](docs/decisions/DR-002-wan-hostfilter-control.md) |
| **Phase 2.5** | TR-064 Transport, Semantics & Hardware Acceptance | ⚪ Not Started | - |
| **Phase 3** | Timers, Scheduling & State Persistence | ⚪ Not Started | - |
| **Phase 4** | Web Server & Dashboard UI | ⚪ Not Started | - |
| **Phase 5** | Security, Authentication & WireGuard Remote Access | ⚪ Not Started | - |
| **Phase 6** | Hardening, RAM Optimization & Watchdog | ⚪ Not Started | - |

---

## Detailed Milestone Backlog

### Phase 0: Project Setup & Agent Framework 🟢
- [x] Create project modular structure (`src/`, `docs/`, `www/`, `tests/`, `tools/`).
- [x] Configure `.gitignore` and `config.example.json` (prevent credential leakage).
- [x] Define `AGENTS.md` with hardware limits, rules, and Decision Report requirement.
- [x] Create `docs/decisions/TEMPLATE.md` for consistent feature documentation.
- [x] Initialize Git repository.
- [x] Create `tools/flash.py` and `tools/deploy.py` helper scripts for `mpremote`/`esptool`.
- [x] Complete **[DR-000](docs/decisions/DR-000-project-setup-and-agent-framework.md)**.

### Phase 0.1: Development Workflow & Evidence Hardening 🟢
- [x] Add README with setup, current status, security guidance and acceptance levels.
- [x] Pin the verified host-side toolchain and centralize pytest configuration.
- [x] Remove the known web password from the example configuration and ignore `.venv/`.
- [x] Add host-side CI for tests and CPython compilation checks.
- [x] Index normative FRITZ!/MicroPython references and remove the superseded raw design-session export.
- [x] Separate estimates, mock results, transport tests and hardware evidence in Decision Reports.
- [x] Complete **[DR-003](docs/decisions/DR-003-development-workflow-and-evidence.md)**.

---

### Phase 1: TR-064 Core & Device Discovery (`Hosts:1`) 🟡
- [x] Implement `src/core/config.py` (safe JSON config loader).
- [x] Implement `src/fritz/soap.py` (MicroPython lightweight SOAP 1.1 HTTP request generator & parser).
- [x] Implement `src/fritz/tr064.py` (TR-064 client with transparent HTTP Digest Authentication).
- [x] Implement `src/fritz/hosts.py` (`GetHostNumberOfEntries`, `GetGenericHostEntry`, `X_AVM-DE_GetSpecificHostEntryByIP`).
- [x] Create mock SOAP responses in `tests/mocks/` for local testing.
- [x] Write unit tests `tests/test_config.py`, `tests/test_soap.py`, and `tests/test_hosts.py`.
- [x] Complete **[DR-001](docs/decisions/DR-001-tr064-soap-client-and-device-discovery.md)**.
- [ ] Complete ESP32/router acceptance through Phase 2.5.

---

### Phase 2: WAN Access Control & Verification (`HostFilter:1`) 🟡
- [x] Implement `src/fritz/host_filter.py`.
- [x] Implement `DisallowWANAccessByIP` (block WAN access for IPv4).
- [x] Implement `GetWANAccessByIP` (query actual current WAN state).
- [x] Add post-command state verification loop (handling asynchronous router updates).
- [x] Add batch blocking/unblocking with rate limiting.
- [x] Write unit tests `tests/test_host_filter.py`.
- [x] Complete **[DR-002](docs/decisions/DR-002-wan-hostfilter-control.md)**.
- [ ] Complete effective-WAN and hardware acceptance through Phase 2.5.

### Phase 2.5: TR-064 Transport, Semantics & Hardware Acceptance ⚪
- [ ] Verify effective WAN state, not only the `NewDisallow` override flag.
- [ ] Treat missing, invalid and `WANAccess="error"` states as unknown/failure, never as allowed.
- [ ] Add byte-accurate HTTP framing, bounded response reads and explicit protocol errors.
- [ ] Add XML escaping, IPv4 validation and robust Digest challenge handling.
- [ ] Either implement and measure HTTPS on MicroPython or reject `use_ssl=true` explicitly.
- [ ] Add wire-level fake-router tests for 401, SOAP faults, timeouts and malformed responses.
- [ ] Capability-detect optional actions from the live router SCPD.
- [ ] Implement Wi-Fi connection and auto-reconnect required for hardware integration.
- [ ] Record ESP32 heap metrics and FRITZ!Box hardware acceptance with exact versions.
- [ ] Harden `tools/deploy.py` and `tools/flash.py` argument handling and success reporting.
- [ ] Complete **DR-004: TR-064 Transport & Hardware Acceptance**.

---

### Phase 3: Timers, Scheduling & State Persistence ⚪
- [ ] Implement `src/core/storage.py` (Flash NV-storage for active timer state).
- [ ] Implement `src/network/ntp.py` (NTP client for accurate time synchronization).
- [ ] Implement `src/services/access_manager.py` (15m, 30m, 1h, 2h, custom durations).
- [ ] Implement `src/services/scheduler.py` (day-of-week interval schedules).
- [ ] Implement `src/services/recovery.py` (fail-safe reboot recovery without inadvertent unblocking).
- [ ] Write unit tests `tests/test_scheduler.py` and `tests/test_recovery.py`.
- [ ] Complete **DR-005: Access Scheduling & Reboot Recovery**.

---

### Phase 4: Web Server & Dashboard UI ⚪
- [ ] Implement `src/network/http_server.py` (`uasyncio` streaming HTTP/1.1 server).
- [ ] Implement chunked static file serving from Flash (`www/`).
- [ ] Implement REST API in `src/api/routes.py` (`/api/devices`, `/api/block`, `/api/unblock`, `/api/timer`).
- [ ] Remove the runtime `admin` password default and refuse empty, placeholder or default credentials.
- [ ] Build responsive mobile-friendly UI:
  - `www/index.html` (Dashboard).
  - `www/devices.html` (Device table with toggles).
  - `www/schedules.html` (Schedule editor).
  - `www/settings.html` (System config).
- [ ] Test frontend memory impact on MicroPython heap.
- [ ] Include authentication and CSRF protection before exposing mutating API routes.
- [ ] Complete **DR-006: Async HTTP Server, Auth & Frontend UI**.

---

### Phase 5: Security, Authentication & WireGuard Access ⚪
- [ ] Review session expiry, credential rotation and audit logging after the authenticated Phase 4 API is complete.
- [ ] Add rate limiting and security regression tests for exposed endpoints.
- [ ] Configure WireGuard topology documentation (FRITZ!Box VPN endpoint vs ESP32 LAN).
- [ ] Write security tests `tests/test_auth.py`.
- [ ] Complete **DR-007: Security & Remote Access Architecture**.

---

### Phase 6: Production Hardening, Watchdog & RAM Optimization ⚪
- [ ] Implement `src/core/watchdog.py` (Hardware WDT with ping health check).
- [ ] Test long-running Wi-Fi/router disconnect and reconnect behavior; fallback AP requires an explicit security design.
- [ ] Optimize heap memory with `micropython.mem_info()` profiling and GC tuning.
- [ ] Perform power-cut and network disconnection resilience tests.
- [ ] Complete **DR-008: Production Hardening & Resource Optimization**.
