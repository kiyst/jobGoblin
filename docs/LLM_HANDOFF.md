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

- Date/agent: 2026-09-20, Claude Code (Sonnet 5). Risk class **H** (same
  slice, same authorization). Base `B` (unchanged for this slice's whole
  correction lifetime, `7ce4a1d`) -> candidate `C4`: this commit; same
  branch `phase-3/realistic-evaluation-corpus`, on top of the existing
  pushed tip `A3 = 18e1d03ea7f8126ca8e3d36e3dfa4f0354d7d612`. `slice_id:
  2026-09-20-realistic-evaluation-corpus-7ce4a1d` (unchanged). Addresses
  Sol's C3/A3 re-review, which confirmed all three prior mechanisms
  correct but found one remaining High evidence-integrity finding on
  `C3 = 5aa1a57271b2317885e154e0de5e7b4cd183d94e` / `A3 =
  18e1d03ea7f8126ca8e3d36e3dfa4f0354d7d612`, both of which remain
  unamended, still pushed, still present in history exactly as they
  were; the `C3`/`A3` receipt cycle
  (`c394be69-b724-44ab-8e26-05bdce25cfba`) is superseded and
  non-reusable as of this entry. No network contact, board-token
  request, corpus acquisition, `R`, merge, `M`/`Q`, parser-semantic
  change, database work, or fetcher change performed.
- **Finding (contradictory scored label, evidence integrity)**: the
  loader enforced only one direction of the outcome/value invariant --
  "any outcome other than `present_supported` requires a null
  `expected_value`" -- but never its converse. `outcome=
  "present_supported"` with `expected_value=null`/`expected_provenance=
  "unavailable"` (Sol reproduced this through `load_corpus`) silently
  loaded despite being self-contradictory: `present_supported` means
  the parser is expected to return a real value, while null/unavailable
  means expected abstention. Left uncorrected, such a record corrupts
  `supported_correctness`/`supported_abstention`'s shared denominator
  downstream.
- **Fix**: added `_validate_scored_label`, one function now shared
  identically by every place a scalar/composite-component scored label
  is checked -- the primary annotation (via `_validate_scalar_
  annotation_shape`), `disagreement.second_annotation` (the same
  function, `allow_disagreement=False`), and `disagreement.
  adjudication`'s resolved `final_outcome`/`final_value`/
  `final_provenance` triple (via `_validate_scalar_disagreement`,
  passing `outcome_field="final_outcome"` etc. so error messages still
  name the real JSON keys) -- so none of the three can ever drift into
  different rules. The new check is exactly bidirectional:
  `(outcome == "present_supported") != (expected_value is not None)`
  raises. The two previously-duplicated inline invariant blocks (one in
  the annotation-shape validator, one in the disagreement validator)
  are deleted outright, not left behind alongside the new function.
  Skill-id annotations are outcome-only and were correctly left
  untouched -- no `expected_value`/`expected_provenance` concept
  applies to them.
- **Regressions added** (3 rejections + 2 positive controls, all new):
  `test_load_corpus_rejects_present_supported_with_null_value` (the
  exact reproduced defect, on the primary annotation);
  `test_load_corpus_rejects_second_annotation_present_supported_with_null_value`;
  `test_load_corpus_rejects_adjudication_present_supported_with_null_value`
  (traced to confirm each raises from the new bidirectional check
  specifically, not some other already-invalid field in the same
  constructed record); `test_load_corpus_accepts_present_supported_with_non_null_value`
  and `test_load_corpus_accepts_absent_with_null_value` (the two valid,
  non-contradictory directions of the same invariant). One pre-existing
  test, `test_load_corpus_accepts_disagreement_differing_only_in_outcome`,
  previously relied on a now-invalid `present_supported`/null/
  unavailable primary label to build an "outcome-only difference"
  disagreement; corrected to use `absent`/`ambiguous` (both non-
  `present_supported`, both null/unavailable) instead, preserving a
  genuine differing-outcome disagreement under the new invariant.
- **Mutation-proved**: temporarily reverted the new bidirectional check
  in `_validate_scored_label` back to the old one-directional form
  (`outcome != "present_supported" and expected_value is not None`) and
  reran the full focused suite -- exactly the 3 new rejection tests
  failed (one of the three, the adjudication case, failed via a
  different, still-correctly-firing consistency check rather than a
  false pass -- confirming the mutation genuinely disabled the intended
  guard rather than the test being vacuous), all other 57 tests still
  passed; restored the fix and reran to confirm 60/60 pass again.
- **Adversarial self-review**: a dedicated pass traced every check in
  `_validate_scored_label` in order, confirmed no `bool()`/truthiness
  substitutes for `is None`/`is not None` anywhere, confirmed all three
  call sites actually reach the centralized function on every path with
  no duplicated/contradicting inline check remaining, confirmed the
  skill-id path was untouched, and traced both new rejection-by-
  disagreement tests field-by-field against the exact validation order
  to confirm each raises for the intended reason. No defect requiring a
  further change was found.
- Files changed: `backend/scripts/evaluate_phase3_corpus.py` (the
  centralized `_validate_scored_label` function and its three call
  sites), `backend/tests/test_evaluate_phase3_corpus.py` (60 tests, up
  from 55), `docs/LLM_HANDOFF.md` (this entry, plus the iteration
  rotation above). No other file touched -- no fetcher change, no
  network contact, no board-token request, no corpus acquisition, no
  parser-semantic change, no database work, no workflow-tooling change.
- **Two-iteration rotation applied**: the oldest iteration (the
  `C2`/`A2` correction) is deleted; the former Iteration 2 (the
  `C3`/`A3` correction) is renumbered to Iteration 1, unchanged in
  content; this correction becomes Iteration 2.
- Verification: pending — see the workflow-metadata block below and the
  publication (`A4`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
executed_gate: final
candidate_sha: 61a18819abb509ab0a5f74c60924cc968dc1499f
receipt_id: 16ea83c7-ea7a-4a5e-aea8-e53e3c4b8c1a
receipt_path: docs/verification-receipts/61a18819abb509ab0a5f74c60924cc968dc1499f/16ea83c7-ea7a-4a5e-aea8-e53e3c4b8c1a.json
full_suite_count: 3004
focused_test_count: 218
mutation_witness_count: 34
```

---

## Iteration 2

### Work done

- Date/agent: 2026-09-24, Claude Code (Sonnet 5). Risk class **H** (same
  slice, same authorization). Base `B` (unchanged for this slice's whole
  correction lifetime, `7ce4a1d`) -> candidate `C5`: this commit; same
  branch `phase-3/realistic-evaluation-corpus`, on top of the existing
  pushed tip `A4 = 549229bde2c59f6453b69c852c9ce5175b6a2f52`. `slice_id:
  2026-09-20-realistic-evaluation-corpus-7ce4a1d` (unchanged). Implements
  Sol's frozen, twice-revised sanitizer-correction design proposal
  (addressing the real double-HTML-encoding defect discovered during the
  authorized acquisition against `gitlab`/`anthropic`/`discord`, and the
  30-candidate manually-reviewed salvage batch produced from it, both
  preserved unchanged by this slice). No network contact, board-token
  request, corpus acquisition, staged/review-artifact change, parser-
  semantic change, database work, or unrelated tooling performed.
- **Explicit input-mode contract**: `convert_html_to_text(html, *,
  mode="standard")` gained a second mode, `"declared-double-escaped"`,
  selected only by an explicit caller argument -- never inferred from
  content. `"standard"` (the default) is byte-for-behavior identical to
  the function's behavior before this change, with zero new checks at
  any stage. `"declared-double-escaped"` permits exactly one additional
  `html.unescape()` pass, bracketed by two fail-closed validation
  stages sharing one pair of fixed regex constants
  (`_ESCAPED_ANGLE_REFERENCE_RE` for fully-terminated named/decimal/hex
  escaped angle-bracket forms; `_UNTERMINATED_NAMED_ANGLE_RE` for a
  semicolonless `&lt`/`&gt` prefix, rejected regardless of what follows
  it, since its interaction with `html.unescape()`'s own legacy
  longer-entity matching -- e.g. the real, unrelated `&ltimes;` -- is not
  trusted to be safe): raw-input validation
  (`"mixed-literal-and-escaped-markup"` if a literal angle bracket and an
  escaped form coexist; `"unsupported-angle-reference"` for any bare
  semicolonless form) and post-decode validation
  (`"unsupported-angle-reference"` or `"residual-nested-encoding"`). A
  new `HtmlDoubleEncodingError(HtmlConversionError)` carries only a fixed
  category string, never content. A documented accepted limitation: a
  legitimate escaped-code example that survives exactly one correct
  decode is indistinguishable from a genuine unresolved second layer, so
  `"declared-double-escaped"` mode conservatively rejects it too --
  proved by a direct regression, never "fixed" by making the check
  smarter (that would violate the bounded design).
- **Explicit board specification and CLI grammar**: `BoardAcquisitionSpec`
  (`board_token`, `employer`, closed `content_mode`, `mode_basis_ref`)
  replaces the prior bare `(board_token, employer)` tuple everywhere
  (`run_acquisition`, `_fetch_board`, `_sanitize_job_detail`,
  `SanitizedCandidate`). `mode_basis_ref` is required (non-`None`) iff
  `content_mode == "declared-double-escaped"`, matching a closed grammar
  (`^(prior-capture|probe):[A-Za-z0-9_-]{1,100}$`) that resolves the
  authorization circularity: it must cite either a stable reference to
  evidence already retained from an earlier, separately authorized
  capture, or a separately authorized, distinct probe -- never the
  run's own unapproved contact. No permanent board-token-to-mode
  inference table exists anywhere. CLI grammar:
  `token:Employer:standard` (3 parts) or
  `token:Employer:declared-double-escaped:basis-kind:basis-id` (5
  parts); `_parse_board_arg` reuses the existing `validate_board_token`
  (translating its `ValueError` to `argparse.ArgumentTypeError`) and
  rejects every malformed input during argument parsing, strictly before
  `run_acquisition` is reachable. `mode_basis_ref`/`content_mode` are
  appended as fixed-format text onto the existing free-text
  `sanitization_lineage` provenance field -- no new structured schema
  field, so `evaluate_phase3_corpus.py`'s provenance validator needed no
  change, staying within this correction's frozen file scope.
- **Redaction ownership unchanged**: `_redact_contact_patterns` remains
  entirely in `fetch_greenhouse_evaluation_postings.py`, called exactly
  once per description, strictly after the full conversion (all decode
  stages) completes.
- **Adversarial self-review findings, fixed before this commit**: (1) a
  test claiming to prove "`_parse_board_arg` never contacts the
  network" asserted only that the function is not a coroutine -- a
  synchronous function can still perform blocking I/O, so the assertion
  proved nothing; removed rather than papered over (the actual
  guarantee -- every malformed input raises during argument parsing,
  strictly before `run_acquisition` is ever reachable in `main()` --
  is already established by the other `_parse_board_arg` rejection
  tests together with `main()`'s own control flow). (2)
  `BoardAcquisitionSpec`'s docstring claimed its mode/basis invariant as
  a hard contract, but nothing enforced it at construction -- only
  `_parse_board_arg` checked it, so any non-CLI caller building a spec
  directly could silently construct an inconsistent, unauthorized
  combination. Fixed: added `__post_init__` validation to the dataclass
  itself, with new regressions proving both valid combinations succeed
  and both invalid combinations raise `ValueError` at construction,
  independent of the CLI.
- Files changed (exactly the six named in the frozen proposal's scope,
  no others): `backend/scripts/greenhouse_html_convert.py`,
  `backend/scripts/fetch_greenhouse_evaluation_postings.py`,
  `backend/tests/test_greenhouse_html_convert.py` (26 -> 49 tests),
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py` (60 ->
  81 tests), `docs/DECISIONS/0010-realistic-evaluation-corpus-
  methodology.md` (states the corrected contract and the salvage
  batch's honest lineage), `docs/LLM_HANDOFF.md` (this entry, plus the
  iteration rotation above).
- Verification: pending — see the workflow-metadata block below and the
  publication (`A5`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
```
