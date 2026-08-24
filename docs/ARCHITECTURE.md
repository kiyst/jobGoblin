# Architecture

Status: Phase 0 design document. No application code exists yet. This document is the
output of the "first task" review requested for the job platform: a critical read of the
master spec, a confirmed repository structure, and definitions for the Phase 0/1
interfaces. See [ROADMAP.md](ROADMAP.md) for phase sequencing and
[DATA_MODEL.md](DATA_MODEL.md) for the full schema.

## Revision history

- **Rev 4** (this revision): a third design review. Moved `collection_run_provider_attempts`
  into **Phase 1** (migrated) with Phase 2 as its first writer — it was wrongly deferred to
  Phase 9 in Rev 3 even though Phase 2's fixture proof already needs to persist partial
  provider results and per-source failures (§9, §13; [ADR 0003](DECISIONS/0003-minimal-phase1-schema.md),
  [ADR 0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md)); gave the table its
  full constraint set (status-lifecycle `CHECK`s, non-negative counters, `UNIQUE
  (collection_run_id, provider, source)`) and documented it as one aggregate row per
  run/provider/source, not per individual request/retry. Replaced provider-wide
  `ProviderCapabilities.max_concurrency`/`requests_per_second`/`supported_query_fields`/
  filter-support booleans with a `SourceCapabilities` value per source, keyed in
  `ProviderCapabilities.sources: dict[str, SourceCapabilities]` (§6.4) — capacity and
  filter support are source-level facts, not provider-wide ones. Defined `QueryPlanner`'s
  validation and expansion behavior explicitly (§6.6): unknown sources fail before any
  provider call, an explicit empty source list means no execution, and an unspecified
  source preference expands to every configured source for that provider. Added
  `saved_searches.enabled_sources` (jsonb) to represent source-level selection
  unambiguously, supplementing (not replacing) `enabled_providers`. Simplified
  `SourceRunStats` (§6.3) by removing the redundant `requested` field (one entry per
  requested source is now a validated invariant, not a flag) and adding
  `incomplete_results` so a truncated-but-successful source isn't misrepresented as
  failed. Added `identity_conflicts` lifecycle `CHECK` constraints (§DATA_MODEL). Finished
  `companies.domain` normalization (IDNA/punycode, credentials/port stripping, explicit
  malformed-input rule). Updated: ADR 0003, ADR 0005.
- **Rev 3**: a second design review caught semantic/database issues Rev
  2's link-validation pass didn't cover. Fixed a real NULL-distinctness bug in the
  `job_occurrences` natural key (§8) — Rev 2's single partial unique index silently
  failed to enforce uniqueness for NULL-tenant sources (LinkedIn/Indeed), now split into
  two partial indexes; scoped the tenant-requisition match key to include
  `provider`/`source`, not just `source_tenant_id` (§8); replaced Rev 2's infeasible
  conflict-handling ("create a new Job" for a case where the natural key already exists,
  which would violate the very constraint being matched on) with a feasible
  quarantine workflow via a new `identity_conflicts` table, migrated in Phase 1
  (§8–9, [ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md)); kept
  `duplicate_groups` reserved exclusively for Phase 6's fuzzy tier, no longer overloaded
  with deterministic conflicts; finished separating per-posting processing status
  (`raw_job_ingestions.processing_status`, renamed from `retrieval_status`, narrowed to
  states that can actually apply to a payload that was fetched) from request-level
  telemetry (§9); added explicit `sources` selection to `SourceQuery` and wired it through
  cache fingerprints/telemetry/fixtures (§6.1); made `DiscoveryResult.source_stats`
  authoritative, deriving `requested_sources`/`completed_sources`/`possibly_incomplete`
  as properties instead of separately-settable fields that could disagree (§6.3);
  normalized `companies.domain` before uniqueness applies; added `job_notes.updated_at`;
  pinned a minimum supported PostgreSQL version (16, §2). New ADR:
  [0007](DECISIONS/0007-identity-conflict-quarantine.md). Updated: ADR 0002, ADR 0003,
  ADR 0004.
- **Rev 2**: corrections from a first design review. Deterministic identity no
  longer trusts bare requisition IDs as globally unique (§8); removed a circular FK
  between `job_occurrences` and `raw_job_ingestions` (see [DATA_MODEL.md](DATA_MODEL.md));
  `DiscoveryProvider.discover()` now returns a typed `DiscoveryResult` that carries partial
  failure instead of an all-or-nothing `list[DiscoveredJob]` (§6.3); the dependency
  "chain" is now documented as the graph it actually is, with an explicit allowed-import
  list per module (§5); added a project naming decision (§3); strengthened Phase 0/1
  acceptance criteria (§12–13); fixed a malformed Markdown link and a stray phase-number
  typo from Rev 1. New ADRs: [0004](DECISIONS/0004-scoped-deterministic-identity.md),
  [0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md),
  [0006](DECISIONS/0006-userjob-workflow-invariants.md).
- **Rev 1**: initial Phase 0 deliverable.

---

## 1. Critical review of the spec

The spec (as given) is internally consistent on its main thesis — deterministic pipeline,
modular monolith, provider adapters, Job vs. JobOccurrence — and that thesis is sound.
A few things needed resolving or trimming before they turn into ambiguous code later:

### 1.1 "Deduplication" was doing two different jobs

The spec describes two mechanisms that look like the same feature but are not:

- **§18** describes `JobOccurrence` as the mechanism for attaching *multiple sources of
  the same job* (Workday + LinkedIn + Indeed) to a single `Job` row.
- **§19** separately describes `duplicate_candidate` / `duplicate_group_id` fields for
  flagging probable duplicates.

These are two tiers of the same problem, resolved at different confidence levels — see
[DECISIONS/0002-two-tier-duplicate-detection.md](DECISIONS/0002-two-tier-duplicate-detection.md)
for the tier split, and [§8](#8-deterministic-identity-resolution) below /
[DECISIONS/0004](DECISIONS/0004-scoped-deterministic-identity.md) for how Tier 1
("deterministic") itself is scoped so it can't silently merge unrelated jobs.

### 1.2 Table list in §48 is a menu, not a requirement

The spec itself says "do not create unnecessary tables merely because this list exists."
Several tables depend on features that don't exist yet (`job_skills` depends on the skill
taxonomy from Phase 3; `duplicate_groups` depends on Phase 6; `contacts`/`contact_sources`
depend on Phase 13; `notifications` isn't specified anywhere beyond its name). Phase 1
implements the minimal subset needed to prove the fixture pipeline end-to-end; the rest
are added in the phase that actually needs them. See
[DECISIONS/0003-minimal-phase1-schema.md](DECISIONS/0003-minimal-phase1-schema.md).

### 1.3 `RawJobIngestion` ↔ `JobOccurrence` must not reference each other circularly

Rev 1 gave `job_occurrences` a `last_raw_ingestion_id` FK *and* gave
`raw_job_ingestions` a `job_occurrence_id` FK back — a circular reference between the two
tables. Rev 2 keeps only `raw_job_ingestions.job_occurrence_id`; "the latest ingestion for
an occurrence" is a derived query, not a stored pointer. Full detail:
[§9](#9-raw-ingestion-vs-provider-attempt-telemetry) and
[DECISIONS/0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md).

### 1.4 Single-user vs. multi-user

The spec says "initially one user" but "should not prevent later multi-user hosting."
Concretely: every user-scoped table (`candidate_profiles`, `saved_searches`, `user_jobs`,
`job_notes`) carries a `user_id` foreign key from day one, and a `users` table exists from
Phase 1, even though Phase 1 will only ever populate one row via a seed script (no auth
system yet). This costs nothing now and avoids a schema migration later to retrofit
`user_id` onto tables and backfill existing rows.

### 1.5 Confirmed: architecture-reference repos can still carry active risk

Repo research ([OPEN_SOURCE_REVIEW.md](OPEN_SOURCE_REVIEW.md)) found that
`Masterjx9/OpenPostings` — cited in the spec as an architecture reference for ATS-first
discovery — ships an MCP "apply-agent" server that hands an LLM applicant PII (including
EEO/demographic fields) with instructions to auto-fill and submit applications, gated
only by an approval flag. This is precisely the automated-application behavior §1/§42
rule out. It doesn't change the plan (that repo was never going to be a dependency, only
a pattern source, and the freshness/ATS-detection patterns worth studying are unrelated
to its apply-agent), but it's a concrete reminder to read reference repos for what they
*do*, not just the pattern being cited.

### 1.6 Requisition IDs are not globally unique (Rev 2 correction)

Rev 1's identity resolution treated "identical ATS requisition ID" as a standalone
deterministic-match signal. That's wrong: a requisition ID is only unique *within one
employer's ATS tenant*. Two different companies on the same ATS platform (or even the
same company across two ATS migrations) can legitimately reuse the same requisition
number, and treating a bare requisition-ID match as sufficient to attach an occurrence to
an existing `Job` risks silently merging two unrelated postings from different employers.
Corrected in [§8](#8-deterministic-identity-resolution) and
[DECISIONS/0004](DECISIONS/0004-scoped-deterministic-identity.md): requisition-ID
matching is always scoped, either by ATS tenant or by resolved company identity, and
never used bare.

### 1.7 Nothing else rose to the level of a contradiction

The remaining sections (matching, provenance, scheduling) are consistent with each other
and with the modular-monolith style. They're carried into this document and
DATA_MODEL.md largely as specified, with types made concrete.

---

## 2. Architectural style (confirmed)

**Modular monolith**, confirmed as proposed in the spec. Concretely: one FastAPI process,
one PostgreSQL database, one Python dependency tree, organized into modules with
enforced import rules (§5 below). No microservices, no required message broker, no
required Redis/Celery for Phase 0–9. A background worker process is a second *entry
point* into the same codebase (`python -m app.workers.scheduler`), not a separate service
with its own deployable boundary — it imports the same `services`/`ingestion`/`db`
modules the API does.

This scales down well (single laptop, one Postgres container) and scales up later
without a rewrite: the worker entry point can move to its own container/dyno without code
changes, and each source's own `SourceCapabilities.max_concurrency`/`requests_per_second`
(§6.4 — genuinely per-source, not a shared provider-wide value, per Rev 4) already gives
the throttling that would otherwise require a job queue to bolt on later.

**Minimum supported PostgreSQL version: 16** (Rev 3). Pinned explicitly because several
schema decisions depend on specific index/constraint behavior — see
[DATA_MODEL.md](DATA_MODEL.md)'s conventions section. Concretely, this schema relies on:
`gen_random_uuid()` built in (no `pgcrypto` extension needed — available since PG13),
partial and expression unique indexes (standard since long before 16), and `jsonb`. It
deliberately does **not** rely on PG15's `NULLS NOT DISTINCT` clause even though our
minimum already clears that bar — [§8](#8-deterministic-identity-resolution) uses
separate partial indexes instead, which work identically on any modern Postgres and are
easier to read than a `NULLS NOT DISTINCT` clause tucked into one combined index. Pinning
16 (rather than the 13/15 floor the features above would technically allow) is simply
"use a current, boring, well-supported version" for a project with no legacy-version
constraint of its own.

---

## 3. Naming

The repository already exists on disk as `jobGoblin`; the spec's working title was the
generic "job-aggregator." To stop the two names drifting further apart across docs (Rev 1
used "job-aggregator" in prose and in the repo-tree diagram, which no longer matches
reality), this is now fixed explicitly:

| Context | Name | Notes |
|---|---|---|
| Product / marketing name | **JobGoblin** | what a human calls it |
| Git repository | `jobGoblin` | matches the existing local repo directory — not renamed |
| Python backend package (`pyproject.toml` `name`, PyPI-style) | `job-goblin` | hyphenated, standard for a distributable project name |
| Python import package (`import job_goblin...` if ever packaged; internal code lives under `backend/app/`) | `job_goblin` | snake_case per PEP 8 |
| Docker Compose project / container name prefix | `jobgoblin` | lowercase, no separators, Compose-safe |

`backend/app/` (the FastAPI app directory) keeps its generic name rather than embedding
the product name — that's a common Python convention independent of what the project is
called, and matches most FastAPI project templates. Earlier/other docs' references to
"job-aggregator" as a generic description of what the project *is* (a job aggregator) are
fine to keep as prose; only structural/identifier uses (repo tree root, package names)
needed to be pinned down.

---

## 4. Repository structure

```text
jobGoblin/
│
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app factory, router registration
│   │   ├── config.py                  # Pydantic Settings (env-driven)
│   │   │
│   │   ├── api/                       # HTTP layer only — thin, delegates to services/
│   │   │   ├── deps.py                 # shared FastAPI dependencies (db session, current user)
│   │   │   ├── profiles.py
│   │   │   ├── searches.py
│   │   │   ├── jobs.py
│   │   │   ├── collection.py
│   │   │   ├── providers.py
│   │   │   └── analytics.py
│   │   │
│   │   ├── db/
│   │   │   ├── base.py                 # declarative base, naming convention
│   │   │   ├── session.py              # engine/sessionmaker
│   │   │   └── models/                 # SQLAlchemy ORM models, 1 module per aggregate
│   │   │       ├── user.py
│   │   │       ├── candidate_profile.py
│   │   │       ├── saved_search.py
│   │   │       ├── company.py
│   │   │       ├── job.py
│   │   │       ├── job_occurrence.py
│   │   │       ├── raw_job_ingestion.py
│   │   │       ├── collection_run.py
│   │   │       └── user_job.py
│   │   │
│   │   ├── schemas/                    # Pydantic request/response + internal transport
│   │   │   ├── discovered_job.py       # DiscoveredJob, DiscoveryResult, ProviderError
│   │   │   ├── provider.py             # SourceQuery, SourceCapabilities, ProviderCapabilities, ProviderHealth, SourceHealth
│   │   │   ├── match.py                # MatchResult
│   │   │   └── ...
│   │   │
│   │   ├── providers/
│   │   │   ├── base.py                 # DiscoveryProvider Protocol
│   │   │   ├── registry.py             # ProviderRegistry
│   │   │   ├── fixture.py              # FixtureProvider (Phase 2)
│   │   │   ├── ats_scrapers_provider.py# wraps `ats-scrapers` (Phase 4)
│   │   │   ├── jobspy_provider.py      # wraps `python-jobspy` (Phase 7)
│   │   │   └── manual_url_provider.py  # user-pasted career URL (later)
│   │   │
│   │   ├── discovery/
│   │   │   ├── query_planner.py        # SavedSearch -> SourceQuery per provider
│   │   │   └── source_detection.py     # career URL -> ATS/provider guess
│   │   │
│   │   ├── ingestion/
│   │   │   ├── pipeline.py             # orchestrates providers -> raw storage -> normalize -> persistence
│   │   │   ├── raw_storage.py          # RawJobIngestion read/write
│   │   │   ├── identity.py             # deterministic identity resolution (ADR 0004)
│   │   │   └── persistence.py          # the ONLY module issuing Job/JobOccurrence SQLAlchemy writes
│   │   │
│   │   ├── normalization/
│   │   │   ├── titles.py
│   │   │   ├── skills.py
│   │   │   ├── salary.py
│   │   │   ├── experience.py
│   │   │   ├── location.py
│   │   │   ├── employment.py
│   │   │   ├── seniority.py
│   │   │   ├── company.py
│   │   │   └── url.py                  # canonical URL normalization (ADR 0004)
│   │   │
│   │   ├── taxonomy/
│   │   │   ├── skills.yaml
│   │   │   ├── titles.yaml
│   │   │   ├── industries.yaml
│   │   │   ├── seniority.yaml
│   │   │   └── aliases.yaml
│   │   │
│   │   ├── matching/
│   │   │   ├── scorer.py
│   │   │   ├── weights.py
│   │   │   └── explanations.py
│   │   │
│   │   ├── dedupe/
│   │   │   ├── similarity.py           # fuzzy signal scoring (Tier 2 only — see ADR 0002/0004)
│   │   │   └── grouping.py             # duplicate_group assignment
│   │   │
│   │   ├── analytics/                  # read-only SQL aggregations over normalized data
│   │   ├── contacts/                   # Phase 13, empty until then
│   │   ├── services/                   # use-case orchestration + transaction boundaries
│   │   └── workers/
│   │       └── scheduler.py            # Run Now / hourly / daily / weekly loop
│   │
│   ├── migrations/                     # Alembic
│   ├── tests/
│   │   ├── fixtures/                   # canned provider payloads, no live network calls
│   │   ├── unit/                       # normalization, matching, dedupe — pure functions
│   │   ├── db/                         # constraint/migration tests against a real Postgres
│   │   └── integration/                # explicitly separated, may hit live sources, skipped by default
│   └── pyproject.toml
│
├── frontend/                           # Next.js + TypeScript, added Phase 8
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── ROADMAP.md
│   ├── SOURCE_CONNECTORS.md
│   ├── OPEN_SOURCE_REVIEW.md
│   └── DECISIONS/
│       ├── 0001-job-vs-job-occurrence.md
│       ├── 0002-two-tier-duplicate-detection.md
│       ├── 0003-minimal-phase1-schema.md
│       ├── 0004-scoped-deterministic-identity.md
│       ├── 0005-raw-ingestion-vs-provider-attempts.md
│       ├── 0006-userjob-workflow-invariants.md
│       └── 0007-identity-conflict-quarantine.md
│
├── docker-compose.yml                  # postgres + backend, added Phase 0
├── .env.example
└── README.md
```

Changes from Rev 1: root folder renamed `job-aggregator/` → `jobGoblin/` (§3); moved
deterministic identity resolution out of `dedupe/detector.py` into
`ingestion/identity.py` (it runs *during* ingestion, before a `Job` row exists, so it
belongs with ingestion orchestration, not with the post-persistence fuzzy-matching code
in `dedupe/`); added `normalization/url.py` for canonical URL normalization; `dedupe/`
now only contains the Tier 2 probabilistic pieces; added `tests/db/` for constraint and
migration tests (§13).

---

## 5. Dependency boundaries

Rev 1 described this as a single top-to-bottom chain. It isn't one — `matching/`,
`dedupe/`, and `analytics/` are independent siblings that all read the domain model but
never call each other; `api/` and `workers/` are two independent entry points that both
sit on top of `services/`; `normalization/` and `providers/` are both leaves with no
dependency on each other. Describing it as a chain implied orderings that don't exist
(e.g. that `normalization/` depends on `ingestion/`, when it's the reverse). What actually
holds is a **DAG**, enforced per-module:

| Module | May import from | Must NOT import |
|---|---|---|
| `schemas/` | stdlib, Pydantic | anything else in this app — these are provider-independent value objects (`DiscoveredJob`, `DiscoveryResult`, `SourceQuery`, `MatchResult`, etc.) that every other layer imports *from* |
| `taxonomy/` | (data files, no code) | — |
| `normalization/` | `schemas/`, `taxonomy/` | `providers/`, `db/`, `ingestion/`, `services/`, `api/`, any network client (`httpx`, `ats_scrapers`, `jobspy`) — pure functions only: value/dict in, typed value + provenance out |
| `providers/` | `schemas/`, external libraries (`ats_scrapers`, `jobspy`) | `db/`, `normalization/`, `ingestion/`, `services/`, `api/` — a provider's job is to produce a `DiscoveryResult`, nothing else; it never normalizes or persists |
| `discovery/` (query_planner, source_detection) | `schemas/`, `db/models` (read `SavedSearch`), `providers/` (only `ProviderCapabilities`, to plan — never calls `discover()`) | network clients, `ingestion/`, `services/` |
| `db/` (models, session) | `schemas/` (shared enums/types only) | `providers/`, `normalization/`, `ingestion/`, `services/`, `api/` — pure ORM + engine |
| `ingestion/` (pipeline, raw_storage, identity, persistence) | `schemas/`, `providers/` (via `ProviderRegistry`, calls `discover()`), `discovery/`, `normalization/`, `db/` | `matching/`, `dedupe/`, `analytics/`, `api/` — and only `ingestion/persistence.py` (not `pipeline.py` directly) issues SQLAlchemy writes |
| `matching/`, `dedupe/`, `analytics/` | `schemas/`, `db/models` (read), `normalization/` (reuse comparison helpers) | `providers/`, `ingestion/`, `api/`, any network client — read-only over already-persisted rows |
| `services/` | `db/`, `ingestion/`, `matching/`, `dedupe/`, `analytics/`, `schemas/` | `api/` — this is the only layer allowed to compose across ingestion + matching/dedupe/analytics for one use case, and the only layer allowed to write `user_jobs`/`job_notes` |
| `api/` | `services/`, `schemas/` | `db/`, `providers/`, `ingestion/` directly — routes never bypass `services/` |
| `workers/` | `services/`, `db/` (session bootstrap only) | same rule as `api/` — a scheduled run calls a `services/` function, never `ingestion/` directly, so there's exactly one orchestration path whether triggered by a cron tick or a "Run Now" button |
| `frontend/` | the HTTP API only | everything else — no direct DB or provider access, ever |

Hard rules that don't fit neatly into the table:

- **`ats_scrapers` and `jobspy` types (Pydantic models, DataFrames) never appear outside
  their adapter module.** `AtsScrapersProvider.discover()` and `JobSpyProvider.discover()`
  are the only functions that import those packages. Everything downstream sees
  `DiscoveredJob`/`DiscoveryResult`. This is what makes the two libraries replaceable
  per §7/§8/§54's "implementation rule."
- **`providers/` code never writes `user_jobs`, `job_notes`, or any user-state table.** A
  provider's only output is a `DiscoveryResult`. It cannot know a user exists.
- **Only one function writes `user_jobs.status`/`applied_at` together** — see
  [DECISIONS/0006](DECISIONS/0006-userjob-workflow-invariants.md) — so the
  status/applied_at consistency invariant can't be violated by a code path that forgets
  the pairing.

---

## 6. Core interfaces

These are Phase 2 deliverables; defined now so Phase 1's schema and Phase 2's provider
work don't have to be re-negotiated. Shown as typed Python for precision — the actual
Phase 2 commit will put these in `schemas/`, and `DiscoveryProvider` in `providers/base.py`.
All list/set/dict-valued fields use `Field(default_factory=...)`, not a bare mutable
literal default (Rev 1 used `= []`/`= set()`, which is the classic Python/Pydantic
shared-mutable-default trap).

### 6.1 `SourceQuery` — what a provider is asked to do

```python
from pydantic import BaseModel, Field

class SourceQuery(BaseModel):
    # Explicit sub-source selection (Rev 3, item 6; validation rules in §6.6, Rev 4). A
    # provider that fans out to multiple sites/ATS-types (JobSpy's 8 sites; ats-scrapers'
    # dozens of ATS types) needs to know exactly which ones this call should hit.
    # An empty list means "run this provider with zero sources" (i.e. don't call it),
    # not "all sources" — see §6.6 for why that distinction has to be explicit.
    sources: list[str] = Field(default_factory=list)

    # Fields a provider MAY use; not all sources support all of them —
    # see SourceCapabilities (§6.4) for what a given source actually honors.
    titles: list[str] = Field(default_factory=list)
    excluded_titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_ok: bool | None = None          # None = no preference
    radius_miles: float | None = None
    salary_floor: int | None = None
    employment_types: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    posted_within_hours: int | None = None
    company_filter: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    max_results: int | None = None

    # Set by the QueryPlanner, not the caller. Rev 4 change: replaces Rev 1–3's single
    # flat `enforced_remotely: set[str]`, which couldn't represent "source A supports
    # salary filtering but source B (same provider, same call) doesn't" — filter support
    # is a per-source fact (SourceCapabilities, §6.4), so enforcement has to be tracked
    # per source too. Keyed by source name (must match an entry in `sources`); each value
    # is the set of SourceQuery field names that source cannot enforce remotely and must
    # be filtered out of that source's results locally, after the fact.
    local_enforcement: dict[str, set[str]] = Field(default_factory=dict)
```

`QueryPlanner.plan(saved_search, provider_capabilities) -> SourceQuery` translates a
`SavedSearch` into one `SourceQuery` per enabled provider. Full validation, expansion, and
per-source enforcement rules are in [§6.6](#66-queryplanner-behavior-rev-4); summary of
what `sources` participates in:
- **Query planning** — set here, by `QueryPlanner`, validated against
  `ProviderCapabilities.sources` (§6.4).
- **Cache fingerprinting** (master spec §39, detailed in §6.6) — the fingerprint key
  includes the sorted `sources` list; a request for `["linkedin"]` and
  `["linkedin","indeed"]` are different queries and must not share a cache entry.
- **`DiscoveryResult`** — `source_stats` (§6.3, revised below) has exactly one entry per
  entry in `sources` — a validated invariant, not a flag on each entry (Rev 4 removed
  `SourceRunStats.requested` for this reason).
- **Provider-attempt telemetry** — `collection_run_provider_attempts` (§9, migrated in
  Phase 1 as of Rev 4) gets exactly one row per `(run, provider, source)` for each entry
  in `sources`.
- **Fixture tests** — the partial-failure fixture case (§11) sets `sources` explicitly
  (e.g. `["healthy_source", "broken_source"]`) so the test is driven by an actual query
  input, not an implicit assumption inside the fixture provider.

### 6.2 `DiscoveredJob` — universal per-posting output

Matches §16 as specified:

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

class DiscoveredJob(BaseModel):
    provider: str            # e.g. "ats_scrapers", "jobspy"
    source: str              # e.g. "greenhouse", "linkedin"
    source_tenant_id: str | None   # e.g. Workday subdomain, Greenhouse board token — see §8
    source_job_id: str | None
    requisition_id_raw: str | None # as reported by this source, unscoped — see §8

    title: str | None
    company: str | None
    location: str | None

    source_url: str
    apply_url: str | None
    canonical_url: str | None

    description: str | None
    compensation_text: str | None

    posted_at: datetime | None
    discovered_at: datetime

    raw: dict[str, Any] = Field(default_factory=dict)      # provider-specific payload, preserved verbatim
```

### 6.3 `DiscoveryResult` — what a provider call actually returns (Rev 2, revised Rev 3)

Rev 1 had `DiscoveryProvider.discover() -> list[DiscoveredJob]`: an all-or-nothing
return. That doesn't match reality — confirmed in
[OPEN_SOURCE_REVIEW.md](OPEN_SOURCE_REVIEW.md), `python-jobspy`'s own multi-site call can
raise from a LinkedIn failure and destroy already-fetched Indeed/Glassdoor results if the
caller isn't careful. A provider wrapping multiple sub-sources must be able to report
"here's what I got, here's what failed, here's whether that means the result set might be
incomplete" — a single failed source must never discard another source's successful jobs.

**Rev 3 change:** Rev 2 stored `requested_sources`, `completed_sources`, and
`source_stats` as three independent fields that could disagree with each other (nothing
stopped a provider adapter from populating them inconsistently). Rev 3 makes
`source_stats` the single source of truth and derives the other two as read-only
properties, so there is exactly one place an adapter can get this wrong instead of three.

**Rev 4 change:** since `SourceQuery.sources` (§6.1) is now validated before a provider is
ever called, `source_stats` is guaranteed to contain *exactly* one entry per requested
source (see the validation rules below) — that guarantee makes `SourceRunStats.requested`
redundant (it would always be `True`), so it's removed. In its place,
`SourceRunStats.incomplete_results` is added: a source that returns *some* jobs before
hitting a cap, rate limit, or pagination cutoff is `completed=True,
incomplete_results=True` — it succeeded, just not exhaustively — which is different from
`completed=False` (the source produced nothing usable at all). Conflating "partially
successful" with "failed" would make a source that returns 40 good jobs out of a
likely-larger true count look identical to a source that returned zero.

```python
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator

class ProviderErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    BLOCKED = "blocked"              # anti-bot / 403 / 406
    PARSE_ERROR = "parse_error"
    NOT_FOUND = "not_found"
    UPSTREAM_ERROR = "upstream_error"  # 5xx
    UNKNOWN = "unknown"

class ProviderError(BaseModel):
    source: str                      # which sub-source failed, e.g. "linkedin"
    category: ProviderErrorCategory
    retryable: bool
    detail: str | None                # sanitized — no secrets, tokens, or full stack traces
    occurred_at: datetime

class SourceRunStats(BaseModel):
    source: str
    completed: bool
    jobs_found: int
    incomplete_results: bool = False   # new in Rev 4 — see above
    duration_ms: int | None = None
    rate_limited: bool = False
    retry_count: int = 0

class DiscoveryResult(BaseModel):
    provider: str
    jobs: list[DiscoveredJob] = Field(default_factory=list)
    source_stats: list[SourceRunStats] = Field(default_factory=list)   # authoritative
    errors: list[ProviderError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime

    @property
    def requested_sources(self) -> list[str]:
        return [s.source for s in self.source_stats]

    @property
    def completed_sources(self) -> list[str]:
        return [s.source for s in self.source_stats if s.completed]

    @property
    def possibly_incomplete(self) -> bool:
        return (
            bool(self.errors)
            or any(not s.completed for s in self.source_stats)
            or any(s.incomplete_results for s in self.source_stats)
        )

    @model_validator(mode="after")
    def _check_consistency(self) -> "DiscoveryResult":
        sources = [s.source for s in self.source_stats]
        if len(sources) != len(set(sources)):
            raise ValueError("duplicate source names in source_stats")
        error_sources = {e.source for e in self.errors}
        if not error_sources <= set(sources):
            raise ValueError("ProviderError.source with no matching source_stats entry")
        job_sources = {j.source for j in self.jobs}
        if not job_sources <= set(sources):
            raise ValueError("DiscoveredJob.source with no matching source_stats entry")
        for s in self.source_stats:
            if not s.completed and s.jobs_found != 0:
                raise ValueError(
                    f"{s.source}: completed=False must have jobs_found=0 — a source "
                    "that returned any jobs is completed=True, incomplete_results=True"
                )
        return self
```

**`DiscoveryResult` validation rules (Rev 4, item 5) — enforced by the model validator
above, not left to adapter discipline:**
- No duplicate source names in `source_stats`.
- Every `SourceQuery.sources` entry appears in `source_stats` exactly once — this is
  enforced by construction at the call site (`ingestion/pipeline.py` asserts the sets
  match after `discover()` returns) rather than inside the model itself, since
  `DiscoveryResult` alone doesn't have access to the originating `SourceQuery`; the
  in-model checks above catch the sub-cases a single `DiscoveryResult` *can* verify on
  its own (no duplicates, no orphaned errors/jobs).
- Every `ProviderError.source` corresponds to a `source_stats` entry — no error can
  reference a source that was never part of this call.
- `jobs` may only contain sources represented in `source_stats` — no job can be attributed
  to a source the result doesn't otherwise account for.
- `completed=False` implies `jobs_found=0`. The MVP does not support streaming partial
  results from a source that ultimately failed — a source either fully or partially
  *succeeds* (`completed=True`, with `incomplete_results=True` for the truncated case) or
  it *fails* with nothing to show (`completed=False`, `jobs_found=0`). A future streaming
  design that needs to represent "got 12 jobs, then failed" would have to revisit this
  rule explicitly; it isn't supported implicitly today.

An adapter constructs one `SourceRunStats` entry per source in the inbound
`SourceQuery.sources` (§6.1) — that's the only thing it needs to get right; the derived
properties then can't drift out of sync with it by construction, and the validator
catches it if an adapter still gets it wrong. (If a future caller needs `requested_sources`/
`completed_sources`/`possibly_incomplete` as *serialized* JSON fields rather than
in-process attributes, use Pydantic v2's `@computed_field` decorator instead of a bare
`@property` — the shape above assumes in-process consumption by
`ingestion/pipeline.py`, which is the only Rev 1–4 consumer.)

**Concretely, for JobSpy:** `JobSpyProvider.discover()` calls the underlying library once
*per requested site in `query.sources`*, each in its own `try/except` (never passing a
multi-site list to a single library call — see
[OPEN_SOURCE_REVIEW.md §2](OPEN_SOURCE_REVIEW.md)). If Indeed succeeds and LinkedIn
raises, the adapter appends `SourceRunStats(source="indeed", completed=True,
jobs_found=N, ...)` and `SourceRunStats(source="linkedin", completed=False,
jobs_found=0, ...)`, Indeed's jobs land in `jobs`, and a `ProviderError(source="linkedin",
category=BLOCKED or UPSTREAM_ERROR, retryable=True, ...)` lands in `errors` —
`discover()` still returns normally (doesn't raise), and `possibly_incomplete` computes
to `True` because LinkedIn's entry is `completed=False`. `discover()` is only allowed to
raise for genuine programmer errors (e.g. a malformed `SourceQuery`); any
anticipated-but-uncontrollable failure (timeout, block, rate limit, one bad source) is
reported *in* the returned `DiscoveryResult`, never by raising past the adapter boundary.
`ingestion/pipeline.py` persists whatever came back and records `errors`/`source_stats`
onto the run's `collection_run_provider_attempts` rows (§9/[DATA_MODEL.md](DATA_MODEL.md))
— one source's failure never discards another source's successful results, and never
silently disappears from observability either.

### 6.4 `DiscoveryProvider` protocol, `SourceCapabilities`, `ProviderCapabilities`, `ProviderHealth`

**Rev 4 change:** Rev 1–3's `ProviderCapabilities` put `max_concurrency`,
`requests_per_second`, the four `supports_*_filter` booleans, and
`supported_query_fields` directly on the provider — as if every source a provider talks
to shares one concurrency budget and one set of supported filters. That's false: within a
single `JobSpyProvider`, LinkedIn and Glassdoor have different real-world rate limits and
different filter surfaces (§9's example), and within `AtsScrapersProvider`, Greenhouse's
public API has no published limit while a Workday tenant behind bot detection needs to be
throttled much harder. A provider-wide value is either wrong for some sources or forces
the most conservative source's limits onto every other source unnecessarily. These are
now **per-source** facts, collected under `ProviderCapabilities.sources`:

```python
class SourceCapabilities(BaseModel):
    source: str
    supported_query_fields: set[str] = Field(default_factory=set)  # used by QueryPlanner to decide local vs remote enforcement
    max_concurrency: int = Field(ge=1)
    requests_per_second: float | None = Field(default=None, gt=0)
    supports_salary_filter: bool = False
    supports_location_filter: bool = False
    supports_remote_filter: bool = False
    supports_posted_within_filter: bool = False

class ProviderCapabilities(BaseModel):
    provider: str
    sources: dict[str, SourceCapabilities] = Field(default_factory=dict)  # keyed by source name
```

`ProviderCapabilities.sources` is now **authoritative** for everything that used to live
provider-wide:
- which source names the provider supports at all — this is the validation surface
  `QueryPlanner` checks `SourceQuery.sources` and `SavedSearch.enabled_sources` against
  (§6.6);
- per-source filter support (`supports_*_filter`) — drives `SourceQuery.local_enforcement`
  per source, not once per provider;
- per-source concurrency/rate limiting — `AtsScrapersProvider`/`JobSpyProvider` must
  throttle each source independently using that source's own
  `max_concurrency`/`requests_per_second`, never a single shared value applied to every
  source in the call.

There is no longer a provider-wide `max_concurrency`/`requests_per_second`/
`supported_query_fields`/`supports_*_filter` field anywhere on `ProviderCapabilities` —
not even as a "default the per-source values start from." If a provider's sources
genuinely do share the same practical limits (plausible for e.g. `ats-scrapers`' public,
unauthenticated JSON APIs), that's expressed by giving each of those `SourceCapabilities`
entries the same literal values, not by a shared provider-level fallback field — keeping
exactly one place (`sources[name]`) that `QueryPlanner` and `ingestion/` ever have to read
avoids the ambiguity of "did this source override the provider default, or inherit it."

```python
class SourceHealth(BaseModel):
    source: str
    healthy: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    detail: str | None

class ProviderHealth(BaseModel):
    provider: str
    healthy: bool                              # provider-level: can it be used AT ALL right now
    sources: list[SourceHealth] = Field(default_factory=list)
    last_checked_at: datetime
```

Rev 1's `ProviderHealth` conflated provider-level and source-level health into one flat
`healthy: bool`. That's insufficient once a provider fans out to multiple sub-sources
(JobSpy's 8 sites; `ats-scrapers`' dozens of ATS types) — "LinkedIn is currently blocked"
and "the whole JobSpy provider is unusable" are different facts, and Phase 12's
anomaly-detection needs the *source*-level signal specifically (§10 below). Rev 2 splits
`ProviderHealth.healthy` (provider-level: is at least one enabled source usable) from a
list of per-`SourceHealth` entries. A provider that only ever talks to one source (rare,
but possible for a future single-site adapter) simply reports a `sources` list of length
one. (`ProviderHealth.sources` is a `list`, not a `dict` like
`ProviderCapabilities.sources` — health is normally read as "iterate everything and show
me the unhealthy ones," not looked up by name, so a list is the simpler shape there; the
two aren't required to match shape since they serve different access patterns.)

```python
class DiscoveryProvider(Protocol):
    name: str

    async def discover(self, query: SourceQuery) -> DiscoveryResult: ...
    def capabilities(self) -> ProviderCapabilities: ...
    async def health(self) -> ProviderHealth: ...
```

`ProviderRegistry` holds the configured provider instances, exposes them by name, and is
the single place `ingestion/pipeline.py` asks "which providers are enabled for this saved
search, and are they healthy" — no other module enumerates providers directly.

### 6.5 `SavedSearch.enabled_sources` — unambiguous source selection

Rev 1–3's `saved_searches.enabled_providers: text[]` said which *providers* run at all,
but had no way to say "run JobSpy, but only against LinkedIn and Indeed, not Glassdoor."
**Rev 4 adds `enabled_sources: jsonb`**, supplementing (not replacing) `enabled_providers`
— the two answer different questions and are both kept:

- `enabled_providers` — which providers are enabled for this saved search at all.
- `enabled_sources` — for providers that need finer-grained control, which of that
  provider's sources to actually use. Shape:

```json
{
  "jobspy": ["linkedin", "indeed", "glassdoor"],
  "ats_scrapers": ["greenhouse", "lever", "workday"]
}
```

Rules, validated by `QueryPlanner` against `ProviderRegistry`/`ProviderCapabilities`
at planning time (§6.6):
- A provider present in `enabled_providers` but **absent** as a key in `enabled_sources`
  has no source-level preference — `QueryPlanner` expands it to every source that
  provider's `ProviderCapabilities.sources` currently advertises.
- A provider present as a key in `enabled_sources` with a **non-empty** list uses exactly
  those sources, after validating each name exists in that provider's
  `ProviderCapabilities.sources`.
- A provider present as a key in `enabled_sources` with an **explicit empty list** (`[]`)
  runs with zero sources — i.e. it doesn't run at all this cycle — distinct from "absent
  key," which means "no preference, use everything." This distinction has to be explicit;
  collapsing "no preference" and "deliberately none" into the same representation (e.g.
  both meaning an empty/missing list) would make it impossible for a user to temporarily
  disable a provider's sources without also implicitly opting back into "all sources"
  the next time a new source is added to that provider.
- Any source name in `enabled_sources` not present in `ProviderRegistry`/
  `ProviderCapabilities` fails validation before query planning proceeds for that
  provider.

### 6.6 `QueryPlanner` behavior (Rev 4)

`QueryPlanner.plan(saved_search, provider_capabilities) -> SourceQuery` is called once
per provider present in `saved_search.enabled_providers`. Its behavior, precisely:

1. **Resolve source selection.** Look up `saved_search.enabled_sources[provider]`
   (§6.5). If the key is absent, the resolved source list is *every* source in
   `provider_capabilities.sources` (expand to all configured/enabled sources for that
   provider). If the key is present, the resolved source list is exactly that list
   (including the empty-list case, resolved to zero sources).
2. **Validate.** Every name in the resolved source list must be a key in
   `provider_capabilities.sources`. An unknown name fails validation for that provider
   **before** `discover()` is ever called — `ingestion/pipeline.py` records this as a
   planning-time failure on the `CollectionRun` (not a `collection_run_provider_attempts`
   row, since no provider call was attempted for that source) and continues with
   whatever other providers/sources in the run remain valid.
3. **Empty resolved list → no execution.** If, after steps 1–2, the resolved list for a
   provider is empty (either because `enabled_sources[provider] == []` explicitly, or —
   degenerately — because every listed source failed validation), `QueryPlanner`
   produces no `SourceQuery` for that provider at all, and `ingestion/pipeline.py` never
   calls that provider's `discover()`. This is different from "the provider errored" —
   it's simply not part of this run.
4. **Build one `SourceQuery` per provider.** `sources` is set to the validated,
   non-empty source list from steps 1–3.
5. **Determine local vs. remote enforcement per source.** For each source in `sources`,
   compare the `SavedSearch` fields that are actually populated (e.g. `salary_floor` is
   set) against that source's own `SourceCapabilities` booleans (e.g.
   `supports_salary_filter`). Any populated field the source's capabilities say it can't
   honor remotely goes into `local_enforcement[source]` (§6.1) for that source
   specifically — two sources in the same call can validly end up with different
   `local_enforcement` entries.
6. **Record the enforcement mapping for observability.** The full `provider -> source ->
   locally_enforced_fields` mapping (i.e. `{provider: source_query.local_enforcement}`
   assembled across every provider planned this run) is written to
   `collection_runs.providers_enforced_locally` (jsonb — see
   [DATA_MODEL.md](DATA_MODEL.md)), so "why did a bad job slip through" is answerable
   without re-reading code.

**Cache fingerprinting** (master spec §39) uses: `provider`, the sorted `sources` list,
and the normalized values of only the `SourceQuery` fields that are actually
populated/relevant to this call (empty/`None` fields are excluded from the fingerprint
rather than hashed as "empty," so two queries that differ only in an irrelevant unset
field still share a cache entry). A request for `sources=["linkedin"]` and
`sources=["linkedin","indeed"]` are different queries and never share a cache entry.

**Behavior summary for the cases called out explicitly:**
- *No saved source preference for a provider* (key absent from `enabled_sources`) → every
  currently-configured source for that provider is used.
- *Explicit empty source list* (`enabled_sources[provider] == []`) → that provider runs
  with zero sources this cycle — no `discover()` call at all.
- *Unknown source name* → validation failure for that provider, recorded on the
  `CollectionRun`, before any provider call; other valid providers/sources in the same
  run are unaffected.
- *Two sources with different filter capabilities* (e.g. one supports salary filtering,
  one doesn't) → they end up with different `local_enforcement` entries in the same
  `SourceQuery`, even though both belong to the same provider and the same planning call.

### 6.7 `MatchResult`

```python
class MatchResult(BaseModel):
    job_id: UUID
    saved_search_id: UUID
    total_score: float
    title_score: float
    skills_score: float
    location_score: float
    salary_score: float
    seniority_score: float
    experience_score: float
    employment_score: float
    hard_filter_failures: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
```

Hard filters (e.g. salary below floor) are evaluated separately from scoring and can
short-circuit it; missing data always scores neutral, never zero or reject, per §35.

---

## 7. Job vs. JobOccurrence

This is the central modeling decision and gets its own ADR:
[DECISIONS/0001-job-vs-job-occurrence.md](DECISIONS/0001-job-vs-job-occurrence.md). Summary:

- **`Job`** is the conceptual opening — "Acme, Senior Data Analyst, Req #1234." It holds
  the canonical, provenance-tracked fields described in §20 (title, company, location,
  salary, etc.), which are *resolved* from one or more occurrences (§22's field-merging).
- **`JobOccurrence`** is one observed appearance of that opening on one source
  (Workday, LinkedIn, Indeed, Glassdoor each get their own row). It holds
  source-specific facts that must never be conflated across sources: `source_url`,
  `apply_url`, `applicant_count`, `first_seen_at`/`last_seen_at` *for that source*, its
  own `source_tenant_id`/`requisition_id_raw` (§8), and a link from the
  `RawJobIngestion`(s) that produced/refreshed it.
- A `Job` has one-to-many `JobOccurrence`s. An occurrence attaches to an existing `Job`
  when ingestion finds a **scoped** deterministic identity match (§8 — never a bare
  requisition-ID match); otherwise it creates a new `Job` with itself as the sole
  occurrence.
- Deleting/expiring is occurrence-scoped (`active`/`inactive` per occurrence — a posting
  can disappear from LinkedIn while still active on Workday); a `Job` is only considered
  fully closed when all its occurrences are inactive.

---

## 8. Deterministic identity resolution

Full decision records: [DECISIONS/0004-scoped-deterministic-identity.md](DECISIONS/0004-scoped-deterministic-identity.md)
(scoping + URL normalization + precedence) and
[DECISIONS/0007-identity-conflict-quarantine.md](DECISIONS/0007-identity-conflict-quarantine.md)
(what happens when the precedence rules can't cleanly resolve — Rev 3, split out because
Rev 2's original conflict handling was infeasible; see below). Summary of what changed
and why it matters operationally:

**The problem.** A requisition ID (or even a `source_job_id`) is only unique *within the
scope that issued it* — one ATS tenant, one company. Matching on a bare requisition ID
across the whole `job_occurrences` table risks attaching an occurrence to a completely
unrelated employer's job that happens to reuse the same number.

**The fix — every deterministic signal is scoped, tried in this precedence order:**

1. **Same natural key, same occurrence.** `(provider, source, source_tenant_id,
   source_job_id)` exact match — enforced by **two separate partial unique indexes**, not
   one (Rev 3 fix, see below) — means this *is* the same occurrence being re-observed —
   update in place (refresh `last_seen_at`, etc.), not a new occurrence.
2. **Normalized canonical URL match.** Two *different* occurrences (different
   `provider`/`source`) sharing the same normalized `canonical_url` is the strongest
   cross-occurrence signal — a URL is inherently host-scoped, so this doesn't need
   additional tenant scoping. Normalization rules (lowercase host, strip fragment, strip
   default ports, strip known tracking params, normalize trailing slash, retain
   provider-identified identity params, source-specific override rules) live in
   `normalization/url.py`; full algorithm in ADR 0004.
3. **Tenant-scoped requisition match.** `(provider, source, source_tenant_id,
   requisition_id_raw)` exact match across occurrences — **Rev 3 fix**: Rev 2's key
   omitted `provider`/`source`, which implicitly assumed a `source_tenant_id` value is
   comparable across different providers/sources. It isn't documented to be, so the key
   now includes the full namespace it's actually scoped within. Used when no canonical
   URL is available but a tenant *is* known (e.g. two different aggregators both scraped
   the same Workday tenant's posting, through the *same* adapter/source pairing, without
   preserving a canonical link). If a future need arises to match across two genuinely
   different providers hitting the same real-world ATS tenant (e.g. `ats_scrapers`'
   "workday" source and some other library's own "workday" source both resolving to the
   same employer instance), that requires defining a separate, explicitly normalized ATS
   identity concept (e.g. `companies.ats_tenant_key` or similar) — not silently dropping
   `provider`/`source` from this key. Not needed today; noted as a deliberate non-goal.
4. **Company-scoped requisition match — fallback only.** `(company_id,
   requisition_id_raw)` exact match, used only when `source_tenant_id` is unavailable at
   all. Weaker than tier 3 because a requisition ID isn't guaranteed unique across a
   company's own multiple ATS instances (e.g. mid-migration). If this fallback matches
   **more than one** existing distinct `Job`, that's ambiguous, not a match — see below.
5. **No deterministic match** → create a new `Job` with this as its sole occurrence.

### NULL-safe natural key (Rev 3 fix, item 1)

Rev 2's natural key was one partial unique index —
`UNIQUE (provider, source, source_tenant_id, source_job_id) WHERE source_job_id IS NOT
NULL` — which **does not enforce uniqueness when `source_tenant_id` is NULL**, because
ordinary PostgreSQL unique indexes treat every NULL as distinct from every other NULL.
Since `source_tenant_id` is *documented* to be NULL for LinkedIn and Indeed (no tenant
concept), this index silently allowed unlimited duplicate rows for
`(provider="jobspy", source="linkedin", source_tenant_id=NULL, source_job_id="123")` —
exactly the sources most likely to be re-ingested on every scheduled run.

Fixed with **two separate partial unique indexes** (preferred over PG15's
`NULLS NOT DISTINCT` or a `COALESCE`-based expression index — see
[§2](#2-architectural-style-confirmed)'s minimum-version note for why):

```sql
-- Tenant-scoped sources (Workday, Greenhouse, Lever, ...)
CREATE UNIQUE INDEX job_occurrences_natural_key_tenant
  ON job_occurrences (provider, source, source_tenant_id, source_job_id)
  WHERE source_job_id IS NOT NULL AND source_tenant_id IS NOT NULL;

-- Sources with no tenant concept (LinkedIn, Indeed, ...)
CREATE UNIQUE INDEX job_occurrences_natural_key_no_tenant
  ON job_occurrences (provider, source, source_job_id)
  WHERE source_job_id IS NOT NULL AND source_tenant_id IS NULL;
```

Every row falls into exactly one of these two indexes (never both, since a row's
`source_tenant_id` is either NULL or not), and both actually enforce uniqueness — the
second index has no NULL column in its key at all, so there's no distinctness loophole
left. Behaviorally: for a source with a tenant, two rows can share a `source_job_id` as
long as their `source_tenant_id` differs (correct — different employers' job #123 are
different jobs); for a source with no tenant, `source_job_id` alone must be unique within
`(provider, source)` (correct — LinkedIn's own posting IDs are already globally unique on
LinkedIn).

**Required Phase 1 database tests** (join the list in
[§13](#13-phase-1-acceptance-criteria-strengthened-rev-2)):
- inserting two rows with identical `(provider, source, source_job_id)` and
  `source_tenant_id = NULL` is **rejected** by `job_occurrences_natural_key_no_tenant`;
- inserting two rows with the same `source_job_id` but two different non-null
  `source_tenant_id` values is **allowed** (they're different employers' postings);
- re-ingesting a payload whose natural key already exists **resolves to the existing
  occurrence** (an `UPDATE`, or an `INSERT ... ON CONFLICT (...) DO UPDATE` targeting
  whichever of the two partial indexes applies) rather than raising a constraint
  violation the application has to catch — idempotency is a designed code path, not an
  incidentally-caught exception.

### Collision and ambiguity handling (Rev 3 — replaces infeasible Rev 2 behavior)

Rev 2 said a Tier 1/2 conflict or a Tier 4 ambiguity should "create a new `Job` for the
incoming occurrence." For a **Tier 1** conflict specifically, that's impossible: Tier 1
matching *by definition* means a row with that exact natural key **already exists** —
inserting a second row with the same key would violate the very constraint that makes
Tier 1 matching meaningful. Rev 3 splits this into two distinct, both-feasible outcomes,
detailed in [ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md):

- **`evidence_mismatch`** (Tier 1 only): the natural key matches an *existing* occurrence,
  but the incoming payload's normalized canonical URL conflicts with that occurrence's
  already-recorded one. **No second occurrence is created.** The existing occurrence's
  disputed field(s) are left untouched; purely observational fields (`last_seen_at`,
  `applicant_count`, `applicant_count_text`, `is_active`) still update normally, since the
  posting genuinely was observed again — only the *disputed* fields are frozen pending
  review. An `identity_conflicts` row is recorded referencing the existing occurrence.
- **`ambiguous_match`** (Tiers 2–4): a matching tier finds **more than one** distinct
  candidate `Job` to attach to. This *is* a genuinely new occurrence (no natural-key row
  exists for it yet), so creating a new, standalone `Job` for it remains valid — it's
  flagged via an `identity_conflicts` row (holding the list of candidate occurrences) for
  human review, rather than guessed into one of them.

Both route to the new `identity_conflicts` table (§9, [ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md))
— **not** `duplicate_groups`. `duplicate_groups` (Phase 6,
[ADR 0002](DECISIONS/0002-two-tier-duplicate-detection.md)) is reserved exclusively for
Tier 2's fuzzy/probabilistic similarity matching; conflating a deterministic
exact-match conflict with a probabilistic similarity suggestion was a Rev 2 modeling
mistake, corrected here (item 4).

`jobs.requisition_id` (the resolved, display-only field from §20) is populated *after*
identity resolution, from whichever occurrence's requisition ID is most authoritative —
it is never itself used as a matching key. The matching key lives on `job_occurrences`
(`source_tenant_id`, `requisition_id_raw`), scoped, as above.

---

## 9. Raw ingestion vs. provider-attempt telemetry

Full decision records: [DECISIONS/0005-raw-ingestion-vs-provider-attempts.md](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md)
and [DECISIONS/0007-identity-conflict-quarantine.md](DECISIONS/0007-identity-conflict-quarantine.md).

Rev 1 conflated two different granularities under "raw ingestion": *did calling a source
work at all* (a request-level concern — durations, retries, rate limits, zero-result
responses) and *here is one specific posting's payload* (a per-record concern). Rev 2
separated them into two tables but left `raw_job_ingestions`' own status enum
(`retrieval_status: ok / http_error / parse_error / rate_limited / timeout`) still mixing
the two granularities — `http_error`/`rate_limited`/`timeout` describe *why a fetch never
produced a payload at all*, which by definition means no `RawJobIngestion` row would
exist to hold that status. **Rev 3 (item 5)** finishes the separation:

- **`collection_run_provider_attempts`** ([DATA_MODEL.md](DATA_MODEL.md), **migrated in
  Phase 1** as of Rev 4 — see §13; Phase 2's fixture proof is its first writer, not Phase
  9 — see below) — exactly **one aggregate row per `(collection_run, provider, source)`**,
  enforced by `UNIQUE (collection_run_id, provider, source)`. Records request-level
  telemetry for that source's execution within that run: `started_at`/`completed_at`,
  `status` (`running` / `completed` / `partial` / `failed`), `retry_count`,
  `rate_limited`, `error_category` (`timeout`/`rate_limited`/`auth_error`/`blocked`/etc. —
  reusing `ProviderErrorCategory` from §6.3), sanitized `error_message`,
  `incomplete_results`, and per-slice `jobs_discovered`/`jobs_inserted`/`jobs_updated`
  counts (all non-negative by `CHECK`). A source that returns zero jobs successfully is
  `status = 'completed'`, `jobs_discovered = 0` — not an error; a source that returned
  some jobs but hit a cap/rate-limit mid-pagination is `status = 'partial'` with
  `incomplete_results = true` and **no error required** — `error_category`/
  `error_message` stay `NULL` for a clean partial result, since truncated pagination
  isn't itself a hard error. **Cardinality note:** this is one *aggregate* row per source
  execution, not one row per individual HTTP request/retry — `retry_count` *summarizes*
  how many retries happened within that one source's execution for this run. If
  individual per-request attempt history is ever needed (e.g. for detailed
  request-level debugging), that's a separate future table, `provider_request_attempts`,
  keyed by this table's row — it does **not** change this table's cardinality.
  `CollectionRun` remains the parent aggregate over these rows (`ON DELETE CASCADE`).
- **`raw_job_ingestions`** (Phase 1 table) — one row per individual `DiscoveredJob`
  payload that was **actually fetched**, created before normalization runs. Its column is
  renamed `processing_status` (Rev 3, was `retrieval_status`) with a narrower enum
  describing only what happens to a payload *after* it exists: `fetched` (just written,
  not yet processed — transient), `parse_error` (normalization failed), `normalized`
  (cleanly resolved — attached to an existing occurrence or created a new one, no
  conflict), `identity_conflict` (parsed fine, but [§8](#8-deterministic-identity-resolution)'s
  resolution produced an `evidence_mismatch` or `ambiguous_match` — see
  [ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md)). There is no `http_error`/
  `rate_limited`/`timeout` value here anymore — those never had a payload to attach to,
  so they only ever belonged on `collection_run_provider_attempts`.

A single provider attempt can produce zero, one, or many `RawJobIngestion` rows. A
provider-level failure (the search endpoint itself times out) produces a
`collection_run_provider_attempts` row with an error and **no** `RawJobIngestion` rows —
there was no payload to preserve. A per-posting parse failure (the batch fetched fine,
but one posting's JSON didn't map cleanly) produces exactly one `RawJobIngestion` row with
`processing_status = 'parse_error'`, under a `collection_run_provider_attempts` row that
otherwise reports `status = 'completed'`.

**Out of scope, noted explicitly so it isn't reinvented ad hoc later:** if a future
feature fetches *additional detail* for an already-discovered candidate (e.g. a two-phase
flow — a lightweight search result, then a separate detail-page fetch) and that detail
fetch itself fails with an HTTP-level error, that is **not** a `raw_job_ingestions`
`processing_status` — there's no payload yet to attach it to. Model it as its own
explicit fetch-attempt record keyed by the existing `source_identifier` (already present
on `raw_job_ingestions` for exactly this kind of cross-reference) or a similar discovery
reference, not by stretching this table's enum to cover a request that produced no
posting.

**Required Phase 1 database tests for `collection_run_provider_attempts` (Rev 4, item 1):**
- inserting two rows with the same `(collection_run_id, provider, source)` is **rejected**
  by the `UNIQUE` constraint;
- inserting a row with a negative `jobs_discovered`, `jobs_inserted`, `jobs_updated`, or
  `retry_count` is **rejected** by the corresponding `CHECK (... >= 0)`;
- inserting a row with `status = 'running'` and a non-`NULL` `completed_at` is
  **rejected**;
- inserting a row with a terminal `status` (`completed`/`partial`/`failed`) and a `NULL`
  `completed_at` is **rejected**;
- deleting a `CollectionRun` **cascades** to delete its `collection_run_provider_attempts`
  rows.

**Required Phase 1 database tests for `identity_conflicts`' lifecycle constraints (Rev 4,
item 4 — full column list in [DATA_MODEL.md](DATA_MODEL.md)):**
- `status` outside `('open', 'resolved', 'ignored')` is **rejected**;
- `conflict_type` outside `('evidence_mismatch', 'ambiguous_match')` is **rejected**;
- `status = 'open'` with a non-`NULL` `resolved_at` is **rejected**;
- `status IN ('resolved', 'ignored')` with a `NULL` `resolved_at` is **rejected**;
- a `NULL` `existing_value` or `NULL` `incoming_value` is **rejected** — both are always
  populated by construction (§8), so this is a hard invariant, not merely expected
  application behavior.

---

## 10. Where `ats-scrapers` and JobSpy plug in

```text
Saved Search
     │
     ▼
QueryPlanner ──► SourceQuery (per provider)
     │
     ├──► AtsScrapersProvider ──► ats_scrapers library ──► Greenhouse/Lever/Workday/Ashby/...
     │         (Pipeline B, §33 — preferred canonical source when available)
     │
     └──► JobSpyProvider ──► python-jobspy library ──► LinkedIn/Indeed/Glassdoor/Google/ZipRecruiter
               (Pipeline A, §32 — broad discovery, treated as lower-authority;
                one library call per site, independent try/except per §6.3)
     │
     ▼  (both converge here)
DiscoveryResult { jobs, errors, source_stats, ... }
     │
     ▼
ingestion/pipeline.py: RawJobIngestion → normalization/* → ingestion/identity.py (§8) → ingestion/persistence.py
     │
     ▼
Job + JobOccurrence (upserted, provenance-tagged)
```

Both adapters live entirely inside `providers/`; neither library's types cross that
boundary (§5, §54's implementation rule). If either library becomes unmaintained or
blocked by a source, the corresponding provider reports it via `ProviderHealth`/
`SourceHealth` (§6.4) and the pipeline continues with whatever providers/sources remain
healthy — no other code changes.

Two verified findings from [OPEN_SOURCE_REVIEW.md](OPEN_SOURCE_REVIEW.md) feed directly
into the adapter design:

- **`python-jobspy`'s multi-site call is not failure-isolated** (§6.3 above) —
  `JobSpyProvider` must call each configured site independently.
- **`ats-scrapers` has no `health()`-equivalent.** `AtsScrapersProvider.health()`
  (Phase 4) must be synthesized rather than delegated.

One open item for Phase 4, not yet resolved: `ats-scrapers`' `Job` model exposes
`ats_type`/`ats_id` (source + source_job_id) directly, but the adapter still needs to
confirm which of its fields cleanly maps to our `source_tenant_id` (§8) for each ATS type
— e.g. a Workday tenant subdomain or a Greenhouse board token both function as tenant
identity, but the exact field to pull varies per ATS module and needs to be verified
against `ats-scrapers`' per-scraper source at Phase 4 implementation time, not assumed
here.

The canonical upstream for `python-jobspy` is `speedyapply/JobSpy` (moved from
`cullenwatson/JobSpy`; the plain PyPI/GitHub name `jobspy` also collides with an
unrelated LGPL Redis library — pin `python-jobspy` explicitly, not `jobspy`).

---

## 11. Fixture-driven end-to-end ingestion proof (Phase 2 target)

Goal: prove the full pipeline shape with zero network calls, before any real provider
exists.

1. `providers/fixture.py` implements `DiscoveryProvider` and returns a `DiscoveryResult`
   built from JSON files in `tests/fixtures/`, covering:
   - a clean case;
   - a missing-salary case;
   - a duplicate-canonical-URL case against another fixture job (proves §8 tier 2);
   - a same-tenant-scoped-requisition case against another fixture job, `(provider,
     source, source_tenant_id, requisition_id_raw)` all matching (proves §8 tier 3,
     including that `provider`/`source` are part of the key per the Rev 3 fix);
   - a **re-observation case**: the identical natural key submitted twice with no
     conflicting evidence — must resolve to the *same* occurrence (`UPDATE`, refreshed
     `last_seen_at`), never a constraint violation or a second row (proves §8's NULL-safe
     natural key and its idempotent-upsert requirement);
   - a **NULL-tenant collision case**: two fixture payloads sharing `(provider, source,
     source_job_id)` with `source_tenant_id = NULL` (simulating LinkedIn/Indeed) — the
     second must resolve to the existing occurrence, never insert a duplicate (proves the
     `job_occurrences_natural_key_no_tenant` index actually enforces uniqueness);
   - a **same `source_job_id`, two different tenants case**: two fixture payloads with
     identical `source_job_id` but different non-null `source_tenant_id` — must produce
     **two separate `Job`s** (proves tenant scoping, not just NULL-safety);
   - an **`evidence_mismatch` case**: a payload matching an existing occurrence's natural
     key exactly, but with a normalized canonical URL that conflicts with the one already
     recorded — must **not** create a second occurrence (would violate the natural-key
     index); must produce exactly one `identity_conflicts` row
     (`conflict_type = 'evidence_mismatch'`) referencing the existing occurrence, with
     the existing occurrence's canonical URL left untouched but `last_seen_at` still
     advanced (proves §8's Rev 3 conflict-handling redesign, [ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md));
   - an **`ambiguous_match` case**: a payload whose company-scoped requisition fallback
     (tier 4) matches two distinct existing `Job`s — must create a new, standalone `Job`
     plus an `identity_conflicts` row (`conflict_type = 'ambiguous_match'`) listing both
     candidates, never guessing which one it belongs to;
   - a malformed/partial payload (produces a `RawJobIngestion` with
     `processing_status = 'parse_error'` and no `JobOccurrence`);
   - a simulated partial-provider-failure case, driven by an explicit
     `SourceQuery.sources = ["healthy_source", "broken_source"]` (§6.1) — the fixture
     provider reports `broken_source` as errored in its `DiscoveryResult.errors` (with a
     `SourceRunStats(source="broken_source", completed=False, jobs_found=0, ...)` entry)
     while `healthy_source` completes — proves jobs from the healthy source are still
     persisted (§6.3), that `DiscoveryResult.possibly_incomplete` computes correctly from
     `source_stats` alone, and (Rev 4) that this produces **exactly one successful and
     one failed row** in `collection_run_provider_attempts` (`healthy_source` →
     `status='completed'`; `broken_source` → `status='failed'` with `error_category` set).

**Additional required fixture cases (Rev 4, item 2 — `SourceCapabilities`/`QueryPlanner`
validation):**
   - an **unknown source** named in `SavedSearch.enabled_sources` for the fixture
     provider — `QueryPlanner` must reject it during planning, and `FixtureProvider
     .discover()` must **never be called** for that provider this run (assert via a
     call-count/spy check, not just the end persisted state);
   - **two fixture sources with different `SourceCapabilities`** (one with
     `supports_salary_filter=True`, one `False`, both queried with a populated
     `salary_floor`) — must produce **different `local_enforcement` entries** for the two
     sources within the same planned `SourceQuery`;
   - an **explicit empty source list** (`enabled_sources["fixture_provider"] == []`) —
     `QueryPlanner` produces no `SourceQuery` for that provider, and
     `FixtureProvider.discover()` is never called;
   - **no source-level preference** (`"fixture_provider"` absent from `enabled_sources`
     entirely) — `QueryPlanner` expands `SourceQuery.sources` to every source in that
     provider's `ProviderCapabilities.sources`.
2. `ingestion/pipeline.py` calls `FixtureProvider.discover()`, writes one
   `RawJobIngestion` row per successfully-fetched payload (raw payload = the fixture
   JSON, `parser_version` set), then runs normalization, `ingestion/identity.py`'s
   resolution (§8), and `ingestion/persistence.py`'s upsert logic.
3. `persistence.py` resolves each `DiscoveredJob` to a `Job` (creating one if no
   deterministic match) and a `JobOccurrence`, linking back to its `RawJobIngestion` via
   `raw_job_ingestions.job_occurrence_id` (§9 — no reverse pointer). For the two conflict
   cases, `job_occurrence_id` is still populated (pointing at the existing occurrence for
   `evidence_mismatch`, or the newly-created one for `ambiguous_match`) — see
   [ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md) for why it's never left
   `NULL` in either conflict case.
4. A `CollectionRun` row records the run's provider list, counts, and duration.
5. Tests assert: the canonical-URL and tenant-scoped-requisition duplicate cases each
   collapse into one `Job` with two `JobOccurrence`s; the re-observation and
   NULL-tenant-collision cases each resolve to one occurrence with no duplicate insert;
   the two-tenants-same-source_job_id case produces two distinct `Job`s; the
   `evidence_mismatch` case leaves the existing occurrence's disputed field untouched and
   creates exactly one `identity_conflicts` row; the `ambiguous_match` case creates a new
   `Job` plus an `identity_conflicts` row listing both candidates; the missing-salary
   fixture ends up with `salary_min/max = NULL` (never `0`); the parse-error fixture
   produces a `RawJobIngestion` with no linked occurrence; the partial-failure fixture
   persists the healthy source's jobs, records the failed source's error, and produces
   one `completed` and one `failed` `collection_run_provider_attempts` row; the
   unknown-source case rejects at planning time with zero `discover()` calls; the
   differing-filter-capabilities case produces two distinct `local_enforcement` entries;
   the empty-source-list case produces zero `discover()` calls and zero
   `collection_run_provider_attempts` rows for that provider; the no-preference case
   expands to every configured fixture source; re-running the full fixture set is
   idempotent (no duplicate rows, `last_seen_at` advances).

This is the acceptance test for Phase 1+2 combined — see §13.

---

## 12. Phase 0 acceptance criteria

- `docker-compose up` starts PostgreSQL and the FastAPI backend.
- `alembic upgrade head` runs cleanly against a fresh database.
- `GET /health` returns 200 and reports DB connectivity.
- `pytest` runs (even with zero real tests yet) via CI-equivalent local command.
- `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/ROADMAP.md`,
  `docs/SOURCE_CONNECTORS.md`, `docs/OPEN_SOURCE_REVIEW.md` exist and are current (this
  deliverable).
- No provider, normalization, or scoring code exists yet — Phase 0 is scaffolding only.

## 13. Phase 1 acceptance criteria (strengthened, Rev 2)

- Alembic migrations create: `users`, `candidate_profiles`, `candidate_skills`,
  `saved_searches` (+ `saved_search_titles`, `saved_search_locations`), `companies`,
  `jobs`, `job_occurrences`, `raw_job_ingestions`, `identity_conflicts`,
  `collection_runs`, `collection_run_provider_attempts`, `user_jobs`, `job_notes`. (Full
  field list and constraints: [DATA_MODEL.md](DATA_MODEL.md).) **Both
  `identity_conflicts` and `collection_run_provider_attempts` are migrated in Phase 1**
  (item 4 / Rev 3, and Rev 4 respectively) even though neither is written to until
  Phase 2's fixture proof — unlike `duplicate_groups` (genuinely deferred to Phase 6,
  since nothing before then produces fuzzy-match groupings, and `job_skills`/`contacts`/
  `notifications`, deferred for the same reason), Phase 2's fixture proof needs both
  tables to already exist to write their `evidence_mismatch`/`ambiguous_match` and
  per-source partial-failure/attempt rows into. **`collection_run_provider_attempts` is
  migrated in Phase 1 and first written to in Phase 2** — Phase 9 (the scheduler) is its
  first *real* (non-fixture) writer and extends how it's used for scheduled runs; Phase 9
  does not introduce this table. Phase 12 consumes its accumulated historical rows for
  volume-trend/anomaly analysis.
- **Identity-related columns and indexes are tenant/company-scoped and NULL-safe, not
  bare.** `job_occurrences` carries `source_tenant_id` and `requisition_id_raw`; the
  natural key is enforced by **two separate partial unique indexes**
  (tenant-present / tenant-absent, §8) rather than one index that would silently fail to
  enforce uniqueness for NULL-tenant sources; the tenant-scoped requisition lookup index
  includes `provider`/`source`, not just `source_tenant_id` (§8, item 2). No column or
  index anywhere treats a raw requisition ID as independently unique.
- **No circular foreign keys.** `raw_job_ingestions.job_occurrence_id` is the only FK
  between that pair of tables; `job_occurrences` has no pointer back (§9).
- **Identity-conflict tests exist**: the three cases in [§8](#8-deterministic-identity-resolution)'s
  "Required Phase 1 database tests" (NULL-tenant collision rejected, same
  `source_job_id` under two tenants allowed, re-ingestion resolves the existing row) all
  pass against a real Postgres, plus the `evidence_mismatch`/`ambiguous_match` fixture
  cases from [§11](#11-fixture-driven-end-to-end-ingestion-proof-phase-2-target) prove no
  second occurrence is ever created against an existing natural key.
- **`identity_conflicts` lifecycle tests exist** (§9's "Required Phase 1 database tests"):
  invalid `status`/`conflict_type` values rejected, `open` ⟺ `resolved_at IS NULL`
  enforced both directions, `existing_value`/`incoming_value` `NOT NULL` enforced.
- **`collection_run_provider_attempts` tests exist** (§9's "Required Phase 1 database
  tests"): duplicate `(collection_run_id, provider, source)` rejected, negative counters
  rejected, `running` with `completed_at` set rejected, terminal status without
  `completed_at` rejected, `CollectionRun` deletion cascades to its attempt rows.
- **Migrations encode every constraint documented in [DATA_MODEL.md](DATA_MODEL.md)'s
  constraints section** — uniqueness, `CHECK`, and `ON DELETE` behavior are asserted in
  the migration, not left to application-code discipline alone.
- **Both migration directions are tested**: `alembic upgrade head` and `alembic
  downgrade base` both run cleanly against a fresh database in CI/local test runs, round
  trip included (upgrade → downgrade → upgrade again).
- **Database constraint tests exist** (`tests/db/`, run against a real Postgres, not
  mocked): each documented unique/check constraint has at least one test proving the
  database itself rejects a violating insert/update (not just that application code
  happens to avoid producing one).
- **`UserJob` invariant tests exist**: the `status`/`applied_at` `CHECK` constraint
  (ADR 0006) is proven to reject an inconsistent row at the database level, and the
  single service-layer status-transition function is tested for the pairing behavior it's
  responsible for.
- Each model has a factory/fixture usable from tests without hitting any network.
- A seeded `CandidateProfile` and at least one `SavedSearch` can be created, fetched, and
  updated through direct service-layer calls (API routes not required until Phase 8).
- Unit tests cover: `Job`/`JobOccurrence` creation and the upsert-does-not-duplicate case,
  and `UserJob` state surviving a re-ingestion of its parent `Job` (proves user state is
  never clobbered by source refresh, per §37).
- **No provider or external-library implementation exists yet.** `ats-scrapers` and
  `python-jobspy` are not installed or imported anywhere in Phase 1 — Phase 1 proves the
  schema and persistence layer only, against fixtures/factories.
- **No live-network tests run in the default `pytest` invocation.** Anything that would
  reach a real external service lives under `tests/integration/` and is excluded from the
  default test command (§47).
