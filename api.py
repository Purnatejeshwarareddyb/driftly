"""
api.py

FastAPI routes. This is a thin layer over services.py / ingestion.py /
chaos.py - no business logic lives here, only request/response shaping.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

import chaos
import services
from database import get_session
from models import Job
from schemas import EventOut, IngestionRunOut, JobOut, SourceHealthOut

router = APIRouter(prefix="/api")


@router.get("/jobs", response_model=list[JobOut])
def get_jobs(search: str | None = Query(default=None), source: str | None = Query(default=None)):
    return services.list_jobs(search=search, source=source)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int):
    with get_session() as session:
        job = session.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        session.expunge(job)
        return job


@router.get("/health")
def get_health():
    status = services.get_system_status()
    return {"state": status.state, "detail": status.detail}


@router.get("/source-health", response_model=SourceHealthOut)
def get_source_health():
    row = services.get_source_health()
    if row is None:
        raise HTTPException(status_code=404, detail="No source configured")
    return row


@router.get("/metrics")
def get_metrics():
    return services.get_metrics()


@router.get("/events", response_model=list[EventOut])
def get_events(severity: str | None = Query(default=None)):
    return services.list_events(severity=severity)


@router.get("/ingestion/runs", response_model=list[IngestionRunOut])
def get_runs():
    return services.list_runs()


@router.post("/ingestion/run")
def post_run_ingestion():
    outcome = services.trigger_ingestion()
    return {
        "run_id": outcome.run_id,
        "status": outcome.status,
        "records_received": outcome.records_received,
        "records_valid": outcome.records_valid,
        "records_stored": outcome.records_stored,
        "records_duplicate": outcome.records_duplicate,
        "records_failed": outcome.records_failed,
        "empty_response": outcome.empty_response,
        "schema_drift": outcome.schema_drift,
    }


@router.post("/chaos/rate-limit")
def post_chaos_rate_limit():
    outcome = chaos.simulate_rate_limit()
    return {"status": outcome.status, "run_id": outcome.run_id}


@router.post("/chaos/empty")
def post_chaos_empty():
    outcome = chaos.simulate_empty_response()
    return {"status": outcome.status, "run_id": outcome.run_id, "empty_response": outcome.empty_response}


@router.post("/chaos/source-failure")
def post_chaos_source_failure():
    outcome = chaos.simulate_source_failure()
    return {"status": outcome.status, "run_id": outcome.run_id}


@router.post("/chaos/schema-drift")
def post_chaos_schema_drift():
    outcome = chaos.simulate_schema_drift()
    return {"status": outcome.status, "run_id": outcome.run_id, "schema_drift": outcome.schema_drift}
