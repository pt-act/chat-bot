import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from db.redis_client import get_redis

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request, trusted_proxies: list[str]) -> str:
    """
    Extract the real client IP, accounting for reverse proxies.

    - If the direct client (request.client.host) is in trusted_proxies,
      look at X-Forwarded-For (last hop) or X-Real-IP.
    - Otherwise, use the direct client IP to prevent header spoofing.
    """
    direct_ip = request.client.host if request.client else "unknown"

    # Check if the direct connection comes from a trusted proxy
    is_trusted = False
    for proxy in trusted_proxies:
        if "/" in proxy:
            # CIDR notation
            import ipaddress

            try:
                network = ipaddress.ip_network(proxy, strict=False)
                if ipaddress.ip_address(direct_ip) in network:
                    is_trusted = True
                    break
            except ValueError:
                continue
        else:
            if direct_ip == proxy:
                is_trusted = True
                break

    if not is_trusted:
        return direct_ip

    # Trusted proxy: check forwarded headers
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Last hop is the rightmost entry
        last_hop = forwarded.split(",")[-1].strip()
        return last_hop

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip

    return direct_ip


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Limits how many requests a single IP can make per minute.

    How it works:
      - Every request gets a Redis key:  rate_limit:{ip}:{current_minute}
      - The key is incremented on each request (atomic — no race conditions)
      - TTL of 61s means Redis cleans it up automatically after the window passes
      - If the count exceeds max_requests, return 429 Too Many Requests

    Proxy awareness:
      - Configured via TRUSTED_PROXIES env var (CIDR or single IP)
      - If the direct client is a trusted proxy, X-Forwarded-For is used
      - Otherwise, direct IP is used to prevent header spoofing
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._trusted_proxies = get_settings().trusted_proxies

    def _headers(self, remaining: int, reset_epoch: int) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(reset_epoch),
        }

    async def dispatch(self, request: Request, call_next):
        ip = _get_client_ip(request, self._trusted_proxies)
        now = int(time.time())
        window = now // self.window_seconds  # current time window
        key = f"rate_limit:{ip}:{window}"
        reset_epoch = (window + 1) * self.window_seconds  # when the window rolls over

        try:
            redis = get_redis()
            count = redis.incr(key)  # increment and get new value atomically

            # set TTL only on the first request in this window
            # (avoids resetting TTL on every request, which would prevent expiry)
            if count == 1:
                redis.expire(key, self.window_seconds + 1)

            if count > self.max_requests:
                retry_after = max(1, reset_epoch - now)
                logger.warning("Rate limit exceeded for IP %s (%d requests)", ip, count)
                headers = self._headers(0, reset_epoch)
                headers["Retry-After"] = str(retry_after)
                return JSONResponse(
                    status_code=429,
                    media_type="application/problem+json",
                    headers=headers,
                    content={
                        "type": "https://errors.chat-bot/rate-limit",
                        "title": "Too many requests",
                        "status": 429,
                        "detail": (
                            f"Limit is {self.max_requests} requests per {self.window_seconds}s. Try again shortly."
                        ),
                    },
                )

            response = await call_next(request)
            for k, v in self._headers(self.max_requests - count, reset_epoch).items():
                response.headers[k] = v
            return response
        except Exception:
            # If Redis is unavailable, fail open to avoid blocking all traffic
            logger.warning("Rate limiting unavailable (Redis error), allowing request from %s", ip)

        return await call_next(request)
