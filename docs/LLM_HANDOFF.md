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

- Date/agent: 2026-08-29, Codex acting as authorized implementer. Class H correction
  pass for the six findings in review commit `fde5fa6`. Branch:
  `phase-2/natural-key-ingestion-spine`; base `fde5fa6` -> correction commit
  `7f01a9f`.
- Outcome:
  1. Re-observation is now observational-only (`last_seen_at` and `is_active`);
     descriptive/source/canonical fields remain frozen. A non-null canonical-URL
     disagreement raises distinct `DeferredIdentityConflictError` before mutation and
     propagates as a failed run; no conflict persistence was added.
  2. Unresolvable identity telemetry is fixed and sanitized at the persistence
     boundary. Raw URLs/payload values never enter error messages or logs.
  3. Failure telemetry now stores exact accumulated run/per-source discovered,
     inserted, and updated counters plus run duration, including failure after an
     earlier posting committed.
  4. The pipeline validates result-provider and job-provider identity and fails closed
     before posting writes for provider errors, incomplete results, or incomplete
     sources. The later partial-success policy remains unimplemented.
  5. Added payload-free INFO start/end, WARNING parse-error (raw-ingestion id only), and
     ERROR failure (run id + exception type only) logging.
  6. `RawJobIngestion.fetched_at` now uses `DiscoveredJob.discovered_at`;
     `observed_at` remains exclusive to Job/Occurrence observation state.
- Files changed: `backend/app/ingestion/{identity.py,persistence.py,pipeline.py}`;
  `backend/tests/test_ingestion_pipeline.py`; this handoff.
- Regression coverage: frozen changed/missing fields; direct and pipeline canonical
  mismatch behavior; secret-bearing malformed URL storage/logging; distinct fetch vs.
  observation timestamps; fail-on-second-posting counters; mismatched result/job
  provider; provider error, incomplete source, and incomplete-results fail-closed
  states. Focused ingestion/schema suite: **41 passed** (was 33). Full suite:
  **1147 passed** (was 1139), using workspace-local `--basetemp` because the host
  profile temp directory denies enumeration.
- Verification: Ruff format/check clean (73 files); mypy clean (91 source files);
  `scripts/check_repo.py` exit 0; `git diff --check` clean; test DB at sole head
  `0017`; `alembic check` reports no drift; development DB confirmed at `0006`.
  No model or migration changed.
- Adversarial Class-H self-review: challenged all 12 workflow questions against the
  correction diff. Fixed one defensive telemetry gap (the private terminal updater
  still accepted arbitrary exception text) and one test-hygiene class (failure-path
  cleanup now derives exact created IDs). The first targeted run also exposed and fixed
  an invalid two-source test fake whose job-provider labels disagreed with its provider.
- Deviation: an initial cleanup command used `TEST_DATABASE_URL`, which Alembic does
  not consume, and temporarily upgraded the development DB from `0006` to `0017`.
  Those newly created later tables were empty; development was immediately downgraded
  back to exactly `0006`, then `jobgoblin_test` was rebuilt with the correct
  `DATABASE_URL` override. Both current revisions were independently reconfirmed
  (`0006` development, `0017` test) before final verification.
- Known bounded limitations: canonical conflicts remain durable raw rows at `fetched`
  with failed run telemetry until the separately approved conflict-quarantine writer;
  partial provider results fail closed until their dedicated persistence slice.
- Rollback/handoff boundary: `7f01a9f` contains all executable corrections and tests;
  reverting that commit restores the reviewed `e725fd2` implementation without any
  schema downgrade or data migration. Review commit `fde5fa6` is documentation-only.
- STOP — awaiting independent review. Do not implement conflict persistence,
  QueryPlanner, tiers 2-4, multi-source partial-success behavior, live providers, or
  modify/merge `main`.

### Work review

- Date/reviewer: 2026-08-29, Claude Code (Sonnet 5) acting as independent reviewer
  (role transferred per the user's explicit instruction for this pass). Diff
  reviewed: correction commit `7f01a9f` against the six findings in review commit
  `fde5fa6`, on `phase-2/natural-key-ingestion-spine` (remote tip `66ae644`, a
  handoff-only rollback-boundary note; no executable change beyond `7f01a9f`).
- Pre-flight target verification (performed before any database command, per
  instruction): `docker exec ... \l` and `\dt` confirmed `jobgoblin` (development)
  holds only the five tables migration `0006` produces and `alembic_version='0006'`;
  `jobgoblin_test` (disposable) is a distinct database at `alembic_version='0017'`.
  `Settings().database_url`/`.test_database_url` resolved as expected (dev URL
  default; test override `None`, falling back to `conftest.py`'s disposable
  default). Reconfirmed both revisions unchanged after every command below.
- Independent verification performed (all against real PostgreSQL, `jobgoblin_test`
  only): `ruff format --check`/`ruff check` — clean; `mypy .` — clean, 91 source
  files; targeted (`test_ingestion_pipeline.py` + the four sibling ingestion/schema
  test files) — **41 passed**, matching the claim; full suite with an explicit
  writable `--basetemp` — **1147 passed**, matching the claim; `alembic heads` —
  `0017 (head)`; `alembic check` (DATABASE_URL explicitly overridden to
  `jobgoblin_test`) — `No new upgrade operations detected`; `scripts/check_repo.py`
  — exit 0; `git status`/`git diff --check` — clean, no executable file touched by
  this review. Development database reconfirmed at `0006` with its original
  five-table shape, both before and after the full run.
- Findings: **none.** Each of the eight required checks was independently
  confirmed by reading the actual diff and exercising it, not by trusting the
  `Work done` summary:
  1. **Re-observation is observational-only.** `persistence.py:118-123` — the
     found branch mutates only `occurrence.last_seen_at`/`.is_active` and the
     parent `Job.last_seen_at`; no descriptive/canonical/source field is touched.
     `test_reobservation_only_advances_observational_fields` submits a replay with
     both changed and `None`-ed descriptive fields and asserts every one of them
     still reads back as the *original* posting's values — passed.
  2. **Canonical-URL conflicts fail closed, pre-mutation, and are never
     `parse_error`.** `persistence.py:107-117` — `DeferredIdentityConflictError`
     is raised before any attribute assignment on the found branch. It is a
     distinct `RuntimeError` subclass; `pipeline.py`'s per-posting loop catches
     only `UnresolvableIdentityError`, so a conflict propagates to the outer
     handler as a failed run, never miscategorized as `parse_error`.
     `test_canonical_evidence_mismatch_fails_closed_before_mutation` (unit level)
     and `test_pipeline_leaves_conflicting_raw_row_fetched_and_marks_run_failed`
     (pipeline level: run `status='failed'`, the conflicting posting's raw row
     stays `'fetched'`, the pre-existing occurrence's `last_seen_at`/
     `canonical_url` are untouched) both passed.
  3. **No raw URL, token, payload value, or exception message ever reaches
     stored telemetry or logs.** `identity.py:26-48` — the exception message is
     now the fixed `UNRESOLVABLE_IDENTITY_MESSAGE` constant (confirmed via
     `git show 7f01a9f -- backend/app/ingestion/identity.py`: the prior code
     literally interpolated `job.source_url!r}` into the exception text — a real
     secret-leak bug, now removed). `pipeline.py`'s `_mark_parse_error` stores
     that same constant, never `str(identity_exc)`. Every `logger.*` call in
     `pipeline.py` (grepped exhaustively — 4 call sites, none in `identity.py`/
     `persistence.py`/`natural_key.py`) logs only IDs, status strings, counts, or
     `type(exc).__name__` — never a message or field value.
     `test_parse_error_telemetry_is_sanitized_logged_safely_and_uses_fetch_time`
     embeds a literal secret token in both `source_url` and `raw` and asserts it
     *is* present in `raw_payload` but absent from `error_message` and every
     captured log record; `test_unexpected_failure_propagates_and_marks_run_failed`
     and the `provider_error` case of
     `test_pipeline_fails_closed_for_unsupported_provider_result_states` repeat the
     same secret-absence proof against a generic exception message and a
     `ProviderError.detail` string, respectively — all passed.
  4. **Failed runs retain exact accumulated counters.** `pipeline.py:154-156,246-249`
     — `per_source_discovered`/`_inserted`/`_updated` are populated incrementally
     during the per-posting loop and read directly (not re-derived from a
     zeroed default) by the outer failure handler.
     `test_unexpected_failure_propagates_and_marks_run_failed` fails deliberately
     on the second of two postings and asserts both the run row and its one
     attempt row report `jobs_discovered=2, jobs_inserted=1, jobs_updated=0` —
     the exact state at the moment of failure, not zero and not the full batch —
     passed.
  5. **Provider-identity mismatches and unsupported partial/error results fail
     closed before any posting write.** `pipeline.py:161-177` — four checks
     (`result.provider`, source-set equality, per-job provider, `possibly_incomplete`)
     all run before `_write_fetched_row` is ever called for any job.
     `test_pipeline_fails_closed_for_unsupported_provider_result_states`
     (parametrized over all 5 cases named in the finding) asserts zero
     `RawJobIngestion` and zero `Job` rows exist afterward for every case — passed.
  6. **Required logging events exist.** `ingestion_run_started`/`_completed` (INFO),
     `ingestion_parse_error` (WARNING, raw-ingestion id only), `ingestion_run_failed`
     (ERROR, run id + exception type only) — all four present and asserted via
     `caplog` in the tests cited under (3)/(4) above.
  7. **`RawJobIngestion.fetched_at` uses `DiscoveredJob.discovered_at`.**
     `pipeline.py:182-184` passes `job.discovered_at`, not `observed_at`.
     `test_parse_error_telemetry_is_sanitized_logged_safely_and_uses_fetch_time`
     asserts `raw.fetched_at == job.discovered_at` **and** `!= observed_at` with
     deliberately distinct values — not merely coincidentally equal — passed.
  8. **Test cleanup is failure-safe; no schema/migration drift.** Every new/edited
     test either captures IDs immediately after each fetch and before any
     assertion on that data (the pattern this same review required last pass), or
     — in the two tests exercising `pipeline.run()` against a pre-existing
     occurrence — snapshots the full set of `Job`/`CollectionRun`/
     `RawJobIngestion` ids before the test body runs and cleans up the set
     difference afterward, which is strictly more robust against a missed
     `extend()` call. `alembic check` reports no drift; no migration file exists
     in this diff; development database independently confirmed unchanged at
     `0006` before and after this review's own verification run.
- Also explicitly checked, no defect found: the two-source counter test's fixture
  postings correctly set `provider="two_source_provider"` matching the fake
  provider's own `DiscoveryResult.provider` (the self-reported "invalid two-source
  test fake" bug from the prior pass — verified fixed, not merely claimed fixed);
  the concurrency test suite (`test_ingestion_concurrency.py`) is unaffected by the
  canonical-URL-conflict check, since every concurrent pair submits an identical
  payload (identical canonical URL cannot "disagree" with itself); no product
  documentation (`ARCHITECTURE.md`/`DATA_MODEL.md`/ADRs) was touched by this
  correction, consistent with the review's own explicit scope boundary (conflict
  persistence/quarantine documentation is deferred alongside the conflict-writer
  itself, not part of this bounded pass).
- Missing/inconclusive checks: none. Every one of the eight required checks was
  independently reproducible against real PostgreSQL, not merely inferred from the
  `Work done` narrative.
- **Verdict: approved. No corrections required.**
- STOP — awaiting user merge authorization. Do not implement conflict persistence,
  `QueryPlanner`, identity tiers 2–4, multi-source partial-success handling, live
  providers, or modify/merge `main` without separate authorization.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `dfb2db6` (no findings). Per user authorization, `phase-2/natural-key-
ingestion-spine` was merged into `main` with a normal merge commit (`20ab7d4`;
`--no-ff`, no squash/rebase/force-push) and pushed. `main`/`origin/main` are both
now at `20ab7d4`. Verified: feature branch was clean and `main`/`origin/main` were
still at `903ad0d` immediately before the merge; `main` has zero content diff
against the feature branch (`git diff main phase-2/natural-key-ingestion-spine
--stat` empty); migration `0017` remains the sole Alembic head;
`python backend/scripts/check_repo.py` exits 0 with zero findings; `git diff
--check` clean; working tree clean.

**Rollback boundary:** reverting `20ab7d4` (a single merge commit) restores `main`
to `903ad0d` exactly — no schema/migration exists in this slice to downgrade, and
no data migration accompanies it. This merges Phase 2's first vertical slice only
(the natural-key ingestion spine: identity tiers 1/5 across all three ADR-0004
natural-key forms, observational-only re-observation, fail-closed canonical-URL
conflict detection, sanitized telemetry/logging, and fail-closed provider/partial-
result validation) — it does **not** complete Phase 2. `QueryPlanner`,
`ProviderRegistry`, multi-source/partial-success handling, identity tiers 2–4,
conflict-quarantine persistence, live providers, Phase 3 normalization, API routes,
and scheduling all remain not started and are not authorized by this merge.

## Iteration 2

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
