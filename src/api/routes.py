"""Authenticated REST and static dashboard routes."""

from core.storage import StorageError
from fritz.tr064 import TR064Error
from net.http_server import FileResponse, HTTPError, Response
from services.access_manager import AccessManagerError
from services.recovery import RecoveryError
from services.scheduler import SchedulerError


CONTENT_TYPES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("css/style.css", "text/css; charset=utf-8"),
    "/app.js": ("js/app.js", "application/javascript; charset=utf-8"),
}


class APIRouter:
    def __init__(self, auth, hosts, access_manager, scheduler, clock,
                 www_root="/www", recovery_status=None):
        self.auth = auth
        self.hosts = hosts
        self.access_manager = access_manager
        self.scheduler = scheduler
        self.clock = clock
        self.www_root = www_root.rstrip("/")
        self.recovery_status = recovery_status if recovery_status is not None else {}

    def _auth(self, request, csrf=False):
        return self.auth.require(request, csrf=csrf)

    async def _login(self, request):
        data = request.json()
        token, session = self.auth.login(data.get("password", ""))
        return Response.json({
            "ok": True, "csrf": session["csrf"],
            "expires_in": self.auth.ttl_seconds,
        }, headers={
            "Set-Cookie": self.auth.cookie_header(token, self.auth.ttl_seconds),
        })

    async def _devices(self, request):
        self._auth(request)
        parameters = {}
        for pair in request.query.split("&") if request.query else ():
            key, separator, value = pair.partition("=")
            if separator:
                parameters[key] = value
        try:
            offset = int(parameters.get("offset", "0"))
            limit = int(parameters.get("limit", "4"))
        except ValueError as exc:
            raise HTTPError(400, "Invalid device page") from exc
        return Response.json(await self.hosts.get_hosts_page(offset, limit))

    async def _status(self, request):
        _, session = self._auth(request)
        timers = self.access_manager.list_timers()
        return Response.json({
            "clock_synchronized": self.clock.is_synchronized(),
            "recovery_ok": bool(self.recovery_status.get("ok")),
            "timer_count": len(timers),
            "schedule_count": len(self.scheduler.list_policies()),
            "csrf": session["csrf"],
        })

    async def _block(self, request):
        self._auth(request, csrf=True)
        data = request.json()
        timer = await self.access_manager.block_for(
            data.get("ip"), data.get("duration_sec")
        )
        return Response.json({"timer": timer}, 201)

    async def _unblock(self, request):
        self._auth(request, csrf=True)
        data = request.json()
        result = await self.access_manager.unblock(data.get("ip"))
        return Response.json({"status": result})

    async def _schedules_put(self, request):
        self._auth(request, csrf=True)
        data = request.json()
        policies = data.get("policies")
        if not isinstance(policies, list):
            raise HTTPError(400, "policies must be a list")
        self.scheduler.replace_policies(policies)
        return Response.json({"policies": self.scheduler.list_policies()})

    async def __call__(self, request):
        try:
            if request.path in CONTENT_TYPES and request.method == "GET":
                relative, content_type = CONTENT_TYPES[request.path]
                return FileResponse(self.www_root + "/" + relative, content_type)
            if request.path == "/api/login" and request.method == "POST":
                return await self._login(request)
            if request.path == "/api/logout" and request.method == "POST":
                self.auth.logout(request)
                return Response.json({"ok": True}, headers={
                    "Set-Cookie": "fc_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
                })
            if request.path == "/api/status" and request.method == "GET":
                return await self._status(request)
            if request.path == "/api/devices" and request.method == "GET":
                return await self._devices(request)
            if request.path == "/api/timers" and request.method == "GET":
                self._auth(request)
                return Response.json({"timers": self.access_manager.list_timers()})
            if request.path == "/api/block" and request.method == "POST":
                return await self._block(request)
            if request.path == "/api/unblock" and request.method == "POST":
                return await self._unblock(request)
            if request.path == "/api/schedules" and request.method == "GET":
                self._auth(request)
                return Response.json({"policies": self.scheduler.list_policies()})
            if request.path == "/api/schedules" and request.method == "PUT":
                return await self._schedules_put(request)
            if request.path.startswith("/api/"):
                raise HTTPError(404, "API route not found")
            raise HTTPError(404, "Not found")
        except HTTPError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPError(400, str(exc)) from exc
        except (AccessManagerError, SchedulerError, RecoveryError,
                StorageError, TR064Error) as exc:
            raise HTTPError(503, str(exc)) from exc
