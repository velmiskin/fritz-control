# Normative references

Use this index to verify TR-064 services, actions, arguments and state values.
The live SCPD served by the target FRITZ!Box remains the final capability source:
not every action is available on every FRITZ!OS version.

| Reference | Revision checked | Purpose |
|---|---:|---|
| [FRITZ! interface catalogue](https://fritz.com/en/pages/interfaces) | 2026-11-09 | Official document index |
| [TR-064 HostFilter](https://fritz.support/resources/TR-064_Host_Filter.pdf) | 2025-09-11, version 8 | WAN access and filter profiles |
| [TR-064 Hosts](https://fritz.support/resources/TR-064_Hosts.pdf) | 2026-01-29, version 32 | Host discovery and host metadata |
| [MicroPython uasyncio](https://docs.micropython.org/en/latest/library/asyncio.html) | Accessed 2026-11-09 | Supported asynchronous I/O API |

## Capability verification

Before using an optional action, record all of the following in the relevant
Decision Report:

1. FRITZ!Box model and FRITZ!OS version.
2. Service type, control URL and SCPD URL from the device description.
3. Presence of the exact action and arguments in the router-provided SCPD.
4. Required user rights.
5. Result of a non-destructive or explicitly authorised hardware check.

`PROJECT_SPEC.md` is preserved as a raw design-session export. It contains UI
markup and historical generated citations, so it is informative only and must
not be used to justify protocol details.
