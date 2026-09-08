# Multi-LLM Engineering Workflow v3

Status: active as of 2026-08-30. This is the operating process for Claude Code as the
primary implementer and Codex as the independent reviewer. Product requirements remain
authoritative in the master guide, architecture, data model, roadmap, and accepted ADRs.
The user remains the scope and merge authority. A Workflow v3.1 pilot layer (see "Workflow
v3.1 pilot" below) is being trialed across three slices starting 2026-09-08; it is
additive to everything in this file unless a section says otherwise.

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

## Workflow v3.1 pilot (three-slice trial)

Status: piloted starting with this tooling slice (`tooling/workflow-v3.1-handoff-metadata`),
itself pilot slice 1 of 3. v3.1 is a measurable trial layered on v3, not an assumed
improvement — a mandatory retrospective follows the third piloted slice (see below), and
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

### Two-pass requirement

A Class H proposal receives two self-review passes before implementation, both performed
on the proposal itself, before any repository file changes: the claim-to-evidence matrix
first, then the historical-defect checklist, with the proposal revised between passes
when either surfaces a gap. Both passes are reported in the proposal, not merely asserted
complete.

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
  permitted and required — `full_suite_count`/`focused_test_count` must then literally be
  `not_run`, never a fabricated or copy-pasted number, and `lightweight_checks` must name
  what was actually done instead (e.g. `git diff --check`, `check_repo.py`). `--docs-only`
  on `verify.py` enforces this at the tool level: it skips the database and pytest steps
  and requires the handoff to declare `not_run`, so a docs-only run can never silently
  paper over a stale or missing test count.

### Mandatory retrospective

After the third piloted slice's `Work review` is recorded, before starting a fourth slice
under v3.1, the user and the implementer jointly assess: did the claim-to-evidence matrix
or historical-defect checklist catch a genuine defect before code was written on any of
the three slices (the first `classify_experience` preflight already did, prior to this
tooling slice existing); did `check_handoff.py` ever block a fabricated or stale count; did
either self-review pass meaningfully slow a slice without finding anything. The retrospective
decides, per element, whether to keep it as standing process, narrow it, or drop it — v3.1
is not retained by default merely because it shipped.

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
