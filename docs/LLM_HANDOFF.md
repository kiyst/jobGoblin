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

### Merge record

- Date: 2026-09-08. User authorized publishing the pending review commit and
  merging `phase-3/experience-classifier` into `main` following Astra's
  Approved review above (correction diff `1610f57..559e77a`; approval
  recorded in commit `d46f20f`).
- Review publication: local-only review commit `d46f20f` (docs-only, `docs/
  LLM_HANDOFF.md` alone, 31 insertions/0 deletions) was pushed to
  `origin/phase-3/experience-classifier` first, resolving the prior
  publication gap noted in the review's own "Recording limitation" line.
- Pre-merge state: `main` and `origin/main` both at `ddb427d`; feature
  branch `phase-3/experience-classifier` and its origin both clean and
  synced at `d46f20f` (containing implementation commit `e13d8a6`, four
  correction passes `2589eec`/`2fcdc0f`/`1610f57`/`559e77a`, and this
  review-publication commit).
- Merge: `git merge --no-ff phase-3/experience-classifier` on `main` —
  merge commit `6f9ae53`. `git diff phase-3/experience-classifier HEAD` is
  empty (zero content difference); `git diff --check` and `check_repo.py`
  both exit 0; working tree clean.
- Post-merge verification: genuine external `python -m scripts.verify
  --level routine --focus tests/test_normalization_experience.py` (full
  run) — all **11 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
  `git diff --check`, disposable-database URL/reachability, **98 focused /
  1944 full-suite tests**, handoff metadata validation, temp-directory
  cleanup).
- Migration/database state: unchanged. `git diff ddb427d HEAD --
  backend/alembic backend/app/db` is empty — no migration or
  database-layer file is part of this diff, so no migration was run and no
  schema changed.
- Pushed: `main` at `6f9ae53`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `ddb427d` (the
  commit immediately before this merge) — this removes
  `backend/app/normalization/experience.py`, its fixture corpus and test
  file, and the `classify_experience` entries in
  `docs/ARCHITECTURE.md`/`docs/ROADMAP.md`, cleanly, with no migration to
  reverse and no data written by this slice to any environment (a pure
  parser addition, never wired into ingestion/persistence or any
  database).
- **`classify_experience` is Workflow v3.1 pilot slice 1 of 3.** It closed
  after five correction rounds (four `AskUserQuestion`-confirmed plus one
  user-self-authorized), not the one-round target; per Astra's review,
  the mandatory pilot retrospective must count this actual round total
  rather than characterize the slice as meeting that target.
- STOP — do not begin pilot slice 2/3 of Workflow v3.1 or any other Phase 3
  parser without separate authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-09, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, established parser-slice convention). Base ->
  ending commit: `b9d7f0c` -> this commit; new branch
  `phase-3/salary-classifier`. Workflow v3.1 pilot parser slice 2 of 3,
  implementing the round-4-approved `classify_salary` proposal (three
  proposal-review rounds preceded implementation; no branch/code existed
  before this pass). Scope held to the parser, its tests/fixtures, and
  the two documentation files the proposal's own Files-expected-to-change
  list named.
- Outcome: `backend/app/normalization/salary.py::classify_salary(compensation_text)
  -> SalaryResult` (four independently-provenanced fields: `minimum`/
  `maximum`/`currency`/`period`), reading `compensation_text` only (no
  `title`/`description`, an explicit approved scope boundary). Implements
  every binding decision from the three proposal-review rounds:
  - `Provenance.PARSED_DESCRIPTION` (not `INFERRED`) for every successful
    extraction, per `docs/DATA_MODEL.md`'s literal "extracted via
    regex/rules from free text" definition.
  - A whole-field lexical/semantic split: five finite `re.fullmatch`
    productions (bare/open-lower, open-upper, hyphen-range, to-range,
    between-and-range), each requiring the *entire* normalized field to
    match — unknown leftover text, a second candidate, or a
    component-attribution word (bonus/commission/OTE/equity/stock/
    stipend/sign-on/total-compensation) all fail to fullmatch and land in
    Table D (all four fields unavailable), with no separate keyword-scan
    mechanism needed.
  - Numeric failure is atomic across a range: either operand invalid ->
    both bounds unavailable, proven across all three separators
    (`-`/`to`/`between...and`) and both operand positions.
  - ASCII-only `[0-9]` digit classes (never bare `\d`), with NFKC
    pre-normalization so a fullwidth digit folds into range while a
    genuinely different digit system (Arabic-Indic) is lexically
    rejected, landing in Table D rather than a semantic numeric failure.
  - The exact three-step normalization order (NFKC -> covered-whitespace
    strip -> at most one trailing-period strip -> re-strip).
  - The full currency-compatibility table (`$` compatible with
    `USD`/`CAD`/`AUD`, conflicting with `GBP`/`EUR`; `£`/`€` unambiguous
    to `GBP`/`EUR`; two conflicting codes/symbols -> currency unavailable
    only, numeric/period unaffected).
  - The closed period-synonym catalog (22 synonyms across
    `hourly`/`daily`/`monthly`/`annual`) plus the enumerated-unsupported
    and generic `/word`/`per word` fallback, whose match invalidates
    numeric bounds too (the one approved cross-field contamination rule).
  - Bare single amount -> equal `minimum`/`maximum`; explicit open-
    lower/upper set only their stated bound; shared trailing `k` in a
    complete range applies to both operands.
  - Nonnegative/ordered/PostgreSQL-int32-range enforcement (malformed
    grouping and overflow both reject; an inverted range is never
    silently reordered, mirroring `ExperienceRange`'s established
    defense-in-depth pattern).
  - The explicit anchor requirement: a bare unanchored number (even
    across a structurally-valid range) is never extracted.
- Files changed: `backend/app/normalization/salary.py`,
  `backend/tests/fixtures/normalization/salary_cases.json` (86 cases),
  `backend/tests/test_normalization_salary.py`, `docs/ARCHITECTURE.md`,
  `docs/ROADMAP.md` (both updated for this slice's status **and** the two
  stale "pending Astra review — not merged" `classify_experience`
  references, corrected here as a same-cycle mechanical edit per the
  user's explicit instruction, not a separate slice), this handoff entry.
  No other file touched.
- Mutation-proof mapping:

  | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|
  | Range atomicity (both separators, both operand positions) | all 8 `atomic_failure_*` fixtures | Disabled the invalid-operand-nulls-both branch (kept the clean operand as a standalone match): all 8 failed, each producing a spurious single-sided value. Restored: all 8 passed. |
  | Anchor requirement | `bare_zero_no_anchor`, `range_no_anchor_at_all` | Forced `has_anchor = True` unconditionally: both failed (produced a value instead of unavailable). Restored: both passed. **Note**: `no_anchor_no_extraction` does not itself isolate this mechanism — it fails earlier at the whole-field fullmatch stage (leading prose) regardless of the anchor check; noted directly in its fixture `note`. |
  | Currency-compatibility conflict check | `dollar_gbp_conflicting`, `dollar_eur_conflicting`, `pound_usd_conflicting`, `euro_gbp_conflicting` | Removed the symbol-vs-code compatibility check (returned the explicit code unconditionally): all 4 failed (wrongly resolved a currency instead of unavailable). Restored: all 4 passed. **Note**: `multiple_codes_conflicting` does not itself isolate this mechanism — it is independently rejected by the separate two-codes-conflict check; noted directly in its fixture `note`. |
  | ASCII-only digit class (`[0-9]` vs. bare `\d`) | `unicode_digit_rejected_whole_field_unavailable` | Replaced `[0-9]` with `\d` in the lexical numeric body: the Arabic-Indic-digit text now wrongly fullmatched, leaking `currency`/`period` as resolved instead of all four fields unavailable. Restored: passed. |
  | Shared trailing `k` | `k_shorthand_shared_trailing` | Disabled the backward-sharing step: failed (`minimum=120` instead of `120000`). Restored: passed. |
  | Malformed-grouping shape check | `malformed_grouping`, `malformed_grouping_leading_1digit_then_2` | Removed the grouping-shape validation: both failed (wrongly extracted a concatenated value). Restored: both passed. **Note**: `atomic_failure_malformed_grouping_first_endpoint` does not itself isolate this mechanism — with grouping unchecked, the first operand's concatenated value exceeds the second operand's, so the pre-existing inversion check independently produces the same double-unavailable outcome; noted directly in its fixture `note`. |
  | Int32 overflow guard | `overflow`, `atomic_failure_overflow_second_endpoint`, `atomic_failure_to_range_second_operand`, `atomic_failure_between_and_second_operand` | Removed the `> _INT32_MAX` check: all 4 failed (wrongly extracted or promoted an out-of-range value). Restored: all 4 passed (`exactly_int32_max_valid`, the boundary case, correctly unaffected either way). |
  | Unsupported-period invalidates numeric | `unsupported_period_enumerated`, `unsupported_period_generic_fallback` | Removed the cross-field invalidation step: both failed (numeric bounds wrongly survived). Restored: both passed. |

- Verification: `ruff format --check`/`ruff check`/`mypy` all pass.
  `python -m scripts.check_repo` exits 0. Genuine external `python -m
  scripts.verify --level routine --focus tests/test_normalization_salary.py`
  (full run, see metadata below) — all 11 steps PASS, including `handoff
  metadata validation`. Full unfocused suite: **2040 passed** (was 1944;
  +96 fixture/test cases). An additional ad hoc contract-conformance and
  counterexample sweep (not committed as fixtures) covering: leading-
  garbage-before-label/currency text, an unenumerated `per diem` generic
  fallback, a space inside a grouped number, scientific notation, a
  three-operand range, a double period marker, symbol-then-sign ordering
  (`"$-120,000"`, not part of the approved grammar), per-operand code
  repetition (not part of the approved grammar), and both operands
  already carrying their own `k` — every case resolved to either the
  correct value or safely `unavailable`, with no confidently-wrong
  output.
- Deviations/known limitations: every fixture is hand-constructed
  synthetic (`synthetic_representative`/`synthetic_adversarial`); no
  real, sanitized salary-bearing posting text has been collected or
  reviewed for this slice — an explicit, disclosed exit-gate evidence
  limitation, not treated as satisfied (mirrors `classify_experience`'s
  own disclosed "corpus is synthetic" limitation). The negative-sign
  grammar recognizes only sign-before-symbol ordering (`"-$3"`), per the
  approved proposal's own example; the reverse ordering
  (`"$-3"`) is not part of the finite grammar and fails safely to
  `unavailable` rather than misreading it, not a confidently-wrong gap.
- STOP — awaiting Astra's review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_salary.py
focused_test_count: 96
full_suite_count: 2040
fixture_path: backend/tests/fixtures/normalization/salary_cases.json
fixture_count: 86
```
