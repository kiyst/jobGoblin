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

- Date/agent: 2026-10-21, Claude (implementer; Claude Opus 5.5, coordinating session).
  Branch `phase-4/read-api-s4`, base `2a9c2a9570d3cb105a376a9b907658f736950be8` (`Q` of
  the S3 merge). The pre-publication advisory candidate
  `ab5620f0769eac57dae7eec41ea36def5410a8a6` is preserved unamended. Ending commit: this
  commit, **correction 1** (its direct single-parent child). Neither is final `C`: no
  coordinator run, receipt, `A`, formal review, or merge metadata exists.
- Slice: Phase 4 S4, the local read-only jobs API
  ([ADR 0019](DECISIONS/0019-local-read-only-jobs-api.md)). Risk class R (user
  decision), `slice_kind: tooling`, `declared_gate: final`.
- Contract: the user's S4 product decision (2026-10-21; recorded in ADR 0019), the
  implementation proposal, and one fresh Claude proposal review (changes requested;
  eight findings batched into one amendment). Review artifacts are gitignored under
  `.claude/runtime/claude-autopilot/s4/`. The earlier planning determination that the
  docs left S4 undefined was reviewed by a separate fresh Claude agent and resolved by the
  user's decision.
- Implementation:
  - `app/api/jobs.py` and `app/api/deps.py`: `GET /jobs` and `GET /jobs/{job_id}`. Thin
    routing, no typed parameters (so no 422), fixed JSON errors, and a generic 500 that
    logs only the exception type.
  - `app/services/job_read.py`: strict query and cursor validation, filters with
    literal `ILIKE` escaping, active-only default, `(last_seen_at, id)` cursor
    pagination, and detail with ordered occurrences. A services-owned session runs
    `SET TRANSACTION READ ONLY` lazily and always rolls back.
  - `app/schemas/job_read.py`: response models that forbid extra fields.
  - `app/main.py` registers the router.
  - `docker-compose.yml` binds `127.0.0.1` only.
  - `scripts/seed_demo_jobs.py`: a labelled fixture seeder and remover for the
    disposable test DB only.
- Tests: `tests/test_jobs_api.py` (59) and `tests/test_seed_demo_jobs.py` (3), both on
  real PostgreSQL. They cover exact schemas and forbidden fields, null and company cases,
  the active scope, each filter, wildcard literals, combined filters, equal-timestamp
  cursor pagination, the default and maximum limits, every error case without echo or
  422, error precedence, occurrence ordering, no commit or flush, a write rejected by the
  read-only transaction, leak-free 500s, the Compose bindings, import boundaries, and the
  route inventory.
- Docs: ADR 0019; `ARCHITECTURE.md` (the `api/` session-boundary clarification and the
  `health.py` exception); `ROADMAP.md` (S3 corrected to merged at `M=af849da…` /
  `Q=2a9c2a9…`, plus the S4 entry); the `README.md` demo. `DATA_MODEL.md` is unchanged.
- No migration or `app/db/` change. No file in the S3 D1 closure is edited, so the parser
  version is unchanged; the manifest tests pass.
- Verification at `ab5620f` (offline; the authoring checkout, not a receipt):
  `scripts/verify.py --level routine` passed all 10 checks: Ruff format and
    check, mypy, `check_repo`, `git diff --check`, test-DB URL validation and
    reachability, the full suite (**4,845 passed, 1 skipped**: S3's 4,783 plus 62 new),
    handoff metadata, and temporary-directory cleanup. No row leaked into the disposable
    test DB.
- Retained limitations:
  - unauthenticated, with no user isolation: safe only because of the localhost
    binding;
  - `null` cannot distinguish abstention from never-normalized;
  - fixture data only until S5;
  - `api/health.py`'s direct `db` import remains a recorded exception;
  - the terms acceptance covers personal, localhost use only and is not legal
    clearance.
- Workflow metrics so far:
  - planning reviews: 1 (the determination);
  - proposal reviews: 1 (changes requested, amended);
  - advisory and formal reviews: 0;
  - correction commits: 0;
  - receipt runs: 0;
  - user relays: 1 (the S4 decision).
- **Correction 1**, from advisory review 1 of `ab5620f` by a fresh Claude
  general-purpose agent (read-only; changes requested; one medium and two low findings;
  preserved under `.claude/runtime/claude-autopilot/s4/advisory-review-1.md`):
  - Medium: a cursor that decoded cleanly but held an out-of-range time (year 1 at
    `+01:00`, or 9999-12-31 at `-01:00`) reached PostgreSQL and returned the generic
    500 instead of 400 `invalid_cursor`. Nothing leaked. Fix: `decode_cursor` now
    normalizes the time to UTC inside its guarded block and treats `OverflowError` as
    `invalid_cursor`.
  - Low: tests added for both overflow directions, a non-UTC-offset cursor that denotes
    the same instant, and NULL `title`/`location_raw` rows under filters. The seeder
    refusal test now asserts the specific `RuntimeError`.
  - Low (informational): ADR 0019 §7 now notes FastAPI's fixed default 404/405 bodies
    for unmatched paths, and the UTC cursor normalization.
  - Verification at this commit: Ruff and mypy (180 files) clean; the API, seeder,
    health, and D1 manifest suites pass (158); no row leaked. A temporary mutation that
    removes the UTC normalization makes both overflow cases fail; the file was restored
    byte-identically. The full suite runs in the final-gate coordinator.
  - Workflow metrics: advisory reviews 1; correction commits 1; receipt runs 0.
- STOP -- for a narrow re-review of correction 1. No final `C`, coordinator run, `A`,
  `R`, merge, provider contact, live ingestion, or S5.
- **Final `C`** (this commit, the direct single-parent child of correction 1
  `85e3ccb80e133773349b6aa3d135fceb761891d6`). Changes only this file, recording the
  narrow advisory re-review of correction 1:
  - Reviewer: a fresh Claude general-purpose agent (read-only; Claude Opus 5.5; not Sol,
    Codex, or Astra). Verdict **approved, no findings**. Preserved under
    `.claude/runtime/claude-autopilot/s4/advisory-rereview-1.md`.
  - It confirmed the exact 5-file correction scope and that every hunk maps to an
    advisory finding.
  - Its probe of 32 edge cases passed: 18 unrepresentable or malformed cursor times all
    return 400 `invalid_cursor` with no echo and no 500, 10 valid edge times return 200,
    and 4 non-UTC same-instant cursors paginate identically to UTC.
  - It reran the API and seeder suites (66 passed), plus Ruff, mypy and
    `check_handoff`.
  - Final `C` differs from `85e3ccb` only by this ledger entry. No code, test,
    configuration, dependency, schema, or semantic document changes. Migration is not
    triggered: nothing in `2a9c2a9..C` touches `app/db/` or a migration path.
  - Workflow metrics: proposal reviews 1; advisory reviews 2 (changes requested, then
    approved); correction commits 1; receipt runs 1 pending, against this `C`.
- Verification: the genuine candidate-bound `verification_coordinator` `gate=final` run
  against this `C` is pending. It is recorded in `A` only if every step passes, cleanup
  completes, and `approval_eligible` is `true`. No provider is contacted.
- STOP after `A` for the formal primary review (Sol Medium, as the validator requires
  for tooling slices). No `R`, `M`/`Q`, merge, provider contact, live ingestion, or S5.
- **Formal review of `C=0a2e4ad`/`A=f476248`, and correction 2:**
  - Sol Medium was invoked through the Codex CLI (`codex exec -m gpt-6.1-sol`, medium
    reasoning effort, read-only sandbox, structured output). Artifacts are preserved
    under `.claude/runtime/claude-autopilot/s4/`.
  - Attempt 1 was **blocked**: its command-execution host was missing from the CLI
    install used, so it inspected nothing and approved nothing. Attempt 2 ran the same
    model and prompt with a complete CLI install.
  - Attempt 2 verdict: **changes requested, one P2 finding** (session
    `01a15c3a-3722-7b13-848a-a99f82e109b1`; result SHA-256
    `ea682101619f46f6815e4c2c7efe28de04ce3981109a9c05c3e5c9fdf370bf02`). `_clean_filter`
    trimmed before checking for control characters, so `"\tEngineer\n"` was accepted
    by all five filters, contrary to ADR 0019 §5.
  - Sol independently verified ancestry, the 14-file scope, the unchanged 24-module D1
    closure, receipt integrity and eligibility, and the C→A transition. It relied on
    the receipt for database-backed results.
  - **Correction 2** (this commit, the direct single-parent child of `A=f476248`):
    - control characters are now rejected anywhere in the raw value, before trimming;
      ordinary spaces are still trimmed;
    - 20 regression cases cover leading and trailing control characters on every filter,
      plus a space-trimming test;
    - a temporary mutation that checks after trimming fails all 20 cases (file restored
      byte-identically);
    - the API and seeder suites pass (87), with Ruff and mypy clean.
  - The receipt `1bf379ae…` and `A=f476248` remain valid evidence for `C=0a2e4ad` only;
    a new final `C`, coordinator run, `A`, and formal review are required.
  - Workflow metrics: correction commits 2 (the maximum); formal review attempts 2
    (1 environment-blocked, 1 changes requested); receipt runs 1.
  - The metadata block below returns from `published` to `pending` for the new
    candidate. The superseded publication was `executed_gate: final`,
    `candidate_sha: 0a2e4ad23d6f077b1576998cf45b5b38d7ee2733`, receipt
    `1bf379ae-2337-41ed-b61c-036b1d75b876`; its receipt file stays committed as
    evidence for that `C` only.
- STOP -- for a new final `C` and its single coordinator run.
- **Final `C` (2)** (this commit, the direct single-parent child of correction 2
  `69bb92b9382e854bfedc6d1dc43ac8e182893233`). Changes only this file.
  - It differs from correction 2 only by this ledger entry: no code, test,
    configuration, dependency, schema, or semantic document changes. Migration is not
    triggered: nothing in `2a9c2a9..C` touches `app/db/` or a migration path.
  - Correction 2 answers the single P2 finding of Sol Medium's formal review. Its
    narrow change is reviewed cumulatively in the new formal review; no separate Claude
    advisory pass was run on it.
  - Verification: the genuine candidate-bound `verification_coordinator` `gate=final`
    run against this `C` is pending. It is recorded in `A` only if every step passes,
    cleanup completes, and `approval_eligible` is `true`. No provider is contacted.
  - STOP after `A` for the Sol Medium formal primary review (via the Codex CLI). No
    `R`, `M`/`Q`, merge, provider contact, live ingestion, or S5.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-21-phase4-read-api-s4-2a9c2a9
slice_kind: tooling
risk_class: R
base_sha: 2a9c2a9570d3cb105a376a9b907658f736950be8
declared_gate: final
executed_gate: final
candidate_sha: ce5ad248157018d7ae9cce5519ccd32b19f3ccea
receipt_id: 4d8320ca-98da-4c4b-be42-de7a9173c087
receipt_path: docs/verification-receipts/ce5ad248157018d7ae9cce5519ccd32b19f3ccea/4d8320ca-98da-4c4b-be42-de7a9173c087.json
```

### Work review

- Date/reviewer: 2026-10-21 (UTC), Sol (primary, Sol Medium). Formal review of Phase 4 S4,
  the local read-only jobs API, on `phase-4/read-api-s4`:
  - base `2a9c2a9570d3cb105a376a9b907658f736950be8`;
  - final candidate `C` = `ce5ad248157018d7ae9cce5519ccd32b19f3ccea`;
  - publication `A` = `dd8258380bec0d5d2fe017349080075dc4216a45`;
  - receipt `4d8320ca-98da-4c4b-be42-de7a9173c087`, SHA-256
    `5d6bfb4009d7cddffbfc56a099ee7ad1a27249ef5a39e89de357e2dcca5d121f`.
- Invocation: the coordinating agent ran Sol Medium automatically through the Codex CLI
  (`codex exec -m gpt-6.1-sol`, medium reasoning effort, read-only sandbox, structured
  output), with no user relay.
  - Codex session `01a15c48-7940-72a3-989d-d2717fef539c`.
  - The prompt, result and log are preserved, gitignored, under
    `.claude/runtime/claude-autopilot/s4/sol-formal-3/`. Result SHA-256
    `d09dd2002cef0359a513aedd8f7c92fb86ddba0c9628f8c651441bdb6204cc3d`.
  - `reviewed_at` below is the result file's modification time.
- Earlier formal-review history in this slice, both recorded in Work done above:
  - attempt 1 was environment-blocked and inspected nothing;
  - attempt 2, on the superseded `C=0a2e4ad`/`A=f476248`, requested changes with one P2
    finding, fixed by correction 2.
- Sol's durable handoff paragraph, verbatim:

> Sol Medium formal primary review: approved, no findings, for C=ce5ad248157018d7ae9cce5519ccd32b19f3ccea and A=dd8258380bec0d5d2fe017349080075dc4216a45. Independently verified the complete single-parent chain, 15-path cumulative scope, unchanged 24-module S3 D1 closure and taxonomy, receipt SHA-256/schema/bindings/committed hashes, recomputed affected surface and focused selector, no migration trigger, complete 34-witness inventory, approval eligibility, and permitted C→A metadata transition. Inspected implementation, tests, contract, documentation, and prior review artifacts. Reran repository, handoff, diff, and selected static checks; offline ASGI probes confirmed control rejection before trimming across all five filters, ordinary-space trimming, fixed errors, validation precedence, leak-free failure responses, UTC cursor handling, and rollback on failure. Relied on receipt 4d8320ca-98da-4c4b-be42-de7a9173c087 for the 4,870-test full suite, 87 focused tests, database-backed behavior, and witness execution. No files changed, database accessed, or network service contacted.

- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings.
- Exact bounded correction: none required.
- Approval is review status, not production readiness. It does not authorize provider
  contact, live ingestion, S5, public or LAN exposure, or another slice.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-21-phase4-read-api-s4-2a9c2a9
risk_class: R
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-21T02:30:03+00:00
candidate_sha: ce5ad248157018d7ae9cce5519ccd32b19f3ccea
publication_commit_sha: dd8258380bec0d5d2fe017349080075dc4216a45
receipt_path: docs/verification-receipts/ce5ad248157018d7ae9cce5519ccd32b19f3ccea/4d8320ca-98da-4c4b-be42-de7a9173c087.json
receipt_id: 4d8320ca-98da-4c4b-be42-de7a9173c087
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-21 (UTC). Merged `phase-4/read-api-s4` into `main` with
  `git merge --no-ff` at the approved, reviewed commit
  `60ba63cc83fc6f7cc23754b462c86e3a8eb4b1bf` (`R`). `R` records Sol Medium's "approved,
  no findings" formal verdict on `C=ce5ad248157018d7ae9cce5519ccd32b19f3ccea` /
  `A=dd8258380bec0d5d2fe017349080075dc4216a45`.
  - Merge commit `M`: `ee463cbc353aa4db774f2e9a7c8c506e03065da2`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `2a9c2a9570d3cb105a376a9b907658f736950be8`.
  - Lineage: base `2a9c2a9` -> advisory candidate `ab5620f` -> correction 1 `85e3ccb` ->
    superseded `C` `0a2e4ad` -> superseded `A` `f476248` -> correction 2 `69bb92b` ->
    `C` `ce5ad24` -> `A` `dd82583` -> `R` `60ba63c` -> `M` `ee463cb` -> `Q` (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch, its upstream, and the remote ref sat at `R`; `R`'s sole parent is
    `A`, and `A`'s is `C`; the tree was clean;
  - `main`/`origin/main`/remote `main` were synchronized at the rollback boundary;
  - **receipt `4d8320ca-98da-4c4b-be42-de7a9173c087`** (file SHA-256
    `5d6bfb4009d7cddffbfc56a099ee7ad1a27249ef5a39e89de357e2dcca5d121f`):
    - schema-valid and bound to `C`, the base, the slice, gate `final`, and risk class R;
    - its verifier, checker, and configuration hashes equal the files committed at `C`;
    - the affected surface, focused selector, migration decision (not triggered), and
      complete 34-witness inventory recomputed identically;
    - independently recomputed as approval-eligible;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`, `reviewer_role: primary`,
    `gate: final`, `published_slice_kind: tooling`, and base `2a9c2a9`.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, 2a9c2a9)` passed.
  - `verification_coordinator.run_post_merge_verification` ran once against `M` in a
    disposable detached worktree, as one tracked background task (its duration
    approaches the foreground cap); nothing else ran until it exited. It produced
    artifact `1d1040a6-fab3-413d-8c70-49d6538994ef`.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit.
- Post-merge evidence:
  `docs/post-merge/ee463cbc353aa4db774f2e9a7c8c506e03065da2/1d1040a6-fab3-413d-8c70-49d6538994ef.json`
  (SHA-256 of the artifact file as written:
  `84cb48a1d92c778788b770436c757d6a30f6037a4cc971ea049d61d42f1959f3`). It references
  original receipt `4d8320ca-98da-4c4b-be42-de7a9173c087`.
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push;
  their results are in the agent's final report.
- Evidence by source:
  - **Post-merge coordinator (this artifact, at `M`):** all 11 steps PASS (Ruff format and
    check, mypy, `check_repo`, `git diff --check`, test-database URL validation and
    reachability, full suite, contract mutation witnesses, handoff metadata,
    temporary-directory cleanup). Full suite **4,870 passed**; **34 of 34** registered
    witnesses; migration not triggered; worktree removed with no residue; recorded step
    duration 534.297 seconds.
  - **Pre-merge receipt (at `C`):** all 12 final-gate steps PASS, including focused
    pytest (87), the full suite (4,870), and 34/34 witnesses; migration not triggered;
    cleanup PASS.
  - **Formal review (`R`):** Sol Medium approved with no findings (Codex CLI session
    `01a15c48-7940-72a3-989d-d2717fef539c`). Sol reran the repository, handoff, diff, and
    static checks plus offline ASGI probes, and relied on the receipt for the full suite,
    focused tests, database-backed behavior, and witnesses.
  - **Advisory and formal history** (gitignored artifacts under
    `.claude/runtime/claude-autopilot/s4/`; Claude reviewers attributed as Claude, never
    as Sol):
    - the planning determination and its review;
    - the proposal review and amendments;
    - advisory review 1 (changes requested, fixed by correction 1) and its re-review
      (approved);
    - Sol formal attempt 1 (environment-blocked), attempt 2 (one P2 finding, fixed by
      correction 2), and attempt 3 (approved).
  - **Superseded publication:** receipt `1bf379ae-2337-41ed-b61c-036b1d75b876` and
    `A=f476248` stay in history as evidence for `C=0a2e4ad` only.
- Network and data boundary:
  - no provider was contacted at any point in S4, no data was captured, and no
    production database was accessed;
  - every suite run used the disposable test database;
  - the demo seeder writes only labelled fixture rows to that database.
- Status: merged. S4 adds the local, unauthenticated, read-only jobs API
  (`GET /jobs`, `GET /jobs/{job_id}`;
  [ADR 0019](DECISIONS/0019-local-read-only-jobs-api.md)), bound to localhost by Docker
  Compose, and a fixture-data demo. It performs no ingestion, provider contact, or
  migration. `ROADMAP.md`'s S4 entry still reads "in progress, not merged"; this merge
  record supersedes it until the next slice's documentation update.
- Retained limitations (ADR 0019):
  - no authentication or user isolation, which is safe only because of the localhost
    binding;
  - `null` cannot distinguish parser abstention from never-normalized;
  - fixture data only until S5;
  - `api/health.py`'s direct `db` import is a recorded exception;
  - the terms acceptance covers personal, localhost use only and is not legal
    clearance.

  Approval and passing verification are review and verification status, not production
  readiness.
- STOP -- S4 is complete once this `Q` reaches `main`. S5 (complete live ingestion)
  requires separate authorization; no provider contact, live ingestion, or public
  exposure follows from this merge.

## Iteration 2

### Work done

- Date/agent: 2026-10-21, Claude (implementer; Claude Opus 5.5, coordinating session).
  - Branch: `phase-4/live-ingestion-s5`.
  - Base: `fa761e4efc6c7305bfbb4fdcd95e4415ee22c479`, the `Q` of the S4 merge.
  - Ending commit: this commit, the **offline pre-live advisory candidate**. It is not
    final `C`. No live request, rehearsal, coordinator run, receipt, `A`, formal review,
    or merge metadata exists.
- Slice: Phase 4 S5, one bounded live Greenhouse ingestion into PostgreSQL, read back
  through the S4 API ([ADR 0020](DECISIONS/0020-greenhouse-live-ingestion.md)).
  - Risk class H, `slice_kind: tooling`, `declared_gate: final`.
  - The classification comes from ADR 0013's five-slice table.
- Contract:
  - the user's S5 objective and constraints (2026-10-21);
  - one fresh Claude planning agent's proposal;
  - one fresh Claude proposal review: approve-with-amendments, no blocking finding,
    amendments A1-A10 adopted.

  The artifacts are gitignored under `.claude/runtime/claude-autopilot/s5/`.
- Implementation: `scripts/run_greenhouse_s5_live_ingestion.py` is the only new code.
  - **Composition root.** It runs the unchanged S1 adapter (`discord`,
    `declared-double-escaped`), S3's `build_normalization_context` (its version is checked
    offline before any I/O), `pipeline.run`, and the S4 `create_app()` routes over ASGI.
  - **Reused S2c code**, by import: reservation, Job Object supervision, request
    constants and fingerprint, and failure classification.
  - **Request guard.** It allows one GET only, holds a process-wide one-send latch, sets
    `Accept-Encoding: identity`, enforces the 5 MB and 500-record caps, and keeps the body
    in memory only. Its refusals are not `httpx` exceptions.
  - **Live gates:** the environment gate, the board allowlist, the HEAD SHA on a clean
    tree, the authorization hash, the parser version, and an exclusive attempt directory.
  - **Database.** A generated `jobgoblin_test_s5_<hex>` database is created, migrated with
    `alembic upgrade head`, and checked by both `db_safety` guards. It is always dropped
    and leak-checked unless `--retain-database-on-pass` applies to a PASS.
  - **Supervised worker.** It checks the database is fresh, ingests, checks the counts,
    reads the jobs back through the API, re-observes the same body offline, and writes a
    categorical summary with redacted representative JSON.
  - **Offline `rehearse` mode.** It runs the same machinery with a `MockTransport`
    serving a synthetic envelope.
  - **No change** to `app/`, migrations, the D1 closure, or the parser version.
    `db_safety.py` changes its docstring only.
- Tests: `tests/test_greenhouse_s5_live_ingestion.py` (72), on real PostgreSQL through
  the S3 network guard. They cover:
  - the frozen constants and the offline parser version;
  - every guard refusal;
  - a second `discover()` refused;
  - PASS end to end, with API read-back and re-observation;
  - replay of the committed S2c fixture;
  - the rehearsal envelope;
  - a parser-version mismatch and a non-fresh database refused before any request;
  - nine provider failures, none of which is PASS or writes a row;
  - content abstention, duplicates, a `meta.total` mismatch, and an identity conflict;
  - guard refusals that leave the run `failed` with no raw rows;
  - a failure at posting k (per-posting atomicity, FAIL-CLOSED);
  - cancellation;
  - redaction;
  - every preflight gate;
  - the database-name grammar;
  - the lifecycle and supervisor outcomes with fakes (PASS drop, retention, deadline,
    worker failure, cleanup failure, migration failure);
  - worker mode and gate binding;
  - import and write boundaries.
- Docs:
  - ADR 0020;
  - `ROADMAP.md`: S4 corrected to merged at `M=ee463cb…` / `Q=fa761e4…`, plus the S5
    entry;
  - `ARCHITECTURE.md`: the only context builder;
  - `SOURCE_CONNECTORS.md`: the stale Greenhouse terms note.
- Verification of this candidate (offline, in the authoring checkout; not a receipt):
  - `scripts/verify.py --level routine` passed: Ruff format and check, mypy,
    `check_repo`, `git diff --check`, test-DB URL validation and reachability, the full
    suite, handoff metadata, and cleanup.
  - The exact totals are in the commit report.
  - No row leaked into the disposable test database.
- Network and data: no provider contact, live request, rehearsal, `CREATE DATABASE`, or
  `DROP DATABASE` has occurred.
- Next: Claude advisory review, Sol Medium primary and Astra pre-live reviews, at most one
  batched correction, then the single pre-live authorization packet and a stop.
- Workflow metrics so far:
  - planning agents: 1;
  - proposal reviews: 1;
  - advisory and formal reviews: 0;
  - correction commits: 0;
  - receipt runs: 0;
  - user relays: 0.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-21-phase4-live-ingestion-s5-fa761e4
slice_kind: tooling
risk_class: H
base_sha: fa761e4efc6c7305bfbb4fdcd95e4415ee22c479
declared_gate: final
```
