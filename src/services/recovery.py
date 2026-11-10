"""Fail-safe reboot reconciliation before scheduler activation."""

from core.storage import StorageError
from fritz.tr064 import TR064Error
from services.access_manager import AccessManagerError


class RecoveryError(Exception):
    pass


class RecoveryService:
    def __init__(self, clock, host_filter, access_manager, scheduler):
        self.clock = clock
        self.host_filter = host_filter
        self.access_manager = access_manager
        self.scheduler = scheduler

    async def recover(self, rtc=None):
        try:
            await self.clock.synchronize(rtc)
            now = self.clock.now()
            timers = self.access_manager.list_timers()
        except Exception as exc:
            raise RecoveryError(
                "Trusted time or persistent timer state is unavailable"
            ) from exc

        policies = self.scheduler.list_policies()
        ips = {timer["ip"] for timer in timers}
        ips.update(policy["ip"] for policy in policies)

        # Phase 1 is read-only: no WAN action is permitted until every managed
        # address has returned a valid, unambiguous router state.
        statuses = {}
        try:
            for ip_address in sorted(ips):
                status = await self.host_filter.get_wan_access_by_ip(ip_address)
                if status.get("wan_access") not in ("granted", "denied"):
                    raise RecoveryError("Router returned an ambiguous WAN state")
                statuses[ip_address] = status
        except (TR064Error, ValueError, RecoveryError) as exc:
            raise RecoveryError(
                "Router reconciliation failed before any WAN action"
            ) from exc

        due = []
        active = []
        stale = []
        for timer in timers:
            status = statuses[timer["ip"]]
            if timer["unblock_at"] > now:
                active.append((timer, status))
            elif not status["disallow"] and status["wan_access"] == "granted":
                stale.append(timer)
            elif not status["disallow"] and status["wan_access"] == "denied":
                # A filter profile still denies WAN, but the explicit timer
                # override is already clear. Remove only the stale timer.
                stale.append(timer)
            else:
                due.append(timer)

        blocked = []
        cleared = []
        unblocked = []
        try:
            # Safe-direction actions first: restore missing explicit blocks for
            # timers that have not expired.
            for timer, status in active:
                if not status["disallow"] or status["wan_access"] != "denied":
                    result = await self.host_filter.set_wan_access_and_verify(
                        timer["ip"], disallow=True
                    )
                    if not result.get("verified"):
                        raise RecoveryError("Router did not verify restored block")
                    blocked.append(timer["ip"])

            for timer in stale:
                self.access_manager.clear_timer_record(timer["ip"])
                cleared.append(timer["ip"])

            # Potentially permissive actions are deliberately last.
            for timer in due:
                await self.access_manager.unblock(timer["ip"])
                unblocked.append(timer["ip"])
        except (TR064Error, StorageError, AccessManagerError, RecoveryError) as exc:
            raise RecoveryError(
                "Recovery actions did not complete; scheduler gate remains closed"
            ) from exc

        self.scheduler.mark_recovery_complete()
        return {
            "reconciled": len(statuses),
            "blocks_restored": tuple(blocked),
            "stale_cleared": tuple(cleared),
            "expired_unblocked": tuple(unblocked),
        }
