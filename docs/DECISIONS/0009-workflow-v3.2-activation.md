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
- **Correction round 1** (Sol review: Changes requested on the original candidate
  `16ec8b3`/publication `c1c2cc1`, superseded and not reused) completed the outer-launcher/
  subprocess-reexecution design for `check_review.py` (proven against this project's own
  editable-install `sys.path` precedence), the complete `C..A`/`A..R` byte-identical
  transition validators, explicit `Q`/`validate_published` post-merge validation, deep
  receipt-content validation (required step names, genuinely positive numeric counts, the
  reproduced empty-steps/all-`not_run` negative case), fully fail-closed coordinator
  cleanup ordering (including safe removal of only its own stale scratch directories), the
  `base_sha == origin/main` + ancestry + slice-ID enforcement performed before any
  execution, pre-execution coverage computation feeding the actual `--focus`/`--witness`
  arguments, full `migration_matrix.run_full_matrix` integration into `verify.py` as a real
  step, and an explicit, separately named `--compat-v3.1` flag. No scope limit remains
  undocumented; `migration_matrix.run_full_matrix` is exercised by real, passing
  fault-injection tests but is still not triggered by this slice's own candidate diff,
  since this tooling slice touches no migration/model path.

## Post-merge evidence: one-time bootstrap exception for M = 9649cba

`M = 9649cba1deebdc73911790de3ccb2ac51fd483a6` (the merge of
`tooling/workflow-v3.2-activation` into `main`) has no `Q`. `main`'s existing direct child
of `M`, `27a2a5e2cf81b2e347d1fa19012822fe1f0b6198` (the merge-record commit), adds no
post-merge artifact and therefore fails `check_review.validate_q(M, 27a2a5e)`:
`ReviewValidationError: M..Q must add exactly one post-merge artifact (status A), got []` —
independently confirmed by direct invocation. `check_review.validate_published(C10, A10, R,
M, *)` will fail unless a conforming sibling `Q` is later authorized and published; the gap
is absent-for-now, not impossible — `M` can still take a `Q`-shaped direct child on a
separate branch at any time (Git places no limit on how many direct children a commit can
have).

This is accepted as a one-time bootstrap exception, not a precedent. The reason is
procedural, not technical: `M`'s own merged tree already contains the `validate_q`/
`validate_published` tooling (this merge is what introduced it to `main`), so nothing
prevented authoring a conforming `Q` immediately after `M`. What happened instead is that
the agent stopped as instructed after the merge, then authored the merge-record commit as
the next, expected step — before the `Q` requirement was checked against Git. That
merge-record commit occupies the position `validate_q` would otherwise have checked, and
undoing that would mean rewriting a published commit, which this project does not do.

The underlying verification checks are not lost, but they are reported, not independently
reproducible from Git. `docs/LLM_HANDOFF.md`'s "Merge record" entry for this merge (dated
2026-09-17) reports: zero content diff between merged `main` and `R`, `git diff --check`
clean, `check_repo.py` clean, no migration/schema changes, and a canonical-verifier run of
all 12 checks PASS (480 focused / 2,647 full-suite tests, 34/34 mutation witnesses) run
directly against `M`'s own tree before the merge-record commit existed. Git preserves that
prose report and the merge itself, but not the original run's own output (step timings,
environment descriptor, receipt-shaped JSON) — that was never captured as a durable
artifact. The same checks can be rerun against `M`'s tree at any time to obtain equivalent
(not identical) fresh evidence.

Consequence: any future automated check that requires `validate_published` to succeed for
this exact slice will fail until a conforming `Q` is authored and published for it, which is
not currently planned. Nothing in this codebase today makes that call a required gate. This
entry is the record of why the gap exists and that it was a deliberate, reviewed
exception — not an oversight to silently work around, and not a precedent: it does not
authorize repeating this pattern for any future slice. See "Project policy: `Q` is the next
mainline commit after `M`" in `LLM_WORKFLOW.md`, which requires an approved `Q` producer or
evidence-capture procedure *before* merge authorization for every future slice, and requires
stopping at `M` — never publishing a merge-record-only commit — if post-merge verification
or `Q` validation fails.

## Post-merge (`Q`) evidence producer

Implemented in this slice (`tooling/workflow-v3.2-post-merge-q-producer`):
`verification_coordinator.run_post_merge_verification`, alongside a new
`PostMergeEligibleRequest` dataclass carrying only the five chain commit SHAs (`candidate_
sha`, `publication_sha`, `review_sha`, `merge_sha`, `expected_first_parent`) — no
`base_sha`/`slice_id`/receipt-reference field exists for a caller to forge. Every one of
those values is instead derived from `check_review.validate_c_a_r_chain`'s own independently
re-validated chain output before any worktree is created. The migration trigger is computed
over that same chain-derived `base_sha..candidate_sha` range — never a caller-supplied range
and never `base_sha..merge_sha` — so a forged or omitted value can never suppress a genuine
migration requirement. Verification runs in a disposable detached worktree at `M` (always
full/final, never gated or focus-narrowed), reusing the receipt producer's own worktree/
lock/cache-cleanup lifecycle under its own `post-merge-coordinator-` run-directory prefix
(`cleanup_stale_coordinator_dirs` is now parameterized by prefix and rejects any prefix
outside the two known ones, before ever scanning a directory). Emission is explicitly
fail-closed: a failed verification run, a cleanup failure, or an artifact that would fail
its own self-validation all produce *no file at all* — never a durable-but-ineligible
artifact, since `Q`'s only meaning is structural (its committed existence is what `validate_
q` checks) and a failed run must never be mistaken for evidence. The function only ever
writes the artifact file; committing `Q` (bundling that file with the append-only
merge-record edit to the handoff, per the mainline-`Q`-next policy below) remains a separate
step. A small `confirm_main_unchanged` guard supports the release sequence: re-fetch
`origin/main` immediately before pushing a locally-prepared `M`/`Q` together, refusing to
push if the remote advanced in the meantime.

Proven by genuine disposable-Git-repository tests (`tests/test_verification_coordinator_
post_merge.py`): a real local `C -> A -> R -> M -> Q` chain passes `check_review.
validate_published` end to end; a failed verification run and a worktree-removal (cleanup)
failure both write no artifact; incorrect `M` parentage and a malformed committed `A`
receipt (both a schema-invalid variant and a schema-valid-but-cross-referenced-wrong
variant) are all rejected before any worktree is created; a candidate genuinely touching a
migration-trigger path drives `--migration-required` from the chain-derived base, with a
negative control for an unrelated candidate; the two cleanup-prefix scopes never cross, an
unknown prefix is rejected before any directory scan, and an actively-locked directory of
either prefix is left alone; and the release-sequence guard both passes when the remote is
unchanged and rejects when a genuine second push advances it.
