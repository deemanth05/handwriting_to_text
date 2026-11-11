"""Enterprise Circuit Breaker Implementation.

Implements the Martin Fowler Circuit Breaker pattern with state machine:
- CLOSED: Requests pass through normally. Failures increment failure_count.
- OPEN: Tripped after consecutive failures or rate limits (HTTP 429).
        Fails fast immediately (0ms) without wasting network sockets.
- HALF_OPEN: After recovery_timeout, allows a single trial/canary request.
             If successful -> CLOSED. If failure -> returns to OPEN.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Operational states of the circuit breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Thread-safe, high-performance circuit breaker for upstream model providers."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 2,
        recovery_timeout_seconds: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(0.001, recovery_timeout_seconds)

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._last_state_change: float = time.time()
        self._last_error: str | None = None

    @property
    def state(self) -> CircuitState:
        """Current state, accounting for recovery timeout elapsed in OPEN state."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._last_state_change = time.time()
                logger.info(
                    "CircuitBreaker [%s] transitioned from OPEN to HALF_OPEN after %.1fs cooldown",
                    self.name,
                    elapsed,
                )
        return self._state

    def can_execute(self) -> bool:
        """Check whether a request should be permitted."""
        current_state = self.state
        if current_state == CircuitState.CLOSED:
            return True
        if current_state == CircuitState.HALF_OPEN:
            return True  # Canary trial permitted
        return False  # OPEN: fail-fast

    def record_success(self) -> None:
        """Record successful execution, resetting circuit to CLOSED."""
        if self._state != CircuitState.CLOSED:
            logger.info("CircuitBreaker [%s] recovered to CLOSED state", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._last_error = None
        self._last_state_change = time.time()

    def record_failure(self, error: str, is_rate_limit: bool = False) -> None:
        """Record failure.

        If rate limit (429) or consecutive failures >= threshold, trips to OPEN.
        """
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._last_error = error

        if is_rate_limit:
            # Immediate trip on rate limit (HTTP 429) to prevent quota hammering
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
            logger.warning(
                "CircuitBreaker [%s] TRIPPED to OPEN immediately due to rate limit (429): %s",
                self.name,
                error,
            )
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
            logger.warning(
                "CircuitBreaker [%s] TRIPPED to OPEN after %d consecutive failures: %s",
                self.name,
                self._failure_count,
                error,
            )
        elif self._state == CircuitState.HALF_OPEN:
            # Canary failed, return immediately to OPEN
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
            logger.warning(
                "CircuitBreaker [%s] canary trial failed; returning to OPEN: %s",
                self.name,
                error,
            )

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._last_error = None
        self._last_state_change = time.time()

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic dictionary for health and telemetry routes."""
        current_state = self.state
        remaining_recovery = 0.0
        if current_state == CircuitState.OPEN and self._last_failure_time is not None:
            remaining_recovery = max(0.0, self.recovery_timeout - (time.time() - self._last_failure_time))

        return {
            "name": self.name,
            "state": current_state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout,
            "remaining_cooldown_seconds": round(remaining_recovery, 1),
            "last_error": self._last_error,
            "can_execute": self.can_execute(),
        }
