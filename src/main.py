"""FritzControl application entrypoint for ESP32 MicroPython."""

import gc
import uasyncio as asyncio

from api.auth import SessionAuth
from api.routes import APIRouter
from core.config import Config
from core.logger import log
from core.storage import TimerStateStore
from fritz.host_filter import HostFilterService
from fritz.hosts import HostsService
from fritz.tr064 import TR064Client
from net.http_server import AsyncHTTPServer
from net.ntp import NTPClient
from net.wifi import WiFiManager
from services.access_manager import AccessManager
from services.recovery import RecoveryError, RecoveryService
from services.scheduler import Scheduler, WeeklyPolicyStore


async def main():
    config = Config.load("config.json")
    log.set_level(config.get("system", "log_level", "INFO"))
    # Validate security configuration before network or router activity.
    auth = SessionAuth(config.web_password)
    wifi = WiFiManager(
        config.get("wifi", "ssid", ""),
        config.get("wifi", "password", ""),
    )
    network_config = await wifi.connect()

    client = TR064Client(
        host=config.fritz_host, port=config.fritz_port,
        username=config.fritz_user, password=config.fritz_password,
        use_ssl=config.fritz_use_ssl,
    )
    hosts = HostsService(client)
    host_filter = HostFilterService(client)
    clock = NTPClient(
        server=config.get("ntp", "server", "pool.ntp.org"),
        dns_server=network_config[3],
    )
    timer_store = TimerStateStore("timer_state.json")
    access_manager = AccessManager(host_filter, timer_store, clock)
    policy_store = WeeklyPolicyStore("weekly_policies.json")
    scheduler = Scheduler(
        access_manager, host_filter, clock, policies=None,
        timezone_offset_hours=config.get("ntp", "timezone_offset_hours", 0),
        policy_store=policy_store,
    )
    recovery_status = {"ok": False}
    recovery = RecoveryService(clock, host_filter, access_manager, scheduler)
    try:
        recovery_status["result"] = await recovery.recover()
        recovery_status["ok"] = True
    except RecoveryError as exc:
        log.error("Recovery gate remains closed: {}".format(exc))

    router = APIRouter(
        auth, hosts, access_manager, scheduler, clock,
        www_root="/www", recovery_status=recovery_status,
    )
    server = AsyncHTTPServer(router, port=config.web_port)
    await server.start()
    log.info("Dashboard listening on port {}".format(config.web_port))

    asyncio.create_task(wifi.maintain_connection())
    if recovery_status["ok"]:
        asyncio.create_task(scheduler.run())
    gc.collect()
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Application stopped")
