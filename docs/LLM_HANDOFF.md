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
  existing pushed checkpoint `64dd730`, preserved unamended. One bounded
  correction round for Sol's Stage 1 re-review verdict (**CHANGES
  REQUESTED**, four findings, F7/F8/F9/F10, all High). The F3/F4/F5/F6
  mechanical corrections from the prior round were accepted unchanged and
  are untouched here. No annotation pass, adjudication, corpus freeze,
  baseline evaluation, provider contact, database work, parser-semantic
  change, or new `compensation_text`/`location_raw` extraction performed.
  Ending commit: this commit.
- **F7 (source-field rule hid the provider-mapping gap)**: the rubric's
  source-field table no longer restricts salary/location *ground truth* to
  `compensation_text`/`location_raw` alone -- both are now pooled with
  `title` + `description`, so a real salary/location statement in
  `description` is annotated as `present_supported` even when the narrower
  wired field is null (documented fact: all 30 retained records have
  `compensation_text == null`; an offline scan found dollar-figure salary
  evidence in `description` for 24/30). The **actual parser invocation is
  unchanged** -- `classify_salary`/`classify_location` still receive only
  `compensation_text`/`location_raw`, and nothing extracts or backfills
  either field. `evaluate_phase3_corpus.py` gained a new
  `ParserComponentMetrics.provider_mapping_gap` counter: a
  `present_supported` case now first splits on whether the parser's actual
  wired input was present at all; if not, it is counted only as
  `provider_mapping_gap` (with its own `MismatchDetail` category) and is
  **never** folded into `supported_correctness`/`supported_abstention`/
  `confidently_wrong`, which continue to mean "wired input was present."
  The rubric states plainly that this corpus can measure today's end-to-end
  salary gap but not salary-parser correctness on realistic non-null
  inputs without a separately reviewed extraction/mapping slice.
- **F8 (domain table substituted schema types for semantics)**: added
  closed decision tables to the rubric: a numeric range table for
  `experience.min/max`/`salary.min/max` (single value, closed range,
  open-ended lower/upper bound, fractional-value unsupported-form, and the
  "range plus a preferred figure" non-ambiguity case); a currency
  normalization table (ISO 4217 codes, ambiguous-bare-symbol handling); and
  a location table (verbatim copy, no abbreviation-expansion/contraction,
  multiple-location/conflict handling). `salary.period`'s canonical domain
  is now closed to exactly `hourly`/`daily`/`monthly`/`annual`, matching
  `docs/DATA_MODEL.md`'s `salary_period` enum -- the one composite
  sub-field the project already documents a closed domain for; currency/
  location sub-fields have no project-documented enum and stay free text,
  stated explicitly rather than left ambiguous. Code: `evaluate_phase3_
  corpus.EXPECTED_VALUE_VALIDATORS["salary.period"]` changed from
  `_is_non_empty_str` to the closed-set check (no other validator changed).
- **F9 (no target-role relevance rule)**: added a "Role-relevance filter"
  section, applied before any outcome is chosen for any field: a mention
  only counts if it asserts something about the advertised role or its
  candidate requirements, never an unrelated person/reporting line,
  customer/team description, generic benefits boilerplate, company/product
  description, or passing example. Five synthetic examples included (a
  benefits-boilerplate `employment_type` non-assertion, a "reports to"
  non-assertion for `seniority`, a "leads senior/intermediate engineers"
  non-assertion about the candidate's *own* level, a company-language
  `skills` non-assertion, and a positive-control genuine requirement).
- **F10 (real record id/example contaminated blindness)**: the compact
  schema example's record id `gitlab:8396674002` (a real batch identifier)
  and its speculative seniority label are replaced with a wholly synthetic
  id (`examplecorp:0000000001`) and synthetic labels with no correspondence
  to any real record's actual content; the rubric now states explicitly
  that no example may pre-label or quote any of the 30 real evaluation
  records.
- Because the rubric changed again before any annotation exists,
  `RUBRIC_VERSION` bumped `1.0.1 -> 1.0.2`. **Historical, superseded
  evidence** (neither ever annotated against), both now recorded in the
  rubric's own superseded-evidence table: `1.0.0` (rubric sha256
  `bb4c8ac44ccb7bf6c0978d36bb4350449076df032e337ef6a8b03a651ee2ade0`,
  `source_packet_hash 867e5b6d30a4fc858de3146122437ca03a936936c8f88ddc034
  8ab5dedb92957`, commit `7644e20`) and `1.0.1` (rubric sha256
  `47f833d80eb37c8046fc6b243e53fbeaa4cdab78c6b71a52748ecb42e7106f2c`,
  `source_packet_hash 914ebc5700a4baf9f7b15d25e109ea86d647ef9c8d5bd2fb8e04c
  db608299651`, commit `64dd730`). **Current**: rubric sha256
  `736d53bb7da78cd558fb6f7cab1c18fc991940416e059f5e60cc3b92e19ea0f9`,
  `source_packet_hash 08409a3e57dccf84c34127675078106d6c510ff71813860fb23b
  69fd26bed55a` (taxonomy/salvage hashes unchanged).
- Verification: `ruff format --check`/`ruff check` clean on all five
  touched files; `mypy` clean on both scripts; full backend suite **3114
  passed** (was 3107; +7 = 6 new evaluator tests (2 F8 domain, 3 F7
  unit/composite, 1 F7 end-to-end via real classifiers) + 1 new freeze-
  builder F8 pass-loading test); `check_repo.py` clean; `git diff --check`
  clean.
- Adversarial self-review: confirmed `provider_mapping_gap`'s denominator
  is every `present_supported` case for that component (not just the
  gapped ones), so the rendered ratio is a genuine "N of M present_supported
  cases had no wired input" signal, not a bare count; confirmed the
  `supported_abstention`/`confidently_wrong`/`supported_correctness`/
  `provenance_correctness` block is skipped **entirely** (not scored as 0)
  when the wired input is absent, so it renders `N/A` rather than a
  misleadingly clean "0/0"-shaped result; confirmed `experience`'s call
  site was deliberately left at the `wired_input_present=True` default
  (title+description is already the full pooled ground-truth input for
  that parser, so no analogous gap concept applies there); confirmed the
  end-to-end F7 test exercises the real `classify_salary` via
  `evaluate_corpus`, not a mock, against a `compensation_text=None` record
  matching this batch's actual, confirmed (30/30) condition; confirmed
  `location`'s parallel `wired_input_present` wiring is real but
  currently inert in this batch specifically because `location_raw` is
  null in 0/30 real records (checked directly against the salvage file),
  stated as such rather than left to be discovered later.
- Files changed: `docs/evaluation/phase3-realistic-annotation-rubric.md`
  (F1 continuation + F7/F8/F9/F10, `rubric_version` bump), `backend/
  scripts/evaluate_phase3_corpus.py` (`provider_mapping_gap` metric,
  `salary.period` closed-set validator, docstring), `backend/tests/
  test_evaluate_phase3_corpus.py` (64 -> 70 tests), `backend/scripts/
  freeze_phase3_realistic_corpus.py` (`RUBRIC_VERSION` bump only),
  `backend/tests/test_freeze_phase3_realistic_corpus.py` (41 -> 42 tests),
  `docs/LLM_HANDOFF.md` (this entry, plus the iteration rotation above).
- STOP -- this remains a checkpoint within an incomplete slice, not a
  candidate. No annotation pass, adjudication, corpus freeze, baseline
  evaluation, provider contact, database work, parser change, title
  normalization, `R`, merge, `M`, or `Q` is authorized by this commit.
  Waiting for Sol's re-review of the twice-corrected Stage 1 checkpoint.

---

## Iteration 2

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
