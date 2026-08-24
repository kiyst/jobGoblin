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
no longer pending, so the previous Iteration 1 (the `_COVERED_WHITESPACE`/fail-closed-guard
implementation pass and Codex's first review of it) was removed rather than kept
alongside two already-reviewed entries. Nothing below was rewritten — only renumbered.*

### Work done

- Date and agent: 2026-08-24, Claude Code (Sonnet 4.5).
- Approved phase/slice: second bounded correction pass over the existing Phase 1 `users`
  slice only — all six corrections in Iteration 1's `Work review` approved as one pass.
  No other table, no new slice.
- Outcome: all six approved corrections addressed and verified against real PostgreSQL;
  both the disposable test database and the `jobgoblin` development database now sit at
  migration `0003` with the corrected email-normalization constraints. 26 tests passed,
  0 skipped.
- Base/starting commit: `3ba2635` ("docs(review): request migration and test safety
  fixes") on branch `codex/phase1-users-wip` — Codex's own review commit, on top of
  `28655bb`. Confirmed via `git diff HEAD -- docs/LLM_HANDOFF.md` (empty) before making
  any changes.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this file's
  own "Git workflow" instructions above).
- Files changed:
  - `backend/migrations/versions/0002_users.py` — **restored verbatim** to the exact DDL
    in checkpoint `3816d0a` (the original, bare-`trim` CHECK constraints) — no longer
    describes a fix it never actually applied to any database that had already run it.
  - `backend/migrations/versions/0003_fix_email_whitespace_checks.py` (new) —
    forward-only migration: `upgrade()` drops and recreates the two email CHECK
    constraints with the explicit space/tab/LF/CR expression; `downgrade()` restores the
    original bare-`trim` expressions. Constraint names wrapped in `op.f(...)` — an
    unwrapped plain string re-applies the naming convention a second time, which is
    exactly the bug the first attempt at this migration hit (see Deviations below).
  - `backend/app/config.py` — added `Settings.test_database_url: str | None`, loaded via
    the same `.env`/pydantic-settings mechanism as every other setting.
  - `backend/tests/conftest.py` — `assert_is_disposable_test_database` now takes both
    the test URL and the actual configured development URL, and rejects when their
    resolved `(host, port, database)` match — not just a hardcoded `"jobgoblin"` string
    — as well as when the test URL lacks a `"test"` marker. Added `_redact()` and used it
    in every raised message so a credential-bearing URL is never printed. `db_engine` now
    reads `Settings.test_database_url` (falling back to `DEFAULT_TEST_DATABASE_URL` only
    if unset) instead of `os.environ.get(...)` directly.
  - `backend/tests/test_users.py` — guard tests rewritten for the new two-argument
    signature; added cases for a custom dev-database name containing "test" that's
    actually the configured development target, the ordinary development database,
    a genuinely distinct accepted test database, and credential redaction.
  - `README.md` — removed the `docker compose down -v` example entirely; replaced with
    an explicit warning that it destroys the development database's volume and is not
    part of normal test setup.
  - `docs/DATA_MODEL.md` — documents the `0002`/`0003` split (Rev 6a note) and explains
    why the fix is a forward migration, not an in-place rewrite of an applied one.
  - `docs/ROADMAP.md` — Phase 1 status line now cites both `0002` and `0003`.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 removed; old Iteration 2
    renumbered to Iteration 1; this entry appended as the new Iteration 2).
- Migration revisions: `0002` (`down_revision = "0001"`) restored to its original,
  as-applied DDL, no revision-id change. `0003` (new, `down_revision = "0002"`) —
  forward-only fix to the two email CHECK constraints.
- Commands run and exact results:
  - `git show 3816d0a:backend/migrations/versions/0002_users.py` → fetched the exact
    original DDL used to restore `0002` verbatim.
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` → success, test DB emptied.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → **failed**:
    `asyncpg.exceptions.UndefinedObjectError: constraint
    "ck_users_ck_users_email_normalized" does not exist` — `0003`'s
    `op.drop_constraint`/`op.create_check_constraint` calls passed already-fully-resolved
    names as plain strings, which re-applied the naming convention and double-prefixed
    them. Postgres DDL is transactional and the whole `0001->0002->0003` run was one
    transaction (no `transaction_per_migration`), so this rolled back completely —
    confirmed via `psql`: `alembic_version` had 0 rows, `users` table absent. No partial/
    corrupted state.
  - Fixed `0003` to wrap both constraint names in `op.f(...)`.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` (retry) → success,
    `-> 0001 -> 0002 -> 0003`; `alembic current` → `0003 (head)`; `psql \d users` →
    corrected constraint text confirmed (fresh `base -> head`, scenario 1 of 3).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0002` → success; `psql \d users` →
    **original** bare-`trim` constraint text confirmed restored (half of scenario 3).
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0002 -> 0003`;
    `psql \d users` → corrected text confirmed again (scenario 2 "existing `0002 ->
    0003`", and completes scenario 3 "`0003 -> 0002 -> 0003`").
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.` (model/head parity).
  - `pytest -v` → **26 passed, 0 skipped** (up from 24 — 5 guard tests rewritten/added,
    net +2).
  - `ruff format --check .` → 1 file needed reformatting → `ruff format .` → recheck:
    18 files formatted.
  - `ruff check .` → all checks passed (no fixes needed this time).
  - `mypy app tests` → success, 14 source files.
  - `pytest -q` (re-run after formatting) → 26 passed.
  - Development database, before: `SELECT count(*) FROM users` → `0`; `alembic_version`
    → `0002`.
  - `alembic upgrade head` against the **development** database (default
    `DATABASE_URL`, no override) → success, `0002 -> 0003` only — no downgrade, no drop,
    per the approved correction; `alembic current` → `0003 (head)`.
  - `psql \d users` (development DB) → corrected constraint text confirmed;
    `SELECT count(*) FROM users` → `0` (unchanged, table was never touched structurally
    beyond the constraint swap).
  - Direct tab/newline probe against the **development** database:
    `INSERT INTO users (id, email) VALUES (gen_random_uuid(), E'\tperson@example.com\n');`
    → `ERROR: new row for relation "users" violates check constraint
    "ck_users_email_normalized"` (rejected, as required). `SELECT count(*) FROM users`
    after → `0` (confirmed no row persisted).
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "every migration is reviewed and
  tested upgrade -> downgrade -> upgrade" — now genuinely exercised for `0003`
  specifically, including starting from an already-applied `0002` state matching the
  real development database's actual history, which is exactly the scenario the first
  attempt at this fix got wrong; "PostgreSQL behavior is tested against PostgreSQL" —
  the migration bug itself was only caught by actually running `0003` against real
  Postgres, not by code review alone; "logs and API responses never expose credentials" —
  directly addressed via `_redact()` and its dedicated test.
- Skipped or unavailable verification: none. Every command above executed for real,
  including the development-database migration and its direct probe.
- Deviations and ADR impact: the first attempt at migration `0003` failed on first run
  (naming-convention double-prefixing bug, detailed above) — caught before being
  reported as verified, fixed, and the full round-trip sequence re-run from scratch
  afterward. No ADR impact — Phase 1 implementation-slice detail only.
- Known limitations: none new. The development-database schema drift flagged in
  Iteration 1's `Work review` is resolved (both databases now at `0003` with matching,
  corrected constraints). `updated_at` still only advances for ORM-driven writes
  (unchanged, out of scope for this pass).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `candidate_profiles`.

### Work review

- Date and reviewing agent: 2026-08-24, Codex
- Diff/revision reviewed: commit `31aa213` (`fix(phase-1): forward-migrate email checks
  and harden test-db guard`) against review commit `3ba2635` on branch
  `codex/phase1-users-wip`. The branch matched the remote and the working tree was clean
  before review.
- Verification independently performed:
  - Inspected the complete `3ba2635..31aa213` diff and every changed implementation,
    migration, test, and documentation file.
  - Confirmed `backend/migrations/versions/0002_users.py` is byte-for-byte unchanged
    from checkpoint `3816d0a`.
  - `ruff format --check .`: 18 files already formatted.
  - `ruff check .`: passed.
  - `mypy app tests`: passed for 14 source files.
  - `pytest -v`: 26 passed, 0 skipped.
  - Independently ran `0003 -> 0002 -> 0003` on `jobgoblin_test`: passed.
  - Independently ran `0003 -> base -> 0003` on `jobgoblin_test`: passed.
  - `alembic check` at test-database head: no new upgrade operations detected.
  - Live inspection confirmed both `jobgoblin` and `jobgoblin_test` are at revision
    `0003` with the corrected space/tab/LF/CR constraints.
  - Direct guard probes showed equivalent spellings of the same test-named database are
    accepted: `localhost` versus `127.0.0.1`, and omitted default port versus explicit
    `5432`.
- Findings, ordered by severity, with file and line references:
  1. **High — the destructive-test guard still permits the configured development
     database through common connection aliases.** `backend/tests/conftest.py:55-61`
     compares raw `(host, port, database)` tuples. Consequently, a development URL of
     `postgresql+asyncpg://...@127.0.0.1:5432/my_test_env` and test URL of
     `postgresql+asyncpg://...@localhost:5432/my_test_env` are treated as distinct, even
     though they normally reach the same database; the same occurs for omitted port
     versus explicit PostgreSQL port `5432`. Both probes were accepted. The current
     defaults are safe because their database names differ, but the guard explicitly
     promises protection for custom development database names containing `test`, and
     that promise remains bypassable.
  2. **Low — `0003` is described as “forward-only” despite implementing a downgrade.**
     `backend/migrations/versions/0003_fix_email_whitespace_checks.py:14` and the newest
     `Work done` use that term while the migration is intentionally reversible. This is
     wording only; the downgrade itself passed.
- Missing or inconclusive verification: No destructive production/development action
  was attempted. Host equivalence cannot be proven generically from URL text, so the
  safe invariant should not depend on resolving every possible hostname alias.
- Architecture/documentation consistency: The forward migration strategy, current live
  schemas, four-character whitespace rule, `.env` loading, redacted errors, and removal
  of the destructive volume-reset recommendation are now consistent and verified. Only
  the guard alias gap and minor wording remain.
- Verdict: changes requested.
- Exact requested corrections:
  1. In addition to the current checks, reject the test target whenever its normalized
     database name equals the configured development database name, regardless of host,
     port, credentials, or driver spelling. This conservative rule may reject a
     same-named database on a genuinely separate server; that is acceptable for a
     fail-closed destructive-test guard. Keep the requirement that the test name contain
     `test`.
  2. Add regression tests for same database name with `localhost` versus `127.0.0.1`,
     omitted versus explicit default port, case variation, and distinct database names
     on the same server. Preserve credential-redaction coverage.
  3. Replace “forward-only migration” with “forward corrective migration” or equivalent
     wording everywhere it describes reversible `0003`.
  4. Rerun format, lint, mypy, all tests, and a focused `0003 -> 0002 -> 0003` migration
     cycle. Rotate the two-entry ledger, record the correction as the newest `Work
     done`, commit/push only the task branch, and stop. Do not begin
     `candidate_profiles`.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

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
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
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
  - `docs/LLM_HANDOFF.md` — this rotation (Iteration 1 removed; prior Iteration 2
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
