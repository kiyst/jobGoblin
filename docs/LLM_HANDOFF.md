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
the previous Iteration 1 (the correction pass over `candidate_profiles` and Codex's
approval of it) was removed rather than kept alongside two already-reviewed entries.
Nothing below was rewritten — only renumbered.*

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: first bounded Phase 1 slice after `candidate_profiles` —
  `candidate_skills` only. No `saved_searches`, no auth, no APIs/services, no
  providers/ingestion/matching/normalization, no other Phase 1 table.
- Outcome: model, migration `0005`, factories, and database tests implemented and
  verified against real PostgreSQL. 81 tests passed, 0 skipped (up from 61 — 20 new
  `candidate_skills` tests).
- Base/starting commit: `7817073` (`docs(review): approve candidate profile
  corrections`) on branch `phase-1/candidate-profiles` — Codex's approval commit for
  the `candidate_profiles` slice (previous Iteration 1's `Work review`, verdict:
  approved). Confirmed via `git status` (clean, up to date with origin) and
  `git log --oneline` before making any changes. Branch `phase-1/candidate-skills`
  created directly from `7817073`, per the user's explicit instruction — `main` was
  not touched.
- Ending commit or working-tree state: `9d35f75` (`feat(phase-1): implement candidate
  skills slice` — this is the commit Codex's `Work review` below actually reviewed and
  approved).
- Product decisions approved by the user before this pass began (proposed in advance,
  not invented during implementation):
  1. `created_at`/`updated_at` added as non-null `timestamptz` columns with
     `server_default now()` and ORM `onupdate=func.now()` — `docs/DATA_MODEL.md`'s
     `candidate_skills` column list had omitted them despite the project's global
     "all tables have these unless noted" convention.
  2. `skill` is normalized by trimming exactly the same four-character whitespace set
     as `users.email` (space, tab, LF, CR), preserving case and internal whitespace —
     unlike `email`, never lowercased.
  3. Database `CHECK`s requiring `skill = trim(both E'\t\n\r ' from skill)` and
     `trim(both E'\t\n\r ' from skill) <> ''`, mirroring `email`'s normalization/
     not-empty pair.
  4. A matching ORM `@validates` normalizer using exactly the same four-character set
     — explicitly not Python's unrestricted `.strip()`, for the same reason `email`'s
     validator doesn't use it (Postgres's `trim()` and Python's `.strip()` disagree on
     which characters count as whitespace).
  5. Case-insensitive, profile-scoped uniqueness via a functional unique index on
     `(candidate_profile_id, lower(skill))`.
  6. `category` nullable free text, no enum `CHECK`.
  7. `priority` not null, `CHECK`-restricted to `must_have` / `preferred`.
- Files changed:
  - `backend/app/db/models/candidate_skill.py` (new) — `CandidateSkill` model. `skill`
    uses a `@validates` normalizer (trim only, no lowercasing — the opposite case-
    handling from `User._normalize_email`). `PRIORITIES` module constant lists the two
    allowed values, reused by tests. The case-insensitive unique index is declared with
    `Index(..., CandidateSkill.candidate_profile_id, func.lower(CandidateSkill.skill),
    unique=True)`, the same pattern as `users`' `lower(email)` index.
  - `backend/app/db/models/__init__.py` — registers `CandidateSkill` alongside the
    other two models.
  - `backend/app/db/base.py` — docstring updated to mention all three Phase 1 models.
  - `backend/migrations/versions/0005_candidate_skills.py` (new) — `down_revision =
    "0004"`. Table created with all constraints defined inline in
    `op.create_table(...)` (the `0002_users.py`/`0004_candidate_profiles.py` pattern);
    the functional unique index added via a separate `op.create_index(...)`, matching
    `0002`'s `lower(email)` index. `downgrade()` drops the index then the table.
  - `backend/tests/conftest.py`:
    - Added `make_candidate_skill`, a factory fixture matching the
      `make_candidate_profile` pattern (takes `candidate_profile_id` explicitly).
    - Moved `_real_committed_user_and_profile` here from
      `test_candidate_profiles.py`, renamed `real_committed_user_and_profile` (no
      leading underscore, now a shared cross-module helper) — required so
      `candidate_skills`' own real-commit tests (cascade delete, `updated_at`
      advancement) could reuse the same failure-safe lifecycle/cleanup pattern without
      one test module importing from another, per the user's explicit instruction.
      Behavior is unchanged from the version reviewed and approved in the previous
      iteration.
    - Added `real_committed_user_profile_and_skill`, which builds on the above by
      additionally creating a `CandidateSkill` on the same real-commit lifecycle, with
      its own best-effort cleanup (skill, then — via the wrapped helper — profile,
      then user) so a partially cascaded state is skipped rather than treated as an
      error. Defaults `profile_kwargs["remote_preference"]` to `"no_preference"` so
      callers that only care about the skill don't have to supply it.
  - `backend/tests/test_candidate_profiles.py` — updated to import
    `real_committed_user_and_profile` from `tests.conftest` instead of defining it
    locally; call sites renamed to match. No behavioral change; re-verified all 61
    existing tests still pass unmodified otherwise.
  - `backend/tests/test_candidate_skills.py` (new) — 20 tests: valid insert/retrieve;
    ORM trimming of a whitespace-wrapped skill (case preserved); direct-SQL rejection
    of an empty, a covered-whitespace-only, and a non-normalized (leading/trailing-
    wrapped) skill; direct-SQL rejection of a whitespace-wrapped duplicate attempting
    to bypass the uniqueness index (mirroring `test_users.py`'s equivalent test —
    the normalization `CHECK` rejects it before the index is ever consulted);
    same-case and case-insensitive duplicate rejection; confirmation that case is
    preserved despite case-insensitive uniqueness; the same skill accepted on two
    different profiles (proves per-profile scoping); distinct skills accepted on one
    profile; nonexistent `candidate_profile_id` FK rejection; `ON DELETE CASCADE` from
    `candidate_profiles` (real commits via the new fixture-shared helper); every
    allowed `priority` value accepted; an invalid `priority` rejected; `category`
    defaulting to `None` and accepting arbitrary free text; UTC-aware timestamps; and
    `updated_at` advancing on update (same real-commit pattern as the other two
    tables' equivalent tests).
  - `docs/DATA_MODEL.md` — `candidate_skills` marked **Implemented**; added a "Rev 8"
    note and updated the table's own column list (adding `created_at`/`updated_at`,
    marking `skill`/`priority` not null) and the "Phase 1 constraints & indexes"
    summary table to state the normalization/not-empty/priority `CHECK`s explicitly.
  - `docs/ROADMAP.md` — Phase 1 status line now also describes the `candidate_skills`
    slice as complete and verified.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the first
    `candidate_profiles` implementation pass — removed; prior Iteration 2 renumbered
    to Iteration 1; this entry appended as the new Iteration 2).
- Migration revisions: `0005` (new, `down_revision = "0004"`) — adds
  `candidate_skills`. `0001`–`0004` unchanged.
- Commands run and exact results:
  - `git checkout -b phase-1/candidate-skills 7817073` → success, clean tree, `HEAD`
    at `7817073`.
  - `ruff format .` → 24 files left unchanged (no reformatting needed at any point in
    this pass).
  - `ruff check .` → all checks passed.
  - `mypy app tests` → success, 18 source files.
  - `pytest -v` (first run, after adding `real_committed_user_profile_and_skill` and
    the new test file) → **2 failed, 79 passed**: both new real-commit tests
    (`test_deleting_profile_cascades_to_candidate_skill`,
    `test_updating_a_skill_advances_updated_at`) failed with a `NotNullViolationError`
    on `candidate_profiles.remote_preference` — `real_committed_user_profile_and_skill`
    forwarded an empty `profile_kwargs` by default, and unlike the
    `make_candidate_profile` fixture, the underlying
    `real_committed_user_and_profile` helper has no default for
    `remote_preference`. Fixed by defaulting `remote_preference` to
    `"no_preference"` inside `real_committed_user_profile_and_skill` specifically
    (not the shared, lower-level helper, which intentionally requires callers to be
    explicit) whenever the caller doesn't override it.
  - `pytest -v` (after the fix) → **81 passed, 0 skipped**.
  - `DATABASE_URL=...jobgoblin_test alembic current` (before any change) → `0004`.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0004 -> 0005`
    ("existing `0004 -> 0005`" scenario).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0004` → success.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0004 -> 0005`
    again (round-trip scenario, repeated twice against the same running instance).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.`
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` → success, all tables
    dropped.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, ` -> 0001 -> 0002
    -> 0003 -> 0004 -> 0005` ("fresh `base -> head`" scenario).
  - `alembic current` against the **development** database (default `DATABASE_URL`,
    no override) → `0003`, unchanged throughout — confirmed untouched.
  - `pytest -q` (final re-run after the full migration verification sequence) →
    **81 passed**.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "define nullability/defaults/
  uniqueness/checks/indexes/ON DELETE before implementing each table" — all seven
  product decisions above were approved before migration `0005` was written, none
  invented during implementation; "every migration is reviewed and tested upgrade ->
  downgrade -> upgrade" — exercised as four separate scenarios (existing `0004 ->
  0005`, round-trip twice, fresh `base -> head`); "PostgreSQL behavior is tested
  against PostgreSQL" — every normalization/uniqueness/priority `CHECK` has both a
  direct-SQL and (where applicable) an ORM-path test exercising real Postgres, not
  mocked; "destructive cascades" — the profile-to-skill cascade is proven with real,
  separately-committed transactions, not merely asserted from ORM configuration.
- Skipped or unavailable verification: none. Every command above executed for real,
  including the development-database confirmation.
- Deviations and ADR impact: the first full test run failed (2 of 81) for the
  `remote_preference` default reason above; fixed and re-verified before reporting
  success. No ADR impact — Phase 1 implementation-slice detail only.
- Known limitations: none new. `updated_at` still only advances for ORM-driven writes
  (unchanged, out of scope for this pass, same as prior tables).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `saved_searches`.

### Work review

- Date and reviewing agent: 2026-08-24, Codex.
- Diff/revision reviewed: commit `9d35f75` (`feat(phase-1): implement candidate skills
  slice`) against approved base `7817073` on branch `phase-1/candidate-skills`. The
  branch matched `origin/phase-1/candidate-skills`, and the working tree was clean
  before review.
- Verification independently performed:
  - Inspected the complete `7817073..9d35f75` diff and resulting model, migration,
    model registration, shared real-commit helpers, candidate-profile refactor, all 20
    candidate-skill tests, data-model/roadmap changes, and handoff rotation.
  - Confirmed the ORM validator and both database `CHECK`s use the identical explicit
    space/tab/LF/CR set, preserve case, reject non-normalized or empty values, and leave
    internal whitespace unchanged.
  - Confirmed profile-scoped case-insensitive uniqueness is represented consistently in
    model metadata and migration `0005` as a functional unique index on
    `(candidate_profile_id, lower(skill))`.
  - Confirmed `category` is nullable unconstrained text; `priority` is non-null and
    `CHECK`-restricted to `must_have`/`preferred`; timestamps follow the established
    server-default/ORM-on-update convention.
  - Confirmed the extracted `real_committed_user_and_profile` helper retains its prior
    failure-safe lifecycle, and the skill wrapper cleans any surviving skill before the
    wrapped profile/user cleanup. Existing candidate-profile call sites use the shared
    helper without behavioral changes.
  - `ruff format --check .`: 24 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 18 source files.
  - `pytest -v`: 81 passed, 0 skipped.
  - Independently ran `0005 -> 0004 -> 0005` against `jobgoblin_test`: passed.
  - Independently ran `base -> 0001 -> 0002 -> 0003 -> 0004 -> 0005` against
    `jobgoblin_test`: passed.
  - `alembic check` after both incremental and fresh migration verification: no new
    upgrade operations detected.
  - Live PostgreSQL verification after migration testing: `jobgoblin_test` remained at
    `0005` with zero users, profiles, and skills; the development database remained at
    `0003` with zero users.
- Findings, ordered by severity, with file and line references: none.
- Missing or inconclusive verification: none material for this bounded slice.
- Architecture/documentation consistency: the implemented column types, nullability,
  FK cascade, normalization rules, functional uniqueness, priority invariant,
  timestamps, migration chain, metadata, tests, `DATA_MODEL.md`, and `ROADMAP.md` are
  mutually consistent and match the seven explicitly approved decisions.
- Verdict: approved.
- Exact requested corrections: none. The `candidate_skills` slice is accepted. Do not
  begin `saved_searches`, modify or merge `main`, or advance to any other slice until
  the user explicitly approves the next action.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

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
  Codex's approval commit for the `candidate_skills` slice (Iteration 1's `Work
  review`, verdict: approved), fast-forward-merged into `main` by the user outside
  this session (confirmed via `git reflog show main`: "merge phase-1/candidate-skills:
  Fast-forward") before this pass began. Confirmed `main`/`origin/main` both at
  `906cf24` before making any changes. Branch `phase-1/saved-searches` created
  directly from `906cf24`.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
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
     `NUMERIC(6, 2)`.
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

Status: awaiting review.
