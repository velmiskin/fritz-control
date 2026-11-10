"""Live asynchronous DNS/NTP acceptance executed on the ESP32."""

import gc
import sys


STAGING_ROOT = "/phase3_ntp"
if STAGING_ROOT not in sys.path:
    sys.path.insert(0, STAGING_ROOT)

import machine
import network
import uasyncio as asyncio
from core.config import Config
from net.ntp import NTPClient
from net.wifi import WiFiManager


async def run():
    config = Config.load(STAGING_ROOT + "/config.json")
    interface = getattr(network, "IF_STA", None)
    if interface is None:
        interface = network.STA_IF
    wlan = network.WLAN(interface)
    was_connected = wlan.isconnected()
    wifi = WiFiManager(
        config.get("wifi", "ssid", ""),
        config.get("wifi", "password", ""),
        wlan=wlan,
        network_module=network,
    )
    gc.collect()
    heap_before = gc.mem_free()
    try:
        network_config = await wifi.connect()
        dns_server = network_config[3]
        client = NTPClient(
            server=config.get("ntp", "server", "pool.ntp.org"),
            dns_server=dns_server,
            timeout=4,
            retries=3,
        )
        result = await client.synchronize(machine.RTC())
        rtc_value = machine.RTC().datetime()
        gc.collect()
        heap_after = gc.mem_free()
        assert result["unix_time"] >= 946684800
        assert rtc_value[0] >= 2026
        print("phase3_ntp PASS")
        print("stratum", result["stratum"])
        print("rtc_year", rtc_value[0])
        print("heap_before", heap_before)
        print("heap_after", heap_after)
    finally:
        if not was_connected:
            try:
                wlan.disconnect()
                wlan.active(False)
            except OSError:
                pass


asyncio.run(run())
