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

- Date/agent: 2026-09-03, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/provider-registry` for the two bounded findings from Iteration 1's
  `Work review` above (uncommitted at review time; committed together with
  this correction, preserved byte-for-byte, not rewritten). Base: `4ab3a0d`
  plus the uncommitted review. No product code beyond the two corrections
  requested: orchestration, pipeline ownership, `enabled_providers`
  semantics, `CollectionRun` behavior, production composition, Tier 4, and
  migrations all remain untouched.
- Outcome, addressing each finding exactly:
  1. **Malformed `capabilities()` return, fully sanitized.** `registry.py`'s
     constructor now checks `isinstance(capabilities, ProviderCapabilities)`
     immediately after the (still try/except-guarded) `capabilities()` call,
     before `.provider` is ever read or `.model_copy()` is ever called. A
     duck-shaped object with a coincidentally-matching `.provider` attribute
     (e.g. `SimpleNamespace(provider="alpha")`, which previously reached
     `.model_copy(...)` and raised a raw `AttributeError` there) now fails
     closed with the same fixed `ProviderRegistrationError` as every other
     malformed-return case, before either attribute is touched.
  2. **Provider-name access hardened, at both construction and resolution.**
     Construction: `provider.name` is now read inside its own `try/except
     Exception` (a missing attribute or a raising `.name` property converts
     to a new fixed `_ERROR_PROVIDER_NAME_UNAVAILABLE`), followed by an
     explicit `isinstance(name, str)` check (`_ERROR_PROVIDER_NAME_NOT_STRING`)
     before the value is ever passed to `is_canonical_slug()` — closing the
     raw `TypeError` `re.fullmatch()` would otherwise raise on a non-`str`
     (e.g. `None`). Resolution: `get()`'s `entry.provider.name` read is now
     inside the same kind of `try/except Exception`, folded into the
     existing name-drift check (`_ERROR_NAME_DRIFT`, message text updated to
     cover "unavailable or no longer matches") — a `.name` property that
     starts raising after successful registration fails closed exactly like
     an outright name mismatch. `except Exception` (never a bare `except:`
     or `except BaseException`) is used at every one of these new guards, so
     `asyncio.CancelledError`/`KeyboardInterrupt`/`SystemExit` are never
     caught — confirmed by construction (`CancelledError` is a
     `BaseException` subclass since Python 3.8, not an `Exception`
     subclass), not merely asserted.
- Files changed: `backend/app/providers/registry.py` (both corrections;
  updated `ProviderRegistrationError` docstring's raise-site list; updated
  `get()`'s docstring), `backend/tests/test_provider_registry.py` (6 new
  tests, below), `docs/ARCHITECTURE.md` §6.4 (construction-time-validation
  and name-drift-detection bullets rewritten to describe the corrected full
  boundary — guarded `.name` access, non-`str` rejection, and the
  duck-shaped-capabilities rejection — matching Codex's finding that the
  prior wording no longer matched reality), this handoff entry (Iteration 1
  preserved verbatim per the rotation rule, including its own now-superseded
  Work done claims — corrected going forward starting with this entry and
  the current §6.4 text, not retroactively rewritten as history). No
  `ingestion/`, `db/models/`, migration, or `enabled_providers`/
  `CollectionRun` file touched.
- New tests (6, all isolated to exactly one guard each): a malformed
  duck-shaped `capabilities()` return whose `.provider` matches the
  registered name; `None` and a non-string (`123`) provider name at
  construction; a provider missing `.name` entirely; a `.name` property that
  raises at construction; a `.name` property that starts raising only after
  successful registration, caught on resolution.
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_provider_registry.py` — all **10 steps PASS**: Ruff
  format/check, mypy (49 source files, including the new protocol-violating
  test doubles under explicit, narrow `# type: ignore[list-item]` — the
  violation is the deliberate point of each test), `check_repo.py`, `git diff
  --check`, database-URL safety, real test-database reachability, **21
  focused tests** (was 15; +6), **1467 full-suite tests** (was 1461; +6),
  temp-directory cleanup, ~107s. `alembic heads` confirms `0017` remains the
  sole head; `git diff --stat -- backend/migrations/` is empty. Dev database
  (`jobgoblin`) confirmed unchanged at the pre-existing `0006` before and
  after, via a direct `alembic current` read.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff (abbreviated to the questions that actually apply — a pure
  in-memory correction, no schema/concurrency surface). It independently ran
  the tests (62/62: 21 registry + 41 query_planner) and mypy (clean, with
  `warn_unused_ignores = true` proving every new `# type: ignore[...]` is
  necessary and correctly coded, not a blanket suppression); empirically
  confirmed `is_canonical_slug(None)`/`is_canonical_slug(123)` raise a raw
  `TypeError` absent the `isinstance(name, str)` guard, proving that guard is
  load-bearing rather than decorative; empirically confirmed
  `asyncio.CancelledError`'s MRO excludes `Exception` on this project's
  Python 3.12, proving (not assuming) `except Exception` cannot swallow it;
  and, for each of the 6 new tests, mentally reverted its specific target
  guard and confirmed the test would then fail on a *different*, unsanitized
  exception rather than silently pass for the wrong reason — including
  tracing that reverting the `isinstance(capabilities, ProviderCapabilities)`
  check causes the duck-shaped-object test to instead crash unsanitized at
  `.model_copy(...)`, exactly the original defect. **One Low/informational
  residual, deliberately not acted on**: the `.provider` read and
  `.model_copy()` calls occurring *after* the `isinstance` check are still
  unguarded — a hypothetical malicious `ProviderCapabilities` *subclass*
  overriding `.provider` as a raising property could still escape unsanitized.
  Out of scope of the two specific corrections Codex requested (which named
  the non-instance/duck-typing case, now fixed) and `ProviderCapabilities` is
  a project-owned Pydantic model, not attacker-controlled input — left
  unaddressed per the "exactly the two bounded fail-closed corrections"
  instruction, same disposition as the prior slice's declined out-of-scope
  suggestion.
- Deviations/known limitations: none beyond the already-recorded, pre-existing
  `alembic check` substitution.
- STOP — awaiting Codex re-review. Do not merge or begin orchestration,
  pipeline ownership changes, `enabled_providers` semantics, ProviderRegistry
  production composition, provider contact, Tier 4, Phase 3, or migrations.

### Work review

- Date/agent: 2026-09-03, Codex. Correction diff reviewed:
  `4ab3a0d..0784b07` on `phase-2/provider-registry`.
- Independent verification: inspected every changed executable, test, and documentation
  path; ran the six focused malformed-capabilities/name-access regressions directly
  (**6 passed**); then ran the genuine external canonical verifier focused on
  `tests/test_provider_registry.py`: all **10 steps PASS**, including Ruff, mypy,
  repository/diff checks, disposable-database safety/reachability, **21 focused tests**,
  **1467 full-suite tests**, and temporary-directory cleanup.
- Prior-finding disposition: **closed**. Construction now establishes an actual
  `ProviderCapabilities` instance before accessing/copying it, so a duck-shaped matching
  object receives the fixed registration error rather than leaking `AttributeError`.
  Construction-time provider-name access now sanitizes missing/raising attributes and
  rejects non-string values before slug validation; resolution-time access likewise
  converts a newly-raising property into the fixed drift/registration error. The ordinary
  `Exception` boundary correctly leaves cancellation and process-control exceptions
  uncaught.
- Documentation/scope check: ARCHITECTURE §6.4 matches the corrected runtime boundary;
  no QueryPlanner behavior, orchestration, pipeline ownership, enabled-provider
  semantics, database model, migration, or provider contact entered the correction.
  The disclosed hypothetical malicious `ProviderCapabilities` subclass is outside the
  project-owned Pydantic contract and does not warrant broadening this bounded slice.
  No further findings.
- Verdict: **Approved**. The ProviderRegistry slice and bounded correction pass are
  accepted; no additional correction is required.
- Exact requested corrections: none.
- STOP — do not merge to `main` or begin multi-provider orchestration, pipeline changes,
  `enabled_providers` semantics, production composition, provider contact, Tier 4,
  Phase 3, or any other slice until the user explicitly authorizes the next action.

### Merge record

- Date: 2026-09-04. User authorized merging `phase-2/provider-registry` into
  `main` following Codex's final Approved re-review (no findings) above.
- Pre-merge state: `main` and `origin/main` both at `342534f`; feature branch
  pushed and clean at `eada592` (merge-base `342534f` — no divergence).
- Merge: `git merge --no-ff phase-2/provider-registry` on `main` — merge
  commit `c67f1f5`. Post-merge diff against the feature branch's tip is
  empty (zero content difference); `check_repo.py` and `git diff --check`
  both clean.
- Post-merge verification: genuine external `verify.py --level routine
  --focus tests/test_provider_registry.py` — all **10 steps PASS** (Ruff
  format/check, mypy, `check_repo.py`, `git diff --check`, disposable-
  database URL/reachability, **21 focused tests**, **1467 full-suite
  tests**, temp-directory cleanup). One transient reachability failure was
  observed on the first attempt (the local `jobgoblin-postgres-1` Docker
  container had exited ~15 minutes earlier, unrelated to this merge);
  restarted the container, confirmed healthy, and reran to a clean pass.
  `alembic heads` confirms `0017` remains the sole head; no migration files
  touched by the merge. Dev database (`jobgoblin`) confirmed unchanged at
  `0006` — untouched throughout.
- Pushed: `main` at `c67f1f5`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `342534f` (the
  commit immediately before this merge) — this removes `ProviderRegistry`,
  the shared `is_canonical_slug()` extraction, and their tests/docs cleanly,
  with no migration to reverse and no data written by this slice to any
  environment.
- STOP — do not begin multi-provider orchestration, pipeline ownership
  changes, `enabled_providers` semantics, production composition, provider
  contact, Tier 4, Phase 3, or migrations without separate authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-05, Claude Code (Sonnet 5). Class H implementation of
  the approved, twice-revised multi-provider orchestration proposal, on
  `phase-2/orchestration`, based on clean `main@9f4c921`. Implements exactly
  `run_saved_search()` per the final authorized design (superseding two
  prior proposal-only rounds); no live providers, parallelism, scheduler,
  API routes, Tier 4, Phase 3, migration, or `ProviderRegistry` production
  composition touched.
- Outcome:
  - **`app/ingestion/provider_execution.py`** (new) — extracted the
    discover→validate→write-raw→resolve-identity→persist→accumulate logic
    out of `pipeline.py::run()`'s inlined body, unchanged in substance.
    `ProviderExecutionState` (a typed dataclass: per-source counters,
    `failures`, `had_parse_error`, `had_conflict`, `possibly_incomplete`,
    `source_stats`, `selected_errors`) is mutated **in place** by
    `execute_provider_query()` — `source_stats`/`selected_errors`/`failures`
    are populated immediately once a valid `DiscoveryResult` is received,
    *before* the per-posting loop that could later raise, so a downstream
    persistence exception still leaves genuinely-known telemetry available
    to whichever caller's exception handler runs next. `UnsupportedDiscoveryResultError`
    and the per-posting transaction helpers (`_write_fetched_row`,
    `_mark_parse_error`) moved here too; `pipeline.py` re-exports both for
    the existing test suite's direct use.
  - **`app/ingestion/pipeline.py`** — `run()`'s internals now delegate to
    `provider_execution.py`; public signature/behavior is unchanged (zero
    regression across the entire existing pipeline/concurrency/live-proof
    suite). Two existing tests (`test_ingestion_pipeline.py`,
    `test_live_proof_greenhouse_adapter.py`) had their
    `monkeypatch.setattr(pipeline, "persist_posting", ...)` call sites
    retargeted to `provider_execution.persist_posting` — the only place the
    call now actually lives after extraction; no other change to either
    test file.
  - **`app/ingestion/orchestrator.py`** (new) — `run_saved_search(engine,
    saved_search_id, provider_registry, *, clock, observed_at) -> uuid.UUID`,
    plus `SavedSearchNotFoundError`, `InactiveSavedSearchError`,
    `MalformedEnabledProviderError`, `DuplicateEnabledProviderError`. One
    `CollectionRun` per call, `saved_search_id` always populated. One
    initialization transaction: `SELECT ... FOR SHARE`s the `SavedSearch`
    row (closing the FK-race window against a concurrent delete — protects
    only the parent/FK write, never a serializable snapshot of title/
    location child rows, read plain/unlocked in the same transaction),
    validates `is_active`/`enabled_providers` (every entry a `str` matching
    `is_canonical_slug()`, no duplicates) before any write, then creates the
    run. Sequential per-provider loop: only `UnknownProviderError` and
    `QueryPlanValidationError` are sibling-continuing planning failures,
    durably recorded the instant they occur (`failures`, `source: null` —
    reusing the existing `ProviderErrorCategory.UNKNOWN` value, never an
    invented one); `ProviderRegistrationError` (registry name drift), any
    `discover()` exception, `UnsupportedDiscoveryResultError`, and any raw-
    storage/identity/persistence/database exception are **not** caught
    per-provider — they abort the entire run, matching `pipeline.run()`'s
    existing fail-closed posture, now scoped over N providers. Attempt rows
    are created lazily, atomically with `providers_attempted`/
    `providers_enforced_locally` (`local_enforcement`'s `set[str]` values
    converted to `sorted(list)` first — deterministic JSON regardless of set
    hash order), immediately before each provider's `discover()` call — a
    provider never reached has zero attempt rows. Normal per-provider
    completion atomically increments `CollectionRun`'s rollup by that
    provider's own deltas (one SQL `col = col + :delta` expression, same
    transaction as its attempt rows). **The targeted regression fix**: on a
    whole-run abort, `CollectionRun`'s rollup is *never* derived from a
    parallel Python running total (none exists anywhere in this file) — it
    is recomputed from a fresh `SELECT SUM(...)` over every persisted
    attempt row for the run and written as an absolute value, so it is
    provably always exactly `SUM` over its own attempt rows, never double-
    counted or lost regardless of when the abort was delivered.
  - **`tests/support/configurable_provider.py`** (new) — a fully
    configurable `DiscoveryProvider` test double (distinct name, arbitrary/
    malformed `DiscoveryResult`, or an exception to raise from `discover()`);
    `FixtureProvider` stays completely untouched.
  - **`tests/test_orchestrator.py`** (new, 23 tests) — every scenario from
    the approved test matrix: two providers succeeding; explicit
    empty/`None`-skipped selections; malformed slug (including a non-string
    element) / inactive / duplicate / not-found zero-write validation;
    planning-failure and graceful-`ProviderError` sibling-continuation;
    registry-drift / unexpected-exception / malformed-result whole-run
    abort with no sibling execution; persistence exception after partial
    progress (the exact-once-counter regression, proving `CollectionRun.
    jobs_* == SUM(attempts)` post-abort); parse error and identity conflict
    each independently forcing `completed_with_errors`; deterministic
    sorted `providers_enforced_locally`; per-provider attempt timestamp
    ordering (via a `FixedClock.advance()` side effect proving no provider
    inherits an earlier one's start time); deterministic provider
    processing order (explicit preserved, `NULL` sorted) and child
    (title/location) ordering (proving `(created_at, id)`, not insertion
    order — same-transaction inserts share an identical `created_at`);
    cancellation mid-provider; a genuine two-real-transaction `SavedSearch`
    deletion-race test (`asyncio.Event`-coordinated `FOR SHARE` vs.
    concurrent `DELETE`, proving the row survives with `saved_search_id =
    NULL`); no leaked rows or permanently-running rows across every
    scenario.
  - **`docs/ARCHITECTURE.md`** — new §6.8 documenting the full design above;
    corrected every "future orchestrator (not yet implemented)" placeholder
    in §6.4/§6.6 now that it exists, without overclaiming production
    composition (still genuinely deferred). **`docs/DATA_MODEL.md`** —
    documents `failures`'s `source: null` planning-failure case, reconciled
    with the existing `{provider, source, error}` shape (Rev 24 note).
    **`docs/ROADMAP.md`** — Phase 2 status paragraph updated; removed
    `ProviderRegistry`/orchestration from "still deferred."
- Files changed: exactly the above — `backend/app/ingestion/
  provider_execution.py` (new), `backend/app/ingestion/pipeline.py`
  (extraction refactor), `backend/app/ingestion/orchestrator.py` (new),
  `backend/tests/support/__init__.py`/`configurable_provider.py` (new),
  `backend/tests/test_orchestrator.py` (new), `backend/tests/
  test_ingestion_pipeline.py`/`test_live_proof_greenhouse_adapter.py`
  (monkeypatch-target retargeting only), `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/ROADMAP.md`, this handoff entry. No `db/
  models/` or migration file touched.
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_orchestrator.py` — all **10 steps PASS**: Ruff
  format/check, mypy (51 source files), `check_repo.py`, `git diff --check`,
  database-URL safety, real test-database reachability, **23 focused
  tests**, **1490 full-suite tests** (was 1467; +23), temp-directory
  cleanup, ~119s. `alembic heads` confirms `0017` remains the sole head;
  `git diff --stat -- backend/migrations/` is empty. Dev database
  (`jobgoblin`) confirmed unchanged at the pre-existing `0006`. A direct
  disposable-database row-count check (`raw_job_ingestions`, `jobs`,
  `job_occurrences`, `collection_runs`, `collection_run_provider_attempts`,
  `users`, `saved_searches`) confirmed 0 before and 0 after the full suite —
  no leaked rows.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff, scoped to 12 specific correctness properties (one `Collection
  Run` per call; the narrowed exception boundary; the no-double-counting
  abort mechanism; lazy atomic attempt creation; `ProviderExecutionState`'s
  mutate-in-place design; `pipeline.run()`'s unchanged behavior;
  `enabled_providers` zero-write validation; the deletion-race test's actual
  concurrency soundness — including tracing what would happen if the lock
  were broken, confirming no false-positive pass is possible; per-provider
  timestamp distinctness; the earlier leaked-row defect class specifically
  re-checked and confirmed absent via independent row-count reruns;
  `local_enforcement` JSON determinism; and 3 specific docs-vs-code claims).
  It independently reran the full suite, mypy, ruff, and a live
  `is_canonical_slug(None)` repro. **One Medium finding**: `enabled_providers`
  containing a `None` element crashed with a raw, unsanitized `TypeError`
  instead of the documented `MalformedEnabledProviderError`, since
  `is_canonical_slug()` assumes `str` and `enabled_providers` is a plain
  `text[]` with no CHECK constraining its elements. Fixed: added an
  `isinstance(name, str)` guard before the slug check (mirroring
  `ProviderRegistry`'s own established pattern for the identical class of
  defect); widened `_ERROR_MALFORMED_ENABLED_PROVIDER`'s fixed message;
  added `test_non_string_enabled_provider_element_zero_writes`. Two Low
  findings (no orchestrator-level test composing a graceful `ProviderError`
  with a successful sibling; no test for a mid-`_finalize_provider_success`
  database exception) — the first was cheap and directly on point, so
  `test_graceful_provider_error_plus_successful_sibling` was added; the
  second was traced algebraically (an exception there rolls back that one
  atomic transaction entirely, leaving the abort handler's own state
  correctly bound) and left as a documented, no-code-defect-found residual,
  disproportionate to add a synthetic DB-fault-injection test for. Reran the
  full verifier after both fixes: 23 focused (was 21; +2), 1490 full-suite
  (was 1488; +2), all 10 steps still PASS, zero leaked rows reconfirmed.
- Deviations/known limitations: none beyond the already-recorded,
  pre-existing `alembic check` substitution.
- STOP — awaiting Codex review. Do not merge or begin live-provider
  contact, parallel/concurrent provider execution, the scheduler, API
  routes, Tier 4, Phase 3, `ProviderRegistry` production composition, or any
  migration.
