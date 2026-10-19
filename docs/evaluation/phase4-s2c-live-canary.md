# Phase 4 S2c live canary report — attempts 1 and 2

> **Attempt 1: `FAIL-CLOSED:worker_failed`, permanent.** Attempt 1 can never become PASS,
> PASS-WITH-FINDINGS, or INCONCLUSIVE, however clean its processing summary is.
>
> **Attempt 2: computed verdict `PASS`, with no findings.** That completes the live-evidence
> requirement. Attempt-2 raw cleanup ran exactly once through the reviewed mechanism and
> passed, and attempt 2 remains `PASS` with no findings after cleanup. S2c workflow
> publication is not complete until the `C`/`A`/`R`/`M`/`Q` controls succeed. Each attempt
> keeps its own verdict.

Post-run advisory report. The user approved this minimized report and projected fixture for publication to the S2c feature branch for post-run advisory review. They are not final-C evidence, and attempt 1 remains permanently `FAIL-CLOSED:worker_failed`. The attempt-2 sections were added as the attempt-2 post-run advisory candidate, and the verified attempt-2 cleanup was recorded at the attempt-2 verified-cleanup checkpoint. Governing record:
[ADR 0017](../DECISIONS/0017-greenhouse-live-canary.md). Bounded by ADR 0017 §7:
aggregates, categorical observations, and no titles, locations, warnings, exception text,
raw keys, or descriptions.

## Attempt 1: what ran

- **Request:** exactly one `GET https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true`
  at 2026-10-08T23:18:16Z, with no retry, no redirect, and no second request.
- **Harness:** candidate `1cb715a00c52fef07ea93ea356612ffe0322ac83`, harness SHA-256
  `b5ecedb6ffbea05d64a3e9b662fd951e3f4a9ecd6062e1206a7b3d9e9aa0b61a`.
- **Headers:** the locked default User-Agent (observed `python-httpx/0.28.1`) and
  `Accept-Encoding: identity`.
- **Bounds:**
  - 5,000,000-byte response cap and 500-record cap;
  - adapter timeouts of 5 s connect, 10 s read, 5 s write, and 5 s pool, with a 30 s
    attempt deadline;
  - one supervised 60-second whole-run deadline.
- **Authority:** the user's U1 network authorization, under the approved personal-use terms
  amendment (a risk decision, not legal clearance).

## Attempt 1: response and processing observations

- HTTP 200, JSON media type.
- **Complete capture:** 413,101 bytes, SHA-256
  `3bbce131108b1fb0b0645a90bcb5174b58c69360fd4257f1ff288460cbf90c19`.
- **Source records:** 48, with `meta.total` 48; completeness consistent.
- **Records:** 48 valid, 48 retained, 48 with conversion outcome `converted`; 0 invalid,
  0 duplicate, and no incomplete results.
- **Encoding:** for this board at this time, the captured content was compatible with the
  declared `declared-double-escaped` content mode. No encoding-class or content-class
  abstention occurred. This does not establish any other board or time.

### Normalized component output (non-abstention counts, 48 retained jobs)

| Component | Jobs with a value |
|---|---|
| `employment_type` | 47 |
| `seniority` | 30 |
| `title` (canonical title) | 25 |
| `remote_type` | 0 |
| `experience.minimum` / `experience.maximum` | 0 / 0 |
| `location.city` / `state` / `country` / `postal_code` | 0 / 0 / 0 / 0 |
| `skills` | 30 jobs, 59 matches |

These counts are **observations, not accuracy evidence**. No posting was annotated, and no
value was checked against ground truth. `title` is smoke evidence only. The components
ADR 0014 lists as unproven remain unproven.

## Attempt 1: why the outcome is `FAIL-CLOSED:worker_failed`

The worker completed processing and wrote its run summary. It then exited with 0xC0000005
instead of 0, so the supervisor correctly recorded a failure:

- The cause was the defense-in-depth daemon stdin watchdog. It was still blocked reading
  the supervisor's open stdin pipe, holding stdin's buffer lock, at interpreter shutdown.
- CPython then aborted with `Fatal Python error: _enter_buffered_busy`.

**Correction 3** (candidate `3d9404b0fe42663457ad80cf58f791e801bd7ff4`) removes that
watchdog. The verified kill-on-close Job Object remains the sole parent-loss containment.
A real-process regression now proves a successful worker exits 0 with no shutdown
diagnostic. Sol Medium and Astra approved Correction 3 (as relayed by the user).

At attempt 1's time, the corrected harness had not completed a live attempt. Attempt 2 (below)
was that separately authorized corrected attempt.

## Attempt 1: fidelity review (bounded)

- **Selection:** only source ordinal 0, the first eligible, screening-clean converted record
  in provider order (`first_converted`). All 48 records were eligible and screening-clean.
  No negative sample was selected or fabricated.
- **Fixture content:** `backend/tests/fixtures/providers/greenhouse_s2c_projected.json`
  contains an exact, contiguous, unmodified **excerpt** `[0, 1005)` of a 5,413-code-point
  source: 1,005 code points and 1,007 UTF-8 bytes. It is not the complete posting. The
  excerpt replays as `converted`, with 876 characters of output.
- **Decisions** (user-owned final decisions; Sol Medium and Astra independently returned the
  same five with no findings):

  | Decision | Result |
  |---|---|
  | full-capture fidelity | `faithful` |
  | excerpt-replay fidelity | `faithful` |
  | publication safe | `true` |
  | excerpt proper and useful | `true` |
  | lineage and golden expectations correct | `true` |

  The reviewer recorded in the fixture is `user`.
- **No coverage claim:** ordinal 0's normalized results are regression expectations for that
  excerpt only. They make no positive normalization-coverage claim, and they do not prove
  that excerpt normalization equals complete-posting normalization.

## Attempt 2: computed verdict `PASS` (cleanup verified)

### What ran

- **Request:** exactly one `GET https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true`
  at 2026-10-10T19:03:13Z, through the reviewed `live` gate. There was no retry, redirect,
  fallback, or other endpoint, board, or provider.
- **Headers:** the unchanged httpx default User-Agent (observed `python-httpx/0.28.1`); only
  `Accept-Encoding: identity` was overridden.
- **Bounds:**
  - 5,000,000-byte response cap and 500-record cap;
  - HTTP phase timeouts of connect 5 s, read 10 s, write 5 s, and pool 5 s;
  - the adapter's 30 s attempt deadline is an elapsed-time check, not a separate timer;
  - one independently supervised 60-second whole-operation deadline.
- **Containment:** the corrected harness ran with Correction 3 containment; the worker exited
  0 with a written summary.
- **Authority and identities:**

  | Item | Identity |
  |---|---|
  | candidate | `408e09e58cf833f72886dfd6e4c8992d3e730089` (harness `7bcc0edff2e1df734b52eba4ad7767bd51c0493b7b84edac5ef129b1cab099c0`) |
  | retry proposal | `1dff80daadefbfa60ff45d6d863f039e68f81694b38dc63e86fafb315e2466e2` |
  | attempt-2 terms decision | `1a1a2513ee4a53034bdf6c4e99473a57cdc4b3fd76b7e24c2a357334a2b3ff06` |
  | attempt-2 U1 authorization | `3fb904ac019ad7ec032c9693de40f03369fd941b6ba03ae025c4d9f9a1df1653` |
  | attempt-2 reservation | `0f89c0c1946007a2027c3a108c5ccc2d1b3c7eb9436ea043637f3c84de0fd329` |
  | attempt-1 reservation archive | `18763cf69c9452d36e96017ee91b9ad3638398726b7dbce24917ef75efd00f5e` |
  | raw capture | 420,784 bytes, `43ca81bd854df7764b691fae8424d2669c750411e43e65036de0890785f215c5` |
  | run summary | `482cc4f5dbeafe40d4f0003d8ca9c5baabb50818589cb7ad1dbb7b24c64169da` |
  | worker launch / claim | `be2632c2f69fcf9e2622eb05e0fd78cca365af8e22439b369711fc519ce1576b` / `551f557cc52b3ed36f020491f6fb80463d9f4b237a12da74c50cd75581aae11c` |
  | projection preview | `7f31b86469220c7c5b737dbe29e367c3c3095f5a6ebb8cf38385513fac91acac` |
  | fidelity packet | `67cb2c50327f36f9a86b1f89cad3a303a718c32fca6c359c95d351340299bce7` |
  | decisions | `cce96428beb80274d5b32c7631b4307a9b29aeebaee8c929c5c632d97aef48c8` |
  | seven-file staging inventory (canonical) | `bbdc7659e1a2bc86bd5e1b18e23c725e041c8dbde7654fe7b898782afa6404bb` |

### Response and processing observations

- HTTP 200, JSON media type.
- **Complete capture:** 420,784 bytes, SHA-256
  `43ca81bd854df7764b691fae8424d2669c750411e43e65036de0890785f215c5`.
- **Source records:** 49, with `meta.total` 49; completeness consistent.
- **Records:** 49 valid, 49 retained, 49 `converted`; 0 invalid, 0 skipped, 0 duplicate,
  and no incomplete results. The board had changed since attempt 1 (48 records then).

| Component | Jobs with a value (49 retained) |
|---|---|
| `employment_type` | 48 |
| `seniority` | 30 |
| `title` (canonical title) | 25 |
| `skills` | 29 jobs, 55 matches |
| `experience`, `remote_type`, `location` (all fields) | 0 |

These are **observations, not accuracy evidence**.

### Fidelity review and verdict

- **Selection:** only source ordinal 0 (`first_converted`), under the frozen converted-first
  rule. All 49 records were eligible and screening-clean. No negative sample was selected,
  because all 49 converted.
- **Lineage** (hashes only; no captured content is reproduced here):

  | Lineage item | SHA-256 |
  |---|---|
  | selected source record (ordinal 0) | `c6630cc4b8911599d35701728f81fe6e8042c85cac7c0cb7d1756548b5c0b099` |
  | selected source content (5,413 code points) | `3d2d39d2d4d65d2fe11fc395d4c64415e05a61f41921bb804275e30b2f17c471` |
  | excerpt `[0, 1005)` (1,005 code points, 1,007 UTF-8 bytes) | `3938fb4de3aaf631089e42d2b403361455425606ad29b8f0a1332b566fde5537` |
  | projected record | `ebf2e02407c77303ccd91bf1ce0e60e1e6789d5e2cc27987e61521706c7753f8` |
  | replay output (876 characters) | `9de972b24f937f6d8b41aa042fda2a15e06280b36ee70b153e6dde9334505ec3` |
  | golden expectations | `a8871bfdd6e281b7aa59b49cb945d9c77c7ff0f1b734632ac87b72fc8996870a` |

  The attempt-2 projection was independently computed and equals the committed attempt-1
  fixture's projection: the selected posting's source record was unchanged.
- **Decisions:** both independent reviewers found full capture faithful, excerpt replay
  faithful, publication safe, excerpt proper and useful, and lineage and golden
  expectations correct. The user adopted all five (reviewer `user`).
- **Verdict:** the offline verdict computation (`build_projection`, with full validation and
  semantic replay, then `compute_verdict`) returned **`PASS` with no findings**.
- **Completion:** under the reviewed rule, only PASS completes the live-evidence
  requirement. When this verdict was first published, cleanup was still pending, and a
  cleanup failure would have been `FAIL-CLOSED`. Cleanup later passed (below). S2c workflow
  publication is not complete until the subsequent `C`/`A`/`R`/`M`/`Q` controls succeed.

### Option-A reproducibility boundary

- The committed attempt-1 fixture and replay test are unchanged. **They do not prove
  attempt-2 fidelity.**
- Attempt 2 has no durable executable fixture. Its staging-only preview is bound by the
  preview, packet, decisions, and inventory hashes above.
- Both reviewers inspected the retained attempt-2 raw-to-preview derivation before
  cleanup.
- Cleanup deleted the attempt-2 preview and full raw response. They can no longer be
  reread or independently replayed. The remaining attempt-2 evidence is only this report,
  the identities, aggregates, lineage hashes, decisions, the cleanup attestation, and Git
  history.
- **No attempt-2 replayability claim is made.**

### Verified cleanup

- **Invocation.** Both Sol Medium and Astra approved the Correction 7 cleanup mechanism,
  and the user asserted single-operator quiescence (as relayed by the user). The reviewed
  harness `cleanup` subcommand then ran **exactly once**, with fixed arguments and no
  retry, fallback, or manual deletion:
  - cleanup candidate and executing SHA `2232d9693b54a225bf87d23ec5d65898a081602f`;
  - harness and checker SHA-256
    `190f9427a2d88a27565412af98441120ccc798d110db1f48d0d0562f6bf21be8`;
  - cleaned at 2026-10-10T23:38:07+00:00.
- **Result:** exit 0, `passed` literally `true`, `checker_failure` null.
- **Attestation** (gitignored; never committed):
  `.claude/runtime/phase4-s2c-attempt2-cleanup-attestation.json`, 3,717 bytes, SHA-256
  `e9a41acedc407ca9db3ae7438920dc9e604726f223ad058250ea71841140d576`.
- **Bound identities:**
  - expected-inventory manifest
    `7bab5eda4f5abd6cc4529a5793a011f2ea8d13a335c2a6271545a3c9e48b88f0`;
  - expected, observed, and attested inventory, all equal:
    `bbdc7659e1a2bc86bd5e1b18e23c725e041c8dbde7654fe7b898782afa6404bb`;
  - raw evidence: 420,784 bytes, SHA-256
    `43ca81bd854df7764b691fae8424d2669c750411e43e65036de0890785f215c5`, Git blob identity
    `fc1d8a9cc83cb65a071afc7a9c70ab2d673faf3f`;
  - attempt-2 reservation `0f89c0c1946007a2027c3a108c5ccc2d1b3c7eb9436ea043637f3c84de0fd329`;
  - attempt-1 archive `18763cf69c9452d36e96017ee91b9ad3638398726b7dbce24917ef75efd00f5e`;
  - fixture `d7e14857e3279090709093d71f0c7c26d3e7baf806f35615c3b32520c75b5249`;
  - report as bound at cleanup, before the checkpoint documentation update,
    `093f59b52b277bd17ff29ed53be95985858af9d1cd5bdd8a0d8bcd9b6419873e`.
- **Verified:**
  - all seven approved staging artifacts were removed;
  - the staging root and every known staging path are absent;
  - all ten pre-deletion checks were literally `true`;
  - exactly fourteen fresh-checker keys were present, all literally `true`;
  - the checker identity matched the reviewed harness, and the executing SHA matched the
    cleanup candidate;
  - no tracked, staged, untracked, or ignored S2c staging residue remained;
  - no runtime path or raw blob identity entered the reviewed Git range or the index;
  - both reservations, the fixture, and the report remained exact.
- **Verdicts unchanged:** attempt 1 remains permanently `FAIL-CLOSED:worker_failed`.
  Attempt 2 remains `PASS` with no findings after cleanup.
- **Limits:**
  - This is logical deletion from controlled project locations, not forensic erasure.
  - The deleted attempt-2 source content can no longer be reread. Attempt 2 has no durable
    executable replay fixture, and the attempt-1 fixture does not prove attempt-2
    fidelity.
  - The remaining attempt-2 evidence is the approved report, the identities, aggregates,
    lineage and decisions, the cleanup attestation, and Git history.
  - The retained post-cleanup filesystem does not independently prove the historical
    absence of every possible unrecorded manual action or network event. The attestation,
    the reservations, Git state, and the retained identities contain no conflicting
    evidence.
  - The evidence does not prove broad normalization accuracy, provider generalization, D1,
    persistence, runtime activation, or production readiness.
  - S2c workflow completion is still pending final `C`/`A`/`R`/`M`/`Q`. **No third
    request is authorized.**

## Salary

No salary-specific parameters or endpoint were requested; no salary field was extracted or composed, and the salary classifier was not invoked. Incidental compensation text may occur in captured content. The bridge supplies no compensation input; ADR 0011 L4 remains open.

## What this proves and does not prove

**Observed:**
- two real list responses from one board, at two times, were captured completely;
- each was processed by the unchanged adapter, converter, bridge, and composition without a
  processing failure;
- their content was compatible with the declared mode;
- the corrected harness completed attempt 2 with a clean worker exit, and its offline
  verdict computation returned PASS.

**Not proven:**
- S2c workflow completion (`C`/`A`/`R`/`M`/`Q` are pending);
- attempt-2 replayability after cleanup;
- normalization accuracy or coverage;
- generalization to other boards, times, or encodings;
- provider stability or rate behavior;
- forensic erasure of deleted content;
- production readiness, runtime registration or activation, or operational use;
- persistence, or D1 compliance;
- salary support.

No production-readiness or generalized-provider claim is made.

## Retained limitations

- Attempt 1 is permanently `FAIL-CLOSED:worker_failed`.
- The corrected harness has completed one live attempt (attempt 2), for one board at one
  time.
- Attempt-1 raw staging was cleaned through the reviewed mechanism (attestation
  `a31f363817c9ac44062cbc1dc06d49053dba3288b0eaf0afb6ef9cc7214ee21f`). Attempt-2 raw staging
  was likewise cleaned (attestation
  `e9a41acedc407ca9db3ae7438920dc9e604726f223ad058250ea71841140d576`). Both are logical
  deletion from controlled project locations, not forensic erasure.
- Once a capture is deleted, omitted source content cannot be reconstructed or
  independently re-verified from hashes.
- Fidelity was reviewed for one excerpt of one record per attempt only.
- Screening for emails, phone numbers, mailto and tel links, and profile URLs is defense
  in depth only. The converted text is unredacted.
- Conversion detects only end-of-input truncation. Text swallowed mid-input by a construct
  that a later quote or `-->` closes would be lost silently.
- Behavior depends on CPython's `html.parser` (verified on 3.12.13).
- D1 is unsatisfied and nothing is persisted or runtime-reachable. ADR 0011 L4 (salary)
  remains open.
- The W1–W12 mutation experiments are manual advisory evidence. No coordinator executed
  them.
- The terms dispositions are the user's accepted residual ambiguity, recorded separately
  for each attempt, for personal, self-hosted, noncommercial use. Attempt 2's decision
  acknowledged changed and uncharacterized legal-page hashes. It is not legal clearance,
  and it grants no recurring-collection authority.
- U1 repeated a stale "55-second per-board bound". The reconciled contract has no separate
  per-board timer: 55 seconds is only the conservative sum of the adapter's internal
  timeouts, under one supervised 60-second deadline. U1 is preserved unchanged, and future
  authorizations must state the corrected model.
- Publication is advisory only: this report is part of the attempt-2 verified-cleanup checkpoint on the S2c feature branch (first published in the attempt-2 post-run advisory candidate), not final-C evidence. Final `C`/`A`/`R`/`M`/`Q` and any further request remain unauthorized. **No third request is authorized.**
