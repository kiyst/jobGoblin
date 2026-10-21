# 0019 — Local read-only jobs API (Phase 4 S4)

## Status

Implemented on `phase-4/read-api-s4` (risk class R, `slice_kind: tooling`,
`declared_gate: final`), base `2a9c2a9570d3cb105a376a9b907658f736950be8` (`Q` of the
Phase 4 S3 merge). Not merged.

The product contract is the user's S4 decision (2026-10-21), recorded below. The
implementation details come from the consolidated implementation proposal as amended by
one fresh Claude proposal review (changes requested; eight findings batched into one
amendment). ADR 0014's Phase 4 sequence left S4 as "read API" without routes; this ADR
fixes it. Nothing in ADR 0011, 0013–0018 changes.

## Context

S3 persists three normalized fields with provenance on an opt-in, offline path. Before
S4 the application had only `/health` and `/ready`, and nothing could inspect persisted
jobs. The repository did not define S4's routes, fields, pagination, errors, access, or
terms; a planning review established that, and the user decided them.

## Decision

### 1. Routes

`GET /jobs` and `GET /jobs/{job_id}`, no version prefix (the ADR 0013 route precedent).
No create, update, delete, ingestion, run-now, user-state, or administrative route.

### 2. Responses

- **List:** `{"items": [...], "next_cursor": "<opaque>" | null}`. Each item has exactly
  `id`, `title`, `company` (`null` or `{id, name}`), `location_raw`, `country`,
  `employment_type`, `seniority`, `canonical_url`, `first_seen_at`, `last_seen_at`,
  `active`.
- **Detail:** the list fields plus `description_clean` and `occurrences`. Occurrences
  are ordered `last_seen_at DESC, id DESC`, and each has exactly `provider`, `source`,
  `source_url`, `apply_url`, `is_active`, `first_seen_at`, `last_seen_at`.
- **Never exposed:** `description_raw`, raw payloads, `field_provenance`, parser
  versions, raw-ingestion or occurrence IDs, source tenant/job/requisition identifiers,
  applicant counts, normalized URL internals, salary, scores, or user state.
- The Pydantic response models (`app/schemas/job_read.py`) forbid extra fields.

### 3. Missing values and provenance

An absent value is JSON `null`; clients must render it as **"not listed"**. No default
is manufactured (no "unknown", zero, empty string, or empty object). `null` does **not**
say whether a parser abstained or the field was never normalized: S3 writes no
`unavailable` provenance entry, so S4 cannot tell. `field_provenance` is not exposed.

### 4. Which jobs appear

By default only jobs with at least one active occurrence; `include_inactive=true` (exactly
`true` or `false`) includes the rest. `active` = "at least one occurrence is active". Any
job, active or not, is retrievable by ID. No hidden-job behavior (that is user state, and
S4 has no user scope).

### 5. Filters

Optional, combinable, all trimmed:

- `title`, `location`: case-insensitive literal substring of `Job.title` /
  `Job.location_raw`, at most 200 characters; `\`, `%` and `_` are matched literally
  (`ILIKE … ESCAPE '\'`).
- `country`, `employment_type`, `seniority`: case-insensitive exact match, at most 64
  characters.

Empty or whitespace-only values, over-length values, and values containing a control
character are invalid, never silently broadened. No other filter exists.

### 6. Pagination and ordering

Cursor pagination, fixed order `last_seen_at DESC, id DESC`, default limit 25, maximum
100, no total count, no sort option. The cursor is URL-safe base64 (no padding) of
compact JSON `{"i": <uuid>, "t": <ISO-8601 with offset>}` for the last row returned; the
next page is `(last_seen_at, id) < (t, i)`, so equal timestamps are neither duplicated
nor skipped under an unchanged snapshot.

### 7. Error contract (fixed, non-reflective)

| Case | Status | Body |
|---|---|---|
| Malformed job UUID, or no such job | 404 | `{"error":{"code":"job_not_found","message":"Job not found"}}` |
| Malformed cursor | 400 | `{"error":{"code":"invalid_cursor","message":"Invalid pagination cursor"}}` |
| Invalid limit, filter, or `include_inactive`; unknown or repeated parameter | 400 | `{"error":{"code":"invalid_query","message":"Invalid query parameters"}}` |
| Unexpected failure inside a route | 500 | `{"error":{"code":"internal_error","message":"Internal server error"}}` |

- **No 422:** neither route declares a typed query or path parameter, so FastAPI's
  input-echoing 422 cannot occur.
- **Precedence:** `invalid_query` checks run before the cursor check.
- **"Missing" job:** a well-formed UUID with no row. `/jobs/` itself redirects to
  `/jobs`. Paths and methods that match neither route (`/jobs/a/b`, `POST /jobs`) get
  FastAPI's fixed default 404/405 bodies, which reflect nothing.
- **Cursor times** are normalized to UTC while decoding. A cursor whose time cannot be
  represented, or whose offset is missing, is `invalid_cursor`.
- **Logging:** route failures log only the exception type, never its message.
- **Failures outside the route body** (dependency setup or teardown, response
  serialization) get Starlette's plain-text generic `Internal Server Error`. No SQL,
  path, traceback, or submitted value appears in any response.

Implementation choices within the contract, recorded here:

- rejecting unknown and repeated parameters, and control characters;
- the JSON shape of the 500 body;
- retrieving inactive jobs by ID.

### 8. Access boundary

Unauthenticated, **localhost only**. Docker Compose binds `127.0.0.1:8000:8000`
(backend) and `127.0.0.1:5432:5432` (PostgreSQL); Uvicorn still listens on `0.0.0.0`
inside its container. S4 is not an Internet- or LAN-facing API, and has no
authentication or user isolation. No auth system is added.

### 9. Architecture

- `app/api/jobs.py` does thin routing and response mapping only.
- `app/api/deps.py` wires `JobReaderDep`.
- `app/services/job_read.py` owns query validation, cursor handling, every
  ORM/SQLAlchemy interaction, and session acquisition (`job_reader`,
  `open_read_only_reader`).
- `app/schemas/job_read.py` holds the response models and imports only the standard
  library and Pydantic.
- `app/main.py` only registers the router.

**Clarification of ARCHITECTURE.md §5:** `api/deps.py` provides the database session
indirectly, by depending on a services-owned provider. So `api/` never imports `db/` or
SQLAlchemy, and routes contain no ORM model or query. `api/health.py`'s direct
`app.db.session` import predates this decision and is a recorded exception, not
precedent.

### 10. Read-only enforcement

- `open_read_only_reader` opens a session and always rolls it back, in `finally`.
- The reader's first statement is `SET TRANSACTION READ ONLY`, so PostgreSQL rejects
  any write in that transaction. It is issued lazily, inside the route's error handling.
- The service issues only `SELECT`s: no commit, flush, add, delete, update, row lock,
  ingestion call, or provider import. Tests and an AST check pin this.

### 11. Terms and scope

Localhost presentation of already-persisted job data, for personal, self-hosted,
noncommercial use. Only `description_clean` may be returned; `description_raw` and raw
ingestion data stay private. This is **not** legal clearance and does not authorize
public or LAN exposure, commercial use or resale, recurring collection, a provider
request, another board or endpoint, persistence activation, runtime ingestion, or S5.

### 12. Risk class and workflow

Class R, final gate (`app/api`, `app/services`, `app/schemas` and the other new paths are
unmapped in `verification_scope`). Rationale: read-only, localhost-only, unauthenticated,
no acquisition, no persisted change; the localhost binding and the non-reflective error
contract are load-bearing. The Phase 8 personalized-feed preflight does not apply: S4 is
a bounded Phase 4 inspection API, not the Phase 8 feed, scoring, or user workspace. The
repository validator requires Sol Medium for the formal primary review of executable
(tooling) slices.

### 13. Proof and demo data

- **Tests:** every test runs against deterministic fixtures in the disposable PostgreSQL
  test database. None contacts Greenhouse or depends on S2c staging.
- **Demo:** `scripts/seed_demo_jobs.py` seeds or removes clearly labelled **fixture**
  rows. It writes only to the disposable test database, guarded by `db_safety`, and
  calls no provider, network, or ingestion code. The API and service layer stay
  read-only; this host-side fixture tool is the only writer.
- Demo output is not live Greenhouse ingestion. After S5, the same API displays actually
  persisted live-ingestion results.

## Exclusions

No provider contact, live ingestion, S5, persistence activation, migration or schema
change, auth system, user state, write route, `field_provenance` exposure,
`description_raw`, public or LAN exposure, or change to the S3 D1 closure (no file in it
is edited; `app/schemas/__init__.py` is untouched).

## Consequences

- Persisted jobs can be inspected locally as JSON with a stable, documented contract.
- Exposing more fields, provenance, user state, or a non-local binding is a new,
  separately decided change.
