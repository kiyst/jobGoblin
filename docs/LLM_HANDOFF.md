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
no longer pending — Codex gave its findings and requested corrections, which are being
addressed in this rotation's Iteration 2 — so the previous Iteration 1 (the
`candidate_skills` implementation pass and Codex's approval of it) was removed rather
than kept alongside two already-reviewed entries. Nothing below was rewritten — only
renumbered, with "Ending commit" backfilled to the actual hash Codex reviewed.*

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: first bounded Phase 1 slice after `candidate_skills` —
  `saved_searches` parent table only. `saved_search_titles`/`saved_search_locations`
  remain out of scope (separate future slices, same incremental pattern as
  `candidate_profiles` -> `candidate_skills`). No auth, no APIs/services, no
  providers/ingestion/matching/normalization, no other Phase 1 table.
- Outcome: model, migration `0006`, factories, and database tests implemented and
  verified against real PostgreSQL. 132 tests passed, 0 skipped (up from 81 — 51 new
  `saved_searches` tests).
- Base/starting commit: `906cf24` (`docs(review): approve candidate skills slice`) —
  Codex's approval commit for the `candidate_skills` slice (previous Iteration 1's
  `Work review`, verdict: approved), fast-forward-merged into `main` by the user
  outside this session (confirmed via `git reflog show main`: "merge
  phase-1/candidate-skills: Fast-forward") before this pass began. Confirmed
  `main`/`origin/main` both at `906cf24` before making any changes. Branch
  `phase-1/saved-searches` created directly from `906cf24`.
- Ending commit or working-tree state: `a267a2f` (`feat(phase-1): implement saved
  searches slice` — this is the commit Codex's `Work review` below actually
  reviewed).
- Separately authorized, file-free operational step performed before this
  implementation pass, at the user's explicit request: the **development** database
  (`jobgoblin`, distinct from the disposable `jobgoblin_test`) was upgraded from `0003`
  to `0005` (head at the time) via `alembic upgrade head` with the default
  `DATABASE_URL`. Row counts in `users`/`candidate_profiles`/`candidate_skills`
  confirmed `0` both before and after. No files were changed, no branch created, no
  commit made for this step, per explicit instruction.
- Product decisions approved by the user before this pass began (proposed in advance
  by the implementing agent, then explicitly overridden on four points by the user
  before implementation — see below):
  1. Every `text[]` column nullable, no server default, `MutableList.as_mutable`
     wrapped from the start (not a later correction, unlike `candidate_profiles`).
  2. `created_at`/`updated_at` added (`docs/DATA_MODEL.md`'s `saved_searches` column
     list omitted them — the same gap already fixed for `users` and
     `candidate_skills`).
  3. **`name`**: normalized non-empty — trimmed of the same four-character whitespace
     set as `skill` (space, tab, LF, CR), case preserved (no lowercasing, since `name`
     has no uniqueness requirement), with matching `CHECK`s
     (`name = trim(both E'\t\n\r ' from name)`, non-empty after trim) and an ORM
     `@validates` normalizer. This explicitly overrides the implementing agent's
     initial proposal of "no `CHECK`."
  4. **`enabled_sources`/`scoring_weights` (jsonb)**: restricted by a `CHECK` requiring
     the stored value be a top-level JSON *object* when non-null
     (`jsonb_typeof(col) = 'object'`). This explicitly overrides the initial proposal
     of "leave fully unconstrained."
  5. **`radius_miles`**: plain, **unconstrained** `numeric` — no precision/scale, no
     non-negative `CHECK`. This explicitly overrides the initial proposal of
     `NUMERIC(6, 2)`. *(Iteration 2 below records that this specific reading — no
     non-negative CHECK at all — was itself an implementer misreading of the
     authorization, corrected after review.)*
  6. **Both `jsonb` columns wrapped with `MutableDict.as_mutable`, with the top-level-
     only tracking limitation explicitly documented** (in the model's docstring and a
     dedicated test) — `MutableDict`, like `MutableList`, only instruments the wrapped
     column's own top-level `__setitem__`/`__delitem__`; a value already nested inside
     one of these columns can be mutated in place without the unit-of-work noticing,
     and the change is still silently dropped on commit.
  7. `salary_floor`, `preferred_salary`, `recency_limit_hours` each get a non-negative
     `CHECK`, plus `salary_floor <= preferred_salary` when both are non-null — carried
     over unchanged from the implementing agent's initial proposal (not addressed by
     the four overrides above, so not treated as conflicting).
  8. `name` has no uniqueness constraint (a user may have multiple saved searches
     sharing a name) — unchanged from the initial proposal.
  9. A plain non-unique `INDEX (user_id)` for the "list a user's saved searches"
     query — unchanged from the initial proposal.
  The implementing agent could not locate the four-point override instruction
  recorded anywhere in this repository or its own prior conversation turns before
  receiving it; it restated its interpretation of each override explicitly before
  implementing, rather than silently guessing or blocking on an unverifiable
  provenance claim.
- Files changed:
  - `backend/app/db/models/saved_search.py` (new) — `SavedSearch` model.
    `REMOTE_RULES`/`POLLING_SCHEDULES` module constants list the allowed enum values,
    reused by tests. `name` uses a `@validates` normalizer (trim only, no lowercasing —
    same case-handling as `CandidateSkill.skill`). All ten `text[]` columns wrapped
    with `MutableList.as_mutable(ARRAY(Text))`; both `jsonb` columns wrapped with
    `MutableDict.as_mutable(JSONB())`. `radius_miles` typed `Numeric`/`Decimal`,
    deliberately without a `CHECK`. A plain `Index("ix_saved_searches_user_id", ...)`
    declared after the class, outside `__table_args__`, since it is a performance
    index, not a correctness constraint.
  - `backend/app/db/models/__init__.py` — registers `SavedSearch` alongside the other
    three models.
  - `backend/app/db/base.py` — docstring updated to mention all four Phase 1 models.
  - `backend/migrations/versions/0006_saved_searches.py` (new) — `down_revision =
    "0005"`. Table created with all constraints defined inline in
    `op.create_table(...)` (the established pattern); the non-unique `user_id` index
    added via a separate `op.create_index(...)`. `downgrade()` drops the index then
    the table.
  - `backend/tests/conftest.py`:
    - Added `make_saved_search`, a factory fixture matching the
      `make_candidate_profile`/`make_candidate_skill` pattern (takes `user_id`
      explicitly).
    - Added `real_committed_user_and_saved_search`, mirroring
      `real_committed_user_and_profile`'s failure-safe real-commit lifecycle/cleanup
      pattern exactly (User + SavedSearch instead of User + CandidateProfile), for
      `saved_searches`' own cascade-delete/`updated_at`/mutation-persistence tests.
  - `backend/tests/test_saved_searches.py` (new) — 51 tests: valid insert/retrieve
    (including `is_active` defaulting `true`); ORM trimming of a whitespace-wrapped
    `name` (case preserved); direct-SQL rejection of an empty, a
    covered-whitespace-only, and a non-normalized `name`; every allowed
    `remote_rules`/`polling_schedule` value accepted, one invalid value each rejected;
    `is_active` default and explicit-`false` settability; all nullable array/jsonb
    fields defaulting to `None`; NULL-vs-empty-array distinction (one representative
    field, mirroring `candidate_profiles`); array-field mutation persisting after
    reload (parameterized across all ten `text[]` fields); jsonb nullable defaults;
    a nested-dict jsonb round-trip; top-level jsonb key mutation persisting after
    reload (parameterized across both `jsonb` fields); a dedicated test proving a
    *nested* jsonb mutation is **not** tracked and is silently dropped (documents
    decision 6's limitation directly); direct-SQL rejection of a non-object jsonb
    value for each `jsonb` column plus one accepted-valid-object case; non-negative
    `CHECK` accepted (zero and positive) / rejected (negative) cases for all three
    integer numeric fields; a dedicated test proving `radius_miles` is genuinely
    unconstrained (accepts a negative value without error — proves decision 5 is
    actually implemented, not merely absent by omission); accepted (equal, ascending,
    either-side-only) and rejected (descending) cases for the salary-ordering `CHECK`;
    nonexistent `user_id` FK rejection; `ON DELETE CASCADE` from `users` (real
    commits); UTC-aware timestamps; and `updated_at` advancing on update (real
    commits).
  - `docs/DATA_MODEL.md` — `saved_searches` marked **Implemented** (parent table only);
    added a "Rev 9" note and updated the table's own column list and the "Phase 1
    constraints & indexes" summary table (which previously had no row for
    `saved_searches` itself) to state every resolved rule explicitly.
  - `docs/ROADMAP.md` — Phase 1 status line now also describes the `saved_searches`
    slice as complete and verified.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the `candidate_skills`
    implementation pass — removed; prior Iteration 2 renumbered to Iteration 1; this
    entry appended as the new Iteration 2).
- Migration revisions: `0006` (new, `down_revision = "0005"`) — adds `saved_searches`.
  `0001`–`0005` unchanged.
- Commands run and exact results:
  - Development-database upgrade (separately authorized, described above):
    `alembic current` → `0003`; row counts confirmed `0`; `alembic upgrade head` →
    `0003 -> 0004 -> 0005`; `alembic current` → `0005 (head)`; row counts confirmed
    `0` again.
  - `git checkout -b phase-1/saved-searches 906cf24` → success, clean tree, `HEAD` at
    `906cf24`.
  - `ruff format .` → 2 files reformatted (the new model and test file) → recheck: 27
    files formatted.
  - `mypy app tests` (first run) → **4 errors**: `MutableDict.as_mutable(JSONB)`
    passed the bare class instead of an instance (fixed: `JSONB()`); a test's indexed
    assignment into a `dict[str, object] | None`-typed nested value (fixed: targeted
    `# type: ignore[index]`, since the test deliberately exercises untyped dynamic
    JSON shape); a test assigned a bare `int` to a `Decimal`-typed attribute (fixed:
    wrapped in `Decimal(...)`).
  - `mypy app tests` (after fixes) → success, 20 source files.
  - `ruff check .` → all checks passed.
  - `pytest -v` (first run) → **1 failed, 131 passed**:
    `test_insert_and_retrieve_valid_saved_search` failed with `MissingGreenlet` — the
    same expired-attribute bug caught (and supposedly learned from) during the
    `candidate_profiles` slice: `user.id` was read in a final assertion *after* the
    saved search's own `commit()` had already expired `user`. Fixed the same way as
    before — capture `user_id = user.id` immediately after the user's own commit,
    before any later commit.
  - `pytest -v` (after the fix) → **132 passed, 0 skipped**.
  - `DATABASE_URL=...jobgoblin_test alembic current` (before any change) → `0006
    (head)` (already upgraded once ad hoc before the first test run).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0005` → success.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0005 -> 0006`
    ("existing `0005 -> 0006`" scenario).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0005` / `upgrade head` → success
    again (round-trip scenario).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.`
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` → success, all tables
    dropped.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, ` -> 0001 -> ... ->
    0005 -> 0006` ("fresh `base -> head`" scenario).
  - `alembic current` against the **development** database (default `DATABASE_URL`,
    no override) → `0005`, unchanged throughout this test-database-only verification
    sequence — confirmed untouched (correctly still one migration behind `jobgoblin_test`,
    since only the dev-database upgrade to `0005` was separately authorized, not `0006`).
  - `pytest -q` (final re-run after the full migration verification sequence) →
    **132 passed**.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "define nullability/defaults/
  uniqueness/checks/indexes/ON DELETE before implementing each table" — nine product
  decisions above, four of which were explicit user overrides of the implementing
  agent's own proposal, none invented during implementation; "every migration is
  reviewed and tested upgrade -> downgrade -> upgrade" — exercised as four scenarios
  (existing `0005 -> 0006`, round-trip, fresh `base -> head`, plus the separately
  authorized dev-database `0003 -> 0005` operational upgrade); "PostgreSQL behavior is
  tested against PostgreSQL" — the `MutableDict` top-level-tracked-but-not-nested
  behavior, and the jsonb-object `CHECK`, are each proven with real Postgres round
  trips and direct-SQL probes, not mocked; "destructive cascades" — the user-to-
  saved-search cascade is proven with real, separately-committed transactions.
- Skipped or unavailable verification: none. Every command above executed for real,
  including both database confirmations.
- Deviations and ADR impact: mypy failed 4 checks and pytest failed 1 test on first
  runs, both for reasons detailed above; fixed and re-verified before reporting
  success. No ADR impact — Phase 1 implementation-slice detail only.
- Known limitations: `MutableDict`'s top-level-only tracking is a real, documented
  (and tested) limitation of this pass's own design, not a defect — a caller that
  mutates a value nested inside `scoring_weights`/`enabled_sources` in place will
  silently lose that change on commit; `updated_at` still only advances for
  ORM-driven writes (unchanged, out of scope for this pass, same as prior tables).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `saved_search_titles`,
  `saved_search_locations`, or any other slice.

### Work review

- Date and reviewing agent: 2026-08-24, Codex.
- Diff/revision reviewed: commit `a267a2f` (`feat(phase-1): implement saved searches
  slice`) against approved base `906cf24` on branch `phase-1/saved-searches`. The branch
  matched `origin/phase-1/saved-searches`, and the working tree was clean before review.
- Verification independently performed:
  - Inspected the complete `906cf24..a267a2f` diff and resulting saved-search model,
    migration `0006`, registration/base changes, factory and real-commit helper, all 51
    new tests, data-model/roadmap changes, and handoff rotation.
  - Confirmed the array mappings use `MutableList`, JSONB mappings use `MutableDict`,
    name normalization uses the approved four-character set, JSONB object checks and
    enum/salary/recency checks match between metadata and migration, and the user FK,
    lookup index, defaults, and timestamps are otherwise consistent.
  - `ruff format --check .`: 27 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 20 source files.
  - `pytest -v`: 132 passed, 0 skipped; this includes a test that currently codifies
    the incorrect acceptance of a negative radius described in finding 1.
  - Independently ran `0006 -> 0005 -> 0006` against `jobgoblin_test`: passed.
  - `alembic check` at test-database head: no new upgrade operations detected.
  - Live PostgreSQL verification after the suite and round-trip: `jobgoblin_test`
    remained at `0006` with zero users/saved searches; the development database
    remained untouched at `0005` with zero users.
- Findings, ordered by severity, with file and line references:
  1. **High — the approved non-negative radius invariant was reversed.**
     `backend/app/db/models/saved_search.py:97-101`,
     `backend/migrations/versions/0006_saved_searches.py:28-30,79`,
     `backend/tests/test_saved_searches.py:454-469`, `docs/DATA_MODEL.md:93-94,259,830`,
     and `docs/ROADMAP.md:156` deliberately allow and document negative
     `radius_miles`. The authorization used "unconstrained `NUMERIC`" to mean no
     precision/scale/rounding/maximum, then separately and explicitly required a
     non-negative `radius_miles` `CHECK`. A negative search radius is also not a valid
     domain magnitude. Add matching model/migration constraints
     (`radius_miles IS NULL OR radius_miles >= 0`), replace the negative-acceptance
     test with zero/positive acceptance and negative rejection, and correct every
     statement that calls the column unconstrained. Keep `Numeric` itself free of
     precision and scale.
  2. **Medium — several explicitly requested persistence/edge contracts are absent
     from the test suite.** `backend/tests/test_saved_searches.py` has no complete-row
     test, no duplicate-name-accepted test, no explicit SQL-NULL-versus-empty-object
     round-trip for both JSONB fields, no direct-SQL JSON `null` rejection, and no
     precise fractional `Decimal` radius round-trip. Its generic top-level JSON test
     (`:339-357`) stores numeric values in `enabled_sources`, rather than exercising
     the supported real shape and the required replacement pattern
     `enabled_sources[provider] = [*old_sources, new_source]`. Add these cases. Keep
     the documented top-level-only `MutableDict` limitation, but prove the supported
     nested-list replacement workflow through a separate-session reload.
  3. **Low — two source comments contain a malformed documentation reference.**
     `backend/app/db/models/saved_search.py:54` and
     `backend/migrations/versions/0006_saved_searches.py:35` say `SS6.5-6.6`; change
     this to `§6.5–6.6` (or plain `sections 6.5–6.6`).
- Missing or inconclusive verification: fresh `base -> head` was reported by the
  implementer but not repeated in this review because the bounded round-trip and
  metadata drift check were sufficient to establish the current migration mechanics;
  it must be rerun after correcting migration `0006`.
- Architecture/documentation consistency: all approved rules except the radius
  invariant are represented consistently. The current model, migration, tests,
  `DATA_MODEL.md`, and `ROADMAP.md` agree with one another about allowing negative
  radius, but that agreement is based on a misreading of the authorization and must be
  corrected together.
- Verdict: changes requested.
- Exact requested corrections:
  1. Add the non-negative `radius_miles` CHECK to model metadata and migration `0006`
     while retaining unconstrained `Numeric` precision/scale; correct its tests and all
     affected documentation.
  2. Add the missing complete/minimal-boundary tests listed in finding 2, including
     realistic `enabled_sources` replacement and separate-session persistence.
  3. Correct the two malformed section references.
  4. Rerun format, lint, mypy, all tests, `0006 -> 0005 -> 0006`, fresh `base -> head`,
     and `alembic check` against `jobgoblin_test`; confirm development remains at
     `0005`. Rotate the ledger, commit/push only `phase-1/saved-searches`, and stop.
     Do not begin either saved-search child table.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: bounded correction pass over the `saved_searches` slice only —
  all three findings and the exact correction pass requested in Iteration 1's `Work
  review` approved as one pass. No `saved_search_titles`, no `saved_search_locations`,
  no new table.
- Outcome: all three findings addressed and verified against real PostgreSQL. 141
  tests passed, 0 skipped (up from 132 — 9 net new tests).
- Base/starting commit: `a267a2f` (`feat(phase-1): implement saved searches slice`) on
  branch `phase-1/saved-searches`, with Codex's review commit `ff039b4`
  (`docs(review): request saved search corrections`) on top. Confirmed via
  `git log --oneline` and `git status` (clean, up to date with origin) before making
  any changes.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
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

Status: awaiting review.
