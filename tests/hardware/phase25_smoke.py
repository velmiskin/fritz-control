"""Read-only Phase 2.5 smoke test executed with mpremote on an ESP32."""

import gc
import sys


STAGING_ROOT = "/phase25_smoke"
if STAGING_ROOT not in sys.path:
    sys.path.insert(0, STAGING_ROOT)

gc.collect()
heap_before = gc.mem_free()

import network
import uasyncio as asyncio
from fritz.capabilities import parse_action_names
from fritz.host_filter import HostFilterService
from fritz.hosts import HostsService
from fritz.soap import build_soap_envelope
from fritz.tr064 import TR064Client
from fritz.validation import validate_ipv4
from net.wifi import WiFiManager

gc.collect()
heap_after_import = gc.mem_free()

envelope = build_soap_envelope(
    "urn:test", "Action", {"NewName": "A&B <tablet>"}
)
assert "A&amp;B &lt;tablet&gt;" in envelope
assert validate_ipv4("192.168.178.20") == "192.168.178.20"
assert parse_action_names(
    "<scpd><actionList><action><name>GetWANAccessByIP</name></action>"
    "</actionList></scpd>"
) == ("GetWANAccessByIP",)

client = TR064Client()
HostFilterService(client)
HostsService(client)
wlan = network.WLAN(network.STA_IF)
WiFiManager("hardware-smoke", "", wlan=wlan, network_module=network)

https_rejected = False
try:
    TR064Client(use_ssl=True)
except ValueError:
    https_rejected = True
assert https_rejected


class FakeReader:
    async def readexactly(self, size):
        assert size == 5
        return b"<ok/>"


async def async_transport_smoke():
    body = await client._read_body(
        FakeReader(), 200, {"content-length": "5"}, 16
    )
    assert body == b"<ok/>"
    client._parse_www_authenticate(
        'Digest realm="fritz", nonce="abc", qop="auth,auth-int"'
    )
    assert "qop=auth" in client._build_auth_header("POST", "/control")


asyncio.run(async_transport_smoke())

gc.collect()
heap_after_checks = gc.mem_free()

print("phase25_import_smoke PASS")
print("heap_before", heap_before)
print("heap_after_import", heap_after_import)
print("heap_after_checks", heap_after_checks)
print("wifi_active", wlan.active())
print("wifi_connected", wlan.isconnected())
print("wifi_status", wlan.status())
