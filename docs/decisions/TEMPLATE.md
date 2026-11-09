# Decision Report: [DR-XXX] [Feature/Decision Title]

**Date:** YYYY-MM-DD  
**Status:** [Proposed | Accepted | Superseded by DR-YYY]  
**Author:** AI Agent / Developer  
**Related Milestone/Feature:** [e.g., Phase 1 - TR-064 SOAP Client]
**Evidence Level:** [Design only | Unit/mock tested | Transport tested | Hardware accepted]
**Tested Versions:** [Python, MicroPython, FRITZ!OS, hardware; use "not tested" explicitly]

---

## 1. Context & Problem Statement
- What feature was being implemented or what architectural question needed to be solved?
- What are the specific requirements and constraints (e.g., MicroPython memory limits, FRITZ!OS versions, network latency)?

## 2. Technical Decision
- What approach was chosen?
- Architecture and module design (classes, functions, data flow).
- Exact TR-064 / SOAP actions and arguments used (referencing official AVM docs).
- Capability assumptions and the router SCPD used to verify optional actions.

## 3. Resource & Hardware Impact (ESP32 Constraints)
- **RAM / Memory allocation:** Separate measured values from estimates. Include the measurement procedure for every measured value.
- **Async Event Loop:** Are there any blocking operations? How are network timeouts handled?
- **Flash / NVS Storage:** Does this write to flash? How is flash write endurance protected?

## 4. Security & Fault Tolerance
- **Credentials & Network:** Are credentials shielded from logs and serialized safely?
- **Reboot & Crash Behavior:** What happens if ESP32 reboots mid-operation? (Reminder: devices must never be unblocked automatically on reboot without validation).
- **Router Error Handling:** How are SOAP faults, invalid IP addresses, or router unreachable errors handled?

## 5. Verification & Testing Results
- **Commands:** Exact commands that were executed.
- **Unit / Mock Tests:** Result and scope; state what the mocks do not prove.
- **Transport Tests:** HTTP framing, authentication, timeouts and malformed-response coverage.
- **Physical / Network Verification:** ESP32, MicroPython, router and FRITZ!OS versions. Write "not performed" when unavailable.
- **Observed Outputs / Metrics:** Sanitised outputs and measured memory before/peak/after. Do not present estimates as observations.
- **Known Gaps:** Work that remains before hardware or production acceptance.

## 6. Alternatives Considered & Trade-offs
- What other approaches were considered?
- Why were they rejected in favor of the current solution?

## 7. Next Steps
- What subsequent feature or refinement builds on this decision?

## 8. Traceability
- Roadmap item and pull request/commit, if available.
- Official specification URL and revision date.
- Router-provided SCPD path used during hardware verification.
