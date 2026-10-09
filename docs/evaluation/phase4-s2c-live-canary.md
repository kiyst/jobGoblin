# Phase 4 S2c live canary report — attempt 1

> **Official outcome: `FAIL-CLOSED:worker_failed`.** This is the controlling verdict and is
> permanent. Attempt 1 can never become PASS, PASS-WITH-FINDINGS, or INCONCLUSIVE, however
> clean its processing summary is. S2c has not passed.

Post-run advisory report. The user approved this minimized report and projected fixture for publication to the S2c feature branch for post-run advisory review. They are not final-C evidence, and attempt 1 remains permanently `FAIL-CLOSED:worker_failed`. Governing record:
[ADR 0017](../DECISIONS/0017-greenhouse-live-canary.md). Bounded by ADR 0017 §7:
aggregates, categorical observations, and no titles, locations, warnings, exception text,
raw keys, or descriptions.

## What ran

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

## Response and processing observations

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

## Why the outcome is `FAIL-CLOSED:worker_failed`

The worker completed processing and wrote its run summary. It then exited with 0xC0000005
instead of 0, so the supervisor correctly recorded a failure:

- The cause was the defense-in-depth daemon stdin watchdog. It was still blocked reading
  the supervisor's open stdin pipe, holding stdin's buffer lock, at interpreter shutdown.
- CPython then aborted with `Fatal Python error: _enter_buffered_busy`.

**Correction 3** (candidate `3d9404b0fe42663457ad80cf58f791e801bd7ff4`) removes that
watchdog. The verified kill-on-close Job Object remains the sole parent-loss containment.
A real-process regression now proves a successful worker exits 0 with no shutdown
diagnostic. Sol Medium and Astra approved Correction 3 (as relayed by the user).

**The corrected harness has not yet completed a live attempt.** A separately authorized new
request is required before S2c can pass. It needs new U1 network authorization stating the
corrected timeout model, plus an explicitly authorized reservation reset.

## Fidelity review (bounded)

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

## Salary

No salary-specific parameters or endpoint were requested; no salary field was extracted or composed, and the salary classifier was not invoked. Incidental compensation text may occur in captured content. The bridge supplies no compensation input; ADR 0011 L4 remains open.

## What this proves and does not prove

**Observed:**
- one real list response from one board, at one time, was captured completely;
- it was processed by the unchanged adapter, converter, bridge, and composition without a
  processing failure;
- its content was compatible with the declared mode.

**Not proven:**
- S2c passing, or the corrected harness working live;
- normalization accuracy or coverage;
- generalization to other boards, times, or encodings;
- provider stability or rate behavior;
- production readiness, runtime registration, or operational use;
- persistence, or D1 compliance;
- salary support.

No production-readiness or generalized-provider claim is made.

## Retained limitations

- Attempt 1 is permanently `FAIL-CLOSED:worker_failed`.
- The corrected harness is untested live.
- Raw cleanup is still pending. Once the capture is deleted, omitted source content cannot
  be reconstructed or independently re-verified from hashes.
- Fidelity was reviewed for one excerpt of one record only.
- Screening for emails, phone numbers, mailto and tel links, and profile URLs is defense
  in depth only. The converted text is unredacted.
- Conversion detects only end-of-input truncation. Text swallowed mid-input by a construct
  that a later quote or `-->` closes would be lost silently.
- Behavior depends on CPython's `html.parser` (verified on 3.12.13).
- D1 is unsatisfied and nothing is persisted or runtime-reachable. ADR 0011 L4 (salary)
  remains open.
- The W1–W12 mutation experiments are manual advisory evidence. No coordinator executed
  them.
- The terms disposition is the user's accepted residual ambiguity for one personal,
  self-hosted, noncommercial canary. It is not legal clearance.
- U1 repeated a stale "55-second per-board bound". The reconciled contract has no separate
  per-board timer: 55 seconds is only the conservative sum of the adapter's internal
  timeouts, under one supervised 60-second deadline. U1 is preserved unchanged, and future
  authorizations must state the corrected model.
- Publication is advisory only: this report and the fixture are the post-run advisory candidate on the S2c feature branch, not final-C evidence. Final `C`/`A`/`R`/`M`/`Q` and any new request remain unauthorized.
