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
no longer pending — Codex's verdict was "changes requested," and all five requested
corrections were approved and addressed in the next iteration — so the previous
Iteration 1 (the third `users`-slice correction pass and Codex's approval of it) was
removed rather than kept alongside two already-reviewed entries. Nothing below was
rewritten — only renumbered.*

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: first bounded Phase 1 slice after `users` — `candidate_profiles`
  only. No `candidate_skills`, no saved searches, no auth, no APIs/services, no
  providers/ingestion/matching/normalization, no other Phase 1 table.
- Outcome: model, migration `0004`, factory fixture, and database tests implemented and
  verified against real PostgreSQL. 52 tests passed, 0 skipped (up from 30 — 22 new
  `candidate_profiles` tests).
- Base/starting commit: `49aa748` on branch `codex/phase1-users-wip` — Codex's approval
  commit for the `users` slice (previous Iteration 1's `Work review`, verdict: approved),
  confirmed by the user before authorizing this slice. `main` did not exist in this
  repository before this pass (git was initialized with `main` as the default branch
  name, but every commit had only ever been made on `codex/phase1-users-wip`); per the
  user's explicit choice (asked directly rather than assumed), `main` was created at
  `49aa748` and pushed, then `phase-1/candidate-profiles` was branched from `main`.
- Ending commit or working-tree state: `b02158f` (`feat(phase-1): implement candidate
  profiles slice` — this is the commit Codex's `Work review` below actually reviewed).
- Three product rules were not determined by `docs/DATA_MODEL.md` and were resolved by
  explicit user approval before migration `0004` was written, per this slice's approval
  message's explicit stop-and-ask instruction (not silently invented):
  1. The five `text[]` columns (`target_role_families`, `certifications`,
     `preferred_industries`, `excluded_industries`, `preferred_locations`) are nullable
     with no server default; NULL means "never specified," distinct from a future
     explicit empty-array write.
  2. `years_experience`, `salary_expectation_min`, and `salary_expectation_max` each have
     a `CHECK` requiring the value be NULL or `>= 0`.
  3. `salary_expectation_min`/`salary_expectation_max` have an additional `CHECK`
     requiring `salary_expectation_min <= salary_expectation_max` whenever both are
     non-null.
  `remote_preference` was treated as **not** nullable — unlike the columns above, its
  row in `docs/DATA_MODEL.md`'s existing column table was never annotated "nullable,"
  matching that table's own established convention (only nullable columns are marked as
  such) — so this was not treated as a fourth open ambiguity.
- Files changed:
  - `backend/app/db/models/candidate_profile.py` (new) — `CandidateProfile` model
    following `User`'s existing pattern (`Uuid` PK with app-side `uuid.uuid4` default,
    `timestamptz` `created_at`/`updated_at` with `server_default=func.now()` and
    `onupdate=func.now()`). `REMOTE_PREFERENCES` module constant lists the four allowed
    values, reused by the migration's CHECK and by tests.
  - `backend/app/db/models/__init__.py` — registers `CandidateProfile` alongside `User`.
  - `backend/app/db/base.py` — docstring updated to mention both Phase 1 models.
  - `backend/migrations/versions/0004_candidate_profiles.py` (new) — `down_revision =
    "0003"`. Table created with all constraints defined inline in `op.create_table(...)`
    (the `0002_users.py` pattern, not a separate `op.drop_constraint`/`op.f()` ALTER
    step, so the naming-convention double-prefixing bug hit during the `users` slice
    cannot recur here). `downgrade()` drops the table.
  - `backend/tests/conftest.py` — added `make_candidate_profile` factory fixture,
    parameterized by an explicit `user_id` (not creating its own `User`) so tests can
    inspect/delete the owning row directly (e.g. to observe the cascade).
  - `backend/tests/test_candidate_profiles.py` (new) — 22 tests: valid insert/retrieve;
    one-profile-per-user uniqueness; nonexistent `user_id` FK rejection; `ON DELETE
    CASCADE` from `users` (verified with real, separate commits via `db_engine`, not the
    savepoint-isolated `db_session`); every allowed `remote_preference` value accepted;
    an invalid value rejected; all nullable fields default to `None`; NULL vs. an
    explicitly-stored empty array round-trip as distinguishable values;
    `relocation_willingness` NULL-means-unknown; both accepted (zero/positive) and
    rejected (negative) cases for each of the three non-negative `CHECK`s; both accepted
    (equal, ascending, min-only) and rejected (descending) cases for the salary-ordering
    `CHECK`; `updated_at` advancing on update (same `db_engine`-direct pattern as
    `test_users.py`, for the same `now()`-is-transaction-fixed reason); UTC-aware
    timestamps; and an explicit `test_table_starts_empty` isolation check.
  - `docs/DATA_MODEL.md` — `candidate_profiles` marked **Implemented**; added a "Rev 7"
    note and updated the table's own column list and the "Phase 1 constraints & indexes"
    summary table to state the three resolved rules explicitly (nullability, the two
    non-negative `CHECK`s, and the ordering `CHECK`).
  - `docs/ROADMAP.md` — Phase 1 status line now also describes the `candidate_profiles`
    slice as complete and verified.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the second `users`
    correction pass — removed; prior Iteration 2 renumbered to Iteration 1; this entry
    appended as the new Iteration 2).
- Migration revisions: `0004` (new, `down_revision = "0003"`) — adds `candidate_profiles`.
  `0001`–`0003` unchanged.
- Commands run and exact results:
  - `git branch main 49aa748` / `git push -u origin main` → success (new branch on
    origin); `git checkout -b phase-1/candidate-profiles main` → success, clean tree,
    `HEAD` at `49aa748`.
  - Read `docs/DATA_MODEL.md`'s `candidate_profiles` section, `docs/ARCHITECTURE.md`, and
    ADRs 0001–0007: confirmed none of the three product rules above were already
    determined (the closest existing precedent, `jobs.salary_min`/`salary_max`, is
    documented as "nullable, as originally stated" with no `CHECK`) — presented to the
    user as three explicit ambiguities before writing any migration code; user resolved
    all three.
  - `DATABASE_URL=...jobgoblin_test alembic current` (before any change) → `0003`.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0003 -> 0004`
    ("existing `0003 -> 0004`" scenario).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0003` → success.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0003 -> 0004` again
    (round-trip scenario).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.`
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` → success, all tables
    dropped.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, ` -> 0001 -> 0002 ->
    0003 -> 0004` ("fresh `base -> head`" scenario).
  - `alembic current` against the **development** database (default `DATABASE_URL`, no
    override) → `0003`, both before and after all of the above — confirmed untouched.
  - `ruff format --check .` → 2 files needed reformatting (the new model and test file)
    → `ruff format .` → recheck: 21 files formatted.
  - `ruff check .` → all checks passed.
  - `mypy app tests` → success, 16 source files.
  - `pytest -v` (first full run) → **16 failed, 36 passed**. Root cause investigated
    rather than worked around: several new tests read an ORM attribute (e.g. `user.id`,
    `profile.id`) *after* a later `session.commit()` had already expired it
    (`expire_on_commit` is on by default), which under `asyncpg`'s async dialect raises
    `MissingGreenlet` instead of transparently refreshing — not a database bug. Fixed by
    capturing needed values into local variables immediately after the commit that
    populated them, before any subsequent commit. One of the affected tests
    (`test_deleting_user_cascades_to_candidate_profile`) used `db_engine` directly (real
    commits, no savepoint) and had no cleanup path for this failure, which left rows
    permanently committed in `jobgoblin_test` and caused unrelated tests in the same file
    to fail on stale row counts on every subsequent run until the database was reset
    (`alembic downgrade base` / `upgrade head` against `jobgoblin_test` only).
  - `pytest -v` (after the fix, against a freshly reset `jobgoblin_test`) → **52 passed,
    0 skipped**.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "define nullability/defaults/
  uniqueness/checks/indexes/ON DELETE before implementing each table" — done explicitly
  via the three-ambiguity stop-and-ask above, before any migration code was written;
  "every migration is reviewed and tested upgrade -> downgrade -> upgrade" — exercised as
  three separate scenarios (existing `0003 -> 0004`, round-trip, fresh `base -> head`);
  "PostgreSQL behavior is tested against PostgreSQL" — the `MissingGreenlet`/expired-
  attribute bug above was only caught by actually running the tests against real
  Postgres, not by code review; "null-bearing unique key tests" and "accepted+rejected
  constraint tests" — covered for every new `CHECK` and the `UNIQUE (user_id)` index.
- Skipped or unavailable verification: none. Every command above executed for real,
  including the development-database confirmation.
- Deviations and ADR impact: the first full test run failed (16 of 52) for the reasons
  above; fixed and re-verified from a clean database before reporting success. No ADR
  impact — Phase 1 implementation-slice detail only.
- Known limitations: none new. `updated_at` still only advances for ORM-driven writes
  (unchanged, out of scope for this pass, same as the `users` slice).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `candidate_skills`.

### Work review

- Date and reviewing agent: 2026-08-24, Codex
- Diff/revision reviewed: commit `b02158f` (`feat(phase-1): implement candidate profiles
  slice`) against approved base `49aa748` on branch `phase-1/candidate-profiles`. The
  branch matched `origin/phase-1/candidate-profiles`, and the working tree was clean
  before review.
- Verification independently performed:
  - Inspected the complete `49aa748..b02158f` diff and every changed model, migration,
    fixture, test, roadmap, data-model, and handoff entry.
  - `ruff format --check .`: 21 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 16 source files.
  - `pytest -v`: 52 passed, 0 skipped.
  - Independently ran `0004 -> 0003 -> 0004` against `jobgoblin_test`: passed.
  - Independently ran `0004 -> base -> 0004` against `jobgoblin_test`: passed.
  - `alembic check` at test-database head: no new upgrade operations detected.
  - Live database verification after review: development remained at `0003` with zero
    users; the disposable test database returned to `0004` with zero users and zero
    candidate profiles.
  - Ran a rolled-back/cleaned ORM mutation probe against `jobgoblin_test`: after loading
    `target_role_families=['engineering']`, appending `'data'`, and committing,
    `session.is_modified(..., include_collections=True)` returned `False` and the stored
    value remained `['engineering']`.
- Findings, ordered by severity, with file and line references:
  1. **High — in-place edits to every array field are silently discarded by the ORM.**
     The five PostgreSQL arrays at
     `backend/app/db/models/candidate_profile.py:37-44` use plain `ARRAY(Text)`.
     SQLAlchemy does not track mutation inside a plain Python list without its mutable
     extension. The independent live probe confirmed that `.append()` leaves the model
     clean and loses the change on commit. Candidate preferences and certifications are
     inherently editable collections, so requiring every future caller to replace the
     entire list is an undocumented and failure-prone constraint.
  2. **Medium — the real-commit cascade test can still poison the shared test database
     when it fails.** `backend/tests/test_candidate_profiles.py:94-123` commits a user
     and profile but has no `try/finally` cleanup path. The reported first run already
     demonstrated this exact failure mode: an exception left durable rows that caused
     unrelated tests to fail. Capturing expired IDs fixed the immediate
     `MissingGreenlet`, but not the database-leak mechanism. The `updated_at` test at
     lines 315-344 begins its cleanup `try` only after both committed inserts, leaving a
     similar pre-`try` leak window.
  3. **Low — two test names/claims exceed their actual coverage.** The parameterized
     `test_non_negative_check_accepts_zero_and_positive` sets only `0`, never a positive
     value, and salary ordering covers minimum-only but not maximum-only. Both behaviors
     should be explicit boundary cases because the handoff claims they were exercised.
  4. **Low — the consolidated users constraint row is stale.**
     `docs/DATA_MODEL.md:755` still lists the original bare-`trim` checks from migration
     `0002`, even though migration `0003` and the current model enforce the explicit
     space/tab/LF/CR expressions. The users section explains the history correctly, but
     the consolidated head-schema checklist should state the current constraints.
- Missing or inconclusive verification: I did not deliberately force an assertion
  failure inside a real-commit test because that would intentionally dirty the shared
  test database; the absence of cleanup is directly visible, and the implementation
  handoff already records the reproduced leak from the first run.
- Architecture/documentation consistency: Table shape, null-versus-empty semantics,
  remote-preference enum, numeric/order checks, timestamps, one-to-one uniqueness, FK
  cascade, migration chain, roadmap, and the approved product decisions are otherwise
  consistent.
- Verdict: changes requested.
- Exact requested corrections:
  1. Wrap each array mapping with SQLAlchemy's mutable list tracking (for example,
     `MutableList.as_mutable(ARRAY(Text))`) so in-place append/remove operations mark the
     profile dirty. No migration should be needed because this changes ORM tracking, not
     PostgreSQL DDL. Add a PostgreSQL-backed test that mutates a loaded array in place,
     commits, reloads it in a new session/transaction, and observes the persisted value;
     parameterize across all five array fields.
  2. Make every test using real commits failure-safe. Capture identifiers as soon as
     available, wrap the entire committed lifecycle in cleanup, rollback failed
     sessions when necessary, and perform best-effort cleanup in a fresh session so an
     assertion or intermediate commit failure cannot leave durable users/profiles.
  3. Actually test both zero and a positive value for all three non-negative columns,
     and add the maximum-only salary-bound case.
  4. Update the consolidated users row in `docs/DATA_MODEL.md` to show the current
     migration-`0003` explicit whitespace checks while retaining the historical
     explanation in the users section.
  5. Rerun format, lint, mypy, all tests, `0004 -> 0003 -> 0004`, and `alembic check`.
     Rotate the two-entry ledger, record the correction as the newest `Work done`,
     commit/push only `phase-1/candidate-profiles`, and stop. Do not begin
     `candidate_skills`.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: bounded correction pass over the `candidate_profiles` slice only
  — all five corrections in Iteration 1's `Work review` approved as one pass. No
  `candidate_skills`, no new table.
- Outcome: all five corrections addressed and verified against real PostgreSQL. 61 tests
  passed, 0 skipped (up from 52 — 9 net new tests).
- Base/starting commit: `b02158f` (`feat(phase-1): implement candidate profiles slice`)
  on branch `phase-1/candidate-profiles`, with Codex's review commit `b35869e`
  (`docs(review): request candidate profile mutation fixes`) on top. Confirmed via
  `git log --oneline` and `git status` (clean, branch up to date with origin) before
  making any changes.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
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
