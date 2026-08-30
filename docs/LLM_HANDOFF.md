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

- Date/agent: 2026-08-30, Codex. Correction diff reviewed:
  `8c1388e..6238096` on
  `phase-2/evidence-mismatch-conflict-persistence`; original implementation
  context rechecked against `10aa747..6238096` where relevant.
- The three findings from review commit `8c1388e` are closed:
  1. `persist_posting()` now re-resolves `job` through `resolve_identity()` and
     requires exact `NaturalKey` equality before mutation. The adversarial
     forged-tenant-key regression keeps every earlier raw-association signal
     valid, proves this new check is the rejecting boundary, and proves the raw
     row, Job/Occurrence population, and conflict population remain unchanged.
  2. The three-run test now proves cumulative run/attempt totals, every run and
     attempt's exact status/counters, every persisted `UserJob` column on the
     same id, and `error_message IS NULL` for every quarantined raw row.
  3. ADR 0007 now describes injected `observed_at`, the exact currently
     represented observation fields, the parent-Job update, and the explicit
     applicant-count deferral. ROADMAP accurately distinguishes the merged
     natural-key spine from this still-unmerged feature branch.
- Independent verification: `scripts/check_repo.py` exit 0; Ruff format/check
  clean; mypy clean across **73 source files**; focused ingestion/concurrency
  suite **28 passed**; full suite **1157 passed** with workspace-local
  `--basetemp`; `alembic check` reports no drift; `jobgoblin_test` remains at
  `0017 (head)` and development `jobgoblin` remains at `0006`; working tree
  clean after removing the review temp directory.
- Findings: none.
- **Verdict: approved.** Tier-1 `evidence_mismatch` conflict persistence and
  its correction pass are accepted. STOP — do not merge this branch into
  `main` or begin `ambiguous_match`, identity tiers 2–4, `QueryPlanner`,
  `ProviderRegistry`, multi-source handling, live providers, normalization,
  APIs, scheduling, or any other slice until the user explicitly authorizes
  the next action.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `f2472f2` (no findings). Per user authorization,
`phase-2/evidence-mismatch-conflict-persistence` was merged into `main` with a
normal merge commit (`227184e`; `--no-ff`, no squash/rebase/force-push) and
pushed. `main`/`origin/main` are both now at `227184e`. Verified: feature
branch was clean at `f2472f2` and `main`/`origin/main` were still at `10aa747`
immediately before the merge; `main` has zero content diff against the feature
branch (`git diff main phase-2/evidence-mismatch-conflict-persistence --stat`
empty); migration `0017` remains the sole Alembic head; `python
backend/scripts/check_repo.py` exits 0 with zero findings; `git diff --check`
clean; development database reconfirmed at `0006` with its original five-table
shape; working tree clean.

**Rollback boundary:** reverting `227184e` (a single merge commit) restores
`main` to `10aa747` exactly — no schema/migration exists in this slice to
downgrade, and no data migration accompanies it. This merges Phase 2's second
vertical slice only (Tier-1 `evidence_mismatch` conflict persistence:
`persist_posting()`'s raw/natural-key-validated quarantine transaction, the
private rollback-test seam, the nondeterministic concurrency proof, the
three-run counter matrix, and the sanitized `ingestion_identity_conflict`
telemetry) — it does **not** complete Phase 2. `ambiguous_match`, identity
tiers 2–4, `QueryPlanner`, `ProviderRegistry`, multi-source partial-success
handling, live providers, Phase 3 normalization, API routes, and scheduling all
remain not started and are not authorized by this merge.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Authorized slice: Phase 2's
  third vertical slice, **Tier-2/Tier-3 cross-occurrence identity
  attachment** — Class H (identity/concurrency risk per
  PHASE_RISK_CHECKLIST.md's Phase 2 primary risks). Base `main`@`bd59a14` ->
  branch `phase-2/tier2-tier3-identity-attachment`. Implements the
  final-decision-table amendment (three prior review rounds: initial
  proposal, redesign-required correction, final four-finding amendment).
  This slice does **not** complete deterministic identity resolution — Tier
  4 remains deferred (see below).
- Outcome, per the approved amendment:
  1. **Mutually exclusive Tier 2/3 precedence** (`upsert_job_occurrence`):
     Tier 2 (normalized canonical URL) is attempted only when the incoming
     canonical URL normalizes to a usable value; a zero-candidate result
     there proceeds directly to Tier 5 — Tier 3 is never attempted for that
     posting. Tier 3 (tenant-scoped requisition) is attempted only when the
     canonical URL does *not* normalize to a usable value at all, and both
     `source_tenant_id`/`requisition_id_raw` are present. A usable canonical
     URL's miss is never treated as license to fall back to Tier 3.
  2. **Single-pass, fail-closed candidate resolution** (`_discover_candidates`/
     `_attach_to_candidate`, shared by both tiers): at most two distinct
     candidate `Job` ids retrieved; zero returns `None` (fall through to the
     next tier); more than one raises `AmbiguousIdentityMatchError`; exactly
     one acquires that Job `FOR UPDATE`; a missing Job raises
     `CandidateResolutionUnstableError`; the same query is rerun once under
     the lock; anything other than the same single Job raises one of those
     two errors. Never retried within the same transaction — no bare
     assertion anywhere in this path.
  3. **New advisory-lock domain** (`natural_key.py`):
     `canonical_url_advisory_lock_key()` (tag 4) and
     `tenant_requisition_advisory_lock_key()` (tag 5), sharing `NaturalKey`'s
     own versioned/length-prefixed/SHA-256 encoding via two extracted helper
     functions. Tag 5 is deliberately distinct from `NaturalKeyDomain.TENANT`'s
     tag 1 (a posting's `source_job_id`/`requisition_id_raw` can
     coincidentally match). Lock order is always natural-key lock -> Tier-1
     row lock -> (tier-specific lock, if reached) -> candidate discovery ->
     Job `FOR UPDATE` (parent) -> new `JobOccurrence` insert (child) —
     parent-before-child, compatible with `jobs` -> `job_occurrences`
     `ON DELETE CASCADE`.
  4. **`UpsertKind.ATTACHED`** — a new `JobOccurrence` under an *existing*
     Job — counts as `jobs_updated`, never `jobs_inserted`, at both
     `collection_runs` and `collection_run_provider_attempts` levels (no new
     Job was created; the existing Job's own `last_seen_at` is what
     advanced).
  5. **Pre-existing correctness fix, now in scope**: Tier 1's own found-branch
     parent-`Job` fetch changed from `session.get()` to
     `SELECT ... FOR UPDATE` — required because this slice is the first to
     make a Job reachable via more than one natural key (hence more than one
     advisory lock), which could otherwise lose a concurrent
     `last_seen_at` update under READ COMMITTED.
  6. **`_after_attach_flush()`** — a new private test seam in
     `persist_posting()`, fired after the existing Job's `last_seen_at`
     update, the new `JobOccurrence` insert, and the raw row's terminal
     update have all flushed, before commit — mirrors `_after_quarantine_flush()`'s
     established placement exactly.
  7. **Tier 4 remains deferred, not blocked-forever**: `DiscoveredJob.company`
     is raw text; no company-text-to-`company_id` resolution capability
     exists in the ingestion pipeline. That prerequisite — not merely an
     unwritten implementation — is what unlocks Tier 4; its residual
     duplicate-creation risk is accepted temporarily.
- Files changed: `backend/app/ingestion/{natural_key.py,persistence.py,pipeline.py}`;
  four new fixtures (`canonical_url_match_{primary,secondary}.json`,
  `tenant_requisition_match_{primary,secondary}.json`);
  `backend/tests/{test_ingestion_pipeline.py,test_ingestion_concurrency.py,
  test_ingestion_natural_key.py}`;
  `docs/DECISIONS/0004-scoped-deterministic-identity.md` (Phase 2
  implementation-notes addendum, no schema change); `docs/ROADMAP.md` (Phase
  2 status, also correcting stale "not yet merged" wording for the
  evidence-mismatch slice); this handoff. No migration —
  `ix_job_occurrences_tenant_requisition_lookup` already exists (confirmed
  live, exact column order, both before and after implementation).
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 73 source files.
  - Focused (`test_ingestion_pipeline.py` + `test_ingestion_concurrency.py`
    + `test_ingestion_natural_key.py`) -> **63 passed** (net +17 new tests
    overall this slice).
  - Full suite with a workspace-local `--basetemp` -> **1174 passed** (was
    1157).
  - Concurrency-sensitive tests (both real-transaction races) rerun 5x in a
    stress loop -> stable, no flakiness.
  - `alembic check` (against `jobgoblin_test`) -> `No new upgrade operations
    detected`; `alembic heads` -> `0017 (head)`, unchanged.
  - `\d job_occurrences` against `jobgoblin_test` -> confirmed
    `ix_job_occurrences_tenant_requisition_lookup btree (provider, source,
    source_tenant_id, requisition_id_raw)` live, exact expected column
    order, both before and after this pass.
  - Development database reconfirmed at `0006` with its original five-table
    shape, both before and after this pass.
  - `python scripts/check_repo.py` -> exit 0, zero findings.
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - Table-count queries against `jobgoblin_test` after every test run in
    this pass -> all ingestion-related tables at 0 rows; no leaked test
    data at any point.
- Adversarial self-review (fresh read of the complete diff before this
  entry): found and fixed **one real bug** — a pre-existing test
  (`test_per_source_attempt_counters_are_not_the_run_wide_aggregate`)
  constructed three "different" postings via `model_copy` without
  overriding `canonical_url`, so all three silently shared
  `clean_tenant_scoped`'s own canonical URL. Before this slice that was
  harmless (nothing checked canonical URL cross-occurrence); with Tier 2
  now live, two of the three incorrectly attached to the first's Job
  instead of each getting its own, breaking that test's own unrelated
  per-source-counter assertion. Fixed by giving each of the three postings
  its own distinct canonical URL. Also explicitly traced every other
  pre-existing test that constructs a `natural_key`/`job` pair to confirm
  none of them could be spuriously affected by the new Tier 2/3 branches —
  none share a canonical URL or tenant+requisition combination across
  otherwise-unrelated fixtures. Verified the parent-before-child lock
  reasoning holds specifically because acquiring the Job's `FOR UPDATE`
  lock blocks any concurrent cascading delete of that same row for the
  rest of the transaction — confirmed by the real two-transaction deletion
  test, not merely asserted in a docstring.
- Deviations/known limitations: none beyond those already disclosed in the
  approved amendment (Tier 4's deferral; `ambiguous_match` persistence and
  its evidence shape as a separate future slice; multiple-candidate
  failures are whole-run, not per-posting-isolated, until that future slice
  lands). `QueryPlanner`, `ProviderRegistry`, multi-source partial-success
  handling, live providers, Phase 3 normalization, API routes, and
  scheduling remain explicitly out of scope. `main` untouched throughout.
- STOP — awaiting Codex review. Do not begin `ambiguous_match`, Tier 4,
  `QueryPlanner`, `ProviderRegistry`, multi-source handling, live providers,
  normalization, APIs, scheduling, the workflow-automation/tooling slice, or
  modify/merge `main`.

### Work review

_Pending._

---
