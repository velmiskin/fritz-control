import asyncio
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from services.scheduler import Scheduler, SchedulerError, WeeklyPolicy


def unix(year, month, day, hour=0, minute=0):
    return int(datetime.datetime(
        year, month, day, hour, minute, tzinfo=datetime.timezone.utc
    ).timestamp())


class FakeClock:
    def __init__(self, value):
        self.value = value

    def now(self):
        return self.value


class FakeAccessManager:
    def __init__(self, timers=()):
        self.timers = list(timers)
        self.unblocked = []
        self.cleared = []

    def list_timers(self):
        return list(self.timers)

    async def unblock(self, ip_address):
        self.unblocked.append(ip_address)
        self.timers = [item for item in self.timers if item["ip"] != ip_address]

    def clear_timer_record(self, ip_address):
        self.cleared.append(ip_address)
        self.timers = [item for item in self.timers if item["ip"] != ip_address]


class FakeHostFilter:
    def __init__(self, verified=True):
        self.verified = verified
        self.calls = []

    async def set_wan_access_and_verify(self, ip_address, disallow):
        self.calls.append((ip_address, disallow))
        return {"verified": self.verified}


def timer(ip, unblock_at):
    return {
        "ip": ip, "blocked_at": unblock_at - 100,
        "unblock_at": unblock_at, "state": "blocked",
    }


def test_weekly_policy_uses_monday_zero_and_fixed_timezone_offset():
    policy = WeeklyPolicy("192.168.178.30", [
        {"day": 0, "start_minute": 8 * 60, "end_minute": 9 * 60},
    ])
    assert policy.is_blocked_at(unix(2026, 11, 9, 8, 30)) is True  # Monday
    assert policy.is_blocked_at(unix(2026, 11, 9, 7, 30), 1) is True
    assert policy.is_blocked_at(unix(2026, 11, 9, 9, 0)) is False


@pytest.mark.parametrize("intervals", [
    [{"day": 7, "start_minute": 0, "end_minute": 1}],
    [{"day": 0, "start_minute": 60, "end_minute": 60}],
    [
        {"day": 0, "start_minute": 60, "end_minute": 120},
        {"day": 0, "start_minute": 90, "end_minute": 180},
    ],
])
def test_invalid_weekly_intervals_are_rejected(intervals):
    with pytest.raises(ValueError):
        WeeklyPolicy("192.168.178.30", intervals)


def test_scheduler_does_nothing_before_recovery():
    router = FakeHostFilter()
    scheduler = Scheduler(
        FakeAccessManager(), router, FakeClock(unix(2026, 11, 9, 8, 30)),
        [WeeklyPolicy("192.168.178.30", [
            {"day": 0, "start_minute": 480, "end_minute": 540},
        ])],
    )
    with pytest.raises(SchedulerError, match="gate"):
        asyncio.run(scheduler.tick())
    assert router.calls == []


def test_due_timer_unblocks_after_recovery():
    now = unix(2026, 11, 9, 10)
    access = FakeAccessManager([timer("192.168.178.30", now)])
    scheduler = Scheduler(access, FakeHostFilter(), FakeClock(now))
    scheduler.mark_recovery_complete()
    asyncio.run(scheduler.tick())
    assert access.unblocked == ["192.168.178.30"]


def test_weekly_block_prevents_transient_unblock_for_due_timer():
    now = unix(2026, 11, 9, 8, 30)
    access = FakeAccessManager([timer("192.168.178.30", now)])
    router = FakeHostFilter()
    scheduler = Scheduler(access, router, FakeClock(now), [
        WeeklyPolicy("192.168.178.30", [
            {"day": 0, "start_minute": 480, "end_minute": 540},
        ])
    ])
    scheduler.mark_recovery_complete()
    asyncio.run(scheduler.tick())
    assert access.unblocked == []
    assert access.cleared == ["192.168.178.30"]
    assert router.calls == [("192.168.178.30", True)]


def test_active_timer_keeps_policy_device_blocked_outside_interval():
    now = unix(2026, 11, 9, 10)
    access = FakeAccessManager([timer("192.168.178.30", now + 600)])
    router = FakeHostFilter()
    scheduler = Scheduler(access, router, FakeClock(now), [
        WeeklyPolicy("192.168.178.30", [
            {"day": 0, "start_minute": 480, "end_minute": 540},
        ])
    ])
    scheduler.mark_recovery_complete()
    asyncio.run(scheduler.tick())
    asyncio.run(scheduler.tick())
    assert router.calls == [("192.168.178.30", True)]


def test_unverified_weekly_change_is_retried_not_cached():
    now = unix(2026, 11, 9, 8, 30)
    router = FakeHostFilter(verified=False)
    scheduler = Scheduler(FakeAccessManager(), router, FakeClock(now), [
        WeeklyPolicy("192.168.178.30", [
            {"day": 0, "start_minute": 480, "end_minute": 540},
        ])
    ])
    scheduler.mark_recovery_complete()
    with pytest.raises(SchedulerError, match="did not verify"):
        asyncio.run(scheduler.tick())
    with pytest.raises(SchedulerError):
        asyncio.run(scheduler.tick())
    assert len(router.calls) == 2
