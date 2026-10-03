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

### Work review

- Date/reviewer: 2026-10-03, Sol (primary, Sol Medium). Formal review of the Workflow
  Throughput Protocol pilot activation on `workflow/throughput-protocol-pilot`:
  - base `6b4d9ea1a2503553c18ef5efd684fc354adf515a`;
  - candidate `C` = `c8c18e18545a9b127875040352cc4abf1a638481`;
  - publication `A` = `faf25881af66678622bbb769f0078c4b39916247`.

  Reviewed against the user's activation authorization and the consolidated
  Astra-amended, Sol-approved packet.
- Independently checked by Sol:
  - **Git ancestry and synchronization:** `C`'s sole parent is the base; `A`'s sole
    parent is `C`; the local and remote branch both equal `A`; `main`/`origin/main`
    remain at the base.
  - **Scope:**
    - `base..C` changes exactly the authorized three paths:
      `docs/DECISIONS/0012-workflow-throughput-protocol-pilot.md` (new),
      `docs/LLM_WORKFLOW.md`, and `docs/LLM_HANDOFF.md`;
    - `C..A` adds only the C-bound receipt and the permitted pending -> published
      metadata transition, with `executed_gate: final`.
  - **Policy content and consultation representation:**
    - Astra's A1–A10 amendments are incorporated.
    - Workflow v3.2 authority is unchanged; existing validator-enforced rules win any
      conflict.
    - Clean-path verification targets are explicitly not caps or quotas.
    - Later findings remain unrestricted.
    - The pilot is inactive until this slice's `Q` reaches `main`.
    - Astra's and Sol's policy consultations are recorded as prose only, never as
      formal review metadata.
  - **Delay evidence:** the 18-receipt / seven-slice count in ADR 0012 was reproduced
    from the committed receipts: skill-taxonomy foundation 2, skill classifier 3,
    realistic evaluation corpus 6, realistic-corpus freeze/evaluation 1, baseline
    correction 2, title classifier 2, exit audit 2.
  - **Classification:** risk class D with `slice_kind: docs` is accepted. There is no
    executable, test, fixture, schema, or configuration change, which matches the
    precedent of the Phase 3 exit audit and the ADR 0008 policy slice. `gate: final`
    is the correct treatment, because `docs/LLM_WORKFLOW.md` is a
    `workflow-governing-doc` and that category forces the final gate.
  - **Receipt:** receipt `e8ef9fe9-b555-40f8-add9-85e12707acde` is:
    - schema-valid and bound to `C` and the base;
    - consistent with the committed verifier, checker, and configuration hashes;
    - recorded with affected surface `docs-only`, `handoff-transition`,
      `workflow-governing-doc`;
    - consistent with the complete active witness inventory;
    - approval-eligible, independently recomputed as `true`.
  - **Validations:** the C->A transition, handoff, repository, and diff validations
    passed.
- Relied upon from the genuine `C` receipt, not rerun by Sol:
  - all 11 coordinator steps passed;
  - full suite: 3,470 passed;
  - 34/34 active mutation witnesses passed;
  - migration not triggered;
  - isolated-worktree integrity snapshots identical, with cleanup passing;
  - no residual worktree.

  Sol did not rerun the full suite or the mutation witnesses.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings.
- Exact bounded correction: none required.
- STOP -- record-only. This review authorizes no merge, `M`, `Q`, Phase 4 work, policy
  or tooling change, or other slice. Merge requires separate user authorization.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-03-workflow-throughput-protocol-pilot-6b4d9ea
risk_class: D
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-03T17:09:36.037747+00:00
candidate_sha: c8c18e18545a9b127875040352cc4abf1a638481
publication_commit_sha: faf25881af66678622bbb769f0078c4b39916247
receipt_path: docs/verification-receipts/c8c18e18545a9b127875040352cc4abf1a638481/e8ef9fe9-b555-40f8-add9-85e12707acde.json
receipt_id: e8ef9fe9-b555-40f8-add9-85e12707acde
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-03. Merged `workflow/throughput-protocol-pilot` into `main` with
  `git merge --no-ff`, at the approved, reviewed commit
  `9ea083db0c8fb4c85582b1e26a8b37d0cde5b9dc` (`R`). `R` is Sol Medium's
  "approved -- no findings" verdict on
  `C=c8c18e18545a9b127875040352cc4abf1a638481` /
  `A=faf25881af66678622bbb769f0078c4b39916247`.
  - Merge commit `M`: `baebfd189fa1fdbdd6a4d3e18e9c8018f1c9a656`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `6b4d9ea1a2503553c18ef5efd684fc354adf515a`.
  - Full lineage: base `6b4d9ea` -> `C` `c8c18e1` -> `A` `faf2588` -> `R` `9ea083d` ->
    `M` `baebfd1` -> `Q` (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch and its origin both sat at `R`, and `R`'s sole parent is `A`;
  - `main`/`origin/main` were both clean and synchronized at the rollback boundary;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`;
  - receipt `e8ef9fe9-b555-40f8-add9-85e12707acde` was schema-valid, bound to `C`, and
    independently recomputed as approval-eligible.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, 6b4d9ea)` passed.
  - `verification_coordinator.run_post_merge_verification` ran against `M` in a
    disposable detached worktree (always full/final). It produced artifact
    `7bcc8b38-cb03-4024-ac6a-ec28dfe2b354`:
    - all 11 steps PASS;
    - full pytest suite: **3470 passed**;
    - all 34 registered mutation witnesses passed;
    - no migration triggered;
    - identical worktree snapshots, worktree removed with no residual entry or
      directory, and cleanup PASS.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit (this entry).
- Post-merge evidence:
  `docs/post-merge/baebfd189fa1fdbdd6a4d3e18e9c8018f1c9a656/7bcc8b38-cb03-4024-ac6a-ec28dfe2b354.json`
  (SHA-256 of the artifact file as written:
  `60e770a8990b95dafe1a4ac21c09a14975e0c84a30b81f8bb3f9574d8de5eeb8`). It references
  original receipt `e8ef9fe9-b555-40f8-add9-85e12707acde`
  (`docs/verification-receipts/c8c18e18545a9b127875040352cc4abf1a638481/e8ef9fe9-b555-40f8-add9-85e12707acde.json`).
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- Pilot status: the Workflow Throughput Protocol pilot
  ([ADR 0012](DECISIONS/0012-workflow-throughput-protocol-pilot.md)) becomes active
  only when this `Q` reaches `main`. It then applies to the next three product-oriented
  implementation slices. Existing Workflow v3.2 validator-enforced rules remain
  controlling.
- Phase 4 has not started. Phase 4, normalized persistence, and provider integration
  remain unstarted and unauthorized.
- STOP -- report the synchronized final `main` SHA and stop. No Phase 4 work,
  normalized persistence, provider contact, policy or tooling change, or another slice
  without separate explicit user authorization.

## Iteration 2

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
