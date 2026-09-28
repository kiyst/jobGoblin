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

- Date/agent: 2026-09-27, Claude Code (Sonnet 5). Same slice, same
  authorization (`slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-
  0dae468`, risk class **H**, `slice_kind: tooling`, `declared_gate: final`).
  Same branch `phase-3/realistic-corpus-freeze-evaluation`, on top of the
  existing pushed checkpoint `d2097b4`, preserved unamended. One bounded
  correction round for Sol's final Stage 1 re-review verdict (**CHANGES
  REQUESTED**, three findings, F11/F12 High, F13 Medium). The F3-F10
  corrections from the prior two rounds were accepted unchanged and are
  untouched here except where F13 explicitly required fixing a bug
  introduced by F7's own implementation (the metric rename/semantics
  below). No annotation pass, adjudication, corpus freeze, baseline
  evaluation, provider contact, database work, parser-semantic change, or
  new `compensation_text`/`location_raw` extraction performed. Ending
  commit: this commit.
- **F11 (location must describe canonical normalized outputs, not a
  verbatim copy)**: replaced the prior "copy verbatim" rule (which would
  have falsely scored "US" as `confidently_wrong` against the classifier's
  actual `United States` output) with a canonicalization policy — country:
  one canonical full-English-name form, with an explicit alias table
  (`US`/`U.S.`/`USA`/`United States` -> `United States`,
  `UK`/`United Kingdom` -> `United Kingdom`, generalized to "any other
  country in its own full form"); state: exactly one USPS two-letter code
  (the one location sub-field with a genuinely closed domain in the
  current US-only classifier design); city: a deterministic cleaned
  spelling, with an explicit rule that a *region* ("San Francisco Bay
  Area") is never silently annotated as a city; postal code: a
  deterministic normalized textual form (digits-only ZIP5/ZIP5-4 for US,
  natural form otherwise). Added the explicit rule that `description`
  evidence may fill a sub-field `location_raw` leaves unstated, but a
  genuine semantic conflict (not just a spelling difference) between them
  is `ambiguous`. Documented, as a known and deliberate (not newly
  discovered) scope boundary, that `location.city` is expected to show
  `supported_abstention` at or near 100% whenever annotated
  `present_supported`, since the current classifier never populates
  `city` at all, for any input, by permanent design (confirmed directly
  against `app/normalization/location.py`'s own module docstring). Code:
  `evaluate_phase3_corpus.EXPECTED_VALUE_VALIDATORS["location.state"]`
  tightened from `_is_non_empty_str` to the closed 50-state+DC USPS set
  (`_USPS_STATE_CODES`, declared independently, mirroring
  `app.normalization.location.py`'s own `_STATES` catalog rather than
  importing parser internals) — `country`/`city`/`postal_code` stay free
  text, since `docs/DATA_MODEL.md` documents no enum for them (matching
  the `salary.currency`/`.period` precedent from the prior round).
- **F12 (no rules for multiple/nested/conditional numeric requirements)**:
  added a decision table for `experience.minimum`/`.maximum` and
  `salary.minimum`/`.maximum` covering: independent "and"-joined
  requirements with no combined figure (`ambiguous` — two co-equal domains,
  neither is "the" answer); explicit cumulative/additive wording (sum
  exactly as stated, never invented); nested "including" wording (the
  general/outer figure only; the narrower nested figure has no dedicated
  field and is not separately captured -- a scope limitation, not an
  ambiguity); "or"-joined alternatives (`ambiguous` if both paths are
  numeric and differ; the numeric path alone is `present_supported` if the
  other path is non-numeric, e.g. a degree); preferred/ideal vs. required
  thresholds (annotate the required/gating figure only); and multiple
  salary ranges tied to different locations/conditions (`ambiguous` unless
  this record's own stated location selects one band). States plainly:
  never sum potentially overlapping figures unless the text itself makes
  them explicitly additive. All examples fabricated.
- **F13 (gap metric too narrow in scope-description, and had a real
  rendering bug)**: renamed `provider_mapping_gap` ->
  `missing_wired_input_gap` everywhere (dataclass field, `MismatchDetail`
  category, `render_report` line, rubric, docstring) and added an explicit
  statement that it detects only a *completely absent* wired input, never
  a non-null-but-incomplete or mis-mapped one -- that requires later,
  manual mismatch attribution. Fixed the confirmed bug: `_score_component`/
  `_evaluate_composite`'s `wired_input_present` previously defaulted to
  `True`, so every scalar/`experience.*` `present_supported` case
  incremented the gap counter's denominator with `hit=False`, rendering a
  misleading `"0/N"` instead of the promised `"N/A"`. Changed the parameter
  to an explicit applicability sentinel, `bool | None`, defaulting to
  `None` ("not applicable" -- the counter is never touched, so it renders
  `N/A`); only salary/location's call sites in `_evaluate_records` pass an
  explicit `True`/`False`. Also fixed a related, previously-undetected gap:
  a wired input that is present but whitespace-only was being silently
  counted as "present" even though the real `classify_salary`/
  `classify_location` abort on it identically to `None` -- added
  `_is_meaningfully_present()` (non-null and non-blank after `.strip()`)
  and used it at both call sites.
- Because the rubric changed a third time before any annotation exists,
  `RUBRIC_VERSION` bumped `1.0.2 -> 1.0.3`. **Historical, superseded
  evidence** (none ever annotated against), all three now recorded in the
  rubric's own superseded-evidence table: `1.0.0` (commit `7644e20`),
  `1.0.1` (commit `64dd730`), and `1.0.2` (rubric sha256
  `736d53bb7da78cd558fb6f7cab1c18fc991940416e059f5e60cc3b92e19ea0f9`,
  `source_packet_hash 08409a3e57dccf84c34127675078106d6c510ff71813860fb23b
  69fd26bed55a`, commit `d2097b4`). **Current**: rubric sha256
  `3948ec6a09c188a95b9a2ee1fb9ecd94edda2ab5c48bb39e32826e36f51f7f87`,
  `source_packet_hash b56b0f65529fc83a8f30c8958ba697544a321a003b323220b92a
  7c1ac8c6dd1b` (taxonomy/salvage hashes unchanged).
- Verification: `ruff format --check`/`ruff check` clean on all four
  touched files; `mypy` clean on both scripts; full backend suite **3121
  passed** (was 3114; +7 = 6 new/renamed evaluator tests (gap-metric
  applicability-sentinel coverage, whitespace-only handling, scalar N/A
  end-to-end, USPS state closed-set accept/reject) + 1 new freeze-builder
  USPS-state pass-loading test); `check_repo.py` clean; `git diff --check`
  clean.
- Adversarial self-review: reproduced the F13 bug directly (temporarily
  reverted the `None` default back to `True` and reran the affected tests
  -- confirmed `test_evaluate_corpus_scalar_gap_metric_is_not_applicable`
  and `test_score_component_wired_input_present_none_is_not_applicable`
  fail exactly as expected, then restored); confirmed
  `_is_meaningfully_present` is exercised through the real
  `classify_salary`/`classify_location` calls (via `evaluate_corpus`), not
  a mock, against a genuinely whitespace-only `compensation_text`;
  confirmed tightening `location.state` does not affect any existing test
  (none hardcoded a non-USPS state value); confirmed the F12 table's
  "nested including" row and F9's prior "subordinate seniority" row are
  compatible (a general/outer figure is always annotated when one exists,
  never zero information) rather than contradictory; confirmed no example
  anywhere in the rubric quotes or pre-labels any of the 30 real records
  (F10's requirement, re-checked given how much text F11/F12 added).
- Files changed: `docs/evaluation/phase3-realistic-annotation-rubric.md`
  (F11/F12 sections, F13 terminology, `rubric_version` bump),
  `backend/scripts/evaluate_phase3_corpus.py` (`missing_wired_input_gap`
  rename + applicability-sentinel fix, `_is_meaningfully_present`,
  `location.state` closed-set validator, docstring), `backend/tests/
  test_evaluate_phase3_corpus.py` (70 -> 76 tests), `backend/scripts/
  freeze_phase3_realistic_corpus.py` (`RUBRIC_VERSION` bump only),
  `backend/tests/test_freeze_phase3_realistic_corpus.py` (42 -> 43 tests),
  `docs/LLM_HANDOFF.md` (this entry, plus the iteration rotation above).
- STOP -- this remains a checkpoint within an incomplete slice, not a
  candidate. No annotation pass, adjudication, corpus freeze, baseline
  evaluation, provider contact, database work, parser change, title
  normalization, `R`, merge, `M`, or `Q` is authorized by this commit.
  Waiting for Sol's final Stage 1 re-review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-27, Claude Code (Sonnet 5). Same slice, same
  authorization (`slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-
  0dae468`, risk class **H**, `slice_kind: tooling`, `declared_gate: final`).
  Same branch `phase-3/realistic-corpus-freeze-evaluation`, on top of the
  existing pushed checkpoint `80b4672`, preserved unamended. One bounded
  correction round for Sol's final Stage 1 re-review verdict on that
  checkpoint (two findings, F14/F15). Every unaffected F11-F13 rule
  (canonical location forms, the multi-requirement decision table, the
  gap-metric rename/applicability sentinel, `_is_meaningfully_present`'s
  whitespace handling) is preserved unchanged. No annotation pass,
  adjudication, corpus freeze, baseline evaluation, provider contact,
  database work, or parser-semantic change performed. Ending commit: this
  commit.
- **F14 (contradictory non-US `location.state` instructions)**: the
  canonical-domain table already correctly classified a non-US state/
  province/region as `present_unsupported_form`, but the location-
  normalization table's US-state bullet contradicted it, saying to
  annotate such a value "in its own natural written form" -- a value the
  loader's closed USPS-code validator would reject outright. Corrected
  that bullet to state explicitly: `outcome = "present_unsupported_form"`,
  `expected_value = null`, `expected_provenance = "unavailable"`, and
  that the region's natural form must never be written into
  `expected_value`. Added a fabricated synthetic example to the location
  situation/rule table (`location_raw` = "Toronto, Ontario, Canada" ->
  `location.state` is `present_unsupported_form`/null/unavailable, while
  `location.country` = `"Canada"` `present_supported` is unaffected, since
  country's domain is open free text). Also corrected the adjacent
  postal-code wording, which described ZIP+4 as "digits only" -- a ZIP+4
  is exactly five ASCII digits, one hyphen, and four ASCII digits, and the
  hyphen is a required literal part of the form, not a digit; ZIP5 remains
  exactly five ASCII digits.
- **F15 (format-character-only wired inputs silently counted as
  present)**: `_is_meaningfully_present` previously used a bare
  `value.strip() != ""` check, which does not strip Unicode format
  characters (category `Cf`, e.g. U+200B zero-width space, U+FEFF BOM,
  U+180E Mongolian vowel separator) -- confirmed directly that
  `classify_salary`/`classify_location` return entirely unavailable
  results for all three, individually and mixed with ordinary whitespace,
  yet the old check reported them as "present." Replaced it with the
  project's own established meaningful-text rule, mirrored from
  `fetch_greenhouse_evaluation_postings.py`'s `_has_meaningful_text`: a
  value is meaningfully present only if it contains at least one
  character that is neither Unicode whitespace (`str.isspace()`) nor
  category `Cf`. Added `import unicodedata`. Six new regressions: U+200B-
  only, U+FEFF-only, U+180E-only, and ordinary whitespace mixed with only
  those three (all four parametrized as "rejected"); a positive control
  mixing `Cf` characters with genuine visible content (accepted); and one
  end-to-end test through the real `evaluate_corpus`/`classify_salary`
  pipeline confirming a U+200B-only `compensation_text` routes a
  `present_supported` salary annotation to `missing_wired_input_gap`,
  never `supported_abstention`.
- Because the annotation contract changed a fourth time before any
  annotation exists, `RUBRIC_VERSION` bumped `1.0.3 -> 1.0.4`. **Historical,
  superseded evidence** (none ever annotated against), all four now
  recorded in the rubric's own superseded-evidence table: `1.0.0` (commit
  `7644e20`), `1.0.1` (commit `64dd730`), `1.0.2` (commit `d2097b4`), and
  `1.0.3` (rubric sha256
  `3948ec6a09c188a95b9a2ee1fb9ecd94edda2ab5c48bb39e32826e36f51f7f87`,
  `source_packet_hash b56b0f65529fc83a8f30c8958ba697544a321a003b323220b92a
  7c1ac8c6dd1b`, commit `80b4672`). **Current**: rubric sha256
  `70961ec18fcbd5a316bb6ae49b4c9edc0cc1b3957aa6f5cd1f59c1684057eeb9`,
  `source_packet_hash 010a13e0b5040121d4f55df62a0dc3780033469c316380cc1e4
  15c5a86641f92` (taxonomy/salvage hashes unchanged).
- Verification: `ruff format --check`/`ruff check` clean on all four
  touched files; `mypy` clean on both scripts; full backend suite **3128
  passed** (was 3121; +7 = the F15 regressions above); `check_repo.py`
  clean; `git diff --check` clean; focused
  `test_evaluate_phase3_corpus.py` (83 tests) and
  `test_freeze_phase3_realistic_corpus.py` (43 tests, unchanged -- no
  freeze-builder logic touched this round beyond the `RUBRIC_VERSION`
  constant it imports indirectly via the rubric path) both green.
- Adversarial self-review: independently reproduced Sol's exact claim
  before fixing anything -- ran `classify_salary` directly against
  U+200B/U+FEFF/U+180E and a mixed string, confirmed all four return
  entirely unavailable results, and confirmed `unicodedata.category()`
  reports `Cf` for all three code points in this environment's Unicode
  database before trusting the fix's premise; confirmed the new
  `_is_meaningfully_present` body is character-for-character identical in
  logic to `fetch_greenhouse_evaluation_postings.py`'s own
  `_has_meaningful_text`, not a lookalike reimplementation; confirmed the
  new fabricated location example's `country` sub-field is genuinely
  unaffected by the `state` fix (open free-text domain, no validator
  change) rather than assuming it without checking; confirmed no
  existing test asserted the old (incorrect) "natural written form"
  behavior anywhere, so no other test needed updating for F14.
- Files changed: `docs/evaluation/phase3-realistic-annotation-rubric.md`
  (F14 corrections + synthetic example, `rubric_version` bump),
  `backend/scripts/evaluate_phase3_corpus.py` (F15 fix, `unicodedata`
  import, docstring), `backend/tests/test_evaluate_phase3_corpus.py`
  (76 -> 83 tests), `backend/scripts/freeze_phase3_realistic_corpus.py`
  (`RUBRIC_VERSION` bump only), `docs/LLM_HANDOFF.md` (this entry, plus
  the iteration rotation above).
- STOP -- this remains a checkpoint within an incomplete slice, not a
  candidate. No annotation pass, adjudication, corpus freeze, baseline
  evaluation, provider contact, database work, parser change, title
  normalization, `R`, merge, `M`, or `Q` is authorized by this commit.
  Waiting for Sol's final Stage 1 re-review.
