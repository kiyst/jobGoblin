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

- Date/agent: 2026-09-07, Claude Code (Sonnet 5). Risk class R. New,
  read-only-audit-then-approved bounded slice on new branch
  `phase-3/employment-classifier`, base: clean `main@243a78a` (the
  remote-classifier merge commit). Second Phase 3 parser:
  `classify_employment_type(title, description) ->
  NormalizationResult[EmploymentType]` where `EmploymentType = full_time |
  part_time | seasonal | internship`.
- Scope boundary (per approved proposal, revised after a binding
  correction caught the original proposal conflating axes): this slice
  covers only `jobs.employment_type` (schedule/commitment). It never
  reads, writes, or reasons about `jobs.contract_type` (engagement/
  payroll axis — `contract`, `temporary`, `contract_to_hire`, `1099`,
  `W2`; deferred to its own future slice) or `jobs.shift` (no parser
  currently planned for it at all). Cross-axis vocabulary is cross-axis
  masked as inert (small, closed, explicitly enumerated list —
  `contract`, `temporary`/`temp`, `contract to hire`/`temp to perm`,
  `1099`, `w2`, `per diem`) so it can never falsely conflict with an
  `employment_type` value (e.g. `"Full-Time Contract"` ->
  `full_time`/`inferred`, "Contract" contributing nothing). `per_diem` is
  unsupported in v1 by design — no evidence, not silently assigned to
  either axis. Two distinct `employment_type` values detected in one
  field (e.g. `"Seasonal, Full-Time"`) are `unavailable`, even though both
  may be true in reality — documented as a limitation of the existing
  scalar column, not of the parser.
- Independent implementation, not a `remote.py` import: no cross-module
  private-helper import (proven by `test_import_boundary_allow_list` plus
  a new regression, `test_import_boundary_rejects_cross_parser_private_
  helper_import`, asserting `app.normalization.remote` specifically is
  rejected by this module's own allow-list). Smaller than `remote.py` by
  design — no comma-contrast rescue, so no character-span tracking at
  all, only token-index tracking.
- Files changed: `backend/app/normalization/employment.py` (new),
  `backend/tests/test_normalization_employment.py` (new),
  `backend/tests/fixtures/normalization/employment_type_cases.json` (new,
  40 cases), `docs/ROADMAP.md` (Phase 3 bullet updated — also corrected a
  pre-existing staleness: it still said the remote-classifier slice was
  "pending review, not merged" despite the merge already recorded above
  at `1bc8247`), this handoff entry. `app/normalization/types.py`,
  `app/normalization/remote.py`, and both of its test/fixture files
  untouched.
- Verification: targeted `test_normalization_employment.py` plus the two
  existing modules explicitly rerun together (`test_normalization_remote.
  py`, `test_normalization_types.py`) — **133 passed** (45 new in the
  employment module; the existing 88 remote/types tests unchanged). `ruff
  format --check`, `ruff check`, `mypy` all pass. Genuine external `python
  scripts/verify.py --level routine` (full run) — all **9 steps PASS**,
  **1628 full-suite tests** (was 1583; +45). `check_repo.py` and `git diff
  --check` both pass as part of the verifier. No database/migration/
  schema touched.
- Full fresh-context adversarial review (not abbreviated, per explicit
  instruction): probed ~15 unseen phrasings beyond the fixture corpus
  (undelimited same-axis compounds, cross-axis compounds, case-folding,
  occupational-prefix internship titles, `"neither...nor"`, comma-
  separated negation-contrast). Found and fixed three real issues before
  they reached the corpus:
  1. **`"neither"` was missing from the negation cue list**, letting a
     genuinely-negated qualified candidate survive
     (`"neither a full-time position nor anything else"` incorrectly
     returned `full_time`). Added `"neither"`; regression added
     (`negation_neither_nor_full_time`).
  2. **`temp`/`temp-to-perm` were not cross-axis masked**, an internal-
     consistency gap versus the already-approved `temporary`/
     `contract_to_hire`. Added both as aliases of the approved terms;
     regressions added (`cross_axis_description_temp_abbreviation`,
     `cross_axis_title_temp_to_perm`).
  3. **Masking-order bug, caught by the new fixture in (2) itself**:
     `_mask_other_axis_tokens` iterated a `frozenset` with no defined
     order, so the 1-token `"temp"` phrase could claim a token before the
     3-token `"temp to perm"` phrase got a chance, blocking it via the
     overlap-skip guard. Fixed by sorting mask phrases longest-first
     before matching (`_OTHER_AXIS_MASK_PHRASES_BY_LENGTH`).
- **One known, discovered limitation left undecided rather than
  guess-fixed** (documented in the module docstring and pinned by
  `known_limitation_backward_bare_beats_forward_qualified_across_comma`):
  the nearest-candidate negation window has no clause-boundary awareness,
  so `"This is a paid internship, not a full-time position."` currently
  returns `full_time`/`parsed_description` rather than `unavailable` — a
  closer *backward* bare candidate (`"internship"`, distance 1, before
  `"not"`) wins the "nearest" slot over the actually-negated *forward*
  qualified candidate (`"full-time position"`, distance 2, after `"not"`,
  in a separate clause). A "qualified candidates always win" tie-break
  was tried and rejected: it fixes this sentence but breaks the
  symmetric, already-correct `"Not internship, full-time position
  available."` (bare `"internship"` is directly, canonically negated;
  the qualified candidate is a later, separate clause that must not be
  suppressed). The two patterns are only distinguishable by whether a
  comma separates the negator from a backward candidate, which needs
  character-span tracking this slice deliberately omits (no comma-
  contrast, per binding correction). Flagged for explicit user/Codex
  decision rather than silently left undiscovered or patched with an
  unproven heuristic.
- Deviations/known limitations: the one above, plus the pre-existing
  `alembic check` substitution (unchanged, unrelated to this slice).
  Comma contrast remains omitted, per instruction, since no fixture
  demonstrated it was necessary for a *different* reason than the one
  documented above.
- STOP — awaiting Codex review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-07, Codex.
- Diff reviewed: `243a78a..cee74e5` on `phase-3/employment-classifier`.
- Verdict: **Changes requested.** The axis split, fail-closed result type, bounded
  module boundary, and most positive/negative cases are sound. One disclosed
  negation defect generalizes into confident contradicted facts, and one phrase-matching
  mechanism directly violates the approved separator requirement.
- Independent verification: inspected all five changed files; reran the three
  normalization modules (**133 passed**); ran the canonical verifier with employment
  focus (**all 10 checks PASS, 45 focused / 1628 full-suite tests**); and directly
  exercised contrast, punctuation, label/value, and common internship forms.
- Findings:
  1. **High — backward-nearest negation can return the exact value explicitly negated.**
     This is not limited to the pinned `paid internship` example. Direct execution also
     returns `full_time` for `This is a part-time role, not a full-time position.`,
     returns `part_time` for the symmetric full-time/part-time sentence, and returns
     `full_time` for `This is seasonal work, not a full-time position.` The current
     regression therefore codifies a known false fact, contrary to Phase 3's fail-closed
     rule. Bind negation using direction/clause-aware evidence: prefer an eligible
     forward candidate in the negator's clause; fall back to a backward candidate only
     when no forward candidate applies. Preserve `Not internship, full-time position
     available.` as `full_time`, and preserve trailing backward negation such as
     `Full-time positions are not available.` as unavailable. Replace the known-
     limitation expectation and add the full asymmetric matrix above.
  2. **Medium — phrase matching discards separator identity and accepts malformed
     pseudo-phrases.** `_compile_phrase("full-time")` becomes the token tuple
     `("full", "time")`, while `_TOKEN_RE` discards slash, comma, and dash characters.
     Consequently `Full/Time` is classified as `full_time`, and descriptions such as
     `This is a full/time position.`, `full, time position`, and `part/time role` produce
     confident values. This directly violates the binding instruction not to turn
     arbitrary punctuation into phrase adjacency. Preserve character gaps or
     canonicalize only explicitly permitted spellings before matching. Apply the same
     exactness to multi-token cross-axis masks, while preserving the deliberately
     supported `full-time`, `full time`, and approved masked compound cases. Add title
     and description regressions for slash/comma/dash separators.
  3. **Medium — the implemented corpus does not deliver the approved per-value structural
     matrix.** The proposal committed to whole-title, parenthesized/bracketed,
     delimiter-segment, and explicit-phrase title positives for each of four values.
     The corpus instead has one structural title positive per value and no distinct
     explicit-phrase-anywhere mechanism. Either implement the promised safe, explicit
     catalog and cross-product, or revise the contract to state that no anywhere-title
     phrases exist and add the missing per-value structural controls. Do not count a
     larger aggregate fixture total as proof of the omitted matrix.
  4. **Low — ROADMAP still says all Phases 4–14 are unstarted despite merged Phase 4
     proof slices.** Git contains the merged Greenhouse canary (`64a3534`) and disposable-
     database live proof (`907b3f0`). Correct the status narrowly: the production
     `AtsScrapersProvider` adapter remains unstarted, but the preliminary read-only
     canary/live-ingestion proof work is merged. Do not declare Phase 4 complete.
- Accepted scope: `EmploymentType` remains exactly `full_time | part_time | seasonal |
  internship`; contract/temporary/tax terms and `per_diem` remain inert; same-axis
  compounds remain unavailable; no database writes, shared-helper extraction,
  ingestion wiring, migration, provider contact, or other parser belongs in this pass.
- Exact requested correction: address only the four findings above in the classifier,
  corpus/tests, ROADMAP, and next handoff entry. Run the targeted normalization tests
  and canonical verifier, perform fresh-context adversarial review of the corrected
  negation and separator mechanisms, commit/push the feature branch, and stop for
  re-review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-07, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/employment-classifier` for all four findings in
  Iteration 1's `Work review` above. Base: commit `cee74e5` plus the
  uncommitted review. Preserved: the axis split/scope, `EmploymentType`
  vocabulary, cross-axis inert masking concept, same-axis-conflict rule,
  fail-closed import allow-list, `NormalizationResult`/`Provenance`, public
  signature, and pure/offline scope. No ingestion/persistence/providers/
  models/migration or other parser touched.
- Outcome, addressing each finding exactly:
  1. **Negation direction/clause-aware binding.** The nearest-candidate
     search now tries the *forward* tier (candidates after the negator)
     first; only falls back to the *backward* tier when no forward
     candidate is in-window. Fixes the reported false facts (`"part-time
     role... not a full-time position"` -> `part_time`, its symmetric
     swap -> `full_time`, `"seasonal work... not a full-time position"`
     -> `seasonal`) while preserving both required-unchanged patterns
     (`"Not internship, full-time position available."` -> `full_time`;
     trailing backward-only negation with no forward candidate ->
     `unavailable`). Replaced the prior "known limitation" fixture with
     the fixed expectation and added the full asymmetric matrix (6 new
     `negation_direction_*` cases).
  2. **Separator identity.** `_TOKEN_RE` now treats comma/slash/ampersand/
     en-dash/em-dash as their own standalone hard tokens instead of
     silently vanishing like whitespace. A further adversarial finding
     during this same pass: a plain ASCII hyphen with whitespace on
     either side (`"full - time"`) was still slipping through as
     transparent, unlike the two genuinely-approved spellings — fixed by
     normalizing only *glued* hyphens (`(?<=\S)-(?=\S)`) to a space before
     tokenization, so a spaced hyphen now tokenizes as its own hard token
     too. Applies uniformly to multi-token cross-axis mask phrases (no
     separate code path). 9 new `separator_exactness_*` regressions
     (title and description; slash, comma, ampersand, en-dash, glued
     em-dash, spaced hyphen; one multi-token mask-phrase case; one
     positive control for the space-separated spelling).
  3. **Structural title matrix.** Added the 11 missing
     `structural_matrix_*` cells to complete the 4-structural-form
     (whole-title, parenthesized, bracketed, delimiter-segment) x
     4-value cross-product (16 total, 5 pre-existing + 11 new). Also
     added an explicit docstring statement that no "explicit phrase
     anywhere" mechanism exists for `title` in this slice, and why —
     rather than leaving its absence implicit.
  4. **ROADMAP correction.** Replaced the blanket "Phases 4-14: not
     started" bullet with a narrow correction: the Greenhouse canary
     (`64a3534`) and disposable-database live proof (`907b3f0`) are
     merged prework, the production `AtsScrapersProvider` adapter and
     Phase 4 completion remain outstanding. Confirmed both commits are
     ancestors of `main` before writing this.
- Files changed: `backend/app/normalization/employment.py` (tokenizer,
  negation direction, docstring), `backend/tests/fixtures/normalization/
  employment_type_cases.json` (1 replaced in place + 26 new, 66 total,
  was 40), `docs/ROADMAP.md` (Phase 4 bullet), this handoff entry.
  `backend/tests/test_normalization_employment.py`, `app/normalization/
  types.py`, `app/normalization/remote.py` untouched.
- Verification: targeted employment module alone (**71 passed** — 66
  fixture cases + 5 code-level tests —, was 45); all three normalization
  modules together (**159 passed**). `ruff format --check`/`ruff
  check`/`mypy` all pass. Genuine external `python scripts/verify.py
  --level routine` (full run) — all **9 steps PASS**, **1654 full-suite
  tests** (was 1628; +26, exactly matching the 26 net-new fixture cases).
  No database/migration/schema touched.
- Fresh-context adversarial review of the corrected negation and separator
  mechanisms (required this round, not abbreviated): probed ~13 unseen
  sentences beyond the fixture corpus (multi-clause negation with mixed
  forward/backward assertions, `"neither...nor"` combined with direction,
  underscore/tab/double-space/mixed-case separators, a slash-separated
  disjunction title). All resolved correctly or to an already-documented,
  orthogonal scope limitation. One new, out-of-scope observation
  surfaced and reported rather than fixed: `"This is neither seasonal nor
  a full-time position."` still lets `full_time` survive, because
  or/nor coordination propagation requires *exactly* one token between
  spans, and the article "a" breaks that gap here — an existing
  characteristic of the coordination mechanism itself (unchanged by this
  pass), not something finding 1 asked this pass to fix.
- Deviations/known limitations: the coordination-adjacency gap above
  (new observation, out of scope, not fixed); the pre-existing `alembic
  check` substitution (unrelated). No other known limitation remains
  from Iteration 1's review — the previously-documented negation
  direction limitation is fixed, not merely narrowed.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.
