# Decision Report: [DR-001] TR-064 SOAP Client & Device Discovery (Hosts:1)

**Date:** 2026-11-04  
**Last Hardware Verification:** 2026-11-10
**Status:** Accepted  
**Author:** AI Agent & Engineering Team  
**Related Milestone/Feature:** Phase 1 — TR-064 Core & Device Discovery (`Hosts:1`)
**Evidence Level:** Hardware accepted
**Tested Versions:** Python 3.15.2; MicroPython 1.29.0 ESP32_GENERIC; FRITZ!Box 6690 Cable, FRITZ!OS 8.25

---

## 1. Context & Problem Statement
To control internet access per device on an AVM FRITZ!Box 6690 Cable, the ESP32 must discover active and registered local network devices (IP, MAC, hostname, active status). 
Key challenges and constraints:
- **MicroPython Memory Constraints:** Parsing XML using standard DOM parsers (like `xml.etree` or `minidom`) requires building tree nodes in RAM, rapidly triggering MemoryError on ESP32 (~120KB free heap).
- **Authentication:** Modern FRITZ!OS (7.50+ / 8.0+) protects TR-064 with HTTP Digest Authentication (RFC 2617) with MD5 hashing, realm challenge, nonce, and quality of protection (`qop="auth"`).
- **Service Verification:** FRITZ!Box uses `urn:dslforum-org:service:Hosts:1` at `/upnp/control/hosts`.

## 2. Technical Decision
1. **Zero-DOM Lightweight String Parser (`src/fritz/soap.py`):**
   - Replaced XML tree parsing with linear substring indexing (`str.find`) in `extract_tag_value` and `parse_soap_response`.
   - Generates compact SOAP envelopes (`build_soap_envelope`) without gratuitous indentation or whitespace.
   - Extracts UPnP SOAP Faults (`<faultcode>`, `<faultstring>`, `<errorCode>`, `<errorDescription>`).
2. **Async TR-064 Client with Transparent Digest Auth (`src/fritz/tr064.py`):**
   - Implemented `TR064Client` over `uasyncio` streams (`open_connection`, `wait_for` timeouts).
   - Handles `401 Unauthorized` challenge transparently: parses `WWW-Authenticate`, calculates MD5 digest response (`HA1:nonce:nc:cnonce:qop:HA2`), and re-dispatches the SOAP action.
   - Automatically invokes `gc.collect()` upon stream closure to prevent heap fragmentation.
3. **Hosts Service Model (`src/fritz/hosts.py`):**
   - Implemented `GetHostNumberOfEntries` to read total device count.
   - Implemented `GetGenericHostEntry` for index-based device iteration (`ip`, `mac`, `hostname`, `active`, `interface`).
   - Implemented vendor extension `X_AVM-DE_GetSpecificHostEntryByIP` to inspect WAN access and disallow flags.
   - Gracefully handles error code `714 (NoSuchEntryInArray)` when reaching the end of the host table.
4. **Configuration Manager (`src/core/config.py`):**
   - Safe deep-copy dictionary loading from `config.json` with fallback to default host (`192.168.178.1`) and ports (`49000` / `49443`).

## 3. Resource & Hardware Impact (ESP32 Constraints)
- **RAM / Memory Allocation:**
  - Targeted string parsing avoids allocating an XML DOM.
  - SOAP responses are bounded to 16 KiB and SCPD documents to 32 KiB before
    parsing; connection-close bodies are accumulated in one bounded bytearray.
  - `gc.collect()` called immediately after connection teardown.
  - During authenticated ESP32 discovery, observed free heap after collection
    was 109,152 bytes before Wi-Fi connection, 108,912 after connection, and
    99,728 after SCPD discovery plus two Hosts SOAP actions. These are point
    observations, not peak-allocation measurements.
- **Async Event Loop:**
  - All network I/O utilizes non-blocking `asyncio` / `uasyncio` streams with strict 10-second timeouts, preventing hangs if the router is busy.

## 4. Security & Fault Tolerance
- **Credentials & Network:**
  - Passwords are used strictly for MD5 digest generation and are never logged or echoed across serial logs.
- **Router Error Handling:**
  - Parses SOAP faults cleanly. Error `714` is caught as a normal iteration termination rather than an unhandled crash.

## 5. Verification & Testing Results
- **Automated Mock Test Suite:**
  - Created 16 unit tests across `tests/test_config.py`, `tests/test_soap.py`, and `tests/test_hosts.py`.
  - Tested:
    - Default configuration and file loading.
    - SOAP envelope generation and tag extraction (with and without attributes).
    - SOAP Fault 714 parsing.
    - HTTP Digest Authorization header calculation.
    - `HostsService` methods (`get_host_number_of_entries`, `get_generic_host_entry`, `get_specific_host_by_ip`, `get_all_hosts`).
  - Historical result at milestone completion: **16 passed in 0.09s** via `pytest`.
- **Live Router Connectivity Check:**
  - Successfully retrieved `tr64desc.xml` and `hostsSCPD.xml` directly from FRITZ!Box 6690 Cable (`192.168.178.1:49000`), verifying actual action definitions.
  - `python tools/hardware_discovery.py COM3 --config config.json` temporarily
    staged the candidate modules and ignored configuration on the ESP32. The
    board connected to Wi-Fi, completed Digest authentication, advertised both
    required Hosts actions, returned 33 entries from `GetHostNumberOfEntries`,
    and returned a valid first `GetGenericHostEntry` containing IP and MAC.
    No router state was changed and the staging directory was removed.
  - The first hardware attempt exposed that the MicroPython build lacks the
    `iso-8859-1` codec. HTTP header parsing now uses strict ASCII, matching the
    headers generated and required by this client; unexpected octets fail closed.
- **Current host result:** **54 tests passed** on Python 3.15.2, including
  wire-level Digest, framing, malformed-header and timeout coverage.
- **Known gaps:** the full firmware entrypoint, long-running reconnect behavior,
  timers and reboot recovery are not yet integrated.

## 6. Alternatives Considered & Trade-offs
- *Alternative 1: `micropython-xml` or regex-based tree parser.* Rejected because tree construction uses excessive heap and is prone to fragmentation.
- *Alternative 2: Fetching the entire device list as one giant XML file via `X_AVM-DE_GetHostListPath`.* Rejected for MVP because a 60+ device network generates a 30KB+ XML file that can easily cause memory allocation spikes on ESP32. Fetching entry-by-entry with `GetGenericHostEntry` guarantees flat, predictable RAM consumption per query.

## 7. Next Steps
- Proceed to **Phase 3**: implement persistent timer state, NTP synchronization,
  scheduling, and fail-safe reboot recovery without automatic unblocking.

## 8. Traceability
- Roadmap: Phase 1.
- Hardware runner: `tools/hardware_discovery.py`; device script:
  `tests/hardware/phase1_discovery.py`.
- Live router SCPD path: `/hostsSCPD.xml`.
