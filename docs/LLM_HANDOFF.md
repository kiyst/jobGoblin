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

- Date/agent: 2026-09-09, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, unchanged). Base -> ending commit: `3c02fac` ->
  this commit; same branch `phase-3/salary-classifier`. Bounded
  correction pass addressing Codex/Sol's review of commit `3c02fac`
  (relayed as text; no `### Work review` commit exists on this branch or
  its origin). Scope held to the parser, its tests/fixtures, and this
  documentation, per the user's explicit authorization of this bounded
  correction. Verdict was **corrections required; do not merge.**
- Seven findings addressed, all narrowing grammar-boundary strictness
  (no behavior change to currency compatibility, period-synonym mapping,
  numeric validation, or atomicity — those remain exactly as merged):
  1. **Unrestricted `\s` replaced with the covered-whitespace class**
     (`_WS = r"[\t\n\r ]"`, matching `_normalize_field`'s own
     `_WHITESPACE`) everywhere a grammar boundary is expressed — label,
     code, operand, period, range separators, and `up ... to`.
  2. **Label boundary strictness**: without a trailing colon, at least
     one covered-whitespace character is now required before whatever
     follows; with a colon, whitespace after it remains optional.
     `"salary120000"`, `"pay$120000"`, `"base salaryUSD120000"` now
     reject; `"Salary:$130,000"` (colon, zero whitespace) remains
     accepted, as does every previously-approved spaced label form.
  3. **Currency-code boundary strictness**: a code (prefix or suffix)
     now always requires at least one covered-whitespace character
     between itself and the amount expression, regardless of the
     label's own boundary. `"USD120000"`, `"120000USD"`,
     `"salary:USD120000"` now reject; `"USD 120000"`, `"120000 CAD"`,
     `"Salary: USD 120000"` remain accepted.
  4. **Period boundary strictness, split by shape**: a slash form
     (`/hr`/`/day`/`/mo`/`/yr`/`/year`, generic `/word`) may still attach
     directly to the amount with no covered-whitespace boundary; every
     word form (`year`, `hourly`, `per year`, an unsupported word, the
     generic `per word` fallback) now requires at least one covered-
     whitespace character before it. `"$120000year"`,
     `"$120000per year"`, `"120000USDyear"` now reject; `"$120000/year"`
     and `"$120000 per year"` remain accepted. The period-synonym dict
     lookup now collapses internal covered-whitespace runs to a single
     space first, so a captured `"per\thour"`-shaped match (an internal
     boundary, not this finding's target, but the same `_WS` discipline)
     still resolves correctly.
  5. **`up ... to` narrowed to exactly two forms**: `"up"` + mandatory
     covered whitespace + `"to"`, or the literal `"up-to"` — replacing
     the old `up[\s-]+to` permissive class. `"up--to"`, `"up -to"`,
     `"up- to"` now reject; `"up to $150,000"` and `"up-to $150,000"`
     remain accepted.
  6. Regression fixtures added for every reproduced malformed input plus
     a neighboring positive control for each — see Files changed and the
     mutation-proof mapping below.
  7. **Documentation attribution corrected**: every claim in
     `salary.py`'s docstring, `test_normalization_salary.py`, and this
     slice's own status lines in `docs/ARCHITECTURE.md`/`docs/ROADMAP.md`
     that this slice was reviewed or would be reviewed by Astra is
     replaced with neutral Codex/proposal-review wording — this slice
     was never in Astra's review queue; the "Astra round-4 correction"
     annotations were a copy-paste artifact from the merged
     `classify_experience` precedent. The historical
     `classify_experience` entries above (Iteration 1, and the quoted
     stale-reference text inside this slice's own prior Work done entry)
     are untouched — Astra genuinely reviewed that slice.
- Files changed: `backend/app/normalization/salary.py`,
  `backend/tests/fixtures/normalization/salary_cases.json` (+19 cases,
  105 total), `backend/tests/test_normalization_salary.py` (attribution
  fix only, no behavior change), `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`
  (attribution fix only), this handoff entry. No other file touched.
- Mutation-proof mapping:

  | Fix | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|---|
  | 2 | Label no-colon mandatory whitespace | `correction_reject_label_no_colon_glued`, `correction_reject_label_no_colon_glued_symbol` | Weakened `_LABEL_PREFIX` back to `\s*:?\s*` (optional either way): both failed (wrongly extracted a value). Restored: both passed. **Note**: `correction_reject_label_no_colon_glued_code` and `correction_reject_label_colon_code_glued` do not isolate this mechanism alone — both are independently rejected by the still-intact code-boundary guard regardless of the label mutation; noted directly in their fixture `note`s. |
  | 3 | Currency-code mandatory whitespace (prefix/suffix) | `correction_reject_code_prefix_glued`, `correction_reject_code_suffix_glued`, `correction_reject_label_colon_code_glued` | Weakened `_CODE_PREFIX`/`_CODE_SUFFIX` to optional whitespace: all three failed. Restored: all three passed. **Note**: `correction_reject_code_and_period_glued` does not isolate this mechanism alone — independently rejected by the still-intact period-boundary guard; noted in its fixture `note`. |
  | 4 | Period word-form mandatory whitespace | `correction_reject_word_period_glued`, `correction_reject_per_period_glued` | Weakened the word-period branch to optional whitespace: both failed. Restored: both passed. **Note**: `correction_reject_code_and_period_glued` does not isolate this mechanism alone either — independently rejected by the code-boundary guard; noted in its fixture `note`. |
  | 5 | `up ... to` narrowed to two forms | `correction_reject_up_double_hyphen`, `correction_reject_up_space_then_hyphen`, `correction_reject_up_hyphen_then_space` | Reverted `_UP_TO` to the old `up[\s-]+to\s+`: all three failed (wrongly extracted `maximum=150000`). Restored: all three passed. |

- Verification: `ruff format --check`/`ruff check`/`mypy` all pass.
  `python -m scripts.check_repo` exits 0. Genuine external `python -m
  scripts.verify --level routine --focus tests/test_normalization_salary.py`
  (full run, see metadata below) — all 11 steps PASS, including `handoff
  metadata validation`. Full unfocused suite: **2059 passed** (was 2040;
  +19 fixture/test cases). All previously-approved forms re-verified
  unchanged (all 96 prior fixtures still pass with no expected-value
  edits).
- Deviations/known limitations: unchanged from the prior iteration's
  disclosed limitations (synthetic-only corpus; sign-before-symbol-only
  negative-number ordering). No new limitations introduced by this
  correction pass — it only tightens boundary strictness, changing no
  approved-form behavior.
- STOP — awaiting Codex/Sol's re-review. Do not merge, begin another
  Phase 3 parser, wire into ingestion/persistence, contact providers, or
  create a migration.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_salary.py
focused_test_count: 115
full_suite_count: 2059
fixture_path: backend/tests/fixtures/normalization/salary_cases.json
fixture_count: 105
```

### Work review

- Date/reviewer: 2026-09-09, Codex/Sol. Correction diff reviewed:
  `3c02fac..261ffe3` on `phase-3/salary-classifier` (relayed as text; no
  `### Work review` commit exists on this branch or its origin).
- Verdict: **Approved.** No findings.
- Independent verification: replayed every reported malformed-boundary
  case (label/code/period glued forms, the three `up...to` mixed-
  separator forms) plus their adjacent valid controls and non-covered-
  whitespace cases; **115/115 focused salary tests pass**; Ruff format/
  check, mypy, `check_repo.py`, `handoff metadata validation`, and
  `git diff --check` all pass.
- Missing/inconclusive checks: the reported **2,059-test full-suite
  result was not independently repeated**.
- Next action: awaiting the user's separate authorization before any
  merge or next-parser work.
- STOP — no merge, no next Phase 3 parser, without explicit user
  authorization.

### Merge record

- Date: 2026-09-09. User authorized merging
  `phase-3/salary-classifier` into `main` following Codex/Sol's Approved
  review above (correction diff `3c02fac..261ffe3`; approval recorded in
  commit `396c939`).
- Pre-merge state: `main` and `origin/main` both at `b9d7f0c`; feature
  branch `phase-3/salary-classifier` and its origin both clean and synced
  at `396c939` (containing implementation commit `3c02fac`, correction
  commit `261ffe3`, and this review-publication commit).
- Merge: `git merge --no-ff phase-3/salary-classifier` on `main` — merge
  commit `5b144a2`. `git diff phase-3/salary-classifier HEAD` is empty
  (zero content difference); `git diff --check` and `check_repo.py` both
  exit 0; working tree clean. No squash, rebase, force-push, or
  implementation change of any kind performed during the merge.
- Post-merge verification: genuine external `python -m scripts.verify
  --level routine --focus tests/test_normalization_salary.py` (full run)
  — all **11 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
  `git diff --check`, disposable-database URL/reachability, **115 focused
  / 2059 full-suite tests**, handoff metadata validation, temp-directory
  cleanup).
- Migration/database state: unchanged. `git diff b9d7f0c HEAD --
  backend/alembic backend/app/db` is empty — no migration or
  database-layer file is part of this diff, so no migration was run and
  no schema changed (this slice introduced no schema changes, as
  expected for a pure parser addition).
- Pushed: `main` at `5b144a2`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `b9d7f0c` (the
  commit immediately before this merge) — this removes
  `backend/app/normalization/salary.py`, its fixture corpus and test
  file, and the `classify_salary` entries in
  `docs/ARCHITECTURE.md`/`docs/ROADMAP.md`, cleanly, with no migration to
  reverse and no data written by this slice to any environment (a pure
  parser addition, never wired into ingestion/persistence or any
  database).
- **`classify_salary` is Workflow v3.1 pilot slice 2 of 3.** It closed
  after one bounded correction round (grammar-boundary strictness),
  within the pilot's one-round target — a pilot-tracking fact, contrasted
  with `classify_experience` (slice 1 of 3), which needed five rounds.
  One more parser slice remains before the mandatory retrospective
  triggers after slice 3's `Work review`.
- STOP — do not begin pilot slice 3 of Workflow v3.1, the mandatory
  retrospective, ingestion wiring, or any other Phase 3 parser without
  separate authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-09, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, established parser-slice convention). Base ->
  ending commit: `d82445f` -> this commit; new branch
  `phase-3/location-classifier`. Workflow v3.1 pilot parser slice 3 of 3,
  implementing the round-4-approved `classify_location` proposal (four
  proposal-review rounds preceded implementation; no branch/code existed
  before this pass). Scope held to the parser, its tests/fixtures, and
  the documentation files the proposal's own Files-expected-to-change
  list named. **Per explicit user instruction, this commit is frozen
  immediately after push for a blind Sol/Astra comparison review — no
  correction pass, no further commits, no Work review recorded by the
  implementer.**
- Outcome: `backend/app/normalization/location.py::classify_location(location)
  -> LocationResult` (four independently-provenanced fields:
  `city`/`state`/`country`/`postal_code`), reading `location` only (no
  `title`/`description`). Implements every binding decision from the
  four proposal-review rounds:
  - **`city` is unconditionally `Provenance.UNAVAILABLE`** for every
    input — deferred, not implemented, in this slice. A denylist-based
    approach (reject known-generic phrases, otherwise trust a city-
    shaped span) was rejected during proposal review as unable to
    establish a positive correctness guarantee; the fix is structural,
    not enumerative. Every production still structurally requires a
    geo/region-shaped span (so a bare, contextless state code alone is
    never confidently resolved either), but that span is always
    discarded, never wired into any output field.
  - Five finite `re.fullmatch` productions (country-alone, geo+state,
    geo+state+ZIP, geo+country, geo+region+country), each wrapped in an
    identical, independently-optional marker prefix/suffix — never both
    present in one match.
  - A frozen, independently-derived, live-source-confirmed (2026-09-09,
    USPS Appendix B + ISO 3166 authority) 26-code collision set (a USPS
    state abbreviation that is also a current ISO 3166-1 alpha-2 country
    code): AL/AR/AZ/CA/CO/DE/GA/ID/IL/IN/KY/LA/MA/MD/ME/MN/MO/MS/MT/NC/
    NE/PA/SC/SD/TN/VA. A collision-bearing code with no US-only anchor
    (ZIP or explicit US country) fails closed; disambiguated by either
    anchor regardless of collision-set membership.
  - The three-part dispatch's four explicit semantic rules (recognized-
    state x explicit-US/non-US, non-state-region x non-US/explicit-US),
    making `"Austin, TX, Canada"` fail while preserving `"Toronto, ON,
    Canada"`.
  - The generic/non-geographic sentinel catalog retained as defense-in-
    depth only (`multiple locations`/`various locations`/`worldwide`/
    `various`/`multiple`/`nationwide`/`global`), rejecting the whole
    result (including `country`) on an exact match — explicitly not the
    mechanism that makes discarding the geo span safe, since nothing
    needs to make that safe.
  - The coordinator/delimiter exclusion (standalone `or`/`and`, `/`/`;`/
    `|`) and marker-embedded-in-geography exclusion applied to every
    discarded geo/region span — necessary specifically because those
    spans are open-ended (unlike `state`/`country`, which reject junk
    "for free" via closed-catalog lookup).
  - Country-alias canonicalization to full English names
    (`US`/`U.S.`/`U.S.A.`/`USA` -> `United States`, `UK` -> `United
    Kingdom`); the `D.C.`/`DC` state exception.
  - Covered-whitespace-only grammar boundaries (`_WS = r"[\t\n\r ]"`)
    and a mandatory-whitespace prefix-hyphen marker boundary, applied
    from the start rather than needing a correction round (the
    `salary.py` grammar-boundary correction's lesson applied
    proactively).
- Files changed: `backend/app/normalization/location.py`,
  `backend/tests/fixtures/normalization/location_cases.json` (98 cases),
  `backend/tests/test_normalization_location.py`, `docs/ARCHITECTURE.md`,
  `docs/ROADMAP.md` (both updated for this slice's status **and** the
  stale "pending Codex review — not merged" `classify_salary` reference,
  corrected here as a same-cycle mechanical edit, not a separate slice —
  a doc-attribution fix, not product behavior), `docs/LLM_WORKFLOW.md`
  (stale "slices 2/3 unstarted" pilot-status line corrected the same
  way), this handoff entry. No other file touched.
- Mutation-proof mapping:

  | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|
  | City-never-populated structural invariant | all 4 `generic_phrase_*_country_only` fixtures, `test_city_field_is_always_unavailable_v1_deferred` | Wired the discarded geo span into the `city` field unconditionally: all 4 fixtures plus the structural-invariant test failed (wrongly showed a populated `city`). Restored: all passed. |
  | Collision-set gate | `collision_ca_no_anchor_rejected`, `collision_in_no_anchor_rejected`, `collision_tn_no_anchor_rejected` | Disabled the `state in _COLLISION_STATES` check: all 3 failed (wrongly resolved `state`/`country`). Restored: all 3 passed. |
  | Sentinel catalog (defense-in-depth) | all 4 `sentinel_*_rejected` fixtures | Forced the sentinel-match check to always return `False`: all 4 failed (wrongly extracted `country`, e.g. `United States` from `"Multiple Locations, United States"`). Restored: all 4 passed. The neighbor positive control (`sentinel_neighbor_legitimate_extracts_country`) correctly remained unaffected either way. |
  | Covered-whitespace-only boundary (NBSP vs. LINE SEPARATOR) | `line_separator_not_covered_whitespace_rejected` | Widened `_WS` to Python's Unicode-aware bare `\s`: failed (U+2028 was wrongly treated as a boundary, resolving `state`/`country` normally instead of rejecting). Restored: passed. `nbsp_normalizes_to_covered_whitespace` correctly remained unaffected either way (NBSP already folds via NFKC regardless of `_WS`'s width). |

- Verification: `ruff format --check`/`ruff check`/`mypy` all pass.
  `python -m scripts.check_repo` exits 0. Genuine external `python -m
  scripts.verify --level routine --focus tests/test_normalization_location.py`
  (full run, see metadata below) — all 11 steps PASS, including `handoff
  metadata validation`. Full unfocused suite: **2166 passed** (was 2059;
  +107 fixture/test cases). An additional novel ad hoc counterexample
  sweep (not committed as fixtures) covering: leading garbage before a
  valid form, a marker-only string wrapped in parentheses with no
  geography, case-insensitive sentinel matching, a three-letter state
  lookalike, glued/doubled comma spacing around a state code, a region
  token that is itself a recognized foreign country name (not a state),
  confirmation that the sentinel check is exact-match only (not
  substring — `"Worldwide Team, Canada"` extracts `country=Canada`
  normally, while `"Worldwide Remote Team, Canada"` is rejected only via
  the embedded-marker check), a lowercase state with a ZIP, a three-part
  state+UK conflict, and a purely numeric discarded-geo span — every
  case resolved to either the correct value or safely `unavailable`,
  with no confidently-wrong output.
- Deviations/known limitations: every synthetic fixture is hand-
  constructed (`synthetic_representative`/`synthetic_adversarial`); the
  one real sanitized location string in this repository (`"Remote,
  US"`, `greenhouse_live_canary.json`) is exercised by
  `test_real_sanitized_greenhouse_fixture_classifies_correctly`, which
  loads the actual fixture file and asserts the source value before
  asserting the classification, so the claim cannot silently drift.
  `city` resolution is explicitly deferred, not implemented (see the
  module docstring) — a disclosed scope boundary, not a defect. The
  26-code collision set was independently derived and cross-checked
  against a second independently-proposed candidate set during proposal
  review, converging exactly; a live-source confirmation against USPS
  Appendix B and the ISO 3166 authority was separately performed and
  accepted (2026-09-09) prior to this implementation. Non-US postal
  codes, non-US subnational abbreviations in the state catalog, and a
  parenthesized-marker-prefix form remain unsupported, per the approved
  proposal's exclusions.
- STOP — this commit is frozen for the planned blind Sol/Astra
  comparison review. Do not merge, begin pilot slice retrospective,
  wire into ingestion/persistence, contact providers, or create a
  migration. No further correction, no Work review, no additional
  commits on this branch until the user separately authorizes the next
  action.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_location.py
focused_test_count: 107
full_suite_count: 2166
fixture_path: backend/tests/fixtures/normalization/location_cases.json
fixture_count: 98
```
