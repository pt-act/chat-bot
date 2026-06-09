"""Provider resilience — retry transient failures + an in-process circuit breaker (#14).

A transient ``429`` / ``5xx`` / timeout from an LLM or embedding provider must not fail a
turn. ``resilient_invoke`` (and the ``@resilient_call`` decorator) wrap a synchronous
provider call with:

- **Exponential backoff retries** (tenacity), retrying *only* transient errors
  (timeouts, connection errors, HTTP 429/5xx-style exceptions). Non-transient errors
  (e.g. ``ValueError`` from a guardrail) are re-raised immediately, never retried.
- **A circuit breaker** that opens after ``cb_failure_threshold`` consecutive transient
  failures and fast-fails subsequent calls (``CircuitBreakerOpen``) until
  ``cb_reset_seconds`` elapse, after which a single half-open trial call is allowed.

Streaming callers retry only the *initial connection* (before any token is yielded);
once tokens flow a stream cannot be safely replayed.
"""

import logging
import time
from functools import wraps

from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from config import get_settings

logger = logging.getLogger(__name__)

# HTTP statuses worth retrying — rate limiting and transient server-side failures.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
# Exception class-name fragments used by openai/httpx/requests-style transient errors,
# matched case-insensitively so we don't have to import every optional provider SDK.
_TRANSIENT_NAME_HINTS = (
    "timeout",
    "connection",
    "ratelimit",
    "serviceunavailable",
    "internalservererror",
    "apiconnection",
    "apitimeout",
)


class CircuitBreakerOpen(RuntimeError):
    """Raised when an open circuit rejects a call without attempting the provider."""


def is_transient(exc: BaseException) -> bool:
    """True when ``exc`` looks like a retryable, transient provider failure."""
    if isinstance(exc, TimeoutError | ConnectionError):
        return True
    for attr in ("status_code", "http_status", "code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int) and val in _TRANSIENT_STATUS:
            return True
    resp = getattr(exc, "response", None)  # requests-style errors carry a response
    status = getattr(resp, "status_code", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS:
        return True
    name = type(exc).__name__.lower()
    return any(hint in name for hint in _TRANSIENT_NAME_HINTS)


class CircuitBreaker:
    """A minimal in-process circuit breaker (closed → open → half-open → closed)."""

    def __init__(
        self, failure_threshold: int = 5, reset_seconds: float = 30, name: str = "default", clock=time.monotonic
    ):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.name = name
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.reset_seconds:
            return "half_open"
        return "open"

    def before_call(self) -> None:
        if self.state == "open":
            raise CircuitBreakerOpen(f"circuit '{self.name}' is open")

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()
            logger.warning("Circuit '%s' opened after %d consecutive failures", self.name, self._failures)


# One breaker per logical provider surface (e.g. "llm"), shared process-wide.
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    cb = _breakers.get(name)
    if cb is None:
        s = get_settings()
        cb = CircuitBreaker(failure_threshold=s.cb_failure_threshold, reset_seconds=s.cb_reset_seconds, name=name)
        _breakers[name] = cb
    return cb


def reset_breakers() -> None:
    """Clear the breaker registry (used by tests for isolation)."""
    _breakers.clear()


def _log_retry(retry_state) -> None:
    logger.warning(
        "Retrying provider call (attempt %d) after %r",
        retry_state.attempt_number,
        retry_state.outcome.exception() if retry_state.outcome else None,
    )


def _retry(func, settings, args, kwargs):
    retryer = Retrying(
        stop=stop_after_attempt(max(1, settings.provider_max_retries)),
        wait=wait_exponential(multiplier=settings.provider_retry_base_delay),
        retry=retry_if_exception(is_transient),
        reraise=True,
        before_sleep=_log_retry,
    )
    return retryer(func, *args, **kwargs)


def resilient_invoke(func, *args, name: str = "llm", **kwargs):
    """Call ``func(*args, **kwargs)`` with retries + circuit-breaker protection."""
    settings = get_settings()
    cb = get_breaker(name) if settings.circuit_breaker_enabled else None
    if cb is not None:
        cb.before_call()
    try:
        result = _retry(func, settings, args, kwargs)
    except Exception as e:
        if cb is not None and is_transient(e):
            cb.record_failure()
        raise
    if cb is not None:
        cb.record_success()
    return result


def resilient_call(func=None, *, name: str = "llm"):
    """Decorator form of :func:`resilient_invoke`."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return resilient_invoke(fn, *args, name=name, **kwargs)

        return wrapper

    return decorator(func) if func is not None else decorator
