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

---

## Iteration 1

### Work done

Status: awaiting the next implementation handoff.

When completing this section, replace the placeholder with:

- Date and agent:
- Approved phase/slice:
- Outcome:
- Base/starting commit:
- Ending commit or working-tree state:
- Files changed:
- Migration revisions:
- Commands run and exact results:
- Risks exercised from `PHASE_RISK_CHECKLIST.md`:
- Skipped or unavailable verification:
- Deviations and ADR impact:
- Known limitations:
- Recommended next smallest slice:
- STOP — awaiting review and user approval.

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
