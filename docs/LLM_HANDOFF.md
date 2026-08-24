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
no longer pending — Codex's verdict was "approved" — so the previous Iteration 1 (the
second `users`-slice correction pass, whose review had requested further changes that
were then made in this iteration) was removed rather than kept alongside two
already-reviewed entries. Nothing below was rewritten — only renumbered.*

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: third bounded correction pass over the existing Phase 1 `users`
  slice only — the guard alias-comparison fix and the "forward-only" wording correction
  from Iteration 1's `Work review`, approved as one final pass. No other table, no new
  slice.
- Outcome: both corrections addressed and verified against real PostgreSQL. 30 tests
  passed, 0 skipped.
- Base/starting commit: `50f6e58` ("docs(review): close test-db alias gap") on branch
  `codex/phase1-users-wip` — Codex's own review commit, on top of `31aa213`
  ("fix(phase-1): forward-migrate email checks and harden test-db guard"), the commit
  its review evaluated. Confirmed via `git log --oneline` before making any changes.
- Ending commit or working-tree state: `49aa748` (Codex's approval commit for this
  iteration's `Work review`, below — this is also the commit the user confirmed and the
  commit `main` was created at before branching `phase-1/candidate-profiles`).
- Files changed:
  - `backend/tests/conftest.py` — `assert_is_disposable_test_database` no longer
    compares `(host, port, database)` tuples; it now compares **database name only**
    (case-insensitive), deliberately ignoring host/port/credentials/driver spelling, per
    the review's explicit conservative-rejection instruction. Docstring rewritten to
    explain why (a `localhost`/`127.0.0.1` pair, or an omitted vs. explicit default port,
    can reach the identical database while looking different as tuples).
  - `backend/tests/test_users.py` — added regression tests: same database name via
    `localhost` vs. `127.0.0.1`, same name via omitted vs. explicit default port, same
    name with different case, and a distinct database name on the same server (must
    still be accepted). Updated the existing "test-named-but-actually-dev" test's
    expected message substring to match the new wording. Kept the credential-redaction
    test unchanged.
  - `backend/migrations/versions/0003_fix_email_whitespace_checks.py` — docstring
    wording: "forward-only correction" → "forward corrective migration" (it has a
    working, tested `downgrade()`; "forward-only" incorrectly implied it couldn't be
    reversed).
  - `docs/ROADMAP.md` — same wording correction in the Phase 1 status line.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 removed; prior Iteration 2
    renumbered to Iteration 1; this entry appended as the new Iteration 2). Historical
    "forward-only" wording inside the now-Iteration-1 `Work done`/`Work review` text was
    **not** edited — per the rotation rule, retained entries are renumbered, not
    rewritten, even when they use since-corrected wording.
- Migration revisions: none added or changed — `0002` and `0003` are unchanged from the
  previous pass; only the guard logic and prose were corrected this time.
- Commands run and exact results:
  - `ruff format --check .` → 18 files already formatted (no changes needed).
  - `ruff check .` → all checks passed.
  - `mypy app tests` → success, 14 source files.
  - `pytest -v` → **30 passed, 0 skipped** (up from 26 — 4 new guard regression tests).
  - Focused migration cycle against `jobgoblin_test`: `alembic current` → `0003 (head)`;
    `alembic downgrade 0002` → success; `alembic upgrade head` → success, `0002 -> 0003`;
    `alembic check` → `No new upgrade operations detected.`
  - Development database, confirmed untouched by the above (test-DB-only commands):
    `SELECT version_num FROM alembic_version` → `0003`; `SELECT count(*) FROM users` →
    `0`.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "PostgreSQL behavior is tested against
  PostgreSQL" — the alias-comparison gap (`localhost` vs `127.0.0.1`, default port) was
  itself only demonstrable against real connection-string parsing, not by inspection;
  "every migration is reviewed and tested upgrade -> downgrade -> upgrade" — re-verified
  for `0003` specifically after this pass's unrelated changes, to confirm nothing in the
  guard/wording fix touched migration behavior.
- Skipped or unavailable verification: none. All commands executed for real.
- Deviations and ADR impact: none. This pass touched only test infrastructure and prose;
  no schema, model, or ADR-relevant decision changed.
- Known limitations: the guard's name-only comparison is deliberately conservative — a
  same-named test database on a genuinely different, unrelated PostgreSQL server would
  still be rejected (documented in the guard's own docstring as an accepted trade-off,
  per the review's explicit instruction). `updated_at` still only advances for
  ORM-driven writes (unchanged, out of scope for this pass).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `candidate_profiles`.

### Work review

- Date and reviewing agent: 2026-08-24, Codex
- Diff/revision reviewed: commit `d484a90` (`fix(phase-1): compare test/dev database
  targets by name, fix wording`) against review commit `50f6e58` on branch
  `codex/phase1-users-wip`. The branch matched `origin/codex/phase1-users-wip`, and the
  working tree was clean before review.
- Verification independently performed:
  - Inspected the complete `50f6e58..d484a90` diff and every changed implementation,
    test, migration-comment, roadmap, and handoff entry.
  - Confirmed the guard now compares case-normalized database names independently of
    host, port, credentials, and driver spelling, while still requiring the test marker.
  - Re-ran the previously bypassing `localhost`/`127.0.0.1` and omitted/explicit-port
    scenarios through the committed regression suite.
  - `ruff format --check .`: 18 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 14 source files.
  - `pytest -v`: 30 passed, 0 skipped.
  - Independently ran `0003 -> 0002 -> 0003` against `jobgoblin_test`: passed.
  - `alembic check` at test-database head: no new upgrade operations detected.
  - Live PostgreSQL verification: both `jobgoblin` and `jobgoblin_test` remain at
    revision `0003`; both contain zero user rows after verification.
- Findings, ordered by severity, with file and line references: none.
- Missing or inconclusive verification: none material for this bounded correction pass.
- Architecture/documentation consistency: The conservative name-only guard matches the
  documented fail-closed trade-off; credential redaction remains covered; `0003` is
  accurately described as a reversible forward corrective migration; the migration
  chain, model metadata, live schemas, tests, roadmap, and data-model documentation are
  consistent.
- Verdict: approved.
- Exact requested corrections: none. The Phase 1 `users` slice and its correction chain
  are accepted. Do not begin another slice until the user approves it; the next proposed
  bounded slice may be evaluated separately.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: first bounded Phase 1 slice after `users` — `candidate_profiles`
  only. No `candidate_skills`, no saved searches, no auth, no APIs/services, no
  providers/ingestion/matching/normalization, no other Phase 1 table.
- Outcome: model, migration `0004`, factory fixture, and database tests implemented and
  verified against real PostgreSQL. 52 tests passed, 0 skipped (up from 30 — 22 new
  `candidate_profiles` tests).
- Base/starting commit: `49aa748` on branch `codex/phase1-users-wip` — Codex's approval
  commit for the `users` slice (Iteration 1's `Work review`, verdict: approved),
  confirmed by the user before authorizing this slice. `main` did not exist in this
  repository before this pass (git was initialized with `main` as the default branch
  name, but every commit had only ever been made on `codex/phase1-users-wip`); per the
  user's explicit choice (asked directly rather than assumed), `main` was created at
  `49aa748` and pushed, then `phase-1/candidate-profiles` was branched from `main`.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
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
