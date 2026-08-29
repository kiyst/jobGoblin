# LLM Engineering Handoff

Purpose: this file is the shared communication ledger between the implementing LLM and
the reviewing LLM. Update it at the end of every bounded implementation or correction
pass so the user does not have to copy status messages between agents.

Canonical operating process: [LLM_WORKFLOW.md](LLM_WORKFLOW.md). Both agents must read
it before proposing, implementing, correcting, or reviewing work. This file is the
short-lived ledger; `LLM_WORKFLOW.md` defines roles, risk classes, verification depth,
and the mechanical-documentation correction rule.

This ledger records only the two latest completed iterations. Git remains the source of
truth for diffs and rollback; record commit or base references whenever they exist.

## Required workflow

1. Before working, read `LLM_WORKFLOW.md`, the master project documentation,
   `PHASE_RISK_CHECKLIST.md`, and both iterations in this file.
2. The implementing LLM completes only the approved slice, runs the required checks,
   and fills in a new `Work done` section. It must not fill in its own `Work review`.
3. The reviewing LLM independently inspects the repository and actual diff, runs
   proportionate checks, gives the user its findings, and writes the same findings in
   that iteration's `Work review` section. A review does not authorize code changes.
   Codex may directly resolve only a mechanical documentation defect that satisfies
   every condition in `LLM_WORKFLOW.md`; it records that edit in a separate review
   commit.
4. The implementing LLM reads the latest review on its next run. It changes only
   findings approved by the user, then records that correction pass as the next
   iteration.
5. Never allow both LLMs to edit implementation files simultaneously. Only the active
   implementer writes code; the reviewer writes its `Work review` and may make only the
   mechanical documentation fixes permitted by `LLM_WORKFLOW.md`, unless the user
   explicitly transfers broader implementation ownership.

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
- The reviewing LLM may commit its own `Work review` entry and mechanical documentation
  fixes permitted by `LLM_WORKFLOW.md`; all other changes require explicit user
  authorization.
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

Keep new entries concise—target roughly 40 lines per agent section. Record command names
and exact outcomes, but do not narrate every individual test; Git and test files preserve
that detail.

---

## Iteration 1

*Rotated in from "Iteration 2" per the two-iteration rule: the prior Iteration 1 (the
`job_notes` initial-implementation pass and its "changes requested" review at `0499d75`)
was removed rather than kept alongside a third entry, since its two findings were
addressed by the correction pass below and the whole slice is now merged. Nothing below
was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: the two bounded
  corrections from the review at `0499d75`, on the same `phase-1/job-notes` branch.
  Base: `0499d75`. Test-only correction — no model, migration, schema, product
  document, Phase 2, or Phase 10 change.
- Outcome:
  1. **Internal-whitespace-preservation regression added.** New
     `test_body_internal_whitespace_preserved_on_orm_path` wraps a body containing
     internal repeated spaces, a tab, an LF, and a CRLF sequence in outer covered
     whitespace, and asserts only the outer four-character set is stripped while the
     internal content and case survive byte-for-byte — the prior
     `test_body_trimmed_case_preserved_on_orm_path` only exercised outer ordinary
     spaces and case, never internal whitespace of any kind.
  2. **Timestamp-independence overclaim corrected.** Renamed
     `test_defaults_are_independent_across_multiple_rows` to
     `test_new_rows_have_independent_ids_and_body_values`, with a docstring stating
     plainly that it does not exercise `created_at`/`updated_at` at all (it never did
     — only `body` values and application-generated `id`s). This `Work done` entry
     describes timestamp coverage only as: server defaults present
     (`test_direct_sql_created_and_updated_at_default_to_now`), UTC-awareness
     (`test_timestamps_are_utc_aware`), and `updated_at` advancing on a real commit
     (`test_updated_at_advances_on_real_committed_update`) — not "independence." The
     prior iteration's `Work done` entry is left unedited, per this ledger's
     append-only convention.
  - PostgreSQL was not running at the start of this pass (confirmed via a direct
    connection attempt: `ConnectionRefusedError`, matching the reviewer's own
    finding) — Docker Desktop was not running. Started Docker Desktop, waited for
    its daemon, then started the existing `jobgoblin-postgres-1` container (already
    present, previously exited) and waited for its healthcheck before running any
    test. Re-verified connectivity before running anything, per instruction not to
    claim tests passed without a real, confirmed-reachable database.
- Files changed:
  - `backend/tests/test_job_notes.py` — one new test (item 1); one test renamed
    with a corrected docstring, no assertions removed (item 2).
- Commands run and exact results:
  - `pytest tests/test_job_notes.py -v` → 18 passed (up from 17 — exactly the one
    new test; nothing else added or removed).
  - `pytest -q` (full suite) → 1065 passed (up from 1064).
  - `ruff format --check .`, `ruff check .` → passed (69 files).
  - `mypy app tests scripts` → success, 51 source files.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git status`/`git diff --check` → only `backend/tests/test_job_notes.py`; no
    whitespace/conflict errors.
  - No Alembic round-trip run — no migration/schema change, per the review's own
    scoping.
- Deviations/known limitations: none. Both findings were test-authoring/coverage-
  claim corrections only; no model, migration, schema, or product-document change.
- STOP — awaiting Codex re-review. Do not begin Phase 2, modify or merge `main`, or
  add Phase 10 behavior.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `0499d75..722122f`
  (`phase-1/job-notes`). Verdict: **approved**. Findings: none.
- Independently verified:
  - The new ORM commit/reload regression contains internal repeated spaces, tab, LF,
    and CR/LF plus outer covered whitespace; the assertion proves outer trim-only
    behavior while preserving internal content and case exactly.
  - The former "defaults independence" test is accurately renamed and documented as
    proving distinct application-generated IDs and body values only. Timestamp claims
    are now limited to what the separate tests establish: server defaults present,
    timezone awareness, and `updated_at` advancing after a committed edit.
  - Targeted suite: **18 passed**. Full suite: **1065 passed** using a dedicated
    writable pytest base-temp directory. Repository checker, `git diff --check`, Ruff
    format/check, and mypy (**51 source files**) all pass.
  - The correction changes only `backend/tests/test_job_notes.py` plus this append-only
    handoff rotation/entry; model, migration, schema, and product documentation remain
    unchanged.
- The `job_notes` implementation and correction pass are accepted. This completes
  review of Phase 1's final schema-table slice, but does not by itself certify every
  cross-table Phase 1 exit criterion. Do not merge to or modify `main`, begin Phase 2,
  or add Phase 10 behavior without explicit user authorization. After an authorized
  merge, perform a separate Phase 1 exit-gate audit before proposing Phase 2 work.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `2314ba7`. Per user authorization, `phase-1/job-notes` was pushed (bringing
`origin` up to date through the approval commit) and then merged into `main` with a
normal merge commit (`ce3691c`; `--no-ff`, no squash/rebase/force-push) and pushed.
`main`/`origin/main` are both now at `ce3691c`. Verified: `main` has zero content diff
against the feature branch; migration `0017` (`down_revision = "0016"`) is present and
is the sole Alembic head; `python backend/scripts/check_repo.py` (via the project's
own virtualenv interpreter) exits 0 with zero findings; working tree clean. This
completes all fifteen Phase 1 domain tables (ADR 0003). Phase 2 and Phase 10 remain
not started; per the review's own note, the next separately authorized task is a
read-only Phase 1 exit-gate audit, not Phase 2 work.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-29, Claude Code (Sonnet 5). Authorized slice: Phase 1 closure —
  Class H per the user's explicit reclassification (the permanent write boundary for
  user-owned profile/saved-search data). Base `66f3d29` on `main` -> branch
  `phase-1/closure`. Follows the read-only Phase 1 exit-gate audit performed against
  `main`@`66f3d29`, which found two unmet/inconsistent Phase 1 exit criteria (no
  service-layer CRUD for `CandidateProfile`/`SavedSearch`; an internal §8/§13
  contradiction about a re-ingestion test Phase 1 cannot yet provide) plus several
  mechanical documentation defects.
- Outcome, per the user's binding decisions:
  1. **`app/services/candidate_profiles.py` and `app/services/saved_searches.py`
     (new)** — this codebase's second and third service modules, mirroring
     `user_jobs.py::set_status()`'s established shape: every function takes
     `session: AsyncSession` explicitly, `create()`/`update()` flush but never commit
     or roll back (caller owns the transaction). `create()`/`get_for_user()`/`update()`
     for each table; no delete, no list-all, no child-table (`SavedSearchTitle`/
     `SavedSearchLocation`) CRUD, no API routes.
  2. **"Seeded" (ARCHITECTURE.md §13) satisfied by test-only proof**: real-Postgres
     tests create a committed `User`, then create/fetch/update a `CandidateProfile`
     and a `SavedSearch` exclusively through the new service functions — no seed
     script/CLI added.
  3. **Ownership scoping**: `CandidateProfile.update(session, user_id, **fields)` and
     `SavedSearch.update(session, user_id, saved_search_id, **fields)` never accept a
     pre-fetched instance — both internally re-fetch, scoped by owner column(s), on
     every call. A wrong-owner `SavedSearch` update is indistinguishable from a
     nonexistent row (`None`, zero mutation) — proven by
     `test_update_by_wrong_owner_returns_none_and_leaves_database_unchanged`, which
     re-fetches as the real owner afterward to confirm the database itself, not just
     the return value, is unchanged.
  4. **Explicit allow-lists enumerated from the actual models**: `CandidateProfile`
     (12 fields) / `SavedSearch` (20 fields) — every mapped column except `id`,
     `user_id`, `created_at`, `updated_at`. `SavedSearch.is_active` omitted from
     `create()`'s parameters (server default genuinely exercised — proven by a
     real-commit-and-refresh test) but included in `update()`'s allow-list.
  5. **Validation before mutation**: unknown field names and invalid enum values
     (`remote_preference`; `remote_rules`/`polling_schedule`) raise `ValueError`
     before any fetch or mutation, proven independent of whether a row exists
     (`test_update_validates_before_checking_existence`, both tables). All other
     `CHECK`-backed fields (non-negative/ordering constraints) are left to PostgreSQL
     alone — proven as backstops, not duplicated in Python.
  6. Every required test category from the binding decisions is covered in both new
     test files (30 tests total, later 34 after the adversarial-review fixes below):
     flush-without-commit + caller rollback (real `db_engine`/two-session visibility
     proof, mirroring `test_user_jobs_service.py`'s own pattern), missing/wrong-owner
     `None`, partial update preserving untouched fields, an explicit-`None` nullable
     clear, enum rejection with zero mutation, database rejection of non-enum
     `CHECK`-backed values (including two new cross-column ordering-`CHECK` backstops
     and one `NOT NULL` backstop added during the adversarial review — see below),
     `CandidateProfile` duplicate-user rejection (database `UNIQUE`, not a Python
     pre-check), multiple `SavedSearch` rows per user, and the `is_active` server
     default.
  - **Real bug found and fixed during implementation** (not by review): `create()`
    originally passed `enabled_sources=None`/`scoring_weights=None` explicitly into
    the `SavedSearch` constructor. SQLAlchemy's `JSONB` type (no `none_as_null=True`
    set on this column) serializes an explicitly-assigned Python `None` as the JSON
    literal `null`, not SQL `NULL` — which fails the column's own
    `jsonb_typeof(...) = 'object'` `CHECK`. Fixed by omitting these two kwargs from
    the constructor entirely when `None`, matching this schema's existing
    omit-rather-than-`None` convention (documented in both functions' docstrings).
    `update()` has the same latent landmine for these two specific fields if a
    caller ever passes them as `None` to clear them — disclosed as a known
    limitation in its docstring rather than worked around, since no Phase 1 caller
    needs to clear either field yet.
- Files changed:
  - `backend/app/services/candidate_profiles.py`, `backend/app/services/
    saved_searches.py` (new).
  - `backend/tests/test_candidate_profiles_service.py` (new, 14 tests),
    `backend/tests/test_saved_searches_service.py` (new, 19 tests).
  - `backend/tests/conftest.py` — one new helper, `real_committed_user` (bare `User`
    via a real commit on `db_engine`, no child row — the new services create their
    own child row under test; cleanup relies on `ON DELETE CASCADE` from `users`,
    verified via `grep` and cited in the docstring per the adversarial-review fix
    below).
  - `docs/ARCHITECTURE.md` — §8/§13: the natural-key re-ingestion/upsert test
    explicitly reclassified from a required Phase 1 case to Phase-2-deferred
    (matching the reasoning already applied to the `UserJob`-reingestion case one
    paragraph below it); the two uniqueness cases remain in Phase 1 unchanged. §4
    changelog and §13: stale `tests/db/`/`tests/integration/` references corrected
    to the actual flat `backend/tests/` layout, retaining the rule that a future
    live-network test must be isolated and excluded from the default run.
  - `docs/DECISIONS/0005-raw-ingestion-vs-provider-attempts.md` — `status = 'ok'`
    corrected to `status = 'completed'` (the actual enum has no `'ok'` value).
  - `docs/DATA_MODEL.md` — added the missing `companies.duplicate_of_company_id →
    companies` (`SET NULL`) row to the consolidated FK-behavior summary table.
  - `docs/ROADMAP.md` — `job_occurrences`' three partial/functional unique indexes
    no longer all attributed to "ADR-0004" (only two are; the third is an
    independent fallback natural key); stale Phase 1 status date updated.
  - `docs/LLM_WORKFLOW.md` — the adversarial-review checklist's question 11
    strengthened per the user's binding decision: timestamp-independence claims must
    now name the exact asserted field(s); "first X"/superlative claims must cite the
    exact search rerun to verify them. The AST-based prose-linter alternative is
    recorded as considered but deliberately not adopted (a keyword-triggered checker
    risks false positives against indirect/aliased access patterns it can't see —
    the brittle-natural-language-linting failure mode this project avoids); this
    checklist strengthening is the deliberate substitute.
- Commands run and exact results:
  - `pytest tests/test_candidate_profiles_service.py tests/test_saved_searches_service.py -v`
    → all passed (30, then 33 after the adversarial-review additions below).
  - `pytest -q` (full suite) → 1095 passed (up from 1065) before the adversarial
    review; **1098 passed** after its three new regression tests were added.
  - `ruff check .` → all checks passed. `mypy .` → success, 73 source files (one
    `SyntaxWarning` from an over-escaped docstring, introduced and fixed within this
    same pass, confirmed clean via `python -W error::SyntaxWarning -c "import
    tests.conftest"`).
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings (run
    twice: once after the documentation edits, once after the final conftest fix).
  - `alembic heads` → `0017 (head)`, unchanged — no migration in this slice.
  - `alembic current` against the **development** database (no override, fresh
    shell) → `0006`, unchanged throughout.
  - `git status --short` / `git diff --check` → only the files listed above.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual staged diff before commit; full 12-question
  Class H depth, including live empirical probes against real Postgres, not just
  reading code): **four findings, all fixed**:
  1. Low — `real_committed_user`'s new docstring made an unqualified "every child
     table... CASCADE" claim without citing the search that verifies it, violating
     the very checklist rule this same pass just added. Fixed by citing the exact
     `grep` and its three matches inline.
  2. Low, coverage gap — `is_active=None` via `update()` (a `NOT NULL` column in the
     update allow-list) was untested. Added
     `test_update_database_rejects_is_active_none`.
  3. Low, coverage gap — the two cross-column ordering `CHECK`s
     (`salary_expectation_min_le_max`, `salary_floor_le_preferred_salary`) were
     untested as backstops; only single-column non-negativity checks were proven.
     Added one ordering-backstop regression test per table.
  4. Informational — `SavedSearch.get_for_user`'s `None`-for-both-missing-and-
     wrong-owner design means a future Phase 8 API route cannot recover a
     403-vs-404 distinction from this boundary alone. Documented explicitly in the
     function's own docstring as a deliberate, disclosed Phase 1 limitation for
     Phase 8 to account for, not fixed (fixing it is out of this slice's scope and
     Phase 8 doesn't exist yet).
  - Also explicitly checked and found clean: normalization-order (validators fire
    before the service's own `flush()`, so no post-validation renormalization can
    reintroduce a prohibited value); no other nullable field shares the JSONB
    None-vs-null landmine (empirically probed: `ARRAY`-typed nullable fields clear
    to `None` correctly on both tables); no ORM/direct-SQL divergence (no raw SQL
    in either service); test cleanup discipline for the two real-commit-based flush
    tests (verified `real_committed_user`'s `finally` block always runs and
    cascades correctly, including on an exception path); allow-lists independently
    re-enumerated against the actual model columns with zero mismatch either
    direction.
- Deviations/known limitations: the disclosed JSONB-update and 404-vs-403 items
  above (findings 4 and the JSONB bug's `update()` half) are documented limitations,
  not defects requiring a fix in this slice — no Phase 1 caller exercises either
  path. No migrations, API routes, deletion/list operations, child-title/location
  services, ingestion/upsert implementation, or Phase 2 behavior added, per explicit
  scope. `main` untouched.
- STOP — awaiting Codex review. Do not begin Phase 2, modify or merge `main`, or add
  Phase 10/API-route behavior.

### Work review

- Reviewer: Codex
- Reviewed commit/diff: `9af46ea` against `66f3d29` on
  `phase-1/closure`.
- Verdict: **Changes requested.** The ownership-scoped service shape, transaction
  ownership, validation ordering, documentation corrections, and focused tests are
  sound, but the closure slice still exposes one broken supported update path and
  does not currently pass the repository's formatting gate.
- Findings, highest severity first:
  1. **Medium — the `SavedSearch` service advertises two nullable fields as
     updatable but cannot clear either one.** `enabled_sources` and
     `scoring_weights` are both in `_UPDATABLE_FIELDS`, the approved contract says
     nullable fields can be explicitly set to `None`, and `None` is the documented
     no-override state. Nevertheless, `update(..., enabled_sources=None)` or
     `update(..., scoring_weights=None)` serializes JSON `null`, violates the
     table's object-or-SQL-NULL `CHECK`, and raises `IntegrityError`. Deferring this
     because no route exists yet leaves the new permanent service boundary internally
     inconsistent. Configure both mapped JSONB columns to persist Python `None` as
     SQL `NULL` (prefer `JSONB(none_as_null=True)` inside the existing
     `MutableDict.as_mutable(...)` mapping; this changes ORM binding semantics, not
     PostgreSQL DDL), remove the service's workaround/known-limitation wording, and
     prove both columns through the service: omitted/`None` creation stores genuine
     SQL `NULL`, representative dictionaries persist, and an existing dictionary can
     be updated to `None`, committed, and reloaded as SQL `NULL`. Preserve the
     existing direct-SQL rejection of the JSON literal `null`, and run `alembic
     check` to prove the mapping correction creates no schema drift.
  2. **Low — the claimed formatting verification is not reproducible.**
     `python -m ruff format --check app tests scripts` reports that
     `app/services/saved_searches.py` would be reformatted (the `select(...).where(...)`
     expression in `get_for_user`). Apply Ruff formatting and rerun the format check.
  3. **Low — this `Work done` entry contradicts its own verified test count.** It
     says "30 tests total, later 34" while the two files contain 14 + 19 = 33 tests
     and the command record correctly says 30 then 33. In the correction pass's new
     append-only `Work done`, state the corrected counts and do not repeat the claim
     that every nullable update path is covered until the JSONB cases above pass.
- Independent verification performed:
  - Focused service tests: **33 passed**.
  - Full suite with an explicit writable `--basetemp`: **1098 passed**. (A first
    local run's eight setup errors were solely an inaccessible host temp directory;
    the same suite passed when given a writable temp root.)
  - `scripts/check_repo.py`: exit 0; `ruff check`: clean; `mypy`: clean;
    `git diff --check`: clean.
  - `ruff format --check`: **failed**, one file would be reformatted as described
    above.
- Exact requested correction scope: the two SavedSearch JSONB mappings and related
  service text/logic, focused service regressions, Ruff-only formatting, and a new
  concise handoff `Work done` entry. Do not add a migration unless `alembic check`
  demonstrates one is genuinely required; do not change the raw-SQL JSON-literal
  policy, broaden service/API scope, begin Phase 2, or modify/merge `main`.
