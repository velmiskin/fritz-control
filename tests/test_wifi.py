import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from net.wifi import WiFiError, WiFiManager


class FakeNetwork:
    STAT_WRONG_PASSWORD = -3
    STAT_NO_AP_FOUND = -2
    STAT_CONNECT_FAIL = -1


class FakeWLAN:
    def __init__(self, statuses, config=("192.168.178.50", "255.255.255.0", "192.168.178.1", "192.168.178.1")):
        self.statuses = list(statuses)
        self.network_config = config
        self.connected = False
        self.password_seen = None
        self.active_state = False
        self.disconnected = False

    def active(self, value):
        self.active_state = value

    def config(self, **kwargs):
        return kwargs

    def connect(self, ssid, password):
        self.password_seen = password

    def disconnect(self):
        self.disconnected = True

    def status(self):
        if self.statuses:
            status = self.statuses.pop(0)
            if status == 3:
                self.connected = True
            return status
        return 0

    def isconnected(self):
        return self.connected

    def ifconfig(self):
        return self.network_config


def test_wifi_connect_is_async_and_returns_network_config():
    async def run():
        wlan = FakeWLAN([1, 3])
        manager = WiFiManager(
            "ssid", "secret", wlan=wlan, network_module=FakeNetwork,
            connect_timeout=1, poll_interval=0.001,
        )
        config = await manager.connect()
        assert config[0] == "192.168.178.50"
        assert wlan.active_state is True
        assert wlan.password_seen == "secret"
    asyncio.run(run())


def test_wifi_stops_on_authentication_failure_without_logging_password():
    async def run():
        wlan = FakeWLAN([FakeNetwork.STAT_WRONG_PASSWORD])
        manager = WiFiManager(
            "ssid", "do-not-log", wlan=wlan, network_module=FakeNetwork,
            connect_timeout=1, poll_interval=0.001,
        )
        with pytest.raises(WiFiError, match="status") as exc:
            await manager.connect()
        assert "do-not-log" not in str(exc.value)
    asyncio.run(run())
