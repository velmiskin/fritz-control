# Decision Report: [DR-002] WAN Access Control & Verification (HostFilter:1)

**Date:** 2026-11-08  
**Status:** Accepted  
**Author:** AI Agent & Engineering Team  
**Related Milestone/Feature:** Phase 2 — WAN Access Control & Verification (`HostFilter:1`)
**Evidence Level:** Unit/mock tested; prior live SCPD inspection recorded, ESP32 acceptance pending<br>
**Tested Versions:** CPython host tests; MicroPython and FRITZ!OS versions not recorded

---

## 1. Context & Problem Statement
The primary goal of FritzControl is per-device internet access restriction (parental control/access management). 
Specific technical constraints and challenges:
- **AVM TR-064 Service Authenticity:** Control actions must adhere strictly to the router's real SCPD definition (`urn:dslforum-org:service:X_AVM-DE_HostFilter:1` at `/upnp/control/x_hostfilter`).
- **Asynchronous Router State Updates:** When `DisallowWANAccessByIP` is sent to a FRITZ!Box, the router adjusts its internal iptables/packet filter rules asynchronously. An immediate subsequent query can report the stale state.
- **Resource Constraints (ESP32):** Batch operations across multiple IP addresses must not block the `uasyncio` event loop or flood the router with simultaneous TCP connections, which would exhaust MicroPython socket descriptors (typically max 4-8 concurrent sockets on ESP32).

## 2. Technical Decision
1. **HostFilter Service Implementation (`src/fritz/host_filter.py`):**
   - Implemented `get_wan_access_by_ip(ip_address)`: queries `GetWANAccessByIP` and extracts boolean `disallow` and string `wan_access` ('granted' / 'denied').
   - Implemented `disallow_wan_access_by_ip(ip_address, disallow=True)`: executes `DisallowWANAccessByIP` with parameter `NewDisallow="1"` (block) or `"0"` (unblock).
   - Implemented `get_host_entry_by_ip(ip_address)`: queries `GetHostEntryByIP` to retrieve filter profile ID and time budget details.
2. **Post-Command Verification Loop (`set_wan_access_and_verify`):**
   - After dispatching `DisallowWANAccessByIP`, the service polls `GetWANAccessByIP` with a configurable constant delay (`retries=3`, `delay_sec=1`) until the reported `NewDisallow` flag matches the request.
   - Returns a `verified: True/False` flag in the result payload.
   - Limitation: clearing `NewDisallow` does not prove effective WAN access because the device's filter profile can still yield `NewWANAccess="denied"`. Phase 2.5 must correct this result contract before scheduling builds on it.
3. **Sequential Rate-Limited Batch Processing (`set_batch_wan_access`):**
   - Iterates through a target list of IPv4 addresses sequentially with `await asyncio.sleep(delay_between_sec)` (default 200ms) between devices to prevent router connection refusal and socket exhaustion.

## 3. Resource & Hardware Impact (ESP32 Constraints)
- **RAM / Memory Allocation:**
  - Operates using targeted string parsing instead of an XML DOM. Exact peak heap allocation has not been measured and the transport currently buffers the complete response body.
  - Single active socket connection at any point in time.
- **Async Event Loop:**
  - Uses `uasyncio.sleep` between verification attempts and batch elements; the event loop remains completely non-blocking, allowing background tasks and the web server to remain responsive.

## 4. Security & Fault Tolerance
- **Fail-safe Operation:** Devices are identified explicitly by IPv4 registered in the DHCP/ARP table.
- **Error Propagation:** If an individual device in a batch fails (e.g. invalid IP or router timeout), the error is isolated to that device's result record and does not abort the remaining batch.

## 5. Verification & Testing Results
- **Router SCPD Validation:**
  - Action signatures inspected directly on the FRITZ!Box 6690 Cable via `http://192.168.178.1:49000/x_hostfilterSCPD.xml`.
  - Confirmed action names: `DisallowWANAccessByIP`, `GetWANAccessByIP`, `GetHostEntryByIP`.
  - This was a manual check recorded by the prior development session; the router and firmware versions were not captured in a repeatable acceptance record.
- **Automated Unit & Mock Tests (`tests/test_host_filter.py`):**
  - Tested `get_wan_access_by_ip` for both allowed and disallowed mock states.
  - Tested `disallow_wan_access_by_ip` parameter serialization (`NewDisallow` 1 vs 0).
  - Tested `set_wan_access_and_verify` simulating asynchronous router update delay (first check stale, second check verified).
  - Tested `set_batch_wan_access` sequential execution across multiple target IPs.
  - Tested `get_host_entry_by_ip` extraction of time and profile metadata.
  - Result: **22 passed in 1.36s** via `pytest`.
- **Known gaps:** effective unblock verification, `WANAccess="error"`, transport faults/timeouts, invalid IPv4 input, bounded memory, HTTPS, and target-hardware acceptance.

## 6. Alternatives Considered & Trade-offs
- *Alternative 1: Fire-and-forget commands without verification.* Rejected because network drops or router busy states can lead to silent failure, leaving internet unblocked when parental control expects it blocked.
- *Alternative 2: Parallel batch execution (`asyncio.gather`).* Rejected because ESP32 has limited socket handles; opening multiple concurrent TR-064 SSL/TCP connections risks socket starvation and memory allocation spikes.

## 7. Next Steps
- Proceed to **Phase 3 (DR-003)**: Timers, Scheduling & State Persistence (`src/services/access_manager.py`, `src/network/ntp.py`, `src/core/storage.py`, reboot recovery).
