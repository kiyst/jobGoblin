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

- Date/agent: 2026-09-05, Claude Code (Sonnet 5). Class H implementation of
  the approved, twice-revised multi-provider orchestration proposal, on
  `phase-2/orchestration`, based on clean `main@9f4c921`. Implements exactly
  `run_saved_search()` per the final authorized design (superseding two
  prior proposal-only rounds); no live providers, parallelism, scheduler,
  API routes, Tier 4, Phase 3, migration, or `ProviderRegistry` production
  composition touched.
- Outcome:
  - **`app/ingestion/provider_execution.py`** (new) — extracted the
    discover→validate→write-raw→resolve-identity→persist→accumulate logic
    out of `pipeline.py::run()`'s inlined body, unchanged in substance.
    `ProviderExecutionState` (a typed dataclass: per-source counters,
    `failures`, `had_parse_error`, `had_conflict`, `possibly_incomplete`,
    `source_stats`, `selected_errors`) is mutated **in place** by
    `execute_provider_query()` — `source_stats`/`selected_errors`/`failures`
    are populated immediately once a valid `DiscoveryResult` is received,
    *before* the per-posting loop that could later raise, so a downstream
    persistence exception still leaves genuinely-known telemetry available
    to whichever caller's exception handler runs next. `UnsupportedDiscoveryResultError`
    and the per-posting transaction helpers (`_write_fetched_row`,
    `_mark_parse_error`) moved here too; `pipeline.py` re-exports both for
    the existing test suite's direct use.
  - **`app/ingestion/pipeline.py`** — `run()`'s internals now delegate to
    `provider_execution.py`; public signature/behavior is unchanged (zero
    regression across the entire existing pipeline/concurrency/live-proof
    suite). Two existing tests (`test_ingestion_pipeline.py`,
    `test_live_proof_greenhouse_adapter.py`) had their
    `monkeypatch.setattr(pipeline, "persist_posting", ...)` call sites
    retargeted to `provider_execution.persist_posting` — the only place the
    call now actually lives after extraction; no other change to either
    test file.
  - **`app/ingestion/orchestrator.py`** (new) — `run_saved_search(engine,
    saved_search_id, provider_registry, *, clock, observed_at) -> uuid.UUID`,
    plus `SavedSearchNotFoundError`, `InactiveSavedSearchError`,
    `MalformedEnabledProviderError`, `DuplicateEnabledProviderError`. One
    `CollectionRun` per call, `saved_search_id` always populated. One
    initialization transaction: `SELECT ... FOR SHARE`s the `SavedSearch`
    row (closing the FK-race window against a concurrent delete — protects
    only the parent/FK write, never a serializable snapshot of title/
    location child rows, read plain/unlocked in the same transaction),
    validates `is_active`/`enabled_providers` (every entry a `str` matching
    `is_canonical_slug()`, no duplicates) before any write, then creates the
    run. Sequential per-provider loop: only `UnknownProviderError` and
    `QueryPlanValidationError` are sibling-continuing planning failures,
    durably recorded the instant they occur (`failures`, `source: null` —
    reusing the existing `ProviderErrorCategory.UNKNOWN` value, never an
    invented one); `ProviderRegistrationError` (registry name drift), any
    `discover()` exception, `UnsupportedDiscoveryResultError`, and any raw-
    storage/identity/persistence/database exception are **not** caught
    per-provider — they abort the entire run, matching `pipeline.run()`'s
    existing fail-closed posture, now scoped over N providers. Attempt rows
    are created lazily, atomically with `providers_attempted`/
    `providers_enforced_locally` (`local_enforcement`'s `set[str]` values
    converted to `sorted(list)` first — deterministic JSON regardless of set
    hash order), immediately before each provider's `discover()` call — a
    provider never reached has zero attempt rows. Normal per-provider
    completion atomically increments `CollectionRun`'s rollup by that
    provider's own deltas (one SQL `col = col + :delta` expression, same
    transaction as its attempt rows). **The targeted regression fix**: on a
    whole-run abort, `CollectionRun`'s rollup is *never* derived from a
    parallel Python running total (none exists anywhere in this file) — it
    is recomputed from a fresh `SELECT SUM(...)` over every persisted
    attempt row for the run and written as an absolute value, so it is
    provably always exactly `SUM` over its own attempt rows, never double-
    counted or lost regardless of when the abort was delivered.
  - **`tests/support/configurable_provider.py`** (new) — a fully
    configurable `DiscoveryProvider` test double (distinct name, arbitrary/
    malformed `DiscoveryResult`, or an exception to raise from `discover()`);
    `FixtureProvider` stays completely untouched.
  - **`tests/test_orchestrator.py`** (new, 23 tests) — every scenario from
    the approved test matrix: two providers succeeding; explicit
    empty/`None`-skipped selections; malformed slug (including a non-string
    element) / inactive / duplicate / not-found zero-write validation;
    planning-failure and graceful-`ProviderError` sibling-continuation;
    registry-drift / unexpected-exception / malformed-result whole-run
    abort with no sibling execution; persistence exception after partial
    progress (the exact-once-counter regression, proving `CollectionRun.
    jobs_* == SUM(attempts)` post-abort); parse error and identity conflict
    each independently forcing `completed_with_errors`; deterministic
    sorted `providers_enforced_locally`; per-provider attempt timestamp
    ordering (via a `FixedClock.advance()` side effect proving no provider
    inherits an earlier one's start time); deterministic provider
    processing order (explicit preserved, `NULL` sorted) and child
    (title/location) ordering (proving `(created_at, id)`, not insertion
    order — same-transaction inserts share an identical `created_at`);
    cancellation mid-provider; a genuine two-real-transaction `SavedSearch`
    deletion-race test (`asyncio.Event`-coordinated `FOR SHARE` vs.
    concurrent `DELETE`, proving the row survives with `saved_search_id =
    NULL`); no leaked rows or permanently-running rows across every
    scenario.
  - **`docs/ARCHITECTURE.md`** — new §6.8 documenting the full design above;
    corrected every "future orchestrator (not yet implemented)" placeholder
    in §6.4/§6.6 now that it exists, without overclaiming production
    composition (still genuinely deferred). **`docs/DATA_MODEL.md`** —
    documents `failures`'s `source: null` planning-failure case, reconciled
    with the existing `{provider, source, error}` shape (Rev 24 note).
    **`docs/ROADMAP.md`** — Phase 2 status paragraph updated; removed
    `ProviderRegistry`/orchestration from "still deferred."
- Files changed: exactly the above — `backend/app/ingestion/
  provider_execution.py` (new), `backend/app/ingestion/pipeline.py`
  (extraction refactor), `backend/app/ingestion/orchestrator.py` (new),
  `backend/tests/support/__init__.py`/`configurable_provider.py` (new),
  `backend/tests/test_orchestrator.py` (new), `backend/tests/
  test_ingestion_pipeline.py`/`test_live_proof_greenhouse_adapter.py`
  (monkeypatch-target retargeting only), `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/ROADMAP.md`, this handoff entry. No `db/
  models/` or migration file touched.
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_orchestrator.py` — all **10 steps PASS**: Ruff
  format/check, mypy (51 source files), `check_repo.py`, `git diff --check`,
  database-URL safety, real test-database reachability, **23 focused
  tests**, **1490 full-suite tests** (was 1467; +23), temp-directory
  cleanup, ~119s. `alembic heads` confirms `0017` remains the sole head;
  `git diff --stat -- backend/migrations/` is empty. Dev database
  (`jobgoblin`) confirmed unchanged at the pre-existing `0006`. A direct
  disposable-database row-count check (`raw_job_ingestions`, `jobs`,
  `job_occurrences`, `collection_runs`, `collection_run_provider_attempts`,
  `users`, `saved_searches`) confirmed 0 before and 0 after the full suite —
  no leaked rows.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff, scoped to 12 specific correctness properties (one `Collection
  Run` per call; the narrowed exception boundary; the no-double-counting
  abort mechanism; lazy atomic attempt creation; `ProviderExecutionState`'s
  mutate-in-place design; `pipeline.run()`'s unchanged behavior;
  `enabled_providers` zero-write validation; the deletion-race test's actual
  concurrency soundness — including tracing what would happen if the lock
  were broken, confirming no false-positive pass is possible; per-provider
  timestamp distinctness; the earlier leaked-row defect class specifically
  re-checked and confirmed absent via independent row-count reruns;
  `local_enforcement` JSON determinism; and 3 specific docs-vs-code claims).
  It independently reran the full suite, mypy, ruff, and a live
  `is_canonical_slug(None)` repro. **One Medium finding**: `enabled_providers`
  containing a `None` element crashed with a raw, unsanitized `TypeError`
  instead of the documented `MalformedEnabledProviderError`, since
  `is_canonical_slug()` assumes `str` and `enabled_providers` is a plain
  `text[]` with no CHECK constraining its elements. Fixed: added an
  `isinstance(name, str)` guard before the slug check (mirroring
  `ProviderRegistry`'s own established pattern for the identical class of
  defect); widened `_ERROR_MALFORMED_ENABLED_PROVIDER`'s fixed message;
  added `test_non_string_enabled_provider_element_zero_writes`. Two Low
  findings (no orchestrator-level test composing a graceful `ProviderError`
  with a successful sibling; no test for a mid-`_finalize_provider_success`
  database exception) — the first was cheap and directly on point, so
  `test_graceful_provider_error_plus_successful_sibling` was added; the
  second was traced algebraically (an exception there rolls back that one
  atomic transaction entirely, leaving the abort handler's own state
  correctly bound) and left as a documented, no-code-defect-found residual,
  disproportionate to add a synthetic DB-fault-injection test for. Reran the
  full verifier after both fixes: 23 focused (was 21; +2), 1490 full-suite
  (was 1488; +2), all 10 steps still PASS, zero leaked rows reconfirmed.
- Deviations/known limitations: none beyond the already-recorded,
  pre-existing `alembic check` substitution.
- STOP — awaiting Codex review. Do not merge or begin live-provider
  contact, parallel/concurrent provider execution, the scheduler, API
  routes, Tier 4, Phase 3, `ProviderRegistry` production composition, or any
  migration.

### Work review

- Date/agent: 2026-09-05, Codex. Implementation diff independently reviewed:
  `9f4c921..63e16ef` on `phase-2/orchestration`.
- Verification: inspected every changed implementation/test/documentation path; ran
  `tests/test_orchestrator.py` directly (**23 passed**); then ran the genuine canonical
  verifier focused on that file: all **10 steps PASS**, including Ruff, mypy,
  repository/diff checks, disposable-database safety/reachability, **23 focused tests**,
  **1490 full-suite tests**, and temporary-directory cleanup. No migration diff was
  introduced. The existing suite is green, but it does not exercise the transaction-
  boundary cases below.
- **High — cancellation after lazy-attempt commit can leave an attempt permanently
  `running`.** `run_saved_search()` assigns `current_attempt_ids` only after awaiting
  `_begin_provider_attempt()` (`orchestrator.py:448-453`). If that helper's transaction
  commits and cancellation is delivered before the await returns, the attempt rows and
  `providers_attempted` entry are durable but the abort handler still sees
  `current_attempt_ids is None`; it skips `_finalize_provider_aborted()` and marks only
  the parent run failed. This is the exact async commit-ambiguity window the approved
  design required the implementation to close. Abort recovery must discover persisted
  `status='running'` attempts by `collection_run_id`, not depend exclusively on IDs
  assigned after an awaited commit. Add a regression that wraps the real begin helper,
  lets it commit, then raises `CancelledError`, and proves no attempt remains running.
- **High — cancellation after successful provider-finalization commit can duplicate
  failures and overwrite a completed attempt as failed.** `_finalize_provider_success()`
  atomically commits attempt completion, counter increments, and `state.failures`, but
  `current_attempt_ids/current_state` are cleared only after the await returns
  (`orchestrator.py:468-481`). Cancellation delivered after the commit but before return
  sends the same state through `_finalize_provider_aborted()`, which appends its
  `ProviderError` entries a second time and rewrites already-terminal attempts to
  `failed`. Abort reconciliation must re-read durable attempt status and finalize/append
  only when the success transaction did not commit (for example, operate only on still-
  `running` attempts). Add a regression that calls the real success finalizer, raises
  `CancelledError` immediately after it commits, and proves one error remains one error,
  completed attempts stay completed, counters equal attempt sums, and the parent run is
  failed because orchestration was cancelled.
- **Medium — a `ProviderError` on a source that reports `completed=True` can leave the
  parent run incorrectly `completed`.** The single-provider pipeline uses
  `state.possibly_incomplete`, which is true whenever `DiscoveryResult.errors` is
  non-empty. The orchestrator aggregates only planning/parse/conflict and non-completed
  attempt flags (`orchestrator.py:472-493`), never `state.possibly_incomplete`. The new
  graceful-error test uses `completed=False`, so the failed attempt masks this omission.
  Aggregate a run-level provider/source-issue flag from every completed execution state
  and add the missing case: `completed=True`, `incomplete_results=False`, one real
  `ProviderError`, plus a successful sibling must yield a completed attempt carrying its
  error and a `CollectionRun.status='completed_with_errors'`.
- **Medium — the new persistent-database tests repeat the cleanup-ordering defect the
  handoff claims was checked.** Several tests perform fallible assertions before
  capturing created Job/RawJobIngestion IDs (for example
  `test_orchestrator.py:883-941`), and some exception-path tests assert run counts before
  recording the run ID (`:646-648`, `:698-700`, `:880-882`). A failed assertion can
  therefore leave rows that corrupt later row-count tests. Audit the new file and make
  cleanup independent of assertions: capture IDs immediately after the operation and
  before assertions, or use a failure-safe before/after identity-scope cleanup pattern.
- **Medium — the deletion-race test proves a copied SQL sequence, not
  `run_saved_search()` itself.** `test_saved_search_deletion_race_survives_with_saved_search_id_null`
  manually repeats the `SELECT ... FOR SHARE` and `CollectionRun` insert
  (`test_orchestrator.py:1306-1333`). Removing the lock from production would leave this
  test green. Exercise the real initialization path using a narrow private coordination
  seam/event (or an equivalent non-duplicating mechanism), bounded timeouts, and
  failure-safe release/cleanup so the regression is load-bearing against the actual
  orchestrator.
- Verdict: **Changes requested.** The overall architecture, narrowed exception policy,
  database-derived abort rollups, ProviderExecutionState extraction, planning semantics,
  JSON conversion, and documentation direction are sound. Correct only the five bounded
  findings above, rerun Class H verification and adversarial review, then stop for
  re-review. Do not merge or begin another slice.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-05, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/orchestration` for the five bounded findings from Iteration 1's
  `Work review` above (uncommitted at review time; committed together with
  this correction, preserved byte-for-byte, not rewritten). Base: `63e16ef`
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
  sentence on the test-only seam), this handoff entry (Iteration 1
  preserved verbatim per the rotation rule). No `db/models/`,
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
