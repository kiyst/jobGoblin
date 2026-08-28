# Roadmap

Before beginning or approving any phase, complete its entry checks and exit gate in
[PHASE_RISK_CHECKLIST.md](PHASE_RISK_CHECKLIST.md).

Phases as scoped in the master spec (§51), carried through unchanged except where
[ARCHITECTURE.md §1](ARCHITECTURE.md#1-critical-review-of-the-spec) trimmed scope. Each
phase should ship as its own reviewable change; do not start a phase before the previous
one's acceptance criteria pass. See [ARCHITECTURE.md §12–13](ARCHITECTURE.md#12-phase-0-acceptance-criteria)
for the detailed Phase 0/1 criteria — this file gives the one-paragraph version for every
phase so the whole sequence is visible at a glance.

## MVP definition

The MVP (§50) is complete when a Saved Search can run against a real ATS provider and a
real broad-board provider, produce ranked, deduplicated, explainable results queryable
through the API, with save/hide/applied state and notes working and never clobbered by
re-ingestion — without any LLM in the runtime path. A polished frontend is not required
to claim the MVP.

## Phase 0 — Repository Foundation
FastAPI + PostgreSQL + SQLAlchemy + Alembic + Pydantic + pytest + Docker Compose
scaffolding, env config, `/health` endpoint. Docs (this set) exist. No domain logic yet.

## Phase 1 — Domain Model
`CandidateProfile`, `SavedSearch` (+ titles/locations, + `enabled_sources`), `Company`,
`Job`, `JobOccurrence`, `RawJobIngestion`, `IdentityConflict`, `CollectionRun`,
`CollectionRunProviderAttempt`, `UserJob` migrated and tested via factories. Both
`IdentityConflict` and `CollectionRunProviderAttempt` are migrated here (not later)
because Phase 2's fixture proof needs both tables to exist — to write
`evidence_mismatch`/`ambiguous_match` rows and per-source partial-failure/attempt rows
respectively — even though neither is written to until then. See
[DECISIONS/0003](DECISIONS/0003-minimal-phase1-schema.md),
[DECISIONS/0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md), and
[DECISIONS/0007](DECISIONS/0007-identity-conflict-quarantine.md). No providers, no
normalization — proves persistence only.

## Phase 2 — Provider Interface
`DiscoveryProvider`, `ProviderRegistry`, `SourceCapabilities`/`ProviderCapabilities`
(per-source, not provider-wide — [ARCHITECTURE.md §6.4](ARCHITECTURE.md#64-discoveryprovider-protocol-sourcecapabilities-providercapabilities-providerhealth)),
`ProviderHealth`, `DiscoveredJob`, `DiscoveryResult`, `QueryPlanner` (validation/expansion
rules in [ARCHITECTURE.md §6.6](ARCHITECTURE.md#66-queryplanner-behavior-rev-4)),
`ingestion/identity.py`'s scoped deterministic resolution
([DECISIONS/0004](DECISIONS/0004-scoped-deterministic-identity.md)), its
`evidence_mismatch`/`ambiguous_match` conflict quarantine
([DECISIONS/0007](DECISIONS/0007-identity-conflict-quarantine.md)), plus
`FixtureProvider`. Proves Fixture → RawJobIngestion → identity resolution → Job →
JobOccurrence end-to-end with zero network calls, including NULL-tenant/cross-tenant
natural-key cases, both conflict-quarantine cases, `QueryPlanner` source-validation
cases (unknown source, empty selection, no-preference expansion, differing per-source
filter support), and a partial-provider-failure case — this phase is also the **first
writer** of `CollectionRunProviderAttempt` (migrated in Phase 1), persisting one
successful and one failed attempt row per the partial-failure fixture (design in
[ARCHITECTURE.md §11](ARCHITECTURE.md#11-fixture-driven-end-to-end-ingestion-proof-phase-2-target)).

## Phase 3 — Normalization
Title, skill (taxonomy-backed), salary, experience, seniority, employment, remote, and
location parsers, each pure-function-tested against fixture strings, no database or
network dependency.

## Phase 4 — ats-scrapers Provider
`AtsScrapersProvider` wraps the `ats-scrapers` dependency behind `DiscoveryProvider`.
External types never leak past the adapter; raw payload preserved; failures degrade to
`ProviderHealth(healthy=False)` without affecting other providers.

## Phase 5 — Matching
Deterministic weighted scoring (`matching/scorer.py`, `weights.py`) producing
`MatchResult` with per-component scores and explanations. Hard filters evaluated
separately from scoring; missing data scores neutral, never zero/reject.

## Phase 6 — Deduplication
`dedupe/similarity.py` and `grouping.py` for the probabilistic `duplicate_groups` tier
([DECISIONS/0002](DECISIONS/0002-two-tier-duplicate-detection.md)). (Deterministic
identity resolution itself — `ingestion/identity.py` — is a Phase 2 concern, exercised
by the fixture provider before any real source exists; see
[DECISIONS/0004](DECISIONS/0004-scoped-deterministic-identity.md).) No automatic merging
of `Job` rows from fuzzy signals. `duplicate_groups` is reserved exclusively for this
phase's fuzzy/probabilistic matching — Phase 2's deterministic identity conflicts use a
separate table, `identity_conflicts` (migrated in Phase 1, first written to in Phase 2;
see [DECISIONS/0007](DECISIONS/0007-identity-conflict-quarantine.md)), not this one.

## Phase 7 — JobSpy Provider
`JobSpyProvider` wraps `python-jobspy`, isolated per §9. Per-query TTL caching,
source-specific failure isolation, no DataFrame/JobSpy model leakage past the adapter.

## Phase 8 — API / Minimal UI
Job feed (title, company, location, salary, age, score + breakdown, source indicators,
save/hide/apply actions) via the `api/` routers and a minimal Next.js frontend. No visual
polish required yet.

## Phase 9 — Scheduler
`workers/scheduler.py`: Run Now / hourly / daily / weekly execution, `CollectionRun`
tracking, provider-failure isolation, retry/backoff per `ProviderCapabilities`. **Reuses**
the `collection_run_provider_attempts` table — migrated in Phase 1 and first written to
by Phase 2's fixture pipeline, not introduced here (see
[DECISIONS/0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md) and this
document's own Phase 1/2 entries above) — extending how it's populated to cover real
scheduled runs.

## Phase 10 — User Workspace
Saved/applied views, notes, statuses, applied date, days-since-applied — all reading and
writing only `user_jobs`/`job_notes`, never `jobs`/`job_occurrences`.

## Phase 11 — Analytics
Market-level analytics (§40) over normalized tables: compensation, skills, experience,
titles, location, employment-type, source-overlap, freshness distributions. No scraping
inside analytics code.

## Phase 12 — Provider Health
Historical volume tracking and anomaly detection (§41) to distinguish "market has fewer
jobs" from "our connector broke," reading per-`(provider, source)` trend lines from
`collection_run_provider_attempts` rather than run-level-only aggregates — see
[DECISIONS/0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md).

## Phase 13 — Contact Intelligence
Only after ingestion is reliable. Public-source recruiter/contact discovery, explicit
`inferred`/`unavailable` email-status labeling, no numeric confidence scores (§42).

## Phase 14 — Resumes / Documents
Only after job aggregation is proven. Local filesystem storage in dev, object-storage
abstraction for production; PostgreSQL stores metadata/references only, not blobs (§43).

---

## Status

- **Phase 0: complete and verified (2026-08-24).** The backend image builds; Compose
  PostgreSQL is healthy; Alembic upgrade -> downgrade -> upgrade passes; Ruff, mypy, and
  pytest pass; and live liveness/readiness behavior has been verified with the database
  both available and unavailable.
- **Phase 1: in progress (2026-08-24).** `users` slice complete and verified: model
  (`backend/app/db/models/user.py`), migrations `0002` (table, reviewed/hand-edited, not
  autogenerate-as-is) and `0003` (forward corrective migration, reversible, fixing the
  email-normalization `CHECK` constraints' whitespace handling — see
  `docs/DATA_MODEL.md`), and database tests against real Compose PostgreSQL all pass —
  including the normalized-email `CHECK`s/unique index, required-field rejection, and
  `updated_at` advancing on update. `candidate_profiles` slice also complete and
  verified: model (`backend/app/db/models/candidate_profile.py`), migration `0004`
  (`down_revision = "0003"`), and database tests all pass — including the one-profile-
  per-user uniqueness, `ON DELETE CASCADE` from `users`, the `remote_preference` enum
  `CHECK`, non-negative `CHECK`s on `years_experience`/`salary_expectation_min`/
  `salary_expectation_max`, the `salary_expectation_min <= salary_expectation_max`
  `CHECK`, and the NULL-means-unspecified/empty-array-means-explicitly-none distinction
  on the `text[]` columns (see `docs/DATA_MODEL.md`). `candidate_skills` slice also
  complete and verified: model (`backend/app/db/models/candidate_skill.py`), migration
  `0005` (`down_revision = "0004"`), and database tests all pass — including the
  same-whitespace-set trim/non-empty `CHECK`s and case-preserving normalization used for
  `users.email`, the case-insensitive `(candidate_profile_id, lower(skill))` unique index,
  `ON DELETE CASCADE` from `candidate_profiles`, and the `priority` enum `CHECK` (see
  `docs/DATA_MODEL.md`). `saved_searches` slice also complete and verified (parent table
  only — `saved_search_titles`/`saved_search_locations` remain future slices): model
  (`backend/app/db/models/saved_search.py`), migration `0006` (`down_revision = "0005"`),
  and database tests all pass — including the `name` trim/non-empty `CHECK`s,
  `remote_rules`/`polling_schedule` enum `CHECK`s, non-negative `CHECK`s on
  `radius_miles`/`salary_floor`/`preferred_salary`/`recency_limit_hours` (`radius_miles`
  has no precision/scale, but is still non-negative), the
  `salary_floor <= preferred_salary` `CHECK`, `ON DELETE CASCADE` from `users`, and — the
  first `jsonb` columns in this schema — `MutableDict`-tracked top-level mutation with a
  documented (and tested) nested-mutation limitation, plus a top-level-JSON-object `CHECK`
  on `enabled_sources`/`scoring_weights` (see `docs/DATA_MODEL.md`). `saved_search_titles`
  slice also complete and verified (`saved_search_locations` remains a future slice):
  model (`backend/app/db/models/saved_search_title.py`), migration `0007`
  (`down_revision = "0006"`), and database tests all pass — including the `title`
  trim/non-empty `CHECK`s and case-preserving normalization (mirroring `skill`/`name`),
  the case-insensitive `(saved_search_id, lower(title))` unique index, the partial
  `UNIQUE (saved_search_id) WHERE is_primary` index enforcing at most one primary title
  per search while allowing zero, and `ON DELETE CASCADE` from `saved_searches` (see
  `docs/DATA_MODEL.md`). `saved_search_locations` slice also complete and verified (the
  final child table of the `saved_searches` group): model
  (`backend/app/db/models/saved_search_location.py`), migration `0008`
  (`down_revision = "0007"`), and database tests all pass — including the `location_text`
  trim/non-empty `CHECK`s and case-preserving normalization (mirroring `title`), the
  case-insensitive `(saved_search_id, lower(location_text))` unique index, `CHECK`s
  restricting latitude to `[-90, 90]` and longitude to `[-180, 180]`, a coordinate-pair
  `CHECK` requiring both be NULL or both be non-NULL, a non-negative `CHECK` on
  `radius_miles_override`, and `ON DELETE CASCADE` from `saved_searches` (see
  `docs/DATA_MODEL.md`). `companies` slice also complete and verified (Class H — the
  first table with a self-referential FK, `ON DELETE SET NULL`, and a PostgreSQL
  generated column): model (`backend/app/db/models/company.py`), domain normalization
  (`backend/app/normalization/company.py::normalize_domain()`, IDNA2008/UTS #46 via the
  `idna` package), migration `0009` (`down_revision = "0008"`), and database tests all
  pass — including the case-insensitive, NULL-safe partial `UNIQUE (lower(domain))`
  index (multiple `NULL`-domain companies coexist; a real concurrent-insert race
  correctly leaves exactly one winner), the `normalized_name` PostgreSQL `GENERATED
  ALWAYS AS (...) STORED` column (trim/collapse/lowercase of `name`, proven generated
  even via a direct SQL insert that never mentions it), the `duplicate_of_company_id`
  self-referential FK's `ON DELETE SET NULL` behavior and its direct-self-reference
  `CHECK`, and NULL-safe normalization `CHECK`s on `homepage_url`/`career_page_url`/
  `industry` (see `docs/DATA_MODEL.md`). The `jobs` slice is also complete and verified
  (Class H): model (`backend/app/db/models/job.py`), migration `0010` (`down_revision =
  "0009"`), and database tests cover its nullable `company_id` FK with `ON DELETE
  RESTRICT`, explicit ordered observation timestamps, resolved-value constraints,
  coordinate and numeric invariants, mutable certifications/provenance collections, and
  the absence of any job-level identity `UNIQUE` constraint (identity keys belong to the
  future `job_occurrences` slice; see `docs/DATA_MODEL.md`). The `job_occurrences` slice
  is also complete and verified (Class H): model
  (`backend/app/db/models/job_occurrence.py`), the new
  `backend/app/normalization/url.py::normalize_url()` pure identity canonicalizer,
  migration `0011` (`down_revision = "0010"`), and database tests cover the three
  ADR-0004 partial unique indexes (including the exact NULL-tenant loophole ADR 0004
  fixes, proven both sequentially and under real concurrent inserts), canonical
  `provider`/`source` identifiers, `ON DELETE CASCADE` isolation from `jobs`, and the
  explicit-observation-time invariants (see `docs/DATA_MODEL.md`). The
  `raw_job_ingestions` slice is also complete and verified (Class H): model
  (`backend/app/db/models/raw_job_ingestion.py`), migration `0012` (`down_revision =
  "0011"`), and database tests cover the canonical `provider`/`source` identifiers
  (generalized from `job_occurrences`), the top-level-JSON-object `raw_payload` `CHECK`,
  the `fetched`/`parse_error`-only-direction `processing_status`/`job_occurrence_id`
  consistency `CHECK` (deliberately one-directional so `ON DELETE SET NULL` can still
  preserve a `normalized`/`identity_conflict` row past its occurrence's deletion), and
  `ON DELETE SET NULL` isolation from `job_occurrences` (see `docs/DATA_MODEL.md`). The
  `identity_conflicts` slice is also complete and verified (Class H): model
  (`backend/app/db/models/identity_conflict.py`), migration `0013` (`down_revision =
  "0012"`), and database tests cover the plain `conflict_type`/`status` enums, the full
  `status`/`resolved_at` lifecycle consistency matrix plus the new `resolved_at >=
  created_at` ordering `CHECK`, the `conflict_type`-conditional JSON shape `CHECK` on
  `existing_value`/`incoming_value` (object for `evidence_mismatch`, array for
  `ambiguous_match`, including the empty-object/empty-array acceptance case), and both
  independent `ON DELETE SET NULL` cascades (from `job_occurrences` and from
  `raw_job_ingestions`) proven in isolation from each other and from an unrelated
  conflict row (see `docs/DATA_MODEL.md`). The `collection_runs` slice is also complete
  and verified (Class H): model (`backend/app/db/models/collection_run.py`), migration
  `0014` (`down_revision = "0013"`), and database tests cover the bidirectional
  `status`/`completed_at` lifecycle consistency matrix, the `completed_at >= started_at`
  ordering `CHECK`, the no-server-default `started_at`/`status` contract (raw-SQL
  omission proven rejected), independent per-row defaults for the three job counters,
  both JSONB columns, and the provider array, in-place `MutableList` append persistence
  after a separate-session reload for both `providers_attempted` and `failures`,
  whole-value-assignment persistence for `providers_enforced_locally`, the top-level
  JSON object/array shape `CHECK`s (SQL NULL, JSON null, and wrong-shape values all
  rejected), a planning-time failure existing without any `providers_attempted` entry,
  `completed_with_errors` retaining accurate non-zero rollups alongside recorded
  failures, and `ON DELETE SET NULL` isolation from `saved_searches` against an
  unrelated run (see `docs/DATA_MODEL.md`). No later Phase 1 table is implemented yet;
  the rest of Phase 1's exit gate (§[PHASE_RISK_CHECKLIST.md](PHASE_RISK_CHECKLIST.md))
  remains outstanding.
- **Phases 2-14: not started.** Begin each phase only after completing its preflight in
  [PHASE_RISK_CHECKLIST.md](PHASE_RISK_CHECKLIST.md) and receiving approval for the next
  smallest slice.
