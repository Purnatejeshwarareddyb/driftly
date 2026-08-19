"""
schemas.py

Pydantic models used for two purposes:
  1. Validating raw records coming out of a source adapter (RawJobRecord).
  2. Shaping API responses (the *Out models).
Keeping these separate from the SQLAlchemy models in models.py means a
source-side schema change can never silently corrupt the database schema.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, field_validator


class RawJobRecord(BaseModel):
    """What we require from *any* source before it is trusted as a job."""

    title: str
    company: str
    location: str
    url: str
    external_id: str | None = None
    description: str | None = None
    published_at: dt.datetime | None = None

    @field_validator("title", "company", "location", "url")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field must not be blank")
        return v.strip()


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    location: str
    description: str | None
    url: str
    source: str
    published_at: dt.datetime | None
    created_at: dt.datetime


class SourceHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    url: str
    status: str
    last_success: dt.datetime | None
    last_failure: dt.datetime | None
    consecutive_failures: int
    last_latency: float | None


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    started_at: dt.datetime
    completed_at: dt.datetime | None
    status: str
    records_received: int
    records_valid: int
    records_stored: int
    records_duplicate: int
    records_failed: int


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    event_type: str
    severity: str
    message: str
    created_at: dt.datetime
