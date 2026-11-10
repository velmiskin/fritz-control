import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from core.storage import StorageError, empty_timer_state
from fritz.tr064 import TR064Error
from services.access_manager import AccessManager, AccessManagerError


class FakeClock:
    def __init__(self, value=1000, error=None):
        self.value = value
        self.error = error

    def now(self):
        if self.error:
            raise self.error
        return self.value


class FakeStore:
    def __init__(self, state=None, load_error=None, save_error=None):
        self.state = state or empty_timer_state()
        self.load_error = load_error
        self.save_error = save_error
        self.saves = []

    def load(self):
        if self.load_error:
            raise self.load_error
        return self.state

    def save(self, state):
        if self.save_error:
            raise self.save_error
        self.state = state
        self.saves.append(state)
        return True


class FakeHostFilter:
    def __init__(self, verified=True, error=None):
        self.verified = verified
        self.error = error
        self.calls = []

    async def set_wan_access_and_verify(self, ip_address, disallow):
        self.calls.append((ip_address, disallow))
        if self.error:
            raise self.error
        return {"verified": self.verified, "disallow": disallow}


def run(awaitable):
    return asyncio.run(awaitable)


def test_block_is_verified_before_timer_is_persisted():
    router = FakeHostFilter()
    store = FakeStore()
    manager = AccessManager(router, store, FakeClock(1000))
    timer = run(manager.block_for("192.168.178.30", 900))
    assert router.calls == [("192.168.178.30", True)]
    assert timer == {
        "ip": "192.168.178.30", "blocked_at": 1000,
        "unblock_at": 1900, "state": "blocked",
    }
    assert store.state["timers"] == [timer]


def test_untrusted_clock_or_storage_failure_does_not_touch_router():
    router = FakeHostFilter()
    manager = AccessManager(router, FakeStore(), FakeClock(error=RuntimeError()))
    with pytest.raises(AccessManagerError, match="Trusted time"):
        run(manager.block_for("192.168.178.30", 900))
    assert router.calls == []

    manager = AccessManager(
        router, FakeStore(load_error=StorageError("corrupt")), FakeClock()
    )
    with pytest.raises(AccessManagerError, match="not changed"):
        run(manager.block_for("192.168.178.30", 900))
    assert router.calls == []


def test_unverified_or_failed_block_is_not_persisted():
    store = FakeStore()
    manager = AccessManager(FakeHostFilter(verified=False), store, FakeClock())
    with pytest.raises(AccessManagerError, match="did not verify"):
        run(manager.block_for("192.168.178.30", 900))
    assert store.saves == []

    manager = AccessManager(
        FakeHostFilter(error=TR064Error("offline")), store, FakeClock()
    )
    with pytest.raises(AccessManagerError, match="operation failed"):
        run(manager.block_for("192.168.178.30", 900))
    assert store.saves == []


def test_persistence_failure_never_compensates_by_unblocking():
    router = FakeHostFilter()
    store = FakeStore(save_error=StorageError("flash full"))
    manager = AccessManager(router, store, FakeClock())
    with pytest.raises(AccessManagerError, match="Device is blocked"):
        run(manager.block_for("192.168.178.30", 900))
    assert router.calls == [("192.168.178.30", True)]


def test_verified_unblock_removes_timer_after_router_change():
    existing = {
        "version": 1,
        "timers": [{
            "ip": "192.168.178.30", "blocked_at": 100,
            "unblock_at": 1000, "state": "blocked",
        }],
    }
    router = FakeHostFilter()
    store = FakeStore(existing)
    manager = AccessManager(router, store, FakeClock())
    run(manager.unblock("192.168.178.30"))
    assert router.calls == [("192.168.178.30", False)]
    assert store.state == empty_timer_state()


def test_failed_unblock_retains_timer():
    existing = {
        "version": 1,
        "timers": [{
            "ip": "192.168.178.30", "blocked_at": 100,
            "unblock_at": 1000, "state": "blocked",
        }],
    }
    store = FakeStore(existing)
    manager = AccessManager(FakeHostFilter(verified=False), store, FakeClock())
    with pytest.raises(AccessManagerError, match="effective WAN"):
        run(manager.unblock("192.168.178.30"))
    assert store.state == existing
    assert store.saves == []


@pytest.mark.parametrize("duration", [59, 7 * 24 * 60 * 60 + 1, 900.0])
def test_invalid_duration_is_rejected_without_router_action(duration):
    router = FakeHostFilter()
    manager = AccessManager(router, FakeStore(), FakeClock())
    with pytest.raises(ValueError):
        run(manager.block_for("192.168.178.30", duration))
    assert router.calls == []
