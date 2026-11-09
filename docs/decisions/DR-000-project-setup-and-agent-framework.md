# Decision Report: [DR-000] Project Setup & Agentic Development Framework

**Date:** 2026-11-03  
**Status:** Accepted  
**Author:** AI Agent & Engineering Team  
**Related Milestone/Feature:** Phase 0 — Project Setup & Agent Framework

---

## 1. Context & Problem Statement
The FritzControl project aims to build an autonomous access control system running on an ESP32-WROOM-32E (MicroPython) to manage a FRITZ!Box 6690 Cable via TR-064 SOAP interfaces. Developing microcontroller firmware via autonomous AI coding agents carries substantial risks:
- Agents can hallucinate non-existent TR-064 SOAP actions or standard CPython libraries (`requests`, `lxml`) that exceed ESP32 SRAM.
- Large diffs can corrupt the `uasyncio` event loop or introduce blocking network calls.
- Lack of continuous documentation makes it difficult to audit decisions (e.g. how timers recover after power outages).

A rigid agentic framework with strict guardrails and mandatory post-feature decision reporting was required.

## 2. Technical Decision
1. **Modular Architecture:** Split the code into independent, loosely coupled layers:
   - `core/`: system primitives (config, storage, logger, watchdog).
   - `fritz/`: dedicated TR-064 protocol engine (SOAP generator, Hosts:1, HostFilter:1).
   - `network/`: Wi-Fi lifecycle, NTP time, and `uasyncio` HTTP server.
   - `services/`: higher-level business logic (device management, access timer state machine, weekly schedules, recovery).
   - `api/`: REST endpoints separating business logic from presentation.
   - `www/`: static web assets stored in Flash and streamed to clients.
2. **Mandatory Post-Feature Decision Reports:** Standardized `docs/decisions/TEMPLATE.md`. After completing each feature in `ROADMAP.md`, the agent must produce a Decision Report detailing memory usage, trade-offs, and verification before advancing to the next task.
3. **Local Testing Harness:** Created `tests/` with mock SOAP fixtures so logic and XML parsing can be tested in CI/CD or locally on Windows before flashing the physical MCU.

## 3. Resource & Hardware Impact (ESP32 Constraints)
- **RAM / SRAM:** MicroPython heap on ESP32-WROOM-32E typically leaves 100–180KB free. The project forbids loading full XML trees or entire web pages into RAM. Static files must be chunk-streamed from Flash.
- **Async Event Loop:** Zero blocking socket calls allowed. All network interaction must pass through `uasyncio` with strict timeouts.
- **Flash / NVS Storage:** NV storage operations must write only on state changes (not periodic polling) to preserve flash write cycles.

## 4. Security & Fault Tolerance
- **Secret Isolation:** Created `.gitignore` excluding `config.json`, `.env`, and credentials. `config.example.json` now contains placeholders rather than a known web password. The runtime default in `src/core/config.py` remains development-only and must be removed before the web API is exposed.
- **Fail-safe Reboot Rule:** In the event of an ESP32 watchdog reset or power loss, devices must **never** be inadvertently unblocked until stored timer state is reconciled with NTP and current router state.

## 5. Verification & Testing Results
- Directory scaffold verified with all required subdirectories (`src/`, `www/`, `tests/`, `tools/`, `docs/decisions/`).
- Initial skeletons created: `src/boot.py`, `src/main.py`, `tools/deploy.py`, `tools/flash.py`.
- `config.example.json` parsed successfully as JSON. No project JSON Schema exists yet.
- Initial design-session requirements were consolidated into `AGENTS.md` and `ROADMAP.md`; the raw export was later removed and remains available in Git history.

## 6. Alternatives Considered & Trade-offs
- *Alternative 1: Monolithic `main.py`.* Rejected because large files degrade agent reasoning, create merge conflicts, and hinder unit testing.
- *Alternative 2: C++ (ESP-IDF / Arduino).* Rejected per project spec to maintain rapid prototyping and dynamic web serving via MicroPython.

## 7. Next Steps
- Initialize Git repository and commit baseline.
- Begin **Phase 1 (DR-001)**: implement `src/core/config.py` and `src/fritz/soap.py` with mock-tested SOAP envelope generation and XML extraction.
