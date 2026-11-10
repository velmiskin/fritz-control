# FritzControl

FritzControl is a MicroPython application for an ESP32-WROOM-32E that controls
per-device WAN access on a FRITZ!Box through the TR-064 SOAP interface.

The project is under active development. The Hosts and HostFilter modules have
CPython mock tests, but the firmware entrypoint is not integrated yet. Do not
interpret a passing host-side test suite as proof that the complete application
runs on the ESP32.

## Current status

| Area | Status | Evidence |
|---|---|---|
| Project and agent workflow | Complete | DR-000, DR-003 |
| SOAP, Hosts and HostFilter modules | Transport-tested; router pending | DR-001, DR-002, DR-004 |
| TR-064 transport on ESP32 | Import/async smoke-tested | DR-004 |
| Timers and reboot recovery | Not started | Phase 3 |
| HTTP API and dashboard | Not started | Phase 4 |

Known limitations are tracked in `ROADMAP.md`. HTTPS is explicitly rejected
until certificate validation and heap impact are designed. Live FRITZ!Box
acceptance remains required before scheduling is implemented.

## Development setup

Requirements:

- Python 3.11 or newer for host-side tooling;
- an ESP32-compatible MicroPython firmware;
- `mpremote` and `esptool` for device operations.

Create a virtual environment and install the pinned development tools:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Run the host-side verification suite:

```powershell
python -m pytest
python -m compileall -q src tools
```

The tests execute on CPython and use recorded SOAP fixtures. Hardware acceptance
must be recorded separately with the MicroPython and FRITZ!OS versions, commands
run, and observed heap measurements.

Run the reproducible ESP32 smoke test with
`python tools/hardware_smoke.py COM3`. It stages candidate modules under a
temporary `/phase25_smoke` directory, cleans it afterward, and never uses Wi-Fi
credentials or changes router state.

Probe the router's public SCPD documents without credentials or state changes
with `python tools/router_probe.py --host 192.168.178.1`.

An explicit host-side block operation requires the target IP twice:
`python tools/access_control.py --block 192.168.178.30 --confirm-block 192.168.178.30`.
The tool reads `config.json`, checks the current state first, and sends the block
only after successful authentication and capability verification.

## Configuration and secrets

Copy `config.example.json` to `config.json` and replace every placeholder.
`config.json` is ignored by Git. Never paste real Wi-Fi or FRITZ!Box credentials
into tests, logs, Decision Reports, issues or commits.

The example contains only password placeholders. The current firmware runtime
still has a development default; the web server must refuse to start with a
default or empty password before the API is exposed.

## Device tools

Flash MicroPython only when the target port and firmware image have been checked:

```powershell
python tools/flash.py COM3 firmware/esp32-v1.29.0.bin --yes
```

Deploy the current firmware files:

```powershell
python tools/deploy.py COM3
```

The deployment helper uploads source and static assets and verifies every remote
path. It is not yet atomic and does not remove stale remote files. Use
`python tools/deploy.py --dry-run` to inspect the manifest first.

## Project documentation

- `AGENTS.md` contains mandatory coding-agent constraints.
- `ROADMAP.md` is the authoritative progress tracker.
- `docs/decisions/` records accepted implementation decisions and evidence.
- `docs/references/README.md` lists normative external specifications.

## Definition of done

A milestone is complete only when its stated tests pass, its Decision Report is
accepted, and the corresponding roadmap item links to the report. Claims about
hardware behavior or memory usage require observed hardware evidence; estimates
must be labelled as estimates.
