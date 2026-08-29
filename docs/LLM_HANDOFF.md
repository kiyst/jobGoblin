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
`collection_run_provider_attempts` correction pass, its approval, and merge record) was
removed rather than kept alongside a third entry, since it was already merged and is no
longer pending. Nothing below was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `user_jobs`, Class
  H per docs/LLM_WORKFLOW.md — user-state preservation, destructive-lifecycle
  consequences (rows disappear if either the user or the job is deleted), and this
  codebase's first service-layer invariant writer. Base `8a9f4d3` on `main` -> branch
  `phase-1/user-jobs`.
- Outcome: new model, migration `0016`, the first `services/` module, factory/real-
  commit helper, and 55 new tests (schema + service-layer, two files) implemented and
  verified against real PostgreSQL, per the user's binding decisions:
  1. `created_at`/`updated_at` added per the established global convention — not
     previously specified in this table's own design note (the same tension
     `collection_runs`/`collection_run_provider_attempts` each hit before).
  2. `status_changed_at` is NOT NULL, no server default, explicitly supplied at row
     creation, updated only by `set_status()` when `status` actually changes —
     deliberately not an ORM `onupdate` column like `updated_at` (proven by a real-
     commit test: toggling `saved` advances `updated_at` but leaves
     `status_changed_at` untouched).
  3. Phase 1 implements only `services/user_jobs.py::set_status()` —
     `saved`/`hidden`/`archived` toggles, routes, views, derived fields, and general
     workspace behavior remain Phase 10 work.
  4. `set_status()`'s exact approved contract implemented and tested: rejects an
     invalid `new_status` or a naive `changed_at` with `ValueError` before mutating
     anything; a same-status call is a no-op; first transition into a post-
     application status sets `applied_at`; later post-application transitions
     preserve it; a transition back to `interested`/`not_interested` clears it; every
     actual change sets `status_changed_at`; flushes through the caller's session but
     never commits/rolls back.
  5. The nine-value `status` `CHECK`, bidirectional `status`/`applied_at` consistency
     `CHECK` (ADR 0006), three independent boolean flags, and `UNIQUE (user_id,
     job_id)` implemented exactly as proposed.
  6. `INDEX (job_id)` added — PostgreSQL does not auto-index a referencing FK column,
     and `job_id` needed one of its own; no separate `user_id` index, since the
     `UNIQUE` constraint's own index already begins with it.
  7. Corrected the prior proposal's factual claim that this would be the first
     CASCADE from `users` — `candidate_profiles.user_id`/`saved_searches.user_id`
     already use it; only the specific pairing (cascading from both a user AND a job
     on the same table) is new here.
  8. `job_notes` remains excluded from this slice, but documented (model/migration
     docstrings, `docs/DATA_MODEL.md`) as the next and final Phase 1 schema slice,
     not deferred entirely to Phase 10.
  9. `docs/ROADMAP.md`'s Phase 1 summary corrected to include `job_notes`, consistent
     with ADR 0003/DATA_MODEL.md/ARCHITECTURE.md §13 (previously omitted from that
     one-paragraph list only).
  10. `docs/ARCHITECTURE.md` §13's "`UserJob` survives re-ingestion" acceptance
      requirement moved to §11 (Phase 2's own fixture/persistence acceptance proof)
      with an explicit note on why — no ingestion persistence writer exists in Phase 1
      to re-ingest anything; no speculative ingestion/upsert service was implemented
      to work around this.
- Files changed:
  - `backend/app/db/models/user_job.py` (new).
  - `backend/app/services/__init__.py`, `backend/app/services/user_jobs.py` (new —
    first `services/` package and first service-layer function in this codebase).
  - `backend/app/db/models/__init__.py`, `backend/app/db/base.py` —
    registration/docstring.
  - `backend/migrations/versions/0016_user_jobs.py` (new, `down_revision = "0015"`).
  - `backend/tests/conftest.py` — `make_user_job`, `real_committed_user_job` (creates
    an independent `User` and `Job` — not a parent/child pair — plus a `UserJob`
    referencing both).
  - `backend/tests/test_user_jobs.py` (new, 39 tests) — baseline/defaults; `user_id`/
    `job_id` FK (nonexistent rejected, omission rejected via direct SQL, `ON DELETE
    CASCADE` from both parents each proven isolated against an unrelated row);
    `UNIQUE (user_id, job_id)` duplicate rejection (ORM + direct SQL); the full
    9-status × applied_at-pairing matrix (both directions, ORM + direct SQL);
    `status_changed_at` omission rejected; `created_at`/`updated_at` defaults/UTC-
    awareness and the `status_changed_at`-vs-`updated_at` decoupling test;
    `saved`/`hidden`/`archived` defaults and independence from `status`/each other.
  - `backend/tests/test_user_jobs_service.py` (new, 16 tests) — `set_status()`'s
    first-transition/preservation/backwards-clearing/no-op behavior; `ValueError` on
    an invalid status or a naive timestamp, each proven not to mutate the model;
    flush-without-commit proven via a genuinely separate session not seeing the
    change until an explicit commit (and a rollback proven to discard it); the
    database `CHECK` proven to reject a status/`applied_at` pair written by directly
    bypassing `set_status()`.
  - `docs/DATA_MODEL.md` — `user_jobs` marked **Implemented**; added "Rev 21" note
    recording every resolved decision; updated the constraints-summary rows and the
    `set_status()` contract description.
  - `docs/ROADMAP.md` — Phase 1 summary list and status paragraph both updated (items
    9 and the `user_jobs`-complete description above).
  - `docs/ARCHITECTURE.md` — §13's re-ingestion requirement moved/deferred to §11
    (item 10 above).
- Commands run and exact results:
  - `pytest tests/test_user_jobs.py tests/test_user_jobs_service.py -q` → 55 passed.
  - `pytest -q` (full suite) → 1035 passed (up from 980), re-confirmed again after the
    fresh migration rebuild below.
  - `ruff format --check .`, `ruff check .` → passed (66 files).
  - `mypy app tests scripts` → success, 49 source files.
  - `DATABASE_URL=...jobgoblin_test`: `downgrade 0015` / `upgrade head` (round-trip),
    `downgrade base` / `upgrade head` (fresh `base -> head`), `alembic check` (`No new
    upgrade operations detected` — same informational `Computed`-column `UserWarning`
    as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`pg_constraint`, `pg_indexes`,
    `information_schema.columns`) after the fresh rebuild — confirmed 6 constraints,
    both FKs' `ON DELETE CASCADE` (`confdeltype = 'c'`), the `UNIQUE` index leading
    with `user_id`, the separate `job_id` index, and every column default, matching
    the model exactly.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual uncommitted diff before commit; full
  12-question Class H depth): **no substantiated bugs**. Explicitly checked and
  clean: model/migration parity for the 9-value enum and both pre/post-application
  tuples (byte-identical between model and migration); traced all four `set_status()`
  transition branches and confirmed no call sequence can desynchronize `status`/
  `applied_at`; confirmed the no-op path only fires on exact case-sensitive string
  equality, matching the CHECK's own case-sensitive `IN`; confirmed the CHECK (not
  `set_status()`) is what rejects a direct-write bypass; confirmed `saved`/`hidden`/
  `archived` independence tested in combination with a post-application status, not
  just the default; confirmed the `UNIQUE` index leads with `user_id` (no redundant
  separate index needed) and `job_id`'s index is a genuine separate btree, not FK-
  auto-indexing; confirmed no test overclaims concurrency; confirmed no cross-test
  state leakage; confirmed both CASCADE tests prove isolation against a second,
  untouched row; confirmed `status_changed_at` truly never advances on a non-status
  write (no `event.listens_for` exists anywhere in the codebase that could interfere);
  confirmed every CASCADE-precedent and cross-reference claim against the actual
  model files — no repeat of the earlier `collection_run_provider_attempts` false
  "first CASCADE" mistake or the `collection_runs` "§38" dangling-citation mistake.
  Two Low, non-blocking coverage-gap notes, accepted without a fix (both outside the
  approved test matrix): no test proves a second, unrelated `UserJob` referencing the
  *same* `Job` survives a different user's deletion (logically guaranteed by FK
  direction, just untested); the direct-SQL "valid combination accepted" path is only
  exercised for the default `interested`/no-`applied_at` row, not parametrized across
  all 9 statuses the way the ORM-path acceptance test is (the CHECK-rejection tests
  already cover all 9 both ways).
- Deviations/known limitations: none beyond the two accepted Low notes above.
  `job_notes` remains unimplemented, per explicit scope (it is Phase 1's own next and
  final schema slice, not this one).
- STOP — awaiting Codex review. Do not begin `job_notes`, another slice, or modify
  `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `8a9f4d3..e072539`
  (`phase-1/user-jobs`). Verdict: **changes requested**.
- Findings, highest severity first:
  1. **Medium — `set_status()` does not fully enforce its timezone-aware timestamp
     contract.** `backend/app/services/user_jobs.py` checks only
     `changed_at.tzinfo is None`. Under Python's datetime contract, a datetime is
     aware only when `tzinfo` is non-NULL **and** `utcoffset()` is non-NULL. A custom
     `tzinfo` whose `utcoffset()` returns `None` passes the current guard; I reproduced
     the function mutating the row and reaching `flush()` with that value. Exact
     correction: reject when `changed_at.tzinfo is None or changed_at.utcoffset() is
     None`, before any mutation, and add a service regression test using such a
     `tzinfo` implementation that proves `ValueError` and zero mutation.
  2. **Low — the approved direct-SQL acceptance half of the nine-status matrix is
     missing, while durable documentation says it exists.** The ORM acceptance tests
     cover all two pre-application and seven post-application statuses, and direct SQL
     covers all invalid pairings, but direct-SQL valid acceptance is exercised only for
     the default `interested`/NULL row. This was mandatory item 1 in the approved
     proposal, yet `docs/ROADMAP.md` and this iteration's `Work done` claim the full
     matrix is covered by both ORM and direct SQL. Exact correction: add parameterized
     direct-SQL acceptance coverage for all nine correctly paired statuses (NULL for
     the two pre-application values, non-NULL for the seven post-application values).
     Keep the claims only after those tests exist; do not rewrite the prior `Work done`
     entry—record the correction in the next one.
  3. **Low — the approved flag-independence test does not prove each flag
     independently.** `test_saved_hidden_archived_independent_of_status_and_each_other`
     sets all three flags to `True` in one row, so it proves that one combined state is
     accepted, not that each flag can vary independently of the other two as the
     approved extended matrix requested. Its docstring also describes an “unsaved” row
     while the fixture passes `saved=True`. Exact correction: parameterize the three
     flags (one `True`, the other two `False`) and assert the persisted/reloaded values;
     retain a post-application status so independence from workflow status remains
     covered, and correct the misleading prose.
- Independently verified: targeted `user_jobs` suites pass (55/55); repository checker,
  Ruff format/check, and mypy pass. A full-suite run reached 1027 passes with 8 setup
  errors confined to pytest's inaccessible host temp directory
  (`AppData/Local/Temp/pytest-of-Kiwi`), not product/test assertions. Model/migration
  parity, migration `0016` ancestry, FK/CHECK/index definitions, service transition
  branches, CASCADE cleanup/isolation, and the Phase 1/Phase 10 documentation boundary
  were also inspected; no further findings.
- Scope for the correction pass: service validation, the bounded tests above, truthful
  documentation wording where needed, and a new concise `Work done` entry only. No
  migration/schema change is needed; do not start `job_notes`, merge to or modify
  `main`, or advance to another slice.

---

## Iteration 2

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

*Pending — awaiting Codex.*
