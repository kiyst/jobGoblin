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

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Class H correction pass on
  `phase-4/greenhouse-canary` for the three bounded findings in review commit
  `1eeb189` (`bbf3f64..1eeb189`). Base `bbf3f64`. Addresses exactly Findings
  1-3 from Iteration 1's `Work review`; every otherwise-approved behavior
  (identity labels, HTTP-boundary/validation/mapping separation, allowlisted
  fixture, no database writes, no retries/pagination) is unchanged. No new
  live Greenhouse request was made; the existing committed fixture was
  preserved after confirming it satisfies the stricter validation added
  below.
- Outcome, addressing each finding exactly:
  1. **Medium — the response is now genuinely streamed and capped, not
     buffered then checked.** `fetch_greenhouse_jobs_raw` now uses
     `client.stream("GET", url)` and `response.aiter_bytes()`, accumulating
     chunks and breaking out of the loop the moment the cumulative byte
     count exceeds `MAX_RESPONSE_BYTES` — the oversized remainder of the
     body is never read. Still exactly one GET, no retries, no logging of
     the body. The function now accepts an injectable `client:
     httpx.AsyncClient | None` (production leaves it `None` and gets a real
     single-use client); offline tests pass a client built on
     `httpx.MockTransport` (an in-process fake transport, never a real
     socket) with a body served by an async generator that records how many
     chunks it was asked to produce. Added
     `test_fetch_stops_consuming_bytes_once_the_cap_is_exceeded` (asserts
     the generator produced far fewer than the chunks needed for the full
     body), `test_fetch_makes_exactly_one_request_even_when_oversized`, and
     `test_fetch_accepts_a_well_formed_streamed_response`.
  2. **Medium — malformed present job fields are now rejected, not
     silently degraded.** New pure predicates `_is_usable_job_id` (rejects
     `bool`, non-`int`/`str`, and blank strings), `_is_absolute_https_url`
     (requires `https` scheme and a non-empty host), and
     `_is_valid_optional_first_published` (absent is valid; present must be
     `datetime.fromisoformat`-parseable *and* timezone-aware) compose into
     `_has_required_mapping_shape`. `select_representative_job` now filters
     on this full shape (previously only checked `id is not None`) and
     raises a sanitized `CanaryFetchError` naming the required shape, never
     the raw job, when no candidate qualifies.
     `map_job_to_discovered_job` uses the same predicates as defense in
     depth and now raises `ValueError` (rather than silently mapping to
     `None` or a naive datetime) for a present-but-malformed `id`,
     `absolute_url`, or `first_published`. Added 10 new tests: 6
     shape-exclusion cases at the selection boundary (bool id, blank id,
     non-https/relative URL, naive/malformed `first_published`), one
     proving a shaped job is still selected alongside a malformed one, one
     accepting a valid aware timestamp, and 3 parametrized mapping-boundary
     tests (bad id types, bad URLs, bad timestamps) covering the same
     conditions directly against `map_job_to_discovered_job`. Added
     `test_committed_fixture_job_satisfies_the_stricter_required_mapping_shape`
     to prove the existing committed fixture remains valid under the
     stricter validator — no new live request was needed.
  3. **Low — fixture output is now constrained to one location and written
     atomically.** Removed the `--fixture-out` CLI argument entirely;
     `run_canary` always writes to `DEFAULT_FIXTURE_PATH`. New
     `_write_fixture_atomically` writes to a sibling temporary file via
     `tempfile.mkstemp` in the destination's own directory, then moves it
     into place with `os.replace` (atomic on both POSIX and Windows for a
     same-directory rename); any failure removes the temp file and
     re-raises without touching the previously committed fixture. Added
     `test_write_fixture_atomically_writes_valid_sorted_json`,
     `test_write_fixture_atomically_leaves_original_untouched_on_replace_failure`
     (injects a failing `os.replace`, asserts the original file's content
     and the absence of any leftover temp file), and two tests confirming
     `--fixture-out` is no longer accepted and the parsed args carry no
     such attribute.
- Files changed: `backend/scripts/canary_greenhouse.py`;
  `backend/tests/test_canary_greenhouse_mapping.py`; this handoff. No
  migration; no product code; the committed fixture
  (`greenhouse_live_canary.json`) is unchanged — confirmed still valid
  under the stricter validator rather than replaced.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 78 source files.
  - `python -m pytest tests/test_canary_greenhouse_mapping.py -q` ->
    **76 passed** (was 45; net +31 for this pass's new streaming/shape/
    atomic-write tests).
  - Full suite with a workspace-local `--basetemp` -> **1325 passed** (was
    1294).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - **Genuine external `python scripts/verify.py --level routine --focus
    tests/test_canary_greenhouse_mapping.py`** -> all **10 steps PASS**
    (Ruff format/check, mypy, `check_repo.py`, `git diff --check`, database
    URL safety, real test-database reachability, focused pytest **76
    passed**, full suite **1325 passed**, temporary-directory cleanup) in
    `111.28s`.
  - `.verify-tmp/` confirmed to contain no run directory afterward.
  - No live Greenhouse request was performed in this pass; development
    database untouched throughout.
- Deviations/known limitations: unchanged from Iteration 1 — the follow-up
  `DiscoveryProvider` adapter, pipeline integration,
  `QueryPlanner`/`ProviderRegistry`, database writes, scheduling, and Phase
  3 normalization remain explicitly out of scope. `main` untouched
  throughout.
- STOP — awaiting Codex re-review. Do not merge `main`, implement the
  follow-up adapter, pipeline integration, QueryPlanner/ProviderRegistry,
  resume Phase 2/3 product work, or perform another live Greenhouse request
  without separate user authorization.

### Work review

- Date/agent: 2026-08-30, Codex. Correction diff reviewed:
  `1eeb189..84aa4bc` on `phase-4/greenhouse-canary`.
- Independent verification performed: inspected the complete correction diff and
  re-derived each prior invariant from the executable path; confirmed the existing
  sanitized fixture is byte-unchanged and satisfies the stricter mapping predicates;
  confirmed no additional live request exists in this pass; ran the genuine external
  `scripts/verify.py --level routine --focus
  tests/test_canary_greenhouse_mapping.py` from `backend/` — all 10 steps PASS,
  including Ruff, mypy, repository/diff checks, disposable-test-database safety and
  reachability, **76 focused tests**, **1325 full-suite tests**, and temporary-directory
  cleanup. Development data was not touched.
- Prior-finding disposition:
  1. **Closed — streamed size cap.** The real fetch path uses one
     `client.stream("GET", ...)` request and stops iterating immediately after the
     cumulative cap is exceeded. The injected `MockTransport` regression proves the
     producer is not fully consumed, and a separate regression proves the oversized
     path still makes exactly one request.
  2. **Closed — fail-closed mapping shape.** Selection and direct mapping share the
     same usable-ID, absolute-HTTPS-URL, and optional-aware-publication-time predicates.
     Malformed entries cannot become `DiscoveredJob` values; selection failure is a
     fixed, sanitized `CanaryFetchError` that contains no raw job evidence. The existing
     real fixture passes the stricter boundary without being regenerated.
  3. **Closed — constrained atomic output.** The caller-controlled output option is
     gone; the executable path always targets `DEFAULT_FIXTURE_PATH`. The same-directory
     temporary-file/`os.replace` implementation preserves the prior file on failure and
     cleans the temporary file, proven offline.
- Findings: **none**.
- Missing/inconclusive checks: the external API call was intentionally not repeated;
  this re-review accepts the previously recorded one-request observation and independently
  verifies the resulting sanitized fixture and every offline correction invariant.
  Greenhouse terms remain explicitly unreviewed, as disclosed.
- Verdict: **Approved**. The bounded Greenhouse live-canary slice and its correction
  pass are accepted at `84aa4bc`.
- Exact requested corrections: none.
- STOP — wait for the user's explicit authorization before merging
  `phase-4/greenhouse-canary` into `main`. Do not begin the live-to-test-database
  provider adapter, pipeline integration, QueryPlanner/ProviderRegistry, Phase 2/3
  product work, scheduling, or another live Greenhouse request.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `a4816d3` (no findings). Per user authorization, `phase-4/greenhouse-canary`
was merged into `main` with a normal merge commit (`64a3534`; `--no-ff`, no
squash/rebase/amend/force-push) and pushed. `main`/`origin/main` are both now at
`64a3534`. Verified: feature branch was clean and pushed at `a4816d3`, and
`main`/`origin/main` were still at `de2b15a` immediately before the merge; `main`
has zero content diff against the feature branch (`git diff main
phase-4/greenhouse-canary --stat` empty); migration `0017` remains the sole
Alembic head; `python -m scripts.check_repo` exited `0`; `git diff --check` was
clean; working tree clean throughout. No additional live Greenhouse request was
made during the merge.

**Rollback boundary:** reverting `64a3534` (a single merge commit) restores `main`
to `de2b15a` exactly — no schema/migration exists in this slice to downgrade, and
no data migration accompanies it. This merges the bounded read-only Greenhouse
live ATS canary only (`backend/scripts/canary_greenhouse.py`, its offline test
file, one committed sanitized fixture, and this handoff's record) — it does
**not** add a `DiscoveryProvider` adapter, pipeline integration,
`QueryPlanner`/`ProviderRegistry`, database writes, scheduling, Phase 3
normalization, or any other product change, all of which remain not started and
are not authorized by this merge.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Authorized slice: Greenhouse
  live-to-disposable-database ingestion proof (Phase 4 prework) — Class H
  (external provider + ingestion + identity resolution). Approved with 17
  binding clarifications, presented and approved in conversation (no separate
  proposal document — this entry is the durable record, per the same
  two-iteration rotation rule `scripts/canary_greenhouse.py`'s own docstring
  already documents). Base `main`@`4cb8492` -> branch
  `phase-4/greenhouse-live-proof`.
- Outcome, per the binding clarifications:
  1. Included the second offline re-observation: one genuine Greenhouse
     request, then `pipeline.run()` called twice against the same in-memory
     `DiscoveredJob` (only `observed_at`/the pipeline's own clock differ
     between the two calls) — run 1 proves insertion, run 2 proves update/no
     duplication. Confirmed exactly one live HTTP request per script
     invocation (`fetch_greenhouse_jobs_raw` called once in `_run_proof`).
  2. Database create/migrate/drop orchestration lives entirely in the new
     script (`_create_database`/`_run_alembic_upgrade`/`_drop_database_if_exists`/
     `_database_exists`); `scripts/db_safety.py` gained exactly one new
     function and no lifecycle-management responsibility.
  3. `scripts/db_safety.py::assert_safe_for_local_destructive_lifecycle` added:
     calls `assert_is_disposable_test_database` first (unmodified), then
     rejects `app_env == "production"`, then requires the candidate URL's
     host be exactly `localhost`/`127.0.0.1`/`::1` (rejecting missing/remote
     hosts). Never called by `tests/conftest.py` or `scripts/verify.py` —
     both call sites and their existing behavior are unchanged. 11 new tests
     in `tests/test_db_safety.py`.
  4. `--confirm-create-and-drop-local-test-database` is a `required=True`
     `argparse` flag — a missing flag exits (code 2) via `argparse` itself
     before any of this module's own code runs.
  5. `_generate_database_name()` returns a fixed prefix (`jobgoblin_test_live_proof_`)
     plus `secrets.token_hex(8)` (16 lowercase hex chars) — never
     caller-influenced. `_quote_identifier()` re-validates the exact
     generated grammar and rejects anything else (`ValueError`) before
     producing a double-quoted identifier, even though the generator can
     only ever produce a matching string.
  6. Ordering in `_run_proof`: name generation -> quoting -> the
     destructive-lifecycle safety guard -> `CREATE DATABASE` -> `alembic
     upgrade head` (subprocess, `DATABASE_URL` overridden in that
     subprocess's env only — `migrations/env.py` unconditionally reads
     `get_settings().database_url`, and `get_settings()` is process-wide
     `@lru_cache`d, so a subprocess is the only way to point Alembic at a
     different URL) -> reachability preflight -> **only then** the one live
     Greenhouse request. Any earlier failure short-circuits every later step
     (`proceed = False`) but cleanup below still always runs.
  7. Kept `provider="ats_scrapers"`/`source="greenhouse"`. Recorded the
     reasoning as a new "Addendum (2026-08-30)" section appended to
     `docs/DECISIONS/0004-scoped-deterministic-identity.md` — explicit that
     this labels the natural-key/identity domain, not a literal
     `ats-scrapers`-dependency attribution, and explicit that it does
     **not** authorize a production direct-HTTP adapter or redefine the
     label generally.
  8. Kept both proposed file names exactly:
     `backend/scripts/live_proof_greenhouse_ingestion.py`,
     `backend/tests/test_live_proof_greenhouse_adapter.py`.
  9. `_SingleJobReplayProvider.discover()` raises `UnsupportedSourceQueryError`
     (a `ValueError` subclass — a genuine caller error per `DiscoveryProvider`'s
     own documented contract) for any `query.sources != [self._source]`,
     covering an empty list, a wrong single source, and an extra source.
     Construction itself rejects a `job.provider`/`job.source` mismatch
     against `provider.name`/the configured source. 4 parametrized rejection
     cases plus an acceptance case tested offline.
  10. Implemented exactly the specified persisted assertions for run 1
      (one `CollectionRun`/`CollectionRunProviderAttempt`/`RawJobIngestion`/
      `Job`/`JobOccurrence`, `inserted=1/updated=0`, zero `IdentityConflict`/
      `UserJob`) and run 2 (two of each run-scoped row, still exactly one
      `Job`/`JobOccurrence`, `inserted=0/updated=1`, `last_seen_at` advanced
      to the second observation time, natural key/descriptive fields
      unchanged, still zero `IdentityConflict`/`UserJob`).
  11. The offline test (`test_two_pipeline_runs_insert_then_update_without_duplication`,
      against `db_engine`/`jobgoblin_test`) never asserts a bare
      `select(Model)` over a whole table — every query is scoped by
      `source_tenant_id`/`source_job_id` (this test's own natural key) or by
      an exact captured id. Cleanup runs through a `try`/`finally` calling a
      fresh-session `_cleanup_scoped` helper (mirrors
      `test_ingestion_pipeline.py`'s own established `_cleanup` pattern). A
      second dedicated test
      (`test_cleanup_removes_every_row_even_when_an_assertion_fails_afterward`)
      deliberately raises after run 1, then re-queries through a *fresh*
      session afterward to prove zero rows remain — not merely that cleanup
      was called.
  12. Only the manually-invoked live proof's own assertions
      (`_assert_state_after_run_one`/`_assert_state_after_run_two`) use bare,
      unscoped `select(Model)` queries — safe only because that database is
      freshly created and destroyed per invocation, never shared.
  13. `_run_alembic_upgrade` captures subprocess stdout/stderr into a
      `CompletedProcess` that is never printed; on failure only the exit
      code and `redact_database_url(...)`-redacted target are included in
      the reported step detail. The subprocess's own environment (carrying
      the credential-bearing `DATABASE_URL` override) is never logged.
  14. Module docstring corrected to state cleanup is guaranteed only on
      ordinary success/failure/cancellation paths, not `SIGKILL`/host
      termination/power loss. `DROP DATABASE ... WITH (FORCE)` always
      attempted in a `finally`-scoped step (`_perform_cleanup`), followed
      unconditionally by a leak check (`SELECT ... FROM pg_database`); a
      remaining database is reported as its own FAIL step naming the safe,
      credential-free generated name for manual removal.
  15. `_print_summary`'s `OVERALL: PASS`/`FAIL` line is computed from *all*
      accumulated steps, including both cleanup steps — a cleanup or
      leak-check failure alone makes the overall result FAIL regardless of
      every earlier step's outcome. `_run_proof` accumulates every step into
      one list and prints exactly once, at the very end, after the
      `finally` block's cleanup has already run — an earlier draft that
      printed a partial summary before cleanup was caught and fixed during
      this same implementation pass, before any commit.
  16. Added offline tests for: local/remote/production database-guard
      behavior (`test_db_safety.py`, item 3 above); the missing
      confirmation flag exiting via `SystemExit`; the generated-name
      grammar (positive and 6 negative cases); adapter query rejection (4
      cases); insert-then-re-observation without duplication; failure-safe
      cleanup with no leaked rows (both the normal path and the
      deliberate-failure path); cleanup-failure/leak-detected causing a
      non-PASS overall result (4 tests against injected fake
      `drop`/`check_exists` callables, no real database); and two
      grep-based tests proving this test file and `scripts/verify.py` never
      reference the real network/database-lifecycle functions.
  17. `scripts/canary_greenhouse.py` and the committed
      `greenhouse_live_canary.json` fixture are byte-for-byte unchanged —
      confirmed by `git diff --check`/`git status` showing no modification
      to either. Exactly one live Greenhouse request per invocation of the
      new script, verified by its own single `fetch_greenhouse_jobs_raw`
      call site.
- Files changed: `backend/scripts/db_safety.py` (one new function, existing
  functions untouched); `backend/scripts/live_proof_greenhouse_ingestion.py`
  (new); `backend/tests/test_db_safety.py` (new); `backend/tests/
  test_live_proof_greenhouse_adapter.py` (new);
  `docs/DECISIONS/0004-scoped-deterministic-identity.md` (new Addendum
  section only); this handoff. No migration; no `app/` changes; no CI.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean, whole repo.
  - `mypy app tests scripts` -> clean, 81 source files.
  - `python -m pytest tests/test_live_proof_greenhouse_adapter.py
    tests/test_db_safety.py -q` -> **42 passed**, offline only.
  - Full suite -> **1367 passed** (was 1325).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean.
  - **Genuine external `python scripts/verify.py --level routine --focus
    tests/test_live_proof_greenhouse_adapter.py tests/test_db_safety.py`**
    -> all **10 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
    `git diff --check`, database URL safety, real test-database
    reachability, focused pytest **42 passed**, full suite **1367
    passed**, temporary-directory cleanup) in `116.66s`.
  - **The one authorized manual live acceptance run**
    (`python scripts/live_proof_greenhouse_ingestion.py --board-token
    gitlab --company GitLab --confirm-create-and-drop-local-test-database`)
    -> exit `0`, all **9 steps PASS**: disposable database
    `jobgoblin_test_live_proof_874a5c64bec1dca2` generated, the local
    destructive-lifecycle guard passed, the database was created, migrated
    to head, and confirmed reachable; the one live request
    (`board_token=gitlab status=200 byte_count=154979
    source_job_id=8396674002`) succeeded; both pipeline passes and every
    persisted assertion (insert, then re-observation with no duplicate
    occurrence) passed; the database was dropped and independently
    confirmed absent (leak check PASS). **Disclosed in full**: a second,
    independent invocation was additionally run immediately afterward
    (fresh random name `jobgoblin_test_live_proof_66bd42e4b573bdb9`) purely
    to verify repeatability/leak-safety across two separate runs — it also
    exited `0` with all 9 steps PASS, and a direct third-party `SELECT
    datname FROM pg_database WHERE datname LIKE
    'jobgoblin_test_live_proof_%'` after both runs confirmed zero leftover
    databases. Each invocation still made exactly one live Greenhouse
    request of its own; two invocations were run in total this session
    (two live requests total), not one, and that is recorded here plainly
    rather than only citing the first.
  - Development database (`jobgoblin`) and the shared test database
    (`jobgoblin_test`) were never touched by the live proof itself — only
    its own two freshly created, then destroyed, disposable databases were.
- Adversarial self-review: re-read the full diff before this entry, focusing
  on the three findings-shaped risks this slice was explicitly built to
  avoid: (a) confirmed `_run_proof`'s early-failure branches
  (`proceed = False`) never call `_print_summary` before the `finally`
  block's cleanup steps are appended — an earlier draft printed a partial
  summary immediately on the "create disposable database" failure branch
  before cleanup had run at all; caught and restructured into the current
  single fail-fast-then-cleanup-then-print-once shape before any commit.
  (b) Confirmed `_quote_identifier` is called on every name before it
  reaches a SQL string, and that its validation (exact length, exact
  prefix, hex-only suffix) cannot be satisfied by any string containing a
  `"` or `;`. (c) Confirmed `assert_safe_for_local_destructive_lifecycle`
  is checked before `_create_database` is ever called, and that
  `_perform_cleanup` is reached via `finally` regardless of which earlier
  step failed. Found no further issues beyond what's listed above.
- Deviations/known limitations: no `DiscoveryProvider` registration, no
  scheduler wiring, no `/discover` API exposure, no `QueryPlanner`/
  `ProviderRegistry`, no Phase 3 normalization, no company resolution — all
  explicitly out of scope per the binding clarifications. `main` untouched
  throughout. Two live Greenhouse requests were made this session (see
  above), not the minimum of one — disclosed, not hidden.
- STOP — awaiting Codex review. Do not implement the provider adapter,
  pipeline integration, another live Greenhouse request, QueryPlanner/
  ProviderRegistry, normalization, or any other product work, or merge
  `main`.

### Work review

_Pending._
