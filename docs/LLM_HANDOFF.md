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
  correction lifetime, `7ce4a1d`) -> candidate `C3`: this commit; same
  branch `phase-3/realistic-evaluation-corpus`, on top of the existing
  pushed tip `A2 = 616dd59a17c6c6d64cecf359f625796de311bd24`.
  `slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d` (unchanged).
  Addresses Sol's re-review of `C2 = f9f531eb568027ebad311404ed05
  cba9c28ab0c2` / `A2 = 616dd59a17c6c6d64cecf359f625796de311bd24`, both
  of which remain unamended, still pushed, still present in history
  exactly as they were; the `C2`/`A2` receipt cycle
  (`2b6174d6-138e-4cd9-b1f8-7b770fdbd282`) is superseded and
  non-reusable as of this entry. No network contact, board-token
  request, corpus acquisition, `R`, merge, `M`/`Q`, parser-semantic
  change, or database work performed.
- **Finding 1 (total-run byte accounting)**: `_stream_get` checked the
  per-response cap before charging a chunk to `_RunBudget`, so a chunk
  rejected for exceeding `MAX_RESPONSE_BYTES` was never counted toward
  `MAX_TOTAL_RUN_BYTES` -- repeated oversized responses could never
  exhaust the cumulative cap. Fixed: every chunk is now charged to
  `run_budget.consume` first, and only then is the per-response ceiling
  evaluated, so `FatalBudgetExhaustedError` takes precedence over an
  ordinary per-response `EvaluationFetchError` when one chunk triggers
  both. Three regressions added:
  `test_stream_get_charges_run_budget_even_when_per_response_cap_rejects_the_chunk`,
  `test_run_acquisition_repeated_per_response_overflows_still_hit_the_cumulative_cap`,
  `test_run_acquisition_simultaneous_overflow_raises_fatal_error_and_stops_immediately`.
- **Finding 2 (complete adjudication)**: `disagreement.adjudication`
  previously resolved `final_value` alone, so an adjudication that only
  ever resolved a null value could coincidentally "match" an `absent`/
  unavailable primary annotation without ever actually resolving the
  real disagreement (Sol's exact reproduction: primary absent/null/
  unavailable, second present_supported/remote/inferred, adjudication
  resolving only null -- previously accepted). Fixed: for scalar/
  composite-component annotations, adjudication now resolves the
  complete `(final_outcome, final_value, final_provenance)` label,
  validated with the same vocabulary/type/null-iff-unavailable/outcome-
  value rules as any primary annotation, and the primary annotation's
  own scored triple must equal it exactly; for per-skill annotations,
  adjudication resolves `final_outcome` only, checked against the
  primary's own `outcome`. A `disagreement` block is now also rejected
  if the primary and second annotation's scored labels are identical
  (`_validate_scalar_disagreement`/`_validate_skill_id_disagreement`
  replace the old single generic `_validate_disagreement`). New
  regressions cover: the exact reproduced defect
  (`test_load_corpus_rejects_adjudication_resolving_only_a_null_value`),
  independent outcome-only and provenance-only disagreement acceptance,
  a "no actual difference" rejection for both the scalar and skill-id
  flavors, and a skill-id adjudication inconsistent with the primary
  outcome.
- **Finding 3 (usable-detail text)**: `_is_usable_detail_candidate`
  replaced `bool(title)`/`bool(description)` with `_has_meaningful_text`,
  which rejects missing, empty, whitespace-only (`str.isspace()` --
  including NBSP), and Unicode-format-character-only (category `Cf`)
  text, including any mixture of the two, while adding no broader
  semantic quality heuristic. Regressions cover an ASCII-whitespace-only
  title, an NBSP-only sanitized description produced by the real
  `convert_html_to_text("<p>&nbsp;</p>")` path, format-character-only
  content, mixed whitespace/format-character-only content, and ordinary
  non-empty text (including text merely *containing* stray whitespace/
  format characters alongside real words, which must still be accepted).
- **Adversarial self-review**: a dedicated pass traced all three fixes'
  actual execution paths (exception propagation for finding 1; every
  validation branch and a deliberate search for a bypass of the "no
  actual difference" check for finding 2; character-by-character boolean
  logic for finding 3) and found no defect requiring a code change.
  **Disclosed, not fixed** (deliberately out of Sol's narrow scope for
  finding 3): `_has_meaningful_text` does not reject text composed
  solely of Unicode control characters (category `Cc`, e.g. `\x00`) --
  neither `str.isspace()` nor category `Cf` -- since Sol's instruction
  was explicitly limited to whitespace and category-`Cf` text and warned
  against adding broader semantic quality heuristics; noted here for a
  possible future, separately-authorized bounded amendment rather than
  addressed unilaterally.
- Files changed: `backend/scripts/fetch_greenhouse_evaluation_postings.py`
  (streaming budget reorder, `_has_meaningful_text`),
  `backend/scripts/evaluate_phase3_corpus.py` (adjudication rewrite),
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py` (60
  tests, up from 45), `backend/tests/test_evaluate_phase3_corpus.py` (55
  tests, up from 49), `docs/LLM_HANDOFF.md` (this entry, plus the
  iteration rotation above). No other file touched -- no network
  contact, board-token request, corpus acquisition, parser-semantic
  change, database work, or unrelated tooling.
- **Two-iteration rotation applied**: the oldest iteration (this
  slice's original `C`/`A`) is deleted; the former Iteration 2 (the
  `C2`/`A2` correction) is renumbered to Iteration 1, unchanged in
  content; this correction becomes Iteration 2.
- Verification: pending — see the workflow-metadata block below and the
  publication (`A3`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
executed_gate: final
candidate_sha: 5aa1a57271b2317885e154e0de5e7b4cd183d94e
receipt_id: c394be69-b724-44ab-8e26-05bdce25cfba
receipt_path: docs/verification-receipts/5aa1a57271b2317885e154e0de5e7b4cd183d94e/c394be69-b724-44ab-8e26-05bdce25cfba.json
full_suite_count: 2999
focused_test_count: 213
mutation_witness_count: 34
```

---

## Iteration 2

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
state: pending
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
```
