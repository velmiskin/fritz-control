import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from core import storage
from core.storage import StorageError, TimerStateStore, empty_timer_state


def timer_state(ip="192.168.178.30", blocked_at=100, unblock_at=1000):
    return {
        "version": 1,
        "timers": [{
            "ip": ip,
            "blocked_at": blocked_at,
            "unblock_at": unblock_at,
            "state": "blocked",
        }],
    }


def test_missing_state_is_empty_and_round_trip_is_deterministic(tmp_path):
    store = TimerStateStore(str(tmp_path / "timers.json"))
    assert store.load() == empty_timer_state()
    assert store.save(timer_state()) is True
    assert store.load() == timer_state()
    assert store.save(timer_state()) is False


def test_state_is_normalized_and_previous_version_is_retained(tmp_path):
    store = TimerStateStore(str(tmp_path / "timers.json"))
    state = {
        "version": 1,
        "timers": [
            timer_state("192.168.178.40")["timers"][0],
            timer_state("192.168.178.20")["timers"][0],
        ],
    }
    store.save(timer_state("192.168.178.10"))
    store.save(state)
    assert [item["ip"] for item in store.load()["timers"]] == [
        "192.168.178.20", "192.168.178.40"
    ]
    assert TimerStateStore(store.backup_path).load() == timer_state("192.168.178.10")


def test_corrupt_primary_loads_valid_backup_fail_closed(tmp_path):
    store = TimerStateStore(str(tmp_path / "timers.json"))
    store.save(timer_state("192.168.178.10"))
    store.save(timer_state("192.168.178.20"))
    (tmp_path / "timers.json").write_text("not json", encoding="utf-8")
    assert store.load() == timer_state("192.168.178.10")


def test_no_valid_state_raises_instead_of_silently_resetting(tmp_path):
    path = tmp_path / "timers.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(StorageError, match="No valid timer state"):
        TimerStateStore(str(path)).load()


@pytest.mark.parametrize("state", [
    {"version": 2, "timers": []},
    {"version": 1, "timers": [{
        "ip": "192.168.178.999", "blocked_at": 1,
        "unblock_at": 2, "state": "blocked",
    }]},
    {"version": 1, "timers": [{
        "ip": "192.168.178.30", "blocked_at": 1,
        "unblock_at": 1, "state": "blocked",
    }]},
    {"version": 1, "timers": [{
        "ip": "192.168.178.30", "blocked_at": 1,
        "unblock_at": 2, "state": "allowed",
    }]},
])
def test_invalid_or_non_blocked_state_is_rejected(tmp_path, state):
    with pytest.raises(StorageError):
        TimerStateStore(str(tmp_path / "timers.json")).save(state)


def test_failed_atomic_replace_restores_primary(monkeypatch, tmp_path):
    store = TimerStateStore(str(tmp_path / "timers.json"))
    original = timer_state("192.168.178.10")
    store.save(original)
    real_rename = storage.os.rename

    def fail_temp_rename(source, target):
        if source == store.temp_path:
            raise OSError("simulated power-loss boundary")
        return real_rename(source, target)

    monkeypatch.setattr(storage.os, "rename", fail_temp_rename)
    with pytest.raises(StorageError, match="Unable to persist"):
        store.save(timer_state("192.168.178.20"))
    assert store.load() == original


def test_failed_replace_preserves_valid_backup_when_primary_is_corrupt(
        monkeypatch, tmp_path):
    store = TimerStateStore(str(tmp_path / "timers.json"))
    backup_state = timer_state("192.168.178.10")
    store.save(backup_state)
    store.save(timer_state("192.168.178.20"))
    (tmp_path / "timers.json").write_text("not json", encoding="utf-8")
    real_rename = storage.os.rename

    def fail_temp_rename(source, target):
        if source == store.temp_path:
            raise OSError("simulated power-loss boundary")
        return real_rename(source, target)

    monkeypatch.setattr(storage.os, "rename", fail_temp_rename)
    with pytest.raises(StorageError, match="Unable to persist"):
        store.save(timer_state("192.168.178.30"))
    assert store.load() == backup_state
