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

- Date/agent: 2026-10-02, Claude (implementer). Branch `phase-3/exit-audit`. Bounded
  C2 documentation correction as the direct child of
  `A = 0de449434242f6172cd0c9740f68a0727f6f7d62`.
  `C = 78cfd2077b4370b2d6da3d30843eb9252657ea82` and `A` are preserved unamended (no
  rebase, amend, or force-push). Ending commit: this commit (candidate `C2`).
- Sol's findings, with the correction authorized by the user in a three-file envelope:
  - **F001 (evidence description).** ADR 0011 described the two-input sweep as `(s,
    None)` and `(s, s)`. The approved, independently reproduced method is `(s, None)`
    and `(None, s)`, which isolates title and description independently.
  - **F002 (overbroad wording).** "no parser-version identifier exists" in ADR 0011 and
    ROADMAP was overbroad, because `RawJobIngestion.parser_version` already exists as
    storage. It is replaced with exactly "no Phase 3 normalization-version identifier or
    threading exists".
- Files (exactly three):
  - `docs/DECISIONS/0011-phase-3-exit-audit.md`: the sweep-method sentence (F001) and
    one production-readiness bullet (F002);
  - `docs/ROADMAP.md`: one closure-entry bullet (F002);
  - this file.

  No other wording or evidence changed. The D1 ruling, the nullable `parser_version`
  storage statement, the binding precondition, the combined-pipeline-version allowance,
  D2, the limitations, the evidence totals, the evaluator hash, the `M`/`Q` history, and
  the Phase 4 obligations are unchanged. `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`,
  ADR 0010, and all executable content are byte-identical to `A`.
- Corrected sweep method. The five title/description parsers were called with `(s,
  None)` (title only) and `(None, s)` (description only) for each of the 940 strings.
  `classify_salary`, `classify_location`, and `classify_title` were called once per
  string. The implementer reproduced it read-only with the project venv and no file
  writes. Totals are unchanged and match Sol's independent reproduction:
  - 940 distinct strings;
  - 12,220 parser invocations;
  - 0 exceptions;
  - 0 returned `explicit_source`;
  - 0 returned `structured_metadata`.
- Receipt supersession: `A`'s receipt
  `docs/verification-receipts/78cfd2077b4370b2d6da3d30843eb9252657ea82/90d6c6b4-b669-4de2-b36d-4d0470891cd1.json`
  is **superseded and non-reusable** for this slice's approval. It is bound to `C`, not
  `C2`, and is left unmodified and undeleted. No `A2` exists. The fresh receipt for this
  correction is bound to `C3` and recorded in `A3` (see below).
- **C3 gate-escalation correction (user-authorized; one file, this one).**
  - `C3` is `C2`'s direct single-parent child
    (`C2 = 358234799d4ce9f7478cad162af46a0b93a06c91`). `C`, `A`, and `C2` are preserved
    unamended. Ending commit: this commit (candidate `C3`). `C2` and `C3` together form
    this correction's candidate, and `C3` is the commit verified and published.
  - What happened. The attempted `gate=docs` coordinator run against `C2` stopped during
    its pre-verification affected-surface check. The cumulative `base..C2` diff includes
    `A`'s immutable receipt under `docs/verification-receipts/**`, which
    `scripts/verification_scope.py` classifies as `unmapped`, and an `unmapped` path
    forces `gate=final`.
  - That attempt ran no verification step, created no receipt, and created no temporary
    verification worktree. It was a scope refusal, not a failed verification run.
  - The pending metadata below therefore declares `gate: final`. Risk class stays D and
    `slice_kind` stays `docs`.
  - Final-gate escalation is conservative verification only. It is not executable work
    and not a risk reclassification, and it changes nothing in the Phase 3 closure
    contract. F001, F002, ADR 0011, ROADMAP, ARCHITECTURE, DATA_MODEL, the evidence
    totals, D1, D2, the closure wording, and the Phase 4 obligations are unchanged from
    `C2`.
  - Deferred workflow backlog, requiring separate authorization: classification of
    committed receipt paths during docs-gate correction cycles. Today any correction
    round on a `gate=docs` slice is forced to `gate=final`. This slice does not change
    any verification tooling.
- STOP after `A3` for Sol's re-review. No `R`, merge, `M`/`Q`, Phase 4, tooling fix, or
  executable change.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-02-phase3-exit-audit-b319168
slice_kind: docs
risk_class: D
base_sha: b31916827c07715bb59f430ad52dd0193561c35b
declared_gate: final
executed_gate: final
candidate_sha: c92b9923b25badde06f5a70f05bc0098c3ff2656
receipt_id: d67a0497-6061-4809-9dac-55f6d03cd5f7
receipt_path: docs/verification-receipts/c92b9923b25badde06f5a70f05bc0098c3ff2656/d67a0497-6061-4809-9dac-55f6d03cd5f7.json
```

### Work review

- Date/reviewer: 2026-10-03, Sol (primary). Reviewed the Phase 3 exit-audit correction
  chain on `phase-3/exit-audit`: `C2` (`3582347`), the gate-escalation correction
  `C3` (`c92b9923b25badde06f5a70f05bc0098c3ff2656`), and its publication `A3`
  (`00d977bc8c02719df19dc30f35ae697c6d9271c2`), against the frozen exit-audit contract,
  the F001/F002 correction envelope, and the authorized C3 escalation.
- Verified by Sol against Git and committed content:
  - the original `C` (`78cfd20`) / `A` (`0de4494`) and `C2` remain unamended;
  - `C3` is `C2`'s sole child, and `A3` is `C3`'s sole child;
  - `C2` -> `C3` changes only the latest correction entry in `docs/LLM_HANDOFF.md`;
  - ADR 0011, ROADMAP, ARCHITECTURE, DATA_MODEL, F001/F002, D1/D2, the closure wording,
    the evidence totals, and the Phase 4 obligations are byte-identical to `C2`;
  - the earlier `gate=docs` attempt against `C2` was a scope refusal at the
    pre-verification affected-surface check, before any verification step or worktree
    creation; it produced no receipt and is not a failed verification run;
  - `C3` keeps risk class D and `slice_kind: docs`, declares `gate: final`, and
    contains no `executed_gate`;
  - `A3` changes only the permitted pending -> published transition (adding
    `executed_gate: final`) and adds the fresh receipt;
  - receipt `d67a0497-6061-4809-9dac-55f6d03cd5f7` is schema-valid and bound to `C3`,
    and its verifier, checker, and configuration hashes match the committed files;
  - its affected surface correctly records `docs-only`, `handoff-transition`, and the
    expected `unmapped` classification of the prior receipt;
  - approval eligibility independently recomputes `true`;
  - transition, handoff, repository, and diff validations passed.
- Relied on from the genuine `C3` receipt, not rerun by Sol:
  - all 11 final-gate steps passed;
  - full suite: 3,470 passed;
  - registered mutation witnesses: 34/34 passed;
  - focused tests correctly not run, because no focused target was computed;
  - migration not triggered;
  - identical tracked-tree snapshots, with no untracked files and no leaked worktree;
  - cleanup passed.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no executable findings.
- Exact bounded correction: none required.
- STOP -- record-only. No merge, `M`, `Q`, executable-file change, verification-tooling
  change, or Phase 4 work is authorized by this review.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-02-phase3-exit-audit-b319168
risk_class: D
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-03T03:40:01.908673+00:00
candidate_sha: c92b9923b25badde06f5a70f05bc0098c3ff2656
publication_commit_sha: 00d977bc8c02719df19dc30f35ae697c6d9271c2
receipt_path: docs/verification-receipts/c92b9923b25badde06f5a70f05bc0098c3ff2656/d67a0497-6061-4809-9dac-55f6d03cd5f7.json
receipt_id: d67a0497-6061-4809-9dac-55f6d03cd5f7
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-03. Merged `phase-3/exit-audit` into `main` with `git merge --no-ff`,
  at the approved, reviewed commit `b3f35ff4b7047f571805d8afd6a98569119261ae` (`R`):
  Sol's "approved -- no executable findings" verdict on
  `C3=c92b9923b25badde06f5a70f05bc0098c3ff2656` /
  `A3=00d977bc8c02719df19dc30f35ae697c6d9271c2`.
  - Merge commit `M`: `5dba60c649b6ffae450114a0f33437866e8efa47`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `b31916827c07715bb59f430ad52dd0193561c35b`.
  - Full lineage: base `b319168` -> `C` `78cfd20` -> `A` `0de4494` -> `C2` `3582347` ->
    `C3` `c92b992` -> `A3` `00d977b` -> `R` `b3f35ff` -> `M` `5dba60c` -> `Q` (this
    commit). No `A2` exists, and `A`'s receipt is superseded.
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch and its origin both sat at `R`, and `main`/`origin/main` were both
    clean and synchronized at the rollback boundary;
  - `validate_c_a_r_chain(C3, A3, R)` and `check_merge_eligibility(C3, A3, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`;
  - receipt `d67a0497-6061-4809-9dac-55f6d03cd5f7` was schema-valid, bound to `C3`, had
    matching committed verifier/checker/configuration hashes, and recomputed as
    approval-eligible.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, b319168)` passed.
  - `verification_coordinator.run_post_merge_verification` ran against `M` in a
    disposable detached worktree (always full/final): artifact
    `74fd572f-0c6a-41bd-bdba-088a9bc180b4`, all 11 steps PASS, full pytest suite **3470
    passed**, all 34 registered mutation witnesses passed, no migration triggered,
    identical worktree snapshots, no leftover worktree, and cleanup PASS.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit (this entry).
- Post-merge evidence:
  `docs/post-merge/5dba60c649b6ffae450114a0f33437866e8efa47/74fd572f-0c6a-41bd-bdba-088a9bc180b4.json`,
  which references original receipt `d67a0497-6061-4809-9dac-55f6d03cd5f7`
  (`docs/verification-receipts/c92b9923b25badde06f5a70f05bc0098c3ff2656/d67a0497-6061-4809-9dac-55f6d03cd5f7.json`).
  `check_review.validate_published(C3, A3, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- Phase 3 status: **closed within the approved conservative scope recorded in
  [ADR 0011](DECISIONS/0011-phase-3-exit-audit.md).**
  - Closed means parser-contract completion. It is not production readiness: no Phase 3
    parser is wired into ingestion or persistence, no Phase 3 normalization-version
    identifier or threading exists, providers do not map fields into parser inputs, and
    realistic-text coverage is low.
  - ADR 0011's D1 (deterministic parser-version identifier) and D2 (executable
    realistic-output protection) preconditions remain binding on any future
    normalized-persistence slice.
  - Phase 4, normalized persistence, and provider integration remain unstarted and
    unauthorized.
- STOP -- report the synchronized final `main` SHA and stop. No Phase 4, normalized
  persistence, provider contact, workflow-tooling correction, or another slice without
  separate explicit user authorization.

## Iteration 2

### Work done

- Date/agent: 2026-10-03, Claude (implementer). Branch
  `workflow/throughput-protocol-pilot`, base `6b4d9ea1a2503553c18ef5efd684fc354adf515a`
  (`Q` of the Phase 3 exit-audit merge `M=5dba60c`). Ending commit: this commit
  (candidate `C`).
- Slice: Workflow Throughput Protocol pilot activation, a bounded documentation-policy
  slice. Risk class D and `slice_kind: docs`, matching the precedent of the Phase 3 exit
  audit and the ADR 0008 policy slice: no executable, test, fixture, schema, or
  configuration change. `declared_gate: final`, because `docs/LLM_WORKFLOW.md` is a
  `workflow-governing-doc` under `scripts/verification_scope.py`, and that category
  forces `gate=final`.
- Contract: the user's activation authorization, plus the consolidated, gitignored
  runtime packet `.claude/runtime/workflow-throughput-protocol-pilot.md` (SHA-256
  `0160b6635c2c1b2b24c08faab80f3ed34be946403a5401fa301602318c444405`, verified before
  any edit). The packet itself is not committed.
- Policy consultations, recorded as prose only and not as formal review metadata:
  - Astra approved the protocol with binding amendments A1–A10, all incorporated;
  - Sol approved the amended protocol as compatible with the current v3.2 validators.

  Neither consultation is an `R` for this slice.
- Files (exact closed three-path list):
  - `docs/DECISIONS/0012-workflow-throughput-protocol-pilot.md` (new);
  - `docs/LLM_WORKFLOW.md`: a new "Workflow Throughput Protocol pilot (ADR 0012)"
    subsection inside "Workflow v3.2 (active)", plus a one-sentence pointer in that
    section's status paragraph. No existing requirement was deleted or reworded;
  - this file: two-iteration rotation. The exit-audit `C` entry was removed, and the
    exit-audit correction, Work review, and merge record were retained byte-for-byte as
    Iteration 1.
- Material content:
  - pre-publication advisory review, kept distinct from formal `R`;
  - formal `R` remains authoritative;
  - unchanged Sol Medium requirements;
  - a clean-path target of one final run at `C` and one post-merge run at `M`, as a
    target and not a cap;
  - mutation-witness timing;
  - three correction classes;
  - repository-first handoff;
  - blocking versus preference findings;
  - the docs-correction `unmapped` limitation, with direct-parent-only scope calculation
    prohibited;
  - metrics, exit criteria, deferred changes, and rollback;
  - explicit precedence: existing validator-enforced rules win any conflict.
- ADR 0012's Phase 3 delay evidence was recomputed from committed receipts: 18 receipts
  across the seven Phase 3 slices verified under v3.2, with 6 for the realistic corpus
  (`C`–`C6`) and 1 for the freeze slice. It makes no claim that the pilot is faster or
  equally safe.
- Not changed: `CLAUDE.md`, ROADMAP, validators and verification tooling, tests,
  fixtures, schemas, configuration, reviewer-identity policy, metadata schemas, handoff
  retention, Phase 3 closure, and Phase 4 scope. No executable or schema change. Phase 4
  is not activated. The pilot takes effect only after this slice reaches `Q` on `main`.
- Verification: the genuine `verification_coordinator` `gate=final` run against `C`,
  recorded in `A`.
- STOP after `A` for formal Sol Medium review. No `R`, merge, `M`/`Q`, validator change,
  Phase 4, provider contact, production data access, migration, or persistence wiring.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-03-workflow-throughput-protocol-pilot-6b4d9ea
slice_kind: docs
risk_class: D
base_sha: 6b4d9ea1a2503553c18ef5efd684fc354adf515a
declared_gate: final
executed_gate: final
candidate_sha: c8c18e18545a9b127875040352cc4abf1a638481
receipt_id: e8ef9fe9-b555-40f8-add9-85e12707acde
receipt_path: docs/verification-receipts/c8c18e18545a9b127875040352cc4abf1a638481/e8ef9fe9-b555-40f8-add9-85e12707acde.json
```
