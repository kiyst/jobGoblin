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

---

## Iteration 2

### Work done

- Date/agent: 2026-09-09, Claude Code (Sonnet 5). Risk class R
  (R-plus-adversarial, unchanged). Base -> ending commit: `88cdb2f` ->
  this commit; same branch `phase-3/location-classifier`. Bounded
  correction pass applying eight independently-validated findings from
  the blind Sol/Astra comparison review of frozen commit `88cdb2f`,
  per the user's explicit authorization. **Reviewer attribution per
  finding (which came from Astra Light vs. Sol Medium) was not included
  in the correction request relayed to the implementer; this entry
  records the combined validated union of eight defects without
  per-finding attribution, since fabricating that mapping would not be
  honest. The user or the reviewing agents should supply the per-finding
  attribution directly if it needs to be recorded.**
- Eight findings addressed, no behavior change outside them:
  1. **Country-alias trailing-period compatibility**: `_normalize_field`'s
     generic trailing-period strip can remove exactly one period from a
     `U.S.`/`U.S.A.` alias's own final period. Made only that one final
     period optional in each alias (`U\.S\.A\.?`/`U\.S\.?`); a genuine
     doubled terminal period (`"U.S.."`) still correctly fails to
     fullmatch. Applies uniformly across all four productions that use
     `_COUNTRY_TOKEN`.
  2. **State+ZIP country provenance**: `state_zip_form` was wrongly using
     `Provenance.PARSED_DESCRIPTION` for `country="United States"` even
     though "United States" is never literally present in a plain
     `"<geo>, <state> <zip>"` string. Now `Provenance.INFERRED`, matching
     the bare `state_form` case.
  3. **Region whitespace trimming + one exact state parser**: a greedy
     `_GEO_TOKEN` region capture can include incidental trailing
     whitespace before the next comma (e.g. `"TX "` instead of `"TX"`),
     which the old ad hoc `.replace(".", "").upper()` + set-membership
     check did not trim, silently misclassifying a real state as "not a
     state." Replaced with a single authority, `_is_recognized_state`,
     that trims covered whitespace then requires an exact fullmatch
     against the closed `_STATE_TOKEN` grammar (also closes finding 8).
  4. **Standalone negation/exclusion cues**: `"not"`/`"except"`/
     `"excluding"`/`"excluded"` inside a discarded geo/region span now
     reject the whole result the same way the `or`/`and` coordinator
     check does — `"All countries except, Canada"` and `"Not in, Canada"`
     no longer confidently extract `country=Canada`.
  5. **Recognized country in a discarded span is a conflict**: a
     discarded geo or region span that itself exactly matches the
     country catalog (`"Canada, France"`, `"Canada, United States"`,
     `"London, Germany, France"`) is now a rejection trigger, not silently
     ignored — a genuine multi-country conflict, never resolved by
     picking the explicit country slot's value. `"Toronto, ON, Canada"`
     is unaffected (`"ON"` is not a recognized country).
  6. **ASCII-only case-insensitivity for state matching**: added
     `re.ASCII` alongside `re.IGNORECASE` on every compiled pattern in
     this module. Without it, Python's Unicode-aware case-folding could
     treat U+0130 (Turkish dotted capital İ) as case-equivalent to ASCII
     "I", letting `"Wİ"` match Wisconsin or `"İN"` match Indiana — neither
     is an NFKC compatibility variant of "I" (unlike a genuine fullwidth
     letter, which still folds and still resolves correctly).
  7. **State-recognition precedence over the coordinator check**: in the
     three-part form, `"OR"` (Oregon) was being rejected by the
     `or`/`and` standalone-word check before ever being checked against
     the state catalog. `region` is now checked against
     `_is_recognized_state` *first*; only a region that is not a
     recognized state goes through the open-text validation (coordinator/
     negation/marker/sentinel/country-conflict checks). A genuinely
     coordinator-bearing non-state region (`"East or West"`) is still
     correctly rejected.
  8. **Exact state-token grammar validated before canonicalization**:
     `"T...X"`/`"TX..."` no longer fullmatch `_STATE_TOKEN` and are
     correctly never recognized as states (closed by the same fix as
     finding 3); `"DC"`/`"D.C"`/`"D.C."` all remain correctly recognized.
- Files changed: `backend/app/normalization/location.py`,
  `backend/tests/fixtures/normalization/location_cases.json` (+27 cases,
  125 total), `docs/LLM_HANDOFF.md`. No other file touched — none of the
  eight findings required a documentation-attribution or status-line
  fix.
- Mutation-proof mapping:

  | Finding | Mechanism | Regression test(s) | Mutation outcome |
  |---|---|---|---|
  | 1 | Optional final period on `U.S.`/`U.S.A.` aliases | `country_alias_us_dotted`, `country_alias_us_dotted_no_final_period`, `country_alias_usa_dotted`, `country_alias_usa_dotted_no_final_period` | Reverted both aliases to mandatory final periods: all 4 failed (wrongly unavailable). Restored: all 4 passed. `country_alias_us_doubled_period_rejected` correctly unaffected either way. |
  | 2 | `state_zip_form` country provenance | `collision_ca_disambiguated_by_zip`, `collision_ga_disambiguated_by_zip`, `noncolliding_state_zip_positive_control`, `city_state_zip_plus4` | Reverted to the `PARSED_DESCRIPTION` default: all 4 failed. Restored: all 4 passed. |
  | 3 | Region whitespace trim in `_is_recognized_state` | `region_whitespace_space_trimmed_before_comma`, `region_whitespace_nbsp_trimmed_before_comma` | Disabled the trim (`trimmed = raw`): both failed. Restored: both passed. **Note**: `region_whitespace_tab_trimmed_before_comma` does not isolate this mechanism — tab is not in `_GEO_TOKEN`'s character class at all, so the greedy region capture never includes it regardless of trimming; noted directly in its fixture `note`, and it remains a valid neighboring covered-whitespace control per the correction's own request. |
  | 4 | Standalone negation-word check | `negation_except_rejected`, `negation_not_in_rejected` | Removed the negation-word check: both failed (wrongly extracted `country=Canada`). Restored: both passed. `negation_ordinary_positive_control` correctly unaffected either way. |
  | 5 | Country-catalog match on a discarded span | `country_conflict_geo_is_country_france`, `country_conflict_geo_is_country_us`, `country_conflict_region_is_country` | Disabled the check (forced it to always return `False`): all 3 failed (wrongly extracted the explicit country). Restored: all 3 passed. `three_part_region_nonUS_country_preserved` (`"Toronto, ON, Canada"`) correctly unaffected either way. |
  | 6 | `re.ASCII` on the five `_PRODUCTIONS` compiles | `ascii_only_wi_lookalike_rejected`, `ascii_only_in_lookalike_rejected`, `ascii_only_wi_lookalike_zip_rejected` | Removed `re.ASCII` from the five compiled productions: all 3 failed (wrongly resolved Wisconsin/Indiana from the Turkish-İ lookalikes). Restored: all 3 passed. `ascii_only_lowercase_positive_control`/`ascii_only_fullwidth_positive_control` correctly unaffected either way. |
  | 7 | State-check precedence before the coordinator check | `oregon_state_plus_explicit_us` | Reverted the check order (open-text validation runs unconditionally before the state check): failed (Oregon wrongly rejected). Restored: passed. **Note**: `oregon_state_plus_canada_conflict` does not isolate this mechanism — both the (wrong) coordinator rejection and the (correct) state+non-US-country conflict rule produce the same all-four-unavailable outcome; noted directly in its fixture `note`. `genuine_coordinator_region_rejected` correctly unaffected either way. |
  | 8 | Exact `_STATE_TOKEN_RE.fullmatch` (shared fix with finding 3) | `malformed_state_dots_rejected_as_state`, `malformed_state_trailing_dots_rejected_as_state` | Replaced the exact-grammar check with the old loose strip+membership check: both failed (`"T...X"`/`"TX..."` wrongly recognized as states, nulling `country` via the state+non-US-country conflict rule instead of preserving it). Restored: both passed. `dc_bare_preserved_three_part`/`dc_one_period_preserved_three_part`/`dc_two_period_preserved_three_part` correctly unaffected either way. |

- Verification: `ruff format --check`/`ruff check`/`mypy` all pass.
  `python -m scripts.check_repo` exits 0. Genuine external `python -m
  scripts.verify --level routine --focus tests/test_normalization_location.py`
  (full run, see metadata below) — all 11 steps PASS, including `handoff
  metadata validation`. Full unfocused suite: **2193 passed** (was 2166;
  +27 fixture cases). All previously-approved forms re-verified unchanged
  (all 98 prior fixtures still pass with no expected-value edits except
  the four corrected by finding 2).
- Deviations/known limitations: unchanged from the prior iteration's
  disclosed limitations (city resolution deferred; synthetic-only
  corpus apart from the one real Greenhouse fixture; non-US postal
  codes/subnational abbreviations/parenthesized-marker-prefix form
  remain unsupported). No new limitations introduced — this pass only
  fixes the eight reported defects.
- STOP — this commit is frozen for final Codex re-review. Do not merge,
  begin pilot slice retrospective, wire into ingestion/persistence,
  contact providers, or create a migration. No Work review recorded by
  the implementer — that is the reviewer's to write.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: parser
verification_level: routine
focused_test_selector: tests/test_normalization_location.py
focused_test_count: 134
full_suite_count: 2193
fixture_path: backend/tests/fixtures/normalization/location_cases.json
fixture_count: 125
```
