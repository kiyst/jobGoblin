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
  `tooling/workflow-v3-routine-verifier` for the three bounded findings in
  review commit `103fbaa` (`6000658..103fbaa`). Base `6000658`. Addresses
  exactly Findings 1-3 from Iteration 1's `Work review`; every
  otherwise-accepted routine-verifier behavior (safety extraction, command
  structure, direct repository-check step, focus validation, non-recursive
  tests, database preflight/redaction, unique run directories, Workflow-v3
  durable rules, Phase-2 status, result model) is unchanged.
- Outcome, addressing each finding exactly:
  1. **Medium — `git diff --check` now works in the Codex reviewer
     environment.** `git_diff_check_command()` returns
     `["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "diff",
     "--check"]` — command-local via `-c`, never global/user Git config.
     `REPO_ROOT.as_posix()` (forward slashes) because Git's config-value
     parser treats a bare backslash as an escape character, which a raw
     Windows path would otherwise trip. Added
     `test_git_diff_check_command_is_the_one_non_python_step`'s exact-argv
     assertion (including a `no backslash` check) and reran the genuine
     `python scripts/verify.py --level routine --focus tests/test_verify.py`
     from both `backend/` and the repository root.
  2. **Medium — temporary-directory cleanup now fails closed and is its own
     reported step.** `safe_rmtree()` now refuses `path == must_be_under`
     (a strict-child check, not merely `is_relative_to`, which is trivially
     true of a path and itself) and never passes `ignore_errors=True` — its
     new injectable `remove` parameter (default `shutil.rmtree`) lets a
     deletion failure propagate to the caller instead of being swallowed.
     New `cleanup_run_dir_step()` wraps it as a PASS/FAIL `StepResult`; new
     `_execute_and_cleanup()` runs the step list, then *always* appends the
     cleanup result in a `finally` — including after an earlier verification
     failure — before returning. `main()` now builds its exit code from
     *all* results, so a failed cleanup alone makes the run exit nonzero.
     Added 8 tests: root-refusal, a genuinely-surfaced deletion failure (via
     injected `remove`, since real filesystem permission failures are
     unreliable to simulate portably), a nonexistent-child deletion now
     correctly raising instead of silently succeeding, `cleanup_run_dir_step`
     PASS/FAIL reporting, and — via `_execute_and_cleanup` — cleanup still
     running and reported after an earlier step's failure, a surfaced
     cleanup failure making the overall result set non-all-PASS, and
     concurrent-run isolation (cleaning up one invocation's directory never
     touches a second, still-active one).
  3. **Low — corrected the remaining stale Phase-1 ROADMAP statements.**
     `docs/ROADMAP.md`: "Phase 1: in progress (updated 2026-08-28)" ->
     "Phase 1: complete (updated 2026-08-30)"; removed the closing claim that
     "the rest of Phase 1's exit gate... remains to be independently
     verified before declaring the phase complete", replaced with the
     Git-verified basis for completion — all fifteen tables migrated, the
     `phase-1/closure` slice merged (`bfdd56d`), and Phase 2 subsequently
     authorized and three vertical slices merged, which
     `PHASE_RISK_CHECKLIST.md`'s own phase-gating rule could not have
     permitted had Phase 1's exit gate not already been satisfied. The
     already-correct three-slice Phase-2 paragraph is untouched. Recorded
     here, in this new entry — Iteration 1's historical `Work done`/
     `Work review` text is left exactly as written.
- Files changed: `backend/scripts/verify.py`; `backend/tests/test_verify.py`;
  `docs/ROADMAP.md`; this handoff. No migration; no product code; no
  `db_safety.py` change (Finding 1/2 are both `verify.py`-local).
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 76 source files.
  - `python -m pytest tests/test_verify.py -q` -> **73 passed** (was 65;
    net +8 for this pass's new/replaced cleanup and Git-argv tests).
  - Full suite with a workspace-local `--basetemp` -> **1249 passed** (was
    1241).
  - `python -m scripts.check_repo` -> exit 0, zero findings (confirms the
    ROADMAP.md edits introduced no broken links/anchors and no stale
    migration-revision references — `bfdd56d` is a commit hash, not a
    4-digit migration revision, so it does not trip that check).
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - **Genuine external verifier reruns** (never from inside pytest): both
    `cd backend && python scripts/verify.py --level routine --focus
    tests/test_verify.py` and the repository-root equivalent
    (`python backend/scripts/verify.py --level routine --focus
    tests/test_verify.py`) -> all **10** steps PASS in each run, including
    the new `temporary-directory cleanup` step; `focused pytest` **73
    passed**, `full pytest suite` **1249 passed**.
  - `.verify-tmp/` confirmed to contain only the empty, gitignored root after
    every run in this pass.
- Adversarial self-review (fresh read of the corrected diff before this
  entry): confirmed the strict-child check is evaluated *before*
  `is_relative_to` specifically because `Path.is_relative_to` is trivially
  true of a path compared to itself — without the explicit `resolved ==
  root` branch, the prior code would have let `must_be_under` itself reach
  `remove()`, exactly the defect Codex found. Confirmed `_execute_and_cleanup`
  correctly appends the cleanup result even when `_run_steps` itself never
  raises (the normal case, including the fail-fast/NOT-RUN path) and traced
  that an unexpected exception escaping `_run_steps` would still run cleanup
  via `finally` before re-propagating (a genuine crash, not a reported
  result — outside this finding's scope, unchanged from before). Confirmed
  `main()`'s `remove=` is never overridden from its real default in
  production, only in tests. Found no further issues beyond the three
  findings addressed above.
- Deviations/known limitations: unchanged from Iteration 1 (no CI, markers,
  `--level schema`/`--level high-risk`, status generator, metrics, or
  handoff automation; `--level` choices remain `["routine"]` only). `main`
  untouched throughout.
- STOP — awaiting Codex re-review. Do not add CI, schema/high-risk levels,
  markers, status automation, handoff automation, metrics, or resume product
  work, or merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Correction diff reviewed:
  `103fbaa..1f54e20` on `tooling/workflow-v3-routine-verifier`.
- All three findings from review commit `103fbaa` are closed:
  1. The Git step now applies the script-derived repository path through a
     command-local `-c safe.directory=...` with forward slashes, never global
     configuration. It succeeds in the Codex reviewer environment that
     reproduced the original failure.
  2. Cleanup now requires a strict resolved child, refuses the temp root,
     propagates removal failures into a reported cleanup result, always runs
     after verification, and participates in the overall exit decision.
  3. ROADMAP now marks Phase 1 complete and removes the stale outstanding-
     exit-gate claim while preserving the correct three-slice Phase-2 status.
- Independent verification used the new canonical command itself:
  `python scripts/verify.py --level routine --focus tests/test_verify.py`.
  All **10 steps passed**: Ruff format/check, mypy, repository checker, Git
  diff check, database URL safety, real test-database reachability, focused
  pytest **73 passed**, full suite **1249 passed**, and temporary-directory
  cleanup. The `.verify-tmp` root was independently confirmed empty afterward;
  working tree clean.
- Findings: none.
- **Verdict: approved.** The Workflow-v3 routine-verifier foundation and its
  correction pass are accepted. STOP — do not merge this branch into `main`,
  add schema/high-risk levels or CI/markers/status/handoff automation, or
  resume Phase-2 product work until the user explicitly authorizes the next
  action.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `0c9787b` (no findings). Per user authorization,
`tooling/workflow-v3-routine-verifier` was merged into `main` with a normal merge
commit (`257b6a5`; `--no-ff`, no squash/rebase/force-push) and pushed.
`main`/`origin/main` are both now at `257b6a5`. Verified: feature branch was clean
and pushed at `0c9787b` and `main`/`origin/main` were still at `adb6e62`
immediately before the merge; `main` has zero content diff against the feature
branch (`git diff main tooling/workflow-v3-routine-verifier --stat` empty);
migration `0017` remains the sole Alembic head; the canonical
`python scripts/verify.py --level routine` command itself was run against merged
`main` and reported **all 9 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
`git diff --check`, database URL safety, real test-database reachability, full
suite **1249 passed**, temporary-directory cleanup) in `117.52s`; `.verify-tmp`
confirmed to contain no run directory afterward; development database reconfirmed
at `0006`; working tree clean.

**Rollback boundary:** reverting `257b6a5` (a single merge commit) restores `main`
to `adb6e62` exactly — no schema/migration exists in this slice to downgrade, and
no data migration accompanies it. This merges the Workflow v3 tooling program's
first slice only (the routine-verifier foundation: `scripts/verify.py --level
routine`, `scripts/db_safety.py`, the fail-closed temporary-directory cleanup
reported as its own step, the reviewer-safe `git diff --check` invocation, the
Phase-1-complete/three-slice-Phase-2 ROADMAP correction, and Workflow v3's durable
process rules in `docs/LLM_WORKFLOW.md`) — it does **not** add CI, pytest markers,
`--level schema`/`--level high-risk`, a canonical-status generator, handoff-
structure automation, process/performance metrics, or any Phase 2 product change,
all of which remain not started and are not authorized by this merge.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Authorized slice: bounded
  read-only Greenhouse live ATS canary (Phase 4 prework) — Class H (external
  network access, per `LLM_WORKFLOW.md`'s risk table). Approved with 15
  binding clarifications, presented and approved in conversation (no
  separate proposal document — this entry is the durable record). Base
  `main`@`de2b15a` -> branch `phase-4/greenhouse-canary`.
- Outcome, per the binding clarifications:
  1. "No database writes" (not "no writes anywhere") — the script never
     imports `app.db.session` or opens a connection; repository writes are
     limited to the script, offline tests, one sanitized fixture, and this
     handoff.
  2. The unsanitized response body lives only in a local variable inside
     `fetch_greenhouse_jobs_raw`/`validate_and_parse_response` — every
     `print()` and every raised message uses only `FetchMetadata` (status,
     content-type, byte count, elapsed time, board token) or
     `type(exc).__name__`, never the body.
  3. The committed fixture (`greenhouse_live_canary.json`) is built via
     `FIXTURE_ALLOWED_JOB_FIELDS`, an explicit allowlist — `content=true` is
     never sent, so no HTML description exists to redact in the first
     place. The fixture is labeled `"_fixture_kind": "sanitized_derived_sample"`
     with an explicit "NOT a byte- or structure-preserved raw payload" note.
  4. `DiscoveredJob.provider="ats_scrapers"`/`source="greenhouse"` — the
     project's established identity labels — used unconditionally even
     though this canary calls Greenhouse directly, never through
     `ats-scrapers`.
  5. `GREENHOUSE_API_ORIGIN` is a fixed module constant; `validate_board_token`
     enforces a conservative ASCII slug (`^[A-Za-z0-9_-]{1,100}$`) before any
     URL construction. `--company` is a required, explicit CLI argument —
     `map_job_to_discovered_job` never reads the payload's own `company_name`
     field, proven against the real fixture (which genuinely contains
     `company_name="GitLab"`) by asserting a deliberately different supplied
     name wins.
  6. Exactly one `httpx` GET per invocation, `follow_redirects=False`, no
     retries, no pagination, no second request. `MAX_RESPONSE_BYTES=5_000_000`
     and `REQUEST_TIMEOUT_SECONDS=10.0` are self-imposed caps. Fails closed on
     non-2xx, oversized body, missing/wrong content-type, invalid JSON, and a
     missing/null/non-list/empty `jobs` field.
  7. Every `CanaryFetchError` message interpolates only `FetchMetadata` or an
     exception type name — never `response.body`.
  8. `select_representative_job` filters to jobs with a usable `id`, sorts by
     `str(id)` ascending, returns the first — proven order-independent by
     feeding the same job list forward, reversed, and arbitrarily shuffled
     and asserting identical selection.
  9. `discovered_at` is captured once via `datetime.now(UTC)` in `run_canary`,
     before the fetch, and threaded through explicitly. `posted_at` maps only
     from `first_published` (a field whose name is itself an explicit
     publish-time claim); `updated_at` is never read for this purpose at
     all, proven even when `first_published` is deleted from a copy of the
     real job dict while `updated_at` remains present.
  10. `source_url`/`canonical_url` both come from `absolute_url`; `apply_url`
      stays `None` unconditionally — no code path ever copies `absolute_url`
      into it (the public Job Board API exposes no distinct apply link).
  11. `test_canary_greenhouse_mapping.py` never calls `fetch_greenhouse_jobs_raw`
      or `run_canary`/`main` — confirmed by grep, not just by docstring claim.
      `scripts/verify.py` contains zero references to `canary_greenhouse`
      anywhere, confirmed by grep and by a genuine external
      `python scripts/verify.py --level routine --focus
      tests/test_canary_greenhouse_mapping.py` run (below) completing with no
      network step at all.
  12. All eight required cases are covered (see Commands below for the exact
      test count) plus additional offline coverage of `validate_and_parse_response`'s
      six fail-closed conditions, `validate_board_token`, and the fixture
      allowlist itself.
  13. The module docstring's Greenhouse-terms caveat restates
      `docs/SOURCE_CONNECTORS.md`'s existing, unresolved caveat verbatim in
      substance — no new legal or rate-limit claim is made; the self-imposed
      timeout/byte-cap are explicitly attributed to this script's own
      caution, not to any Greenhouse-published limit.
  14. Documented below (this entry) rather than copying raw response content
      into it.
  15. No `DiscoveryProvider`, no pipeline integration, no `QueryPlanner`/
      `ProviderRegistry`, no database writes, no scheduling, no Phase 3
      normalization anywhere in this diff — confirmed by grep across the new
      files for each of those names.
- Live invocation record (the one authorized request):
  - Board token: `gitlab`; company: `GitLab` (supplied explicitly).
  - Request: `GET https://boards-api.greenhouse.io/v1/boards/gitlab/jobs` —
    documented at <https://developers.greenhouse.io/job-board.html>, accessed
    2026-08-30.
  - Result: `status=200 content_type=application/json byte_count=154979
    elapsed_seconds=0.469`; `jobs_count=220`.
  - Selected job (deterministic, minimum stringified `id`):
    `source_job_id="8396674002"`.
- Observed field mapping / findings (updates the proposal's own "to confirm"
  table with real evidence):
  - `company_name` **is** present in the real payload ("GitLab") — the
    proposal's assumption that company would need external supply either
    way is confirmed, and per binding clarification 5 it is deliberately
    ignored regardless of availability.
  - `requisition_id` **is** present and genuinely distinct from `id`
    ("5899" vs `8396674002`) — resolves the proposal's "to confirm" item;
    mapped to `requisition_id_raw`.
  - `first_published` **is** present and distinct from `updated_at`
    (`2026-03-06T14:25:31-05:00` vs `2026-08-29T16:08:37-04:00` for the
    selected job) — mapped to `posted_at`; `updated_at` never used.
  - `apply_url`: no distinct field anywhere in the payload — stays `None`.
  - No `content`/description field appears anywhere in the default (no
    `content=true`) response — the redaction question is sidestepped by
    construction, not by post-hoc filtering.
  - Pagination: the single response's top level is only `{"jobs": [...],
    "meta": {...}}` — no cursor/page fields observed; all 220 jobs returned
    in one response, consistent with the proposal's "to confirm" note.
  - Minor upstream data-quality observation: the selected job's `title` has
    trailing whitespace ("Manager, Solutions Architects - San Francisco ")
    in the real API response — not a mapping defect, left as-is (the
    project's own convention is to preserve raw values; normalization is
    Phase 3's concern, out of scope here).
- Blockers to routing a real payload through the existing pipeline
  (test-database ingestion) — **narrower than "Phase 4"**: `pipeline.run()`
  already accepts any object satisfying the three-method `DiscoveryProvider`
  Protocol with a directly-constructed `SourceQuery`, exactly as every
  `FixtureProvider`-based test already does. `QueryPlanner`/`ProviderRegistry`
  orchestrate *multiple* providers/sources — not required for one hardcoded
  provider. Phase 3 normalizers are not on the ingestion path at all — Phase
  2 persists raw + resolves identity only. The only missing piece is a
  **minimal `DiscoveryProvider` adapter** wrapping this canary's own
  fetch/select/map functions — deliberately not built in this slice.
- Files changed: `backend/scripts/canary_greenhouse.py` (new);
  `backend/tests/fixtures/discovery/greenhouse_live_canary.json` (new,
  sanitized derived sample, produced by the one live invocation above);
  `backend/tests/test_canary_greenhouse_mapping.py` (new, 45 tests); this
  handoff. No product code changed; no `app/` changes; no migration; no CI.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 78 source files.
  - `python -m pytest tests/test_canary_greenhouse_mapping.py -q` ->
    **45 passed** — offline only, confirmed via grep that no test calls the
    network-touching function.
  - Full suite with a workspace-local `--basetemp` -> **1294 passed** (was
    1249).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean.
  - **Genuine external `python scripts/verify.py --level routine --focus
    tests/test_canary_greenhouse_mapping.py`** -> all **10 steps PASS**
    (Ruff format/check, mypy, `check_repo.py`, `git diff --check`, database
    URL safety, real test-database reachability, focused pytest **45
    passed**, full suite **1294 passed**, temporary-directory cleanup) in
    `113.56s`; confirms `scripts/verify.py` never touches Greenhouse.
  - `.verify-tmp/` confirmed to contain no run directory afterward.
  - Development database untouched throughout — this script never opens a
    connection to it.
- Adversarial self-review: dispatched a fresh subagent (no prior context on
  this diff) to independently check all 15 binding requirements plus general
  correctness/privacy against the actual repository, including reading the
  committed fixture's real values (not just field names) for anything
  sensitive. It found **zero High/Medium findings** against the 15 binding
  requirements — all satisfied with direct file/line citations and passing
  tests. It found **one Low-Medium finding**: this module's docstring cited
  "the approved proposal in `docs/LLM_HANDOFF.md`", but that file's
  two-iteration rotation rule means no such document persists there — the
  proposal was presented and approved in conversation, never committed
  separately. Fixed: the docstring now correctly points to this `Work done`
  entry itself as the durable approval record, and reruns of ruff/mypy/the
  focused test file all stayed clean afterward. No other issues found.
- Deviations/known limitations: the follow-up minimal `DiscoveryProvider`
  adapter, pipeline integration, `QueryPlanner`/`ProviderRegistry`, database
  writes, scheduling, and Phase 3 normalization all remain explicitly out of
  scope and unimplemented, per binding clarification 15. `main` untouched
  throughout.
- STOP — awaiting Codex review. Do not implement the follow-up adapter,
  pipeline integration, QueryPlanner/ProviderRegistry, scheduling, Phase 3
  normalization, or any database writes, or merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Diff reviewed:
  `de2b15a..bbf3f64` on `phase-4/greenhouse-canary`.
- Independent verification performed: inspected all four changed files and the live
  canary's actual HTTP/mapping/output boundaries; confirmed the committed fixture is
  allowlisted and contains no `content`/description HTML; confirmed the default test
  suite and routine verifier contain no live-canary invocation; ran the genuine
  external `scripts/verify.py --level routine --focus
  tests/test_canary_greenhouse_mapping.py` from `backend/` — all 10 steps PASS,
  including Ruff, mypy, repository/diff checks, disposable-test-database safety and
  reachability, **45 focused tests**, **1294 full-suite tests**, and cleanup. No live
  Greenhouse request was repeated during review; development data was not touched.
- Findings, by severity:
  1. **Medium — the response-size limit does not bound the download.**
     `backend/scripts/canary_greenhouse.py:215-225` uses `client.get()` and then reads
     `response.content`; httpx has therefore already buffered the complete response
     before `validate_and_parse_response()` checks `MAX_RESPONSE_BYTES`. The script
     rejects an oversized payload only after consuming it, so the advertised memory/
     response-size safety boundary is ineffective against an unexpectedly large
     upstream response. Required invariant: stop consuming the response as soon as
     the cumulative streamed byte count exceeds the cap, while still making exactly
     one GET and never logging/persisting the body. A streaming implementation is the
     recommended mechanism, not itself the invariant. Add an offline regression that
     proves bytes beyond the cap are not consumed, rather than only passing an already
     oversized in-memory `bytes` value to the pure validator.
  2. **Medium — malformed external job entries are not actually rejected at the
     selection/mapping boundary.** `select_representative_job()` at line 235 treats
     every non-`None` `id` as usable (including booleans, containers, blank strings,
     or otherwise non-Greenhouse-shaped identifiers), while lines 280-301 accept any
     non-empty string as `absolute_url` and silently turn a malformed or timezone-naive
     present `first_published` value into either `None` or a naive datetime. This is
     weaker than the slice's fail-closed malformed-schema claim and could hand the next
     live-to-pipeline slice an unstable identity, unsafe/non-absolute URL, or invalid
     business timestamp. Required invariant: the selected entry must satisfy the
     documented Greenhouse identity/mapping shape before it becomes a `DiscoveredJob`;
     absent optional values may remain `None`, but present malformed values must fail
     cleanly. Validate a real usable job ID, an absolute HTTPS URL, and an aware
     `first_published` timestamp when present; select deterministically among entries
     that meet the required mapping shape; surface a sanitized `CanaryFetchError`
     without a raw traceback/body. Add offline accepted/rejected boundary tests. Do not
     make another live request or change the existing fixture unless the stricter
     validator shows that fixture is invalid.
  3. **Low — `--fixture-out` can escape the one authorized repository location.**
     Lines 400-401 create and overwrite any caller-supplied filesystem path, despite
     the approved invariant limiting repository output to the single sanitized fixture.
     Constrain output to the intended fixture location (removing the option is the
     simplest acceptable mechanism), and write it atomically so a failed write cannot
     leave a truncated committed fixture. Add offline tests for path refusal/atomic
     replacement as applicable to the chosen mechanism.
- Missing/inconclusive checks: the review intentionally did not repeat the authorized
  external request; its recorded status/size/timing cannot be independently reproduced
  without performing a second live call. The committed sample and offline behavior were
  independently verified. Greenhouse terms remain explicitly unreviewed, as disclosed.
- Verdict: **Approved with binding clarifications** — the canary design and the real
  fetch/mapping result are accepted, but Findings 1-3 require one bounded correction
  pass before merge. No proposal rewrite is required.
- Exact bounded correction: modify only the canary script, its offline test file, and
  this handoff entry as needed to close Findings 1-3; preserve the existing sanitized
  fixture unless stricter validation demonstrates it is invalid. Run no additional live
  request. Run the routine verifier with the focused canary tests, record actual counts,
  commit/push the correction branch, and stop for re-review.
- STOP — do not merge `main`, implement the provider adapter or pipeline integration,
  add QueryPlanner/ProviderRegistry, resume Phase 2/3 product work, or perform another
  live Greenhouse request without separate user authorization.
