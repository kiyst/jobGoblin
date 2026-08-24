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

### Work done

*Backfilled retroactively during the Iteration 2 correction pass, from the
implementation handoff report Claude Code gave the user at the time — this work predates
adoption of this ledger, so it was never recorded here as it happened. Content below
describes the state Codex's `Work review` (right) actually reviewed; it does not include
any of Iteration 2's corrections.*

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: Phase 1, `users` table only (model, migration, database tests) —
  no other Phase 1 table, no providers/ingestion, no auth.
- Outcome: `users` model, migration `0002`, and database tests implemented and passing
  against real PostgreSQL (Docker Compose).
- Base/starting commit: none — the repository had no commits at all at the time; every
  file was untracked.
- Ending commit or working-tree state: uncommitted working tree (no ledger/Git workflow
  existed yet). This state was later snapshotted, once this ledger was adopted, as
  commit `3816d0a` ("checkpoint: Phase 0 and Phase 1 users slice") on branch
  `codex/phase1-users-wip` — that commit is the exact state this row describes and that
  Codex's `Work review` (right) evaluated.
- Files changed (all new, Phase 0 + this slice together, since nothing had been
  committed before): `backend/app/db/models/user.py`,
  `backend/app/db/models/__init__.py`, `backend/migrations/versions/0002_users.py`,
  `backend/migrations/env.py` (updated to import `app.db.models`),
  `backend/tests/conftest.py` (added `db_engine`/`db_session`/`make_user` fixtures),
  `backend/tests/test_users.py` (new), `docs/DATA_MODEL.md` (`users` table entry),
  `docs/ROADMAP.md` (status line).
- Migration revisions: `0002` (`down_revision = "0001"`) — creates `users`.
- Commands run and exact results (against the `jobgoblin` development database, which at
  the time was the only database available — see Codex's finding 2 on the right):
  `alembic revision --autogenerate` (reviewed, then hand-renamed to `0002_users.py`);
  `alembic upgrade head` (created `users`, confirmed via `psql \d users`);
  `alembic downgrade 0001` then `alembic upgrade head` (round-trip passed, table
  dropped/recreated); a second `alembic revision --autogenerate` produced an empty
  migration (model/migration parity), then was deleted; `pytest -v` — 15 passed, 0
  skipped; `ruff format --check .` — 17 files formatted; `ruff check .` — passed; `mypy
  app tests` — passed, 14 source files; `SELECT count(*) FROM users` on the development
  database after the suite — `0` (no leaked rows).
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: timezone-aware UTC timestamps tested;
  Alembic autogenerate output manually reviewed and hand-edited, not accepted as-is;
  every constraint tested both accepted and rejected; `IntegrityError` recovery via
  explicit `session.rollback()` before continuing, verified the session stays usable
  afterward; a valid-state-by-default factory fixture (`make_user`); model/migration
  parity confirmed explicitly (empty-diff autogenerate). Not applicable to this table:
  null-bearing unique keys (no nullable column participates in a unique constraint here).
- Skipped or unavailable verification: none reported as passing that didn't actually
  run; `test_ready_succeeds_when_database_available` ran for real (not skipped) since
  Docker/PostgreSQL was available in that session.
- Deviations and ADR impact: none — this slice didn't touch any ADR.
- Known limitations (as reported at the time; see Codex's `Work review` for what these
  missed): `updated_at` only advances for ORM-driven writes (`onupdate`), no DB trigger;
  no RFC email validation (by design, per instructions).
- Recommended next smallest slice (as given at the time): `candidate_profiles` alone.
  Superseded by Codex's review — the approved next step is this correction pass, not a
  new table.
- STOP — awaiting review and user approval. *(Historical note: Codex's review at right
  is that review; this backfill does not re-trigger a new review cycle by itself.)*

### Work review

- Date and reviewing agent: 2026-08-24, Codex
- Diff/revision reviewed: Phase 1 `users` slice as described in the user's pasted Claude
  handoff. The repository has no commits and every file is currently untracked, so no
  reliable base-to-ending Git diff exists. This review inspected the present files
  directly.
- Verification independently performed:
  - Docker Compose reports the backend running and PostgreSQL 16 healthy.
  - `ruff format --check .`: 17 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 14 source files.
  - `pytest -v`: 15 passed, 0 skipped.
  - Alembic current revision: `0002 (head)`.
  - Alembic `0002 -> 0001 -> 0002` downgrade/upgrade: passed.
  - `alembic check`: no new upgrade operations detected.
  - Live `\\d+ users`: columns, primary key, two checks, and functional unique index
    match migration `0002`.
  - Rolled-back live PostgreSQL probes confirmed no rows remained afterward.
- Findings, ordered by severity, with file and line references:
  1. **High — the database email-normalization backstop is bypassable.**
     `backend/app/db/models/user.py:39-40` and
     `backend/migrations/versions/0002_users.py:51-52` use PostgreSQL `trim(email)`,
     whose default trim character is an ordinary space, while the ORM uses Python
     `strip()` at `backend/app/db/models/user.py:52`. Direct SQL successfully inserted
     both `E'\\tperson@example.com\\t'` and a whitespace-only `E'\\t\\n'` value through
     the checks. The former can also coexist with `person@example.com` because the
     unique index retains the surrounding control whitespace. This contradicts the
     claimed invariant in `docs/DATA_MODEL.md:82-93` and the migration comments.
  2. **High — PostgreSQL tests target the ordinary development database.**
     `backend/tests/conftest.py:50-64` constructs its engine from the same cached
     `DATABASE_URL` whose default is the `jobgoblin` development database at
     `backend/app/config.py:28-34`. Tests currently assume the entire table starts empty
     (`backend/tests/test_users.py:13-16`), and one test makes real commits before
     cleanup (`backend/tests/test_users.py:122-149`). More importantly, the required
     migration downgrade/upgrade workflow drops real tables. This is safe only while
     the development database is disposable and empty; it needs a dedicated test
     database before additional state accumulates.
  3. **Medium — there is no Git baseline or handoff record for this slice.** All files
     are untracked and `main` has no commits. The pasted report can explain intent but
     cannot establish exactly what changed or provide a rollback point. The `Work done`
     section above also remains empty because this work appears to predate the ledger.
  4. **Low — status documentation is internally stale.** `README.md:7-8` and
     `backend/app/db/base.py:19-21` still say that no domain models exist. In addition,
     `docs/ROADMAP.md:91-96` says Phase 9 migrates
     `collection_run_provider_attempts`, while the Phase 1 roadmap and data model say it
     is migrated in Phase 1 and first written in Phase 2.
- Missing or inconclusive verification: Historical attribution is impossible without a
  commit or prior snapshot. I did not recreate Claude's deleted temporary autogenerate
  file; `alembic check` independently established current model/migration parity.
- Architecture/documentation consistency: The `users` table shape and Phase 1 scope are
  otherwise consistent with the current data model, roadmap, and phase-risk checklist.
  The whitespace behavior and stale status statements above are the exceptions.
- Verdict: changes requested.
- Exact requested corrections:
  1. Define one explicit supported whitespace-normalization rule shared by Python and
     PostgreSQL. Update the model, migration `0002` (still uncommitted), and data-model
     text so the database expression matches the ORM. Add direct-SQL regression tests
     for tab/newline-only input, tab/newline-wrapped input, and collision with the same
     normalized email.
  2. Introduce a dedicated PostgreSQL test database/URL and make database tests fail
     closed if they are pointed at the normal development database. Run migrations and
     migration round trips only against that disposable test database.
  3. Update the stale README/Base statements and correct the Phase 9 roadmap sentence.
  4. Backfill this iteration's `Work done` entry from the implementation handoff without
     altering this review. Establish a Git baseline/commit only after the user approves
     what belongs in the initial snapshot.
  5. Rerun format, lint, mypy, all tests, Alembic check, and
     upgrade/downgrade/upgrade against the dedicated test database; record exact results
     as the next `Work done` iteration and stop. Do not begin `candidate_profiles` yet.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: correction pass over the existing Phase 1 `users` slice only,
  addressing all four findings in Iteration 1's `Work review` (user approved all four).
  No other table, no new slice.
- Outcome: all four approved findings addressed and verified against real PostgreSQL.
  Zero database tests skipped.
- Base/starting commit: `3816d0a` ("checkpoint: Phase 0 and Phase 1 users slice") on
  branch `codex/phase1-users-wip`, already pushed to `origin` before this pass began —
  this is the exact state Iteration 1's `Work review` evaluated. (A pre-fix checkpoint
  commit was requested at the start of this pass; one already existed matching that
  description exactly, verified via `git diff` showing zero working-tree changes against
  it apart from this ledger file — see Deviations below. No redundant checkpoint was
  created.)
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this file's
  own "Git workflow" instructions above).
- Files changed:
  - `backend/app/db/models/user.py` — explicit shared whitespace set
    (`_COVERED_WHITESPACE = " \t\n\r"`), CHECK constraints rewritten to
    `trim(both E'\t\n\r ' from email)` matching it exactly.
  - `backend/migrations/versions/0002_users.py` — same CHECK-constraint SQL corrected in
    place (migration was never applied anywhere but the disposable/dev databases in this
    repo, so fixed in place rather than adding `0003`).
  - `backend/tests/conftest.py` — added `TEST_DATABASE_URL`/
    `DEFAULT_TEST_DATABASE_URL`/`assert_is_disposable_test_database` (fail-closed guard);
    `db_engine` now targets the disposable test database, never `DATABASE_URL`.
  - `backend/tests/test_users.py` — added guard unit tests and the required direct-SQL
    regression tests (tab/newline-only, tab/newline-wrapped lowercase, tab/newline-wrapped
    mixed-case, whitespace-wrapped-vs-normalized collision, valid-normalized-accepted,
    empty-string); kept all previously-passing tests.
  - `docker-compose.yml` — mounts `./postgres-init` into the Postgres container's
    `docker-entrypoint-initdb.d`.
  - `postgres-init/01-create-test-db.sql` (new) — creates `jobgoblin_test` on fresh
    volumes.
  - `.env.example` — added `TEST_DATABASE_URL`.
  - `README.md` — corrected the stale "no domain models" line; added a "Dedicated test
    database" section (setup + exact commands); migration-cycle verification commands
    now target the test database, not the development database.
  - `backend/app/db/base.py` — docstring no longer says no domain models exist.
  - `docs/ROADMAP.md` — Phase 9 no longer says it migrates
    `collection_run_provider_attempts`; says it reuses the Phase-1-migrated,
    Phase-2-first-written table instead.
  - `docs/DATA_MODEL.md` — `users` section corrected to the real shared whitespace rule,
    with the bug explained; Rev 6 changelog note.
  - `docs/LLM_HANDOFF.md` — this pass's entries (Iteration 1 backfill + this Iteration 2).
- Migration revisions: `0002` unchanged as a revision id (`down_revision = "0001"`) — its
  DDL was corrected in place, not superseded by a new revision.
- Commands run and exact results:
  - One-time: `docker exec jobgoblin-postgres-1 psql -U jobgoblin -d jobgoblin -c "CREATE
    DATABASE jobgoblin_test OWNER jobgoblin;"` → `CREATE DATABASE`.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → created `users` on the test
    database (baseline + `0002` applied fresh).
  - `pytest -v` → **24 passed, 0 skipped** (4 health/ready + 20 users, up from 15/0).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0001` → `users` dropped.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → `users` recreated; `psql \d
    users` confirmed the corrected CHECK constraint text
    (`TRIM(BOTH E'\t\n\r '::text FROM email)`).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.` (model/migration parity).
  - `ruff format --check .` → 2 files needed reformatting → `ruff format .` applied →
    recheck: 17 files formatted.
  - `ruff check .` → 1 import-order error → `ruff check --fix .` → recheck: all checks
    passed.
  - `mypy app tests` → success, 14 source files.
  - Development database verification (untouched): `docker exec jobgoblin-postgres-1
    psql -U jobgoblin -d jobgoblin -c "\dt"` → still only `alembic_version` + `users` at
    revision `0002`; `SELECT count(*) FROM users` → `0`.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "PostgreSQL behavior is tested against
  PostgreSQL, never inferred from SQLite or mocks" (real Postgres, now on a disposable
  database); "every migration is reviewed and tested upgrade -> downgrade -> upgrade"
  (done against the test database specifically this time); "test every important
  constraint with both an accepted and rejected case" (extended — the whitespace fix
  added 6 new rejected cases plus 1 new accepted case); database constraint tests remain
  the sole source of truth for the fixed behavior, not a re-read of the code.
- Skipped or unavailable verification: none. All 24 tests executed for real.
- Deviations and ADR impact: (1) No new pre-fix checkpoint commit was created — one
  already existed (`3816d0a`) matching the requested description exactly, confirmed via
  `git diff` before any edits. Creating a second, functionally identical checkpoint was
  judged redundant; this is flagged explicitly rather than silently substituted. (2)
  Chose a 4-character covered-whitespace set (space, tab, LF, CR) rather than a broader
  one (e.g. including vertical tab/form feed) — documented explicitly in
  `docs/DATA_MODEL.md` and the model itself as the deliberately-scoped definition, per
  the instruction not to claim identical behavior unless genuinely implemented as such.
  No ADR impact — this is a Phase 1 implementation-slice detail, not an architectural
  decision the ADRs track.
- Known limitations: the `jobgoblin` development database's *live* `users` table still
  has the **old**, pre-fix CHECK constraint text on disk (it was migrated before this
  correction pass and was deliberately left untouched, per instructions). It has zero
  rows, so this has no practical effect today, but its schema is currently out of sync
  with the corrected `0002_users.py` migration file until someone runs
  `alembic downgrade 0001 && alembic upgrade head` against it specifically — not done in
  this pass because the instructions required leaving the development database
  untouched. `updated_at` still only advances for ORM-driven writes (unchanged
  limitation from Iteration 1, not in scope for this pass).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `candidate_profiles`.

### Work review

- Date and reviewing agent: 2026-08-24, Codex
- Diff/revision reviewed: commit `28655bb` (`fix(phase-1): harden users slice and isolate
  database tests`) against checkpoint `3816d0a` on branch
  `codex/phase1-users-wip`. The branch matched `origin/codex/phase1-users-wip`, and the
  working tree was clean before review.
- Verification independently performed:
  - Inspected the complete `3816d0a..28655bb` commit diff and all changed files.
  - Docker Compose reports the backend running and PostgreSQL 16 healthy.
  - `ruff format --check .`: 17 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 14 source files.
  - `pytest -v`: 24 passed, 0 skipped.
  - Dedicated `jobgoblin_test` migration `0002 -> 0001 -> 0002`: passed.
  - `alembic check` against `jobgoblin_test`: no new upgrade operations detected.
  - Live schema comparison: both databases report Alembic revision `0002`, but
    `jobgoblin` has the old plain-space-only checks while `jobgoblin_test` has the new
    explicit space/tab/LF/CR checks.
  - `alembic check` against the stale development schema still reported no new upgrade
    operations, confirming that this type of applied-migration drift is not detected or
    repaired automatically.
- Findings, ordered by severity, with file and line references:
  1. **High — rewriting applied migration `0002` creates silent, unrecoverable schema
     drift.** `backend/migrations/versions/0002_users.py:55-61` now contains corrected
     DDL, but the development database already records `0002` and retains the vulnerable
     old checks, as acknowledged in `docs/LLM_HANDOFF.md:306-313`. A normal `alembic
     upgrade head` does nothing because no later revision exists, and `alembic check`
     also reports clean. Any other database that applied checkpoint `3816d0a` has the
     same problem. The correction must be a new forward migration, not a historical
     rewrite.
  2. **High — the fail-closed database guard is not tied to the configured development
     target and exposes credentials on failure.** `backend/tests/conftest.py:22-43`
     hard-codes only the default development database name (`jobgoblin`) instead of
     comparing `TEST_DATABASE_URL` with the actual configured `DATABASE_URL`. A custom
     development database whose name contains `test` can therefore pass the guard even
     when both URLs target the same database. The raised error also includes `url!r`,
     which prints embedded usernames/passwords into test output. In addition,
     `TEST_DATABASE_URL` is read directly from `os.environ` at lines 19-20, so the value
     shown in `.env.example` is not loaded from the project's `.env` by the existing
     Pydantic settings loader; custom configuration behavior is inconsistent with the
     rest of the project.
  3. **High — the test-database documentation casually suggests deleting the persistent
     development volume.** `README.md:79-82` gives `docker compose down -v` as an example
     setup route. That command destroys `postgres_data`, including the development
     database this change is intended to protect. The safe manual `CREATE DATABASE`
     path is sufficient for an existing volume; destructive reset instructions should
     not be presented as a routine alternative.
- Missing or inconclusive verification: I did not execute the README's destructive
  `docker compose down -v` example. I did not test an external database; the live local
  comparison was sufficient to reproduce the migration-drift condition.
- Architecture/documentation consistency: The four-character email rule, ORM behavior,
  fresh-schema migration, regression tests, corrected README/Base status statements,
  and Phase 9 roadmap correction are internally consistent. The three findings above
  concern migration lifecycle and safety boundaries rather than the normalized-email
  rule itself.
- Verdict: changes requested.
- Exact requested corrections:
  1. Restore migration `0002` to the exact DDL in checkpoint `3816d0a`. Add migration
     `0003` whose upgrade drops/recreates the two email checks with the explicit
     space/tab/LF/CR expressions and whose downgrade restores the old `0002` checks.
     Verify fresh `base -> head`, existing `0002 -> 0003`, `0003 -> 0002 -> 0003`, and
     model/head parity against the disposable test database.
  2. Apply the new constraint-only `0003` with `alembic upgrade head` to the empty
     development database; do not downgrade or drop its `users` table. Confirm both
     databases reach `0003` and reject the tab/newline probes.
  3. Make the safety guard compare the normalized test target with the actual configured
     development target as well as requiring an explicit test marker. Never include a
     credential-bearing URL in an exception. Add tests for equal dev/test targets, a
     custom development database name containing `test`, missing test markers, accepted
     distinct test targets, and credential redaction.
  4. Load/document `TEST_DATABASE_URL` consistently with the project's `.env` behavior;
     do not imply that copying `.env.example` configures a value that the tests ignore.
  5. Remove the `docker compose down -v` setup suggestion. If volume deletion is
     mentioned at all, label it explicitly destructive and unnecessary for normal test
     setup.
  6. Rerun format, lint, mypy, all tests, and the migration checks above. Rotate the
     ledger according to its two-iteration rule, record the correction as the newest
     `Work done`, commit/push only the task branch, and stop. Do not begin
     `candidate_profiles`.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.
