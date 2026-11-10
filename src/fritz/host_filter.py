"""
src/fritz/host_filter.py - FRITZ!Box X_AVM-DE_HostFilter:1 Service Handler
Implements WAN internet access control (blocking/unblocking) per IPv4 address
with asynchronous state verification and batch execution.
"""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from core.logger import log
from fritz.capabilities import ServiceCapabilities
from fritz.soap import parse_soap_response, extract_tag_value
from fritz.tr064 import TR064Error
from fritz.validation import validate_ipv4

HOST_FILTER_SERVICE_TYPE = "urn:dslforum-org:service:X_AVM-DE_HostFilter:1"
HOST_FILTER_CONTROL_URL = "/upnp/control/x_hostfilter"
HOST_FILTER_SCPD_URL = "/x_hostfilterSCPD.xml"

class HostFilterService:
    def __init__(self, client, capabilities=None):
        self.client = client
        self.capabilities = capabilities

    async def discover_capabilities(self):
        self.capabilities = await ServiceCapabilities.discover(
            self.client, HOST_FILTER_SERVICE_TYPE, HOST_FILTER_SCPD_URL
        )
        return self.capabilities

    async def _require_action(self, action_name):
        capabilities = self.capabilities
        if capabilities is None:
            capabilities = await self.discover_capabilities()
        if not capabilities.supports(action_name):
            raise TR064Error("Router does not advertise action {}".format(action_name))

    async def get_wan_access_by_ip(self, ip_address):
        """
        Queries the current WAN internet access status of a device.
        :param ip_address: IPv4 address string (e.g. '192.168.178.50')
        :return: dict with 'ip', 'disallow' (bool), 'wan_access' (str: 'granted'|'denied')
        """
        ip_address = validate_ipv4(ip_address)
        body = await self.client.call_action(
            control_url=HOST_FILTER_CONTROL_URL,
            service_type=HOST_FILTER_SERVICE_TYPE,
            action_name="GetWANAccessByIP",
            params={"NewIPv4Address": ip_address}
        )
        parsed = parse_soap_response(body, ["NewDisallow", "NewWANAccess"])
        disallow_str = parsed.get("NewDisallow")
        wan_access_str = parsed.get("NewWANAccess")
        if disallow_str not in ("0", "1"):
            raise TR064Error("Invalid or missing NewDisallow in router response")
        if wan_access_str not in ("granted", "denied", "error"):
            raise TR064Error("Invalid or missing NewWANAccess in router response")
        return {
            "ip": ip_address,
            "disallow": disallow_str == "1",
            "wan_access": wan_access_str,
            "effective_allowed": wan_access_str == "granted",
        }

    async def disallow_wan_access_by_ip(self, ip_address, disallow=True):
        """
        Blocks or unblocks WAN access for a specific IP.
        :param ip_address: IPv4 address string
        :param disallow: True to block internet, False to unblock/allow
        :return: raw response XML body
        """
        ip_address = validate_ipv4(ip_address)
        if not isinstance(disallow, bool):
            raise ValueError("disallow must be a boolean")
        flag_val = "1" if disallow else "0"
        action_verb = "Blocking" if disallow else "Unblocking"
        log.info(f"{action_verb} WAN access for {ip_address}...")

        body = await self.client.call_action(
            control_url=HOST_FILTER_CONTROL_URL,
            service_type=HOST_FILTER_SERVICE_TYPE,
            action_name="DisallowWANAccessByIP",
            params={
                "NewIPv4Address": ip_address,
                "NewDisallow": flag_val
            }
        )
        return body

    async def set_wan_access_and_verify(self, ip_address, disallow=True, retries=3, delay_sec=1):
        """
        Sends the block/unblock command and verifies that the router actually applied the change.
        FRITZ!OS applies firewall filter rules asynchronously.
        :param ip_address: Target IPv4 address
        :param disallow: True to block, False to unblock
        :param retries: Number of verification checks
        :param delay_sec: Delay in seconds between checks
        :return: dict with 'ip', 'disallow', 'wan_access', 'verified' (bool)
        """
        if not isinstance(retries, int) or retries < 1:
            raise ValueError("retries must be at least 1")
        await self.disallow_wan_access_by_ip(ip_address, disallow)

        status = None
        last_status_error = None
        for attempt in range(1, retries + 1):
            await asyncio.sleep(delay_sec)
            try:
                status = await self.get_wan_access_by_ip(ip_address)
            except TR064Error as exc:
                last_status_error = exc
                log.warn(
                    f"Verification attempt {attempt}/{retries} returned an invalid state"
                )
                continue
            expected_wan = "denied" if disallow else "granted"
            override_applied = status["disallow"] == disallow
            effective_applied = status["wan_access"] == expected_wan
            if override_applied and effective_applied:
                log.info(f"Verified WAN status for {ip_address}: disallow={disallow} on attempt {attempt}")
                status["override_applied"] = True
                status["verified"] = True
                status["reason"] = "effective_state_verified"
                return status
            log.warn(f"Verification attempt {attempt}/{retries} pending for {ip_address}")

        log.error(f"Failed to verify WAN status change for {ip_address} after {retries} attempts.")
        if status is None:
            raise TR064Error(
                "Router did not return a valid WAN state after {} attempts: {}".format(
                    retries, last_status_error or "unknown status error"
                )
            )
        status["override_applied"] = status["disallow"] == disallow
        status["verified"] = False
        if not disallow and not status["disallow"] and status["wan_access"] == "denied":
            status["reason"] = "filter_profile_denied"
        elif status["wan_access"] == "error":
            status["reason"] = "router_state_error"
        else:
            status["reason"] = "state_not_applied"
        return status

    async def set_batch_wan_access(self, ip_list, disallow=True, delay_between_sec=0.2):
        """
        Blocks or unblocks a list of IP addresses sequentially with rate-limiting.
        :param ip_list: list of IPv4 strings
        :param disallow: True to block, False to unblock
        :param delay_between_sec: delay between requests to avoid overwhelming router TR-064
        :return: dict mapping ip to verification result
        """
        results = {}
        for ip in ip_list:
            try:
                res = await self.set_wan_access_and_verify(ip, disallow=disallow, retries=2, delay_sec=0.5)
                results[ip] = res
            except (TR064Error, ValueError) as e:
                log.error(f"Error updating WAN access for {ip}: {e}")
                results[ip] = {"ip": ip, "error": str(e), "verified": False}
            await asyncio.sleep(delay_between_sec)
        return results

    async def get_host_entry_by_ip(self, ip_address):
        """
        Retrieves filter profile, usage time, and WAN status for a given IP.
        """
        ip_address = validate_ipv4(ip_address)
        await self._require_action("GetHostEntryByIP")
        body = await self.client.call_action(
            control_url=HOST_FILTER_CONTROL_URL,
            service_type=HOST_FILTER_SERVICE_TYPE,
            action_name="GetHostEntryByIP",
            params={"NewIPv4Address": ip_address}
        )
        tags = [
            "NewHostName", "NewFilterProfileID", "NewTimeUsed",
            "NewTimeMax", "NewTicketsInAdvance", "NewTicketValid",
            "NewIsTimeShared", "NewWANAccess"
        ]
        parsed = parse_soap_response(body, tags)
        return {
            "ip": ip_address,
            "hostname": parsed.get("NewHostName", "") or "",
            "profile_id": parsed.get("NewFilterProfileID", "") or "",
            "time_used": int(parsed.get("NewTimeUsed", 0) or 0),
            "time_max": int(parsed.get("NewTimeMax", 0) or 0),
            "wan_access": parsed.get("NewWANAccess", "") or ""
        }
