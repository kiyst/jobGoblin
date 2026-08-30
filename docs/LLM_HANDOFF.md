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
  `phase-2/tier2-tier3-identity-attachment` for the three bounded findings in
  review commit `54518bd` (`988dcd1..54518bd`). Base `988dcd1`. Addresses
  exactly Findings 1-3 from Iteration 1's `Work review`; every
  otherwise-approved Tier-2/Tier-3 behavior (precedence, candidate
  revalidation, `ATTACHED -> jobs_updated`, three-effect rollback boundary,
  existing-index reuse, Tier-4 deferral) is unchanged.
- Outcome, addressing each finding exactly:
  1. **Medium — Tier 1's found branch now genuinely locks parent-before-
     child.** `_select_existing` (always `FOR UPDATE`) is replaced by
     `_existing_occurrence_query` (unlocked). `upsert_job_occurrence`'s found
     branch now: probes the existing occurrence unlocked -> pauses at the new
     `_before_tier1_parent_lock()` test seam -> locks the parent `Job`
     `FOR UPDATE` (raising `CandidateResolutionUnstableError` if it is gone,
     never a bare assertion) -> re-runs the identical domain query, now
     `FOR UPDATE`, and fails closed with the same error if the occurrence is
     gone or its `job_id` no longer matches the just-locked parent. This
     removes the opposite-order deadlock surface Codex identified: any
     future Job-deletion writer that also locks parent-before-child now only
     ever contends for the parent first, never a mix of orders. Added
     `test_tier1_reobservation_vs_parent_deletion_uses_real_transactions_no_deadlock`:
     two real, separately-committed PostgreSQL transactions (via
     `_before_tier1_parent_lock` + `asyncio.Event`s, mirroring the existing
     Tier-2/3 deletion-race test's shape) — transaction A pauses right
     before the parent lock, transaction B deletes and commits that same
     Job, transaction A resumes and fails closed with
     `CandidateResolutionUnstableError`; bounded by a 10s timeout so a
     regression to the old order fails the test rather than hanging it.
     Updated `upsert_job_occurrence`'s own docstring and ADR 0004's Phase-2
     notes to describe the corrected, now-global parent-before-child
     discipline and why the old order was unsafe.
  2. **Low — hardened both real-transaction concurrency tests.** In
     `test_candidate_deleted_between_discovery_and_lock_uses_real_transactions`,
     `_delete_candidate()`'s `resume.set()` moved into a `finally` block so a
     failed delete can never leave the paired task waiting forever; the
     coordinated `asyncio.gather` is now wrapped in `asyncio.wait_for(...,
     timeout=10)`; `existing_job_id` is now included in `job_ids` for
     best-effort cleanup. In `test_concurrent_tier2_attach_produces_no_duplicate_job`
     (`test_ingestion_concurrency.py`), each `raw_id` is now appended to the
     shared `raw_ids` list immediately after `_write_fetched_row` returns —
     before `persist_posting` runs and could raise — so a regression can no
     longer leak an uncleaned raw row into later tests.
  3. **Low — corrected the focused-test count.** The three named files
     collect and pass **53** tests on this branch (52 at `988dcd1`, the
     count Codex verified independently, plus the one new Tier-1-vs-parent-
     deletion test added for Finding 1). Iteration 1's own entries above are
     left unedited per the two-iteration rotation rule's "do not rewrite the
     other LLM's entry" — the 63 previously reported there was simply wrong
     and is called out, not silently replaced.
- Files changed: `backend/app/ingestion/persistence.py`;
  `backend/tests/test_ingestion_pipeline.py`;
  `backend/tests/test_ingestion_concurrency.py`;
  `docs/DECISIONS/0004-scoped-deterministic-identity.md`; this handoff. No
  migration; no change to `natural_key.py` or `pipeline.py`.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 73 source files.
  - Focused (`test_ingestion_pipeline.py` + `test_ingestion_concurrency.py`
    + `test_ingestion_natural_key.py`) -> **53 passed** (53 collected;
    corrected count, +1 over the 52 Codex verified at `988dcd1`).
  - Full suite with a workspace-local `--basetemp` -> **1175 passed** (was
    1174).
  - The three real-transaction concurrency tests (the two pre-existing
    genuine races plus the new Tier-1-vs-parent-deletion one) rerun 5x each
    in a stress loop -> stable, no flakiness, no timeouts.
  - `alembic check` (against `jobgoblin_test`) -> `No new upgrade operations
    detected`; `alembic heads` -> `0017 (head)`, unchanged.
  - `\d`-equivalent index query against `jobgoblin_test` -> confirmed
    `ix_job_occurrences_tenant_requisition_lookup` still
    `btree (provider, source, source_tenant_id, requisition_id_raw)`,
    unchanged.
  - Development database (`alembic current`, default `DATABASE_URL`) ->
    `0006`, unchanged.
  - `python scripts/check_repo.py` -> exit 0, zero findings.
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - Table-count queries against `jobgoblin_test` after the full run ->
    every ingestion-related table at 0 rows; no leaked test data.
- Adversarial self-review (fresh read of the complete corrected diff before
  this entry): re-derived the deadlock argument independently (parent-
  before-child on both sides of any future concurrent delete removes the
  opposite-order cycle) rather than trusting the prior entry's now-known-
  wrong version of that same claim; confirmed no other test constructs a
  `natural_key`/`job` pair that could be spuriously affected by the
  reordered found-branch queries (the full suite passing at 1175 is
  consistent with, not a substitute for, that trace); confirmed
  `CandidateResolutionUnstableError`'s docstring broadening (now shared by
  Tier 1 and Tier 2/3) does not change any existing `pytest.raises`/
  `isinstance` assertion, since none of them match on the exception's
  message text. Found no further issues beyond the three findings addressed
  above.
- Deviations/known limitations: none beyond those already disclosed in
  Iteration 1 (Tier 4's deferral; `ambiguous_match` persistence and its
  evidence shape as a separate future slice; multiple-candidate failures
  are whole-run, not per-posting-isolated, until that future slice lands).
  `QueryPlanner`, `ProviderRegistry`, multi-source partial-success handling,
  live providers, Phase 3 normalization, API routes, scheduling, and the
  workflow-automation/tooling slice remain explicitly out of scope. `main`
  untouched throughout.
- STOP — awaiting Codex re-review. Do not begin `ambiguous_match`, Tier 4,
  `QueryPlanner`, `ProviderRegistry`, multi-source handling, live providers,
  normalization, APIs, scheduling, the workflow-automation/tooling slice, or
  modify/merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Correction diff reviewed:
  `54518bd..272afb8` on
  `phase-2/tier2-tier3-identity-attachment`.
- Findings 2 and 3 from review commit `54518bd` are closed: both coordinated
  deletion tests now release their paused peer in `finally`, use a bounded
  wait, and retain setup ids for best-effort cleanup; the concurrent-attach
  test records raw ids before persistence can fail; the new entry accurately
  reports **53** focused tests without rewriting the historical entry.
- Finding 1 is directionally corrected: Tier 1 no longer locks the occurrence
  before its parent, the real parent-deletion race is bounded and passes, and
  the bare parent assertion is gone. One revalidation defect remains:
  1. **Medium — Tier 1's association recheck can read the session's stale ORM
     identity-map value instead of the freshly locked database value.** The
     initial unlocked `_existing_occurrence_query()` loads a full
     `JobOccurrence` entity. The later locked execution of the same ORM query
     can return that already-loaded instance without refreshing its loaded
     `job_id`. If the same occurrence row is reassociated between probe and
     lock, SQL can select the row while `occurrence.job_id` still contains the
     old cached parent id, allowing the new equality check to pass and the
     method to return/update the wrong parent association. Make the initial
     probe select only fresh scalar identity values (`id`, `job_id`) so it
     does not seed the ORM identity map, then load the entity only in the
     post-parent-lock `FOR UPDATE` query; alternatively force an explicit
     database refresh with equivalent guarantees. Add a regression that
     changes the occurrence's `job_id` in a separately committed transaction
     at the test seam and proves `CandidateResolutionUnstableError`, no stale
     parent update, no raw transition, and failure-safe cleanup. This test is
     defense-in-depth for the promised revalidation; supported future writers
     must still obey the documented advisory/row-lock discipline.
- Independent proportionate verification: repository checker exit 0; Ruff
  format/check clean; mypy clean across **73 source files**; the named focused
  suite **53 passed**; `git diff --check` clean; working tree clean. Full-suite
  and schema results reported in `Work done` were not repeated because this
  remaining correction is isolated before approval.
- **Verdict: changes requested.** Make only the scalar-probe/fresh-entity
  revalidation correction and its regression test, update affected wording,
  run proportionate verification, append a concise `Work done`, commit and
  push, then stop for re-review. Do not merge `main`, begin another product
  slice, or start workflow-automation tooling.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/tier2-tier3-identity-attachment` for the single bounded finding in
  review commit `6eadd00` (`272afb8..6eadd00`). Base `272afb8`. Addresses
  exactly Finding 1 from Iteration 1's `Work review`; every otherwise-approved
  Tier-2/Tier-3 and Tier-1 behavior (precedence, candidate revalidation,
  `ATTACHED -> jobs_updated`, three-effect rollback boundary, existing-index
  reuse, Tier-4 deferral, parent-before-child lock order) is unchanged.
- Outcome, addressing the finding exactly:
  1. **Medium — Tier 1's initial probe no longer seeds the ORM identity map.**
     `_existing_occurrence_query()` (full entity, `FOR UPDATE`-chainable) is
     unchanged in shape but its domain-filter conditions are now shared via a
     new `_existing_occurrence_conditions()` helper. A new
     `_existing_occurrence_identity_query()` selects only the bare
     `JobOccurrence.id`/`job_id` scalar columns — never the ORM entity — and
     is what `upsert_job_occurrence`'s found branch now uses for the initial,
     unlocked probe. Because that probe never touches the identity map, the
     later `FOR UPDATE` load of `_existing_occurrence_query()` is always that
     row's *first* load into the session, so its `job_id` is guaranteed fresh
     from the database rather than a value cached from before a concurrent
     reassociation. The revalidation check (`occurrence.id`/`job_id` vs. the
     scalar probe) is otherwise unchanged — still fails closed with
     `CandidateResolutionUnstableError`, never a bare assertion. Added
     `test_tier1_reassociation_between_probe_and_lock_is_detected_not_stale`:
     two real, separately-committed PostgreSQL transactions (via
     `_before_tier1_parent_lock` + `asyncio.Event`s, mirroring the existing
     Tier-1-vs-parent-deletion test's shape) — transaction A pauses right
     after the scalar probe, transaction B reassigns the same occurrence's
     `job_id` to a second, independently existing Job and commits,
     transaction A resumes, locks the *original* parent (which still exists),
     loads the occurrence fresh, and fails closed with
     `CandidateResolutionUnstableError` before any mutation. Proved this is a
     genuine regression test, not vacuous, by temporarily reverting the probe
     to the full-entity query and confirming the test fails (it returned
     `UpsertKind.UPDATED` instead of raising) before restoring the fix and
     re-confirming green. Also proves neither Job's `last_seen_at` advances
     and the raw row stays `fetched`/unlinked. Updated
     `upsert_job_occurrence`'s docstring and ADR 0004's Phase-2 notes to
     describe the identity-map hazard and the scalar-probe correction.
- Files changed: `backend/app/ingestion/persistence.py`;
  `backend/tests/test_ingestion_pipeline.py`;
  `docs/DECISIONS/0004-scoped-deterministic-identity.md`; this handoff. No
  migration; no change to `natural_key.py`, `pipeline.py`, or
  `test_ingestion_concurrency.py`.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 73 source files.
  - Focused (`test_ingestion_pipeline.py` + `test_ingestion_concurrency.py`
    + `test_ingestion_natural_key.py`) -> **54 passed** (53 at `272afb8`, +1
    new reassociation regression).
  - Full suite with a workspace-local `--basetemp` -> **1176 passed** (was
    1175).
  - The four real-transaction concurrency tests (both pre-existing genuine
    races, the Tier-1-vs-parent-deletion one, and the new reassociation one)
    rerun 5x each in a stress loop -> stable, no flakiness, no timeouts.
  - `alembic check` (against `jobgoblin_test`) -> `No new upgrade operations
    detected`.
  - Development database (`alembic current`, default `DATABASE_URL`) ->
    `0006`, unchanged.
  - `python scripts/check_repo.py` -> exit 0, zero findings.
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - Table-count queries against `jobgoblin_test` after the full run, and
    after the deliberate revert-and-fail run below -> every ingestion-related
    table at 0 rows both times; no leaked test data, including on the
    intentional failure path.
- Adversarial self-review (fresh read of the complete corrected diff before
  this entry): rather than only reasoning about the fix, empirically proved
  the new test is a genuine regression guard by reverting the probe to
  `_existing_occurrence_query()` (loading the full entity) and rerunning it
  in isolation — it failed with the stale `job_id` silently accepted
  (`UpsertKind.UPDATED` returned instead of the exception), and its own
  `finally`-based cleanup still left zero leaked rows even on that induced
  failure; then restored the fix and reconfirmed green. Confirmed
  `_discover_candidates` (Tier 2/3's own candidate discovery) has no
  analogous defect: it already selects only the scalar `job_id` column and
  never loads a `JobOccurrence` entity before the candidate's `Job` lock, so
  Tier 2/3's `_attach_to_candidate` was never exposed to this identity-map
  hazard in the first place. Confirmed the `Job` `FOR UPDATE` load in Tier
  1's found branch is likewise always a first load (nothing earlier in that
  transaction touches `Job` via the ORM). Found no further issues beyond the
  one finding addressed above.
- Deviations/known limitations: none beyond those already disclosed in
  Iteration 1 (Tier 4's deferral; `ambiguous_match` persistence and its
  evidence shape as a separate future slice; multiple-candidate failures are
  whole-run, not per-posting-isolated, until that future slice lands).
  `QueryPlanner`, `ProviderRegistry`, multi-source partial-success handling,
  live providers, Phase 3 normalization, API routes, scheduling, and the
  workflow-automation/tooling slice remain explicitly out of scope. `main`
  untouched throughout.
- STOP — awaiting Codex re-review. Do not begin `ambiguous_match`, Tier 4,
  `QueryPlanner`, `ProviderRegistry`, multi-source handling, live providers,
  normalization, APIs, scheduling, the workflow-automation/tooling slice, or
  modify/merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Correction diff reviewed:
  `6eadd00..370af23` on
  `phase-2/tier2-tier3-identity-attachment`.
- The remaining finding from review commit `6eadd00` is closed:
  `_existing_occurrence_identity_query()` now probes only bare `id`/`job_id`
  columns and therefore cannot seed SQLAlchemy's ORM identity map. After the
  parent `Job` lock, `_existing_occurrence_query().with_for_update()` performs
  the entity's first session load and compares its fresh database `id` and
  `job_id` against the scalar probe before any mutation. Shared conditions
  keep the two query shapes aligned.
- The new two-transaction regression pauses after the scalar probe, commits a
  real reassociation to a second parent, and proves
  `CandidateResolutionUnstableError`, unchanged observational state on both
  Jobs and the occurrence, and a fetched/unlinked raw row. Its timeout,
  `finally` release, and cleanup cover the prior test-hygiene requirements.
- Independent proportionate verification: repository checker exit 0; Ruff
  format/check clean; mypy clean across **73 source files**; focused suite
  **54 passed**; `alembic check` against `jobgoblin_test` reports no drift;
  `git diff --check` clean; working tree clean. The correction is localized,
  so the independently reported full-suite **1176 passed** result was not
  redundantly repeated in this re-review.
- Findings: none.
- **Verdict: approved.** The Tier-2/Tier-3 cross-occurrence identity-
  attachment slice and all correction passes are accepted. STOP — do not
  merge this branch into `main`, begin `ambiguous_match`/Tier 4 or another
  product slice, or start workflow-automation tooling until the user
  explicitly authorizes the next action.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `b235d18` (no findings). Per user authorization,
`phase-2/tier2-tier3-identity-attachment` was merged into `main` with a normal
merge commit (`1f4f787`; `--no-ff`, no squash/rebase/force-push) and pushed.
`main`/`origin/main` are both now at `1f4f787`. Verified: feature branch was
clean and pushed at `b235d18` and `main`/`origin/main` were still at `bd59a14`
immediately before the merge; `main` has zero content diff against the feature
branch (`git diff main phase-2/tier2-tier3-identity-attachment --stat` empty);
migration `0017` remains the sole Alembic head; `python
backend/scripts/check_repo.py` exits 0 with zero findings; `git diff --check`
clean; development database reconfirmed at `0006`; working tree clean.

**Rollback boundary:** reverting `1f4f787` (a single merge commit) restores
`main` to `bd59a14` exactly — no schema/migration exists in this slice to
downgrade, and no data migration accompanies it (Tier-3's supporting index,
`ix_job_occurrences_tenant_requisition_lookup`, already existed before this
slice). This merges Phase 2's fourth vertical slice only (Tier-2/Tier-3
cross-occurrence identity attachment: mutually exclusive Tier-2/Tier-3
precedence, single-pass fail-closed candidate resolution,
`AmbiguousIdentityMatchError`/`CandidateResolutionUnstableError`, the new
canonical-URL/tenant-requisition advisory-lock domain, `UpsertKind.ATTACHED`,
the corrected global parent-before-child lock discipline including Tier 1's
own found-branch fix, and the scalar-probe fresh-entity revalidation) — it
does **not** complete Phase 2. `ambiguous_match` persistence, Tier 4, the
company-resolution prerequisite it depends on, `QueryPlanner`,
`ProviderRegistry`, multi-source partial-success handling, live providers,
Phase 3 normalization, API routes, scheduling, and the workflow-automation
tooling slice all remain not started and are not authorized by this merge.
