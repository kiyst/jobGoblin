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

### Work review

- Date/reviewer: 2026-09-09, Codex/Sol (combining Astra Light and Sol
  Medium's blind-comparison findings). Correction diff reviewed:
  `88cdb2f..071d8dc` on `phase-3/location-classifier` (relayed as text;
  no `### Work review` commit exists on this branch or its origin).
- Verdict: **Approved.** All eight findings independently confirmed
  closed by direct reproduction against the actual committed code (not
  merely by re-reading the implementer's own report).
- Independent verification performed, with file/line evidence:
  1. Dotted `U.S.`/`U.S.A.` aliases — `location.py:349-378` (`_COUNTRY_CANONICAL`/
     `_COUNTRY_TOKEN`). Reproduced `"Remote, U.S."`, `"Remote, U.S"`,
     `"Austin, U.S.A."`, `"Austin, U.S.A"` all -> `country=United States`;
     `"Remote, U.S.."` (genuine doubled terminal period) -> unavailable,
     confirming no broadened malformed-punctuation acceptance.
  2. ZIP-implied country provenance — `location.py:591-600` (`state_zip_form`).
     Reproduced `"Austin, TX 78701"` -> `country.provenance == INFERRED`
     (was `PARSED_DESCRIPTION`); the three-part explicit form
     (`"Austin, TX, United States"`) correctly still yields
     `PARSED_DESCRIPTION` — no cross-contamination between the two paths.
  3. Region trailing-whitespace bypass — `location.py:488-500`
     (`_is_recognized_state`). Reproduced `"Toronto, TX , United States"`
     (ASCII space) and the NBSP variant both -> `state=TX`; mutation-
     disabled the trim myself (independently, not merely re-reading the
     implementer's claim) and confirmed both fail without it.
  4. Negation/exclusion in discarded spans — `location.py:425-433`
     (`_NEGATION_WORDS_RE`). Reproduced `"All countries except, Canada"`
     and `"Not in, Canada"` both -> all four unavailable; `"Chicago,
     Canada"` and `"Andover, NH"` (substring, not standalone) both
     unaffected.
  5. Conflicting country tokens — `location.py:454-461`
     (`_geo_span_is_rejected`'s final check). Reproduced `"Canada,
     France"`, `"Canada, United States"`, `"London, Germany, France"` all
     -> all four unavailable; `"Toronto, ON, Canada"` correctly preserved
     (`"ON"` is not a recognized country).
  6. Unicode state-token matching — `location.py:333`
     (`_STATE_TOKEN_RE`), `location.py:401-432` (`_PRODUCTIONS`/`_OR_AND_RE`/
     `_NEGATION_WORDS_RE`/`_MARKER_WORD_RE`, all now `re.IGNORECASE |
     re.ASCII`). Reproduced `"Austin, Wİ"`, `"Austin, İN"`, `"Austin, Wİ
     12345"` (U+0130) all -> unavailable; `"austin, wi"` and `"Austin,
     ＷＩ"` (genuine NFKC-folding fullwidth letters) both correctly ->
     `state=WI`. Independently removed `re.ASCII` from the five compiled
     productions and confirmed the three Turkish-İ cases wrongly resolve
     to Wisconsin/Indiana without it.
  7. Oregon `OR` precedence — `location.py:565-576` (`classify_location`'s
     region-then-coordinator-check ordering). Reproduced `"Austin, OR,
     United States"` -> `state=OR`; `"Austin, OR, Canada"` -> all four
     unavailable via the state+non-US-country conflict rule (not the
     coordinator check); `"Toronto, East or West, Canada"` (genuinely
     non-state, coordinator-bearing) still correctly rejected.
  8. Malformed state punctuation — same fix site as finding 3
     (`_is_recognized_state`'s `_STATE_TOKEN_RE.fullmatch`). Reproduced
     `"Toronto, T...X, Canada"` and `"Toronto, TX..., Canada"` both ->
     `country=Canada`/`state` unavailable (never recognized as a state);
     `"Somewhere, DC/D.C/D.C., United States"` all three -> `state=DC`.
- **Mutation-proof adequacy, independently re-verified** (not merely
  accepted from the Work done narrative): the two fixtures flagged
  "non-isolating" were re-tested directly. `region_whitespace_tab_trimmed_before_comma`
  (finding 3) genuinely does not isolate the trim mechanism — `_GEO_TOKEN`
  (`location.py:396`, `r"[A-Za-z][A-Za-z .'\-]*"`) never included tab in
  its character class, so the greedy region capture excludes it
  regardless of trimming; confirmed by independently disabling the trim
  and observing the tab fixture still passes while the space/NBSP
  fixtures for the same finding correctly fail. `oregon_state_plus_canada_conflict`
  (finding 7) is similarly confirmed non-isolating — reverting the
  precedence fix leaves it passing, because the wrong path (coordinator
  rejection) and the correct path (state+non-US-country conflict rule)
  both produce all-four-unavailable. In both cases, **at least one other
  fixture for the same finding is genuinely load-bearing**
  (`region_whitespace_space_trimmed_before_comma`/
  `region_whitespace_nbsp_trimmed_before_comma` for finding 3;
  `oregon_state_plus_explicit_us` for finding 7), independently confirmed
  to fail under mutation. Workflow v3.1's rule — a test must not be
  *reported as closing* a finding it does not actually prove when its
  guard is disabled — is satisfied: the Work done entry already labels
  both fixtures as non-isolating rather than claiming they close their
  findings, and does not rely on them as the sole evidence for findings
  3 or 7. This is a satisfied disclosure, not a remaining process/evidence
  defect.
- **Cross-cutting regression checks** (per the review request, beyond
  the eight findings themselves): no broader alias acceptance (`"U..S."`,
  `"U.S.A.."`, `"U.S.A.A."` all still correctly rejected); no provenance
  cross-contamination (explicit-country forms stay `PARSED_DESCRIPTION`,
  state-inferred forms stay `INFERRED`, confirmed across all four
  three-part dispatch rules independently); no Unicode bypass beyond
  finding 6 itself; no new state/country dispatch inconsistency (all
  four three-part rules and the collision-set ZIP/explicit-US
  disambiguation paths re-verified unaffected).
- Historical Work done entry integrity: `git diff 88cdb2f..071d8dc --
  docs/LLM_HANDOFF.md` shows the location classifier's own prior Work
  done entry (this iteration's, now renumbered Iteration 1 by the
  standard two-iteration rotation) preserved byte-for-byte, only
  appended to. The entry deleted by that same rotation belongs to the
  already-merged, already-closed `classify_salary` slice, not this one.
- Missing/inconclusive checks: none. Every finding was reproduced
  directly; every mutation-proof claim was independently re-executed,
  not merely re-read.
- Attribution for the record: **Astra Light** found findings 1 (dotted
  aliases) and 2 (ZIP-implied country provenance). **Sol Medium** found
  finding 1 (independently, shared with Astra Light) plus findings 3-8.
  The combined validated union across both reviewers is eight defects,
  all now closed.
- Next action: awaiting the user's separate authorization before any
  merge or next-parser work.
- STOP — no merge, no next Phase 3 parser, no mandatory retrospective,
  without explicit user authorization.

### Merge record

- Date/agent: 2026-09-09, Claude Code (Sonnet 5), per explicit user
  merge authorization.
- Approved feature tip: `c1a5235` (`phase-3/location-classifier`,
  includes the approved `Work review` above). Pre-merge `main`/
  `origin/main`: `d82445f`, synchronized, clean working tree — verified
  immediately before merging, not assumed from a prior snapshot.
- Merge: `git merge --no-ff --no-edit` (no squash, no rebase, no
  force-push, no implementation changes) of `phase-3/location-classifier`
  into `main`. Merge commit: `a32b5cc`.
- Zero-content-difference check: `git diff c1a5235 main` — empty;
  confirms the merge introduced no content beyond what was already
  approved on the feature tip.
- Canonical verifier on merged `main` (`python -m scripts.verify
  --level routine --focus tests/test_normalization_location.py`): ALL
  11 CHECKS PASSED — 134 focused / 2193 full-suite tests, `check_repo.py`
  ok, `git diff --check` ok, `handoff metadata validation` ok.
- Migration/database state: unchanged. `git diff --stat 88cdb2f main --
  backend/alembic backend/migrations` and `git log d82445f..main --
  backend/alembic backend/migrations` both empty — no schema/migration
  file touched by this slice or its merge; the verifier's disposable
  test-database reachability preflight passed against the existing
  schema with no drift.
- Pushed: `origin/main` now at `a32b5cc` (was `d82445f`).
- Rollback boundary: `git reset --hard d82445f` on `main` (pre-merge
  tip) would fully revert this merge; the feature branch
  `phase-3/location-classifier` at `c1a5235` remains intact and
  unforced, independently recoverable regardless of any `main` rollback.
- STOP — merge complete. Do not begin another Phase 3 parser. The
  mandatory Workflow v3.1 pilot retrospective (three parser slices now
  merged: `classify_experience`, `classify_salary`, `classify_location`)
  is required next, under separate explicit user authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-09, Claude Code (Sonnet 5). Risk class D
  (documentation-only). Base -> ending commit: `4ecc4b3` -> this commit;
  new branch `tooling/workflow-v3.2-retrospective`. This is the mandatory
  Workflow v3.1 pilot retrospective, authorized as Slice 1 of 3 of a
  staged Workflow v3.2 proposal (Slices 2/3 — the parser-contract harness
  and the fast/final verifier/receipt/metadata redesign — are planned but
  **not authorized** by this slice; see the ADR's "Activation boundary").
- Outcome: `docs/DECISIONS/0008-workflow-v3.1-retrospective-and-v3.2-adoption.md`
  (new) records: the corrected per-slice retrospective for
  `classify_experience` (four post-implementation correction rounds, 13
  findings [7+3+2+1], six pre-code amendments recorded separately,
  proposal-submission count not reconstructible), `classify_salary`
  (three documented proposal-review rounds, one executable correction
  round addressing five executable grammar-boundary mechanisms, their
  accompanying regression fixtures, and one documentation-attribution
  correction; no salary finding meets the strict confidently-wrong bar —
  the boundary-acceptance defects demonstrate malformed input being
  wrongly accepted, not a value contradicted by the input — and no exact
  count under that definition is reconstructible from durable evidence),
  and `classify_location`
  (four documented proposal-review rounds, one executable correction
  round, eight validated findings including four committed
  confidently-wrong cases); the four numerical target verdicts
  (correction-round: fail; confidently-wrong: fail; handoff-count: pass;
  load-bearing-regression: pass); the Astra Light/Sol Medium comparison
  recorded strictly as a configuration comparison, not a model/effort
  claim; and the note that count-mismatch fault injection already exists
  in `backend/tests/test_check_handoff.py` and simply was not triggered
  by a real fabricated count during the pilot. It also records the
  accepted Workflow v3.2 design principles (compact contracts,
  two-submission parser proposal limit, Sol Medium as mandatory primary
  reviewer, selective Astra escalation, executable parser contracts,
  mechanism-level mutation evidence, fast/final gates, stable slice/
  finding IDs, durable verification evidence, unchanged user-only scope
  and merge authority) and five unresolved Slice 3 design questions
  (pre-receipt candidate verification; non-circular receipt attestation;
  allowed documentation-only differences between attested and merged
  trees; a candidate/reviewed/corrected/approved/merge-reuse metadata
  state machine; no ephemeral receipt as durable merge evidence).
- **Workflow v3.1 remains the sole active workflow version.** No
  version-bearing consumer was touched: `CLAUDE.md`,
  `.claude/hooks/compact_checkpoint.py`, `backend/scripts/check_handoff.py`,
  its tests, and every existing `docs/LLM_HANDOFF.md` entry's
  `workflow_version` field are unmodified by this slice. The ADR
  describes Slices 2/3's planned artifacts (contract harness, receipts,
  verifier profiles) without linking to any file, since none of them
  exist yet.
- Files changed: `docs/DECISIONS/0008-workflow-v3.1-retrospective-and-v3.2-adoption.md`
  (new), this handoff entry (two-iteration rotation — the prior
  Iteration 1, `classify_location`'s original pre-correction Work done
  entry, was deleted per the standard rotation rule since the whole
  `classify_location` slice is already closed via Iteration 2's approval
  and merge record; Iteration 2's content is preserved byte-for-byte
  above, only renumbered to Iteration 1). No other file touched.
- Verification (docs-only, per Workflow v3.1's existing `slice_kind:
  docs` provisions): `git diff --check` — clean. `python -m
  scripts.check_repo` exits 0. Genuine external `python -m scripts.verify
  --docs-only` — all applicable steps PASS (database/pytest steps
  correctly skipped per `--docs-only`'s own contract); no executable or
  test file changed, so no focused/full-suite run applies.
- Deviations/known limitations: this ADR's own "not reconstructible"
  figures (experience's proposal-submission count; salary's exact
  confidently-wrong finding count under the strict definition) are
  deliberate gaps — not zero, and not to be silently filled with an
  estimate later.
- STOP — this is Slice 1 of 3 only. Do not implement the contract
  harness, receipt system, verifier profiles, metadata schema changes,
  workflow-version changes, title parser, or skill parser. Do not merge,
  begin Slice 2 or 3, or start any other Phase 3/4 work without separate
  explicit user authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: docs
verification_level: not_run
focused_test_selector: none
focused_test_count: not_run
full_suite_count: not_run
lightweight_checks: git diff --check; python -m scripts.check_repo; python -m scripts.verify --docs-only
```
