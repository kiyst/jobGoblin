# 0020 — One bounded live Greenhouse ingestion into PostgreSQL (Phase 4 S5)

## Status

**Proposed: offline advisory candidate. No live request has been made.** Phase 4 S5
(`phase-4/live-ingestion-s5`, risk class H, `slice_kind: tooling`,
`declared_gate: final`). Base: `fa761e4efc6c7305bfbb4fdcd95e4415ee22c479`, the `Q` of the
S4 merge.

**Pre-live reviews and correction 1.** All three pre-live reviews of the first
advisory candidate (`6ce89cc`) were batched into correction 1:

- **Sol Medium** (primary; `gpt-6.1-sol`, medium effort, Codex CLI): changes requested.
- **Astra** (escalation; `gpt-6-astra`, high effort, Codex CLI): changes requested.
- **A fresh Claude advisory reviewer:** approved, with should-fix findings.

**Authority**, in order:

1. The user's S5 objective and constraints (2026-10-21).
2. ADR 0013 §8 and its five-slice table:
   > S5 | live enablement (separate network authorization; Sol plus Astra) | H / final
3. ADR 0018's open point: "S5 must decide when production ingestion builds and passes a
   context."
4. One consolidated proposal: a fresh Claude planning agent, amended by one fresh Claude
   proposal review (approve-with-amendments; no blocking finding; amendments A1–A10).
   The review artifacts are gitignored under `.claude/runtime/claude-autopilot/s5/`.

The live attempt, the terms and retention disposition, and the database-retention
choice wait for the user's exact authorization at the pre-live checkpoint. Results are
appended under [Results](#results) after the run.

Nothing in ADRs 0011 or 0013–0019 changes.

## Context

S1–S4 built every piece of the path:
- the direct Greenhouse adapter (S1), with the content conversion inside it (S2b);
- pure composition (S2);
- a bounded live canary with no persistence (S2c);
- the D1 parser version and opt-in normalized persistence (S3);
- a local read-only API (S4).

Nothing composes them against a real response. ADR 0018 notes that nothing in the
application builds a normalization context. The Phase 4 exit gate (`ROADMAP.md`;
`PHASE_RISK_CHECKLIST.md`) asks for a real Greenhouse job through the complete pipeline
into PostgreSQL. The earlier live proof (`scripts/live_proof_greenhouse_ingestion.py`)
predates the S1 adapter and normalization, so it does not meet that gate.

## Decision

### 1. Composition root

`backend/scripts/run_greenhouse_s5_live_ingestion.py` is the only composition root. It
builds the normalization context once, from the same provider instance, immediately
before the run, and refuses if its parser version is not the expected one. It reuses
these unchanged:

- `GreenhouseJobBoardProvider`, with board `discord`, company "Discord" and
  `declared-double-escaped`;
- `build_normalization_context`; `pipeline.run` verifies the context again before any
  row;
- `pipeline.run` and its transaction boundaries, which are the only writers;
- the S4 routes (`create_app()`). Only the reader's session binding is overridden, to
  point at the disposable database;
- S2c's reviewed reservation helpers, worker supervision (kill-on-close Job Object and
  terminate/kill/confirm), request constants and request fingerprint, and adapter-failure
  classification, all by import.

The script adds no registry entry, scheduler, application setting or runtime activation.
No file under `app/` changes, so the D1 manifest and the parser version stay unchanged.
For `discord` the version is
`jgnorm-v1:sha256:f086bdd675c364dc250b0770dafedb13c75d3809b905bda6f7373bee62441e32`.

The script must not import `scripts/canary_greenhouse.py` or
`scripts/live_proof_greenhouse_ingestion.py`, so no parallel fetch path exists (A1). A
test pins this.

### 2. Request and bounds

The S2c frozen values:

- **Request:** exactly one `GET https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true`.
- **Retries and routing:** `max_attempts=1`, so no retry; no redirect (`follow_redirects=False`);
  proxy environment ignored (`trust_env=False`).
- **Headers:** the locked `httpx` default User-Agent; the only override is
  `Accept-Encoding: identity`.
- **Timeouts:** connect 5 s, read 10 s, write 5 s and pool 5 s, with a 30 s attempt
  deadline. The adapter's worst case is 55 s.
- **Size limits:** a 5,000,000-byte cap and a 500-record cap, checked before adapter
  conversion.

A guard transport refuses, before any I/O:
- every other method, scheme, host, port, path or query;
- any second send.

It also refuses a non-identity `Content-Encoding`.

The guard enforces two send limits (A3):

- **A per-composition latch**, shared by every transport the provider creates. The adapter
  creates a new transport on each `discover()`, so the latch must sit outside it.
- **A process-lifetime network send budget**, for real `httpx.AsyncHTTPTransport` inner
  transports. No later composition or latch can reset it. Mock transports never use it.

The guard bounds its own send and body read by the adapter's 30 s attempt deadline,
because the adapter's deadline checks cannot run while the guard is still buffering. On
timeout it refuses with `guard_deadline_exceeded`, which counts as INCONCLUSIVE.

Every refusal is a non-`httpx` exception, so the adapter cannot downgrade it into a
graceful per-source failure. It propagates, and `pipeline.run` marks the run `failed`
before any raw row exists (A4).

The body is held in memory only and is never written to a file.

### 3. Gates, reservation and supervision

`live` requires every gate element:

- `JOBGOBLIN_S5_LIVE_INGESTION=authorized-once`;
- `--board discord`;
- `--expected-sha` equal to HEAD on a clean checkout;
- the authorization file and its SHA-256;
- `--expected-parser-version`, computed offline before any network or database work;
- no existing `.claude/runtime/phase4-s5-live/`.

The attempt directory is created exclusively and holds the fsynced reservation, which
binds:
- the board and SHA;
- the request fingerprint;
- the parser version;
- the authorization hash;
- the generated database name;
- the retention flag.

A second attempt is always refused.

The parent process supervises the run (A5):

1. It creates and migrates the database.
2. It launches one worker inside a kill-on-close Job Object, with a 120 s wall-clock
   deadline, and releases a one-time launch capability to it.
3. It always drops the database and checks for leaks, unless retention applies.
4. It appends exactly one terminal outcome.

The parent's own administrative database calls have connect and command timeouts.

The worker's environment gate must match the reserved mode. It does the rest in order:

1. checks the database is fresh;
2. makes the guarded request through `pipeline.run`;
3. checks the persisted rows;
4. reads them back through the API;
5. re-observes the same body offline;
6. writes a categorical summary.

**Offline rehearsal.** `rehearse --confirm-create-and-drop-local-test-database` runs the
same machinery: reservation, `CREATE DATABASE`, migration, supervised worker, guard,
pipeline, API read-back, re-observation, drop and leak check. Only the inner transport
differs: a `MockTransport` serving a synthetic three-record `discord`-shaped envelope.
There is no network. The rehearsal never retains its database and never blocks the live
attempt.

### 4. Database target

The target is a freshly created local database named `jobgoblin_test_s5_<16 hex>`, with
these properties:
- the name is generated, never supplied by a caller, and checked against its grammar
  before quoting;
- it has the same host, port and credentials as `DATABASE_URL`. The URL is built from
  validated components only (`URL.create`), never by editing the configured URL. A
  configured URL is refused if it has any of the following, because asyncpg would apply
  query overrides after the guards inspect the URL:
  - a query option (for example `?host=`, `?database=`, `?port=` or a DSN);
  - another driver;
  - a non-local or multi-host host;
  - a non-integer port.

  Administration, migration and the worker all use this one construction;
- it must pass both `assert_is_disposable_test_database` and
  `assert_safe_for_local_destructive_lifecycle`: localhost only, not production, the name
  contains "test", and it differs from the development database;
- its schema is created by `alembic upgrade head`, the existing migrations, with no new
  migration.

The script never touches the development database (`jobgoblin`) or the shared test
database (`jobgoblin_test`).

**Retention:**
- **Default:** `DROP DATABASE … WITH (FORCE)` plus a leak check, in every outcome.
- **`--retain-database-on-pass`:** keeps only a PASS database, so the user can browse it
  with a local uvicorn bound to 127.0.0.1. Dropping it later is a separately authorized
  step.
- **Non-PASS:** always dropped.

### 5. Raw retention

Persisting stores each complete record, including its HTML `content`, in the disposable
database's `raw_job_ingestions.raw_payload`, which is the existing schema. That content
may include recruiter contact details (ADR 0013 §4).

The S2c terms records explicitly excluded persistence and a third request. So the live
attempt requires the user's new terms and retention disposition, recorded as part of
the authorization.

Retained evidence:
- the gitignored attempt directory (reservation, launch, claim, summary);
- the committed categorical report.

Neither contains titles, URL paths, descriptions, content or other record fields.
Dropping the database is logical deletion, not forensic erasure.

### 6. Verdicts

**PASS** requires all of the following:

1. **Fresh database:** zero runs, raw rows, jobs, occurrences and conflicts before the
   request.
2. **Request:** HTTP 200 JSON with a complete identity-encoded body; `meta.total` equals
   the record count, and every record id is unique.
3. **Run:** `completed`, with the attempt `completed`, no incomplete results, and
   `jobs_discovered` equal to the record count N.
4. **Counts:** `inserted + updated` = N; raw rows = N, all `normalized` with the expected
   parser version; occurrences = N; jobs = `inserted`; zero identity conflicts.
5. **API read-back:**
   - `GET /jobs` pages list every persisted job and nothing else;
   - each `GET /jobs/{id}` returns exactly the ADR 0019 keys;
   - every occurrence has provider and source `greenhouse`.
6. **Offline re-observation** (a separate provider whose only transport is a
   `MockTransport`):
   - run `completed`, 0 inserted and N updated;
   - no new job or occurrence;
   - 2N normalized raw rows;
   - every job's `last_seen_at` advanced.
7. **Cleanup and leak check:** passed, or PASS retention applies.

**INCONCLUSIVE** (S2c's classification):
- timeout, deadline (including the guard deadline) or connection failure;
- HTTP 429 or 5xx;
- an otherwise clean partial attempt (content abstention or completeness evidence).

Identity conflicts and parse errors are decisive local failures. They are checked before
a partial attempt and are FAIL-CLOSED (`posting_errors`).

**FAIL-CLOSED:** everything else. That includes:
- a guard refusal;
- any pipeline exception;
- a run that is `failed`, still `running`, or `completed_with_errors` for a parse error
  or conflict;
- any count or API mismatch;
- the worker deadline;
- worker or containment failure;
- cleanup failure or interruption. The terminal outcome is appended even then.

A missing or non-integer `meta.total` is never PASS.

Unexpected supervisor errors print only a categorical `ERROR` with the exception class.

**Atomicity (A2).** "No partial normalized write" means **per-posting** atomicity. No
normalized value is ever written without its provenance and `parser_version`, in the
same transaction. The run as a whole is not atomic: this is the existing, reviewed
Phase 2/S3 behaviour. If a failure hits posting k:
- postings before k stay fully normalized;
- the rest stay raw `fetched`;
- the run is `failed` (or `running` if the failure telemetry itself fails).

None of that is PASS, and a non-PASS database is always dropped.

### 7. API evidence

The read-back runs the real `create_app()` routes and `open_read_only_reader` over
`httpx.ASGITransport`, with no socket, against the disposable database. This is the S5
API evidence (A10).

The representative output is redacted:
- **Kept:** locally generated IDs, timestamps, booleans, provider/source and taxonomy
  values;
- **Replaced:** titles, locations and descriptions become `<redacted:N chars>`;
- **Reduced:** URLs become scheme and host plus `/<redacted>`.

Greenhouse jobs carry `company: null`, because the pipeline resolves no company (an
existing limitation).

### 8. Sequence and reviewers

1. **Offline advisory candidate and pre-live reviews:**
   - a Claude advisory review;
   - the Sol Medium primary review, which the repository requires for risk H or tooling
     (`check_review.py`);
   - the mandatory Astra network, privacy and threat-model review (ADR 0013 §8), recorded
     separately; it never satisfies the primary role.
2. **One batched correction**, if needed.
3. **The single authorization packet**, then a stop.
4. **The authorized rehearsal, then exactly one live attempt**, on the authorized advisory
   SHA.
5. **Post-run evidence.**
6. **Final `C`**, which differs from the live SHA only in evidence and documentation (A7).
   Otherwise, the changed code is reviewed again, and the live evidence stays attributed
   to the earlier SHA.
7. **`A`, `R`, `M`, `Q`.**

No second live attempt is implied.

## Boundaries

S5 adds none of the following:
- `app/` change, migration or schema change;
- registry, scheduler or runtime activation;
- recurring collection, another provider, board or endpoint;
- salary, scoring, matching, user state or authentication;
- public or LAN exposure.

It also adds no change to ADR 0019's API contract, and no reuse or reconstruction of
deleted S2c staging.

## Results

Pending the authorized rehearsal and live attempt.

## Bounded claim and limitations

**Claim:** one real board, one request, through the complete pipeline into PostgreSQL,
readable through the S4 API. It is not accuracy, coverage, generalization or production
readiness.

Limitations:
- logical deletion only;
- the run is not atomic (§6);
- `company` is null for Greenhouse jobs;
- `null` cannot tell parser abstention from never-normalized (ADR 0019);
- the terms acceptance is a narrow personal risk decision, not legal clearance;
- recurring ingestion remains future work.

## Consequences

- A PASS supplies the Phase 4 exit-gate evidence (a real Greenhouse job, end to end,
  into PostgreSQL). A Phase 4 exit audit is a separate step.
- Production ingestion still does not build a context by default. Any recurring or
  runtime ingestion is a new, separately reviewed decision.
