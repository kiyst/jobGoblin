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

- Date/agent: 2026-09-20, Claude Code (Sonnet 5). Risk class **H**
  (Sol's verdict: one bounded slice covering both acquisition and
  evaluation under a single authorization). Base `B` -> candidate `C`:
  `7ce4a1dc770827653ccf8140188c5d1dec6621d8` -> this commit; new branch
  `phase-3/realistic-evaluation-corpus`, cut from a freshly verified
  clean `main` (`main` == `origin/main`, both at `7ce4a1d`).
  `slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d`.
  `slice_kind: tooling` (product-evaluation code, not a classifier and
  not workflow/verification tooling — excluded from the three-slice
  discretionary-tooling freeze per its own binding authorization).
- **Blocked, honestly, before this entry was written**: the user's
  authorization named board token 1 (`gitlab`) but left board tokens 2
  and 3 as the literal placeholder text `[INSERT EXACT TOKEN]`/
  `[INSERT EXACT TOKEN OR none]`. Per the binding requirement that at
  least two distinct boards must succeed or the fetcher aborts with no
  corpus, and per the standing rule that no network request is
  authorized until the final exact token list is recorded, **no live
  network contact was attempted**. This `C` implements and thoroughly
  tests every piece that does not require it; the live fetch, the real
  corpus, and the real baseline report remain outstanding, explicitly
  flagged to the user rather than guessed at.
- **`backend/scripts/greenhouse_html_convert.py`** (new):
  `convert_html_to_text(html) -> str`. Deterministic: covered whitespace
  is exactly `" \t\n\r"`; CRLF/CR normalize to `\n` before parsing; each
  block boundary (`p`/`div`/`br`/`li`/`h1`-`h6`/`ul`/`ol`) is exactly one
  `\n`, deduped at the source for adjacent/nested tags; `script`/`style`
  content is suppressed; horizontal ASCII space/tab runs collapse to one
  space per line; repeated blank lines (from genuine source whitespace
  text nodes, not from tag-boundary insertion, which never stacks)
  collapse to one; NBSP and every other Unicode whitespace/format
  character are preserved unchanged. 20 offline regressions in
  `backend/tests/test_greenhouse_html_convert.py`, including the exact
  concatenation/entity/suppression/blank-line cases the binding
  requirement named.
- **`backend/scripts/fetch_greenhouse_evaluation_postings.py`** (new):
  two-phase per-board fetch (one metadata-only list `GET`, never
  `content=true`; deterministic selection of <=10 job ids before any
  description exists to examine; one detail `GET` per id, never
  `questions=true`/`pay_transparency=true`) reusing
  `canary_greenhouse.py`'s origin/token-validation/streaming-cap
  primitives directly rather than re-deriving them. Zero retries. Two
  independent byte caps (5,000,000 per response, 20,000,000 per run).
  Reads only `id`/`title`/`location.name`/`content` from a parsed
  response — no other key is ever traversed, so an unknown or sensitive
  upstream field cannot reach a log, a staged record, or the committed
  corpus by construction, never by enumeration. Redaction is explicitly
  documented as defense in depth only. `compensation_text` is always
  `None` here. Requires >=2 distinct successful boards or raises without
  staging anything; a failing board is skipped, never retried, never
  substituted. Staging is fixed (`backend/.evaluation-staging/`, now
  gitignored), atomic, and create-only, reusing
  `verification_receipts.write_receipt_atomic`'s exact algorithm
  (duplicated, since that function is dict-only and this module's
  payload is a JSON array). 32 offline tests in
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py`, all via
  `httpx.MockTransport` (mirroring `test_canary_greenhouse_mapping.py`'s
  own established pattern) — no test causes a real HTTP request.
- **`backend/scripts/evaluate_phase3_corpus.py`** (new): a fail-closed
  loader (rejects unknown record/annotation/component fields, an
  unknown parser or composite-component name, `frozen != true`, an
  unresolved annotation disagreement, an invalid split/provenance/
  outcome value, a mismatched `expected_value`/`expected_provenance`
  pair, and a `compensation_text` that is not an exact substring of
  `description` at its recorded offsets) plus a minimal evaluator
  against the seven merged classifiers. Every metric reports numerator
  and denominator explicitly (`MetricCounter.render()` prints `N/A` on
  a zero denominator, never `0%`). Composite parsers
  (`experience`/`salary`/`location`) are scored per independently
  annotated component. `skills` is scored set-based; any returned skill
  outside the frozen `expected_canonical_ids` is an unconditional false
  positive. No pass threshold, no CI wiring, no dashboard anywhere. 36
  tests in `backend/tests/test_evaluate_phase3_corpus.py`: one test per
  fail-closed loader rule, direct scoring-logic tests against
  hand-built `MetricCounter`/`ParserComponentMetrics`/`SkillsMetrics`
  inputs, and one true end-to-end smoke test against the real
  classifiers (using a title `remote.py` actually recognizes — an
  earlier draft of this same test used an undelimited "Remote X" title,
  which is a documented false negative in `remote.py`'s own structural
  rule, not a bug; caught and corrected before this commit).
- **`docs/DECISIONS/0010-realistic-evaluation-corpus-methodology.md`**
  (new): records every binding acquisition/sanitization/annotation/
  partitioning/metric decision from this slice's negotiated proposal
  rounds as durable policy, not restated per-round in this ledger.
- Files changed: the four new files above plus their three new test
  files; `backend/scripts/verification_scope.py` and
  `backend/tests/test_verification_scope.py` (the narrowly necessary
  owner mapping for `backend/tests/fixtures/evaluation/
  phase3_realistic_corpus.json`, mirroring `_TAXONOMY_FIXTURE_FILES`/
  `_SKILL_FIXTURE_FILES` exactly — without it the file would fail
  closed with `OwnerMappingRequiredError` the moment it existed);
  `.gitignore` (`backend/.evaluation-staging/`); `docs/ROADMAP.md`
  (corrected the stale "skill-classifier ... not yet merged" passage —
  it merged last iteration — and added this slice's own neutral,
  not-yet-merged status); `docs/ARCHITECTURE.md` (corrected the stale
  "skills.py/skills.yaml ... planned/not yet merged" entries to match).
  No database lifecycle operation performed; no network contact of any
  kind attempted; no parser semantic change; no schema/persistence
  work; `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json`
  does **not** exist yet.
- **Adversarial self-review findings, fixed before this commit** (10
  findings; the 6 below were fixed, 4 were confirmed low-risk/hygiene
  and left as disclosed, not fixed — see the review's own report for
  the full list):
  - `greenhouse_html_convert.py`: an entity-encoded CR/LF (e.g. `&#13;`)
    bypassed line-ending normalization entirely, since `HTMLParser`
    decodes character references *during* parsing, after the one
    pre-parse normalization pass already ran. Fixed by normalizing the
    fully extracted text a second time, after parsing.
  - `greenhouse_html_convert.py`: an unclosed `<script>`/`<style>`
    silently discarded every character after it (Python's `HTMLParser`
    treats both as CDATA), including real description text, with no
    signal of truncation. Fixed by raising a new `HtmlConversionError`
    instead of returning unreliable text; `fetch_greenhouse_evaluation_
    postings.py`'s `_sanitize_job_detail` converts it to
    `EvaluationFetchError` (fail closed, never silently degrades).
  - `evaluate_phase3_corpus.py`: a recorded `disagreement.adjudication`
    was checked for presence only, never for consistency with the
    annotation's own scored value — three mutually contradictory values
    (top-level, second annotation, adjudication) could coexist and
    evaluation would silently score against the top-level one,
    ignoring the adjudication entirely. Fixed: the loader now requires
    `adjudication.final_value` and rejects the record if it does not
    equal the annotation's own scored field.
  - `evaluate_phase3_corpus.py`'s `_score_component`: `provenance_
    correctness` was updated for *any* present outcome, not just
    `present_supported` — pooling a false positive on an absent/
    unsupported-form/ambiguous case (already counted by its own
    dedicated metric) back into a metric meant to describe
    provenance-labeling quality on genuine hits. Fixed: gated on
    `present_supported` only.
  - `fetch_greenhouse_evaluation_postings.py::run_acquisition`: a board
    that responded successfully but yielded zero usable candidates
    (e.g. a non-empty list with no job carrying a usable id) was never
    logged — only the exception path printed anything. Fixed: an
    explicit log line for this case too.
  - `fetch_greenhouse_evaluation_postings.py`: `MAX_REQUESTS_PER_BOARD`
    was declared and documented but never actually checked at runtime —
    the real ceiling was only an emergent consequence of `_select_job_
    ids`'s own limit, so a future edit to that limit could silently
    break the documented guarantee. Fixed: an explicit, independently
    tested check in `_fetch_board`. Also fixed in the same pass:
    `_select_job_ids` now de-duplicates repeated ids before selecting
    (never wasting part of the 10-request budget re-fetching one job
    twice), and `evaluate_phase3_corpus.py`'s loader now rejects a
    non-scalar `expected_value` and an out-of-bounds/inverted
    `compensation_text_source_span` (negative indices, `start > end`)
    instead of silently accepting either.
  - 14 new regression tests added across the three test files for the
    six fixes above (103 tests total in the three new test files, up
    from 89).
- Verification: pending — see the workflow-metadata block below and the
  publication (`A`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
executed_gate: final
candidate_sha: a0ddad9489c9020b1c1921d4dac182e7a42ef3d0
receipt_id: 788ec89b-c81f-41c0-859b-ded428c2d466
receipt_path: docs/verification-receipts/a0ddad9489c9020b1c1921d4dac182e7a42ef3d0/788ec89b-c81f-41c0-859b-ded428c2d466.json
full_suite_count: 2961
focused_test_count: 175
mutation_witness_count: 34
```

---

## Iteration 2

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
state: pending
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
```
