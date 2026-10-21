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

- Date/agent: 2026-10-20, Claude (implementer). Branch
  `phase-4/normalized-persistence-s3`, base
  `b0bb33ac6c471fed759f33555dc4b681876a8927` (`Q` of the S2c merge). The immutable
  pre-publication advisory candidate `7fd1b94298e0a73a1f08d0abc62872dcb2c113eb` is
  preserved unamended, as is correction 1
  `a6e807e13e9274c3e020bca7c27d913877750583` (its direct child). Ending commit: this
  commit, **correction 2** (correction 1's direct single-parent child), for Sol Medium's
  narrow re-review. None is final `C`: no coordinator run, receipt, `A`, formal review, or
  merge metadata exists.
- Slice: Phase 4 S3, D1 parser version and opt-in normalized persistence
  ([ADR 0018](DECISIONS/0018-d1-parser-version-and-normalized-persistence.md)). Risk
  class H, `slice_kind: tooling`, `declared_gate: final`. Streamlined workflow: Sol Medium
  is the sole reviewer; Astra is not required (no new network, privacy, authorization,
  destructive-cleanup, or threat-model boundary).
- Contract: the consolidated S3 proposal, Sol Medium's binding amendments A1–A6, and the
  user's implementation clarifications 1–8 (all as relayed by the user).
- First check (clarification 5): the 30 reconstructed corpus envelopes, run through the
  real adapter over `httpx.MockTransport`, reproduced the D2 `PostingInputs` exactly (30
  jobs, no warnings or errors), and the non-null `employment_type`, `seniority`, and
  `location.country` outputs equal ADR 0014's `CORRECT` literals exactly (10, 18, 5).
- Implementation:
  - `app/ingestion/normalization_version.py`: the D1 manifest (`jgnorm-v1`). It binds a
    22-module application closure computed from import syntax trees (canonical-LF
    SHA-256 per file), the standard library through the full interpreter version, the
    declared third-party versions (`yaml` with its exact loader hierarchy, `pydantic`,
    `pydantic_core`), the parsed taxonomy content, the Unicode database version, and the
    board/content-mode configuration. Undeclared, unreadable, unresolvable, dynamic,
    relative, or stale evidence fails closed.
  - `app/ingestion/normalized_fields.py`: the builder-only context, the verifier, the
    three-field projection with board binding, and the single-provider merge rule.
  - `app/ingestion/persistence.py`: the projection is computed before Transaction B. On a
    clean outcome it is merged under an explicit `FOR UPDATE` re-select of the
    destination `Job` and `raw.parser_version` is set, in the same transaction. A new
    `_after_normalized_flush` test seam was added.
  - `pipeline.py` verifies the context before any run, provider call, or write.
    `provider_execution.py` passes it through, keeping Phase 2's exact call when it is
    absent.
  - `app/providers/greenhouse_record.py`: the record validation and conversion-gate
    semantics, extracted unchanged from the adapter (the diff shows only the
    method-to-function signature change). `greenhouse.py` gains the read-only
    `board_content_modes` snapshot.
- Tests:
  - new: `tests/test_normalization_version.py` (65), `tests/test_normalized_fields.py`
    (55), and `tests/test_normalized_persistence.py` (19, real PostgreSQL). The primary
    D2 proof runs the 30 envelopes through the real adapter into PostgreSQL and compares
    a fresh reload with the D2 literals;
  - updated for the extraction only: `tests/test_greenhouse_posting_inputs.py` (an import
    moves, two direct calls use the extracted function, the import-set and reachability
    pins change) and `tests/test_greenhouse_s2c_canary.py` (one monkeypatch target
    moves);
  - docs: ADR 0018, plus `DATA_MODEL.md`, `ARCHITECTURE.md`, and `ROADMAP.md` (S2c marked
    complete; S3 entry).
- Verification at `7fd1b94` (offline; the authoring checkout, not a receipt):
  `scripts/verify.py --level routine` (compat mode) passed all 10 checks: Ruff format
    and check, mypy, `check_repo`, `git diff --check`, test-database URL validation and
    reachability, the full suite (**4,748 passed, 1 skipped**), handoff metadata, and
    temporary-directory cleanup. `scripts.contract_mutation_witnesses`: **34 of 34**
    registered witnesses passed. New files alone: 65 + 55 + 19 passed. No row leaked into
    the disposable test database. Migration not triggered (no `app/db/` or migration
    change).
- Advisory evidence (not registered witnesses): 15 temporary mutations of the new
  invariants were applied, and every one was caught; the source was restored
  byte-for-byte. Log `.claude/runtime/phase4-s3-mutation-log.txt` (gitignored), SHA-256
  `91d923b4d230676dc073fe089632bf63cede4da818557d25b22a0dbbfa9c64bd`.
- Production verification vs test evidence: nothing runs in production. All evidence is
  offline tests against the disposable test database. No provider was contacted and no
  new data was captured.
- Retained limitations: listed in ADR 0018. In brief:
  - the guards stop misuse, not hostile in-process code;
  - an abstention never retracts an older value, and no backfill tool exists;
  - cross-provider priority is not implemented;
  - the S2c replay record abstains on all three fields;
  - value evidence is the exposed, reconstructed 30-record corpus only;
  - no accuracy, generalization, live, runtime, or production-readiness claim.
- Workflow metrics so far:
  - proposal reviews: 1 (approved with A1–A6, no second round);
  - advisory and formal reviews: 0;
  - user relays: 3 (one further duplicate relay was not counted);
  - correction commits: 0;
  - receipt runs: 0;
  - elapsed: re-anchor about 04:45Z, implementation start 19:28Z, and this candidate
    about 20:14Z, on 2026-10-20.
- **Correction 1** (Sol Medium's advisory review of `7fd1b94`: changes requested, two
  bounded P1 data-integrity findings; all other portions accepted, as relayed by the
  user):
  - **P1a, unbound Greenhouse semantics.** The adapter still decided values the manifest
    did not hash. `greenhouse_record.py` now also holds `GreenhouseBoard`, a new
    `GreenhouseBoardSet` (the single source of both the snapshot verification binds and
    the board each job is built with), response decoding and JSON parsing, `jobs`
    extraction, and record and duplicate selection, all moved unchanged.
    - `greenhouse.py` keeps transport, timeouts, retries and backoff, media-type and size
      checks, health, and completeness diagnostics only. It passes just a board token and
      the body to `parse_body`, and its snapshot property only returns the board set's.
    - Existing importers, including the frozen S2c harness, are served by explicit
      re-exports.
    - No new module; the closure is still 22 modules. An AST test pins that the adapter
      decodes nothing, reads no content mode, and constructs no job.
    - Named rotation tests cover decoding, JSON configuration, `jobs` extraction,
      kept-record and duplicate selection, the per-job content-mode argument, and
      snapshot derivation. Transport-only edits (retryable statuses, backoff, maximum
      attempts) do not rotate the version.
  - **P1b, hash used as an order.** At equal trust and an equal instant, an identical
    value is a no-op and a differing value now raises `ProvenanceIntegrityError`,
    whatever the parser versions; a parser version is evidence, never an ordering signal.
    A newer version replaces only through a strictly later observation.
    - New pure tests: V1→V2 and V2→V1 conflicts and same-version conflicts are refused;
      identical values are a no-op under any version; the later-observation rule; and
      instant equality across offsets.
    - New PostgreSQL tests: the same three conflict orders, each with full rollback (value,
      provenance, `last_seen_at`, occurrence and raw linkage, run `failed`); and a
      concurrent equal-time agreeing/conflicting pair in both lock orders, where the
      conflict is refused, its Tier 2 attach is rolled back, and the stored state is
      identical.
    - The corpus rerun now shows a newer version is a no-op at the same instant and
      replaces only at a later one.
  - Docs: ADR 0018 (§2 exclusion, §4 extraction, §6 rule 6, §7, limitations), the
    `DATA_MODEL.md` merge paragraph, and the `ARCHITECTURE.md` module note.
  - Tests changed: `test_greenhouse_provider.py` (+3), `test_greenhouse_posting_inputs.py`
    (the adapter import pin drops `json`/`types`), `test_normalization_version.py` (+9),
    `test_normalized_fields.py` (+4, rule 6 rewritten), `test_normalized_persistence.py`
    (+5, rerun rewritten).
  - Verification at `a6e807e` (offline; not a receipt):
    `scripts/verify.py --level routine` passed all 10 checks, including the full
    suite (**4,769 passed, 1 skipped**: the earlier 4,748 plus 21 new tests). Registered
    witnesses: **34 of 34** passed. Affected suites: Greenhouse
    provider/content/bridge/canary/live-proof 1,146 passed; S3 74 + 59 + 24 passed. No row
    leaked into the disposable test database. Migration not triggered.
  - Temporary mutations (advisory, not registered): 21 of 21 caught, including hash
    ordering, silent equal-time keeping, concurrent conflict acceptance, the adapter
    re-deriving the snapshot or decoding, and the board set ignoring a board's own mode.
    The tree was byte-identical after the run. One earlier attempt hit a transient
    Windows file lock while restoring one file; the line was restored by hand and
    checked, and the harness reran from scratch with retries. Log
    `.claude/runtime/phase4-s3-correction1-mutation-log.txt` (gitignored), SHA-256
    `0efab345d5ba7b7fd31f7f0f226ec52ccb2f6baaf7c024cb5c2643195520598f`.
  - Workflow metrics:
    - proposal reviews: 1;
    - advisory reviews: 1 (changes requested);
    - user relays: 4, plus 1 uncounted duplicate;
    - correction commits: 1 (this one);
    - receipt runs: 0;
    - elapsed: correction 1 started at about 21:00Z and this commit is about 21:36Z on
      2026-10-20.
- **Correction 2** (Sol Medium's narrow re-review of `a6e807e`: P1b resolved; one
  remaining P1, as relayed by the user). The unhashed adapter still owned the
  response -> board -> returned-jobs association (`_discover_board`, the token passed to
  `parse_body`, `_aggregate`, the snapshot property). Applied the conservative option
  Sol named:
  - `app.providers.greenhouse` is now a manifest root and is bound whole, which brings in
    `app/schemas/provider.py`; the closure is 24 modules. `httpx` is a declared
    third-party binding, read from installed package metadata
    (`importlib.metadata.version`) so `httpx` stays imported only by the adapter, as S1
    requires. The closure walker allows exactly `importlib.metadata`; any other
    `importlib` use still fails closed.
  - Trade-off, stated in ADR 0018: until a separately reviewed boundary binds the
    response-to-board association independently, any adapter edit, transport-only
    included, rotates the combined version. `greenhouse_record.py` and
    `GreenhouseBoardSet` are retained unchanged in behavior; only their module docstring
    was corrected to say the adapter is bound too.
  - `test_normalization_version.py` (74 -> 88 tests):
    - removed: the transport-only no-rotation claim and test;
    - added: rotation for the board token passed to `parse_body`, aggregated jobs, the
      snapshot property, retryable statuses, backoff, and maximum attempts;
    - added: an unchanged adapter and runtime give the same identifier;
    - added: a context built under each changed adapter fails verification;
    - added: an adapter changed on disk after first observation fails closed;
    - added: an undeclared `httpx` binding fails closed, and the `httpx` version rotates
      the identifier.
  - Docs: ADR 0018 (§2 closure, third-party, conservative adapter binding; §4; a new
    limitation) and the `ARCHITECTURE.md` module note.
  - No Greenhouse behavior, D2 corpus, schema, migration, persisted field, runtime
    activation, or network behavior changed.
  - Verification at this commit (offline; not a receipt):
    - manifest, normalized-field, provider, bridge, content, and normalized-persistence
      suites: 709 passed;
    - S2c canary, canary-mapping, and live-proof adapter suites: 472 passed, 1 skipped;
    - Ruff format and check, mypy (173 files), `check_repo`, `check_handoff`, and
      `git diff --check` all pass;
    - no row leaked into the disposable test database.

    Per the review, no further full-suite run at this advisory stage: the change is the
    manifest boundary, its tests and docs, plus one docstring.
  - Manifest mutations (advisory, not registered): 8 of 8 caught (adapter root dropped,
    record root dropped, `httpx` binding removed or unbound, any `importlib` allowed,
    configuration omitted, micro version dropped, first-seen pin disabled), with the tree
    byte-identical afterwards. Log
    `.claude/runtime/phase4-s3-correction2-mutation-log.txt` (gitignored), SHA-256
    `f8f0f89cd5d6bcfb995964a6f92c530ae7d99d9d13e395f325175831c503f265`.
  - Workflow metrics:
    - proposal reviews: 1;
    - advisory reviews: 2 (both changes requested);
    - user relays: 5, plus 1 uncounted duplicate;
    - correction commits: 2;
    - receipt runs: 0;
    - elapsed: this correction finished at about 22:30Z on 2026-10-20.
- STOP -- for Sol Medium's narrow re-review of correction 2. No final `C`, coordinator
  run, `A`, `R`, merge, provider contact, runtime activation, S4, or S5.
- **Final `C`** (this commit, the direct single-parent child of correction 2
  `a9ee747c5c82d9ed0474bdd8203489471fc7867b`). Changes only this file. It records Sol
  Medium's advisory review of correction 2, verbatim from the structured review result
  (verdict `approved`, findings: none):

> Sol Medium independently reviewed a9ee747c5c82d9ed0474bdd8203489471fc7867b against parent a6e807e13e9274c3e020bca7c27d913877750583 and cumulatively against published S2c base b0bb33ac6c471fed759f33555dc4b681876a8927: advisory approved, no findings. The manifest conservatively binds the entire Greenhouse adapter and extracted record module plus the exact installed httpx version; tests cover association, aggregation, snapshot, retry/backoff edits, determinism, and stale-context rejection. Equal-trust/equal-time identical values remain no-ops; differing values fail closed regardless of parser hash, with later observations required for replacement. Persistence locking, atomicity, rollback, scope, and documentation were inspected directly. Git diff checks and static parsing passed; pytest and database tests were not rerun in this read-only session. This approval authorizes no final C, coordinator execution, receipt, A, formal R, merge, provider contact, activation, cleanup, or further slice.

  - The review's non-authorization sentence was accurate when written. The user later
    explicitly authorized final `C`, one genuine `gate=final` coordinator run, and `A`,
    then a stop. That authorization excludes formal `R`, merge, provider contact,
    cleanup, migration, persistence or runtime activation, and S4.
  - Final `C` differs from the advisory-reviewed `a9ee747` only by this ledger entry. No
    code, test, fixture, configuration, dependency, schema, or semantic document
    changes. Migration is not triggered (no `app/db/` or migration path in
    `b0bb33a..C`).
  - Workflow metrics: advisory reviews 3 (the last approved, no findings); correction
    commits 2; receipt runs: 1 pending, against this `C`.
- Verification: the genuine candidate-bound `verification_coordinator` `gate=final` run
  against this `C` is pending. It is recorded in `A` only if every step passes, cleanup
  completes, and `approval_eligible` is `true`. No provider is contacted.
- STOP after `A` for formal Sol Medium review. No `R`, `M`/`Q`, merge, provider contact,
  cleanup, migration, persistence or runtime activation, S4, or S5.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-20-phase4-normalized-persistence-s3-b0bb33a
slice_kind: tooling
risk_class: H
base_sha: b0bb33ac6c471fed759f33555dc4b681876a8927
declared_gate: final
executed_gate: final
candidate_sha: 06c89b29ef7d8ddedc187e8bb504963bcc04523a
receipt_id: 87b753eb-fd7c-474d-8010-37d6a7b02180
receipt_path: docs/verification-receipts/06c89b29ef7d8ddedc187e8bb504963bcc04523a/87b753eb-fd7c-474d-8010-37d6a7b02180.json
```

### Work review

- Date/reviewer: 2026-10-21 (UTC), Sol (primary, Sol Medium). Formal review of Phase 4 S3,
  D1 parser version and opt-in normalized persistence, on
  `phase-4/normalized-persistence-s3`:
  - base `b0bb33ac6c471fed759f33555dc4b681876a8927`;
  - final candidate `C` = `06c89b29ef7d8ddedc187e8bb504963bcc04523a`;
  - publication `A` = `c08c5c713dd3969209aa48d018d810737f7a91ae`;
  - receipt `87b753eb-fd7c-474d-8010-37d6a7b02180`, SHA-256
    `3f0093dc31d661305431fb606530dd9a87cfd9941b160ffb7b9de2e074e5ad4f`.

  Source: the complete review supplied by the user at
  `.claude/runtime/claude-autopilot/s3-formal-review.md` (gitignored), SHA-256
  `c1fce228b95f9540ebb080d866882288f48ba1259fd0647dc8e7b541e62e4553`, 5,105 bytes.
  `reviewed_at` below is that file's modification time; the review states no time of its
  own. Its durable handoff paragraph, verbatim:

> **Phase 4 S3 formal primary review — approved, no findings (Sol Medium).** Formally reviewed C `06c89b29ef7d8ddedc187e8bb504963bcc04523a`, A `c08c5c713dd3969209aa48d018d810737f7a91ae`, and C-bound receipt `87b753eb-fd7c-474d-8010-37d6a7b02180` (SHA-256 `3f0093dc31d661305431fb606530dd9a87cfd9941b160ffb7b9de2e074e5ad4f`) against published base `b0bb33ac6c471fed759f33555dc4b681876a8927`; approved with no findings. Independent review confirmed exact ancestry and C→A scope; receipt schema, bindings, committed-input hashes, affected surface, focused selector, migration decision, complete 34-guard inventory, and recomputed approval eligibility; whole-adapter, record-module, dependency, runtime, taxonomy and board-configuration D1 binding; verified-context-before-work ordering; opt-in three-field persistence with complete provenance; parser-version-neutral equal-time conflict refusal; explicit row locking, atomicity, rollback and concurrency behavior; the real-adapter 30-record D2 PostgreSQL proof; and accurate documentation and retained limitations. Independently reran the focused selector (806 passed, 1 expected Windows FIFO skip), Ruff formatting/checks, mypy, and repository/handoff/transition/diff checks. Relied on the genuine C-bound receipt for all 12 coordinator steps, the 4,783-test full suite, 34/34 registered witnesses, no migration, and clean disposable-worktree cleanup. This approval is review status, not evidence of runtime activation, provider generalization, broad normalization accuracy, production readiness, or authorization for another provider request or later slice.

- **Independently verified or rerun in formal review** (per the review): exact ancestry
  and C→A scope; receipt schema, bindings, committed-input hashes, affected surface,
  focused selector, migration decision, the complete 34-guard inventory, and recomputed
  approval eligibility; the D1 binding and the persistence, conflict, locking, rollback,
  concurrency, and D2 evidence listed above. Rerun: the focused selector (**806 passed, 1
  expected Windows FIFO skip**), Ruff format and check, mypy (172 source files), and the
  repository, handoff, transition, receipt cross-check, metadata, and diff checks.
- **Relied upon from the genuine C-bound receipt** (not rerun): all 12 final-gate steps
  passed; the full suite (**4,783 passed**); registered witnesses **34 of 34**; migration
  not triggered; disposable-worktree snapshots identical and cleanup without residue.
- Retained limitations: as stated in the paragraph above and in ADR 0018. Approval is
  review status, not runtime activation, provider generalization, broad normalization
  accuracy, production readiness, or authorization for another provider request or
  later slice.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings.
- Exact bounded correction: none required.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-20-phase4-normalized-persistence-s3-b0bb33a
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-21T00:09:53+00:00
candidate_sha: 06c89b29ef7d8ddedc187e8bb504963bcc04523a
publication_commit_sha: c08c5c713dd3969209aa48d018d810737f7a91ae
receipt_path: docs/verification-receipts/06c89b29ef7d8ddedc187e8bb504963bcc04523a/87b753eb-fd7c-474d-8010-37d6a7b02180.json
receipt_id: 87b753eb-fd7c-474d-8010-37d6a7b02180
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-21 (UTC). Merged `phase-4/normalized-persistence-s3` into `main` with
  `git merge --no-ff` at the approved, reviewed commit
  `9319207eca320197f0e3a96088ea52c55fc8fae5` (`R`). `R` records Sol Medium's "approved --
  no findings" formal verdict on `C=06c89b29ef7d8ddedc187e8bb504963bcc04523a` /
  `A=c08c5c713dd3969209aa48d018d810737f7a91ae`.
  - Merge commit `M`: `af849daf908d1ba9eb2655dd67428d1250d1fc92`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `b0bb33ac6c471fed759f33555dc4b681876a8927`.
  - Lineage: base `b0bb33a` -> advisory candidate `7fd1b94` -> correction 1 `a6e807e` ->
    correction 2 `a9ee747` -> `C` `06c89b2` -> `A` `c08c5c7` -> `R` `9319207` -> `M`
    `af849da` -> `Q` (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch, its upstream, and the remote ref sat at `R`; `R`'s sole parent is
    `A`, and `A`'s is `C`; the tree was clean;
  - `main`/`origin/main`/remote `main` were synchronized at the rollback boundary;
  - **receipt `87b753eb-fd7c-474d-8010-37d6a7b02180`** (file SHA-256
    `3f0093dc31d661305431fb606530dd9a87cfd9941b160ffb7b9de2e074e5ad4f`):
    - schema-valid and bound to `C`, the base, the slice, gate `final`, and risk class H;
    - its verifier, checker, and configuration hashes equal the files committed at `C`;
    - the affected surface, focused selector, migration decision (not triggered), and
      complete 34-witness inventory recomputed identically;
    - independently recomputed as approval-eligible;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`, `reviewer_role: primary`,
    `gate: final`, `published_slice_kind: tooling`, and base `b0bb33a`.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, b0bb33a)` passed.
  - `verification_coordinator.run_post_merge_verification` ran once against `M` in a
    disposable detached worktree (always full/final), as one tracked background task the
    user approved because its expected duration approached the 10-minute foreground cap;
    nothing else ran until it exited. It produced artifact
    `8d40847d-2592-46e4-9f83-99f0155b0e46`.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit.
- Post-merge evidence:
  `docs/post-merge/af849daf908d1ba9eb2655dd67428d1250d1fc92/8d40847d-2592-46e4-9f83-99f0155b0e46.json`
  (SHA-256 of the artifact file as written:
  `8310ff1a818f9901bf396e47fa7121e5e7c96ebd5a28e275949b07b1839c6932`). It references
  original receipt `87b753eb-fd7c-474d-8010-37d6a7b02180`.
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- Evidence by source:
  - **Post-merge coordinator (this artifact, at `M`):**
    - all 11 steps PASS: Ruff format and check, mypy, `check_repo`, `git diff --check`,
      disposable test-database URL validation and reachability preflight, the full
      suite, contract mutation witnesses, handoff metadata validation, and
      temporary-directory cleanup;
    - full pytest suite: **4,783 passed**;
    - all 34 registered mutation witnesses passed, 0 failed;
    - no migration triggered;
    - identical initial and final worktree snapshots; worktree removed with no residual
      entry or directory; cleanup PASS;
    - recorded step duration 502.796 seconds.
  - **Pre-merge receipt (at `C`):** all 12 final-gate steps PASS, including focused pytest
    (806) and the full suite (4,783 passed), and 34/34 registered witnesses; migration
    not triggered; cleanup PASS.
  - **Formal review (`R`):** Sol Medium approved with no findings (review file SHA-256
    `c1fce228b95f9540ebb080d866882288f48ba1259fd0647dc8e7b541e62e4553`). Per the review,
    Sol reran the focused selector (806 passed, 1 expected Windows FIFO skip), Ruff, mypy,
    and the repository, handoff, transition, and diff checks, and relied on the receipt
    for the full suite and registered witnesses.
  - **Advisory history (not coordinator-executed, not registered witnesses):** two
    advisory change requests resolved by corrections 1 and 2, the advisory approval
    recorded in `C`, and the temporary mutation logs in `.claude/runtime/`
    (gitignored).
- Network and data boundary: no provider was contacted at any point in S3, no data was
  captured, and no production database or production data was accessed. Every suite run
  used the configured disposable test database.
- Recovery note: an earlier automated attempt created `C` and started a coordinator that
  died without output or receipt. The genuine run's own stage 0 removed that provably
  abandoned scratch directory; its git worktree registration remains listed as
  prunable and was not pruned (no cleanup was authorized).
- Status: merged. S3 adds D1-versioned, opt-in, offline normalized persistence of
  `employment_type`, `seniority`, and `location.country` with provenance for Greenhouse
  jobs ([ADR 0018](DECISIONS/0018-d1-parser-version-and-normalized-persistence.md)). It
  activates no runtime ingestion, provider registration, scheduler, API, or additional
  field. `ROADMAP.md`'s S3 entry still reads "in progress, not merged"; this merge record
  supersedes it until the next slice's documentation update.
- Retained limitations (ADR 0018): the guards stop misuse, not hostile in-process code;
  any Greenhouse adapter edit rotates the parser version; an abstention never retracts an
  older value and no backfill exists; equal-time conflicts abort rather than resolve;
  cross-provider priority is not implemented; value evidence is the exposed,
  reconstructed 30-record corpus only; no accuracy, generalization, live, runtime, or
  production-readiness claim.

  Approval and passing verification are review and verification status, not production
  readiness.
- STOP -- S3 is complete once this `Q` reaches `main`. No S4, S5, runtime activation, or
  provider request without separate authorization.

## Iteration 2

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

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-21-phase4-read-api-s4-2a9c2a9
slice_kind: tooling
risk_class: R
base_sha: 2a9c2a9570d3cb105a376a9b907658f736950be8
declared_gate: final
executed_gate: final
candidate_sha: 0a2e4ad23d6f077b1576998cf45b5b38d7ee2733
receipt_id: 1bf379ae-2337-41ed-b61c-036b1d75b876
receipt_path: docs/verification-receipts/0a2e4ad23d6f077b1576998cf45b5b38d7ee2733/1bf379ae-2337-41ed-b61c-036b1d75b876.json
```
