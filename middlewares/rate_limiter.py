import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from db.redis_client import get_redis

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Limits how many requests a single IP can make per minute.

    How it works:
      - Every request gets a Redis key:  rate_limit:{ip}:{current_minute}
      - The key is incremented on each request (atomic — no race conditions)
      - TTL of 61s means Redis cleans it up automatically after the window passes
      - If the count exceeds max_requests, return 429 Too Many Requests

    Why per-minute windows?
      Using the current minute (Unix timestamp // 60) as part of the key means
      each minute starts a fresh counter with zero cost — no reset logic needed.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        window = int(time.time()) // self.window_seconds  # current time window
        key = f"rate_limit:{ip}:{window}"

        redis = get_redis()
        count = redis.incr(key)  # increment and get new value atomically

        # set TTL only on the first request in this window
        # (avoids resetting TTL on every request, which would prevent expiry)
        if count == 1:
            redis.expire(key, self.window_seconds + 1)

        if count > self.max_requests:
            logger.warning("Rate limit exceeded for IP %s (%d requests)", ip, count)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "detail": f"Limit is {self.max_requests} requests per {self.window_seconds}s. Try again shortly."
                }
            )

        return await call_next(request)
