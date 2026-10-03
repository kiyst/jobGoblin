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
state: published
slice_id: 2026-10-02-phase3-exit-audit-b319168
slice_kind: docs
risk_class: D
base_sha: b31916827c07715bb59f430ad52dd0193561c35b
declared_gate: docs
executed_gate: docs
candidate_sha: 78cfd2077b4370b2d6da3d30843eb9252657ea82
receipt_id: 90d6c6b4-b669-4de2-b36d-4d0470891cd1
receipt_path: docs/verification-receipts/78cfd2077b4370b2d6da3d30843eb9252657ea82/90d6c6b4-b669-4de2-b36d-4d0470891cd1.json
```

## Iteration 2

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
  `C2`, and is left unmodified and undeleted. `C2` needs its own fresh `gate=docs`
  receipt, recorded in `A2`.
- STOP after `A2` for Sol's re-review. No `R`, merge, `M`/`Q`, Phase 4, or executable
  change.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-02-phase3-exit-audit-b319168
slice_kind: docs
risk_class: D
base_sha: b31916827c07715bb59f430ad52dd0193561c35b
declared_gate: docs
```
