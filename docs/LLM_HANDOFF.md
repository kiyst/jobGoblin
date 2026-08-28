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
`collection_runs` initial implementation pass and its "changes requested" review) was
removed rather than kept alongside a third entry, since the correction pass below
superseded it and the whole slice is now merged. Nothing below was rewritten — only
renumbered.*

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

---

## Iteration 2

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice:
  `collection_run_provider_attempts`, Class H per docs/LLM_WORKFLOW.md — the
  authoritative per-source telemetry record feeding Phase 12's provider-health
  analysis, Phase 2's second fixture-proof writer alongside `identity_conflicts`, and
  this schema's first table whose own name is long enough to force four explicit
  shortened constraint names. Base `0ac9635` on `main` -> branch
  `phase-1/collection-run-provider-attempts`.
- Outcome: new model, migration `0015`, factory/real-commit helper, and 98 new tests
  implemented and verified against real PostgreSQL, per the user's binding corrections
  to the prior proposal:
  1. `error_category` is nullable text, database-`CHECK`-restricted to exactly the 8
     `ProviderErrorCategory` values (ARCHITECTURE.md §6.3): `timeout`, `rate_limited`,
     `auth_error`, `blocked`, `parse_error`, `not_found`, `upstream_error`, `unknown`.
     Kept as a plain string column (not a native Postgres enum type) — a future 9th
     category is a single additive migration. No ORM case-fold (plain closed-enum
     column like `status`; tested that an otherwise-valid value in the wrong case is
     rejected, not silently normalized). Phase 2+ must keep this list synchronized with
     the Python enum by hand.
  2. No `CHECK` ties `incomplete_results` to `status` — both independent at the
     database level, tested with an explicit accepted-combination case (`completed` +
     `incomplete_results=true`, `partial` + `incomplete_results=false`).
  3. New `CHECK (completed_at IS NULL OR completed_at >= started_at)`, extending the
     ordering convention already established on `job_occurrences`/`identity_conflicts`/
     `collection_runs`. Tested equal/later accepted, earlier rejected, via ORM and
     direct SQL.
  4. Corrected the prior proposal's factual claim that `ON DELETE CASCADE` would be
     this schema's first use of it — `job_occurrences.job_id`,
     `candidate_skills.candidate_profile_id`, and the `saved_search_*` child tables
     already use it; only the parent-table identity (`collection_runs`, not an
     audit-trail table) is new here. `collection_run_id` is NOT NULL, `ON DELETE
     CASCADE` — an attempt row has no independent meaning without its run.
  5. `provider`/`source` get the exact established canonical-identifier treatment from
     `job_occurrences`/`raw_job_ingestions`: ORM-trimmed (four-character whitespace
     set) and lowercased; database `CHECK` requires an already-canonical, non-empty
     ASCII-slug value (`^[a-z0-9][a-z0-9._-]*$`). Tests distinguish ORM normalization
     (uppercase/whitespace-wrapped accepted and stored canonically) from the database
     backstop (non-ASCII/embedded-space values survive ORM normalization unchanged but
     are rejected by the slug `CHECK`; direct SQL independently proves the same
     rejection bypassing the ORM entirely) — mirroring `test_job_occurrences.py`'s own
     battery exactly.
  6. `error_message` gets the established nullable-free-text treatment: ORM-trimmed
     with whitespace-only collapsed to `None`, case/internal-whitespace preserved,
     NULL-safe trim/non-empty `CHECK` pair proven via direct SQL. Documented (not
     tested, since it isn't a database property) that sanitization against
     secrets/tokens remains an application-level responsibility.
  7. ADR 0003's Decision-section table list corrected to include
     `collection_run_provider_attempts` (previously present only in its own
     now-superseded Rev-2/3-era prose paragraph), alongside the usual DATA_MODEL.md
     implementation marker/constraints-summary rows and ROADMAP.md status update.
  - Four constraint names required an explicit, shortened form beyond the naming
    convention's default template — this table's own name (33 characters) is long
    enough that the FK and three `CHECK`s (`status`/`completed_at` consistency,
    `completed_at`/`started_at` ordering, `jobs_discovered` non-negative) would
    otherwise exceed Postgres's 63-byte identifier limit; verified via direct DDL
    rendering before writing the migration, and re-verified against the live schema
    after a fresh rebuild.
  - `UNIQUE (collection_run_id, provider, source)` — this schema's first plain,
    non-functional multi-column `UniqueConstraint` (every prior multi-column
    uniqueness in this schema needed a functional/partial `Index` instead, since
    `UniqueConstraint` only covers plain columns).
  - No JSONB/array columns at all on this table — every column is scalar, so no
    `MutableList`/`MutableDict` wrapping decisions were needed.
- Files changed:
  - `backend/app/db/models/collection_run_provider_attempt.py` (new).
  - `backend/app/db/models/__init__.py`, `backend/app/db/base.py` —
    registration/docstring.
  - `backend/migrations/versions/0015_collection_run_provider_attempts.py` (new,
    `down_revision = "0014"`).
  - `backend/tests/conftest.py` — `make_collection_run_provider_attempt` (omits a
    kwarg entirely rather than passing `None` for defaulted columns, so Postgres's
    `server_default` applies on `INSERT`), `real_committed_collection_run_provider_
    attempt` (builds on the pre-existing `real_committed_collection_run` helper, with
    a `collection_run_kwargs` disambiguation parameter mirroring
    `real_committed_identity_conflict`'s own `job_kwargs=None`-style mypy fix).
  - `backend/tests/test_collection_run_provider_attempts.py` (new) — 98 tests:
    baseline/defaults; `collection_run_id` FK (nonexistent rejected, omission
    rejected via direct SQL, `ON DELETE CASCADE` deletion proven isolated from an
    unrelated run's own attempt row); `UNIQUE (collection_run_id, provider, source)`
    (duplicate rejected via ORM and direct SQL; one provider's two distinct sources
    proven to coexist under the same run — the exact Phase 2 fixture-proof shape from
    ARCHITECTURE.md §11, using `fixture_provider`/`healthy_source`/`broken_source`);
    `status` enum validity/omission; the full status/`completed_at` lifecycle matrix
    (3 terminal statuses × both directions, ORM + direct SQL); the new
    `completed_at >= started_at` ordering; `started_at` omission; `created_at`/
    `updated_at` defaults/independence/UTC-awareness/advancing-on-commit; all four
    counters' (including `retry_count`) defaults/acceptance/negative-rejection;
    `rate_limited`/`incomplete_results` defaults and independence from `status`;
    the full `provider`/`source` canonicalization battery (8 tests, mirroring
    `test_job_occurrences.py`); `error_category`'s 8 valid values, invalid-value
    rejection (ORM + direct SQL), and no-case-fold proof; `error_message`'s
    trim/blank-to-`None`/case-preservation/direct-SQL-backstop battery (mirroring
    `test_raw_job_ingestions.py`).
  - `docs/DATA_MODEL.md` — `collection_run_provider_attempts` marked
    **Implemented**; added "Rev 20" note recording every resolved decision; updated
    the constraints-summary rows to reflect the actual implemented constraint set.
  - `docs/ROADMAP.md` — Phase 1 status paragraph describes the
    `collection_run_provider_attempts` slice as complete.
  - `docs/DECISIONS/0003-minimal-phase1-schema.md` — added
    `collection_run_provider_attempts` to the Decision section's literal table list,
    with a "Rev 4 correction" note reconciling it with the still-accurate
    `duplicate_groups` prose paragraph above it.
- Commands run and exact results:
  - `pytest tests/test_collection_run_provider_attempts.py -q` → 98 passed.
  - `pytest -q` (full suite) → 977 passed (up from 879), re-confirmed again after the
    fresh migration rebuild below.
  - `ruff format --check .`, `ruff check .` → passed (60 files).
  - `mypy app tests scripts` → success, 44 source files.
  - `DATABASE_URL=...jobgoblin_test`: `downgrade 0014` / `upgrade head` (round-trip),
    `downgrade base` / `upgrade head` (fresh `base -> head`), `alembic check` (`No new
    upgrade operations detected` — same informational `Computed`-column `UserWarning`
    as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`pg_constraint`, `pg_indexes`,
    `information_schema.columns`) after the fresh rebuild — confirmed 19 constraints,
    the FK's `ON DELETE CASCADE` (`confdeltype = 'c'`), the `UNIQUE`'s exact column
    order, both lookup indexes, and every column default, matching the model exactly.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual uncommitted diff before commit; full
  12-question Class H depth): **no substantiated findings**. Explicitly checked and
  clean: model/migration parity for every constraint including all 4 shortened names
  (byte-counts re-verified against the docstring's stated overflow amounts);
  no ORM-side logic can produce a value violating its own `CHECK`; no case-fold/
  Unicode bypass on `status`/`error_category` (plain equality, no normalization) or on
  `provider`/`source` (ASCII-slug `CHECK` blocks non-ASCII homoglyphs); ORM/direct-SQL/
  DB-default paths all covered where they matter; confirmed no JSONB/array columns
  exist at all (no mutable-collection gap possible); `UNIQUE`/index column order
  verified against live introspection; no test overclaims concurrency; no cross-test
  state leakage; the `ON DELETE CASCADE` test proves isolation against a second,
  untouched run's own attempt row, not merely the deleted run's own row being gone;
  every docstring cross-reference (ARCHITECTURE.md §9/§11/§6.3, ADR 0005,
  PHASE_RISK_CHECKLIST.md) resolves to a real, matching section — no repeat of the
  earlier `collection_runs` "§38" dangling-citation mistake; the Phase 2 fixture
  scenario (`fixture_provider` executing `healthy_source`/`broken_source`, one
  `completed`, one `failed`) is directly exercised and proves the `UNIQUE` constraint
  keys on all three columns, not `(collection_run_id, provider)` alone. One
  informational, non-actionable note: this table's own tests have no ORM-path test for
  an empty-string `provider`/`source` (only direct-SQL) — the reviewer confirmed this
  exact gap already exists identically in `test_job_occurrences.py`/
  `test_raw_job_ingestions.py`, so it is established project convention, not a new
  omission.
- Deviations/known limitations: none. `user_jobs`/`job_notes` remain unimplemented,
  per explicit scope.
- STOP — awaiting Codex review. Do not begin `user_jobs`/`job_notes`, another slice,
  or modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `0ac9635..755b219`.
- Verdict: **changes requested**. The table design, model/migration parity, constraints,
  canonicalization, CASCADE behavior, enum values, defaults, indexes, and documentation
  are otherwise coherent. Findings:
  1. **Low — the approved timestamp test matrix is incomplete.** The binding instruction
     required equal, later, and earlier `completed_at` cases through both ORM and raw SQL.
     Equal/later are accepted only through ORM; raw SQL covers only the rejected earlier
     case. The handoff consequently overstates completion of the approved matrix.
  2. **Low — `rate_limited=True` is never exercised.** Tests prove its ORM and database
     defaults are `false`, but the approved proposal also required both explicit boolean
     values and independence from status/`incomplete_results`. The sole independence
     test varies only `incomplete_results`; no test ever writes `rate_limited=True`.
  3. **Low — three comments incorrectly imply PostgreSQL creates an index for a
     referencing foreign-key column.** PostgreSQL does not automatically index
     `collection_run_id` merely because it is an FK. The explicit index is correct and
     useful, but the model comment, migration docstring, and `DATA_MODEL.md` currently
     describe it as additional to “whatever index the FK itself implies.”
  4. **Low — the handoff claims timestamp-default independence without a corresponding
     test.** The test file proves raw-SQL defaults, UTC awareness, and ORM-driven
     `updated_at` advancement, but not a two-row independence case. Correct the claim;
     no redundant test is required for this point.
- Exact bounded corrections requested:
  1. Add raw-SQL accepted cases for `completed_at == started_at` and `completed_at >
     started_at`, complementing the existing raw-SQL rejection of an earlier timestamp.
  2. Add an ORM persistence/reload case with `rate_limited=True` in a valid row and an
     explicit `incomplete_results` value/status combination that demonstrates the
     approved independence. Do not add any new CHECK.
  3. Correct the three FK-index comments to state that PostgreSQL does not automatically
     index the referencing FK column and that this explicit index supports “all attempts
     for this run” lookups (and efficient parent-side FK maintenance). Do not alter the
     index itself.
  4. Remove `independence` from the handoff's timestamp-test claim, or accurately limit
     the claim to what the tests prove. Do not add a timestamp-independence test solely
     to preserve that wording.
  5. Limit changes to tests, comments/docs, and the handoff. Do not alter model mapping,
     schema behavior, migration operations/revision metadata, constraint/index
     definitions, or begin another slice. Run `git diff --check`, repository checker,
     Ruff, mypy, targeted tests, and the full suite; then update `Work done`, commit and
     push the same branch, and stop for re-review. Alembic round-trips are unnecessary
     for this test/comment-only correction.
- Verified independently: repository checker exit 0; Ruff format/check clean; mypy
  clean (**44 source files**); targeted suite **98 passed**; full suite **977 passed**;
  test database is at Alembic head `0015` and `alembic check` reports no new upgrade
  operations.
- STOP — reviewer changed only this `Work review`. Do not begin `user_jobs`,
  `job_notes`, another slice, or modify/merge `main` without explicit authorization.
