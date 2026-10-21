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
- **Attempt 1 fidelity decisions and post-run advisory artifacts** (direct child of
  `3d9404b`; this commit).
  - The user authorized provisional fixture and report construction only. That excludes
    publication, commit, push, cleanup, another request, a reservation reset, a receipt,
    `A`, `R`, merge, S3, and S4.
  - Inputs:
    - decisions file `.claude/runtime/phase4-s2c-staging/decisions.json` (gitignored),
      SHA-256 `cce96428beb80274d5b32c7631b4307a9b29aeebaee8c929c5c632d97aef48c8`,
      selecting only ordinal 0 (`first_converted`, excerpt `[0, 1005)`);
    - reviewer `user`.
  - Approved bounded fidelity decisions, for source ordinal 0 only:

    | Decision | Result |
    |---|---|
    | full-capture fidelity | `faithful` |
    | excerpt-replay fidelity | `faithful` |
    | publication safe | `true` |
    | excerpt proper and useful | `true` |
    | lineage and golden expectations correct | `true` |

    These are the user's final decisions; Sol Medium and Astra independently returned the
    same five with no findings. They are bound to fidelity packet SHA-256
    `aea88d58434f28538f68ab812219544c391aebc7e3d9cbb4ef2e56a85d3e4975` and raw capture
    `3bbce131…0c19`.
  - Post-run advisory artifacts, built offline at candidate `3d9404b`. SHA-256 values are
    of the files as written (LF):
    - fixture `backend/tests/fixtures/providers/greenhouse_s2c_projected.json`,
      `d7e14857e3279090709093d71f0c7c26d3e7baf806f35615c3b32520c75b5249`. It was produced by
      the reviewed create-only builder and holds one record: the five-field projection,
      the exact proper excerpt `[0, 1005)`, lineage, aggregates, and golden expectations;
    - report `docs/evaluation/phase4-s2c-live-canary.md`,
      `0b3c136954e31ad5c713eb6e47cbeaac2fcf56b22fb11fc0b2aa0491ef80148c`. Its controlling
      verdict is permanently `FAIL-CLOSED:worker_failed`.
  - The user approved the minimized fixture, report, and replay test for publication to the S2c
    feature branch as the immutable post-run advisory candidate. This is advisory publication
    only: raw cleanup remains pending, and final `C`/`A`/`R`/`M`/`Q` and another request
    remain unauthorized.
  - Validation:
    - `validate_fixture` passes, including the semantic replay;
    - the projection, excerpt, lineage, and golden expectations equal the approved
      packet;
    - all canonical, source, and excerpt hashes recompute;
    - the aggregates equal the run summary;
    - there are no prohibited keys and no screening hits;
    - neither the raw bytes nor the complete source appear in the fixture;
    - the fixture maps to `test-fixture:greenhouse-s2c-canary`, and the report is
      `unmapped`, which forces the final gate.
  - Tracked replay test (a test-only posterity correction, approved separately):
    `backend/tests/test_greenhouse_s2c_canary.py::test_committed_projected_fixture_validates_and_replays`.
    - It loads the committed fixture from `PROJECTED_FIXTURE` and pins its canonical JSON
      SHA-256 `3475e5a441bcee0d068238b3f5ca5ca7653901b71b05370734bda6b10974f503`.
    - It calls the real `validate_fixture(document, taxonomy)`. That runs the independent
      adapter -> converter -> bridge -> composition replay and compares the result with
      the golden expectations.
    - It asserts one selected record (ordinal 0, `first_converted`), the
      complete-response SHA-256 `3bbce131…0c19`, and one replay job with `meta.total` 1.
    - It never reads the retained raw capture, so the minimized fixture stays replayable
      after raw cleanup. It runs under the module's autouse network-denial and
      no-live-side-effects fixtures.
    - The module docstring now describes this one committed real-record fixture.
    - No production or harness source changed; the harness is still `7bcc0edf…9c0`.
      W1–W12 were not re-executed. Correction 3's existing mutation evidence (against
      that unchanged harness) is unchanged and is not attributed to this test-only
      change.
  - Limitation: under `core.autocrlf` a later checkout can change working-file bytes, so
    the cleanup binding must use hashes recomputed from the committed candidate.
  - Correction 3 has two advisory approvals, as relayed. The stale 55-second U1 wording
    disclosure above still applies. A separately authorized corrected live attempt is
    still required.
- **Post-run documentation correction 4** (`408e09e58cf833f72886dfd6e4c8992d3e730089`, the direct single-parent child of
  `ec1a0f01fecced17277084cf12b72bf2d8d05abf`). Scope: exactly
  `docs/DECISIONS/0017-greenhouse-live-canary.md` and this file.
  - **Review input (as relayed by the user; complete text not relayed):**
    - Sol Medium's P2 finding: the ADR status and gate heading were stale;
    - Astra's two mechanical documentation clarifications.
  - **Dispositions** (exact ADR 0017 replacements):
    1. status: "Proposed — pre-live advisory candidate." → "Proposed — post-run advisory
       candidate; S2c has not passed.", with the rest of the paragraph unchanged;
    2. report line: "(path reserved; not yet created)" → "(published as post-run advisory
       evidence; not final-C evidence)";
    3. worker evidence: "All of this is categorical, comes from the run summary written
       before the failure, and is unreviewed:" → "These categorical observations come from
       the run summary written before the worker failure. They were checked during post-run
       advisory review and do not supersede the permanent failed-attempt verdict.";
    4. heading: "Remaining pre-live gates" → "Remaining gates for a corrected live attempt",
       with the gates beneath it unchanged.
  - **Unchanged:** the fixture, report, replay test, harness, ROADMAP, raw artifacts, and
    every evidence value. The hashes stay the same:
    - fixture `d7e14857…5249` (canonical `3475e5a4…f503`);
    - report `0b3c1369…148c`;
    - harness `7bcc0edf…9c0`;
    - raw capture `3bbce131…0c19`.
  - Cleanup must bind to this corrected advisory candidate, not to `ec1a0f0`.
  - Workflow metadata remains pending and unchanged.
  - No cleanup, Greenhouse contact, new request, reservation reset, receipt, `A`, formal `R`,
    merge, or other slice is authorized.
- **Live attempt 2 and its post-run advisory candidate** (`97cf21453bf663ca7d30d7dfc8c071e16c3e039a`, the direct
  single-parent child of `408e09e58cf833f72886dfd6e4c8992d3e730089`). Scope: exactly
  `docs/DECISIONS/0017-greenhouse-live-canary.md`, `docs/evaluation/phase4-s2c-live-canary.md`,
  `docs/ROADMAP.md`, and this file.
  - **Sequence**, each step separately authorized:
    1. the restricted terms/robots refresh and the reviewed retry proposal
       (`1dff80da…66e2`);
    2. the fresh user terms decision (`1a1a2513…ff06`);
    3. the reviewed archive/reset, with one `git ls-remote` returning `408e09e`; attempt 1's
       reservation was archived byte-identically (`18763cf6…0f5e`);
    4. the attempt-2 U1 (`3fb904ac…1653`) and exactly one request at 2026-10-10T19:03:13Z;
    5. the offline preview and fidelity packet;
    6. the user-adopted decisions, then the offline verdict computation.
  - **Observations:**
    - HTTP 200 JSON, User-Agent `python-httpx/0.28.1`;
    - a complete 420,784-byte capture, `43ca81bd…15c5`;
    - 49 records with `meta.total` 49, all valid, retained, and converted; 0 invalid,
      skipped, or duplicate; no incomplete results;
    - components: employment type 48, seniority 30, title 25, skills 29 and 55; the others
      0. These are observations, not accuracy evidence.
  - **Fidelity (option A):** ordinal 0 only (`first_converted`), excerpt `[0, 1005)`, no
    negative sample. Both reviewers found all five points sound, and the user adopted them.
    - preview `7f31b864…acac`, packet `67cb2c50…bce7`, decisions `cce96428…48c8`
      (byte-identical to attempt 1's decisions file);
    - seven-file staging inventory `bbdc7659…04bb`;
    - projection `ebf2e024…` independently equals the attempt-1 fixture
      projection.
  - **Verdict:** **`PASS` with no findings.** Only PASS completes the live-evidence
    requirement. Cleanup is pending and fail-closed. S2c workflow publication needs
    cleanup plus `C`/`A`/`R`/`M`/`Q`.
  - **Reproducibility (option A):** the attempt-1 fixture and replay test are unchanged and
    do not prove attempt-2 fidelity. Attempt 2 has no durable fixture, and its preview and
    raw response are not replayable after cleanup.
  - **Unchanged:** fixture `d7e14857…5249`, replay test, harness `7bcc0edf…9c0`, and all
    other tracked paths. Workflow metadata remains pending.
  - **Limitations:** no broad accuracy, provider generalization, D1/persistence readiness,
    salary, runtime activation, recurring collection, or production readiness. No third
    request is authorized.
- **Post-run correction 5: ADR temporal corrections and the exact-inventory cleanup
  safeguard** (`c274f21ef1c029d0eb59318e6f40c386b76d74f0`, the direct single-parent child of
  `97cf21453bf663ca7d30d7dfc8c071e16c3e039a`). Scope: exactly
  `backend/scripts/run_greenhouse_s2c_canary.py`,
  `backend/tests/test_greenhouse_s2c_canary.py`,
  `docs/DECISIONS/0017-greenhouse-live-canary.md`, and this file. The user selected the
  harness-correction option over a one-use wrapper.
  - **ADR temporal corrections**, exactly the statements identified in review:
    - fixture: created for attempt 1 and preserved unchanged as the sole durable replay
      fixture; it does not prove attempt-2 fidelity;
    - attempt-1 staging: retained at that checkpoint, later removed by verified cleanup at
      `408e09e`, with the reservation in the immutable archive;
    - Correction 3: had not completed a live attempt at that checkpoint, and later served
      as attempt 2's corrected harness;
    - "Evidence limitations" became "Attempt-1 evidence limitations at that checkpoint",
      in past tense, stating that attempt-1 evidence could never make attempt 1 pass and
      that attempt 2 is recorded below.
  - **Expected-inventory manifest** (gitignored, outside staging, create-only, fsynced,
    byte-verified): `.claude/runtime/phase4-s2c-attempt2-expected-inventory.json`, SHA-256
    `7bab5eda4f5abd6cc4529a5793a011f2ea8d13a335c2a6271545a3c9e48b88f0`. It binds:
    - source advisory candidate `97cf214`;
    - raw capture 420,784 bytes, `43ca81bd…15c5`;
    - attempt-2 reservation `0f89c0c1…d329` and attempt-1 archive `18763cf6…0f5e`;
    - fixture `d7e14857…5249` and report `093f59b5…873e`;
    - the exact seven staging entries (path, kind, bytes, SHA-256);
    - canonical inventory `bbdc7659…04bb`.
  - **Harness correction.** `cleanup` now requires `--expected-manifest`,
    `--expected-manifest-sha256`, and `--expected-inventory-sha256`. Before the first
    deletion, `cleanup_staging` → `check_expected_inventory` verifies:
    - the manifest exists, is not a link, is outside staging, and matches the supplied
      SHA-256;
    - the strict schema (exact keys and kind; normalized relative paths with no absolute,
      drive, backslash, `.`, or `..` forms; unique entries; `file`/`dir` kinds only;
      nonnegative strict-int sizes; lowercase SHA-256; sorted order; matching canonical
      inventory hash);
    - the supplied inventory SHA;
    - neither reservation is inside staging, and both match their bound hashes;
    - the raw, fixture, report, and source-candidate (in `base..candidate`) bindings;
    - every expected path resolves beneath the staging root;
    - fresh inventory, refusing links, junctions, reparse points, and other non-regular
      objects;
    - exact structural and canonical equality.

    Any failure is a categorical refusal before deletion. There is no manual fallback or
    retry. The existing publication, raw-absence, and fresh-process checks are kept. The
    attestation adds `expected_manifest` (path and SHA-256), `expected_inventory_sha256`,
    `observed_inventory_sha256`, and `inventory_equal`. A checker or invocation failure now
    yields a failed attestation (exit 1) with `checker_output_valid: false`. **Cleanup was
    not run.**
  - **Tests (temporary synthetic staging only; never the real retained staging):**
    - existing cleanup tests updated to pass a synthetic manifest;
    - added: the success path with its attestation fields;
    - added: 29 refusal cases, each proving every runtime byte unchanged:
      - inventory: missing entry, additional entry, same-size changed bytes, changed size,
        wrong kind in staging or in the manifest;
      - manifest: duplicate entry, malformed hash or size, absolute, drive, traversal, or
        backslash path, extra key, wrong canonical inventory, manifest hash mismatch,
        wrong manifest SHA, missing or invalid manifest, manifest inside staging;
      - bindings: archive changed, reservation changed, source not in history, raw or
        report binding mismatch;
    - added: a reservation inside staging as a target; a symlink; a Windows junction; a
      checker failure through the CLI; the required CLI arguments.
  - **Verification** (no full suite; no broader risk found):
    - harness module: 274 passed, 0 skipped, including the symlink and junction cases;
    - related selection: 1,004 passed;
    - Ruff format/check and mypy clean;
    - `check_handoff`, `check_repo`, and `git diff --check` pass.
  - **W1–W12 manual mutations**, rerun after the final semantic change against harness
    `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429`. No anchor needed to move. These are manual advisory evidence only; no
    coordinator executed them, and the 34 registered witnesses are unchanged.
    - Controls: `tests/test_greenhouse_s2c_canary.py::test_default_invocation_refuses` and `tests/test_greenhouse_s2c_canary.py::test_selection_rule_follows_provider_order`.
    - Every anchor occurred exactly once; the baseline and final runs passed.
    - Log: `.claude/runtime/phase4-s2c-correction5-mutation-log.json`, SHA-256
      `1126f0bea8109ae4e2353efdbc3d048018dfed0f16d19539c2a5770373cf2663`.

  | ID | Mutation | Anchor → replacement | Failing witness (`tests/test_greenhouse_s2c_canary.py::`) | Baseline | Mutant | Restored; SHA-256 |
  |---|---|---|---|---|---|---|
  | W1 | request-shape guard removed | `check_request_shape(request) ⏎ request.headers["Accept-Encoding"]` → `request.headers["Accept-Encoding"]` | `test_request_shape_guard_refuses_before_send[other_board]` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W2 | second-send refusal removed | `if self._capture.request_sent: ⏎ raise CanaryRefusal("second_request_refused")` → (deleted) | `test_second_send_is_refused_before_network` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W3 | live gate enabled by default (env check removed) | `if env.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE: ⏎ raise CanaryRefusal("gate_disabled")` → (deleted) | `test_live_preflight_refuses_without_live_env` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W4 | board allowlist check removed | `if request.board != BOARD_TOKEN: ⏎ raise CanaryRefusal("board_not_allowlisted")` → (deleted) | `test_live_preflight_refuses_non_allowlisted_board` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W5 | Accept-Encoding: identity override removed | `request.headers["Accept-Encoding"] = ACCEPT_ENCODING` → (deleted) | `test_accept_encoding_identity_and_default_user_agent` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W6 | raw capture overwrite instead of exclusive create | `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_EXCL \| getattr(os, "O_BINARY", 0))` → `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_TRUNC \| getattr(os, "O_BINARY", 0))` | `test_exclusive_write_never_overwrites` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W7 | supervisor no longer terminates/kills at the deadline | `stop()` → `pass` | `test_supervisor_terminates_and_reaps_worker_at_deadline` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W8 | retries enabled (max_attempts=3) | `max_attempts=1, max_response_bytes=MAX_RESPONSE_BYTES` → `max_attempts=3, max_response_bytes=MAX_RESPONSE_BYTES` | `test_503_is_inconclusive_with_exactly_one_request` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W9 | response cap raised to 5 MiB (5,242,880) | `MAX_RESPONSE_BYTES: Final = 5_000_000` → `MAX_RESPONSE_BYTES: Final = 5_242_880` | `test_body_over_cap_is_partial_without_complete_hash` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W10 | record cap before conversion removed | `if capture.source_record_count > MAX_SOURCE_RECORDS: ⏎ raise CanaryRefusal("record_cap_exceeded")` → (deleted) | `test_record_cap_is_enforced_before_conversion` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W11 | database-layer import added | `from app.ingestion.hashing import canonical_json_hash  # noqa: E402` → `import sqlalchemy  # noqa: E402, F401 ⏎ from app.ingestion.hashing import canonical_json_hash  # noqa: E402` | `test_harness_imports_only_allowed_modules` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  | W12 | existing-reservation refusal removed from preflight | `if os.path.lexists(paths.reservation): ⏎ raise CanaryRefusal("attempt_already_reserved")` → (deleted) | `test_live_preflight_refuses_existing_reservation` | pass | fail; controls pass | pass; `c9eaf40cae48655179bbdbf33a48a97eb219e41641fbd15173c06002cee62429` |
  - **Retained state, unchanged throughout:**
    - the seven staging artifacts and inventory `bbdc7659…04bb`;
    - the attempt-2 reservation and attempt-1 archive;
    - report `093f59b5…873e` and fixture `d7e14857…5249`.

    No staging or runtime file is tracked. Workflow metadata remains pending.
- **Post-run correction 6: strict fresh-checker contract, operational quiescence, and
  non-regular-object evidence** (`02b9fac0652e8e19c238d4d8422e22e084abea9a`, the direct
  single-parent child of `c274f21ef1c029d0eb59318e6f40c386b76d74f0`). Scope: exactly
  `backend/scripts/run_greenhouse_s2c_canary.py`,
  `backend/tests/test_greenhouse_s2c_canary.py`,
  `docs/DECISIONS/0017-greenhouse-live-canary.md`, and this file.
  - **Findings and dispositions:**
    1. *Permissive checker acceptance* (`all(checks.values())` over any Boolean
       dictionary, so `{}` or a partial dictionary passed): fixed by the strict
       contract below.
    2. *Checker launch failure escaped* (an `OSError` from `subprocess.run` lost the
       already-produced attestation): fixed; categorical failure attestation.
    3. *No operational quiescence boundary* before inventory verification: fixed by the
       bounded one-use model below.
    4. *Non-regular objects*: the guard already existed in `c274f21`
       (`elif not stat.S_ISREG(mode): raise CanaryRefusal("staging_unexpected_object")`
       in `staging_inventory`). No production change; this correction adds regression
       evidence only.
    5. *ADR §5 stale wording* `(path reserved; not yet created)`: corrected.
  - **Strict fresh-checker contract** (`required_checker_keys`, `evaluate_checker`). The
    checker passes only when the launch succeeded, the exit code is 0, stdout parses as
    exactly one JSON object, its key set equals the required set exactly (no missing or
    extra key), and every value is literally `True` (`value is True`; type `bool`). With
    a raw blob the required set is exactly these 14 keys: `staging_root_absent`,
    `known_capture_paths_absent`, `no_staging_residue`, `no_staging_path_in_index`,
    `binding_well_formed`, `head_is_candidate`, `tree_clean`,
    `candidate_descends_from_base`, `report_matches_approval`, `report_screening_clean`,
    `fixture_matches_approval`, `no_runtime_path_in_commit_range`,
    `raw_blob_absent_from_commit_range`, `raw_blob_absent_from_index` (12 without a raw
    blob).
  - **Failure attestation.** The checker invocation is wrapped so no launch failure
    escapes. The already-produced attestation (expected and observed inventories,
    manifest identity, deletion result, bindings, quiescence) is emitted with
    `passed: false`, `checker_failure` set to one fixed category, `checks` (only when the
    shape was exact, else `null`), and the checker identity (`null` if unavailable); the
    command exits 1 and never retries. Categories: `checker_launch_failed`,
    `checker_nonzero_exit`, `checker_output_malformed` (non-JSON, non-object, more than one
    value, or a non-Boolean value), `checker_key_set_mismatch` (missing, extra, or
    substituted keys), `checker_check_failed` (a required value `false`). No exception
    message, stdout fragment, or dynamic path is included.
  - **Operational quiescence boundary** (`check_quiescence`), bounded and one-use; no
    concurrency framework, retry, or timer. It runs first in `cleanup_staging`, after the
    staging-presence check and before every raw, binding, manifest, and inventory
    verification. It refuses, deleting nothing, unless:
    - `--operator-quiescence` (now a required CLI argument) equals exactly
      `single-operator-quiescent`: the operator's affirmative assertion that no live,
      projection, fidelity, post-run, or other cleanup command is running, no other
      command is authorized to write staging, and this cleanup is the sole cooperative
      staging accessor (`quiescence_not_asserted`);
    - neither the runtime directory nor staging is a link, and staging resolves directly
      beneath the expected runtime directory (`staging_path_unexpected`);
    - the reservation holds exactly two JSON objects, `reserved` then a `terminal` record
      with a string outcome (`worker_exit_not_recorded`). *(Superseded by Correction 7:
      not every terminal record proves reaping; only the exact outcome
      `OBSERVED:pending_post_run_review` is accepted, as completion evidence for this
      one-use attempt-2 cleanup only.)*
    The attestation records `quiescence` with the operator assertion,
    `worker_exit_recorded`, `worker_terminal_outcome`, `worker_pid_recorded: false`,
    `staging_path_expected`, and the boundary text. **Limitation:** the harness never
    recorded a worker PID, so OS confirmation of the worker's absence is not available;
    process-table inspection of the other commands is not performed, and the operator
    assertion covers them. A second inventory scan is not claimed to establish
    quiescence. Verbatim disclosure: "This boundary excludes cooperative JobGoblin
    writers under the single-operator authorization model. It does not claim protection
    against a malicious process or privileged OS-level mutation." The retained attempt-2
    reservation has exactly the `reserved` and terminal
    `OBSERVED:pending_post_run_review` records, so the real cleanup will satisfy this
    check without any reservation change.
  - **ADR 0017:** §5 now reads `(created for attempt 1 and preserved unchanged as the sole
    durable replay fixture; it does not prove attempt-2 fidelity)`; §4 adds only the
    quiescence boundary (with the verbatim disclosure) and the strict checker contract
    with its failure categories.
  - **Tests** (temporary synthetic staging only; never the real retained staging). Module
    274 → 316 collected: the Correction 5 checker-failure test was replaced, and 43 tests
    were added:
    - `test_invalid_checker_results_fail_the_attestation` (15 cases through `main`):
      `{}`, partial dictionary, extra key, substituted key, `false`, `1`, `"true"`,
      `null`, non-JSON, empty stdout, JSON array, JSON scalar, two concatenated objects,
      nonzero exit with otherwise valid output, nonzero exit with malformed output. Each
      asserts `passed: false`, its category, exit 1, exactly one checker call, the
      attestation kept, and no sentinel output fragment;
    - `test_exact_all_true_checker_result_passes` (exact 14-key all-true → exit 0);
    - `test_checker_launch_failure_yields_a_failed_attestation` (launch `OSError`, kept
      separate from malformed output and nonzero exit; no message or path leaks);
    - `test_evaluate_checker_categories_are_distinct` (6) and
      `test_required_checker_keys_follow_the_raw_binding`;
    - quiescence: `test_quiescence_is_attested_with_its_boundary`,
      `test_quiescence_not_asserted_refuses_before_verification` (4; inventory never
      scanned), `test_unrecorded_worker_exit_refuses_and_preserves_staging` (8),
      `test_missing_reservation_refuses_quiescence`,
      `test_staging_outside_the_expected_parent_refuses_quiescence`,
      `test_linked_staging_refuses_quiescence`,
      `test_cleanup_cli_requires_the_operator_quiescence_assertion`; each refusal proves
      every runtime byte unchanged;
    - non-regular objects: `test_non_regular_staging_object_is_refused_before_deletion`
      (controlled `S_IFIFO` mode; runs on every host) and
      `test_real_fifo_in_staging_is_refused_before_deletion` (skipped here: no
      `os.mkfifo` on Windows).
    Synthetic cleanup reservations now carry a terminal record; existing cleanup calls
    pass the assertion.
  - **Ad hoc load-bearing checks** (manual, not coordinator-executed; harness restored
    byte-identical): removing the non-regular guard, the Boolean-type check, the exact
    key-set check, the launch wrapper (narrowed to `ValueError`), the quiescence call, or
    the `terminal` requirement each failed its new witness. The `terminal` check first
    survived, so the `second-not-terminal` case was added; all six then failed.
  - **Verification** after the final semantic change (no full suite, no coordinator):
    - harness module: 315 passed, 1 skipped (the real-FIFO case);
    - related selection (harness module plus `test_greenhouse_content`,
      `test_greenhouse_posting_inputs`, `test_greenhouse_provider`,
      `test_greenhouse_html_convert`, `test_canary_greenhouse_mapping`,
      `test_normalization_posting`, `test_normalization_posting_realistic`): 1,219 passed,
      1 skipped; `tests/contracts`: 130 passed;
    - Ruff format/check and mypy clean;
    - `check_handoff`, `check_repo`, and `git diff --check` pass.
  - **W1–W12 manual mutations**, rerun after the final semantic change against harness
    `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c`. No anchor needed to move. Manual advisory evidence only; no coordinator
    executed them, and the 34 registered witnesses are unchanged.
    - Controls: `tests/test_greenhouse_s2c_canary.py::test_default_invocation_refuses` and `tests/test_greenhouse_s2c_canary.py::test_selection_rule_follows_provider_order`.
    - Every anchor occurred exactly once; the baseline and final runs passed.
    - Log: `.claude/runtime/phase4-s2c-correction6-mutation-log.json`, SHA-256
      `e4121415c9e5c77559214726087adcde1cb1ba031fe5df65e13414dbf0cc9e51`.

  | ID | Mutation | Anchor → replacement | Failing witness (`tests/test_greenhouse_s2c_canary.py::`) | Baseline | Mutant | Restored; SHA-256 |
  |---|---|---|---|---|---|---|
  | W1 | request-shape guard removed | `check_request_shape(request) ⏎ request.headers["Accept-Encoding"]` → `request.headers["Accept-Encoding"]` | `test_request_shape_guard_refuses_before_send[other_board]` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W2 | second-send refusal removed | `if self._capture.request_sent: ⏎ raise CanaryRefusal("second_request_refused")` → (deleted) | `test_second_send_is_refused_before_network` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W3 | live gate enabled by default (env check removed) | `if env.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE: ⏎ raise CanaryRefusal("gate_disabled")` → (deleted) | `test_live_preflight_refuses_without_live_env` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W4 | board allowlist check removed | `if request.board != BOARD_TOKEN: ⏎ raise CanaryRefusal("board_not_allowlisted")` → (deleted) | `test_live_preflight_refuses_non_allowlisted_board` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W5 | Accept-Encoding: identity override removed | `request.headers["Accept-Encoding"] = ACCEPT_ENCODING` → (deleted) | `test_accept_encoding_identity_and_default_user_agent` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W6 | raw capture overwrite instead of exclusive create | `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_EXCL \| getattr(os, "O_BINARY", 0))` → `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_TRUNC \| getattr(os, "O_BINARY", 0))` | `test_exclusive_write_never_overwrites` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W7 | supervisor no longer terminates/kills at the deadline | `stop()` → `pass` | `test_supervisor_terminates_and_reaps_worker_at_deadline` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W8 | retries enabled (max_attempts=3) | `max_attempts=1, max_response_bytes=MAX_RESPONSE_BYTES` → `max_attempts=3, max_response_bytes=MAX_RESPONSE_BYTES` | `test_503_is_inconclusive_with_exactly_one_request` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W9 | response cap raised to 5 MiB (5,242,880) | `MAX_RESPONSE_BYTES: Final = 5_000_000` → `MAX_RESPONSE_BYTES: Final = 5_242_880` | `test_body_over_cap_is_partial_without_complete_hash` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W10 | record cap before conversion removed | `if capture.source_record_count > MAX_SOURCE_RECORDS: ⏎ raise CanaryRefusal("record_cap_exceeded")` → (deleted) | `test_record_cap_is_enforced_before_conversion` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W11 | database-layer import added | `from app.ingestion.hashing import canonical_json_hash  # noqa: E402` → `import sqlalchemy  # noqa: E402, F401 ⏎ from app.ingestion.hashing import canonical_json_hash  # noqa: E402` | `test_harness_imports_only_allowed_modules` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  | W12 | existing-reservation refusal removed from preflight | `if os.path.lexists(paths.reservation): ⏎ raise CanaryRefusal("attempt_already_reserved")` → (deleted) | `test_live_preflight_refuses_existing_reservation` | pass | fail; controls pass | pass; `307c7df6dc7c5a60871e4ab0e8532be2de6ac3170dca519d8fd2e91ef2d0f06c` |
  - **Retained state, unchanged throughout** (verified before and after):
    - the seven staging artifacts and inventory `bbdc7659…04bb`;
    - the attempt-2 reservation `0f89c0c1…d329` and attempt-1 archive `18763cf6…0f5e`;
    - the expected-inventory manifest `7bab5eda…88f0`;
    - report `093f59b5…873e` and fixture `d7e14857…5249`.

    **Cleanup was not run.** No request was made. No staging or runtime file is tracked
    or staged. Workflow metadata remains pending.
- **Post-run correction 7: exact accepted worker outcome and pre-deletion cleanup
  identities** (`2232d9693b54a225bf87d23ec5d65898a081602f`, the direct single-parent child
  of `02b9fac0652e8e19c238d4d8422e22e084abea9a`). Scope: exactly
  `backend/scripts/run_greenhouse_s2c_canary.py`,
  `backend/tests/test_greenhouse_s2c_canary.py`,
  `docs/DECISIONS/0017-greenhouse-live-canary.md`, and this file.
  - **Findings and dispositions:**
    1. *Any string terminal outcome was accepted as worker-exit evidence* (including
       `FAIL-CLOSED:worker_termination_unconfirmed`): fixed. Quiescence now accepts only
       exactly one `reserved` record then one `terminal` record whose outcome is exactly
       `OBSERVED:pending_post_run_review` (`ACCEPTED_WORKER_OUTCOME`).
    2. *Checker identity and executing SHA were acquired after deletion as optional
       values*: fixed. Both are captured and validated before cleanup is invoked and
       passed unchanged into the attestation.
    3. *`passed` depended only on the checker result*: fixed. `cleanup_passed` also
       requires the complete identities.
    4. *Correction 6 wording that every terminal record proves reaping* (function
       docstring, ADR §4, this file's Correction 6 record): corrected to the narrow
       statement below; the Correction 6 record carries an inline supersession note in
       place of that claim.
  - **Exact accepted outcome.** Not every terminal record proves reaping. The supervisor
    writes `OBSERVED:pending_post_run_review` only on the reviewed path where the worker
    exited zero after supervision and wrote its summary (no containment failure,
    unconfirmed termination, deadline, or worker failure). For this one-use attempt-2
    cleanup, with the reservation hash-bound by the expected-inventory manifest, that
    exact outcome is accepted as worker-completion evidence for this cleanup only. Every
    other outcome refuses with the fixed category `worker_outcome_not_accepted` (no
    outcome value is ever output), before expected-inventory verification and before
    deletion: any `FAIL-CLOSED` (including `worker_termination_unconfirmed`,
    `worker_failed`, `outer_deadline`, `containment_assignment_failed`,
    `supervisor_exception`, `supervisor_interrupted`, `staging_exists`), `INCONCLUSIVE`
    with or without a kind, unknown outcomes (including case and whitespace variants),
    and missing or non-string outcomes. Wrong record counts, reordered records, a second
    `reserved` record in place of the terminal record, and malformed or non-object lines
    refuse as `worker_exit_not_recorded`. **Limitation retained:** this does not
    establish malicious-process exclusion, the harness records no worker PID, and
    unconfirmed termination is never acceptable. The retained attempt-2 reservation's
    terminal outcome is exactly the accepted value, so no reservation change is needed.
  - **Identities captured before deletion** (`_checker_path`,
    `capture_cleanup_identities`), in `_dispatch` before `cleanup_staging` is called.
    The checker must exist, be a regular, non-link, non-reparse file, resolve to the
    current harness file, and have a valid lowercase SHA-256. The executing Git SHA must
    be obtainable, 40 lowercase hex characters, and exactly the binding's candidate. The
    tracked tree and candidate binding are then still checked by the existing
    pre-deletion publication checks. Refusals are fixed categories with exit 2:
    `checker_identity_unavailable`, `checker_identity_invalid`,
    `executing_sha_unavailable`, `executing_sha_invalid`, `executing_sha_not_candidate`.
    Cleanup is not invoked, the checker is not launched, and nothing is retried.
  - **Post-deletion success** (`cleanup_passed`). `passed: true` requires a complete
    pre-captured checker identity (exactly `path` and a valid `sha256`, path equal to the
    harness file name), a pre-captured executing SHA equal to the bound candidate, and no
    checker failure category (launch, zero exit, one exact all-true object). After
    deletion, a checker launch, output, or check failure keeps all deletion and inventory
    evidence and both pre-captured identities, with `passed: false`, the existing
    Correction 6 category, and exit 1, never retried.
  - **ADR 0017 §4:** the exact accepted outcome, the rejected outcomes, the narrow
    completion-evidence statement and retained limitation, identity capture before
    deletion, the success conjunction, and preservation of failed-attestation evidence.
    No live-run, fidelity, `PASS`, report, or option-A evidence was reopened.
  - **Tests** (temporary synthetic staging only). Module 316 → 363 collected: 48 added,
    and the `no-outcome` case moved from the structural test to the outcome test.
    - `test_rejected_terminal_outcomes_refuse_before_inventory_verification` (18 cases):
      seven `FAIL-CLOSED` outcomes, `INCONCLUSIVE` with and without a kind, an unknown
      `PASS`, an unknown `OBSERVED`, case and trailing-space variants, a missing outcome,
      and `null`, integer, Boolean, and list outcomes. Each proves
      `check_expected_inventory` and `staging_inventory` are never reached, no deletion
      occurs, and every runtime byte is unchanged. The structural test
      (`test_unrecorded_worker_exit_refuses_and_preserves_staging`, 7 cases) gained the
      same proof.
    - `test_rejected_outcome_refusal_is_categorical_through_the_cli`: exit 2, a
      categorical line, and no outcome text in the output.
    - Pre-deletion identity refusals through the CLI, each proving cleanup and the
      checker were never invoked, exit 2, no sentinel leak, and every runtime byte
      unchanged:
      - `test_checker_hash_failure_refuses_before_deletion`;
      - `test_malformed_checker_hash_refuses_before_deletion`;
      - `test_missing_checker_path_refuses_before_deletion`;
      - `test_linked_checker_path_refuses_before_deletion` (real symlink; ran here);
      - `test_reparse_or_non_regular_checker_refuses_before_deletion` (reparse attribute;
        FIFO mode);
      - `test_checker_that_is_not_the_harness_file_refuses_before_deletion` (directory;
        byte-identical copy elsewhere);
      - `test_executing_sha_lookup_failure_refuses_before_deletion`;
      - `test_malformed_executing_sha_refuses_before_deletion` (5);
      - `test_executing_sha_other_than_the_candidate_refuses_before_deletion`.
    - `test_identities_are_captured_once_before_deletion`: the checker hash and
      `rev-parse` occur once, before cleanup, and never after.
    - `test_success_requires_every_identity_and_check` (11) and
      `test_all_true_checker_cannot_pass_without_complete_identities` (2).
    - The Correction 6 launch-failure, malformed/partial/failed-output matrix, and
      all-true tests now also assert the pre-captured checker identity and executing SHA.
    - Synthetic reservations use the exact accepted outcome.
      `test_reservation_blocks_rerun_after_cleanup` now drives the real supervisor path to
      `OBSERVED:pending_post_run_review` (an `INCONCLUSIVE` outcome is now correctly
      refused).
  - **Ad hoc load-bearing checks** (manual, not coordinator-executed; harness restored
    byte-identical each time). Fourteen mutants were each killed by their new witness:
    - exact-outcome and outcome-type checks;
    - removal of the capture call;
    - the missing-path, link/regular, is-harness, and hash-validity checks;
    - the hash `OSError` handling, the executing-SHA lookup handling, and the format and
      candidate checks;
    - the `passed` conjunction, and its identity and executing terms.
    The conjunction first survived at the CLI (capture already guarantees validity), so
    `test_all_true_checker_cannot_pass_without_complete_identities` was added.
  - **Verification** after the final semantic change (no full suite, no coordinator):
    - harness module: 362 passed, 1 skipped (the real-FIFO case; no `os.mkfifo`);
    - related selection (as in Correction 6): 1,266 passed, 1 skipped;
    - `tests/contracts`: 130 passed;
    - Ruff format/check and mypy clean;
    - `check_handoff`, `check_repo`, and `git diff --check` pass.
  - **W1–W12 manual mutations**, rerun after the final semantic change against harness
    `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8`. No anchor needed to move. Manual advisory evidence only; no coordinator
    executed them, and the 34 registered witnesses are unchanged.
    - Controls: `tests/test_greenhouse_s2c_canary.py::test_default_invocation_refuses` and `tests/test_greenhouse_s2c_canary.py::test_selection_rule_follows_provider_order`.
    - Every anchor occurred exactly once; the baseline and final runs passed.
    - Log: `.claude/runtime/phase4-s2c-correction7-mutation-log.json`, SHA-256
      `8bbed49909431d97910b367e624db689ee2d44a8486e3bce2eede1930b161a77`.

  | ID | Mutation | Anchor → replacement | Failing witness (`tests/test_greenhouse_s2c_canary.py::`) | Baseline | Mutant | Restored; SHA-256 |
  |---|---|---|---|---|---|---|
  | W1 | request-shape guard removed | `check_request_shape(request) ⏎ request.headers["Accept-Encoding"]` → `request.headers["Accept-Encoding"]` | `test_request_shape_guard_refuses_before_send[other_board]` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W2 | second-send refusal removed | `if self._capture.request_sent: ⏎ raise CanaryRefusal("second_request_refused")` → (deleted) | `test_second_send_is_refused_before_network` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W3 | live gate enabled by default (env check removed) | `if env.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE: ⏎ raise CanaryRefusal("gate_disabled")` → (deleted) | `test_live_preflight_refuses_without_live_env` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W4 | board allowlist check removed | `if request.board != BOARD_TOKEN: ⏎ raise CanaryRefusal("board_not_allowlisted")` → (deleted) | `test_live_preflight_refuses_non_allowlisted_board` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W5 | Accept-Encoding: identity override removed | `request.headers["Accept-Encoding"] = ACCEPT_ENCODING` → (deleted) | `test_accept_encoding_identity_and_default_user_agent` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W6 | raw capture overwrite instead of exclusive create | `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_EXCL \| getattr(os, "O_BINARY", 0))` → `fd = os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_TRUNC \| getattr(os, "O_BINARY", 0))` | `test_exclusive_write_never_overwrites` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W7 | supervisor no longer terminates/kills at the deadline | `stop()` → `pass` | `test_supervisor_terminates_and_reaps_worker_at_deadline` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W8 | retries enabled (max_attempts=3) | `max_attempts=1, max_response_bytes=MAX_RESPONSE_BYTES` → `max_attempts=3, max_response_bytes=MAX_RESPONSE_BYTES` | `test_503_is_inconclusive_with_exactly_one_request` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W9 | response cap raised to 5 MiB (5,242,880) | `MAX_RESPONSE_BYTES: Final = 5_000_000` → `MAX_RESPONSE_BYTES: Final = 5_242_880` | `test_body_over_cap_is_partial_without_complete_hash` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W10 | record cap before conversion removed | `if capture.source_record_count > MAX_SOURCE_RECORDS: ⏎ raise CanaryRefusal("record_cap_exceeded")` → (deleted) | `test_record_cap_is_enforced_before_conversion` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W11 | database-layer import added | `from app.ingestion.hashing import canonical_json_hash  # noqa: E402` → `import sqlalchemy  # noqa: E402, F401 ⏎ from app.ingestion.hashing import canonical_json_hash  # noqa: E402` | `test_harness_imports_only_allowed_modules` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  | W12 | existing-reservation refusal removed from preflight | `if os.path.lexists(paths.reservation): ⏎ raise CanaryRefusal("attempt_already_reserved")` → (deleted) | `test_live_preflight_refuses_existing_reservation` | pass | fail; controls pass | pass; `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8` |
  - **Retained state, unchanged throughout** (verified before and after):
    - the seven staging artifacts and inventory `bbdc7659…04bb`;
    - the attempt-2 reservation `0f89c0c1…d329` and attempt-1 archive `18763cf6…0f5e`;
    - the expected-inventory manifest `7bab5eda…88f0`;
    - report `093f59b5…873e` and fixture `d7e14857…5249`.

    **Cleanup was not run.** No request was made. No staging or runtime file is tracked
    or staged. Workflow metadata remains pending.
- **Attempt-2 verified-cleanup checkpoint** (this commit, the direct single-parent child
  of `2232d9693b54a225bf87d23ec5d65898a081602f`). This is an advisory checkpoint, **not
  final `C`**. Documentation only: exactly
  `docs/DECISIONS/0017-greenhouse-live-canary.md`,
  `docs/evaluation/phase4-s2c-live-canary.md`, `docs/ROADMAP.md`, and this file.
  - **Approvals** (as relayed by the user):
    - Sol Medium and Astra both approved the exact Correction 7 cleanup mechanism.
      Before the invocation, the user asserted single-operator quiescence: no live,
      projection, fidelity, post-run, or other cleanup command running; no other command
      or task authorized to read or write staging; this cleanup the sole cooperative
      accessor from final verification through deletion; and an understanding that this
      excludes cooperative JobGoblin writers, not a malicious process or privileged
      OS-level mutation.
    - Both reviewers then approved the cleanup result. The user's checkpoint
      authorization records the verified facts and identities below. No separate
      reviewer-authored text was supplied to the implementer, so this entry does not
      itemize either reviewer's individual method beyond those facts.
  - **Invocation and preflight.** Read-only preflight first confirmed:
    - `HEAD`, branch, and tracking ref at `2232d96`, with a clean tree;
    - the harness blob `190f9427…1be8`;
    - every binding exact, and the seven-entry staging inventory equal to the manifest;
    - the reservation records `reserved` then terminal
      `OBSERVED:pending_post_run_review`;
    - no local process referencing the harness or staging.

    Cleanup then ran exactly once through the reviewed harness, using fixed argv with no
    shell, retry, fallback, or manual deletion. The manifest path was passed in absolute
    form (the same file). The attestation was written create-only and fsynced outside
    staging.
  - **Exact cleanup identities:**
    - cleanup candidate and executing SHA `2232d9693b54a225bf87d23ec5d65898a081602f`;
    - cleaned at 2026-10-10T23:38:07+00:00;
    - attestation `.claude/runtime/phase4-s2c-attempt2-cleanup-attestation.json`, 3,717
      bytes, `e9a41acedc407ca9db3ae7438920dc9e604726f223ad058250ea71841140d576`;
    - harness and checker `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8`;
    - manifest `7bab5eda4f5abd6cc4529a5793a011f2ea8d13a335c2a6271545a3c9e48b88f0`;
    - expected, observed, and attested inventory
      `bbdc7659e1a2bc86bd5e1b18e23c725e041c8dbde7654fe7b898782afa6404bb`;
    - raw evidence 420,784 bytes,
      `43ca81bd854df7764b691fae8424d2669c750411e43e65036de0890785f215c5`, Git blob
      `fc1d8a9cc83cb65a071afc7a9c70ab2d673faf3f`;
    - attempt-2 reservation `0f89c0c1946007a2027c3a108c5ccc2d1b3c7eb9436ea043637f3c84de0fd329`;
    - attempt-1 archive `18763cf69c9452d36e96017ee91b9ad3638398726b7dbce24917ef75efd00f5e`;
    - fixture `d7e14857e3279090709093d71f0c7c26d3e7baf806f35615c3b32520c75b5249`;
    - report before this update
      `093f59b52b277bd17ff29ed53be95985858af9d1cd5bdd8a0d8bcd9b6419873e`, and after it
      `c5592176562140b1835cc47d22c0334e113ef9d00f60478c769f83673b95a506`.
  - **Verified:**
    - exit 0, `passed` literally `true`, `checker_failure` null;
    - expected, observed, and attested inventories equal, and all seven approved staging
      artifacts removed;
    - the staging root and every known staging path absent;
    - all ten pre-deletion checks and exactly fourteen fresh-checker keys literally `true`;
    - the checker identity matched the reviewed harness, and the executing SHA matched the
      cleanup candidate;
    - no tracked, staged, untracked, or ignored S2c staging residue (an unrelated,
      pre-existing ignored `backend/.evaluation-staging/` is not S2c staging and was not
      touched);
    - no runtime path or raw blob identity in the reviewed Git range or the index;
    - both reservations, the fixture, and the report exact.

    Attempt 1 remains permanently `FAIL-CLOSED:worker_failed`. Attempt 2 remains `PASS`
    with no findings after cleanup.
  - **Retained limitations:**
    - logical deletion from controlled project locations, not forensic erasure;
    - the deleted attempt-2 source content can no longer be reread;
    - attempt 2 has no durable executable replay fixture, and the attempt-1 fixture does
      not prove attempt-2 fidelity;
    - the remaining evidence is the approved report, the identities, aggregates, lineage
      and decisions, the cleanup attestation, and Git history;
    - the post-cleanup filesystem does not independently prove the historical absence of
      every possible unrecorded manual action or network event. The attestation, the
      reservations, Git state, and the retained identities contain no conflicting
      evidence;
    - no proof of broad normalization accuracy, provider generalization, D1,
      persistence, runtime activation, or production readiness;
    - the quiescence boundary excludes only cooperative writers.
  - **Documentation changes.**
    - Present-state "cleanup pending" statements in ADR 0017, the report, and ROADMAP now
      record the verified cleanup.
    - Historical statements are temporalized, not deleted.
    - ADR 0017 and the report each gain a verified-cleanup section.
    - No live-run, fidelity, `PASS`, or option-A evidence is changed.
  - **Validation** (documentation only, so no pytest, Ruff, mypy, or mutation run):
    - an exact four-file scope check;
    - required-identity and stale-wording checks;
    - the harness's `screening_hits` (as used for `report_screening_clean`) clean on the
      updated report and the changed docs;
    - no `.claude/runtime` path tracked or staged;
    - fixture, harness, and both reservations unchanged;
    - `check_handoff`, `check_repo`, and `git diff --check` pass.
  - **Next:** final `C` may be prepared only after this checkpoint commit receives narrow
    review. Workflow metadata remains pending and byte-identical.
- **Final `C`** (this commit, the direct single-parent child of checkpoint
  `df25db4c21a7eec4c69c5a60dd40b47fac09d862`). Changes only this file. It records the two
  advisory verified-cleanup checkpoint reviews, verbatim as relayed by the user:

> **Sol Medium verified-cleanup checkpoint advisory review — approved, no executable findings.** Reviewed checkpoint `df25db4c21a7eec4c69c5a60dd40b47fac09d862`, direct child of cleanup candidate `2232d9693b54a225bf87d23ec5d65898a081602f`. Independently confirmed the exact four-document scope, synchronized feature refs, clean tree, committed report SHA-256 `c5592176562140b1835cc47d22c0334e113ef9d00f60478c769f83673b95a506`, cleanup-bound report SHA-256 `093f59b52b277bd17ff29ed53be95985858af9d1cd5bdd8a0d8bcd9b6419873e`, cleanup attestation SHA-256 `e9a41acedc407ca9db3ae7438920dc9e604726f223ad058250ea71841140d576`, and all retained harness, manifest, fixture and reservation identities. The documentation accurately records the single successful cleanup, seven removed staging artifacts, absent staging root, ten true pre-deletion checks, exactly fourteen true fresh-checker checks, permanent attempt-1 `FAIL-CLOSED:worker_failed`, and unchanged attempt-2 `PASS` with no findings. Historical pending statements are temporalized; logical deletion is not forensic erasure; attempt 2 has no durable replay fixture; the attempt-1 fixture proves no attempt-2 fidelity; and no accuracy, generalization, D1, persistence, runtime-activation or production-readiness claim is made. Reviewer approvals are represented only as user-relayed where verbatim reviewer text was unavailable, without attributing unrecorded methods. The updated report and newly added checkpoint hunks pass privacy screening; ADR 0017’s unchanged literal policy references `mailto:` and `tel:` trigger the generic whole-file heuristic but contain no captured content or personal information. This checkpoint may parent final C, limited to recording the advisory decisions in `docs/LLM_HANDOFF.md`; formal R retains unrestricted authority.

> Astra independently reviewed verified-cleanup checkpoint `df25db4c21a7eec4c69c5a60dd40b47fac09d862` and approved it with no findings. Review confirmed the four-document scope, ancestry and synchronized clean Git state; current and historical report hashes; retained cleanup identities; unchanged pending metadata; accurate verdict, cleanup, attribution and limitation wording; and passing repository, handoff, diff and changed-content privacy checks. The checkpoint is suitable as the parent for separately authorized final-C preparation. This advisory approval is not formal R, candidate-bound verification, receipt approval, merge authorization or permission for further provider contact.

- Final `C` is designated. Verification: the genuine candidate-bound
  `verification_coordinator` `gate=final` run against this `C` is pending; it is recorded
  in `A` only if every step passes, cleanup completes, and `approval_eligible` is `true`.
  No live request is repeated, no provider is contacted, and neither reservation nor the
  deleted staging is touched.
- STOP after `A` for formal Sol Medium review. No `R`, `M`/`Q`, merge, provider contact,
  reservation change, another request, persistence, runtime activation, S3, or S4.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-05-phase4-greenhouse-live-canary-s2c-eeac72a
slice_kind: tooling
risk_class: H
base_sha: eeac72abb2ba930fb469a4abb563a7601826266a
declared_gate: final
executed_gate: final
candidate_sha: 2a10f13df0e07b6484335bf57af9ca59043a2a9e
receipt_id: 01963a8f-dbaf-4985-ad9c-ddf8ac5beed5
receipt_path: docs/verification-receipts/2a10f13df0e07b6484335bf57af9ca59043a2a9e/01963a8f-dbaf-4985-ad9c-ddf8ac5beed5.json
```

### Work review

- Date/reviewer: 2026-10-19 (UTC), Sol (primary, Sol Medium). Formal review of Phase 4
  S2c, the bounded read-only Greenhouse live canary, on
  `phase-4/greenhouse-live-canary-s2c`:
  - base `eeac72abb2ba930fb469a4abb563a7601826266a`;
  - final candidate `C` = `2a10f13df0e07b6484335bf57af9ca59043a2a9e`;
  - publication `A` = `8d37617e40df5bb2a7655607a5452ef53c5dbcf9`;
  - receipt `01963a8f-dbaf-4985-ad9c-ddf8ac5beed5`, SHA-256
    `697f2edc0f579b8a1a48d979dce6be023f59c47e790d5ad000cc2b1d895ab5aa`.

  The Sol Medium and Astra verified-cleanup checkpoint reviews recorded in `C` were
  advisory only; this is the formal review.
- **1. Sol's formal verdict and limitations** (as relayed by the user; the relay is the
  authority for this review):
  - verdict **approved**, no executable findings;
  - primary reviewer Sol (Sol Medium); gate `final`; slice kind `tooling`; risk class H;
  - attempt 1 remains permanently `FAIL-CLOSED:worker_failed`; attempt 2 remains `PASS`
    with no findings after verified cleanup;
  - the evidence does not establish broad normalization accuracy, provider
    generalization, persistence, D1 satisfaction, runtime activation, or production
    readiness; logical deletion is not forensic erasure; attempt 2 has no durable replay
    fixture;
  - `C`/`A` are ready for an `R` record. The verdict does not authorize merge, `M`/`Q`,
    another provider request, reservation changes, persistence, runtime activation, S3,
    or S4.

  The relay itemizes the evidence below and no further disposition, so none is
  attributed to Sol here.
- **2. Independently verified or rerun in formal review** (per the relay):
  - **ancestry and scope:** `C` is the direct child of `df25db4`, and `A` is `C`'s direct
    child; `C` changes only this file; both advisory paragraphs are recorded correctly;
    `C`'s metadata remains pending without receipt or executed-gate fields; `C..A` adds
    exactly one receipt and changes only the newest metadata block; `A`'s published
    metadata names `C`, the final gate, the receipt ID, and the receipt path;
  - **receipt:** schema-valid and bound to the exact `C`, base, slice, risk class H, and
    final gate; the verifier, handoff-checker, and configuration hashes match their
    committed `C` versions; the affected surface, focused selector, migration decision,
    and complete 34-guard inventory recompute correctly; `approval_eligible` recomputes
    to `true`;
  - **checks:** `check_handoff`, `check_repo`, the transition checks, repository diff
    checks, and working-tree checks pass;
  - **state:** feature `HEAD` and the local tracking ref equal `A`; `main` and
    `origin/main` remain at `eeac72a`; the tree is clean; S2c staging remains absent;
    runtime evidence is untracked; the retained evidence hashes match;
  - **rerun:** the focused selection, **455 passed, 1 expected Windows FIFO skip**; Ruff
    format and check pass; mypy passes.
- **3. Relied upon from the genuine C-bound coordinator receipt** (not rerun in formal
  review):
  - all 12 required steps passed;
  - the full suite, **4,609 passed**;
  - registered witnesses, **34 of 34 passed**;
  - disposable test-database validation and reachability passed;
  - isolated-worktree snapshots matched, cleanup passed, and no worktree residue
    remained;
  - migration was correctly not triggered.
- **4. Retained limitations and explicit exclusions:**
  - no proof of broad normalization accuracy, provider generalization, persistence, D1,
    runtime activation, or production readiness;
  - logical deletion from controlled project locations, not forensic erasure; the deleted
    attempt-2 source content can no longer be reread; attempt 2 has no durable replay
    fixture, and the attempt-1 fixture does not prove attempt-2 fidelity;
  - a receipt proves verification only, never review approval or merge authorization;
  - no third live request is authorized; no provider was contacted, no reservation was
    changed, and no staging was recreated while recording this review.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings.
- Exact bounded correction: none required.
- STOP -- record-only. This review authorizes no merge, `M`, `Q`, provider contact,
  reservation change, another request, persistence, runtime activation, S3, or S4. Merge
  requires separate user authorization.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-05-phase4-greenhouse-live-canary-s2c-eeac72a
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-19T02:35:33+00:00
candidate_sha: 2a10f13df0e07b6484335bf57af9ca59043a2a9e
publication_commit_sha: 8d37617e40df5bb2a7655607a5452ef53c5dbcf9
receipt_path: docs/verification-receipts/2a10f13df0e07b6484335bf57af9ca59043a2a9e/01963a8f-dbaf-4985-ad9c-ddf8ac5beed5.json
receipt_id: 01963a8f-dbaf-4985-ad9c-ddf8ac5beed5
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-19 (UTC). Merged `phase-4/greenhouse-live-canary-s2c` into `main` with
  `git merge --no-ff`, at the approved, reviewed commit
  `04a32f5c17bedfdf8c104e9c94432c7c4aa1b453` (`R`). `R` is Sol Medium's "approved -- no
  findings" formal verdict on `C=2a10f13df0e07b6484335bf57af9ca59043a2a9e` /
  `A=8d37617e40df5bb2a7655607a5452ef53c5dbcf9`.
  - Merge commit `M`: `2b7446fff360ce6a3298ba45aa6b5e85396bc2a3`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `eeac72abb2ba930fb469a4abb563a7601826266a`.
  - Full lineage: base `eeac72a` -> ... -> checkpoint `df25db4` -> `C` `2a10f13` -> `A`
    `8d37617` -> `R` `04a32f5` -> `M` `2b7446f` -> `Q` (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch, its upstream, and the remote ref all sat at `R`; `R`'s sole parent
    is `A`, `A`'s is `C`, and `C`'s is `df25db4`; the tree was clean;
  - `main`/`origin/main`/remote `main` were synchronized at the rollback boundary;
  - **receipt `01963a8f-dbaf-4985-ad9c-ddf8ac5beed5`** (file SHA-256
    `697f2edc0f579b8a1a48d979dce6be023f59c47e790d5ad000cc2b1d895ab5aa`):
    - schema-valid and bound to `C`, the base, the slice, gate `final`, and risk class H;
    - its verifier, checker (`check_handoff.py`), and configuration hashes equal the files
      committed at `C`;
    - the affected surface, focused selector, migration decision (not triggered), and
      complete 34-witness active inventory recomputed identically;
    - independently recomputed as approval-eligible;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`, `reviewer_role: primary`,
    `gate: final`, `published_slice_kind: tooling`, and base `eeac72a`.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, eeac72a)` passed.
  - `verification_coordinator.run_post_merge_verification` ran once against `M` in a
    disposable detached worktree (always full/final). It produced artifact
    `ef644ba0-b1f8-4991-b3dd-4ce7585790c8`.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit (this entry).
- Post-merge evidence:
  `docs/post-merge/2b7446fff360ce6a3298ba45aa6b5e85396bc2a3/ef644ba0-b1f8-4991-b3dd-4ce7585790c8.json`
  (SHA-256 of the artifact file as written:
  `cfd34017ab2d8f84438dbf1d5d452ab2ffdbb7502b689d0c4d81757833feec95`). It references
  original receipt `01963a8f-dbaf-4985-ad9c-ddf8ac5beed5`.
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- Evidence by source:
  - **Post-merge coordinator (this artifact, at `M`):**
    - all 11 steps PASS: Ruff format and check, mypy, `check_repo`, `git diff --check`,
      disposable test-database URL validation and reachability preflight, the full
      suite, contract mutation witnesses, handoff metadata validation, and
      temporary-directory cleanup;
    - full pytest suite: **4,609 passed**;
    - all 34 registered mutation witnesses passed, 0 failed;
    - no migration triggered;
    - identical initial and final worktree snapshots; worktree removed with no residual
      entry or directory; cleanup PASS;
    - recorded step duration 392.594 seconds.
  - **Pre-merge receipt (at `C`):** all 12 final-gate steps PASS, including focused pytest
    (455), the full suite (4,609 passed), and 34/34 registered witnesses; migration not
    triggered; cleanup PASS; recorded step duration 521.765 seconds.
  - **Formal review (`R`):** Sol Medium approved with no executable findings. Per the
    relay, Sol independently verified the lineage, scope, advisory paragraphs, pending and
    published metadata, receipt schema and binding, hashes, affected surface, focused
    selector, migration decision, 34-guard inventory, and approval eligibility, and the
    handoff, repository, transition, diff, and working-tree checks; reran the focused
    selection (455 passed, 1 expected Windows FIFO skip), Ruff, and mypy; and relied on the
    receipt for the full suite and registered witnesses.
  - **Historical advisory and manual evidence (not coordinator-executed, not registered
    witnesses):**
    - the W1–W12 manual mutations, last rerun for Correction 7 against harness
      `190f9427…1be8` (log `.claude/runtime/phase4-s2c-correction7-mutation-log.json`,
      SHA-256 `8bbed499…1a77`);
    - the Sol Medium and Astra advisory reviews of the corrections and the
      verified-cleanup checkpoint, recorded verbatim or as relayed in `Iteration 2`.
  - **Live-network evidence boundary:** the authorized live attempts are recorded in ADR
    0017 and the report and were not repeated. No provider was contacted during `C`, `A`,
    `R`, `M`, or `Q`. No reservation changed, staging was not recreated, and no
    production database or production data was accessed. Both suite runs used the
    configured disposable test database.
- Status: merged. S2c records a bounded, read-only, single-board Greenhouse live canary
  under ADR 0017 and its report `docs/evaluation/phase4-s2c-live-canary.md`, plus its
  verified attempt-2 cleanup. It adds no persistence, runtime registration, or runtime
  activation.
- Retained limitations:
  - attempt 1 remains permanently `FAIL-CLOSED:worker_failed`; attempt 2 is `PASS` with no
    findings;
  - deletion of the attempt-2 staging was logical deletion from controlled project
    locations, not forensic erasure; the deleted source content can no longer be reread;
  - attempt 2 has no durable executable replay fixture, and the attempt-1 fixture does
    not prove attempt-2 fidelity;
  - no proof of broad normalization accuracy, provider generalization, D1, persistence,
    runtime activation, or production readiness;
  - no third provider request is authorized.

  Approval and passing verification are review and verification status, not production
  readiness.
- STOP -- report the synchronized final `main` SHA and stop. S2c is complete once this `Q`
  reaches `main`. No S3, persistence, runtime activation, another provider request, D1
  work, or another slice without separate explicit user authorization.

## Iteration 2

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
