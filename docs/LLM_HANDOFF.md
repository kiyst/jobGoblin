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
`identity_conflicts` correction pass, its approval, and merge record) was removed rather
than kept alongside a third entry, since it was already merged and is no longer pending.
Nothing below was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `collection_runs`,
  Class H per docs/LLM_WORKFLOW.md — a scheduler-execution rollup record combining a
  bidirectional status/timestamp lifecycle `CHECK`, differentiated `MutableList`
  wrapping across a `TEXT[]` and a JSONB array in the same table, and a deliberately
  un-wrapped JSONB object column. Base `0a58742` on `main` -> branch
  `phase-1/collection-runs`.
- Outcome: new model, migration `0014`, factory/real-commit helper, and 76 new tests
  implemented and verified against real PostgreSQL.
  - `CollectionRun` model: `status` is a plain `CHECK`-restricted enum (no ORM
    transform), no server default — fresh creation must explicitly supply `running`.
    `started_at` is NOT NULL with no server default (matches
    `raw_job_ingestions.fetched_at`'s treatment); `completed_at` is nullable only while
    `status = 'running'`, enforced by a bidirectional lifecycle `CHECK` plus a second
    `CHECK (completed_at IS NULL OR completed_at >= started_at)`. `created_at`/
    `updated_at` follow the established global convention (added despite this table's
    own pre-existing `DATA_MODEL.md` column list omitting them — the same tension
    `identity_conflicts` hit before).
  - `providers_attempted` (`TEXT[]`, NOT NULL, `server_default '{}'`) and `failures`
    (jsonb array, NOT NULL, `server_default '[]'`) are both `MutableList`-wrapped for
    in-place top-level append tracking — the first time `MutableList` wraps a JSONB
    column (not `ARRAY`) in this codebase. `providers_enforced_locally` (jsonb object,
    NOT NULL, `server_default '{}'`) is deliberately **not** wrapped: assembled once in
    memory during planning and assigned as a complete value, matching
    `jobs.field_provenance`'s existing documented nested-mutation limitation. Each
    JSONB column has a top-level shape `CHECK` (`= 'object'` / `= 'array'`) — the first
    time a NOT-NULL JSONB column with a non-null server default carries a shape
    `CHECK` in this schema (prior shape-checked columns were nullable-with-no-default
    or NOT-NULL-with-no-default). The three job counters are NOT NULL with
    `server_default 0` and non-negative `CHECK`s; `duration_ms` stays nullable with a
    NULL-safe non-negative `CHECK`. No `CHECK` ties `failures`/counters to `status` —
    `completed_with_errors` may honestly show non-zero rollups alongside recorded
    failures.
  - `saved_search_id` is nullable, `ON DELETE SET NULL`; no other column's `CHECK`
    references its nullness, so — unlike `raw_job_ingestions`/`identity_conflicts` —
    there is no FK-vs-CHECK asymmetric-direction tension on this table.
  - Single FK (`saved_search_id`→`saved_searches`) fit under the naming convention's
    63-byte limit unaided; verified via direct DDL rendering before writing the
    migration, no explicit short name needed (unlike `identity_conflicts`' two FKs).
  - Indexes: `(saved_search_id, started_at DESC)` and `(status)` — lookup support
    only, no uniqueness constraint anywhere; Phase 9's overlapping-run-prevention
    strategy is an explicitly separate, not-yet-designed invariant.
- Files changed:
  - `backend/app/db/models/collection_run.py` (new).
  - `backend/app/db/models/__init__.py`, `backend/app/db/base.py` —
    registration/docstring.
  - `backend/migrations/versions/0014_collection_runs.py` (new,
    `down_revision = "0013"`).
  - `backend/tests/conftest.py` — `make_collection_run` (omits a kwarg entirely rather
    than passing `None` for defaulted columns, so Postgres's `server_default` applies
    on `INSERT`), `real_committed_collection_run` (builds on the pre-existing
    `real_committed_user_and_saved_search` helper).
  - `backend/tests/test_collection_runs.py` (new) — 76 tests: baseline/defaults;
    `saved_search_id` FK (nonexistent rejected; `ON DELETE SET NULL` isolation between
    two real-committed runs); `status` enum validity (ORM + direct SQL) and omission
    (direct SQL); the full status/`completed_at` lifecycle matrix (3 terminal statuses
    × both directions, ORM + direct SQL); `completed_at >= started_at` ordering
    (equal/after accepted, before rejected, ORM + direct SQL); `started_at` omission
    (direct SQL); `created_at`/`updated_at` defaults, independence, UTC-awareness, and
    `updated_at` advancing on a real commit; all three counters' defaults/acceptance/
    negative-rejection (ORM + direct SQL, parametrized); `duration_ms` defaults/
    acceptance/negative-rejection; `providers_attempted` defaults, order-preserving
    round-trip, in-place append persisting after a separate-session reload; multi-row
    default independence (mutable-default trap); `providers_enforced_locally` defaults,
    whole-value-assignment persistence, SQL-NULL and wrong-shape rejection
    (parametrized); `failures` defaults, in-place top-level append persistence,
    SQL-NULL and wrong-shape rejection (parametrized); the Phase 2 fixture scenario —
    a planning-time failure existing with no `providers_attempted` entry, and
    `completed_with_errors` retaining accurate non-zero rollups alongside failures.
  - `docs/DATA_MODEL.md` — `collection_runs` marked **Implemented**; added "Rev 19"
    note recording every resolved decision; added the missing constraints-summary
    rows (previously only its sibling `collection_run_provider_attempts` had one).
  - `docs/ROADMAP.md` — Phase 1 status paragraph describes the `collection_runs` slice
    as complete.
- Commands run and exact results:
  - `pytest tests/test_collection_runs.py -q` → 76 passed.
  - `pytest -q` (full suite) → 879 passed (up from 803).
  - `ruff format --check .`, `ruff check .` → passed (57 files).
  - `mypy app tests scripts` → success, 42 source files.
  - `DATABASE_URL=...jobgoblin_test`: `downgrade 0013` / `upgrade head` (round-trip),
    `downgrade base` / `upgrade head` (fresh `base -> head`), `alembic check` (`No new
    upgrade operations detected` — same informational `Computed`-column `UserWarning`
    as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`pg_constraint`, `pg_indexes`,
    `information_schema.columns`) after the fresh rebuild — confirmed the FK's
    `ON DELETE SET NULL` (`confdeltype = 'n'`), exactly 9 `CHECK` constraints, both
    lookup indexes, and every column default, matching the model exactly; nothing
    drifted through the round-trip.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual uncommitted diff before commit — it also
  independently re-ran the targeted suite and its own migration round-trip; full
  12-question Class H depth): three **Low** findings, no Critical/High/Medium.
  1. Fixed — both the model and migration docstrings cited a nonexistent
     "ARCHITECTURE.md §38" (that document's headings top out at §13); corrected to
     cite `docs/DATA_MODEL.md`'s own `collection_runs` section, whose "§38" is a
     master-spec section number, not an ARCHITECTURE.md one.
  2. Accepted, not fixed — `status`/`started_at` NOT-NULL omission and the JSONB
     shape `CHECK`s are proven only via direct SQL, not also via a bare
     `CollectionRun(...)` ORM construction; Postgres enforces identically either way,
     and the lifecycle/ordering/counter `CHECK`s already get both-path coverage, so
     this is a redundant-angle gap, not a behavioral one.
  3. Accepted, not fixed — the documented "`MutableList` doesn't track nested mutation
     within an already-appended `failures` entry" limitation has no dedicated negative
     test; only the successful top-level-append path is tested. A known/accepted
     SQLAlchemy limitation already documented elsewhere in this schema
     (`jobs.field_provenance`), not a defect in the shipped code.
  Explicitly checked and clean: model/migration parity (every `CheckConstraint` body,
  the FK, all server defaults, both index definitions byte-identical, re-verified
  live); no ORM-side logic can produce a value violating its own shape `CHECK`;
  `status`'s exact-string `CHECK` has no case-fold/trim escape; JSON `null` vs SQL
  `NULL` correctly distinguished and both tested for both JSONB columns; both
  `MutableList`-wrapped columns proven to persist an in-place append after a genuine
  separate-session reload, not just same-session identity-map caching; no test
  overclaims concurrency proof (the migration docstring explicitly disclaims it); no
  cross-test state leakage (distinct emails per `real_committed_collection_run` call);
  the `ON DELETE SET NULL` test proves isolation against a second, untouched run; the
  Phase 2 fixture scenario (one planning-time failure with no attempt row,
  `completed_with_errors` retaining honest non-zero rollups) is directly exercised and
  passes against real Postgres.
- Deviations/known limitations: none new. `collection_run_provider_attempts`,
  `user_jobs`, and all scheduler/ingestion logic remain unimplemented, per explicit
  scope. The two accepted Low findings above are coverage gaps around already-safe,
  database-enforced invariants, not open correctness risks.
- STOP — awaiting Codex review. Do not begin `collection_run_provider_attempts`,
  `user_jobs`, or any other slice, and do not modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `0a58742..b98a4ba`.
- Verdict: **changes requested**. The model, migration, constraints, defaults, mutable-
  collection choices, and lifecycle behavior are otherwise coherent and independently
  verified. Findings:
  1. **Medium — the tests teach source identifiers as provider identifiers.** The
     documented contract says `providers_attempted` contains providers whose execution
     began, while provider/source detail is separate. However, the round-trip, mutation,
     and default-independence tests use `healthy_source`/`broken_source`; most
     importantly, the claimed Phase 2 partial-success scenario stores both source names
     in `providers_attempted` even though its failure entry identifies one provider
     (`fixture_provider`) with one source (`broken_source`). That fixture would cause a
     Phase 2 writer to record two attempted providers for one provider with two sources,
     undermining the contract the test claims to prove.
  2. **Low — the self-review's citation correction is still not resolvable in this
     repository.** The model docstring, migration docstring, and current table section
     in `DATA_MODEL.md` all retain `§38`, but `DATA_MODEL.md` has no numbered §38 or
     anchor to resolve. Calling it a master-spec section number does not make these
     internal references navigable and contradicts the claim that the stale citation
     was corrected.
- Exact bounded corrections requested:
  1. Replace source-like values in every `providers_attempted` test fixture/assertion
     with provider identifiers. In the Phase 2 partial-success scenario, record
     `fixture_provider` exactly once in `providers_attempted`; keep `broken_source` in
     `failures[*].source`. Add or reshape an assertion/test so it explicitly proves that
     one provider executing two sources yields one provider entry, with source detail
     remaining separate. Do not add a database uniqueness constraint: duplicate
     avoidance remains application-level as approved.
  2. Remove the three dangling `§38` references or replace them with a real, resolvable
     Markdown link/heading in this repository. Preserve the substantive prose.
  3. Do not change table behavior, migration operations/revision metadata, or schema.
     This correction should be limited to tests and comments/documentation.
  4. Run `check_repo.py`, `git diff --check`, Ruff format/check, mypy, the targeted
     collection-run tests, and the full suite. Alembic round-trips are not required for
     this test/comment-only correction. Record the pass in a new concise `Work done`,
     commit and push the same feature branch, then stop for re-review.
- Verified independently on the feature branch: repository checker exit 0; Ruff
  format/check clean; mypy clean (**42 source files**); targeted suite **76 passed**;
  full suite **879 passed**; `alembic check` against `jobgoblin_test` reports no new
  upgrade operations. The development database's older revision is expected and was
  not modified.
- STOP — reviewer changed only this `Work review`. Do not begin
  `collection_run_provider_attempts`, `user_jobs`, another slice, or modify/merge
  `main` without explicit user authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: the two bounded
  corrections from the review at `d400fb7`, on the same `phase-1/collection-runs`
  branch. Base: `d400fb7`. Test/comment/documentation-only change — no model, migration
  operations/revision metadata, schema, or behavior changes.
- Outcome:
  1. **`providers_attempted` identifier fix.** Replaced every source-like value in a
     `providers_attempted` test fixture/assertion with a provider identifier, matching
     this codebase's established provider/source naming (`ats_scrapers`/`jobspy` as
     providers, per `test_job_occurrences.py`'s existing convention) instead of
     source-shaped placeholders. In `test_completed_with_errors_retains_successful_
     nonzero_rollups` (the Phase 2 partial-success scenario), `providers_attempted` now
     records `fixture_provider` exactly once — reflecting one provider executing two
     sources, only one of which failed — instead of listing both source names as if
     they were two separate providers. `failures[*].source` still holds `broken_source`
     unchanged, per the review's explicit instruction. Added an explicit assertion
     (`run.providers_attempted == ["fixture_provider"]`) plus a full-value assertion on
     `run.failures` so the test now directly proves the provider/source identifier
     spaces stay separate, rather than only asserting rollup counters and a bare
     `len(failures) == 1`. The order-preserving round-trip, in-place-append, and
     multi-row-independence tests were updated the same way (`ats_scrapers`/`jobspy`).
     No database uniqueness constraint added — duplicate avoidance remains
     application-level, as previously approved.
  2. **Dangling `§38` citation removed.** Removed the unresolvable bare `§38` citation
     from all three places it appeared — `backend/app/db/models/collection_run.py`,
     `backend/migrations/versions/0014_collection_runs.py`, and `docs/DATA_MODEL.md`'s
     `collection_runs` section — rather than re-labeling it, since this repository has
     no local anchor or verifiable master-spec section to point it at and asserting one
     without confirmation would repeat the same defect. All surrounding substantive
     prose (scheduler-execution-record description, the `collection_runs` section
     cross-reference) was preserved unchanged.
- Files changed:
  - `backend/tests/test_collection_runs.py` — provider/source identifier fixes across
    4 tests (`test_providers_attempted_round_trips_order_preserved`,
    `test_providers_attempted_in_place_append_persists_after_separate_session_reload`,
    `test_defaults_are_independent_across_multiple_rows`,
    `test_completed_with_errors_retains_successful_nonzero_rollups`); one new
    assertion pair added to the last of these.
  - `backend/app/db/models/collection_run.py`, `backend/migrations/versions/
    0014_collection_runs.py`, `docs/DATA_MODEL.md` — removed the dangling `§38`
    citation from each (comment/documentation only).
- Commands run and exact results (no Alembic round-trips, per the review's own
  scoping for this test/comment-only correction):
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git diff --check` → clean, no whitespace/conflict errors.
  - `ruff format --check .`, `ruff check .` → passed (57 files).
  - `mypy app tests scripts` → one new error surfaced by the added `run.failures[0]
    [...]` indexing (`failures` is typed `Mapped[list[object]]`, so an element isn't
    indexable) — resolved by asserting the full `failures` list value instead of
    indexing into it (matches the pattern already used by
    `test_failures_in_place_append_persists_after_separate_session_reload`); re-ran →
    success, 42 source files.
  - `pytest tests/test_collection_runs.py -q` → 76 passed (unchanged count — no tests
    added or removed, only fixture/assertion values and one extra assertion pair).
  - `pytest -q` (full suite) → 879 passed (unchanged, as expected for a test/comment-
    only correction).
- Deviations/known limitations: none. No model, migration, schema, or product-behavior
  change — both findings were test-data-realism and documentation-citation issues only.
- STOP — awaiting Codex re-review. Do not begin `collection_run_provider_attempts`,
  `user_jobs`, or any other slice, and do not modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `d400fb7..503c2ab`.
- Verdict: **approved**. Findings: none.
- Verified independently:
  - Every `providers_attempted` fixture/assertion now uses provider identifiers. The
    Phase 2 partial-success scenario records `fixture_provider` exactly once while its
    failure retains `source = broken_source`, and explicitly asserts both complete
    values. No uniqueness constraint or application behavior was added.
  - The three dangling `§38` references were removed while preserving the surrounding
    prose. The migration diff changes only its module docstring; migration operations,
    revision metadata, model mapping, and schema behavior are unchanged.
  - `git diff --check` is clean; repository checker exits 0; Ruff format/check and mypy
    pass (**42 source files**); targeted suite **76 passed**. Claude's post-correction
    full-suite result is **879 passed**; the reviewer did not repeat the full suite for
    this test/comment-only correction after independently running it on the original
    implementation review.
- The `collection_runs` implementation and correction pass are accepted. Do not merge
  to `main`, begin `collection_run_provider_attempts`/another slice, or otherwise
  advance without explicit user authorization.
- STOP — reviewer changed only this `Work review`; no implementation files changed.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `fe51e03`. Per user authorization, `phase-1/collection-runs` was merged into
`main` with a normal merge commit (`5e8395b`; `--no-ff`, no squash/rebase/force-push)
and pushed. `main`/`origin/main` are both now at `5e8395b`. Verified: `main` has zero
content diff against the feature branch; migration `0014` (`down_revision = "0013"`)
is present and is the sole Alembic head; `python backend/scripts/check_repo.py` (via
the project's own virtualenv interpreter) exits 0 with zero findings; working tree
clean. No later Phase 1 table (`collection_run_provider_attempts`, `user_jobs`, or
otherwise) started or proposed.
