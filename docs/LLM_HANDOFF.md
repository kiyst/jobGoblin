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

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `5f65ec0` (no findings). Per user authorization, `phase-4/greenhouse-live-proof`
was merged into `main` with a normal merge commit (`907b3f0`; `--no-ff`, no
squash/rebase/force-push) and pushed. `main`/`origin/main` are both now at `907b3f0`.
Verified: feature branch was clean and pushed at `5f65ec0`, and `main`/`origin/main`
were still at `4cb8492` immediately before the merge; `main` has zero content diff
against the feature branch (`git diff main phase-4/greenhouse-live-proof --stat`
empty); migration `0017` remains the sole Alembic head; `python -m scripts.check_repo`
exited `0`; `git diff --check` was clean; working tree clean throughout. No Greenhouse
request and no real `CREATE`/`DROP DATABASE` invocation were made during the merge.

**Rollback boundary:** reverting `907b3f0` (a single merge commit) restores `main` to
`4cb8492` exactly — no schema/migration exists in this slice to downgrade, and no data
migration accompanies it. This merges the Greenhouse live-to-disposable-database
ingestion proof only (`backend/scripts/live_proof_greenhouse_ingestion.py`, its offline
test file, `backend/tests/test_db_safety.py`, the narrow
`assert_safe_for_local_destructive_lifecycle` addition to
`backend/scripts/db_safety.py`, and the ADR 0004 identity-label addendum) — it does
**not** add a production `DiscoveryProvider` adapter, `QueryPlanner`/`ProviderRegistry`
integration, database writes, scheduling, Phase 3 normalization, or any other product
change, all of which remain not started and are not authorized by this merge.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-31, Codex acting as the user-authorized implementer. Class R
  tooling slice on `codex/tooling-safe-compaction`, based on clean
  `main@10b9432`. Outcome: safe Claude Code compaction policy plus automatic,
  credential-free recovery snapshots around built-in manual/auto compaction.
- Added root `CLAUDE.md` with durable compact instructions: preserve current
  authorization, Git state, active slice/verdict, unresolved decisions, safety
  invariants, verification, external side effects, rollback boundaries, and recovery
  document pointers; discard superseded conversation detail recoverable from Git.
- Added project hooks in `.claude/settings.json` and
  `.claude/hooks/compact_checkpoint.py`:
  - `PreCompact(manual|auto)` atomically snapshots only Git refs/cleanliness,
    trigger, classification, and documentation pointers under ignored
    `.claude/runtime/`.
  - `SessionStart(compact)` injects that checkpoint after compaction and requires
    reconciliation against current Git/docs before any state-changing action.
  - Hooks never store transcript content, compacted summaries, environment values,
    database URLs, credentials, or source-file contents; they perform no network or
    database operation and never block emergency auto-compaction.
- Safe-moment policy: clean synchronized `main` after a verified merge-record commit
  is optimal; a clean pushed feature branch stopped at committed `Work done`/
  `Work review` is secondary/recoverable. Proactive manual compaction is not requested
  amid uncommitted work, running verification, external/destructive activity,
  incomplete handoff writing, or unresolved corrections. Claude Code exposes no safe
  project hook to force `/compact` at a semantic milestone, so this slice deliberately
  does not launch a nested Claude process or lower the automatic threshold.
- Added nine offline tests for optimal/fail-closed classification, pushed-feature and
  dirty-tree states, credential/transcript exclusion, atomic write/cleanup, and restore
  output. A real hook simulation correctly classified this dirty implementation branch
  as unsafe for proactive compaction and restored the snapshot; no secret or external
  state was accessed.
- Verification: genuine external
  `python scripts/verify.py --level routine --focus tests/test_compact_checkpoint.py`
  completed all **10 steps PASS**: Ruff format/check, mypy, repository checker,
  `git diff --check`, database URL safety/reachability, **9 focused tests**, **1379
  full-suite tests**, and temporary-directory cleanup in 129.86s. Settings JSON parsed
  successfully; direct pre/restore hook simulation succeeded.
- Files changed: `CLAUDE.md`, `.claude/settings.json`,
  `.claude/hooks/compact_checkpoint.py`, `.gitignore`, `docs/LLM_WORKFLOW.md`,
  `backend/tests/test_compact_checkpoint.py`, and this handoff entry. No product,
  schema, migration, provider, ingestion, database, or network behavior changed.
- STOP — awaiting independent review. Do not merge to `main`, begin another product
  slice, or treat a compacted summary as new authorization.

### Work review

_Pending._
