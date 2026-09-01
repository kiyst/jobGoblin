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

- Date/agent: 2026-08-31, Claude Code (Sonnet 5). Class H correction pass on
  `phase-4/greenhouse-live-proof` for the three bounded findings in review
  commit `d1d1e69` (`f4a1a5b..d1d1e69`). Base `f4a1a5b`. Addresses exactly
  Findings 1-3 from Iteration 1's `Work review`; Finding 4 (two live
  requests made against an authorization for one) required no executable
  change — its disposition is strict adherence to the stop boundary below.
  No network request and no real `CREATE`/`DROP DATABASE` were performed
  during this pass, per the review's own instruction.
- Outcome, addressing each finding exactly:
  1. **High — a rejected database target can no longer reach the
     destructive cleanup path.** `_run_proof` now tracks a separate
     `cleanup_authorized` flag, initialized `False` and set `True` only
     once `assert_safe_for_local_destructive_lifecycle` has genuinely
     passed (i.e. only once an admin connection is about to be opened to
     attempt `CREATE DATABASE`). The `finally` block now gates on
     `cleanup_authorized`, not on `quoted_name is not None` — a production
     `APP_ENV`, a remote/missing host, or a non-disposable name now never
     opens an admin connection at all, let alone issues `DROP DATABASE`/
     queries `pg_database`. An *authorized* creation attempt that then
     fails (e.g. a transient connection error) still sets
     `cleanup_authorized = True` before the attempt, so cleanup still runs
     for that case, matching the review's own guidance. Added two
     orchestration-level offline tests
     (`test_run_proof_rejects_production_before_touching_any_database_or_network`,
     `test_run_proof_rejects_a_remote_host_before_touching_any_database_or_network`)
     that call the real `_run_proof` with every database/network-facing
     function (`_create_database`, `_drop_database_if_exists`,
     `_database_exists`, `_run_alembic_upgrade`, `_reachability_preflight`,
     `canary.fetch_greenhouse_jobs_raw`, `_run_two_pipeline_passes`)
     replaced by a call-recording fake via `monkeypatch`, and a faked
     `get_settings()` returning a production/remote-host `Settings` —
     both assert the recorded call list is empty and `_run_proof` returns
     `False`.
  2. **Medium — the shared-test-database cleanup is now failure-safe when
     `pipeline.run()` itself raises.** Replaced the list-based
     `_cleanup_scoped` helper (which only ever recorded ids *after* a
     successful return/query, so a `pipeline.run()` call that raised before
     returning left rows no captured id could find) with
     `_capture_identity_scope`/`_delete_new_rows`: a before/after snapshot,
     scoped by the full `(provider, source, tenant, source_job_id)` natural
     key for `JobOccurrence`/`Job`/`RawJobIngestion`/`IdentityConflict`
     (`CollectionRun` has no natural-key column of its own and is
     snapshotted as the whole table — safe since this suite runs
     single-process and sequentially, never under `pytest-xdist`), diffed
     to find exactly what a call created regardless of whether it returned.
     Rewrote both existing database-touching tests to use this mechanism.
     Added
     `test_cleanup_recovers_rows_left_by_a_pipeline_run_that_raises_mid_transaction`,
     which monkeypatches `pipeline.persist_posting` to raise immediately —
     reproducing the exact gap: `pipeline.run()` already committed its
     `CollectionRun`/`CollectionRunProviderAttempt` (before its own `try:`
     block) and the job's `RawJobIngestion` row (Transaction A_i, before
     `persist_posting` is ever called) as separate prior sub-transactions,
     so both are left behind (and asserted to genuinely be present) before
     the snapshot-diff cleanup removes them; a final snapshot proves
     nothing remains.
  3. **Low — added the previously absent persisted-state assertions**, to
     both the live proof and the offline test: run-one
     `completed_at >= started_at`; run-two attempt's
     `provider`/`source`/`status`; both runs' raw rows checked individually
     (not just as a status set) for `raw_content_hash`/`source_identifier`/
     `job_occurrence_id` linkage; and the surviving parent `Job`'s
     `canonical_url`/`first_seen_at` rechecked unchanged after
     re-observation (only `last_seen_at` may advance).
- Files changed: `backend/scripts/live_proof_greenhouse_ingestion.py`;
  `backend/tests/test_live_proof_greenhouse_adapter.py`; this handoff.
  `backend/scripts/db_safety.py`, the ADR 0004 addendum, the canary, its
  fixture, the application pipeline, schema, and migrations are all
  unchanged — confirmed by `git status`/`git diff --check` showing no
  modification to any of them.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean, whole repo.
  - `mypy app tests scripts` -> clean, 81 source files.
  - `python -m pytest tests/test_live_proof_greenhouse_adapter.py
    tests/test_db_safety.py -q` -> **45 passed** (was 42; net +3: two
    orchestration-level guard-rejection tests, one injected
    mid-transaction-failure test), offline only.
  - Full suite -> **1370 passed** (was 1367).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean.
  - **Genuine external `python scripts/verify.py --level routine --focus
    tests/test_live_proof_greenhouse_adapter.py tests/test_db_safety.py`**
    -> all **10 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
    `git diff --check`, database URL safety, real test-database
    reachability, focused pytest **45 passed**, full suite **1370
    passed**, temporary-directory cleanup) in `110.42s`.
  - No live Greenhouse request and no real `CREATE`/`DROP DATABASE` were
    performed during this correction pass, per the review's instruction —
    development (`jobgoblin`) and shared test (`jobgoblin_test`) databases
    were the only databases touched, exactly as in every other slice.
- Adversarial self-review: re-read the corrected diff before this entry,
  confirming (a) `cleanup_authorized` is set only after the guard call
  succeeds and never before, so a guard `RuntimeError` always leaves it
  `False`; (b) an authorized creation attempt that itself fails still
  reaches cleanup, since `cleanup_authorized` is set before
  `_create_database` is called, not after; (c) `_capture_identity_scope`'s
  `CollectionRun` snapshot is a genuine before/after diff of the whole
  table, correct under this suite's single-process, sequential execution
  model but explicitly documented as depending on that (no `pytest-xdist`);
  (d) the new mid-transaction-failure test's own assertions
  (`after["raw_ids"] - before["raw_ids"]` non-empty,
  `after["job_ids"] - before["job_ids"]` empty) independently prove the gap
  was genuinely reproduced, not merely that a fake raised. Found no further
  issues beyond the three findings addressed above.
- Deviations/known limitations: unchanged from Iteration 1 (no
  `DiscoveryProvider` registration, scheduler wiring, `QueryPlanner`/
  `ProviderRegistry`, Phase 3 normalization, or company resolution). Finding
  4's disposition (no further live request without separate authorization)
  is treated as a durable constraint on this and any future correction pass
  for this slice, not merely a one-time acknowledgment. `main` untouched
  throughout.
- STOP — awaiting Codex re-review. Do not merge `main`, contact Greenhouse
  again, run another live proof, alter production ingestion/provider code,
  or begin QueryPlanner/ProviderRegistry, normalization, scheduling, or
  another slice.

### Work review

- Date/agent: 2026-08-31, Codex. Correction diff reviewed:
  `d1d1e69..19581f7` on `phase-4/greenhouse-live-proof`.
- Independent verification performed: inspected the complete correction diff and
  traced guard rejection, authorized creation, cleanup authorization, snapshot/diff
  cleanup, and persisted assertions; ran the genuine external routine verifier focused
  on both changed offline test files — all 10 steps PASS, **45 focused tests** and
  **1370 full-suite tests** pass. No Greenhouse request and no real disposable-database
  create/drop invocation was performed during re-review.
- Prior-finding disposition:
  1. **High finding closed.** `cleanup_authorized` remains false on every guard
     rejection and becomes true only after the destructive-lifecycle guard succeeds,
     before creation is attempted. The production/remote orchestration tests invoke the
     real `_run_proof()` with every DB/network/pipeline boundary instrumented and prove
     none is touched on rejection.
  2. **Medium finding substantially closed, with one remaining scoping defect below.**
     Before/after snapshots now recover run/raw rows even when `pipeline.run()` raises
     after committed sub-transactions; the regression genuinely injects that failure
     and proves a fresh final snapshot equals the initial state.
  3. **Low assertion finding substantially closed, with one remaining descriptive-field
     gap below.** Timestamp ordering, run-two attempt identity/status, raw linkage/hash/
     source identifier, and first-seen preservation are now asserted.
  4. **Process disposition honored.** No additional external call/live proof occurred.
- Remaining findings:
  1. **Medium — the shared-test identity scope still omits half of the natural key.**
     `_capture_identity_scope()` at
     `backend/tests/test_live_proof_greenhouse_adapter.py:397-454`, plus occurrence
     lookups at lines 415, 537, and 614, filter only by
     `(source_tenant_id, source_job_id)`. The requested scope was the full
     `(provider, source, tenant, source_job_id)` domain; two providers/sources may
     legitimately reuse the same tenant/job-id pair. As written, a pre-existing or
     future row in another identity namespace can be selected, included in snapshots,
     or used to derive a Job id. Add the fixed `provider='ats_scrapers'` and
     `source='greenhouse'` predicates everywhere this offline identity is located, and
     construct a unique synthetic offline identity/URL per test so the committed real
     fixture's stable ID cannot collide with stale or concurrently prepared data. Keep
     raw payload/source identifier/hash internally consistent with that synthetic copy.
  2. **Low — “parent Job descriptive fields” remains under-asserted.** The correction
     checks only `canonical_url` and observation timestamps at
     `backend/scripts/live_proof_greenhouse_ingestion.py:389-391,468-470` and the
     corresponding offline assertions. The mapped fields actually written to `Job` are
     `title`, `location_raw`, `compensation_text`, and `canonical_url`. Assert all four
     after insertion and again after re-observation, in both the live assertion helper
     and offline pipeline test.
  3. **Low documentation drift — `_run_proof()`'s docstring is now false.** Lines
     555-556 still say cleanup “always runs ... regardless of where the sequence
     stopped,” while the safety fix correctly skips every cleanup/admin operation when
     the guard rejects the target. Rewrite it to say cleanup always runs after an
     authorized creation attempt, including an ambiguous creation failure, and is
     intentionally skipped before authorization.
- Missing/inconclusive checks: the external proof was intentionally not repeated; this
  pass verifies only the accepted historical live result and the corrected offline
  invariants.
- Verdict: **Approved with binding clarifications** — the destructive cleanup bug and
  intermediate-commit leak are resolved. Apply only the three narrow remaining items
  above; no design or product change is required.
- Exact bounded correction: modify only
  `backend/scripts/live_proof_greenhouse_ingestion.py`,
  `backend/tests/test_live_proof_greenhouse_adapter.py`, and the new `Work done` entry.
  Run the focused offline tests and routine verifier, record actual counts, commit/push,
  and stop for final re-review. Make no network request and no real create/drop run.
- STOP — do not merge `main`, contact Greenhouse, execute the live proof, modify shared
  safety/ADR/canary/application/schema files, or begin another slice.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-31, Claude Code (Sonnet 5). Class H correction pass on
  `phase-4/greenhouse-live-proof` for the three remaining bounded findings in
  review commit `68c6c12` (`19581f7..68c6c12`). Base `19581f7`. Addresses
  exactly the remaining Medium/Low findings; the four prior findings' own
  dispositions (cleanup-authorization gate, snapshot-diff cleanup,
  timestamp/attempt/raw assertions, no-further-live-request) are unchanged
  and untouched. No network request and no real `CREATE`/`DROP DATABASE`
  were performed during this pass.
- Outcome, addressing each remaining finding exactly:
  1. **Medium — the shared-test identity scope now covers the full natural
     key.** Added `provider == "ats_scrapers"`/`source == "greenhouse"`
     predicates to `_capture_identity_scope`'s `JobOccurrence` query and to
     both remaining occurrence lookups in
     `test_two_pipeline_runs_insert_then_update_without_duplication`
     (previously filtered only by `source_tenant_id`/`source_job_id`, which
     could in principle select a row from a different, unrelated identity
     namespace sharing the same tenant/job-id pair). `_mapped_job()` now
     requires an explicit `unique_suffix` keyword and mutates a fresh copy
     of the fixture's job dict — `id` and `absolute_url` become
     `test-{suffix}`-derived synthetic values — *before* mapping, so
     `DiscoveredJob.raw`, `source_job_id`, and `canonical_url` all derive
     from the same synthetic values automatically; `canonical_json_hash
     (job.raw)` stays internally consistent with no separate bookkeeping.
     Every call site now passes a distinct, self-documenting suffix (e.g.
     `"two-runs-insert-update"`, `"cleanup-mid-transaction-failure"`) so no
     database-touching test's identity can collide with another test's, the
     real committed fixture's own stable id, or stale/concurrent data.
  2. **Low — all four mapped parent-`Job` fields are now asserted, both
     after insertion and after re-observation, in both the live assertion
     helpers and the offline pipeline test.** Added `title`/`location_raw`/
     `compensation_text` (alongside the already-present `canonical_url`) to
     `_assert_state_after_run_one`/`_assert_state_after_run_two` in the live
     proof script and to both `Job` checks in
     `test_two_pipeline_runs_insert_then_update_without_duplication`. New
     `_as_stored()` helper (script) mirrors `Job`'s own
     `_normalize_nullable_text` validator (trim `" \t\n\r"`, blank collapses
     to `None`) — the real committed fixture's own `title` has a genuine
     trailing space (an upstream Greenhouse data-quality artifact, already
     noted and left as-is in an earlier slice), so comparing the persisted
     row against the raw `DiscoveredJob` field requires applying the same
     transform to the expected side first; a raw equality assertion added
     without this failed immediately against real fixture data, was caught
     before commit, and is exactly why this helper exists rather than a
     bare `==`. The offline test imports and reuses the same
     `live_proof._as_stored()`, not a second copy.
  3. **Low — `_run_proof()`'s docstring no longer contradicts its own
     code.** Rewritten to state cleanup is guaranteed only after an
     *authorized* creation attempt (including an ambiguous creation
     failure), and is intentionally skipped entirely when the
     destructive-lifecycle safety guard itself rejects the target —
     matching `cleanup_authorized`'s actual behavior from the prior
     correction pass exactly.
- Files changed: `backend/scripts/live_proof_greenhouse_ingestion.py`;
  `backend/tests/test_live_proof_greenhouse_adapter.py`; this handoff.
  `backend/scripts/db_safety.py`, the ADR 0004 addendum, the canary, its
  fixture, the application pipeline, schema, and migrations are all
  unchanged — confirmed by `git status`/`git diff --check`.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean, whole repo.
  - `mypy app tests scripts` -> clean, 81 source files.
  - `python -m pytest tests/test_live_proof_greenhouse_adapter.py
    tests/test_db_safety.py -q` -> **45 passed** (same count as before —
    no tests added or removed this pass, only corrected), offline only.
  - Full suite -> **1370 passed** (unchanged).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean.
  - **Genuine external `python scripts/verify.py --level routine --focus
    tests/test_live_proof_greenhouse_adapter.py tests/test_db_safety.py`**
    -> all **10 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
    `git diff --check`, database URL safety, real test-database
    reachability, focused pytest **45 passed**, full suite **1370
    passed**, temporary-directory cleanup) in `110.12s`.
  - No live Greenhouse request and no real `CREATE`/`DROP DATABASE` were
    performed during this correction pass — development (`jobgoblin`) and
    shared test (`jobgoblin_test`) databases were the only ones touched.
- Adversarial self-review: re-read the corrected diff before this entry.
  Confirmed (a) every `JobOccurrence` query touching shared
  `jobgoblin_test` state now carries all four natural-key predicates,
  grepped to verify no remaining bare `source_tenant_id`/`source_job_id`-
  only filter exists anywhere in the test file; (b) `_mapped_job`'s
  synthetic-identity mutation happens on a dict copy *before*
  `map_job_to_discovered_job` is called, so `raw`/`source_job_id`/
  `canonical_url` cannot drift out of sync with each other by
  construction, not by convention; (c) every one of the eight `_mapped_job`
  call sites was updated with a distinct suffix — grepped for any
  remaining bare `_mapped_job(datetime(...))` call missing the keyword,
  found none; (d) `_as_stored` is defined once, in the script, and the
  offline test calls that same function rather than duplicating the trim
  logic. Found no further issues beyond the three findings addressed
  above.
- Deviations/known limitations: unchanged from Iteration 1. `main`
  untouched throughout. No further live request was made, consistent with
  Iteration 1's disposition on that point.
- STOP — awaiting Codex re-review. Do not merge `main`, contact Greenhouse,
  execute the live proof, modify shared safety/ADR/canary/application/
  schema files, or begin another slice.

### Work review

- Date/agent: 2026-08-31, Codex. Final correction diff reviewed:
  `68c6c12..ae02d22` on `phase-4/greenhouse-live-proof`.
- Independent verification performed: inspected the complete bounded diff and traced
  every affected identity lookup, synthetic fixture construction, persisted-field
  assertion, and cleanup-authorization statement. Ran the genuine external routine
  verifier focused on `tests/test_live_proof_greenhouse_adapter.py` and
  `tests/test_db_safety.py`: all **10 steps PASS**, including **45 focused tests** and
  **1370 full-suite tests**. No Greenhouse request and no real disposable-database
  create/drop invocation was performed during this review.
- Prior-finding disposition:
  1. **Medium finding closed.** `_capture_identity_scope()` and both occurrence
     lookups use the complete fixed identity domain `(provider="ats_scrapers",
     source="greenhouse", source_tenant_id, source_job_id)`. `_mapped_job()` requires
     a distinct explicit suffix at every call site and mutates a fresh fixture-dict
     copy before mapping, keeping `raw`, `source_job_id`, `canonical_url`, and their
     hash mutually consistent.
  2. **Low assertion finding closed.** The live assertion helpers and offline pipeline
     test now verify `title`, `location_raw`, `compensation_text`, and `canonical_url`
     after both insertion and re-observation. `_as_stored()` matches the `Job` model's
     exact covered-whitespace trim and blank-to-`None` behavior.
  3. **Low documentation finding closed.** `_run_proof()` now distinguishes guaranteed
     cleanup after an authorized creation attempt from intentional zero-contact
     behavior when the safety guard rejects the target.
- Adversarial cases checked: cross-provider/source key reuse can no longer enter this
  test scope; synthetic fixture identities cannot collide silently or drift from their
  raw payload; upstream trailing covered whitespace is compared using the actual
  persistence normalization; rejected targets remain outside cleanup authorization.
  No further findings.
- Missing/inconclusive checks: the external proof was intentionally not repeated. The
  accepted historical live result remains the evidence for real Greenhouse transport;
  this final pass verifies the corrected offline invariants only.
- Verdict: **Approved**. The `greenhouse-live-proof` slice and its correction passes are
  accepted; no further correction is required.
- Exact requested corrections: none.
- STOP — do not merge `main`, contact Greenhouse, execute the live proof, begin an
  adapter/provider integration, or start another slice until the user explicitly
  authorizes that action.
