"""
database.py

SQLAlchemy engine and session management. One engine, one sessionmaker,
one declarative base. Nothing else in the project should create its own
connection.
"""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_session():
    """Yield a session and guarantee it is closed, committing on success."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables and seed the configured source row if missing."""
    import models  # noqa: F401  (ensure models are registered on Base)

    Base.metadata.create_all(bind=engine)

    from models import Source
    from config import settings as cfg

    with get_session() as session:
        existing = session.query(Source).filter_by(name=cfg.source_name).first()
        if not existing:
            session.add(Source(name=cfg.source_name, url=cfg.source_url, status="IDLE"))
