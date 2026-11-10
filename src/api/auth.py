"""Small in-memory session and CSRF authentication for the local dashboard."""

try:
    import uhashlib as hashlib
    import ubinascii as binascii
except ImportError:
    import hashlib
    import binascii

try:
    import uos as os
except ImportError:
    import os

try:
    import utime as time
except ImportError:
    import time

from net.http_server import HTTPError


DEFAULT_PASSWORDS = ("admin", "password", "CHANGE_ME_TO_A_UNIQUE_PASSWORD")


def _monotonic_seconds():
    ticks_ms = getattr(time, "ticks_ms", None)
    if ticks_ms:
        return ticks_ms() // 1000
    return int(time.monotonic())


def _sha256(value):
    digest = hashlib.sha256(value).digest()
    return binascii.hexlify(digest).decode("ascii")


def _constant_time_equal(left, right):
    if len(left) != len(right):
        return False
    result = 0
    for left_byte, right_byte in zip(left.encode(), right.encode()):
        result |= left_byte ^ right_byte
    return result == 0


class SessionAuth:
    def __init__(self, password, ttl_seconds=3600, max_sessions=4,
                 random_bytes=None, now_func=None):
        if (not isinstance(password, str) or len(password) < 12 or
                password in DEFAULT_PASSWORDS or password.startswith("YOUR_")):
            raise ValueError("Web admin password must be unique and at least 12 characters")
        if ttl_seconds <= 0 or max_sessions <= 0:
            raise ValueError("Session limits must be positive")
        self._password_hash = _sha256(password.encode("utf-8"))
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.random_bytes = random_bytes or os.urandom
        self.now_func = now_func or _monotonic_seconds
        self.sessions = {}

    def _token(self, size=24):
        return binascii.hexlify(self.random_bytes(size)).decode("ascii")

    def _purge(self):
        now = self.now_func()
        expired = [token for token, session in self.sessions.items()
                   if session["expires"] <= now]
        for token in expired:
            del self.sessions[token]

    def login(self, password):
        candidate = _sha256(str(password).encode("utf-8"))
        if not _constant_time_equal(candidate, self._password_hash):
            raise HTTPError(401, "Invalid credentials")
        self._purge()
        if len(self.sessions) >= self.max_sessions:
            oldest = min(self.sessions, key=lambda token: self.sessions[token]["expires"])
            del self.sessions[oldest]
        token = self._token()
        session = {
            "csrf": self._token(16),
            "expires": self.now_func() + self.ttl_seconds,
        }
        self.sessions[token] = session
        return token, dict(session)

    @staticmethod
    def _cookie_token(headers):
        cookie = headers.get("cookie", "")
        for part in cookie.split(";"):
            key, separator, value = part.strip().partition("=")
            if separator and key == "fc_session":
                return value
        authorization = headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            return authorization[7:]
        return None

    def require(self, request, csrf=False):
        self._purge()
        token = self._cookie_token(request.headers)
        session = self.sessions.get(token)
        if session is None:
            raise HTTPError(401, "Authentication required")
        if csrf and not _constant_time_equal(
                request.headers.get("x-csrf-token", ""), session["csrf"]):
            raise HTTPError(403, "CSRF validation failed")
        return token, session

    def logout(self, request):
        token, _ = self.require(request, csrf=True)
        del self.sessions[token]

    @staticmethod
    def cookie_header(token, max_age):
        return (
            "fc_session={}; Path=/; HttpOnly; SameSite=Strict; Max-Age={}".format(
                token, max_age
            )
        )
