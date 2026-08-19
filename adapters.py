"""
adapters.py

Source adapters isolate everything that is specific to *where* data comes
from. The rest of the pipeline never talks to httpx or knows the shape of
a particular API response directly - it only ever asks an adapter for a
list of raw dicts.

ETHICAL BOUNDARY (see README): adapters in this file only ever perform a
single plain HTTP GET against a public, unauthenticated JSON endpoint using
a normal, honestly-labelled User-Agent. There is no CAPTCHA handling,
fingerprint spoofing, cookie/session theft, proxy or account rotation, or
any other access-control bypass anywhere in this project, and none should
ever be added.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from config import settings

DEMO_FIXTURE_PATH = Path(__file__).resolve().parent / "data" / "demo_fixture.json"


class SourceUnavailableError(Exception):
    """Raised for connection failures / 5xx / timeouts."""


class RateLimitedError(Exception):
    """Raised when the source responds with 429 or an equivalent signal."""


class SchemaDriftError(Exception):
    """Raised when the response shape no longer matches what we expect."""


class BaseJobSource(ABC):
    """Contract every job source must satisfy."""

    name: str
    url: str

    @abstractmethod
    def fetch_raw(self) -> list[dict[str, Any]]:
        """Return a list of raw, source-shaped dicts. Never raises for an
        empty result - an empty list is a valid (if suspicious) outcome.
        Network/API-level problems raise the exceptions above instead."""
        raise NotImplementedError


class PublicFeedSource(BaseJobSource):
    """
    A generic adapter for a public JSON job feed. Works out of the box with
    the RemoteOK public API (https://remoteok.com/api), which requires no
    authentication. Any similarly-shaped public JSON endpoint can be used
    by changing SOURCE_URL - no code change required.
    """

    EXPECTED_KEYS = {"position", "company", "url"}

    def __init__(self, name: str, url: str, timeout: float | None = None):
        self.name = name
        self.url = url
        self.timeout = timeout or settings.request_timeout

    def fetch_raw(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}
        try:
            response = httpx.get(self.url, headers=headers, timeout=self.timeout, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise SourceUnavailableError(f"timeout contacting {self.url}") from exc
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(str(exc)) from exc

        if response.status_code == 429:
            raise RateLimitedError("source returned HTTP 429")
        if response.status_code >= 500:
            raise SourceUnavailableError(f"source returned HTTP {response.status_code}")
        if response.status_code >= 400:
            raise SourceUnavailableError(f"source returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise SchemaDriftError("response was not valid JSON") from exc

        records = self._extract_records(payload)
        return records

    def _extract_records(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            payload = payload.get("jobs") or payload.get("data") or []
        if not isinstance(payload, list):
            raise SchemaDriftError("expected a list of job records")

        records = [row for row in payload if isinstance(row, dict) and "legal" not in row]
        if records and not self._looks_like_job(records[0]):
            raise SchemaDriftError(
                f"record shape changed; expected keys overlapping {self.EXPECTED_KEYS}"
            )
        return records

    def _looks_like_job(self, row: dict[str, Any]) -> bool:
        keys = set(row.keys())
        return bool(keys & self.EXPECTED_KEYS) or bool(keys & {"title", "job_title", "name"})


class DemoFixtureSource(BaseJobSource):
    """Offline, deterministic source used when SOURCE_URL=demo. Guarantees
    the assessment can be run and demoed with zero network dependency."""

    def __init__(self, name: str, url: str = "demo"):
        self.name = name
        self.url = url

    def fetch_raw(self) -> list[dict[str, Any]]:
        if not DEMO_FIXTURE_PATH.exists():
            return []
        with open(DEMO_FIXTURE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def build_source(name: str, url: str) -> BaseJobSource:
    """Factory: picks the right adapter for the configured URL."""
    if url.strip().lower() == "demo":
        return DemoFixtureSource(name=name, url=url)
    return PublicFeedSource(name=name, url=url)
