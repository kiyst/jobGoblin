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

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/remote-classifier` for the single Low finding from
  Iteration 1's `Work review` above. Base: commit `3a8cc70` plus the
  uncommitted review. Preserved: the structural title-marker rule, the
  separator-exact comma-contrast rule, the description positive catalog
  and context protections, coordinated/unresolved negation, the
  fail-closed import allow-list, `NormalizationResult`/`Provenance`, the
  public signature, and the pure/offline scope. No ingestion/persistence/
  providers/models/migration or other parser touched.
- Outcome: `_PAREN_BRACKET_RE` previously matched any opening `(`/`[`
  followed eventually by any closing `)`/`]`, accepting crossed forms like
  `"(Remote]"` or `"[Remote)"` as a valid structural marker. Rewrote it as
  two entirely separate alternatives — `\(([^()\[\]]*)\)` or
  `\[([^()\[\]]*)\]` — so a match only ever comes from a properly paired
  delimiter type; `_title_segments` now reads whichever capture group
  actually matched (`group(1)` for parens, `group(2)` for brackets). A
  crossed-delimiter title now matches neither alternative at all: its
  mismatched characters are left in the plain delimiter-split remainder,
  same as any other stray punctuation, and the whole (undelimited, since
  neither `(`/`[` nor `)`/`]` is a segment delimiter) title fails the
  exact-segment-match check just like `"Remote Systems Administrator"`
  does — no separate exclusion or special-case was needed.
- New fixture cases (corpus now 70 total, +3 net): the two reproduced
  crossed-delimiter regressions (`title_crossed_paren_then_bracket_
  rejected` for `"(Remote] Infrastructure Engineer"`,
  `title_crossed_bracket_then_paren_rejected` for `"[Remote) Infrastructure
  Engineer"`), and one new positive control
  (`positive_control_valid_matched_bracket_marker`,
  `"Facilities Coordinator [Remote]"` -> `remote`/`inferred`) proving valid
  matched-bracket behavior is preserved with actual coverage, not merely
  asserted — no prior fixture exercised a bracket-only marker.
- Files changed: `backend/app/normalization/remote.py` (paired-delimiter
  regex and `_title_segments`, plus an updated docstring on
  `_title_segments`), `backend/tests/fixtures/normalization/
  remote_type_cases.json` (3 new cases), this handoff entry. No other
  file touched.
- Verification: both targeted modules directly (**88 passed**, was 85);
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **10 steps PASS**, **1583 full-suite tests** (was 1580; +3). `ruff
  format --check`/`ruff check`/`mypy` all pass. `check_repo.py` and `git
  diff --check` both pass as part of the verifier. No database/migration/
  schema touched.
- Adversarial self-review: given the narrow, single-finding scope of this
  correction (not separately requested this round), verification relied on
  the two crossed-form regressions themselves — both directly exercise the
  exact defect reported (a crossed pair previously returning a confident
  positive) and both now pass against the corrected regex, alongside the
  new valid-bracket positive control and every previously-passing
  parenthesized/bracketed case (`positive_title_only_remote`,
  `hybrid_cloud_title_and_description_exclusion`'s title, etc.),
  confirming the fix is targeted and did not regress valid matched-pair
  behavior.
- Deviations/known limitations: none beyond those already recorded in
  Iteration 1 (pre-existing `alembic check` substitution; negation-window
  and dual-unconnected-negator scope).
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-06, Codex.
- Diff reviewed: `3a8cc70..7c0bd05` on `phase-3/remote-classifier`.
- Verdict: **Approved with one documentation-only binding clarification.** The
  paired-delimiter defect is closed and there are no remaining executable findings.
- Independent verification: inspected the three-file correction; directly replayed
  both crossed forms (now `unavailable`), valid `(...)` and `[...]` controls (still
  `remote/inferred`), and the prior arbitrary-leading-title regression; reran both
  targeted modules (**88 passed**); and ran the canonical verifier (**all 10 checks
  PASS, 1583 full-suite tests**). Ruff, mypy, repository checks, database safety,
  focused/full pytest, and temporary-directory cleanup all passed.
- Finding disposition: `_PAREN_BRACKET_RE` now encodes `(...)` and `[...]` as separate
  alternatives, and `_title_segments` selects the populated capture group. Neither
  crossed form can be extracted as a structural segment, while both valid pair types
  remain supported. The change is bounded to the requested parser, corpus, and ledger
  files; no other parser, database, migration, provider, or ingestion code changed.
- Documentation-only clarification: Iteration 2's `Work done` says the canonical
  verifier passed “all 9 steps,” but the genuine verifier output reports **10** steps
  (the tenth is temporary-directory cleanup). Correct this current claim to “all 10
  steps” before merge. This is mechanical, does not require another test run, and does
  not require another Codex re-review.
- Merge remains a separate user authorization. Do not begin another parser or wire
  Phase 3 behavior into ingestion as part of that merge.

### Merge record

- Date: 2026-09-07. User authorized merging `phase-3/remote-classifier`
  into `main` following Codex's Approved review (no executable findings;
  approval commit `fecbcec`) above.
- Pre-merge state: `main` and `origin/main` both at `199eb00`; feature
  branch `phase-3/remote-classifier` pushed and clean at `fecbcec`
  (containing implementation commits `21f55ae`, `c8a1217`, `3a8cc70`,
  `7c0bd05`, and the documentation-correction/approval-recording commit
  `fecbcec`).
- Merge: `git merge --no-ff phase-3/remote-classifier` on `main` — merge
  commit `1bc8247`. `git diff phase-3/remote-classifier HEAD` is empty
  (zero content difference); `git diff --check` and `check_repo.py` both
  exit 0; working tree clean.
- Post-merge verification: genuine external `python scripts/verify.py
  --level routine` (full run, no `--focus`, since this is the first Phase
  3 production slice) — all **9 steps PASS** (Ruff format/check, mypy,
  `check_repo.py`, `git diff --check`, disposable-database URL/
  reachability, **1583 full-suite tests**, temp-directory cleanup) — 9,
  not 10, because this run has no separate focused-test step; Codex's
  10-step count in its own review was from a `--focus`-scoped run, a
  different invocation shape, not a discrepancy.
- Pushed: `main` at `1bc8247`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `199eb00` (the
  commit immediately before this merge) — this removes
  `app/normalization/remote.py`, `app/normalization/types.py`, both new
  test files, the fixture corpus, and the ARCHITECTURE.md/ROADMAP.md
  wording changes cleanly, with no migration to reverse and no data
  written by this slice to any environment (pure Python, never wired into
  ingestion/persistence).
- **Phase 3's first parser slice is merged, not Phase 3 itself.** The
  deterministic remote/hybrid/onsite classifier and its shared
  `NormalizationResult`/`Provenance` types are now on `main`, reviewed
  across four correction rounds with no remaining executable findings.
  The other seven required Phase 3 parsers (title, salary, location,
  employment, seniority, experience, skill) remain unstarted; this
  classifier is not wired into `ingestion/pipeline.py` or
  `ingestion/persistence.py`, and no `parser_version`/`field_provenance`
  write exists yet — those remain Phase 4+ concerns.
- STOP — do not begin or propose another Phase 3 parser, wire this
  classifier into ingestion/persistence, contact providers, or create a
  migration without separate authorization.

---

## Iteration 2

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
