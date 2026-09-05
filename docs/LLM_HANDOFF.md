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

- Date/agent: 2026-09-03, Claude Code (Sonnet 5). Class H implementation of the
  approved two-slice boundary's Slice 1, `ProviderRegistry` only, on
  `phase-2/provider-registry`, based on clean `main@342534f`. Slice 2
  (multi-provider orchestration) is explicitly not started — no
  `ingestion/pipeline.py` change, no `CollectionRun`/`enabled_providers`
  behavior, no production composition of a real registry instance.
- Outcome:
  - **`app/schemas/identifiers.py`** (new) — extracts the canonical
    lowercase-ASCII-slug regex out of `query_planner.py` into a single shared
    predicate, `is_canonical_slug(value: str) -> bool`, using `.fullmatch()`
    only. The compiled pattern itself stays private/unexported specifically so
    no caller can reach for it directly and reintroduce the project's own
    prior `.match()` bug — `is_canonical_slug()` is the only entry point.
  - **`app/discovery/query_planner.py`** — now imports and calls
    `is_canonical_slug()` instead of its own private compiled regex; zero
    behavior change (all 41 existing focused tests pass unmodified).
  - **`app/providers/registry.py`** (new) — `ProviderRegistry`,
    `ProviderRegistrationError`, `UnknownProviderError`,
    `RegisteredProvider` (frozen dataclass: `.provider`, `.capabilities`).
    Construction fails closed on: an invalid canonical provider name; a
    duplicate registered name; `capabilities()` raising *or* returning a
    malformed value (e.g. `None` — its declared return type isn't
    runtime-enforced) — both converted to one fixed, categorical
    `ProviderRegistrationError` that never exposes the original
    exception's text; `capabilities().provider != provider.name`. The
    `ProviderCapabilities` snapshot is captured via `.model_copy(deep=True)`
    at registration and never re-fetched; `get(name)` returns a **fresh**
    deep copy every call (mutating one resolved copy can never affect the
    registry's own state or a different caller's copy) and re-checks the
    provider's *current* `.name` against its registered name on every
    resolution — a `DiscoveryProvider` is an arbitrary object, never assumed
    immutable, so drift is detected at resolution, not just at construction.
    `names()` returns every registered name, alphabetically sorted, as a new
    list each call. Registered names are used verbatim as dict keys — never
    normalized. No module-level singleton, no database access, no network
    access.
  - **`backend/tests/test_provider_registry.py`** (new, 15 tests) — empty
    registry; deterministic sorted `names()` independent of registration
    order; successful lookup; duplicate rejection; invalid provider slug
    including isolated trailing-LF/CRLF cases; capabilities-name mismatch;
    `capabilities()` exception sanitization; `capabilities()` returning a
    malformed value (`None`) also rejected, not a raw `AttributeError`
    (added during adversarial review, below); `capabilities()` called
    exactly once on successful registration, confirmed unchanged across two
    subsequent `get()` calls; mutating a resolved snapshot (including a
    *nested* `SourceCapabilities` field, and adding a new dict entry) cannot
    mutate the stored registry state; provider `.name` drift after
    registration detected on resolution; unknown-name errors never contain
    the requested name; a resolved capability snapshot feeds
    `QueryPlanner.plan()` directly and produces a valid `SourceQuery` —
    entirely offline, the real current-consumer compatibility proof.
  - **`docs/ARCHITECTURE.md`** §6.4 — replaces the one-paragraph
    `ProviderRegistry` mention with a precise subsection documenting the
    implemented contract above; explicitly states production composition
    and `ingestion/pipeline.py` wiring are **not yet implemented** (Slice
    2's job), per the instruction not to document the orchestration
    proposal as settled.
  - **`docs/ROADMAP.md`** — Phase 2 status paragraph adds `ProviderRegistry`
    as implemented (same "not yet composed/consulted" caveat), moves it out
    of the "still deferred" list, and reframes the remaining deferred item
    as "multi-provider orchestration" (Slice 2) rather than the prior
    combined "`ProviderRegistry`, multi-provider orchestration" phrasing.
- Files changed: exactly the authorized set — `backend/app/schemas/
  identifiers.py`, `backend/app/discovery/query_planner.py`,
  `backend/app/providers/registry.py`, `backend/tests/
  test_provider_registry.py`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  this handoff entry. No `ingestion/`, `db/models/`, migration, or
  `enabled_providers`/`CollectionRun` file touched.
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_provider_registry.py` — all **10 steps PASS**: Ruff
  format/check, mypy (49 source files), `check_repo.py`, `git diff --check`,
  database-URL safety, real test-database reachability, **15 focused tests**,
  **1461 full-suite tests** (was 1446; +15), temp-directory cleanup, ~96s.
  `alembic heads` confirms `0017` remains the sole head; `git diff --stat --
  backend/migrations/` is empty — zero migration touched, as required. Dev
  database (`jobgoblin`) confirmed unchanged at the pre-existing `0006`
  before and after, via a direct `alembic current` read.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff. It independently re-verified (not merely trusted) that the
  canonical-slug regex now has exactly one compiled copy in the whole
  `backend/` tree (`app/schemas/identifiers.py`, via its own grep) and that
  the three database `CHECK`s the module's comment names are the only
  matching migrations (also its own grep); ran the full suite itself
  (1460 passed, pre-fix count); confirmed the deep-copy isolation claim
  against a *nested* mutable field, not just top-level reassignment; and
  confirmed `query_planner.py`'s extraction is behavior-identical (41/41
  pass). **One Low finding**: `capabilities()` raising was sanitized, but a
  malformed *return value* (e.g. `None`) would instead surface as a raw,
  unsanitized `AttributeError` from the mismatch check right after it,
  inconsistent with the module's own stated intent of converting every
  adapter misbehavior into one categorical exception. Fixed: widened the
  `try` to cover the `.provider` attribute read too, so both failure modes
  convert to the same `ProviderRegistrationError`; added
  `test_capabilities_returning_a_malformed_value_is_rejected_not_a_raw_attribute_error`
  as its regression test; reran the full verifier afterward (1461 passed,
  +1 for the new test) to confirm the fix.
- Deviations/known limitations: none beyond the already-recorded, pre-existing
  `alembic check` substitution.
- STOP — awaiting Codex review. Do not implement or modify ingestion
  orchestration, pipeline ownership, `enabled_providers` semantics,
  `CollectionRun` behavior, `ProviderRegistry` production composition, live
  providers, Tier 4, Phase 3, or any migration.

### Work review

- Date/agent: 2026-09-03, Codex. Implementation diff reviewed:
  `342534f..4ab3a0d` on `phase-2/provider-registry`.
- Independent verification: inspected the complete registry/shared-identifier change,
  tests, and architecture/roadmap updates. Ran the genuine external canonical verifier
  focused on `tests/test_provider_registry.py`: all **10 steps PASS**, including Ruff,
  mypy, repository/diff checks, disposable-database safety/reachability, **15 focused
  tests**, **1461 full-suite tests**, and temporary-directory cleanup. Snapshot copying,
  one-call capability capture, sorted names, duplicate/unknown handling, name drift, and
  QueryPlanner compatibility otherwise match the approved slice.
- **Medium — a malformed capabilities object with a `.provider` attribute escapes as a
  raw exception.** The constructor catches a raised `capabilities()` call and a return
  such as `None`, but it does not establish that the returned object is actually
  `ProviderCapabilities`. A duck-shaped value such as
  `SimpleNamespace(provider="alpha")` passes the guarded attribute read and then raises
  raw `AttributeError` at `capabilities.model_copy(deep=True)`, outside the `try`. This
  contradicts the documented guarantee that malformed returns become a fixed,
  categorical `ProviderRegistrationError`. Require an actual `ProviderCapabilities`
  instance before reading/copying it (or otherwise keep the entire validation/copy path
  inside a sanitized boundary), and add a regression for a malformed object whose
  `.provider` happens to match.
- **Medium — malformed/raising provider names bypass the registry's sanitized boundary.**
  `name = provider.name` is outside a guard and `is_canonical_slug()` assumes `str`.
  A provider exposing `name=None` currently raises raw `TypeError` from `re.fullmatch`;
  a missing or raising `.name` attribute likewise escapes raw at construction. The
  resolution-time `entry.provider.name` read can also propagate a property exception
  rather than the promised categorical name-drift/registration error. Validate that the
  construction-time name is a string before calling the predicate, sanitize ordinary
  exceptions from reading it, and protect the resolution-time read the same way. Do not
  catch `CancelledError`, `KeyboardInterrupt`, or `SystemExit`. Add isolated tests for
  non-string/missing-or-raising construction names and a name property that begins
  raising after successful registration.
- Documentation/handoff correction: update the current Work done and §6.4 wording so
  “malformed capabilities return” and arbitrary-provider/name-drift guarantees match the
  corrected full boundary; preserve this review verbatim. No orchestration or schema
  change is required.
- Verdict: **Changes requested.** The registry design and capability-snapshot approach
  are accepted; only the two bounded fail-closed corrections and their documentation/
  tests are required before merge.
- STOP — do not merge or begin orchestration, pipeline ownership changes,
  `enabled_providers` semantics, ProviderRegistry production composition, provider
  contact, Tier 4, Phase 3, or migrations. Apply only these corrections after user
  authorization and return for re-review.

---

## Iteration 2

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
