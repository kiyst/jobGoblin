# Multi-LLM Engineering Workflow v3

Status: active as of 2026-08-30. This is the operating process for Claude Code as the
primary implementer and Codex as the independent reviewer. Product requirements remain
authoritative in the master guide, architecture, data model, roadmap, and accepted ADRs.
The user remains the scope and merge authority. A Workflow v3.1 pilot layer (see "Workflow
v3.1 pilot" below) is being trialed across three parser slices starting with
`classify_experience`; its enabling tooling (metadata validation, `--docs-only`) shipped
2026-09-08 but is not itself one of the three counted slices. It is additive to everything
in this file unless a section says otherwise.

v3 persists, as durable process rather than conversational instruction, the practices
that emerged across Phase 2's identity-resolution slices: a `Definition of Ready` gate
before implementation, three named review verdicts, concise amendment tables in place of
full proposal rewrites for localized feedback, a two-round cap on free-form Class H
revision, an explicit separation of required invariants from recommended mechanisms, and
use of the canonical verifier (`scripts/verify.py`, once its own slice is approved) for
risk-scaled verification. Everything from v2 not superseded below still applies
unchanged.

## Objectives

- Preserve independent implementation and review.
- Ask the user only about genuinely new product or risk decisions.
- Match slice size and verification effort to risk.
- Resolve mechanical documentation defects without an unnecessary extra agent cycle.
- Keep handoffs concise; Git is the durable history and source of truth for diffs.

## Authority and roles

### User

- Approves new product behavior, scope expansions, phase transitions, and merges to
  `main`.
- May transfer implementation ownership between agents at any time.

### Implementer (normally Claude Code)

- Proposes and implements only the authorized slice.
- Owns code, migrations, tests, and product-document updates during implementation and
  correction passes.
- Runs the adversarial self-review below before committing implementation or writing
  `Work done`.
- Records a concise `Work done` entry and stops after pushing the task branch.
- Never edits its own `Work review` or advances automatically to another slice.

### Reviewer (normally Codex)

- Reviews the actual repository, commit range, tests, migrations, and live schema when
  applicable; summaries from the implementer are evidence pointers, not proof.
- Writes the `Work review`, commits it to the task branch, and stops with a verdict.
- Does not modify executable code, migrations, tests, dependencies, product behavior,
  or architecture while reviewing unless the user explicitly transfers ownership.
- May directly correct a **mechanical documentation-only defect** during review under
  the standing rule below.

## Definition of Ready

Before implementation begins on any slice — product or tooling — the proposal must state,
and the user must have approved:

- The bounded outcome: what user-visible or system behavior changes, stated concretely
  enough that "done" is checkable.
- Authorized scope and its exact exclusions — what this slice does **not** do, named
  explicitly so a later reviewer never has to guess whether an omission was deliberate.
- Dependencies and precedence: what existing code/decisions this slice relies on, and
  what later work depends on it.
- Risk class (below) and the verification level that follows from it.
- Exact files expected to change.
- Genuinely unresolved decisions only — established conventions are defaults (see below)
  and are not re-presented as open questions.

A slice is not ready for implementation merely because a proposal exists; it is ready once
the user has approved these specific points, not the proposal's prose in general.

## Review verdicts

Every `Work review` reaches exactly one of three verdicts:

- **Approved** — no findings requiring a change. The implementer performs no further
  action beyond waiting for merge authorization.
- **Approved with binding clarifications** — the reviewer or user identifies small,
  bounded amendments that do not change the slice's fundamental design; the implementer
  applies exactly those clarifications and proceeds directly to implementation without a
  further proposal round. "Binding" means the clarifications are not optional
  suggestions — they are part of what was approved.
- **Redesign required** — the finding(s) touch the slice's fundamental design (precedence,
  invariants, or scope), not a bounded correction. Implementation stops; the next step is
  a revised proposal (see the two-round limit below), not a code change.

A review finding is never itself authorization to implement a fix — the user still
approves which findings to act on, per the existing authorization boundary below.

## Risk classes and slice size

Classify a proposed slice before implementation:

| Class | Typical work | Default slice | Review/verification level |
|---|---|---|---|
| D — documentation | Typo, duplicate row, stale link or reference, non-semantic wording | One small document pass | Diff, searches, links/anchors as relevant; no backend suite unless executable inputs changed |
| R — routine | Repeated established model/service pattern with no novel identity, concurrency, security, or external behavior | One table/service, or at most two tightly coupled items when the same invariant and tests cover both | Targeted checks plus full static checks/test suite; migration checks if schema changes |
| H — high risk | Identity/deduplication, destructive lifecycle, user-state preservation, concurrency, security/privacy, external providers, ingestion, scheduler | One independently testable invariant or vertical slice | Full relevant suite, adversarial/boundary tests, real backing service where required, explicit rollback/failure checks |

When uncertain, use the higher-risk class. A phase boundary never expands authorization.

## Revision discipline for Class H slices

- **Concise amendments, not full rewrites.** When a review's findings are localized
  (an "approved with binding clarifications" verdict, or a bounded correction request),
  the implementer's response is a decision/amendment table addressing exactly those
  findings — corrected pseudocode or wording only where affected — never a full
  regenerated proposal repeating unaffected sections.
- **Two-round limit on free-form revision.** A Class H proposal may go through at most
  two rounds of open-ended, free-form revision (initial proposal, one redesign). If a
  third round is still needed, both sides move to a **joint decision table**: every
  remaining finding listed with an explicit accept/reject/defer decision, rather than
  another open-ended rewrite. This bounds how long a design can stay unsettled.
- **Required invariants vs. recommended mechanisms.** A proposal or review finding should
  state which of its claims is a required invariant (the property that must hold,
  non-negotiable) versus a recommended mechanism (one way to achieve it). A correction
  that satisfies the same invariant through a different mechanism is acceptable without
  re-opening the finding — reviewers evaluate against the invariant, not against whether
  the implementer's mechanism matches the one originally suggested.

## End-to-end flow

1. **Read current authority.** Read this file, `PHASE_RISK_CHECKLIST.md`, the latest
   handoff review, relevant product docs/ADRs, and current Git state.
2. **Propose only new decisions.** The implementer states the bounded outcome, risk
   class, files, acceptance checks, and only unresolved decisions. Established project
   conventions are defaults and are not repeatedly presented as open questions.
3. **Design review before code when needed.** For a new or high-risk pattern, Codex
   reviews the proposal and gives the user one consolidated recommendation and an exact
   authorization prompt. Routine work that merely applies recorded conventions may be
   approved directly by the user.
4. **User authorization.** The user approves the slice and any new semantic decisions.
   A review finding or proposal is not authorization by itself.
5. **Implementation.** Claude creates/uses the task branch, implements only the approved
   slice, runs risk-proportionate verification, performs the adversarial self-review
   below, writes `Work done` (including its self-review section), commits, pushes, and
   stops.
6. **Independent review.** Codex reviews the actual diff and relevant runtime state,
   records findings by severity with precise references, writes `Work review`, commits,
   pushes, and stops.
7. **Disposition.** Use exactly one route:
   - **Approved:** no correction pass; wait for user merge authorization.
   - **Mechanical docs only:** Codex may fix and approve in the same review cycle under
     the rule below.
   - **Executable/product finding:** Claude performs one user-approved bounded
     correction pass; Codex re-reviews only the correction plus affected invariants.
   - **Design conflict:** stop and return one consolidated decision to the user before
     either agent writes implementation changes.
8. **Merge checkpoint.** Only the user authorizes merging to `main`. After merge, verify
   branch/main state and propose—but do not start—the next slice.

## Context compaction and recovery

Claude Code's built-in auto-compaction remains enabled and must not be blocked: its
`PreCompact` hook can run after a context-limit error, where blocking would fail the
current request rather than protect it. The project instead uses three complementary
controls:

1. Root `CLAUDE.md` supplies durable compaction instructions and is re-injected after
   compaction. It tells the summarizer what authorization, invariants, verification, and
   recovery pointers must survive.
2. `.claude/hooks/compact_checkpoint.py` runs before manual or automatic compaction and
   atomically records a credential-free Git recovery snapshot under ignored
   `.claude/runtime/`. A `SessionStart(compact)` hook injects that snapshot after
   compaction. It never stores the transcript, compacted summary, environment variables,
   database URLs, or file contents.
3. Agents recommend proactive `/compact` only at a durable boundary. The optimal moment
   is clean, pushed `main` immediately after the verified merge-record commit and before
   a new slice starts. A clean, pushed feature branch stopped after committed `Work done`
   or `Work review` is recoverable but secondary. Never proactively compact amid
   uncommitted changes, running verification, external/destructive activity, incomplete
   handoff writing, or unresolved corrections.

Claude Code currently exposes automatic threshold compaction and compaction lifecycle
hooks, but no project hook that safely forces `/compact` at an arbitrary semantic
milestone. Do not simulate one by launching a nested Claude process. The safe automation
here is automatic snapshot/recovery around built-in compaction, paired with a manual
`/compact` recommendation at the optimal merge boundary.

## Adversarial implementer self-review

Before committing implementation or writing `Work done`, use a fresh Claude subagent or
context that did not write the implementation, whenever one is available. It inspects
the actual diff without editing first and answers:

1. What assumptions do the implementation and tests share that could both be wrong?
2. Can normalization create a prohibited value after validation?
3. Can whitespace, casing, Unicode, `NULL`, JSON null, or malformed data bypass a
   constraint or identity?
4. Do the ORM, direct-SQL, and database-default paths behave differently?
5. Are mutable collections and separate-session persistence covered?
6. Are all partial-index predicate partitions tested?
7. Is real concurrency required for this invariant?
8. Can a failed test or a committed transaction leak data?
9. Are FK deletion tests isolated?
10. Do the model, migration, live schema, tests, and documentation agree?
11. Did roadmap status, constraint summaries, revision references, or counts go stale?
    - Any test whose name or docstring claims a field is "independent," "unaffected," or
      "never touched" must name the exact field(s) it asserts on, and the test body must
      actually assert on every field named — a claim naming a field the assertions never
      read is itself a finding.
    - Any documentation or docstring claim naming a specific precedent or superlative
      ("first," "only," "no other table") must cite the exact search that was rerun to
      verify it (e.g. "confirmed via grep of `app/db/models/*.py` for `ondelete=
      \"CASCADE\"` + `users`, no other match") — a superlative claim with no cited,
      rerun search is itself a finding, independent of whether the claim happens to be
      true. A generic automated linter for this specific defect class was considered and
      is deliberately not adopted: unlike the timestamp-claim check above (a fixed,
      mechanically checkable pattern), verifying an arbitrary superlative requires
      knowing what structural pattern each individual claim refers to, and a
      keyword-triggered checker risks false positives against indirect/aliased access
      patterns it can't see (e.g. a CASCADE reached through a view, a helper, or a
      renamed import) — exactly the brittle-natural-language-linting failure mode this
      project avoids. This checklist item is the deliberate substitute.
12. Does the design support the next phase's consumer, not merely the current table?

Produce severity-ranked findings with file/line evidence first, before making any edit.
Then, within the authorized scope, correct only substantiated findings, add a
regression test that fails against the pre-fix behavior for each one, and rerun
verification. A "no findings" result must still list the adversarial cases attempted,
not merely assert that none were found.

Scale the depth to the slice's risk class: run the full twelve-question review for
Class H; run a proportionate abbreviated pass (only the questions that actually apply)
for Class R; Class D does not require it. This step supplements, and never replaces,
Codex's independent review, and passing it does not itself authorize starting another
slice.

## Standing rule for mechanical documentation fixes

To avoid an entire Claude/Codex cycle for a non-semantic edit, Codex may directly fix a
documentation defect during review only when **all** conditions are true:

- The correct meaning is already unambiguous from implemented code, accepted decisions,
  and current documentation.
- The edit is limited to spelling/grammar, a duplicate row, a stale path/anchor/revision,
  or removal of wording that is demonstrably superseded.
- It changes no schema, runtime behavior, test expectation, product decision, phase
  scope, or architectural meaning.
- Codex reports the defect and exact edit in `Work review`, verifies the documentation
  diff, and commits it separately with a `docs(review): ...` message.

If any condition is uncertain, Codex requests a correction instead. This rule never
permits Codex to change code, migrations, tests, dependency versions, or semantic
documentation without explicit user authorization.

## Workflow v3.1 pilot (three-slice trial) — CLOSED, superseded by Workflow v3.2

**This section is closed and historical.** The pilot's retrospective, corrected figures,
and the decision to adopt Workflow v3.2 are recorded in
`docs/DECISIONS/0008-workflow-v3.1-retrospective-and-v3.2-adoption.md`; the activation
itself is recorded in `docs/DECISIONS/0009-workflow-v3.2-activation.md`. See the new
"Workflow v3.2" section below, which is now the active mechanism. The narrative below is
retained verbatim as the pilot's own record and is not maintained further.

Status: the approved pilot proposal counts three **parser** slices as its measurement
window: `classify_experience` (slice 1 of 3, merged) and `classify_salary` (slice 2 of 3,
merged) are both complete; `classify_location` (slice 3 of 3) is implemented and frozen
for blind Sol/Astra review, not yet merged. See `docs/ROADMAP.md`'s Phase 3 status for
exact commit references.
`tooling/workflow-v3.1-handoff-metadata` (this branch) is the enabling infrastructure that
makes the pilot measurable — it is not itself one of the three counted slices, since it
has no parsing form/invariant for the claim-to-evidence matrix or historical-defect
checklist to apply to. v3.1 is a measurable trial layered on v3, not an assumed
improvement — a mandatory retrospective follows the third counted slice (see below), and
any element that does not earn its cost may be dropped rather than kept by default.

### Claim-to-evidence matrix

Before implementation on any Class H proposal, and required for any proposal introducing
a new parsing form or invariant, the proposal includes a table with one row per claimed
parsing form/invariant:

| Claim | Example input -> expected output | Verified against |
|---|---|---|

"Verified against" names the fixture case or manual trace that supports the claim — a row
with no cited evidence is itself a finding, the same way an unverified superlative claim
already is under the adversarial self-review above.

### Historical-defect checklist

A proposal's self-review audits the proposed design against each category below,
grounded in defect classes this project has actually produced (e.g. `employment.py`'s
mask-iteration-order bug, the seniority classifier's immediate-trailing-conflict gap, and
the negation/company-tenure gaps the first `classify_experience` preflight caught):

1. Negation/exclusion scope — does a negation word's reach stop where the design assumes?
2. Subject/attribution misassignment — whose property is this value actually describing?
3. Numeric-context confusion — dates, durations, product versions, ages, and unrelated
   numbers mistaken for the value being extracted.
4. Decimal/fractional mishandling — a fractional value silently truncated or re-read as a
   different integer.
5. Token-order/mask-precedence bugs — a shorter match shadowing a longer one, or vice
   versa, depending on iteration order.
6. Range/boundary inversion — an off-by-one, swapped min/max, or an inverted range that
   still parses without error.
7. Structural/positional gating — title-vs-description conflation, or a segment boundary
   assumed to fall somewhere it does not always fall.
8. Provenance/independent-field cross-contamination — one field's resolution silently
   affecting another's.
9. Missing-vs-wrong distinction — the design must be checked for cases that would produce
   a *confident* value contradicted by the input, not merely cases with no extraction.

### Confidently-wrong blocking rule

A case that produces a confident value contradicted by its own input must never be
recorded as an "accepted limitation" — it blocks implementation unless the user
explicitly approves it in writing for that specific case. A case that safely returns
*unavailable* (no extraction, no invented value) may be documented as a limitation without
blocking.

### Two-pass requirement (proposal preflight)

A Class H proposal introducing a new parsing form or invariant receives two self-review
passes before implementation, both performed on the proposal itself, before any repository
file changes: the claim-to-evidence matrix first, then the historical-defect checklist,
with the proposal revised between passes when either surfaces a gap. Both passes are
reported in the proposal, not merely asserted complete.

### Implementation self-review passes (parser slices)

Distinct from the proposal preflight above, and required in addition to it for every
piloted **parser** slice's actual implementation (not merely its proposal): after code is
written, before committing, run two further passes over the diff itself:

1. **Contract-conformance pass** — walk the proposal's stated invariants one at a time and
   confirm the implementation actually enforces each one, not merely that it handles the
   examples in the fixture corpus.
2. **Counterexample pass** — actively construct new inputs designed to break each
   invariant (not drawn from the existing fixture corpus), grounded in the
   historical-defect checklist's nine categories, and confirm the implementation handles
   them correctly or fails safely to *unavailable* (never confidently wrong).

Findings from either pass are fixed before commit, with a regression test added for each,
subject to the mutation-proof rule below. These two passes supplement, and never replace,
the general adversarial implementer self-review already required above for Class H slices.

### Load-bearing regression mutation proof

Every regression test added specifically to close a self-review or review finding (from
either the passes above or Codex's `Work review`) must be proven load-bearing before it is
counted as covering that finding: temporarily revert or disable the specific fix, confirm
the new test actually fails without it, then restore the fix and confirm the test passes
again. A regression test that still passes with its guard disabled is not evidence of
anything and must not be reported as closing the finding it was added for.

### `slice_kind` and the handoff metadata block

Every `Work done` entry's structured `workflow-metadata` fenced block declares
`slice_kind: parser | tooling | docs`, validated by `scripts/check_handoff.py` (see that
module's docstring for the authoritative field-by-field schema) and cross-checked by
`scripts/verify.py`'s required `handoff metadata validation` step against the exact counts
that same invocation observed — never a second subprocess, never a re-derived number.

- **`parser`** — a classifier/normalization slice. Requires an actual (non-`not_run`)
  `focused_test_count` and a matching `focused_test_selector`, plus `fixture_path`/
  `fixture_count` cross-checked against the real fixture file's length.
- **`tooling`** — process or infrastructure work (this slice is one). Full-suite
  verification is required the same as `parser`; focused testing is optional; no fixture
  fields apply.
- **`docs`** — genuinely documentation-only work. `verification_level: not_run` is
  permitted *only* for `slice_kind: docs` (`scripts/check_handoff.py` rejects it
  structurally for `parser`/`tooling`, independent of how `verify.py` was invoked) but is
  never mandatory: if a docs slice actually ran the test suite, it truthfully records
  `verification_level: routine` with real counts like any other slice kind. When
  `not_run` genuinely applies, `full_suite_count`/`focused_test_count` must literally be
  `not_run`, `focused_test_selector` must be `none`, and `lightweight_checks` must name
  what was actually done instead (e.g. `git diff --check`, `check_repo.py`). `--docs-only`
  on `verify.py` enforces this at the tool level: it skips the database and pytest steps
  and independently requires both the handoff to declare `not_run` *and* `slice_kind:
  docs`, so a docs-only run can never silently paper over a stale or missing test count,
  and `--docs-only` can never be used to bypass verification for a parser or tooling
  slice.

### Mandatory retrospective

After the third counted parser slice's `Work review` is recorded (measurement window:
`classify_experience` plus two more parser slices, not this enabling tooling slice), before
starting a fourth slice under v3.1, the user and the implementer jointly assess against
these agreed targets:

- **At most one correction round per slice** — a slice needing two or more `Work review`
  correction rounds counts against the pilot.
- **Zero confidently-wrong review findings** — no case where a piloted slice's shipped
  behavior produced a confident value contradicted by its input (the harm the
  confidently-wrong blocking rule exists to prevent).
- **Zero handoff count defects** — no fabricated, stale, or mismatched
  `full_suite_count`/`focused_test_count` reaching a merged `Work done` entry undetected.
- **Zero regressions that pass with their required guard disabled** — every regression test
  added under a piloted slice actually satisfies the mutation-proof rule above.

The retrospective also records, qualitatively: did the claim-to-evidence matrix or
historical-defect checklist catch a genuine defect before code was written on any of the
three slices (the first `classify_experience` preflight already did, prior to this tooling
slice existing); did `check_handoff.py` ever block a fabricated or stale count; did any
self-review pass meaningfully slow a slice without finding anything. The retrospective
decides, per element, whether to keep it as standing process, narrow it, or drop it — v3.1
is not retained by default merely because it shipped.

## Workflow v3.2 (active)

Status: active, adopted per ADR 0008's accepted principles and activated per ADR 0009
(`docs/DECISIONS/0009-workflow-v3.2-activation.md`). Everything in this file not
explicitly superseded below continues to apply — the Definition of Ready, risk classes,
revision discipline, adversarial self-review, and the closed historical-pilot section
above remain in force. This section adds the durable-evidence and gate mechanism ADR 0008
deferred to a separately authorized slice.

### Reviewer roles (ADR 0008 principles 3–4)

Sol Medium is the mandatory primary reviewer for executable/parser work, including every
Class H slice. Astra review is invoked only for: a user-authorized phase gate;
identity/security/concurrency/destructive/live-provider risk; a disputed finding; or an
explicitly scheduled equal-effort benchmark. An escalation review is additive context — it
is recorded separately from the primary review and can never, by itself, satisfy the
primary-review requirement for an `approved` verdict.

### `--gate fast | final | docs` (`scripts/verify.py`)

Orthogonal to `--level` (risk-class surface). `--gate` is mandatory on every receipt-
eligible invocation:

| Gate | Required execution | Approval eligibility |
|---|---|---|
| `fast` | Static/repository checks; DB safety when applicable; the affected-surface-computed focused tests/contract families/mutation guards (`scripts/verification_scope.py`) | Supports only an intermediate `changes_requested` review |
| `final` | Everything in `fast`, plus the full suite, plus every currently active mutation guard, dynamically discovered (never a hardcoded count) | Required before any executable-slice `approved` verdict |
| `docs` | Existing docs-only static/repository/metadata checks; no DB, pytest, or witnesses | May approve a genuinely docs-only slice only |

`--docs-only` and `--gate docs` are bijective — either alone is a hard error.

### Durable verification receipts (ADR 0008 principle 9)

A receipt-eligible run (`--gate fast|final|docs`) is normally launched by
`scripts/verification_coordinator.py`, never invoked directly against the mutable
authoring checkout: it creates a disposable detached worktree at the candidate commit,
runs verification inside it with every tool's cache redirected into the run directory,
reconfirms the worktree's integrity snapshot is unchanged, removes the worktree,
reconfirms the authoring checkout itself is unchanged, and only then atomically
create-only-writes a receipt under `docs/verification-receipts/<candidate-sha>/
<receipt-id>.json`. A receipt proves verification only — it never proves review approval
or authorizes a merge. `scripts/check_review.py` validates the `C -> A -> R` chain (and,
for a merge, `M`) against Git plumbing and the receipt itself, never against review prose
alone.

### Post-merge (`Q`) evidence producer

`scripts/verification_coordinator.run_post_merge_verification` is the analogous outer
coordinator for `Q`'s post-merge evidence artifact: it verifies the *merged* tree at `M`
(never a pre-merge candidate), always full/final, and derives every field it records
(`base_sha`, `slice_id`, the original receipt reference) from `scripts/check_review.
validate_c_a_r_chain`'s own independently re-validated chain — never from caller-supplied
input, so nothing external can redirect or skip the migration check. It shares the receipt
producer's worktree/lock/cache-cleanup lifecycle under its own `post-merge-coordinator-`
run-directory prefix, and, unlike a receipt, writes nothing at all on a failed verification
or cleanup failure rather than a durable-but-ineligible artifact — `Q`'s only meaning is
structural (`scripts/check_review.validate_q` checks for its committed existence), so
nothing resembling evidence may ever reach disk unless the run genuinely passed.

### Project policy: `Q` is the next mainline commit after `M`

`check_review.validate_q` itself does not require any particular position — it only checks
that the supplied `Q` SHA's sole parent is `M`; a conforming `Q` can equally be a sibling
commit on another branch, authored well after `M`, alongside other unrelated commits
elsewhere. Making `Q` the next commit on `main`'s own mainline after `M` is this project's
own chosen policy, not something the validator enforces or assumes.

**Precondition, checked before merge authorization, not after.** For every future slice,
before the user authorizes merging to `main`, one of the following must already be in
place:

- a reviewed, tested `Q`-artifact producer (`scripts/verification_coordinator.run_post_
  merge_verification`, implemented and tested in the `tooling/workflow-v3.2-post-merge-
  q-producer` slice, becomes exactly this once it is itself reviewed and merged); or
- a separately approved, exact manual evidence-capture procedure on record, specifying at
  minimum: verification isolated against `M`'s own tree in a disposable worktree (never the
  mutable authoring checkout); every required step's output genuinely captured, not
  summarized or copied from an earlier run; the same before/after worktree-integrity
  snapshot and cleanup discipline `verification_coordinator.py` already applies for
  receipts; deterministic construction of the artifact JSON from that captured output
  against the schema `check_review._validate_post_merge_artifact_schema`/`_validate_post_
  merge_artifact_evidence` enforce; and a passing `check_review.validate_published` run
  against the complete chain *before* the `Q` commit is published.

Merge authorization is withheld until one of these exists for the slice being merged. This
closes the gap that produced the `M = 9649cba` exception (see ADR 0009's bootstrap-exception
addendum), which was itself only possible because no such precondition existed yet — that
exception is one-time and does not authorize repeating it.

**Mainline shape once merge proceeds.** The commit immediately following `M` on `main`'s
mainline must be `Q` itself — never a merge-record-only commit. In one commit, `Q` adds both
the schema-valid post-merge artifact (status `A`, under `docs/post-merge/`) and the
append-only merge-record prose to `docs/LLM_HANDOFF.md` (status `M`, pure append) — exactly
what `check_review.validate_q`/`validate_m_to_q_transition` already permit together in a
single transition. `Q` may still have sibling commits on other branches; the policy only
constrains `main`'s own mainline between `M` and `Q`.

**Fail-closed on post-merge failure.** If, after `M` is created, post-merge verification
fails or the assembled `Q` artifact fails `validate_q`/`validate_published`, stop immediately
at `M`. Do not publish a merge-record-only commit as a substitute, and do not report or
imply that the `C -> A -> R -> M -> Q` publication chain is complete. Report the failure and
the exact state of `main` at `M`, and seek explicit user resolution before any further commit
lands on `main`'s mainline.

**Release sequence.** After separate user merge authorization: create `M` locally (not yet
pushed); run the `Q` producer against `M` and, on success, commit `Q` as described above
(still not pushed); run `check_review.validate_published` against the complete local chain;
immediately before pushing, call `verification_coordinator.confirm_main_unchanged` to
re-fetch `origin/main` and confirm it still equals the pre-merge tip — if it has moved, stop
without pushing rather than racing the remote; only then push `M` and `Q` together in one
ref update, so `origin/main` never shows `M` without `Q` immediately following it.

### Schema-v2 handoff metadata (`scripts/check_handoff.py`)

The `workflow-metadata` block moves through exactly two states to avoid a self-referential
commit SHA: `state: pending` (written in the candidate commit itself — `slice_id`,
`slice_kind`, `risk_class`, `base_sha`, `declared_gate`) and `state: published` (the same
block, transitioned by the direct child commit that adds the receipt — adds
`executed_gate` (must equal `declared_gate`), `candidate_sha`, `receipt_id`,
`receipt_path`). Counts live authoritatively in the receipt; if duplicated in the handoff,
they are cross-validated exactly.

### Contract-harness integration

`scripts/contract_mutation_witnesses.py`'s existing single-guard CLI is unchanged; a
`--gate final` run invokes it once per currently active guard (discovered dynamically via
`tests.contracts.taxonomy.active_guards()`) and aggregates the results as its own step.

### Stable IDs (ADR 0008 principle 8)

Slices use `<date>-<slug>-<base-short-sha>`; findings use `<slice-id>/F###`. A
`changes_requested` review requires at least one finding ID; an `approved` review requires
an empty finding list.

### User-only merge authority (unchanged)

A receipt, an `approved` verdict, or any mechanically-satisfied gate never substitutes for
the user's own merge authorization — unchanged from v3 and v3.1.

## Established conventions are defaults

Do not repeatedly ask the user to reconfirm a convention already accepted in current
documentation. Apply it and list it under “conventions applied.” Ask only when a slice
introduces a new semantic choice or a conflict. Examples of established defaults include:

- application-generated UUID primary keys;
- UTC `created_at`/`updated_at` unless a documented exception exists;
- `NULL` for unknown values rather than invented sentinels;
- model/migration parity and named database constraints;
- real PostgreSQL tests for PostgreSQL behavior;
- disposable test-database protection and no destructive development-database tests;
- explicit `ON DELETE` behavior and accepted/rejected constraint coverage.

## Verification matrix

Once `scripts/verify.py` exists (Workflow v3's tooling program; see `docs/ROADMAP.md`'s
tooling sequence), `python scripts/verify.py --level routine` is the canonical way to run
the "Python without schema" row below — it wraps the same checks in the same order, never
a second, independently-drifting copy of the sequence. `--level schema`/`--level
high-risk` extend this table's remaining rows once those levels exist; until a level
exists for a given change surface, run this table's explicit command list directly.
`--docs-only` (Workflow v3.1 pilot) runs the mechanical-docs row's checks that `verify.py`
already covers plus the required handoff-metadata validation, skipping the
database/pytest steps entirely; it is mutually exclusive with `--focus`.

Run the smallest set that can actually detect regressions in the changed surface:

| Change surface | Required verification |
|---|---|
| Mechanical docs only | `git diff --check`; targeted repository searches; link/anchor validation when references changed; `python scripts/check_repo.py` |
| Python without schema | Ruff format/check, mypy, targeted tests, full suite before approval |
| Model or migration | All Python checks; targeted and full tests; existing-head upgrade; downgrade/upgrade; fresh `base -> head`; `alembic check`; `python scripts/check_repo.py`; development DB confirmed untouched unless separately authorized |
| External provider/integration | Offline fixtures/contract tests by default; failure/partial-success behavior; opt-in minimal live test only when explicitly authorized |
| High-risk identity/state/concurrency | Full relevant suite plus adversarial, rollback, isolation, idempotency, and real concurrency/database cases |

Do not rerun unrelated expensive checks for a docs-only correction. Do rerun a broader
set whenever the correction can affect generated configuration, executable examples,
schema, or behavior.

## Handoff format and size

`LLM_HANDOFF.md` retains only the latest two iterations. Keep each agent section concise
and evidence-oriented; do not narrate every individual test when a coverage summary and
command result suffice.

`Work done` should contain:

```text
Date/agent; authorized slice; risk class
Base -> ending commit; branch
Outcome and conventions/new decisions applied
Files changed (grouped, one line each)
Verification commands and exact result counts
Adversarial self-review: assumptions challenged, findings fixed, regression tests
  added, remaining limitations
Deviations/known limitations
STOP and excluded next scope
```

`Work review` should contain:

```text
Date/reviewer; diff reviewed
Independent verification performed
Findings by severity with exact references
Missing/inconclusive checks
Verdict: approved | changes requested
Exact bounded correction, if any
STOP and excluded next scope
```

Target roughly 40 lines per section. Git history carries old narrative and exact diffs;
do not preserve long command transcripts in the ledger.

## Git gates

- One active writer at a time.
- Task branches may be committed and pushed automatically after authorized work.
- Never push implementation directly to `main`.
- No merge, force-push, rebase of shared history, branch deletion, or next-slice work
  without explicit user authorization.
- Keep implementation, review, and any correction as separate commits.
- A clean push is a checkpoint, not permission to continue.

## Process-improvement trigger

When the same defect class is caught twice, propose a small automated prevention check
instead of relying indefinitely on manual review. Add tooling only as its own authorized
slice. Current candidates include Markdown link/anchor validation, duplicate constraints-
summary detection, stale migration-reference detection, and model/migration consistency
checks beyond Alembic's defaults.
