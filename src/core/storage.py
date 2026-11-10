"""Bounded, fail-closed persistence for active access timers."""

try:
    import ujson as json
except ImportError:
    import json

try:
    import uos as os
except ImportError:
    import os

from core.logger import log


SCHEMA_VERSION = 1
MAX_TIMERS = 64
MAX_STATE_BYTES = 8 * 1024


class StorageError(Exception):
    pass


def empty_timer_state():
    return {"version": SCHEMA_VERSION, "timers": []}


def _is_ipv4(value):
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part or not part.isdigit():
            return False
        if len(part) > 1 and part[0] == "0":
            return False
        if int(part) > 255:
            return False
    return True


def validate_timer_state(state):
    if not isinstance(state, dict):
        raise StorageError("Timer state must be an object")
    if state.get("version") != SCHEMA_VERSION:
        raise StorageError("Unsupported timer-state schema version")
    timers = state.get("timers")
    if not isinstance(timers, list):
        raise StorageError("Timer state must contain a timers list")
    if len(timers) > MAX_TIMERS:
        raise StorageError("Timer count exceeds limit")

    normalized = []
    seen_ips = set()
    for timer in timers:
        if not isinstance(timer, dict):
            raise StorageError("Timer entry must be an object")
        ip_address = timer.get("ip")
        if not _is_ipv4(ip_address):
            raise StorageError("Timer entry contains an invalid IPv4 address")
        if ip_address in seen_ips:
            raise StorageError("Timer state contains a duplicate IPv4 address")
        seen_ips.add(ip_address)

        blocked_at = timer.get("blocked_at")
        unblock_at = timer.get("unblock_at")
        if type(blocked_at) is not int or blocked_at < 0:
            raise StorageError("blocked_at must be a non-negative integer")
        if type(unblock_at) is not int or unblock_at <= blocked_at:
            raise StorageError("unblock_at must be later than blocked_at")
        if timer.get("state") != "blocked":
            raise StorageError("Only blocked timer state may be persisted")

        normalized.append({
            "ip": ip_address,
            "blocked_at": blocked_at,
            "unblock_at": unblock_at,
            "state": "blocked",
        })
    normalized.sort(key=lambda item: item["ip"])
    return {"version": SCHEMA_VERSION, "timers": normalized}


class TimerStateStore:
    def __init__(self, path="timer_state.json"):
        if not isinstance(path, str) or not path:
            raise ValueError("Storage path must be a non-empty string")
        self.path = path
        self.temp_path = path + ".tmp"
        self.backup_path = path + ".bak"

    @staticmethod
    def _exists(path):
        try:
            os.stat(path)
            return True
        except OSError:
            return False

    @staticmethod
    def _remove_if_exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _sync():
        sync = getattr(os, "sync", None)
        if sync is not None:
            sync()

    def _read_file(self, path):
        try:
            with open(path, "r") as state_file:
                raw = state_file.read(MAX_STATE_BYTES + 1)
        except OSError as exc:
            raise StorageError("Unable to read timer state") from exc
        if len(raw) > MAX_STATE_BYTES:
            raise StorageError("Timer state exceeds size limit")
        try:
            state = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise StorageError("Timer state is not valid JSON") from exc
        return validate_timer_state(state)

    def load(self):
        if self._exists(self.path):
            try:
                return self._read_file(self.path)
            except StorageError:
                log.error("Primary timer state is invalid; checking backup")
        if self._exists(self.backup_path):
            try:
                state = self._read_file(self.backup_path)
                log.warn("Loaded previous timer state from backup")
                return state
            except StorageError:
                log.error("Backup timer state is invalid")
        if not self._exists(self.path) and not self._exists(self.backup_path):
            return empty_timer_state()
        raise StorageError("No valid timer state is available")

    def save(self, state):
        normalized = validate_timer_state(state)
        primary_exists = self._exists(self.path)
        primary_valid = False
        if primary_exists:
            try:
                current = self._read_file(self.path)
                primary_valid = True
                if current == normalized:
                    return False
            except StorageError:
                pass

        serialized = json.dumps(normalized)
        if len(serialized.encode("utf-8")) > MAX_STATE_BYTES:
            raise StorageError("Timer state exceeds size limit")

        self._remove_if_exists(self.temp_path)
        try:
            with open(self.temp_path, "w") as state_file:
                state_file.write(serialized)
                flush = getattr(state_file, "flush", None)
                if flush is not None:
                    flush()
            self._sync()

            if primary_valid:
                self._remove_if_exists(self.backup_path)
                os.rename(self.path, self.backup_path)
            elif primary_exists:
                if self._exists(self.backup_path):
                    self._remove_if_exists(self.path)
                else:
                    # Preserve corrupt evidence so load() remains fail-closed
                    # if installing the new primary is interrupted.
                    os.rename(self.path, self.backup_path)
            try:
                os.rename(self.temp_path, self.path)
                self._sync()
            except Exception:
                if primary_valid and not self._exists(self.path):
                    os.rename(self.backup_path, self.path)
                raise
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to persist timer state") from exc
        finally:
            self._remove_if_exists(self.temp_path)
        return True
