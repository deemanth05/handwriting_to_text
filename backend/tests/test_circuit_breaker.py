"""Unit tests for the Enterprise Circuit Breaker."""

import time

from backend.app.services.models.circuit_breaker import CircuitBreaker, CircuitState


def test_circuit_breaker_initial_state():
    cb = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout_seconds=5.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True
    assert cb.get_status()["failure_count"] == 0


def test_circuit_breaker_trips_after_threshold_failures():
    cb = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout_seconds=5.0)

    cb.record_failure("connection error 1")
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    cb.record_failure("connection error 2")
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False
    assert "OPEN" in cb.get_status()["state"]


def test_circuit_breaker_immediate_trip_on_rate_limit_429():
    cb = CircuitBreaker(name="test_cb", failure_threshold=5, recovery_timeout_seconds=10.0)

    # 429 rate limit trips immediately on first encounter
    cb.record_failure("HTTP 429 Too Many Requests", is_rate_limit=True)
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


def test_circuit_breaker_recovery_to_half_open_and_closed():
    # Use short recovery timeout (0.1s) for fast unit test
    cb = CircuitBreaker(name="test_cb", failure_threshold=1, recovery_timeout_seconds=0.1)

    cb.record_failure("fail")
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # Wait for cooldown to elapse
    time.sleep(0.15)

    # Check that it transitions to HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.can_execute() is True

    # Successful canary trial resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True
    assert cb.get_status()["failure_count"] == 0


def test_circuit_breaker_failed_canary_returns_to_open():
    cb = CircuitBreaker(name="test_cb", failure_threshold=1, recovery_timeout_seconds=0.1)

    cb.record_failure("fail 1")
    assert cb.state == CircuitState.OPEN

    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN

    # Canary trial fails
    cb.record_failure("canary fail")
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


def test_circuit_breaker_manual_reset():
    cb = CircuitBreaker(name="test_cb", failure_threshold=1, recovery_timeout_seconds=60.0)
    cb.record_failure("crash")
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True
