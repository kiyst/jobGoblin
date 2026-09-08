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

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R (tooling —
  process/infrastructure only, no identity/concurrency/security/external
  behavior). Base -> ending commit: `f003595` -> this commit; branch
  `tooling/workflow-v3.1-handoff-metadata` (new branch, base: clean
  `main@f003595`, the seniority-classifier merge-record commit).
  Implements the Workflow v3.1 pilot's first (of three) piloted slices exactly as
  user-authorized: a `slice_kind`/`verification_level` structured metadata
  block in `LLM_HANDOFF.md`'s `Work done` entries, its validator, a
  required `verify.py` step that cross-checks that block against the same
  invocation's own observed counts, a `--docs-only` verifier mode, a
  `workflow_version` marker in the compaction checkpoint, and the durable
  process text (claim-to-evidence matrix, historical-defect checklist,
  confidently-wrong blocking rule, two-pass requirement) in
  `docs/LLM_WORKFLOW.md`/`CLAUDE.md`.
- `backend/scripts/check_handoff.py` (new): offline, no-subprocess
  validator for the metadata block — presence/allowed-values/cross-field
  structure (`validate_structure`), fixture-count cross-check against the
  real fixture file for `slice_kind: parser` (`validate_fixture_count`),
  and a cross-check against a caller-supplied actual run
  (`validate_against_run`) enforcing that `verification_level: not_run`
  never coexists with a fabricated numeric count and that `slice_kind:
  parser` requires real focused testing. Only ever inspects the *newest*
  `## Iteration N`'s `Work done` section — historical, already-rotated
  entries are never checked.
- `backend/scripts/verify.py`: added `handoff_metadata_step` (new,
  required, unconditional — runs even under `--docs-only`), wired via a
  `pytest_counts` dict shared across `_build_steps`'s pytest step
  closures using `run_pytest_step`'s new `counts_sink`/`counts_key`
  keyword-only parameters (a side channel; no second pytest subprocess is
  ever launched to re-derive counts). Added `--docs-only` (mutually
  exclusive with `--focus`, enforced in `_parse_args`), which skips the
  two database steps and both pytest steps while still requiring the
  handoff-metadata step to pass with `verification_level: not_run`.
- `.claude/hooks/compact_checkpoint.py`: added `WORKFLOW_VERSION =
  "v3.1-pilot"`, included in `render_checkpoint`'s output as `Workflow
  version: v3.1-pilot`.
- `docs/LLM_WORKFLOW.md`: new "Workflow v3.1 pilot (three-slice trial)"
  section — claim-to-evidence matrix template, the nine-category
  historical-defect checklist (grounded in this project's actual past
  defects: the `employment.py` mask-order bug, the seniority immediate-
  trailing-conflict gap, and the negation/attribution gaps the first
  `classify_experience` preflight caught), the confidently-wrong blocking
  rule, the two-pass requirement, the `slice_kind`/metadata-block
  reference, and the mandatory post-third-slice retrospective trigger.
  Also documents `--docs-only` in the verification matrix section.
- `CLAUDE.md`: new "Workflow v3.1 (pilot)" marker section; compaction
  instructions now also preserve the active workflow version and the
  active slice's `slice_kind`/`verification_level`.
- Files changed: `backend/scripts/check_handoff.py` (new),
  `backend/tests/test_check_handoff.py` (new, 43 tests),
  `backend/scripts/verify.py`, `backend/tests/test_verify.py` (15 new
  tests; 2 existing `_build_steps` structural tests updated for the new
  trailing step), `.claude/hooks/compact_checkpoint.py`,
  `backend/tests/test_compact_checkpoint.py` (1 new test),
  `docs/LLM_WORKFLOW.md`, `CLAUDE.md`, this handoff entry (two-iteration
  rotation: deleted the original Iteration 1, renumbered the
  seniority-classifier's Work done/Work review/Merge record to Iteration
  1, appended this entry as Iteration 2). No application code
  (`app/normalization/*`, `app/db/*`, ingestion) touched; no schema or
  migration.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (104
  source files under `app`/`tests`/`scripts`/`.claude/hooks`).
  `python -m scripts.check_repo` exits 0. Genuine external `python
  scripts/verify.py --level routine --focus tests/test_check_handoff.py
  tests/test_verify.py tests/test_compact_checkpoint.py` (full run,
  before this entry existed, to prove the wiring end-to-end): **10 of 11
  steps PASS** — **146 focused / 1820 full-suite tests** — with the new
  `handoff metadata validation` step correctly FAILing (`"the newest
  'Work done' section has no 'workflow-metadata' block"`), proving the
  step actually inspects the real file rather than trivially passing.
  This entry's own metadata block below now supplies that block; a
  second genuine run after this entry is committed (recorded by the
  reviewer's independent verification, per the standing process) is
  expected to show all 11 steps PASS.
- Self-review (Class R, abbreviated per `LLM_WORKFLOW.md`'s scaled-depth
  rule): confirmed `check_handoff.py` never imports or calls anything
  from `verify.py` (no recursive verifier invocation); confirmed
  `run_pytest_step`'s `counts_sink`/`counts_key` default to `None`/`""`
  so every pre-existing call site (all of them, until this slice) is
  unaffected; confirmed `_build_steps`'s `docs_only` branch never
  constructs the database/pytest `Step` closures at all under
  `--docs-only` (not merely skips running them) via a test whose fake
  runner/connectivity-check raise if called; confirmed
  `validate_against_run` independently rejects a parser-slice's
  `not_run` focused count even when isolated from `validate_structure`
  (a defense-in-depth unit test, not merely relying on the structural
  check).
- Deviations/known limitations: this entry's own metadata block is
  necessarily written after the verification run whose counts it
  declares (146/1820, from the run above) rather than the reviewer
  re-deriving them independently — this is inherent to how any
  self-describing ledger works and is exactly why `check_handoff.py`'s
  cross-check against the *reviewer's own* subsequent run exists as a
  separate, independent safeguard. The nine-category historical-defect
  checklist and the pilot's success thresholds are newly authored process
  text, not independently re-derived from a separate source, since this
  is their first codification.
- STOP — awaiting Codex review. Do not merge, begin `classify_experience`
  or any other Phase 3 parser, or start pilot slice 2/3 of Workflow v3.1
  without separate authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: tooling
verification_level: routine
focused_test_selector: tests/test_check_handoff.py tests/test_verify.py tests/test_compact_checkpoint.py
focused_test_count: 146
full_suite_count: 1820
```

### Work review

- Date/reviewer: 2026-09-08, Codex. Diff reviewed: `f003595..d8db682` on
  `tooling/workflow-v3.1-handoff-metadata` (including `62fe128`).
- Verdict: **Approved with binding clarifications.** Five bounded corrections
  below are required before merge; the overall design can remain.
- Independent verification: canonical routine verifier with the three declared
  focus files passes all **11 steps**, **146 focused / 1820 full-suite tests**,
  including static checks, metadata validation, and temporary-directory cleanup.
  Read-only database inspection confirms development `0006`, test `0017`.
  No implementation, test, migration, or hook file changed during this review.
- **1 — Medium: docs-only bypasses parser/tooling verification.**
  `backend/scripts/check_handoff.py:172` returns from `not_run` validation without
  requiring `slice_kind: docs`; `:263` likewise accepts docs-only by level alone.
  Direct probes accept both parser and tooling `not_run` declarations; the real
  `verify.handoff_metadata_step` returns PASS for tooling with no observed tests.
  Require `not_run` to be docs-only and `focused_test_selector: none`; independently
  reject non-docs entries when `docs_only=True`. Add end-to-end metadata/step tests
  for parser/tooling rejection and docs acceptance. No Git-diff classifier is required.
- **2 — Medium: focused-run evidence can be false.**
  `check_handoff.py:287` treats an unparseable executed focus run as an omitted run;
  `:311` checks selector identity only for parsers. Reproduced PASS with an executed
  focus whose parsed counts are None and metadata claiming not_run; also reproduced
  tooling PASS when declared and actual selectors differ but both counts equal 3.
  Use actual selector presence to distinguish omitted from unparseable focus;
  when focus ran, require readable counts, a numeric declaration, and matching
  selectors for every slice kind. Add both regressions and an omitted-focus control.
- **3 — Medium: malformed metadata can silently pass.**
  `check_handoff.py:129` overwrites duplicate keys; `:143` checks workflow_version
  presence but never its value. Reproduced acceptance of workflow_version=garbage
  and conflicting duplicate full_suite_count declarations (last one silently wins).
  Require the supported version, reject duplicate/empty/unknown keys and multiple
  metadata blocks in the selected Work done section, and reject empty required
  selectors/paths. Add focused positive/negative tests without inspecting old entries.
- **4 — Low: malformed input escapes the reported validation failure path.**
  `check_handoff.py:133` uses isdigit() before int(): the value U+00B2 passes the
  predicate and raises ValueError. Missing handoff files also raise FileNotFoundError
  through `verify.handoff_metadata_step`, bypassing its StepResult/summary handling.
  Validate ASCII integer syntax and translate expected conversion/read/decode failures
  into HandoffValidationError at the input boundary, for both standalone and verifier
  entry points. Report concise errors without echoing file contents. Test malformed
  counts, missing/unreadable handoff, and invalid UTF-8; retain cleanup on failure.
- **5 — Medium: durable pilot rules omit the approved experiment.**
  `docs/LLM_WORKFLOW.md:301` replaces the promised pre-review implementation
  contract/counterexample passes with two Class-H-only proposal passes. The Class-R
  experience parser therefore misses the intended requirement. The implementation
  also omits the mutation-proof rule and numerical success thresholds, and counts
  tooling as pilot slice 1 although the approved proposal makes experience slice 1.
  Restore both implementation self-review passes for applicable pilot parser slices,
  proposal preflight for new parsing forms/invariants, the load-bearing regression
  mutation proof, and the three-applicable-slice measurement window starting with
  experience. Record the agreed targets: at most one correction round per slice,
  zero confidently-wrong review findings, zero handoff count defects, and zero
  regressions that pass with their required guard disabled. Preserve proportional
  docs verification; clarify that docs may truthfully record routine tests if run
  (the existing test permits this despite the docs saying not_run is required).
  Align CLAUDE.md and the retrospective trigger. Record deviations in the new entry;
  preserve historical Work done/review text. No extra automation is requested.
- Correction verification: targeted checker/verifier/hook tests and one canonical
  focused run with updated actual metadata counts; no migration round-trip needed.
  Add a concise new Work done entry recording the final successful run rather than
  leaving final success as an expectation for the reviewer to establish.
- STOP: user authorizes the bounded correction pass; no merge, experience
  implementation, other parser, or provider contact is approved by this review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R (tooling)
  correction pass on `tooling/workflow-v3.1-handoff-metadata` addressing
  all five findings in Iteration 1's `Work review` (commit `38ed0a2`)
  above. Base -> ending commit: `38ed0a2` -> this commit; same branch.
  Preserved the overall design (Approved with binding clarifications) —
  every correction below is bounded to the five findings, no scope
  expansion.
- Finding 1 (Medium — docs-only bypassed parser/tooling verification):
  `check_handoff.py`'s `validate_structure` now rejects
  `verification_level: not_run` unless `slice_kind: docs` (structural,
  independent of invocation), and also requires `focused_test_selector:
  none` whenever `not_run` applies. `validate_against_run` independently
  rejects `docs_only=True` when the declared `slice_kind` isn't `docs`,
  as its own defense-in-depth. Added 4 unit tests plus 3 end-to-end
  `validate_handoff` tests covering parser rejection, tooling rejection,
  and docs acceptance.
- Finding 2 (Medium — focused-run evidence could be false): rewrote
  `validate_against_run`'s focus handling to use
  `actual_focus_selector is not None` (not `actual_focused_count is
  None`) as the *omitted* signal, distinguishing it from focus having
  run with an unparseable summary — a declared `not_run` with focus
  actually used is now rejected. The focus-selector match check now
  applies to every `slice_kind`, not only `parser`. Added 5 tests: the
  reproduced not_run-with-executed-focus case, an unparseable-focused-
  count-with-numeric-declaration case, a tooling selector-mismatch case,
  and an omitted-focus control.
- Finding 3 (Medium — malformed metadata could silently pass):
  `parse_metadata_fields` now rejects a duplicate key and an empty key
  (previously last-one-wins); `extract_latest_work_done_metadata_text`
  rejects more than one `workflow-metadata` block in the same `Work
  done` section (previously `.search` silently took the first);
  `validate_structure` now checks `workflow_version`'s actual value
  (`v3.1-pilot` only) and rejects any empty required field or an empty
  `fixture_path`. Added 7 tests.
- Finding 4 (Low — malformed input escaped the reported failure path):
  `_require_int` now matches `^[0-9]+$` before calling `int()` (plain
  `str.isdigit()` accepted non-ASCII "digit" characters, e.g. `²`, that
  `int()` itself then rejected with an unhandled `ValueError`). Added
  `_read_handoff_text`, converting a missing/unreadable file or invalid
  UTF-8 into `HandoffValidationError` at the read boundary, used by both
  `validate_handoff` (the verifier entry point) and `main()` (the
  standalone entry point) — neither `check_handoff.py` call site can
  crash `verify.py`'s `handoff_metadata_step` with an uncaught OS-level
  exception any longer. Added 6 tests (direct `_require_int` probe,
  `validate_structure`-level integration, missing-file and invalid-UTF-8
  cases at both the `_read_handoff_text` and `validate_handoff`/`main()`
  levels).
- Finding 5 (Medium — durable pilot rules omitted the approved
  experiment, docs-only): `docs/LLM_WORKFLOW.md`'s pilot section now
  restores, as a distinct "Implementation self-review passes (parser
  slices)" section, the contract-conformance and counterexample passes
  for parser-slice implementations (separate from the proposal-time
  claim-to-evidence/historical-defect preflight, which is unchanged);
  added the load-bearing regression mutation-proof rule as its own
  section; corrected the pilot's counted-slice window to three **parser**
  slices starting with `classify_experience` (this tooling slice is
  enabling infrastructure, not one of the three); replaced the
  retrospective's vague qualitative-only criteria with the agreed
  numerical thresholds (at most one correction round per slice, zero
  confidently-wrong findings, zero handoff count defects, zero
  regressions passing with their guard disabled); and corrected the
  `docs` slice_kind wording — `not_run` is permitted for docs, never
  mandatory (a docs slice that actually ran tests truthfully records
  `routine` with real counts; the existing code already allowed this,
  only the prose was wrong). `CLAUDE.md`'s pilot marker and this file's
  intro line updated to match. No code change for this finding.
- Files changed: `backend/scripts/check_handoff.py`, `backend/tests/
  test_check_handoff.py` (+25 tests, 68 total), `docs/LLM_WORKFLOW.md`,
  `CLAUDE.md`, this handoff entry. `backend/scripts/verify.py` and its
  tests, `.claude/hooks/compact_checkpoint.py` and its test: unchanged —
  none of the five findings required a change there (`handoff_metadata_step`
  already just forwards to `check_handoff.validate_handoff`, whose
  internal logic is what changed).
- Mutation-proof (Workflow v3.1 pilot's own newly-added rule, applied to
  this correction pass itself): for a representative set spanning all
  five findings (12 individual checks: Finding 1's slice_kind guard x4
  tests, Finding 2's omitted/unparseable distinction and universal
  selector-match x3 tests, Finding 3's duplicate-key and multi-block
  guards x2 tests, Finding 4's ASCII-int check x2 tests and file-read
  boundary x1 test), the specific fix was temporarily reverted, the
  corresponding new test(s) were confirmed to fail (reproducing the
  original defect, including one genuine uncaught `FileNotFoundError`
  and one uncaught `ValueError` escaping past `HandoffValidationError`),
  then the fix was restored and the tests reconfirmed passing. Not every
  one of the 25 new tests was individually mutation-tested — the
  remaining ones are structural variations (different slice_kind, field
  combinations) exercising the same guarded branches already proven
  load-bearing above.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (104
  source files). `python -m scripts.check_repo` exits 0. Genuine
  external `python scripts/verify.py --level routine --focus
  tests/test_check_handoff.py tests/test_verify.py
  tests/test_compact_checkpoint.py` (full run) — **171 focused / 1845
  full-suite tests** (was 146/1820; +25 focused from the new
  `check_handoff` tests, +25 full-suite matching exactly). All 11 steps
  PASS, including `handoff metadata validation` against this entry's own
  metadata block below.
- Deviations/known limitations: none new. Finding 5 is documentation-only
  by its own nature; no code changed for it. The mutation-proof scope
  above is representative, not exhaustive, as stated.
- STOP — awaiting Codex re-review. Do not merge, begin `classify_experience`
  or any other Phase 3 parser, or start pilot slice 2/3 of Workflow v3.1
  without separate authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: tooling
verification_level: routine
focused_test_selector: tests/test_check_handoff.py tests/test_verify.py tests/test_compact_checkpoint.py
focused_test_count: 171
full_suite_count: 1845
```

### Work review

- Date/reviewer: 2026-09-08, Codex.
- Diff reviewed: `38ed0a2..41b3f70` on
  `tooling/workflow-v3.1-handoff-metadata`.
- Verdict: **Changes requested.** Findings 1, 2, 4, and 5 are closed. Finding 3
  is substantially corrected, but one explicitly requested malformed-metadata case
  remains accepted.
- Independent verification: `git diff --check` is clean; the three focused modules pass
  **171/171 tests** with a workspace-local pytest base directory. The default pytest temp
  root was inaccessible to this reviewer account (`PermissionError`) and is an
  environment issue, not a product/test failure. A direct executable probe reproduced
  the remaining issue below. The full 1845-test suite was not rerun because this bounded
  structural defect is already independently demonstrated.
- **Medium — unknown metadata keys still pass validation.** The Iteration 1 correction
  explicitly required rejecting duplicate, empty, **and unknown** keys. The new parser
  rejects duplicates and empty keys, while `validate_structure()` checks required and
  conditional fields but never compares the supplied key set against the closed metadata
  schema (`backend/scripts/check_handoff.py:87`, `:171`). Directly adding
  `typo_full_sute_count: 1` to an otherwise-valid tooling block still returns normally;
  `backend/tests/test_check_handoff.py` has no unknown-key regression. This leaves typos
  and unsupported fields silently ignored, contrary to the validator's fail-closed goal.
- Bounded correction: define the complete allowed field-name set (the six required fields
  plus `lightweight_checks`, `fixture_path`, and `fixture_count`) and have structural
  validation reject every supplied key outside it before conditional checks. Add a
  regression proving an otherwise-valid block with an invented/typo key fails, mutation-
  prove that test, then rerun the focused checker/verifier/hook tests and canonical
  verifier with updated metadata counts. No verifier orchestration, hook, product,
  migration, or pilot-policy change is requested.
- STOP: do not merge or begin `classify_experience` or another parser until this bounded
  correction is implemented and re-reviewed.
