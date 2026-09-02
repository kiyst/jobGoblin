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

- Date/agent: 2026-09-01, Claude Code (Sonnet 5). Class H implementation of the
  approved `ambiguous_match` identity-conflict persistence slice on
  `phase-2/ambiguous-match-persistence`, based on clean `main@e18b2b3`.
- Outcome: Tier 2/3 finding more than one distinct candidate Job no longer raises
  `AmbiguousIdentityMatchError` (a whole-run failure). It now creates a standalone
  Job/JobOccurrence, exactly like a clean insert, and persists an ADR-0007
  `ambiguous_match` `identity_conflicts` row, isolated per posting. No schema or
  migration change — the existing Phase-1 `identity_conflicts` table and its
  `ambiguous_match` array-shape `CHECK` already supported this shape.
- Binding decisions applied exactly as authorized:
  1. `_discover_candidates()`'s `<=2` probe remains the ambiguity *trigger* at both
     `_attach_to_candidate` sites (pre-lock, post-lock recheck); a new
     `_discover_all_candidates()` (unlocked, unbounded, sorted by UUID) supplies the
     *persisted* evidence. If that authoritative requery resolves to fewer than two
     candidates, `CandidateResolutionUnstableError` is raised and nothing is
     persisted — new tests cover both the pre-lock and post-lock-recheck
     disagreement cases, plus a 3-candidate case proving the full set (not just the
     probe's two) is what gets persisted.
  2. `UpsertOutcome.__post_init__` enforces the invariants at construction:
     `AMBIGUOUS` requires >=2 distinct, sorted candidate IDs; every other kind must
     carry none. Four direct unit tests cover missing/singleton/duplicate/unsorted
     tuples and cross-kind rejection.
  3. `existing_value` = sorted candidate Job-ID strings; `incoming_value` =
     single-element array with the new JobOccurrence's ID string — documented
     explicitly (code and all three touched decision/architecture docs) as
     intentionally different entity types, not a symmetry bug.
  4. New `_after_ambiguous_flush()` test seam mirrors `_after_quarantine_flush`/
     `_after_attach_flush`; a forced post-flush failure proves the new Job, new
     JobOccurrence, `IdentityConflict`, and raw terminal update all roll back
     together. A separate test proves reprocessing the same terminal raw row is
     rejected by `_validate_raw_association`'s existing `processing_status` check,
     with no second conflict row and no further mutation.
  5. `pipeline.py`'s counter dispatch is now an exhaustive if/elif over all five
     `UpsertKind` values (`QUARANTINED` moved out of the trailing `else`); a final
     `else: raise AssertionError(...)` fails closed for any future unrecognized
     kind. `AMBIGUOUS` buckets `jobs_inserted` (a real Job was created) and sets
     `had_conflict`; a dedicated test forces a fake outcome kind to prove the
     fail-closed branch and confirms no falsely successful counters.
  6. `AmbiguousIdentityMatchError` deleted; every surviving reference updated —
     `UpsertKind`/`_attach_to_candidate`/`upsert_job_occurrence`/`persist_posting`
     docstrings, `CandidateResolutionUnstableError`'s own docstring, ADR 0004, ADR
     0007 (new "Phase 2 implementation notes" section), ARCHITECTURE.md §8/§11,
     DATA_MODEL.md's `identity_conflicts` row notes, ROADMAP.md.
  - Preserved unchanged: standalone-Job creation (no guessing among candidates);
    zero candidate mutation on either ambiguity site, documented precisely per-site
    (pre-lock touches nothing; post-lock recheck may already hold one candidate's
    `FOR UPDATE` lock but never writes to it); one atomic transaction;
    `completed_with_errors` run status / `completed` attempt status; sanitized
    IDs-only logging; `CandidateResolutionUnstableError` untouched and fail-closed.
  - ROADMAP.md rewritten to be merge-state-neutral per the user's explicit
    correction: dropped the fixed "three merged slices" count (would go stale on
    the next merge), and the new `ambiguous_match` capability is described as
    "implemented, not yet merged — on branch `phase-2/ambiguous-match-persistence`,
    awaiting review and merge authorization."
- Files changed: `backend/app/ingestion/persistence.py`, `backend/app/ingestion/
  pipeline.py`, `backend/tests/test_ingestion_pipeline.py` (11 new tests, 3
  rewritten to persist instead of raise; `test_candidate_changes_after_lock_is_
  detected_not_retried` left unchanged — a genuinely different code path);
  `docs/DECISIONS/0004-scoped-deterministic-identity.md`, `docs/DECISIONS/
  0007-identity-conflict-quarantine.md`, `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/ROADMAP.md`; this handoff entry. No schema,
  migration, provider, or network file touched.
- Verification: genuine external `python scripts/verify.py --level routine --focus
  tests/test_ingestion_pipeline.py` — all **10 steps PASS**: Ruff format/check,
  mypy (82 source files), `check_repo.py`, `git diff --check`, database-URL
  safety, real test-database reachability, **49 focused tests**, **1398
  full-suite tests** (was 1387; net +11), temp-directory cleanup, in ~160s.
  `alembic heads` confirms `0017` remains the sole head (no migration added; `git
  diff --stat migrations/` is empty). `alembic current` against the configured
  dev database (`jobgoblin`) shows it pre-existingly stamped at `0006`, far behind
  head — a condition that predates this branch (this slice adds zero migrations)
  and was **not** remediated: no `alembic upgrade` was run against it; a direct
  before/after `alembic current` check confirms it stayed at `0006` throughout.
  All schema/database work in this slice ran only against the disposable
  `jobgoblin_test` database.
- Adversarial self-review: dispatched a fresh-context subagent against the actual
  diff (not this summary). It confirmed correct control flow (no candidate
  mutation on either ambiguity path), correct `INSERTED`-vs-`AMBIGUOUS` tagging,
  airtight `UpsertOutcome` validation, correct evidence shape against
  DATA_MODEL.md's own `CHECK`, exhaustive/unreachable-else pipeline dispatch, and
  zero leftover `AmbiguousIdentityMatchError` references. It found one real defect
  class (Medium-High): six new tests captured cleanup IDs
  (`job_ids.append(...)`/preexisting-set-diff) *after* assertions that could fail,
  risking a leaked row in the disposable test database on a genuine regression.
  Fixed in all six by moving the capture to immediately follow the mutating call,
  before any assertion — reverified by rerunning the full suite (still 1398
  passed).
- Deviations/known limitations: `alembic check` itself could not be exercised
  end-to-end because of the pre-existing stale dev database described above;
  substituted with `alembic heads` (single, unchanged head) plus an empty
  `migrations/` diff, which together give the equivalent no-schema-drift guarantee
  for a no-migration slice without touching the dev database.
- STOP — awaiting Codex review. Do not merge, start Tier 4, add schema changes,
  contact live providers, or expand this slice.

### Work review

- Date/agent: 2026-09-01, Codex. Implementation diff reviewed:
  `e18b2b3..ddfc1f8` on `phase-2/ambiguous-match-persistence`.
- Independent verification: inspected the persistence and pipeline control flow, all
  changed product documentation, and the new/rewritten tests. Ran the genuine external
  canonical verifier focused on `tests/test_ingestion_pipeline.py`: all **10 steps
  PASS**, including Ruff format/check, mypy, repository and whitespace checks,
  disposable-database safety/reachability, **49 focused tests**, **1398 full-suite
  tests**, and temporary-directory cleanup. Independently confirmed Alembic `0017`
  remains the sole head and the working tree was clean before this review.
- Required-invariant disposition:
  1. The bounded probe never supplies persisted evidence; the authoritative unbounded
     query supplies the complete sorted distinct candidate set and disagreements fail
     closed at both ambiguity sites.
  2. `UpsertOutcome` rejects missing, singleton, duplicate, unsorted, and cross-kind
     candidate tuples at construction.
  3. A stable ambiguity creates a standalone Job/JobOccurrence, records the deliberate
     candidate-Job/new-JobOccurrence evidence asymmetry, links the raw row, and mutates
     no candidate data.
  4. Injected post-flush failure proves atomic rollback of the new Job, occurrence,
     conflict, and raw terminal transition; terminal-row reprocessing is rejected.
  5. A mixed batch proves posting isolation, exact run `completed_with_errors` / attempt
     `completed` states, insertion/update counters, raw links, and IDs-only telemetry.
  6. Pipeline dispatch explicitly handles all five current outcomes; an unknown outcome
     fails the run with exact failed telemetry and no falsely successful counters.
- Documentation-only findings corrected directly under `LLM_WORKFLOW.md`'s mechanical
  rule: ADR 0004 had one current-behavior sentence still naming the deleted
  `AmbiguousIdentityMatchError`; ROADMAP retained a fixed three-slice count and called
  the feature explicitly "not yet merged," despite the binding requirement for
  merge-state-neutral wording. Replaced those statements with the implemented
  `AMBIGUOUS`/instability behavior and timeless capability wording. No executable,
  schema, test, scope, or architectural decision changed.
- Adversarial cases checked: probe/full-query disagreement before and after a candidate
  lock, three-candidate evidence completeness, candidate non-mutation, rollback after
  every ambiguity effect is flushed, repeated raw processing, clean work beside an
  ambiguity in one batch, and a future unhandled outcome. No executable findings.
- Verdict: **Approved** after the mechanical documentation corrections above. The
  `ambiguous_match` persistence slice is accepted; no Claude correction pass is needed.
- Exact requested corrections: none.
- STOP — do not merge to `main`, begin Tier 4, contact a provider, or start another
  slice until the user explicitly authorizes it.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `fd690d5` (no executable findings; two mechanical documentation corrections
recorded in that same review). Per user authorization,
`phase-2/ambiguous-match-persistence` was merged into `main` with a normal merge
commit (`9ab1342`; `--no-ff`, no squash/rebase/force-push) and pushed. `main`/
`origin/main` are both now at `9ab1342`. Verified: the feature branch was clean and
pushed at `fd690d5`, and `main`/`origin/main` were still at `e18b2b3` immediately
before the merge; `main` has zero content diff against the feature branch
(`git diff main phase-2/ambiguous-match-persistence --stat` empty); migration `0017`
remains the sole Alembic head; `python -m scripts.check_repo` exited `0`;
`git diff --check` was clean; working tree clean throughout. No `/compact`, network
request, or database mutation was performed during the merge.

**Rollback boundary:** reverting `9ab1342` (a single merge commit) restores `main` to
`e18b2b3` exactly — no schema/migration exists in this slice to downgrade, and no
data migration accompanies it (the existing Phase-1 `identity_conflicts` table and
its `ambiguous_match` array-shape `CHECK` already supported this shape without any
schema change). This merges the `ambiguous_match` conflict-persistence slice only
(`backend/app/ingestion/persistence.py`, `backend/app/ingestion/pipeline.py`, their
tests, and the five documentation files listed in the `Work done` entry above) — it
does **not** touch Tier 4, `QueryPlanner`, `ProviderRegistry`, any live provider, or
any other Phase 2 work, all of which remain not started and are not authorized by
this merge.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-01, Claude Code (Sonnet 5). Class H implementation of the
  approved multi-source partial-success handling slice on
  `phase-2/partial-success-handling`, based on clean `main@02ef086`.
- Outcome: `ingestion/pipeline.py::run()` no longer aborts the entire run when a
  `DiscoveryResult` reports a source-level failure/partial result/error
  (`possibly_incomplete=True`). A healthy source's jobs persist normally while a
  sibling source's own failure is recorded independently. No schema/migration
  change — every column this slice populates (`collection_run_provider_attempts.
  status='partial'`/`error_category`/`error_message`/`retry_count`/`rate_limited`/
  `incomplete_results`; `collection_runs.failures`) already existed from Phase 1.
- Binding decisions applied exactly as authorized:
  1. Added result-consistency validation `DiscoveryResult`'s own pydantic validator
     cannot express, run before any raw row is written, as three new whole-run
     `UnsupportedDiscoveryResultError` guards (ordered so each is independently
     reachable, not shadowed by another): `completed=False` with any actual
     `DiscoveredJob` attributed to it; `completed=False` with
     `incomplete_results=True`; and (a source having *any* completed value)
     `jobs_found` disagreeing with the actual attributed count. Three dedicated
     tests each assert zero raw/Job/JobOccurrence rows and `status='failed'`
     telemetry.
  2. Attempt-row `status` precedence implemented exactly as specified: `failed` if
     `not completed`; else `partial` if `incomplete_results`; else `completed`. A
     `ProviderError` alone never downgrades a `completed` source's status, though it
     still makes the parent run `completed_with_errors` and still populates that
     row's `error_category`/`error_message`.
  3. Multiple `ProviderError`s per source are valid: every one becomes its own
     `collection_runs.failures` entry (never discarded), while the attempt row's own
     `error_category`/`error_message` reflect only the chronologically latest one
     (ties broken by later `DiscoveryResult.errors` position). Verified by hand and
     by a dedicated test covering both the strict-timestamp and the tie-break case
     across two sources in one run.
  4. `failures` entries use the exact specified shape (`{provider, source, error:
     {category, retryable, detail, occurred_at}}`, `category` as the plain string
     value, `occurred_at` as `.isoformat()`), one per `ProviderError`, in
     `result.errors` order — asserted verbatim in the healthy/broken-source test.
     `detail`/`error_message`/`failures` content is never logged — confirmed by
     direct inspection of every `logger.*` call in the file (IDs/counts/status/
     exception-type only) plus an existing-pattern sanitized-logging test.
  5. Every applicable attempt field is now populated, including `retry_count`/
     `rate_limited` (previously always left at their `0`/`False` defaults
     regardless of what `SourceRunStats` reported) — a dedicated test proves both
     reach the row exactly.
  6. Docs: `docs/DATA_MODEL.md` gained a new Rev 23 entry pinning down the exact
     `failures[*].error` shape and the latest-error attempt-summary rule (correcting
     stale wording that called `failures` a mere "denormalized convenience copy" of
     the attempt row, backwards for the multi-error case); `docs/ARCHITECTURE.md` §9
     gained a clarifying paragraph on the same two rules; `docs/ROADMAP.md` describes
     the new capability without asserting a merge state, and Phase 2 is **not**
     declared complete anywhere (Tier 4/`QueryPlanner`/`ProviderRegistry` remain
     listed as deferred). No new ADR, per instruction.
- Files changed: `backend/app/ingestion/pipeline.py`; `backend/tests/
  test_ingestion_pipeline.py` (narrowed the existing malformed-result parametrized
  test to its two still-genuinely-invalid cases; added 9 new tests — 3 for the new
  consistency guards, 6 for graceful-handling behavior); `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/ROADMAP.md`; this handoff entry. No schema,
  migration, provider, or network file touched. `ingestion/identity.py`/
  `ingestion/persistence.py` untouched — this slice is entirely about source-level
  telemetry, orthogonal to per-job identity resolution.
- Verification: genuine external `python scripts/verify.py --level routine --focus
  tests/test_ingestion_pipeline.py` — all **10 steps PASS**: Ruff format/check,
  mypy (82 source files), `check_repo.py`, `git diff --check`, database-URL
  safety, real test-database reachability, **55 focused tests**, **1404
  full-suite tests** (was 1398; net +6 = 9 added − 3 removed), temp-directory
  cleanup, in ~120-145s across repeated runs. `alembic heads` confirms `0017`
  remains the sole head; `git diff --stat -- migrations/` is empty. `alembic
  current` against the configured dev database (`jobgoblin`) is unchanged at
  `0006` before and after this pass — no `alembic upgrade` was run against it;
  all schema/database work ran only against the disposable `jobgoblin_test`
  database.
- Adversarial self-review: dispatched a fresh-context subagent against the actual
  diff (not this summary). It confirmed: all three new consistency checks are
  independently reachable/testable (traced against `DiscoveryResult`'s own
  pydantic validator to show none is accidentally shadowed); status precedence,
  latest-error selection (including the tie-break), `failures` shape/completeness,
  `error_message` CHECK-safety (`.strip() or None` applied before a Core-style
  `update()`, which bypasses the model's own `@validates`), and log-content
  sanitization are all correct; the two remaining malformed-result parametrized
  cases are clean post-rework; the untouched exception path is still correctly
  reachable and tested. It found one real defect (High): four new tests captured
  cleanup IDs (`job_ids.append(...)`/`raw_ingestion_ids.extend(...)`) *after*
  assertions that could fail — the same defect class caught and fixed in the
  immediately preceding slice, reintroduced here. One of the four additionally had
  the occurrence lookup itself inside `finally`, where a `NoResultFound` (the exact
  regression the test exists to catch) would abort before reaching `_cleanup()`
  entirely. Fixed in all four by moving every ID capture to immediately follow the
  mutating call, before any assertion, and moving the risky lookup out of `finally`
  into the `try` block — reverified by rerunning the full suite (still 1404
  passed). One Low finding (a `failures == []` assertion that would pass even
  under a naive always-empty implementation, given that specific test's own
  `errors=[]` input) was reviewed and left as-is: it is paired with tests that do
  exercise non-empty `failures`, and strengthening it further was judged not worth
  the added complexity.
- Deviations/known limitations: none new beyond the prior iteration's already-
  recorded `alembic check` substitution (same pre-existing stale dev database,
  unrelated to this slice).
- STOP — awaiting Codex review. Do not merge, start Tier 4, `QueryPlanner`,
  `ProviderRegistry`, add schema changes, contact live providers, or expand this
  slice. Per instruction, Phase 2's exit gate is not declared satisfied here — a
  separate audit is required after merge, since Tier 4 remains deferred and the
  documented fixture requirements must be reconciled explicitly.
