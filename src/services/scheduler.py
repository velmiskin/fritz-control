"""Recovery-gated timer and weekly blocking scheduler."""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import ujson as json
except ImportError:
    import json

try:
    import uos as os
except ImportError:
    import os

from core.logger import log
from fritz.tr064 import TR064Error
from fritz.validation import validate_ipv4
from core.storage import StorageError


MINUTES_PER_DAY = 24 * 60
SECONDS_PER_DAY = 24 * 60 * 60
MAX_POLICIES = 64
MAX_POLICY_BYTES = 16 * 1024


class SchedulerError(Exception):
    pass


class WeeklyPolicy:
    """Weekly intervals during which WAN access must be blocked."""

    def __init__(self, ip_address, intervals):
        self.ip = validate_ipv4(ip_address)
        if not isinstance(intervals, list) or not intervals:
            raise ValueError("Weekly policy requires at least one interval")
        normalized = []
        for interval in intervals:
            if not isinstance(interval, dict):
                raise ValueError("Schedule interval must be an object")
            day = interval.get("day")
            start = interval.get("start_minute")
            end = interval.get("end_minute")
            if type(day) is not int or day < 0 or day > 6:
                raise ValueError("Schedule day must be 0 through 6")
            if (type(start) is not int or type(end) is not int or
                    start < 0 or end > MINUTES_PER_DAY or start >= end):
                raise ValueError("Schedule interval minutes are invalid")
            normalized.append((day, start, end))
        normalized.sort()
        for index in range(1, len(normalized)):
            previous = normalized[index - 1]
            current = normalized[index]
            if current[0] == previous[0] and current[1] < previous[2]:
                raise ValueError("Schedule intervals must not overlap")
        self.intervals = tuple(normalized)

    def is_blocked_at(self, unix_time, timezone_offset_hours=0):
        if type(unix_time) is not int or unix_time < 0:
            raise ValueError("Unix time must be a non-negative integer")
        if type(timezone_offset_hours) is not int or not -12 <= timezone_offset_hours <= 14:
            raise ValueError("Timezone offset must be an integer from -12 to 14")
        local_time = unix_time + timezone_offset_hours * 3600
        days, seconds = divmod(local_time, SECONDS_PER_DAY)
        day = (days + 3) % 7  # 1970-01-01 was Thursday; Monday is zero.
        minute = seconds // 60
        for interval_day, start, end in self.intervals:
            if interval_day == day and start <= minute < end:
                return True
        return False

    def as_dict(self):
        return {
            "ip": self.ip,
            "intervals": [
                {"day": day, "start_minute": start, "end_minute": end}
                for day, start, end in self.intervals
            ],
        }


class WeeklyPolicyStore:
    def __init__(self, path="weekly_policies.json"):
        if not isinstance(path, str) or not path:
            raise ValueError("Policy storage path must be a non-empty string")
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
    def _remove(path):
        try:
            os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _normalize(policies):
        if not isinstance(policies, list) or len(policies) > MAX_POLICIES:
            raise StorageError("Weekly policy list is invalid or exceeds limit")
        normalized = []
        seen = set()
        for value in policies:
            try:
                policy = value if isinstance(value, WeeklyPolicy) else WeeklyPolicy(
                    value["ip"], value["intervals"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise StorageError("Weekly policy is invalid") from exc
            if policy.ip in seen:
                raise StorageError("Duplicate weekly policy device")
            seen.add(policy.ip)
            normalized.append(policy.as_dict())
        normalized.sort(key=lambda item: item["ip"])
        return normalized

    def _read(self, path):
        try:
            with open(path, "r") as policy_file:
                raw = policy_file.read(MAX_POLICY_BYTES + 1)
        except OSError as exc:
            raise StorageError("Unable to read weekly policies") from exc
        if len(raw) > MAX_POLICY_BYTES:
            raise StorageError("Weekly policies exceed size limit")
        try:
            document = json.loads(raw)
            if document.get("version") != 1:
                raise StorageError("Unsupported weekly-policy schema")
            return self._normalize(document.get("policies"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise StorageError("Weekly policies are not valid JSON") from exc

    def load(self):
        if self._exists(self.path):
            try:
                return self._read(self.path)
            except StorageError:
                log.error("Primary weekly policies are invalid; checking backup")
        if self._exists(self.backup_path):
            try:
                policies = self._read(self.backup_path)
                log.warn("Loaded previous weekly policies from backup")
                return policies
            except StorageError:
                pass
        if not self._exists(self.path) and not self._exists(self.backup_path):
            return []
        raise StorageError("No valid weekly policies are available")

    def save(self, policies):
        normalized = self._normalize(policies)
        primary_exists = self._exists(self.path)
        primary_valid = False
        if primary_exists:
            try:
                current = self._read(self.path)
                primary_valid = True
                if current == normalized:
                    return False
            except StorageError:
                pass
        serialized = json.dumps({"version": 1, "policies": normalized})
        if len(serialized.encode("utf-8")) > MAX_POLICY_BYTES:
            raise StorageError("Weekly policies exceed size limit")

        self._remove(self.temp_path)
        try:
            with open(self.temp_path, "w") as policy_file:
                policy_file.write(serialized)
                flush = getattr(policy_file, "flush", None)
                if flush:
                    flush()
            sync = getattr(os, "sync", None)
            if sync:
                sync()
            if primary_valid:
                self._remove(self.backup_path)
                os.rename(self.path, self.backup_path)
            elif primary_exists:
                if self._exists(self.backup_path):
                    self._remove(self.path)
                else:
                    os.rename(self.path, self.backup_path)
            try:
                os.rename(self.temp_path, self.path)
            except Exception:
                if primary_valid and not self._exists(self.path):
                    os.rename(self.backup_path, self.path)
                raise
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Unable to persist weekly policies") from exc
        finally:
            self._remove(self.temp_path)
        return True


class Scheduler:
    def __init__(self, access_manager, host_filter, clock, policies=None,
                 timezone_offset_hours=0, tick_interval=5, policy_store=None):
        if tick_interval <= 0:
            raise ValueError("Scheduler tick interval must be positive")
        if type(timezone_offset_hours) is not int or not -12 <= timezone_offset_hours <= 14:
            raise ValueError("Timezone offset must be an integer from -12 to 14")
        self.access_manager = access_manager
        self.host_filter = host_filter
        self.clock = clock
        self.timezone_offset_hours = timezone_offset_hours
        self.tick_interval = tick_interval
        self.policy_store = policy_store
        self._policies = {}
        self._last_weekly_state = {}
        self._recovery_complete = False
        if policies is None and policy_store is not None:
            policies = policy_store.load()
        self.set_policies(policies or [])

    def set_policies(self, policies):
        new_policies = {}
        for policy in policies:
            if not isinstance(policy, WeeklyPolicy):
                policy = WeeklyPolicy(policy["ip"], policy["intervals"])
            if policy.ip in new_policies:
                raise ValueError("Only one weekly policy is allowed per device")
            new_policies[policy.ip] = policy
        self._policies = new_policies
        self._last_weekly_state = {}

    def list_policies(self):
        return [self._policies[ip].as_dict() for ip in sorted(self._policies)]

    def replace_policies(self, policies):
        candidates = []
        for policy in policies:
            candidates.append(
                policy if isinstance(policy, WeeklyPolicy) else WeeklyPolicy(
                    policy["ip"], policy["intervals"]
                )
            )
        if self.policy_store is not None:
            self.policy_store.save(candidates)
        self.set_policies(candidates)

    def mark_recovery_complete(self):
        self._recovery_complete = True
        self._last_weekly_state = {}

    async def _set_weekly_state(self, ip_address, disallow):
        try:
            result = await self.host_filter.set_wan_access_and_verify(
                ip_address, disallow=disallow
            )
        except TR064Error as exc:
            raise SchedulerError("Weekly WAN state change failed") from exc
        if not result.get("verified"):
            raise SchedulerError("Router did not verify weekly WAN state")

    async def tick(self):
        if not self._recovery_complete:
            raise SchedulerError("Scheduler recovery gate is closed")
        try:
            now = self.clock.now()
            timers = self.access_manager.list_timers()
        except Exception as exc:
            raise SchedulerError("Trusted time or timer state unavailable") from exc

        timers_by_ip = {timer["ip"]: timer for timer in timers}
        weekly_now = {
            ip: policy.is_blocked_at(now, self.timezone_offset_hours)
            for ip, policy in self._policies.items()
        }
        for timer in tuple(timers):
            if timer["unblock_at"] <= now:
                if weekly_now.get(timer["ip"], False):
                    self.access_manager.clear_timer_record(timer["ip"])
                else:
                    await self.access_manager.unblock(timer["ip"])
                timers_by_ip.pop(timer["ip"], None)

        for ip_address, weekly_blocked in weekly_now.items():
            desired_blocked = weekly_blocked or ip_address in timers_by_ip
            if self._last_weekly_state.get(ip_address) == desired_blocked:
                continue
            await self._set_weekly_state(ip_address, desired_blocked)
            self._last_weekly_state[ip_address] = desired_blocked

    async def run(self):
        while True:
            try:
                await self.tick()
            except SchedulerError as exc:
                log.warn("Scheduler tick failed: {}".format(exc))
            await asyncio.sleep(self.tick_interval)
