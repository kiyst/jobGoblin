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

- Date/agent: 2026-09-02, Claude Code (Sonnet 5). Class H implementation of the
  approved QueryPlanner fixture-integration slice on `phase-2/query-planner`,
  based on clean `main@5b2c947`. This is a genuinely new product slice
  (following the accepted Phase 2 completion re-sequencing, conclusion 3 of the
  prior read-only exit-gate audit) — not part of the exit-gate closure or
  ProviderRegistry work, both still untouched.
- Outcome: new `app/discovery/query_planner.py::QueryPlanner.plan()` — a
  stateless `@staticmethod`, no database access, no network access, never
  calling a provider's `discover()` — translates one `SavedSearch` plus one
  provider's `ProviderCapabilities` into a `SourceQuery | None`. Not yet wired
  into `ingestion/pipeline.py`; proven instead by a fixture-driven integration
  test feeding its real output into the existing, unmodified
  `pipeline.run()`.
- Binding decisions applied exactly as authorized, across two revision rounds:
  1. `QueryPlanner.plan(saved_search, provider_capabilities, *, titles, locations)
     -> SourceQuery | None` — a class `@staticmethod`, matching the documented
     `QueryPlanner.plan(...)` call form exactly, not a bare module function.
  2. `titles`/`locations` are caller-supplied `Sequence[str]` — `SavedSearchTitle`/
     `SavedSearchLocation` have no ORM relationship to `SavedSearch` and no
     ordering column of their own, so `QueryPlanner` cannot load or order them
     itself; it preserves whatever order it is given, verbatim, and documents
     that defining "deterministic order" is the future loader's responsibility.
     A bare `str`/`bytes` value for either parameter is rejected rather than
     silently iterated character-by-character; every element must be `str`.
  3. The source-validation contradiction is resolved and `ARCHITECTURE.md` §6.6
     step 3 corrected: `None` is returned only for an explicit empty selection
     or an absent key expanding against zero advertised sources — never for
     "every listed source failed validation," since an unknown name always
     raises before the list could be filtered to empty.
  4. `SavedSearch.enabled_sources`' selected-provider value is validated at
     runtime (must be a list, all-string elements, no duplicates) since its own
     `CHECK` only guarantees a top-level JSON object.
  5. `provider_capabilities.provider`, every `ProviderCapabilities.sources`
     mapping key, and every embedded `SourceCapabilities.source` must match the
     same canonical lowercase-ASCII-slug grammar every other `provider`/`source`
     database `CHECK` in this schema already enforces
     (`^[a-z0-9][a-z0-9._-]*$`); every mapping key must equal its own embedded
     `.source`. Malformed identifiers are rejected, never normalized.
  6. Every `QueryPlanValidationError` message is a fixed, categorical string —
     no raise site interpolates a provider name, source name, capabilities key,
     embedded `.source`, or `enabled_sources` value; none of that is "trusted"
     merely because it came from a `ProviderCapabilities` object rather than raw
     JSON.
  7. Complete `SavedSearch` -> `SourceQuery` field mapping implemented exactly
     as specified, including `preferred_companies -> company_filter` (not
     deferred) and `recency_limit_hours -> posted_within_hours` (renamed).
     `remote_rules -> remote_ok`: `remote_only -> True`; `hybrid_ok`/
     `onsite_ok`/`any -> None` — no `onsite_ok -> False`, since a tri-state
     boolean cannot losslessly express four rules and `False` would incorrectly
     assert "remote forbidden."
  8. Every unrepresentable field named explicitly in code and docs
     (`preferred_salary`, `industries`, skill/keyword fields, polling/scoring/
     provider-enablement fields, `max_results`). `SavedSearchLocation.
     radius_miles_override`/coordinates identified as a genuine `SourceQuery`
     schema gap, not silently claimed to be covered by the single global
     `radius_miles` field — `radius_miles` itself is still mapped independently
     of whether `locations` is populated; no new "radius requires location"
     invariant was invented.
  9. `local_enforcement` contains exactly one key per resolved source, always
     (including an explicit empty set). 4 fields are governed exclusively by
     their own dedicated `SourceCapabilities` boolean (`locations`/
     `radius_miles` sharing one); the remaining 6 by `supported_query_fields`
     membership. No contradiction is possible by construction — the two
     mechanisms cover disjoint field-name sets, so a dedicated field's name
     appearing in `supported_query_fields` too is simply never consulted.
- Files changed: `backend/app/discovery/__init__.py` (new),
  `backend/app/discovery/query_planner.py` (new),
  `backend/tests/test_query_planner.py` (new, 33 tests), `docs/ARCHITECTURE.md`
  (signature/return-type correction, §6.6 step 3 contradiction fix, new "Phase 2
  implementation notes" subsection with the complete field-mapping table),
  `docs/ROADMAP.md` (capability description, merge-state-neutral); this handoff
  entry. No schema, migration, `ingestion/pipeline.py`, `providers/fixture.py`,
  `ProviderRegistry`, multi-provider orchestration, planning-failure
  persistence, `providers_enforced_locally` persistence, Tier 4, or live-provider
  file touched.
- Verification: genuine external `python scripts/verify.py --level routine
  --focus tests/test_query_planner.py` — all **10 steps PASS**: Ruff
  format/check, mypy (85 source files), `check_repo.py`, `git diff --check`,
  database-URL safety, real test-database reachability, **33 focused tests**,
  **1438 full-suite tests** (was 1405; +33), temp-directory cleanup, ~114s.
  `alembic heads` confirms `0017` remains the sole head; `git diff --stat --
  backend/migrations/` is empty — zero schema/migration touched, as required.
  `alembic check` against the configured dev database (`jobgoblin`) still fails
  for the same pre-existing reason recorded in the two prior iterations (stamped
  at `0006`, far behind head `0017` — a condition that predates every branch in
  this ledger and is unrelated to this slice, which adds zero migrations); not
  remediated — a direct before/after `alembic current` check confirms it stayed
  at `0006` throughout. All schema/database work ran only against the disposable
  `jobgoblin_test` database.
- Adversarial self-review: dispatched a fresh-context subagent against the
  actual diff. It confirmed, across all 10 checked dimensions: every validation
  check (canonical-slug/key-mismatch, titles/locations bare-string and
  non-string-element, enabled_sources shape, unknown-source) is independently
  reachable and exercised by a test isolating exactly that one check; zero raise
  sites interpolate a runtime value into any message, and the test file's own
  "message never contains the offending value" assertions use sufficiently
  distinctive values to be meaningful, not vacuous; the dedicated-vs-generic
  `local_enforcement` split never contradicts itself even when a test
  deliberately makes `supported_query_fields` disagree with a dedicated
  boolean; no mutation of `saved_search`/`provider_capabilities`/the caller's
  own `titles`/`locations` list objects; `radius_miles` is mapped independent of
  `locations`; `remote_rules` mapping has no accidental `False` path; the one
  database-backed integration test captures every cleanup-tracking ID before
  any assertion that could fail (the exact defect class caught and fixed in
  each of the two immediately preceding slices — deliberately re-checked here
  and found not reintroduced); the integration test's own comments explicitly
  disclaim implying `FixtureProvider` applies filters remotely or that
  `pipeline.run()` filters locally; `plan` is confirmed a `@staticmethod` on a
  class; and the new `ARCHITECTURE.md` prose matches the actual code exactly,
  field for field. No findings.
- Deviations/known limitations: none beyond the already-recorded, pre-existing
  `alembic check` substitution.
- STOP — awaiting Codex review. Do not merge, begin `ProviderRegistry`/
  multi-provider orchestration, add schema changes, contact live providers, wire
  `QueryPlanner` into `pipeline.run()`, or start any other slice.

### Work review

- Date/agent: 2026-09-02, Codex. Implementation diff reviewed:
  `5b2c947..d7cb03c` on `phase-2/query-planner`.
- Independent verification: inspected the complete planner, focused tests, and
  architecture/roadmap changes. Ran the genuine external canonical verifier focused
  on `tests/test_query_planner.py`: all **10 steps PASS**, including Ruff, mypy,
  repository/diff checks, disposable-database safety and reachability, **33 focused
  tests**, **1438 full-suite tests**, and temporary-directory cleanup.
- Confirmed behavior: source expansion and explicit-empty semantics are correct;
  malformed `enabled_sources` values and unknown sources fail before provider use;
  field mappings, remote-rule behavior, per-source enforcement, input copying, and the
  one-source fixture/pipeline compatibility proof otherwise match the approved scope.
- **Medium — the canonical-slug check accepts a final newline.**
  `backend/app/discovery/query_planner.py` compiles
  `^[a-z0-9][a-z0-9._-]*$` and tests it with `Pattern.match()`. In Python, `$` may
  match immediately before a final newline: the current implementation accepts
  `"fixture_provider\n"` even though `Pattern.fullmatch()` rejects it. This violates
  the claimed exact lowercase-ASCII-slug boundary and can let a planner identifier
  differ from the canonical value later produced by ORM trimming. Use an actual full
  match (`fullmatch`, with a pattern suitable for it) and add isolated regressions for
  a trailing LF and CR/LF on the provider, capability-map key, and embedded source
  paths.
- **Medium — unbounded PostgreSQL numeric can become non-finite during planning.**
  `saved_searches.radius_miles` is deliberately an unconstrained-precision PostgreSQL
  `numeric`, while `SourceQuery.radius_miles` is `float`. The direct conversion
  `float(saved_search.radius_miles)` turns a valid stored value such as
  `Decimal("1e10000")` into positive infinity, and Pydantic currently accepts that
  infinity. A non-finite provider query is neither the stored value nor a usable radius.
  Convert and then require `math.isfinite`, raising a fixed, categorical
  `QueryPlanValidationError` on overflow/non-finite output. Add accepted finite/fractional
  and rejected overflow regressions; do not add a database bound or migration.
- **Low — normative architecture text claims deferred orchestration already exists.**
  `docs/ARCHITECTURE.md` §6.6 steps 2–3 still say `ingestion/pipeline.py` records a
  planning-time failure and avoids the provider call. The same new section later
  correctly says the planner is not wired and those behaviors require the future
  ProviderRegistry/orchestration loop. Rewrite steps 2–3 in future/ownership-neutral
  terms: the future orchestrator must record/continue and must not call `discover()`;
  the current `pipeline.run()` does neither planning nor accept `None`.
- **Low — executable schema comments still say QueryPlanner is deferred.**
  `backend/app/schemas/provider.py` still says source expansion and
  `local_enforcement` assignment are deferred and callers construct queries directly.
  Update those comments/docstrings to distinguish the now-implemented planner from its
  still-deferred production orchestration/wiring. No schema behavior change is needed.
- Verdict: **Changes requested.** The planner design is accepted, but the two bounded
  executable corrections and two documentation corrections above are required before
  merge.
- STOP — do not merge, begin ProviderRegistry/multi-provider orchestration, contact a
  provider, add a migration, or start another slice. Apply only these corrections after
  user authorization, rerun the focused canonical verifier/full suite, and return for
  re-review.

---

## Iteration 2

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
