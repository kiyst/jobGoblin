# 0008 — Workflow v3.1 pilot retrospective and Workflow v3.2 adoption decision

## Status

Accepted. The retrospective below is a corrected, durable record superseding any prior
conversational summary of the same pilot. The Workflow v3.2 design principles in
"Decision" are accepted in principle. **Activation is explicitly deferred** — see
"Activation boundary." Workflow v3.1 remains the sole active workflow version as of this
ADR.

## Context

Workflow v3.1 was trialed across a three-**parser**-slice measurement window
(`docs/LLM_WORKFLOW.md`'s "Workflow v3.1 pilot" section, itself layered on Workflow v3):
`classify_experience` (merged `6f9ae53`), `classify_salary` (merged, base `b9d7f0c`), and
`classify_location` (merged `a32b5cc`). Per that section, a mandatory retrospective was
required after the third slice's `Work review`, jointly assessing four numerical targets
and deciding, per v3.1 mechanism, whether to keep it, narrow it, or drop it.

An initial retrospective was produced conversationally and found to contain reconstructed
(not evidence-grounded) figures for several counts — notably `classify_experience`'s
proposal-round count and an inconsistent per-slice tally of "confidently-wrong" findings
for `classify_salary`. This ADR is the corrected replacement, grounded only in `git log`/
`git show` on the actual commits and the `docs/LLM_HANDOFF.md` content committed at each
point in history. Where committed evidence does not exist for a figure, that figure is
recorded as **not reconstructible** rather than estimated.

## Retrospective: per-slice findings

### `classify_experience`

- **Proposal-submission count: not reconstructible.** Proposal-only rounds are, by this
  project's own rule, never committed to the repository ("proposal only: do not create a
  branch, modify files, or begin implementation"), so no git evidence distinguishes one
  proposal round from several. Any prior count for this figure was a reconstruction from
  conversation memory, not evidence, and is withdrawn.
- **Six pre-code amendments**, recorded separately from the post-implementation total:
  the implementation commit `e13d8a6` itself states it "Implements Astra's approved-with-
  clarifications proposal, incorporating all six binding amendments" — applicant-
  attribution framing, uniform continuation-boundary negation handling, atomic numeric-
  rejection redaction, positional preference-marker suppression, internal-conflict-before-
  cross-source precedence, and Unicode/hyphen disambiguation. These were folded into the
  first commit and never produced a separate correction commit.
- **Four post-implementation correction rounds**, totaling **exactly 13 findings**:
  - `2589eec` — 7 findings (reversed-label attribution bypass; title preference/negation
    scope; trailing upper-bound markers plus unsupported prefix; Unicode numeric
    expressions; multi-candidate collection per title segment; two fixture-input
    corrections).
  - `2fcdc0f` — 3 findings (title modifier scope/ordering; composite unsupported-numeric
    poisoning generalized; description label:value exemption removed).
  - `1610f57` — 2 findings (empty-segment title-modifier adjacency; negative-composite
    range leak).
  - `559e77a` — 1 finding (composite numeric rejection missing `re.IGNORECASE`, explicitly
    labeled **High** in its own committed `Work done` text).
  - 7 + 3 + 2 + 1 = 13.
- The slice's own merge record (`b9d7f0c`) states in committed text: "It closed after five
  correction rounds (four `AskUserQuestion`-confirmed plus one user-self-authorized), not
  the one-round target; per Astra's review, the mandatory pilot retrospective must count
  this actual round total rather than characterize the slice as meeting that target." That
  "five" counts the pre-code clarification round together with the four post-implementation
  rounds; this ADR reports the two categories separately per the corrected accounting above
  rather than the merged figure.

### `classify_salary`

- **Three documented proposal-review rounds**: the implementation commit `3c02fac` and its
  own `Work done` entry state "the round-4-approved `classify_salary` proposal (three
  proposal-review rounds preceded implementation)."
- **One executable correction round** (`261ffe3`), addressing **five executable
  grammar-boundary mechanisms**, their accompanying regression fixtures, and **one
  documentation-attribution correction**: unrestricted `\s` replaced with a
  covered-whitespace class; label-boundary strictness; currency-code boundary strictness;
  period-boundary strictness split by shape; `up...to` narrowed to exactly two forms —
  each backed by new regression fixtures — plus a documentation-attribution correction
  (this slice was never in Astra's review queue — a copy-paste artifact from the merged
  `classify_experience` precedent, corrected here as a non-behavioral fix). This ADR no
  longer describes these as "seven boundary findings"; that framing conflated five
  executable mechanisms, their fixtures, and one unrelated documentation fix into a single
  undifferentiated count.
- **Confidently-wrong classification, strict**: a finding counts as confidently wrong only
  where the committed text demonstrates the pre-fix code returned a confident value
  *contradicted by* its own input. The five grammar-boundary mechanisms above demonstrate
  that malformed/glued boundary input (e.g. `"salary120000"`) was wrongly **accepted** by
  the pre-fix grammar — but in each documented case the numeric/currency/period
  information the parser extracted was actually present in the input; the defect is that
  the grammar's boundary was too permissive, not that the extracted value contradicted the
  input. This does not meet the strict confidently-wrong bar. **No salary finding is
  recorded as confidently wrong**, and **no exact count of salary findings under the
  strict definition is reconstructible from durable evidence** — the original review
  request that produced these findings was relayed as text and never committed as its own
  artifact, so the per-finding certainty detail needed to classify each one individually
  cannot be recovered. This ADR does not substitute zero as an exact historical count for
  salary; it records the count as **not reconstructible**, distinct from "zero identified."

### `classify_location`

- **Four documented proposal-review rounds**: the implementation commit `88cdb2f` and its
  own `Work done` entry state "the round-4-approved `classify_location` proposal (four
  proposal-review rounds preceded implementation; no branch/code existed before this
  pass)."
- **One executable correction round** (`071d8dc`), containing **eight validated findings**
  from the blind Sol Medium / Astra Light comparison review of the frozen commit `88cdb2f`.
- **Four committed confidently-wrong cases**, per the correction's own committed text and
  the independent re-review recorded in this branch's prior `Work review` entry:
  1. Negation/exclusion cues in a discarded span (e.g. `"All countries except, Canada"`
     previously extracted `country=Canada`).
  2. Conflicting country tokens silently resolved to the explicit slot instead of rejected
     (e.g. `"Canada, France"`).
  3. Unicode lookalike case-folding (Turkish `İ` previously matched Wisconsin/Indiana).
  4. Malformed state-token punctuation previously accepted as a valid state
     (`"T...X"`/`"TX..."`).
  The remaining four findings (dotted-alias trailing-period rejection, ZIP-implied-country
  provenance mislabeling, region-whitespace-trim false rejection, Oregon-vs-coordinator
  false rejection) are safe-misses or a provenance-label defect, not a wrong extracted
  *value*, and are not counted as confidently-wrong.

## Retrospective: the four numerical v3.1 targets

| Target | Verdict | Basis |
|---|---|---|
| At most one correction round per slice | **Fail** | `classify_experience` alone required four post-implementation correction rounds (13 findings); one violating slice fails the target as written ("a slice needing two or more... counts against the pilot"). Salary and location each needed exactly one. |
| Zero confidently-wrong independent-review findings | **Fail** | Proven without inventing uncertain counts: `classify_experience`'s `559e77a` finding is explicitly documented, in its own committed text, producing a fabricated value; `classify_location`'s four confidently-wrong findings above are independently reproduced and documented. These proven cases alone are sufficient to fail the target independently of salary; salary's boundary-acceptance findings do not meet the strict confidently-wrong bar (see above) and are not used as evidence for this verdict either way. |
| Zero handoff-count defects reaching a merged `Work done` entry undetected | **Pass** | No instance was found, across any of the three slices' committed history, of a fabricated/stale/mismatched count surviving to a merged `Work done` entry. |
| Zero regressions that pass with their required guard disabled | **Pass** | Every fixture flagged non-isolating across all three slices (experience: several per round; salary: 4; location: 2) was explicitly disclosed as such in committed text, was never relied upon as sole proof of its finding, and had a genuinely isolating sibling fixture confirmed by mutation.

## Retrospective: qualitative notes

- **Astra Light vs. Sol Medium** (location's blind review): Astra Light found 2 of the 8
  validated defects (uniquely: ZIP-implied-country provenance); Sol Medium found 7 of the 8
  (all three findings later characterized as High severity), with 1 finding shared. This is
  recorded strictly as a **comparison of those two complete review configurations** as run
  (reviewer identity plus whatever reasoning effort each was actually given) — it is not
  evidence about either underlying model or reasoning-effort level in isolation, since the
  two configurations were not matched for effort.
- **Count-mismatch fault injection already exists.** `backend/tests/test_check_handoff.py`
  already contains dedicated fault-injection coverage for fabricated and mismatched
  `focused_test_count`/`full_suite_count` values (e.g.
  `test_not_run_rejects_a_fabricated_full_suite_count`,
  `test_not_run_rejects_a_fabricated_focused_count`,
  `test_fixture_count_mismatch_is_rejected`,
  `test_normal_run_rejects_mismatched_full_suite_count`,
  `test_normal_run_rejects_mismatched_focused_count`,
  `test_tooling_slice_focus_selector_mismatch_is_also_rejected`). This mechanism's core
  promise has been directly tested since the tooling slice that built it. What did **not**
  happen during the three pilot parser slices is that promise being triggered by an actual
  fabricated count in real use — the only real-world catch observed in this pilot was a
  usage-mismatch (an unfocused `verify.py` invocation against a handoff entry declaring a
  numeric `focused_test_count`), not a fabrication. Both statements are true and distinct;
  neither should be read as the other.

## Decision

The following Workflow v3.2 principles are **accepted in principle** as the direction
future workflow revision should take:

1. **Compact contracts** — one compact contract plus at most one amendment round for every
   novel parser grammar, with further disagreement moving to a decision table rather than a
   third narrative rewrite.
2. **Two-submission parser proposal limit** — no more than two proposal submissions for a
   novel parser grammar before a joint decision table is required.
3. **Sol Medium as mandatory primary reviewer** for executable/parser work, including Class
   H.
4. **Selective Astra escalation** — additional review only for user-authorized phase gates,
   identity/security/concurrency/destructive/live-provider risk, disputed findings, or
   explicitly scheduled equal-effort benchmarks.
5. **Executable parser contracts** — a deterministic, test-side contract framework with
   expected outputs from an independently authored semantic record, never derived from
   production regexes/dispatch.
6. **Mechanism-level mutation evidence** — one isolating mutation witness per distinct
   guard/code path; neighboring controls that merely happen to pass are not evidence.
7. **Fast correction / final approval gates** — a fast gate for bounded corrections (static
   checks, focused fixtures, contract families, affected dependents, relevant mutation
   witnesses) distinct from a final gate that preserves today's full focused-selector-plus-
   full-suite behavior unchanged.
8. **Stable slice/finding IDs** — collision-resistant identifiers (e.g.
   `<date>-<slug>-<base-short-sha>` for slices, `<slice-id>/F001` for findings) that survive
   ledger rotation and paraphrase.
9. **Durable verification evidence** — verification evidence that can authorize reuse must
   be durable (committed) rather than ephemeral/local-only, with content-match validation
   at merge time.
10. **User-only scope and merge authority** — unchanged from v3.1: the user remains sole
    scope, semantic-decision, phase-transition, and merge authority.

## Activation boundary

**Workflow v3.1 remains the sole active workflow version as of this ADR.** No file that
enforces or declares the active workflow version — `CLAUDE.md`, `.claude/hooks/
compact_checkpoint.py`, `backend/scripts/check_handoff.py`, its tests, or any existing
`docs/LLM_HANDOFF.md` entry's `workflow_version` field — is changed by this ADR. The v3.2
principles above are an accepted future direction, not an active requirement: no slice may
be reviewed, corrected, or merged against v3.2 criteria until a separately authorized,
separately gated implementation slice actually activates it.

Two further implementation slices are planned but **not authorized by this ADR**:

- A deterministic parser-contract harness (parser-independent lexical transforms plus
  parser-specific semantic renderers, validated against one representative per distinct
  historical-defect mechanism).
- Fast/final verifier profiles, durable receipt and split `Work done`/`Work review`
  metadata schemas, and the atomic v3.2 activation itself (updating every version-bearing
  consumer listed above together, in one commit set).

Each remains separately gated: proposal, review, and explicit user authorization are
required before implementation begins on either, exactly as for any other slice.

## Unresolved Slice 3 requirements (recorded, not resolved)

The following design questions are recorded here as open items for whichever future slice
implements durable verification receipts. They are **not resolved by this ADR** and must be
answered in that slice's own proposal before implementation:

1. Candidate verification must occur **before** receipt creation — the receipt attests to
   an already-tested state, never a state whose testing it itself triggers.
2. The receipt must attest to an earlier clean candidate **without circularly changing the
   tested tree** — creating the receipt (a new commit) must not alter the content it
   attests to.
3. Receipt-attestation and review commits need an explicit, named allowance for
   documentation-only differences between the attested tree and the tree actually merged,
   so that trivial doc-only commits don't spuriously invalidate reuse.
4. Candidate, reviewed, corrected, approved, and merge-reuse states need a **defined
   metadata state machine** — which transitions are valid, and what invalidates a receipt
   already issued.
5. **No ephemeral receipt may serve as durable merge evidence.** If a durable, committed
   receipt design is rejected at proposal review, merge-time evidence reuse is removed
   entirely and full verification reruns on every merge — ephemeral receipts may still aid
   local diagnostics but never substitute for a rerun.

## Consequences

- Future retrospectives and handoff entries must cite this ADR rather than re-deriving pilot
  figures from conversation memory.
- The v3.1 workflow continues governing all work, including any further Phase 3 parser
  slices, until a separately authorized activation slice changes it.
- The "not reconstructible" figures recorded above (experience's proposal-submission count;
  salary's exact confidently-wrong finding count under the strict definition) must not be
  backfilled with an estimate — including zero — in any future document; if better evidence
  is ever found, it should be added with its source cited, not asserted from memory.
