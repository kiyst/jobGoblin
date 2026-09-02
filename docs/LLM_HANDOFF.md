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

- Date/agent: 2026-09-01, Claude Code (Sonnet 5). Class H implementation of the
  approved multi-source partial-success handling slice on
  `phase-2/partial-success-handling`, based on clean `main@02ef086`.
- Outcome: `ingestion/pipeline.py::run()` no longer aborts the entire run when a
  `DiscoveryResult` reports a source-level failure/partial result/error
  (`possibly_incomplete=True`). A healthy source's jobs persist normally while a
  sibling source's own failure is recorded independently. No schema/migration
  change — every column this slice populates (`collection_run_provider_attempts.
  status='partial'`/`error_category`/`error_message`/`retry_count`/`rate_limited`/
  `incomplete_results`; `collection_runs.failures`) already existed from Phase 1.
- Binding decisions applied exactly as authorized:
  1. Added result-consistency validation `DiscoveryResult`'s own pydantic validator
     cannot express, run before any raw row is written, as three new whole-run
     `UnsupportedDiscoveryResultError` guards (ordered so each is independently
     reachable, not shadowed by another): `completed=False` with any actual
     `DiscoveredJob` attributed to it; `completed=False` with
     `incomplete_results=True`; and (a source having *any* completed value)
     `jobs_found` disagreeing with the actual attributed count. Three dedicated
     tests each assert zero raw/Job/JobOccurrence rows and `status='failed'`
     telemetry.
  2. Attempt-row `status` precedence implemented exactly as specified: `failed` if
     `not completed`; else `partial` if `incomplete_results`; else `completed`. A
     `ProviderError` alone never downgrades a `completed` source's status, though it
     still makes the parent run `completed_with_errors` and still populates that
     row's `error_category`/`error_message`.
  3. Multiple `ProviderError`s per source are valid: every one becomes its own
     `collection_runs.failures` entry (never discarded), while the attempt row's own
     `error_category`/`error_message` reflect only the chronologically latest one
     (ties broken by later `DiscoveryResult.errors` position). Verified by hand and
     by a dedicated test covering both the strict-timestamp and the tie-break case
     across two sources in one run.
  4. `failures` entries use the exact specified shape (`{provider, source, error:
     {category, retryable, detail, occurred_at}}`, `category` as the plain string
     value, `occurred_at` as `.isoformat()`), one per `ProviderError`, in
     `result.errors` order — asserted verbatim in the healthy/broken-source test.
     `detail`/`error_message`/`failures` content is never logged — confirmed by
     direct inspection of every `logger.*` call in the file (IDs/counts/status/
     exception-type only) plus an existing-pattern sanitized-logging test.
  5. Every applicable attempt field is now populated, including `retry_count`/
     `rate_limited` (previously always left at their `0`/`False` defaults
     regardless of what `SourceRunStats` reported) — a dedicated test proves both
     reach the row exactly.
  6. Docs: `docs/DATA_MODEL.md` gained a new Rev 23 entry pinning down the exact
     `failures[*].error` shape and the latest-error attempt-summary rule (correcting
     stale wording that called `failures` a mere "denormalized convenience copy" of
     the attempt row, backwards for the multi-error case); `docs/ARCHITECTURE.md` §9
     gained a clarifying paragraph on the same two rules; `docs/ROADMAP.md` describes
     the new capability without asserting a merge state, and Phase 2 is **not**
     declared complete anywhere (Tier 4/`QueryPlanner`/`ProviderRegistry` remain
     listed as deferred). No new ADR, per instruction.
- Files changed: `backend/app/ingestion/pipeline.py`; `backend/tests/
  test_ingestion_pipeline.py` (narrowed the existing malformed-result parametrized
  test to its two still-genuinely-invalid cases; added 9 new tests — 3 for the new
  consistency guards, 6 for graceful-handling behavior); `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/ROADMAP.md`; this handoff entry. No schema,
  migration, provider, or network file touched. `ingestion/identity.py`/
  `ingestion/persistence.py` untouched — this slice is entirely about source-level
  telemetry, orthogonal to per-job identity resolution.
- Verification: genuine external `python scripts/verify.py --level routine --focus
  tests/test_ingestion_pipeline.py` — all **10 steps PASS**: Ruff format/check,
  mypy (82 source files), `check_repo.py`, `git diff --check`, database-URL
  safety, real test-database reachability, **55 focused tests**, **1404
  full-suite tests** (was 1398; net +6 = 9 added − 3 removed), temp-directory
  cleanup, in ~120-145s across repeated runs. `alembic heads` confirms `0017`
  remains the sole head; `git diff --stat -- migrations/` is empty. `alembic
  current` against the configured dev database (`jobgoblin`) is unchanged at
  `0006` before and after this pass — no `alembic upgrade` was run against it;
  all schema/database work ran only against the disposable `jobgoblin_test`
  database.
- Adversarial self-review: dispatched a fresh-context subagent against the actual
  diff (not this summary). It confirmed: all three new consistency checks are
  independently reachable/testable (traced against `DiscoveryResult`'s own
  pydantic validator to show none is accidentally shadowed); status precedence,
  latest-error selection (including the tie-break), `failures` shape/completeness,
  `error_message` CHECK-safety (`.strip() or None` applied before a Core-style
  `update()`, which bypasses the model's own `@validates`), and log-content
  sanitization are all correct; the two remaining malformed-result parametrized
  cases are clean post-rework; the untouched exception path is still correctly
  reachable and tested. It found one real defect (High): four new tests captured
  cleanup IDs (`job_ids.append(...)`/`raw_ingestion_ids.extend(...)`) *after*
  assertions that could fail — the same defect class caught and fixed in the
  immediately preceding slice, reintroduced here. One of the four additionally had
  the occurrence lookup itself inside `finally`, where a `NoResultFound` (the exact
  regression the test exists to catch) would abort before reaching `_cleanup()`
  entirely. Fixed in all four by moving every ID capture to immediately follow the
  mutating call, before any assertion, and moving the risky lookup out of `finally`
  into the `try` block — reverified by rerunning the full suite (still 1404
  passed). One Low finding (a `failures == []` assertion that would pass even
  under a naive always-empty implementation, given that specific test's own
  `errors=[]` input) was reviewed and left as-is: it is paired with tests that do
  exercise non-empty `failures`, and strengthening it further was judged not worth
  the added complexity.
- Deviations/known limitations: none new beyond the prior iteration's already-
  recorded `alembic check` substitution (same pre-existing stale dev database,
  unrelated to this slice).
- STOP — awaiting Codex review. Do not merge, start Tier 4, `QueryPlanner`,
  `ProviderRegistry`, add schema changes, contact live providers, or expand this
  slice. Per instruction, Phase 2's exit gate is not declared satisfied here — a
  separate audit is required after merge, since Tier 4 remains deferred and the
  documented fixture requirements must be reconciled explicitly.

### Work review

- Date/agent: 2026-09-01, Codex. Implementation diff reviewed:
  `02ef086..a6196db` on `phase-2/partial-success-handling`.
- Independent verification: inspected the pipeline control flow, all changed tests,
  and the architecture/data-model/roadmap updates. Ran the genuine external canonical
  verifier focused on `tests/test_ingestion_pipeline.py`: all **10 steps PASS**, including
  Ruff format/check, mypy, repository and whitespace checks, disposable-database
  safety/reachability, **55 focused tests**, **1404 full-suite tests**, and temporary-
  directory cleanup.
- Confirmed behavior: malformed result consistency is rejected before raw writes;
  healthy work survives a sibling source failure; failed/partial/completed attempt
  precedence is exact; completed sources can retain nonfatal errors; every provider
  error survives in ordered run-level evidence while the latest per source supplies the
  attempt summary; retry/rate-limit fields persist; job-level issues OR correctly with
  source issues; unexpected exceptions still mark the run and all attempts failed.
- **Medium — Core-path error-message normalization exceeds the database/ORM contract.**
  `backend/app/ingestion/pipeline.py:346` uses unrestricted
  `selected_error.detail.strip()`, which removes Python's full Unicode whitespace set.
  The authoritative model and PostgreSQL checks intentionally trim only the established
  four-character set (`" \\t\\n\\r"`; `collection_run_provider_attempt.py:41,255-263`).
  Therefore an adapter detail such as `"\\u00a0detail\\u00a0"` is silently changed to
  `"detail"` by this Core-update path, while assigning the same value through the ORM
  preserves the non-breaking spaces. A detail containing only non-covered whitespace is
  similarly collapsed to SQL NULL only through this path. This repeats the exact class
  of application/database normalization divergence the project guards against.
- Exact requested correction: normalize the Core-update value with the same explicit
  four-character set as the model (prefer one shared/import-safe helper or constant over
  independently drifting literals). Add a regression that persists and reloads a
  `ProviderError.detail` wrapped in non-covered Unicode whitespace and proves it is
  preserved, while covered outer space/tab/LF/CR are still trimmed and a covered-only
  value becomes NULL. The run-level `failures[*].error.detail` remains the exact
  ProviderError value specified by this slice and must not be normalized incidentally.
  No schema, migration, status, aggregation, or logging change is requested.
- Verdict: **Approved with binding clarification** — one bounded executable correction
  is required before merge; the slice's design and all other behavior are accepted.
- STOP — do not merge, begin another Phase 2 slice, or make unrelated changes. The user
  must authorize this correction; then Codex re-reviews only the correction and affected
  normalization invariant.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-01, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/partial-success-handling` for the single finding from review commit
  `d5acc3a`. Base `d5acc3a`. No product code beyond the exact bounded scope
  requested: schema, migrations, statuses, error-selection logic, aggregation,
  `failures` shape, and logging are all untouched.
- Outcome, addressing the finding exactly: the Core-update `error_message`
  normalization now trims the identical four-character set
  (`COVERED_WHITESPACE = " \t\n\r"`) as `CollectionRunProviderAttempt`'s own ORM
  `@validates` and its database `CHECK`s, instead of Python's broader default
  `str.strip()` whitespace set.
  1. Promoted `collection_run_provider_attempt.py`'s existing private
     `_COVERED_WHITESPACE` to a public `COVERED_WHITESPACE` (both `@validates`
     methods updated to the new name; confirmed zero remaining references to the
     old private name anywhere in that file via direct grep).
  2. `pipeline.py` now imports `COVERED_WHITESPACE` from that same module and
     calls `selected_error.detail.strip(COVERED_WHITESPACE) or None` — one
     shared constant, not a second, independently-drifting literal.
  3. `CollectionRun.failures[*].error.detail` construction is untouched — it
     still reads `error.detail` directly (never `error_message`), confirmed by
     direct inspection and by the new test's own assertion that `failures`
     always reflects the exact original `ProviderError.detail`.
- New regression test (`test_pipeline_normalizes_error_message_with_the_shared_
  covered_whitespace_set`) proves, in one run across four sources: covered outer
  whitespace (space/tab/LF/CR) is trimmed from `error_message`; genuine non-covered
  Unicode whitespace (real U+00A0 non-breaking-space characters — confirmed via a
  direct byte-level `repr()` check during adversarial review, not merely visual
  inspection, since a terminal/editor cannot visually distinguish U+00A0 from an
  ASCII space) survives byte-for-byte; a covered-whitespace-only detail collapses
  `error_message` to `NULL`; a non-covered-whitespace-only detail stays non-`NULL`;
  and `CollectionRun.failures[*].error.detail` is the exact untouched original
  value in all four cases simultaneously.
- Files changed: `backend/app/db/models/collection_run_provider_attempt.py`
  (constant rename only — no column, `CHECK`, or migration change);
  `backend/app/ingestion/pipeline.py` (import + one normalization line);
  `backend/tests/test_ingestion_pipeline.py` (one new test); this handoff entry.
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_ingestion_pipeline.py` — all **10 steps PASS**: Ruff
  format/check, mypy (82 source files), `check_repo.py`, `git diff --check`,
  database-URL safety, real test-database reachability, **56 focused tests**
  (was 55; +1), **1405 full-suite tests** (was 1404; +1), temp-directory
  cleanup. `alembic heads` confirms `0017` remains the sole head; `git diff
  --stat -- backend/migrations/` is empty — no schema/migration touched, as
  required.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff. It confirmed the rename left no dangling `_COVERED_WHITESPACE`
  reference; `pipeline.py` imports and uses the shared constant rather than a
  duplicated literal; the new test's "non-covered whitespace" literals are
  genuinely non-ASCII U+00A0 (verified at the byte level, not just visually —
  called out explicitly as exactly the trap this kind of test can fall into);
  all five required behaviors are proven in one test; no other module imports
  `_COVERED_WHITESPACE` from this specific file (the same private-constant name
  is reused independently, unrelated, in several other model files, none of
  which reference this one); and the diff's scope is exactly the three files
  above, touching nothing else. No findings.
- Deviations/known limitations: none new.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 2 slice, or
  make any unrelated change.
