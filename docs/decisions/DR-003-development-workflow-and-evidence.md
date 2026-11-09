# Decision Report: [DR-003] Development Workflow & Evidence Hardening

**Date:** 2026-11-09  
**Status:** Accepted  
**Author:** AI Agent & Engineering Team  
**Related Milestone/Feature:** Phase 0.1 — Development Workflow & Evidence Hardening  
**Evidence Level:** Host-side workflow tested  
**Tested Versions:** Python 3.15.2, pytest 9.2.0, mpremote 1.29.0, esptool 5.6.0

---

## 1. Context & Problem Statement

The repository had a strong architectural scaffold but no README, pinned host
toolchain, pytest configuration or CI workflow. Existing Decision Reports also
mixed estimates with measurements and treated mock-tested modules as if the
complete ESP32 integration were accepted.

## 2. Technical Decision

- Added an operator-facing README with current status, setup, secret handling,
  verification commands and explicit deployment-tool limitations.
- Pinned the verified host toolchain in `requirements-dev.txt` and centralised
  pytest configuration in `pyproject.toml`.
- Added a least-privilege GitHub Actions workflow for Python 3.11 and 3.15.
- Replaced the example web password with an explicit non-secret placeholder and
  ignored the local virtual environment.
- Added a normative reference index with official FRITZ! specifications and a
  live-SCPD capability checklist.
- Extended Decision Reports with evidence levels, tested versions, exact
  commands, known gaps and traceability.
- Corrected unsupported memory and backoff claims in DR-001 and DR-002 without
  rewriting the historical implementation decisions.
- Introduced Phase 2.5 as a required stabilization gate before scheduling.

No firmware implementation under `src/` and no device tooling under `tools/`
was changed in this milestone.

## 3. Resource & Hardware Impact (ESP32 Constraints)

Documentation and host-side configuration are not deployed to the ESP32. Flash,
heap and event-loop behavior are unchanged.

## 4. Security & Fault Tolerance

- CI receives read-only repository-content permission.
- README reiterates that real credentials must remain in ignored `config.json`.
- The setup now records that default web credentials and deployment scripts are
  provisional rather than presenting them as production-ready.
- Hardware claims require explicit target versions and observed evidence.

## 5. Verification & Testing Results

- Commands executed:
  - `python -m pytest`
  - `python -m compileall -q src tools`
  - `python -m mpremote --version`
- Results: 22 unit/mock tests passed; CPython compilation passed; mpremote
  reported version 1.29.0.
- Physical ESP32 and FRITZ!Box verification was not performed because firmware
  behavior was intentionally outside this documentation/setup milestone.
- Known gap: the GitHub Actions workflow cannot be observed until pushed to a
  GitHub repository and run by GitHub.

## 6. Alternatives Considered & Trade-offs

- A packaging-oriented `pyproject.toml` was rejected because firmware modules are
  copied to the ESP32 rather than installed as a CPython package.
- Broad unpinned dependencies were rejected in favor of the locally verified
  versions. Dependency upgrades must be intentional and re-verified.
- Rewriting historical Decision Reports was avoided; corrections are scoped to
  evidence and known limitations so the original decisions remain auditable.

## 7. Next Steps

Complete Phase 2.5: harden TR-064 semantics and transport, add wire-level tests,
then perform explicit ESP32 and router acceptance before starting Phase 3.

## 8. Traceability

- Roadmap: Phase 0.1 and Phase 2.5 gate.
- Specifications: `docs/references/README.md`.
- Commit: to be recorded when this milestone is committed.
