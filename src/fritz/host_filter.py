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
from fritz.soap import parse_soap_response, extract_tag_value
from fritz.tr064 import TR064Error

HOST_FILTER_SERVICE_TYPE = "urn:dslforum-org:service:X_AVM-DE_HostFilter:1"
HOST_FILTER_CONTROL_URL = "/upnp/control/x_hostfilter"

class HostFilterService:
    def __init__(self, client):
        self.client = client

    async def get_wan_access_by_ip(self, ip_address):
        """
        Queries the current WAN internet access status of a device.
        :param ip_address: IPv4 address string (e.g. '192.168.178.50')
        :return: dict with 'ip', 'disallow' (bool), 'wan_access' (str: 'granted'|'denied')
        """
        body = await self.client.call_action(
            control_url=HOST_FILTER_CONTROL_URL,
            service_type=HOST_FILTER_SERVICE_TYPE,
            action_name="GetWANAccessByIP",
            params={"NewIPv4Address": ip_address}
        )
        parsed = parse_soap_response(body, ["NewDisallow", "NewWANAccess"])
        disallow_str = parsed.get("NewDisallow", "0")
        wan_access_str = parsed.get("NewWANAccess", "")
        return {
            "ip": ip_address,
            "disallow": disallow_str == "1",
            "wan_access": wan_access_str or ("denied" if disallow_str == "1" else "granted")
        }

    async def disallow_wan_access_by_ip(self, ip_address, disallow=True):
        """
        Blocks or unblocks WAN access for a specific IP.
        :param ip_address: IPv4 address string
        :param disallow: True to block internet, False to unblock/allow
        :return: raw response XML body
        """
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
        await self.disallow_wan_access_by_ip(ip_address, disallow)

        for attempt in range(1, retries + 1):
            await asyncio.sleep(delay_sec)
            status = await self.get_wan_access_by_ip(ip_address)
            if status["disallow"] == disallow:
                log.info(f"Verified WAN status for {ip_address}: disallow={disallow} on attempt {attempt}")
                status["verified"] = True
                return status
            log.warn(f"Verification attempt {attempt}/{retries} pending for {ip_address}")

        log.error(f"Failed to verify WAN status change for {ip_address} after {retries} attempts.")
        status["verified"] = False
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
            except TR064Error as e:
                log.error(f"Error updating WAN access for {ip}: {e}")
                results[ip] = {"ip": ip, "error": str(e), "verified": False}
            await asyncio.sleep(delay_between_sec)
        return results

    async def get_host_entry_by_ip(self, ip_address):
        """
        Retrieves filter profile, usage time, and WAN status for a given IP.
        """
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
