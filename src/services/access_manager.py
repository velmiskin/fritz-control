"""Verified timed WAN access control with fail-closed persistence."""

from core.storage import SCHEMA_VERSION, StorageError
from fritz.tr064 import TR064Error
from fritz.validation import validate_ipv4


PRESET_DURATIONS = (15 * 60, 30 * 60, 60 * 60, 2 * 60 * 60)
MIN_DURATION_SEC = 60
MAX_DURATION_SEC = 7 * 24 * 60 * 60


class AccessManagerError(Exception):
    pass


class AccessManager:
    def __init__(self, host_filter, store, clock):
        self.host_filter = host_filter
        self.store = store
        self.clock = clock

    @staticmethod
    def _validate_duration(duration_sec):
        if type(duration_sec) is not int:
            raise ValueError("Duration must be an integer number of seconds")
        if duration_sec < MIN_DURATION_SEC or duration_sec > MAX_DURATION_SEC:
            raise ValueError("Duration must be between 60 seconds and 7 days")
        return duration_sec

    def _trusted_now(self):
        try:
            now = self.clock.now()
        except Exception as exc:
            raise AccessManagerError("Trusted time is unavailable") from exc
        if type(now) is not int or now < 0:
            raise AccessManagerError("Trusted clock returned an invalid time")
        return now

    @staticmethod
    def _upsert_timer(state, timer):
        timers = [item for item in state["timers"] if item["ip"] != timer["ip"]]
        timers.append(timer)
        return {"version": SCHEMA_VERSION, "timers": timers}

    @staticmethod
    def _remove_timer(state, ip_address):
        return {
            "version": SCHEMA_VERSION,
            "timers": [
                item for item in state["timers"] if item["ip"] != ip_address
            ],
        }

    async def block_for(self, ip_address, duration_sec):
        ip_address = validate_ipv4(ip_address)
        duration_sec = self._validate_duration(duration_sec)
        now = self._trusted_now()
        try:
            state = self.store.load()
        except StorageError as exc:
            raise AccessManagerError(
                "Timer storage is unavailable; router state was not changed"
            ) from exc

        try:
            result = await self.host_filter.set_wan_access_and_verify(
                ip_address, disallow=True
            )
        except TR064Error as exc:
            raise AccessManagerError("Router block operation failed") from exc
        if not result.get("verified"):
            raise AccessManagerError("Router did not verify the blocked state")

        timer = {
            "ip": ip_address,
            "blocked_at": now,
            "unblock_at": now + duration_sec,
            "state": "blocked",
        }
        try:
            self.store.save(self._upsert_timer(state, timer))
        except StorageError as exc:
            # Never compensate by unblocking: a persistence failure leaves the
            # device blocked and requires explicit reconciliation.
            raise AccessManagerError(
                "Device is blocked but its timer could not be persisted"
            ) from exc
        return timer

    async def unblock(self, ip_address):
        ip_address = validate_ipv4(ip_address)
        self._trusted_now()
        try:
            state = self.store.load()
        except StorageError as exc:
            raise AccessManagerError(
                "Timer storage is unavailable; router state was not changed"
            ) from exc
        try:
            result = await self.host_filter.set_wan_access_and_verify(
                ip_address, disallow=False
            )
        except TR064Error as exc:
            raise AccessManagerError("Router unblock operation failed") from exc
        if not result.get("verified"):
            raise AccessManagerError("Router did not verify effective WAN access")
        try:
            self.store.save(self._remove_timer(state, ip_address))
        except StorageError as exc:
            raise AccessManagerError(
                "Device is allowed but stale timer cleanup failed"
            ) from exc
        return result

    def list_timers(self):
        try:
            return self.store.load()["timers"]
        except StorageError as exc:
            raise AccessManagerError("Timer storage is unavailable") from exc
