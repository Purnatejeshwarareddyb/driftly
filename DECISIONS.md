# DECISIONS.md

Engineer-to-engineer notes on why DRIFTLY is built the way it is.

## 1. Why this ingestion strategy instead of the obvious alternative?

The obvious version of this assignment is "fetch job listings, show them in
a table." That version is graded almost entirely on whether the happy path
works. I instead built the pipeline around the assumption that the source
*will* misbehave during the demo or the review, and made that the main
engineering story: retry/backoff on rate limits, empty-response protection
that refuses to wipe existing data, schema-drift detection that quarantines
instead of corrupting, and a source-health state machine
(`OPERATIONAL -> DEGRADED -> UNAVAILABLE -> RECOVERING`) that the dashboard
reflects honestly. The alternative - polling on a timer with a try/except
around the fetch - would have been faster to write and much weaker to
defend in a follow-up call, because there would be nothing to point at
except "it usually works."

## 2. What trade-off was made under the six-hour constraint?

I kept the module count small on purpose (12 top-level modules, not 30+).
Each module has one clear responsibility (`adapters.py` only knows about
talking to a source, `resilience.py` only knows about retry/backoff and
status transitions, `ingestion.py` only wires stages together), but I did
not split those further into micro-modules just to make the file tree look
larger. The trade-off: some functions in `ingestion.py` (`run_ingestion`
itself) are longer than I'd want in a mature codebase, because I chose
readability and "one place to read the whole pipeline" over maximal
decomposition, given the time budget. I also chose SQLite over Postgres -
correct for a six-hour, single-reviewer demo, wrong for a real production
deployment with concurrent writers.

## 3. What would be improved with a full week?

- Move `run_ingestion` from "one long function with clear sections" to
  properly separated stage objects, now that the behavior is proven out by
  tests - premature separation before the shape was clear would have cost
  more time than it saved.
- Add a real scheduled poller (with its own jitter) instead of a manual
  "Run ingestion" button, plus alerting on `SCHEMA_DRIFT` /
  `SOURCE UNAVAILABLE`.
- Add schema versioning so drift is diffable ("field X disappeared, field Y
  appeared") rather than binary detected/not-detected.
- Load-test the empty-response and schema-drift thresholds against real
  historical response variance from the source, instead of the
  conservative defaults (`DEGRADED_AFTER_FAILURES=1`,
  `UNAVAILABLE_AFTER_FAILURES=3`) I picked for a fast demo.
- Move to Postgres and add connection pooling once there's more than one
  writer.

## 4. Where AI tools were used

I used Claude to scaffold the initial project structure and generate the
first pass of each module from a detailed spec I wrote describing the
pipeline stages, the resilience behavior, the database schema, and the
visual direction (a storm-sky theme tying the "drift" name to the literal
weather metaphor - calmer sky when healthy, more cloud and lightning when
degraded). I also used it to generate the pytest suite and the offline
demo fixture data.

## 5. What was personally verified or changed

I ran the full pipeline end to end against both the live public source and
the offline demo fixture, and ran `pytest tests/ -v` to confirm every
resilience path (rate limit -> recovery, empty response -> preserved data,
schema drift -> quarantine, repeated failure -> `UNAVAILABLE`) actually
happens, not just that the code compiles. In that process I found and
fixed a real bug: the empty-response branch of `run_ingestion` built an
`IngestionOutcome` with its `status` field left at the default `"RUNNING"`
instead of being set to `"DEGRADED"`, so the Chaos Lab's "Simulate Empty
Response" button was reporting the wrong status even though the underlying
behavior (data preserved, source degraded) was correct. I added a
regression test for it (`test_empty_response_preserves_existing_jobs`
now asserts `outcome.status == "DEGRADED"`) so it can't silently regress.
I can walk through any file line by line in the follow-up interview.

## Source selection

RemoteOK's public API was chosen because it requires no authentication, no
API key, and is intended to be machine-readable - it is the lowest-risk
real source that still demonstrates genuine schema variance across
listings. `SOURCE_URL=demo` swaps in a bundled, shape-identical fixture for
fully offline demonstration.

## Rate-limit behavior

Exponential backoff with full jitter (`resilience.compute_backoff`),
capped retries (`MAX_RETRIES`, default 3), every attempt logged as an
event so the Recovery Timeline shows the real sequence rather than a
summary.

## Empty-response protection

Zero records is treated as an anomaly, not "no jobs posted today."
Existing data is never deleted on an empty response; the source is marked
degraded and the event log records `EMPTY_RESPONSE` explicitly.

## Schema-drift strategy

If every record in a batch fails validation, that is classified as drift
(the source's shape changed) rather than "every job posting today happened
to be malformed." The whole batch is quarantined, the source is marked
`DEGRADED`, and existing jobs are left untouched.

## Last-known-good strategy

`services.get_system_status` derives the banner text and state directly
from the `sources` and `jobs` tables on every request - there is no cached
"is everything fine" flag that could drift from reality. When the source is
`UNAVAILABLE`, the dashboard states the real last-success timestamp and
real job count from SQLite.

## Ethical boundary

See README.md "Source strategy & ethical boundary." No CAPTCHA bypass,
fingerprint spoofing, credential/session theft, or proxy/account rotation
is implemented anywhere in this project, and the Chaos Lab never makes an
external network call - every simulated failure is driven by a fake,
in-process adapter.
