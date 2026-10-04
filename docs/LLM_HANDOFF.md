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

- Date/agent: 2026-10-03, Claude (implementer). Branch `phase-4/greenhouse-provider-s1`,
  base `2a72471b95c61b7a1a3e2ae1f944ed40036671b8` (`Q` of the throughput-pilot merge).
  The first immutable pre-publication advisory candidate was
  `1f4bb4e87a2a7db317da3497f152b068773e94ff`; it is preserved unamended. Ending commit:
  this commit, the advisory correction (its direct single-parent child), for Sol
  Medium's narrow advisory re-review. Neither is final `C`: no coordinator run, receipt,
  `A`, or formal review exists.
- Slice: Phase 4 S1, an offline direct `GreenhouseJobBoardProvider` plus
  [ADR 0013](DECISIONS/0013-direct-greenhouse-job-board-provider.md). Pilot product
  slice 1 of 3 under [ADR 0012](DECISIONS/0012-workflow-throughput-protocol-pilot.md).
  Risk class H, `declared_gate: final`. `slice_kind: tooling` is the conservative
  compatibility label required by the current closed schema (`parser | tooling | docs`
  has no provider kind). It is not a claim that provider code is process tooling. No
  schema or validator was changed.
- Contract identity (gitignored runtime packets, not committed):
  - frozen contract `.claude/runtime/phase4-s1-frozen-contract.md`, SHA-256
    `ad3daa68fd34a58aac1fc7f6b77ab7a9afcb1cec7c81a14eed634a8edac82a3c`. It integrates
    the consolidated proposal with Sol Medium's binding proposal review (A1–A15 and
    explicit rulings) and the user's 16-witness reconciliation;
  - Sol's review relay `.claude/runtime/phase4-s1-sol-review.md`, SHA-256
    `5ee125df5ac97bf42fe7f40abcbd9b523022e97bb589756322e0ef3d27d6726c`.
- Dependency-advisory preflight (A14, separately user-authorized, run before branching):
  closure derived from installed metadata (httpx 0.28.1, httpcore 1.0.9, anyio 4.14.2,
  h11 0.16.0, idna 3.19, certifi 2026.7.22, typing-extensions 4.16.0); one read-only OSV
  query per exact PyPI version on 2026-10-03; **zero advisories**. Evidence
  `.claude/runtime/phase4-s1-dependency-advisory-evidence.json`, SHA-256
  `527cdae0f0f244eb6869842b81041d8d2dfd4ffa837dfedf1eb2b951056830e0`. Only `httpx` is
  project-pinned; the transitives are observed versions (no lockfile). ADR 0013 records
  licenses and Sol's exact MPL-2.0 wording.
- Files (exact closed nine-path list):
  - `backend/app/providers/greenhouse.py` (new);
  - `backend/tests/test_greenhouse_provider.py` (new);
  - `backend/pyproject.toml`: `httpx==0.28.1` moved from `dev` to runtime, same pin;
  - `docs/DECISIONS/0013-direct-greenhouse-job-board-provider.md` (new);
  - `docs/ROADMAP.md`, `docs/PHASE_RISK_CHECKLIST.md`, `docs/ARCHITECTURE.md`,
    `docs/SOURCE_CONNECTORS.md`: pointers to ADR 0013 only;
  - this file: rotation. The exit-audit iteration was removed and the pilot-activation
    iteration retained byte-for-byte as Iteration 1.
- Material behavior: A1–A3 board classification and aggregate stats; A4 observed
  health; A5–A7 record, duplicate-identity, and URL validation; A8 media type,
  non-finite JSON, and `meta.total`; A9 one fresh transport and client per `discover`;
  closed retry taxonomy (429/502/503/504, timeouts, connect errors), bounded
  `Retry-After`, streamed size cap, attempt deadline; 225-second conservative default
  bound per board (A11). `raw` is a deep copy of the whole record. No logger; every
  detail, warning, and raised message is a fixed template. Not registered or reachable
  at runtime; no live request, persistence, parser-input mapping, HTML conversion,
  salary behavior, API route, migration, or normalization change.
- Verification at the first advisory candidate `1f4bb4e` (no receipt-producing
  coordinator run):
  - `tests/test_greenhouse_provider.py`: **193 passed**, with zero socket contact and no
    wall-clock retry waiting;
  - the ten provider-related modules (canary, evaluation fetch, Greenhouse provider,
    ingestion pipeline, live-proof adapter, orchestrator, provider registry, query
    planner, taxonomy, db safety): **611 passed**. The pipeline and orchestrator modules
    use the existing local `jobgoblin_test` database as they always do;
  - `ruff format --check`, `ruff check`, and `mypy` on both new Python files: clean;
  - Phase 3 evaluator `python -m scripts.evaluate_phase3_corpus`: SHA-256
    `87a92187a2d37d5150fe998d06042449f6b74d540cecd15d1bba97dd94801de6`, 91,994 bytes,
    1,366 CRLF lines, unchanged;
  - `check_handoff`, `check_repo`, `git diff --check`, and nine-path scope: passed.
- Mutation experiments at `1f4bb4e` (A12, exactly 16; recorded, not registered in
  `tests/contracts`).
  Each anchor occurred exactly once; baseline witness and controls passed; the witness
  failed under the single mutation while its named controls passed; the source was
  restored byte-identically (SHA-256 `04226b7be1a66f1dbbf029070855a7446cbdb5b077b093bbfb4ef8df4d90e965`
  before and after every experiment); the witness then passed. Witness test names drop
  the `test_` prefix:
  - W01 whole-record raw (allowlisted subset) → `t07_raw_is_the_whole_record_structurally`;
  - W02 size cap disabled → `t15_size_cap_stops_reading_the_stream`;
  - W03 `follow_redirects=True` → `t04_redirect_is_not_followed`;
  - W04 HTTP 500 made retryable → `t13_ineligible_failures_make_exactly_one_attempt`;
  - W05 attempt bound off by one → `t13_eligible_failures_stop_at_max_attempts`;
  - W06 `completed=True` always → `t11_all_boards_failed_is_not_completed`;
  - W07 URL boundary reduced to a type check → `t06_url_boundary_rejections_skip_the_record`;
  - W08 timezone check removed → `t06_invalid_timestamps_skip_the_record`;
  - W09 company from `company_name` → `t05_maps_synthetic_record_and_takes_company_from_configuration`;
  - W10 body appended to envelope detail → `t17_envelope_failure_detail_never_contains_the_body`;
  - W11 `Retry-After` cap removed → `t14_retry_after_above_cap_stops_retrying`;
  - W12 deadline check disabled → `t15_attempt_deadline_uses_injected_clock`;
  - W13 source validation disabled → `t03_unsupported_sources_raise_before_transport`;
  - W14 wrong-type optional text treated as absent → `t06_wrong_type_optional_fields_skip_the_record`;
  - W15 duplicate identity `== 1` to `>= 1` → `t20_canonical_duplicates_are_all_skipped`;
  - W16 all-invalid guard removed → `t11_all_invalid_nonempty_response_is_failure_not_successful_empty`.

  Deep-copy/no-alias behavior is T07 regression coverage
  (`t07_raw_is_deep_copied_without_aliasing`), not a mutation witness. The 34
  registered witnesses and their registry are unchanged.
- Deviations and disclosed interpretations (frozen contract, marked for Sol):
  - `sources=[]` creates no transport or client, because no board is queried;
  - a non-object `location` and a whitespace-only `first_published` are malformed;
  - `meta.total` is compared with the number of returned records;
  - "usable hostname" is ASCII dot-separated LDH labels;
  - T20 lists the A6 duplicate-identity tests separately.
  - The socket backups are installed and removed inside the async fixture's own
    lifetime, because pytest-asyncio's Windows teardown loop connects a loopback
    `socketpair`. A first test run exposed this; no production code changed for it.
- Advisory review round 1 (Sol Medium, pre-publication advisory review, not formal
  review). Reviewed `1f4bb4e` against frozen contract `ad3daa68…82a3c`; verdict
  "advisory changes requested". Findings and dispositions:
  - **P1, `Retry-After` escapes the boundary.** A digit-only header was passed to
    `int()`, so a 5,000-digit value raised `ValueError` out of `discover()` instead of a
    categorized one-attempt `RATE_LIMITED` failure. *Accepted and corrected:* the header
    is kept as its digit string; `_bounded_retry_after` strips leading zeroes and treats
    any delta with more significant digits than the cap's integer part as above the cap
    without converting it, so conversion is bounded by the cap's own digit count. Values
    at or below the cap keep their wait; values above it stop retrying; non-digit forms
    keep exponential backoff.
  - **P1, transport closed twice.** `AsyncClient.__aexit__` closes the transport and a
    `finally` block closed it again; tests asserted `closed >= 1` and masked it.
    *Accepted and corrected:* the client context is now the transport's sole owner, and
    tests assert exactly one close on success, anticipated failure, and a propagated
    programming error, plus a close-once transport that raises on a second close.
  - **P2, stale retry claim.** The SOURCE_CONNECTORS Greenhouse row still credited "the
    library's built-in backoff". *Accepted and corrected:* it now says the direct
    adapter applies its own bounded deterministic retry/backoff policy.

  The correction envelope was exactly four paths: `greenhouse.py`, its test module,
  `docs/SOURCE_CONNECTORS.md`, and this file. No ADR, dependency, fixture, registry,
  schema, persistence, normalization, or tooling change. The cumulative base..candidate
  scope is still the same nine paths. The frozen contract is unchanged.
- Verification at this correction (no receipt-producing coordinator run):
  - `tests/test_greenhouse_provider.py`: **204 passed** (11 added). The eight new
    regression tests (exact closure ×3, close-once transport, 5,000-digit delta, and
    three long leading-zero cases) fail against `1f4bb4e`'s adapter and pass here;
  - the same ten-module selection: **622 passed**;
  - `ruff format --check`, `ruff check`, `mypy` on both Python files: clean;
  - Phase 3 evaluator: SHA-256 `87a92187…01de6`, 91,994 bytes, 1,366 CRLF lines,
    unchanged;
  - `check_handoff`, `check_repo`, `git diff --check`, nine-path cumulative scope: see
    the agent's report for this commit;
  - all 16 mutation experiments re-run (not only W11): all passed with byte-identical
    restoration; adapter SHA-256
    `2b5703362f90e719239c45457cac73b7e69e48fdc4026319795c570dc7ae68f0` before and after.
    W11's anchor moved with the fix to the `seconds > cap` comparison in
    `_bounded_retry_after`, with the same witness and controls; the other 15 anchors are
    byte-identical. No seventeenth frozen witness was added.
- Unresolved issues: none known. Limitations: transitive versions unpinned; the OSV
  check is point-in-time; Greenhouse API terms of use remain unreviewed (an S5 blocker).
- Pilot metrics so far: proposal-review rounds 1 (Sol, consolidated, approved with
  A1–A15); advisory-review rounds 1 (changes requested); executable findings 2 (both
  P1) plus 1 documentation finding (P2); pre-`A` correction commits 1 (this commit);
  post-`A` correction commits 0; full-suite executions 0; receipt-producing executions
  0; user relays for S1 so far 5 (decisions, authorization, an identical re-paste of the
  authorization, the Sol-review relay with the 16-witness correction, and the advisory
  findings), including one stop because Sol's amendment text was not yet available in
  the repository or runtime area. Implementation time: branch created
  2026-10-03T20:28:40Z; first candidate committed shortly after 20:41Z.
- STOP after pushing this correction for Sol Medium's narrow advisory re-review. No
  final `C`, coordinator receipt, `A`, formal `R`, merge, `M`/`Q`, Greenhouse contact,
  database access beyond existing local tests, or S2–S5.

**Pre-publication advisory re-review — approved (Sol Medium, advisory only; not formal R).** Reviewed corrected advisory candidate `4a28c5d5e0f713d0d66d6d8c7ee7d0eb7b411212` against frozen-contract SHA-256 `ad3daa68fd34a58aac1fc7f6b77ab7a9afcb1cec7c81a14eed634a8edac82a3c`; all material changes through that SHA were reviewed. The Retry-After overflow, duplicate transport close, and stale connector wording findings are resolved within the authorized four-file correction scope, while cumulative base-to-candidate scope remains the original nine paths. Independent review confirmed 204 focused tests, clean Ruff/mypy and repository checks, unchanged Phase 3 evaluator output, exact one-time transport closure, bounded Retry-After behavior including long digits, leading zeroes and fractional caps, the corrected source hash and unique W11 anchor; the recorded 622-test run, old-implementation substitution, and all 16 mutation experiments with byte-identical restoration were inspected and accepted. The candidate is ready to be designated final C and undergo genuine candidate-bound final verification. This advisory approval is not formal R or merge authorization; formal R retains unrestricted authority.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-03-phase4-greenhouse-provider-s1-2a72471
slice_kind: tooling
risk_class: H
base_sha: 2a72471b95c61b7a1a3e2ae1f944ed40036671b8
declared_gate: final
executed_gate: final
candidate_sha: d9813b492121b78e2fee35113f033eecd59f0a6e
receipt_id: 6489709d-6ab6-4def-ad56-a9da7729de52
receipt_path: docs/verification-receipts/d9813b492121b78e2fee35113f033eecd59f0a6e/6489709d-6ab6-4def-ad56-a9da7729de52.json
```

### Work review

- Date/reviewer: 2026-10-03, Sol (primary, Sol Medium). Formal review of Phase 4 S1, the
  offline direct `GreenhouseJobBoardProvider`, on `phase-4/greenhouse-provider-s1`:
  - base `2a72471b95c61b7a1a3e2ae1f944ed40036671b8`;
  - final candidate `C` = `d9813b492121b78e2fee35113f033eecd59f0a6e`;
  - publication `A` = `dbcb687e5b94d2d629b3411a3cf8f1be3f956e6f`.

  Reviewed against the frozen contract (SHA-256
  `ad3daa68fd34a58aac1fc7f6b77ab7a9afcb1cec7c81a14eed634a8edac82a3c`), which integrates
  Sol's binding amendments A1–A15 and explicit rulings. Sol's two earlier
  pre-publication advisory reviews were advisory only; this is the formal review.
- Independently checked by Sol:
  - **Ancestry and refs:** `C`'s sole parent is `4a28c5d`, `A`'s sole parent is `C`, the
    local and remote branch both equal `A`, the worktree is clean, and
    `main`/`origin/main` remain at the base.
  - **Scope:** `base..C` changes exactly the nine authorized paths. `4a28c5d..C` is the
    handoff-only finalization: the advisory re-review paragraph inserted verbatim before
    valid `state: pending` metadata. `C..A` adds only the C-bound receipt and the
    permitted pending -> published metadata transition.
  - **Implementation identity:** the adapter at `C` has SHA-256
    `2b5703362f90e719239c45457cac73b7e69e48fdc4026319795c570dc7ae68f0`.
  - **Receipt:** receipt `6489709d-6ab6-4def-ad56-a9da7729de52` is schema-valid; bound
    to `C`, the base, gate `final`, the slice, and risk class H; consistent with the
    committed verifier, checker, and configuration hashes; consistent with an
    independently recomputed affected surface and migration determination; covers the
    complete active witness inventory; and recomputes as approval-eligible (`true`).
  - **Focused and static checks:** the 204 provider tests were rerun and passed; Ruff,
    mypy, and repository checks are clean; full-suite collection is exactly 3,674 tests.
  - **Evaluator:** Phase 3 evaluator evidence is unchanged.
  - **Mutation evidence:** the 16 manual S1 mutation definitions and their
    byte-identical restoration evidence were inspected.
  - **Contract:** A1–A15 remain satisfied, and the three advisory findings (unbounded
    `Retry-After` conversion, duplicate transport close, stale connector wording) remain
    resolved.
  - **Boundaries:** no registry or composition-root wiring, live access, persistence,
    parser-input mapping, salary behavior, API route, schema change, or migration.
- Relied upon from the genuine `C` receipt, not rerun by Sol:
  - execution of all 3,674 full-suite tests and the 204 focused tests;
  - the disposable test-database URL validation and reachability checks;
  - execution of 34/34 registered mutation witnesses;
  - isolated-worktree integrity (identical snapshots), cache redirection, and cleanup;
  - worktree removal and leak checks;
  - the recorded environment descriptor and installed-distribution digest.

  The coordinator did not run the 16 manual S1 mutation experiments; they remain
  advisory-candidate evidence and are not registered witnesses.
- Limitations retained:
  - transitive dependencies are not locked (no lockfile);
  - the OSV advisory evidence is point-in-time;
  - Greenhouse's API terms of use remain unreviewed;
  - the adapter is not reachable at runtime;
  - S1 does not satisfy ADR 0011's D1 or D2;
  - S1 does not complete Phase 4.
- Pilot metrics (ADR 0012, pilot product slice 1 of 3), accepted as recorded:
  - proposal-review rounds: 1;
  - advisory-review rounds: 2;
  - findings: 2 executable (P1) and 1 documentation (P2);
  - semantic pre-`A` correction commits: 1;
  - handoff-only finalization commits: 1;
  - post-`A` corrections: 0;
  - full-suite executions through `A`: 1;
  - receipt-producing executions: 1;
  - user relays through `A` publication: 6.

  The relay for this formal review occurred after `A` was published and is outside that
  six-relay boundary.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings. "No unresolved defects currently known" is a
  status statement, not proof of equivalent assurance.
- Exact bounded correction: none required.
- STOP -- record-only. This review authorizes no merge, `M`, `Q`, Greenhouse contact,
  production data access, S2, or change to executable code, policy, validators, schemas,
  dependencies, fixtures, or evidence. Merge requires separate user authorization.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-03-phase4-greenhouse-provider-s1-2a72471
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-03T23:06:46+00:00
candidate_sha: d9813b492121b78e2fee35113f033eecd59f0a6e
publication_commit_sha: dbcb687e5b94d2d629b3411a3cf8f1be3f956e6f
receipt_path: docs/verification-receipts/d9813b492121b78e2fee35113f033eecd59f0a6e/6489709d-6ab6-4def-ad56-a9da7729de52.json
receipt_id: 6489709d-6ab6-4def-ad56-a9da7729de52
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-03. Merged `phase-4/greenhouse-provider-s1` into `main` with
  `git merge --no-ff`, at the approved, reviewed commit
  `a84459f54419a9f786d3793cc79631889bd71fbe` (`R`). `R` is Sol Medium's
  "approved -- no findings" formal verdict on
  `C=d9813b492121b78e2fee35113f033eecd59f0a6e` /
  `A=dbcb687e5b94d2d629b3411a3cf8f1be3f956e6f`.
  - Merge commit `M`: `48cc5c7204ec34ad911d7d9ce9839d9cc49777ea`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `2a72471b95c61b7a1a3e2ae1f944ed40036671b8`.
  - Full lineage: base `2a72471` -> advisory candidate `1f4bb4e` -> advisory correction
    `4a28c5d` -> `C` `d9813b4` -> `A` `dbcb687` -> `R` `a84459f` -> `M` `48cc5c7` ->
    `Q` (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch and its origin both sat at `R`, and `R`'s sole parent is `A`;
  - `main`/`origin/main`/remote `main` were clean and synchronized at the rollback
    boundary;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`,
    `published_slice_kind: tooling`;
  - receipt `6489709d-6ab6-4def-ad56-a9da7729de52` was bound to `C` and independently
    recomputed as approval-eligible.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, 2a72471)` passed.
  - `verification_coordinator.run_post_merge_verification` ran against `M` in a
    disposable detached worktree (always full/final). It produced artifact
    `f788f2db-78ca-46db-8847-7c6fd696728a`:
    - all 11 steps PASS;
    - full pytest suite: **3674 passed**;
    - all 34 registered mutation witnesses passed;
    - no migration triggered;
    - identical worktree snapshots, worktree removed with no residual entry or
      directory, and cleanup PASS.

    No test made a live Greenhouse request; every provider test uses an in-process
    mock transport behind the fixed network guard.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit (this entry).
- Post-merge evidence:
  `docs/post-merge/48cc5c7204ec34ad911d7d9ce9839d9cc49777ea/f788f2db-78ca-46db-8847-7c6fd696728a.json`
  (SHA-256 of the artifact file as written:
  `d0bd9d7b4ceb38556626cde95dfa96ce423a4957fc51ac06a694412f56c037e6`). It references
  original receipt `6489709d-6ab6-4def-ad56-a9da7729de52`
  (`docs/verification-receipts/d9813b492121b78e2fee35113f033eecd59f0a6e/6489709d-6ab6-4def-ad56-a9da7729de52.json`).
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- S1 status: merged. S1 adds an offline provider adapter
  (`GreenhouseJobBoardProvider`) that is not registered or reachable from any runtime
  entry point, plus [ADR 0013](DECISIONS/0013-direct-greenhouse-job-board-provider.md).
  - It does not enable live collection, persist anything, or map provider fields into
    parser inputs.
  - It does not satisfy ADR 0011's D1 or D2.
  - S2 remains unstarted and requires separate authorization. S3–S5 likewise.
  - Phase 4 is not complete.
- Retained limitations: transitive dependencies are not locked; the OSV advisory
  evidence is point-in-time; Greenhouse's API terms of use remain unreviewed; the
  adapter is not runtime-reachable; no D1/D2 satisfaction.
- Pilot metrics through merge (ADR 0012, pilot product slice 1 of 3):
  - proposal-review rounds: 1; advisory-review rounds: 2; formal-review rounds: 1;
  - findings: 2 executable (P1) and 1 documentation (P2), all resolved before `A`;
  - semantic pre-`A` correction commits: 1; handoff-only finalization commits: 1;
    post-`A` corrections: 0;
  - receipt-producing executions: 1 (the clean-path target); full-suite executions:
    2 (the `C` receipt run and the post-merge run at `M`);
  - user relays: 6 through `A` publication, plus the formal-review relay and the merge
    authorization (8 through merge);
  - escaped post-merge defects: none known at merge; newly reachable runtime product
    behavior: none, by design.

  These are measurements, not conclusions; the pilot's exit comparison happens after
  the third slice.
- STOP -- report the synchronized final `main` SHA and stop. No S2, Greenhouse contact,
  runtime provider wiring, production data access, migration, or another slice without
  separate explicit user authorization.

## Iteration 2

### Work done

- Date/agent: 2026-10-03, Claude (implementer). Branch `phase-4/pure-posting-composition-s2`,
  base `0c2c14b573609c6b2dfc67c0d9f14de97c31e03d` (`Q` of the S1 merge). Ending commit:
  this commit, the **immutable pre-publication advisory candidate**, for Sol Medium's
  advisory implementation review. It is not final `C`: no coordinator run, receipt, `A`,
  or formal review exists.
- Slice: Phase 4 S2, a pure provider-neutral `normalize_posting` composition plus scoped
  ADR 0011 D2 protection, and [ADR 0014](DECISIONS/0014-pure-posting-composition-and-scoped-d2.md).
  Pilot product slice 2 of 3 under ADR 0012. Risk class H, `slice_kind: parser`,
  `declared_gate: final`, fixture `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json`
  (30 records). Focused selector: `tests/test_normalization_posting.py
  tests/test_normalization_posting_realistic.py`, **235** tests collected (73 + 162).
  Counts are kept out of the metadata block: the schema has no selector field and the
  receipt cross-validates any duplicated count exactly.
- Contract identity (gitignored runtime packets, never committed):
  - frozen contract `.claude/runtime/phase4-s2-frozen-contract.md`, SHA-256
    `b966b4d4cb9a8ac46c30b5cb65b65280b65239db1b91d986aca1d7b3060a80a2`. It integrates the
    user's authorization, Sol Medium's consolidated proposal review (approved with binding
    amendments A1–A12, which supersede conflicting proposal text), and the proposal;
  - proposal `phase4-s2-proposal.md` `288bb4163cb04d8baeef226764bfa4e92f14780c021b9f0eb9b9dc98d1029c3d`;
    Sol review relay `phase4-s2-sol-review.md` `8f0cfde5120927c3a1d3aaf72fd9724472edd2fbdc3fdc3a3e1df15c4283ebf3`;
  - D2 expectation manifest `phase4-s2-d2-expectation-manifest.json`
    `f480ed2ec0305a7a85987fb9cfca8e1763816c2cad7a50d13203d0893b104d65` and its generator
    `phase4-s2-d2-manifest-generator.py`
    `fff152a4dcd8055aec433191fc9eee4aecd79697656c26766aa414cb4195563c`: derivation and
    review evidence only. The tests never read or require them (A1).
- Files (exact closed seven-path list): `backend/app/normalization/posting.py` (new);
  `backend/tests/test_normalization_posting.py` (new);
  `backend/tests/test_normalization_posting_realistic.py` (new); `docs/DECISIONS/0014-…`
  (new); `docs/ROADMAP.md` (S1 marked merged; S2 bullet); `docs/ARCHITECTURE.md` (§4 tree
  row; §5 note); this file (rotation: the pilot-activation iteration removed, S1's
  iteration retained byte-for-byte as Iteration 1).
- Material behavior: `PostingInputs`/`NormalizedPosting`/`normalize_posting` as frozen —
  validation before any parser call with fixed `TypeError` messages; call order title,
  remote type, employment, seniority, experience, location, skills; exceptions propagate
  and stop later parsers; `result.inputs is inputs`; identical parser result objects;
  skills a new tuple of the identical `SkillMatch` objects; no salary; exact import
  allow-list. Nothing at runtime calls it; no provider, HTML, persistence, `parser_version`,
  migration, or evaluator change.
- D2 durable contract (A1–A9): the realistic module holds literal committed data for the
  30-ID universe, all 13 annotation partitions, correct maps, abstention, confidently-wrong
  and three false-positive sets, the four salary missing-input sets, skills hit/miss/
  false-positive sets, title smoke, the three provenance exceptions, covered/unproven
  lists, and headline totals. Identity pins: corpus canonical JSON
  `ca6e129110b71801e18d6bfba84d59376c689f67cb470f1335ab8805cd388f00`; taxonomy
  canonical-LF `926a2a46cb0c603b953d989f449551af2d1a82cb3b50084a4005e78d7730c67c`
  (D2 evidence identities, not D1). An independent scorer is cross-checked against public
  `evaluate_corpus` (opportunity matrices, runtime failures, per-record mismatch multiset);
  per-record direct-parser equivalence is checked. Totals: 0 runtime failures, 0
  confidently wrong, 0 false positives, skills recall 37/40 (3 known `golang` misses), 56
  supported abstentions, 100 salary gaps, 33 correct values, 159 evaluator mismatches.
  Covered: `employment_type`, `seniority`, `location.country`, plus skills recall.
  Unproven (10): `remote_type`, `experience.minimum`/`maximum`, `location.city`/`state`/
  `postal_code`, and the four `salary.*`. Title smoke only: 22/6/2/0.
- Verification at this candidate (no receipt-producing coordinator run):
  - both new modules: **235 passed**; related existing normalization, title, taxonomy,
    types, evaluator, and freeze modules plus the new ones (14 modules): **1,490 passed**;
    `tests/contracts`: **130 passed**. No database fixture is requested and no network is
    used;
  - `ruff format --check`, `ruff check`, and `mypy` on the three Python files: clean;
  - evaluator `python -m scripts.evaluate_phase3_corpus`: SHA-256
    `87a92187a2d37d5150fe998d06042449f6b74d540cecd15d1bba97dd94801de6`, 91,994 bytes,
    1,366 CRLF lines, unchanged;
  - `check_handoff`, `check_repo`, `git diff --check`, seven-path scope, and runtime-file
    hashes: see the agent's report for this commit.
- Mutation experiments (A10, exactly nine; recorded, not registered). Each anchor occurred
  once in `posting.py`; baseline witness and controls passed; under the single mutation
  every named witness failed and the stable controls passed; the source was restored
  byte-identically (final source SHA-256 `4efe44180eedd042f0200d5cb67cd9422e73cf79d12a0263b716b57c461cef7e`
  before and after each); the witness then passed. All nine were rerun after the self-review fixes. Log
  `.claude/runtime/phase4-s2-mutation-log.json`
  (`0a1a809da7f6e8e026c621ca181ab2a2ab75d5d4dac3606a5aa34aebad9d7663`), driver
  `phase4-s2-mutation-driver.py` (`1de80be18f764454f6584bbd0a6a574734aaeb5710d35c259b07bbb2d2187d92`).
  Witness names drop the `test_` prefix:
  - M1a unused `.salary` import → `import_boundary_is_the_exact_allow_list`;
  - M1b defaulted `salary` field → `normalized_posting_fields_are_exact_with_no_salary`
    (the realistic `salary_is_not_composed_and_stays_unproven` also detects it and was
    deselected from the control run as overlap coverage);
  - M2 seniority title/description swap → `correct_values_are_exact[seniority]`;
  - M3 `None` to location → `correct_values_are_exact[location.country]` and
    `supported_abstentions_are_exact[location.country]`;
  - M4 employment provenance set to `EXPLICIT_SOURCE` via `object.__setattr__` →
    `emitted_provenance_never_claims_explicit_or_structured_sources` and the employment
    provenance test (value sets and the identity test stayed green);
  - M5 `TaxonomyIndex({})` to skills → `skills_recall_hits_are_exact`;
  - M6 employment forced to `full_time` → `false_positive_sets_are_exact[employment_type-false_positive_absent]`;
  - M7 copied `PostingInputs` → `results_pass_through_as_the_identical_objects`;
  - M8 `United States`/`INFERRED` for the unique `Strategic Finance` / `San Francisco Bay
    Area` input (`discord:8575166002`, predicate asserted by
    `m8_input_predicate_matches_exactly_one_record`) → the `location.country` correct and
    abstention tests; false-positive and provenance controls stayed green.
- Deviation for Sol (M8 mechanism): Sol's text mutates "the existing `LocationResult` in
  place". Run literally, that rewrites `classify_location`'s module-level
  `_UNAVAILABLE_RESULT`, the single object returned for every all-unavailable location, so
  every later abstaining record also emitted `United States` and two stable controls
  (`location.country` absent and ambiguous false-positive sets) failed. That attempt's log
  is kept as `phase4-s2-mutation-log-attempt1-inplace-m8.json`
  (`8b0264e0badf4c91e33d855c7d245d9393731e3e5627f3a3c374791fe931ac26`). The recorded M8
  keeps the predicate, value, provenance, witnesses, and controls and builds a new
  `LocationResult` instead. The finding is documented in `posting.py` and ADR 0014:
  results pass through by identity and can be parser-owned shared objects, so callers
  must never mutate them.
- Other disclosed interpretations: a format-character-only title yields `classify_title`'s
  own `unsupported` outcome (its approved contract), not `no_title`; per-record
  direct-parser equivalence lives in the realistic module.
- Adversarial self-review (a fresh read-only subagent, before commit): no P1. Fixed before
  commit:
  - P2-1: ADR 0014 overstated what D2 catches. It now names what is pinned per record and
    what is not (skill-match order, duplicates, and display names). Provenance on `None`
    values and title provenance are fixed by the result types' own invariants;
  - P2-2: the ROADMAP and ARCHITECTURE S2 notes now carry the bounded-claim qualifiers;
  - P3-1: a `PostingInputs` subclass whose attribute reads change between reads could pass
    an unvalidated value to a parser. `_validate` now returns the values it read once and
    checked, and the parsers receive exactly those. The regression test
    `test_parsers_receive_exactly_the_values_that_were_validated` failed against the
    pre-fix code and passes now;
  - P3-2: the static import allow-list cannot see `__import__`, `importlib`, `exec`, or
    `eval`; a separate AST check with synthetic rejections now asserts their absence;
  - P3-3: the per-record provenance test now runs over the covered components and asserts
    they are non-empty; a literal category non-overlap test was added;
  - P3-4: a no-op expression was removed; P3-5: returned skill IDs are asserted to lie
    within the annotated set.

  Accepted unchanged: `str` subclasses pass validation (the `isinstance` contract), and
  the scorer shares the evaluator's category naming, which the literal sets backstop.
- Known limitations: D2 holds only at the composition boundary on an exposed 30-record,
  three-employer corpus; title is smoke-only; ten components are unproven; salary is not
  composed (L4 open); HTML conversion, list-endpoint escaping, and unredacted text are
  unproven; D1 is unsatisfied; the mutation experiments are not registered guards.
- Pilot metrics so far (pilot product slice 2 of 3): proposal-review rounds 1 (Sol,
  approved with A1–A12); advisory-review rounds 0; executable findings 0; pre-`A`
  correction commits 0; post-`A` 0; full-suite executions 0; receipt-producing executions
  0; user relays 3 (the S2 overview request, decisions U1–U7 with the D2 freeze, and this
  authorization with the Sol review relay). Branch created 2026-10-04T01:01:23Z.
- STOP after pushing this candidate for Sol Medium's advisory implementation review. No
  final `C`, coordinator receipt, `A`, formal `R`, merge, `M`/`Q`, Greenhouse contact,
  production data access, or S2b.

**Pre-publication advisory review — approved (Sol Medium, advisory only; not formal R).** Reviewed immutable advisory candidate `d418025aaf1443d9212ced50094800b2756cafb8` against frozen-contract SHA-256 `b966b4d4cb9a8ac46c30b5cb65b65280b65239db1b91d986aca1d7b3060a80a2`; all material changes through that SHA were reviewed, with no advisory findings. Independent review confirmed the exact seven-path scope and clean ancestry; prevalidation and exact parser-input wiring; fixed result fields, call order, pass-through identity and provenance behavior; salary and unauthorized-import exclusion; absence of runtime reachability, provider mapping, persistence, database, migration or network behavior; the bounded D2 accounting and evaluator identity; 235 focused tests, 1,490 related tests, 130 contract tests, clean Ruff/mypy and repository checks. The nine mutation records and byte-identical restoration were inspected and accepted. M8’s new-`LocationResult` mechanism is approved without a replacement witness: literal in-place mutation contaminates `classify_location`’s shared unavailable singleton, while the recorded mutation preserves the exact unique predicate, injected `United States`/`INFERRED` result, required failing witnesses and stable false-positive/provenance controls without unrelated contamination. The candidate remains advisory-only; final candidate-bound verification may proceed, while formal R retains unrestricted authority to reject the slice.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-03-phase4-pure-posting-composition-s2-0c2c14b
slice_kind: parser
risk_class: H
base_sha: 0c2c14b573609c6b2dfc67c0d9f14de97c31e03d
declared_gate: final
fixture_path: backend/tests/fixtures/evaluation/phase3_realistic_corpus.json
fixture_count: 30
```
