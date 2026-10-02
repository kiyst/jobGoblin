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

- Date/agent: 2026-10-02, Claude (implementer). Branch `phase-3/title-normalization`,
  base `aed2694720b0344ae54feeef1916805f91e6b508` (Q of the Go/remote correction).
  Ending commit: this commit (candidate `C`).
- Slice: Phase 3 title classifier, Class H, `slice_kind: parser`, `gate: final`.
  Frozen contract, in precedence order: the title-normalization proposal; Sol's
  A1-A12 binding amendment table; Sol's corrected A2/A4/A5 fragment and final
  12-item mutation-witness inventory. Decisions applied: D1 `INFERRED` only; D2 all
  30 realistic titles as smoke/regression cases; D3 `forward deployed engineer`
  unsupported; D4 nine-title vocabulary frozen.
- Files (closed nine-file list, all within it):
  `backend/app/normalization/titles.py` (new),
  `backend/tests/test_normalization_titles.py` (new),
  `backend/tests/fixtures/normalization/title_cases.json` (new),
  `backend/scripts/verification_scope.py`, `backend/tests/test_verification_scope.py`,
  `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, this file.
- Implementation: `classify_title(title) -> TitleResult` (`canonical_title`,
  `role_family`, `outcome`); the exact contract tables, per-segment
  `MATCH`/`AMBIGUOUS`/`NONE` verdicts, and A5/corrected-fragment precedence; the A7
  bounded per-code-point policy (no unrestricted NFKC, no Unicode casefold); the A6
  single approved decoration; the A8 `TitleResult` invariants; and A9 import-time
  table validation (`TitleVocabularyError`). No regular expressions; no record IDs,
  employer names, splits, or per-title exceptions. Imports only the standard library,
  `types.py`, and `identifiers.py`.
- A11: separate exact-path `_TITLE_FIXTURE_FILES` (`title_cases.json` ->
  `test-fixture:title-classifier`) registered at both exact-map sites. Tests cover the
  exact category, disjointness from every other fixture map, no contract family, no
  literal focus target, `unrelated_cases.json` still raising
  `OwnerMappingRequiredError`, and clear-and-restore fault injection.
- Fixture: 200 cases (42 positive, 27 negative, 27 boundary, 17 ambiguity, 21
  collision, 36 unicode, 30 realistic). The expectations were hand-authored, not
  produced by running the parser. Realistic cases are byte-identical to the frozen
  corpus titles (a test enforces this). They are primary-reviewer-approved
  smoke/regression expectations only, never accuracy, holdout, coverage, precision,
  recall, or generalization evidence. Result: 22 matched, 6 unsupported, 2 ambiguous,
  with exactly Sol's per-record lists.
- Unchanged: `python -m scripts.evaluate_phase3_corpus` output is byte-identical to
  its output at `aed2694` (1366 lines). The frozen corpus, annotations, evaluator,
  every other parser, the skill taxonomy, provider mapping, persistence, migrations,
  and APIs are untouched.
- Local checks: 362 focused tests passed (`tests/test_normalization_titles.py` 276,
  `tests/test_verification_scope.py` 86). ruff, ruff format and mypy are clean on the
  changed code. The full suite and all witnesses are left to the coordinator's
  `gate=final` receipt, recorded in `A`.
- Mutation proofs (ad hoc harness against `titles.py`; source restored byte-for-byte,
  SHA-256 verified): **11 of 12 frozen witnesses proven** (01, 03-12). Each failed
  under its mutant and passed after restoration; the positive controls for 03 and 09
  passed both ways.
  **Witness 02 is NOT PROVEN as specified.** `Technical Recruiter Software Engineer`
  stays `AMBIGUOUS` with `PREFIX_BLOCKERS` disabled, because `recruiter` is also in the
  frozen `PREFIX_ROLE_DESIGNATORS`. Every blocker except `of`/`for`/`to`/`and`/`or`/
  `&` is also a designator, so no witness containing one of the others can isolate
  this guard. The guard itself is load-bearing: the non-inventory fixture cases
  `collision_prefix_blocker_and_only` and `collision_prefix_blocker_for_only` both
  fail under the same mutant. The inventory was not changed; that decision is Sol's.
- Self-review (contract-conformance and counterexample passes): no defect found.
  Contract-exact behaviours disclosed for review:
  - The decoration is ignored only when its content is ASCII letters and spaces, so
    `[Expression-of-Interest]` is processed normally (this resolves "normalized tokens
    are exactly" conservatively).
  - `counsels` is not a designator (the frozen set has `counsel` only).
  - `leads` is an allowed prefix (only the later-terminal set contains it).
  - `Software Engineer II` is `unsupported` (an alias must be the suffix).
  - `Software Engineering Manager` is `ambiguous` (A3 `software` signal).
- Environment: one harness write failed with a transient Windows `Errno 22`. The file
  was verified intact, and the harness was rerun with write-retry and hash
  verification. The local Postgres container was started for verification.
- Outside this slice: the 3 remaining `skills.golang` misses (disclosed backlog) and
  the `salary.*` missing-wired-input gap (future provider-composition work).
- STOP after `A` for Sol's independent review. No `R`, merge, persistence wiring,
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
candidate_sha: e2573bc9792e74f60b59fd2b2974141a1a32302b
receipt_id: d8ea060c-298d-473e-93a6-aa6d32b7c7d7
receipt_path: docs/verification-receipts/e2573bc9792e74f60b59fd2b2974141a1a32302b/d8ea060c-298d-473e-93a6-aa6d32b7c7d7.json
fixture_path: backend/tests/fixtures/normalization/title_cases.json
fixture_count: 200
```

## Iteration 2

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
