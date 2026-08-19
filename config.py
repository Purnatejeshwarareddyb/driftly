"""
config.py

Central configuration for DRIFTLY. Everything that could plausibly change
between environments (dev machine, Docker, CI) lives here and nowhere else.
No secrets are hard-coded; values are read from the environment with sane
defaults so `python main.py` works out of the box.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # Persistence
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'driftly.db'}")

    # Source
    # "demo" uses the bundled offline fixture (no network required).
    # Any http(s) URL is treated as a public JSON feed (e.g. the RemoteOK
    # public jobs API, which requires no authentication and no bypass of
    # any access control).
    source_name: str = os.getenv("SOURCE_NAME", "RemoteOK Public Feed")
    source_url: str = os.getenv("SOURCE_URL", "https://remoteok.com/api")

    # Networking
    request_timeout: float = _env_float("REQUEST_TIMEOUT", 10.0)
    max_retries: int = _env_int("MAX_RETRIES", 3)
    backoff_base: float = _env_float("BACKOFF_BASE", 0.5)
    backoff_max: float = _env_float("BACKOFF_MAX", 8.0)
    user_agent: str = os.getenv(
        "DRIFTLY_USER_AGENT", "DriftlyBot/1.0 (+engineering-assessment-demo)"
    )

    # Resilience thresholds
    degraded_after_failures: int = _env_int("DEGRADED_AFTER_FAILURES", 1)
    unavailable_after_failures: int = _env_int("UNAVAILABLE_AFTER_FAILURES", 3)

    # Server
    host: str = os.getenv("DRIFTLY_HOST", "127.0.0.1")
    port: int = _env_int("DRIFTLY_PORT", 8080)


settings = Settings()
