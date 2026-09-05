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

### Work review

- Date/reviewer: 2026-09-05, Codex.
- Diff reviewed: `4db557c..cffe8a1` (`phase-2/closure`).
- Verdict: **Changes requested.** The architecture correction, four fixtures,
  and the two end-to-end identity scenarios are substantively correct. Both
  new tests pass independently, and the canonical routine verifier passes all
  9 checks with 1495 tests. No production-code, schema, migration, or fixture-
  semantics correction is requested.
- Findings:
  1. **Medium — the two new tests are not failure-safe despite the approved
     cleanup requirement.** In
     `test_two_distinct_tenants_sharing_source_job_id_produce_two_jobs`, the
     post-run global assertions at `tests/test_ingestion_pipeline.py:475-478`
     execute before either the resulting Job ids or raw-ingestion ids are
     captured; the latter are not captured until lines 497 and 527. In
     `test_null_tenant_natural_key_collision_resolves_to_one_occurrence`, the
     post-second-run assertions at lines 605-608 execute before the two raw ids
     are captured at line 641. If any of those assertions fails—as the
     adversarial mutation exercise itself demonstrated can happen—the `finally`
     cleanup lacks enough identifiers to remove all committed rows. Capture all
     cleanup identifiers immediately after each `pipeline.run()` and before any
     assertion, or use a before/after identity-scope snapshot whose cleanup does
     not depend on assertions. Audit both new tests end to end for this ordering.
  2. **Low — the NULL-tenant test does not prove the first half of its claimed
     exact counter transition.** It asserts run 2 and its attempt are
     `inserted=0, updated=1`, but never asserts run 1 and its attempt are
     `completed`, `discovered=1, inserted=1, updated=0` (and have the expected
     empty failure state). Add those first-run assertions after cleanup ids have
     been captured. This makes the documented insert-then-update proof complete.
- Exact requested correction: change only the affected test file and this
  handoff ledger unless a directly necessary test helper extraction is justified;
  make cleanup assertion-independent in both new tests and add exact first-run
  run/attempt assertions for the NULL-tenant case. Preserve the accepted fixture
  contents, product code, architecture wording, and ROADMAP closure-candidate
  status. Re-run the two focused tests, the relevant ingestion/identity suite,
  the canonical routine verifier, and an explicit before/after disposable-DB
  row-count check. Do not merge or declare Phase 2 complete pending re-review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-05, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-2/closure` for the two bounded findings from Iteration 1's
  `Work review` above. Base: commit `cffe8a1` plus the uncommitted review.
  Only the affected test file and this handoff ledger changed — no fixture
  content, product code, architecture wording, or ROADMAP closure-candidate
  status touched, per the user's explicit preservation instruction.
- Outcome, addressing each finding exactly:
  1. **Cleanup not failure-safe.** Audited both new tests end to end.
     `test_two_distinct_tenants_sharing_source_job_id_produce_two_jobs` now
     queries the run's `JobOccurrence`/`RawJobIngestion` rows and extends
     `job_ids`/`raw_ingestion_ids` immediately after `pipeline.run()`
     returns, before any assertion (previously deferred to lines 497/527,
     after the four global-count assertions).
     `test_null_tenant_natural_key_collision_resolves_to_one_occurrence` now
     captures run 1's raw-ingestion id immediately after run 1 (before its
     `first_seen_at`/`last_seen_at` assertions), and run 2's new raw-
     ingestion id immediately after run 2 (before any of the count/content
     assertions that follow) — using the same
     already-captured-ids-minus-new-rows pattern
     `test_two_run_natural_key_spine` established. Both tests' later
     assertions now read from data already captured for cleanup, not the
     other way around.
  2. **NULL-tenant test's first-run counters unproven.** Added an assertion
     block immediately after run 1's raw-ingestion id is captured: `run1`
     is `completed`, `jobs_discovered=1`, `jobs_inserted=1`,
     `jobs_updated=0`, `failures=[]`; its sole
     `CollectionRunProviderAttempt` is `completed`,
     `jobs_discovered=1`/`jobs_inserted=1`/`jobs_updated=0`, and
     `error_category`/`error_message` are both `None` (the "empty failure
     state" Codex requested). The existing run-2 `inserted=0, updated=1`
     assertions are unchanged, so the full insert-then-update transition is
     now proven end to end.
- Files changed: `backend/tests/test_ingestion_pipeline.py` (both tests'
  cleanup-capture ordering; new first-run assertion block in the
  NULL-tenant test), this handoff entry. No fixture, product code, migration,
  or other documentation file touched.
- Verification: the two focused tests directly (**2 passed**); the full
  relevant ingestion/identity suite (`test_ingestion_pipeline.py`,
  `test_ingestion_concurrency.py`, `test_ingestion_natural_key.py`,
  `test_job_occurrences.py`, `test_orchestrator.py`): **250 passed**;
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **9 steps PASS**, **1495 full-suite tests**, ~130-143s across reruns.
  `alembic heads` confirms `0017` remains the sole head; `git diff --stat
  origin/main -- migrations/` is empty; dev database (`jobgoblin`) confirmed
  unchanged at `0006`. Explicit disposable-database row-count check (`jobs`,
  `job_occurrences`, `raw_job_ingestions`, `collection_runs`,
  `collection_run_provider_attempts`, `identity_conflicts`, `users`,
  `user_jobs`): 0 before the suite, 0 after.
- Adversarial self-review (abbreviated, proportionate to Class R): re-broke
  both invariants exercised in Iteration 1's review (`_existing_occurrence_
  conditions()`'s `TENANT`-domain tenant filter removed; `NO_TENANT`-domain
  filter inverted) to prove finding 1's fix is actually load-bearing, not
  just finding 2's new assertions. (1) With the tenant filter removed,
  `test_two_distinct_tenants_...` still failed at the same assertion as
  before — but this time a fresh disposable-database row-count check
  immediately afterward confirmed **0 rows in every affected table**,
  proving the earlier-captured ids let `finally` clean up completely despite
  the failure (this is the exact scenario Codex's finding 1 said could leak
  rows before the fix). (2) With the `NO_TENANT` filter inverted, the second
  `pipeline.run()` call itself raised a real `UniqueViolationError` (as
  before) rather than failing at an assertion; because the raising call
  never returns, its own internally-written `CollectionRun`/attempt/raw rows
  cannot be captured by any id-after-return pattern — a pre-existing
  structural property shared by every test in this file that calls
  `pipeline.run()` once per line, not a regression from this correction and
  not one of Codex's two findings. The resulting one leaked row per table
  was identified and deleted, and a fresh row-count check confirmed 0 before
  the final verification run above. Both temporary breaks were then reverted
  (`git diff --stat -- backend/app/ingestion/persistence.py` empty
  afterward), and the two focused tests re-confirmed passing.
- Deviations/known limitations: the pre-existing `alembic check`
  substitution (unrelated, recorded previously); the structural
  raise-before-return cleanup limitation noted above, which affects the
  whole file, not just these two tests, and was left unmodified as out of
  scope for this bounded correction.
- STOP — awaiting Codex re-review. Do not merge, begin Phase 3, contact
  providers, add production behavior, or create a migration.

### Work review

- Date/reviewer: 2026-09-05, Codex.
- Diff reviewed: `cffe8a1..d09ac00` on `phase-2/closure`.
- Verdict: **Approved.** Both bounded findings from Iteration 1 are closed,
  and no further corrections are required.
- Independent review: inspected both corrected tests and the two-iteration
  ledger rotation. In the distinct-tenant case, the run id, both resulting
  Job ids, and both raw-ingestion ids are now captured before the first
  post-run assertion. In the NULL-tenant case, the first run's Job/raw ids
  and the second run's newly-created raw id are captured before their
  respective assertions. The first run and its sole provider attempt now
  explicitly prove `completed`, `discovered=1`, `inserted=1`, `updated=0`,
  and an empty failure/error state, completing the insert-then-update matrix.
- Verification: reran the two corrected tests directly (**2 passed**) and
  independently ran `python scripts/verify.py --level routine`: all **9
  checks PASS**, including Ruff, mypy, repository/diff checks, disposable-DB
  safety/reachability, **1495 full-suite tests**, and temporary-directory
  cleanup. No product code, fixture content, schema, migration, architecture,
  or ROADMAP semantics changed in this correction.
- Exit-gate disposition: the reviewed closure candidate satisfies the bounded
  Phase 2 exit-gate corrections. Phase 2 may be declared complete after this
  approved branch is merged into `main` and the normal post-merge checks pass.
  Tier 4 remains deliberately deferred and is not represented as implemented.
- Exact requested corrections: none.
- STOP — do not merge to `main` or begin Phase 3 until the user explicitly
  authorizes that action.
