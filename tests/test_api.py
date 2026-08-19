"""Tests for api.py, including the Chaos Lab endpoints, using FastAPI's
TestClient against the same temp database as the other tests."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import router
from database import init_db


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    @app.on_event("startup")
    def _startup():
        init_db()

    return TestClient(app)


def test_health_endpoint_returns_state():
    client = make_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "state" in body and "detail" in body


def test_metrics_endpoint_returns_real_zero_state_when_empty():
    client = make_client()
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_jobs"] == 0
    assert body["successful_runs"] == 0


def test_manual_ingestion_endpoint_runs_pipeline():
    client = make_client()
    resp = client.post("/api/ingestion/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("SUCCESS", "FAILED", "DEGRADED")


def test_jobs_endpoint_after_ingestion():
    client = make_client()
    client.post("/api/ingestion/run")
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_chaos_empty_endpoint_preserves_state_and_reports_empty_response():
    client = make_client()
    client.post("/api/ingestion/run")  # seed some data first
    resp = client.post("/api/chaos/empty")
    assert resp.status_code == 200
    assert resp.json()["empty_response"] is True


def test_chaos_schema_drift_endpoint_reports_drift():
    client = make_client()
    resp = client.post("/api/chaos/schema-drift")
    assert resp.status_code == 200
    assert resp.json()["schema_drift"] is True


def test_chaos_rate_limit_endpoint_recovers():
    client = make_client()
    resp = client.post("/api/chaos/rate-limit")
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESS"


def test_chaos_source_failure_endpoint_reports_failed_status():
    client = make_client()
    resp = client.post("/api/chaos/source-failure")
    assert resp.status_code == 200
    assert resp.json()["status"] == "FAILED"
