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

### Work review

- Date/agent: 2026-09-01, Codex. Correction diff reviewed:
  `d5acc3a..5ceed41` on `phase-2/partial-success-handling`.
- Independent verification: inspected the shared-constant rename, both model-validator
  call sites, the Core-update path, the unchanged run-level failure construction, and
  the new persistence/reload regression. Ran the genuine external canonical verifier
  focused on `tests/test_ingestion_pipeline.py`: all **10 steps PASS**, including **56
  focused tests** and **1405 full-suite tests**.
- Prior-finding disposition: **closed**. `pipeline.py` now trims attempt-level
  `error_message` with the exact public `COVERED_WHITESPACE` constant used by
  `CollectionRunProviderAttempt`; no unrestricted `.strip()` or duplicate literal
  remains in the affected path. Covered outer characters trim, covered-only input
  becomes SQL NULL, and non-covered U+00A0 survives persistence and reload.
- Independently parsed the regression source and confirmed its boundary characters are
  actual U+00A0 code points (`0xA0`), not visually similar ASCII spaces. Confirmed
  `CollectionRun.failures[*].error.detail` remains the exact original input for all four
  cases and receives no incidental normalization.
- Scope check: only the model constant/validator references, pipeline import and one
  normalization call, the regression test, and this handoff rotation changed. No schema,
  migration, status, aggregation, error-selection, failure-shape, or logging behavior
  changed. No further findings.
- Verdict: **Approved**. The multi-source partial-success handling slice and its
  correction are accepted; no additional correction pass is required.
- Exact requested corrections: none.
- STOP — do not merge to `main`, begin another Phase 2 slice, contact providers, or
  perform the Phase 2 exit-gate audit until the user explicitly authorizes it.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `9441ee2` (no findings, after the whitespace-normalization correction recorded
earlier in this same review cycle). Per user authorization,
`phase-2/partial-success-handling` was merged into `main` with a normal merge commit
(`002b7f8`; `--no-ff`, no squash/rebase/force-push) and pushed. `main`/`origin/main`
are both now at `002b7f8`. Verified: the feature branch was clean and pushed at
`9441ee2`, and `main`/`origin/main` were still at `02ef086` immediately before the
merge; `main` has zero content diff against the feature branch (`git diff main
phase-2/partial-success-handling --stat` empty); migration `0017` remains the sole
Alembic head; `python -m scripts.check_repo` exited `0`; `git diff --check` was
clean; working tree clean throughout. No `/compact`, network request, or database
mutation was performed during the merge.

**Rollback boundary:** reverting `002b7f8` (a single merge commit) restores `main` to
`02ef086` exactly — no schema/migration exists in this slice to downgrade, and no
data migration accompanies it (every column this slice populates —
`collection_run_provider_attempts.status='partial'`/`error_category`/`error_message`/
`retry_count`/`rate_limited`/`incomplete_results`, `collection_runs.failures` — already
existed from Phase 1). This merges the multi-source partial-success handling slice
only (`backend/app/ingestion/pipeline.py`, `backend/app/db/models/
collection_run_provider_attempt.py`'s `COVERED_WHITESPACE` promotion, their tests, and
the documentation files listed in the `Work done` entries above) — it does **not**
touch Tier 4, `QueryPlanner`, `ProviderRegistry`, any live provider, the Phase 2
exit-gate audit, or any other Phase 2 work, all of which remain not started and are
not authorized by this merge.

---

## Iteration 2

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
