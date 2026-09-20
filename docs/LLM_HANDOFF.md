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

- Date/agent: 2026-09-19, Claude Code (Sonnet 5). Risk class **H** (same
  slice, same primary-risk reasoning as Iteration 1). Base `B` (unchanged
  for this slice's whole correction lifetime) -> candidate `C3`:
  `d0159a4cc0faf9fb13f30ea814fa2e6c204570bb` -> this commit; same branch
  `phase-3/skill-classifier`, on top of the existing pushed tip
  `449e00c`. `slice_id: 2026-09-19-skill-classifier-d0159a4` (unchanged).
  Addresses Sol's re-review of `C2 = e867450` and `A2 = 449e00c`, both of
  which remain unamended, still pushed, still present in history exactly
  as they were; the `C2`/`A2` receipt cycle is superseded and
  non-reusable as of this entry.
- **Remaining bug, Sol's re-review finding**: the prior correction
  widened `_is_region_ending_boundary` to accept any `str.isspace()`
  character, but three Unicode **format** characters (category `Cf` --
  zero-width space `U+200B`, the BOM/zero-width no-break space
  `U+FEFF`, the Mongolian vowel separator `U+180E`) are *not* whitespace
  by `str.isspace()`, so a punctuation run followed by one of them still
  fell through to the same "skip past it and keep scanning" defect the
  prior fix closed for whitespace. Confirmed exactly as reported:
  `"Skills: Python.​When ready, Go"` returned `golang`;
  `"Skills: Python.﻿See details, Node"` returned `node.js`;
  `"Skills: Python.᠎When ready, Go"` returned `golang`. **Fix**:
  `_is_region_ending_boundary` now also accepts
  `unicodedata.category(char) == "Cf"`, in addition to `str.isspace()`
  and end-of-string. `_is_covered_terminator_boundary` (anchor-start
  eligibility) is untouched -- a format character still never creates a
  new anchor, only ends an existing region, preserving the same
  strict/liberal asymmetry as the whitespace case. `unicodedata` is now
  imported by `app/normalization/skills.py`; its own exact
  import-allow-list test is updated accordingly.
- **Regressions and mutation-proving**: added `backend/tests/fixtures/
  normalization/skill_cases.json` cases
  `description_zwsp_after_terminator_ends_region`,
  `description_bom_after_terminator_ends_region`, and
  `description_mongolian_vowel_separator_after_terminator_ends_region`
  (the three exact reported inputs), plus positive controls
  `description_format_char_does_not_create_anchor` (a format character
  after a period never makes a new anchor-start position),
  `description_letter_after_period_is_non_terminating`, and
  `description_digit_after_period_is_non_terminating` (an ordinary
  letter or digit after a period never ends a region either). Fixture
  corpus is now 72 cases (66 + 6). Added direct unit-level tests
  extending `test_is_covered_terminator_boundary_is_strict` and
  `test_is_region_ending_boundary_is_liberal` with the three `Cf`
  characters plus a bare digit, and two new isolated tests proving the
  `Node.js` internal period and a letter/digit-following period are
  non-terminating at the predicate level directly, independent of the
  fixture corpus -- 120 tests total (104 + 16). **Mutation-proved**:
  temporarily reverted `_is_region_ending_boundary` to the pre-`Cf` form
  (`str.isspace()` only, no `unicodedata` check) in the real source and
  reran the full focused suite -- exactly 6 tests failed (the 3 exact
  fixture regressions and the 3 corresponding `Cf` unit-test
  parametrizations), 114 still passed; restored the fix and reran to
  confirm 120/120 pass again. The regression set is genuinely
  load-bearing, not vacuous.
- **Adversarial self-review finding, fixed before this commit**: while
  applying this correction, found that the module docstring's "terminator"
  paragraph (edited by the prior correction) still described only the
  strict/liberal whitespace asymmetry and did not mention format
  characters at all, understating the grammar this fix now implements.
  Corrected in the same commit to name the `Cf` category explicitly for
  region-ending, restate that format-character eligibility is anchor-end
  only, and add the letter/digit non-terminating examples. While editing
  that paragraph, also found and fixed one stray raw no-break-space byte
  left embedded directly in a docstring example by an earlier round's
  edit tooling (an editing-tool artifact, not a grammar defect) --
  replaced with a proper ` ` escape in source; no behavior changed,
  confirmed by the full suite before and after. Left unchanged: an
  identical-looking stray raw character in this same file's *own*
  historical prose (Iteration 1's "Confirmed exactly as reported" quote)
  -- that is a factual quoting inaccuracy in a past iteration's narrative,
  not a live code or grammar defect, and out of this correction's bounded
  scope; noted here rather than silently touched.
- Files changed: `backend/app/normalization/skills.py` (edited -- the
  `Cf`-category fix, the `unicodedata` import, and the docstring
  correction); `backend/tests/fixtures/normalization/skill_cases.json`
  (edited, +6 cases); `backend/tests/test_normalization_skills.py`
  (edited, +16 tests, +1 import-allow-list entry); `docs/LLM_HANDOFF.md`
  (this entry, plus the iteration rotation below). No taxonomy file,
  migration, model, service, API, or live-provider file touched; no
  realistic-corpus work; no title-parser work; no workflow-policy file
  touched; no database lifecycle operation performed.
- **Two-iteration rotation applied**: the oldest iteration (the original
  skill-classifier implementation's `C`/`A` record) is deleted; the
  former Iteration 2 (the Unicode-whitespace region-boundary correction,
  `C2`/`A2`) is renumbered to Iteration 1, unchanged in content; this
  correction becomes Iteration 2.
- Verification: pending — see the workflow-metadata block below and the
  publication (`A3`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-19-skill-classifier-d0159a4
slice_kind: parser
risk_class: H
base_sha: d0159a4cc0faf9fb13f30ea814fa2e6c204570bb
declared_gate: final
executed_gate: final
candidate_sha: 0dbdbc54443237d35b0f139910eb84d11c06b29d
receipt_id: b8a569cb-ce08-462e-8172-372f42e00b07
receipt_path: docs/verification-receipts/0dbdbc54443237d35b0f139910eb84d11c06b29d/b8a569cb-ce08-462e-8172-372f42e00b07.json
fixture_path: backend/tests/fixtures/normalization/skill_cases.json
fixture_count: 72
full_suite_count: 2855
focused_test_count: 189
mutation_witness_count: 34
```

### Work review

- Sol's review of `C3` = `0dbdbc54443237d35b0f139910eb84d11c06b29d` and
  `A3` = `bc073ea54aaca6df254579d58a82de44a55dbd6d`: **Approved, no
  executable findings.** Independently confirmed: `A3`'s single-parent
  relationship to `C3` (no intervening commit, unlike the earlier
  `17f6f24`/`85ce56a` finding this same slice had); the `C..A` transition
  changed only the `workflow-metadata` block; replayed the three exact
  Unicode-format-character regressions
  (`description_zwsp_after_terminator_ends_region`,
  `description_bom_after_terminator_ends_region`,
  `description_mongolian_vowel_separator_after_terminator_ends_region`)
  and the `Node.js` internal-period positive control, all matching their
  declared expectations; ran all 189 focused tests, `ruff format --check`,
  `ruff check`, `mypy`, `check_handoff.py`, `check_repo.py`, and
  `git diff --check`, all passing; independently validated receipt
  `b8a569cb-ce08-462e-8172-372f42e00b07` and recomputed
  `approval_eligible: true`. Sol did not independently repeat the
  2,855-test full suite.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-19-skill-classifier-d0159a4
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-19T00:00:00Z
candidate_sha: 0dbdbc54443237d35b0f139910eb84d11c06b29d
publication_commit_sha: bc073ea54aaca6df254579d58a82de44a55dbd6d
receipt_path: docs/verification-receipts/0dbdbc54443237d35b0f139910eb84d11c06b29d/b8a569cb-ce08-462e-8172-372f42e00b07.json
receipt_id: b8a569cb-ce08-462e-8172-372f42e00b07
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-19. Merged `phase-3/skill-classifier` at approved,
  reviewed commit `f94638c2a8a82fa290996e4c9a4f8d2d79a15b93` (`R`; Sol's
  "Approved, no executable findings" verdict on `C3`/`A3`, above) into
  `main` via `git merge --no-ff`. Merge commit:
  `dad967789227feb65cf776a0675a8fe179873afa`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `d0159a4cc0faf9fb13f30ea814fa2e6c204570bb`.
- Pre-merge checks: confirmed the feature branch and its origin both sat
  at `f94638c`, and `main`/`origin/main` were both clean and synchronized
  at `d0159a4` before merging; re-confirmed
  `check_merge_eligibility(C3, A3, R)` still returned `approved`
  immediately beforehand.
- Followed the documented `M -> Q` release sequence: `M` was created
  locally, not pushed; zero content difference between `M` and `R`
  confirmed (`git diff --quiet f94638c HEAD`);
  `verification_coordinator.run_post_merge_verification` was run against
  `M` in a disposable detached worktree (always full/final) --
  artifact `3db09310-ca32-4c28-b950-a86b353d18bd`, all 11 steps PASS,
  full pytest suite **2855 passed**, all 34 mutation witnesses pass,
  no migration triggered, cleanup PASS. `Q` was authored as `M`'s direct
  mainline child, bundling that artifact with this append-only merge
  record in one commit -- this entry itself.
- Post-merge evidence status: `docs/post-merge/
  dad967789227feb65cf776a0675a8fe179873afa/
  3db09310-ca32-4c28-b950-a86b353d18bd.json`, referencing original
  receipt `b8a569cb-ce08-462e-8172-372f42e00b07` (`docs/
  verification-receipts/0dbdbc54443237d35b0f139910eb84d11c06b29d/
  b8a569cb-ce08-462e-8172-372f42e00b07.json`). `check_review.
  validate_published(C3, A3, R, M, Q)` and `verification_coordinator.
  confirm_main_unchanged` are run immediately before push; see the
  agent's final report for their results rather than restating them here
  ahead of time.
- STOP -- report the synchronized final `main` SHA and stop. No
  realistic-corpus work, title-parser work, another parser slice, or
  workflow-policy change without separate explicit user authorization.

---

## Iteration 2

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
state: pending
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
```
