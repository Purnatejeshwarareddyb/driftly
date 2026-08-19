"""
ingestion.py

The ingestion pipeline. Each stage is a small, separately-testable function
so the "big function that does everything" trap is avoided. run_ingestion()
is the only thing that wires the stages together in order:

    fetch -> detect (empty/drift) -> validate -> normalize -> deduplicate
    -> store -> health update -> event logging

Nothing here talks to httpx directly - that lives in adapters.py, so this
module can be unit-tested with a fake source.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters import BaseJobSource, RateLimitedError, SchemaDriftError, SourceUnavailableError
from models import IngestionEvent, IngestionRun, Job, QuarantinedRecord, Source
from resilience import RetryEvent, run_with_retry, next_status_on_failure, status_on_success
from schemas import RawJobRecord


@dataclass
class IngestionOutcome:
    run_id: int
    status: str
    records_received: int = 0
    records_valid: int = 0
    records_stored: int = 0
    records_duplicate: int = 0
    records_failed: int = 0
    empty_response: bool = False
    schema_drift: bool = False
    messages: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Field mapping: different public feeds name fields differently. This is the
# single place that knows every alias we support, so adding a new source
# never requires touching validation/normalization/dedup logic below.
# ---------------------------------------------------------------------------
FIELD_ALIASES = {
    "title": ("title", "position", "job_title", "name"),
    "company": ("company", "company_name", "employer"),
    "location": ("location", "candidate_required_location", "job_location"),
    "url": ("url", "job_url", "link", "apply_url"),
    "external_id": ("id", "external_id", "slug"),
    "description": ("description", "summary", "job_description"),
    "published_at": ("date", "published_at", "created_at", "posted_at"),
}


def _first_present(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def map_raw_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate a source-shaped dict into our canonical field names."""
    return {field_name: _first_present(raw, aliases) for field_name, aliases in FIELD_ALIASES.items()}


def validate_record(raw: dict[str, Any]) -> tuple[RawJobRecord | None, str | None]:
    """Returns (validated_record, None) on success or (None, reason) on failure."""
    mapped = map_raw_record(raw)
    try:
        return RawJobRecord(**mapped), None
    except ValidationError as exc:
        return None, str(exc.errors()[0]["msg"]) if exc.errors() else "validation failed"


WHITESPACE_RE = re.compile(r"\s+")


def normalize_record(record: RawJobRecord) -> RawJobRecord:
    """Trim/collapse whitespace, normalize URLs and dates, without discarding
    information that isn't actually redundant."""
    data = record.model_dump()
    for key in ("title", "company", "location", "description"):
        if data.get(key):
            data[key] = WHITESPACE_RE.sub(" ", data[key]).strip()

    if data.get("url") and not data["url"].startswith(("http://", "https://")):
        data["url"] = "https://" + data["url"].lstrip("/")

    if not data.get("location"):
        data["location"] = "Not specified"

    return RawJobRecord(**data)


def content_hash(record: RawJobRecord, source_name: str) -> str:
    """Deterministic fallback identity when the source gives no external id."""
    basis = "|".join(
        [source_name, record.title.lower(), record.company.lower(), record.location.lower(), record.url]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _log_event(session: Session, run_id: int | None, event_type: str, severity: str, message: str) -> None:
    session.add(IngestionEvent(run_id=run_id, event_type=event_type, severity=severity, message=message))


def _persist_run_events(session: Session, run_id: int | None, events: list[RetryEvent]) -> None:
    for ev in events:
        _log_event(session, run_id, ev.event_type, ev.severity, ev.message)


def run_ingestion(session: Session, source_row: Source, source_adapter: BaseJobSource) -> IngestionOutcome:
    """Execute one full ingestion cycle against `source_adapter` and persist
    everything (run row, events, jobs, quarantine, source health) using
    `session`. This is the one function every entry point (manual "Run
    ingestion" button, API route, tests) should call."""

    run = IngestionRun(source=source_row.name, status="RUNNING")
    session.add(run)
    session.flush()  # obtain run.id
    _log_event(session, run.id, "INGESTION_STARTED", "INFO", f"Starting ingestion from {source_row.name}.")

    start = dt.datetime.now(dt.timezone.utc)

    def is_rate_limit(exc: Exception) -> bool:
        return isinstance(exc, RateLimitedError)

    def is_transient(exc: Exception) -> bool:
        return isinstance(exc, SourceUnavailableError)

    outcome = run_with_retry(
        source_adapter.fetch_raw,
        is_rate_limit=is_rate_limit,
        is_transient=is_transient,
    )
    _persist_run_events(session, run.id, outcome.events)

    latency = (dt.datetime.now(dt.timezone.utc) - start).total_seconds()

    if not outcome.success:
        source_row.consecutive_failures += 1
        source_row.last_failure = dt.datetime.now(dt.timezone.utc)
        source_row.last_latency = latency
        source_row.status = next_status_on_failure(source_row.consecutive_failures)

        run.status = "FAILED"
        run.completed_at = dt.datetime.now(dt.timezone.utc)
        _log_event(
            session, run.id, "SOURCE_UNAVAILABLE", "ERROR",
            f"Ingestion failed: {outcome.final_error}. Serving last known good data.",
        )
        return IngestionOutcome(run_id=run.id, status="FAILED", messages=[outcome.final_error or "unknown error"])

    raw_records = outcome.result or []
    result = IngestionOutcome(run_id=run.id, status="RUNNING", records_received=len(raw_records))

    # --- Empty-response protection -----------------------------------
    if len(raw_records) == 0:
        result.empty_response = True
        _log_event(
            session, run.id, "EMPTY_RESPONSE", "WARNING",
            "Source returned zero records. Preserving existing data and serving last known good dataset.",
        )
        source_row.consecutive_failures += 1
        source_row.last_failure = dt.datetime.now(dt.timezone.utc)
        source_row.last_latency = latency
        source_row.status = next_status_on_failure(source_row.consecutive_failures)
        run.status = "DEGRADED"
        run.completed_at = dt.datetime.now(dt.timezone.utc)
        result.status = "DEGRADED"
        return result

    # --- Detect schema drift up front (cheap, catches most drift) ----
    try:
        _ = [map_raw_record(r) for r in raw_records[:1]]
    except Exception:  # noqa: BLE001
        pass  # mapping itself never raises; real drift is caught per-record below

    valid_records: list[tuple[RawJobRecord, dict[str, Any]]] = []
    drift_like_failures = 0

    for raw in raw_records:
        validated, reason = validate_record(raw)
        if validated is None:
            result.records_failed += 1
            session.add(
                QuarantinedRecord(
                    source=source_row.name,
                    raw_payload=json.dumps(raw)[:5000],
                    reason=reason or "validation failed",
                )
            )
            _log_event(session, run.id, "RECORD_QUARANTINED", "WARNING", f"Quarantined record: {reason}")
            drift_like_failures += 1
            continue
        valid_records.append((normalize_record(validated), raw))
        result.records_valid += 1

    # If effectively everything failed validation, treat it as schema drift
    # rather than "everyone happened to submit bad data".
    if raw_records and drift_like_failures == len(raw_records):
        result.schema_drift = True
        source_row.status = "DEGRADED"
        source_row.consecutive_failures += 1
        source_row.last_failure = dt.datetime.now(dt.timezone.utc)
        run.status = "DEGRADED"
        run.completed_at = dt.datetime.now(dt.timezone.utc)
        _log_event(
            session, run.id, "SCHEMA_DRIFT", "ERROR",
            "Source structure no longer matches the expected shape. All records quarantined; "
            "existing data preserved and pipeline remains operational.",
        )
        result.records_received = len(raw_records)
        result.status = "DEGRADED"
        return result

    # --- Deduplicate ----------------------------------------------------
    stored = 0
    duplicates = 0
    for record, raw in valid_records:
        chash = content_hash(record, source_row.name)
        existing = session.execute(select(Job).where(Job.content_hash == chash)).scalar_one_or_none()
        if existing is None and record.external_id:
            existing = session.execute(
                select(Job).where(Job.source == source_row.name, Job.external_id == record.external_id)
            ).scalar_one_or_none()

        if existing is not None:
            duplicates += 1
            continue

        session.add(
            Job(
                external_id=record.external_id,
                title=record.title,
                company=record.company,
                location=record.location,
                description=record.description,
                url=record.url,
                source=source_row.name,
                published_at=record.published_at,
                content_hash=chash,
            )
        )
        stored += 1

    result.records_stored = stored
    result.records_duplicate = duplicates

    # --- Update source health & run -------------------------------------
    source_row.last_success = dt.datetime.now(dt.timezone.utc)
    source_row.last_latency = latency
    new_status = status_on_success(source_row.status)
    if source_row.consecutive_failures > 0:
        _log_event(session, run.id, "RECOVERED", "INFO", "Pipeline recovered after prior failures.")
    source_row.consecutive_failures = 0
    source_row.status = new_status

    run.status = "SUCCESS"
    run.completed_at = dt.datetime.now(dt.timezone.utc)
    run.records_received = result.records_received
    run.records_valid = result.records_valid
    run.records_stored = result.records_stored
    run.records_duplicate = result.records_duplicate
    run.records_failed = result.records_failed

    _log_event(
        session, run.id, "INGESTION_COMPLETED", "INFO",
        f"{stored} stored, {duplicates} duplicate, {result.records_failed} quarantined.",
    )
    result.status = "SUCCESS"
    return result
