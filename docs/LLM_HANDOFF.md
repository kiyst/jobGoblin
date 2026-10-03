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

- Date/agent: 2026-10-02, Claude (implementer). Branch `phase-3/title-normalization`.
  Bounded C2 correction as the direct child of `A = d1c63e0ce9995bd36f981e350b3d8efbd850178d`.
  `C = e2573bc9792e74f60b59fd2b2974141a1a32302b` and `A` are preserved unamended (no
  rebase, amend, or force-push). Ending commit: this commit (candidate `C2`).
- Sol's P2 finding (evidence specification): frozen witness 02 (`Technical Recruiter
  Software Engineer`) cannot isolate `PREFIX_BLOCKERS`, because `recruiter` is also in
  `PREFIX_ROLE_DESIGNATORS`, so it stays `AMBIGUOUS` with the blocker guard disabled.
  The guard itself is load-bearing; this is not an implementation failure. Correction
  authorized by the user within a three-file envelope.
- Files (exactly three): `backend/tests/test_normalization_titles.py` (witness 02
  renamed to `test_witness_02_prefix_blockers_isolating`, input `Data and Software
  Engineer`, expected `AMBIGUOUS`); `backend/tests/fixtures/normalization/title_cases.json`
  (the witness-02 designation moved from `collision_prefix_blocker_recruiter`, which is
  kept unchanged as overlap coverage apart from its note, to
  `collision_prefix_blocker_and_only`; only those two `note` fields changed); this file.
  No production file, vocabulary, rule, Unicode policy, output type, realistic
  expectation, evaluator output, fixture count (still 200), ownership mapping, or other
  doc changed. `titles.py` is byte-identical to `C` (SHA-256 `9550ad31...cd05e`).
- Corrected witness-02 proof (only `PREFIX_BLOCKERS` disabled, via
  `if _prefix_has_blocker(prefix):` -> `if False:`):
  - normal implementation: `Data and Software Engineer` -> `ambiguous`;
  - under the mutant: `matched`, `software-engineer`, so the witness fails;
  - after restoration: `ambiguous`, so the witness passes;
  - `Lead Software Engineer` and `Senior Software Engineer` stay `matched` /
    `software-engineer` under both configurations.
- Corrected final inventory: **12/12 witnesses proven**. All 12 mutants were rerun in
  one harness pass, and the source was restored byte-for-byte (SHA-256 verified).
  Witnesses 01 and 03-12 are unchanged in definition and result.
- Checks: 362 focused tests passed (title 276, verification-scope 86). Realistic
  titles: 22 matched / 6 unsupported / 2 ambiguous, unchanged. Evaluator output is
  byte-identical to the base-approved output (1366 lines).
- Receipt supersession: `A`'s receipt
  `docs/verification-receipts/e2573bc9792e74f60b59fd2b2974141a1a32302b/d8ea060c-298d-473e-93a6-aa6d32b7c7d7.json`
  is **superseded and non-reusable** for this slice's approval. It is bound to `C`,
  not `C2`, and is left unmodified and undeleted. `C2` needs its own fresh
  `gate=final` receipt, recorded in `A2`.
- STOP after `A2` for Sol's re-review. No `R`, merge, `M`/`Q`, production change,
  Phase 3 exit audit, or Phase 4 work.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-02-phase3-title-normalization-aed2694
slice_kind: parser
risk_class: H
base_sha: aed2694720b0344ae54feeef1916805f91e6b508
declared_gate: final
executed_gate: final
candidate_sha: 4c6f933fb3112357f6a96f751115776e74831d73
receipt_id: 1541f94b-45fe-49ef-af52-2afd39fcb367
receipt_path: docs/verification-receipts/4c6f933fb3112357f6a96f751115776e74831d73/1541f94b-45fe-49ef-af52-2afd39fcb367.json
fixture_path: backend/tests/fixtures/normalization/title_cases.json
fixture_count: 200
```

### Work review

- Date/reviewer: 2026-10-02, Sol (primary). Reviewed the title-classifier slice: the
  original candidate `C` (`e2573bc`) and its publication `A` (`d1c63e0`), then the
  bounded evidence correction `C2` (`4c6f933`) and its publication `A2` (`795ed58`),
  on `phase-3/title-normalization`, against the proposal, the A1-A12 amendment table,
  and the corrected A2/A4/A5 fragment with the final 12-witness inventory.
- Prior finding, now resolved: P2 (evidence specification). Frozen witness 02 could
  not isolate `PREFIX_BLOCKERS` because `recruiter` is also a
  `PREFIX_ROLE_DESIGNATOR`. It was corrected in `C2` with no executable change.
- Points verified:
  - `C2` is `A`'s sole child, and `A2` is `C2`'s sole child.
  - `C2` changes exactly the three authorized evidence-correction files.
  - All production code, including `titles.py`, is byte-identical to the original `C`.
  - The fixture still has 200 cases; only two note/designation fields changed.
  - Corrected witness 02 (`Data and Software Engineer`) isolates `PREFIX_BLOCKERS`
    on its own, and both positive controls (`Lead Software Engineer`, `Senior
    Software Engineer`) are stable.
  - Witnesses 01 and 03-12 are unchanged; the inventory is 12/12 proven.
  - Realistic results are still 22 MATCHED / 6 UNSUPPORTED / 2 AMBIGUOUS.
  - Evaluator output is byte-identical (SHA-256
    `87a92187a2d37d5150fe998d06042449f6b74d540cecd15d1bba97dd94801de6`).
  - `C2` -> `A2` contains only the permitted publication transition and the fresh
    receipt.
- Sol's own checks: the focused verification (362 tests) passed. Sol did not rerun
  the full suite.
- Relied on from the genuine `C2` receipt (`1541f94b-45fe-49ef-af52-2afd39fcb367`):
  3,470 full-suite tests and 34/34 registered contract witnesses. The receipt is
  valid, bound to `C2`, and independently recomputes `approval_eligible=true`.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no executable findings.
- Exact bounded correction: none required.
- STOP -- record-only. No merge, `M`, `Q`, executable-file change, Phase 3 exit
  audit, or Phase 4 work is authorized by this review.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-02-phase3-title-normalization-aed2694
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-02T23:03:00.637705+00:00
candidate_sha: 4c6f933fb3112357f6a96f751115776e74831d73
publication_commit_sha: 795ed58573f3994f432ee013c8ae5510ea200e95
receipt_path: docs/verification-receipts/4c6f933fb3112357f6a96f751115776e74831d73/1541f94b-45fe-49ef-af52-2afd39fcb367.json
receipt_id: 1541f94b-45fe-49ef-af52-2afd39fcb367
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-02. Merged `phase-3/title-normalization` at the approved,
  reviewed commit `71176ccba8204058b80552ef70d7b2e25b72a9bc` (`R`; Sol's "approved -- no executable findings" verdict on
  `C2=4c6f933`/`A2=795ed58`, above) into `main` via `git merge --no-ff`. Merge
  commit: `a3c1c12053e7990b88e2c01f6736425cb59f3453`. Pre-merge `main`/`origin/main` tip (rollback boundary): `aed2694720b0344ae54feeef1916805f91e6b508`.
- Pre-merge checks: freshly fetched `origin`. The feature branch and its origin both
  sat at `71176cc`, and `main`/`origin/main` were both clean and synchronized at
  `aed2694`. `validate_c_a_r_chain(C2, A2, R)` and `check_merge_eligibility(C2, A2,
  R)` still returned `approved`, `findings: none`, `reviewer_model: Sol Medium`.
  Receipt `1541f94b-45fe-49ef-af52-2afd39fcb367` remained schema-valid, bound to `C2`, and independently
  recomputed as approval-eligible.
- Release sequence: `M` was created locally and not pushed. `R..M` has zero content
  difference, and `check_review.validate_merge(R, M, aed2694)` confirmed `M`'s exact
  two-parent shape. `verification_coordinator.run_post_merge_verification` ran
  against `M` in a disposable detached worktree (always full/final):
  - artifact `bb3ce6d0-5c3f-4791-a5a9-fcd61fb6a56e`, all 11 steps PASS;
  - full pytest suite **3470 passed**, all 34 registered mutation witnesses
    pass;
  - no migration triggered;
  - worktree initial/final snapshots identical, no residual worktree entry, cleanup
    PASS.
  `Q` is `M`'s direct mainline child: that artifact plus this append-only merge
  record, in one commit (this entry itself).
- Post-merge evidence: `docs/post-merge/a3c1c12053e7990b88e2c01f6736425cb59f3453/bb3ce6d0-5c3f-4791-a5a9-fcd61fb6a56e.json`, referencing original receipt `1541f94b-45fe-49ef-af52-2afd39fcb367`
  (`docs/verification-receipts/4c6f933fb3112357f6a96f751115776e74831d73/1541f94b-45fe-49ef-af52-2afd39fcb367.json`). `check_review.validate_published(C2, A2, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push;
  their results are in the agent's final report rather than restated here ahead of
  time.
- STOP -- report the synchronized final `main` SHA and stop. No Phase 3 exit audit,
  Phase 4, persistence wiring, provider contact, production database work, or another
  correction slice without separate explicit user authorization.

## Iteration 2

### Work done

- Date/agent: 2026-10-02, Claude (implementer). Branch `phase-3/exit-audit`, base
  `b31916827c07715bb59f430ad52dd0193561c35b` (`Q` of the title-normalization merge
  `M=a3c1c12`). Ending commit: this commit (candidate `C`).
- Slice: Phase 3 exit audit. Risk class D, `slice_kind: docs`, `declared_gate: docs`.
  No executable change.
- Frozen contract, in precedence order:
  1. the implementer's read-only Phase 3 exit-audit proposal;
  2. Astra's phase-gate review of D1/D2 and its evidence corrections (an additive
     escalation review, invoked because this is a user-authorized phase gate);
  3. Sol Medium's primary-review final approval, adopting Astra's amendments and the
     binding clarification as the complete contract.

  Neither reviewer authorized `R`, a merge, or Phase 4.
- Files (closed five-file list, all within it):
  `docs/DECISIONS/0011-phase-3-exit-audit.md` (new), `docs/ROADMAP.md`,
  `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, this file.
- ADR 0011 is the durable closure artifact. It records:
  - the closure statement, verbatim;
  - the eight-parser inventory;
  - a requirement-to-evidence matrix for every Phase 3 entry check, required prevention,
    and exit criterion;
  - parser-contract completion as distinct from production readiness;
  - limitations L1-L7;
  - the D1 precondition, verbatim, with its clarifications;
  - the D2 precondition;
  - the other deferred integration obligations;
  - the pre-existing `db/models/company.py` import exception, recorded as outside the
    eight Phase 3 parsers.
- Evidence the implementer reproduced read-only and offline at the base, matching
  Astra's figures:
  - 940 distinct strings, 12,220 parser invocations, no exceptions, and no returned
    `explicit_source`/`structured_metadata`;
  - evaluator output of 91,994 bytes, 1,366 CRLF lines with a final newline, SHA-256
    `87a92187a2d37d5150fe998d06042449f6b74d540cecd15d1bba97dd94801de6`;
  - 100 of 120 salary-component annotations with missing wired input;
  - current combined-split mismatches: 159 (100 missing input, 56 supported abstentions,
    3 `skills.golang` recall misses).

  No full suite was rerun. The audit relies on receipt `1541f94b` and post-merge artifact
  `bb3ce6d0`.
- ROADMAP:
  - added the Phase 3 closure entry with the exact closure wording;
  - replaced the twelfth slice's stale "candidate stage" assertion with `M`/`Q`;
  - annotated the seventh slice's "title … unstarted" sentence as a superseded
    point-in-time statement.

  Other slice history is unchanged.
- ARCHITECTURE:
  - marked `titles.py` as merged;
  - corrected §11 step 2's false claim that the fixture pipeline runs normalization and
    sets `parser_version`;
  - added §5 notes on the pre-existing company-model exception and on deferred, binding
    parser-version/normalization persistence.
- DATA_MODEL: reworded five current-state "until Phase 3" or unstated-deferral notes:
  `target_role_families`, `candidate_skills.skill`, the `candidate_skills` index
  rationale, `normalized_title`, and `parser_version`. Moved the `job_skills` introduction
  to Phase 4+ normalization-persistence integration. No schema commitment, migration, or
  point-in-time history changed.
- ADR 0010 is byte-identical (SHA-256
  `beda935f94f63de30a5516c2ea6a055ca8da913dbd58a0161d2f078ba16813da`).
- Verification: the genuine `verification_coordinator` `gate=docs` run against `C`,
  recorded in `A`.
- Self-review:
  - every numeric claim in ADR 0011 was recomputed from the repository, not copied;
  - provenance safety is worded as an implementation/test result, because the enum is
    permissive;
  - zero-wrong-value and zero-false-positive claims are scoped to the frozen corpus and
    this invocation;
  - title's 30 realistic cases are described only as smoke/regression expectations;
  - the corpus is described as evaluating seven parsers.

  No executable, fixture, test, schema, or configuration change was found to be needed.
- Observed and left unchanged as out of scope: ROADMAP's historical Phase 2 header
  ("in progress (updated 2026-09-01)"), which is followed by its own completion record;
  and ARCHITECTURE §1.2's `job_skills` rationale, which is still accurate.
- STOP after `A` for Sol's independent review. No `R`, merge, `M`/`Q`, Phase 4, provider
  contact, persistence wiring, or parser change.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-02-phase3-exit-audit-b319168
slice_kind: docs
risk_class: D
base_sha: b31916827c07715bb59f430ad52dd0193561c35b
declared_gate: docs
```
