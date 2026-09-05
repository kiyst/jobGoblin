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

- Date/agent: 2026-09-05, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/orchestration` for the five bounded findings from the original
  implementation's review (that original implementation and its review are
  now rotated out of this ledger per the two-iteration rule; both remain in
  Git history at commit `63e16ef` and its review commit). Base: `63e16ef`
  plus the uncommitted review. No product code beyond the five corrections
  requested: live providers, parallelism, scheduler, API routes, Tier 4,
  Phase 3, migration, and `ProviderRegistry` production composition all
  remain untouched.
- Outcome, addressing each finding exactly:
  1. **Cancellation after `_begin_provider_attempt()` commits, before
     `current_attempt_ids` is assigned.** New `_fetch_running_attempts()`
     queries `collection_run_provider_attempts` directly for
     `status='running'` rows scoped to this run — the durable, authoritative
     source of truth the abort handler now consults *instead of* trusting
     `current_attempt_ids`/`current_state` as the sole gate. A row genuinely
     still `'running'` is always found and finalized to `'failed'`
     regardless of whether the Python variables ever got assigned.
  2. **Cancellation after `_finalize_provider_success()` commits, before
     `current_attempt_ids`/`current_state` reset to `None`.** Same
     `_fetch_running_attempts()` mechanism closes this window too: a
     provider whose rows already reached a terminal status is never
     rediscovered (its rows are no longer `'running'`), so
     `_finalize_running_attempts_aborted()` (renamed from
     `_finalize_provider_aborted`) never re-touches it. `state` is only
     "trusted" for telemetry/`failures`-merging when the durable set of
     still-running attempt ids exactly equals `current_attempt_ids`'s
     values — never merely `state is not None` — so a stale reference to an
     already-committed provider can never duplicate its `failures` entry or
     overwrite its completed attempt back to `'failed'`. The `UPDATE` itself
     repeats the `WHERE status = 'running'` guard (not just the discovery
     `SELECT`), defense-in-depth against a row turning terminal between the
     two.
  3. **A `ProviderError` on a `completed=True` source was invisible to run
     status.** Replaced `any_attempt_not_completed` (derived only from
     `resolve_attempt_status() != "completed"`) with `run_had_source_issue`,
     aggregated from each provider's own `state.possibly_incomplete` —
     mirroring `DiscoveryResult.possibly_incomplete` exactly (any source not
     completed, any incomplete results, *or* any `ProviderError` at all).
     This subsumes the narrower check it replaces and additionally catches
     the missed case: a source that stays `completed=True`/
     `incomplete_results=False` despite carrying a real `ProviderError`
     (e.g. "succeeded after a retry") now correctly forces
     `'completed_with_errors'`.
  4. **Assertion-before-ID-capture leak risk.** Audited the entire test
     file, not just the cited line ranges — every test that can produce a
     `CollectionRun`/`Job`/`RawJobIngestion` row now captures its cleanup id
     immediately after the relevant query/operation, before any assertion
     that could fail, including tests Codex's review didn't explicitly cite
     (e.g. the two-providers-succeed happy path, the `None`-skip test, both
     planning-failure/graceful-error sibling tests, both
     `providers_enforced_locally`/timestamp tests, both explicit/`NULL`
     provider-order sub-tests). The partial-progress test's block was
     restructured most substantially: all three cleanup queries (run,
     `JobOccurrence`, `RawJobIngestion`) now run as one contiguous block
     immediately after the run raises, before any of its many content
     assertions.
  5. **Deletion-race test proved a copied SQL sequence, not
     `run_saved_search()` itself.** Added a narrow, private, no-op-by-
     default keyword-only parameter to `run_saved_search()` itself,
     `_after_saved_search_locked: Callable[[], Awaitable[None]] | None =
     None`, awaited once immediately after the real `FOR SHARE` lock is
     confirmed and the row validated, inside the real initialization
     transaction. The test now calls the *real* `run_saved_search()`,
     passing a callback that starts a genuinely concurrent `DELETE` and
     waits (bounded, `asyncio.wait_for(..., timeout=...)`) for it to
     actually reach PostgreSQL and block on the real lock, before letting
     the real transaction proceed to commit — proven (below) to fail loudly
     with a foreign-key violation if the real lock is ever removed, rather
     than staying silently green.
- Files changed: `backend/app/ingestion/orchestrator.py` (all five
  corrections: `_fetch_running_attempts`, renamed
  `_finalize_running_attempts_aborted`, `run_had_source_issue`,
  `_after_saved_search_locked` seam; docstring rewritten to match),
  `backend/tests/test_orchestrator.py` (3 new regression tests; the
  deletion-race test rewritten to use the real function via the new seam;
  cleanup-ordering fixes across the file), `docs/ARCHITECTURE.md` §6.8
  (abort-mechanics and status-aggregation prose corrected to match; new
  sentence on the test-only seam), this handoff entry. No `db/models/`,
  `enabled_providers` semantics, `CollectionRun` schema, migration,
  provider-contact, or other-slice file touched.
- New tests (3): `test_cancellation_after_begin_attempt_commit_leaves_no_row_running`,
  `test_cancellation_after_success_finalization_commit_does_not_duplicate_or_overwrite`
  (both wrap the *real* `_begin_provider_attempt`/`_finalize_provider_success`
  via `monkeypatch`, let it genuinely commit, then raise `CancelledError`
  immediately after — simulating the exact commit/cancellation windows
  Codex identified, deterministically, without relying on real asyncio
  scheduling races), and
  `test_provider_error_on_completed_source_forces_completed_with_errors`
  (the exact missing case Codex named: `completed=True`,
  `incomplete_results=False`, one real `ProviderError`, successful
  sibling).
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_orchestrator.py` — all **10 steps PASS**: Ruff
  format/check, mypy (51 source files), `check_repo.py`, `git diff --check`,
  database-URL safety, real test-database reachability, **26 focused
  tests** (was 23; +3), **1493 full-suite tests** (was 1490; +3),
  temp-directory cleanup, ~121-149s across reruns. `alembic heads` confirms
  `0017` remains the sole head; `git diff --stat -- backend/migrations/` is
  empty. Dev database (`jobgoblin`) confirmed unchanged at the pre-existing
  `0006`. A direct disposable-database row-count check confirmed 0 before
  and 0 after the full suite, both before and after the adversarial
  stress-testing described below — no leaked rows at any point.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff, instructed to *prove* — not merely read — that each of the
  five corrections is load-bearing. For each finding, it temporarily
  reverted the specific fixed mechanism (finding 1/2: swapped
  `_fetch_running_attempts()` back for the old
  `current_attempt_ids is not None and current_state is not None` gate;
  finding 3: swapped `run_had_source_issue` back for the old
  `any_attempt_not_completed`; finding 5: removed `.with_for_update(read=
  True)` from the real `SELECT`), reran that finding's specific regression
  test, and confirmed it failed in exactly the predicted way (attempt stuck
  `'running'`; `failures` duplicated to length 2; status stayed
  `'completed'` instead of `'completed_with_errors'`; a real
  `ForeignKeyViolationError` on the `CollectionRun` insert), then reverted
  its own temporary edit and confirmed `git diff`/`git status` matched the
  pre-stress-test state exactly. For finding 4, it re-scanned the *entire*
  test file (not only the cited tests) for the same assertion-before-
  capture pattern and found none remaining anywhere. It additionally
  confirmed `run_saved_search()` has zero production callers yet (so the
  new test-only seam cannot activate outside a test), reran
  `test_ingestion_pipeline.py`/`test_ingestion_concurrency.py`/
  `test_live_proof_greenhouse_adapter.py` explicitly (95 passed, confirming
  `pipeline.run()` is still unaffected), and reran the full suite plus a
  fresh row-count check after all stress-testing to confirm no residue.
  No further findings.
- Deviations/known limitations: none beyond the already-recorded,
  pre-existing `alembic check` substitution.
- STOP — awaiting Codex re-review. Do not merge or begin live-provider
  contact, parallel/concurrent provider execution, the scheduler, API
  routes, Tier 4, Phase 3, `ProviderRegistry` production composition, or any
  migration.

### Work review

- Date/agent: 2026-09-05, Codex. Correction diff independently reviewed:
  `63e16ef..7384be5` on `phase-2/orchestration`.
- Independent verification: inspected the corrected abort discovery/finalization flow,
  source-issue aggregation, cleanup ordering, real initialization seam, associated tests,
  and documentation. Ran the three timing-sensitive regressions five consecutive times
  against PostgreSQL (**15/15 executions passed**), then the complete focused file
  (**26 passed**). Ran the genuine canonical verifier focused on
  `tests/test_orchestrator.py`: all **10 steps PASS**, including Ruff, mypy,
  repository/diff checks, disposable-database safety/reachability, **26 focused tests**,
  **1493 full-suite tests**, and temporary-directory cleanup.
- Finding disposition: **all five prior findings are closed.** Abort recovery now queries
  durable `status='running'` attempt rows by `collection_run_id`, closing the post-begin
  commit window. It trusts the in-memory execution state only when its durable attempt-id
  set exactly matches those running rows; an already-committed success is therefore not
  re-finalized, its errors are not duplicated, and its terminal attempts are not
  overwritten. The run rollup remains an absolute SQL-SUM reconciliation over attempt
  rows. `state.possibly_incomplete` is now aggregated across providers, covering the
  completed-source-plus-ProviderError case while leaving that source's attempt completed.
  Cleanup identifiers are captured before assertions throughout the new test file. The
  deletion race now invokes the real `run_saved_search()` initialization through a narrow
  no-op-by-default coordination seam, with bounded waits and failure-safe task cleanup.
- Scope/documentation: only the authorized orchestrator, tests, architecture text, and
  handoff ledger changed; no model, migration, live provider, parallel execution,
  scheduler, API, Tier 4, Phase 3, or production composition entered the pass. No further
  findings.
- Verdict: **Approved.** The bounded multi-provider orchestration slice and its correction
  pass are accepted; no additional correction is required.
- Exact requested corrections: none.
- STOP — do not merge to `main` or begin another slice until the user explicitly
  authorizes it.

### Merge record

- Date: 2026-09-06. User authorized merging `phase-2/orchestration` into
  `main` following Codex's final Approved re-review (no findings) above.
- Pre-merge state: `main` and `origin/main` both at `9f4c921`; feature
  branch pushed and clean at `f0fe7cd` (merge-base `9f4c921` — no
  divergence), containing correction commit `7384be5` plus the review
  commit.
- Merge: `git merge --no-ff phase-2/orchestration` on `main` — merge commit
  `7959a2e`. Post-merge diff against the feature branch's tip is empty
  (zero content difference); `check_repo.py` and `git diff --check` both
  exit 0; working tree clean.
- Post-merge verification: genuine external `verify.py --level routine
  --focus tests/test_orchestrator.py` — all **10 steps PASS** (Ruff
  format/check, mypy, `check_repo.py`, `git diff --check`, disposable-
  database URL/reachability, **26 focused tests**, **1493 full-suite
  tests**, temp-directory cleanup). `alembic heads` confirms `0017` remains
  the sole head; no migration files touched by the merge. Dev database
  (`jobgoblin`) confirmed unchanged at `0006` — untouched throughout.
- Pushed: `main` at `7959a2e`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `9f4c921` (the
  commit immediately before this merge) — this removes `run_saved_search()`,
  `provider_execution.py`, the `pipeline.py` extraction refactor, and their
  tests/docs cleanly, with no migration to reverse and no data written by
  this slice to any environment.
- STOP — do not begin live-provider integration, production
  `ProviderRegistry` composition, parallel/concurrent provider execution,
  the scheduler, API routes, Tier 4, Phase 3, or migrations without separate
  authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-05, Claude Code (Sonnet 5). Risk class R Phase 2
  closure pass on `phase-2/closure`, based on clean `main@4db557c`,
  implementing the smallest bounded closure identified by a prior read-only
  Phase 2 exit-gate audit (also this session). The audit found no
  unsatisfied Phase 2 requirement and no blocking gap; it found exactly two
  bounded documentation/test-coverage discrepancies, both closed here. Full
  suite and real-PostgreSQL verification were run (a heavier bar than R's
  default) at the user's explicit direction, since the new tests exercise
  identity behavior. No live providers, Tier 4, Phase 3, migration, or
  production behavior touched.
- Findings closed:
  1. **ARCHITECTURE.md §11 cited an unimplemented Tier 4 path as the
     required `ambiguous_match` fixture case.** Reworded to state the
     conflict type is proven through the implemented Tier 2/3
     candidate-resolution paths; Tier 4 remains explicitly deferred per
     [ADR 0004](DECISIONS/0004-scoped-deterministic-identity.md) pending a
     company-text-to-`company_id` resolution capability that does not exist.
     No implication that Tier 4 is implemented or required for closure.
  2. **Two of §11's required fixture-driven pipeline cases were previously
     proven only at the Phase 1 database-constraint level**
     (`test_job_occurrences.py`), not through the actual `pipeline.run()`
     path §11 specifies. Added two new fixtures under
     `tests/fixtures/discovery/` (`two_tenants_shared_source_job_id_primary/
     secondary.json`, `null_tenant_collision_primary/secondary.json`) and two
     new tests in `tests/test_ingestion_pipeline.py`:
     `test_two_distinct_tenants_sharing_source_job_id_produce_two_jobs`
     (same `source_job_id`, two distinct non-null tenants, distinct
     canonical URLs/requisition ids so Tier 2/3 cannot accidentally attach
     them — proves two `Job`s/two `JobOccurrence`s, exact run/attempt
     counters, both raw rows normalized) and
     `test_null_tenant_natural_key_collision_resolves_to_one_occurrence`
     (same `source_job_id`, `source_tenant_id = NULL` in two genuinely
     distinct payloads — identical canonical URL so this is a clean
     re-observation, not `evidence_mismatch`; differ only in
     `compensation_text` — proves one `Job`/one `JobOccurrence`, both raw
     rows normalized, `first_seen_at` frozen, `last_seen_at` advances, exact
     insert/update counters, zero `IdentityConflict` rows, and that the
     differing descriptive field stays frozen on replay, not silently
     proving nothing changed).
- Files changed: `docs/ARCHITECTURE.md` §11 (wording fix only),
  `docs/ROADMAP.md` (Phase 2 status: audit summary and closure-candidate
  note appended), `backend/tests/fixtures/discovery/` (4 new JSON files),
  `backend/tests/test_ingestion_pipeline.py` (2 new tests), this handoff
  entry. No model, schema, migration, provider-contact, or
  production-behavior file touched.
- Verification: genuine external `python scripts/verify.py --level routine`
  (full run, no `--focus`, since this closure spans the whole Phase 2
  fixture-proof surface) — all **9 steps PASS**: Ruff format/check, mypy,
  `check_repo.py`, `git diff --check`, disposable-database URL/reachability,
  **1495 full-suite tests** (was 1493; +2), temp-directory cleanup, ~137s.
  Also ran the full relevant ingestion/identity suites directly
  (`test_ingestion_pipeline.py`, `test_ingestion_concurrency.py`,
  `test_ingestion_natural_key.py`, `test_job_occurrences.py`,
  `test_orchestrator.py`): **250 passed**. `alembic heads` confirms `0017`
  remains the sole head; `git diff --stat origin/main -- migrations/` is
  empty. Dev database (`jobgoblin`) confirmed unchanged at the pre-existing
  `0006`. A direct disposable-database row-count check (`jobs`,
  `job_occurrences`, `raw_job_ingestions`, `collection_runs`,
  `collection_run_provider_attempts`, `identity_conflicts`, `users`,
  `user_jobs`) confirmed 0 before and 0 after the full suite.
- Adversarial self-review (abbreviated, proportionate to Class R per
  `LLM_WORKFLOW.md`): temporarily broke each new test's own invariant in
  `app/ingestion/persistence.py::_existing_occurrence_conditions()` and
  confirmed the corresponding new test failed for the intended reason, then
  reverted cleanly (`git diff --stat` empty afterward). (1) Removed the
  `TENANT`-domain `source_tenant_id` equality condition — the two-tenants
  test failed exactly at `_job_count(db_engine) == 2` (got `1`), with the
  second payload incorrectly colliding into the first tenant's occurrence
  and raising an `evidence_mismatch` conflict, proving tenant scoping is
  load-bearing. (2) Inverted the `NO_TENANT`-domain condition from
  `.is_(None)` to `.isnot(None)` — the NULL-tenant-collision test failed
  with a real `UniqueViolationError` on `uq_job_occurrences_no_tenant_natural_key`
  (the lookup could no longer find the existing row, so the second
  submission attempted a raw `INSERT`), proving the application-side lookup
  — not just the underlying constraint — is what makes this a clean
  idempotent upsert. Both breaks left transient rows in the disposable test
  database (from the crashed second run in case 2); both were identified
  and deleted before continuing, and a fresh row-count check confirmed 0
  rows across all affected tables before the final verification run above.
- Deviations/known limitations: none beyond the already-recorded,
  pre-existing `alembic check` substitution. This closure pass does not
  declare Phase 2 complete — that determination is Codex's, on independent
  exit-gate review.
- STOP — awaiting Codex's independent exit-gate review and sign-off. Do not
  merge, begin Phase 3, contact providers, add production behavior, or
  create a migration.
