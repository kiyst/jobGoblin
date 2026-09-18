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

- Date/agent: 2026-09-13, Claude Code (Sonnet 5). Risk class H (process/
  security-relevant tooling — touches `.claude/hooks/*.py` and every
  workflow-governing document/checker; "when uncertain, use the
  higher-risk class"). Base `B` -> candidate `C`: `66202c23facff6bd33d8f
  624e327cabdd40708b4` -> this commit; branch
  `tooling/workflow-v3.2-activation`. Workflow v3.2 activation per the
  frozen contract authorized across this session's proposal/amendment
  rounds (see `docs/DECISIONS/0009-workflow-v3.2-activation.md`), which
  supersedes and consolidates that entire negotiation into one accepted
  design. `slice_kind: tooling`. `slice_id:
  2026-09-13-workflow-v3-2-activation-66202c2`.
- Outcome: new `backend/scripts/verification_worktree.py`,
  `verification_receipts.py`, `verification_scope.py`,
  `verification_coordinator.py`, `migration_matrix.py`, `check_review.py`
  (+ their test files); schema-v2 rewrite of `check_handoff.py` (+
  rewritten `test_check_handoff.py`); `verify.py` gains `--gate
  {fast,final,docs}`, `--witness`, `--emit-step-json`, and a `contract
  mutation witnesses` step; `.claude/hooks/compact_checkpoint.py`'s
  `WORKFLOW_VERSION` -> `"v3.2"`; `CLAUDE.md`/`docs/LLM_WORKFLOW.md`
  updated (v3.1 pilot section marked closed/historical, new "Workflow
  v3.2" section added); new ADR 0009; `backend/pyproject.toml` gains a
  narrow mypy override for `asyncpg` (no stubs, used directly by
  `migration_matrix.py`).
- Adversarial/implementation self-review found and fixed, before this
  entry was written: (1) the generated fresh-database name must itself
  contain `"test"` or the *existing* `assert_is_disposable_test_database`
  guard rejects it for the wrong reason; (2) the derived admin
  (`postgres`) connection must **not** be run through the full
  `assert_safe_for_local_destructive_lifecycle` (its name correctly never
  contains `"test"`) — split into a narrower host/production-only check
  reusing `db_safety`'s own host allowlist, never a second copy; (3) a
  `--docs-only`/`--gate` argparse bug accepted `--docs-only` with no
  `--gate` at all; (4) `check_handoff.main()`'s use of mutable
  module-level defaults as function defaults meant monkeypatching
  `HANDOFF_PATH`/`REPO_ROOT` in tests silently had no effect — fixed by
  referencing the module globals inside the function body. Each was
  caught by a genuinely failing test, fixed, and re-verified.
- Files changed (new): `backend/scripts/{verification_worktree,
  verification_receipts,verification_scope,verification_coordinator,
  migration_matrix,check_review}.py`;
  `backend/tests/test_{verification_worktree,verification_receipts,
  verification_scope,verification_coordinator,migration_matrix,
  check_review}.py`; `docs/DECISIONS/0009-workflow-v3.2-activation.md`.
  Rewritten: `backend/scripts/check_handoff.py`,
  `backend/scripts/verify.py`, `backend/tests/test_check_handoff.py`,
  `backend/tests/test_verify.py` (obsolete v3.1-pilot-schema tests
  replaced, not merely patched). Edited: `.claude/hooks/
  compact_checkpoint.py`, `CLAUDE.md`, `docs/LLM_WORKFLOW.md`,
  `backend/pyproject.toml`, this handoff entry. No production parser
  (`app/normalization/*`) touched; no migration/model file touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass
  (139 source files, backend + `.claude/hooks`). Full pytest suite:
  **2431 passed** (up from 2323 — 108 new/replacing tests). All 34
  mutation witnesses pass unmodified
  (`python -m scripts.contract_mutation_witnesses`). `python -m
  scripts.check_repo` exits 0.
- Database-lifecycle evidence (real, against the local disposable
  Postgres — never the development database beyond a read-only `SELECT
  current_database()`/state check): `test_migration_matrix.py`'s 13
  tests genuinely create and drop a real, uniquely-named disposable
  database via a derived admin connection, cover production/remote-host/
  pre-existing-name/failed-before-create/acknowledgement-lost-after-
  create, and confirm a pre-existing database under a collided name is
  never touched. `capture_development_state` fails closed (raises,
  never skips) when the development database is unreachable or its
  state can't be read.
- Deviations/known limitations, as of the original candidate (superseded
  below): (1) `check_review.py`'s merge/post-merge modes validated
  parent shape and content identity but did not yet implement the
  outer-launcher/subprocess-reexecution design or a full per-transition
  byte-identical-historical-text diff validator. (2) `migration_matrix.py`
  was implemented and tested but not yet wired into `verify.py`/the
  coordinator as an executable step. (3) `--compat-v3.1` did not yet
  exist as a distinct, named CLI mode.

#### Correction round 1 (Sol review: Changes requested)

- **Supersedes candidate `C` = `16ec8b35b58ece71a9f83c4cc380d97b424a01ed`
  and publication `A` = `c1c2cc1b4f7e2dda5ea911afbd859086bc7f3d99`.** The
  receipt published there
  (`docs/verification-receipts/16ec8b35b58ece71a9f83c4cc380d97b424a01ed/
  885fbb02-2bdf-49a8-a1ef-639e53b27df2.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C`/`A` themselves are left exactly as pushed, per Git
  gates — never amended or rewritten.
- Implements every required correction: `check_review.py` now has closed
  primary/escalation review schemas, exact `C -> A -> R` cross-
  references, byte-identical `C..A`/`A..R` transition validation (with
  fault-injection tests for a smuggled edit, a historical-iteration
  rewrite, and a second smuggled receipt), a distinct
  `check_merge_eligibility` (record validity vs. merge eligibility),
  explicit `Q` validation, an outer detached-checkout launcher that
  re-executes the *target commit's own* `check_review.py` as a
  subprocess (proven against this project's real editable-install
  precedence, not merely asserted), and `validate_published` (full
  post-merge re-derivation, never trusting the artifact's own claims).
  `verification_receipts.compute_approval_eligible` now deep-validates
  required step names, a genuinely positive numeric full-suite count,
  and a genuinely positive numeric witness-passed count with zero
  failures — the reproduced negative case (empty steps, every execution
  group `not_run`) is a dedicated test and is correctly ineligible.
  `verification_coordinator.py` now fetches `origin/main` and enforces
  `base_sha == origin/main` plus ancestry plus `slice_id`-suffix
  consistency *before* anything else runs; computes the
  `base_sha..candidate_sha` diff and required coverage *before* creating
  any worktree (`verification_scope.compute_required_coverage`); enforces
  forced-final categories; safely removes only its own stale
  `coordinator-*` scratch directories on startup; and wraps every stage
  in `finally` so cache/worktree/run-directory cleanup is always
  attempted and a cleanup failure blocks receipt emission. The migration
  matrix (`migration_matrix.run_full_matrix`) is now a real `verify.py`
  step (`--migration-required`), with fault-injection tests for a
  failure after fresh-database creation and for direct-target-validation
  failure (both proven to still clean up correctly — the latter exposed
  and fixed a real gap where `provision_fresh_database` could leave a
  database behind on that specific failure path). `verify.py` gains an
  explicit, separately named `--compat-v3.1` flag.
- Verification (this correction round): `ruff format --check`/
  `ruff check`/`mypy` clean (139 source files). Full pytest suite:
  **2480 passed**. All 34 mutation witnesses pass unmodified.
  `check_repo.py` exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 2 (Sol review: Changes requested)

- **Supersedes candidate `C2` = `854be7c46de3d26592e145f6cdad23f9f7b5fc6b`
  and publication `A2` = `c1f612fd50eb3291255d888ecdba03dce8cd8c5c`.** The
  receipt published there
  (`docs/verification-receipts/854be7c46de3d26592e145f6cdad23f9f7b5fc6b/
  8dc185bf-1dc6-4798-a20e-fb1218fd1c03.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C2`/`A2` themselves are left exactly as pushed, per Git
  gates — never amended or rewritten.
- Implements every required correction from Sol's second review: (1)
  `verification_receipts.py`'s receipt schema is now fully recursively
  closed/typed — every nested object (`coordinator`, `steps[]`,
  `full_suite`/`focused_tests`/`mutation_witnesses`, `migration_matrix`,
  `cleanup`, `dependency_and_config_inputs[]`, `environment_descriptor`)
  rejects an unrecognized field, duplicate step names are rejected, and a
  "ran" suite/witness summary must bind to a corresponding step that
  exists exactly once with status `PASS` — with dedicated regression
  tests for an unrecognized field nested at every level and for the
  binding failure itself. (2) `check_review.py` now parses and
  structurally re-validates the *published* (`A`) `workflow-metadata`
  block during `C -> A -> R` validation (reusing `check_handoff.py`'s own
  validator), cross-checks `slice_id`/`risk_class`/`candidate_sha`/
  `gate`/`receipt_id`/`receipt_path` against the review metadata,
  requires the published `base_sha` to be a genuine ancestor of the
  candidate, and cross-checks the receipt's own `slice_id`/`risk_class`/
  `base_sha` against the published block. The Sol Medium primary-
  reviewer requirement now triggers for every executable
  (`parser`/`tooling`) slice, not only `risk_class: H`. A `gate: docs`
  receipt is merge-eligible only when the bound published slice is
  genuinely `slice_kind: docs`. (3) Post-merge artifact validation is now
  deep: `_validate_post_merge_artifact_schema` reuses
  `verification_receipts.py`'s own nested validators for
  `coordinator`/`steps`/`full_suite`/`mutation_witnesses`/
  `migration_matrix`/`cleanup`/`environment_descriptor`; a new
  `_validate_post_merge_artifact_evidence` requires a genuinely positive
  full-suite count, genuinely positive passing witnesses, no `FAIL`
  step, passing cleanup, and (when triggered) a passing migration
  matrix; `validate_published` now cross-checks the artifact's
  `base_sha`/`slice_id`/`original_receipt_id`/`original_receipt_path`
  against the independently recomputed chain, then re-reads and
  re-validates the original receipt at `M` itself and cross-checks its
  content against the artifact's claims. A new
  `validate_m_to_q_transition` restricts `Q`'s optional handoff change to
  a pure, at-most-once append, mirroring `validate_a_to_r_transition`.
  (4) `migration_matrix.py` now captures a real `DevelopmentState`
  (Alembic revision + a schema fingerprint over `information_schema.
  columns`) before/after, and a real, distinct PostgreSQL server version
  (`query_postgresql_server_version`); `provision_fresh_database`'s
  direct-target verification now cleans up on a raised exception, not
  only on a wrong-name return. (5) `verify.py --gate fast` now genuinely
  omits the full suite (the `full pytest suite` step is only appended
  when `gate != "fast"`); `--gate final` and the ungated compat profile
  still always include it. (6) A new `verification_lock.py` provides a
  cross-platform, genuinely non-blocking exclusive advisory file lock
  (`msvcrt.locking` / `fcntl.flock`). `verification_coordinator.py` now
  holds this lock for a run's entire lifetime and only removes a stale
  `coordinator-*` scratch directory when it can itself acquire that
  directory's lock (proving no live owner) — proven with a genuine
  concurrent-subprocess regression test that a live run is never cleaned
  up by another. The detached-review-launcher's cleanup
  (`run_via_detached_checkout`) now fails closed on a worktree-teardown
  failure and verifies no residual worktree/run directory remains,
  instead of silently swallowing the error.
- Real bug found and fixed while implementing finding (1) above (not
  itself one of Sol's findings): the real `verify.py` never included
  `guard_refs` in its `mutation_witnesses` step-JSON payload, so the
  stricter, now-required schema binding would have made every real
  receipt with `mutation_witnesses.status: "ran"` fail validation. Fixed
  in `mutation_witnesses_step`/`_build_steps`/`_write_step_json` (the
  whole-registry run's actual per-guard `PASS`/`FAIL` lines are now
  parsed to populate it); proven by a fixture that previously omitted it
  now failing until fixed.
- Files changed: `backend/scripts/{check_review,migration_matrix,
  verification_coordinator,verification_receipts,verify}.py` (edited);
  `backend/scripts/verification_lock.py` (new);
  `backend/tests/test_{check_review,migration_matrix,
  verification_coordinator,verification_receipts,verify}.py` (edited);
  `backend/tests/test_verification_lock.py` (new). No production parser
  (`app/normalization/*`) touched; no migration/model file touched.
- Verification (this correction round): `ruff format --check`/
  `ruff check`/`mypy` clean (158 source files, backend + `.claude/hooks`).
  Full pytest suite: **2531 passed**. All 34 mutation witnesses pass
  unmodified. `check_repo.py` exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 3 (Sol review: Changes requested)

- **Supersedes candidate `C3` = `ca7e4233ba880fb8e25b6019a575caafef9829f6`
  and publication `A3` = `081f6f7ddd9960524a999c662fa677aa1338886a`.** The
  receipt published there
  (`docs/verification-receipts/ca7e4233ba880fb8e25b6019a575caafef9829f6/
  94b13ec0-9327-46fa-aff6-f228c92e9059.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C3`/`A3` themselves are left exactly as pushed, per Git
  gates — never amended or rewritten.
- Implements every required correction from Sol's third review: (1)
  `check_review.py` now independently recomputes `B..C` affected-surface
  coverage and migration triggering using this checkout's own
  `verification_scope` module (never the reviewer's possibly-stale
  in-process copy when run through the detached-checkout launcher), and
  cross-checks the receipt's `affected_surface.computed_categories`/
  `required_contract_families`/`required_guard_refs`/
  `directly_executed_tests`, `migration_matrix.triggered`,
  `focused_tests.selector` (superset of recomputed required focus
  targets), and `mutation_witnesses.guard_refs` (superset of recomputed
  required guard refs) against that recomputation. It also independently
  recomputes `verifier_hash`/`checker_hash`/
  `dependency_and_config_inputs` from a genuine disposable checkout at
  `C` (never `git show`'s raw blob bytes, which this project's own
  `core.autocrlf=true` proved would diverge from the coordinator's own
  working-tree-based hash) and cross-checks them against the receipt.
  The exact required regression — a candidate changing
  `backend/migrations/versions/...` with the receipt claiming
  `migration_matrix.triggered: false` — is now rejected by both
  `validate_c_a_r_chain` and `check_merge_eligibility`. (2) The review
  and escalation metadata schemas are now fully closed (unrecognized
  fields rejected) and require an exact supported `schema_version`.
  `verification_receipts.py`'s receipt schema now requires an exact
  supported `schema_version`, a typed and format-valid `slice_id`
  (matching `check_handoff.py`'s own `<date>-<slug>-<base-short-sha>`
  format), full `sha256` hex format for `verifier_hash`/`checker_hash`/
  `dependency_and_config_inputs[].sha256`, and every SHA/receipt-ID/
  timestamp field now guards against a non-string JSON value before
  regex-matching it (previously a crash, not a clean rejection). New
  regressions cover a numeric `schema_version`/`slice_id` and a malformed
  hash. (3) The post-merge artifact's evidence validation now requires
  every applicable final-gate static-check step (`ruff format --check`,
  `ruff check`, `mypy`, `check_repo.py`, `git diff --check`) to exist
  exactly once with status `PASS` — an omitted step and a step present
  but `NOT_RUN` are both rejected identically — and `validate_published`
  now independently re-derives whether migration evidence was required
  for the original slice diff and cross-checks it against the artifact's
  own `migration_matrix.triggered`. (4) `DevelopmentState.schema_
  fingerprint` now hashes the full migration-relevant schema surface for
  `public`: every column's type, nullability, *and* default; every
  constraint's full definition text (`pg_get_constraintdef`, which
  already renders a FOREIGN KEY's own ON DELETE/ON UPDATE action into the
  definition, so no separate lookup was needed); and every index's full
  definition text — proven, against the real disposable Postgres, that a
  default-only, nullability-only, constraint-only, index-only, or
  FK-action-only mutation each independently changes the fingerprint
  while the Alembic revision (absent in these fresh, migration-free
  probe databases) stays unchanged.
- Real bug found and fixed while implementing finding 1's hash
  recomputation (not itself one of Sol's findings): the disposable test
  fixture (`test_check_review.py`'s `car_repo`) had no `backend/scripts/
  verify.py`/`check_handoff.py`/`pyproject.toml` files at all, and
  `verification_worktree.py`'s module-level `REPO_ROOT` (fixed at import
  time to the real project root) meant every worktree-creating call in
  that test file needed the disposable repo monkeypatched in, not just
  the two detached-checkout-launcher tests that already did so — fixed by
  adding the stand-in files and moving the monkeypatch into the `car_repo`
  fixture itself.
- Files changed: `backend/scripts/{check_review,verification_receipts,
  migration_matrix}.py` (edited); `backend/tests/test_{check_review,
  verification_receipts,migration_matrix}.py` (edited). No production
  parser (`app/normalization/*`) touched; no migration/model file
  touched.
- Verification (this correction round): `ruff format --check`/
  `ruff check`/`mypy` clean (158 source files, backend + `.claude/hooks`).
  Full pytest suite: **2579 passed**. All 34 mutation witnesses pass
  unmodified. `check_repo.py` exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 4 (Sol review: Changes requested)

- **Supersedes candidate `C4` = `0ad2c4e594fed8a736863040fe934893169a5044`
  and publication `A4` = `6271dc83027d307fbe3ad8563e791c2fbb2939e1`.** The
  receipt published there
  (`docs/verification-receipts/0ad2c4e594fed8a736863040fe934893169a5044/
  d70b98e7-f70f-464e-ac51-0d6a1f3e9604.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C4`/`A4` themselves are left exactly as pushed, per Git
  gates — never amended or rewritten.
- Implements every required correction from Sol's fourth review: (1)
  `check_review.py` now independently discovers the complete active
  mutation-guard inventory for `gate: final` using this checkout's own
  `tests.contracts.taxonomy` module (the target commit's own copy when
  run through the detached-checkout launcher) and requires the receipt's
  `mutation_witnesses.guard_refs` to equal that exact set, with
  `passed == len(guard_refs)` and `failed == 0` — never merely a subset,
  which remains the (weaker, diff-computed) requirement for `fast`. (2)
  `verification_receipts.compute_approval_eligible` now requires, when
  `migration_matrix.triggered` is true: the `migration matrix` step
  exists exactly once with PASS; the matrix's own `status` is PASS;
  before/after `DevelopmentState` values are equal (the development
  database is only ever *read*, never migrated, by
  `migration_matrix.run_full_matrix` — drift here means the matrix itself
  is untrustworthy even if it reported PASS); the fresh-database
  lifecycle was both created and cleaned up; and the remaining evidence
  fields (`postgresql_server_version`, `steps`) are present and valid.
  Untriggered remains vacuously fine. (3) A new `compute_applicable_
  final_step_names`/`compute_applicable_docs_step_names` pair in
  `verification_receipts.py` defines the exact, gate-specific applicable-
  step-name matrix *once* — static checks, DB URL safety, DB reachability,
  focused tests when computed, full suite, all witnesses, migration
  matrix when triggered, handoff validation, and temporary-directory
  cleanup for `final`; the separate, smaller static+handoff+cleanup set
  for `docs` — and both `compute_approval_eligible` (receipt) and
  `check_review.py`'s post-merge artifact evidence check
  (`_require_post_merge_steps_present`) now reuse it, so the two can
  never independently drift. Every applicable step must exist exactly
  once with PASS; an omitted step and a step present but `NOT_RUN` are
  both rejected identically. Post-merge migration-matrix evidence now
  also reuses the same deep validation as finding (2), for the same
  consistency reason.
- Files changed: `backend/scripts/{check_review,verification_receipts}.py`
  (edited); `backend/tests/test_{check_review,verification_receipts,
  verification_coordinator}.py` (edited). No production parser
  (`app/normalization/*`) touched; no migration/model file touched.
- Verification (this correction round): `ruff format --check`/
  `ruff check`/`mypy` clean (158 source files, backend + `.claude/hooks`).
  Full pytest suite: **2619 passed**. All 34 mutation witnesses pass
  unmodified. `check_repo.py` exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 5 (Sol review: Changes requested)

- **Supersedes candidate `C5` = `d3c2d74d794b320f4f9adca331e31cabb26b9d20`
  and publication `A5` = `eae5d01e0bcdead422c58321970a8159fda5f7a1`.** The
  receipt published there
  (`docs/verification-receipts/d3c2d74d794b320f4f9adca331e31cabb26b9d20/
  4e833d27-5d2f-407f-aa92-e0d877072436.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C5`/`A5` themselves are left exactly as pushed, per Git
  gates — never amended or rewritten.
- Implements the one remaining bounded finding: unifies witness-inventory
  validation into a single shared mechanism, used identically in all
  three places it previously existed independently. New
  `verification_receipts.compute_active_guard_refs()` (the complete,
  dynamically discovered active-guard inventory, resolved via whichever
  `tests.contracts.taxonomy` module is importable in the current process
  -- the target commit's own copy when run inside a disposable worktree
  or detached-checkout subprocess) and `witnesses_match_complete_active_
  inventory()` (the shared predicate: `mutation_witnesses.guard_refs`
  must exactly equal that inventory, `passed == len(guard_refs)`,
  `failed == 0` -- never a positive-count-only or subset-only path) are
  now the *only* witness-completeness check anywhere in this codebase.
  `compute_approval_eligible` uses it directly for a `final`-gate receipt
  (replacing the old, weaker `_witnesses_genuinely_ran_and_passed`, which
  is deleted, not merely superseded). `check_review.py`'s pre-merge
  `C -> A -> R` cross-check and its post-merge artifact/Q evidence check
  both now call the same shared predicate (via a new `_require_complete_
  active_witness_inventory` helper that adds a detailed diff to the
  raised error) instead of each independently re-deriving or weakening
  the requirement — the post-merge path previously only required a
  positive count with zero failures, never the complete inventory, which
  is exactly the gap this round closes.
- Files changed: `backend/scripts/{check_review,verification_receipts}.py`
  (edited); `backend/tests/test_{check_review,verification_receipts,
  verification_coordinator}.py` (edited). No production parser
  (`app/normalization/*`) touched; no migration/model file touched.
- Verification (this correction round): `ruff format --check`/
  `ruff check`/`mypy` clean (158 source files, backend + `.claude/hooks`).
  Full pytest suite: **2625 passed**. All 34 mutation witnesses pass
  unmodified. `check_repo.py` exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-13-workflow-v3-2-activation-66202c2
slice_kind: tooling
risk_class: H
base_sha: 66202c23facff6bd33d8f624e327cabdd40708b4
declared_gate: final
executed_gate: final
candidate_sha: 332947196d028b9a46a52aa3c44e51028d5f7e0c
receipt_id: 08c77b12-634a-42ee-a24d-199076baf438
receipt_path: docs/verification-receipts/332947196d028b9a46a52aa3c44e51028d5f7e0c/08c77b12-634a-42ee-a24d-199076baf438.json
full_suite_count: 2625
focused_test_count: 458
mutation_witness_count: 34
```

### Work review

- Sol's final re-review of `C6` = `332947196d028b9a46a52aa3c44e51028d5f7e0c`
  and `A6` = `4ee69a96981c01b12bce1ad3ce7706ff34b5a149`: **Approved, no
  findings.** Independent verification performed: all 458 focused
  tooling tests passed; the genuine receipt validates and recomputes
  `approval_eligible: true`; the exact 1-of-34 receipt and post-merge
  reproductions are now rejected; migration and applicable-step
  enforcement remain closed; `git diff --check` and repository
  cleanliness passed. The reported 2,625-test full suite was not
  independently repeated.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-13-workflow-v3-2-activation-66202c2
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-15T00:00:00Z
candidate_sha: 332947196d028b9a46a52aa3c44e51028d5f7e0c
publication_commit_sha: 4ee69a96981c01b12bce1ad3ce7706ff34b5a149
receipt_path: docs/verification-receipts/332947196d028b9a46a52aa3c44e51028d5f7e0c/08c77b12-634a-42ee-a24d-199076baf438.json
receipt_id: 08c77b12-634a-42ee-a24d-199076baf438
gate: final
verdict: approved
findings: none
```

---

## Iteration 2

### Work done

- Date/agent: 2026-09-15, Claude Code (Sonnet 5). Risk class H (same
  process/security-relevant tooling as Iteration 1). Base `B` -> candidate
  `C7`: `66202c23facff6bd33d8f624e327cabdd40708b4` -> this commit; branch
  `tooling/workflow-v3.2-activation` (continued). `slice_kind: tooling`.
  `slice_id: 2026-09-13-workflow-v3-2-activation-66202c2` (unchanged --
  same base, same underlying activation slice).
- **Supersedes Iteration 1's review record.** Sol approved `C6` =
  `332947196d028b9a46a52aa3c44e51028d5f7e0c` / `A6` =
  `4ee69a96981c01b12bce1ad3ce7706ff34b5a149`, with `R` =
  `0c42aae891a24181f871df56e52b732322fd1d0e` recording that verdict.
  Immediately after, independently running the full `check_review.
  validate_c_a_r_chain(C6, A6, R)` (and therefore `check_merge_
  eligibility`) for the first time -- Sol's own approval was necessarily
  based on direct receipt/repo inspection, since `R` did not yet exist
  when they reviewed -- surfaced a genuine failure: the receipt's
  `checker_hash` for `backend/scripts/check_handoff.py` did not match
  what `check_review.py`'s own hash cross-check recomputed. Root cause:
  that cross-check hashed a *fresh detached-worktree checkout* of the
  file, while the coordinator that produced the receipt hashes the
  *authoring checkout's on-disk bytes* directly -- and that file
  currently carries LF-only line endings in the long-lived authoring
  checkout (never freshly re-checked-out under this project's
  `core.autocrlf=true`), while a fresh worktree checkout smudges it to
  CRLF, so the two hashes diverge. This is a latent defect in `check_
  review.py`'s own tooling, not a problem with `C6`/`A6`'s actual content
  -- `R`'s own structure, the `A6..R` append-only diff, and the review-
  metadata cross-check all independently passed. Per explicit user
  instruction: `C6`/`A6`/`R` are preserved exactly as pushed, never
  amended or rewritten, but this cycle's review record is **not treated
  as valid merge-eligible approval** -- a fresh `C7`/`A7` cycle (this
  iteration) is required, with a new `R` to be authored only after a
  fresh Sol re-review.
- Fix: defines one canonical, platform-independent hashing mechanism,
  reused identically everywhere a file's content is hashed for receipt
  purposes. New `verification_receipts.blob_bytes_at_commit`/
  `committed_file_hash` read the exact committed Git blob bytes for
  `<commit_sha>:<repo_relative_path>` directly from the object database
  via `git cat-file` -- never a working-tree or fresh-checkout read,
  which can differ from the committed bytes whenever a local checkout
  filter (`core.autocrlf`) converts line endings on smudge. Never text-
  decoded, never newline-normalized. Fails closed for a missing commit/
  path, a git failure, or a non-blob object. `dependency_and_config_
  inputs` is rewritten on top of it (now takes `commit_sha` instead of a
  working-tree `repo_root` read) and fails closed on a duplicate or
  malformed path. `verification_coordinator._file_hash_at` and `check_
  review.py`'s `_cross_check_recorded_hashes` (the worktree-spinning-up
  `_recompute_hashes_at_candidate` is deleted entirely, no longer needed)
  both now call this single mechanism, so receipt generation and review-
  time recomputation can never independently diverge again.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2637
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean. New regressions prove: an LF
  authoring-checkout hash and a genuinely CRLF-smudged fresh-worktree
  hash for the same commit are identical; changing committed content
  changes the hash; mutating working-tree bytes without changing the Git
  blob does not; and a real coordinator-generated receipt's hashes agree
  with `check_review.py`'s independent recomputation even after the
  authoring checkout is subsequently mutated on disk.
- Deviations/known limitations: none beyond the superseded Iteration 1
  review record noted above.

#### Correction round 1 (own follow-on finding, before Sol re-review)

- **Supersedes candidate `C7` = `cf60c424dcbc551874f94686fd8b3332cb9d4a86`
  and publication `A7` = `f215fe8031eab8da4a48c5410de5cd0afdf1d6f4`.** The
  receipt published there
  (`docs/verification-receipts/cf60c424dcbc551874f94686fd8b3332cb9d4a86/
  562fad62-93f1-45be-9f52-4e69ced38a82.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. **Correction (Sol's review of `C8`/`A8`):** `C7`/`A7` were
  not independently pushed as branch tips before `C8` was committed on
  top of them -- but pushing `A8` (a descendant of `C8`, a descendant of
  `A7`, a descendant of `C7`) made all three reachable on the remote
  branch as superseded ancestors. They are therefore **not** "purely
  local" or "never pushed to origin"; that was incorrect wording in this
  entry's original form. Both are still preserved unamended, never
  rewritten, per the same discipline as every other correction round in
  this project.
- Found while independently proving the frozen contract's own required
  step -- "the complete `C7 -> A7 -> synthetic-R` chain validates
  successfully before publishing the real `R`" -- using a throwaway,
  never-pushed synthetic `R` in a disposable worktree (deleted
  immediately after). `check_review.extract_review_metadata_text` (and
  `extract_escalation_blocks`) scanned the *entire* handoff file for a
  `workflow-review-metadata`/`workflow-escalation-metadata` block,
  instead of scoping to the newest `## Iteration N` section the way
  `check_handoff.py`'s own metadata-block search already does. Once
  Iteration 1's real `R` (recording Sol's approval of `C6`/`A6`,
  preserved unchanged) and this iteration's own review block coexist in
  the same file, that unscoped search finds both and raises "more than
  one block found" -- this is not merely a test artifact: it would also
  have broken the real `R` for this iteration once authored, since
  Iteration 1's historical block never goes away.
- Fix: new `_latest_iteration_text` scopes to the text from the newest
  `## Iteration N` heading onward (mirroring `check_handoff.py`'s own
  per-iteration scoping); both `extract_review_metadata_text` and
  `extract_escalation_blocks` now search within that scope only. New
  regressions prove: extraction correctly returns the latest iteration's
  own block when an earlier iteration's historical block coexists (never
  raising "more than one" for two blocks in two different iterations);
  escalation-block extraction is scoped identically; and two genuine
  blocks within the *same* latest iteration are still correctly rejected
  as "more than one".
- Files changed (this correction only): `backend/scripts/check_review.py`
  (edited); `backend/tests/test_check_review.py` (edited). No production
  parser (`app/normalization/*`) touched; no migration/model file
  touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2640
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 2 (Sol review of C8/A8: two bounded issues)

- **Supersedes candidate `C8` = `d23273c0addd30717046edc8dfe8b58ebca835b6`
  and publication `A8` = `a056f77b8f949b020dcee2b21267e2b6b4fab2dd`.** The
  receipt published there
  (`docs/verification-receipts/d23273c0addd30717046edc8dfe8b58ebca835b6/
  e917a12f-1b43-43ca-8323-62df0dff785a.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C8`/`A8` are preserved unamended, never rewritten; both
  are reachable on the remote branch (pushed as ancestors of `A8`'s own
  push), not merely local.
- **Finding 1 (A→R boundary):** `check_review.py`'s prior fix (this
  project's own "scope to the latest `## Iteration N` section" approach,
  from the previous correction round) was still not precise enough.
  Review and escalation metadata are now extracted and validated
  *exclusively* from the exact appended suffix
  (`handoff_at_r[len(handoff_at_a):]`), never by searching the whole
  handoff file and never by searching "the latest iteration onward" --
  neither of those weaker scopes can distinguish an already-existing
  historical block from what `R` itself actually added.
  `validate_a_to_r_transition` now computes and returns this suffix
  (after confirming the pure-append invariant), and itself enforces:
  the suffix introduces no new `## Iteration N` heading, and the suffix
  contains exactly one `### Work review` section. `extract_review_
  metadata_text`/`extract_escalation_blocks` are reverted to their
  original simple form (extract from exactly the text given -- no
  internal scoping of their own) since the caller (`validate_c_a_r_
  chain`) now always passes this exact suffix, never the whole file.
  New regressions prove, via genuine Git commits: a fabricated `##
  Iteration N` heading appended between two review blocks is rejected
  outright (the full-transition regression); an escalation block hidden
  behind that same fabricated heading is rejected identically (the
  analogous hidden-escalation proof); and a suffix with two `### Work
  review` sections (no fake iteration needed) is also rejected.
- **Finding 2 (handoff wording):** The previous correction round's own
  entry incorrectly described `C7`/`A7` as "purely local" and "never
  pushed to origin". Corrected in place (see that entry, above): `C7`/
  `A7` were not independently pushed as branch tips before `C8`, but
  pushing `A8` (a descendant of `C8`, a descendant of `A7`, a descendant
  of `C7`) made all three reachable on the remote branch as superseded
  ancestors.
- Files changed (this correction only): `backend/scripts/check_review.py`
  (edited); `backend/tests/test_check_review.py` (edited);
  `docs/LLM_HANDOFF.md` (wording correction to the prior entry, plus this
  entry). No production parser (`app/normalization/*`) touched; no
  migration/model file touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2643
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 3 (Sol review of C9/A9: one bounded issue)

- **Supersedes candidate `C9` = `5a3e18787b878d61035815bca0d31d2f04603e8a`
  and publication `A9` = `033e935e7681db7e402b4f3e9790ae5de12eb50e`.** The
  receipt published there
  (`docs/verification-receipts/5a3e18787b878d61035815bca0d31d2f04603e8a/
  7801c0b5-4993-4d24-8b8e-8a99142fa230.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C9`/`A9` are preserved unamended, never rewritten; both
  are reachable on the remote branch (pushed as ancestors of `A9`'s own
  push), not merely local.
- **Finding (remaining Medium A→R boundary gap):** Sol's C9/A9 re-review
  confirmed both prior findings closed, but found that the previous
  round's suffix-shape check -- "the suffix introduces no new `##
  Iteration N` heading, and contains exactly one `### Work review`
  section" -- did not reject an appended **second** `### Work done`
  heading carrying its own, independently schema-valid
  `workflow-metadata` block, placed after an otherwise-legitimate
  review. `check_merge_eligibility` incorrectly returned `approved` for
  such a suffix, and `check_handoff.py` would then treat that appended
  Work-done metadata as the current state -- violating the closed,
  review-only `A -> R` transition.
- Fix: hardened the exact appended-suffix grammar in `check_review.py`'s
  `validate_a_to_r_transition`. New `_LEVEL_2_OR_3_HEADING_RE` locates
  every level-2 (`## `) or level-3 (`### `) heading introduced by the
  suffix. The suffix is now rejected unless: its first heading is
  exactly its sole `### Work review`; no additional level-2 or level-3
  heading follows (including a second `### Work done`); and no
  `workflow-metadata` fenced block appears anywhere in the suffix (that
  block belongs exclusively to a `### Work done` section, which the
  suffix may never introduce). Ordinary prose beneath the sole `### Work
  review` heading, and validated `workflow-escalation-metadata` blocks
  alongside the review, remain permitted, exactly as before.
- New regressions prove, via genuine Git commits and the full chain: the
  required reproduction -- a suffix pairing a valid `### Work review`
  with an appended second `### Work done` section containing
  *structurally valid* `workflow-metadata` (independently confirmed
  schema-valid via `check_handoff.validate_structure` before the
  reproduction, so the rejection is proven to be about the closed
  transition, not malformed content) -- is rejected by
  `validate_a_to_r_transition`, `validate_c_a_r_chain`, **and**
  `check_merge_eligibility` alike; a bare `workflow-metadata` block
  appended with no heading at all is rejected identically; and two
  neighboring positive controls confirm ordinary review prose beneath
  the sole `### Work review` heading, and a validated escalation block
  alongside the review, both still validate successfully end-to-end.
- Files changed (this correction only): `backend/scripts/check_review.py`
  (edited); `backend/tests/test_check_review.py` (edited);
  `docs/LLM_HANDOFF.md` (this entry, plus resetting the metadata block
  below to `state: pending` for the fresh `C10`/`A10` cycle). No
  production parser (`app/normalization/*`) touched; no migration/model
  file touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2647
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-13-workflow-v3-2-activation-66202c2
slice_kind: tooling
risk_class: H
base_sha: 66202c23facff6bd33d8f624e327cabdd40708b4
declared_gate: final
executed_gate: final
candidate_sha: c7933d072d2c7f92844ec3206863010ef13ff2ad
receipt_id: c22ded07-a429-4154-a6ea-84c553758baa
receipt_path: docs/verification-receipts/c7933d072d2c7f92844ec3206863010ef13ff2ad/c22ded07-a429-4154-a6ea-84c553758baa.json
full_suite_count: 2647
focused_test_count: 480
mutation_witness_count: 34
```

### Work review

- Sol's re-review of `C10` = `c7933d072d2c7f92844ec3206863010ef13ff2ad`
  and `A10` = `688216a8ea1e4da52cb026d2e075a2608c262953`: **Approved, no
  findings.** The A→R suffix now rejects an appended second Work-done
  section or `workflow-metadata` block while allowing ordinary review
  prose and valid escalation metadata. Independent verification
  performed: all 87 focused review tests passed; the `C10→A10`
  publication shape, receipt validity, and hash cross-checks were
  confirmed; `approval_eligible` was independently recomputed; `ruff`,
  `check_repo.py`, and `git diff --check` passed; the branch is clean
  and synchronized. The full 2,647-test suite and the 34 mutation
  witnesses were not independently re-run; those results are taken from
  Claude's receipt.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-13-workflow-v3-2-activation-66202c2
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-17T00:00:00Z
candidate_sha: c7933d072d2c7f92844ec3206863010ef13ff2ad
publication_commit_sha: 688216a8ea1e4da52cb026d2e075a2608c262953
receipt_path: docs/verification-receipts/c7933d072d2c7f92844ec3206863010ef13ff2ad/c22ded07-a429-4154-a6ea-84c553758baa.json
receipt_id: c22ded07-a429-4154-a6ea-84c553758baa
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-17. Merged `tooling/workflow-v3.2-activation` at
  approved, reviewed commit `a070ba974e321f360c0a36282bffabe700be617d`
  (Sol's "Approved, no findings" verdict on `C10`/`A10`, above) into
  `main` via `git merge --no-ff`. Merge commit:
  `9649cba1deebdc73911790de3ccb2ac51fd483a6`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `66202c23facff6bd33d8f624e327cabdd40708b4`.
- Pre-merge checks: confirmed the feature branch and its origin both sat
  at `a070ba9`, and `main`/`origin/main` were both clean and
  synchronized at `66202c23` before merging.
- Post-merge verification, all run directly against merged `main`:
  - `git diff --quiet a070ba9 HEAD` — zero content difference between
    merged `main` and the approved feature-branch tip, confirmed.
  - `git diff --check` — clean.
  - `python -m scripts.check_repo` — clean.
  - No migration/schema changes: `git diff --stat 66202c23..HEAD --
    backend/alembic backend/migrations` and `git log --oneline
    66202c23..HEAD -- backend/alembic backend/migrations` both empty.
  - `python -m scripts.verify --level routine --gate final --focus
    tests/test_check_handoff.py tests/test_check_review.py
    tests/test_migration_matrix.py tests/test_verification_coordinator.py
    tests/test_verification_lock.py tests/test_verification_receipts.py
    tests/test_verification_scope.py tests/test_verification_worktree.py
    tests/test_verify.py` — **all 12 checks PASS**, 480 focused /
    2,647 full-suite tests passed.
  - `python -m scripts.contract_mutation_witnesses` — **34 passed, 0
    failed**, out of 34 active-guard witnesses.
- Pushed: `main` pushed to `origin/main`
  (`66202c23..9649cba1deebdc73911790de3ccb2ac51fd483a6`); both now
  synchronized.
- This merge activates Workflow v3.2's own tooling (schema-v2
  `workflow-metadata`, verification receipts, `C -> A -> R` chain/merge
  validation) as reusable machinery. It does **not** itself authorize
  Slice 3 product/parser work, `Q` post-merge evidence generation, or
  any other new slice — those remain separate authorizations.
- STOP — report the synchronized final `main` SHA and stop. No `Q`
  artifact, no Slice 3, no other Phase 3/4 parser, without separate
  explicit user authorization.
- **Post-merge evidence status:** no `Q` exists for this merge; see ADR
  0009's "Post-merge evidence: one-time bootstrap exception for
  M = 9649cba" for the full record. `validate_published` will fail for
  this `(C10, A10, R, M)` tuple unless a conforming `Q` is later
  authorized and published. The post-merge verification above (zero
  content diff, clean statics, 12/12 canonical-verifier checks, 34/34
  mutation witnesses) was genuinely run and reported here; it can be
  rerun against `M`'s tree for equivalent fresh evidence, but the
  original run's own output was not captured as a durable artifact.

---

## Iteration 3

### Work done

- Date/agent: 2026-09-18, Claude Code (Sonnet 5). Risk class H
  (process/security-relevant tooling, same category as every prior
  Workflow v3.2 tooling slice). Base `B` -> candidate `C`:
  `27a2a5e2cf81b2e347d1fa19012822fe1f0b6198` -> this commit; new branch
  `tooling/workflow-v3.2-post-merge-q-producer`, cut from `main` after a
  freshly verified clean checkout (`main` == `origin/main`, `check_repo.py`
  clean, `git diff --check` clean). `slice_kind: tooling`.
  `slice_id: 2026-09-18-post-merge-q-producer-27a2a5e`. Implements the
  bounded, proposal-reviewed "post-merge `Q`-evidence producer" slice:
  Workflow v3.2's `C -> A -> R -> M -> Q` chain had a validator for `Q`
  (`check_review.validate_q`/`validate_published`) but no producer at
  all until this slice.
- **Producer:** `verification_coordinator.run_post_merge_verification`,
  taking a new `PostMergeEligibleRequest` (only the five chain commit
  SHAs -- `candidate_sha`, `publication_sha`, `review_sha`, `merge_sha`,
  `expected_first_parent` -- no `base_sha`/`slice_id`/receipt-reference
  field for a caller to forge). Every one of those values is instead
  derived from `check_review.validate_c_a_r_chain`'s own independently
  re-validated chain output, before any worktree is created. The
  migration trigger is computed over that same chain-derived
  `base_sha..candidate_sha` range -- never a caller-supplied range and
  never `base_sha..merge_sha` -- so nothing external can suppress a
  genuine migration requirement. Verification runs in a disposable
  detached worktree at `M` (always full/final, never gated or
  focus-narrowed), reusing the receipt producer's own worktree/lock/
  cache-cleanup lifecycle under its own `post-merge-coordinator-`
  run-directory prefix. Emission is explicitly fail-closed: a failed
  verification run, a cleanup failure, or an artifact that would fail
  its own self-validation (`check_review._validate_post_merge_artifact_
  schema`/`_validate_post_merge_artifact_evidence`, called before the
  write) all produce *no file at all* -- a deliberate divergence from
  the existing receipt producer, which does write a receipt marked
  `approval_eligible: false` on a failed run. The function only ever
  writes the artifact file; committing `Q` (bundling that file with the
  append-only merge-record edit to the handoff, per the mainline-`Q`-
  next policy in `LLM_WORKFLOW.md`) remains a separate step.
- **Cleanup-prefix fix:** `cleanup_stale_coordinator_dirs` is now
  parameterized (`prefix: str = "coordinator-"`), restricted to a closed
  set of exactly two known prefixes (`"coordinator-"`,
  `"post-merge-coordinator-"`); an unrecognized prefix (including an
  empty string, which would otherwise match every directory) is rejected
  before any directory is ever scanned.
- **Release-sequence guard:** new `confirm_main_unchanged(expected_sha)`
  re-fetches `origin/main` and refuses if it no longer equals
  `expected_sha` -- run immediately before pushing a locally-prepared
  `M`/`Q` together, so a remote that advanced in the meantime is caught
  before the push rather than raced against.
- **Adversarial self-review** (fresh subagent, full twelve-question
  pass; see `LLM_WORKFLOW.md`'s "Adversarial implementer self-review"):
  no Critical/High findings. Confirmed clean, with concrete evidence:
  the stage-1/2 pre-flight (`validate_c_a_r_chain`/`validate_merge`)
  genuinely runs before any worktree is created on every path; every
  raise point between the worktree stage and the artifact write is an
  unguarded `raise` with no exception-swallowing; `base_sha` is assigned
  exactly once, from the chain-derived `published_base_sha`, with no
  other path into the migration decision; the prefix-rejection in
  `cleanup_stale_coordinator_dirs` is the function's literal first
  statement; there is no TOCTOU window since `A`/`R` content is read
  from immutable commit objects and `M`'s worktree is independently
  snapshotted before/after. Three Medium findings (test-rigor gaps, not
  implementation defects) were fixed in response: two rejection tests
  now also assert a worktree-creation guard (proving *when* rejection
  happens, not just *that* it does, since `.verify-tmp` absence alone
  couldn't distinguish "never created" from "created and cleaned up");
  the success and verify-invocation-failure tests now assert
  `.verify-tmp` is clean (empty or absent) directly, since it is
  gitignored and `git status` is blind to it; and a new regression
  (`test_post_merge_verification_writes_no_artifact_when_self_
  validation_fails`) proves the artifact's own self-validation gate --
  not just the `returncode`/`all_passed` check -- independently blocks
  emission, using a stand-in `verify.py` that mis-reports `all_passed:
  true` while silently omitting a required step. Three Low findings
  were reviewed and accepted as pre-existing, informational, and out of
  this slice's bounded scope (see Deviations below), not fixed here.
- **Documentation (the three proposal-approved addenda):** `docs/
  DECISIONS/0009-workflow-v3.2-activation.md` gains "Post-merge
  evidence: one-time bootstrap exception for M = 9649cba" (the corrected
  explanation: a conforming `Q` remains constructible on a sibling
  branch at any time, since Git places no limit on a commit's children
  -- what is actually foreclosed is only `main`'s own already-pushed
  linear continuation from `M`; the reason is procedural, not technical,
  since `M`'s own tree already contained the `Q` tooling; the
  preserved evidence is reported and rerunnable, not "independently
  reproducible from Git") and "Post-merge (`Q`) evidence producer"
  (describing this slice's implementation). `docs/LLM_WORKFLOW.md` gains
  "Post-merge (`Q`) evidence producer" and "Project policy: `Q` is the
  next mainline commit after `M`" (explicitly framed as this project's
  own policy choice, not a `validate_q` requirement; a precondition --
  an approved producer or evidence-capture procedure must exist *before*
  merge authorization, not after; the mainline-shape rule; a fail-closed
  stop-at-`M` rule if post-merge verification or `Q` validation ever
  fails; and the release sequence tying `confirm_main_unchanged` into
  the push step). This handoff gains the "Post-merge evidence status"
  pointer note on the prior Merge record entry (above) and this Work
  done entry itself.
- Files changed: `backend/scripts/verification_coordinator.py` (edited);
  `backend/tests/test_verification_coordinator_post_merge.py` (new, 16
  tests); `docs/DECISIONS/0009-workflow-v3.2-activation.md` (edited);
  `docs/LLM_WORKFLOW.md` (edited); `docs/LLM_HANDOFF.md` (this entry,
  the prior entry's pointer note, and the two-iteration rotation below).
  No production parser (`app/normalization/*`), model, migration, or
  live-provider file touched; no database lifecycle operation performed.
- **Two-iteration rotation applied**: the oldest iteration (the Slice 2
  contract-harness bounded-correction pass, already merged) is deleted;
  the former Iteration 2 (the original v3.2 activation candidate/review
  cycle) and Iteration 3 (the C7-C10 correction saga plus the merge
  record) are renumbered to Iteration 1 and Iteration 2 respectively,
  with every in-prose cross-reference to the renumbered iteration
  updated to match; this entry becomes the new Iteration 3.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (159
  source files, backend + `.claude/hooks`). Full pytest suite: **2663
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- Deviations/known limitations (all reviewed, accepted, non-blocking):
  (1) on a worktree-removal failure, cleanup still deletes the physical
  worktree directory without `git worktree remove`/`prune`, which can
  leave a dangling `.git/worktrees/<id>` metadata entry -- inherited,
  byte-identical behavior from the existing `run_receipt_eligible_
  verification`, not introduced or changed by this slice; (2)
  `cleanup_stale_coordinator_dirs` cannot detect or repair that kind of
  leak, since it only scans `COORDINATOR_RUN_ROOT`, never `git worktree
  list` -- same shared, pre-existing limitation; (3) no dedup/lock scopes
  a given `merge_sha` itself, so two concurrent producer runs against the
  same `M` could both succeed and coexist as separate untracked artifact
  files under `docs/post-merge/<merge_sha>/` -- harmless in practice,
  since `validate_q` requires exactly one *committed* artifact addition,
  and the actual choice of which artifact becomes `Q` is made at commit
  time, not by the producer.
- STOP — this is a bounded tooling slice only. Do not author `R`, merge,
  create a real `M`/`Q` for this slice or retroactively for `M =
  9649cba`, begin another slice, rebase, or force-push.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-18-post-merge-q-producer-27a2a5e
slice_kind: tooling
risk_class: H
base_sha: 27a2a5e2cf81b2e347d1fa19012822fe1f0b6198
declared_gate: final
executed_gate: final
candidate_sha: 3397e1d37a558b9e714c5970ed66f4d98989e7b6
receipt_id: a78ee96c-ee63-4e70-9269-4d8f52874371
receipt_path: docs/verification-receipts/3397e1d37a558b9e714c5970ed66f4d98989e7b6/a78ee96c-ee63-4e70-9269-4d8f52874371.json
full_suite_count: 2663
focused_test_count: 16
mutation_witness_count: 34
```
