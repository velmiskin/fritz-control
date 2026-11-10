import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from api.auth import SessionAuth
from api.routes import APIRouter
from net.http_server import FileResponse, HTTPError, Request


class FakeHosts:
    async def get_hosts_page(self, offset=0, limit=4):
        assert offset == 0
        assert limit == 4
        return {"devices": [{
            "ip": "192.168.178.30", "hostname": "tablet"
        }], "total": 1, "offset": 0}


class FakeAccess:
    def __init__(self):
        self.timers = []
        self.calls = []

    def list_timers(self):
        return self.timers

    async def block_for(self, ip, duration):
        self.calls.append(("block", ip, duration))
        timer = {"ip": ip, "unblock_at": 2000}
        self.timers.append(timer)
        return timer

    async def unblock(self, ip):
        self.calls.append(("unblock", ip))
        return {"ip": ip, "verified": True}


class FakeScheduler:
    def __init__(self):
        self.policies = []

    def list_policies(self):
        return self.policies

    def replace_policies(self, policies):
        self.policies = policies


class FakeClock:
    def is_synchronized(self):
        return True


def request(method, path, body=None, headers=None):
    data = b"" if body is None else json.dumps(body).encode()
    base = dict(headers or {})
    if body is not None:
        base["content-type"] = "application/json"
    return Request(method, path, base, data)


def setup_router(tmp_path):
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    auth = SessionAuth("a-unique-password")
    access = FakeAccess()
    scheduler = FakeScheduler()
    router = APIRouter(
        auth, FakeHosts(), access, scheduler, FakeClock(), str(tmp_path), {"ok": True}
    )
    return router, auth, access, scheduler


def login_headers(auth):
    token, session = auth.login("a-unique-password")
    return {"cookie": "fc_session={}".format(token),
            "x-csrf-token": session["csrf"]}


def test_static_login_status_and_devices(tmp_path):
    router, auth, _, _ = setup_router(tmp_path)
    assert isinstance(asyncio.run(router(request("GET", "/"))), FileResponse)
    login = asyncio.run(router(request(
        "POST", "/api/login", {"password": "a-unique-password"}
    )))
    assert login.status == 200
    assert "Set-Cookie" in login.headers
    headers = login_headers(auth)
    status = json.loads(asyncio.run(router(request(
        "GET", "/api/status", headers=headers
    ))).body)
    assert status["recovery_ok"] is True
    assert status["csrf"]
    devices = json.loads(asyncio.run(router(request(
        "GET", "/api/devices?offset=0&limit=4", headers=headers
    ))).body)
    assert devices["devices"][0]["hostname"] == "tablet"


def test_mutations_require_csrf_and_dispatch(tmp_path):
    router, auth, access, scheduler = setup_router(tmp_path)
    token, session = auth.login("a-unique-password")
    cookie_only = {"cookie": "fc_session={}".format(token)}
    with pytest.raises(HTTPError) as exc:
        asyncio.run(router(request(
            "POST", "/api/block",
            {"ip": "192.168.178.30", "duration_sec": 900}, cookie_only,
        )))
    assert exc.value.status == 403
    headers = dict(cookie_only, **{"x-csrf-token": session["csrf"]})
    response = asyncio.run(router(request(
        "POST", "/api/block",
        {"ip": "192.168.178.30", "duration_sec": 900}, headers,
    )))
    assert response.status == 201
    assert access.calls == [("block", "192.168.178.30", 900)]
    policies = [{"ip": "192.168.178.30", "intervals": []}]
    asyncio.run(router(request(
        "PUT", "/api/schedules", {"policies": policies}, headers
    )))
    assert scheduler.policies == policies


def test_unknown_api_and_missing_auth_fail_closed(tmp_path):
    router, _, _, _ = setup_router(tmp_path)
    with pytest.raises(HTTPError) as exc:
        asyncio.run(router(request("GET", "/api/status")))
    assert exc.value.status == 401
    with pytest.raises(HTTPError) as exc:
        asyncio.run(router(request("GET", "/api/unknown")))
    assert exc.value.status == 404
