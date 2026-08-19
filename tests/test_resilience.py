"""Tests for resilience.py - retry/backoff and status transition logic."""
import pytest

from resilience import (
    SourceStatus,
    compute_backoff,
    next_status_on_failure,
    run_with_retry,
    status_on_success,
)


class RateLimited(Exception):
    pass


class Transient(Exception):
    pass


class Permanent(Exception):
    pass


def is_rate_limit(exc):
    return isinstance(exc, RateLimited)


def is_transient(exc):
    return isinstance(exc, Transient)


def test_compute_backoff_within_bounds():
    for attempt in range(1, 6):
        delay = compute_backoff(attempt, base=0.5, cap=8.0)
        assert 0 <= delay <= 8.0


def test_run_with_retry_succeeds_first_try():
    outcome = run_with_retry(lambda: "ok", is_rate_limit=is_rate_limit, is_transient=is_transient)
    assert outcome.success is True
    assert outcome.attempts == 1
    assert outcome.result == "ok"


def test_run_with_retry_recovers_after_rate_limit():
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimited("429")
        return "recovered"

    outcome = run_with_retry(
        op, is_rate_limit=is_rate_limit, is_transient=is_transient, max_retries=5, sleep_fn=lambda s: None
    )
    assert outcome.success is True
    assert outcome.result == "recovered"
    assert any(e.event_type == "RECOVERED" for e in outcome.events)


def test_run_with_retry_exhausts_retries():
    def op():
        raise Transient("down")

    outcome = run_with_retry(
        op, is_rate_limit=is_rate_limit, is_transient=is_transient, max_retries=2, sleep_fn=lambda s: None
    )
    assert outcome.success is False
    assert outcome.attempts == 3  # initial + 2 retries
    assert any(e.event_type == "RETRY_FAILED" for e in outcome.events)


def test_run_with_retry_does_not_retry_non_retryable_errors():
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise Permanent("schema drift")

    outcome = run_with_retry(
        op, is_rate_limit=is_rate_limit, is_transient=is_transient, max_retries=5, sleep_fn=lambda s: None
    )
    assert outcome.success is False
    assert calls["n"] == 1  # never retried
    assert any(e.event_type == "NON_RETRYABLE_ERROR" for e in outcome.events)


def test_status_escalation():
    assert next_status_on_failure(0) == SourceStatus.OPERATIONAL
    assert next_status_on_failure(1) == SourceStatus.DEGRADED
    assert next_status_on_failure(3) == SourceStatus.UNAVAILABLE


def test_status_on_success_marks_recovering_from_bad_state():
    assert status_on_success(SourceStatus.DEGRADED) == SourceStatus.RECOVERING
    assert status_on_success(SourceStatus.UNAVAILABLE) == SourceStatus.RECOVERING
    assert status_on_success(SourceStatus.OPERATIONAL) == SourceStatus.OPERATIONAL
