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

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Authorized slice: Phase 2's
  second vertical slice, Tier-1 `evidence_mismatch` conflict persistence — Class H
  (identity/concurrency risk per PHASE_RISK_CHECKLIST.md's Phase 2 primary risks).
  Base `main`@`10aa747` -> branch
  `phase-2/evidence-mismatch-conflict-persistence`. Implements the twice-revised,
  fully negotiated proposal (replacing `DeferredIdentityConflictError` with real
  ADR-0007 quarantine persistence), including both of the final round's corrections
  (raw-association `raw_content_hash`/`fetched_at` checks; a private, patchable
  rollback-test seam replacing the earlier, structurally-impossible "inject after
  return" design) plus this pass's four additional binding clarifications
  (quarantine still advances parent `Job.last_seen_at`; rollback proof extended to
  the parent `Job`; a monotonic-timestamp regression for the conflict path; the
  secret-leakage test's secret placed in a `normalize_url()`-surviving query
  parameter).
- Outcome:
  1. **`persistence.py::persist_posting(engine, natural_key, job, observed_at,
     raw_id) -> UpsertOutcome`** — new transaction-owning entry point.
     `UpsertOutcome.inserted: bool` -> `.kind: UpsertKind`
     (`INSERTED`/`UPDATED`/`QUARANTINED`) plus `conflict_id: uuid.UUID | None`.
     `upsert_job_occurrence()` keeps its original signature and now always
     advances observational fields (occurrence `last_seen_at`/`is_active`, parent
     `Job.last_seen_at`) on a found match, returning `kind=QUARANTINED` instead of
     raising when the normalized canonical URL disagrees — it never touches
     `RawJobIngestion`/`IdentityConflict` itself.
  2. **Raw-association validation** (`_validate_raw_association`, under a
     `SELECT ... FOR UPDATE` lock, before any mutation): existence,
     `processing_status=='fetched'`, `job_occurrence_id IS NULL`, provider/source,
     `source_identifier`, `raw_content_hash == canonical_json_hash(job.raw)`,
     `fetched_at == job.discovered_at`. The last two close the URL-fallback-domain
     gap where `source_identifier` alone is `NULL` for every such posting from a
     given provider/source. `InvalidRawIngestionAssociationError` raised before any
     occurrence/conflict/raw mutation; this also structurally enforces "one
     conflict per distinct new `RawJobIngestion`" (a consumed raw row fails the
     `processing_status` check on any retry).
  3. **Quarantine transaction**: on `QUARANTINED`, inserts one `IdentityConflict`
     (`conflict_type='evidence_mismatch'`, `existing_value`/`incoming_value` =
     `{"canonical_url_normalized": ...}`, `status='open'`) and reroutes the raw row
     to `processing_status='identity_conflict'` linked to the *existing* occurrence
     — never a second `job_occurrences` row. `pipeline.py` buckets a quarantined
     outcome as `jobs_updated`, sets `completed_with_errors`, and logs one sanitized
     WARNING (`ingestion_identity_conflict`: raw/conflict/occurrence ids only).
  4. **Private rollback-test seam**: `persistence._after_quarantine_flush()`, a
     no-op called after the occurrence+parent-Job+conflict+raw writes are flushed
     but before `persist_posting`'s own `session.begin()` block exits — not a
     public parameter. Monkeypatched to raise in
     `test_quarantine_rollback_discards_all_effects_and_marks_run_failed`, which
     proves all four effects roll back together and the run/attempt report the
     exact counters from the one posting that had already, separately, committed.
  5. Exact three-run counter/table matrix (`test_three_run_conflict_matrix`):
     Run 1 inserts cleanly; Run 2 quarantines a conflicting re-observation
     alongside one unrelated valid posting; Run 3 quarantines the same dispute
     again via a distinct new ingestion (a second, independent conflict — not a
     duplicate). Cumulative `IdentityConflict` count: 0 -> 1 -> 2. A `UserJob`
     created after Run 1 is proven byte-identical (including `updated_at`) after
     both Run 2 and Run 3.
  6. Nondeterministic-order-safe concurrency test
     (`test_concurrent_conflicting_canonical_urls_quarantine_the_loser`): two
     postings race the same absent natural key with different canonical URLs;
     assertions determine winner/loser from each task's own returned `outcome.kind`
     rather than assuming which one wins.
  7. Two adversarial raw-association tests isolate the content-hash and
     `fetched_at` checks independently in the URL-fallback domain; two
     reprocessing-guard tests (plain and quarantine-specific) prove a consumed
     `raw_id` cannot be replayed into a duplicate mutation or a second conflict.
- Files changed: `backend/app/ingestion/{persistence.py,pipeline.py}`;
  `backend/tests/fixtures/discovery/evidence_mismatch_conflicting.json` (new);
  `backend/tests/{test_ingestion_pipeline.py,test_ingestion_concurrency.py}`;
  `docs/DECISIONS/0007-identity-conflict-quarantine.md` (narrow "Phase 2
  implementation notes" addendum, no schema change); `docs/ROADMAP.md` (Phase 2
  status paragraph); this handoff. No migration — no schema changed.
- Commands run and exact results:
  - `ruff format`/`ruff format --check .` → 3 files reformatted, then clean;
    `ruff check .` → all checks passed.
  - `mypy app/` and the two edited test files → clean (one `str | None` narrowing
    fix applied in a new test).
  - Targeted (`test_ingestion_pipeline.py` + `test_ingestion_concurrency.py`) →
    **27 passed**.
  - Full suite (`pytest`) → **1156 passed** (was 1147).
  - `alembic heads` → `0017 (head)`, unchanged; no migration in this diff.
  - Development database reconfirmed at `0006` with its original five-table shape
    both before and after this pass; `jobgoblin_test` confirmed already at `0017`.
  - `python scripts/check_repo.py` → exit 0, zero findings.
  - `git diff --check` → clean (only a benign LF/CRLF note, not a whitespace
    violation).
  - Table-count query against `jobgoblin_test` after the full suite → all
    ingestion-related tables at 0 rows; no leaked test data.
- Adversarial self-review (fresh read of the diff before this entry): found and
  fixed **one High** bug during the initial targeted test run — a new test's
  `make_user_job(..., status="applied")` call omitted `applied_at`, tripping
  `user_jobs`' `status_changed_at`/`applied_at` consistency `CHECK` mid-test. The
  crash propagated past the test's `job_ids`/`raw_ingestion_ids` collection points,
  so `finally`'s cleanup ran with incomplete id lists and left one orphaned
  `Job`/`JobOccurrence` and one orphaned `normalized` `RawJobIngestion` row in
  `jobgoblin_test`, which then made an unrelated concurrency-test assertion and a
  raw-row-count assertion in a later test fail (both symptoms of the same root
  leak, not independent bugs). Fixed by adding `applied_at=t1`; purged the leaked
  rows by hand and reran the full targeted suite clean. Also hardened the shared
  `_cleanup()` helper (used by every test in `test_ingestion_pipeline.py`) to
  delete `IdentityConflict` rows referencing the raw ids being cleaned up before
  deleting those raw rows — previously absent, since no test before this slice
  ever created a real, committed `IdentityConflict` row; without this fix, every
  conflict-producing test would have permanently accumulated an orphaned
  `identity_conflicts` row (both FKs `SET NULL`, never cascade-deleted) in the
  shared disposable test database.
- Deviations/known limitations: none beyond the natural-key spine's own
  already-documented residual limits. The raw-association hash/timestamp checks
  cannot distinguish two postings that are byte-identical in both `raw` content
  and `discovered_at` — an accepted, disclosed degenerate case, since the actual
  pipeline call site always pairs `job`/`raw_id` in lockstep and never needs this
  distinction in practice. `ambiguous_match`, identity tiers 2–4, `QueryPlanner`,
  `ProviderRegistry`, multi-source partial-success handling, live providers, Phase
  3 normalization, API routes, and scheduling remain explicitly out of scope.
  `main` untouched throughout.
- STOP — awaiting Codex review. Do not begin `ambiguous_match`, identity tiers
  2–4, `QueryPlanner`, `ProviderRegistry`, multi-source handling, live providers,
  normalization, APIs, scheduling, or modify/merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Diff reviewed: `10aa747..4684a4b` on
  `phase-2/evidence-mismatch-conflict-persistence`. Review type: independent
  Class H implementation review against the approved twice-revised proposal and
  its four final binding clarifications.
- Verification reproduced: `scripts/check_repo.py` exit 0; Ruff format/check
  clean; mypy clean across `app tests scripts`; focused ingestion/concurrency
  suite **27 passed**; full suite **1156 passed** using a workspace-local
  `--basetemp` (the first run's eight setup errors were solely the already-known
  Windows host-temp permission problem); `alembic check` reports no drift;
  `jobgoblin_test` is at `0017 (head)` and development `jobgoblin` remains at
  `0006`; working tree clean after verification.
- Findings:
  1. **High — `persist_posting()` does not prove the supplied `NaturalKey`
     belongs to the supplied `DiscoveredJob`.** `_validate_raw_association()`
     compares raw provider/source/source-identifier to `natural_key`, and raw
     hash/time to `job`, but never compares `natural_key` to `job`. A caller can
     therefore combine a genuine raw/job pair with a different posting's key.
     The found branch can mutate/quarantine the wrong occurrence; the insert
     branch can acquire an advisory lock for one key while inserting an
     occurrence whose provider/source fields come from another, defeating the
     concurrency guarantee. Re-resolve the expected natural key from `job` and
     require exact equality before mutation (or remove the independently
     supplied key); add an adversarial mismatched-key test proving no rows mutate.
  2. **Medium — the advertised exact three-run matrix is only partially
     asserted.** `test_three_run_conflict_matrix` does not check cumulative
     `CollectionRun`/attempt-row totals after each run, does not prove every
     run's attempt status/counters (only Run 2's partial counters), and calls the
     `UserJob` byte-identical while snapshotting only `status` and `updated_at`.
     Complete the promised run/attempt matrix and compare every persisted
     `UserJob` column (or narrow the claim, but the approved matrix requires the
     complete proof). Also assert quarantined raw rows keep `error_message IS
     NULL` as the approved decision states.
  3. **Low — ADR/roadmap wording disagrees with the executable behavior and
     branch state.** ADR 0007 still says the implemented walkthrough uses
     `last_seen_at = now()` and updates applicant-count fields, while this slice
     correctly uses injected `observed_at` and currently has no applicant-count
     input; its new addendum nevertheless says the walkthrough is implemented
     “verbatim.” Correct the walkthrough to name the actual current fields
     (occurrence `last_seen_at`/`is_active`, parent `Job.last_seen_at`) and note
     applicant-count observation is deferred until represented by
     `DiscoveredJob`. `ROADMAP.md` also says both Phase 2 slices are “merged so
     far,” although this slice is still only on its feature branch; use wording
     accurate both before and after review/merge.
- **Verdict: changes requested.** The quarantine transaction, rollback seam,
  nondeterministic concurrency assertions, sanitized logging, monotonic parent/
  occurrence observation updates, and distinct-ingestion idempotency are sound;
  corrections are bounded to the three findings above. Rerun Ruff/mypy, the
  focused suites, full pytest, repository checker, and `alembic check`; append a
  new `Work done` entry and stop for re-review. No migration is expected. Do not
  begin another Phase 2 slice or modify/merge `main`.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/evidence-mismatch-conflict-persistence` for the three findings in
  review commit `8c1388e` (`10aa747..4684a4b`). Base `4684a4b`.
- Outcome, addressing each finding exactly:
  1. **High — `persist_posting()` now proves `natural_key` belongs to `job`.**
     `_validate_raw_association()` re-resolves `job`'s own identity via
     `resolve_identity(job)` and requires exact equality with the supplied
     `natural_key`, run last among the pre-mutation checks (existence, status,
     linkage, provider/source, `source_identifier`, `raw_content_hash`,
     `fetched_at`, then this). A `natural_key` differing only in a forged
     `source_tenant_id` (or, structurally, a forged normalized URL) now fails
     closed before any mutation, since neither is a column `RawJobIngestion`
     itself stores to compare against. Added
     `test_persist_posting_rejects_natural_key_that_does_not_match_the_job`: a
     genuinely valid raw/job pair (`clean_tenant_scoped`, matching hash and
     `fetched_at`) combined with a `NaturalKey` differing only by
     `tenant_id="evil-corp"` — proves the raw row stays `fetched`/unlinked, no
     `Job`/`JobOccurrence` is created, and no `IdentityConflict` references
     that raw id.
  2. **Medium — the three-run matrix now asserts everything the proposal
     promised.** `test_three_run_conflict_matrix` now checks, after every one
     of the three runs: cumulative `CollectionRun` and
     `CollectionRunProviderAttempt` row totals (1/2/3 each); each run's own
     attempt row `status` plus exact `jobs_discovered`/`jobs_inserted`/
     `jobs_updated` (not only Run 2's); every persisted `UserJob` column
     (via a `_user_job_snapshot()` helper covering all ten non-`id` columns,
     not just `status`/`updated_at`) unchanged after Run 2 and Run 3; and that
     every quarantined `RawJobIngestion` row (one after Run 2, two after
     Run 3) has `error_message IS NULL`. Added `_collection_run_count()`/
     `_attempt_count()` helpers alongside the existing per-table counters.
  3. **Low — ADR 0007 and ROADMAP.md now match the executable behavior and
     branch state.** ADR 0007's transaction walkthrough (step 5a) and its
     "Decision" summary bullet now both name the actual implemented fields —
     `last_seen_at = max(existing, observed_at)` (the injected business
     timestamp, never `now()`) and `is_active` on the occurrence, plus the
     parent `Job.last_seen_at` the same way — and state explicitly that
     `applicant_count`/`applicant_count_text` are deferred because
     `DiscoveredJob` does not currently represent either field. The
     "Raw-ingestion association" implementation note was extended to describe
     the new `natural_key`-vs-`job` check. `ROADMAP.md`'s Phase 2 paragraph
     now says one slice (the natural-key spine) is merged into `main` and
     names this slice's own feature branch explicitly as **not yet merged**.
- Files changed: `backend/app/ingestion/persistence.py`;
  `backend/tests/test_ingestion_pipeline.py`;
  `docs/DECISIONS/0007-identity-conflict-quarantine.md`; `docs/ROADMAP.md`;
  this handoff.
- Commands run and exact results:
  - `ruff format .` → 1 file reformatted, then clean; `ruff check .` → all
    checks passed.
  - `mypy app tests scripts` → clean, 73 source files.
  - Focused (`test_ingestion_pipeline.py` + `test_ingestion_concurrency.py`) →
    **28 passed** (was 27; +1 new adversarial test).
  - Full suite with a workspace-local `--basetemp` → **1157 passed** (was
    1156).
  - `alembic check` (against `jobgoblin_test`) → `No new upgrade operations
    detected`; `alembic heads` → `0017 (head)`, unchanged; no migration in
    this diff.
  - Development database reconfirmed at `0006` with its original five-table
    shape both before and after this pass; `jobgoblin_test` confirmed already
    at `0017`.
  - `python scripts/check_repo.py` → exit 0, zero findings.
  - `git diff --check` → clean (only benign LF/CRLF notices, not whitespace
    violations).
  - Table-count queries against `jobgoblin_test` after both the focused and
    full runs → all ingestion-related tables at 0 rows; no leaked test data.
- Adversarial self-review: traced every existing test that constructs a
  `natural_key`/`job` pair and passes it to `persist_posting`/
  `upsert_job_occurrence` to confirm the new re-resolution check could not
  spuriously reject a legitimate case — every existing test either derives
  `natural_key` directly from the same `job` via `resolve_identity()`, or
  varies only fields that do not participate in natural-key resolution
  (`canonical_url`, `discovered_at` where isolating the hash/`fetched_at`
  checks specifically). Confirmed empirically: all pre-existing tests in both
  edited files still pass unchanged. Also confirmed the new adversarial test
  actually isolates the new check (not an existing one) by checking that
  `raw.source_identifier` still agrees with the forged key's `job_id` — only
  `tenant_id` differs, which no other check compares.
- Deviations/known limitations: none beyond those already recorded in
  Iteration 1. `ambiguous_match`, identity tiers 2–4, `QueryPlanner`,
  `ProviderRegistry`, multi-source partial-success handling, live providers,
  Phase 3 normalization, API routes, and scheduling remain explicitly out of
  scope. `main` untouched throughout.
- STOP — awaiting Codex re-review. Do not begin `ambiguous_match`, identity
  tiers 2–4, `QueryPlanner`, `ProviderRegistry`, multi-source handling, live
  providers, normalization, APIs, scheduling, or modify/merge `main`.

### Work review

_Pending._

---
