# LLM Engineering Handoff

Purpose: this file is the shared communication ledger between the implementing LLM and
the reviewing LLM. Update it at the end of every bounded implementation or correction
pass so the user does not have to copy status messages between agents.

This ledger records only the two latest completed iterations. Git remains the source of
truth for diffs and rollback; record commit or base references whenever they exist.

## Required workflow

1. Before working, read the master project documentation, `PHASE_RISK_CHECKLIST.md`,
   and both iterations in this file.
2. The implementing LLM completes only the approved slice, runs the required checks,
   and fills in a new `Work done` section. It must not fill in its own `Work review`.
3. The reviewing LLM independently inspects the repository and actual diff, runs
   proportionate checks, gives the user its findings, and writes the same findings in
   that iteration's `Work review` section. A review does not authorize code changes.
4. The implementing LLM reads the latest review on its next run. It changes only
   findings approved by the user, then records that correction pass as the next
   iteration.
5. Never allow both LLMs to edit implementation files simultaneously. Only the active
   implementer writes code; the reviewer writes only its `Work review` entry unless the
   user explicitly transfers implementation ownership.

## Two-iteration rotation rule

- Keep at most two completed iterations below.
- When adding a third iteration, delete only the oldest iteration, retain the newer
  iteration, and append the new one after it.
- Renumber the retained entries as `Iteration 1` and `Iteration 2` so `Iteration 2` is
  always the newest.
- Never erase an iteration whose `Work review` is still pending.
- Do not rewrite the other LLM's entry. Add corrections or disagreements to the next
  appropriate section and support them with file paths, tests, or documentation.

## Git workflow

Agents may automatically commit and push completed passes to the current task branch.
The user remains the only merge authority.

After completing an authorized pass and updating the agent's assigned handoff section:

1. Run all validation required for the bounded slice.
2. Inspect `git status` and the staged diff. Confirm that no secrets, `.env` files,
   caches, virtual environments, database files, generated artifacts, unrelated user
   changes, or other out-of-scope files will be committed.
3. Commit only files belonging to the authorized pass, using a descriptive conventional
   commit message.
4. Push only to the current task branch. Never push directly to `main`.
5. Never merge, force-push, rewrite or rebase shared history, delete branches, or create
   tags without explicit user authorization.
6. Stop after pushing and report the branch, commit hash, validation results, and any
   uncommitted files. Wait for the next agent or user approval.

Role boundaries:

- The implementing LLM may commit implementation files and its own `Work done` entry.
- The reviewing LLM may commit only its own `Work review` entry unless the user
  explicitly authorizes implementation changes.
- Neither LLM may rewrite the other LLM's handoff content.
- Only one LLM may edit or perform Git writes at a time.
- A successful push is a checkpoint, not approval to begin another slice.
- Only the user may approve merging a task branch into `main`.

Recommended history per bounded slice:

```text
feat(phase-N): implement the approved slice
docs(review): record independent review of the slice
fix(phase-N): address approved review findings
docs(review): verify the corrected slice
```

Do not create an extra commit merely to insert that same commit's hash into its own
handoff entry. Before committing, record the branch and write `Ending commit: this
commit`. After committing, report the actual hash in the agent's final response. The Git
history already binds the handoff entry to its commit; the following agent must resolve
and record the actual commit it reviewed.

---

## Iteration 1

*Rotated in from "Iteration 2" per the two-iteration rule: its `Work review` (below) is
no longer pending — Codex's verdict was "approved," with no requested corrections — so
the previous Iteration 1 (the first `saved_searches` implementation pass and Codex's
"changes requested" review of it, already superseded by this iteration's fixes) was
removed rather than kept alongside two already-reviewed entries. Nothing below was
rewritten — only renumbered, with "Ending commit" backfilled to the actual hash Codex
reviewed.*

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: bounded correction pass over the `saved_searches` slice only —
  all three findings and the exact correction pass requested in the previous
  iteration's `Work review` approved as one pass. No `saved_search_titles`, no
  `saved_search_locations`, no new table.
- Outcome: all three findings addressed and verified against real PostgreSQL. 141
  tests passed, 0 skipped (up from 132 — 9 net new tests).
- Base/starting commit: `a267a2f` (`feat(phase-1): implement saved searches slice`) on
  branch `phase-1/saved-searches`, with Codex's review commit `ff039b4`
  (`docs(review): request saved search corrections`) on top. Confirmed via
  `git log --oneline` and `git status` (clean, up to date with origin) before making
  any changes.
- Ending commit or working-tree state: `223ccb4` (`fix(phase-1): restore non-negative
  radius check and add missing saved search tests` — this is the commit Codex's `Work
  review` below actually reviewed and approved).
- Migration `0006` was corrected **in place**, not via a new forward migration:
  unlike the `0002`/`0003` situation, `0006` had not yet been applied to the
  **development** database (which was deliberately stopped at `0005` per a prior,
  separately authorized instruction) — only to the disposable `jobgoblin_test`
  database, which is safe to rebuild. There is no already-applied-elsewhere version to
  preserve or drift from, so no `0007` corrective migration was needed.
- Files changed:
  - `backend/app/db/models/saved_search.py` — added
    `CheckConstraint("radius_miles IS NULL OR radius_miles >= 0", name=
    "radius_miles_non_negative")` to `__table_args__`; corrected the column's comment
    (previously claimed "no non-negative CHECK ... explicit product decision"); fixed
    `SS6.5-6.6` → `§6.5–6.6` in the class docstring. Addresses findings 1 and 3.
  - `backend/migrations/versions/0006_saved_searches.py` — added the matching
    `sa.CheckConstraint` (`op.f("ck_saved_searches_radius_miles_non_negative")`);
    corrected the docstring's claim about `radius_miles` being unconstrained; fixed
    the same `SS6.5-6.6` typo; added a docstring paragraph explaining the in-place
    correction (see above). Addresses findings 1 and 3.
  - `backend/tests/test_saved_searches.py`:
    - Replaced `test_radius_miles_is_unconstrained_and_accepts_a_negative_value` with
      `test_radius_miles_non_negative_check_accepts_zero_and_positive` (parameterized
      over `Decimal(0)`/`Decimal(5)`), `test_radius_miles_non_negative_check_rejects_
      negative_value`, and `test_radius_miles_preserves_fractional_precision`
      (`Decimal("12.75")` round-trip, proving precision/scale is still unconstrained
      even though the value must now be non-negative). Addresses finding 1.
    - Added `test_insert_and_retrieve_a_fully_populated_saved_search` (every column
      populated at once) and `test_duplicate_name_across_saved_searches_is_accepted`
      (two saved searches sharing a `name` for the same user). Addresses finding 2.
    - Added `test_explicit_empty_jsonb_object_is_distinct_from_null`, parameterized
      over both `jsonb` fields — explicit SQL-`NULL`-versus-`{}` round-trip, mirroring
      the existing array NULL-vs-empty test. Addresses finding 2.
    - Added `test_enabled_sources_rejects_a_json_null_literal` — a direct-SQL
      `'null'::jsonb` insert, distinct from a genuine SQL `NULL`, rejected by the same
      object-only `CHECK`. Addresses finding 2.
    - Added `test_enabled_sources_provider_list_replacement_persists_after_reload` —
      exercises the actual documented `enabled_sources` shape
      (`{"jobspy": ["linkedin"]}`) and the supported top-level-replacement workaround
      for `MutableDict`'s nested-mutation limitation
      (`enabled_sources["jobspy"] = [...]`, not an in-place list mutation), verified
      through a separate-session reload. The existing generic
      `test_setting_a_top_level_jsonb_key_persists_after_reload` (parameterized over
      both `jsonb` fields with an arbitrary `{"first": 1}` shape) was left as-is — it
      tests generic `MutableDict` key-tracking mechanics, which is a distinct, still
      valid purpose from the new realistic-shape test. Addresses finding 2.
  - `docs/DATA_MODEL.md` — the Rev 9 note, the `saved_searches` table's own
    `radius_miles` row, and the consolidated "Phase 1 constraints & indexes" row now
    state the non-negative `CHECK` instead of "deliberately unconstrained." Addresses
    finding 1.
  - `docs/ROADMAP.md` — same correction in the Phase 1 status line. Addresses
    finding 1.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the `candidate_skills`
    implementation pass — removed; prior Iteration 2 renumbered to Iteration 1; this
    entry appended as the new Iteration 2).
- Migration revisions: `0006` corrected in place (see above, not a new revision
  number) — now includes `ck_saved_searches_radius_miles_non_negative`. `0001`–`0005`
  unchanged.
- Commands run and exact results:
  - `ruff format .` → 1 file reformatted (`test_saved_searches.py`) → recheck: 27
    files formatted.
  - `ruff check .` → all checks passed.
  - `mypy app tests` → success, 20 source files.
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` / `upgrade head` →
    success — full rebuild from scratch since `0006` changed in place and the
    previously-applied version was stale; `alembic current` → `0006 (head)`.
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0005` / `upgrade head` →
    success (round-trip scenario, on the corrected migration).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.`
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` / `upgrade head` →
    success, ` -> 0001 -> ... -> 0005 -> 0006` (fresh `base -> head`, explicitly
    rerun per the review's request since it wasn't independently repeated last time).
  - `alembic current` against the **development** database (default `DATABASE_URL`,
    no override) → `0005`, unchanged throughout — confirmed untouched.
  - `pytest -v` → **141 passed, 0 skipped** (up from 132 — 9 net new tests: 2 replaced
    with 3 for `radius_miles`, plus 2 parameterized NULL-vs-`{}` cases, 1 JSON-`null`
    rejection, 1 provider-list-replacement, 1 complete-row, 1 duplicate-name).
  - `pytest -q` (final re-run after the full migration verification sequence) →
    **141 passed**.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "every migration is reviewed and
  tested upgrade -> downgrade -> upgrade" — re-verified as three scenarios (round-trip,
  fresh `base -> head`, `alembic check`) specifically because the migration's own DDL
  changed in this pass; "PostgreSQL behavior is tested against PostgreSQL" — the
  corrected non-negative invariant, the SQL-`NULL`-vs-JSON-`{}`/`null` distinctions,
  and the realistic `enabled_sources` replacement workflow are all proven against real
  Postgres, not asserted from code alone.
- Skipped or unavailable verification: none. Every command above executed for real,
  including the development-database confirmation.
- Deviations and ADR impact: none — every correction matched the review's exact
  requests on the first attempt; no unexpected failures this pass. No ADR impact —
  Phase 1 implementation-slice detail only.
- Known limitations: none new, beyond what Iteration 1 already documented (the
  `MutableDict` top-level-only tracking limitation and `updated_at` advancing only for
  ORM-driven writes).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin either saved-search
  child table.

### Work review

- Date and reviewing agent: 2026-08-24, Codex.
- Diff/revision reviewed: commit `223ccb4` (`fix(phase-1): restore non-negative radius
  check and add missing saved search tests`) against review commit `ff039b4` on branch
  `phase-1/saved-searches`. The branch matched `origin/phase-1/saved-searches`, and the
  working tree was clean before review.
- Verification independently performed:
  - Inspected the complete `ff039b4..223ccb4` diff and resulting model constraint,
    corrected migration `0006`, all new/replaced tests, data-model/roadmap corrections,
    source references, and handoff rotation.
  - Confirmed model metadata and migration now both enforce
    `radius_miles IS NULL OR radius_miles >= 0` while retaining plain `Numeric` without
    declared precision or scale.
  - Confirmed the complete-row, duplicate-name, JSON SQL-NULL-versus-`{}`, JSON `null`
    rejection, realistic provider-list replacement, radius boundary, and fractional
    round-trip cases are present and exercise real PostgreSQL behavior where required.
  - `ruff format --check .`: 27 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 20 source files.
  - `pytest -v`: 141 passed, 0 skipped.
  - Independently rebuilt `jobgoblin_test` via `base -> 0001 -> ... -> 0006`: passed.
  - Independently ran `0006 -> 0005 -> 0006`: passed.
  - `alembic check` at corrected test-database head: no new upgrade operations
    detected.
  - Live-schema inspection confirmed `saved_searches.radius_miles` reports no numeric
    precision or scale and that `ck_saved_searches_radius_miles_non_negative` exists.
  - Live database verification after all checks: `jobgoblin_test` remained at `0006`
    with zero users/saved searches; development remained untouched at `0005` with zero
    users.
- Findings, ordered by severity, with file and line references: none.
- Missing or inconclusive verification: none material for this bounded correction pass.
- Architecture/documentation consistency: the corrected radius invariant, unrestricted
  numeric precision/scale, JSONB semantics and mutation contract, name rules, enums,
  salary/recency invariants, FK/index/default/timestamp behavior, migration chain,
  tests, `DATA_MODEL.md`, and `ROADMAP.md` are mutually consistent and match the
  approved decisions.
- Verdict: approved.
- Exact requested corrections: none. The `saved_searches` parent-table slice is
  accepted. Do not begin `saved_search_titles`, `saved_search_locations`, modify or
  merge `main`, or advance to another slice until the user explicitly approves it.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: first bounded Phase 1 slice after `saved_searches` —
  `saved_search_titles` only. `saved_search_locations` remains out of scope (separate
  future slice, same incremental pattern as every prior Phase 1 table). No other
  table, no auth, no APIs/services.
- Outcome: model, migration `0007`, factories, and database tests implemented and
  verified against real PostgreSQL. 167 tests passed, 0 skipped (up from 141 — 26 new
  `saved_search_titles` tests).
- Base/starting commit: `33a38e3` (`docs(review): approve saved searches slice`) —
  Codex's approval commit for the `saved_searches` slice (Iteration 1's `Work review`,
  verdict: approved). Confirmed `main`/`origin/main` both at `33a38e3` and the working
  tree clean before making any changes. Also confirmed the development database was
  already at `0006` (this upgrade happened outside this session — flagged to the user
  as an external repo-state change, consistent with the earlier `main` fast-forward —
  and matched what the user separately stated). Branch `phase-1/saved-search-titles`
  created directly from `33a38e3`.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
- Product decisions approved by the user before this pass began (proposed in advance
  by the implementing agent, all ten confirmed as-proposed with no overrides this
  time):
  1. `id`: application-generated UUID primary key.
  2. `saved_search_id`: non-null FK to `saved_searches.id`, `ON DELETE CASCADE`.
  3. `title`: non-null, case-preserving text; trimmed of exactly space/tab/LF/CR via a
     matching ORM `@validates` normalizer and database `CHECK` (same pattern as
     `candidate_skills.skill`/`saved_searches.name`).
  4. Empty and covered-whitespace-only titles rejected via a `CHECK`.
  5. Case-insensitive, per-search uniqueness via a functional unique index on
     `(saved_search_id, lower(title))`.
  6. `is_primary`: non-null boolean, `server_default false`.
  7. At most one primary title per saved search enforced by a partial unique index on
     `saved_search_id WHERE is_primary`.
  8. Zero primary titles is allowed at the database level — no trigger attempting to
     enforce "exactly one."
  9. `created_at`/`updated_at` added as non-null `timestamptz` columns with the
     established `server_default`/ORM `onupdate` convention (the same recurring gap
     already fixed for `users`, `candidate_skills`, `saved_searches`).
  10. No separate plain index on `saved_search_id` — the composite unique index
      already supports lookups by its leading column.
- Files changed:
  - `backend/app/db/models/saved_search_title.py` (new) — `SavedSearchTitle` model.
    `title` uses a `@validates` normalizer (trim only, no lowercasing — same
    case-handling as `CandidateSkill.skill`/`SavedSearch.name`). The case-insensitive
    unique index and the partial primary-title unique index are both declared as
    module-level `Index(...)` calls after the class, outside `__table_args__`, matching
    the established pattern for functional/expression indexes.
  - `backend/app/db/models/__init__.py` — registers `SavedSearchTitle` alongside the
    other four models.
  - `backend/app/db/base.py` — docstring updated to mention all five Phase 1 models.
  - `backend/migrations/versions/0007_saved_search_titles.py` (new) — `down_revision =
    "0006"`. Table created with all constraints defined inline in
    `op.create_table(...)` (the established pattern); both indexes (the composite
    functional unique index and the partial primary-title unique index) added via
    separate `op.create_index(...)` calls, the latter using
    `postgresql_where=sa.text("is_primary")`. `downgrade()` drops both indexes then
    the table.
  - `backend/tests/conftest.py`:
    - Added `make_saved_search_title`, a factory fixture matching the
      `make_candidate_skill` pattern (takes `saved_search_id` explicitly).
    - Added `real_committed_user_saved_search_and_title`, mirroring
      `real_committed_user_profile_and_skill`'s failure-safe real-commit lifecycle/
      cleanup pattern exactly (built on top of `real_committed_user_and_saved_search`),
      for `saved_search_titles`' own cascade-delete/`updated_at` tests.
  - `backend/tests/test_saved_search_titles.py` (new) — 26 tests: valid insert/
    retrieve; ORM trimming of a whitespace-wrapped title (case preserved); direct-SQL
    rejection of an empty, a covered-whitespace-only, and a non-normalized title;
    direct-SQL rejection of a whitespace-wrapped duplicate attempting to bypass the
    uniqueness index; same-case and case-insensitive duplicate rejection;
    confirmation that case is preserved despite case-insensitive uniqueness; the same
    title accepted on two different saved searches (proves per-search scoping);
    distinct titles accepted on one saved search; nonexistent `saved_search_id` FK
    rejection; `is_primary` defaulting to `false` and settable to `true`; direct-SQL
    `NULL is_primary` rejection; one primary plus multiple non-primary titles on one
    search accepted; two primary titles on the same search rejected; primary titles on
    two different searches accepted; zero primary titles accepted; changing which
    title is primary by clearing the old one before setting the new one (two
    sequential commits, since setting the new primary before clearing the old would
    violate the partial unique index); `ON DELETE CASCADE` from `saved_searches` (real
    commits) proven two ways — deleting a saved search removes its own title, and a
    second, independent saved search's title survives that same deletion untouched;
    UTC-aware timestamps; and `updated_at` advancing on both an ORM title-text update
    and an ORM `is_primary` update (two separate tests, both real commits).
  - `docs/DATA_MODEL.md` — `saved_search_titles` marked **Implemented**; added a
    "Rev 10" note and updated the table's own column list (adding `created_at`/
    `updated_at`, marking `title`/`is_primary` not null, documenting the partial
    unique index) and the "Phase 1 constraints & indexes" summary table.
  - `docs/ROADMAP.md` — Phase 1 status line now also describes the
    `saved_search_titles` slice as complete and verified.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the `saved_searches`
    correction pass — removed; prior Iteration 2 renumbered to Iteration 1; this entry
    appended as the new Iteration 2).
- Migration revisions: `0007` (new, `down_revision = "0006"`) — adds
  `saved_search_titles`. `0001`–`0006` unchanged.
- Commands run and exact results:
  - `git checkout -b phase-1/saved-search-titles 33a38e3` → success, clean tree,
    `HEAD` at `33a38e3`.
  - `ruff format .` → 1 file reformatted (the new test file, before an `SIM117`
    nested-`with` fix) → recheck: 30 files formatted.
  - `ruff check .` (first run) → 1 finding: `SIM117` (nested `async with` statements
    in the two-independent-saved-searches cascade test) → combined into a single
    `async with (... , ...):` statement → all checks passed.
  - `mypy app tests` → success, 22 source files.
  - `pytest -v` (first and only run) → **167 passed, 0 skipped** — no failures this
    time; the expired-attribute (`MissingGreenlet`) bug that recurred on the two
    previous slices did not recur here, since `_insert_saved_search`'s returned id is
    captured before any later commit.
  - `DATABASE_URL=...jobgoblin_test alembic current` (before any change) → `0006`.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0006 -> 0007`
    ("existing `0006 -> 0007`" scenario).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0006` / `upgrade head` →
    success (round-trip scenario).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.`
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` / `upgrade head` →
    success, ` -> 0001 -> ... -> 0006 -> 0007` (fresh `base -> head`).
  - `alembic current` against the **development** database (default `DATABASE_URL`,
    no override) → `0006`, unchanged throughout — confirmed untouched.
  - `pytest -q` (final re-run after the full migration verification sequence) →
    **167 passed**.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "define nullability/defaults/
  uniqueness/checks/indexes/ON DELETE before implementing each table" — all ten
  product decisions above were approved before migration `0007` was written, none
  invented during implementation; "every migration is reviewed and tested upgrade ->
  downgrade -> upgrade" — exercised as four scenarios (existing `0006 -> 0007`,
  round-trip, fresh `base -> head`, `alembic check`); "PostgreSQL behavior is tested
  against PostgreSQL" — the partial-unique-index primary-title invariant (including
  the zero-primary-allowed and change-of-primary cases) is proven against real
  Postgres constraint enforcement, not asserted from code; "destructive cascades" —
  proven both for the deleted search's own title and for a second, unrelated search's
  title surviving untouched, using real, separately-committed transactions.
- Skipped or unavailable verification: none. Every command above executed for real,
  including the development-database confirmation.
- Deviations and ADR impact: none — `ruff check` caught one `SIM117` style finding,
  fixed before the first full verification pass; no test failures at any point. No
  ADR impact — Phase 1 implementation-slice detail only.
- Known limitations: "exactly one primary title" is intentionally unenforced at the
  database level (decision 8) — a saved search with zero primary titles is valid and
  the application layer, not the schema, is responsible for prompting the user to pick
  one if that UX is ever needed; `updated_at` still only advances for ORM-driven
  writes (unchanged, out of scope for this pass, same as prior tables).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin
  `saved_search_locations`.

### Work review

- Date and reviewing agent: 2026-08-24, Codex.
- Diff/revision reviewed: commit `195eb09` (`feat(phase-1): implement saved search
  titles slice`) against approved base `33a38e3` on branch
  `phase-1/saved-search-titles`. The branch matched
  `origin/phase-1/saved-search-titles`, and the working tree was clean before review.
- Verification independently performed:
  - Inspected the complete `33a38e3..195eb09` diff and resulting model, migration
    `0007`, model registration, factory/real-commit helper, all 26 new tests,
    data-model/roadmap changes, and handoff rotation.
  - Confirmed the title normalization checks, case-insensitive scoped unique index,
    partial primary-title index, FK cascade, timestamps, and model/migration metadata
    are structurally consistent with the approved decisions.
  - `ruff format --check .`: 30 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 22 source files.
  - `pytest -v`: 167 passed, 0 skipped.
  - Independently rebuilt `jobgoblin_test` via `base -> 0001 -> ... -> 0007`: passed.
  - Independently ran `0007 -> 0006 -> 0007`: passed.
  - `alembic check` at test-database head: no new upgrade operations detected.
  - Live-schema inspection confirmed PostgreSQL has `is_primary DEFAULT false`, the
    functional index on `(saved_search_id, lower(title))`, and the partial unique index
    on `saved_search_id WHERE is_primary`.
  - Live database verification after all checks: `jobgoblin_test` contained zero users
    and titles; development remained untouched at `0006` with zero users.
- Findings, ordered by severity, with file and line references:
  1. **Medium — the server-default test supplies the value itself and therefore cannot
     detect a missing database default.** `backend/tests/conftest.py:246-260` defines
     `make_saved_search_title(..., is_primary=False)` and always passes that value into
     the model. `backend/tests/test_saved_search_titles.py:297-311` uses this factory,
     so `test_is_primary_defaults_to_false` explicitly inserts `false`; it would still
     pass if migration `0007` omitted `server_default false`. This is particularly
     important because the current Alembic environment does not enable explicit
     server-default comparison. Replace or rewrite the test so the insert genuinely
     omits `is_primary` (preferably a raw SQL `INSERT ... RETURNING is_primary`, or an
     ORM instance constructed without that attribute), then assert PostgreSQL supplies
     `false`. The implementation is currently correct—the live-schema inspection above
     confirmed it—but the committed regression test does not prove that invariant.
- Missing or inconclusive verification: only the automated server-default assertion
  described above; the current live database was inspected directly and is correct.
- Architecture/documentation consistency: model, migration, live schema, indexes,
  constraints, behavior, `DATA_MODEL.md`, and `ROADMAP.md` are otherwise mutually
  consistent and match all ten approved decisions.
- Verdict: changes requested.
- Exact requested corrections:
  1. Correct `test_is_primary_defaults_to_false` so the tested insert omits
     `is_primary` and proves the database server default supplies `false`. Keep the
     explicit-false and explicit-true paths covered separately as useful.
  2. Rerun format, lint, mypy, all tests, `0007 -> 0006 -> 0007`, and `alembic check`
     against `jobgoblin_test`; confirm development remains at `0006`. Rotate the
     ledger, commit/push only `phase-1/saved-search-titles`, and stop. No model,
     migration, or product-document changes are requested unless the corrected test
     exposes a real mismatch. Do not begin `saved_search_locations`.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.
