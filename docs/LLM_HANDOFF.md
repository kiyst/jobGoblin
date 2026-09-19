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
  primary-risk reasoning as the taxonomy-foundation slice: ambiguous-alias
  false matches are Phase 3's own named risk, and this is the first
  classifier consuming that taxonomy). Base `B` -> candidate `C`:
  `d0159a4cc0faf9fb13f30ea814fa2e6c204570bb` -> this commit; new branch
  `phase-3/skill-classifier`, cut from a freshly verified clean `main`
  (`main` == `origin/main`, both at `d0159a4`). `slice_kind: parser` (unlike
  the taxonomy foundation: this slice owns a genuine single JSON-array
  fixture corpus, the classic classifier-fixture shape). `slice_id:
  2026-09-19-skill-classifier-d0159a4`. Implements the four-round-negotiated,
  user-approved `classify_skills` proposal and its amendments in full.
- **Classifier** (`backend/app/normalization/skills.py`):
  `classify_skills(title, description, *, taxonomy) -> list[SkillMatch]`.
  One shared segment/token grammar (`[,;|:/]` then
  `[^\s()\[\]{}"&]+`, hyphen/`+`/`#`/`.` preserved); a single-vs-doubled
  trailing-punctuation rule (`.`/`!`/`?`); the ambiguous keys `c`/`r`/`go`/
  `node` require standalone-in-segment (title) or a narrow role-noun
  adjacency for `c`/`r`/`go` only (title), or an explicit anchor-bounded
  region (description) — never punctuation structure alone. The
  description anchor grammar (`skills:`/`languages:`/`technologies:`/
  `tech stack:`) is ASCII-literal and covered-whitespace-exact (no `\s`,
  no `re.IGNORECASE`, no `.lower()`), valid only at start-of-field,
  start-of-line, or immediately after a genuine sentence terminator; a
  region's end is a terminator's own `Pattern.end()` (Python's exclusive
  slice convention), inclusive of the whole punctuation run, so the
  existing single-vs-doubled rule remains the only thing deciding
  match/no-match once a token is extracted. `SkillMatch.__post_init__`
  revalidates `canonical_id` against `is_canonical_slug()` and
  `display_name` against this module's own covered-whitespace class,
  never a bare truthiness check; `provenance` must be a genuine
  `Provenance` member. Every error message is fixed and categorical.
  Exact-match taxonomy lookup only — no taxonomy growth, no persistence,
  no `parser_version`.
- **Fixtures and tests**: `backend/tests/fixtures/normalization/
  skill_cases.json` (61 cases, each isolating one mechanism — tokenizer
  boundaries, the `node`/`c`/`r`/`go` ambiguity rule, the title
  role-noun-adjacency rule and its three counterexamples, terminal
  punctuation and its malformed-run negatives, the anchor grammar's three
  start conditions and two Unicode no-break-space negatives (before and
  after the colon — see the adversarial finding below), region
  termination at a genuine sentence boundary, cross-field dedup/provenance
  escalation); honestly labeled `synthetic_representative`/
  `synthetic_adversarial`, never `sanitized_capture`.
  `backend/tests/test_normalization_skills.py` (76 tests): the fixture
  corpus, origin-honesty, determinism, sort/dedup invariants, `SkillMatch`
  unit-level invariant tests (non-slug `canonical_id`, whitespace-only/
  covered-whitespace-only/empty `display_name`, non-enum `provenance`,
  and a check that no invariant-violation message ever contains the
  offending input text), and the AST import-boundary allow-list.
- **Disclosed, necessary deviation** (found by actually running
  `verification_scope.classify_path` against the new fixture path, not by
  code review): `backend/tests/fixtures/normalization/skill_cases.json`
  is a non-`.py` path under `backend/tests/` with no exact rule, so it
  raised `OwnerMappingRequiredError` exactly like the taxonomy
  foundation's own YAML fixtures once did. Fixed the same way: added one
  exact-path entry, `_SKILL_FIXTURE_FILES`, to
  `backend/scripts/verification_scope.py` (never a new directory prefix),
  classifying it as `test-fixture:skill-classifier` — deliberately not a
  `contract-record` kind, since this fixture has no contract-harness
  guard/family involvement. Three new regression tests added to
  `backend/tests/test_verification_scope.py` mirroring the existing
  taxonomy-fixture ones. This was not part of the approved file list;
  flagging it here rather than treating it as silently in scope.
- **Adversarial self-review finding, fixed before this commit**: an
  independent adversarial-review pass (read-only, against the working
  tree before this candidate existed) found that the description
  anchor's post-colon whitespace group (`[\t\n\r ]*`, zero-or-more, with
  no mandatory literal after it) never actually rejected a non-covered
  whitespace lookalike sitting immediately after the colon — unlike
  every other whitespace span in the anchor grammar, which is always
  followed by a mandatory literal a lookalike can't satisfy. Concretely,
  `"Skills: Go"` (a no-break space right after the colon) produced a
  `golang` match, because the un-consumed no-break space was left as the
  first character of the region text, where the region's own ordinary
  Unicode-`\s`-aware tokenizer still treated it as a token separator —
  silently rescuing the ambiguous key the anchor grammar exists to gate.
  This directly contradicted the module's own docstring, which explicitly
  claimed this case was already rejected. Fixed by adding
  `_has_uncovered_whitespace_immediately_after` and an explicit rejection
  check in `_anchor_regions` for exactly this case; added fixture
  `description_nbsp_lookalike_after_colon_rejected` as the regression.
  Everything else the review checked (region/terminator index arithmetic,
  overlapping anchors, the ASCII casefold table, punctuation-stripping
  edge cases, exception safety on empty/very-long input, and hand
  re-derivation of the trickier fixture cases) held up with no further
  findings.
- **Two-iteration rotation applied**: the oldest iteration (the original
  v3.2 activation candidate/review cycle, C1–C6) is deleted; the former
  Iteration 2 (the post-merge `Q`-producer slice) and Iteration 3 (the
  skill-taxonomy-foundation slice) are renumbered to Iteration 1 and
  Iteration 2 respectively; this entry becomes the new Iteration 3.
- Files changed: `backend/app/normalization/skills.py` (new);
  `backend/tests/fixtures/normalization/skill_cases.json` (new, 61
  cases); `backend/tests/test_normalization_skills.py` (new, 76 tests);
  `backend/scripts/verification_scope.py`,
  `backend/tests/test_verification_scope.py` (edited, 3 new tests (one
  new parametrized case plus two new functions) — see the disclosed
  deviation above); `docs/ROADMAP.md` (edited: corrected
  the stale "skill-taxonomy foundation ... not yet merged" passage to
  record its actual merge SHA, and added this slice's own status
  paragraph); `docs/LLM_HANDOFF.md` (this entry, plus the two-iteration
  rotation above). No taxonomy file, migration, model, service, API, or
  live-provider file touched; no database lifecycle operation performed;
  no provider contact of any kind. `docs/ARCHITECTURE.md` intentionally
  not touched — its `skills.py` filename entry already matches this
  slice exactly; a separate, genuinely stale passage there (the
  taxonomy-foundation's own tree entries still say "candidate/publication
  stage, not yet merged") was noticed but is out of this slice's
  authorized two-document scope, so it is disclosed here rather than
  silently fixed.
- Verification: pending — see the workflow-metadata block below and the
  publication (`A`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-19-skill-classifier-d0159a4
slice_kind: parser
risk_class: H
base_sha: d0159a4cc0faf9fb13f30ea814fa2e6c204570bb
declared_gate: final
executed_gate: final
candidate_sha: 109a3070375be1b8a412abc3dbbbbc76dc379290
receipt_id: 769a9115-2e13-4c92-abfe-6c37a92e26e9
receipt_path: docs/verification-receipts/109a3070375be1b8a412abc3dbbbbc76dc379290/769a9115-2e13-4c92-abfe-6c37a92e26e9.json
fixture_path: backend/tests/fixtures/normalization/skill_cases.json
fixture_count: 61
full_suite_count: 2811
focused_test_count: 145
mutation_witness_count: 34
```

---

## Iteration 2

### Work done

- Date/agent: 2026-09-19, Claude Code (Sonnet 5). Risk class **H**
  (same slice, same primary-risk reasoning as Iteration 1). Base `B`
  (unchanged for this slice's whole correction lifetime) ->
  candidate `C2`: `d0159a4cc0faf9fb13f30ea814fa2e6c204570bb` -> this
  commit; same branch `phase-3/skill-classifier`, on top of the existing
  pushed tip `17f6f24`. `slice_id: 2026-09-19-skill-classifier-d0159a4`
  (unchanged — same slice, a correction cycle within it, matching the
  skill-taxonomy-foundation slice's own C1/C2 precedent). Addresses
  Sol's review of `C = 109a307` and claimed `A = 17f6f24`, both of which
  remain unamended, still pushed, still present in history exactly as
  they were.
- **Bug fix, Sol's finding**: `_next_genuine_terminator_end` scanned
  forward for the first punctuation run whose *following* character was
  in this module's covered-whitespace class (`\t`/`\n`/`\r`/space) or
  end-of-string, and — critically — **skipped past** any punctuation run
  that failed that check, continuing to scan for a *later* one instead
  of stopping. A punctuation run followed by any other Unicode
  whitespace (a no-break space, a vertical tab, a form feed, an em
  space, ...) therefore never ended the region at all; the scan kept
  going, and if no strictly-covered terminator existed later in the
  text, the region silently extended all the way to end-of-string —
  crossing an unrelated clause boundary and wrongly authorizing a
  standalone ambiguous key found there. Confirmed exactly as reported:
  `"Skills: Python. When ready, Go"` returned `golang`;
  `"Skills: Python. See details, Node"` returned `node.js`.
  **Fix**: split the single `_is_genuine_terminator_end` helper into two
  deliberately asymmetric forms. `_is_covered_terminator_boundary`
  (strict — covered whitespace or end-of-string only) is now used
  *exclusively* by `_sentence_boundary_start_positions`, governing where
  an anchor may *begin* — unchanged, since granting a new anchor must
  stay hard to trigger. `_is_region_ending_boundary` (liberal — *any*
  Unicode whitespace character, via `str.isspace()`, or end-of-string)
  is now used by `_next_genuine_terminator_end`, governing where a
  region *ends* — widened, fail-closed: a region also grants extra
  permission, so a punctuation run followed by anything whitespace-like
  must stop the region right there rather than risk extending across
  unrelated text looking for a stricter match. No other grammar changed:
  unambiguous whole-text matching, the title role-noun-adjacency rule,
  and the anchor-start mechanism itself are all untouched.
- **Regressions and mutation-proving**: added `backend/tests/fixtures/
  normalization/skill_cases.json` cases
  `description_nbsp_after_terminator_ends_region_go` and `..._node` (the
  two exact reported inputs, both now correctly returning only
  `python`), `description_ascii_space_after_terminator_ends_region_control`
  (the same shape with an ordinary space, proving the already-correct
  covered-whitespace case is unaffected), and
  `description_vertical_tab_after_terminator_ends_region` /
  `..._form_feed_after_terminator_ends_region` (proving the fix
  generalizes beyond the no-break space specifically). Fixture corpus is
  now 66 cases (61 + 5). Added direct unit-level tests in
  `backend/tests/test_normalization_skills.py` against the two boundary
  helpers themselves (`_is_covered_terminator_boundary`,
  `_is_region_ending_boundary`), parametrized over covered whitespace,
  four non-covered whitespace variants, a non-whitespace letter, and a
  bare punctuation character, plus a test proving the liberal form
  accepts a strict superset of what the strict form accepts (never a
  narrower, inconsistent widening) — 104 tests total (76 + 28).
- **Adversarial self-review finding, fixed before this commit**: an
  independent adversarial-review pass (read-only, including live
  monkeypatch-based reverts of the fix and direct execution against the
  real taxonomy, not just static reasoning) confirmed the fix genuinely
  generalizes across a wide range of Unicode whitespace categories
  (no-break space, vertical tab, form feed, em/en space, line/paragraph
  separator, narrow no-break space, NEL, ideographic space, C0
  separators), confirmed no regression across the 61 pre-existing
  fixture cases (provably, since covered whitespace is a strict subset
  of `str.isspace()`, so the liberal boundary can only end a region at
  the same position or earlier, never later), confirmed the two new
  unit tests are not vacuous (reverting `_is_region_ending_boundary` to
  the old strict form makes them, and 4 of the 5 new fixture cases,
  genuinely fail), and confirmed no analogous bug on the anchor-start
  side. It found one real defect: the module docstring's "terminator"
  definition still described only the strict, covered-whitespace-only
  rule, which after this fix is accurate for anchor-*start* eligibility
  only, not for region-*ending* -- silently understating the fix to a
  future reader relying on the docstring as the grammar spec. Fixed by
  splitting the docstring's single "terminator" definition into the same
  two named, asymmetric concepts the code now uses. Also noted, not
  fixed here (identical before and after this diff, so out of this
  correction's bounded scope): Unicode format characters (zero-width
  space, BOM, the Mongolian vowel separator) are category `Cf`, not
  whitespace, so `str.isspace()` is `False` for them and they still do
  not end a region either way -- a pre-existing residual gap in the same
  threat family, not introduced or worsened by this correction.
- **Old receipt/publication cycle superseded, non-reusable**: receipt
  `769a9115-2e13-4c92-abfe-6c37a92e26e9` (for `candidate_sha: 109a307`)
  verified code containing the bug above and is superseded by this
  correction — it must not be cited as current evidence for this slice
  going forward. It remains on disk unmodified (receipts are
  durable/create-only, never deleted or edited) purely as an immutable
  historical record of what that specific candidate actually contained.
- **`17f6f24` structurally could not serve as `A`**: `check_review.
  validate_c_to_a_transition(C=109a307, A=17f6f24, ...)` passed, because
  that validator only diffs file *content* between the two named commits
  — it never inspects git parentage. But `17f6f24`'s sole parent is
  `85ce56a` (the mistaken commit that first published the receipt with
  an out-of-scope prose expansion), not `109a307` directly. `A` must be
  `C`'s own direct, single-parent child — a content-only diff passing is
  necessary but not sufficient. This is disclosed here rather than
  silently relied upon; `109a307`, `85ce56a`, and `17f6f24` are all
  preserved unamended in history as the record of how this was found and
  worked around, but `17f6f24` is not treated as a valid `A` for
  anything going forward. `C2`/`A2` (this correction) will have their
  own genuine, directly-verified single-parent relationship, checked
  explicitly before this correction is reported complete.
- **Handoff ledger corrected to the documented at-most-two-iteration
  rule**: the ledger had drifted to a rolling three-iteration pattern
  across several prior slices (each rotation kept the two newest of
  three instead of collapsing to two), never itself flagged before now.
  Corrected in this same commit: the two older, unrelated iterations
  (the post-merge `Q`-producer slice and the skill-taxonomy-foundation
  slice) are removed entirely; the skill-classifier implementation entry
  (this slice's own `C`/`A` record, previously "Iteration 3") is
  renumbered to Iteration 1, unchanged in content; this correction
  becomes Iteration 2.
- Files changed: `backend/app/normalization/skills.py` (edited — the
  boundary-helper fix only); `backend/tests/fixtures/normalization/
  skill_cases.json` (edited, +5 cases); `backend/tests/
  test_normalization_skills.py` (edited, +28 tests); `docs/LLM_HANDOFF.md`
  (this entry, plus the iteration-count correction above). No taxonomy
  file, migration, model, service, API, or live-provider file touched;
  no realistic-corpus work; no title-parser work; no workflow-policy
  file touched; no database lifecycle operation performed.
- Verification: pending — see the workflow-metadata block below and the
  publication (`A2`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-09-19-skill-classifier-d0159a4
slice_kind: parser
risk_class: H
base_sha: d0159a4cc0faf9fb13f30ea814fa2e6c204570bb
declared_gate: final
fixture_path: backend/tests/fixtures/normalization/skill_cases.json
fixture_count: 66
```
