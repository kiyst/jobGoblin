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
`user_jobs` correction pass, its approval, and merge record) was removed rather than
kept alongside a third entry, since it was already merged and is no longer pending.
Nothing below was rewritten — only renumbered.*

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

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `93a4ee5..1287b5e`
  (`phase-1/job-notes`). Verdict: **changes requested**.
- Findings, highest severity first:
  1. **Low — the approved internal-whitespace-preservation behavior is asserted in the
     handoff but not tested.** `test_body_trimmed_case_preserved_on_orm_path` proves
     outer ordinary spaces are removed and letter case survives, but its body contains
     no internal repeated whitespace, tab, LF, or CR. The binding decision explicitly
     says internal whitespace is preserved, which matters for multiline user notes.
     Exact correction: add one ORM persistence/reload regression containing outer
     covered whitespace plus internal repeated spaces, tab, LF, and CR/LF, and assert
     that only the outer four-character set is removed while the internal content and
     case remain byte-for-byte unchanged. Do not change the validator or schema unless
     that test exposes a mismatch.
  2. **Low — the timestamp-default “independence” coverage is overclaimed again.**
     `test_defaults_are_independent_across_multiple_rows` asserts only the two explicit
     body values and application-generated UUIDs; it never reads either row's
     `created_at` or `updated_at`. The `Work done` file summary nevertheless groups it
     under timestamp “defaults/independence.” Exact correction: rename/reframe that
     test to state what it actually proves (independent application-generated IDs and
     row values), or fold those assertions into the multiple-notes test; in the new
     `Work done`, describe timestamp coverage only as server defaults present,
     UTC-awareness, and `updated_at` advancing on commit. Do not edit the prior
     append-only entry solely to repair its historical wording.
- Independently inspected and found correct: model/migration parity; migration `0017`
  ancestry; required trim/non-empty database backstop; absence of a redundant
  `user_id` and `UNIQUE`; `(user_job_id, created_at DESC)` index definition; direct,
  user-level, and job-level CASCADE test structure and cleanup isolation; model
  registration; Phase 1/Phase 10 boundary; the corrected two-level-CASCADE precedent;
  and all related durable documentation. Repository checker, `git diff --check`, Ruff
  format/check, and mypy (**51 source files**) pass.
- Reviewer test limitation: PostgreSQL was not running/reachable during this review,
  so the attempted targeted run ended only in `ConnectionRefusedError` setup failures;
  no product assertion executed and this is not an additional finding. Claude's
  recorded pre-push evidence remains 17 targeted and 1064 full-suite tests passing,
  twice including after a fresh `base -> head` rebuild.
- Scope for the correction pass: the two bounded test/claim corrections above and a
  concise new `Work done` entry only. No model, migration, schema, product-document,
  Phase 2, Phase 10, or `main` change is authorized. Rerun proportionate static,
  targeted, and full-suite verification once PostgreSQL is reachable, then stop for
  re-review.

---

## Iteration 2

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
  - The former “defaults independence” test is accurately renamed and documented as
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
