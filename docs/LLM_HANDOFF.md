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
  correction lifetime, `7ce4a1d`) -> candidate `C2`: this commit; same
  branch `phase-3/realistic-evaluation-corpus`, on top of the existing
  pushed tip `A = 5160a57731c49e4a28bf4f4cde15b9fc45d4209c`.
  `slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d` (unchanged).
  Addresses Sol's "Changes requested" verdict on `C = a0ddad9489c9020
  b1c1921d4dac182e7a42ef3d0` / `A = 5160a57731c49e4a28bf4f4cde15b9fc45d42
  09c`, both of which remain unamended, still pushed, still present in
  history exactly as they were; the `C`/`A` receipt cycle
  (`788ec89b-c81f-41c0-859b-ded428c2d466`) is superseded and
  non-reusable as of this entry. No network contact, board-token
  request, corpus acquisition, `R`, merge, `M`/`Q`, parser-semantic
  change, or database work performed.
- **Finding 1 (streaming total-run budget)**: `fetch_greenhouse_
  evaluation_postings.py`'s `_stream_get` checked the total-run budget
  only once, after an entire response had already been downloaded, and
  the same `EvaluationFetchError` its per-board caller already treats as
  an ordinary, skip-and-continue failure. Fixed: the per-response cap
  and the shared `_RunBudget` are now both enforced before each streamed
  chunk is accepted; exhausting the budget now raises a new
  `FatalBudgetExhaustedError`, deliberately **not** a subclass of
  `EvaluationFetchError`, so it propagates straight out of
  `run_acquisition`'s per-board exception handling uncaught, aborting
  the whole run. Regression:
  `test_run_acquisition_fatal_budget_exhaustion_prevents_later_board_requests`
  proves exhausting a 10-byte budget on board A's first request leaves
  boards B and C completely uncontacted.
- **Finding 2 (usable-record gate + loader hardening)**: added
  `_is_usable_detail_candidate` (matching id, non-empty title, non-empty
  sanitized content) so `_fetch_board` only counts a genuinely usable
  detail record toward board success; an unusable one is skipped, not
  aborted. `evaluate_phase3_corpus.py`'s loader now rejects (each with
  its own regression): duplicate JSON keys at any nesting depth, an
  empty corpus, a non-list top level, a duplicate record id, any missing
  scalar/composite/skill annotation, any `bool` masquerading as an
  `int`, any value from the wrong parser's closed vocabulary, malformed/
  naive `frozen_at`/`accessed_at`/`reviewed_at`/`adjudicated_at`
  timestamps, a malformed `capture.board_token`/`capture.job_id`, and a
  missing/malformed `manual_review` block.
- **Finding 3 (exhaustive annotations + full disagreement validation)**:
  annotations are now exhaustive over all three scalar parsers, every
  composite component, and every taxonomy canonical id under `skills`
  (never a subset). `_validate_disagreement` now fully validates
  `second_annotation`'s entire shape (exact keys, outcome, `expected_
  value`/`expected_provenance` invariants, metadata) via the same
  flavor-specific validator used for the primary annotation --
  previously only the scored field and metadata were checked, so a
  `second_annotation` with a garbage `outcome`/`expected_provenance`
  loaded silently (an adversarial-review finding on this same commit,
  below). `adjudication.final_value` must still equal the annotation's
  own scored field.
- **Finding 4 (corrected metrics)**: `supported_correctness`/
  `supported_abstention`/`confidently_wrong` now unconditionally share
  one denominator for every `present_supported` case with a completed
  invocation (an abstention is incorrect but never also confidently
  wrong). `_evaluate_composite` now increments a composite parser's
  `runtime_failure` exactly once per invocation, never once per
  component, and skips all component-level scoring on a raised
  invocation. `MismatchDetail` records are deterministic, keyed by
  record/parser/component, and never carry posting text.
- **Finding 5 (partitioning)**: `_validate_partitioning` requires
  non-empty `dev` and `holdout` employer sets and rejects any employer
  appearing in both. `evaluate_corpus` returns `dev`/`holdout`/
  `combined` as three fully independent `SplitEvaluation`s.
- **Finding 6 (exhaustive skills outcome model)**: skills annotations
  are now `{canonical_id: {outcome, ...}}` over every known id (never a
  flat `expected_canonical_ids` list); `_evaluate_skills` derives
  recall and all three false-positive categories from every known id's
  outcome, and precision plus `false_positive_outside_frozen_set` from
  every actually-returned id's own outcome in that same frozen map --
  proven by `test_skills_record_with_all_four_outcomes_simultaneously`
  (one record scoring `present_supported`, `present_unsupported_form`,
  and `ambiguous` ids all at once).
- **Adversarial self-review findings, fixed before this commit** (2
  findings, both confirmed real by tracing execution paths, not merely
  re-reading docstrings):
  - `fetch_greenhouse_evaluation_postings.py::_fetch_board`: a
    sanitization failure on one job (`_sanitize_job_detail` raising
    `EvaluationFetchError` for an unclosed `<script>`/`<style>`) was
    uncaught locally, so it propagated out of `_fetch_board`, discarding
    every already-collected valid candidate from earlier job ids on
    that same board and aborting the board entirely -- directly
    contradicting this module's own "skipped, not staged, does not
    abort the board" contract. Fixed: caught locally and treated the
    same as an unusable record (skip, continue). Regression:
    `test_fetch_board_skips_unsanitizable_record_without_discarding_earlier_candidates`.
  - `evaluate_phase3_corpus.py::_validate_disagreement`: as noted under
    finding 3 above, `second_annotation` was validated on its scored
    field and metadata only -- a garbage `outcome` or `expected_
    provenance` in `second_annotation` loaded without error. Fixed by
    extracting `_validate_scalar_annotation_shape`/`_validate_skill_id_
    annotation_shape` (parameterized on `allow_disagreement`, so a
    `second_annotation` is held to the same rules as a primary
    annotation but may never declare a nested disagreement of its own)
    and validating `second_annotation` through the same function as the
    primary annotation. Four new regressions cover invalid `outcome`,
    invalid `expected_provenance`, a nested `disagreement`, and the
    previously-untested skill-id disagreement path.
- Files changed: `backend/scripts/evaluate_phase3_corpus.py` (rewritten
  loader/evaluator), `backend/scripts/fetch_greenhouse_evaluation_
  postings.py` (streaming budget + usable-record gate + sanitization-
  failure fix), `backend/tests/test_evaluate_phase3_corpus.py`
  (rewritten for the new exhaustive schema, 49 tests, up from 36),
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py` (45
  tests, up from 32), `docs/LLM_HANDOFF.md` (this entry, plus the
  iteration rotation above). No other file touched -- no network
  contact, board-token request, corpus acquisition, parser-semantic
  change, database work, or unrelated tooling.
- **Two-iteration rotation applied**: the oldest iteration (the
  skill-classifier Unicode-format-character correction, `C3`/`A3`,
  merged and `Q`'d) is deleted; the former Iteration 2 (this slice's
  original `C`/`A`) is renumbered to Iteration 1, unchanged in content;
  this correction becomes Iteration 2.
- Verification: pending — see the workflow-metadata block below and the
  publication (`A2`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
executed_gate: final
candidate_sha: f9f531eb568027ebad311404ed05cba9c28ab0c2
receipt_id: 2b6174d6-138e-4cd9-b1f8-7b770fdbd282
receipt_path: docs/verification-receipts/f9f531eb568027ebad311404ed05cba9c28ab0c2/2b6174d6-138e-4cd9-b1f8-7b770fdbd282.json
full_suite_count: 2978
focused_test_count: 192
mutation_witness_count: 34
```

---

## Iteration 2

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
state: pending
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
```
