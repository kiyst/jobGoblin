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

- Date/agent: 2026-10-04, Claude (implementer). Branch
  `workflow/throughput-protocol-retention`, base
  `6752dcdc0ce1b57c0af164aa217d3181566086bd` (`Q` of the Phase 4 S2b merge
  `M=692c420`). Ending commit: this commit (candidate `C`).
- Slice: the ADR 0012 pilot evaluation and adoption, a bounded documentation-policy
  slice. Risk class D, `slice_kind: docs`, `declared_gate: final`. `docs/LLM_WORKFLOW.md`
  is a `workflow-governing-doc` under `scripts/verification_scope.py`, which forces
  `gate=final`. No executable, test, fixture, schema, or configuration change.
- Re-anchor, before any edit and after a fresh fetch:
  - local `main`, `origin/main`, and remote `main` all equalled the base, and the tree was
    clean;
  - S1, S2, and S2b each reached `Q`, which exhausts ADR 0012's three-slice
    authorization;
  - no S2c, provider-contact, persistence, D1, S3, or S4 work had begun.
- Contract: the user's adoption decision and authorization, frozen with every binding
  input in the create-only, gitignored runtime packet
  `.claude/runtime/workflow-throughput-protocol-retention-contract.md` (SHA-256
  `369a6c20c9135d087a50168576c5a1dff886b120ea9e8088743884e6eec4608a`). The packet is not
  committed. Inputs, in precedence order:
  1. the user's decision and authorization;
  2. Sol Medium's compatibility review, with binding amendments E9–E13;
  3. Astra's amendments E1–E8, as relayed. Astra's full response was not received, and
     ADR 0016 discloses this with E13's exact wording;
  4. the implementer's revised evaluation and O1–O5;
  5. ADR 0012 and Workflow v3.2.

  Both reviews were policy consultations, not formal `R` metadata.
- Files (exact closed four-path list):
  - `docs/DECISIONS/0016-workflow-throughput-pilot-evaluation-and-retention.md` (new).
    It records the required decision sentence verbatim, the evaluation with cited
    evidence paths, O1–O5, retained and deferred controls, the Phase 4 exit assessment,
    and rollback;
  - `docs/LLM_WORKFLOW.md`, in the Workflow v3.2 section:
    - the ADR 0012 subsection is renamed "Workflow Throughput Protocol (ADR 0012,
      retained by ADR 0016)", with an updated status and status pointer;
    - "pilot" becomes "protocol" in the precedence, product-priority, and metrics
      wording;
    - the exit paragraph now covers the exit evaluation, next assessment, and rollback;
    - O1–O5 are added;
    - two deferred items are added: a new metrics framework, and another model-approval
      layer.

    No existing requirement was deleted;
  - `docs/ROADMAP.md`: S2b's stale "in progress" status is replaced with its `M`/`Q`,
    and an entry is added for this evaluation;
  - this file: the two-iteration rotation. The S2 iteration was removed. The S2b
    iteration is retained unchanged as Iteration 1, apart from its renumbered heading.
- Not changed: ADR 0012 (byte-identical to the base), `CLAUDE.md`, validators and
  verification tooling, tests, fixtures, schemas, configuration, reviewer roles, receipt
  binding, handoff retention, and registered witnesses.
- Metrics, recomputed from committed evidence before commit (receipt and post-merge
  `duration_seconds` summed with exact decimal arithmetic; commit chains from `git log`):
  - committed receipts:
    - pilot: 3 across 3 slices (1.00 per slice);
    - Phase 3 risk class H: 16 across 6 (2.67);
    - all Phase 3 v3.2 product slices: 18 across 7 (2.57);
  - Phase 3 risk class H receipt-bearing corrections after the first `A`: 10, each
    changing code, tests, or fixtures;
  - recorded step time:
    - Phase 3 risk class H receipts: 6,158.988 seconds, averaging 384.937 seconds;
    - pilot candidate receipts: 1,190.484 seconds;
    - pilot post-merge runs: 1,238.609 seconds;
  - known pilot full-suite runs: 9;
  - pilot relays: 24 (19 necessary, 2 non-actionable, 3 indeterminate).

  Every cited receipt and artifact path exists.
- Implementer notes, recorded in the packet at freeze and disclosed for formal review:
  - N1. ADR 0016 names the evaluation checkpoint (`6752dcd`, 2026-10-04T22:18:42Z) so
    that E12's "less than 24 hours old" sentence stays true. At that instant, S1's `Q`
    was about 22.4 hours old;
  - N2. E9 is kept verbatim. One added factual sentence discloses `17f6f24`, the
    skill-classifier slice's handoff-only commit after its first `A`. It carries no
    receipt and is not a correction candidate.
- Pre-commit checks: `check_repo`, `check_handoff`, and `git diff --check` pass. A
  consistency review covered all four documents.
- Verification: the genuine `verification_coordinator` `gate=final` run against `C`,
  recorded in `A`.
- STOP after `A` for formal Sol Medium review. No `R`, merge, `M`/`Q`, validator or
  tooling change, Greenhouse or provider contact, S2c, persistence, D1, S3, or S4.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-04-workflow-throughput-protocol-retention-6752dcd
slice_kind: docs
risk_class: D
base_sha: 6752dcdc0ce1b57c0af164aa217d3181566086bd
declared_gate: final
executed_gate: final
candidate_sha: eac6f0a37e9ceb8a744b2c0c54b1c2315e08ebd2
receipt_id: 734bd347-bac1-4a8d-a3e7-97b957a995bb
receipt_path: docs/verification-receipts/eac6f0a37e9ceb8a744b2c0c54b1c2315e08ebd2/734bd347-bac1-4a8d-a3e7-97b957a995bb.json
```

### Work review

- Date/reviewer: 2026-10-05 (UTC), Sol (primary, Sol Medium). Formal review of the
  Workflow Throughput Protocol evaluation-and-retention slice (ADR 0016), on
  `workflow/throughput-protocol-retention`:
  - base `6752dcdc0ce1b57c0af164aa217d3181566086bd`;
  - candidate `C` = `eac6f0a37e9ceb8a744b2c0c54b1c2315e08ebd2`;
  - publication `A` = `cc76502a0d3c4f23e8225b1573184fe0a2f99e9c`;
  - receipt `734bd347-bac1-4a8d-a3e7-97b957a995bb`, SHA-256
    `e6e349cda892b013f11cdc9bbc168d7eca962a5335200c5bb2bcc5e67692563d`.

  Reviewed against frozen contract SHA-256
  `369a6c20c9135d087a50168576c5a1dff886b120ea9e8088743884e6eec4608a`. The earlier Astra
  and Sol policy consultations (E1–E8 as relayed, and E9–E13) are contract evidence, not
  formal review metadata for this slice; this is the formal review.
- **1. Sol's formal verdict and disposition** (as relayed by the user; the relay is the
  authority for this review):
  - verdict **approved, no executable findings**; findings none;
  - primary reviewer Sol (Sol Medium); gate `final`; risk class D, `slice_kind: docs`;
  - lineage: `C` is the base's direct single-parent child and `A` is `C`'s; the feature
    branch and origin equal `A`; `main` and `origin/main` remain at the base; the tree is
    clean;
  - scope: base→`C` changes exactly the four authorized documentation paths, and ADR 0012's
    blob is byte-identical to the base. No executable, fixture, configuration, dependency,
    migration, schema, validator, verification tool, registered witness, reviewer role,
    receipt rule, handoff-retention rule, or product behavior changed;
  - `C`→`A` adds exactly one receipt and changes only the newest workflow metadata from
    pending to published. `C` has no `executed_gate` or formal-review metadata; `A`
    records D/docs/final, the exact candidate, receipt ID, and path;
  - contract conformance: ADR 0016, `LLM_WORKFLOW.md`, `ROADMAP.md`, and this file
    correctly incorporate the retain-with-bounded-revisions decision, O1–O5, E1–E8 as
    relayed, and E9–E13. E13's limitation on Astra attribution appears exactly and
    prominently. Existing validator-enforced rules retain precedence;
  - O1–O5 conform:
    - O1 is a pre-advisory default, not a verification cap or closed exception list;
    - O2 distinguishes immutable candidate reviews from proposal or policy reviews
      without a candidate commit, and requires state-sensitive handling of repeated
      messages;
    - O3 requires a dependency-removal or reachable-capability statement without
      compelling premature or unsafe wiring;
    - O4 permits evidence reuse while leaving review depth, complete semantic rereview,
      and rejection entirely within formal R's authority;
    - O5 requires normal defect handling and a bounded process assessment, without
      automatic rollback or new authorization;
  - the evaluation makes none of the prohibited claims: measured delivery time, a
    controlled counterfactual, unchanged assurance, relay improvement, production
    readiness, or generalization to live-provider or persistence work.
- **Rulings:**
  - **N1 (evaluation checkpoint): approved.** Anchoring the exposure-age statement to
    commit `6752dcdc0ce1b57c0af164aa217d3181566086bd` at `2026-10-04T22:18:42Z` preserves
    a historically testable checkpoint as wall-clock time advances. At that checkpoint
    S1's `Q` was about 22 hours 24 minutes old, S2's about 19 hours 7 minutes, and S2b's
    `Q` was the checkpoint commit itself, so "less than 24 hours" is accurate and
    sufficiently bounded.
  - **N2 (non-receipt handoff commit): approved.**
    `17f6f241d2c76f0ce3876ec1e2ae5a9bfb0880f3` is a direct post-`A` handoff-only commit
    that changes only `docs/LLM_HANDOFF.md`. It has no receipt and is not a
    receipt-bearing correction candidate. Its disclosure does not conflict with E9 or
    alter the 16-receipt or 10-correction totals.
  - **Continued metric recording: approved.** Continuing ADR 0012's existing metrics
    through the Phase 4 exit assessment adds no metric, field, schema, or tool; creates no
    new pilot authorization window; adds no reviewer or approval layer; authorizes no
    product work; and is compatible with the retained protocol.
- **2. Independently rerun or recomputed in formal review** (per the relay):
  - Git ancestry, branch synchronization, the clean tree, the four-path scope, and ADR
    0012's identity;
  - receipt schema and its `C`/base/slice/risk/gate binding; the committed verifier,
    checker, and configuration hashes;
  - the affected surface (`docs-only`, `handoff-transition`, `workflow-governing-doc`),
    no required focused selector, migration not triggered, and the complete active
    registered-witness inventory;
  - `approval_eligible=true`;
  - `require_single_parent` for `C` and `A`; `validate_c_to_a_transition`; published
    metadata validation; handoff, repository, and diff checks;
  - every material receipt count, correction candidate, and duration total:
    - committed receipts: pilot 3 / 3 slices = 1.00; Phase 3 risk class H 16 / 6 = 2.67;
      all Phase 3 Workflow v3.2 product slices 18 / 7 = 2.57;
    - risk class H receipt-bearing corrections after the first `A`: 10, all changing
      executable code, tests, or fixtures, none handoff-only;
    - Phase 3 risk class H receipt-step duration 6,158.988 seconds, averaging 384.937;
      pilot candidate receipts 1,190.484 seconds; pilot post-merge runs 1,238.609
      seconds;
    - known pilot full-suite executions: 9;
    - pilot relays: 24 (19 necessary, 2 non-actionable, 3 indeterminate);
  - existence and readability of all 22 cited evidence files; all 19 cited verification
    receipts are schema-valid.
- **3. Committed content inspected directly** (per the relay): ADR 0016; the full
  `LLM_WORKFLOW.md`, `ROADMAP.md`, and `LLM_HANDOFF.md` changes; the frozen contract; the
  `C`→`A` publication diff; the receipt; the cited historical receipt and artifact
  inventory; commit `17f6f24`; and the retained handoff rotation.
- **4. Relied upon from the genuine C-bound receipt** (coordinator run at `C`; not rerun
  in formal review):
  - all 11 applicable final-gate steps PASS, including the full suite (**4,240
    passed**) and registered contract mutation witnesses (**34 of 34 passed**);
  - disposable test-database URL validation and reachability passed;
  - migration not triggered; isolated-worktree integrity and cleanup passed;
  - recorded coordinator step duration: 481.625 seconds.
- Re-verified from Git plumbing and the receipt when this review was recorded:
  - the local and remote feature branch equalled `A`, whose sole parent is `C`;
    `main`, `origin/main`, and the remote `main` remained at the base; the tree was
    clean;
  - the receipt file SHA-256 and the frozen-contract SHA-256 matched exactly; the
    receipt is schema-valid, bound to `C`, and recomputes `approval_eligible=true`.
- Evidence boundary: no Greenhouse or other live-network contact, production database, or
  production-data access occurred. The full suite used the configured disposable test
  database.
- **Approved operating rules** (effective only after this slice reaches `Q` on `main`):
  O1 pre-advisory verification default; O2 actionable review evidence; O3 product
  capability statement; O4 formal-review evidence reuse with unchanged authority; O5
  incident assessment trigger. The next workflow assessment is at Phase 4 exit, with
  earlier O5 assessments if triggered.
- **Limitations retained:**
  - Astra's full response was not received; only the relayed E1–E8 text was available to
    the evaluator;
  - complete end-to-end timing is unavailable; only recorded verification-step durations
    exist, and authoring, reviewer, waiting, relay, and unrecorded verification time
    remain unknown;
  - Phase 3 is a historical comparison group, not a controlled baseline, and the tasks
    are not matched;
  - equivalent assurance and reduced relay frequency have not been demonstrated;
  - the evidence does not generalize to live-provider, runtime-reachable, or persistence
    work.

  "No findings" is a review status. It does not prove unchanged assurance or improved
  throughput.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings.
- Exact bounded correction: none required.
- STOP -- record-only. This review authorizes no merge, `M`, `Q`, tooling or policy
  change, Greenhouse contact, S2c, persistence, D1, S3, S4, or other slice. Merge
  requires separate user authorization.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-04-workflow-throughput-protocol-retention-6752dcd
risk_class: D
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-05T17:34:25+00:00
candidate_sha: eac6f0a37e9ceb8a744b2c0c54b1c2315e08ebd2
publication_commit_sha: cc76502a0d3c4f23e8225b1573184fe0a2f99e9c
receipt_path: docs/verification-receipts/eac6f0a37e9ceb8a744b2c0c54b1c2315e08ebd2/734bd347-bac1-4a8d-a3e7-97b957a995bb.json
receipt_id: 734bd347-bac1-4a8d-a3e7-97b957a995bb
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-05 (UTC). Merged `workflow/throughput-protocol-retention` into `main` with
  `git merge --no-ff`, at the approved, reviewed commit
  `7a2e007ab1fac085cfb018a4c1b3a1882646640c` (`R`). `R` is Sol Medium's "approved -- no
  findings" formal verdict on `C=eac6f0a37e9ceb8a744b2c0c54b1c2315e08ebd2` /
  `A=cc76502a0d3c4f23e8225b1573184fe0a2f99e9c`.
  - Merge commit `M`: `e1f510bf7482bb4f48ef1c21c0d35f32ac0ee0ba`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `6752dcdc0ce1b57c0af164aa217d3181566086bd`.
  - Full lineage: base `6752dcd` -> `C` `eac6f0a` -> `A` `cc76502` -> `R` `7a2e007` ->
    `M` `e1f510b` -> `Q` (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch, its origin, and the remote ref all sat at `R`; `R`'s sole parent
    is `A` and `A`'s is `C`; the tree was clean;
  - `main`/`origin/main`/remote `main` were synchronized at the rollback boundary;
  - **receipt `734bd347-bac1-4a8d-a3e7-97b957a995bb`** (file SHA-256
    `e6e349cda892b013f11cdc9bbc168d7eca962a5335200c5bb2bcc5e67692563d`):
    - schema-valid and bound to `C`, the base, the slice, gate `final`, and risk class D;
    - its verifier, checker (`check_handoff.py`), and configuration hashes equal the files
      committed at `C`;
    - the affected surface (`docs-only`, `handoff-transition`, `workflow-governing-doc`)
      and migration decision (not triggered) recomputed identically;
    - independently recomputed as approval-eligible;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`, `reviewer_role: primary`,
    `gate: final`, `published_slice_kind: docs`.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, 6752dcd)` passed.
  - `verification_coordinator.run_post_merge_verification` ran against `M` in a
    disposable detached worktree (always full/final). It produced artifact
    `41e35df6-9d84-4e01-9726-9d0d71d4aa44`:
    - all 11 steps PASS: Ruff format and check, mypy, `check_repo`, `git diff --check`,
      disposable test-database URL validation and reachability preflight, the full
      suite, contract mutation witnesses, handoff metadata validation, and
      temporary-directory cleanup;
    - full pytest suite: **4240 passed**;
    - all 34 registered mutation witnesses passed, 0 failed;
    - no migration triggered;
    - worktree removed with no residual entry or directory; cleanup PASS;
    - recorded step duration 457.172 seconds.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit (this entry).
- Post-merge evidence:
  `docs/post-merge/e1f510bf7482bb4f48ef1c21c0d35f32ac0ee0ba/41e35df6-9d84-4e01-9726-9d0d71d4aa44.json`
  (SHA-256 of the artifact file as written:
  `1248b5f1f91f2aee758bd1361a26e8cd8602c98b540a7636c18c860052d10ee6`). It references
  original receipt `734bd347-bac1-4a8d-a3e7-97b957a995bb`.
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- Evidence by source:
  - **Post-merge coordinator (this artifact, at `M`):** the 11 steps above, including the
    4,240-test full suite and 34/34 registered witnesses.
  - **Pre-merge receipt (at `C`):** all 11 final-gate steps PASS, including the full suite
    (4,240 passed) and 34/34 registered witnesses; migration not triggered; cleanup PASS;
    recorded step duration 481.625 seconds.
  - **Formal review (`R`):** Sol independently reran or recomputed the lineage, scope,
    ADR 0012 identity, receipt binding and hashes, affected surface, witness inventory,
    approval eligibility, the `C`→`A` transition, handoff/repository/diff checks, and
    every material evaluation metric. Sol inspected the four documents, the frozen
    contract, and the cited evidence inventory, and relied on the receipt for the full
    suite and registered witnesses. Sol approved N1, N2, and continued recording of ADR
    0012's existing metrics.
  - No Greenhouse or other live-network contact, production database, or production-data
    access occurred. Both suite runs used the configured disposable test database.
- Status: merged. This slice adds
  [ADR 0016](DECISIONS/0016-workflow-throughput-pilot-evaluation-and-retention.md), which
  records the ADR 0012 three-slice pilot evaluation and retains the Workflow Throughput
  Protocol with bounded operational revisions O1–O5. **O1–O5 become effective only when
  this `Q` reaches `main`.** The next workflow assessment is at Phase 4 exit, with earlier
  O5 incident assessments if triggered. No validator, verification tool, metadata schema,
  reviewer role, receipt-binding rule, handoff-retention rule, registered witness,
  executable behavior, or product behavior changed. ADR 0012 is unchanged.
- Retained limitations:
  - Astra's full response was not received; only the relayed E1–E8 text was available to
    the evaluator;
  - complete end-to-end timing is unavailable; only recorded verification-step durations
    exist, and authoring, reviewer, waiting, relay, and unrecorded verification time
    remain unknown;
  - Phase 3 is a historical comparison group, not a controlled baseline, and the tasks
    are not matched;
  - equivalent assurance and reduced relay frequency have not been demonstrated;
  - the evidence does not generalize to live-provider, runtime-reachable, or persistence
    work.

  Approval and passing verification are review and verification status. They do not
  establish unchanged assurance or a demonstrated throughput improvement.
- STOP -- report the synchronized final `main` SHA and stop. No Greenhouse contact, S2c,
  runtime wiring, persistence, D1 work, migration, workflow-tooling change, S3, S4, or
  another slice without separate explicit user authorization.

## Iteration 2

### Work done

- Date/agent: 2026-10-05, Claude (implementer). Branch
  `phase-4/greenhouse-live-canary-s2c`, base
  `eeac72abb2ba930fb469a4abb563a7601826266a` (`Q` of the ADR 0016 retention slice).
  The chain of immutable advisory candidates, each preserved unamended:
  - the pre-live candidate `cc14774533035c5b119060e980bf8bbc9062537d`;
  - correction 1, `6ca5fd18bef83a300117918370625c1a5a3f303d`;
  - correction 2, `1cb715a00c52fef07ea93ea356612ffe0322ac83`, under which live attempt 1 ran (`FAIL-CLOSED:worker_failed`).

  Ending commit: this commit, **post-run correction 3**, the direct single-parent child of
  correction 2, for narrow re-review by Sol Medium and Astra. None of them is final `C`: no
  coordinator run, receipt, `A`, formal review, or merge metadata exists. The consumed
  reservation and gitignored raw staging from attempt 1 exist and are unchanged.
- Slice: Phase 4 S2c, a bounded read-only Greenhouse live canary
  ([ADR 0017](DECISIONS/0017-greenhouse-live-canary.md)), offline pre-live portion only.
  Risk class H, `slice_kind: tooling`, `declared_gate: final`.
- Contract: frozen, create-only, gitignored packet
  `.claude/runtime/phase4-s2c-frozen-contract.md`, SHA-256
  `ac2cc00afc9e2bb7b7520eba71da7d6349e7b523f1b9b601bb2ad254c450800b`, frozen from the
  user's relay packet (SHA-256
  `b1268d8d85c7a2c1ce89cebb6fabb4d138f9a32ff38b604e77a742975187a1cd`). It holds nine
  immutable inputs:
  - three authoritative sources, re-read and verified before freezing: the proposal
    `6de1fd21…24a6`, Astra's review `38759f5a…acc6`, and Sol's review `8822137e…1eb9`;
  - Sol's compatibility ruling;
  - Astra's two compatibility findings;
  - Sol's final corrections;
  - Astra's confirmation;
  - the user's decisions U1–U8 and the authorization.

  The packet records the hash of every section. Each embedded source equals its file
  after CRLF-to-LF and outer blank-line trimming.
- User decisions:
  - U1: network authorization withheld;
  - U2: board `discord`;
  - U3: the terms/robots review is pending;
  - U4: create-only raw retention through post-run review, then verified deletion before
    final `C`;
  - U5: publication approval pending;
  - U6: default `httpx` User-Agent plus `Accept-Encoding: identity`;
  - U7: Sol Medium and Astra review the pre-live and post-run candidates;
  - U8: raw-capture fidelity required for PASS.
- Files (cumulative scope; 7 of the 9 authorized paths):
  - `backend/scripts/run_greenhouse_s2c_canary.py` (new): the default-off harness;
  - `backend/scripts/verification_scope.py`: exactly `_GREENHOUSE_S2C_FIXTURE_FILES`,
    included in configuration validation and classification;
  - `backend/tests/test_greenhouse_s2c_canary.py` (new) and
    `backend/tests/test_verification_scope.py`;
  - `docs/DECISIONS/0017-greenhouse-live-canary.md` (new; results section empty);
  - `docs/ROADMAP.md` (S2c bullet);
  - this file. Rotation: S2b's iteration was removed; the ADR 0016 iteration is retained
    unchanged apart from its renumbered heading.

  Reserved, deliberately not created: `backend/tests/fixtures/providers/greenhouse_s2c_projected.json`
  and `docs/evaluation/phase4-s2c-live-canary.md`. No fabricated or placeholder live
  evidence exists.
- Harness, offline: everything in ADR 0017 §2–§7 for the pre-live portion:
  - gates, the one guarded request, and headers;
  - complete-versus-partial capture;
  - the record cap before conversion;
  - the attempt reservation and supervised deadline;
  - diagnostic reconstruction cross-checked against the adapter;
  - verdicts;
  - selection, projection, excerpts, lineage, the fixture validator, and the report
    draft;
  - cleanup and the fresh-process checker.

  It makes no `app/` change. Its imports are limited to the authorized adapter,
  converter, bridge, composition, taxonomy, schemas, and hashing helper.
- Disclosed interpretations for review:
  - **Private helpers.** The harness reuses the adapter's private `_validate_record`,
    `_duplicate_identity`, and `_is_json_media_type` for diagnostic reconstruction, and
    cross-checks the result against the adapter's own output.
  - **Unavailable fidelity review** caps the verdict at INCONCLUSIVE, per Sol A16 (not
    superseded).
  - **5xx and transport errors.** Every 5xx is INCONCLUSIVE, per final §6. A non-timeout
    transport error is FAIL-CLOSED.
  - **Mutation inventory.** The contract names "W1–W12" without an itemized list, so the
    reconciled inventory below is the implementer's mapping of the original M1–M12 onto
    the amended safety boundaries.
- O1 pre-advisory evidence (no full suite; no risk required one):
  - focused harness tests: 128 passed;
  - verification-scope tests: 93 passed;
  - existing Greenhouse adapter, converter, bridge, composition, D2 realistic, and HTML
    oracle tests: 828 passed (unchanged);
  - Ruff format/check and mypy clean on all changed Python;
  - `check_handoff` and `check_repo` pass, and `git diff --check` is clean.
- W1–W12 manual mutations, run after the last harness change against harness SHA-256
  `778c549e78039b458078d3d5de1ea16df4fab87163ecabb009b3b97671fdd082`. Each has a unique
  anchor and one named failing witness; two stable controls passed under every
  mutation; every restoration was byte-identical; the baseline and final runs passed.
  1. W1: request-shape guard removed;
  2. W2: second-send refusal removed;
  3. W3: env gate removed;
  4. W4: board allowlist removed;
  5. W5: `Accept-Encoding: identity` removed;
  6. W6: raw overwrite instead of exclusive create;
  7. W7: no terminate/kill at the deadline;
  8. W8: `max_attempts=3`;
  9. W9: cap raised to 5 MiB;
  10. W10: record cap removed;
  11. W11: database-layer import added;
  12. W12: reservation refusal removed.

  These are advisory evidence, not registered witnesses; the 34 registered witnesses are
  unchanged.
- Network and side effects: no Greenhouse or other provider contact. No live transport
  was constructed: tests disable real transports and DNS. No database or production
  data was accessed, and no real staging or reservation was created.
- Remaining pre-live gates:
  1. Sol Medium and Astra advisory review of this candidate;
  2. the user's recorded terms/robots review;
  3. explicit network authorization naming the board, this exact SHA (or an approved
     correction child), the contract hash, the request, the bounds, the one-attempt rule,
     and the retention policy.

  Publication (U5), the post-run review, cleanup, final `C`/`A`/`R`, and merge each
  require their own authorization.
- Retained limitations:
  - a live result is unproven;
  - Discord's response size is unknown;
  - screening is defense in depth, not a guarantee;
  - after cleanup, omitted source content cannot be reconstructed from hashes;
  - D1 is unsatisfied and L4 remains open;
  - nothing is runtime-reachable.
- **Pre-live advisory correction 1** (`6ca5fd18bef83a300117918370625c1a5a3f303d`, the direct single-parent child of
  `cc14774533035c5b119060e980bf8bbc9062537d`). Authority: packet
  `.claude/runtime/phase4-s2c-prelive-correction1-authorization.md` (gitignored), SHA-256
  `991a91136b12c3575fd9a021d979109f2a7b217380db18f74e8d0436f968bff7`. It holds both
  complete advisory reviews ("Changes requested") and the user's bounded correction
  authorization. Scope: exactly `backend/scripts/run_greenhouse_s2c_canary.py`,
  `backend/tests/test_greenhouse_s2c_canary.py`, and this file. The union of both reviews:
  1. **Fidelity.** Both dispositions are validated against the closed vocabulary; an
     invalid value is FAIL-CLOSED `review_disposition_invalid`. Either `not_performed`
     caps the verdict at INCONCLUSIVE `fidelity_review_unavailable`, and PASS needs both
     `faithful`. A mismatch stays PASS-WITH-FINDINGS below higher-priority conditions.
  2. **Converted-first selection.** With no eligible converted record the selection is
     empty. The builder refuses `no_converted_sample` and the validator rejects a
     negative-only or empty fixture. A findings-only report remains possible.
  3. **Exclusive worker authorization.** After reserving and staging, the supervisor
     writes a create-only launch capability. It is bound to the reservation line's SHA-256,
     its identities, and the SHA-256 of a one-time token passed only over the worker's stdin
     pipe. Before any transport exists, the worker:
     - re-derives the capability and compares it;
     - requires an open, single-line reservation and no existing claim, raw capture, or
       summary;
     - exclusively creates its claim.

     Each of these is refused: direct invocation, a wrong or missing token, a missing or
     mismatched capability, an altered or closed reservation, crash residue, a restart
     after the request began, and a concurrent or duplicate launch.
  4. **Containment.** Any abnormal supervisor exit after launch (interrupt or supervision
     failure) terminates the worker, escalates to kill if needed, and confirms it is gone.
     Only then does it record `FAIL-CLOSED:supervisor_interrupted` (or
     `FAIL-CLOSED:worker_termination_unconfirmed`), and the reservation is kept.

     Parent loss: the supervisor keeps the worker's stdin pipe open until the worker exits.
     The worker's watchdog thread exits it at once (code 75) when the pipe closes,
     including when the supervisor process is killed. No second timer was added.
  5. **Proper excerpts.** A selection spanning the complete source string is refused,
     however short, in both the builder and the validator (recorded offsets and original
     length). Both size limits and exact-substring semantics are unchanged.
  6. **Cleanup binding.** Cleanup and the fresh-process checker are bound to:
     - the post-run candidate SHA, with `HEAD` equal to it and a clean tree;
     - the approved fixture SHA-256 (or approved absence) and the approved report SHA-256.

     The fixture must validate, including `publication_safe=true`, performed reviews, and a
     non-blank reviewer. While raw staging exists, the raw response's Git blob id must be
     absent from the commit range and the index. Its bytes (LF and CRLF forms) must be
     absent from every changed and publication file, whatever the filename. Any failure
     refuses and deletes nothing. Screening is recorded but never decides publication
     safety; independent content review stays mandatory.
  7. **CLI.** Decisions are type-checked before conversion (`decisions_invalid`). Every
     other failure is a fixed categorical line with a nonzero status
     (`operational_failure`, `supervision_aborted`, `interrupted`). No message, chained
     exception, traceback, or staged value is printed.
  8. **Evidence.** The table below.

  This correction supersedes the candidate's test totals and mutation evidence above.
- Verification at `6ca5fd1` (no full suite; no correction finding indicated broader
  risk):
  - harness module: 204 passed;
  - verification-scope tests plus the existing Greenhouse adapter, converter, bridge,
    composition, D2 realistic, and HTML-oracle tests: 921 passed;
  - Ruff format/check and mypy clean;
  - `check_handoff`, `check_repo`, and `git diff --check` pass.
- W1–W12 at `6ca5fd1`: all twelve were detected against harness SHA-256
  `45d98eccda7c5c5fba56bd233692d30288ce6978a4f9c9937f6778b393ecaadb`, with byte-identical
  restoration. The complete per-mutation table is in this file at commit `6ca5fd1`. The
  gitignored log is `.claude/runtime/phase4-s2c-correction1-mutation-log.json`, SHA-256
  `86c222d37e89be3d8e0ef6d2908c30239bd24e022b27b8709501b49a28c3b4fe`.
- **Pre-live advisory correction 2** (`1cb715a00c52fef07ea93ea356612ffe0322ac83`, the direct single-parent child of
  `6ca5fd18bef83a300117918370625c1a5a3f303d`). Authority: packet
  `.claude/runtime/phase4-s2c-prelive-correction2-authorization.md` (gitignored), SHA-256
  `951486634ad8fcea1fb0175a400c2193db566c4c9b9537293b7d89e58436d9b9`. It holds both
  complete re-reviews ("Changes requested") and the user's bounded correction
  authorization. Scope: exactly `backend/scripts/run_greenhouse_s2c_canary.py`,
  `backend/tests/test_greenhouse_s2c_canary.py`,
  `docs/DECISIONS/0017-greenhouse-live-canary.md`, and this file. Dispositions:
  1. **Kernel containment.** Before the reservation exists, the supervisor creates a
     Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and verifies it by
     reading it back. It holds the only, non-inheritable handle.
     - It assigns the worker and confirms membership with `IsProcessInJob` before it
       releases the stdin token.
     - Until then the worker can only block waiting for the token.
     - Closing the handle, including on supervisor crash or kill, makes the kernel
       terminate the worker in any phase, independent of its interpreter and GIL.
     - Unsupported or failed setup refuses (`containment_unavailable`) before the
       reservation. A failed assignment releases no token, stops the worker, and records
       `FAIL-CLOSED:containment_assignment_failed`.
     - Without containment, no token is ever released (`containment_required`).
     - The worker-side kill-on-close check and the stdin watchdog are defense in depth
       only. Disclosed: this host's shell already runs inside a kill-on-close job, so
       the worker-side check alone proves little here; the supervisor's assignment is
       the guarantee.
  2. **Shutdown.** Terminate, then kill, reaping after each step.
     - Failures or interruptions of terminate, kill, wait, or poll never skip escalation.
     - Death is confirmed only by the reaped code or by OS process state (OpenProcess /
       GetExitCodeProcess). Otherwise the result is `termination_unconfirmed`.
     - An interruption is honoured (`SupervisionAborted`) only after shutdown was
       attempted.
     - No exception text escapes.
  3. **Replay-converted-first builder.** The first sample's projected excerpt must
     actually replay as `converted` (`first_sample_not_converted` otherwise). Later
     samples must replay to distinct outcomes that are not `converted` or `invalid_type`
     (`distinct_outcome_violation`).
  4. **Semantic fixture validation.** `validate_fixture(document, taxonomy)` replays every
     projected job through the unchanged adapter, converter, bridge, and composition.
     - It requires golden expectations to equal the recomputed results
       (`golden_mismatch`).
     - It enforces the selection contract on actual outcomes, with strictly increasing
       source ordinals.
     - Relabelling or fully recomputed hashes cannot pass.
     - Cleanup's publication check uses it, and any validation or replay failure counts
       as not approved.
  5. **ADR 0017 reconciled.** §2–§5 now describe:
     - the launch capability, stdin-only token, and single worker claim;
     - kernel containment and shutdown confirmation;
     - the pre-deletion candidate, artifact, review-state, and raw-absence binding, plus
       the fresh-process checks;
     - proper substrings and the replay-converted first sample.

     Request limits, the frozen contract, the authorization sequence, and other design
     decisions are unchanged. The earlier temporary statement that this entry overrode
     the ADR is withdrawn: ADR 0017 is the normative record.
  6. **Evidence.** The table below.
- Verification at `1cb715a` (no full suite; no finding indicated broader risk):
  - harness module: 239 passed, 0 skipped, on Windows. This includes nine real-process
    supervisor-loss tests:
    - before assignment and before claim;
    - during claim, transport construction, and blocking I/O;
    - during GIL-holding work, the request, capture, and summary writing.

    Each kills the supervisor mid-phase and requires OS-confirmed worker death with no
    later phase completed.
  - verification-scope plus the existing Greenhouse adapter, converter, bridge,
    composition, D2 realistic, and HTML-oracle tests: 921 passed;
  - Ruff format/check and mypy clean;
  - `check_handoff`, `check_repo`, and `git diff --check` pass.
- W1–W12 at `1cb715a`: all twelve were detected against harness SHA-256
  `b5ecedb6ffbea05d64a3e9b662fd951e3f4a9ecd6062e1206a7b3d9e9aa0b61a`, with byte-identical
  restoration. The complete per-mutation table is in this file at commit `1cb715a`. The
  gitignored log is `.claude/runtime/phase4-s2c-correction2-mutation-log.json`, SHA-256
  `cc80c54628eb9b6803473e79c0025bef04b7a42ec8aefe82f278acff99631c8b`.
- **Live attempt 1 (immutable): `FAIL-CLOSED:worker_failed`.**
  - **Authority.**
    - Candidate `1cb715a00c52fef07ea93ea356612ffe0322ac83`, harness `b5ecedb6…a0b61a`.
    - Personal-use terms amendment
      `46b2c55c9f5d9990b4c6b12970d55744c7071e01eb9a7e3bb26699619f165323`, approved as
      compatible by Sol Medium and Astra, as relayed.
    - The user's U1 network authorization, recorded verbatim at
      `.claude/runtime/phase4-s2c-u1-network-authorization.md`, SHA-256
      `8564eaafdf60d1719128fd6bd9ff79283ab8ba3ce967db76dfd96b09f0795fcd`.
  - **The request.** Exactly one `GET https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true`
    at 2026-10-08T23:18:16Z, with no retry and no second request.
  - **Recorded outcome.** The consumed reservation `.claude/runtime/phase4-s2c-attempt.jsonl`
    (SHA-256 `18763cf69c9452d36e96017ee91b9ad3638398726b7dbce24917ef75efd00f5e`) holds
    `reserved`, then `FAIL-CLOSED:worker_failed`. This outcome is permanent.
  - **Run summary** (written before the failure; categorical, unreviewed):
    - HTTP 200, JSON, User-Agent `python-httpx/0.28.1`;
    - a complete 413,101-byte capture, SHA-256
      `3bbce131108b1fb0b0645a90bcb5174b58c69360fd4257f1ff288460cbf90c19`;
    - 48 source records, with `meta.total` 48;
    - 48 retained, all `converted`;
    - no run findings.

    No PASS is derived from this clean processing summary.
  - **Cause.** The defense-in-depth daemon stdin watchdog held stdin's `BufferedReader`
    lock at interpreter shutdown. CPython aborted with `Fatal Python error:
    _enter_buffered_busy` and exit code 0xC0000005, which the supervisor correctly
    treated as a failure.
  - **Staging** (gitignored; unchanged through this correction; never committed or
    logged). SHA-256 values were taken before and after the correction:

    | Artifact | SHA-256 |
    |---|---|
    | raw capture | `3bbce131108b1fb0b0645a90bcb5174b58c69360fd4257f1ff288460cbf90c19` |
    | run summary | `0ca3ded395beab0d7ebb161845f17c9c0e65943f1003e5f0010a31f3929de46c` |
    | launch capability | `ac86b5d980957a32061b27c4d0f17665c8197cd75fb42687d2f4ab73798e14ad` |
    | worker claim | `25a8a1ea5f1099dae988300270af9d14163c9b799293f31282b3dc0c5b68404d` |
  - **Evidence limits.**
    - The capture is usable only for bounded evidence: captured-response, replay,
      lineage, and provisional fidelity.
    - A corrected candidate must complete a separately authorized new live request,
      under new U1 authorization with an explicitly authorized reservation reset, before
      S2c can pass.
    - The W1–W12 experiments are manual. No coordinator executed them.
  - **Timeout-wording disclosure.** U1 repeated a stale "55-second per-board bound". The
    reconciled contract removed that separate harness timer. The only bounds are the
    adapter's internal timeouts (a conservative 55-second per-board sum) and the one
    supervised 60-second deadline. U1 is preserved unchanged, and no timer was added. Any
    future authorization must state the corrected timeout model.
- **Post-run correction 3** (this commit, the direct single-parent child of `1cb715a00c52fef07ea93ea356612ffe0322ac83`).
  - **Authority.** The user's post-run correction 3 authorization. Scope: exactly
    `backend/scripts/run_greenhouse_s2c_canary.py`,
    `backend/tests/test_greenhouse_s2c_canary.py`,
    `docs/DECISIONS/0017-greenhouse-live-canary.md`, and this file.
  - **Mechanism.** The redundant daemon stdin watchdog is removed. `worker_entry` starts
    no thread and reads stdin once, for the token. The verified kill-on-close Job Object
    remains the sole and authoritative parent-loss containment. All of these are
    unchanged:
    - assignment and membership before token release;
    - the atomic claim and consumed-reservation controls;
    - no transport before authorization and containment;
    - fail-closed, evidence-based shutdown.

    Request, retention, privacy, fixture, and provider semantics are unchanged.
  - **Tests.**
    - Removed: the two watchdog-only tests.
    - Changed: the direct `_worker` CLI refusal must now be exactly 3. A `worker_entry`
      test proves that no thread starts and that nothing beyond the token line is read.
    - Added: a real-process regression that drives the actual `_worker` entry under the
      real supervisor, Job Object, launch capability, token, claim, and mocked transport
      (no network possible). It requires exit 0 within the deadline, an empty fd-2
      stderr, an observed summary, and the terminal line
      `OBSERVED:pending_post_run_review`. It **fails against `1cb715a`** with
      `_enter_buffered_busy`; this was rerun against the exact `b5ecedb6…` harness bytes,
      which were then restored byte-identically. It **passes after the correction**.
  - **ADR 0017** records the immutable attempt, the defect and its cause, the mechanism,
    the regression, the evidence limits, the timeout-wording disclosure, and that a new
    attempt needs separate authorization.
- Verification at this commit (no full suite; no broader risk was found):
  - harness module: 238 passed, 0 skipped (239, minus two watchdog-only tests, plus the
    regression). This includes:
    - all nine real-process supervisor-loss phase tests;
    - the direct-worker refusal, assignment and token-ordering, claim and reservation,
      transport-containment, and shutdown-escalation tests;
  - verification-scope plus related tests: 921 passed;
  - Ruff format/check and mypy clean;
  - `check_handoff`, `check_repo`, and `git diff --check` pass.
- W1–W12 manual mutations, rerun after the final semantic change against harness SHA-256
  `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0`. No anchor needed to move. Manual advisory evidence only: no
  coordinator executed them, and the 34 registered witnesses are unchanged.
  - Stable controls for every mutation: `tests/test_greenhouse_s2c_canary.py::test_default_invocation_refuses` and `tests/test_greenhouse_s2c_canary.py::test_selection_rule_follows_provider_order`.
  - Every anchor occurred exactly once.
  - The baseline and final runs of all witnesses and controls passed.
  - Anchors are shown with line indentation omitted; ⏎ marks a newline.
  - The gitignored log is `.claude/runtime/phase4-s2c-correction3-mutation-log.json`,
    SHA-256 `6ed5b8718438ae04221f626ab29fad4e52ef95e1c5af151ee55a823cacfcb915`.

  | ID | Mutation | Anchor → replacement | Failing witness (`tests/test_greenhouse_s2c_canary.py::`) | Baseline | Mutant | Restored; SHA-256 |
  |---|---|---|---|---|---|---|
  | W1 | request-shape guard removed | `check_request_shape(request) ⏎ request.headers["Accept-Encoding"]` → `request.headers["Accept-Encoding"]` | `test_request_shape_guard_refuses_before_send[other_board]` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W2 | second-send refusal removed | `if self._capture.request_sent: ⏎ raise CanaryRefusal("second_request_refused")` → (deleted) | `test_second_send_is_refused_before_network` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W3 | live gate enabled by default (env check removed) | `if env.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE: ⏎ raise CanaryRefusal("gate_disabled")` → (deleted) | `test_live_preflight_refuses_without_live_env` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W4 | board allowlist check removed | `if request.board != BOARD_TOKEN: ⏎ raise CanaryRefusal("board_not_allowlisted")` → (deleted) | `test_live_preflight_refuses_non_allowlisted_board` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W5 | Accept-Encoding: identity override removed | `request.headers["Accept-Encoding"] = ACCEPT_ENCODING` → (deleted) | `test_accept_encoding_identity_and_default_user_agent` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W6 | raw capture overwrite instead of exclusive create | `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_EXCL \| getattr(os, "O_BINARY", 0))` → `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_TRUNC \| getattr(os, "O_BINARY", 0))` | `test_exclusive_write_never_overwrites` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W7 | supervisor no longer terminates/kills at the deadline | `stop()` → `pass` | `test_supervisor_terminates_and_reaps_worker_at_deadline` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W8 | retries enabled (max_attempts=3) | `max_attempts=1, max_response_bytes=MAX_RESPONSE_BYTES` → `max_attempts=3, max_response_bytes=MAX_RESPONSE_BYTES` | `test_503_is_inconclusive_with_exactly_one_request` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W9 | response cap raised to 5 MiB (5,242,880) | `MAX_RESPONSE_BYTES: Final = 5_000_000` → `MAX_RESPONSE_BYTES: Final = 5_242_880` | `test_body_over_cap_is_partial_without_complete_hash` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W10 | record cap before conversion removed | `if capture.source_record_count > MAX_SOURCE_RECORDS: ⏎ raise CanaryRefusal("record_cap_exceeded")` → (deleted) | `test_record_cap_is_enforced_before_conversion` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W11 | database-layer import added | `from app.ingestion.hashing import canonical_json_hash  # noqa: E402` → `import sqlalchemy  # noqa: E402, F401 ⏎ from app.ingestion.hashing import canonical_json_hash  # noqa: E402` | `test_harness_imports_only_allowed_modules` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
  | W12 | existing-reservation refusal removed from preflight | `if os.path.lexists(paths.reservation): ⏎ raise CanaryRefusal("attempt_already_reserved")` → (deleted) | `test_live_preflight_refuses_existing_reservation` | pass | fail; controls pass | pass; `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0` |
- STOP -- post-run correction 3, for narrow re-review by Sol Medium and Astra. No
  Greenhouse request, reservation reset, second attempt, staging change or deletion,
  tracked fixture, tracked report, receipt, final `C`/`A`/`R`, `M`/`Q`, persistence, or
  other slice.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-05-phase4-greenhouse-live-canary-s2c-eeac72a
slice_kind: tooling
risk_class: H
base_sha: eeac72abb2ba930fb469a4abb563a7601826266a
declared_gate: final
```
