"""Tests for utils.resilience — provider retry/backoff + circuit breaker (#14)."""

from unittest.mock import MagicMock, patch

import pytest

from utils.resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    is_transient,
    reset_breakers,
    resilient_invoke,
)


def _settings(retries=3, base_delay=0.0, cb=False, threshold=5, reset=30):
    return MagicMock(
        provider_max_retries=retries,
        provider_retry_base_delay=base_delay,
        circuit_breaker_enabled=cb,
        cb_failure_threshold=threshold,
        cb_reset_seconds=reset,
    )


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_breakers()
    yield
    reset_breakers()


class TestIsTransient:
    def test_builtin_timeout_and_connection_are_transient(self):
        assert is_transient(TimeoutError("x"))
        assert is_transient(ConnectionError("x"))

    def test_status_code_attribute(self):
        exc = Exception("rate limited")
        exc.status_code = 429
        assert is_transient(exc)
        exc.status_code = 400
        assert not is_transient(exc)

    def test_response_status_attribute(self):
        exc = Exception("server error")
        exc.response = MagicMock(status_code=503)
        assert is_transient(exc)

    def test_name_hint(self):
        class APITimeoutError(Exception):
            pass

        assert is_transient(APITimeoutError())

    def test_plain_value_error_not_transient(self):
        assert not is_transient(ValueError("bad input"))


class TestRetry:
    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("transient")
            return "ok"

        with patch("utils.resilience.get_settings", return_value=_settings(retries=3, cb=False)):
            assert resilient_invoke(flaky) == "ok"
        assert calls["n"] == 3

    def test_exceeds_max_retries_raises(self):
        def always_fail():
            raise TimeoutError("transient")

        with patch("utils.resilience.get_settings", return_value=_settings(retries=3, cb=False)):
            with pytest.raises(TimeoutError):
                resilient_invoke(always_fail)

    def test_non_transient_not_retried(self):
        calls = {"n": 0}

        def fail():
            calls["n"] += 1
            raise ValueError("nope")

        with patch("utils.resilience.get_settings", return_value=_settings(retries=3, cb=False)):
            with pytest.raises(ValueError):
                resilient_invoke(fail)
        assert calls["n"] == 1


class TestCircuitBreaker:
    def test_opens_after_threshold_and_half_opens_after_reset(self):
        clock = {"now": 0.0}
        cb = CircuitBreaker(failure_threshold=2, reset_seconds=30, clock=lambda: clock["now"])

        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"
        with pytest.raises(CircuitBreakerOpen):
            cb.before_call()

        clock["now"] = 31  # advance past reset window
        assert cb.state == "half_open"
        cb.before_call()  # half-open allows a trial call
        cb.record_success()
        assert cb.state == "closed"

    def test_resilient_invoke_opens_circuit_and_fast_fails(self):
        def fail():
            raise TimeoutError("transient")

        with patch("utils.resilience.get_settings", return_value=_settings(retries=1, cb=True, threshold=2)):
            for _ in range(2):
                with pytest.raises(TimeoutError):
                    resilient_invoke(fail, name="prov")

            # Circuit is now open — the provider must not be hit again.
            hit = {"n": 0}

            def fail_again():
                hit["n"] += 1
                raise TimeoutError("transient")

            with pytest.raises(CircuitBreakerOpen):
                resilient_invoke(fail_again, name="prov")
            assert hit["n"] == 0
