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

- Date/agent: 2026-08-29, Claude Code (Sonnet 5). Authorized slice: Phase 2's first
  vertical slice, the "natural-key ingestion spine" — Class H (first permanent
  ingestion writer; identity/concurrency risk per PHASE_RISK_CHECKLIST.md's Phase 2
  primary risks). Base `903ad0d` on `main` -> branch
  `phase-2/natural-key-ingestion-spine`. Implements the twice-revised, fully
  negotiated proposal (11 binding decisions from the final approval) proving
  Fixture -> `RawJobIngestion` -> identity resolution (natural-key tiers 1/5 only,
  all three key forms) -> `Job`/`JobOccurrence` -> two distinct `CollectionRun`s,
  against real PostgreSQL, zero network, one provider/one source.
- Outcome, per the approved binding decisions:
  1. **Four fixtures, two `CollectionRun`s**: `clean_tenant_scoped` (tenant-scoped
     key), `missing_salary_no_tenant` (no-tenant key), `url_fallback_only`
     (`source_job_id=None`, URL-fallback key), `unprocessable` (`source_job_id=None`
     *and* an unnormalizable relative `source_url` — genuinely no key of any form).
     Run 1 processes all four (`status='completed_with_errors'`, one
     `collection_run_provider_attempts` row `status='completed'`); a `UserJob` is
     created against run 1's tenant-scoped `Job` between the two runs; run 2
     resubmits the three resolvable fixtures byte-identical
     (`status='completed'`). Exact counters: run 1 `jobs_discovered=4/inserted=3/
     updated=0`; run 2 `jobs_discovered=3/inserted=0/updated=3`; 7
     `RawJobIngestion` rows total (4 + 3), 3 `Job`/`JobOccurrence` rows total (never
     duplicated between runs).
  2. **File layout exactly as dictated**: `app/schemas/discovered_job.py`
     (`DiscoveredJob`, `DiscoveryResult`, `ProviderErrorCategory`, `ProviderError`,
     `SourceRunStats`), `app/schemas/provider.py` (`SourceQuery`,
     `SourceCapabilities`, `ProviderCapabilities`, `ProviderHealth`,
     `SourceHealth`), `app/providers/base.py` (`DiscoveryProvider` Protocol only).
  3. **Natural-key canonicalization + advisory lock**
     (`app/ingestion/natural_key.py`): provider/source canonicalized identically to
     `JobOccurrence`'s own ORM validators (trim+lower; documented "must stay in
     sync"); a versioned, domain-tagged (tenant/no-tenant/URL), length-prefixed byte
     encoding (never a colon-joined string) hashed via SHA-256 into a signed 64-bit
     `pg_advisory_xact_lock` key — never Python's `hash()` or Postgres's 32-bit
     `hashtext()`.
  4. Casing/whitespace-collision, component-boundary-ambiguity, and domain-
     separation tests in `test_ingestion_natural_key.py`; genuine concurrent-
     insertion safety proven for **all three** natural-key forms in
     `test_ingestion_concurrency.py` (parametrized), not just the tenant-scoped one.
  5. **Durable run-init transaction**: `CollectionRun`/`CollectionRunProviderAttempt`
     committed `status='running'` *before* `provider.discover()` is ever called, so
     the best-effort failure handler always has rows to update. Run/attempt
     lifecycle timestamps come from an injected `Clock`
     (`app/ingestion/clock.py`, `FixedClock` in tests); `Job`/`JobOccurrence`
     business timestamps come from a separate, explicit `observed_at` parameter.
  6. `last_seen_at` (occurrence and parent `Job`) only ever advances —
     `max(existing, incoming)`, computed against the value read under the row lock
     already held, never a blind overwrite. A dedicated out-of-order-replay test
     proves an older resubmission cannot move it backward.
  7. **Upsert lifecycle**: `pipeline.py` writes each `DiscoveredJob` through two
     transactions — Transaction A_i commits one `RawJobIngestion`
     (`processing_status='fetched'`) independently; Transaction B_i (identity +
     `Job`/`JobOccurrence` upsert + terminal `RawJobIngestion` update, one
     transaction) or Transaction C_i (reroute to `parse_error`) follows. The advisory
     lock (point 3 above) serializes concurrent attempts at the same key so the
     "not found" branch never races — no `ON CONFLICT` clause exists or is needed.
  8. `canonical_json_hash` (`app/ingestion/hashing.py`):
     `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True,
     allow_nan=False)` then SHA-256; tested against top-level and nested key-order
     variation (not just file reloads), Unicode-non-normalized-but-visually-similar
     strings, and NaN/Infinity rejection matching what PostgreSQL's own `jsonb`
     input function would reject.
  9. Only `identity.py`'s one `UnresolvableIdentityError` is ever caught and
     reclassified as `parse_error`. Every other exception — including
     `asyncio.CancelledError` — triggers a best-effort attempt to mark the
     `CollectionRun`/attempt `failed` and is always re-raised;
     `KeyboardInterrupt`/`SystemExit` are never in any `except` clause.
  10. Narrow documentation clarification (no schema/migration change): tier 5
     ("no deterministic match → create a new `Job`") now states explicitly that it
     requires a derivable key (`source_job_id` or a normalizable `source_url`); a
     payload with neither is `parse_error`, not an unkeyed occurrence — added to
     `docs/ARCHITECTURE.md` §8, `docs/DECISIONS/0004-scoped-deterministic-identity.md`,
     and `docs/DATA_MODEL.md`'s `job_occurrences` unique-constraints note.
  11. `FixtureProvider` (`app/providers/fixture.py`) takes its fixture list as an
     explicit constructor argument — fixture selection never hides inside
     `SourceQuery` filters. Contract tests for the schemas layer
     (`test_schemas_discovery.py`, 11 tests): mutable-default isolation (4 cases),
     `DiscoveryResult`'s duplicate-source/orphaned-job/orphaned-error/
     `completed=False`-with-jobs rejections, derived-property behavior;
     `pipeline.py` itself asserts `SourceQuery.sources == DiscoveryResult.
     requested_sources` (a call-site invariant per ARCHITECTURE.md §6.3, not
     something the model can check alone), tested via a deliberately mismatched
     fake provider.
  - `__init__.py` present in all three new packages (`schemas/`, `providers/`,
    `ingestion/`). No migration — every table touched (`jobs`, `job_occurrences`,
    `raw_job_ingestions`, `collection_runs`, `collection_run_provider_attempts`)
    already existed.
- Files changed:
  - `backend/app/schemas/{__init__.py,discovered_job.py,provider.py}` (new).
  - `backend/app/providers/{__init__.py,base.py,fixture.py}` (new).
  - `backend/app/ingestion/{__init__.py,clock.py,hashing.py,identity.py,
    natural_key.py,persistence.py,pipeline.py}` (new).
  - `backend/tests/fixtures/discovery/{clean_tenant_scoped,missing_salary_no_tenant,
    url_fallback_only,unprocessable}.json` (new).
  - `backend/tests/test_ingestion_pipeline.py` (new, 7 tests),
    `test_ingestion_concurrency.py` (new, 1 test × 3 params),
    `test_ingestion_hashing.py` (new, 5 tests), `test_ingestion_natural_key.py`
    (new, 7 tests), `test_schemas_discovery.py` (new, 11 tests) — 33 collected.
  - `docs/ARCHITECTURE.md`, `docs/DECISIONS/0004-scoped-deterministic-identity.md`,
    `docs/DATA_MODEL.md` — narrow tier-5/unkeyed-occurrence clarification (point 10
    above).
- Commands run and exact results:
  - `ruff format --check`/`ruff format` → clean after formatting.
  - `ruff check .` → all checks passed.
  - `mypy .` → success, 91 source files.
  - Targeted (all 5 new test files) → **33 passed**.
  - `pytest -q` (full suite, writable `--basetemp`) → **1139 passed** (up from
    1106 — 33 new tests, all collected, matches exactly).
  - `alembic check` (against `jobgoblin_test`) → `No new upgrade operations
    detected` — confirms no migration needed.
  - `alembic heads` → `0017 (head)`, unchanged.
  - `alembic current` against the **development** database (no override, fresh
    shell) → `0006`, unchanged throughout.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual staged diff before commit; full Class H
  depth): **3 High, 2 Medium fixed; 2 Low documented, not fixed**:
  1. **High — `suppress(Exception)` around the best-effort failure-telemetry
     block did not also suppress `asyncio.CancelledError`** (a `BaseException`
     subclass, not `Exception`), so a second cancellation during that block could
     replace the original exception instead of the intended `raise` re-raising it.
     Fixed: `suppress(Exception, asyncio.CancelledError)`.
  2. **High — the "found" (re-observation) branch used a Core-style `update()`
     statement, which bypasses `JobOccurrence`/`Job`'s own `@validates`
     normalization** that the "not found" (insert) branch gets automatically — an
     incidentally-whitespace-padded or blank re-observed field could be stored
     un-normalized (or violate a `CHECK` a first insert would have satisfied).
     Fixed: rewrote `persistence.py` to fetch and mutate the ORM entities directly
     (`occurrence.field = value`) on both branches, so `@validates` applies
     identically either way. New regression test added
     (`test_reobservation_normalizes_text_fields_identically_to_first_insert`)
     proves a covered-whitespace-only re-observed value collapses to `NULL` and a
     padded value trims, exactly as the insert path already did.
  3. **High — every `CollectionRunProviderAttempt` row was written the run-wide
     aggregate count, not its own source's count** — invisible with one source per
     run (aggregate and per-source coincide), but silently wrong the moment a
     future slice adds a second source, contradicting the model's own "authoritative
     per-source detail" docstring. Fixed: `pipeline.py` now tracks per-source
     discovered/inserted/updated dicts and writes each attempt row its own source's
     numbers; `collection_runs`' three counters remain the correct run-level sum.
     New regression test added
     (`test_per_source_attempt_counters_are_not_the_run_wide_aggregate`, a two-source
     fake provider) proves two sources with deliberately different counts each land
     on their own attempt row correctly.
  4. **Medium — cleanup-tracking lists in `test_ingestion_pipeline.py`'s flagship
     test were populated after assertions that could fail**, risking a leaked row
     in the shared disposable test database on an assertion failure. Fixed:
     moved `raw_ingestion_ids.extend(...)`/`job_ids.extend(...)` to immediately
     after each fetch, before any assertion on the fetched data.
  5. **Medium — the `UserJob`-untouched proof never asserted `updated_at`**, the
     one column the model's own docstring says advances on any write to the row —
     the single strongest signal ingestion never touched `user_jobs`. Fixed: added
     to both the snapshot and the final assertion.
  - **Documented, not fixed** (explicitly out of this slice's approved scope):
    (a) `provider`/`source` values are canonicalized but not validated against the
    ASCII-slug grammar before the lock/lookup stage — a misconfigured provider
    constant would only fail at the database `CHECK` inside Transaction B_i,
    aborting the whole run rather than failing at construction time; acceptable
    since `provider`/`source` are adapter-level constants, not per-posting data, in
    every phase through Phase 4. (b) The concurrency test's race has the same
    timing-luck weakness already accepted elsewhere in this codebase (bare
    `asyncio.gather`, no explicit interleaving barrier) — consistent with existing
    precedent, not a new regression. (c) `DiscoveredJob.raw` has no JSON-
    serializability enforcement at the schema level; a non-JSON-native value would
    raise a generic `TypeError` from `canonical_json_hash`, not a friendly error —
    acceptable since every fixture is JSON-loaded (hence always JSON-safe); a live
    provider adapter (Phase 4+) will need to guarantee this itself.
  - Also explicitly checked and found clean: no other divergence between the
    natural-key canonicalizer and `JobOccurrence`'s ORM validators (stress-tested
    non-ASCII/whitespace input); all three partial-index domains genuinely
    exercised in both the natural-key unit tests and the concurrency test; no FK
    deletion behavior introduced by this slice (none applicable); the new
    ARCHITECTURE.md/ADR-0004/DATA_MODEL.md wording matches what the code actually
    does, not just internally consistent prose.
- Deviations/known limitations: the three "documented, not fixed" items above.
  `source_url`/`source_url_normalized` are deliberately never refreshed on
  re-observation (only observational fields and other display text are) — these are
  the URL-fallback domain's own identity-key components, and blindly overwriting
  them without reconciliation logic would risk a subtle mismatch between what's
  stored and what the row was actually looked up by; not exercised by any test since
  every re-observation fixture in this slice is byte-identical. No `QueryPlanner`,
  `ProviderRegistry`, multiple sources/providers per run, identity tiers 2–4,
  conflict quarantine, company resolution, Phase 3 normalization, live providers,
  API routes, or scheduling — all explicitly out of scope. `main` untouched.
- STOP — awaiting Codex review. Do not begin any further Phase 2 slice (tiers 2–4,
  conflict quarantine, `QueryPlanner`, multi-source), modify or merge `main`, or add
  Phase 3/4/8/9/10 behavior.

### Work review

- Date/reviewer: 2026-08-29, Codex. Diff reviewed: `903ad0d..e725fd2` on
  `phase-2/natural-key-ingestion-spine`. Verdict: **changes requested**.
- Independent verification completed against real PostgreSQL: the five new targeted
  test files pass (**33 passed**); the full suite passes (**1139 passed**); Ruff format
  and lint pass; mypy passes; `scripts/check_repo.py` exits 0; test DB is at sole head
  `0017`; `alembic check` reports no drift. These results establish that the current
  tests and schema are green, but do not close the contract defects below.
- Findings, highest severity first:
  1. **High — re-observation violates the Phase 2 idempotency/conflict contract.**
     `backend/app/ingestion/persistence.py:100-115` overwrites `posted_at`, `apply_url`,
     both canonical-URL fields, `requisition_id_raw`, and the parent `Job`'s title,
     location, compensation text, and canonical URL. The Phase 2 exit gate requires a
     fixture replay to *only* advance observational fields
     (`PHASE_RISK_CHECKLIST.md:136-142`), while ADR 0007 requires a Tier-1 canonical-URL
     mismatch to leave disputed fields untouched and enter conflict quarantine. The
     current behavior can silently erase known values with incoming `NULL`, replace
     canonical evidence, and bypass the deferred provenance/merge policy. The new
     `test_reobservation_normalizes_text_fields_identically_to_first_insert` positively
     codifies this incorrect overwrite behavior. In this bounded slice, make the found
     branch observational-only (`last_seen_at`, `is_active`; applicant fields only if
     the schema later supplies them). Do not mutate descriptive/canonical fields. Add
     regressions proving changed and missing incoming non-observational values remain
     frozen. For a Tier-1 match where both normalized canonical URLs are non-null and
     differ, fail closed with a distinct, non-`parse_error` deferred-conflict exception
     before mutation; do not implement conflict-row persistence without a separately
     approved scope.
  2. **High — a malformed URL can leak secrets/PII into persisted error telemetry.**
     `identity.py:39-42` embeds the raw `source_url` in
     `UnresolvableIdentityError`; `pipeline.py:46-60` stores that exception text in
     `raw_job_ingestions.error_message`. Source URLs commonly contain tokens, query
     strings, or user-identifying data, and the approved observability contract says
     field values must not be exposed. Persist a fixed, sanitized error message/code
     that identifies only the failure class; retain the original evidence solely in
     `raw_payload`. Add a secret-bearing malformed-URL regression proving the secret is
     absent from stored error text and logs.
  3. **Medium — failed-run telemetry loses already-committed progress.**
     `pipeline.py:210-231` marks the run/attempt failed but never writes the counters
     accumulated before the exception. Because each earlier posting commits
     independently, a failure after one successful posting leaves durable Job/raw rows
     while both telemetry rows falsely report zero. The approved proposal explicitly
     required "whatever counts had accumulated so far." Initialize counters before
     fallible provider/posting work, persist the exact run and per-source counters in
     the best-effort failure transaction, and add a fail-on-the-second-posting test.
  4. **Medium — provider result failures and identity are silently misreported.**
     `pipeline.py:137-207` validates only the set of source names. It does not require
     `result.provider == provider.name` or each job's provider to match, and ignores
     `DiscoveryResult.errors`, `SourceRunStats.completed=False`,
     `incomplete_results`, and `possibly_incomplete`; such a result is recorded as a
     fully completed attempt/run. Full partial-failure persistence is excluded from
     this slice, so fail closed before posting writes when any unsupported partial/error
     state is returned, and validate provider identity. Add adversarial tests for a
     mismatched result/job provider and each unsupported partial/error signal. Do not
     implement the later multi-source partial-success policy in this correction pass.
  5. **Medium — the approved safe observability layer is absent.** The proposal required
     `logging.getLogger(__name__)`, payload-free INFO start/end events, a WARNING per
     parse error containing only the raw-ingestion id, and an ERROR at the outer failure
     boundary. No ingestion logger or log call exists. Implement those bounded events
     and use `caplog` to prove both event presence and absence of payload/field values.
     Avoid logging exception messages or traceback locals at this boundary.
  6. **Low — `RawJobIngestion.fetched_at` is populated with the wrong clock.**
     `pipeline.py:145-147` passes the Job/Occurrence business `observed_at`, even though
     the model defines `fetched_at` as the posting's actual fetch event and
     `DiscoveredJob` already supplies `discovered_at`. This collapses timestamps the
     proposal explicitly separated and makes backfill audit ordering inaccurate. Use
     `job.discovered_at` for the raw row, keep `observed_at` exclusively for
     Job/Occurrence observation fields, and test deliberately different timestamps.
- Exact correction scope: address only the six findings above; no migration is expected.
  Replace the regression that expects descriptive-field overwrite, add the specified
  adversarial cases, rerun the Class-H verification matrix and fresh-context self-review,
  append a new `Work done`, and stop for re-review. Do not begin conflict persistence,
  QueryPlanner, tiers 2-4, multi-source partial-success handling, live providers, or
  merge/modify `main`.

## Iteration 2

### Work done

- Date/agent: 2026-08-29, Codex acting as authorized implementer. Class H correction
  pass for the six findings in review commit `fde5fa6`. Branch:
  `phase-2/natural-key-ingestion-spine`; base `fde5fa6` -> correction commit
  `7f01a9f`.
- Outcome:
  1. Re-observation is now observational-only (`last_seen_at` and `is_active`);
     descriptive/source/canonical fields remain frozen. A non-null canonical-URL
     disagreement raises distinct `DeferredIdentityConflictError` before mutation and
     propagates as a failed run; no conflict persistence was added.
  2. Unresolvable identity telemetry is fixed and sanitized at the persistence
     boundary. Raw URLs/payload values never enter error messages or logs.
  3. Failure telemetry now stores exact accumulated run/per-source discovered,
     inserted, and updated counters plus run duration, including failure after an
     earlier posting committed.
  4. The pipeline validates result-provider and job-provider identity and fails closed
     before posting writes for provider errors, incomplete results, or incomplete
     sources. The later partial-success policy remains unimplemented.
  5. Added payload-free INFO start/end, WARNING parse-error (raw-ingestion id only), and
     ERROR failure (run id + exception type only) logging.
  6. `RawJobIngestion.fetched_at` now uses `DiscoveredJob.discovered_at`;
     `observed_at` remains exclusive to Job/Occurrence observation state.
- Files changed: `backend/app/ingestion/{identity.py,persistence.py,pipeline.py}`;
  `backend/tests/test_ingestion_pipeline.py`; this handoff.
- Regression coverage: frozen changed/missing fields; direct and pipeline canonical
  mismatch behavior; secret-bearing malformed URL storage/logging; distinct fetch vs.
  observation timestamps; fail-on-second-posting counters; mismatched result/job
  provider; provider error, incomplete source, and incomplete-results fail-closed
  states. Focused ingestion/schema suite: **41 passed** (was 33). Full suite:
  **1147 passed** (was 1139), using workspace-local `--basetemp` because the host
  profile temp directory denies enumeration.
- Verification: Ruff format/check clean (73 files); mypy clean (91 source files);
  `scripts/check_repo.py` exit 0; `git diff --check` clean; test DB at sole head
  `0017`; `alembic check` reports no drift; development DB confirmed at `0006`.
  No model or migration changed.
- Adversarial Class-H self-review: challenged all 12 workflow questions against the
  correction diff. Fixed one defensive telemetry gap (the private terminal updater
  still accepted arbitrary exception text) and one test-hygiene class (failure-path
  cleanup now derives exact created IDs). The first targeted run also exposed and fixed
  an invalid two-source test fake whose job-provider labels disagreed with its provider.
- Deviation: an initial cleanup command used `TEST_DATABASE_URL`, which Alembic does
  not consume, and temporarily upgraded the development DB from `0006` to `0017`.
  Those newly created later tables were empty; development was immediately downgraded
  back to exactly `0006`, then `jobgoblin_test` was rebuilt with the correct
  `DATABASE_URL` override. Both current revisions were independently reconfirmed
  (`0006` development, `0017` test) before final verification.
- Known bounded limitations: canonical conflicts remain durable raw rows at `fetched`
  with failed run telemetry until the separately approved conflict-quarantine writer;
  partial provider results fail closed until their dedicated persistence slice.
- Rollback/handoff boundary: `7f01a9f` contains all executable corrections and tests;
  reverting that commit restores the reviewed `e725fd2` implementation without any
  schema downgrade or data migration. Review commit `fde5fa6` is documentation-only.
- STOP — awaiting independent review. Do not implement conflict persistence,
  QueryPlanner, tiers 2-4, multi-source partial-success behavior, live providers, or
  modify/merge `main`.

### Work review

- Date/reviewer: 2026-08-29, Claude Code (Sonnet 5) acting as independent reviewer
  (role transferred per the user's explicit instruction for this pass). Diff
  reviewed: correction commit `7f01a9f` against the six findings in review commit
  `fde5fa6`, on `phase-2/natural-key-ingestion-spine` (remote tip `66ae644`, a
  handoff-only rollback-boundary note; no executable change beyond `7f01a9f`).
- Pre-flight target verification (performed before any database command, per
  instruction): `docker exec ... \l` and `\dt` confirmed `jobgoblin` (development)
  holds only the five tables migration `0006` produces and `alembic_version='0006'`;
  `jobgoblin_test` (disposable) is a distinct database at `alembic_version='0017'`.
  `Settings().database_url`/`.test_database_url` resolved as expected (dev URL
  default; test override `None`, falling back to `conftest.py`'s disposable
  default). Reconfirmed both revisions unchanged after every command below.
- Independent verification performed (all against real PostgreSQL, `jobgoblin_test`
  only): `ruff format --check`/`ruff check` — clean; `mypy .` — clean, 91 source
  files; targeted (`test_ingestion_pipeline.py` + the four sibling ingestion/schema
  test files) — **41 passed**, matching the claim; full suite with an explicit
  writable `--basetemp` — **1147 passed**, matching the claim; `alembic heads` —
  `0017 (head)`; `alembic check` (DATABASE_URL explicitly overridden to
  `jobgoblin_test`) — `No new upgrade operations detected`; `scripts/check_repo.py`
  — exit 0; `git status`/`git diff --check` — clean, no executable file touched by
  this review. Development database reconfirmed at `0006` with its original
  five-table shape, both before and after the full run.
- Findings: **none.** Each of the eight required checks was independently
  confirmed by reading the actual diff and exercising it, not by trusting the
  `Work done` summary:
  1. **Re-observation is observational-only.** `persistence.py:118-123` — the
     found branch mutates only `occurrence.last_seen_at`/`.is_active` and the
     parent `Job.last_seen_at`; no descriptive/canonical/source field is touched.
     `test_reobservation_only_advances_observational_fields` submits a replay with
     both changed and `None`-ed descriptive fields and asserts every one of them
     still reads back as the *original* posting's values — passed.
  2. **Canonical-URL conflicts fail closed, pre-mutation, and are never
     `parse_error`.** `persistence.py:107-117` — `DeferredIdentityConflictError`
     is raised before any attribute assignment on the found branch. It is a
     distinct `RuntimeError` subclass; `pipeline.py`'s per-posting loop catches
     only `UnresolvableIdentityError`, so a conflict propagates to the outer
     handler as a failed run, never miscategorized as `parse_error`.
     `test_canonical_evidence_mismatch_fails_closed_before_mutation` (unit level)
     and `test_pipeline_leaves_conflicting_raw_row_fetched_and_marks_run_failed`
     (pipeline level: run `status='failed'`, the conflicting posting's raw row
     stays `'fetched'`, the pre-existing occurrence's `last_seen_at`/
     `canonical_url` are untouched) both passed.
  3. **No raw URL, token, payload value, or exception message ever reaches
     stored telemetry or logs.** `identity.py:26-48` — the exception message is
     now the fixed `UNRESOLVABLE_IDENTITY_MESSAGE` constant (confirmed via
     `git show 7f01a9f -- backend/app/ingestion/identity.py`: the prior code
     literally interpolated `job.source_url!r}` into the exception text — a real
     secret-leak bug, now removed). `pipeline.py`'s `_mark_parse_error` stores
     that same constant, never `str(identity_exc)`. Every `logger.*` call in
     `pipeline.py` (grepped exhaustively — 4 call sites, none in `identity.py`/
     `persistence.py`/`natural_key.py`) logs only IDs, status strings, counts, or
     `type(exc).__name__` — never a message or field value.
     `test_parse_error_telemetry_is_sanitized_logged_safely_and_uses_fetch_time`
     embeds a literal secret token in both `source_url` and `raw` and asserts it
     *is* present in `raw_payload` but absent from `error_message` and every
     captured log record; `test_unexpected_failure_propagates_and_marks_run_failed`
     and the `provider_error` case of
     `test_pipeline_fails_closed_for_unsupported_provider_result_states` repeat the
     same secret-absence proof against a generic exception message and a
     `ProviderError.detail` string, respectively — all passed.
  4. **Failed runs retain exact accumulated counters.** `pipeline.py:154-156,246-249`
     — `per_source_discovered`/`_inserted`/`_updated` are populated incrementally
     during the per-posting loop and read directly (not re-derived from a
     zeroed default) by the outer failure handler.
     `test_unexpected_failure_propagates_and_marks_run_failed` fails deliberately
     on the second of two postings and asserts both the run row and its one
     attempt row report `jobs_discovered=2, jobs_inserted=1, jobs_updated=0` —
     the exact state at the moment of failure, not zero and not the full batch —
     passed.
  5. **Provider-identity mismatches and unsupported partial/error results fail
     closed before any posting write.** `pipeline.py:161-177` — four checks
     (`result.provider`, source-set equality, per-job provider, `possibly_incomplete`)
     all run before `_write_fetched_row` is ever called for any job.
     `test_pipeline_fails_closed_for_unsupported_provider_result_states`
     (parametrized over all 5 cases named in the finding) asserts zero
     `RawJobIngestion` and zero `Job` rows exist afterward for every case — passed.
  6. **Required logging events exist.** `ingestion_run_started`/`_completed` (INFO),
     `ingestion_parse_error` (WARNING, raw-ingestion id only), `ingestion_run_failed`
     (ERROR, run id + exception type only) — all four present and asserted via
     `caplog` in the tests cited under (3)/(4) above.
  7. **`RawJobIngestion.fetched_at` uses `DiscoveredJob.discovered_at`.**
     `pipeline.py:182-184` passes `job.discovered_at`, not `observed_at`.
     `test_parse_error_telemetry_is_sanitized_logged_safely_and_uses_fetch_time`
     asserts `raw.fetched_at == job.discovered_at` **and** `!= observed_at` with
     deliberately distinct values — not merely coincidentally equal — passed.
  8. **Test cleanup is failure-safe; no schema/migration drift.** Every new/edited
     test either captures IDs immediately after each fetch and before any
     assertion on that data (the pattern this same review required last pass), or
     — in the two tests exercising `pipeline.run()` against a pre-existing
     occurrence — snapshots the full set of `Job`/`CollectionRun`/
     `RawJobIngestion` ids before the test body runs and cleans up the set
     difference afterward, which is strictly more robust against a missed
     `extend()` call. `alembic check` reports no drift; no migration file exists
     in this diff; development database independently confirmed unchanged at
     `0006` before and after this review's own verification run.
- Also explicitly checked, no defect found: the two-source counter test's fixture
  postings correctly set `provider="two_source_provider"` matching the fake
  provider's own `DiscoveryResult.provider` (the self-reported "invalid two-source
  test fake" bug from the prior pass — verified fixed, not merely claimed fixed);
  the concurrency test suite (`test_ingestion_concurrency.py`) is unaffected by the
  canonical-URL-conflict check, since every concurrent pair submits an identical
  payload (identical canonical URL cannot "disagree" with itself); no product
  documentation (`ARCHITECTURE.md`/`DATA_MODEL.md`/ADRs) was touched by this
  correction, consistent with the review's own explicit scope boundary (conflict
  persistence/quarantine documentation is deferred alongside the conflict-writer
  itself, not part of this bounded pass).
- Missing/inconclusive checks: none. Every one of the eight required checks was
  independently reproducible against real PostgreSQL, not merely inferred from the
  `Work done` narrative.
- **Verdict: approved. No corrections required.**
- STOP — awaiting user merge authorization. Do not implement conflict persistence,
  `QueryPlanner`, identity tiers 2–4, multi-source partial-success handling, live
  providers, or modify/merge `main` without separate authorization.
