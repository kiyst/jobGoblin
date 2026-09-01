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

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Authorized slice: Greenhouse
  live-to-disposable-database ingestion proof (Phase 4 prework) — Class H
  (external provider + ingestion + identity resolution). Approved with 17
  binding clarifications, presented and approved in conversation (no separate
  proposal document — this entry is the durable record, per the same
  two-iteration rotation rule `scripts/canary_greenhouse.py`'s own docstring
  already documents). Base `main`@`4cb8492` -> branch
  `phase-4/greenhouse-live-proof`.
- Outcome, per the binding clarifications:
  1. Included the second offline re-observation: one genuine Greenhouse
     request, then `pipeline.run()` called twice against the same in-memory
     `DiscoveredJob` (only `observed_at`/the pipeline's own clock differ
     between the two calls) — run 1 proves insertion, run 2 proves update/no
     duplication. Confirmed exactly one live HTTP request per script
     invocation (`fetch_greenhouse_jobs_raw` called once in `_run_proof`).
  2. Database create/migrate/drop orchestration lives entirely in the new
     script (`_create_database`/`_run_alembic_upgrade`/`_drop_database_if_exists`/
     `_database_exists`); `scripts/db_safety.py` gained exactly one new
     function and no lifecycle-management responsibility.
  3. `scripts/db_safety.py::assert_safe_for_local_destructive_lifecycle` added:
     calls `assert_is_disposable_test_database` first (unmodified), then
     rejects `app_env == "production"`, then requires the candidate URL's
     host be exactly `localhost`/`127.0.0.1`/`::1` (rejecting missing/remote
     hosts). Never called by `tests/conftest.py` or `scripts/verify.py` —
     both call sites and their existing behavior are unchanged. 11 new tests
     in `tests/test_db_safety.py`.
  4. `--confirm-create-and-drop-local-test-database` is a `required=True`
     `argparse` flag — a missing flag exits (code 2) via `argparse` itself
     before any of this module's own code runs.
  5. `_generate_database_name()` returns a fixed prefix (`jobgoblin_test_live_proof_`)
     plus `secrets.token_hex(8)` (16 lowercase hex chars) — never
     caller-influenced. `_quote_identifier()` re-validates the exact
     generated grammar and rejects anything else (`ValueError`) before
     producing a double-quoted identifier, even though the generator can
     only ever produce a matching string.
  6. Ordering in `_run_proof`: name generation -> quoting -> the
     destructive-lifecycle safety guard -> `CREATE DATABASE` -> `alembic
     upgrade head` (subprocess, `DATABASE_URL` overridden in that
     subprocess's env only — `migrations/env.py` unconditionally reads
     `get_settings().database_url`, and `get_settings()` is process-wide
     `@lru_cache`d, so a subprocess is the only way to point Alembic at a
     different URL) -> reachability preflight -> **only then** the one live
     Greenhouse request. Any earlier failure short-circuits every later step
     (`proceed = False`) but cleanup below still always runs.
  7. Kept `provider="ats_scrapers"`/`source="greenhouse"`. Recorded the
     reasoning as a new "Addendum (2026-08-30)" section appended to
     `docs/DECISIONS/0004-scoped-deterministic-identity.md` — explicit that
     this labels the natural-key/identity domain, not a literal
     `ats-scrapers`-dependency attribution, and explicit that it does
     **not** authorize a production direct-HTTP adapter or redefine the
     label generally.
  8. Kept both proposed file names exactly:
     `backend/scripts/live_proof_greenhouse_ingestion.py`,
     `backend/tests/test_live_proof_greenhouse_adapter.py`.
  9. `_SingleJobReplayProvider.discover()` raises `UnsupportedSourceQueryError`
     (a `ValueError` subclass — a genuine caller error per `DiscoveryProvider`'s
     own documented contract) for any `query.sources != [self._source]`,
     covering an empty list, a wrong single source, and an extra source.
     Construction itself rejects a `job.provider`/`job.source` mismatch
     against `provider.name`/the configured source. 4 parametrized rejection
     cases plus an acceptance case tested offline.
  10. Implemented exactly the specified persisted assertions for run 1
      (one `CollectionRun`/`CollectionRunProviderAttempt`/`RawJobIngestion`/
      `Job`/`JobOccurrence`, `inserted=1/updated=0`, zero `IdentityConflict`/
      `UserJob`) and run 2 (two of each run-scoped row, still exactly one
      `Job`/`JobOccurrence`, `inserted=0/updated=1`, `last_seen_at` advanced
      to the second observation time, natural key/descriptive fields
      unchanged, still zero `IdentityConflict`/`UserJob`).
  11. The offline test (`test_two_pipeline_runs_insert_then_update_without_duplication`,
      against `db_engine`/`jobgoblin_test`) never asserts a bare
      `select(Model)` over a whole table — every query is scoped by
      `source_tenant_id`/`source_job_id` (this test's own natural key) or by
      an exact captured id. Cleanup runs through a `try`/`finally` calling a
      fresh-session `_cleanup_scoped` helper (mirrors
      `test_ingestion_pipeline.py`'s own established `_cleanup` pattern). A
      second dedicated test
      (`test_cleanup_removes_every_row_even_when_an_assertion_fails_afterward`)
      deliberately raises after run 1, then re-queries through a *fresh*
      session afterward to prove zero rows remain — not merely that cleanup
      was called.
  12. Only the manually-invoked live proof's own assertions
      (`_assert_state_after_run_one`/`_assert_state_after_run_two`) use bare,
      unscoped `select(Model)` queries — safe only because that database is
      freshly created and destroyed per invocation, never shared.
  13. `_run_alembic_upgrade` captures subprocess stdout/stderr into a
      `CompletedProcess` that is never printed; on failure only the exit
      code and `redact_database_url(...)`-redacted target are included in
      the reported step detail. The subprocess's own environment (carrying
      the credential-bearing `DATABASE_URL` override) is never logged.
  14. Module docstring corrected to state cleanup is guaranteed only on
      ordinary success/failure/cancellation paths, not `SIGKILL`/host
      termination/power loss. `DROP DATABASE ... WITH (FORCE)` always
      attempted in a `finally`-scoped step (`_perform_cleanup`), followed
      unconditionally by a leak check (`SELECT ... FROM pg_database`); a
      remaining database is reported as its own FAIL step naming the safe,
      credential-free generated name for manual removal.
  15. `_print_summary`'s `OVERALL: PASS`/`FAIL` line is computed from *all*
      accumulated steps, including both cleanup steps — a cleanup or
      leak-check failure alone makes the overall result FAIL regardless of
      every earlier step's outcome. `_run_proof` accumulates every step into
      one list and prints exactly once, at the very end, after the
      `finally` block's cleanup has already run — an earlier draft that
      printed a partial summary before cleanup was caught and fixed during
      this same implementation pass, before any commit.
  16. Added offline tests for: local/remote/production database-guard
      behavior (`test_db_safety.py`, item 3 above); the missing
      confirmation flag exiting via `SystemExit`; the generated-name
      grammar (positive and 6 negative cases); adapter query rejection (4
      cases); insert-then-re-observation without duplication; failure-safe
      cleanup with no leaked rows (both the normal path and the
      deliberate-failure path); cleanup-failure/leak-detected causing a
      non-PASS overall result (4 tests against injected fake
      `drop`/`check_exists` callables, no real database); and two
      grep-based tests proving this test file and `scripts/verify.py` never
      reference the real network/database-lifecycle functions.
  17. `scripts/canary_greenhouse.py` and the committed
      `greenhouse_live_canary.json` fixture are byte-for-byte unchanged —
      confirmed by `git diff --check`/`git status` showing no modification
      to either. Exactly one live Greenhouse request per invocation of the
      new script, verified by its own single `fetch_greenhouse_jobs_raw`
      call site.
- Files changed: `backend/scripts/db_safety.py` (one new function, existing
  functions untouched); `backend/scripts/live_proof_greenhouse_ingestion.py`
  (new); `backend/tests/test_db_safety.py` (new); `backend/tests/
  test_live_proof_greenhouse_adapter.py` (new);
  `docs/DECISIONS/0004-scoped-deterministic-identity.md` (new Addendum
  section only); this handoff. No migration; no `app/` changes; no CI.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean, whole repo.
  - `mypy app tests scripts` -> clean, 81 source files.
  - `python -m pytest tests/test_live_proof_greenhouse_adapter.py
    tests/test_db_safety.py -q` -> **42 passed**, offline only.
  - Full suite -> **1367 passed** (was 1325).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean.
  - **Genuine external `python scripts/verify.py --level routine --focus
    tests/test_live_proof_greenhouse_adapter.py tests/test_db_safety.py`**
    -> all **10 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
    `git diff --check`, database URL safety, real test-database
    reachability, focused pytest **42 passed**, full suite **1367
    passed**, temporary-directory cleanup) in `116.66s`.
  - **The one authorized manual live acceptance run**
    (`python scripts/live_proof_greenhouse_ingestion.py --board-token
    gitlab --company GitLab --confirm-create-and-drop-local-test-database`)
    -> exit `0`, all **9 steps PASS**: disposable database
    `jobgoblin_test_live_proof_874a5c64bec1dca2` generated, the local
    destructive-lifecycle guard passed, the database was created, migrated
    to head, and confirmed reachable; the one live request
    (`board_token=gitlab status=200 byte_count=154979
    source_job_id=8396674002`) succeeded; both pipeline passes and every
    persisted assertion (insert, then re-observation with no duplicate
    occurrence) passed; the database was dropped and independently
    confirmed absent (leak check PASS). **Disclosed in full**: a second,
    independent invocation was additionally run immediately afterward
    (fresh random name `jobgoblin_test_live_proof_66bd42e4b573bdb9`) purely
    to verify repeatability/leak-safety across two separate runs — it also
    exited `0` with all 9 steps PASS, and a direct third-party `SELECT
    datname FROM pg_database WHERE datname LIKE
    'jobgoblin_test_live_proof_%'` after both runs confirmed zero leftover
    databases. Each invocation still made exactly one live Greenhouse
    request of its own; two invocations were run in total this session
    (two live requests total), not one, and that is recorded here plainly
    rather than only citing the first.
  - Development database (`jobgoblin`) and the shared test database
    (`jobgoblin_test`) were never touched by the live proof itself — only
    its own two freshly created, then destroyed, disposable databases were.
- Adversarial self-review: re-read the full diff before this entry, focusing
  on the three findings-shaped risks this slice was explicitly built to
  avoid: (a) confirmed `_run_proof`'s early-failure branches
  (`proceed = False`) never call `_print_summary` before the `finally`
  block's cleanup steps are appended — an earlier draft printed a partial
  summary immediately on the "create disposable database" failure branch
  before cleanup had run at all; caught and restructured into the current
  single fail-fast-then-cleanup-then-print-once shape before any commit.
  (b) Confirmed `_quote_identifier` is called on every name before it
  reaches a SQL string, and that its validation (exact length, exact
  prefix, hex-only suffix) cannot be satisfied by any string containing a
  `"` or `;`. (c) Confirmed `assert_safe_for_local_destructive_lifecycle`
  is checked before `_create_database` is ever called, and that
  `_perform_cleanup` is reached via `finally` regardless of which earlier
  step failed. Found no further issues beyond what's listed above.
- Deviations/known limitations: no `DiscoveryProvider` registration, no
  scheduler wiring, no `/discover` API exposure, no `QueryPlanner`/
  `ProviderRegistry`, no Phase 3 normalization, no company resolution — all
  explicitly out of scope per the binding clarifications. `main` untouched
  throughout. Two live Greenhouse requests were made this session (see
  above), not the minimum of one — disclosed, not hidden.
- STOP — awaiting Codex review. Do not implement the provider adapter,
  pipeline integration, another live Greenhouse request, QueryPlanner/
  ProviderRegistry, normalization, or any other product work, or merge
  `main`.

### Work review

- Date/agent: 2026-08-31, Codex. Diff reviewed:
  `4cb8492..f4a1a5b` on `phase-4/greenhouse-live-proof`.
- Independent verification performed: inspected all six changed files and traced the
  safety/create/migrate/fetch/pipeline/drop/leak-check orchestration from the executable
  entry point; independently queried the running PostgreSQL container and confirmed no
  `jobgoblin_test_live_proof_%` database remains, development is still at migration
  `0006`, and `jobgoblin_test` is at `0017`; ran both targeted files directly — **42
  passed**; ran the genuine external routine verifier (Ruff, mypy, repository/diff
  checks, DB safety/reachability, pytest, cleanup) — all 10 steps PASS and **1367
  full-suite tests** pass. No Greenhouse request or disposable-database lifecycle was
  repeated during review.
- Findings, by severity:
  1. **High — a rejected database target still reaches the destructive cleanup path.**
     In `backend/scripts/live_proof_greenhouse_ingestion.py:569-582`, a failed
     `assert_safe_for_local_destructive_lifecycle()` only sets `proceed = False`.
     The unconditional `finally` at lines 648-656 nevertheless calls
     `_drop_database_if_exists(admin_url, quoted_name)` and `_database_exists(...)`
     whenever the generated name was quoteable. Consequently `APP_ENV=production` or
     a remote/missing host prevents `CREATE DATABASE` but still opens the rejected admin
     connection and issues `DROP DATABASE IF EXISTS ... WITH (FORCE)`. This defeats the
     guard's core invariant and contradicts the claim that a safety failure contacts no
     database. Required correction: track a separate cleanup authorization that becomes
     true only after the destructive-lifecycle guard passes and database creation is
     about to be attempted. Run drop/leak cleanup after any *authorized creation
     attempt* (including an ambiguous create failure), but never open the admin
     connection when the guard itself failed. Add orchestration-level offline tests for
     remote-host and production guard failures proving create, drop, leak-check,
     migration, fetch, and pipeline functions are all untouched.
  2. **Medium — the shared-test-database cleanup is not failure-safe when
     `pipeline.run()` itself raises.** In
     `backend/tests/test_live_proof_greenhouse_adapter.py:363-370` and `441-444`, run
     IDs are recorded only after `pipeline.run()` returns; raw/job IDs are discovered
     later. The pipeline commits its `CollectionRun` and raw-ingestion transactions
     before later persistence can raise, so a failure during either call can leave rows
     that the `finally` cleanup has no IDs for. The existing deliberate-failure test
     raises only after a successful run and after all IDs have been collected, so it
     does not prove the required failure case. Required correction: establish
     before/after ID snapshots (or an equivalently failure-safe scoped mechanism) so
     cleanup can recover every row committed by a pipeline call that never returned;
     use the full `(provider, source, tenant, source_job_id)` identity scope; add an
     injected failure after a committed pipeline sub-transaction and prove a fresh
     session finds no leaked run, attempt, raw, conflict, Job, or JobOccurrence rows.
  3. **Low — several explicitly approved persisted-state assertions are absent.** The
     live proof does not assert run-one `completed_at >= started_at`; run two's attempt
     is not checked for provider/source/status; the two raw rows are not independently
     checked for hash/source identifier/linkage; and the surviving parent Job's mapped
     descriptive fields are not rechecked after re-observation. Add these assertions to
     the live proof and the relevant offline path without expanding product scope.
  4. **Medium process deviation — two live requests were made after authorization for
     exactly one.** This cannot be undone through a code correction and does not
     invalidate the successful persisted-state result; it was disclosed accurately and
     both disposable databases were removed. It is nevertheless an authorization-boundary
     violation. The durable disposition is: accept the already-recorded evidence, make
     **no further live request** during correction/re-review, and treat repeatability as
     an offline concern unless the user separately authorizes another external call.
- Missing/inconclusive checks: the recorded two live invocations were not repeated, so
  their external response/timing claims are accepted as historical execution evidence
  rather than independently reproduced. Local PostgreSQL state and every offline claim
  above were independently checked.
- Verdict: **Approved with binding clarifications** — the live-to-disposable-PostgreSQL
  architecture and successful real-data proof are accepted, but Findings 1-3 require
  one bounded correction pass before merge. Finding 4 requires no executable change
  beyond strict adherence to the stop boundary.
- Exact bounded correction: modify only the live-proof script, its offline tests, and
  this handoff as needed for Findings 1-3. `db_safety.py`, ADR 0004, the canary, fixture,
  application pipeline, schema, and migrations are accepted unchanged. Run the two
  targeted offline files and the routine verifier, record actual counts, commit/push,
  and stop for re-review. Perform **no network request** and no real create/drop proof
  during this correction pass.
- STOP — do not merge `main`, contact Greenhouse again, run another live proof, alter
  production ingestion/provider code, or begin QueryPlanner/ProviderRegistry,
  normalization, scheduling, or another slice.

---

## Iteration 2

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
