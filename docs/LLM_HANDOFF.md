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

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R implementation
  of the approved Phase 3 remote-classifier proposal (v3 plus its binding
  implementation clarifications) on `phase-3/remote-classifier`, based on
  clean `main@199eb00`. This is the first Phase 3 parser slice — a bounded,
  pure-function proof of the parser pattern the remaining seven required
  parsers (title, salary, location, employment, seniority, experience,
  skill) will each follow in their own future slices. Not wired into
  ingestion/persistence, no `parser_version` threading, no `field_provenance`
  write, no other parser touched.
- Outcome:
  - **`app/normalization/types.py`** (new) — `Provenance` (`StrEnum`, the
    six-value docs/DATA_MODEL.md vocabulary exactly) and
    `NormalizationResult[T]` (frozen dataclass: one atomic `value`/
    `provenance` pair). `__post_init__` checks, in order: (1)
    `isinstance(provenance, Provenance)` — rejecting a raw string or
    unknown value with a fixed, categorical `ValueError` containing no
    interpolated runtime content, checked first specifically because a raw
    string sharing a real member's text (e.g. literal `"unavailable"`)
    would otherwise silently satisfy the invariant below without being a
    real member; (2) `value is None` iff `provenance is
    Provenance.UNAVAILABLE`, its own separate fixed categorical message.
    Documented as deliberately narrow to one atomic value — a future
    composite parser (salary, location) composes several independent
    `NormalizationResult`s or defines its own structured per-field result,
    never one shared provenance tag across sub-fields.
  - **`app/normalization/remote.py`** (new) — `classify_remote_type(title,
    description) -> NormalizationResult[Literal["remote","hybrid","onsite"]]`.
    Pipeline: NFKC-normalize, fold curly apostrophes to straight, case-fold;
    split into sentences on `. ; : ! ?`; tokenize each sentence on
    whitespace/`,()[]{}"/&-`/en-em-dash (apostrophe deliberately excluded,
    so contractions survive as one token; zero-width/format characters
    never stripped and never a boundary, so an obfuscated keyword fails
    closed rather than matching); catalog phrases compiled through the
    identical pipeline (`_compile_phrase`), never a hand-written parallel
    regex. Exclusion-span masking removes every token of a matched
    exclusion phrase (e.g. "remote sensing") from all later consideration,
    including the embedded "remote" token itself. Negation suppresses only
    the *nearest* candidate(s) to a cue within a 3-token same-sentence
    window (a tie suppresses both, never neither; a cue never suppresses
    every candidate in its window). Context-exclusion cues (e.g. "stipend")
    suppress *every* candidate in their own 3-token window. Cross-field
    precedence: any conflict anywhere (within one field or between fields)
    -> `(None, UNAVAILABLE)`; title-only -> `INFERRED`; description-only ->
    `PARSED_DESCRIPTION`; agreement -> `PARSED_DESCRIPTION`; no signal
    anywhere -> `(None, UNAVAILABLE)`. Catalogs are deliberately minimal and
    exhaustive for this slice (5 remote / 1 hybrid / 4 onsite phrases, 3
    exclusion phrases, 5 context cues, 6 negation cues) — an unsupported
    phrase (e.g. "telecommute") returns no signal, never a guess.
  - **`backend/tests/fixtures/normalization/remote_type_cases.json`** (new,
    27 cases) — every case labeled `synthetic_representative` or
    `synthetic_adversarial`; none claim `sanitized_capture`, since no real
    captured project text exists yet for this parser. Covers the full v3
    matrix plus every binding-clarification proof case: negation
    nearest-only (`"Not remote, onsite."` -> `onsite`), negation tie-break
    (`"Remote not onsite."` -> `unavailable`), straight- and
    curly-apostrophe contractions, the 3-token context-exclusion window,
    sentence-boundary-blocks-phrase-match, and the unsupported-phrase case.
  - **`backend/tests/test_normalization_types.py`** (new, 13 tests) —
    table-driven valid/invalid `(value, provenance)` pairs, including the
    present-value-with-raw-string case that would otherwise silently bypass
    the None invariant, each asserting the exact fixed error message.
  - **`backend/tests/test_normalization_remote.py`** (new, 30 tests) —
    corpus-driven (table-first, one parametrized test over the JSON file),
    plus an origin-honesty check, a determinism check (identical input ->
    bit-for-bit identical result twice — idempotence narrowed to this claim
    only, not "output fed back in as title is stable", which would not be a
    meaningful invariant for a free-text-in/enum-out function), and an
    AST-based import-boundary test proving neither new module imports
    `app.providers`/`app.db`/`app.ingestion`/`app.services`/`app.api`/
    `sqlalchemy`/`asyncpg`/`alembic`/`httpx`/`fastapi`.
  - **`docs/ARCHITECTURE.md`** §4 — added `remote.py`/`types.py` to the
    `normalization/` diagram (previously missing `remote.py` despite
    `remote_type` being a required Phase 3 parser and schema column).
    **`docs/ROADMAP.md`** — states the first Phase 3 slice is implemented
    on this branch, explicitly not a Phase 3 completion claim; the other
    seven parsers remain unstarted.
- Files changed: exactly the six files above plus this handoff entry. No
  `db/models/`, `ingestion/`, `providers/`, `services/`, `api/`, or
  migration file touched.
- A real bug was found and fixed during testing, before any commit: the
  initial context-exclusion cue list included the word "software", which
  incorrectly suppressed the "remote" signal in the extremely common title
  "Software Engineer (Remote)" — caught by the corpus's own
  `positive_punctuation_heavy`/`positive_unicode_fullwidth` cases failing.
  Narrowed the cue list to `stipend`/`collaboration`/`vpn`/`protocol`/
  `allowance` — words unambiguous in this context, rejecting
  `tool`/`tools`/`software`/`equipment`/`access` as too generic and
  title-collision-prone.
- Verification: `ruff format --check`, `ruff check`, `mypy` all pass on the
  four new files; the two targeted test modules directly (**43 passed**);
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **9 steps PASS**, **1538 full-suite tests** (was 1495; +43),
  temp-directory cleanup, ~100-107s across reruns. `check_repo.py` and
  `git diff --check` both exit 0 standalone. No database/migration/schema
  touched by this slice at all (pure Python, no `--focus` needed since
  nothing here exercises PostgreSQL).
- Adversarial self-review (abbreviated, proportionate to Class R): four
  targeted breaks, each reverted cleanly (`git diff --stat` empty
  afterward) and each proven to fail the specific test(s) designed to
  catch it. (1) Disabled exclusion-span masking — the three
  `false_positive_remote_*` cases failed, each leaking an unmasked
  "remote" instead of `None`. (2) Reverted negation from
  nearest-candidate-only to suppress-every-candidate-in-window — exactly
  `negation_nearest_only_comma_onsite` failed (`"Not remote, onsite."`
  incorrectly became `unavailable` instead of `onsite`), while the other
  two negation cases were unaffected (correctly, since neither
  distinguishes the two behaviors). (3) Removed the `isinstance(provenance,
  Provenance)` guard — all three `test_non_enum_provenance_...` cases
  failed; critically, `NormalizationResult(value="remote",
  provenance="inferred")` (a raw string) then constructed with **no error
  at all**, proving this is exactly the invariant-bypass the guard exists
  to prevent. (4) Disabled sentence-splitting and additionally treated `.`
  as an ordinary token boundary (simulating a period treated as just
  another separator) — `sentence_boundary_prevents_cross_sentence_phrase_
  match` failed, with "on"/"site" now incorrectly combining across the
  removed boundary into a spurious "onsite" match that conflicted with the
  later "remote", producing `unavailable` instead of the expected clean
  `remote`.
- Deviations/known limitations: the pre-existing `alembic check`
  substitution (unrelated, recorded previously, and not applicable here
  since no schema/migration was touched). The documented, accepted
  negation-window limitation (a negator more than 3 tokens from its target
  is not recognized) — stated in `remote.py`'s own module docstring, not
  silently handled.
- STOP — awaiting Codex review. Do not merge, begin another Phase 3 parser,
  wire into ingestion/persistence, contact providers, or create a migration.

### Work review

- Date/reviewer: 2026-09-06, Codex.
- Diff reviewed: `199eb00..cba5b14` on `phase-3/remote-classifier`.
- Verdict: **Changes requested.** The shared result/provenance type, deterministic
  mechanics, fixture harness, and implementation boundaries are sound, and all
  authored tests pass. The classifier nevertheless emits confident structured facts
  for several common phrases that do not state the job's work arrangement—the exact
  primary risk named by the Phase 3 checklist.
- Independent verification: inspected all eight changed files; ran both targeted
  modules (**43 passed**) and the canonical routine verifier (**all 9 checks PASS,
  1538 full-suite tests**). Directly exercised additional realistic negative cases
  against the committed implementation.
- Findings:
  1. **High — generic tokens are treated as work-arrangement evidence without
     sufficient field/context qualification, and negation can fail open.** The
     committed classifier returns `hybrid/PARSED_DESCRIPTION` for `Hybrid Cloud
     Engineer` / `Build hybrid cloud infrastructure`, `remote/PARSED_DESCRIPTION`
     for `Manage remote teams across several regions` and `Troubleshoot remote
     systems and devices`, and `onsite/PARSED_DESCRIPTION` for `Candidates must
     attend an in-person interview` and `Attend quarterly in-person meetings`.
     It also returns `remote/PARSED_DESCRIPTION` for `This is not, under any
     circumstances, a remote position` and `hybrid/PARSED_DESCRIPTION` for `This
     position is not remote or hybrid`. These are false facts, not merely missed
     detections. The module docstring calls the long-negation behavior "fail-closed"
     even though it preserves the positive match and therefore fails open. Replace
     the shared bare-token treatment with conservative field-aware evidence rules:
     title markers may remain narrowly supported with domain exclusions, while
     description matches must express an arrangement (for example, remote/hybrid/
     onsite role, position, schedule, attendance, or work), not merely mention a
     remote team/system, hybrid technology, or an in-person event. Add domain/event
     exclusions as needed. An unmatched negation cue in a sentence containing a
     candidate must make that field unavailable rather than leave the candidate
     positive; propagate negation across directly coordinated `or`/`nor` alternatives
     so `not remote or hybrid` cannot produce `hybrid`. Preserve the already-correct
     `not remote, onsite` behavior. Add all seven reproduced strings above as
     regressions, plus title-only `Hybrid Cloud Engineer` and a positive control for
     every retained arrangement phrase.
  2. **Medium — the AST import-boundary test is a deny-list while claiming to prove
     the complete no-network/no-layer dependency boundary.** It would accept imports
     such as `requests`, `aiohttp`, `urllib.request`, `socket`, or any newly introduced
     client not named in `_DISALLOWED_IMPORT_PREFIXES`. Use a fail-closed allow-list
     for these two modules' exact permitted imports (standard-library modules actually
     required plus `app.normalization.types` for `remote.py`), and add a synthetic AST
     regression proving an unrecognized import is rejected.
  3. **Low — ROADMAP's adjacent Phase 2 status remains stale.** The edited status
     section still calls `phase-2/closure` a pending closure candidate even though
     it was approved, merged at `d4bd606`, recorded at `199eb00`, and Phase 2 is
     officially complete. Correct that historical status while retaining the accurate
     statement that this Phase 3 branch is pending review and Phase 3 is incomplete.
- Exact requested correction: address only the classifier semantics/docstring,
  regression corpus/tests, fail-closed import-boundary test, ROADMAP status, and this
  handoff ledger. Preserve `NormalizationResult`/`Provenance`, public signature,
  offline/pure boundary, exhaustive-catalog discipline, no-persistence scope, and all
  previously passing safety cases. Run the targeted modules and canonical verifier;
  in the adversarial self-review explicitly replay every reproduced false-positive and
  temporarily break the new field/context and unresolved-negation protections. Do not
  merge or start another parser pending re-review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/remote-classifier` for the three findings from Iteration
  1's `Work review` above. Base: commit `cba5b14` plus the uncommitted
  review. Preserved: `NormalizationResult`/`Provenance`, the public
  `classify_remote_type(title, description)` signature, the pure/offline
  boundary, unsupported-phrase behavior, and every previously-passing
  safety case (all reconfirmed still passing, unchanged expected values).
  No ingestion/persistence/providers/models/migration or other parser
  touched.
- Outcome, addressing each finding exactly:
  1. **Generic tokens treated as evidence without context; negation could
     fail open.** Resolved via three additions, all scoped to
     `remote.py`, without a broad "positive arrangement requirement" that
     would have (and, in an earlier draft, did) broken the already-correct
     `"Not remote, onsite."` case:
     - New exclusion phrase `"hybrid cloud"` (masked in both fields) —
       closes the `Hybrid Cloud Engineer`/`Build hybrid cloud
       infrastructure` false positives, including the title-only case,
       which the description-only mechanisms below cannot reach.
     - New **description-only** context-cue set (`team`/`teams`/
       `system`/`systems`/`device`/`devices`/`interview`/`meeting`/
       `meetings`), applied only when processing `description`, never
       `title` — closes `Manage remote teams...`, `Troubleshoot remote
       systems and devices`, `...an in-person interview`, and `...quarterly
       in-person meetings` by suppressing the nearby positive match, the
       same 3-token-window mechanism the existing universal context cues
       already used, just field-scoped. `title` keeps only the universal
       cues and exclusion phrases, per the review's own distinction
       ("title markers may remain narrowly supported with domain
       exclusions, while description matches must express an
       arrangement").
     - **Negation coordination + unresolved-negation poisoning**: negation
       suppression now propagates transitively to any candidate directly
       coordinated with an already-suppressed one via exactly one
       `"or"`/`"nor"` token between their spans (never a bare
       comma-adjacent gap — verified this distinction explicitly, see
       below) — closes `This position is not remote or hybrid`. Separately,
       if a negation cue is present in a sentence containing a candidate
       anywhere, but its own nearest-candidate search finds nothing within
       its 3-token window (an "unresolved" negator), that sentence's
       candidates are now discarded entirely rather than left positive —
       closes `This is not, under any circumstances, a remote position`
       (previously a documented "accepted limitation"; now genuinely
       fixed, not merely relabeled).
     - Module docstring corrected: the old "fail-closed" claim for
       long-distance negation (which actually preserved a positive match)
       is removed; the new unresolved-negation-poisoning behavior is
       documented as what it actually is.
  2. **AST deny-list, not fail-closed.** Replaced `_DISALLOWED_IMPORT_
     PREFIXES` with an exact `_ALLOWED_IMPORTS` dict (one entry per file,
     naming every import actually present — stdlib only, plus
     `app.normalization.types` for `remote.py`); anything not explicitly
     listed now fails. Added
     `test_import_boundary_rejects_unrecognized_import`, a synthetic
     regression parsing a fabricated `"import requests"` snippet (not a
     real file) and asserting it is correctly rejected by the same
     allow-list check — proving the mechanism itself is fail-closed, not
     only that the two real files happen to pass it today.
  3. **ROADMAP's stale Phase 2 status.** The `phase-2/closure` paragraph
     now states it was approved, merged at `d4bd606`, recorded at
     `199eb00`, and that Phase 2 is officially complete — replacing the
     old "pending Codex's independent exit-gate review" wording. The
     adjacent Phase 3 paragraph (already accurate — first slice
     implemented, pending review, not complete) is untouched.
- New/changed fixture cases (14 added to the corpus, now 41 total): the
  seven reproduced strings verbatim (`hybrid_cloud_title_and_description_
  exclusion`, `hybrid_cloud_title_only_exclusion`, `description_only_
  remote_team_mention_not_arrangement`, `description_only_remote_systems_
  mention_not_arrangement`, `description_only_in_person_interview_event_
  not_arrangement`, `description_only_in_person_meetings_event_not_
  arrangement`, `unresolved_long_distance_negation_forces_unavailable`,
  `negation_coordinated_or_alternative_forces_unavailable`), one extra
  coordination case isolating the or/nor mechanism from every other
  protection (`negation_coordination_propagates_independent_of_other_
  protections`), an explicit duplicate recording that comma-adjacency
  must never coordinate (`negation_preserves_uncoordinated_alternative`),
  and four positive controls (`positive_control_work_from_home`,
  `positive_control_wfh`, `positive_control_in_office`,
  `positive_control_onsite_bare`) covering every retained catalog phrase
  not already exercised elsewhere.
- Files changed: `backend/app/normalization/remote.py` (all corrections;
  docstring rewritten to match), `backend/tests/test_normalization_
  remote.py` (allow-list import-boundary tests replacing the deny-list
  test), `backend/tests/fixtures/normalization/remote_type_cases.json`
  (14 new cases), `docs/ROADMAP.md` (Phase 2 status correction), this
  handoff entry. `app/normalization/types.py` and `test_normalization_
  types.py` untouched — no finding required changing them.
- Verification: the two targeted modules directly (**59 passed**, was 43);
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **9 steps PASS**, **1554 full-suite tests** (was 1538; +16, i.e. +14
  corpus cases and +2 import-boundary tests replacing the 1 old deny-list
  test), ~120-126s across reruns. `ruff format --check`, `ruff check`, and
  `mypy` all pass on the changed files individually before the full run.
  `check_repo.py` and `git diff --check` both pass as part of the
  verifier. No database/migration/schema touched.
- Adversarial self-review (abbreviated, proportionate to Class R): replayed
  all seven reproduced false-positive strings against the corrected
  implementation (all now `unavailable`, confirmed via the passing corpus
  tests above), then four targeted breaks against the new protections,
  each reverted cleanly (`git diff --stat` empty afterward). (1) Disabled
  the description-only context cues — exactly the four non-hybrid-cloud
  reproduction cases failed, each leaking its false-positive value again.
  (2) Removed `"hybrid cloud"` from the exclusion phrases — both
  hybrid-cloud cases (title+description, and title-only) failed, leaking
  `hybrid`. (3) Disabled unresolved-negation poisoning — exactly the
  long-distance-negation case failed, leaking `remote`. (4) Disabled
  or/nor coordination propagation — both coordination-dependent cases
  failed, leaking `hybrid`, while `negation_preserves_uncoordinated_
  alternative` (`"Not remote, onsite."`) **still passed** even with
  coordination disabled — direct proof that the comma-adjacent case never
  relied on coordination, and that the two mechanisms are genuinely
  independent as designed.
- Deviations/known limitations: the pre-existing `alembic check`
  substitution (unrelated, recorded previously, not applicable — no
  schema/migration touched). The module docstring's remaining accepted
  limitation (two separate, unconnected negators/candidates coincidentally
  sharing one sentence could still cross-poison) is stated explicitly, not
  silently handled — narrower in scope than the original long-distance
  case, which is now fixed.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.
