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
the previous Iteration 1 (the first `candidate_profiles` implementation pass and Codex's
"changes requested" review of it, already superseded by this iteration's fixes) was
removed rather than kept alongside two already-reviewed entries. Nothing below was
rewritten — only renumbered.*

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: bounded correction pass over the `candidate_profiles` slice only
  — all five corrections in the previous iteration's `Work review` approved as one pass.
  No `candidate_skills`, no new table.
- Outcome: all five corrections addressed and verified against real PostgreSQL. 61 tests
  passed, 0 skipped (up from 52 — 9 net new tests).
- Base/starting commit: `b02158f` (`feat(phase-1): implement candidate profiles slice`)
  on branch `phase-1/candidate-profiles`, with Codex's review commit `b35869e`
  (`docs(review): request candidate profile mutation fixes`) on top. Confirmed via
  `git log --oneline` and `git status` (clean, branch up to date with origin) before
  making any changes.
- Ending commit or working-tree state: `2024d1d` (`fix(phase-1): track array mutations
  and harden candidate profile tests` — this is the commit Codex's `Work review` below
  actually reviewed and approved).
- Files changed:
  - `backend/app/db/models/candidate_profile.py` — the five `text[]` columns
    (`target_role_families`, `certifications`, `preferred_industries`,
    `excluded_industries`, `preferred_locations`) now use
    `MutableList.as_mutable(ARRAY(Text))` instead of plain `ARRAY(Text)`, so an in-place
    `.append()`/`.remove()` on a loaded list marks the profile dirty and is actually
    written on commit — previously silently dropped, per finding 1. No migration
    needed: this changes only SQLAlchemy's in-Python change-tracking, not PostgreSQL
    DDL, and `alembic check` (below) confirms no new upgrade operations were detected.
    Added a short comment explaining why the wrapper is required.
  - `backend/tests/test_candidate_profiles.py`:
    - Added `_real_committed_user_and_profile`, a shared async context manager wrapping
      the entire committed lifecycle (user insert, profile insert, and whatever the
      test body does) in a `try`/`finally`. The `finally` always rolls back the
      session (`contextlib.suppress(Exception)`, since the session may already be in a
      failed-transaction state) and then performs best-effort cleanup in a **fresh**
      session — fetching the profile and user by their captured ids and deleting each
      only if still present — so a test-body exception or an already-cascaded row
      can't leave a durable row behind or raise a second error while cleaning up.
      Addresses finding 2.
    - `test_deleting_user_cascades_to_candidate_profile` and
      `test_updating_a_profile_advances_updated_at` rewritten to use this helper
      instead of ad hoc `db_engine`/manual cleanup, closing the pre-`try` leak window
      the review identified in the latter.
    - Added `test_appending_to_array_field_persists_after_reload`, parameterized across
      all five array fields (`ARRAY_FIELDS`): builds a profile with the field set to
      `["first"]` via the new helper, appends `"second"` to the *loaded* list in place,
      commits, and reloads the row in a genuinely separate `AsyncSession` (not
      `.refresh()` on the same object) to prove the value was actually written to
      PostgreSQL, not merely echoed back from the original session's identity map.
      Addresses finding 1's requested test.
    - `test_non_negative_check_accepts_zero_and_positive` reparameterized over both
      `(field, 0)` and `(field, 5)` for all three non-negative columns (6 cases instead
      of 3-cases-at-zero-only), and now also refreshes and asserts the persisted value
      instead of only asserting `commit()` didn't raise. Addresses finding 3.
    - Added `test_salary_max_without_min_is_not_constrained_by_ordering_check`,
      mirroring the existing minimum-only case. Addresses finding 3.
  - `docs/DATA_MODEL.md` — the consolidated `users` row in "Phase 1 constraints &
    indexes" now states the current migration-`0003` explicit space/tab/LF/CR `CHECK`
    expressions instead of the stale migration-`0002` bare-`trim` ones; the `users`
    table's own section (which explains the `0002`/`0003` history) was left unchanged.
    Addresses finding 4.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the approved third `users`
    correction pass — removed; prior Iteration 2 renumbered to Iteration 1; this entry
    appended as the new Iteration 2).
- Migration revisions: none added or changed. `0004` is unchanged; only ORM-level
  mutation tracking and test/documentation content were corrected this pass, exactly as
  the review anticipated ("No migration should be needed").
- Commands run and exact results:
  - `ruff format .` → 1 file reformatted (`candidate_profile.py`, from wrapping the
    array columns), then a second reformat after adding `contextlib.suppress` → 21
    files left unchanged (stable).
  - `ruff check .` → one `SIM105` finding (`try`/`except`/`pass` in the new cleanup
    helper) → replaced with `contextlib.suppress(Exception)` → all checks passed.
  - `mypy app tests` → success, 16 source files.
  - `pytest -v` (first run after the new mutation tests) → **5 failed, 56 passed**: the
    five new `test_appending_to_array_field_persists_after_reload` cases asserted
    `reloaded is not None` *after* the helper's `async with` block had already exited —
    the helper's cleanup deletes the profile/user as soon as the block exits, so the
    row was legitimately gone by the time the reload ran. Fixed by moving the
    reload-and-assert *inside* the `async with` block, before cleanup runs (a test
    ordering bug in this pass's own new test, not a defect in the reviewed model fix or
    the cleanup helper itself).
  - `pytest -v` (after the fix) → **61 passed, 0 skipped**.
  - `DATABASE_URL=...jobgoblin_test alembic current` (before any change) → `0004
    (head)`.
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0003` → success.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0003 -> 0004`
    (round-trip scenario, confirming the model change needed no migration).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.`
  - `alembic current` against the **development** database (default `DATABASE_URL`, no
    override) → `0003`, unchanged — confirmed untouched.
  - `pytest -q` (final re-run after the migration round-trip) → **61 passed**.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "PostgreSQL behavior is tested against
  PostgreSQL" — the `MutableList` fix and the new persistence test only prove anything
  because the reload happens in a genuinely separate session hitting real Postgres, not
  the same session's identity map; "every migration is reviewed and tested upgrade ->
  downgrade -> upgrade" — re-verified for `0004` after this pass's ORM-only change, to
  confirm nothing in the fix touched migration behavior.
- Skipped or unavailable verification: none. All commands executed for real, including
  the development-database confirmation.
- Deviations and ADR impact: the first run of the five new mutation tests failed (test
  ordering bug in the new test itself, detailed above); fixed and re-verified before
  reporting success. No ADR impact — Phase 1 implementation-slice detail only.
- Known limitations: none new. `updated_at` still only advances for ORM-driven writes
  (unchanged, out of scope for this pass, same as prior passes).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `candidate_skills`.

### Work review

- Date and reviewing agent: 2026-08-24, Codex.
- Diff/revision reviewed: commit `2024d1d` (`fix(phase-1): track array mutations and
  harden candidate profile tests`) against review commit `b35869e` on branch
  `phase-1/candidate-profiles`. The local branch matched
  `origin/phase-1/candidate-profiles`, and the working tree was clean before review.
- Verification independently performed:
  - Inspected the complete `b35869e..2024d1d` diff and the resulting candidate-profile
    model, test helper, affected tests, data-model correction, and handoff rotation.
  - Confirmed all five nullable `text[]` attributes use
    `MutableList.as_mutable(ARRAY(Text))`, and that the regression test mutates each
    loaded list in place, commits, and verifies persistence through a separate
    `AsyncSession` before cleanup.
  - Confirmed both tests that require real commits now place creation, test behavior,
    and cleanup inside `_real_committed_user_and_profile`; its `finally` rolls back and
    closes the working session and removes any surviving profile/user through a fresh
    session, closing the prior pre-cleanup leak windows.
  - Confirmed the non-negative acceptance matrix exercises zero and a positive value
    for all three numeric columns, and the salary-ordering tests cover minimum-only and
    maximum-only rows.
  - `ruff format --check .`: 21 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 16 source files.
  - `pytest -v`: 61 passed, 0 skipped.
  - Independently ran `0004 -> 0003 -> 0004` against `jobgoblin_test`: passed.
  - `alembic check` at test-database head: no new upgrade operations detected.
  - Live PostgreSQL verification after the suite and migration round-trip:
    `jobgoblin_test` contained zero `users` and zero `candidate_profiles`; the
    development database remained at revision `0003` with zero `users`.
- Findings, ordered by severity, with file and line references: none.
- Missing or inconclusive verification: none material for this bounded correction pass.
- Architecture/documentation consistency: the ORM-only mutation-tracking change
  correctly produces no migration; nullable-array semantics and all approved numeric
  invariants remain unchanged; the consolidated `users` constraint row now matches
  migration `0003`; implementation, migration metadata, tests, and documentation are
  consistent.
- Verdict: approved.
- Exact requested corrections: none. The `candidate_profiles` slice and this correction
  pass are accepted. Do not begin `candidate_skills` or merge to `main` until the user
  explicitly approves the next action.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

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
  the `candidate_profiles` slice (Iteration 1's `Work review`, verdict: approved).
  Confirmed via `git status` (clean, up to date with origin) and `git log --oneline`
  before making any changes. Branch `phase-1/candidate-skills` created directly from
  `7817073`, per the user's explicit instruction — `main` was not touched.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
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

Status: awaiting review.
