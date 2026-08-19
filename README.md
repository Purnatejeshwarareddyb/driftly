# DRIFTLY

**Catch the change before it breaks the pipeline.**

A resilient job-data ingestion platform. The job listings are the
demonstration data; the actual product idea is a system that keeps
ingesting from an external source and stays useful when that source
becomes unreliable.

##  Live
[![Live Demo]([https://shields.io](https://driftly-li9i.onrender.com/))]([https://your-demo-url.com](https://driftly-li9i.onrender.com/))


## Problem

Any pipeline that depends on a third-party source will, eventually, meet a
source that rate-limits it, goes down, returns nothing, or silently
changes its response shape. Most demo projects assume the happy path and
fall over the first time that happens. DRIFTLY assumes the unhappy path is
the interesting part.

## Solution

A single Python process ingests job listings from a public feed through a
pipeline that validates, normalizes, deduplicates, and stores every
record - and that keeps serving the last known good dataset instead of
going blank the moment the source misbehaves.

```
SOURCE -> FETCH -> DETECT -> VALIDATE -> NORMALIZE -> DEDUPLICATE -> STORE
                                    |
                                    v
                        MONITOR  ->  RECOVER
```

## Why DRIFTLY exists

Ingestion projects are usually graded on whether they can fetch and
display data. DRIFTLY is built around the harder question: what does the
system do in the first ten seconds *after* the source stops cooperating?
That is where source health tracking, retry/backoff, empty-response
protection, schema-drift detection, and last-known-good serving all come
from - they are the answer to "what happens next," not decoration on top
of a working demo.

## Architecture

One process serves both the dashboard and the JSON API - no separate
frontend build, no Node.js.

| File | Responsibility |
|---|---|
| `main.py` | Entry point; wires FastAPI, the API router, and the NiceGUI dashboard together |
| `config.py` | All environment-driven configuration in one place |
| `database.py` | SQLAlchemy engine/session, schema creation |
| `models.py` | ORM tables: jobs, sources, ingestion_runs, ingestion_events, quarantined_records |
| `schemas.py` | Pydantic validation models, kept separate from the ORM on purpose |
| `adapters.py` | Source adapter abstraction (`BaseJobSource`, `PublicFeedSource`, `DemoFixtureSource`) |
| `ingestion.py` | The pipeline itself: fetch, detect, validate, normalize, deduplicate, store |
| `resilience.py` | Retry/backoff with jitter, source status transitions |
| `services.py` | Read-side services (health, metrics, events, quarantine) backed entirely by SQLite |
| `api.py` | FastAPI routes |
| `ui.py` | NiceGUI dashboard |
| `chaos.py` | Chaos Lab: drives the real pipeline against fake, in-process failing sources |

## Data flow

A manual "Run ingestion" action (UI button or `POST /api/ingestion/run`)
calls `ingestion.run_ingestion`, which:

1. Asks the configured source adapter for raw records, wrapped in
   `resilience.run_with_retry` (exponential backoff + jitter on rate
   limits and transient errors).
2. If the source returned zero records, treats that as suspicious rather
   than "no jobs today": logs `EMPTY_RESPONSE`, leaves existing data
   alone, and marks the source degraded.
3. Validates every record against `schemas.RawJobRecord`. Anything that
   fails validation is quarantined with a reason, never silently dropped.
4. If effectively every record in a batch fails validation, that is
   treated as schema drift rather than universally bad data: the batch is
   quarantined wholesale, the source is marked `DEGRADED`, and existing
   jobs are untouched.
5. Normalizes whitespace, URLs, and missing locations.
6. Deduplicates on `source + external_id`, falling back to a deterministic
   content hash of stable fields.
7. Stores new jobs, updates source health, and logs every step as an
   `ingestion_event` so the dashboard's Recovery Timeline is built from
   real rows, not scripted copy.

## Resilience strategy

- **Rate limits**: limited retries, exponential backoff with jitter,
  events for `RATE_LIMITED` / `RETRY_STARTED` / `RETRY_FAILED` /
  `RECOVERED`.
- **Empty response**: never deletes existing jobs; logs the anomaly,
  keeps serving the last successful dataset, and surfaces
  "Serving last known good dataset" in the UI.
- **Source failure**: after repeated failures the source is marked
  `UNAVAILABLE`; the dashboard explicitly shows "SOURCE UNAVAILABLE -
  Serving last known good data" along with the real timestamp and record
  count of the last successful run.
- **Schema drift**: detected when a batch of records no longer validates
  against the expected shape; affected data is quarantined, existing data
  is preserved, and the pipeline stays operational rather than crashing
  or corrupting the database.

## Source strategy & ethical boundary

The default source is the RemoteOK public jobs API
(`https://remoteok.com/api`), a public, unauthenticated JSON endpoint. The
adapter (`adapters.PublicFeedSource`) performs a single plain HTTP GET
with an honestly-labelled `User-Agent` and nothing more.

This project deliberately does **not** implement CAPTCHA bypass,
fingerprint spoofing, cookie/session theft, authentication bypass, proxy
or account rotation, or any other access-control evasion technique, and
none should be added. If a source requires that kind of access, it is out
of scope for DRIFTLY - the goal is to demonstrate resilient ingestion
architecture, not to defeat a website's security. Setting
`SOURCE_URL=demo` runs the whole pipeline offline against a bundled
fixture (`data/demo_fixture.json`) shaped like the same public API, so the
system can be fully demonstrated with no network dependency at all.

## Database design

SQLite via SQLAlchemy, five tables: `jobs`, `sources`, `ingestion_runs`,
`ingestion_events`, `quarantined_records`. See `models.py` for exact
columns. Deduplication uses a unique index on `jobs.content_hash`, and a
secondary lookup on `(source, external_id)` when a source provides its own
identifier.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/jobs` | List jobs (`search`, `source` query params) |
| GET | `/api/jobs/{id}` | Single job |
| GET | `/api/health` | System status used by the dashboard |
| GET | `/api/source-health` | Current source health record |
| GET | `/api/metrics` | Real, database-derived metrics |
| GET | `/api/events` | Ingestion events (`severity` filter) |
| GET | `/api/ingestion/runs` | Recent ingestion runs |
| POST | `/api/ingestion/run` | Trigger a real ingestion cycle |
| POST | `/api/chaos/rate-limit` | Simulate a rate-limited-then-recovered source |
| POST | `/api/chaos/empty` | Simulate an empty response |
| POST | `/api/chaos/source-failure` | Simulate a source that is fully down |
| POST | `/api/chaos/schema-drift` | Simulate a source whose shape has changed |

## Chaos Lab

Every Chaos Lab button drives the *real* `ingestion.run_ingestion`
function against a fake, in-process source built specifically to fail in
one way (`chaos.py`). This means the recovery behavior you see in the
Chaos Lab is the same code path a genuine outage would hit - nothing is
scripted or faked for the demo. No Chaos Lab action ever makes an
external network call.

## Testing

```
pytest tests/ -v
```

Covers: retry/backoff and status transitions (`test_resilience.py`),
validation, normalization, deduplication, empty-response handling, schema
drift, and recovery (`test_ingestion.py`), and the API surface including
every Chaos Lab endpoint (`test_api.py`). Tests run against a throwaway
temp SQLite database and never touch `data/driftly.db` or the network.

## PyCharm setup (Windows)

1. Open the `driftly/` folder as a PyCharm Community Edition project.
2. Create/select a Python 3.11 virtual environment when prompted (or via
   *File > Settings > Project > Python Interpreter*).
3. Open the Terminal tab inside PyCharm and run:
   ```
   pip install -r requirements.txt
   ```
4. Run `main.py` (right-click -> Run, or `python main.py` in the
   terminal).
5. Open `http://127.0.0.1:8080` in a browser.

No Node.js, no npm, no separate frontend process.

## Local execution

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

Then open `http://127.0.0.1:8080`.

## Docker

```
docker compose up --build
```

Runs as a single service; SQLite data persists in the `driftly-data`
volume, mounted at `/app/data`.

## Known limitations

- Ingestion is manually triggered rather than scheduled; a production
  version would add a background poller with its own jitter.
- The demo source (RemoteOK) is a convenient public feed, not a
  contractual data source - field coverage varies job to job.
- SQLite is intentionally simple for a six-hour build; a production
  deployment would move to Postgres for concurrent writers.
- Chaos Lab simulations are in-process and do not exercise real network
  failure modes (DNS failures, TLS errors, partial responses) - only the
  application-level failure classes DRIFTLY is designed to handle.

## Future improvements

- Scheduled polling with configurable interval and its own backoff state.
- Multiple concurrent source adapters feeding the same pipeline.
- Alerting (webhook/email) on `SCHEMA_DRIFT` and `SOURCE UNAVAILABLE`.
- Structured schema versioning so drift can be diffed, not just detected.
