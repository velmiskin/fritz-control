"""Non-blocking Wi-Fi STA connection and reconnect management."""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from core.logger import log


class WiFiError(Exception):
    pass


class WiFiManager:
    def __init__(self, ssid, password, wlan=None, network_module=None,
                 connect_timeout=15, poll_interval=0.25, retry_delay=5):
        if not ssid:
            raise ValueError("Wi-Fi SSID must not be empty")
        if connect_timeout <= 0 or poll_interval <= 0 or retry_delay <= 0:
            raise ValueError("Wi-Fi timing values must be positive")
        self.ssid = ssid
        self.password = password
        self.connect_timeout = connect_timeout
        self.poll_interval = poll_interval
        self.retry_delay = retry_delay

        if network_module is None:
            try:
                import network as network_module
            except ImportError:
                network_module = None
        self.network = network_module
        if wlan is None:
            if network_module is None:
                raise WiFiError("MicroPython network module is unavailable")
            interface = getattr(network_module, "IF_STA", None)
            if interface is None:
                interface = getattr(network_module, "STA_IF")
            wlan = network_module.WLAN(interface)
        self.wlan = wlan

    def _failure_statuses(self):
        if self.network is None:
            return ()
        values = []
        for name in ("STAT_WRONG_PASSWORD", "STAT_NO_AP_FOUND", "STAT_CONNECT_FAIL"):
            value = getattr(self.network, name, None)
            if value is not None:
                values.append(value)
        return tuple(values)

    async def connect(self):
        if self.wlan.isconnected():
            return self.wlan.ifconfig()

        self.wlan.active(True)
        try:
            self.wlan.config(reconnects=0)
        except (AttributeError, OSError, ValueError):
            pass
        try:
            self.wlan.disconnect()
        except OSError:
            pass
        self.wlan.connect(self.ssid, self.password)

        elapsed = 0
        failure_statuses = self._failure_statuses()
        while elapsed < self.connect_timeout:
            if self.wlan.isconnected():
                config = self.wlan.ifconfig()
                log.info("Wi-Fi connected")
                return config
            status = self.wlan.status()
            if status in failure_statuses:
                try:
                    self.wlan.disconnect()
                except OSError:
                    pass
                raise WiFiError("Wi-Fi connection failed with status {}".format(status))
            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        try:
            self.wlan.disconnect()
        except OSError:
            pass
        raise WiFiError("Wi-Fi connection timed out")

    async def maintain_connection(self):
        while True:
            if not self.wlan.isconnected():
                try:
                    await self.connect()
                except WiFiError as exc:
                    log.warn("{}; retrying".format(exc))
            await asyncio.sleep(self.retry_delay)
