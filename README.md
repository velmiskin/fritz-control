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
| SOAP, Hosts and HostFilter modules | Mock-tested | DR-001, DR-002 |
| TR-064 transport on ESP32 | Hardening required | Phase 2.5 |
| Timers and reboot recovery | Not started | Phase 3 |
| HTTP API and dashboard | Not started | Phase 4 |

Known limitations are tracked in `ROADMAP.md`. In particular, HTTPS transport,
bounded HTTP response handling and verification of effective WAN access must be
completed before scheduling is implemented.

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
python tools/flash.py COM3 firmware/esp32-v1.29.0.bin
```

Deploy the current firmware files:

```powershell
python tools/deploy.py COM3
```

The existing deployment helpers are provisional. They do not yet provide an
atomic deployment, stale-file cleanup, static asset upload or post-upload
verification. Review their output before resetting the device.

## Project documentation

- `AGENTS.md` contains mandatory coding-agent constraints.
- `ROADMAP.md` is the authoritative progress tracker.
- `docs/decisions/` records accepted implementation decisions and evidence.
- `docs/references/README.md` lists normative external specifications.
- `docs/references/PROJECT_SPEC.md` is a legacy design-session export and is not
  a normative source.

## Definition of done

A milestone is complete only when its stated tests pass, its Decision Report is
accepted, and the corresponding roadmap item links to the report. Claims about
hardware behavior or memory usage require observed hardware evidence; estimates
must be labelled as estimates.
