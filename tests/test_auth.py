import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from api.auth import SessionAuth
from net.http_server import HTTPError, Request


def request(headers=None):
    return Request("POST", "/api/action", headers or {}, b"")


def test_default_short_and_placeholder_passwords_are_rejected():
    for password in ("admin", "short", "CHANGE_ME_TO_A_UNIQUE_PASSWORD", "YOUR_PASSWORD"):
        with pytest.raises(ValueError):
            SessionAuth(password)


def test_login_cookie_auth_and_csrf():
    values = iter((b"a" * 24, b"b" * 16))
    auth = SessionAuth(
        "a-unique-password", random_bytes=lambda size: next(values),
        now_func=lambda: 100,
    )
    token, session = auth.login("a-unique-password")
    headers = {
        "cookie": "fc_session={}".format(token),
        "x-csrf-token": session["csrf"],
    }
    assert auth.require(request(headers), csrf=True)[0] == token
    assert "HttpOnly" in auth.cookie_header(token, 3600)
    assert "SameSite=Strict" in auth.cookie_header(token, 3600)


def test_wrong_password_missing_session_and_csrf_are_rejected():
    auth = SessionAuth("a-unique-password")
    with pytest.raises(HTTPError) as exc:
        auth.login("wrong")
    assert exc.value.status == 401
    with pytest.raises(HTTPError) as exc:
        auth.require(request(), csrf=False)
    assert exc.value.status == 401

    token, _ = auth.login("a-unique-password")
    with pytest.raises(HTTPError) as exc:
        auth.require(request({"cookie": "fc_session={}".format(token)}), csrf=True)
    assert exc.value.status == 403


def test_expired_sessions_are_removed():
    current = [100]
    auth = SessionAuth("a-unique-password", ttl_seconds=10,
                       now_func=lambda: current[0])
    token, _ = auth.login("a-unique-password")
    current[0] = 111
    with pytest.raises(HTTPError):
        auth.require(request({"cookie": "fc_session={}".format(token)}))
    assert token not in auth.sessions
