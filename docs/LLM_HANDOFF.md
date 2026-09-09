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

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, unchanged from the original implementation). Base
  -> ending commit: `e13d8a6` -> this commit; same branch `phase-3/experience-classifier`.
  Bounded correction pass addressing Astra's review of commit `e13d8a6`
  (relayed to the implementer directly by the user as text; **not**
  committed to this branch as its own `### Work review` section — no such
  commit exists on `phase-3/experience-classifier` or its origin as of
  this entry). Scope held exactly to the parser, its tests/fixtures, and
  this documentation, per the review's own stated scope boundary.
- Seven findings addressed:
  1. **Reversed-label attribution bypass**: `_LABEL_VALUE_RE.search` →
     `.match` in `_extract_description_bounds`, anchoring the reversed
     label:value acceptance path to the sentence's own opening word.
     `"Our vendor experience: 5 years."` now rejects; `"Experience: 5+
     years"` (positive control) unaffected.
  2. **Title preference/negation scope**: added `_TITLE_LEADING_PREFERENCE_RE`
     (leading marker, comma optional) and cross-segment `_is_qualifier_only_segment`/
     `has_adjacent_qualifier` (a comma-separated qualifier-only segment
     modifies the preceding segment rather than standing alone).
     `"Preferred 3-5 years experience"`, `"Ideally 5 years of experience"`,
     and `"5 years experience, not required"` now all reject; `"The ideal
     candidate must have 5 years of experience."` and `"No Experience
     Required"` (positive controls) unaffected.
  3. **Trailing upper-bound markers + unsupported prefix**: added
     `bare_trail_hi`/`bare_trail_lo` grammar alternatives (marker *after*
     the complete "N years of experience" phrase, distinct from the
     existing before-the-unit-word suffix forms) and `_UNSUPPORTED_PREFIX_RE`
     (`"less than"`/`"fewer than"`) as a new poison pattern. `"...5 years
     of experience or fewer."` now yields `maximum=5`; `"less than 5
     years..."` now safely rejects instead of fabricating `minimum=5`.
  4. **Unicode numeric expressions**: NFKC-decomposed vulgar fractions use
     U+2044 FRACTION SLASH, not ASCII `/` — normalized to `/` before
     poisoning runs. Added `_UNICODE_DASH_NUMERIC_RE` (figure dash, en
     dash, em dash, Unicode minus U+2212) as a poison pattern, distinct
     from the ASCII hyphen the range grammar recognizes. `"1½ years
     experience"`, `"3–5 years experience"`, and `"−5 years experience"`
     all now reject instead of fabricating `2`, `5`, and `5` respectively.
  5. **Multi-candidate collection per title segment**: added
     `_iter_forward_phrases`, collecting every non-overlapping match in a
     segment rather than only the first. `"3 years experience and 5 years
     experience"` now conflicts (both collected) instead of returning only
     `minimum=3`.
  6. **Regression input corrections**: `amendment6_title_internal_conflict_beats_description_agreement`
     now supplies a real description (`"This role requires 5 years of
     experience."`, agreeing with one of the two conflicting title
     minima) instead of `null`. `shortform_not_isolated_negative` is now a
     title input (was a description, which cannot exercise the
     title-only short-form waiver).
  7. **Verification and scope**: see below.
- Files changed: `backend/app/normalization/experience.py`,
  `backend/tests/fixtures/normalization/experience_cases.json` (+15
  cases: 14 new regressions plus one added mid-pass — see mutation-proof
  note below — for 70 total), `backend/tests/test_normalization_experience.py`
  (unchanged in structure; case count grows via the fixture file), this
  handoff entry. No other file touched.
- Mutation-proof mapping (Workflow v3.1, required — an exact fix/test/
  outcome table, not a rounded count):

  | Fix | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|---|
  | 1 | `_LABEL_VALUE_RE.match` (anchored) | `round2_fix1_reversed_label_bypasses_attribution` | Reverted to `.search`: test failed (`minimum=5`, expected `unavailable`). Restored: passed. |
  | 2a | `_TITLE_LEADING_PREFERENCE_RE` | `round2_fix2_title_leading_preferred_range`, `round2_fix2_title_leading_ideally_no_comma` | Removed from `has_preference`: both failed (`minimum=3`/`5` instead of `unavailable`). Restored: both passed. |
  | 2b | `_is_qualifier_only_segment` / `has_adjacent_qualifier` | `round2_fix2_title_not_required_across_comma` | `has_adjacent_qualifier` forced `False`: failed (`minimum=5`). Restored: passed. |
  | 3a | `bare_trail_hi`/`bare_trail_lo` grammar | `round2_fix3_description_trailing_or_fewer_after_full_phrase`, `round2_fix3_title_trailing_or_fewer_after_full_phrase` | Marker text replaced with an unmatchable placeholder: both failed. Restored: both passed. |
  | 3b | `_UNSUPPORTED_PREFIX_RE` poison pattern | `round2_fix3_unsupported_less_than_title_isolation` | Removed from `_POISON_PATTERNS`: failed (`minimum=5`). Restored: passed. **Note**: the companion description-only fixture (`round2_fix3_unsupported_less_than_safely_rejects`) does *not* isolate this fix — it is independently protected by Iteration 1's match-start-zero attribution check, so it still passed even with this fix disabled; the title-only fixture above is what actually proves it. |
  | 4a | Fraction-slash (U+2044→`/`) normalization | `round2_fix4_unicode_vulgar_fraction` | Replacement removed: failed (`minimum=2`). Restored: passed. |
  | 4b | `_UNICODE_DASH_NUMERIC_RE` poison pattern | `round2_fix4_unicode_en_dash_range`, `round2_fix4_unicode_minus_sign` | Removed from `_POISON_PATTERNS`: both failed (`minimum=5`). Restored: both passed. |
  | 5 | `_iter_forward_phrases` (collect all) | `round2_fix5_same_segment_conflict`, `round2_fix5_same_segment_conflict_reversed_order`, `round2_fix5_independent_bounds_two_phrases_one_segment` | Reverted to first-match-only: all three failed. Restored: all three passed. **Note**: a fourth related fixture (`round2_fix5_description_agrees_with_one_conflicting_candidate`) still passed even with this fix disabled — with only one title candidate collected it reaches `unavailable` via ordinary cross-source conflict instead, so it does not itself isolate this mechanism; it remains a valid correctness case, just not this fix's proof. |

  Every mutation was independently reverted, its listed test(s) confirmed
  failing with the exact reported pre-fix defect, then the fix restored
  and the test(s) reconfirmed passing — 8 distinct fixes, each with at
  least one isolating regression, matching the review's own numbered
  findings exactly (no rounded or inflated count this time).
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (106
  source files). `python -m scripts.check_repo` exits 0. Genuine external
  `python scripts/verify.py --level routine --focus
  tests/test_normalization_experience.py` (full run) — **78 focused /
  1924 full-suite tests** (was 63/1909; +15 fixture cases). All 11 steps
  PASS, including `handoff metadata validation` against this entry's own
  metadata block below.
- Deviations/known limitations: unchanged from Iteration 1's explicit
  exclusions; no new limitations introduced by this correction pass.
- STOP — awaiting Astra's re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_experience.py
focused_test_count: 78
full_suite_count: 1924
fixture_path: backend/tests/fixtures/normalization/experience_cases.json
fixture_count: 70
```

---

## Iteration 2

### Work done

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, unchanged). Base -> ending commit: `2589eec` ->
  this commit; same branch `phase-3/experience-classifier`. Bounded
  correction pass addressing Astra's review of commit `2589eec` (relayed
  as text; no `### Work review` commit exists on this branch or its
  origin). Scope held to the parser, its tests/fixtures, and this
  documentation.
- Three findings addressed, plus one genuine defect this pass discovered
  on its own while mutation-proving finding 3:
  1. **Title modifier scope/ordering**: `_title_segments` now interleaves
     paired-parenthesis/bracket content with delimiter-split text in
     **original left-to-right order**, instead of hoisting all
     parenthesized content to the front of the segment list.
     `has_adjacent_qualifier` now checks **both** the preceding and
     following segment, not only the following one. `"Ideally, 5 years of
     experience"`, `"Preferred, 3-5 years experience"`, and `"5 years
     experience (not required)"` now all reject.
  2. **Composite unsupported numeric expressions**: replaced the
     hyphen-only `_DECIMAL_RANGE_RE` with generalized
     `_DECIMAL_COMPOSITE_RANGE_RE`/`_FRACTION_COMPOSITE_RANGE_RE`, which
     poison a decimal or fraction combined with *any* adjacent range
     separator (hyphen, `"to"`, `"and"`, either operand order) as one
     whole span, rather than only the decimal/fraction's own two
     operands. `"3.5 to 5 years experience"` and `"1/2-5 years
     experience"` no longer leak the untouched second endpoint as a
     surviving bare candidate; a separate, well-formed neighboring phrase
     is unaffected.
  3. **Description label:value exemption removed**: the reversed
     label:value form (`"Experience: 5+ years"`) no longer has any
     independent acceptance path on the description side at all —
     sentence-initial position was never an approved exception, per this
     review. It now only matches on the title side. The label:value
     grammar's unit word is also now mandatory (`"Experience: 5"` with no
     `"years"`/`"yrs"` at all previously matched; it no longer does).
     **Genuine defect found while mutation-proving this fix**: title-side
     label:value matching turned out to be effectively dead code all
     along — the colon in `"Experience: N"` is itself a segment
     delimiter, so segmentation always separated the word `experience`
     from its value before the label:value grammar ever saw them
     together; every prior passing fixture for this form "worked" only
     by coincidence, via the isolated-segment short-form waiver matching
     the post-colon fragment on its own. Fixed by checking the label:value
     grammar against the **whole title**, anchored at position 0 with a
     remainder check, *before* segmentation runs — mirroring the
     description side's existing whole-sentence discipline. This makes
     the mandatory-unit fix (and the grammar generally) actually
     reachable and testable for the first time.
- Files changed: `backend/app/normalization/experience.py`,
  `backend/tests/fixtures/normalization/experience_cases.json` (+10
  cases, 80 total), this handoff entry. No other file touched.
- Mutation-proof mapping:

  | Fix | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|---|
  | 1a | Order-preserving `_title_segments` | `round3_fix1_three_segment_order_preservation_isolation` | Reverted to hoist-parens-first: failed (`minimum=5`). Restored: passed. **Note**: the simpler two-segment fixture (`round3_fix1_trailing_parenthesized_not_required`) still passes even with this fix disabled — with only two segments, "preceding" and "following" are symmetric, so the bidirectional check alone compensates; the three-segment fixture is what actually isolates order-preservation. |
  | 1b | Bidirectional `has_adjacent_qualifier` | `round3_fix1_leading_ideally_with_comma`, `round3_fix1_leading_preferred_with_comma_range` | Reverted to following-only: both failed. Restored: both passed. |
  | 2 | `_DECIMAL_COMPOSITE_RANGE_RE`/`_FRACTION_COMPOSITE_RANGE_RE` | `round3_fix2_decimal_to_range`, `round3_fix2_fraction_hyphen_range`, `round3_fix2_composite_does_not_swallow_neighboring_valid_phrase` | Removed from `_POISON_PATTERNS`: all three failed (first two fabricated `minimum=5`; the third failed differently — the fabricated `5` conflicted with the real, independent `10`, masking it behind a spurious cross-candidate conflict instead of surfacing `minimum=10`). Restored: all three passed. |
  | 3a | Description label:value path removed | `round3_fix3_description_label_value_no_longer_exempt` | Reinstated the old exemption: failed (`minimum=5`). Restored: passed. |
  | 3b | Mandatory unit + whole-title anchoring | `round3_fix3_label_value_unit_now_mandatory_title` | Made unit optional again: failed (`minimum=5`) once tested against the corrected whole-title path — the same mutation against the original (dead) per-segment path had silently passed, which is what surfaced the whole-title fix's necessity in the first place. Restored: passed. |

  The description-side `round3_fix3_label_value_unit_now_mandatory` fixture
  does not itself isolate 3b (already independently rejected by 3a's
  removal of the description path entirely) — noted directly in its
  fixture `note`.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (106
  source files). `python -m scripts.check_repo` exits 0. Genuine external
  `python scripts/verify.py --level routine --focus
  tests/test_normalization_experience.py` (full run) — **88 focused /
  1934 full-suite tests** (was 78/1924; +10 fixture cases). All 11 steps
  PASS, including `handoff metadata validation` against this entry's own
  metadata block below. A broader ad hoc regression sweep (not committed
  as fixtures) covering every prior round's examples plus new
  combinations (a leading *and* trailing qualifier together, a
  label:value form followed by a comma-separated `"not required"`, a
  valid range sharing a segment with a poisoned composite, a composite
  inside an attribution frame, and a *leading* parenthesized qualifier)
  all resolved correctly with no confidently-wrong output.
- Deviations/known limitations: unchanged from prior iterations' explicit
  exclusions. The label:value grammar still supports only bare/plus/
  hyphen-range forms, not open-upper/open-lower prefixes (e.g.
  `"Experience: up to 10 years"` remains unsupported) — this was never
  claimed or tested before either, so it is not a regression, just an
  explicitly noted scope boundary discovered during this pass's
  debugging.
- STOP — awaiting Astra's re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_experience.py
focused_test_count: 88
full_suite_count: 1934
fixture_path: backend/tests/fixtures/normalization/experience_cases.json
fixture_count: 80
```
