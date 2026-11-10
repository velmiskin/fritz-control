"""Read-only authenticated Hosts discovery executed on the ESP32."""

import gc
import sys


STAGING_ROOT = "/phase1_discovery"
if STAGING_ROOT not in sys.path:
    sys.path.insert(0, STAGING_ROOT)

import network
import uasyncio as asyncio
from core.config import Config
from fritz.hosts import HostsService
from fritz.tr064 import TR064Client
from net.wifi import WiFiManager


async def run():
    config = Config.load(STAGING_ROOT + "/config.json")
    wlan = network.WLAN(getattr(network, "IF_STA", network.STA_IF))
    was_connected = wlan.isconnected()
    wifi = WiFiManager(
        config.get("wifi", "ssid", ""),
        config.get("wifi", "password", ""),
        wlan=wlan,
        network_module=network,
    )
    gc.collect()
    heap_before_connect = gc.mem_free()
    try:
        await wifi.connect()
        gc.collect()
        heap_after_connect = gc.mem_free()
        client = TR064Client(
            host=config.fritz_host,
            port=config.fritz_port,
            username=config.fritz_user,
            password=config.fritz_password,
            use_ssl=config.fritz_use_ssl,
        )
        hosts = HostsService(client)
        capabilities = await hosts.discover_capabilities()
        required = ("GetHostNumberOfEntries", "GetGenericHostEntry")
        for action in required:
            if not capabilities.supports(action):
                raise RuntimeError("Router does not advertise required Hosts action")

        count = await hosts.get_host_number_of_entries()
        if count < 1:
            raise RuntimeError("Router returned no host entries")
        sample = await hosts.get_generic_host_entry(0)
        if not isinstance(sample, dict) or sample.get("index") != 0:
            raise RuntimeError("Router returned an invalid generic host entry")
        gc.collect()
        heap_after_discovery = gc.mem_free()

        print("phase1_discovery PASS")
        print("host_count", count)
        print("sample_has_ip", bool(sample.get("ip")))
        print("sample_has_mac", bool(sample.get("mac")))
        print("heap_before_connect", heap_before_connect)
        print("heap_after_connect", heap_after_connect)
        print("heap_after_discovery", heap_after_discovery)
    finally:
        if not was_connected:
            try:
                wlan.disconnect()
                wlan.active(False)
            except OSError:
                pass


asyncio.run(run())
