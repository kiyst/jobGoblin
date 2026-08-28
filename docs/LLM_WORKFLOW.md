# Multi-LLM Engineering Workflow v2

Status: active as of 2026-08-26. This is the operating process for Claude Code as the
primary implementer and Codex as the independent reviewer. Product requirements remain
authoritative in the master guide, architecture, data model, roadmap, and accepted ADRs.
The user remains the scope and merge authority.

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

## Risk classes and slice size

Classify a proposed slice before implementation:

| Class | Typical work | Default slice | Review/verification level |
|---|---|---|---|
| D — documentation | Typo, duplicate row, stale link or reference, non-semantic wording | One small document pass | Diff, searches, links/anchors as relevant; no backend suite unless executable inputs changed |
| R — routine | Repeated established model/service pattern with no novel identity, concurrency, security, or external behavior | One table/service, or at most two tightly coupled items when the same invariant and tests cover both | Targeted checks plus full static checks/test suite; migration checks if schema changes |
| H — high risk | Identity/deduplication, destructive lifecycle, user-state preservation, concurrency, security/privacy, external providers, ingestion, scheduler | One independently testable invariant or vertical slice | Full relevant suite, adversarial/boundary tests, real backing service where required, explicit rollback/failure checks |

When uncertain, use the higher-risk class. A phase boundary never expands authorization.

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
