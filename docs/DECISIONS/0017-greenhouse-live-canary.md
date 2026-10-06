# 0017 — Bounded read-only Greenhouse live canary (Phase 4 S2c)

## Status

**Proposed — pre-live advisory candidate.** Phase 4 S2c
(`phase-4/greenhouse-live-canary-s2c`, risk class H, `slice_kind: tooling`, `gate: final`),
base `eeac72abb2ba930fb469a4abb563a7601826266a` (`Q` of the ADR 0016 retention slice).

**No live request has been made.** This ADR records the reviewed contract and the offline
harness. The live result, the projected fixture, and the report do not exist yet. They may
be recorded only from the evidence of a separately authorized run, under
[Results](#results-pending).

The contract is the frozen, gitignored packet `.claude/runtime/phase4-s2c-frozen-contract.md`
(SHA-256 `ac2cc00afc9e2bb7b7520eba71da7d6349e7b523f1b9b601bb2ad254c450800b`). It holds nine
separately identified immutable inputs, applied in order. Later compatibility corrections
supersede only the clauses they explicitly replace.

1. the implementer's original S2c proposal;
2. Astra's complete original review;
3. Sol Medium's complete original review;
4. Sol's compatibility ruling (C1–C28);
5. Astra's first compatibility findings;
6. Astra's canonical-hash finding;
7. Sol's final compatibility corrections (C1, C12, C19, C28);
8. Astra's final compatibility confirmation;
9. the user's decisions U1–U8 and the offline implementation authorization.

This ADR changes nothing in ADRs 0011, 0013, 0014, 0015, or 0016.

## Context

ADR 0015 §10–11 left the real `/jobs?content=true` list-endpoint encoding unproven: no
captured raw Greenhouse `content` exists. S2c tests the published offline path once
against one real board: the S1 adapter (`declared-double-escaped`), S2b's converter and
bridge, and S2's `normalize_posting`. ADR 0013 §8, ADR 0014 §8, and ADR 0015 §11 require
explicit network authorization, a user-performed terms review, Sol Medium and Astra
review, default-off execution, and explicit caps.

## Decision

### 1. One slice, two advisory checkpoints

S2c is one slice:

1. offline harness (this candidate);
2. pre-live advisory review by Sol Medium and Astra;
3. one separately authorized request;
4. a post-run advisory candidate with the projected fixture, embedded lineage, report,
   golden expectations, and selection and fidelity decisions, reviewed by both while the
   raw capture still exists;
5. verified raw cleanup;
6. final `C`, receipt, `A`, formal `R`, and `M`/`Q`, each under its own authorization.

Neither checkpoint triggers an extra full suite. Final `C` may add only the advisory
dispositions, the cleanup attestation, and pending workflow metadata.

### 2. The single request

- Exactly one `GET https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true`
  (U2: `discord`). There is no retry, redirect, fallback board, or second send.
- The harness (`backend/scripts/run_greenhouse_s2c_canary.py`) wraps the unchanged
  adapter's transport. Every other method, host, port, path, or query, and any second
  send, is refused before network I/O.
- The locked `httpx` default User-Agent is kept and recorded. The only request-header
  override is `Accept-Encoding: identity`. A non-identity `Content-Encoding` is refused
  without fallback.
- Adapter settings: `max_attempts=1` and `max_response_bytes=5_000_000` (exactly
  5,000,000 bytes, not 5 MiB). Every other bound is the reviewed default.
- The 500-record cap is checked on the bounded body before any adapter conversion.
- The complete automated operation runs in a separately supervised worker process with
  one 60-second wall-clock deadline that starts immediately before launch. The worker
  spawns no process. No second harness timer exists.
- **Parent-loss containment (operating-system enforced).** Before the reservation exists,
  the supervisor creates a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
  and verifies that setting by reading it back. The supervisor holds the only,
  non-inheritable handle.
  - The worker is assigned to the job, and membership is confirmed with
    `IsProcessInJob`, before the launch token is released.
  - Until then the worker can only block waiting for the token, so it cannot claim,
    construct a transport, request, capture, convert, or write a summary.
  - When the supervisor's handle closes, including when the supervisor crashes or is
    killed, the kernel terminates the worker in any phase. This does not depend on the
    worker's interpreter, threads, event loop, or GIL.
  - Unsupported platforms or failed configuration refuse with `containment_unavailable`
    before the reservation. A failed assignment releases no token, stops the worker, and
    records `FAIL-CLOSED:containment_assignment_failed`.
  - The worker also refuses unless it runs inside a kill-on-close job, and a stdin-pipe
    watchdog remains. Both are defense in depth only, never the guarantee.
- **Shutdown confirmation.** At the deadline, and on any abnormal supervisor exit after
  launch (interrupt or supervision failure), the supervisor terminates, then kills, and
  reaps after each step.
  - Failures or interruptions of terminate, kill, wait, or poll never skip escalation.
  - Death counts as confirmed only on evidence: the reaped return code, or the operating
    system's process state.
  - Without evidence the result is `FAIL-CLOSED:worker_termination_unconfirmed`.
  - An interruption is honoured only after shutdown was attempted. It is recorded as
    `FAIL-CLOSED:supervisor_interrupted` with the reservation kept.
  - No exception text is ever reported.

### 3. Gates and the attempt reservation

Live operation is disabled by default. A live attempt requires every gate element:

- the `live` subcommand and `JOBGOBLIN_S2C_LIVE_CANARY=authorized-once`;
- `--board discord`;
- a clean checkout whose `HEAD` equals `--expected-sha`;
- the frozen-contract SHA-256;
- the authorization record's file and SHA-256;
- no existing attempt reservation and no existing staging directory.

Before any transport exists, the harness exclusively creates and fsyncs
`.claude/runtime/phase4-s2c-attempt.jsonl`, outside raw staging. Its first record binds
the board, advisory SHA, contract SHA-256, request fingerprint, authorization identity and
SHA-256, and timestamp. The supervisor appends exactly one terminal categorical outcome.
A one-line crash residue still consumes the authorization.

Any existing reservation refuses every later attempt, including after raw cleanup. It is
retained through `Q` or recorded abandonment; its SHA-256 and outcome are recorded in the
handoff before any deletion. A new request needs new explicit authorization and an
explicitly authorized reservation reset.

**Launch capability and single worker claim.** After reserving and creating staging, the
supervisor writes a create-only launch capability to staging. It is bound to:
- the exact reservation line's SHA-256 and its board, advisory SHA, contract,
  authorization, and request-fingerprint identities;
- the SHA-256 of a one-time secret token.

The token itself is delivered only over the worker's stdin pipe, after kernel
containment, and is never written to disk, argv, or the environment.

Before any transport exists, the worker:
1. re-derives the capability from the open, single-line reservation and the token, and
   compares it;
2. requires that no claim, raw capture, or summary exists;
3. exclusively creates its claim.

Each of these is refused before any transport: direct invocation, a wrong or missing
token, a missing or mismatched capability, an altered or closed reservation, crash
residue, a restart after the request began, and a concurrent or duplicate launch.

### 4. Capture, retention, and cleanup

- Only a complete 200 JSON identity-encoded body that reaches EOF within the cap gets a
  complete-response SHA-256 (of the entity-body bytes before decoding).
- Interrupted, oversized, or unexpectedly encoded bodies are partial and are never given a
  complete-response hash. Non-200 and rejected bodies are never drained.
- The complete body is written once, exclusive-create, to
  `.claude/runtime/phase4-s2c-staging/` (gitignored). It is kept through post-run review
  and is never committed, staged, pushed, logged, pasted, or included in a receipt (U4).
- Cleanup, after post-run advisory clearance and before final `C`, is bound to the exact
  immutable post-run advisory candidate SHA and to the approved fixture SHA-256 (or
  approved absence, for a findings-only report) and the approved report SHA-256.
  **Before any deletion**, all of these must hold, or cleanup refuses and deletes nothing:
  1. the raw hash and size match the captured evidence;
  2. `HEAD` is the candidate, the tree is clean, and the candidate descends from the
     base;
  3. the fixture and report bytes equal the approved hashes, so any change after
     approval fails;
  4. the fixture passes full validation, including:
     - `publication_safe=true`;
     - both fidelity reviews performed (`faithful` or `mismatch`);
     - a non-blank reviewer;
     - the semantic replay in §5;
  5. the raw response, whatever its filename, is absent:
     - its Git blob id from the commit range and the index;
     - its bytes (LF and CRLF forms) from every changed and publication file.

  Content screening is recorded but never establishes publication safety; independent
  content review of derived artifacts stays mandatory. Cleanup then:
  1. inventories staging by relative path, size, and hash only;
  2. refuses links, junctions, and reparse points;
  3. deletes everything beneath the staging root, then the root;
  4. runs a fresh checker process bound to the same candidate and hashes. It confirms the
     root and every known capture path are absent, no staging residue is tracked, staged,
     untracked, or ignored, no runtime path appears in the commit range or the index,
     the raw blob is absent from the commit range and the index, and the artifact
     bindings still hold.

  Cleanup failure blocks final `C`. This proves logical deletion from controlled
  locations, not forensic erasure.

### 5. Projected fixture and lineage

`backend/tests/fixtures/providers/greenhouse_s2c_projected.json` (path reserved; not yet
created) has `fixture_kind = projected_live_record_with_exact_content_excerpt`:

- at most three selected records, chosen in provider order:
  1. the first publication-safe, adapter-valid `converted` record with a safe excerpt
     **whose projected excerpt itself replays as `converted`** through the unchanged
     adapter, converter, bridge, and composition. A source that converts but whose
     proposed excerpt abstains is not eligible as the first sample; a different safe
     proper excerpt must be chosen or the record excluded;
  2. optionally, the first later record with a distinct actual non-`converted` outcome;
  3. optionally, another such record.

  `invalid_type` stays synthetic-only. Without an eligible replay-converted first sample
  no projected fixture is created; a findings-only report remains allowed.
- Each projected record contains only `id`, `absolute_url`, `title`, `location.name`, and
  `content`. Missing versus `null` is preserved.
- String `content` is replaced by one exact, contiguous, unmodified **proper** substring
  of the source (never the complete source string, however short), of at most 2,000 code
  points and 4,096 UTF-8 bytes, with code-point offsets and the original length recorded.
- Fixture validation replays every projected job independently and enforces actual
  outcomes, not labels or self-consistent hashes:
  - golden expectations must equal the recomputed results;
  - the first sample is `first_converted` and actually replays as `converted`;
  - later samples are `distinct_outcome`, with actual outcomes that are not `converted`
    or `invalid_type` and are pairwise distinct;
  - source ordinals strictly increase.

  Review states must be valid, performed, and publication-safe.
- Detailed lineage covers selected records only:
  - source-record, allowed-field, original-content, excerpt, projected-record, and
    golden-output hashes;
  - aggregates for the whole response.

  There is no key inventory or per-record identifier list for unselected records.
- Canonical hashes use the repository's
  `app.ingestion.hashing.canonical_json_hash` (`ensure_ascii=True`).
- The replay envelope (`jobs`, `meta.total` = projected count) is explicitly synthetic.
- Golden values cover the selected excerpts only. They are reviewed regression
  expectations, not annotated truth, and not proof that excerpt normalization equals
  complete-posting normalization.
- Screening for emails, phones, `mailto:`/`tel:` links, and profile URLs is defense in
  depth only. A hit excludes a record, never redacts it. Every published value is
  manually reviewed (U5).

`backend/scripts/verification_scope.py` maps exactly that path to
`test-fixture:greenhouse-s2c-canary` (no contract family, not a direct pytest target).

### 6. Verdicts

Exactly four verdicts, in precedence order. A higher-priority condition is never
downgraded because other records succeeded.

1. **`FAIL-CLOSED`:** preflight, authorization, reservation, request-control,
   unexpected-mode (`not_requested`), outer-timeout, response-cap, record-cap,
   schema/envelope, lineage, cleanup, `parser_error`, bridge, normalization, or
   worker-termination failure.
2. **`INCONCLUSIVE`:** a successful empty board, or a bounded upstream transient
   (timeout, connectivity, 429, 5xx), with no retry. The fidelity review being
   unavailable also caps the verdict here.
3. **`PASS-WITH-FINDINGS`:** usable observations with any designed abstention:
   - `absent`, `blank`, `invalid_type`, `input_too_large`, `output_too_large`,
     `empty_after_conversion`, `mixed_literal_and_escaped_markup`,
     `unsupported_angle_reference`, `residual_nested_encoding`,
     `unclosed_suppressed_element`, or `malformed_truncated_markup`;
   - skipped or duplicate records, completeness findings, or `incomplete_results`;
   - no safe converted sample, or a fidelity mismatch.
4. **`PASS`:** all integrity checks pass, source processing is complete, and a safe
   converted sample exists whose capture-based full-content fidelity and excerpt-replay
   fidelity both pass (U8).

### 7. Report

`docs/evaluation/phase4-s2c-live-canary.md` (path reserved; not yet created) covers:

- aggregates for all source records;
- categorical per-record rows: ordinal, disposition, outcome, and length;
- converted text for the selected excerpts only, at most 1,000 characters per record.

It never automatically publishes titles, locations, warnings, exception text, or raw keys.
Its salary statement is exactly:

> No salary-specific parameters or endpoint were requested; no salary field was extracted
> or composed, and the salary classifier was not invoked. Incidental compensation text may
> occur in captured content. The bridge supplies no compensation input; ADR 0011 L4
> remains open.

### 8. Boundaries

- **No application-code change.** The harness may import and invoke the existing adapter,
  converter, bridge, composition, taxonomy loader, schemas, and canonical-hashing helper.
  Database and ingestion-persistence imports are forbidden; an AST test and a subprocess
  test enforce this.
- **Not authorized:**
  - runtime registration or activation;
  - database access, operational persistence, or a migration;
  - D1 implementation or salary composition;
  - a generalized capture framework or production-data reuse;
  - a second request;
  - S3 or S4.
- **D1 and D2.** D1 remains unsatisfied. Bounded fixture expectations and reports are
  evaluation artifacts with no runtime consumer, and S2c adds no D2 evidence.

## Results (pending)

None. This section may be completed only from the separately authorized run's recorded,
reviewed evidence. Nothing here is a live result.

## Remaining pre-live gates

1. Sol Medium and Astra review of the immutable pre-live advisory candidate (U7).
2. The user's terms-of-use and robots.txt review, recorded with URLs, date, and separate
   dispositions (U3).
3. Explicit network authorization (U1) naming:
   - the board, the exact advisory SHA, and the contract hash;
   - the request, bounds, one-attempt rule, and retention policy.

## Consequences

- An operator-visible, default-off, single-use canary exists offline. Nothing is
  runtime-reachable (O3: it removes the unknown list-endpoint encoding dependency only
  after the authorized run).
- The W1–W12 manual mutation experiments are advisory evidence, not registered
  witnesses. The 34 registered witnesses are unchanged.
- Rollback before the live run: abandon the branch. No external effect has occurred.
