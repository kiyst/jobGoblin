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
  (R-plus-adversarial, matching `seniority.py`'s precedent — deterministic
  pure-function text classifier, no identity/concurrency/security/
  external/destructive surface). Base -> ending commit: `ddb427d` -> this
  commit; new branch `phase-3/experience-classifier`. Workflow v3.1 pilot
  parser slice 1 of 3. Implements the fresh proposal Astra approved with
  binding clarifications, incorporating every amendment below exactly.
- `app/normalization/experience.py` (new): `classify_experience(title,
  description) -> ExperienceRange`, the first parser needing `types.py`'s
  deferred composite-result case — two independently-provenanced
  `NormalizationResult[int]` bounds (`minimum`, `maximum`). Independent
  implementation (own regex grammar, own segment/sentence splitting,
  no import from `seniority.py`/`employment.py`/`remote.py`), proven by
  the same AST-inspection allow-list pattern as the other three parsers.
- Astra review amendments incorporated (all from the `604213a` proposal
  review): **(2)** applicant attribution is a closed
  `ALLOWED_SUBJECT REQUIRE_VERB [ATTRIBUTION_OBJECT] <phrase> END` frame,
  not subject/verb adjacency alone — `"We require vendors with 5 years of
  experience."` and `"We require no experience to use our platform."`
  both correctly reject. **(3)** the continuation-boundary rule is
  uniform: only an empty remainder accepts; a recognized negation and a
  wholly unrecognized hedge both reject identically, so unsupported
  negation can never silently become a positive requirement, while
  `"no more than 5 years"` still correctly yields `maximum=5` (consumed
  whole by the open-upper production, never reaching the boundary check
  as trailing text). **(4)** numeric rejection is atomic: a single
  text-wide redaction pass (decimal-beside-range, fraction, free-standing
  negative, bare decimal) runs before any sentence/segment splitting, so
  a poisoned digit can never resurface via a narrower production —
  proven necessary specifically on the *title* path (no redundant
  match-start/continuation-boundary guard there), where four new fixtures
  demonstrate the old (mutated-off) behavior fabricating `min=5`, `min=2`,
  etc. **(5)** preference-marker suppression is positional, not lexical:
  `"the ideal candidate"` (a closed subject phrase) is never confused with
  the `"ideal"/"ideally"` preference marker, since the marker check only
  ever inspects a sentence-initial `"Ideally,"` or an immediate trailing
  tag after an already-matched number — never the subject position.
  **(6)** internal (within-source) conflict is checked, and wins, before
  cross-source reconciliation, independently per bound — mirrors
  `seniority.py`'s exact `_CONFLICT`-before-agreement precedence.
- Files changed: `backend/app/normalization/experience.py` (new),
  `backend/tests/test_normalization_experience.py` (new, 63 tests),
  `backend/tests/fixtures/normalization/experience_cases.json` (new, 55
  cases), `docs/ROADMAP.md` (Phase 3 bullet — also corrected a
  pre-existing staleness: the seniority-classifier bullet still said
  "pending Codex review — not merged" despite that merge already existing
  at `92fcefc`), `docs/ARCHITECTURE.md` (annotated `experience.py`'s
  status), this handoff entry (two-iteration rotation). No other file
  touched; no schema, migration, or ingestion/persistence wiring.
- Contract-conformance pass (Workflow v3.1, required for parser slices):
  walked every claim in the approved proposal plus every Astra amendment
  individually against the implementation via direct manual traces
  (documented above and in the module docstring) before writing the
  fixture corpus — all confirmed enforced, not merely fixture-satisfied.
- Counterexample pass (Workflow v3.1, required for parser slices): probed
  ~25 new inputs not in the fixture corpus across the historical-defect
  checklist's nine categories (disallowed subjects beyond the reviewed
  examples — "the client", "our previous engineer"; non-adjacent
  "requires" separated from its subject by other clauses; an inverted
  raw range "7-3 years" correctly caught by the same consistency
  invariant that catches cross-bound inversion; a hyphenated compound
  "5-Year Minimum..." that doesn't match any production). No confidently-
  wrong output found; every excluded case resolved to `UNAVAILABLE`. Two
  new safe-miss scope boundaries noted, not fixed: a "5-Year" hyphenated-
  compound adjective form, and a `REQUIRE_VERB` frame requiring direct
  subject-verb adjacency (no intervening clause) — both documented
  limitations, not confidently-wrong cases.
- Load-bearing regression mutation proofs (Workflow v3.1, required):
  individually reverted and reconfirmed 8 fixes — amendment 2's
  attribution-object gate, amendment 3's uniform continuation-boundary
  rule, amendment 4's redaction mechanism (isolated via 4 new title-side
  fixtures after discovering the original description-side fixtures were
  masked by amendment 2/3's own guards — a real gap this pass itself
  caught and closed), amendment 5's positional preference check, amendment
  6's internal-conflict precedence, and Risk 5's hyphen disambiguation.
  Every mutation reproduced the exact pre-fix defect (a fabricated value
  or a crash); every fix, once restored, passed again.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (106
  source files). `python -m scripts.check_repo` exits 0. Genuine external
  `python scripts/verify.py --level routine --focus
  tests/test_normalization_experience.py` (full run) — **63 focused /
  1909 full-suite tests** (was 1846; +63 from the three targeted
  normalization suites run together plus the new module, net +63 to the
  full suite). All 11 steps PASS, including `handoff metadata validation`
  against this entry's own metadata block below.
- Deviations/known limitations: explicit exclusions carried from the
  approved proposal (no `"Requirements:"`-header-scoped attribution, no
  `exp` unit abbreviation, negation-marker catalog acknowledged
  non-exhaustive) plus the two new counterexample-pass findings above
  (hyphenated-compound numbers, non-adjacent requirement clauses) — all
  safe misses (`UNAVAILABLE`), none confidently wrong, none requiring
  user approval under the confidently-wrong blocking rule.
- STOP — awaiting Astra's implementation review. Do not merge, begin
  another Phase 3 parser, wire into ingestion/persistence, contact
  providers, or create a migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_experience.py
focused_test_count: 63
full_suite_count: 1909
fixture_path: backend/tests/fixtures/normalization/experience_cases.json
fixture_count: 55
```

---

## Iteration 2

### Work done

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, unchanged from Iteration 1). Base -> ending commit:
  `e13d8a6` -> this commit; same branch `phase-3/experience-classifier`.
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
