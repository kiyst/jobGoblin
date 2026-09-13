# 0009 — Workflow v3.2 activation

## Status

Accepted. This ADR records the activation of Workflow v3.2 (ADR 0008's accepted-in-
principle design), resolves ADR 0008's five recorded receipt-design questions, and is
itself the activation candidate's own durable record. Workflow v3.1 governed this slice's
own authorization and review; Workflow v3.2 governs every slice that follows it.

## Context

ADR 0008 accepted ten Workflow v3.2 principles in principle but explicitly deferred
activation to a separately authorized, separately gated implementation slice, and recorded
five unresolved receipt-design questions for that slice's own proposal to answer. This
slice (`tooling/workflow-v3.2-activation`) is that slice.

## Decision

### Resolution of ADR 0008's five receipt-design questions

1. **Verification precedes receipt creation.** A receipt is only ever created by
   `scripts/verification_coordinator.py` after every verification step, cache cleanup, and
   integrity reconfirmation has already completed inside a disposable detached worktree —
   never a state whose testing the receipt itself triggers.
2. **No circular attestation.** The receipt attests to the candidate commit SHA that
   already exists and was already tested; it is written into the authoring checkout as a
   new, additive file, never amending or rewriting the candidate commit.
3. **Named doc-only allowance.** `docs/LLM_HANDOFF.md` is the one file permitted to differ
   between the receipt's attested tree and the eventual merge tree, validated by
   `scripts/check_review.py`'s per-transition diff checks — every other path must be
   identical.
4. **Defined state machine.** `C` (candidate, `state: pending`) → `A` (direct child,
   `state: published`, adds the receipt) → `R` (direct child, review verdict) → `M`
   (user-authorized merge). Any commit after a receipt is issued, other than the doc-only
   allowance, invalidates that receipt.
5. **No ephemeral receipt as durable merge evidence.** Every receipt is a durable,
   create-only, committed artifact — there is no ephemeral/local-only receipt path in this
   implementation.

### Implemented mechanism

- `backend/scripts/verification_worktree.py` — disposable detached-worktree lifecycle and
  a four-condition integrity snapshot (`HEAD` SHA, `git diff --quiet`, `git diff --cached
  --quiet`, empty `git status --porcelain=v2 --untracked-files=all`).
- `backend/scripts/verification_receipts.py` — the closed receipt schema, canonical UUID4
  `receipt_id` generation, atomic create-if-absent write (`os.link`, never `os.replace`),
  strict duplicate-JSON-key rejection, and `approval_eligible` recomputation.
- `backend/scripts/verification_scope.py` — affected-surface classification (exact-path
  and directory-prefix rules only, config-load-time duplicate/overlap rejection) and the
  deterministic migration/schema-change trigger (`backend/migrations/**`,
  `backend/alembic.ini`, `backend/app/db/**`).
- `backend/scripts/verification_coordinator.py` — the outer launcher implementing the
  corrected sequence: create worktree → snapshot → run → clean caches → snapshot → remove
  worktree → confirm no leak → reconfirm authoring checkout → emit receipt.
- `backend/scripts/migration_matrix.py` — guarded database routing for a schema-changing
  candidate: the development URL is captured once; every target (including a generated
  fresh database) is validated via the existing `scripts/db_safety.py` guards; a fresh
  database's admin/maintenance connection is derived by changing only the database
  component; ownership is proven via pre-attempt absence, this run's own generated
  identity, and post-attempt presence before any cleanup `DROP DATABASE`.
- `backend/scripts/check_handoff.py` (schema v2) — `state: pending | published`,
  `slice_id`, `risk_class`, `base_sha`, `declared_gate`/`executed_gate`.
- `backend/scripts/check_review.py` — `C -> A -> R` chain validation (parent-shape,
  review-metadata schema, receipt cross-check, recomputed `approval_eligible`) and merge
  validation (`M`'s parents, empty `R..M` diff).
- `backend/scripts/verify.py` — `--gate {fast,final,docs}`, `--witness`,
  `--emit-step-json`; a new `contract mutation witnesses` step aggregating
  `scripts/contract_mutation_witnesses.py` (unchanged single-guard CLI) once per selected
  guard.

### Ten ADR 0008 principles — operative rules

| # | Principle | Operative rule |
|---|---|---|
| 1 | Compact contracts | Unchanged from v3's revision discipline: one compact contract plus at most one amendment round for a novel parser grammar |
| 2 | Two-submission limit | Confirmed as applying to novel-parser-grammar proposals specifically |
| 3 | Sol Medium primary reviewer | `docs/LLM_WORKFLOW.md`'s new "Reviewer roles" subsection |
| 4 | Selective Astra escalation | Same subsection; escalation is additive, never a substitute for the primary review |
| 5 | Executable parser contracts | Already delivered (Slice 2); required for every future parser slice |
| 6 | Mechanism-level mutation evidence | `verify.py`'s mutation-witness step, dynamically discovered guards |
| 7 | Fast/final/docs gates | `--gate` (above) |
| 8 | Stable IDs | `<date>-<slug>-<base-short-sha>` / `<slice-id>/F###`, in `docs/LLM_WORKFLOW.md` |
| 9 | Durable verification evidence | The receipt mechanism (above) |
| 10 | User-only merge authority | Restated explicitly; unchanged |

### This slice's own activation as a one-time transition

Workflow v3.1 governs this slice's own authorization and review — its `Work done` entry
declares `workflow_version: v3.2` (the schema this slice itself introduces) under the
user's explicit authorization of this specific transition, not by mechanically satisfying
the pre-activation `check_handoff.py`, which correctly only accepted `v3.1-pilot` and
cannot evaluate code it predates. This is recorded here as a one-time, named exception —
never a precedent for skipping schema validation on any later slice.

## Consequences

- Every future slice declares `workflow_version: v3.2` and follows the pending/published
  metadata lifecycle, the `--gate` profiles, and the receipt mechanism above.
- No existing `docs/LLM_HANDOFF.md` entry's `workflow_version` field is rewritten; history
  before this activation remains `v3.1-pilot`, exactly as ADR 0008 required.
- Rollback boundary: reverting this slice's merge commit restores Workflow v3.1 as the
  sole active workflow, atomically. No further slice begins during any rollback-
  consideration window.
- Known scope limits, recorded honestly rather than silently: `scripts/check_review.py`'s
  merge/post-merge modes validate parent-shape and content-identity but do not yet
  implement the full outer-launcher/subprocess-reexecution design (running `R`'s own
  checked-out validator code rather than the caller's in-process copy) or the complete
  per-transition byte-identical-historical-text diff validator; `scripts/migration_matrix.py`
  is implemented and tested end-to-end against a real disposable database but is not
  exercised by this slice's own candidate (a tooling slice that touches no migration/model
  path). Both are follow-on hardening for a future slice, not a gap in this activation's
  own verification.
