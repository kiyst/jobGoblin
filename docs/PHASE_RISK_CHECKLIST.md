# Phase Risk Checklist

Status: active engineering checklist. Read this document before planning, implementing,
or reviewing every phase. It supplements [ARCHITECTURE.md](ARCHITECTURE.md),
[DATA_MODEL.md](DATA_MODEL.md), and [ROADMAP.md](ROADMAP.md); accepted ADRs remain the
authority when a checklist item and a recorded decision appear to conflict.

## How to use this checklist

For each phase:

1. Confirm the previous phase's exit gate is complete.
2. Review the phase's risks and entry checks below.
3. Approve one small, testable slice rather than the entire phase at once.
4. Keep one active writer. A second engineer/LLM reviews read-only until explicitly
   authorized to fix accepted findings.
5. Run the phase's required tests and record actual results; never report skipped or
   unavailable verification as passing.
6. Stop at the phase boundary and wait for approval.

Every implementation handoff must list files changed, migrations added, commands run,
results, deviations, limitations, and the next smallest task.

## Cross-cutting non-negotiables

- Default tests never contact public job sources.
- PostgreSQL behavior is tested against PostgreSQL, never inferred from SQLite or mocks.
- Every migration is reviewed and tested upgrade -> downgrade -> upgrade.
- Missing or unknown values remain `NULL`; they are never represented as zero or an
  invented value.
- Raw source values are preserved before aggressive transformation.
- Inferred, parsed, derived, and explicit values retain distinct provenance.
- External-library types remain inside their adapter modules.
- One provider/source failure never discards another source's successful results.
- Ingestion never overwrites `UserJob` state or notes.
- Deterministic identity signals are scoped; ambiguous evidence is quarantined, never
  silently merged.
- Fuzzy duplicate detection never automatically merges or deletes jobs.
- Network clients, retries, timeouts, concurrency, and rate limits are source-specific.
- Logs and API responses never expose credentials, tokens, raw stack traces, or applicant
  PII.
- New tables, services, and dependencies require a current consumer and a documented
  replacement/removal path.
- Live-source features have a per-source kill switch and can be disabled without making
  the rest of the application unusable.

## Phase 0 - Repository foundation

Primary risk: a scaffold that appears valid locally but cannot build, migrate, or detect
dependency failure in its real runtime.

Entry checks:

- Python, Docker, Docker Compose, and PostgreSQL versions are explicit.
- Configuration and secret locations are consistent across host and containers.

Exit gate:

- Backend image builds.
- PostgreSQL becomes healthy under Compose.
- Alembic upgrade -> downgrade -> upgrade passes against real PostgreSQL.
- Ruff, mypy, and pytest pass.
- `/health` remains 200 while PostgreSQL is stopped.
- `/ready` returns 503 while PostgreSQL is stopped and returns 200 after restoration.
- Container logs contain no unexpected errors or secrets.

Current status: complete and verified on 2026-08-24.

## Phase 1 - Domain model

Primary risks: irreversible migrations, model/migration drift, incorrect null/unique
behavior, destructive cascades, and user state coupled to source data.

Entry checks:

- Re-read DATA_MODEL.md and ADRs 0001-0007.
- Break work into small migration/model/test slices.
- Define nullability, defaults, uniqueness, checks, indexes, and `ON DELETE` behavior
  before implementing each table.

Required prevention:

- Use timezone-aware UTC timestamps.
- Review Alembic output manually; do not trust autogenerate blindly.
- Test every important constraint with both an accepted and rejected case.
- Test null-bearing unique keys explicitly.
- Keep ingestion/source fields separate from `UserJob` and notes.
- Add factories/helpers that create only valid states by default.

Exit gate:

- Model metadata and migrations describe the same schema.
- Every migration round trip passes on a fresh PostgreSQL database.
- FK deletion behavior and check/unique constraints are covered by database tests.
- User workflow invariants reject contradictory states.
- No provider, network collection, normalization, or scoring code has entered the phase.

## Phase 2 - Provider interface and fixture ingestion

Primary risks: non-idempotent ingestion, incorrect exact identity, partial failures losing
good results, and provider abstractions that cannot represent real behavior.

Entry checks:

- Phase 1 constraints are executable and passing.
- Provider schemas contain only application-owned types.
- Query source selection and per-source capabilities are explicit.

Required fixtures:

- clean posting;
- missing salary and other unknown fields;
- identical re-observation;
- null-tenant re-observation;
- same source ID under different tenants;
- same canonical URL with tracking differences;
- same requisition under different companies/tenants;
- natural-key evidence mismatch;
- ambiguous exact match;
- malformed posting among valid postings;
- one source succeeds while another fails;
- concurrent ingestion of the same natural key.

Exit gate:

- Fixture -> raw ingestion -> identity -> Job/JobOccurrence -> PostgreSQL passes.
- Re-running fixtures is idempotent and only advances observational fields.
- Raw data survives parse and identity failures.
- Successful partial results persist while source errors remain observable.
- Database concurrency tests prove duplicate occurrence insertion is safe.
- No public network access occurs.

## Phase 3 - Deterministic normalization

Primary risk: confidently storing false facts from ambiguous text.

Entry checks:

- Raw fields and provenance storage are stable.
- Each parser has an explicit unknown outcome.

Required prevention:

- Keep parsers pure: text/value in, normalized value plus provenance out.
- Separate extraction from product filtering/scoring policy.
- Preserve raw input and parser version.
- Test negative and ambiguous examples as heavily as happy paths.
- Prefer `NULL` over a low-confidence guess.
- Build a regression corpus from realistic captured payloads with sensitive information
  removed.

Exit gate:

- Title, salary, location, remote type, employment, seniority, experience, and skill
  parsers pass table-driven positive, negative, boundary, and ambiguity tests.
- Parsed/derived/inferred values cannot appear as explicit-source facts.
- No parser imports providers, ORM models, UI code, or network clients.

## Phase 4 - ATS provider

Primary risks: upstream schema changes, tenant-specific failures, rate limits, external
types leaking inward, and treating connector failure as zero jobs.

Entry checks:

- Phase 2 pipeline and Phase 3 normalizers pass without network access.
- Dependency license, reviewed version/commit, compatibility, and replacement path are
  current.
- Start with one structured, low-risk source: Greenhouse or Lever before Workday.

Required prevention:

- Pin the dependency and import it only inside `AtsScrapersProvider`.
- Convert immediately to `DiscoveryResult`/`DiscoveredJob` and preserve `raw`.
- Add captured-response contract fixtures for each enabled ATS.
- Configure timeout, retries, concurrency, and request rate per source.
- Distinguish successful zero results, incomplete results, and connector failure.
- Keep live tests opt-in and low-volume.
- Enable one source/company cohort at a time and observe before expanding.

Exit gate:

- At least one real Greenhouse or Lever job travels through the complete pipeline into
  PostgreSQL with correct raw data, provenance, Job, and JobOccurrence.
- Default tests still pass offline.
- Source failure is visible and does not corrupt or erase prior data.
- External package types cannot be imported outside the adapter.

## Phase 5 - Matching

Primary risks: missing data treated as failure, arbitrary weights appearing objective,
and explanations disagreeing with calculations.

Required prevention:

- Evaluate hard filters separately from scores.
- Treat missing data neutrally.
- Produce component scores and explanations from the same evaluated facts.
- Keep weights configurable per SavedSearch.
- Add boundary, monotonicity, weight, and missing-data tests.
- Do not add runtime LLM scoring.

Exit gate:

- Scores are deterministic and bounded.
- Improving one criterion cannot reduce its component score.
- Explanations reproduce the actual components and provenance used.
- Hard-filter failures are explicit and never hidden inside a low score.

## Phase 6 - Duplicate candidates

Primary risk: false-positive merging or loss of source provenance.

Required prevention:

- Keep exact occurrence identity separate from fuzzy Job similarity.
- Generate conservative candidate sets before expensive comparisons.
- Store reasons/signals and keep suspected Jobs separate.
- Test same-title/different-company, same-company/different-role, reposts, multi-location
  roles, and near-identical descriptions.
- Measure false positives on a labeled fixture set before exposing suggestions.

Exit gate:

- Fuzzy matches only create reviewable candidates/groups.
- No fuzzy path deletes, merges, or silently hides a Job or occurrence.
- Exact identity and `identity_conflicts` behavior remains unchanged.

## Phase 7 - JobSpy provider

Primary risks: blocking/CAPTCHAs, frequent site changes, legal/compliance concerns, and
one source aborting a multi-source call.

Entry checks:

- Re-check dependency activity, license, supported sites, known breakage, and current
  platform terms. Record engineering/compliance risk; do not present it as legal advice.
- Obtain explicit approval for each source to enable.

Required prevention:

- Call JobSpy once per site behind an independent timeout/exception boundary.
- Preserve completed sources if another source fails.
- Use conservative, per-source rate/concurrency settings and query caching.
- Never build CAPTCHA bypassing or aggressive evasion.
- Keep per-source kill switches and provider-health records.
- Treat zero results as success only when the source call actually completed.

Exit gate:

- A test where one source succeeds, one fails, and one returns incomplete results stores
  all successful jobs and records each source outcome accurately.
- Live checks are opt-in; default tests remain offline and deterministic.
- Disabling JobSpy leaves ATS ingestion and the rest of the product functional.

## Phase 8 - API and minimal UI

Primary risks: API/domain leakage, inconsistent pagination/filtering, stale client state,
and user actions overwriting source fields.

Required prevention:

- API routes call services, never providers or ORM persistence directly.
- Use stable response schemas and explicit pagination/sort semantics.
- Test save/hide/apply/note operations against re-ingestion.
- Show provenance and unknown values honestly.
- Keep collection logic out of the frontend.

Exit gate:

- Browser -> API -> PostgreSQL returns ranked jobs and occurrence/source details.
- Save, hide, applied status, and notes survive source refreshes.
- API errors are sanitized and validation behavior is tested.

## Phase 9 - Scheduler

Primary risks: overlapping runs, retry storms, abandoned `running` records, and stale-job
cleanup after incomplete collection.

Required prevention:

- Reuse the same service path for manual and scheduled runs.
- Make ingestion idempotent before scheduling it.
- Prevent overlapping runs for the same SavedSearch with a database lock/constraint.
- Bound retries and backoff per source.
- Detect and close abandoned runs.
- Never mark jobs stale after a failed/incomplete source run.
- Test time behavior with a fake clock.

Exit gate:

- Manual/hourly/daily/weekly triggers create durable, non-overlapping CollectionRuns.
- Restart/recovery, timeout, retry, and incomplete-run behavior is tested.

## Phase 10 - User workspace

Primary risk: source refresh, deduplication, or deletion changing personal history.

Required prevention:

- Only user-job services write `UserJob` and notes.
- Test applied/saved/hidden/note state across source refresh and occurrence changes.
- Prefer inactivation over destructive deletion.
- Define state reconciliation before any future Job merge action.

Exit gate:

- Personal state remains stable under re-ingestion, source disappearance, and duplicate
  candidate creation.

## Phase 11 - Analytics

Primary risks: counting occurrences as jobs, mixing inferred and explicit fields, and
mistaking connector changes for market changes.

Required prevention:

- State whether each metric counts Jobs, JobOccurrences, companies, or postings over time.
- Query normalized data and include provenance/unknown handling.
- Exclude or segment incomplete provider runs.
- Validate representative aggregates against small hand-calculated datasets.

Exit gate:

- Every displayed metric has a documented denominator, time window, grouping unit, and
  missing-data policy.

## Phase 12 - Provider health

Primary risk: flagging real market movement as connector failure, or vice versa.

Required prevention:

- Use per-source attempt history, not run-level totals alone.
- Compare several signals: volume, failures, duration, retries, and rate limits.
- Require sufficient history before anomaly alerts.
- Surface warnings for review rather than automatically disabling or deleting data.

Exit gate:

- Synthetic volume-drop and connector-failure histories produce distinguishable results.

## Phase 13 - Contact intelligence

Primary risks: privacy, inaccurate contact claims, terms violations, and accidental
outbound communication.

Required prevention:

- Use public, approved sources only and record provenance.
- Label inferred/unavailable contact information honestly.
- Do not automate email, messaging, or applications.
- Minimize retained personal data and define deletion/retention rules.
- Perform a dedicated compliance/privacy review before enabling collection.

Exit gate:

- No contact is presented as confirmed without explicit source evidence.
- No outbound action exists in the runtime path.

## Phase 14 - Resumes and documents

Primary risks: sensitive-document exposure, unsafe file handling, and coupling database
records to local paths.

Required prevention:

- Validate type and size; generate safe storage names; reject traversal paths.
- Keep blobs behind a storage abstraction and store metadata/references in PostgreSQL.
- Never log document contents or applicant PII.
- Define access, retention, backup, and deletion behavior before hosting.

Exit gate:

- Upload/read/delete behavior is authorized, path-safe, tested, and portable between local
  and future object storage.

## Phase handoff template

Use this at the end of every slice:

```text
Phase/slice:
Outcome:
Files changed:
Migration revisions:
Commands run and exact results:
Risks exercised from PHASE_RISK_CHECKLIST.md:
Skipped/unavailable verification:
Deviations and ADR impact:
Known limitations:
Recommended next smallest slice:
STOP - awaiting approval.
```
