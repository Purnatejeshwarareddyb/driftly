"""
chaos.py

Chaos Lab. Every simulation here drives the *real* ingestion pipeline
(ingestion.run_ingestion) against a fake, in-process adapter that behaves
badly on purpose. This is deliberate: it means the recovery behavior the
Chaos Lab shows you is the same code path a real outage would hit, not a
canned animation.

Nothing in this file makes an external network call. That is the whole
point of "controlled" - blast radius is limited to DRIFTLY's own SQLite
database.
"""
from __future__ import annotations

from typing import Any

from adapters import BaseJobSource, RateLimitedError, SourceUnavailableError
from database import get_session
from ingestion import IngestionOutcome, run_ingestion
from services import get_or_create_source


class _RateLimitedThenOkSource(BaseJobSource):
    """Fails with 429 for the first two calls, then returns good data -
    exercises RATE_LIMITED -> RETRY_STARTED -> RECOVERED."""

    def __init__(self, name: str, url: str):
        self.name, self.url = name, url
        self._calls = 0

    def fetch_raw(self) -> list[dict[str, Any]]:
        self._calls += 1
        if self._calls <= 2:
            raise RateLimitedError("simulated HTTP 429 from Chaos Lab")
        return [
            {
                "title": "Chaos-Verified Reliability Engineer",
                "company": "Driftly Internal",
                "location": "Remote",
                "url": "https://example.invalid/chaos/rate-limit",
                "id": "chaos-rate-limit-1",
            }
        ]


class _EmptyResponseSource(BaseJobSource):
    """Always returns zero records - exercises empty-response protection."""

    def __init__(self, name: str, url: str):
        self.name, self.url = name, url

    def fetch_raw(self) -> list[dict[str, Any]]:
        return []


class _AlwaysFailsSource(BaseJobSource):
    """Always raises a transient error - exercises the UNAVAILABLE path and
    last-known-good serving."""

    def __init__(self, name: str, url: str):
        self.name, self.url = name, url

    def fetch_raw(self) -> list[dict[str, Any]]:
        raise SourceUnavailableError("simulated connection failure from Chaos Lab")


class _SchemaDriftSource(BaseJobSource):
    """Returns records that no longer contain any recognizable job fields -
    exercises schema-drift detection and quarantine."""

    def __init__(self, name: str, url: str):
        self.name, self.url = name, url

    def fetch_raw(self) -> list[dict[str, Any]]:
        return [
            {"unexpected_field_a": "value", "unexpected_field_b": 42},
            {"totally_different_shape": True},
        ]


def _run_with(adapter_cls) -> IngestionOutcome:
    with get_session() as session:
        source_row = get_or_create_source(session)
        adapter = adapter_cls(source_row.name, source_row.url)
        return run_ingestion(session, source_row, adapter)


def simulate_rate_limit() -> IngestionOutcome:
    return _run_with(_RateLimitedThenOkSource)


def simulate_empty_response() -> IngestionOutcome:
    return _run_with(_EmptyResponseSource)


def simulate_source_failure() -> IngestionOutcome:
    return _run_with(_AlwaysFailsSource)


def simulate_schema_drift() -> IngestionOutcome:
    return _run_with(_SchemaDriftSource)
