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
- `radius_miles` is plain `numeric` with no precision/scale (no rounding, no maximum —
  that part is a deliberate product decision), but **does** require a non-negative
  `CHECK`, same as the integer numeric fields above — a negative search radius is not a
  valid domain magnitude.
- `enabled_sources` and `scoring_weights` (the first `jsonb` columns in this schema) are
  each restricted by a `CHECK` requiring the stored value be a top-level JSON *object*
  when non-null; deeper shape is a Phase 2 `QueryPlanner`-time concern
  ([ARCHITECTURE.md §6.5–6.6](ARCHITECTURE.md#65-savedsearchenabled_sources--unambiguous-source-selection)),
  not a Phase 1 database constraint.
- `created_at`/`updated_at` are added, per the same previously-omitted-despite-the-global-
  convention gap already fixed for `users` (Rev 5) and `candidate_skills` (Rev 8).

**Rev 10 changes** (fifth Phase 1 implementation slice, `saved_search_titles` only;
`saved_search_locations` remains a future slice): this table's column list below did not
previously state several product rules, resolved by explicit approval before migration
`0007` was written:
- `title` is normalized the same way `skill`/`name` are (trim-only, case preserved,
  matching `CHECK`s).
- `is_primary` is not null with `server_default false`. At most one primary title per
  saved search is enforced by a partial unique index on `saved_search_id WHERE
  is_primary`; zero primary titles is a valid, unconstrained state — enforcing "exactly
  one" would need a trigger, which is deliberately not added.
- `created_at`/`updated_at` are added, per the same recurring gap already fixed for
  `users`, `candidate_skills`, and `saved_searches`.
- No separate plain index on `saved_search_id`: it is already the leading column of the
  `(saved_search_id, lower(title))` unique index, so a second index would be redundant.

**Rev 11 changes** (sixth Phase 1 implementation slice, `saved_search_locations` — the
final child table of the `saved_searches` group): this table's column list below did not
previously state several product rules, resolved by explicit approval before migration
`0008` was written:
- `location_text` is normalized the same way `title`/`skill`/`name` are (trim-only, case
  preserved, matching `CHECK`s). The unique index is `(saved_search_id,
  lower(location_text))` — **not** `lower(trim(location_text))` as an earlier revision of
  this section's prose implied — because the normalization `CHECK`s already guarantee
  every stored value is trimmed, so a plain `lower(...)` expresses an equivalent but
  stronger invariant on the stored data.
- `latitude`/`longitude` each have a `CHECK` restricting them to a valid coordinate range
  (`[-90, 90]` / `[-180, 180]`) when non-null, plus a coordinate-pair `CHECK` requiring
  both be NULL or both be non-NULL — a half-geocoded row is not a valid state.
- `radius_miles_override` has a `CHECK` requiring it be NULL or `>= 0`, matching
  `saved_searches.radius_miles`'s established pattern.
- All three numeric columns are left with no precision/scale, same as
  `saved_searches.radius_miles`.
- `created_at`/`updated_at` are added, per the same recurring gap already fixed for
  `users`, `candidate_skills`, `saved_searches`, and `saved_search_titles`.
- No separate plain index on `saved_search_id`: same reasoning as `saved_search_titles`.
- **Corrected stale wording:** this table's own section previously said each location
  carries its own "radius/remote override." No remote-override column has ever been
  documented or approved for this table — only `radius_miles_override` exists. That
  phrase was stale wording, corrected below; no new column was added.

**Rev 12 changes** (seventh Phase 1 implementation slice, `companies` — Class H per
docs/LLM_WORKFLOW.md, the first table with a self-referential FK, `ON DELETE SET NULL`,
and a PostgreSQL generated column): this table's column list below did not previously
state several implementation decisions, resolved by explicit approval before migration
`0009` was written:
- **`normalize_domain()`'s IDNA step uses the `idna` PyPI package
  (`idna.encode(host, uts46=True, std3_rules=True)`), not Python's stdlib `str.encode
  ("idna")` codec.** The stdlib codec only implements the older IDNA2003 algorithm;
  `café.com` happens to work under both, but UTS #46 validation/mapping (rejecting
  underscores, leading/trailing hyphens, and other STD3-disallowed forms under
  `std3_rules=True`) is only available via the dedicated package. `idna==3.19` is a new
  **direct** runtime dependency (not merely transitively installed via `httpx`) — see
  `backend/pyproject.toml` for its license (BSD-3-Clause) and replacement/removal note.
- **`normalized_name` is a PostgreSQL `GENERATED ALWAYS AS (...) STORED` column**, not an
  independently writable column kept in sync by an ORM `@validates` normalizer. A
  validator-maintained mirror column can be bypassed by direct SQL or a bulk operation,
  silently storing a `name`/`normalized_name` pair that disagree; generating it in the
  database makes that impossible. Algorithm: trim `name`'s covered whitespace (space,
  tab, LF, CR — same four-character set as every other trim-only column), collapse any
  remaining internal run of that same four-character set to one ordinary space, then
  lowercase. Because `name`'s own not-empty `CHECK` already guarantees a non-empty
  trimmed input, no separate `normalized_name_not_empty` CHECK is needed — it could never
  fire.
- **A `CHECK` rejects direct self-reference:** `duplicate_of_company_id IS NULL OR
  duplicate_of_company_id <> id`. This prevents only a company pointing at itself; a
  longer duplicate cycle (A → B → A) is out of scope for this migration and remains a
  future reconciliation-workflow responsibility, consistent with
  `duplicate_of_company_id` itself being schema-reserved and unenforced beyond this one
  invariant.
- `homepage_url`, `career_page_url`, and `industry` each get a NULL-safe pair of
  `CHECK`s (`col IS NULL OR col = trim(...)` / `col IS NULL OR trim(...) <> ''`) — a
  non-NULL value must already be trimmed and non-empty, same defense-in-depth posture as
  every other text column in this schema, just NULL-safe since these three are optional.
  No URL-format validation is applied to `homepage_url`/`career_page_url`, per explicit
  decision. On the ORM path, a covered-whitespace-only input is converted to `NULL`
  rather than failing ingestion — these fields are optional, so a blank value is "not
  provided," not invalid input.

**Rev 13 changes** (first `companies` correction pass, per independent review): fixed a
real canonicalization-ordering bug in `normalize_domain()` — the `www.`/trailing-dot/
IP-literal/multi-label structural checks ran on the *pre*-IDNA/UTS #46 input, so a
Unicode look-alike (the ideographic/fullwidth full stop, fullwidth digits) could bypass
them by only becoming `www.`/a trailing dot/an IP literal *after* UTS #46 mapping, and a
doubled ASCII trailing dot lost one dot to pre-mapping stripping before IDNA ever saw
the resulting empty label. See the corrected algorithm above (step 4 now runs before
step 5) for the fix; no schema/migration change was needed since this was an
application-layer normalization bug, not a database-constraint gap.

**Rev 14 changes** (eighth Phase 1 implementation slice, `jobs` — Class H per
docs/LLM_WORKFLOW.md: the first migration to actually exercise `ON DELETE RESTRICT`,
and a large canonical record with many downstream dependencies, even though identity
resolution itself is entirely out of scope): this table's column list above did not
previously state several implementation decisions, resolved by explicit approval before
migration `0010` was written:
- `company_id` is **nullable**, not required — `DiscoveredJob.company` is explicitly
  nullable in ARCHITECTURE.md, and requiring a resolved company would force ingestion to
  either reject an otherwise-valid job or manufacture a fake "unknown company" row.
  `ON DELETE RESTRICT` still applies whenever it is set. A plain, non-unique index on
  `company_id` supports the "list a company's jobs" query.
- `remote_type`'s previously-documented 4th enum value, `'unknown'`, is **not**
  implemented — it contradicted this schema's own global NULL-means-unknown convention.
  `NULL` means unknown; the `CHECK` restricts a non-null value to exactly `remote`/
  `hybrid`/`onsite`.
- `compensation_explicit` is nullable with no server default — `NULL` means not yet
  classified, distinct from both `true` and `false`.
- `duplicate_group_id` is omitted entirely from this migration (see the table's own
  section above) — deferred to Phase 6 alongside `duplicate_groups` itself, rather than
  added now as an unconstrained/orphan column with no FK.
- `first_seen_at`/`last_seen_at` are NOT NULL with **no** server default — they describe
  observation time, not row-creation time, so nothing may silently substitute `now()`
  for an omitted value; a `CHECK` requires `first_seen_at <= last_seen_at`.
- Every other nullable free-text column gets the established NULL-safe trim/non-empty
  `CHECK` pair (no URL-format validation, no new enums beyond `remote_type`/
  `salary_period`, which were already documented); numeric ranges get the established
  non-negative + min≤max `CHECK` pattern; `latitude`/`longitude` get the established
  coordinate-range and both-or-neither `CHECK`s; `field_provenance` gets the established
  top-level-JSON-object `CHECK`, matching `saved_searches.enabled_sources`/
  `scoring_weights`.
- `created_at`/`updated_at` are added, per the same recurring gap already fixed for
  every prior table.

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
| radius_miles | numeric, nullable | no precision/scale (deliberate); `CHECK (radius_miles IS NULL OR radius_miles >= 0)` |
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
**Implemented** (`backend/app/db/models/saved_search_title.py`; migration `0007`,
`down_revision = "0006"`). Split out (rather than an array column on `saved_searches`)
because titles need per-entry alias expansion against `taxonomy/titles.yaml` in Phase 3,
and because a title can independently carry "this is the primary title" vs. "this is an
acceptable alias."

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`), not a DB-side default |
| saved_search_id | UUID FK → saved_searches, `ON DELETE CASCADE`, not null | |
| title | text, not null | normalized before storage — see below |
| is_primary | boolean, not null | `server_default false`; at most one `true` row per `saved_search_id` — see below |
| created_at | timestamptz, not null | `server_default now()` |
| updated_at | timestamptz, not null | `server_default now()`, reset to `now()` by the ORM (`onupdate`) on every update |

**Title normalization:** trimmed of exactly the same four-character whitespace set as
`candidate_skills.skill`/`saved_searches.name` (space, tab, line feed, carriage return) —
case preserved, never lowercased. A SQLAlchemy `@validates` normalizer covers the ORM
write path, but the database is the authoritative backstop:
- `CHECK (title = trim(both E'\t\n\r ' from title))` — rejects any row (including a write
  that bypasses the ORM) whose stored value isn't already trimmed.
- `CHECK (trim(both E'\t\n\r ' from title) <> '')` — rejects empty or
  covered-whitespace-only title.
- `UNIQUE` functional index on `(saved_search_id, lower(title))` — case-insensitive,
  scoped per saved search. Because the CHECK constraints above guarantee a stored row is
  already fully trimmed, a whitespace-wrapped duplicate can never be inserted in the
  first place.

**At most one primary title:** a partial unique index on `saved_search_id WHERE
is_primary` rejects a second `true` row for the same saved search, but zero primary
titles is a valid, unconstrained state — enforcing "exactly one" is deliberately not
attempted (would require a trigger, not a declarative constraint).

### `saved_search_locations`
**Implemented** (`backend/app/db/models/saved_search_location.py`; migration `0008`,
`down_revision = "0007"` — the final child table of the `saved_searches` group). Split out
for the same reason as titles — each location independently carries its own radius
override, and future per-location geocoding work (master spec §30) keys off individual
location rows rather than a whole saved search.

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`), not a DB-side default |
| saved_search_id | UUID FK → saved_searches, `ON DELETE CASCADE`, not null | |
| location_text | text, not null | e.g. "Ashburn, VA"; normalized before storage — see below |
| latitude | numeric, nullable | nullable until geocoded; `CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90)`; no precision/scale |
| longitude | numeric, nullable | nullable until geocoded; `CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)`; no precision/scale |
| radius_miles_override | numeric, nullable | falls back to `saved_searches.radius_miles` when null; `CHECK (radius_miles_override IS NULL OR radius_miles_override >= 0)`; no precision/scale |
| created_at | timestamptz, not null | `server_default now()` |
| updated_at | timestamptz, not null | `server_default now()`, reset to `now()` by the ORM (`onupdate`) on every update |

**Location text normalization:** trimmed of exactly the same four-character whitespace
set as `saved_search_titles.title` (space, tab, line feed, carriage return) — case
preserved, never lowercased. A SQLAlchemy `@validates` normalizer covers the ORM write
path, but the database is the authoritative backstop:
- `CHECK (location_text = trim(both E'\t\n\r ' from location_text))` — rejects any row
  (including a write that bypasses the ORM) whose stored value isn't already trimmed.
- `CHECK (trim(both E'\t\n\r ' from location_text) <> '')` — rejects empty or
  covered-whitespace-only location text.
- `UNIQUE` functional index on `(saved_search_id, lower(location_text))` — case-
  insensitive, scoped per saved search. Only `lower(...)` is needed, not
  `lower(trim(...))`: the CHECK constraints above already guarantee every stored value is
  trimmed, so a whitespace-wrapped duplicate can never be inserted in the first place —
  the CHECK rejects it before the index is ever consulted. Does not attempt to dedupe
  genuinely different textual representations of the same place (e.g. "Ashburn, VA" vs.
  "Ashburn, Virginia") — that's a normalization/geocoding concern, not a uniqueness
  concern, and geocoding hasn't run yet at insert time.

**Coordinate invariants:** `latitude`/`longitude` must be either both NULL (not yet
geocoded) or both non-NULL (`CHECK ((latitude IS NULL) = (longitude IS NULL))`) — a
half-geocoded row is not a valid state.

### `companies`
**Implemented** (`backend/app/db/models/company.py`; migration `0009`, `down_revision =
"0008"`; domain normalization in `backend/app/normalization/company.py`). Deduplicated
employer identity. **This is deliberately not "solved" by a single unique constraint** —
company identity resolution is a hard, ongoing problem, not a one-time schema decision:

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`) |
| name | text, not null | trimmed (case preserved), matching `CHECK`s — see below |
| normalized_name | text, not null | **PostgreSQL `GENERATED ALWAYS AS (...) STORED`** column derived from `name` — not an ORM-maintained mirror; see Rev 12 below. Indexed (non-unique — see below) |
| domain | text | nullable, always stored pre-normalized by `normalize_domain()` — see below |
| homepage_url | text | nullable, NULL-safe normalization `CHECK`s |
| career_page_url | text | nullable, NULL-safe normalization `CHECK`s |
| industry | text | nullable, NULL-safe normalization `CHECK`s |
| duplicate_of_company_id | UUID | nullable, self-referential FK, `ON DELETE SET NULL`, `CHECK` rejects direct self-reference — see below |
| created_at | timestamptz, not null | `server_default now()` |
| updated_at | timestamptz, not null | `server_default now()`, ORM `onupdate` |

**Domain normalization (Rev 3, item 8b; completed Rev 4, item 3; implementation detail
corrected at Rev 12; ordering corrected at Rev 13 — see below):** `domain` is always
stored pre-normalized by `app/normalization/company.py::normalize_domain()` before any
insert/update touches this column. Full algorithm:
1. Trim, then lowercase the input.
2. Accept either a bare host or an arbitrary `scheme://` URL — detected only by the
   presence of `://`, so a bare host with a port (e.g. `acme.com:8080`) is never
   misparsed as scheme `acme.com` with path `8080`.
3. Strip userinfo/credentials (`user:pass@`), the port, path, query string, and
   fragment — only the host remains. An invalid or missing host/port is rejected
   (returns `None`) here.
4. Convert the remaining host through IDNA2008/UTS #46
   (`idna.encode(host, uts46=True, std3_rules=True)` — see Rev 12), which rejects empty
   labels, invalid punycode, disallowed codepoints (e.g. embedded whitespace,
   underscores under STD3 rules), and oversized labels/names.
5. **Only on this already-canonical, already-ASCII result:** strip one leading `www.`
   and one trailing dot (the DNS root-label separator, e.g. `acme.com.` → `acme.com`),
   then reject (return `None`) a single-label host or an IP literal (IPv4 or IPv6,
   bracketed or bare).
6. Return the canonical ASCII, lowercase result.

**Why step 4 (IDNA/UTS #46 conversion) must run *before* step 5's structural checks, not
after (Rev 13 correction — a real bug, not a style preference):** UTS #46 mapping can
itself turn a Unicode look-alike into the exact ASCII form step 5 is watching for — the
ideographic full stop `U+3002` and fullwidth full stop `U+FF0E` both map to ASCII `.`;
fullwidth digits `U+FF10`-`U+FF19` map to ASCII `0`-`9`. Checking "does this look like
`www.`/an IP literal/a doubled trailing dot" on the *pre-mapping* string lets a Unicode
form that only becomes that *after* mapping bypass the check entirely. Confirmed against
the pre-fix implementation: `www。acme.com` (ideographic full stop) failed to collide
with `www.acme.com`; `acme.com。` kept a root-label separator instead of being stripped;
a fullwidth-digit rendering of `127.0.0.1` was accepted as an ordinary hostname instead
of rejected as an IP literal; and `acme.com..` (two ASCII dots) lost one dot to
pre-mapping stripping before IDNA ever saw the doubled/empty label it should have
rejected. Running every structural check on the already-canonical output closes all
four.

**Explicit rule for malformed input:** if the input cannot be parsed into a valid
hostname at all (empty string, garbage input, a URL with no discernible host, an IP
literal, a single-label host), `normalize_domain()` returns `None` rather than raising —
the caller stores `NULL` in `companies.domain`, the same representation already used for
"domain unknown" elsewhere in this schema. This is a deliberate choice, not a fallback of
convenience: ingestion must never abort or crash a batch because one company's source
data had a malformed URL (consistent with §17/§32's requirement that provider/parsing
failures stay isolated); raising an exception here would do exactly that. Rejecting
outright (as opposed to normalizing to `NULL`) was considered and rejected for the same
reason — this is the one explicitly documented rule the acceptance tests below check.

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
**Implemented** (`backend/app/db/models/job.py`; migration `0010`, `down_revision =
"0009"`). The canonical opening (§20). Fields here are **resolved** values — see
[Provenance](#provenance) below for how they're chosen when occurrences disagree.
Every resolved field has a paired `*_provenance` and, for anything not sourced verbatim,
a pointer to which occurrence supplied it — modeled here as a single
`field_provenance jsonb` column (`{"salary_min": {"source": "explicit_source", "occurrence_id": "..."}, ...}`)
rather than one provenance column per field, to avoid a ~20-column-wide provenance
shadow-table for Phase 1. This can be split into a normalized `job_field_provenance`
table later without changing anything upstream, if per-field querying becomes common.
This table declares **no UNIQUE constraint of its own** — identity/matching keys live
entirely on `job_occurrences` (a separate, later slice); `requisition_id`/`canonical_url`
below are resolved *display* values only.

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`) |
| company_id | UUID FK → companies, `ON DELETE RESTRICT` | **nullable** (Rev 14) — `DiscoveredJob.company` is explicitly nullable in [ARCHITECTURE.md](ARCHITECTURE.md); requiring a resolved company would force ingestion to either reject an otherwise-valid job or manufacture a fake "unknown company" row. `ON DELETE RESTRICT` still applies whenever non-null: a company merge/delete must be an explicit reconciliation step, never an accidental cascade. Indexed (plain, non-unique) for the "list a company's jobs" query |
| requisition_id | text | nullable, **resolved display value only — not an identity/matching key** (Rev 2: see [ARCHITECTURE.md §8](ARCHITECTURE.md#8-deterministic-identity-resolution) and [ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md); the actual matching key lives on `job_occurrences`, scoped by tenant or company) |
| canonical_url | text | nullable, resolved display value — the identity-matching comparison happens on `job_occurrences.canonical_url_normalized`, not this column |
| preferred_apply_url | text | nullable |
| title | text | nullable |
| normalized_title | text | nullable until Phase 3 — a plain nullable column in this slice (nothing populates it yet), not a generated column; any non-null value must already be trimmed and non-empty, same as every other nullable text column below |
| job_family | text | nullable |
| department | text | nullable |
| team | text | nullable |
| description_raw | text | nullable |
| description_clean | text | nullable |
| location_raw | text | nullable |
| city / state / country / postal_code | text | all nullable |
| latitude / longitude | numeric | nullable, same range/pairing `CHECK`s as `saved_search_locations` |
| remote_type | text | nullable (Rev 14) — `CHECK` restricts to exactly `remote`/`hybrid`/`onsite` when non-null. **No `'unknown'` sentinel is stored**; `NULL` means unknown, consistent with this schema's global NULL-means-unknown convention. (Previously documented as a 4-value enum including `unknown`, which contradicted that convention — corrected here, not implemented as originally written.) |
| employment_type | text | nullable, free text (no enum — documented examples are illustrative, matching `candidate_skills.category`'s precedent) |
| seniority | text | nullable, free text |
| contract_type | text | nullable, free text |
| shift | text | nullable, free text |
| salary_min / salary_max | int | nullable; non-negative `CHECK`s; `CHECK (salary_min <= salary_max)` when both non-null |
| salary_currency | text | nullable |
| salary_period | text | nullable — `CHECK` restricts to exactly `hourly`/`daily`/`monthly`/`annual` when non-null |
| annualized_salary_min / max | int | nullable, derived (application concern, not enforced/computed by this migration); same non-negative + min≤max `CHECK`s as `salary_min`/`salary_max` |
| compensation_text | text | nullable, original string |
| compensation_explicit | boolean | nullable (Rev 14), **no server default** — `true` = employer-stated, `false` = third-party estimate, `NULL` = not yet classified |
| years_experience_min / max | int | nullable; non-negative `CHECK`s; `CHECK (years_experience_min <= years_experience_max)` when both non-null |
| education_requirement | text | nullable, free text |
| certifications | text[] | nullable, `MutableList.as_mutable`-wrapped (same rationale as `candidate_profiles`' array columns) |
| clearance_requirement | text | nullable, free text |
| visa_sponsorship_status | text | nullable, free text |
| travel_requirement | text | nullable, free text |
| posted_at | timestamptz | nullable — original source date, if any |
| first_seen_at | timestamptz, not null | **no server default** (Rev 14) — describes observation time, not row-creation time; nothing may silently substitute `now()` for an omitted value. Writers (and the test factory) must supply it explicitly |
| last_seen_at | timestamptz, not null | same as `first_seen_at`; `CHECK (first_seen_at <= last_seen_at)` |
| application_deadline | timestamptz | nullable |
| field_provenance | jsonb | nullable, `MutableDict.as_mutable`-wrapped; `CHECK` restricts to a top-level JSON object when non-null, matching `saved_searches.enabled_sources`/`scoring_weights` — same documented nested-mutation limitation (replace the complete per-field object, e.g. `job.field_provenance["salary_min"] = updated_entry`, rather than mutating a nested dict in place) |
| created_at / updated_at | timestamptz, not null | `server_default now()`, per the established global convention |

**Deferred (Rev 14): `duplicate_group_id` is omitted from this migration entirely.**
`duplicate_groups` is a Phase 6 table that does not exist yet (see "Later tables"
below), so no FK constraint could be declared against it now. It will be added, with its
FK (`ON DELETE SET NULL`), in a Phase 6 migration alongside `duplicate_groups` itself —
not added now as an unconstrained/orphan column.

### `job_occurrences`
**Implemented** (`backend/app/db/models/job_occurrence.py`; migration `0011`,
`down_revision = "0010"`; URL normalization in
`backend/app/normalization/url.py`). One observed appearance on one source (§18).
**Rev 2** adds the fields identity resolution actually needs (§ADR 0004) and removes
the circular FK to `raw_job_ingestions` (§ADR 0005). This is the table the project's
deterministic identity-resolution scheme is built on — its three partial unique
indexes below **are** the scoped identity signals ADR 0004 defines. This table
declares no additional identity-matching logic of its own; the actual
match-precedence application logic (querying by these indexes in order, deciding
new-vs-existing-occurrence, writing `identity_conflicts` rows) is Phase 2+ ingestion
code — Phase 2's offline fixture pipeline is the first writer/user of this persistence
and deterministic-identity path; Phase 4 introduces the first live ATS provider to
reuse it. Out of scope for this schema-only slice.

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`) |
| job_id | UUID FK → jobs, `ON DELETE CASCADE`, not null | |
| provider | text, not null | e.g. "ats_scrapers", "jobspy" — a required canonical identifier: lowercased and trimmed by the ORM, `CHECK`-enforced already lowercase/trimmed/non-empty (Rev 15), and restricted to a lowercase ASCII slug grammar `^[a-z0-9][a-z0-9._-]*$` (Rev 16) |
| source | text, not null | e.g. "greenhouse", "linkedin" — same canonical-identifier treatment as `provider` |
| source_tenant_id | text | **new in Rev 2** — nullable, case-preserving (not case-folded — externally assigned, unlike `provider`/`source`). The ATS-tenant or employer-account identifier *within* `(provider, source)`: a Workday tenant subdomain, a Greenhouse board token, a Lever company slug. Null for sources with no tenant concept (e.g. a LinkedIn/Indeed posting isn't scoped to a "tenant" beyond the site itself). This is what makes requisition-ID matching safe — see [ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md) |
| source_job_id | text | nullable, case-preserving |
| requisition_id_raw | text | **new in Rev 2** — nullable, case-preserving. The requisition ID exactly as reported by *this* source, unscoped by itself; only ever compared in combination with `source_tenant_id` or a resolved `company_id`, never alone |
| source_url | text, not null | as provided by the source; required, trim-only, case-preserving |
| source_url_normalized | text | **new in Rev 2** — normalized per [ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md); used as the fallback natural-key component when `source_job_id` is absent. **Rev 15: application-owned, not database-derived** — see below |
| apply_url | text | nullable, case-preserving |
| canonical_url | text | nullable, as provided by the source, case-preserving |
| canonical_url_normalized | text | **new in Rev 2** — normalized per ADR 0004; this is the column identity resolution actually compares, not the raw `canonical_url`. **Rev 15: application-owned, not database-derived**; `CHECK` requires `canonical_url IS NULL` to imply this column is also `NULL` — see below |
| first_seen_at | timestamptz, not null | for *this* occurrence. **Rev 15: no server default, no ORM `onupdate`** — describes observation time, not row-creation time; `CHECK (first_seen_at <= last_seen_at)` |
| last_seen_at | timestamptz, not null | updated every time this occurrence is re-observed — an explicit business event, not an automatic side effect of any other write (Rev 15) |
| posted_at | timestamptz | nullable, source-reported |
| applicant_count | int | nullable, source-specific — never merged across sources; non-negative `CHECK` |
| applicant_count_text | text | nullable, original string (e.g. "over 200 applicants"), case-preserving |
| is_active | boolean, not null | `server_default true` (Rev 15) — false once the posting disappears from this source |
| created_at / updated_at | timestamptz, not null | `server_default now()`, per the established global convention (Rev 15) |

**Rev 15 changes** (tenth Phase 1 implementation slice, `job_occurrences` — Class H
per docs/LLM_WORKFLOW.md): this table's column list above did not previously state
several implementation decisions, resolved by explicit approval before migration
`0011` was written:
- **`app/normalization/url.py::normalize_url()` is new in this slice** — a narrowly
  scoped, pure, schema-bound identity canonicalizer (see
  [PHASE_RISK_CHECKLIST.md](PHASE_RISK_CHECKLIST.md)'s Phase 1 clarification),
  deliberately **not** built on `normalize_domain()`: a URL host must retain `www.`
  and a valid IP-literal host remains a valid URL host, both of which
  `normalize_domain()` rejects outright since it's answering a different question
  (company identity, not "is this a stable, comparable click-through target").
  Accepts only an absolute `http`/`https` URL with a hostname and no userinfo/
  credentials; rejects relative/protocol-relative URLs, a missing host, and an
  invalid port by returning `None`, never raising. Lowercases scheme and host
  (IDNA/UTS #46 for a domain; preserved-and-reconstructed for an IPv4/bracketed-IPv6
  literal), drops the fragment, drops the port only when it equals the scheme's
  default, collapses an empty/root path and `/` to the same `/` while stripping
  trailing slashes from any other path (case preserved), and strips every query
  parameter matching a deny-list (case-insensitive `utm_*` prefix, plus the fixed
  exact names `gh_src`/`lever-source`/`trk`/`li_fat_id`/`ref`/`fbclid`/`gclid`/
  `mc_cid`/`mc_eid`) unless the caller's `(provider, source)` has that name on its
  own per-source allow-list — deliberately empty in this slice (ADR 0004: "starts
  empty/conservative, grows with evidence").
- **`source_url_normalized`/`canonical_url_normalized` are application-owned, not
  database-derived.** The database cannot guarantee a Python function's output
  agrees with its raw input, so no such guarantee is claimed or enforced beyond one
  `CHECK`: `canonical_url IS NULL` implies `canonical_url_normalized IS NULL` (the
  one relationship that *is* checkable — a non-null `canonical_url` may still
  legitimately normalize to `NULL` if malformed, so this is a one-way implication,
  not full equivalence). Phase 2's persistence path is responsible for calling
  `normalize_url()` before comparison/write; this slice tests only the pure
  function and that rows can store its result explicitly.
- **`provider`/`source` are canonical identifiers**, not free display text: the ORM
  lowercases and trims them, and a `CHECK` requires the stored value already be
  lowercase/trimmed/non-empty — casing or whitespace differences must never let two
  logically-identical rows bypass the natural-key indexes below.
  `source_tenant_id`/`source_job_id`/`requisition_id_raw` remain case-preserving
  (externally assigned identifiers, never case-folded).
- **`first_seen_at`/`last_seen_at` are NOT NULL with no server default and no ORM
  `onupdate`** — they describe observation time, not row-creation/update time,
  matching `jobs`' own established treatment; a `CHECK` requires
  `first_seen_at <= last_seen_at`.
- `applicant_count` gets the established non-negative `CHECK`. `is_active` is NOT
  NULL with `server_default true`, matching `saved_searches.is_active`.
  `created_at`/`updated_at` are added, per the established global convention.

**Rev 16 corrections** (Codex review at commit `5ad85bd`, applied on the same
`phase-1/job-occurrences` branch): three defects in Rev 15's implementation, found by
adversarial self-review and independent review before merge:
- **`normalize_url()` now rejects embedded whitespace instead of silently
  repairing or ignoring it.** `urlsplit()` on its own quietly deletes an embedded
  `\t`/`\n`/`\r` from anywhere in the raw input (a CPython header-injection
  mitigation) while leaving an embedded literal space untouched — so two
  different-looking raw URLs could each "successfully" normalize and collide as a
  false identity match. `normalize_url()` now trims only symmetric *outer* wrapper
  whitespace before parsing, then returns `None` for the whole input if any covered
  whitespace remains anywhere inside it. Percent-encoded whitespace (`%20`) is
  unaffected — it is not a literal whitespace character in the raw string.
- **A single trailing DNS root-dot now canonicalizes identically to no trailing
  dot.** `example.com.` (or a UTS #46-mapped equivalent, e.g. U+3002/U+FF0E) previously
  normalized to a *different* host string than `example.com`, so the same real posting
  could fail to match itself depending on whether a source happened to include the
  root separator. `_canonicalize_host()` now strips exactly one trailing dot from the
  post-IDNA ASCII form; a doubled or otherwise empty label (`example.com..`,
  `.example.com`) is still rejected outright (`idna.encode()` already treats these as
  errors), never silently repaired.
- **`provider`/`source` are now restricted to a lowercase ASCII slug grammar**
  (`^[a-z0-9][a-z0-9._-]*$`), in addition to the existing trim/lower/non-empty
  `CHECK`s. Python's `str.lower()` (used by the ORM validator) and PostgreSQL's
  `lower()` (used by the `_normalized` `CHECK`) can disagree on non-ASCII input
  depending on locale/collation (e.g. Turkish dotted-İ); restricting both columns to
  ASCII makes that divergence structurally impossible rather than an accepted
  limitation. `normalize_url()`'s per-`(provider, source)` allow-list lookup is also
  now canonicalized (trim + lowercase) before the dict lookup, so a future
  evidence-based allow-list entry can't silently miss due to caller casing.
- The `job_occurrences` factory (`backend/tests/conftest.py`) now computes
  `source_url_normalized = normalize_url(source_url, ...)` by default instead of
  leaving it `NULL` — a "valid occurrence" produced by an application-level test
  helper must actually be identity-consistent, the same way a real ingestion write
  would be. Tests that need the model's own non-derivation behavior, or a
  deliberately malformed/`NULL` normalized value, override it explicitly.

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
**Implemented** (`backend/app/db/models/raw_job_ingestion.py`; migration `0012`,
`down_revision = "0011"`). Preserved pre-normalization payload (§17), **one row per
individual discovered posting** — not per provider request/attempt (see
[ADR 0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md) and the new
`collection_run_provider_attempts` table below for request-level telemetry). Phase 2's
offline fixture pipeline is the first writer/user of this persistence and
deterministic-identity path; Phase 4 introduces the first live ATS provider to reuse
it. This Phase 1 slice only migrates the schema.

| column | type | notes |
|---|---|---|
| id | UUID PK | generated application-side (`uuid.uuid4`) |
| provider | text, not null | same canonical-identifier treatment as `job_occurrences.provider`: lowercased/trimmed by the ORM, `CHECK`-enforced already lowercase/trimmed/non-empty and matching the ASCII slug grammar `^[a-z0-9][a-z0-9._-]*$` (Rev 17) — generalized from `job_occurrences` since these are this project's own internal categorization labels, not "raw" external data |
| source | text, not null | same treatment as `provider` |
| source_identifier | text | nullable, case-preserving, NULL-safe trim/non-empty `CHECK` — provider's ID for this specific posting, before we know if it maps to an existing occurrence. Also the reference point a future per-posting detail-fetch feature should key off of (see below), rather than overloading this table |
| job_occurrence_id | UUID | FK → job_occurrences, `ON DELETE SET NULL`, nullable, set once this payload is associated with any occurrence — see nullable-behavior note below |
| fetched_at | timestamptz, not null | **Rev 17: no server default** — represents the actual fetch event, which may differ from row-insertion time during buffering, replay, or backfill; callers/factories must supply it explicitly |
| raw_payload | jsonb, not null | the `DiscoveredJob.raw` dict; **not** full raw HTML (§17 — avoid unbounded storage). `CHECK` requires a top-level JSON object (Rev 17). Stays not null through Phase 1 — see the retention note below. Deliberately not `MutableDict`-wrapped: an immutable, write-once snapshot set at insert, unlike `jobs.field_provenance`'s incrementally-updated fields — this is an application-level convention (Phase 2's ingestion code must honor it), not a schema-enforced immutability guarantee |
| raw_content_hash | text, not null | sha256 of raw_payload, used to skip re-normalizing unchanged content. `CHECK` requires trim/non-empty only (Rev 17) — deliberately no length/hex-format constraint, since this is application-computed, not user input |
| parser_version | text | nullable, case-preserving, NULL-safe trim/non-empty `CHECK` — which normalization code version produced the linked occurrence, if any |
| processing_status | text, not null | **renamed from `retrieval_status` in Rev 3** — `CHECK`-restricted enum: `fetched` / `parse_error` / `normalized` / `identity_conflict`. Describes only what happens to *this payload* after it exists; request-level failure modes (`http_error`, `rate_limited`, `timeout`) were removed from this enum — see below |
| error_message | text | nullable, case-preserving, NULL-safe trim/non-empty `CHECK` |
| created_at / updated_at | timestamptz, not null | `server_default now()`, per the established global convention (Rev 17) — the standard row-lifecycle pair, distinct from the business timestamp `fetched_at` above |

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

**Rev 17 changes** (eleventh Phase 1 implementation slice, `raw_job_ingestions` — Class
H per docs/LLM_WORKFLOW.md): this table's column list above did not previously state
several implementation decisions, resolved by explicit approval before migration `0012`
was written:
- **`provider`/`source` reuse `job_occurrences`' canonical-identifier `CHECK`s**
  (trim/lower/non-empty plus the ASCII slug grammar `^[a-z0-9][a-z0-9._-]*$`) —
  generalized to a second table, since these are this project's own internal
  categorization labels, not external "raw" data the cross-cutting "preserve raw
  values" principle protects.
- **The `processing_status`/`job_occurrence_id` consistency invariant is
  database-enforced in only one direction.** A `CHECK` requires
  `processing_status IN ('fetched', 'parse_error') ⟹ job_occurrence_id IS NULL` — safe
  because those two states can never have an occurrence to link to in the first place,
  so `ON DELETE SET NULL` never touches them. The reverse (`normalized`/
  `identity_conflict` implying a non-null `job_occurrence_id`) is deliberately **not**
  a `CHECK`: it holds at write time (Phase 2's future persistence-service tests will
  prove that; Phase 1 has no ingestion service to test it against), but a real,
  already-committed `normalized`/`identity_conflict` row must be allowed to end up with
  `job_occurrence_id IS NULL` after its target occurrence is later deleted — the exact
  historical audit-preservation state this section's "Deletion/retention" note above
  already describes wanting, not a data-integrity violation. Enforcing both directions
  would make `ON DELETE SET NULL`'s own cascade `UPDATE` violate the `CHECK`, turning it
  into `RESTRICT` in practice for those rows.
- `raw_payload` stays NOT NULL through Phase 1 with a `CHECK` requiring a top-level JSON
  object; the retention job described above that nulls old payloads will need its own
  deliberate migration to relax this when actually built, not a speculative relaxation
  now. Not `MutableDict`-wrapped — an immutable, write-once snapshot, unlike
  `jobs.field_provenance`'s incrementally-updated fields; omitting the wrapper does not
  itself guarantee immutability (whole-value reassignment and direct SQL `UPDATE`s
  remain possible), so this is an application-level convention, tested behaviorally,
  not schema-enforced.
- `raw_content_hash` gets a trim/non-empty `CHECK` only — no length/hex-format
  constraint, since it's application-computed, not user input.
- `fetched_at` is NOT NULL with **no** server default, unlike `created_at`/`updated_at`
  (added this slice, per the established global convention) — it represents the actual
  fetch event, which may differ from row-insertion time during buffering, replay, or
  backfill.
- No uniqueness constraint of any kind: this table is an intentionally append-only
  audit log — re-observing the same posting on a later run creates a new row, it does
  not update or replace the previous one.

### `identity_conflicts`
**Implemented** (`backend/app/db/models/identity_conflict.py`; migration `0013`,
`down_revision = "0012"`). **New in Rev 3** (item 3/4) — the quarantine record for
deterministic identity resolution's two conflict outcomes (see
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
| id | UUID PK | generated application-side (`uuid.uuid4`) |
| existing_job_occurrence_id | UUID | FK → job_occurrences, nullable, `ON DELETE SET NULL`. Set for `evidence_mismatch` (the one existing occurrence in dispute). `NULL` for `ambiguous_match`, where there isn't one single existing occurrence to point at — see `existing_value`. **Rev 18: `CHECK` requires `ambiguous_match ⟹ NULL`; the reverse is deliberately not a `CHECK`** — see below |
| incoming_raw_job_ingestion_id | UUID | FK → raw_job_ingestions, nullable, `ON DELETE SET NULL`. The payload that triggered this conflict. Nullable (rather than `NOT NULL`/cascade) so the conflict record — including its own `existing_value`/`incoming_value` snapshots — survives even if the raw ingestion row it originated from is ever cleaned up; the snapshots make this table self-contained regardless. **Rev 18: no `CHECK` of any kind** — populated for both conflict types at write time, but must remain legitimately nullable after its own cascade fires |
| conflict_type | text, not null | enum: `evidence_mismatch` (Tier 1 natural-key match, conflicting corroborating evidence — see ARCHITECTURE.md §8) / `ambiguous_match` (Tiers 2–4, more than one candidate `Job`). **Rev 18**: plain `CHECK`-restricted enum, no ORM trim/case transform — matches `raw_job_ingestions.processing_status`'s treatment (a closed literal set, not a cross-table join key) |
| existing_value | jsonb, not null | for `evidence_mismatch`: the existing occurrence's disputed field value(s), e.g. `{"canonical_url_normalized": "..."}`. For `ambiguous_match`: a JSON array of the candidate `job_id`/`job_occurrence_id` values that matched. **Rev 18: `CHECK` enforces this shape by type** (object vs. array) — see below. Not `MutableDict`/`MutableList`-wrapped: an immutable, write-once snapshot, same rationale as `raw_job_ingestions.raw_payload` |
| incoming_value | jsonb, not null | the incoming payload's corresponding value(s) — same shape convention and `CHECK` as `existing_value` |
| status | text, not null | enum: `open` / `resolved` / `ignored`. **Rev 18: no server default** — fresh conflict creation must explicitly supply `'open'` |
| resolution | text | nullable free-form note recorded when a human resolves or ignores the conflict — e.g. "confirmed different postings, kept separate" or "same posting, canonical URL corrected manually." No automated merge action exists yet; resolution is narrative/manual, consistent with this project's "never auto-merge" principle applied elsewhere (`companies.duplicate_of_company_id`, Tier 2 duplicate groups). **Rev 18**: ORM trims and collapses blank to `NULL`, but a direct SQL write is **not** promised this normalization — no backing `CHECK`, unlike every other nullable text column in this schema |
| created_at | timestamptz, not null | `server_default now()` (Rev 18) — a conflict row's creation moment is its detection moment, unlike `raw_job_ingestions.fetched_at` |
| updated_at | timestamptz, not null | `server_default now()` + ORM `onupdate` (Rev 18) — the standard lifecycle pair |
| resolved_at | timestamptz | nullable until `status` leaves `open`. **Rev 18: `CHECK (resolved_at IS NULL OR resolved_at >= created_at)`** in addition to the lifecycle consistency check below |

Indexes: `INDEX (status)` (the "show me all open conflicts" query);
`INDEX (existing_job_occurrence_id)`; `INDEX (incoming_raw_job_ingestion_id)` — no
uniqueness constraint on any of these, since a single raw ingestion could in principle
raise more than one conflict record (e.g. disputing more than one field at once) and a
single existing occurrence could accumulate multiple conflicts over time.

**Lifecycle `CHECK` constraints (Rev 4, item 4; extended Rev 18):**

```sql
CHECK (status IN ('open', 'resolved', 'ignored'))
CHECK (conflict_type IN ('evidence_mismatch', 'ambiguous_match'))
CHECK (
  (status = 'open' AND resolved_at IS NULL)
  OR
  (status IN ('resolved', 'ignored') AND resolved_at IS NOT NULL)
)
CHECK (resolved_at IS NULL OR resolved_at >= created_at)
CHECK (
  (conflict_type = 'evidence_mismatch' AND jsonb_typeof(existing_value) = 'object')
  OR
  (conflict_type = 'ambiguous_match' AND jsonb_typeof(existing_value) = 'array')
)
CHECK (
  (conflict_type = 'evidence_mismatch' AND jsonb_typeof(incoming_value) = 'object')
  OR
  (conflict_type = 'ambiguous_match' AND jsonb_typeof(incoming_value) = 'array')
)
CHECK (conflict_type <> 'ambiguous_match' OR existing_job_occurrence_id IS NULL)
```

`existing_value`/`incoming_value` are always populated by construction (§ADR 0004/0007 —
every conflict path snapshots both sides before writing the row), so `NOT NULL` on the
column itself is the hard invariant (no separate redundant `CHECK`, matching
`raw_job_ingestions.raw_payload`'s own treatment). `resolution` (the free-form
narrative field) is **not** constrained by a `CHECK` — it may legitimately stay `NULL`
for an `ignored` conflict (a human decided it wasn't worth writing up) and should
normally be populated for a `resolved` one, but that's a documented convention, not a
database rule: enforcing non-empty narrative text via `CHECK` would be enforcing writing
quality, which this project does not attempt to do anywhere else in the schema, and
nothing about the product requires it here either.

**Rev 18 changes** (twelfth Phase 1 implementation slice, `identity_conflicts` — Class H
per docs/LLM_WORKFLOW.md): this table's design had several decisions resolved by explicit
approval before migration `0013` was written:
- **The JSON shape of `existing_value`/`incoming_value` is now database-enforced**,
  conditional on `conflict_type`: a top-level JSON object for `evidence_mismatch`, a
  top-level JSON array for `ambiguous_match` — using the same `jsonb_typeof()` primitive
  already established (`jobs.field_provenance`, `raw_job_ingestions.raw_payload`), applied
  conditionally on another column for the first time in this schema. Neither non-empty
  objects/arrays nor inner element schemas are enforced — only the top-level shape,
  matching this project's posture of not validating what isn't demonstrated necessary
  (an empty object/array is explicitly accepted).
- **The `conflict_type`/`existing_job_occurrence_id` relationship is enforced in only
  one direction**, for the same reason `raw_job_ingestions.processing_status`/
  `job_occurrence_id` is: `ambiguous_match` requires `existing_job_occurrence_id IS
  NULL` (safe — an `ambiguous_match` row never has a non-null value to begin with, so
  `ON DELETE SET NULL` never touches it in a way that could violate this). The reverse
  (`evidence_mismatch` implying non-null) is deliberately **not** a `CHECK`: a real,
  already-committed `evidence_mismatch` row must be allowed to end up with
  `existing_job_occurrence_id IS NULL` after its disputed occurrence is later deleted —
  the historical audit-preservation state this table exists to support, not a violation.
  Enforcing both directions would turn `ON DELETE SET NULL` into `RESTRICT` in practice.
- **`incoming_raw_job_ingestion_id` gets no `CHECK` at all** — populated for both
  conflict types at write time, but must remain legitimately nullable after its own
  `ON DELETE SET NULL` fires.
- **`resolved_at >= created_at`** is a new ordering `CHECK`, matching this project's
  established before/after invariant pattern elsewhere (`first_seen_at <=
  last_seen_at`, etc.) — not previously specified for this table.
- **`status` has no server default** — fresh conflict creation must explicitly supply
  `'open'`, consistent with this project's "no silent substitution for a business-
  meaningful value" posture.
- **`created_at`/`updated_at` follow the established global convention** — a conflict
  row's creation moment is its detection moment (unlike `raw_job_ingestions.fetched_at`),
  so no separate business timestamp is needed; `updated_at` is new (not previously
  specified for this table).
- Both FK constraints (`existing_job_occurrence_id → job_occurrences`,
  `incoming_raw_job_ingestion_id → raw_job_ingestions`) required explicit, shortened
  constraint names — the naming convention's full template exceeds Postgres's 63-byte
  identifier limit for both and would otherwise be silently truncated with an
  auto-appended hash suffix.

### `collection_runs`
**Implemented** (`backend/app/db/models/collection_run.py`; migration `0014`,
`down_revision = "0013"`). Scheduler execution record, one row per saved-search
execution — the parent aggregate over the new `collection_run_provider_attempts` table
below.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| saved_search_id | UUID FK → saved_searches, nullable, `ON DELETE SET NULL` | nullable so a run's history survives deletion of the saved search that triggered it — the run is a historical fact independent of whether the search still exists; no other column's `CHECK` references this column's nullness, so unlike `raw_job_ingestions`/`identity_conflicts` there is no FK-vs-CHECK asymmetric-direction tension here |
| started_at | timestamptz, not null, no server default | supplied explicitly by the scheduler/pipeline code, matching `raw_job_ingestions.fetched_at`'s treatment |
| completed_at | timestamptz, nullable | nullable only while `status = 'running'` — see the lifecycle `CHECK` below; `CHECK (completed_at IS NULL OR completed_at >= started_at)` |
| status | text, not null, no server default | enum: running / completed / completed_with_errors / failed; `CHECK` restricts to these four values; a second `CHECK` requires `completed_at IS NULL` for `running` and `completed_at IS NOT NULL` for every terminal status; fresh creation must explicitly supply `'running'` |
| providers_attempted | text[], not null, server default `'{}'` | providers whose execution *actually began* — not merely planned; a provider rejected during planning with no `discover()` call is recorded in `failures` instead, never here; `MutableList`-wrapped for in-place append tracking |
| providers_enforced_locally | jsonb, not null, server default `'{}'` | **shape (Rev 4): `{provider: {source: [field, ...]}}`** — which `SourceQuery` filters fell back to local enforcement, per provider *and* per source within that provider (filter support is a per-source `SourceCapabilities` fact — see [ARCHITECTURE.md §6.6](ARCHITECTURE.md#66-queryplanner-behavior-rev-4) — so two sources under the same provider can legitimately have different entries here); supports §31's observability requirement; `CHECK` requires a top-level JSON object; deliberately **not** `MutableDict`-wrapped — assembled once in memory during planning and assigned as a complete value, matching `jobs.field_provenance`'s own documented nested-mutation limitation |
| jobs_discovered | int, not null, server default 0 | run-level rollup; authoritative per-provider/source detail lives in `collection_run_provider_attempts`; `CHECK (jobs_discovered >= 0)` |
| jobs_inserted | int, not null, server default 0 | run-level rollup; `CHECK (jobs_inserted >= 0)` |
| jobs_updated | int, not null, server default 0 | run-level rollup; `CHECK (jobs_updated >= 0)` |
| failures | jsonb, not null, server default `'[]'` | run-level summary rollup of `{provider, source, error}` — **Rev 2 note**: this is now a denormalized convenience copy; the authoritative per-attempt error detail (category, retryable, retry_count, rate_limited) lives in `collection_run_provider_attempts`, not here; can accumulate at both planning time (no attempt row exists) and execution time, potentially across more than one write; `CHECK` requires a top-level JSON array; `MutableList`-wrapped for top-level append tracking — nested mutation within an already-appended entry is not tracked, correcting an entry requires replacing the whole list; no `CHECK` ties `failures` or the three job counters to `status` — `completed_with_errors` may legitimately show accurate non-zero rollups alongside a non-empty `failures` array |
| duration_ms | int, nullable | `CHECK (duration_ms IS NULL OR duration_ms >= 0)` |
| created_at | timestamptz, not null, server_default `now()` | added in Rev 19 despite this table's own earlier column list omitting it, per the established global convention |
| updated_at | timestamptz, not null, server_default `now()`, ORM `onupdate=func.now()` | added in Rev 19, same global convention |

Indexes: `(saved_search_id, started_at DESC)` (run history per search; also serves Phase
9's "is there already a run for this search" lookup by leading column) and `(status)`
(Phase 9's "find all still-running rows" abandoned-run detection, not scoped to one
search) — lookup support only, they do not prevent overlapping runs under concurrency;
Phase 9's own database-lock/partial-unique strategy for that is a separate, explicitly
designed scheduler invariant, out of scope here. No uniqueness constraint of any kind in
this slice.

**Rev 19 changes** (thirteenth Phase 1 implementation slice, `collection_runs` — Class H
per docs/LLM_WORKFLOW.md): this table's design had several decisions resolved by explicit
approval before migration `0014` was written, in addition to the columns/notes above:
- **`created_at`/`updated_at` were added**, even though this table's own original column
  list (above, pre-Rev-19) omitted them — the same tension `identity_conflicts` hit in
  Rev 18, resolved the same way: they follow the established global convention regardless
  of what an individual table's earlier design note happened to list.
- **The bidirectional lifecycle `CHECK`** (`status`/`completed_at` consistency) and the
  **`completed_at >= started_at` ordering `CHECK`** both extend patterns already
  established elsewhere in this schema (`identity_conflicts.status`/`.resolved_at`;
  `job_occurrences.first_seen_at <= last_seen_at`) rather than introducing new ones.
  `collection_run_provider_attempts` already documented an equivalent status/
  `completed_at` pattern for itself before this table implemented its own.
  Never enforced in both directions in a way that would fight `saved_search_id`'s
  `ON DELETE SET NULL` — no CHECK here references that column's nullness, so the
  FK-vs-CHECK asymmetric-direction tension seen on `raw_job_ingestions`/
  `identity_conflicts` does not arise for this table.
- **`providers_attempted` and `failures` are both `MutableList`-wrapped; `providers_
  enforced_locally` is deliberately not.** This is the first table in this schema where
  a JSONB (not `ARRAY`) column (`failures`) is `MutableList`-wrapped, and the first
  table where a NOT-NULL JSONB/array column with a non-null `server_default` (rather
  than nullable-with-no-default, or NOT-NULL-with-no-default) carries a shape `CHECK`.
  The wrapping choice is driven purely by mutation semantics: append-incrementally
  (`providers_attempted`, `failures`) is wrapped; assign-once-as-a-whole-value
  (`providers_enforced_locally`) is not, matching `jobs.field_provenance`'s existing
  precedent for the latter.
- **No `CHECK` ties `failures` or the three job counters to `status`** — mirroring
  `collection_run_provider_attempts`' own already-documented "no `CHECK` ties
  `error_category`/status" reasoning, so `completed_with_errors` can honestly retain
  non-zero successful rollups alongside recorded failures.
- **No uniqueness constraint of any kind in this slice** — the two indexes are lookup
  support only; the Phase 9 scheduler-level overlapping-run-prevention strategy is an
  explicitly separate, not-yet-designed invariant.

### `collection_run_provider_attempts`
**Implemented** (`backend/app/db/models/collection_run_provider_attempt.py`; migration
`0015`, `down_revision = "0014"`). **Moved into Phase 1 in Rev 4** (was a "later table,"
deferred to Phase 9/12 in Rev 2/3 — see [ADR 0003](DECISIONS/0003-minimal-phase1-schema.md)
and [ADR 0005](DECISIONS/0005-raw-ingestion-vs-provider-attempts.md) for why that was
wrong: Phase 2's fixture-driven ingestion proof already needs to persist partial provider
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
| collection_run_id | UUID FK → collection_runs, `ON DELETE CASCADE`, not null | an attempt row has no independent meaning without its parent run — unlike this schema's audit-trail FKs (all `SET NULL`) |
| provider | text, not null | canonical identifier: lowercased/trimmed by the ORM, `CHECK`-restricted to an already-canonical ASCII-slug value (`^[a-z0-9][a-z0-9._-]*$`) — same treatment as `job_occurrences`/`raw_job_ingestions` |
| source | text, not null | same canonical-identifier treatment as `provider` |
| started_at | timestamptz, not null, no server default | supplied explicitly by the attempt-recording code |
| completed_at | timestamptz, nullable | nullable only while `status = 'running'` — see `CHECK` below; `CHECK (completed_at IS NULL OR completed_at >= started_at)` |
| status | text, not null, no server default | enum: `running` / `completed` / `partial` / `failed` |
| jobs_discovered | int, not null, default 0 | `CHECK (jobs_discovered >= 0)` |
| jobs_inserted | int, not null, default 0 | `CHECK (jobs_inserted >= 0)` |
| jobs_updated | int, not null, default 0 | `CHECK (jobs_updated >= 0)` |
| retry_count | int, not null, default 0 | `CHECK (retry_count >= 0)` — summarizes retries within this one source's execution, see cardinality note above |
| rate_limited | boolean, not null, default false | independent of `incomplete_results` and of `status` — no `CHECK` relates any of the three |
| error_category | text, nullable | `CHECK`-restricted to exactly 8 values reused from `ProviderErrorCategory` (ARCHITECTURE.md §6.3): `timeout`, `rate_limited`, `auth_error`, `blocked`, `parse_error`, `not_found`, `upstream_error`, `unknown`. Kept as a plain string column, not a native Postgres enum type, so adding a category is a single migration adding one `CHECK` value. No ORM case-fold (plain closed-enum column, like `status`) — Phase 2+ must keep this list synchronized with the Python enum by hand |
| error_message | text, nullable | case-preserving free text: ORM-trimmed with a covered-whitespace-only value collapsed to `NULL` (same treatment as `raw_job_ingestions.error_message`), NULL-safe trim/non-empty `CHECK` pair. Sanitization against secrets/tokens/stack traces is an application-level responsibility — not proven by this `CHECK` |
| incomplete_results | boolean, not null, default false | true if this source's own result set may be partial (e.g. hit a result cap, paginated fetch stopped early on rate limit) — distinct from total failure; no `CHECK` ties this to `status` (see below) — Phase 2's application logic establishes the normal `status = 'partial'` pairing, not the database |
| created_at | timestamptz, not null, server_default `now()` | |
| updated_at | timestamptz, not null, server_default `now()`, ORM `onupdate=func.now()` | |

**Constraints:**

```sql
UNIQUE (collection_run_id, provider, source)

CHECK (status IN ('running', 'completed', 'partial', 'failed'))

CHECK (
  (status = 'running' AND completed_at IS NULL)
  OR
  (status IN ('completed', 'partial', 'failed') AND completed_at IS NOT NULL)
)

CHECK (completed_at IS NULL OR completed_at >= started_at)

CHECK (jobs_discovered >= 0)
CHECK (jobs_inserted >= 0)
CHECK (jobs_updated >= 0)
CHECK (retry_count >= 0)

CHECK (provider = lower(trim(both E'\t\n\r ' from provider)))
CHECK (trim(both E'\t\n\r ' from provider) <> '')
CHECK (provider ~ '^[a-z0-9][a-z0-9._-]*$')
-- same three, mirrored for source

CHECK (error_category IS NULL OR error_category IN
  ('timeout', 'rate_limited', 'auth_error', 'blocked', 'parse_error',
   'not_found', 'upstream_error', 'unknown'))

CHECK (error_message IS NULL OR error_message = trim(both E'\t\n\r ' from error_message))
CHECK (error_message IS NULL OR trim(both E'\t\n\r ' from error_message) <> '')
```

Four constraint names required an explicit, shortened form beyond the naming
convention's default template: the `collection_run_id` FK, the `status`/`completed_at`
consistency `CHECK`, the `completed_at`/`started_at` ordering `CHECK`, and the
`jobs_discovered` non-negative `CHECK` — this table's own name (33 characters) is long
enough that four of its full constraint names would otherwise exceed Postgres's 63-byte
identifier limit, verified via direct DDL rendering before the migration was written.

**No `CHECK` ties `error_category`/`error_message` to `status`, nor `incomplete_results`
to `status`.** All are simply independent columns, for every status. In particular, a
`status = 'partial'` row does **not** require an error to be populated — incomplete
pagination or a hit result cap is a successful-but-truncated outcome
(`incomplete_results = true`), not necessarily an error condition, and forcing one would
misrepresent "we got some results, cleanly, just not all of them" as a failure. `status =
'failed'` rows are expected (by application convention, not a database rule) to populate
`error_category`, but nothing in the schema enforces that either — the same "don't
enforce narrative/soft expectations with `CHECK`" principle applied to
`identity_conflicts.resolution` above. Likewise, `incomplete_results = true` is not
required to imply, nor implied by, `status = 'partial'` at the database level — Phase 2's
application logic establishes that normal mapping.

**Indexes:** `INDEX (provider, source, started_at DESC)` (the volume-trend query Phase
12 reads — "give me this source's `jobs_discovered` over time"); `INDEX
(collection_run_id)` (explicit, in addition to whatever index the FK itself implies, for
the "all attempts for this run" query).

**Rev 20 changes** (fourteenth Phase 1 implementation slice, `collection_run_provider_
attempts` — Class H per docs/LLM_WORKFLOW.md): this table's design had several decisions
resolved by explicit approval before migration `0015` was written, beyond what this
section already specified:
- **`error_category` is now database-enforced** as a `CHECK`-restricted enum mirroring
  `ProviderErrorCategory`'s 8 current values, rather than left as unconstrained free
  text — matching this schema's general posture of enforcing closed sets at the
  database. Kept as a plain string column (not a native Postgres enum type) so a future
  9th category is a single additive migration. Phase 2+ must keep this list
  synchronized with the Python enum by hand.
- **A `completed_at >= started_at` ordering `CHECK` was added**, extending the pattern
  already established on `job_occurrences`/`identity_conflicts`/`collection_runs` —
  not previously specified for this table.
- **`provider`/`source` now get the same canonical-identifier `CHECK`/ORM-validator
  treatment as `job_occurrences`/`raw_job_ingestions`** (lowercased/trimmed, ASCII-slug
  `CHECK`) — this table's own earlier column list (above, pre-Rev-20) only said "text,
  not null" with no canonicalization specified.
- **`error_message` gets the standard nullable-free-text treatment** (ORM trim +
  blank-to-`NULL`, NULL-safe trim/non-empty `CHECK`) already used for `raw_job_
  ingestions.error_message` — not previously specified in this table's own column list.
- **No `CHECK` ties `incomplete_results` to `status`** — considered and explicitly
  rejected, for the same "don't enforce narrative/soft expectations with `CHECK`"
  reasoning already applied to `error_category`/`error_message` above.
- **`collection_run_id` uses `ON DELETE CASCADE`**, confirmed as not a new pattern for
  this schema (`job_occurrences.job_id`, `candidate_skills.candidate_profile_id`, and
  the `saved_search_*` child tables already use it) — only the parent-table identity is
  new here.

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
| `saved_searches` | `INDEX (user_id)`; `CHECK (name = trim(both E'\t\n\r ' from name))`; `CHECK (trim(both E'\t\n\r ' from name) <> '')`; `CHECK` on `remote_rules`/`polling_schedule` enums; non-negative `CHECK`s on `radius_miles`/`salary_floor`/`preferred_salary`/`recency_limit_hours`; `CHECK (salary_floor <= preferred_salary)`; `CHECK` requiring `enabled_sources`/`scoring_weights` be a top-level JSON object when non-null | reject a non-normalized/empty `name`, an invalid enum, a negative bound, an inverted salary range, or a non-object jsonb value at the database; `radius_miles` has no precision/scale but is non-negative like the other numeric fields — see the table's own section above (Rev 9) |
| `saved_search_titles` | `UNIQUE (saved_search_id, lower(title))`; `CHECK (title = trim(both E'\t\n\r ' from title))`; `CHECK (trim(both E'\t\n\r ' from title) <> '')`; partial `UNIQUE (saved_search_id) WHERE is_primary` | one entry per title per search, case-insensitive; reject a non-normalized or empty title; at most one primary title per search, zero allowed — see the table's own section above (Rev 10) |
| `saved_search_locations` | `UNIQUE (saved_search_id, lower(location_text))`; `CHECK (location_text = trim(both E'\t\n\r ' from location_text))`; `CHECK (trim(both E'\t\n\r ' from location_text) <> '')`; `CHECK` on latitude/longitude range; `CHECK ((latitude IS NULL) = (longitude IS NULL))`; `CHECK (radius_miles_override IS NULL OR radius_miles_override >= 0)` | one entry per location per search, case-insensitive; reject a non-normalized/empty location, an out-of-range or half-geocoded coordinate pair, or a negative radius override — see the table's own section above (Rev 11) |
| `companies` | `UNIQUE (lower(domain)) WHERE domain IS NOT NULL`; `INDEX (normalized_name)`; `CHECK (name = trim(both E'\t\n\r ' from name))`; `CHECK (trim(both E'\t\n\r ' from name) <> '')`; NULL-safe normalized/non-empty `CHECK` pairs on `homepage_url`/`career_page_url`/`industry`; `CHECK (duplicate_of_company_id IS NULL OR duplicate_of_company_id <> id)` | strongest available company identity signal, case-normalized, NULL-safe (any number of `NULL`-domain companies coexist); **no** uniqueness on `normalized_name` (see conservative collision behavior above) — it is a `GENERATED ALWAYS AS (...) STORED` column, not an independently writable one; reject a non-normalized/empty `name`, an optional text field that's present-but-blank/wrapped, or direct self-reference on `duplicate_of_company_id` — see the table's own section above (Rev 12) |
| `jobs` | `INDEX (company_id)`; `CHECK` on `remote_type`/`salary_period` enums; NULL-safe normalized/non-empty `CHECK` pairs on every nullable text column (`requisition_id`, `canonical_url`, `preferred_apply_url`, `title`, `normalized_title`, `job_family`, `department`, `team`, `description_raw`, `description_clean`, `location_raw`, `city`, `state`, `country`, `postal_code`, `employment_type`, `seniority`, `contract_type`, `shift`, `salary_currency`, `education_requirement`, `clearance_requirement`, `visa_sponsorship_status`, `travel_requirement`, `compensation_text`); non-negative + min≤max `CHECK`s on `salary_min`/`salary_max`, `annualized_salary_min`/`max`, `years_experience_min`/`max`; `CHECK` on latitude/longitude range; `CHECK ((latitude IS NULL) = (longitude IS NULL))`; `CHECK` requiring `field_provenance` be a top-level JSON object when non-null; `CHECK (first_seen_at <= last_seen_at)` | no UNIQUE constraint — identity/matching keys live entirely on `job_occurrences`; `company_id` is nullable (`DiscoveredJob.company` is nullable in ARCHITECTURE.md) but `ON DELETE RESTRICT` whenever non-null; reject an invalid enum, a non-normalized/empty optional text field, a negative or inverted numeric range, an out-of-range/half-geocoded coordinate pair, a non-object `field_provenance`, or an inverted observation-time pair — see the table's own section above (Rev 14) |
| `job_occurrences` | `UNIQUE (provider, source, source_tenant_id, source_job_id) WHERE source_job_id IS NOT NULL AND source_tenant_id IS NOT NULL` | natural key for tenant-scoped sources (Rev 3 split — see ADR 0004) |
| `job_occurrences` | `UNIQUE (provider, source, source_job_id) WHERE source_job_id IS NOT NULL AND source_tenant_id IS NULL` | natural key for sources with no tenant concept, e.g. LinkedIn/Indeed (Rev 3 split — the fix for the NULL-distinctness bug, ADR 0004) |
| `job_occurrences` | `UNIQUE (provider, source, source_url_normalized) WHERE source_job_id IS NULL` | fallback natural key when no stable ID is available |
| `job_occurrences` | `INDEX (canonical_url_normalized)` | identity-resolution lookup (ADR 0004 tier 2) |
| `job_occurrences` | `INDEX (provider, source, source_tenant_id, requisition_id_raw)` | identity-resolution lookup (ADR 0004 tier 3 — Rev 3 fix: now scoped by `provider`/`source`, not just `source_tenant_id`, per item 2) |
| `job_occurrences` | `INDEX (job_id, is_active, last_seen_at DESC)` | "active occurrences for this job, freshest first" — the common feed-rendering query |
| `job_occurrences` | `CHECK` requiring `provider`/`source` already lowercase/trimmed/non-empty and matching the ASCII slug grammar `^[a-z0-9][a-z0-9._-]*$` (Rev 16); NULL-safe normalized/non-empty `CHECK` pairs on every other text column (`source_tenant_id`, `source_job_id`, `requisition_id_raw`, `source_url` [not-null], `source_url_normalized`, `apply_url`, `canonical_url`, `canonical_url_normalized`, `applicant_count_text`); `CHECK (canonical_url IS NOT NULL OR canonical_url_normalized IS NULL)`; non-negative `CHECK` on `applicant_count`; `CHECK (first_seen_at <= last_seen_at)` | reject a non-canonical `provider`/`source`, a non-ASCII-slug `provider`/`source`, a non-normalized/empty text field, a normalized canonical URL with no raw URL behind it, a negative applicant count, or an inverted observation-time pair — see the table's own section above (Rev 15/16) |
| `raw_job_ingestions` | `INDEX (job_occurrence_id, fetched_at DESC)` | derives "latest ingestion for this occurrence" without a stored pointer (ADR 0005) |
| `raw_job_ingestions` | `CHECK` requiring `provider`/`source` already lowercase/trimmed/non-empty and matching the ASCII slug grammar `^[a-z0-9][a-z0-9._-]*$`; NULL-safe normalized/non-empty `CHECK` pairs on `source_identifier`/`parser_version`/`error_message`; trim/non-empty `CHECK` on `raw_content_hash` (not-null, no format constraint); `CHECK (jsonb_typeof(raw_payload) = 'object')`; `CHECK` restricting `processing_status` to `fetched`/`parse_error`/`normalized`/`identity_conflict`; `CHECK (processing_status NOT IN ('fetched', 'parse_error') OR job_occurrence_id IS NULL)` (one-directional only — see the table's own section above, Rev 17) | reject a non-canonical `provider`/`source`, a non-normalized/empty text field, a non-object `raw_payload`, an invalid `processing_status`, or a `fetched`/`parse_error` row with a non-null occurrence link — see the table's own section above (Rev 17) |
| `identity_conflicts` | `INDEX (status)`, `INDEX (existing_job_occurrence_id)`, `INDEX (incoming_raw_job_ingestion_id)` | **new in Rev 3** — open-conflict queue lookup and traceback to the occurrence/ingestion in dispute |
| `identity_conflicts` | `CHECK` on `status` enum, `conflict_type` enum, `(status, resolved_at)` consistency, `resolved_at >= created_at`, `existing_value`/`incoming_value` shape conditional on `conflict_type` (object for `evidence_mismatch`, array for `ambiguous_match`), `conflict_type <> 'ambiguous_match' OR existing_job_occurrence_id IS NULL` | reject an invalid `status`/`conflict_type`, an inconsistent status/resolution-timestamp pairing, a resolution timestamp before creation, a snapshot with the wrong top-level JSON shape for its conflict type, or an `ambiguous_match` row with a non-null occurrence link — see the table's own section above (Rev 4/18) |
| `collection_runs` | `INDEX (saved_search_id, started_at DESC)`, `INDEX (status)` | **new in Rev 19** — run history per search and abandoned/still-running-row lookup; lookup support only, does not prevent overlapping runs under concurrency (Phase 9's own database-lock/partial-unique strategy is a separate invariant) |
| `collection_runs` | `CHECK` on `status` enum, `(status, completed_at)` consistency, `completed_at >= started_at`, non-negative `jobs_discovered`/`jobs_inserted`/`jobs_updated`, NULL-safe non-negative `duration_ms`, `jsonb_typeof(providers_enforced_locally) = 'object'`, `jsonb_typeof(failures) = 'array'` | **new in Rev 19** — reject an invalid `status`, an inconsistent status/`completed_at` pairing, a `completed_at` before `started_at`, a negative counter/duration, or a wrong-shape JSONB value; no `CHECK` ties `failures`/counters to `status` — see the table's own section above (Rev 19) |
| `collection_run_provider_attempts` | `UNIQUE (collection_run_id, provider, source)` | one aggregate row per run/provider/source, see table's own section |
| `collection_run_provider_attempts` | `CHECK` on `status` enum, `(status, completed_at)` consistency, `completed_at >= started_at`, non-negative `jobs_discovered`/`jobs_inserted`/`jobs_updated`/`retry_count`, `provider`/`source` canonical-identifier (lowercase/trim/ASCII-slug), `error_category` enum-or-null, `error_message` NULL-safe trim/non-empty | **new in Rev 20** — reject an invalid `status`/`error_category`, an inconsistent status/`completed_at` pairing, a `completed_at` before `started_at`, a negative counter, a non-canonical `provider`/`source`, or a non-normalized/empty `error_message`; no `CHECK` ties `error_category`/`error_message`/`incomplete_results` to `status` — see the table's own section above (Rev 20) |
| `collection_run_provider_attempts` | `INDEX (provider, source, started_at DESC)`, `INDEX (collection_run_id)` | Phase 12's volume-trend query and "all attempts for this run" |
| `user_jobs` | `UNIQUE (user_id, job_id)` | one state row per user per job |
| `user_jobs` | `CHECK` on `(status, applied_at)` | see ADR 0006 — the core invariant fix |

Foreign-key `ON DELETE` behavior (all noted inline above; summarized here for review):

| FK | Behavior | Reasoning |
|---|---|---|
| `candidate_profiles.user_id → users` | CASCADE | profile is meaningless without the user |
| `candidate_skills.candidate_profile_id → candidate_profiles` | CASCADE | |
| `saved_searches.user_id → users` | CASCADE | |
| `saved_search_titles/locations.saved_search_id → saved_searches` | CASCADE | |
| `jobs.company_id → companies` | **RESTRICT** (nullable column) | `company_id` is nullable (Rev 14 — `DiscoveredJob.company` is nullable in ARCHITECTURE.md), but company merges/deletes must be an explicit reconciliation step, never accidental, whenever it is set |
| `job_occurrences.job_id → jobs` | CASCADE | occurrence is meaningless without its job |
| `raw_job_ingestions.job_occurrence_id → job_occurrences` | **SET NULL** | preserve the raw audit trail even if the occurrence is later removed (ADR 0005) |
| `identity_conflicts.existing_job_occurrence_id → job_occurrences` | SET NULL (nullable column) | conflict record survives even if the disputed occurrence is later removed; also naturally NULL for `ambiguous_match` (new in Rev 3) |
| `identity_conflicts.incoming_raw_job_ingestion_id → raw_job_ingestions` | SET NULL (nullable column) | the conflict's own `existing_value`/`incoming_value` jsonb snapshots make the record self-contained even without the FK (new in Rev 3) |
| `jobs.duplicate_group_id → duplicate_groups` | SET NULL (not yet implemented) | a job outlives the grouping mechanism's own lifecycle — deferred to Phase 6 alongside `duplicate_groups` itself (Rev 14); `jobs` migration `0010` does not include this column at all |
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
