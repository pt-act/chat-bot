"""Tests for middlewares/rate_limiter.py."""

from unittest.mock import MagicMock, patch

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middlewares.rate_limiter import RateLimitMiddleware, _get_client_ip


class TestGetClientIP:
    def test_direct_ip_no_proxy(self):
        request = MagicMock()
        request.client.host = "1.2.3.4"
        request.headers = {}
        assert _get_client_ip(request, []) == "1.2.3.4"

    def test_trusted_proxy_uses_x_forwarded_for(self):
        request = MagicMock()
        request.client.host = "10.0.0.1"  # trusted proxy
        request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        assert _get_client_ip(request, ["10.0.0.1"]) == "5.6.7.8"

    def test_trusted_proxy_uses_x_real_ip(self):
        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {"x-real-ip": "1.2.3.4"}
        assert _get_client_ip(request, ["10.0.0.1"]) == "1.2.3.4"

    def test_untrusted_proxy_ignores_headers(self):
        request = MagicMock()
        request.client.host = "1.2.3.4"  # not a trusted proxy
        request.headers = {"x-forwarded-for": "9.9.9.9"}
        assert _get_client_ip(request, ["10.0.0.1"]) == "1.2.3.4"

    def test_cidr_trusted_proxy(self):
        request = MagicMock()
        request.client.host = "10.0.0.5"
        request.headers = {"x-forwarded-for": "1.2.3.4"}
        assert _get_client_ip(request, ["10.0.0.0/8"]) == "1.2.3.4"

    def test_unknown_client(self):
        request = MagicMock()
        request.client = None
        request.headers = {}
        assert _get_client_ip(request, []) == "unknown"


class TestRateLimitMiddleware:
    def _make_app(self, max_requests=2, window_seconds=60):
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        # Start the patch and keep it active for the lifetime of the test.
        # (Previously this used `with patch(...): return TestClient(app)`, which
        # exited the patch *before* any request ran — so the middleware talked to
        # a real Redis, failed open, and the assertions silently passed/failed
        # depending on the environment. teardown_method stops it.)
        self._patcher = patch(
            "middlewares.rate_limiter.get_redis",
            return_value=fakeredis.FakeRedis(decode_responses=True),
        )
        self._patcher.start()
        return TestClient(app)

    def teardown_method(self):
        patcher = getattr(self, "_patcher", None)
        if patcher is not None:
            patcher.stop()

    def test_request_within_limit_succeeds(self):
        client = self._make_app(max_requests=5)
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_request_exceeds_limit_returns_429(self):
        client = self._make_app(max_requests=1)
        client.get("/test")  # first request
        resp = client.get("/test")  # second request → should be blocked
        assert resp.status_code == 429
        assert resp.json()["error"] == "Too many requests"

    def test_different_ips_have_separate_limits(self):
        client = self._make_app(max_requests=1)
        client.get("/test")  # from default IP
        # Simulate a different IP via header
        resp = client.get("/test", headers={"x-forwarded-for": "9.9.9.9"})
        # Should be blocked because we haven't configured trusted proxies
        # and direct IP is used
        assert resp.status_code == 429
