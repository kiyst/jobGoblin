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

---

## Iteration 2

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

_Pending._
