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

- Date/agent: 2026-09-02, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/query-planner` for the four bounded findings from review commit
  (uncommitted at review time; committed together with this correction — see
  Iteration 1's `Work review` above, preserved byte-for-byte, not rewritten).
  Base: `d7cb03c` plus the uncommitted review. No product code beyond the exact
  four corrections requested: `ProviderRegistry`, multi-provider orchestration,
  schema, migrations, and any wiring of `QueryPlanner` into `pipeline.run()`
  remain untouched.
- Outcome, addressing each finding exactly:
  1. **Canonical-slug full-match.** `query_planner.py`'s `_CANONICAL_SLUG_PATTERN`
     is now checked with `.fullmatch()` at all three sites (provider, capability
     mapping key, embedded `SourceCapabilities.source`) instead of `.match()`.
     Python's `$` matches either true end-of-string or immediately before a
     single trailing `\n`, so `.match()` wrongly accepted
     `"fixture_provider\n"`; `.fullmatch()` requires the match to consume the
     entire string, closing that gap — confirmed empirically before and after.
     Six new isolated regressions: trailing LF and CRLF for each of the
     provider/capability-key/embedded-source paths, each holding the other two
     identifiers valid so only the intended check fires. (CRLF was already
     rejected pre-fix — `\r` was never in the allowed character class — so
     those two are confirmatory, not regression, tests; only the LF variants
     would have failed before this fix. Stated explicitly in the test file's
     own comment.)
  2. **`radius_miles` finiteness.** After `Decimal -> float` conversion,
     `math.isfinite()` is now required; a non-finite result (e.g.
     `Decimal("1e10000")` overflowing to infinity — a legitimately storable
     value under `saved_searches.radius_miles`'s unconstrained-precision
     `numeric`) raises a new fixed, categorical `QueryPlanValidationError`
     (`_ERROR_RADIUS_MILES_NOT_FINITE`) that never embeds the actual value or
     the words "inf"/"infinity". Two new tests: an ordinary finite fractional
     value is accepted; `Decimal("1e10000")` is rejected. No database
     `CHECK`/migration added, per instruction.
  3. **`ARCHITECTURE.md` §6.6 steps 2–3, and their "Behavior summary" bullet
     restating the same claim**, no longer assert that the current
     `ingestion/pipeline.py::run()` records planning-time failures or handles a
     `None` planned query — neither is true today (`run()` doesn't call
     `QueryPlanner.plan()` at all). Both responsibilities are now attributed
     explicitly to the future ProviderRegistry/multi-provider orchestrator,
     cross-referenced to this same section's own "Phase 2 implementation
     notes". Checked the rest of §6.6 for the same stale claim restated
     elsewhere — found and fixed one additional instance (the summary bullet)
     beyond the two numbered steps Codex named, for internal consistency
     within the same section.
  4. **`backend/app/schemas/provider.py`'s `SourceQuery` docstring and
     `local_enforcement` comment** now distinguish "`QueryPlanner.plan()` —
     implemented" from "wiring into `ingestion/pipeline.py` — still deferred",
     replacing the stale "QueryPlanner (deferred)" wording. No schema or
     validator change — confirmed the diff is comment-only.
- A fresh-context adversarial review (below) found one additional test-isolation
  gap beyond the four findings, fixed in this same pass: the original
  capability-map-key trailing-LF/CRLF tests set *both* the dict key and the
  embedded `.source` to the same invalid string, so they could not distinguish
  "the key check fired" from "the embedded-source check fired" (both live
  behind one `or`). Fixed by keeping the embedded `.source` a valid — but
  deliberately different-from-the-key — slug in both tests, isolating the
  key-specific path the same way the embedded-source tests already isolated
  theirs.
- Files changed: `backend/app/discovery/query_planner.py` (fullmatch; finite
  check; new error constant and docstring additions),
  `backend/tests/test_query_planner.py` (8 new tests: 6 slug/newline, 2
  radius-finiteness; one existing pair of tests corrected for isolation),
  `docs/ARCHITECTURE.md` (§6.6 steps 2–3 and summary bullet reattributed to the
  future orchestrator), `backend/app/schemas/provider.py` (comment-only), this
  handoff entry (Iteration 1's `Work done`/`Work review` preserved verbatim,
  oldest prior iteration dropped per the rotation rule). No schema, migration,
  `ingestion/pipeline.py`, `ProviderRegistry`, orchestration, Tier 4, or
  live-provider file touched.
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_query_planner.py` — all **10 steps PASS**: Ruff
  format/check, mypy (85 source files), `check_repo.py`, `git diff --check`,
  database-URL safety, real test-database reachability, **41 focused tests**
  (was 33; +8), **1446 full-suite tests** (was 1438; +8), temp-directory
  cleanup, ~137s. `alembic heads` confirms `0017` remains the sole head; `git
  diff --stat -- backend/migrations/` is empty. `alembic current` against the
  configured dev database (`jobgoblin`) confirmed unchanged at the same
  pre-existing `0006` before and after this pass — no `alembic upgrade` was
  run; all schema/database work ran only against the disposable
  `jobgoblin_test` database.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff. It independently re-verified the `.fullmatch()` fix by direct
  regex execution (not just trusting the diff) and confirmed CRLF was already
  rejected pre-fix, correctly distinguishing genuine regressions from
  confirmatory tests; traced the `radius_miles` finite check end-to-end and
  confirmed no false-positive path on an ordinary value and no value/"inf"
  leakage in the new error message; confirmed `ARCHITECTURE.md` §6.6 is now
  internally consistent throughout, not just at the two numbered steps;
  confirmed `provider.py`'s diff is comment-only; and confirmed the capability-
  map-key isolation gap described above, which was fixed in this same pass
  before finalizing. It also flagged that this handoff entry did not yet exist
  at the time it ran (an artifact of running the review before writing this
  `Work done` section, not a defect) and confirmed the diff's scope is exactly
  the four corrections, their tests, and this handoff — nothing else.
- Deviations/known limitations: none beyond the already-recorded, pre-existing
  `alembic check` substitution.
- STOP — awaiting Codex re-review. Do not merge, begin `ProviderRegistry`/
  multi-provider orchestration, add schema changes, contact live providers, wire
  `QueryPlanner` into `pipeline.run()`, or start any other slice.

### Work review

- Date/agent: 2026-09-02, Codex. Correction diff reviewed:
  `d7cb03c..15ce73c` on `phase-2/query-planner`.
- Independent verification: inspected every changed executable/test/documentation file;
  directly ran the eight focused newline/finiteness cases (**8 passed**); then ran the
  genuine external canonical verifier focused on `tests/test_query_planner.py`: all
  **10 steps PASS**, including Ruff, mypy, repository/diff checks, disposable-database
  safety/reachability, **41 focused tests**, **1446 full-suite tests**, and temporary-
  directory cleanup.
- Prior-finding disposition: **closed**. Canonical provider/source identifiers now use
  true full-string matching on all three paths, including isolated trailing-LF/CRLF
  coverage. `radius_miles` conversion now rejects non-finite float output with a fixed,
  sanitized error while preserving valid finite fractional values. No database bound,
  schema change, or migration was introduced.
- Documentation disposition: **closed**. ARCHITECTURE §6.6 now assigns planning-failure
  persistence, continuation, and `None` handling to the future orchestrator and states
  accurately that current `pipeline.run()` accepts only an already-built `SourceQuery`.
  `schemas/provider.py` now distinguishes the implemented planner from its deferred
  automatic wiring without changing schema behavior.
- Scope/adversarial-fix check: the additional test correction only isolates the
  capability-map-key cases by keeping the embedded source valid; it changes no product
  behavior and makes the intended branch provable. No ProviderRegistry, orchestration,
  pipeline wiring, provider contact, migration, or unrelated product work entered the
  diff. No further findings.
- Verdict: **Approved**. The QueryPlanner fixture-integration slice and bounded
  correction pass are accepted; no additional correction is required.
- Exact requested corrections: none.
- STOP — do not merge to `main` or begin ProviderRegistry/multi-provider orchestration,
  Tier 4, provider contact, Phase 3, or any other slice until the user explicitly
  authorizes the next action.

### Merge record

- Date: 2026-09-03. User authorized merging `phase-2/query-planner` into `main`
  following Codex's final Approved re-review (no findings) above.
- Pre-merge state: `main` and `origin/main` both at `5b2c947`; feature branch
  pushed and clean at `1840874` (merge-base `5b2c947` — no divergence).
- Merge: `git merge --no-ff phase-2/query-planner` on `main` — merge commit
  `8a57550`. Post-merge diff against the feature branch's tip is empty (zero
  content difference); `check_repo.py` and `git diff --check` both clean.
- Post-merge verification: genuine external `verify.py --level routine --focus
  tests/test_query_planner.py` — all **10 steps PASS** (Ruff format/check,
  mypy, `check_repo.py`, `git diff --check`, disposable-database URL/
  reachability, **41 focused tests**, **1446 full-suite tests**, temp-directory
  cleanup). `alembic heads` confirms `0017` remains the sole head; no migration
  files touched by the merge. Dev database (`jobgoblin`) confirmed unchanged at
  `0006` — untouched throughout.
- Pushed: `main` at `8a57550`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `5b2c947` (the
  commit immediately before this merge) — this removes `QueryPlanner` and its
  tests/docs cleanly, with no migration to reverse and no data written by this
  slice to any environment.
- STOP — do not begin ProviderRegistry/multi-provider orchestration, Tier 4,
  provider contact, Phase 3, or any other slice without separate authorization.

---

## Iteration 2

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
