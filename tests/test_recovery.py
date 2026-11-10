import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fritz.tr064 import TR064Error
from services.recovery import RecoveryError, RecoveryService


class FakeClock:
    def __init__(self, events, now=1000, error=None):
        self.events = events
        self.value = now
        self.error = error

    async def synchronize(self, rtc=None):
        self.events.append("sync")
        if self.error:
            raise self.error

    def now(self):
        return self.value


class FakeHostFilter:
    def __init__(self, events, statuses, read_error_ip=None, verified=True):
        self.events = events
        self.statuses = statuses
        self.read_error_ip = read_error_ip
        self.verified = verified

    async def get_wan_access_by_ip(self, ip_address):
        self.events.append(("read", ip_address))
        if ip_address == self.read_error_ip:
            raise TR064Error("offline")
        return dict(self.statuses[ip_address])

    async def set_wan_access_and_verify(self, ip_address, disallow):
        self.events.append(("set", ip_address, disallow))
        return {"verified": self.verified}


class FakeAccessManager:
    def __init__(self, events, timers):
        self.events = events
        self.timers = list(timers)

    def list_timers(self):
        self.events.append("load")
        return list(self.timers)

    def clear_timer_record(self, ip_address):
        self.events.append(("clear", ip_address))
        self.timers = [item for item in self.timers if item["ip"] != ip_address]

    async def unblock(self, ip_address):
        self.events.append(("unblock", ip_address))
        self.timers = [item for item in self.timers if item["ip"] != ip_address]


class FakeScheduler:
    def __init__(self, events, policies=()):
        self.events = events
        self.policies = list(policies)
        self.ready = False

    def list_policies(self):
        return list(self.policies)

    def mark_recovery_complete(self):
        self.events.append("gate_open")
        self.ready = True


def timer(ip, unblock_at):
    return {
        "ip": ip, "blocked_at": 100,
        "unblock_at": unblock_at, "state": "blocked",
    }


def status(disallow, wan_access):
    return {"disallow": disallow, "wan_access": wan_access}


def recover(clock, router, access, scheduler):
    return asyncio.run(RecoveryService(
        clock, router, access, scheduler
    ).recover())


def test_recovery_reads_every_state_before_safe_then_permissive_actions():
    events = []
    timers = [
        timer("192.168.178.20", 2000),
        timer("192.168.178.30", 900),
    ]
    router = FakeHostFilter(events, {
        "192.168.178.20": status(False, "granted"),
        "192.168.178.30": status(True, "denied"),
        "192.168.178.40": status(False, "granted"),
    })
    access = FakeAccessManager(events, timers)
    scheduler = FakeScheduler(events, [{"ip": "192.168.178.40"}])
    result = recover(FakeClock(events), router, access, scheduler)
    reads = [event for event in events if isinstance(event, tuple) and event[0] == "read"]
    first_action = events.index(("set", "192.168.178.20", True))
    assert len(reads) == 3
    assert all(events.index(event) < first_action for event in reads)
    assert events.index(("set", "192.168.178.20", True)) < events.index(
        ("unblock", "192.168.178.30")
    )
    assert events[-1] == "gate_open"
    assert result["blocks_restored"] == ("192.168.178.20",)
    assert result["expired_unblocked"] == ("192.168.178.30",)


def test_due_timer_already_allowed_is_cleared_without_wan_action():
    events = []
    ip = "192.168.178.30"
    access = FakeAccessManager(events, [timer(ip, 900)])
    scheduler = FakeScheduler(events)
    result = recover(
        FakeClock(events), FakeHostFilter(events, {ip: status(False, "granted")}),
        access, scheduler,
    )
    assert ("clear", ip) in events
    assert not any(event[0] in ("set", "unblock") for event in events if isinstance(event, tuple))
    assert result["stale_cleared"] == (ip,)


def test_profile_denial_without_override_clears_only_timer():
    events = []
    ip = "192.168.178.30"
    access = FakeAccessManager(events, [timer(ip, 900)])
    recover(
        FakeClock(events), FakeHostFilter(events, {ip: status(False, "denied")}),
        access, FakeScheduler(events),
    )
    assert ("clear", ip) in events
    assert ("unblock", ip) not in events


def test_read_failure_prevents_all_actions_and_keeps_gate_closed():
    events = []
    timers = [timer("192.168.178.20", 2000), timer("192.168.178.30", 900)]
    router = FakeHostFilter(events, {
        "192.168.178.20": status(False, "granted"),
        "192.168.178.30": status(True, "denied"),
    }, read_error_ip="192.168.178.30")
    scheduler = FakeScheduler(events)
    with pytest.raises(RecoveryError, match="before any WAN action"):
        recover(FakeClock(events), router, FakeAccessManager(events, timers), scheduler)
    assert not any(event[0] in ("set", "unblock", "clear")
                   for event in events if isinstance(event, tuple))
    assert scheduler.ready is False


def test_time_sync_failure_does_not_read_or_change_router():
    events = []
    scheduler = FakeScheduler(events)
    with pytest.raises(RecoveryError, match="Trusted time"):
        recover(
            FakeClock(events, error=RuntimeError("no time")),
            FakeHostFilter(events, {}), FakeAccessManager(events, []), scheduler,
        )
    assert events == ["sync"]
    assert scheduler.ready is False


def test_unverified_restore_keeps_gate_closed_and_never_unblocks_due_timer():
    events = []
    active_ip = "192.168.178.20"
    due_ip = "192.168.178.30"
    timers = [timer(active_ip, 2000), timer(due_ip, 900)]
    router = FakeHostFilter(events, {
        active_ip: status(False, "granted"),
        due_ip: status(True, "denied"),
    }, verified=False)
    scheduler = FakeScheduler(events)
    with pytest.raises(RecoveryError, match="gate remains closed"):
        recover(FakeClock(events), router, FakeAccessManager(events, timers), scheduler)
    assert ("unblock", due_ip) not in events
    assert scheduler.ready is False
