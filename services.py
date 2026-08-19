"""
services.py

Cohesive read-side services used by both the API and the UI. Every number
that comes out of here is computed from SQLite - nothing is fabricated.
If there is no data, callers get an honest zero / empty list and are
expected to render an honest empty state.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters import build_source
from config import settings
from database import get_session
from ingestion import run_ingestion, IngestionOutcome
from models import IngestionEvent, IngestionRun, Job, QuarantinedRecord, Source


@dataclass
class SystemStatus:
    state: str  # OPERATIONAL / DEGRADED / RECOVERING / SOURCE UNAVAILABLE / IDLE
    detail: str


def get_or_create_source(session: Session) -> Source:
    row = session.execute(select(Source).where(Source.name == settings.source_name)).scalar_one_or_none()
    if row is None:
        row = Source(name=settings.source_name, url=settings.source_url, status="IDLE")
        session.add(row)
        session.flush()
    return row


def trigger_ingestion() -> IngestionOutcome:
    with get_session() as session:
        source_row = get_or_create_source(session)
        adapter = build_source(source_row.name, source_row.url)
        return run_ingestion(session, source_row, adapter)


def get_system_status() -> SystemStatus:
    with get_session() as session:
        source_row = get_or_create_source(session)
        job_count = session.execute(select(func.count(Job.id))).scalar_one()

        status = source_row.status
        if status in ("OPERATIONAL", "IDLE") and job_count == 0:
            return SystemStatus("IDLE", "No ingestion has run yet.")
        if status == "UNAVAILABLE":
            return SystemStatus(
                "SOURCE UNAVAILABLE",
                f"Serving last known good data ({job_count} jobs) while the source recovers.",
            )
        if status == "DEGRADED":
            return SystemStatus("DEGRADED", "Source is unstable. Existing data is preserved.")
        if status == "RECOVERING":
            return SystemStatus("RECOVERING", "Source has just come back; confirming stability.")
        return SystemStatus("OPERATIONAL", f"Source healthy. {job_count} jobs indexed.")


def get_metrics() -> dict:
    with get_session() as session:
        total_jobs = session.execute(select(func.count(Job.id))).scalar_one()
        successful_runs = session.execute(
            select(func.count(IngestionRun.id)).where(IngestionRun.status == "SUCCESS")
        ).scalar_one()
        failed_runs = session.execute(
            select(func.count(IngestionRun.id)).where(IngestionRun.status.in_(["FAILED", "DEGRADED"]))
        ).scalar_one()
        duplicates = session.execute(select(func.sum(IngestionRun.records_duplicate))).scalar_one() or 0
        quarantined = session.execute(select(func.count(QuarantinedRecord.id))).scalar_one()
        stored = session.execute(select(func.sum(IngestionRun.records_stored))).scalar_one() or 0

        last_run = session.execute(
            select(IngestionRun).where(IngestionRun.status == "SUCCESS").order_by(IngestionRun.completed_at.desc())
        ).scalars().first()

        durations = session.execute(
            select(IngestionRun.started_at, IngestionRun.completed_at).where(IngestionRun.completed_at.is_not(None))
        ).all()
        avg_duration = None
        if durations:
            secs = [(c - s).total_seconds() for s, c in durations if c and s]
            if secs:
                avg_duration = sum(secs) / len(secs)

        return {
            "total_jobs": total_jobs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "duplicates": int(duplicates),
            "quarantined": quarantined,
            "records_stored": int(stored),
            "last_success_at": last_run.completed_at if last_run else None,
            "avg_duration_seconds": avg_duration,
        }


def list_jobs(search: str | None = None, source: str | None = None, limit: int = 200) -> list[Job]:
    with get_session() as session:
        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if search:
            like = f"%{search.lower()}%"
            stmt = select(Job).where(
                func.lower(Job.title).like(like) | func.lower(Job.company).like(like)
            ).order_by(Job.created_at.desc()).limit(limit)
        if source:
            stmt = stmt.where(Job.source == source)
        jobs = session.execute(stmt).scalars().all()
        session.expunge_all()
        return list(jobs)


def list_events(severity: str | None = None, limit: int = 100) -> list[IngestionEvent]:
    with get_session() as session:
        stmt = select(IngestionEvent).order_by(IngestionEvent.created_at.desc()).limit(limit)
        if severity:
            stmt = stmt.where(IngestionEvent.severity == severity)
        events = session.execute(stmt).scalars().all()
        session.expunge_all()
        return list(events)


def list_runs(limit: int = 25) -> list[IngestionRun]:
    with get_session() as session:
        runs = session.execute(
            select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)
        ).scalars().all()
        session.expunge_all()
        return list(runs)


def get_source_health() -> Source | None:
    with get_session() as session:
        row = get_or_create_source(session)
        session.expunge(row)
        return row


def list_quarantine(limit: int = 50) -> list[QuarantinedRecord]:
    with get_session() as session:
        rows = session.execute(
            select(QuarantinedRecord).order_by(QuarantinedRecord.created_at.desc()).limit(limit)
        ).scalars().all()
        session.expunge_all()
        return list(rows)
