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

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R (tooling)
  correction pass on `tooling/workflow-v3.1-handoff-metadata` addressing
  the single remaining bounded finding in Iteration 1's `Work review`
  (commit `d5fec38`) above. Base -> ending commit: `d5fec38` -> this
  commit; same branch. Scope held exactly to the requested correction —
  no verifier orchestration, hook, product, migration, or pilot-policy
  change.
- Finding (Medium — unknown metadata keys still passed validation):
  added `_OPTIONAL_FIELDS` and `_ALLOWED_FIELDS` (the six required fields
  plus `lightweight_checks`/`fixture_path`/`fixture_count` — the complete,
  closed schema) to `check_handoff.py`. `validate_structure` now computes
  `unknown = [key for key in fields if key not in _ALLOWED_FIELDS]` and
  raises before any other check runs if `unknown` is non-empty, so an
  invented or misspelled key can never reach the required/conditional
  logic undetected. Updated the module docstring's schema section to
  state the closed-schema rule explicitly.
- Regression: `test_unknown_metadata_key_is_rejected_even_in_an_otherwise_valid_block`
  reproduces Codex's own example exactly — an otherwise fully-valid
  tooling block with an added `typo_full_sute_count: 1` key — and asserts
  it now raises `HandoffValidationError`.
- Mutation-proof: temporarily removed the new `unknown`/`_ALLOWED_FIELDS`
  check from `validate_structure`, reran the new regression test alone,
  confirmed it failed with `DID NOT RAISE HandoffValidationError`
  (reproducing exactly the reviewer's reported defect), then restored the
  check and reconfirmed the test passes.
- Files changed: `backend/scripts/check_handoff.py`, `backend/tests/
  test_check_handoff.py` (+1 test, 69 total), this handoff entry. No
  other file touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (104
  source files). `python -m scripts.check_repo` exits 0. Genuine external
  `python scripts/verify.py --level routine --focus
  tests/test_check_handoff.py tests/test_verify.py
  tests/test_compact_checkpoint.py` (full run) — **172 focused / 1846
  full-suite tests** (was 171/1845; +1 each, exactly the one new test).
  All 11 steps PASS, including `handoff metadata validation` against
  this entry's own metadata block below.
- Deviations/known limitations: none new.
- STOP — awaiting Codex final re-review. Do not merge, begin
  `classify_experience` or any other Phase 3 parser, or start pilot slice
  2/3 of Workflow v3.1 without separate authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: tooling
verification_level: routine
focused_test_selector: tests/test_check_handoff.py tests/test_verify.py tests/test_compact_checkpoint.py
focused_test_count: 172
full_suite_count: 1846
```

### Work review

- Date/reviewer: 2026-09-08, Codex.
- Diff reviewed: `d5fec38..0c271d4` on
  `tooling/workflow-v3.1-handoff-metadata`.
- Verdict: **Approved.** No executable findings.
- The remaining malformed-metadata finding is closed. The validator now defines the
  complete nine-key schema and rejects every supplied key outside it before evaluating
  required or conditional fields. The regression uses the exact
  `typo_full_sute_count` example from the prior review and is appropriately isolated.
- Independent verification: `git diff --check` and `python -m scripts.check_repo` exit
  clean; the exact regression passes **1/1**; the three focused tooling modules pass
  **172/172 tests** using a workspace-local pytest base directory. Code inspection
  confirms the production path calls `validate_structure()` before fixture/count
  cross-checking. The full 1846-test suite was not independently repeated for this
  isolated structural correction; Claude's recorded canonical run reports all 11 steps
  passing with **172 focused / 1846 full-suite tests**.
- Scope remained bounded to `check_handoff.py`, its unit test, and the handoff rotation.
  No verifier orchestration, hook, product code, migration, or pilot policy changed.
- The Workflow v3.1 handoff-metadata tooling slice and its correction passes are
  accepted. Do not merge or begin `classify_experience` until the user explicitly
  authorizes the next action.

### Merge record

- Date: 2026-09-08. User authorized merging
  `tooling/workflow-v3.1-handoff-metadata` into `main` following Codex's
  Approved review (no executable findings; approval commit `bf1104b`)
  above.
- Pre-merge state: `main` and `origin/main` both at `f003595`; feature
  branch `tooling/workflow-v3.1-handoff-metadata` and its origin both
  clean and synced at `bf1104b` (containing implementation commit
  `62fe128`, the base->ending-commit fix `d8db682`, two correction
  passes `41b3f70`/`0c271d4`, and review commits `38ed0a2`/`d5fec38`/
  `bf1104b`).
- Merge: `git merge --no-ff tooling/workflow-v3.1-handoff-metadata` on
  `main` — merge commit `a3a2226`. `git diff
  tooling/workflow-v3.1-handoff-metadata HEAD` is empty (zero content
  difference); `git diff --check` and `check_repo.py` both exit 0;
  working tree clean.
- Post-merge verification: genuine external `python scripts/verify.py
  --level routine --focus tests/test_check_handoff.py
  tests/test_verify.py tests/test_compact_checkpoint.py` (full run) —
  all **11 steps PASS** (Ruff format/check, mypy, `check_repo.py`, `git
  diff --check`, disposable-database URL/reachability, **172 focused /
  1846 full-suite tests**, handoff metadata validation, temp-directory
  cleanup). A prior run without `--focus` correctly FAILed only the
  handoff-metadata step (`"this invocation was not given --focus, but
  the handoff metadata declares a numeric focused_test_count"`) —
  expected behavior of the validator cross-checking this entry's own
  declared selector, not a regression; the full 1846-test suite passed
  in that run too.
- Migration/database state: unchanged. `git diff main
  tooling/workflow-v3.1-handoff-metadata -- backend/alembic
  backend/app/db` is empty — no migration or database-layer file is
  part of this diff, so no migration was run and no schema changed.
- Pushed: `main` at `a3a2226`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `f003595`
  (the commit immediately before this merge) — this removes
  `backend/scripts/check_handoff.py`, its test file, the `verify.py`
  handoff-metadata step and `--docs-only` mode (and their tests), the
  `compact_checkpoint.py` workflow-version marker (and its test), and
  the `docs/LLM_WORKFLOW.md`/`CLAUDE.md` Workflow v3.1 pilot text,
  cleanly, with no migration to reverse and no data written by this
  slice to any environment (pure tooling/process changes, never wired
  into ingestion/persistence or any database).
- **The Workflow v3.1 pilot's enabling tooling slice is merged, not a
  counted pilot slice itself.** Per `docs/LLM_WORKFLOW.md`'s corrected
  "Workflow v3.1 pilot" section, the three-slice measurement window
  starts with `classify_experience` as pilot slice 1 of 3 — this
  handoff-metadata validator and `--docs-only` mode are the
  infrastructure that makes that measurement possible, not one of the
  three counted slices. The mandatory retrospective still triggers after
  the third counted **parser** slice's `Work review`, not after this one.
- STOP — do not begin or propose `classify_experience` or any other
  Phase 3 parser, or start pilot slice 2/3 of Workflow v3.1, without
  separate authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, matching `seniority.py`'s precedent — deterministic
  pure-function text classifier, no identity/concurrency/security/
  external/destructive surface). Base -> ending commit: `ddb427d` -> this
  commit; new branch `phase-3/experience-classifier`. Workflow v3.1 pilot
  parser slice 1 of 3. Implements the fresh proposal Astra approved with
  binding clarifications, incorporating every amendment below exactly.
- `app/normalization/experience.py` (new): `classify_experience(title,
  description) -> ExperienceRange`, the first parser needing `types.py`'s
  deferred composite-result case — two independently-provenanced
  `NormalizationResult[int]` bounds (`minimum`, `maximum`). Independent
  implementation (own regex grammar, own segment/sentence splitting,
  no import from `seniority.py`/`employment.py`/`remote.py`), proven by
  the same AST-inspection allow-list pattern as the other three parsers.
- Astra review amendments incorporated (all from the `604213a` proposal
  review): **(2)** applicant attribution is a closed
  `ALLOWED_SUBJECT REQUIRE_VERB [ATTRIBUTION_OBJECT] <phrase> END` frame,
  not subject/verb adjacency alone — `"We require vendors with 5 years of
  experience."` and `"We require no experience to use our platform."`
  both correctly reject. **(3)** the continuation-boundary rule is
  uniform: only an empty remainder accepts; a recognized negation and a
  wholly unrecognized hedge both reject identically, so unsupported
  negation can never silently become a positive requirement, while
  `"no more than 5 years"` still correctly yields `maximum=5` (consumed
  whole by the open-upper production, never reaching the boundary check
  as trailing text). **(4)** numeric rejection is atomic: a single
  text-wide redaction pass (decimal-beside-range, fraction, free-standing
  negative, bare decimal) runs before any sentence/segment splitting, so
  a poisoned digit can never resurface via a narrower production —
  proven necessary specifically on the *title* path (no redundant
  match-start/continuation-boundary guard there), where four new fixtures
  demonstrate the old (mutated-off) behavior fabricating `min=5`, `min=2`,
  etc. **(5)** preference-marker suppression is positional, not lexical:
  `"the ideal candidate"` (a closed subject phrase) is never confused with
  the `"ideal"/"ideally"` preference marker, since the marker check only
  ever inspects a sentence-initial `"Ideally,"` or an immediate trailing
  tag after an already-matched number — never the subject position.
  **(6)** internal (within-source) conflict is checked, and wins, before
  cross-source reconciliation, independently per bound — mirrors
  `seniority.py`'s exact `_CONFLICT`-before-agreement precedence.
- Files changed: `backend/app/normalization/experience.py` (new),
  `backend/tests/test_normalization_experience.py` (new, 63 tests),
  `backend/tests/fixtures/normalization/experience_cases.json` (new, 55
  cases), `docs/ROADMAP.md` (Phase 3 bullet — also corrected a
  pre-existing staleness: the seniority-classifier bullet still said
  "pending Codex review — not merged" despite that merge already existing
  at `92fcefc`), `docs/ARCHITECTURE.md` (annotated `experience.py`'s
  status), this handoff entry (two-iteration rotation). No other file
  touched; no schema, migration, or ingestion/persistence wiring.
- Contract-conformance pass (Workflow v3.1, required for parser slices):
  walked every claim in the approved proposal plus every Astra amendment
  individually against the implementation via direct manual traces
  (documented above and in the module docstring) before writing the
  fixture corpus — all confirmed enforced, not merely fixture-satisfied.
- Counterexample pass (Workflow v3.1, required for parser slices): probed
  ~25 new inputs not in the fixture corpus across the historical-defect
  checklist's nine categories (disallowed subjects beyond the reviewed
  examples — "the client", "our previous engineer"; non-adjacent
  "requires" separated from its subject by other clauses; an inverted
  raw range "7-3 years" correctly caught by the same consistency
  invariant that catches cross-bound inversion; a hyphenated compound
  "5-Year Minimum..." that doesn't match any production). No confidently-
  wrong output found; every excluded case resolved to `UNAVAILABLE`. Two
  new safe-miss scope boundaries noted, not fixed: a "5-Year" hyphenated-
  compound adjective form, and a `REQUIRE_VERB` frame requiring direct
  subject-verb adjacency (no intervening clause) — both documented
  limitations, not confidently-wrong cases.
- Load-bearing regression mutation proofs (Workflow v3.1, required):
  individually reverted and reconfirmed 8 fixes — amendment 2's
  attribution-object gate, amendment 3's uniform continuation-boundary
  rule, amendment 4's redaction mechanism (isolated via 4 new title-side
  fixtures after discovering the original description-side fixtures were
  masked by amendment 2/3's own guards — a real gap this pass itself
  caught and closed), amendment 5's positional preference check, amendment
  6's internal-conflict precedence, and Risk 5's hyphen disambiguation.
  Every mutation reproduced the exact pre-fix defect (a fabricated value
  or a crash); every fix, once restored, passed again.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (106
  source files). `python -m scripts.check_repo` exits 0. Genuine external
  `python scripts/verify.py --level routine --focus
  tests/test_normalization_experience.py` (full run) — **63 focused /
  1909 full-suite tests** (was 1846; +63 from the three targeted
  normalization suites run together plus the new module, net +63 to the
  full suite). All 11 steps PASS, including `handoff metadata validation`
  against this entry's own metadata block below.
- Deviations/known limitations: explicit exclusions carried from the
  approved proposal (no `"Requirements:"`-header-scoped attribution, no
  `exp` unit abbreviation, negation-marker catalog acknowledged
  non-exhaustive) plus the two new counterexample-pass findings above
  (hyphenated-compound numbers, non-adjacent requirement clauses) — all
  safe misses (`UNAVAILABLE`), none confidently wrong, none requiring
  user approval under the confidently-wrong blocking rule.
- STOP — awaiting Astra's implementation review. Do not merge, begin
  another Phase 3 parser, wire into ingestion/persistence, contact
  providers, or create a migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_experience.py
focused_test_count: 63
full_suite_count: 1909
fixture_path: backend/tests/fixtures/normalization/experience_cases.json
fixture_count: 55
```
