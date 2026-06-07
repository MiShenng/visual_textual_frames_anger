from datetime import datetime, timedelta

from app.services.circuit_breaker import apply_failure, is_available, reset_failures


def test_apply_failure_enters_cooldown_at_threshold():
    state = apply_failure(2, threshold=3, cooldown_seconds=60)
    assert state.failure_count == 3
    assert state.cooldown_until is not None
    assert is_available(state.cooldown_until) is False


def test_reset_failures_clears_cooldown():
    state = reset_failures()
    assert state.failure_count == 0
    assert state.cooldown_until is None


def test_is_available_accepts_naive_datetime():
    cooldown_until = datetime.now() + timedelta(seconds=60)

    assert is_available(cooldown_until) is False
