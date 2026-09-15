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

- Date/agent: 2026-09-13, Claude Code (Sonnet 5). Risk class R
  (unchanged). Base -> ending commit: `d8c2c09` -> this commit; same
  branch `tooling/workflow-v3.2-slice2-contract-harness`. Bounded
  correction pass applying Sol's five re-review findings against the
  frozen Slice 2 implementation, relayed as text (no separate `###
  Work review` commit exists on this branch or its origin prior to
  this one). Scope held exactly to the harness's own files, per the
  correction's explicit boundary — no production parser, workflow-
  version consumer, or Slice 3 file touched.
- Five findings addressed:
  1. **Import boundary strengthened for equivalent forms/aliases** —
     `test_harness_import_boundary.py`'s detectors now catch `from app
     import normalization` (an equivalent whole-module bind, not just
     `import app.normalization`) and alias-resolved dynamic calls (e.g.
     `from importlib import import_module as load; load(...)`), via a
     new import-alias map that resolves any locally-bound name back to
     its canonical dotted origin before checking it against the banned
     set. Two new isolated synthetic regressions added.
  2. **Expected-output validation made genuinely parser/field-
     discriminated** — replaced the generic "str or int" check with
     `schema.OUTPUT_FIELD_TYPES` (location's four fields: `str`;
     salary/experience numeric bounds: `int`; salary currency/period:
     `str`), enforced in `loader._load_expected_output`. `bool` is
     still rejected outright before the field-specific check runs
     (Python's `bool` is an `int` subclass). `None` is still accepted
     only paired with `unavailable` provenance (unchanged, `ExpectedField`'s
     own invariant).
  3. **Record traceability enforced**: a record_id's slug must start
     with its own `parser` name; a base record's record_id/transform
     must be `variant-base`/`transform-none`; a generated record must
     never use `variant-base` (reserved, so record_id alone signals
     kind); a base record's `historical_defect_ref` must equal its
     guard inventory entry's; and (in `collect_all`, requiring the
     full three-file set) a generated record's `base_record_id` must
     resolve to an actual **base** record (never another generated
     record) sharing its parser, guard_ref, `original_input`, and
     `target` exactly.
  4. **`contract_mutation_witnesses.py` now loads records through the
     fail-closed loader** (`tests.contracts.loader.collect_all`),
     never raw `json.loads`. Before running any witness, it now
     requires: the registry's declared record exists in the loaded
     set; it is that guard's designated primary witness; its
     parser/guard_ref agree with the registry entry; and the
     registry's own `input_` is byte-for-byte identical to the
     record's `expected_transformed_input`. The restored-output
     assertion now compares against the loaded record's own
     `expected_output` directly, not a second raw JSON read.
  5. **Experience-adapter docstring corrected**: it previously implied
     the non-target field is always `None`; corrected to state that a
     record may deliberately populate both `title` and `description`
     together for a cross-source witness (e.g.
     `experience/g05-internal-conflict-precedence`, whose own record
     does exactly this), with `target.input_field` naming the field
     the guard's mechanism most centrally concerns, not "the only
     non-null one."
- Finding 5's docstring edit changed `adapters/experience.py`'s own
  file bytes, which correctly triggered a `STALE adapter fingerprint`
  failure for all 21 experience guards on the next witness run
  (confirming the staleness check, corrected in Iteration 1, genuinely
  fires on a real, intentional change). Recomputed and re-froze only
  `_FROZEN_ADAPTER_FP["experience"]` (`03c559ec88386dc7` ->
  `dfa142423607a5a3`); every other frozen fingerprint (both other
  adapters, all three parser sources, all 34 records) is byte-identical
  to Iteration 1's baseline, confirmed by recomputing all of them fresh
  and diffing.
- Direct fault-injection tests added for every accepted-invalid case
  above: 2 new import-boundary synthetic regressions (finding 1); 5 new
  loader tests covering wrong-type values for each parser/field
  combination plus a bool-still-rejected control (finding 2); 9 new
  loader tests covering the parser-prefix mismatch, base-transform/
  variant misuse, generated-variant-base masquerade, historical_defect_ref
  disagreement, generated-record chaining to a non-base record, and
  generated-record original_input/target mismatches (finding 3); 6 new
  tests exercising `_check_record_matches_registry_entry` directly
  (missing record, non-primary witness, guard/parser/input mismatches,
  and the real matching case) (finding 4).
- Files changed: `backend/scripts/contract_mutation_witnesses.py`,
  `backend/tests/contracts/adapters/experience.py`,
  `backend/tests/contracts/loader.py`,
  `backend/tests/contracts/mutation_registry.py` (frozen adapter
  fingerprint re-freeze only),
  `backend/tests/contracts/schema.py`,
  `backend/tests/contracts/test_harness_import_boundary.py`,
  `backend/tests/contracts/test_harness_self.py`, this handoff entry.
  No production parser, existing fixture, existing parser test,
  verifier, workflow document, hook, metadata validator, dependency
  file, or other version-bearing consumer touched. The corrected
  35-historical/34-active/1-superseded inventory is unchanged (asserted
  fresh at import time, confirmed).
- Mutation-witness acceptance run: `python -m
  scripts.contract_mutation_witnesses` — **34 passed, 0 failed**
  (re-run after the adapter-fingerprint re-freeze above).
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass.
  `python -m scripts.check_repo` exits 0. Genuine external `python -m
  scripts.verify --level routine --focus
  tests/contracts/test_location_contract.py
  tests/contracts/test_salary_contract.py
  tests/contracts/test_experience_contract.py
  tests/contracts/test_harness_self.py
  tests/contracts/test_harness_import_boundary.py` — all 11 steps PASS:
  **123 focused / 2316 full-suite tests** (both counts grew by exactly
  21, matching the 21 new fault-injection/regression tests added across
  the two test files).
- **Follow-up bounded correction (same commit lineage, still Iteration
  2 — Sol independently reproduced this before any review was recorded
  against the entry above, so it is folded in here rather than forcing
  a premature ledger rotation that would delete Iteration 1's still-
  unreviewed original Work done)**: `_dynamic_bypass_calls` (added by
  finding 1 above) only handled an `ast.Attribute` whose immediate
  `.value` was an `ast.Name` — a nested chain two or more levels deep
  (`importlib.util.spec_from_file_location`, or the same via `import
  importlib as il; il.util.spec_from_file_location(...)`) fell through
  entirely, yielding zero findings despite being named in
  `_BANNED_DOTTED_CALLS` and the function's own docstring. Fixed by
  replacing the one-level handling with a recursive `_dotted_path`
  reconstruction of the complete attribute chain, canonicalizing only
  the chain's root through the alias map
  (`_canonicalize_dotted_path`), then comparing the resulting full
  path against the closed banned-call set — never broadened into a
  general analyzer. Both exact reproductions and two positive controls
  (an unrelated two-level chain `os.path.join`, and an unrelated
  three-level chain with no import statement at all) added as isolated
  synthetic regressions. This touched only
  `test_harness_import_boundary.py` (a test file, not a source/adapter/
  record file), so no fingerprint re-freeze was needed or performed —
  confirmed by all 34 mutation witnesses passing unmodified. Genuine
  external `python -m scripts.verify --level routine --focus` (same
  five-file selector as above) re-run after this fix: all 11 steps
  PASS, **127 focused / 2320 full-suite tests** (both grew by exactly
  4, matching the 4 new synthetic regressions/positive controls added)
  — superseded by the second follow-up below, which is now the final,
  current count.
- **Second follow-up bounded correction (same reasoning as the first:
  folded into this still-unreviewed Iteration 2 rather than rotating)**:
  `_build_alias_map`'s `ast.Import` branch mapped a plain dotted
  import's bound name to the *complete* imported path even without an
  `as` clause — `import importlib.util` binds only the name
  `importlib` (referring to the top-level package itself; `.util` is
  reached by ordinary attribute access), but the prior code mapped
  `alias_map["importlib"]` to `"importlib.util"`, so canonicalizing
  `importlib.util.spec_from_file_location` produced the wrong, doubled
  path `importlib.util.util.spec_from_file_location` and the banned
  call escaped detection — also making the function's own docstring
  claim about `import importlib.util` false. Fixed: without `as`, the
  bound root now canonicalizes to itself; only `import a.b.c as d`
  binds `d` to the complete dotted path. Added the exact `import
  importlib.util` reproduction as an isolated regression, a direct
  test of `_build_alias_map`'s corrected binding for that exact
  statement, and a direct canonicalization-level test proving `import
  os.path` canonicalizes `os.path.join` to exactly `os.path.join` (not
  `os.path.path.join`) — the latter is a genuine proof, not merely an
  absence-of-finding assertion, since the pre-fix doubled path for
  `os.path` also happened not to be in the banned set, so the existing
  higher-level positive-control test for it had passed even under the
  bug. Touched only `test_harness_import_boundary.py` again — no
  fingerprint re-freeze needed, confirmed by all 34 mutation witnesses
  passing unmodified. Genuine external `python -m scripts.verify
  --level routine --focus` (same five-file selector) re-run after this
  fix: all 11 steps PASS, **130 focused / 2323 full-suite tests** (both
  grew by exactly 3, matching the 3 new tests added) — this is the
  final, current count.
- Deviations/known limitations: unchanged from Iteration 1's disclosed
  limitations. No new limitations introduced — this pass only tightens
  validation and traceability; no behavior change to any of the 34
  primary-witness records' own expected outputs.
- STOP — this is still Slice 2 only, now corrected. Do not implement
  Slice 3, touch any production parser/fixture/existing test, or begin
  another Phase 3/4 parser. Do not merge without separate explicit user
  authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: tooling
verification_level: routine
focused_test_selector: tests/contracts/test_location_contract.py tests/contracts/test_salary_contract.py tests/contracts/test_experience_contract.py tests/contracts/test_harness_self.py tests/contracts/test_harness_import_boundary.py
focused_test_count: 130
full_suite_count: 2323
```

### Work review

- Date/reviewer: 2026-09-13, Codex/Sol. Reviewed commit: `379f69b` on
  `tooling/workflow-v3.2-slice2-contract-harness` (the final of three
  bounded corrections folded into this Iteration 2 entry — Sol's five
  re-review findings, the nested-attribute-chain fix, and this
  `ast.Import` binding-semantics fix).
- Verdict: **Approved. No findings.**
- Independent verification performed: ran the 130 focused contract
  tests, all 34 mutation witnesses, `check_repo.py`, and `git diff
  --check` — all passed. The reported 2,323-test full-suite result was
  **not independently repeated**.
- Next action: awaiting the user's separate authorization before any
  merge, Workflow v3.2 activation, Slice 3 work, or another parser.
- STOP — no merge, no Workflow v3.2 activation, no Slice 3, no other
  Phase 3/4 parser, without explicit user authorization.

### Merge record

- Date: 2026-09-13. Merged `tooling/workflow-v3.2-slice2-contract-harness`
  at approved, reviewed commit `96917b2` (Codex/Sol "Approved. No
  findings." verdict above) into `main` via `git merge --no-ff`. Merge
  commit: `fe82659a072f93050aaf77c7ee29d2543200d978`. Pre-merge `main`/
  `origin/main` tip (rollback boundary): `d28bf03533b110b030061a6e22c76217d9bf001b`.
- Pre-merge checks: confirmed the feature branch and its origin both sat
  at `96917b2`, and `main`/`origin/main` were both clean and synchronized
  at `d28bf03` before merging.
- Post-merge verification, all run directly against merged `main`:
  - `git diff --quiet 96917b2 main` — zero content difference between
    merged `main` and the approved feature-branch tip, confirmed.
  - `git diff --check` — clean.
  - `python -m scripts.check_repo` — clean.
  - No migration/schema changes: `git diff --stat d28bf03 main --
    backend/alembic backend/migrations` and `git log --oneline
    d28bf03..main -- backend/alembic backend/migrations` both empty.
  - `python -m scripts.verify --level routine --focus
    tests/contracts/test_location_contract.py
    tests/contracts/test_salary_contract.py
    tests/contracts/test_experience_contract.py
    tests/contracts/test_harness_self.py
    tests/contracts/test_harness_import_boundary.py` — **all 11 checks
    PASS**, 130 focused / 2323 full-suite tests passed.
  - `python -m scripts.contract_mutation_witnesses` — **34 passed, 0
    failed**, out of 34 active-guard witnesses (`experience/g07` remains
    correctly excluded as superseded).
- Pushed: `main` pushed to `origin/main` (`d28bf03..fe82659`); both now
  synchronized at `fe82659a072f93050aaf77c7ee29d2543200d978`.
- Workflow v3.1 remains the sole active workflow. Workflow v3.2 is not
  activated by this merge. Slice 3 and any other parser remain
  unauthorized.
- STOP — report the synchronized final `main` SHA and stop. No Workflow
  v3.2 activation, no Slice 3, no other Phase 3/4 parser, without
  separate explicit user authorization.

---

## Iteration 2

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

## Iteration 3

### Work done

- Date/agent: 2026-09-15, Claude Code (Sonnet 5). Risk class H (same
  process/security-relevant tooling as Iteration 2). Base `B` -> candidate
  `C7`: `66202c23facff6bd33d8f624e327cabdd40708b4` -> this commit; branch
  `tooling/workflow-v3.2-activation` (continued). `slice_kind: tooling`.
  `slice_id: 2026-09-13-workflow-v3-2-activation-66202c2` (unchanged --
  same base, same underlying activation slice).
- **Supersedes Iteration 2's review record.** Sol approved `C6` =
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
- Deviations/known limitations: none beyond the superseded Iteration 2
  review record noted above.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-09-13-workflow-v3-2-activation-66202c2
slice_kind: tooling
risk_class: H
base_sha: 66202c23facff6bd33d8f624e327cabdd40708b4
declared_gate: final
```
