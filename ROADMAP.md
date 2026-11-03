# FritzControl — Development Roadmap & Progress Tracker

Every milestone must end with code verification, test passing, and a completed **Decision Report** in `docs/decisions/`.

---

## Progress Overview

| Phase | Description | Status | Decision Report |
|---|---|---|---|
| **Phase 0** | Project Structure, Environment & Agent Rules | 🟡 In Progress | [DR-000](docs/decisions/DR-000-project-setup-and-agent-framework.md) |
| **Phase 1** | TR-064 Core & Device Discovery (`Hosts:1`) | ⚪ Not Started | - |
| **Phase 2** | WAN Block / Unblock (`HostFilter:1`) | ⚪ Not Started | - |
| **Phase 3** | Timers, Scheduling & State Persistence | ⚪ Not Started | - |
| **Phase 4** | Web Server & Dashboard UI | ⚪ Not Started | - |
| **Phase 5** | Security, Authentication & WireGuard Remote Access | ⚪ Not Started | - |
| **Phase 6** | Hardening, RAM Optimization & Watchdog | ⚪ Not Started | - |

---

## Detailed Milestone Backlog

### Phase 0: Project Setup & Agent Framework 🟡
- [x] Create project modular structure (`src/`, `docs/`, `www/`, `tests/`, `tools/`).
- [x] Configure `.gitignore` and `config.example.json` (prevent credential leakage).
- [x] Define `AGENTS.md` with hardware limits, rules, and Decision Report requirement.
- [x] Create `docs/decisions/TEMPLATE.md` for consistent feature documentation.
- [ ] Initialize Git repository.
- [ ] Create `tools/flash.py` and `tools/deploy.py` helper scripts for `mpremote`/`esptool`.
- [ ] Complete **[DR-000](docs/decisions/DR-000-project-setup-and-agent-framework.md)**.

---

### Phase 1: TR-064 Core & Device Discovery (`Hosts:1`) ⚪
- [ ] Implement `src/core/config.py` (safe JSON config loader).
- [ ] Implement `src/fritz/soap.py` (MicroPython lightweight SOAP 1.1 HTTP request generator & basic auth/digest support).
- [ ] Implement `src/fritz/tr064.py` (TR-064 service descriptor parser & endpoint dispatcher).
- [ ] Implement `src/fritz/hosts.py` (`GetHostNumberOfEntries`, `GetGenericHostEntryByNewIndex` / `X_AVM-DE_GetHostList`).
- [ ] Create mock SOAP responses in `tests/mocks/` for local testing.
- [ ] Write unit tests `tests/test_soap.py` and `tests/test_hosts.py`.
- [ ] Complete **DR-001: TR-064 SOAP Client & Device Discovery**.

---

### Phase 2: WAN Access Control & Verification (`HostFilter:1`) ⚪
- [ ] Implement `src/fritz/host_filter.py`.
- [ ] Implement `DisallowWANAccessByIP` (block WAN access for IPv4).
- [ ] Implement `GetWANAccessByIP` (query actual current WAN state).
- [ ] Add post-command state verification loop (handling asynchronous router updates).
- [ ] Add batch blocking/unblocking with rate limiting.
- [ ] Write unit tests `tests/test_host_filter.py`.
- [ ] Complete **DR-002: WAN HostFilter Control & State Verification**.

---

### Phase 3: Timers, Scheduling & State Persistence ⚪
- [ ] Implement `src/core/storage.py` (Flash NV-storage for active timer state).
- [ ] Implement `src/network/ntp.py` (NTP client for accurate time synchronization).
- [ ] Implement `src/services/access_manager.py` (15m, 30m, 1h, 2h, custom durations).
- [ ] Implement `src/services/scheduler.py` (day-of-week interval schedules).
- [ ] Implement `src/services/recovery.py` (fail-safe reboot recovery without inadvertent unblocking).
- [ ] Write unit tests `tests/test_scheduler.py` and `tests/test_recovery.py`.
- [ ] Complete **DR-003: Access Scheduling & Reboot Recovery**.

---

### Phase 4: Web Server & Dashboard UI ⚪
- [ ] Implement `src/network/http_server.py` (`uasyncio` streaming HTTP/1.1 server).
- [ ] Implement chunked static file serving from Flash (`www/`).
- [ ] Implement REST API in `src/api/routes.py` (`/api/devices`, `/api/block`, `/api/unblock`, `/api/timer`).
- [ ] Build responsive mobile-friendly UI:
  - `www/index.html` (Dashboard).
  - `www/devices.html` (Device table with toggles).
  - `www/schedules.html` (Schedule editor).
  - `www/settings.html` (System config).
- [ ] Test frontend memory impact on MicroPython heap.
- [ ] Complete **DR-004: Async HTTP Server & Frontend UI**.

---

### Phase 5: Security, Authentication & WireGuard Access ⚪
- [ ] Implement session/token authentication in `src/api/auth.py`.
- [ ] Add CSRF protection and rate limiting to API endpoints.
- [ ] Configure WireGuard topology documentation (FRITZ!Box VPN endpoint vs ESP32 LAN).
- [ ] Write security tests `tests/test_auth.py`.
- [ ] Complete **DR-005: Security, Auth & Remote Access Architecture**.

---

### Phase 6: Production Hardening, Watchdog & RAM Optimization ⚪
- [ ] Implement `src/core/watchdog.py` (Hardware WDT with ping health check).
- [ ] Implement `src/network/wifi.py` with auto-reconnect and fallback AP mode.
- [ ] Optimize heap memory with `micropython.mem_info()` profiling and GC tuning.
- [ ] Perform power-cut and network disconnection resilience tests.
- [ ] Complete **DR-006: Production Hardening & Resource Optimization**.
