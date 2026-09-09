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
  (R-plus-adversarial, unchanged). Base -> ending commit: `2fcdc0f` ->
  this commit; same branch `phase-3/experience-classifier`. Bounded
  correction pass addressing Astra's review of commit `2fcdc0f` (relayed
  as text; no `### Work review` commit exists on this branch or its
  origin). Scope held to the parser, its tests/fixtures, and this
  documentation.
- Two findings addressed:
  1. **Empty segments break title modifier adjacency**: added
     `_nearest_meaningful_neighbor_is_qualifier`, which walks past any
     empty/whitespace-only segment to find the actual nearest neighbor in
     each direction, instead of checking the raw `index ± 1` position.
     Combined comma+parenthesis splitting (`"(Preferred), 5 years
     experience"`, `"5 years experience, (not required)"`) inserts a
     blank segment directly between the qualifier and its target — the
     raw-index check treated that blank as a barrier; the new check does
     not. Both examples now correctly reject.
  2. **Negative composite ranges leaked an endpoint**: added
     `_NEGATIVE_COMPOSITE_RANGE_RE`, poisoning a free-standing negative
     number combined with any adjacent range separator as one whole span
     — the same treatment the decimal/fraction composites already got in
     the prior round, extended to the negative-number case.
     `"-3 to 5 years experience"` no longer leaks `minimum=5` from the
     untouched second endpoint.
- Files changed: `backend/app/normalization/experience.py`,
  `backend/tests/fixtures/normalization/experience_cases.json` (+5 cases,
  85 total), this handoff entry. No other file touched.
- Mutation-proof mapping:

  | Fix | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|---|
  | 1 | `_nearest_meaningful_neighbor_is_qualifier` | `round4_fix1_leading_parenthesized_qualifier_before_comma`, `round4_fix1_trailing_parenthesized_qualifier_after_comma` | Reverted to raw `index ± 1`: both failed (`minimum=5`). Restored: both passed. |
  | 2 | `_NEGATIVE_COMPOSITE_RANGE_RE` | `round4_fix2_negative_composite_to_range`, `round4_fix2_negative_composite_does_not_swallow_neighboring_valid_phrase` | Removed from `_POISON_PATTERNS`: both failed (first fabricated `minimum=5`; second failed differently — the fabricated `5` conflicted with the real, independent `10`, the same masking-by-spurious-conflict symptom seen in the prior round's equivalent test). Restored: both passed. **Note**: the third related fixture (`round4_fix2_negative_composite_reversed_endpoint_order`, `"5 to -3..."`) does not itself isolate this mechanism — with the poison pattern disabled, `"5"` is still immediately followed by `" to -3 years..."` rather than a unit word, so the pre-existing unit-adjacency strictness independently rejects it regardless; noted directly in its fixture `note`. |

- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (106
  source files). `python -m scripts.check_repo` exits 0. Genuine external
  `python scripts/verify.py --level routine --focus
  tests/test_normalization_experience.py` (full run) — **93 focused /
  1939 full-suite tests** (was 88/1934; +5 fixture cases). All 11 steps
  PASS, including `handoff metadata validation` against this entry's own
  metadata block below. A broader ad hoc regression sweep (not committed
  as fixtures) covering every prior round's examples plus new
  combinations (a leading parenthesized preference marker, an
  alternate-phrasing trailing marker, a three-segment leading case, a
  negative-decimal composite, a composite inside an attribution frame,
  and a qualifier sandwiched between two other segments) all resolved
  correctly with no confidently-wrong output.
- Deviations/known limitations: unchanged from prior iterations' explicit
  exclusions. No new limitations introduced by this correction pass.
- STOP — awaiting Astra's re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_experience.py
focused_test_count: 93
full_suite_count: 1939
fixture_path: backend/tests/fixtures/normalization/experience_cases.json
fixture_count: 85
```

---

## Iteration 2

### Work done

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, unchanged). Base -> ending commit: `1610f57` ->
  this commit; same branch `phase-3/experience-classifier`. Bounded
  correction pass addressing Astra's review of commit `1610f57` (relayed
  as text; no `### Work review` commit exists on this branch or its
  origin). Scope held to the parser, its tests/fixtures, and this
  documentation, per the user's explicit authorization of this single
  bounded correction.
- One finding addressed (High — composite rejection and extraction
  disagree on casing): `_DECIMAL_COMPOSITE_RANGE_RE`,
  `_FRACTION_COMPOSITE_RANGE_RE`, and `_NEGATIVE_COMPOSITE_RANGE_RE` were
  all compiled without `re.IGNORECASE`, while `_RANGE_SEPARATOR`'s
  literal `"to"`/`"and"` substrings and the extraction grammar
  (`_FORWARD_PHRASE_RE`) are case-insensitive. For `"3.5 TO 5 years
  experience"`, the composite poison pattern failed to match on the
  uppercase separator, but the plain `_DECIMAL_RE` (letter-free, casing
  cannot affect it) still poisoned `"3.5"` alone; the untouched `"5"`
  then satisfied the case-insensitive bare production independently,
  fabricating `minimum=5` instead of double-`UNAVAILABLE`. Fixed by
  adding `re.IGNORECASE` to all three composite pattern compilations, so
  poisoning now matches on any casing of the separator, consistent with
  extraction.
- Files changed: `backend/app/normalization/experience.py`,
  `backend/tests/fixtures/normalization/experience_cases.json` (+5 cases,
  90 total), this handoff entry. No other file touched.
- Mutation-proof mapping:

  | Fix | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|---|
  | 1 | `re.IGNORECASE` on all three composite patterns | `round5_fix1_decimal_composite_uppercase_to`, `round5_fix1_negative_composite_uppercase_to`, `round5_fix1_fraction_composite_uppercase_and`, `round5_fix1_decimal_composite_mixed_case_to`, `round5_fix1_composite_does_not_swallow_neighboring_valid_phrase_uppercase` | Removed `re.IGNORECASE` from all three patterns simultaneously: all five failed with the exact reported pre-fix defect (each fabricating `minimum=5` instead of the expected double-`UNAVAILABLE`, or losing the composite's own poisoning while the neighboring independent `10 YEARS EXPERIENCE` phrase remained correctly extracted). Restored: all five passed. |

- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (whole
  tree including `.claude/hooks`). `python -m scripts.check_repo` exits
  0. Genuine external `python -m scripts.verify --level routine --focus
  tests/test_normalization_experience.py` (full run) — **98 focused /
  1944 full-suite tests** (was 93/1939; +5 fixture cases). All 11 steps
  PASS, including `handoff metadata validation` against this entry's own
  metadata block below. An additional ad hoc regression sweep covering
  representative examples from every prior round (basic attribution,
  hyphen-range, leading/trailing parenthesized qualifiers, negative
  composite, uppercase and mixed-case composite variants, label:value,
  short-form) all resolved correctly with no confidently-wrong output.
- Deviations/known limitations: unchanged from prior iterations' explicit
  exclusions. No new limitations introduced by this correction pass.
- STOP — awaiting Astra's re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_experience.py
focused_test_count: 98
full_suite_count: 1944
fixture_path: backend/tests/fixtures/normalization/experience_cases.json
fixture_count: 90
```

### Work review

- Date/reviewer: 2026-09-08, Astra (Codex). Correction diff reviewed:
  `1610f57..559e77a` on `phase-3/experience-classifier`.
- Verdict: **Approved.** The remaining casing inconsistency is corrected in all
  three composite rejection patterns; no required correction remains in this review.
- Reviewed commit: `559e77ac79ce69da877bc57cbba41da38082168c`.
  Clean shared checkout and live `git ls-remote origin` both identify this commit;
  no later commit is present on the remote task branch at review time.
- Independent verification: **98 focused tests pass**; Ruff checks, repository
  validation, and correction diff whitespace checks pass. Independently mutation-
  proved all five round-5 regressions by recompiling the three poison patterns without
  IGNORECASE in memory: all five fail without the fix and pass restored. No executable
  files modified. The 90-case fixture count agrees with the committed corpus.
- Full-suite evidence: Claude's canonical verifier reports all 11 steps passing,
  98 focused / 1944 full-suite tests and metadata validation. The full suite was not
  independently repeated for this isolated regex-flag correction; that limitation
  is explicit and does not invalidate the focused and mutation verification above.
- Remaining limitations: conservative closed grammar; unsupported description section
  headers/standalone labels and numeric forms can yield unavailable; corpus is synthetic.
  No persistence, parser-version/provenance writes, ingestion integration, or Phase 3
  completion claim. Pilot retrospective must count the actual multiple correction
  rounds rather than characterize this slice as meeting the one-round target.
- Recording limitation: this Work review is saved in the review worktree only, pending
  authorized publication; no review commit/push is claimed because the prior automatic
  publication approval rejection remains unresolved. Prior local review preserved.
- Next action: return to Sol to coordinate user-authorized merge verification, including
  resolving review publication before completing the repository workflow. No merge is
  authorized by this review, and no next parser is authorized.
- RETURN TO SOL NOW — Astra's review cycle is complete.
