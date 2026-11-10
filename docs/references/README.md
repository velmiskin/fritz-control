# Normative references

Use this index to verify TR-064 services, actions, arguments and state values.
The live SCPD served by the target FRITZ!Box remains the final capability source:
not every action is available on every FRITZ!OS version.

| Reference | Revision checked | Purpose |
|---|---:|---|
| [FRITZ! interface catalogue](https://fritz.com/en/pages/interfaces) | 2026-11-09 | Official document index |
| [TR-064 HostFilter](https://fritz.support/resources/TR-064_Host_Filter.pdf) | 2025-09-11, version 8 | WAN access and filter profiles |
| [TR-064 Hosts](https://fritz.support/resources/TR-064_Hosts.pdf) | 2026-01-29, version 32 | Host discovery and host metadata |
| [FRITZ!Box login guidance](https://fritz.com/fileadmin/user_upload/Global/Service/Schnittstellen/Recommendations%20for%20user%20guidance%20for%20logging%20into%20a%20FRITZBox_v1.1_EN.pdf) | Version 1.1 | Discovering automatically generated users for password-only UI login |
| [MicroPython 1.29 asyncio](https://docs.micropython.org/en/v1.29.0/library/asyncio.html) | Accessed 2026-11-10 | Supported asynchronous I/O and TLS context API |
| [MicroPython 1.29 WLAN](https://docs.micropython.org/en/v1.29.0/library/network.WLAN.html) | Accessed 2026-11-10 | STA connection and status API |

## Capability verification

Before using an optional action, record all of the following in the relevant
Decision Report:

1. FRITZ!Box model and FRITZ!OS version.
2. Service type, control URL and SCPD URL from the device description.
3. Presence of the exact action and arguments in the router-provided SCPD.
4. Required user rights.
5. Result of a non-destructive or explicitly authorised hardware check.

The original design-session export was removed after its durable requirements
were incorporated into `AGENTS.md` and `ROADMAP.md`. It remains recoverable from
Git history but is not a normative project document.
