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
`user_jobs` initial implementation pass and its "changes requested" review) was
removed rather than kept alongside a third entry, since the correction pass below
superseded it and the whole slice is now merged. Nothing below was rewritten — only
renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: the three bounded
  corrections from the review at `15d0212`, on the same `phase-1/user-jobs` branch.
  Base: `15d0212`. Test/service-code/documentation-wording correction only — no
  migration/schema change.
- Outcome:
  1. **`set_status()`'s timezone-aware check fixed.** `backend/app/services/
     user_jobs.py` previously checked only `changed_at.tzinfo is None`. Per Python's
     own datetime contract, a datetime is aware only when `tzinfo` is not `None`
     **and** `tzinfo.utcoffset(self)` is not `None` — a `tzinfo` subclass whose
     `utcoffset()` returns `None` passed the old guard while still being effectively
     naive. Changed the check to `changed_at.tzinfo is None or changed_at.utcoffset()
     is None`, evaluated before any mutation (unchanged ordering — still ahead of the
     status-validity/no-op/mutation logic). Added
     `test_changed_at_with_none_utcoffset_rejected_without_mutation`, using a small
     `_UtcOffsetNoneTzinfo(tzinfo)` test double whose `utcoffset()` returns `None`,
     proving `ValueError` and zero mutation of `status`/`applied_at`/
     `status_changed_at`.
  2. **Direct-SQL acceptance now covers all nine statuses.** Added
     `test_direct_sql_pre_application_status_with_null_applied_at_accepted`
     (parametrized over both pre-application statuses, `applied_at` omitted/`NULL`)
     and `test_direct_sql_post_application_status_with_non_null_applied_at_accepted`
     (parametrized over all seven post-application statuses, `applied_at = now()`).
     The approved nine-status matrix is now genuinely covered by both ORM and direct
     SQL for the accepted half, matching what `docs/ROADMAP.md` and the prior
     iteration's `Work done` already claimed — that prior entry was left unedited, per
     this ledger's append-only convention.
  3. **Flag-independence test now proves each flag independently.** Replaced
     `test_saved_hidden_archived_independent_of_status_and_each_other` (which set all
     three flags `True` in one row, proving only one combined state) with
     `test_flag_independent_of_status_and_other_flags_on_orm_path`, parametrized over
     `saved`/`hidden`/`archived`: each case sets exactly one flag `True` (the other two
     left at their default `False`) alongside a post-application status
     (`offer`/`applied_at` set), commits, reloads, and asserts all three flags match
     the expected per-flag combination — not merely that some combination is accepted.
     The new test's docstring accurately describes what it proves; the prior
     docstring's "unsaved" vs. `saved=True` mismatch no longer exists, since that test
     was replaced rather than reworded.
- Files changed:
  - `backend/app/services/user_jobs.py` — timezone-aware check fix (item 1) plus an
    expanded docstring explaining the `tzinfo`/`utcoffset()` distinction.
  - `backend/tests/test_user_jobs_service.py` — new `_UtcOffsetNoneTzinfo` test
    double and `test_changed_at_with_none_utcoffset_rejected_without_mutation` (item
    1).
  - `backend/tests/test_user_jobs.py` — two new parametrized direct-SQL acceptance
    tests (item 2, 9 parametrized cases total); replaced the single combined-flags
    test with a parametrized per-flag test (item 3, 3 parametrized cases).
- Commands run and exact results (no Alembic round-trips — no migration/schema
  change, per the review's own scoping):
  - `pytest tests/test_user_jobs.py tests/test_user_jobs_service.py -q` → 67 passed
    (up from 55 — 9 new direct-SQL acceptance cases + 1 new tzinfo regression test +
    2 net-new flag-independence cases replacing the 1 prior combined test).
  - `pytest -q` (full suite) → 1047 passed (up from 1035).
  - `ruff format --check .`, `ruff check .` → passed (66 files).
  - `mypy app tests scripts` → success, 49 source files.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Deviations/known limitations: none. All three findings were a service-code
  correctness gap and two test-coverage gaps; no schema, migration, or documented
  product-behavior claim changed beyond what the fixes themselves make true.
- STOP — awaiting Codex re-review. Do not begin `job_notes`, another slice, or modify
  `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `15d0212..b992f6e`
  (`phase-1/user-jobs`). Verdict: **approved**. Findings: none.
- Independently verified:
  - `set_status()` now applies Python's complete awareness test (`tzinfo is not None`
    and `utcoffset() is not None`) before mutation, and the new regression test proves
    the previously accepted `tzinfo`/NULL-offset case raises `ValueError` without
    changing any of the three governed fields.
  - Raw SQL now accepts every one of the nine valid status/`applied_at` pairings: the
    two pre-application statuses with NULL and all seven post-application statuses
    with a timestamp. Together with the existing rejected-pair tests, the documented
    ORM/direct-SQL matrix is complete.
  - The flag test now independently persists and reloads each of `saved`, `hidden`,
    and `archived` as the sole true flag alongside a valid post-application status;
    its prose matches the exercised state.
  - Targeted suites: **67 passed**. Full suite: **1047 passed** using a dedicated
    writable pytest base-temp directory (the prior review's eight setup errors were
    therefore confirmed to be only host-temp permissions). Repository checker,
    `git diff --check`, Ruff format/check, and mypy (**49 source files**) all pass.
    The correction changes only the service, bounded tests, and handoff ledger; model,
    migration, schema, and product documentation are unchanged.
- Non-blocking historical clarification: this iteration's `Work done` says the
  timezone guard remains ahead of “status-validity/no-op/mutation logic.” The actual
  and correct order is invalid-status validation first, timezone validation second,
  then no-op/mutation. Both validations still precede every mutation, so this wording
  has no behavioral or approval impact and the append-only entry is left untouched.
- The `user_jobs` slice and correction pass are accepted. Do not merge to or modify
  `main`, begin `job_notes`, or advance to another slice without explicit user
  authorization.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `71f8861`. Per user authorization, `phase-1/user-jobs` was merged into `main`
with a normal merge commit (`3021ecb`; `--no-ff`, no squash/rebase/force-push) and
pushed. `main`/`origin/main` are both now at `3021ecb`. Verified: `main` has zero
content diff against the feature branch; migration `0016` (`down_revision = "0015"`)
is present and is the sole Alembic head; `python backend/scripts/check_repo.py` (via
the project's own virtualenv interpreter) exits 0 with zero findings; working tree
clean. `job_notes` not started or proposed.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `job_notes`,
  Class H per docs/LLM_WORKFLOW.md — user-state preservation, the same reason
  `user_jobs` is Class H. Phase 1's **final** schema table. Base `93a4ee5` on `main`
  -> branch `phase-1/job-notes`.
- Outcome: new model, migration `0017`, factory/real-commit helper, and 17 new tests
  implemented and verified against real PostgreSQL, per the user's binding decisions:
  1. **No `job_notes.user_id` column added.** Ownership is reached and enforced
     entirely through the required `user_job_id` -> `user_jobs.id` foreign key,
     matching `saved_search_titles.saved_search_id`/`candidate_skills.
     candidate_profile_id`'s own precedent (neither carries a redundant `user_id`
     either). `docs/ARCHITECTURE.md` §1.4 corrected to distinguish directly
     user-owned tables from child tables whose ownership is enforced through a
     required parent FK, rather than adding a redundant column.
  2. `body`: TEXT NOT NULL, ORM-trimmed (established four-character whitespace set,
     case/internal whitespace preserved), matching database `CHECK` pair requiring
     an already-trimmed, non-empty value — empty/whitespace-only notes rejected
     outright, unlike `identity_conflicts.resolution`'s optional-narrative
     blank-collapses-to-`NULL` treatment (a `job_notes` row's only reason to exist
     is to hold `body`).
  3. `INDEX (user_job_id, created_at DESC)` added, no `UNIQUE` constraint — multiple
     notes per `user_job_id` accepted (proven via an explicit `count()` test, not
     merely that a commit didn't raise).
  4. `created_at`/`updated_at` kept exactly as already specified (standard global
     convention; no table-doc-omission tension here, unlike every table since
     `collection_runs`).
  5. All three CASCADE-isolation paths proven: deleting a `User` or a `Job` cascades
     two levels deep through `user_jobs` to `job_notes`; deleting a `UserJob`
     directly also cascades. Each proven isolated against a second, independent
     chain (including the intermediate `UserJob` row itself confirmed deleted for
     the two-level cases).
  6. Documented the "current consumer" resolution: this table's Phase 1 consumers
     are its own factory, the accepted schema exit gate, and the PostgreSQL
     constraint/cascade tests; Phase 10 remains the first production CRUD writer,
     not the first consumer of the schema itself. No service or API code added —
     unlike `user_jobs`, ARCHITECTURE.md §13 names no Phase 1 service function for
     this table.
  - Adversarial self-review (below) found and fixed one real, repeated documentation
    defect: an initial "this schema's first two-level CASCADE chain" claim (written
    into the model, migration, `DATA_MODEL.md`, `ROADMAP.md`, and one test
    docstring) was false — `saved_search_titles`/`saved_search_locations` (via
    `saved_searches.user_id`) and `candidate_skills` (via `candidate_profiles.
    user_id`) already form two-level CASCADE chains from `users`, predating this
    slice. Corrected in all five places to state what is actually new: `user_jobs`
    has two parent FKs, so `job_notes` is reachable by a two-level cascade from
    either `users` or `jobs`, not just one.
- Files changed:
  - `backend/app/db/models/job_note.py` (new).
  - `backend/app/db/models/__init__.py`, `backend/app/db/base.py` —
    registration/docstring (the docstring now describes all fifteen Phase 1 models
    as complete, not "every other Phase 1 table will follow").
  - `backend/migrations/versions/0017_job_notes.py` (new, `down_revision = "0016"`).
  - `backend/tests/conftest.py` — `make_job_note`, `real_committed_job_note` (builds
    on the pre-existing `real_committed_user_job` helper).
  - `backend/tests/test_job_notes.py` (new, 17 tests) — baseline/defaults;
    `user_job_id` FK (nonexistent rejected, omission rejected via direct SQL);
    three CASCADE-isolation tests (via `User`, via `Job`, via `UserJob` directly),
    each proving both the intermediate row (where applicable) and the target note
    are gone, and an unrelated chain's own note survives; `body` NOT NULL/trim/
    non-empty (ORM + direct SQL, including the direct-SQL backstop for an
    untrimmed value bypassing the ORM entirely); `created_at`/`updated_at`
    defaults/independence/UTC-awareness/advancing-on-commit; multiple notes per
    `user_job_id` accepted (explicit count assertion).
  - `docs/DATA_MODEL.md` — `job_notes` marked **Implemented**; added "Rev 22" note
    recording every resolved decision; added the constraints-summary rows (this
    table previously had none at all).
  - `docs/ROADMAP.md` — Phase 1 status paragraph extended to describe the
    `job_notes` slice as complete — noting all fifteen Phase 1 domain tables (ADR
    0003) are now migrated, with the rest of Phase 1's exit gate still to be
    independently verified.
  - `docs/ARCHITECTURE.md` — §1.4 corrected (item 1 above).
- Commands run and exact results:
  - `pytest tests/test_job_notes.py -q` → 17 passed.
  - `pytest -q` (full suite) → 1064 passed (up from 1047), re-confirmed again after
    the fresh migration rebuild below.
  - `ruff format --check .`, `ruff check .` → passed (69 files).
  - `mypy app tests scripts` → success, 51 source files.
  - `DATABASE_URL=...jobgoblin_test`: `downgrade 0016` / `upgrade head` (round-trip),
    `downgrade base` / `upgrade head` (fresh `base -> head`, all fifteen Phase 1
    tables), `alembic check` (`No new upgrade operations detected` — same
    informational `Computed`-column `UserWarning` as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`pg_constraint`, `pg_indexes`,
    `information_schema.columns`) after the fresh rebuild — confirmed 4
    constraints, the FK's `ON DELETE CASCADE` (`confdeltype = 'c'`), the composite
    index with `created_at DESC`, no `UNIQUE` constraint, and every column default,
    matching the model exactly.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual uncommitted diff before commit; full
  12-question Class H depth): **one substantiated Medium finding, fixed** — the
  false "first two-level CASCADE chain" claim described above, found by checking
  every CASCADE-precedent/superlative claim against the actual model files (this
  codebase's own documented history of "first X" mistakes). Explicitly checked and
  clean otherwise: model/migration `CHECK` expressions byte-identical; the ORM trim
  validator cannot itself bypass the CHECK (a whitespace-only input trims to `""`,
  still rejected at commit); the direct-SQL tests prove the database `CHECK` is the
  real backstop independent of the ORM; the composite index's column order/DESC
  direction confirmed via live introspection, and confirmed no `UNIQUE` constraint
  exists anywhere on this table; all three CASCADE tests proven to isolate against
  a fully independent second chain, with the intermediate `UserJob` also confirmed
  deleted for the two-level cases; the multiple-notes test proven via an explicit
  `count()`, not just a non-raising commit; no test overclaims concurrency; no
  cross-test state leakage; no `services/`/`api/` dependency-boundary violation
  anywhere in the new test/conftest code; the schema supports Phase 10's eventual
  list/create/edit/delete-by-recency consumer without any further migration.
- Deviations/known limitations: none beyond the one fixed finding above. No
  service-layer code, API routes, or Phase 10 behavior added, per explicit scope.
  Phase 2 not started, referenced, or scoped.
- STOP — awaiting Codex review. Do not begin Phase 2, modify or merge `main`, or add
  Phase 10 behavior.

### Work review

*Pending — awaiting Codex.*
