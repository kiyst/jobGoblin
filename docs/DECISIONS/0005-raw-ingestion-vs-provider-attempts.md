# 0005 — Raw ingestion vs. provider-attempt telemetry are separate concerns

## Status
Accepted, revised (Rev 3): `raw_job_ingestions`' status column renamed
`processing_status` and its enum narrowed — see
[0007-identity-conflict-quarantine.md](0007-identity-conflict-quarantine.md) for the
full reasoning and the two new conflict-related states it interacts with.

## Context
Rev 1 modeled "raw ingestion" as a single table (`raw_job_ingestions`) and additionally
gave `job_occurrences` a `last_raw_ingestion_id` FK pointing at it, while
`raw_job_ingestions` itself had a `job_occurrence_id` FK pointing back — a circular
reference between the two tables that has to be kept in sync from both directions and
provides no information a derived query couldn't give directly.

Separately, a single table was being asked to answer two different questions at two
different granularities: "did calling this source work at all this run?" (a
request/attempt-level concern — durations, retries, rate limits, zero-result responses,
total failures with no payload at all) and "here is one specific posting's raw payload,
before normalization" (a per-record concern). Conflating them makes it impossible to
represent a common real case cleanly: a provider request that succeeds overall but
contains one malformed posting among many good ones, versus a provider request that
fails entirely before any payload is ever seen.

## Decision

**Remove the circular FK.** `job_occurrences` no longer has `last_raw_ingestion_id`.
The relationship is one-directional: `raw_job_ingestions.job_occurrence_id` (nullable,
set once this payload is associated with any occurrence — see
[0007](0007-identity-conflict-quarantine.md) for the two conflict cases where it's still
populated). "The latest cleanly-processed ingestion for a given occurrence" is a derived
query — `SELECT * FROM raw_job_ingestions WHERE job_occurrence_id = :id AND
processing_status = 'normalized' ORDER BY fetched_at DESC LIMIT 1` (column renamed
`processing_status`, enum narrowed — see the Rev 3 update below) — backed by an index on
`(job_occurrence_id, fetched_at DESC)`. There is no stored pointer to keep in sync, and no
risk of the pointer and the underlying rows disagreeing.

**Insertion order:** a `RawJobIngestion` row is written immediately when a posting
payload is fetched (`job_occurrence_id = NULL` at that point). Normalization and identity
resolution ([0004](0004-scoped-deterministic-identity.md)) run as a subsequent step; only
on success is the row updated to point at the `JobOccurrence` it produced or refreshed.
This ordering guarantees the raw payload is preserved even if normalization crashes,
which is the entire point of retaining raw data per master spec §17.

**Separate the two granularities into two tables:**
- `raw_job_ingestions` (Phase 1) — one row per individual posting payload. Its
  `processing_status` (renamed from `retrieval_status` in the Rev 3 follow-up review —
  see [0007](0007-identity-conflict-quarantine.md)) describes that payload's own
  processing outcome (`fetched` / `parse_error` / `normalized` / `identity_conflict`) —
  narrowed to states that can actually apply to a payload that was fetched at all;
  request-level failure modes that produce no payload live exclusively on
  `collection_run_provider_attempts` below, never here.
- `collection_run_provider_attempts` (Phase 1 schema; first written by Phase 2's
  fixture-driven ingestion proof — see [DATA_MODEL.md](../DATA_MODEL.md)) — one row per
  `(collection_run, provider, source)`. Describes the request itself: `started_at`/
  `completed_at`, `status`, `retry_count`, `rate_limited`, `error_category`, sanitized
  `error_message`, `incomplete_results`, and per-slice job counts. A request that
  succeeds but finds zero jobs is `status = 'ok'`, `jobs_discovered = 0` — not an error.
  A request that fails before any payload is fetched produces an attempt row with an
  error and **zero** associated `RawJobIngestion` rows, since there was no payload to
  preserve.

`CollectionRun` remains the parent aggregate over both: it keeps its own run-level
rollup counters (for fast dashboard reads) while `collection_run_provider_attempts`
holds the authoritative per-source detail.

## Consequences
- No circular foreign key to reason about or accidentally desynchronize.
- "Which specific posting failed to parse" and "which source failed to respond" are
  answerable independently, at the granularity each question actually operates at.
- Phase 12's anomaly detection (master spec §10/§41 — distinguishing "the market has
  fewer jobs" from "our connector broke") reads `collection_run_provider_attempts`,
  which is per-source, so one broken source inside a multi-source provider doesn't get
  averaged away by other healthy sources in the same run.
- `collection_run_provider_attempts` is migrated in Phase 1 because Phase 2's manual
  fixture run already produces per-source attempts and partial-failure telemetry. Phase
  9's scheduler reuses the same table; scheduling is not required for a collection run
  to exist.
