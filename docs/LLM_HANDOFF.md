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

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/remote-classifier` for the three findings from the
  original implementation's review (that original implementation and its
  review are now rotated out of this ledger per the two-iteration rule;
  both remain in Git history at commit `cba5b14` and its review commit).
  Base: `cba5b14` plus the uncommitted review. Preserved:
  `NormalizationResult`/`Provenance`, the public
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

### Work review

- Date/reviewer: 2026-09-06, Codex.
- Diff reviewed: `cba5b14..21f55ae` on `phase-3/remote-classifier`.
- Verdict: **Changes requested.** The prior negation defect is fixed, the
  import-boundary check is now fail-closed, and ROADMAP correctly records Phase 2
  completion. The High semantic finding is only partially closed: the implementation
  still treats bare `remote`/`hybrid`/`in person` tokens in descriptions as affirmative
  work-arrangement evidence and attempts to enumerate nearby counterexamples.
- Independent verification: inspected the five-file correction diff; reran both
  targeted modules (**59 passed**) and the canonical routine verifier (**all 9 checks
  PASS, 1554 full-suite tests**). Replayed all seven originally reported strings and
  confirmed they now return unavailable. Then exercised nearby ordinary constructions
  not present in the expanded corpus.
- Finding:
  1. **High — the description path remains fail-open for unenumerated non-arrangement
     uses of the same generic words.** The committed implementation returns
     `remote/PARSED_DESCRIPTION` for `Serve remote customers across several regions`,
     `Monitor and maintain remote servers around the clock`, and `Travel regularly to
     remote sites in northern Alaska`; `hybrid/PARSED_DESCRIPTION` for `Design and
     operate hybrid databases for enterprise clients`; and
     `onsite/PARSED_DESCRIPTION` for `Conduct in-person demonstrations for prospective
     clients`. The title path likewise returns `remote/INFERRED` for `Remote Systems
     Administrator` and `Remote Team Manager`, both ambiguous domain/subject titles.
     Adding `team/system/device/interview/meeting` cues closed the cited examples but
     not the unsafe rule that produced them. This contradicts the requested boundary
     that description evidence express the position's arrangement and the Phase 3 rule
     to prefer unknown over a false fact.
- Exact requested correction: use separate, explicit positive catalogs for title and
  description. In descriptions, accept only arrangement-bearing phrases (for example
  remote/hybrid/onsite role, position, job, work arrangement or schedule; work
  remotely/from home/from anywhere; onsite attendance or work in office), rather than
  accepting a bare generic token and trying to enumerate every non-arrangement noun.
  Retain context/exclusion cues as defense in depth, not as the primary semantic gate.
  A bare candidate may survive only under a separately tested, structurally explicit
  contrast rule needed for cases such as `Not remote, onsite`; do not weaken that
  accepted behavior. Add the seven newly reproduced strings above as unavailable
  regressions and positive controls for every retained description phrase. Add title
  domain exclusions sufficient for the two reproduced ambiguous titles while
  preserving `Software Engineer (Remote)` and other explicit title markers. Update the
  module contract and handoff claims accordingly. Preserve the completed negation,
  import-boundary, provenance, ROADMAP, pure/offline, and public-signature fixes. Run
  targeted and canonical verification and adversarially test unseen remote/hybrid/
  in-person subject-matter phrases. Do not merge or begin another parser pending
  re-review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/remote-classifier` for the one remaining High finding
  from Iteration 1's `Work review` above. Base: commit `21f55ae` plus the
  uncommitted review. Preserved: `NormalizationResult`/`Provenance`, the
  public signature, the pure/offline boundary, unsupported-phrase
  behavior, the completed negation/import-boundary/ROADMAP fixes, and
  every previously-passing safety case (all reconfirmed, including
  `"Not remote, onsite." -> onsite` and `"Software Engineer (Remote)" ->
  remote`). No ingestion/persistence/providers/models/migration or other
  parser touched.
- Outcome — replaced the bare-token-plus-deny-list design with genuinely
  separate positive catalogs per field:
  - **`title`** keeps the bare marker catalog unchanged (`_BARE_TOKEN_
    PHRASES`) — a bare marker in a title already describes the position,
    by construction. Two new exclusion phrases, `"remote systems"` and
    `"remote team"`, close the two reproduced ambiguous titles.
  - **`description`** now matches only **arrangement-bearing phrases**
    (`_DESCRIPTION_POSITIVE_PHRASES`): `remote`/`hybrid`/`onsite`
    (`onsite` also as `"on site"`) combined with one of `role`,
    `position`, `job`, `work arrangement`, `schedule`, `attendance`,
    `attendance requirement`, plus the self-sufficient `"work remotely"`,
    `"work from home"`, `"work from anywhere"`, `"wfh"`, `"work in the
    office"`. A bare `remote`/`hybrid`/`onsite`/`"in person"` token with no
    arrangement noun nearby now contributes **nothing** — this closes the
    root cause, not just the five reproduced strings (confirmed by
    adversarial testing with ten entirely unseen subject-matter sentences
    below, none of which needed a new exclusion).
  - **Narrow comma-contrast exception**, added specifically to preserve
    `"Not remote, onsite." -> onsite` without globally allowing bare
    description tokens: a bare candidate counts as signal only if it sits
    immediately after (zero-token gap — comma-adjacent) another candidate
    that negation suppressed in the same sentence. Implemented as
    `_is_comma_contrast()`, called only from the new
    `_extract_description_signal()`; `_extract_title_signal()` is
    unaffected (title never needed this exception).
  - Existing negation/coordination/unresolved-negation/exclusion/context-
    cue mechanics from Iteration 1 are unchanged in mechanism, just now
    operate over two field-specific candidate pools (`qualified` and
    `bare`) instead of one shared pool, with context/exclusion cues kept
    explicitly as defense in depth, not the primary gate, per the review's
    instruction.
  - Module docstring rewritten top-to-bottom to describe the actual
    field-specific positive-evidence contract, replacing every reference
    to the old shared bare-token design.
- New/changed fixture cases (corpus now 55 total, +14 net): the seven
  reproduced strings verbatim (five description, two title —
  `title_remote_systems_administrator_exclusion`,
  `title_remote_team_manager_exclusion`,
  `description_only_remote_customers_not_arrangement`,
  `description_only_remote_servers_not_arrangement`,
  `description_only_remote_sites_not_arrangement`,
  `description_only_hybrid_databases_not_arrangement`,
  `description_only_in_person_demonstrations_not_arrangement`), 12
  positive controls covering every retained arrangement noun and every
  self-sufficient phrase, and reworded (not removed) five existing cases
  whose description text used a bare catalog phrase with no arrangement
  noun, to keep testing the same original invariant under the new
  contract (`conflicting_title_vs_description`, `two_classes_one_field_
  conflict`, `negated_remote_then_explicit_onsite`, `sentence_boundary_
  prevents_cross_sentence_phrase_match`, and `negation_coordination_
  propagates_independent_of_other_protections` — the last of these was
  specifically rewritten from a bare-vs-bare sentence, which the new bare-
  token gate alone already resolved without coordination, to a
  qualified-vs-qualified sentence that genuinely isolates or/nor
  propagation as the only reason both candidates are suppressed).
- Files changed: `backend/app/normalization/remote.py` (positive-catalog
  redesign, new exclusions, comma-contrast rule, docstring), `backend/
  tests/fixtures/normalization/remote_type_cases.json` (7 new regressions,
  12 new positive controls, 5 reworded), this handoff entry. `app/
  normalization/types.py`, `test_normalization_types.py`, `test_
  normalization_remote.py`, and `docs/ROADMAP.md` untouched — no finding
  required changing them this round.
- Verification: the two targeted modules directly (**77 passed**, was 59);
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **9 steps PASS**, **1572 full-suite tests** (was 1554; +18),
  ~108-128s across reruns. `ruff format --check`/`ruff check`/`mypy` all
  pass. `check_repo.py` and `git diff --check` both pass as part of the
  verifier. No database/migration/schema touched.
- Adversarial self-review (abbreviated, proportionate to Class R): first,
  probed **ten entirely unseen** subject-matter sentences not present in
  any fixture, per the user's explicit instruction (remote customers,
  remote servers, remote client sites, hybrid cloud technologies, hybrid
  networking equipment, in-person onboarding events, in-person strategy
  meetings, remote monitoring equipment, remote vendors, in-person client
  workshops) — **all ten correctly returned `unavailable`**, with zero new
  exclusion phrases needed, confirming the fix generalizes rather than
  just covering the reproduced examples. Separately probed three unseen
  ambiguous titles (`"Remote Infrastructure Engineer"`, `"Remote Client
  Success Manager"`, `"Hybrid Network Specialist"`) — **all three still
  leak a false positive**, an honestly-discovered, narrower limitation of
  title's still-enumerated exclusion design (which the review's own
  guidance sanctions as acceptable — "title markers may remain narrowly
  supported with domain exclusions"); documented explicitly in the module
  docstring rather than silently left implicit, not fixed in this pass.
  Then four targeted breaks against the new mechanisms, each reverted
  cleanly (`git diff --stat` empty afterward): (1) disabled the positive-
  catalog gate entirely (every candidate counts, qualified or not) —
  exactly the five reproduced description regressions failed, each
  leaking its bare-token value again; (2) disabled `_is_comma_contrast`
  (forced `False`) — both comma-contrast-dependent cases failed, `"Not
  remote, onsite."` incorrectly became `unavailable`; (3) removed the two
  new title exclusion phrases — both reproduced title regressions failed,
  each leaking `remote`; (4) disabled or/nor coordination propagation in
  `_extract_description_signal` — exactly the reworded qualified-vs-
  qualified isolation case failed, leaking `hybrid`, while the other two
  coordination-adjacent cases were correctly unaffected.
- Deviations/known limitations: the pre-existing `alembic check`
  substitution (unrelated, not applicable). The negation-window and dual-
  unconnected-negator limitations from Iteration 1, unchanged. **New**:
  title's exclusion-list approach does not generalize to arbitrary
  ambiguous domain/subject titles beyond the two reproduced strings (see
  adversarial self-review above and the module docstring) — an accepted,
  documented limitation of the "narrow exclusions" design the review
  itself sanctioned for `title`, not silently discovered-and-hidden.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.
