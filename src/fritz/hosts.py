"""
src/fritz/hosts.py - FRITZ!Box Hosts:1 Service Handler
Implements TR-064 device discovery adhering to urn:dslforum-org:service:Hosts:1.
"""

from core.logger import log
from fritz.capabilities import ServiceCapabilities
from fritz.soap import parse_soap_response, extract_tag_value
from fritz.tr064 import TR064Error
from fritz.validation import validate_ipv4

HOSTS_SERVICE_TYPE = "urn:dslforum-org:service:Hosts:1"
HOSTS_CONTROL_URL = "/upnp/control/hosts"
HOSTS_SCPD_URL = "/hostsSCPD.xml"

class HostsService:
    def __init__(self, client, capabilities=None):
        self.client = client
        self.capabilities = capabilities

    async def discover_capabilities(self):
        self.capabilities = await ServiceCapabilities.discover(
            self.client, HOSTS_SERVICE_TYPE, HOSTS_SCPD_URL
        )
        return self.capabilities

    async def _require_action(self, action_name):
        capabilities = self.capabilities
        if capabilities is None:
            capabilities = await self.discover_capabilities()
        if not capabilities.supports(action_name):
            raise TR064Error("Router does not advertise action {}".format(action_name))

    async def get_host_number_of_entries(self):
        """
        Calls GetHostNumberOfEntries.
        :return: Total number of known hosts (int).
        """
        body = await self.client.call_action(
            control_url=HOSTS_CONTROL_URL,
            service_type=HOSTS_SERVICE_TYPE,
            action_name="GetHostNumberOfEntries"
        )
        count_str = extract_tag_value(body, "NewHostNumberOfEntries")
        if count_str and count_str.isdigit():
            return int(count_str)
        return 0

    async def get_generic_host_entry(self, index):
        """
        Calls GetGenericHostEntry by index.
        :param index: 0-based integer index
        :return: dict with host properties or None
        """
        body = await self.client.call_action(
            control_url=HOSTS_CONTROL_URL,
            service_type=HOSTS_SERVICE_TYPE,
            action_name="GetGenericHostEntry",
            params={"NewIndex": str(index)}
        )
        tags = [
            "NewIPAddress", "NewMACAddress", "NewHostName", 
            "NewActive", "NewInterfaceType", "NewLeaseTimeRemaining"
        ]
        parsed = parse_soap_response(body, tags)
        return {
            "index": index,
            "ip": parsed.get("NewIPAddress", "") or "",
            "mac": parsed.get("NewMACAddress", "") or "",
            "hostname": parsed.get("NewHostName", "") or "Unknown",
            "active": parsed.get("NewActive") == "1",
            "interface": parsed.get("NewInterfaceType", "") or "",
            "lease_time": int(parsed.get("NewLeaseTimeRemaining", 0) or 0)
        }

    async def get_specific_host_by_ip(self, ip_address):
        """
        Calls AVM vendor extension X_AVM-DE_GetSpecificHostEntryByIP.
        Returns extended status including WAN access state.
        """
        ip_address = validate_ipv4(ip_address)
        await self._require_action("X_AVM-DE_GetSpecificHostEntryByIP")
        body = await self.client.call_action(
            control_url=HOSTS_CONTROL_URL,
            service_type=HOSTS_SERVICE_TYPE,
            action_name="X_AVM-DE_GetSpecificHostEntryByIP",
            params={"NewIPAddress": ip_address}
        )
        tags = [
            "NewMACAddress", "NewActive", "NewHostName", "NewInterfaceType",
            "NewX_AVM-DE_WANAccess", "NewX_AVM-DE_Disallow", "NewX_AVM-DE_FriendlyName"
        ]
        parsed = parse_soap_response(body, tags)
        return {
            "ip": ip_address,
            "mac": parsed.get("NewMACAddress", "") or "",
            "hostname": parsed.get("NewHostName", "") or "",
            "friendly_name": parsed.get("NewX_AVM-DE_FriendlyName", "") or "",
            "active": parsed.get("NewActive") == "1",
            "wan_access": parsed.get("NewX_AVM-DE_WANAccess", "") or "",
            "disallow": parsed.get("NewX_AVM-DE_Disallow") == "1",
            "interface": parsed.get("NewInterfaceType", "") or ""
        }

    async def get_all_hosts(self, only_active=False, limit=None):
        """
        Retrieves all registered devices by iterating indices.
        :param only_active: Filter to only return currently connected devices
        :param limit: Optional max number of devices to fetch
        :return: list of host dicts
        """
        total = await self.get_host_number_of_entries()
        log.info(f"Router reports {total} total host entries.")
        
        count = min(total, limit) if limit else total
        hosts = []

        for i in range(count):
            try:
                entry = await self.get_generic_host_entry(i)
                if only_active and not entry["active"]:
                    continue
                hosts.append(entry)
            except TR064Error as e:
                # 714 = NoSuchEntryInArray (end of list or gap)
                if e.error_code == 714:
                    break
                log.warn(f"Failed to fetch host index {i}: {e}")

        return hosts

    async def get_hosts_page(self, offset=0, limit=1):
        """Return a bounded page without fetching preceding host entries."""
        if type(offset) is not int or offset < 0:
            raise ValueError("Host page offset must be a non-negative integer")
        if type(limit) is not int or limit != 1:
            raise ValueError("Host page limit must be exactly 1 on ESP32")
        total = await self.get_host_number_of_entries()
        hosts = []
        for index in range(offset, min(total, offset + limit)):
            try:
                hosts.append(await self.get_generic_host_entry(index))
            except TR064Error as exc:
                if exc.error_code == 714:
                    break
                raise
        return {"devices": hosts, "total": total, "offset": offset}
