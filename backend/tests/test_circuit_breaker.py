"""Tests for CircuitBreaker implementation."""

import time
import pytest
from unittest.mock import patch

from app.services.monitor import CircuitBreaker


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in closed state."""
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.is_closed is True

    def test_allows_requests_when_closed(self):
        """Closed circuit allows all requests."""
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)
        assert cb.allow_request() is True
        assert cb.allow_request() is True
        assert cb.allow_request() is True

    def test_opens_after_failure_threshold(self):
        """Circuit opens after reaching failure threshold."""
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)

        # Record failures up to threshold
        cb.record_failure(Exception("error 1"))
        assert cb.state == CircuitBreaker.CLOSED

        cb.record_failure(Exception("error 2"))
        assert cb.state == CircuitBreaker.CLOSED

        cb.record_failure(Exception("error 3"))
        assert cb.state == CircuitBreaker.OPEN
        assert cb.is_closed is False

    def test_blocks_requests_when_open(self):
        """Open circuit blocks requests."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=10.0)

        # Open the circuit
        cb.record_failure(Exception("error 1"))
        cb.record_failure(Exception("error 2"))

        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        """Successful request resets failure count."""
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)

        # Record some failures but not enough to open
        cb.record_failure(Exception("error 1"))
        cb.record_failure(Exception("error 2"))
        assert cb._failure_count == 2

        # Record success
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == CircuitBreaker.CLOSED


class TestCircuitBreakerRecovery:
    """Test circuit breaker recovery behavior."""

    def test_transitions_to_half_open_after_timeout(self):
        """Circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        # Open the circuit
        cb.record_failure(Exception("error 1"))
        cb.record_failure(Exception("error 2"))
        assert cb.state == CircuitBreaker.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Should allow request and transition to half-open
        assert cb.allow_request() is True
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_limits_requests(self):
        """Half-open circuit limits number of test requests."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1, half_open_max_calls=2)

        # Open the circuit
        cb.record_failure(Exception("error 1"))
        cb.record_failure(Exception("error 2"))

        # Wait for recovery timeout
        time.sleep(0.15)

        # First request transitions from OPEN to HALF_OPEN (doesn't count against limit)
        assert cb.allow_request() is True
        assert cb.state == CircuitBreaker.HALF_OPEN

        # Next two requests allowed (half_open_max_calls=2)
        assert cb.allow_request() is True
        assert cb.allow_request() is True

        # Fourth request blocked (limit reached)
        assert cb.allow_request() is False

    def test_success_in_half_open_closes_circuit(self):
        """Successful request in half-open state closes the circuit."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        # Open the circuit
        cb.record_failure(Exception("error 1"))
        cb.record_failure(Exception("error 2"))

        # Wait for recovery timeout
        time.sleep(0.15)

        # Make test request
        cb.allow_request()
        assert cb.state == CircuitBreaker.HALF_OPEN

        # Record success
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.is_closed is True

    def test_failure_in_half_open_reopens_circuit(self):
        """Failure in half-open state re-opens the circuit."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        # Open the circuit
        cb.record_failure(Exception("error 1"))
        cb.record_failure(Exception("error 2"))

        # Wait for recovery timeout
        time.sleep(0.15)

        # Make test request
        cb.allow_request()
        assert cb.state == CircuitBreaker.HALF_OPEN

        # Record failure
        cb.record_failure(Exception("still failing"))
        assert cb.state == CircuitBreaker.OPEN


class TestCircuitBreakerStatus:
    """Test circuit breaker status reporting."""

    def test_get_status_returns_correct_info(self):
        """get_status returns correct circuit breaker information."""
        cb = CircuitBreaker("my-service", failure_threshold=5, recovery_timeout=30.0)

        status = cb.get_status()
        assert status["name"] == "my-service"
        assert status["state"] == CircuitBreaker.CLOSED
        assert status["failure_count"] == 0
        assert status["last_failure_time"] is None
        assert status["threshold"] == 5
        assert status["recovery_timeout"] == 30.0

    def test_get_status_reflects_failures(self):
        """get_status reflects recorded failures."""
        cb = CircuitBreaker("test", failure_threshold=5, recovery_timeout=30.0)

        cb.record_failure(Exception("error"))
        cb.record_failure(Exception("error"))

        status = cb.get_status()
        assert status["failure_count"] == 2
        assert status["last_failure_time"] is not None

    def test_get_status_reflects_open_state(self):
        """get_status reflects open state after threshold reached."""
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=30.0)

        cb.record_failure(Exception("error"))
        cb.record_failure(Exception("error"))

        status = cb.get_status()
        assert status["state"] == CircuitBreaker.OPEN
        assert status["failure_count"] == 2


class TestCircuitBreakerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_failure_threshold_of_one(self):
        """Circuit opens immediately with threshold of 1."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=10.0)

        cb.record_failure(Exception("error"))
        assert cb.state == CircuitBreaker.OPEN

    def test_very_long_recovery_timeout(self):
        """Circuit stays open with very long recovery timeout."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=3600.0)

        cb.record_failure(Exception("error"))
        assert cb.state == CircuitBreaker.OPEN

        # Still blocked after short wait
        time.sleep(0.01)
        assert cb.allow_request() is False

    def test_error_message_preserved(self):
        """Error message is preserved for logging."""
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)

        error = ValueError("specific error message")
        cb.record_failure(error)

        # The error should be passed to record_failure for logging
        # This is primarily testing the interface accepts the error
        assert cb._failure_count == 1

    def test_no_error_on_record_failure(self):
        """record_failure works without an error object."""
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)

        cb.record_failure()  # No error passed
        assert cb._failure_count == 1
        assert cb.state == CircuitBreaker.CLOSED
