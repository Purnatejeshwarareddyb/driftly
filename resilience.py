"""
resilience.py

Everything that keeps DRIFTLY alive when the outside world misbehaves:
retry/backoff with jitter, source status transitions, and the policies for
the two signature failure modes - an unexpectedly empty response, and a
source that has changed shape underneath us (schema drift).

This module never touches the database directly; it returns plain data
(RetryOutcome, SourceStatus) that services.py persists. That separation is
what makes the retry/backoff logic independently testable.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from config import settings


class SourceStatus(StrEnum):
    IDLE = "IDLE"
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    RECOVERING = "RECOVERING"


@dataclass
class RetryEvent:
    event_type: str
    severity: str
    message: str


@dataclass
class RetryOutcome:
    success: bool
    result: Any = None
    attempts: int = 0
    events: list[RetryEvent] = field(default_factory=list)
    final_error: str | None = None


def compute_backoff(attempt: int, base: float | None = None, cap: float | None = None) -> float:
    """Exponential backoff with full jitter. attempt is 1-indexed."""
    base = base if base is not None else settings.backoff_base
    cap = cap if cap is not None else settings.backoff_max
    ceiling = min(cap, base * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)


def run_with_retry(
    operation: Callable[[], Any],
    *,
    is_rate_limit: Callable[[Exception], bool],
    is_transient: Callable[[Exception], bool],
    max_retries: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> RetryOutcome:
    """
    Run `operation`, retrying with exponential backoff + jitter on
    rate-limit or transient errors. Non-transient, non-rate-limit errors
    (e.g. schema drift) are never retried - they propagate immediately
    because retrying will not fix a shape mismatch.
    """
    max_retries = max_retries if max_retries is not None else settings.max_retries
    events: list[RetryEvent] = []
    attempt = 0

    while True:
        attempt += 1
        try:
            result = operation()
            if attempt > 1:
                events.append(RetryEvent("RECOVERED", "INFO", f"Recovered after {attempt} attempt(s)."))
            return RetryOutcome(success=True, result=result, attempts=attempt, events=events)
        except Exception as exc:  # noqa: BLE001 - intentionally broad, classified below
            rate_limited = is_rate_limit(exc)
            transient = is_transient(exc)

            if rate_limited:
                events.append(RetryEvent("RATE_LIMITED", "WARNING", str(exc)))
            elif transient:
                events.append(RetryEvent("SOURCE_ERROR", "WARNING", str(exc)))
            else:
                # Not retryable (e.g. schema drift) - surface immediately.
                events.append(RetryEvent("NON_RETRYABLE_ERROR", "ERROR", str(exc)))
                return RetryOutcome(success=False, attempts=attempt, events=events, final_error=str(exc))

            if attempt > max_retries:
                events.append(
                    RetryEvent("RETRY_FAILED", "ERROR", f"Exhausted {max_retries} retries: {exc}")
                )
                return RetryOutcome(success=False, attempts=attempt, events=events, final_error=str(exc))

            delay = compute_backoff(attempt)
            events.append(
                RetryEvent(
                    "RETRY_STARTED",
                    "INFO",
                    f"Attempt {attempt} failed ({exc}); backing off {delay:.2f}s before retry.",
                )
            )
            sleep_fn(delay)


def next_status_on_failure(consecutive_failures: int) -> SourceStatus:
    if consecutive_failures >= settings.unavailable_after_failures:
        return SourceStatus.UNAVAILABLE
    if consecutive_failures >= settings.degraded_after_failures:
        return SourceStatus.DEGRADED
    return SourceStatus.OPERATIONAL


def status_on_success(previous_status: str) -> SourceStatus:
    if previous_status in (SourceStatus.DEGRADED, SourceStatus.UNAVAILABLE):
        return SourceStatus.RECOVERING
    return SourceStatus.OPERATIONAL
