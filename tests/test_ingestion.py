"""Tests for ingestion.py against a real (temp) SQLite database, using fake
in-process sources so nothing touches the network."""
from typing import Any

from adapters import BaseJobSource
from database import get_session
from ingestion import content_hash, map_raw_record, normalize_record, run_ingestion, validate_record
from models import IngestionEvent, Job, QuarantinedRecord, Source
from schemas import RawJobRecord
from services import get_or_create_source


class FakeSource(BaseJobSource):
    def __init__(self, records: list[dict[str, Any]]):
        self.name = "Test Source"
        self.url = "demo"
        self._records = records

    def fetch_raw(self):
        return self._records


GOOD_RECORD = {
    "title": "  Backend Engineer  ",
    "company": "Acme",
    "location": "Remote",
    "url": "example.com/jobs/1",
    "id": "job-1",
}


def _run(records):
    with get_session() as session:
        source_row = get_or_create_source(session)
        outcome = run_ingestion(session, source_row, FakeSource(records))
        return outcome


def test_map_raw_record_supports_aliases():
    mapped = map_raw_record({"position": "Engineer", "company_name": "Acme", "location": "Remote", "link": "x.com"})
    assert mapped["title"] == "Engineer"
    assert mapped["company"] == "Acme"
    assert mapped["url"] == "x.com"


def test_validate_record_rejects_missing_fields():
    record, reason = validate_record({"title": "Engineer"})
    assert record is None
    assert reason is not None


def test_normalize_record_collapses_whitespace_and_fixes_url():
    raw = RawJobRecord(title="  Backend   Engineer ", company="Acme", location="Remote", url="example.com/x")
    normalized = normalize_record(raw)
    assert normalized.title == "Backend Engineer"
    assert normalized.url.startswith("https://")


def test_content_hash_is_deterministic():
    raw = RawJobRecord(title="Engineer", company="Acme", location="Remote", url="https://x.com")
    assert content_hash(raw, "Test") == content_hash(raw, "Test")


def test_successful_ingestion_stores_job():
    outcome = _run([GOOD_RECORD])
    assert outcome.status == "SUCCESS"
    assert outcome.records_stored == 1
    with get_session() as session:
        assert session.query(Job).count() == 1


def test_duplicate_records_are_not_stored_twice():
    _run([GOOD_RECORD])
    outcome = _run([GOOD_RECORD])
    assert outcome.records_duplicate == 1
    assert outcome.records_stored == 0
    with get_session() as session:
        assert session.query(Job).count() == 1


def test_invalid_record_is_quarantined_not_dropped_silently():
    outcome = _run([GOOD_RECORD, {"title": "No other fields"}])
    assert outcome.records_stored == 1
    assert outcome.records_failed == 1
    with get_session() as session:
        assert session.query(QuarantinedRecord).count() == 1


def test_empty_response_preserves_existing_jobs():
    _run([GOOD_RECORD])
    outcome = _run([])
    assert outcome.empty_response is True
    assert outcome.status == "DEGRADED"
    with get_session() as session:
        assert session.query(Job).count() == 1  # preserved, not deleted
        source = get_or_create_source(session)
        assert source.status in ("DEGRADED", "UNAVAILABLE")


def test_schema_drift_quarantines_everything_and_preserves_data():
    _run([GOOD_RECORD])
    outcome = _run([{"weird_field": 1}, {"another_weird_field": 2}])
    assert outcome.schema_drift is True
    with get_session() as session:
        assert session.query(Job).count() == 1  # preserved
        source = get_or_create_source(session)
        assert source.status == "DEGRADED"


def test_source_recovers_after_failure():
    _run([])  # degrade the source
    with get_session() as session:
        source = get_or_create_source(session)
        assert source.status in ("DEGRADED", "UNAVAILABLE")

    outcome = _run([GOOD_RECORD])
    assert outcome.status == "SUCCESS"
    with get_session() as session:
        source = get_or_create_source(session)
        assert source.status == "RECOVERING"
        assert source.consecutive_failures == 0


def test_ingestion_run_and_events_are_logged():
    _run([GOOD_RECORD])
    with get_session() as session:
        assert session.query(IngestionEvent).count() > 0
