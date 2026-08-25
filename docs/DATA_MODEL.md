# Data Model

Companion to [ARCHITECTURE.md](ARCHITECTURE.md). Covers the Phase 1 schema in full, plus
the shape of tables introduced in later phases so foreign keys and naming stay consistent
when they're added. "Phase 1" tables are built now; "Later" tables are documented but not
migrated until their phase.

**Rev 2 changes** (see [ARCHITECTURE.md's revision history](ARCHITECTURE.md#revision-history)
for the full review this responds to): added tenant/company-scoped identity fields to
`job_occurrences` instead of relying on a bare requisition ID (§ADR 0004); removed the
circular FK between `job_occurrences` and `raw_job_ingestions` (§ADR 0005); added an
explicit [Phase 1 constraints & indexes](#phase-1-constraints--indexes) section; added the
`collection_run_provider_attempts` later-table (§ADR 0005); rewrote `user_jobs` to remove
the independent `applied` boolean and make status/applied_at internally consistent
(§ADR 0006); fixed a stray reference to a nonexistent "Phase 30."

**Rev 3 changes** (second design review, semantic/database corrections): fixed a
NULL-distinctness bug in `job_occurrences`' natural key by splitting it into two partial
unique indexes (§ADR 0004); scoped the tenant-requisition lookup index to include
`provider`/`source` (§ADR 0004); added a new Phase 1 table, `identity_conflicts`, and
removed `identity_conflict` from `duplicate_groups`' reason enum — the two concepts are
now mechanically separate (§ADR 0007, §ADR 0002); renamed
`raw_job_ingestions.retrieval_status` to `processing_status` with a narrower,
payload-only enum (§ADR 0005/0007); normalized `companies.domain` before its uniqueness
constraint applies; added `job_notes.updated_at`; documented a minimum supported
PostgreSQL version.

**Rev 4 changes** (third design review): moved `collection_run_provider_attempts` from a
Phase 9/12 "later table" into a **Phase 1** table with its full constraint set — status
lifecycle `CHECK`s, non-negative counters, `UNIQUE (collection_run_id, provider,
source)` — since Phase 2's fixture proof already needs to persist per-source
partial-failure telemetry (§ADR 0003, §ADR 0005); added `saved_searches.enabled_sources`
(jsonb) for unambiguous source-level selection; added `identity_conflicts` lifecycle
`CHECK` constraints (status/conflict_type enums, `open`⟺`resolved_at IS NULL`,
`existing_value`/`incoming_value NOT NULL`); completed `companies.domain` normalization
(IDNA/punycode, credentials/port stripping, an explicit malformed-input rule);
`collection_runs.providers_enforced_locally`'s documented shape is now explicitly
`{provider: {source: [field, ...]}}`, reflecting that filter enforcement is decided
per source (§ARCHITECTURE.md §6.6), not once per provider.

**Rev 5 changes** (first Phase 1 implementation slice): `users` now explicitly documents
`updated_at` (previously omitted despite the global convention below) and the
normalized-email constraints — a `CHECK` requiring `email = lower(trim(email))`, a
`CHECK` rejecting an empty-after-trim email, and a unique index on `lower(email)` — that
were implemented in `backend/migrations/versions/0002_users.py` and
`backend/app/db/models/user.py`.

**Rev 6 changes** (first Phase 1 correction pass, per independent review): fixed a real
whitespace-normalization mismatch between the Python validator and the PostgreSQL CHECK
constraints — see the `users` table's own section below for the corrected, explicit
four-character whitespace set now shared by both. **Rev 6a** (second correction pass):
the fix itself moved from an in-place rewrite of already-applied migration `0002` (which
the first correction pass did, and which a review correctly flagged as creating
undetectable schema drift on any database that had already applied `0002`) into a new
forward migration, `0003` — `0002` is restored to describe exactly what it always did;
`0003` is what actually changes the CHECK constraints on a database that already has the
table.

**Rev 7 changes** (second Phase 1 implementation slice, `candidate_profiles`): this
table's column list below did not previously state three product rules, each resolved by
explicit approval before migration `0004` was written rather than inferred silently: the
five `text[]` columns are nullable with no server default, and NULL (never specified) is
distinct from a future empty-array write (explicitly specified as none); `years_experience`,
`salary_expectation_min`, and `salary_expectation_max` each have a `CHECK` requiring the
value be NULL or `>= 0`; and `salary_expectation_min`/`salary_expectation_max` have an
additional `CHECK` requiring `salary_expectation_min <= salary_expectation_max` whenever
both are non-null.

**Rev 8 changes** (third Phase 1 implementation slice, `candidate_skills`): this table's
column list below omitted `created_at`/`updated_at` entirely despite the global
convention stated below ("all tables have `created_at`/`updated_at` unless noted" — this
table was never marked as an exception); both are now added, consistent with `users` and
`candidate_profiles`. `skill` is normalized the same way `email` is — trimmed of exactly
the four-character whitespace set (space, tab, LF, CR), enforced by database `CHECK`s in
addition to an ORM validator — but, unlike `email`, `skill` is **not** lowercased; its
case is preserved, and case-insensitive uniqueness is enforced separately by a functional
index on `lower(skill)`, scoped per `candidate_profile_id`. `priority` is not null (this
table's own convention: only `category` is documented as nullable) and restricted by
`CHECK` to `must_have` / `preferred`. `category` remains nullable free text with no enum
`CHECK` — the documented examples are illustrative, not a closed set.

**Rev 9 changes** (fourth Phase 1 implementation slice, `saved_searches` — parent table
only; `saved_search_titles`/`saved_search_locations` remain future slices): this table's
column list below did not previously state several product rules, resolved by explicit
approval before migration `0006` was written:
- Every `text[]` column is nullable with no server default (NULL = never specified),
  same convention as `candidate_profiles`.
- `name` is normalized the same way `skill` is (trim-only, case preserved, matching
  `CHECK`s) — but has no uniqueness requirement, unlike `skill`.
- `salary_floor`, `preferred_salary`, and `recency_limit_hours` each have a `CHECK`
  requiring the value be NULL or `>= 0`, plus a `CHECK` requiring
  `salary_floor <= preferred_salary` whenever both are non-null.
- `radius_miles` is **deliberately unconstrained**: plain `numeric`, no precision/scale,
  no non-negative `CHECK` — an explicit product decision, not an oversight (contrast with
  the integer numeric fields above, which do get non-negative `CHECK`s).
- `enabled_sources` and `scoring_weights` (the first `jsonb` columns in this schema) are
  each restricted by a `CHECK` requiring the stored value be a top-level JSON *object*
  when non-null; deeper shape is a Phase 2 `QueryPlanner`-time concern
  ([ARCHITECTURE.md §6.5–6.6](ARCHITECTURE.md#65-savedsearchenabled_sources--unambiguous-source-selection)),
  not a Phase 1 database constraint.
- `created_at`/`updated_at` are added, per the same previously-omitted-despite-the-global-
  convention gap already fixed for `users` (Rev 5) and `candidate_skills` (Rev 8).

Conventions used throughout:

- **Minimum supported PostgreSQL version: 16.** See
  [ARCHITECTURE.md §2](ARCHITECTURE.md#2-architectural-style-confirmed) for why. Notably,
  this schema deliberately does *not* rely on PG15's `NULLS NOT DISTINCT` — see the
  `job_occurrences` natural key below, which uses two plain partial unique indexes
  instead, for portability and readability.
- All primary keys are `UUID` (generated app-side or via `gen_random_uuid()`), not
  auto-increment integers — avoids leaking row counts and makes multi-environment data
  merges (dev fixture → shared db) collision-free.
- All tables have `created_at` / `updated_at` timestamps (`timestamptz`, UTC) unless noted.
- **A field being absent/unknown is always `NULL`, never `0`, `""`, or a sentinel.** This
  is load-bearing for §20/§35 — a `salary_min` of `0` and a `salary_min` of `NULL` mean
  different things (confirmed-zero vs. unknown) and must never be conflated.
- Every table's uniqueness/CHECK/FK behavior is additionally summarized in one place in
  [Phase 1 constraints & indexes](#phase-1-constraints--indexes) so it can be checked off
  against migrations directly, in addition to being noted inline per table.

---

## Phase 1 tables

### `users`
**Implemented** (`backend/app/db/models/user.py`; migrations `0002` creates the table,
`0003` corrects the email-normalization CHECK constraints — see below). No auth system yet
(no password/session/token columns) — this table is identity only; shape exists so every
user-scoped table already has a real foreign key instead of a future migration.

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`), not a DB-side default |
| email | text, not null | normalized before storage — see below |
| created_at | timestamptz, not null | `server_default now()` |
| updated_at | timestamptz, not null | `server_default now()`, and reset to `now()` by the ORM (`onupdate`) on every update — see note below |

**Email normalization:** trimmed and lowercased, nothing more — no dot-removal,
plus-addressing, or other provider-specific transforms (e.g. Gmail-style aliasing), and
no RFC-822 validation. **The exact covered whitespace set is space, tab, line feed, and
carriage return (ASCII `0x20`/`0x09`/`0x0A`/`0x0D`) — nothing else.** A SQLAlchemy
`@validates` normalizer covers the ORM write path, but the database is the authoritative
backstop, not the validator:
- `CHECK (email = lower(trim(both E'\t\n\r ' from email)))` — rejects any row (including
  a write that bypasses the ORM) whose stored value isn't already normalized.
- `CHECK (trim(both E'\t\n\r ' from email) <> '')` — rejects empty or
  covered-whitespace-only email.
- `UNIQUE` functional index on `lower(email)` — case-insensitive uniqueness. A plain
  `UniqueConstraint` can't express this (constraints only cover literal columns, not an
  expression), so this is an `Index(..., unique=True)`, not a table constraint. Because
  the CHECK constraints above guarantee a stored row is *already* fully trimmed and
  lowercased, a whitespace-wrapped duplicate (e.g. `"\tfoo@x.com\n"` alongside
  `"foo@x.com"`) can never be inserted in the first place — the CHECK rejects it before
  the index is ever consulted, not merely something the index happens to also catch.
- No `CITEXT` — kept explicit/portable through the index and CHECK above instead of an
  extension-dependent column type.

**Why an explicit character set, not bare `trim()`/`.strip()` (corrected — this was a
real bug):** PostgreSQL's `trim(email)` with no explicit character list only strips
plain spaces; Python's bare `str.strip()` strips a much broader Unicode whitespace set
(tabs, newlines, and more). Relying on the two "matching by default" let a value like
`"\tperson@x.com\t"` (tab-wrapped) pass the CHECK constraint outright — Postgres's
default `trim()` left it unchanged on both sides of the `=`, so the equality trivially
held. Both the ORM validator (`_COVERED_WHITESPACE = " \t\n\r"` in
`app/db/models/user.py`) and the CHECK constraints (as of migration `0003` — `0002`
itself still reflects the original, buggy expression, on purpose; see below) now name the
identical four-character set explicitly, so this can't silently drift apart again. If
this set is ever revised, update both sides together, add a new forward migration (not
another in-place rewrite), and add a regression test for the newly-covered character.

**Why the fix is migration `0003`, not a rewrite of `0002`:** `0002` had already been
applied to at least one real database (the `jobgoblin` development database) before this
bug was found. Rewriting `0002`'s DDL in place — the first attempt at this fix — left
`0002` in the repository describing constraints that didn't match what any
already-migrated database actually had, with no later revision to carry a database that
was already at `0002` forward; `alembic upgrade head` and `alembic check` both report
nothing to do, silently. `0003` (`down_revision = "0002"`) instead drops and recreates
the two CHECK constraints explicitly, is reversible (its `downgrade()` restores the
original bare-`trim` expressions), and every database — whether starting from `0001`
fresh or already sitting at `0002` — reaches the same corrected schema by running
`alembic upgrade head` normally.

**`updated_at` caveat:** advanced via SQLAlchemy's `onupdate=func.now()`, which appends
`now()` to any UPDATE the ORM issues for a changed row. This does **not** fire for a
write that bypasses the ORM (e.g. a raw SQL `UPDATE`) — no database trigger exists for
this yet. Acceptable for this slice (nothing writes to `users` outside the ORM); would
need a trigger if a future raw-SQL write path to this table is ever added.

### `candidate_profiles`
**Implemented** (`backend/app/db/models/candidate_profile.py`; migration `0004`, `down_revision
= "0003"`). "Who is the user professionally" (§23). One-to-one with `users` for now; kept
as its own table (not columns on `users`) because it's the thing a future
multi-profile/multi-resume feature would key off of.

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`), not a DB-side default |
| user_id | UUID FK → users, `ON DELETE CASCADE`, **UNIQUE**, not null | enforces one-to-one while the relationship stays 1:1; a future multi-profile feature would need a migration to drop this uniqueness, which is an acceptable/expected cost when that feature actually lands |
| target_role_families | text[], nullable | free-form until Phase 3 taxonomy exists; NULL = never specified (see Rev 7 note above) |
| years_experience | int, nullable | `CHECK (years_experience IS NULL OR years_experience >= 0)` |
| education | text, nullable | |
| certifications | text[], nullable | NULL = never specified |
| clearance | text, nullable | |
| preferred_industries | text[], nullable | NULL = never specified |
| excluded_industries | text[], nullable | NULL = never specified |
| preferred_locations | text[], nullable | NULL = never specified |
| relocation_willingness | boolean, nullable | nullable = unknown |
| remote_preference | text, not null | enum: remote / hybrid / onsite / no_preference — `CHECK (remote_preference IN (...))` |
| salary_expectation_min | int, nullable | annualized; `CHECK (salary_expectation_min IS NULL OR salary_expectation_min >= 0)` |
| salary_expectation_max | int, nullable | annualized; `CHECK (salary_expectation_max IS NULL OR salary_expectation_max >= 0)`, plus `CHECK (salary_expectation_min IS NULL OR salary_expectation_max IS NULL OR salary_expectation_min <= salary_expectation_max)` |
| created_at | timestamptz, not null | `server_default now()` |
| updated_at | timestamptz, not null | `server_default now()`, reset to `now()` by the ORM (`onupdate`) on every update |

### `candidate_skills`
**Implemented** (`backend/app/db/models/candidate_skill.py`; migration `0005`,
`down_revision = "0004"`). Normalized child table rather than an array column, because
skills need independent matching against the taxonomy (Phase 3) and a weight/priority per
skill.

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`), not a DB-side default |
| candidate_profile_id | UUID FK → candidate_profiles, `ON DELETE CASCADE`, not null | |
| skill | text, not null | raw or already-canonical string; taxonomy resolution is Phase 3; normalized before storage — see below |
| category | text, nullable | free text: language / framework / cloud / tool / etc. — examples, not an enforced enum |
| priority | text, not null | enum: must_have / preferred — `CHECK (priority IN (...))` |
| created_at | timestamptz, not null | `server_default now()` |
| updated_at | timestamptz, not null | `server_default now()`, reset to `now()` by the ORM (`onupdate`) on every update |

**Skill normalization:** trimmed of exactly the same four-character whitespace set as
`users.email` (space, tab, line feed, carriage return — ASCII `0x20`/`0x09`/`0x0A`/`0x0D`)
— but, unlike `email`, **never lowercased**; case is preserved for display. A SQLAlchemy
`@validates` normalizer covers the ORM write path, but the database is the authoritative
backstop, not the validator:
- `CHECK (skill = trim(both E'\t\n\r ' from skill))` — rejects any row (including a write
  that bypasses the ORM) whose stored value isn't already trimmed.
- `CHECK (trim(both E'\t\n\r ' from skill) <> '')` — rejects empty or
  covered-whitespace-only skill.
- `UNIQUE` functional index on `(candidate_profile_id, lower(skill))` — case-insensitive,
  scoped per profile, so "Python" and "python" can't both be added to the same profile as
  separate rows before the Phase 3 taxonomy exists to catch that. A plain `UniqueConstraint`
  can't express `lower(skill)`, so this is an `Index(..., unique=True)`, not a table
  constraint. Because the CHECK constraints above guarantee a stored row is already fully
  trimmed, a whitespace-wrapped duplicate can never be inserted in the first place — the
  CHECK rejects it before the index is ever consulted.

### `saved_searches`
**Implemented** (`backend/app/db/models/saved_search.py`; migration `0006`,
`down_revision = "0005"` — parent table only, see Rev 9 note above). "What am I looking
for right now" (§24).

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`), not a DB-side default |
| user_id | UUID FK → users, `ON DELETE CASCADE`, not null | non-unique `INDEX` for lookup |
| name | text, not null | normalized before storage — see below |
| excluded_titles | text[], nullable | NULL = never specified |
| radius_miles | numeric, nullable | deliberately unconstrained — no precision/scale, no `CHECK` |
| remote_rules | text, not null | enum: remote_only / hybrid_ok / onsite_ok / any |
| salary_floor | int, nullable | hard filter; `CHECK (salary_floor IS NULL OR salary_floor >= 0)` |
| preferred_salary | int, nullable | soft/scoring signal; `CHECK (preferred_salary IS NULL OR preferred_salary >= 0)`, plus `CHECK (salary_floor IS NULL OR preferred_salary IS NULL OR salary_floor <= preferred_salary)` |
| industries | text[], nullable | NULL = never specified |
| employment_types | text[], nullable | NULL = never specified |
| seniority | text[], nullable | NULL = never specified |
| must_have_skills | text[], nullable | NULL = never specified |
| preferred_skills | text[], nullable | NULL = never specified |
| excluded_keywords | text[], nullable | NULL = never specified |
| preferred_companies | text[], nullable | NULL = never specified |
| excluded_companies | text[], nullable | NULL = never specified |
| recency_limit_hours | int, nullable | `CHECK (recency_limit_hours IS NULL OR recency_limit_hours >= 0)` |
| enabled_providers | text[], nullable | provider names from ProviderRegistry — which providers run at all; NULL = never specified |
| enabled_sources | jsonb, nullable | **new in Rev 4** — supplements (does not replace) `enabled_providers`. Shape: `{"jobspy": ["linkedin", "indeed", "glassdoor"], "ats_scrapers": ["greenhouse", "lever", "workday"]}`. A provider key absent here (but present in `enabled_providers`) means "no source-level preference — use every source that provider currently supports"; a provider key present with an empty list means "run this provider with zero sources this cycle." Validated against `ProviderRegistry`/`ProviderCapabilities` at query-planning time (see [ARCHITECTURE.md §6.5–6.6](ARCHITECTURE.md#65-savedsearchenabled_sources--unambiguous-source-selection)) — unknown source names fail validation before any provider call, not silently ignored. `CHECK (enabled_sources IS NULL OR jsonb_typeof(enabled_sources) = 'object')` — Phase 1 enforces only the top-level JSON shape, not key/value validity |
| polling_schedule | text, not null | enum: manual / hourly / daily / weekly |
| scoring_weights | jsonb, nullable | overrides matching/weights.py defaults; same top-level-object `CHECK` as `enabled_sources` |
| is_active | boolean, not null | `server_default true` |
| created_at | timestamptz, not null | `server_default now()` |
| updated_at | timestamptz, not null | `server_default now()`, reset to `now()` by the ORM (`onupdate`) on every update |

**Name normalization:** trimmed of exactly the same four-character whitespace set as
`candidate_skills.skill` (space, tab, line feed, carriage return) — case preserved, no
uniqueness requirement (unlike `skill`, there is no `UNIQUE`/functional index on `name`;
a user may have multiple saved searches sharing a name).

**Mutable-collection tracking:** every `text[]` column is wrapped with
`MutableList.as_mutable`, and both `jsonb` columns are wrapped with
`MutableDict.as_mutable`, so an in-place `.append()`/`.remove()`/`dict[key] = value` on a
loaded value is tracked and actually written on commit — the array-mutation gap caught on
`candidate_profiles` (Rev 7/8 correction), applied proactively here from the start.
`MutableDict` (like `MutableList`) only instruments the wrapped column's own top-level
`__setitem__`/`__delitem__` — mutating a value already nested *inside* one of these jsonb
columns (e.g. a dict nested inside `scoring_weights`) is invisible to the unit-of-work and
is still silently dropped on commit; see the model's own docstring and
`test_mutating_a_nested_jsonb_value_is_not_tracked`.

### `saved_search_titles`
Split out (rather than an array column on `saved_searches`) because titles need
per-entry alias expansion against `taxonomy/titles.yaml` in Phase 3, and because a title
can independently carry "this is the primary title" vs. "this is an acceptable alias."

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| saved_search_id | UUID FK → saved_searches, `ON DELETE CASCADE` | |
| title | text | |
| is_primary | boolean | |

Unique constraint: `(saved_search_id, lower(title))`.

### `saved_search_locations`
Split out for the same reason as titles — each location independently carries its own
radius/remote override, and future geocoding work (master spec §30) keys off individual
location rows rather than a whole saved search.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| saved_search_id | UUID FK → saved_searches, `ON DELETE CASCADE` | |
| location_text | text | e.g. "Ashburn, VA" |
| latitude | numeric | nullable until geocoded |
| longitude | numeric | nullable until geocoded |
| radius_miles_override | numeric | nullable, falls back to saved_searches.radius_miles |

Unique constraint: `(saved_search_id, lower(trim(location_text)))` — prevents accidental
duplicate location rows from differing only in case/whitespace; does not attempt to
dedupe genuinely different textual representations of the same place (e.g. "Ashburn, VA"
vs. "Ashburn, Virginia") — that's a normalization/geocoding concern, not a uniqueness
concern, and geocoding hasn't run yet at insert time.

### `companies`
Deduplicated employer identity. **This is deliberately not "solved" by a single unique
constraint** — company identity resolution is a hard, ongoing problem, not a one-time
schema decision:

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| name | text | |
| normalized_name | text | indexed (non-unique — see below) |
| domain | text | nullable |
| homepage_url | text | nullable |
| career_page_url | text | nullable |
| industry | text | nullable |
| duplicate_of_company_id | UUID | nullable, self-referential FK, `ON DELETE SET NULL` — see below |

**Domain normalization (Rev 3, item 8b; completed Rev 4, item 3):** `domain` is always
stored pre-normalized by `normalization/company.py::normalize_domain()` before any
insert/update touches this column. Full algorithm:
1. Lowercase the input.
2. Strip the scheme (`http://`, `https://`, or any other `scheme://` prefix).
3. Strip userinfo/credentials (`user:pass@`) if present.
4. Strip the port (`:8080`), path, query string, and fragment — only the host remains.
5. Strip a leading `www.`.
6. Strip a trailing dot (the DNS root-label separator, e.g. `acme.com.` → `acme.com`).
7. Convert internationalized domain names to their canonical IDNA ASCII (punycode)
   representation (e.g. `café.com` → `xn--caf-dma.com`), so a Unicode domain and its
   punycode-encoded equivalent always normalize to the same stored value.
8. Validate the result is a syntactically plausible hostname (non-empty, valid label
   structure). **Explicit rule for malformed input:** if the input cannot be parsed into
   a valid hostname at all (empty string, garbage input, a URL with no discernible host),
   `normalize_domain()` returns `None` rather than raising — the caller stores `NULL` in
   `companies.domain`, the same representation already used for "domain unknown"
   elsewhere in this schema. This is a deliberate choice, not a fallback of convenience:
   ingestion must never abort or crash a batch because one company's source data had a
   malformed URL (consistent with §17/§32's requirement that provider/parsing failures
   stay isolated); raising an exception here would do exactly that. Rejecting outright
   (as opposed to normalizing to `NULL`) was considered and rejected for the same reason
   — this is the one explicitly documented rule the acceptance tests below check.

Comparing raw, differently-cased, or differently-encoded domain strings (`Acme.com` vs
`acme.com` vs `www.acme.com` vs a Unicode/punycode pair) as if they were distinct would
silently defeat the identity signal below. The uniqueness constraint is additionally
declared as `UNIQUE (lower(domain)) WHERE domain IS NOT NULL` (not a bare
`UNIQUE (domain)`) so the database itself doesn't depend on application-code discipline
for the casing half of normalization — defense in depth on top of `normalize_domain()`
already storing a lowercased value, consistent with this project's general preference
for the database enforcing hard invariants (e.g.
[ADR 0006](DECISIONS/0006-userjob-workflow-invariants.md)).

**Acceptance tests for `normalize_domain()` (Rev 4):**
- `Acme.com` and `acme.com` normalize to the same value and collide under the unique
  index.
- `www.acme.com` and `acme.com` normalize to the same value and collide.
- A Unicode domain and its punycode-equivalent (e.g. `café.com` / `xn--caf-dma.com`)
  normalize to the same value and collide.
- Two different valid domains (e.g. `acme.com` and `acme.io`) remain distinct — the
  normalization doesn't over-collapse unrelated domains.
- A malformed input (empty string, a bare path with no host, unparseable garbage)
  normalizes to `None`/`NULL`, per the explicit rule above — it is not rejected with an
  exception, and it is not stored as the malformed literal text.

**Conservative collision behavior (Rev 2):** a normalized domain match is a reasonably
strong identity signal and worth enforcing at the database level. `normalized_name`
deliberately gets **no** uniqueness
constraint, only a plain index for lookup/search: company names collide too often
(different companies sharing a common name, or the same company appearing under
slightly different formal names across sources) for a name-only unique constraint to be
safe. When ingestion can't confidently match an existing company by domain, it creates a
**new** `companies` row rather than guessing via name similarity — accepting duplicate
company rows as a known, visible limitation rather than silently merging on a weak
signal, consistent with the project's "never silently merge" principle applied at the
company level too. `duplicate_of_company_id` exists so a future (post-MVP) manual
reconciliation workflow has somewhere to record "these two company rows are actually the
same employer" without deleting either row or rewriting every `jobs.company_id` that
points at the one being retired; it is not populated or enforced by anything in Phase 1–6
— it's schema reserved for a phase that isn't scoped yet.

### `jobs`
The canonical opening (§20). Fields here are **resolved** values — see
[Provenance](#provenance) below for how they're chosen when occurrences disagree.
Every resolved field has a paired `*_provenance` and, for anything not sourced verbatim,
a pointer to which occurrence supplied it — modeled here as a single
`field_provenance jsonb` column (`{"salary_min": {"source": "explicit_source", "occurrence_id": "..."}, ...}`)
rather than one provenance column per field, to avoid a ~20-column-wide provenance
shadow-table for Phase 1. This can be split into a normalized `job_field_provenance`
table later without changing anything upstream, if per-field querying becomes common.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| requisition_id | text | nullable, **resolved display value only — not an identity/matching key** (Rev 2: see [ARCHITECTURE.md §8](ARCHITECTURE.md#8-deterministic-identity-resolution) and [ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md); the actual matching key lives on `job_occurrences`, scoped by tenant or company) |
| canonical_url | text | nullable, resolved display value — the identity-matching comparison happens on `job_occurrences.canonical_url_normalized`, not this column |
| preferred_apply_url | text | nullable |
| company_id | UUID FK → companies, `ON DELETE RESTRICT` | restrict, not cascade/set-null — deleting a company that still has jobs attached must be an explicit, deliberate reconciliation step (see `companies.duplicate_of_company_id` above), never an accidental cascade |
| title | text | nullable |
| normalized_title | text | nullable until Phase 3 |
| job_family | text | nullable |
| department | text | nullable |
| team | text | nullable |
| description_raw | text | nullable |
| description_clean | text | nullable |
| location_raw | text | nullable |
| city / state / country / postal_code | text | all nullable |
| latitude / longitude | numeric | nullable |
| remote_type | text | enum: remote / hybrid / onsite / unknown |
| employment_type | text | nullable |
| seniority | text | nullable |
| contract_type | text | nullable |
| shift | text | nullable |
| salary_min / salary_max | int | nullable, as originally stated |
| salary_currency | text | nullable |
| salary_period | text | enum: hourly / daily / monthly / annual |
| annualized_salary_min / max | int | nullable, derived |
| compensation_text | text | nullable, original string |
| compensation_explicit | boolean | true = employer-stated, false = third-party estimate |
| years_experience_min / max | int | nullable |
| education_requirement | text | nullable |
| certifications | text[] | |
| clearance_requirement | text | nullable |
| visa_sponsorship_status | text | nullable |
| travel_requirement | text | nullable |
| posted_at | timestamptz | nullable — original source date, if any |
| first_seen_at | timestamptz | earliest across all occurrences |
| last_seen_at | timestamptz | latest across all occurrences |
| application_deadline | timestamptz | nullable |
| field_provenance | jsonb | see above |
| duplicate_group_id | UUID | nullable, FK → duplicate_groups (Phase 6), `ON DELETE SET NULL` |

### `job_occurrences`
One observed appearance on one source (§18). **Rev 2** adds the fields identity
resolution actually needs (§ADR 0004) and removes the circular FK to
`raw_job_ingestions` (§ADR 0005).

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| job_id | UUID FK → jobs, `ON DELETE CASCADE` | |
| provider | text | e.g. "ats_scrapers", "jobspy" |
| source | text | e.g. "greenhouse", "linkedin" |
| source_tenant_id | text | **new in Rev 2** — nullable. The ATS-tenant or employer-account identifier *within* `(provider, source)`: a Workday tenant subdomain, a Greenhouse board token, a Lever company slug. Null for sources with no tenant concept (e.g. a LinkedIn/Indeed posting isn't scoped to a "tenant" beyond the site itself). This is what makes requisition-ID matching safe — see [ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md) |
| source_job_id | text | nullable |
| requisition_id_raw | text | **new in Rev 2** — nullable. The requisition ID exactly as reported by *this* source, unscoped by itself; only ever compared in combination with `source_tenant_id` or a resolved `company_id`, never alone |
| source_url | text | as provided by the source |
| source_url_normalized | text | **new in Rev 2** — normalized per [ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md); used as the fallback natural-key component when `source_job_id` is absent |
| apply_url | text | nullable |
| canonical_url | text | nullable, as provided by the source |
| canonical_url_normalized | text | **new in Rev 2** — normalized per ADR 0004; this is the column identity resolution actually compares, not the raw `canonical_url` |
| first_seen_at | timestamptz | for *this* occurrence |
| last_seen_at | timestamptz | updated every time this occurrence is re-observed |
| posted_at | timestamptz | nullable, source-reported |
| applicant_count | int | nullable, source-specific — never merged across sources |
| applicant_count_text | text | nullable, original string (e.g. "over 200 applicants") |
| is_active | boolean | false once the posting disappears from this source |

**Removed in Rev 2:** `last_raw_ingestion_id`. Rev 1 gave this table a FK to
`raw_job_ingestions` *and* gave `raw_job_ingestions` a FK back — a circular reference
between the two tables. The relationship now points one way only
(`raw_job_ingestions.job_occurrence_id`); "the latest ingestion for this occurrence" is a
derived query (`ORDER BY fetched_at DESC LIMIT 1`, backed by an index — see
[constraints](#phase-1-constraints--indexes) below and
[ADR 0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md)), not a stored pointer
that has to be kept in sync.

**Unique constraints (Rev 3 fix — now two separate partial indexes, not one; see
[ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md) for the full precedence order
these support and why a single combined index was broken):**

```sql
-- Tenant-scoped sources (Workday, Greenhouse, Lever, ...)
UNIQUE (provider, source, source_tenant_id, source_job_id)
  WHERE source_job_id IS NOT NULL AND source_tenant_id IS NOT NULL

-- Sources with no tenant concept (LinkedIn, Indeed, ...)
UNIQUE (provider, source, source_job_id)
  WHERE source_job_id IS NOT NULL AND source_tenant_id IS NULL

-- Fallback natural key when no stable per-posting ID is available at all
-- (e.g. a generic JSON-LD scrape with only a URL) — unaffected by the NULL-tenant
-- bug since it never included source_tenant_id in the first place
UNIQUE (provider, source, source_url_normalized) WHERE source_job_id IS NULL
```

Rev 2 had a single index, `UNIQUE (provider, source, source_tenant_id, source_job_id)
WHERE source_job_id IS NOT NULL` — which **does not enforce uniqueness when
`source_tenant_id` is NULL**, because ordinary PostgreSQL unique indexes treat every NULL
as distinct from every other NULL. Since `source_tenant_id` is NULL by design for
LinkedIn/Indeed (no tenant concept), that index silently permitted unlimited duplicate
rows for those sources — precisely the sources re-ingested on every scheduled run. Split
into two indexes above: the tenant-present index has no NULL column in its key, so it
enforces normally; the tenant-absent index simply omits `source_tenant_id` from the key
entirely (rather than trying to make NULL "count" as a value), which is also the
semantically correct key for those sources — their own posting ID is already globally
unique within `(provider, source)` without any tenant qualifier.

### `raw_job_ingestions`
Preserved pre-normalization payload (§17), **one row per individual discovered posting**
— not per provider request/attempt (see [ADR 0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md)
and the new `collection_run_provider_attempts` table below for request-level telemetry).

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| provider | text | |
| source | text | |
| source_identifier | text | nullable — provider's ID for this specific posting, before we know if it maps to an existing occurrence. Also the reference point a future per-posting detail-fetch feature should key off of (see below), rather than overloading this table |
| job_occurrence_id | UUID | FK → job_occurrences, `ON DELETE SET NULL`, nullable, set once this payload is associated with any occurrence — see nullable-behavior note below |
| fetched_at | timestamptz | |
| raw_payload | jsonb | the `DiscoveredJob.raw` dict; **not** full raw HTML (§17 — avoid unbounded storage) |
| raw_content_hash | text | sha256 of raw_payload, used to skip re-normalizing unchanged content |
| parser_version | text | which normalization code version produced the linked occurrence, if any |
| processing_status | text | **renamed from `retrieval_status` in Rev 3** — enum: `fetched` / `parse_error` / `normalized` / `identity_conflict`. Describes only what happens to *this payload* after it exists; request-level failure modes (`http_error`, `rate_limited`, `timeout`) were removed from this enum — see below |
| error_message | text | nullable |

**Rev 3 fix — narrower enum, correct granularity (item 5):** Rev 2's `retrieval_status`
enum included `http_error`/`rate_limited`/`timeout`, but those describe a fetch that
*never produced a payload at all* — by definition, no `RawJobIngestion` row would exist
to hold that status, since this table only has rows for payloads that were actually
fetched. Those values were unreachable in practice and misleadingly implied this table
tracks request-level failures; it doesn't — that's exclusively
`collection_run_provider_attempts.error_category` (§ARCHITECTURE.md §9). The corrected
enum describes only payload-level states:
- `fetched` — written immediately on fetch, before processing (transient).
- `parse_error` — normalization failed on this specific payload.
- `normalized` — cleanly resolved: attached to an existing occurrence, or a new one
  created, with no conflict.
- `identity_conflict` — parsed fine, but identity resolution
  ([ARCHITECTURE.md §8](ARCHITECTURE.md#8-deterministic-identity-resolution)) produced an
  `evidence_mismatch` or `ambiguous_match` (see `identity_conflicts` below and
  [ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md)).

**Insertion order (Rev 2, explicit):** a `RawJobIngestion` row is written *immediately*
when a posting payload is fetched, with `job_occurrence_id = NULL` and
`processing_status = 'fetched'`. Normalization and identity resolution
([ARCHITECTURE.md §8](ARCHITECTURE.md#8-deterministic-identity-resolution)) then run as a
second step; `ingestion/persistence.py` updates `processing_status` to its terminal value
and, in every case except `parse_error`, sets `job_occurrence_id`. This ordering means
the raw payload is never lost even if normalization crashes or is later found to be
buggy — it's committed before normalization is attempted, not after.

**Nullable behavior (Rev 3 — now covers the conflict cases explicitly):**
`job_occurrence_id` stays `NULL` only for (a) the transient `fetched` state (not yet
processed) and (b) `parse_error` (nothing to link — the payload itself wasn't usable). It
is populated in **every** other case, including both conflict outcomes from
[ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md): for an `evidence_mismatch`,
it points at the **existing** occurrence the natural key matched (the payload genuinely
is about that occurrence — we just don't trust all of its field values yet); for an
`ambiguous_match`, it points at the **newly created** occurrence/Job the incoming payload
produced (which still exists and is queryable — it's the *attachment decision* that's in
question, not whether a row was created). This is the explicit semantic choice item 3
asked for: `job_occurrence_id` answers "is there an occurrence this payload is linked
to," not "was this payload fully trusted."

**Out of scope (Rev 3 note, item 5):** a future feature that fetches additional detail
for an already-discovered candidate (e.g. a lightweight search result followed by a
separate detail-page fetch) and needs to represent *that* fetch's own HTTP-level failure
should **not** be modeled by stretching `processing_status` — there's no payload yet for
such a failure to attach to. It should be its own explicit fetch-attempt record, keyed by
`source_identifier` or an equivalent discovery reference, when that feature is actually
built.

**Deletion/retention:** rows are never cascade-deleted when their `JobOccurrence` is
removed (`ON DELETE SET NULL` — the audit trail survives). A periodic cleanup job (later
phase) may null out `raw_payload` (keeping the row + hash) past some age for ingestions
that never produced a live occurrence, to bound storage growth per §17's caution against
"storing giant documents forever." No automatic deletion of rows that *did* produce a
live occurrence is planned for Phase 1–9. **Rev 3 addition:** that same cleanup job must
also exclude any row referenced by an `identity_conflicts` row with `status = 'open'` —
resolving a conflict later may require inspecting the actual disputed payload, so an
open conflict's evidence must survive even past the normal payload-nulling age cutoff.

### `identity_conflicts`
**New in Rev 3** (item 3/4) — the quarantine record for deterministic identity
resolution's two conflict outcomes (see
[ARCHITECTURE.md §8](ARCHITECTURE.md#8-deterministic-identity-resolution) and
[ADR 0007](DECISIONS/0007-identity-conflict-quarantine.md)). Deliberately **not**
`duplicate_groups`: this table holds *exact-match signals that couldn't be safely
applied*, whereas `duplicate_groups` (Phase 6, below) holds *probabilistic similarity
suggestions*. Migrated in **Phase 1** — even though nothing produces rows here until
Phase 2's fixture-driven identity resolution exists — because Phase 2's fixture proof
needs this table to already exist to write its `evidence_mismatch`/`ambiguous_match` test
cases into; see [ADR 0003](DECISIONS/0003-minimal-phase1-schema.md)'s update.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| existing_job_occurrence_id | UUID | FK → job_occurrences, nullable, `ON DELETE SET NULL`. Set for `evidence_mismatch` (the one existing occurrence in dispute). `NULL` for `ambiguous_match`, where there isn't one single existing occurrence to point at — see `existing_value` |
| incoming_raw_job_ingestion_id | UUID | FK → raw_job_ingestions, nullable, `ON DELETE SET NULL`. The payload that triggered this conflict. Nullable (rather than `NOT NULL`/cascade) so the conflict record — including its own `existing_value`/`incoming_value` snapshots — survives even if the raw ingestion row it originated from is ever cleaned up; the snapshots make this table self-contained regardless |
| conflict_type | text | enum: `evidence_mismatch` (Tier 1 natural-key match, conflicting corroborating evidence — see ARCHITECTURE.md §8) / `ambiguous_match` (Tiers 2–4, more than one candidate `Job`) |
| existing_value | jsonb | for `evidence_mismatch`: the existing occurrence's disputed field value(s), e.g. `{"canonical_url_normalized": "..."}`. For `ambiguous_match`: a JSON array of the candidate `job_id`/`job_occurrence_id` values that matched |
| incoming_value | jsonb | the incoming payload's corresponding value(s) — same shape convention as `existing_value` |
| status | text | enum: `open` / `resolved` / `ignored` |
| resolution | text | nullable free-form note recorded when a human resolves or ignores the conflict — e.g. "confirmed different postings, kept separate" or "same posting, canonical URL corrected manually." No automated merge action exists yet; resolution is narrative/manual, consistent with this project's "never auto-merge" principle applied elsewhere (`companies.duplicate_of_company_id`, Tier 2 duplicate groups) |
| created_at | timestamptz | |
| resolved_at | timestamptz | nullable until `status` leaves `open` |

Indexes: `INDEX (status)` (the "show me all open conflicts" query);
`INDEX (existing_job_occurrence_id)`; `INDEX (incoming_raw_job_ingestion_id)` — no
uniqueness constraint on any of these, since a single raw ingestion could in principle
raise more than one conflict record (e.g. disputing more than one field at once) and a
single existing occurrence could accumulate multiple conflicts over time.

**Lifecycle `CHECK` constraints (Rev 4, item 4):**

```sql
CHECK (status IN ('open', 'resolved', 'ignored'))
CHECK (conflict_type IN ('evidence_mismatch', 'ambiguous_match'))
CHECK (
  (status = 'open' AND resolved_at IS NULL)
  OR
  (status IN ('resolved', 'ignored') AND resolved_at IS NOT NULL)
)
CHECK (existing_value IS NOT NULL)
CHECK (incoming_value IS NOT NULL)
```

`existing_value`/`incoming_value` are always populated by construction (§ADR 0004/0007 —
every conflict path snapshots both sides before writing the row), so `NOT NULL` here is a
hard invariant, not merely expected application behavior. `resolution` (the free-form
narrative field) is **not** constrained by a `CHECK` — it may legitimately stay `NULL`
for an `ignored` conflict (a human decided it wasn't worth writing up) and should
normally be populated for a `resolved` one, but that's a documented convention, not a
database rule: enforcing non-empty narrative text via `CHECK` would be enforcing writing
quality, which this project does not attempt to do anywhere else in the schema, and
nothing about the product requires it here either.

### `collection_runs`
Scheduler execution record (§38), one row per saved-search execution — the parent
aggregate over the new `collection_run_provider_attempts` table below.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| saved_search_id | UUID FK → saved_searches, nullable, `ON DELETE SET NULL` | nullable so a run's history survives deletion of the saved search that triggered it — the run is a historical fact independent of whether the search still exists |
| started_at | timestamptz | |
| completed_at | timestamptz | nullable while running |
| status | text | enum: running / completed / completed_with_errors / failed |
| providers_attempted | text[] | |
| providers_enforced_locally | jsonb | **shape (Rev 4): `{provider: {source: [field, ...]}}`** — which `SourceQuery` filters fell back to local enforcement, per provider *and* per source within that provider (filter support is a per-source `SourceCapabilities` fact — see [ARCHITECTURE.md §6.6](ARCHITECTURE.md#66-queryplanner-behavior-rev-4) — so two sources under the same provider can legitimately have different entries here); supports §31's observability requirement |
| jobs_discovered | int | run-level rollup; authoritative per-provider/source detail lives in `collection_run_provider_attempts` |
| jobs_inserted | int | run-level rollup |
| jobs_updated | int | run-level rollup |
| failures | jsonb | run-level summary rollup of `{provider, source, error}` — **Rev 2 note**: this is now a denormalized convenience copy; the authoritative per-attempt error detail (category, retryable, retry_count, rate_limited) lives in `collection_run_provider_attempts`, not here |
| duration_ms | int | nullable |

### `collection_run_provider_attempts`
**Moved into Phase 1 in Rev 4** (was a "later table," deferred to Phase 9/12 in Rev 2/3 —
see [ADR 0003](DECISIONS/0003-minimal-phase1-schema.md) and
[ADR 0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md) for why that was wrong:
Phase 2's fixture-driven ingestion proof already needs to persist partial provider
results, record source-specific failures, and prove `SourceRunStats` (§ARCHITECTURE.md
§6.3) round-trips into the database — none of that is possible if this table doesn't
exist until Phase 9). **Migrated in Phase 1; Phase 2's fixture pipeline is its first
writer; Phase 9 (the real scheduler) extends how it's used for scheduled runs rather than
introducing it; Phase 12 reads its accumulated history for volume-trend/anomaly
analysis** (master spec §10/§41).

One **aggregate** row per `(collection_run, provider, source)` — not one row per
individual HTTP request or retry. `retry_count` *summarizes* how many retries happened
within that one source's execution for this run. If per-request attempt history is ever
needed (e.g. granular request-level debugging), that is a separate future table,
`provider_request_attempts`, keyed by this table's row — it does not change this table's
cardinality.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| collection_run_id | UUID FK → collection_runs, `ON DELETE CASCADE`, not null | |
| provider | text, not null | |
| source | text, not null | |
| started_at | timestamptz, not null | |
| completed_at | timestamptz, nullable | nullable only while `status = 'running'` — see `CHECK` below |
| status | text, not null | enum: `running` / `completed` / `partial` / `failed` |
| jobs_discovered | int, not null, default 0 | `CHECK (jobs_discovered >= 0)` |
| jobs_inserted | int, not null, default 0 | `CHECK (jobs_inserted >= 0)` |
| jobs_updated | int, not null, default 0 | `CHECK (jobs_updated >= 0)` |
| retry_count | int, not null, default 0 | `CHECK (retry_count >= 0)` — summarizes retries within this one source's execution, see cardinality note above |
| rate_limited | boolean, not null, default false | |
| error_category | text, nullable | `ProviderErrorCategory` value (ARCHITECTURE.md §6.3) |
| error_message | text, nullable | sanitized — no secrets/tokens/full stack traces |
| incomplete_results | boolean, not null, default false | true if this source's own result set may be partial (e.g. hit a result cap, paginated fetch stopped early on rate limit) — distinct from total failure; see the `status = 'partial'`/no-error-required note below |
| created_at | timestamptz, not null | |
| updated_at | timestamptz, not null | |

**Constraints:**

```sql
UNIQUE (collection_run_id, provider, source)

CHECK (status IN ('running', 'completed', 'partial', 'failed'))

CHECK (
  (status = 'running' AND completed_at IS NULL)
  OR
  (status IN ('completed', 'partial', 'failed') AND completed_at IS NOT NULL)
)
```

**No `CHECK` ties `error_category`/`error_message` to `status`.** Both are simply
nullable, for every status. In particular, a `status = 'partial'` row does **not**
require an error to be populated — incomplete pagination or a hit result cap is a
successful-but-truncated outcome (`incomplete_results = true`), not necessarily an error
condition, and forcing one would misrepresent "we got some results, cleanly, just not
all of them" as a failure. `status = 'failed'` rows are expected (by application
convention, not a database rule) to populate `error_category`, but nothing in the schema
enforces that either — the same "don't enforce narrative/soft expectations with `CHECK`"
principle applied to `identity_conflicts.resolution` above.

**Indexes:** `INDEX (provider, source, started_at DESC)` (the volume-trend query Phase
12 reads — "give me this source's `jobs_discovered` over time"); `INDEX
(collection_run_id)` (explicit, in addition to whatever index the FK itself implies, for
the "all attempts for this run" query).

### `user_jobs`
User state, deliberately isolated from source data (§36). **Rewritten in Rev 2** — see
[ADR 0006](DECISIONS/0006-userjob-workflow-invariants.md) for the full reasoning.

Rev 1 stored `applied` (boolean), `applied_at` (nullable timestamp), and `status` (a
9-value enum including `archived`/`withdrawn`/`rejected`) as three independently
writable fields with no constraint tying them together — nothing prevented
`applied = true` with `status = 'interested'`, or `applied_at` set while `applied =
false`. Rev 2 removes the redundant boolean and makes the remaining two fields mutually
consistent by construction:

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users, `ON DELETE CASCADE` | |
| job_id | UUID FK → jobs, `ON DELETE CASCADE` | |
| saved | boolean | default false — independent lightweight flag, unrelated to workflow status |
| hidden | boolean | default false — independent lightweight "don't show me this" filter; can be toggled freely without implying any workflow judgment |
| archived | boolean | default false — **new in Rev 2, replaces the old `archived` status value**. A terminal "declutter" flag layered on top of whatever `status`/`applied_at` already held, so archiving never destroys the history of what actually happened (an archived "interested, never applied" row and an archived "offer received" row remain distinguishable) |
| applied_at | timestamptz | nullable — **the single source of truth for "has the user applied."** There is no separate `applied` boolean; application code and the UI derive it as `applied_at IS NOT NULL` |
| status | text | enum, see below — **`rejected`/`withdrawn` are now explicit about who acted**: `rejected_by_employer`, `withdrawn_by_user`. Added `not_interested` for a user dismissal that never involved applying |
| status_changed_at | timestamptz | |

**Status enum (Rev 2):** `interested`, `not_interested`, `applied`,
`recruiter_contacted`, `screening`, `interviewing`, `offer`, `rejected_by_employer`,
`withdrawn_by_user`. This distinguishes exactly the four cases the design review called
out: user dismissed without applying (`not_interested`), employer rejected
(`rejected_by_employer`), user withdrew (`withdrawn_by_user`), and "archived" is no
longer a status at all — it's the independent `archived` boolean above, so it can apply
on top of any of these without losing which one it was.

**Invariant, enforced by a database `CHECK` constraint** (not application-code
discipline alone):

```text
CHECK (
  (status IN ('interested', 'not_interested') AND applied_at IS NULL)
  OR
  (status IN ('applied', 'recruiter_contacted', 'screening', 'interviewing',
              'offer', 'rejected_by_employer', 'withdrawn_by_user')
   AND applied_at IS NOT NULL)
)
```

**How the application layer enforces the pairing, on top of the DB-level `CHECK`:**
exactly one service function (`services/user_jobs.py::set_status()`, per
[ARCHITECTURE.md §5](ARCHITECTURE.md#5-dependency-boundaries)) is permitted to write
`status`/`applied_at` together, and it is the only code path that decides whether
`applied_at` gets set (first transition into a post-application status — never
overwritten by later status changes within that branch, so the original application date
survives `recruiter_contacted → interviewing → offer`) or cleared (only when a caller
explicitly corrects a mistake by moving status back to `interested`/`not_interested`,
which clears `applied_at` in the same write). No other code path updates these two
columns — not `ingestion/`, not `providers/` (already forbidden, §5), and not ad-hoc
column updates from `api/`. This is a soft (code-structure) enforcement layered on top of
the hard DB `CHECK`; the `CHECK` is what actually prevents an inconsistent row from ever
being persisted, even if the single-writer discipline is violated by a future bug.
Backwards transitions (e.g. correcting `interviewing` back to `interested`) are
permitted — this is a personal tracker, not a workflow engine with hard-blocked
transitions — but always go through the same function so the paired columns can't drift.

Unique constraint: `(user_id, job_id)`. Nothing in `ingestion/` or `providers/` is ever
permitted to write this table — enforced by code review / the dependency rule in
[ARCHITECTURE.md §5](ARCHITECTURE.md#5-dependency-boundaries), not by a database
trigger, since the app is the only writer.

### `job_notes`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| user_job_id | UUID FK → user_jobs, `ON DELETE CASCADE` | |
| body | text | |
| created_at | timestamptz | |
| updated_at | timestamptz | **added in Rev 3 (item 8a)** — Rev 2 omitted this despite the global `created_at`/`updated_at` convention stated above; notes are user-editable free text, so "when was this last edited" is meaningful, not an oversight worth exempting |

---

## Phase 1 constraints & indexes

Consolidated checklist (each also noted inline on its table above) so migrations can be
reviewed against this list directly:

| Table | Constraint / index | Purpose |
|---|---|---|
| `users` | `CHECK (email = lower(trim(both E'\t\n\r ' from email)))`, `CHECK (trim(both E'\t\n\r ' from email) <> '')`, `UNIQUE` index on `lower(email)` | normalized-email invariant (current, as of migration `0003`) enforced at the database, not just the ORM validator — see the table's own section above (Rev 5/6) |
| `candidate_profiles` | `UNIQUE (user_id)`; `CHECK` on `remote_preference` enum; non-negative `CHECK`s on `years_experience`/`salary_expectation_min`/`salary_expectation_max`; `CHECK (salary_expectation_min <= salary_expectation_max)` | enforce 1:1 with `users` while that holds; reject an invalid `remote_preference`, a negative experience/salary value, or an inverted salary range at the database — see the table's own section above (Rev 7) |
| `candidate_skills` | `UNIQUE (candidate_profile_id, lower(skill))`; `CHECK (skill = trim(both E'\t\n\r ' from skill))`; `CHECK (trim(both E'\t\n\r ' from skill) <> '')`; `CHECK` on `priority` enum | one entry per skill per profile, case-insensitive; reject a non-normalized, empty, or invalid-priority skill at the database — see the table's own section above (Rev 8) |
| `saved_searches` | `INDEX (user_id)`; `CHECK (name = trim(both E'\t\n\r ' from name))`; `CHECK (trim(both E'\t\n\r ' from name) <> '')`; `CHECK` on `remote_rules`/`polling_schedule` enums; non-negative `CHECK`s on `salary_floor`/`preferred_salary`/`recency_limit_hours`; `CHECK (salary_floor <= preferred_salary)`; `CHECK` requiring `enabled_sources`/`scoring_weights` be a top-level JSON object when non-null | reject a non-normalized/empty `name`, an invalid enum, a negative bound, an inverted salary range, or a non-object jsonb value at the database; `radius_miles` is deliberately unconstrained — see the table's own section above (Rev 9) |
| `saved_search_titles` | `UNIQUE (saved_search_id, lower(title))` | one entry per title per search, case-insensitive |
| `saved_search_locations` | `UNIQUE (saved_search_id, lower(trim(location_text)))` | one entry per location text per search |
| `companies` | `UNIQUE (lower(domain)) WHERE domain IS NOT NULL` | strongest available company identity signal, case-normalized (Rev 3, item 8b); **no** uniqueness on `normalized_name` (see conservative collision behavior above) |
| `companies` | `INDEX (normalized_name)` | non-unique, for search/lookup only |
| `job_occurrences` | `UNIQUE (provider, source, source_tenant_id, source_job_id) WHERE source_job_id IS NOT NULL AND source_tenant_id IS NOT NULL` | natural key for tenant-scoped sources (Rev 3 split — see ADR 0004) |
| `job_occurrences` | `UNIQUE (provider, source, source_job_id) WHERE source_job_id IS NOT NULL AND source_tenant_id IS NULL` | natural key for sources with no tenant concept, e.g. LinkedIn/Indeed (Rev 3 split — the fix for the NULL-distinctness bug, ADR 0004) |
| `job_occurrences` | `UNIQUE (provider, source, source_url_normalized) WHERE source_job_id IS NULL` | fallback natural key when no stable ID is available |
| `job_occurrences` | `INDEX (canonical_url_normalized)` | identity-resolution lookup (ADR 0004 tier 2) |
| `job_occurrences` | `INDEX (provider, source, source_tenant_id, requisition_id_raw)` | identity-resolution lookup (ADR 0004 tier 3 — Rev 3 fix: now scoped by `provider`/`source`, not just `source_tenant_id`, per item 2) |
| `job_occurrences` | `INDEX (job_id, is_active, last_seen_at DESC)` | "active occurrences for this job, freshest first" — the common feed-rendering query |
| `raw_job_ingestions` | `INDEX (job_occurrence_id, fetched_at DESC)` | derives "latest ingestion for this occurrence" without a stored pointer (ADR 0005) |
| `identity_conflicts` | `INDEX (status)`, `INDEX (existing_job_occurrence_id)`, `INDEX (incoming_raw_job_ingestion_id)` | **new in Rev 3** — open-conflict queue lookup and traceback to the occurrence/ingestion in dispute |
| `identity_conflicts` | `CHECK` on `status`, `conflict_type`, `(status, resolved_at)`, `existing_value NOT NULL`, `incoming_value NOT NULL` | **new in Rev 4** — full lifecycle constraint set, see the table's own section above |
| `collection_run_provider_attempts` | `UNIQUE (collection_run_id, provider, source)` | **new in Rev 4** — one aggregate row per run/provider/source, see table's own section |
| `collection_run_provider_attempts` | `CHECK` on `status`, `(status, completed_at)`, non-negative `jobs_discovered`/`jobs_inserted`/`jobs_updated`/`retry_count` | **new in Rev 4** |
| `collection_run_provider_attempts` | `INDEX (provider, source, started_at DESC)`, `INDEX (collection_run_id)` | **new in Rev 4** — Phase 12's volume-trend query and "all attempts for this run" |
| `user_jobs` | `UNIQUE (user_id, job_id)` | one state row per user per job |
| `user_jobs` | `CHECK` on `(status, applied_at)` | see ADR 0006 — the core invariant fix |

Foreign-key `ON DELETE` behavior (all noted inline above; summarized here for review):

| FK | Behavior | Reasoning |
|---|---|---|
| `candidate_profiles.user_id → users` | CASCADE | profile is meaningless without the user |
| `candidate_skills.candidate_profile_id → candidate_profiles` | CASCADE | |
| `saved_searches.user_id → users` | CASCADE | |
| `saved_search_titles/locations.saved_search_id → saved_searches` | CASCADE | |
| `jobs.company_id → companies` | **RESTRICT** | company merges/deletes must be an explicit reconciliation step, never accidental |
| `job_occurrences.job_id → jobs` | CASCADE | occurrence is meaningless without its job |
| `raw_job_ingestions.job_occurrence_id → job_occurrences` | **SET NULL** | preserve the raw audit trail even if the occurrence is later removed (ADR 0005) |
| `identity_conflicts.existing_job_occurrence_id → job_occurrences` | SET NULL (nullable column) | conflict record survives even if the disputed occurrence is later removed; also naturally NULL for `ambiguous_match` (new in Rev 3) |
| `identity_conflicts.incoming_raw_job_ingestion_id → raw_job_ingestions` | SET NULL (nullable column) | the conflict's own `existing_value`/`incoming_value` jsonb snapshots make the record self-contained even without the FK (new in Rev 3) |
| `jobs.duplicate_group_id → duplicate_groups` | SET NULL | a job outlives the grouping mechanism's own lifecycle |
| `collection_runs.saved_search_id → saved_searches` | **SET NULL** (nullable column) | run history is a historical fact independent of the search's continued existence |
| `collection_run_provider_attempts.collection_run_id → collection_runs` | CASCADE | attempt rows are meaningless without their parent run |
| `user_jobs.user_id → users` | CASCADE | |
| `user_jobs.job_id → jobs` | CASCADE | |
| `job_notes.user_job_id → user_jobs` | CASCADE | |

---

## Later tables (not migrated in Phase 1)

| table | introduced | why deferred |
|---|---|---|
| `job_skills` | Phase 3 | depends on the skill taxonomy existing to normalize against |
| `duplicate_groups` | Phase 6 (schema previewed now — see below) | depends on `dedupe/similarity.py` producing groupings to store. **Rev 3 correction:** deterministic identity conflicts do **not** route here — they use the new Phase 1 `identity_conflicts` table above instead (ADR 0007); `duplicate_groups` is reserved exclusively for Tier 2's fuzzy/probabilistic similarity matching |
| `contacts`, `contact_sources` | Phase 13 | contact intelligence is explicitly out of scope until core ingestion is proven |
| `notifications` | unspecified | no feature currently generates notifications; add when one does |

**Rev 4 correction:** `collection_run_provider_attempts` is **no longer listed here** —
it moved into the Phase 1 tables section above (see the `collection_runs` entry's
sibling table). It was wrongly deferred to Phase 9/12 in Rev 2/3; Phase 2's fixture proof
needs it to exist to persist partial-provider-result and per-source-failure telemetry.

`duplicate_groups` (Phase 6 preview, so `jobs.duplicate_group_id` above has a stable
target name):

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| reason | text | enum: `fuzzy_title_company_location` / `description_similarity` / `manual`. **Rev 3 correction:** the Rev 2 value `identity_conflict` is removed from this enum — deterministic identity conflicts now live exclusively in the Phase 1 `identity_conflicts` table (ADR 0007), keeping this table's `reason` values genuinely limited to fuzzy/probabilistic signals plus manual grouping |
| confidence | numeric | nullable, 0–1 — every remaining reason value here is either a similarity judgment or manual, so a confidence score is always at least meaningful to consider (unlike the removed `identity_conflict` case, which never had one) |
| first_seen_job_id | UUID FK → jobs | earliest member, for display purposes |
| created_at | timestamptz | |

---

## Provenance

Per §21, values that aren't verbatim from an authoritative source must say so. Provenance
methods, in decreasing trust order:

1. `explicit_source` — the employer/ATS stated it directly (e.g. Workday salary field).
2. `structured_metadata` — JSON-LD or similar structured data on the posting page.
3. `parsed_description` — extracted via regex/rules from free text.
4. `derived` — computed from other known fields (e.g. annualized from hourly).
5. `inferred` — a guess with a stated basis (e.g. seniority guessed from title alone).
6. `unavailable` — explicitly unknown; UI must render this as "not listed," never blank
   implying zero.

The UI must never present `parsed_description`, `derived`, or `inferred` values with the
same visual confidence as `explicit_source`/`structured_metadata` (§21 — no dressing up
inferred data as confirmed fact). This is a frontend concern (Phase 8+) but the schema's
`field_provenance` column is what makes it possible.

## Field merging across occurrences

When multiple occurrences of the same `Job` disagree (§22 — e.g. Workday has a salary,
LinkedIn doesn't), resolution prefers, in order: explicit-source over inferred, more
recent `last_seen_at` over older, and a configurable per-provider priority list (employer
ATS sources outrank aggregators by default). This resolution logic lives in
`ingestion/persistence.py` and only ever *improves or replaces with equal-or-better*
provenance — it must never overwrite an `explicit_source` field with a weaker
`inferred`/`parsed_description` value from a lower-priority source. Implementation is a
Phase 4+ concern (there's nothing to merge with only `FixtureProvider` in Phase 2); the
column shape above is what Phase 1 commits to so it doesn't need a later migration. The
same "never silently merge on a weak signal" principle applies to `companies` (see
above) and to job identity itself (ADR 0004) — this is a consistent theme across the
schema, not a one-off rule for job fields.
