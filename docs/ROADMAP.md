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
`CollectionRunProviderAttempt`, `UserJob`, `JobNote` migrated and tested via factories
(the last two per ADR 0003/DATA_MODEL.md/ARCHITECTURE.md §13, already part of Phase 1's
scope; `job_notes`' own CRUD service, routes, and workspace behavior remain Phase 10
work — see that phase below). Both
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
- **Phase 1: complete (updated 2026-08-30).** `users` slice complete and verified: model
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
  migration `0011` (`down_revision = "0010"`), and database tests cover
  `job_occurrences`' three partial/functional unique indexes — two of which are ADR-0004's
  own NULL-tenant fix (proven both sequentially and under real concurrent inserts); the
  third is an independent fallback natural key (`source_job_id IS NULL`), unaffected by
  the NULL-tenant bug ADR 0004 addresses — canonical
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
  unrelated run (see `docs/DATA_MODEL.md`). The `collection_run_provider_attempts`
  slice is also complete and verified (Class H): model
  (`backend/app/db/models/collection_run_provider_attempt.py`), migration `0015`
  (`down_revision = "0014"`), and database tests cover the bidirectional
  `status`/`completed_at` lifecycle consistency matrix, the new `completed_at >=
  started_at` ordering `CHECK`, the canonical `provider`/`source` identifiers
  (generalized from `job_occurrences`/`raw_job_ingestions`), the closed `error_category`
  enum `CHECK` reused from `ProviderErrorCategory` (ARCHITECTURE.md §6.3), the
  trim/blank-to-`NULL` `error_message` treatment, independence of `incomplete_results`
  from `status` (no `CHECK` ties them), the `UNIQUE (collection_run_id, provider,
  source)` constraint (proven to allow one provider's two distinct sources to coexist
  under the same run — the exact Phase 2 fixture-proof shape from ARCHITECTURE.md §11),
  and `ON DELETE CASCADE` isolation from `collection_runs` against an unrelated run's
  own attempt row (see `docs/DATA_MODEL.md`). The `user_jobs` slice is also complete
  and verified (Class H): model (`backend/app/db/models/user_job.py`), migration
  `0016` (`down_revision = "0015"`), the first `services/` module
  (`backend/app/services/user_jobs.py::set_status()`, per ADR 0006 — the only function
  permitted to write `status`/`applied_at`/`status_changed_at` together), and database
  tests cover the nine-value `status` enum, the bidirectional `status`/`applied_at`
  consistency `CHECK` across all nine values (both directions, ORM + direct SQL),
  `UNIQUE (user_id, job_id)`, independent `ON DELETE CASCADE` isolation from both
  `users` and `jobs` against an unrelated row, the three independent boolean flags,
  and `status_changed_at` as a distinct business timestamp that `updated_at` never
  substitutes for. Service-layer tests cover `set_status()`'s first-transition/
  preservation/backwards-clearing/no-op behavior, its flush-not-commit contract, its
  `ValueError` rejection of an invalid status or a naive timestamp without partial
  mutation, and that the database `CHECK` still rejects a status/`applied_at` pair
  written by directly bypassing `set_status()` (see `docs/DATA_MODEL.md`). The
  `job_notes` slice is also complete and verified (Class H) — Phase 1's **final**
  schema table: model (`backend/app/db/models/job_note.py`), migration `0017`
  (`down_revision = "0016"`), and database tests cover the required, trim-only,
  non-empty `body` `CHECK`, `ON DELETE CASCADE` isolation proven through three
  distinct deletion paths (`User`, `Job`, and `UserJob` directly — the same two-
  level-cascade shape already used by `saved_search_titles`/`saved_search_locations`
  and `candidate_skills`, now reachable through `user_jobs`' two parent FKs from
  either `users` or `jobs`), and multiple notes per `user_job_id` being accepted (no
  `UNIQUE` constraint). No new
  `services/` code was added — ARCHITECTURE.md §13 names no Phase 1 service function
  for this table, unlike `user_jobs`' `set_status()`; this table's Phase 1 consumers
  are its own factory and the database tests themselves, with Phase 10 remaining its
  first production CRUD writer (see `docs/DATA_MODEL.md`). All fifteen Phase 1
  domain tables (ADR 0003) are migrated, and Phase 1's own closure slice
  (`phase-1/closure`, merge commit `bfdd56d`) is merged into `main`. Phase 2 was
  subsequently authorized and is in progress (below) —
  under [PHASE_RISK_CHECKLIST.md](PHASE_RISK_CHECKLIST.md)'s own phase-gating rule
  ("confirm the previous phase's exit gate is complete" before starting the next
  phase), that would not have been authorized had Phase 1's exit gate not already
  been satisfied.
- **Phase 2: in progress (updated 2026-09-01).** Several bounded, Class H vertical
  slices are merged into `main`; Git history and
  [docs/LLM_HANDOFF.md](LLM_HANDOFF.md) remain authoritative for the exact, current
  list rather than a fixed count restated here (a count would go stale as soon as the
  next slice merges). Merged capabilities include the **natural-key ingestion spine**
  (offline, fixture-driven, no live provider) — `DiscoveredJob`/`DiscoveryResult`/
  `ProviderError`/`SourceRunStats` schemas, `DiscoveryProvider` protocol,
  `FixtureProvider`, `ingestion/clock.py`, `ingestion/hashing.py::canonical_json_hash()`,
  `ingestion/natural_key.py`'s versioned/domain-tagged/SHA-256 advisory-lock encoding,
  `ingestion/identity.py::resolve_identity()`, and `ingestion/pipeline.py::run()`'s
  per-`CollectionRun` orchestration (Transaction A_i/B_i/C_i pattern, durable run-init,
  per-source counter rollups, sanitized failure telemetry) — proves Fixture →
  `RawJobIngestion` → identity resolution → `Job` → `JobOccurrence` end-to-end across
  all three natural-key domains plus the genuinely unkeyable (`parse_error`) case;
  **Tier-1 `evidence_mismatch` conflict persistence**
  ([DECISIONS/0007](DECISIONS/0007-identity-conflict-quarantine.md)) —
  `ingestion/persistence.py::persist_posting()` replaces the spine's original
  fail-closed `DeferredIdentityConflictError` placeholder with real quarantine: a
  canonical-URL evidence mismatch on an existing natural key now updates observational
  fields only, inserts one `identity_conflicts` row per distinct new `RawJobIngestion`,
  and reroutes that raw row to `processing_status='identity_conflict'`, all validated
  against a `SELECT ... FOR UPDATE`-locked `raw_id` and a re-resolved `natural_key`
  before any mutation; and **Tier-2/3 cross-occurrence attachment**
  ([DECISIONS/0004](DECISIONS/0004-scoped-deterministic-identity.md)'s "Phase 2
  implementation notes"): `upsert_job_occurrence()` attempts normalized-canonical-URL
  matching (Tier 2, only when a usable canonical URL exists) or tenant-scoped
  requisition matching (Tier 3, only when no usable canonical URL exists — the two are
  mutually exclusive per posting, never a sequential fallback), attaching a new
  `JobOccurrence` to an existing `Job` (a new `UpsertKind.ATTACHED` outcome, counted as
  `jobs_updated`) rather than creating a duplicate; a candidate that disappears or
  changes between discovery and its `FOR UPDATE` lock raises
  `CandidateResolutionUnstableError`, never a retry.
  **Ambiguous-match conflict persistence**
  ([DECISIONS/0004](DECISIONS/0004-scoped-deterministic-identity.md),
  [DECISIONS/0007](DECISIONS/0007-identity-conflict-quarantine.md)) — Tier 2/3 finding
  more than one distinct candidate Job now creates a standalone Job/JobOccurrence and
  records the complete, sorted candidate set as an `identity_conflicts` row
  (`ambiguous_match`) instead of failing the whole run; a new `UpsertKind.AMBIGUOUS`
  outcome counts as `jobs_inserted`, and `pipeline.py`'s counter dispatch is now
  exhaustive over all five `UpsertKind` values, fail-closed for any future unrecognized
  one.
  Multi-source partial-success handling
  ([ARCHITECTURE.md §6.3](ARCHITECTURE.md#63-discoveryresult--what-a-provider-call-actually-returns-rev-2-revised-rev-3)/
  [§9](ARCHITECTURE.md#9-raw-ingestion-vs-provider-attempt-telemetry)/
  [§11](ARCHITECTURE.md#11-fixture-driven-end-to-end-ingestion-proof-phase-2-target))
  addresses `PHASE_RISK_CHECKLIST.md`'s exit-gate item for successful partial results: a
  source-level failure or partial result no longer aborts the whole run.
  `ingestion/pipeline.py::run()` first validates `DiscoveryResult`'s own internal
  consistency before writing any raw row (declared `jobs_found` against actual
  `DiscoveredJob` counts per source; `completed=False` can carry neither actual jobs nor
  `incomplete_results=True` — each a whole-run `UnsupportedDiscoveryResultError`, never a
  graceful per-source outcome), then persists every other source's jobs normally while
  each source's own `collection_run_provider_attempts` row records its independent
  outcome (`status` precedence `failed`/`partial`/`completed`; `error_category`/
  `error_message` from that source's chronologically latest `ProviderError`; `retry_count`;
  `rate_limited`; `incomplete_results`) — every `ProviderError` is still retained
  individually in `collection_runs.failures`, never collapsed to the one selected per
  source.
  `QueryPlanner` ([ARCHITECTURE.md §6.5–6.6](ARCHITECTURE.md#66-queryplanner-behavior-rev-4)) —
  `discovery/query_planner.py::QueryPlanner.plan()` is a stateless, I/O-free
  `@staticmethod` translating one `SavedSearch` plus one provider's
  `ProviderCapabilities` into a `SourceQuery | None`: absent source preference expands to
  every advertised source (sorted); an explicit empty selection or a capabilities object
  advertising zero sources returns `None`; an unknown requested source name always raises
  before any query is built, never silently dropped; `enabled_sources`' own shape is
  validated at runtime (list of strings, no duplicates) since its `CHECK` alone doesn't
  guarantee that; provider/source identifiers are validated against the same canonical
  slug grammar every other `provider`/`source` column in this schema already enforces;
  every current `SourceQuery` filter field is mapped from `SavedSearch` explicitly, with
  every unrepresentable field named rather than silently dropped; `local_enforcement` is
  computed per source from dedicated capability booleans (4 fields) plus
  `supported_query_fields` (the rest), never contradicting each other by construction.
  Proven by a fixture-driven integration test feeding its real output into the existing,
  unmodified `ingestion/pipeline.py::run()`; also now called by the multi-provider
  orchestrator below.
  `ProviderRegistry` ([ARCHITECTURE.md §6.4](ARCHITECTURE.md#64-discoveryprovider-protocol-sourcecapabilities-providercapabilities-providerhealth)) —
  `app/providers/registry.py::ProviderRegistry` is a pure in-memory, fail-closed
  name→instance directory: construction rejects an invalid canonical provider slug, a
  duplicate name, a `capabilities()` exception (converted to a sanitized
  `ProviderRegistrationError`), or a `capabilities().provider`/`.name` mismatch; a
  registered provider's `ProviderCapabilities` is captured as a read-isolated deep-copy
  snapshot, never re-fetched from `capabilities()` after registration; `get()` re-checks
  the provider's current `.name` against its registered name on every resolution (a
  provider is never assumed immutable) and raises a sanitized `UnknownProviderError` for
  an unregistered name; `names()` returns every registered name, alphabetically sorted.
  The canonical lowercase-ASCII-slug grammar is shared with `QueryPlanner` via
  `app/schemas/identifiers.py::is_canonical_slug()`, replacing two independent copies of
  the same regex. Now consulted by the multi-provider orchestrator below; composing the
  one real production registry instance (which live provider adapters to register) remains
  deferred until a live provider adapter exists (Phase 4+).
  Multi-provider orchestration ([ARCHITECTURE.md §6.8](ARCHITECTURE.md#68-multi-provider-orchestration-run_saved_search)) —
  `app/ingestion/orchestrator.py::run_saved_search()` creates exactly one `CollectionRun`
  spanning every provider selected for one saved search, sequentially: loads the
  authoritative `SavedSearch` (locked `FOR SHARE` for the duration of a single
  initialization transaction, so a concurrent delete can't race the `CollectionRun`'s FK)
  plus its title/location rows (`ORDER BY created_at, id` — deterministic, not insertion
  order); validates `enabled_providers` (canonical slugs, no duplicates) before any write;
  plans each provider via `QueryPlanner`, durably recording an unknown-provider or
  planning-validation failure (`source: null`) as a sibling-continuing outcome the instant
  it occurs; creates attempt rows lazily, atomically with `providers_attempted`/
  `providers_enforced_locally`, immediately before each provider's `discover()` call —
  never pre-created, never left behind for an unreached provider. Every other failure
  (registry name drift, an unexpected provider exception, a malformed `DiscoveryResult`, a
  persistence/database exception, or cancellation) aborts the entire run; `CollectionRun`'s
  rollup counters are then recomputed from a fresh `SUM` over its own attempt rows and
  written as an absolute value — never a parallel in-memory running total — so they can
  never disagree with the attempt rows or double-count. `pipeline.py::run()` is unchanged
  (zero behavior/signature change; its logic is now shared via a new
  `app/ingestion/provider_execution.py` module, not duplicated).
  Still deferred: Tier 4 (blocked on a company-text-to-`company_id` resolution capability
  that does not exist yet, not merely unimplemented), `ProviderRegistry` production
  composition, live providers.
  A read-only Phase 2 exit-gate audit (2026-09-05, from clean `main@4db557c`) cross-checked
  every documented Phase 2 requirement against the actually-merged code, tests, and
  migrations. It found no unsatisfied requirement and no blocking gap; it found exactly two
  bounded documentation/test-coverage discrepancies: ARCHITECTURE.md §11 cited an
  unimplemented Tier 4 path as the required `ambiguous_match` fixture case (the conflict
  type is actually proven through Tiers 2/3), and two of §11's required fixture-driven
  pipeline cases (same-`source_job_id`-different-tenants; NULL-tenant natural-key collision)
  were previously proven only at the Phase 1 database-constraint level, not through the
  Phase 2 fixture-driven `pipeline.run()` path §11 specifies. The `phase-2/closure` branch
  corrects both — the §11 wording, and two new fixture-driven tests
  (`test_two_distinct_tenants_sharing_source_job_id_produce_two_jobs`,
  `test_null_tenant_natural_key_collision_resolves_to_one_occurrence`) in
  `tests/test_ingestion_pipeline.py`. This closure was reviewed and approved by Codex,
  merged into `main` at `d4bd606` (merge record committed at `199eb00`), and **Phase 2
  is officially complete.**
- **Phase 3: first slice (remote/hybrid/onsite classifier) merged into `main` at
  `1bc8247` (approval commit `fecbcec`, merge record in
  [LLM_HANDOFF.md](LLM_HANDOFF.md)) — not a Phase 3 completion claim.**
  `app/normalization/remote.py`'s deterministic remote/hybrid/onsite classifier and
  the shared `app/normalization/types.py` (`NormalizationResult[T]`/`Provenance`) are
  tested against a fixture-driven regression corpus, with an automated import-boundary
  proof (no database/ORM/provider/network dependency). Not wired into
  ingestion/persistence, no `parser_version` threading.
  A second slice (full_time/part_time/seasonal/internship classifier) merged into
  `main` at `8e136c0` (approval commit `67cf09b`, merge record in
  [LLM_HANDOFF.md](LLM_HANDOFF.md)). `app/normalization/employment.py` deliberately
  covers only the `jobs.employment_type` schedule/commitment axis; `jobs.contract_type`
  (deferred to its own future slice) and `jobs.shift` (no parser currently planned) are
  untouched.
  A third slice (entry_level/mid_level/senior/staff/principal/director classifier)
  merged into `main` at `92fcefc` (approval commit `0c92b7d`, merge record in
  [LLM_HANDOFF.md](LLM_HANDOFF.md)). `app/normalization/seniority.py` is code-defined
  and bounded — no `taxonomy/` directory or YAML file created; `docs/ARCHITECTURE.md`'s
  `seniority.yaml` entry is annotated as planned future enrichment, not implemented by
  this slice.
  A fourth slice (years-of-experience range classifier, Workflow v3.1 pilot parser
  slice 1 of 3) merged into `main` at `6f9ae53` (approval recorded in commit `d46f20f`,
  merge record in [LLM_HANDOFF.md](LLM_HANDOFF.md)). `app/normalization/experience.py`
  produces an `ExperienceRange` (independently-provenanced `minimum`/`maximum`), the
  first parser needing `types.py`'s deferred composite-result-type case. Not wired into
  ingestion/persistence, no `parser_version` threading, no `jobs.years_experience_min`/
  `max` write of any kind — those remain Phase 4+ concerns. This slice needed five
  correction rounds against the pilot's one-round target — a pilot-tracking fact, not a
  reopened finding.
  A fifth slice (base-pay classifier, Workflow v3.1 pilot parser slice 2 of 3) merged
  into `main` at `5b144a2` (approval recorded in commit `396c939`, merge record in
  [LLM_HANDOFF.md](LLM_HANDOFF.md)). `app/normalization/salary.py` reads
  `compensation_text` only (no `title`/`description`) and produces a `SalaryResult` —
  four independently-provenanced fields (`minimum`/`maximum`/`currency`/`period`), the
  case `types.py`'s own docstring anticipated. A finite, whole-field lexical/semantic
  grammar (five productions; no substring fallback) rather than `experience.py`'s
  segment-scanning design. Not wired into ingestion/persistence, no `parser_version`
  threading, no `jobs.salary_min/max/currency/period` write of any kind, no
  annualization, no FX conversion, no `compensation_explicit` classification — all
  Phase 4+ or explicitly out-of-scope concerns. This slice needed one bounded correction
  round (grammar-boundary strictness), within the pilot's one-round target.
  A sixth slice (location-geography classifier, Workflow v3.1 pilot parser slice 3 of 3)
  **merged into `main` at `a32b5cc` (approval recorded in commit `c1a5235`, merge record
  in [LLM_HANDOFF.md](LLM_HANDOFF.md)).** `app/normalization/location.py` reads
  `location` only and produces a `LocationResult` — four independently-provenanced
  fields (`city`/`state`/`country`/`postal_code`). **`city` is deliberately never
  populated in this slice** (unconditionally `unavailable`) — a denylist-based approach
  was rejected during proposal review as unable to establish a positive correctness
  guarantee without a real gazetteer; `state`/`country`/`postal_code` remain
  independently extractable via closed catalogs and a strict ZIP pattern. Includes a
  frozen, independently-derived and live-source-confirmed 26-code collision set (a USPS
  state abbreviation that is also a current ISO 3166-1 alpha-2 country code) requiring a
  US-only anchor (ZIP or explicit US country) to disambiguate. Not wired into
  ingestion/persistence, no `parser_version` threading, no
  `jobs.city/state/country/postal_code` write of any kind, no lat/long geocoding, no
  external lookups, no taxonomy — all Phase 4+ or explicitly out-of-scope concerns.
  All six Phase 3 classifier parsers (remote, employment, seniority, experience, salary,
  location) are now merged into `main` — this is still not a Phase 3 completion claim.
  Title parser has not been started.
  A seventh slice, the **skill-taxonomy foundation** (Class H; risk classified high
  because ambiguous-alias false matches are Phase 3's own named primary risk, and this
  is novel infrastructure two future parsers depend on, not a "repeated established
  pattern"), is **merged into `main` at `1876f7e2168d90e36a1fb46f039cd5969fe49d6c`.**
  `app/taxonomy/skills.yaml` (a versioned, schema-closed, duplicate-key-rejecting YAML
  file) and `app/normalization/taxonomy.py` (the loader, canonical-ID grammar reusing
  `app/schemas/identifiers.py::is_canonical_slug()`, and an exact-match-only lookup
  returning a typed `TaxonomyLookupResult`, never a bare `None`) together resolve a raw
  skill string to a canonical entry. Deliberately does not scan free text and does not
  implement a skill classifier — that slice unblocked a future `classify_skill`-style
  parser only. Title normalization is **not** unblocked: job titles are free-form
  multi-word phrases needing their own, likely hierarchical taxonomy schema, entirely
  unstarted. Seeded with 15 explicitly reviewed, non-exhaustive entries (see the slice's
  own proposal record for the frozen table and each alias's rationale).
  An eighth slice, the **skill classifier** (Class H, same primary-risk reasoning as the
  taxonomy foundation above), consumes that taxonomy: `app/normalization/skills.py`'s
  `classify_skills(title, description, *, taxonomy)` returns a deduplicated,
  canonical-ID-ascending-sorted `list[SkillMatch]` — never a single value, since a
  posting can name several distinct skills. Exact-match taxonomy lookup only, no
  free-text scanning inside the taxonomy itself; this module supplies its own
  segmentation. The ambiguous aliases `c`/`r`/`go`/`node` (which collide with ordinary
  English words) require additional structural evidence — a standalone list position,
  a narrow title-only role-noun adjacency for `c`/`r`/`go`, or (in `description`) an
  explicit, closed skill-list anchor (`skills:`, `languages:`, `technologies:`,
  `tech stack:`) plus a bounded list region — never punctuation structure alone.
  **Merged into `main` at `dad967789227feb65cf776a0675a8fe179873afa`.**
  An ongoing correction lineage on this slice (`C2`/`A2`, `C3`/`A3`) fixed the
  description anchor's region-ending boundary to fail closed on Unicode whitespace and
  then on Unicode format characters (categories `Cf`) — both are recorded in this
  slice's own `docs/LLM_HANDOFF.md` history, not restated here.
  A ninth slice, the **realistic Phase 3 evaluation corpus** (Class H — acquisition,
  sanitization, annotation, and a minimal evaluator under one authorization), addresses
  the exit-gate item every one of the seven merged classifiers' own test suites
  disclosed as unmet: no realistic captured-payload regression corpus exists yet.
  `backend/scripts/fetch_greenhouse_evaluation_postings.py` performs a bounded,
  two-phase, GET-only fetch against a closed, user-named set of public Greenhouse
  boards; `backend/scripts/evaluate_phase3_corpus.py` is a fail-closed loader plus a
  minimal, threshold-free evaluator. Implemented on
  `phase-3/realistic-evaluation-corpus` — **candidate/publication stage, not yet
  reviewed, not merged.** The live network contact and its resulting real corpus are
  gated on separate, explicit board-token authorization — see this slice's own
  `docs/LLM_HANDOFF.md` entry and `docs/DECISIONS/0010-realistic-evaluation-corpus-
  methodology.md` for exactly what is and is not yet populated.
- **Phase 4: two bounded read-only prework proofs merged into `main`; the production
  `AtsScrapersProvider` adapter is not started and Phase 4 is not complete.** The
  Greenhouse live ATS canary (`phase-4/greenhouse-canary`, merged at `64a3534`) and the
  Greenhouse live-to-disposable-database ingestion proof (`phase-4/greenhouse-live-proof`,
  merged at `907b3f0`) both exist; neither is the production `DiscoveryProvider`-wrapping
  `AtsScrapersProvider` adapter described in this section's own header, which remains
  unstarted.
- **Phases 5-14: not started.** Begin each phase only after completing its preflight in
  [PHASE_RISK_CHECKLIST.md](PHASE_RISK_CHECKLIST.md) and receiving approval for the next
  smallest slice.
