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

---

## Iteration 2

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
