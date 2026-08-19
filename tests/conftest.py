"""Shared pytest fixtures. Points DRIFTLY at a throwaway SQLite file so
tests never touch data/driftly.db."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_dir = tempfile.mkdtemp(prefix="driftly-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test_driftly.db"
os.environ["SOURCE_URL"] = "demo"
os.environ["SOURCE_NAME"] = "Test Source"

from database import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_database():
    from database import Base, engine

    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
