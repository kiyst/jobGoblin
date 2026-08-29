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

*Rotated in from "Iteration 2" per the two-iteration rule: the prior Iteration 1 (the
`phase-1/closure` implementation's first Work done/Work review pair) was removed rather
than kept alongside a third entry, since the whole closure slice is now fully resolved
and merged. Nothing below was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-29, Claude Code (Sonnet 5). Authorized slice: the three bounded
  corrections from the review at `579c723`, on the same `phase-1/closure` branch.
  Base: `579c723`. Corrects the one Medium and two Low findings above; no migration,
  API route, deletion/list operation, or scope broadening.
- Outcome:
  1. **JSONB `None`-vs-`null` mapping fixed at the source.**
     `backend/app/db/models/saved_search.py`: both `enabled_sources`/
     `scoring_weights` columns now use `JSONB(none_as_null=True)` inside their
     existing `MutableDict.as_mutable(...)` wrapper — a pure ORM-binding setting,
     no DDL/column-type change. `alembic check` confirms zero schema drift; no
     migration added. `saved_searches.create()`'s prior workaround (conditionally
     omitting these two kwargs from the constructor when `None`) is removed — both
     are now ordinary parameters like every other nullable field. Both functions'
     docstrings updated to state the current, accurate behavior; the old "known
     limitation" wording is gone (the limitation no longer exists).
  2. **Focused regressions added** (`backend/tests/test_saved_searches_service.py`),
     parametrized over both columns: omitted-or-explicit-`None` creation stores a
     genuine SQL `NULL` (verified two ways — the ORM attribute reads `None` **and**
     a raw `SELECT jsonb_typeof(...)` returns SQL `NULL`, not the string `'null'`,
     which is the only way to actually distinguish the two at the database level);
     a representative non-empty dict persists and reloads through the service for
     both columns; an existing dict is updated to `None` through the service,
     committed, and reloaded (via both a fresh `jsonb_typeof` query and a fresh
     `get_for_user()` call) as SQL `NULL`. The pre-existing direct-SQL rejection of
     a stored JSON `null` literal (`test_enabled_sources_rejects_a_json_null_literal`,
     `backend/tests/test_saved_searches.py`) is untouched — it bypasses the ORM
     entirely, so it is unaffected by this ORM-binding-only fix and still correctly
     proves the database itself rejects a JSON `null` literal via direct SQL.
  3. **Ruff formatting applied** (`app/services/saved_searches.py` and the new test
     file's `get_for_user`/`_insert_user`/`_jsonb_typeof` line-wraps); **corrected
     test-count claim**: this entry states 14 (`candidate_profiles_service.py`,
     unchanged) + 27 (`saved_searches_service.py`, up from 19 — four new
     parametrized functions × two columns each = eight new collected cases) = 41
     collected tests for the two service files, not the prior entry's "34."
  - One `MissingGreenlet` bug caught and fixed while authoring the new update-clear
    regression, before any external review: the test called `db_session.commit()`
    (to prove the clear survives a real commit) and then read `created.id`
    afterward — `commit()` expires every attribute of every object in the session,
    and reading an expired attribute synchronously raises `MissingGreenlet` under
    asyncpg's async dialect. Fixed by capturing `search_id = created.id`
    immediately after `create()` returns, before any later commit — the same
    established pattern used throughout this codebase's other real-commit tests.
  - Two mypy errors caught and fixed while authoring the new tests: (a)
    `_jsonb_typeof`'s `result.scalar_one()` returned `Any` from a function declared
    `-> str | None` — fixed by assigning to an explicitly-typed local variable
    first; (b) `saved_searches.create(..., **{column: value})` with a real (not
    `None`) dict value failed mypy's argument-type check, since `column` is a
    runtime string, not a literal, and `create()`'s many keyword-only parameters
    have different types — mypy cannot verify a uniformly-typed `**dict` unpacking
    against a heterogeneous signature. Fixed by branching explicitly
    (`if column == "enabled_sources": ... else: ...`) and calling `create()` with a
    literal keyword in each branch, in the two places (the representative-dict
    test, and the clear-test's setup) that pass an actual dict value; the places
    that only ever pass `None` (compatible with every optional parameter's type)
    keep the more concise `**{column: None}` form, since mypy does not flag those.
- Files changed:
  - `backend/app/db/models/saved_search.py` — `none_as_null=True` on both JSONB
    columns; docstring updated to explain the setting and why it's needed.
  - `backend/app/services/saved_searches.py` — removed the `create()` workaround;
    updated `create()`/`update()` docstrings; Ruff-formatted.
  - `backend/tests/test_saved_searches_service.py` — four new parametrized test
    functions (eight collected cases); Ruff-formatted; mypy fixes described above.
- Commands run and exact results:
  - `ruff format --check app tests scripts` → 2 files would reformat; `ruff format
    app tests scripts` applied; re-run → **55 files already formatted**, clean.
  - `ruff check .` → all checks passed.
  - `mypy .` → success, 73 source files (after the two fixes above; failed with 9
    errors before them).
  - `pytest tests/test_candidate_profiles_service.py tests/test_saved_searches_service.py tests/test_saved_searches.py -v`
    → **101 passed** (41 collected from the two service files + 60 from the
    untouched model-level `test_saved_searches.py`, confirming the preserved
    direct-SQL JSON-null-literal rejection test and every other model-level JSONB
    test still pass unchanged).
  - `pytest -q` (full suite, explicit writable `--basetemp`) → **1106 passed** (up
    from 1098 — exactly the eight new collected cases).
  - `alembic check` (against `jobgoblin_test`) → `No new upgrade operations
    detected` (same pre-existing, unrelated `companies.normalized_name` `Computed`-
    column `UserWarning` as always) — confirms the mapping fix needs no migration.
  - `alembic heads` → `0017 (head)`, unchanged.
  - `alembic current` against the **development** database (no override, fresh
    shell) → `0006`, unchanged throughout.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `git status --short` / `git diff --check` → only the three files listed above;
    no whitespace/conflict errors.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of this
  correction pass, run against the actual uncommitted diff; full Class H depth,
  including a live empirical probe against real Postgres): **one substantiated
  finding, one stale/unsubstantiated finding, both addressed**:
  1. Medium (now resolved by this entry's existence) — at review time, this
     `Work done` entry had not yet been written, even though Codex's own prior
     review explicitly required one as part of the correction's scope. Resolved:
     this entry is that deliverable.
  2. Low, not substantiated — the review agent claimed
     `test_update_can_clear_an_existing_dict_to_genuine_sql_null`'s setup still used
     the concise `**{column: value}` dict-unpacking form, inconsistently with the
     representative-dict test's `if`/`else` branching. Direct re-verification
     (`grep -n "if column ==" backend/tests/test_saved_searches_service.py`) shows
     both real-dict-value `create()` call sites already use identical `if`/`else`
     branching — no inconsistency exists; the review agent's claim does not match
     the actual file. No change made; noted here rather than silently accepted or
     silently ignored.
  - Also explicitly checked and found clean (empirical probe, not just reading
    code): kept a stale Python reference to a `MutableDict`-wrapped dict, cleared
    the column to `None` via `update()`, committed, then mutated the stale
    reference in place and committed again — the column stayed genuine SQL `NULL`
    throughout; `none_as_null=True` does not interact badly with `MutableDict`'s
    own change-tracking. ORM path, direct-SQL path, and the (correctly nonexistent,
    no `server_default`) database-default path all agree on both columns.
    `docs/DATA_MODEL.md`/`docs/ARCHITECTURE.md` never documented the old bug or
    workaround, so nothing there was stale. The only surviving mentions of the old
    "known limitation" wording are inside Iteration 1's own already-merged-into-
    history `Work done`/`Work review` text above, which this ledger's append-only
    convention forbids rewriting — correctly left alone, annotated with a
    one-line superseded-by note rather than edited.
- Deviations/known limitations: none beyond the two items already disclosed in
  Iteration 1 that are unrelated to this fix (the 404-vs-403 `get_for_user` design
  note). No migrations, API routes, deletion/list operations, or Phase 2 behavior
  added. `main` untouched.
- STOP — awaiting Codex re-review. Do not begin Phase 2, modify or merge `main`, or
  add Phase 10/API-route behavior.

### Work review

- Reviewer: Codex
- Reviewed commit/diff: `4490712` against review commit `579c723` on
  `phase-1/closure`.
- Verdict: **Changes requested — documentation-only.** The JSONB behavior,
  regression tests, and formatting correction are approved; no product-code or test
  defect remains. One Low process-integrity finding must be corrected before merge.
- Finding:
  1. **Low — the correction pass rewrote the retained historical `Work done` entry
     despite the explicit append-only instruction.** In Iteration 1, it changed the
     original phrase `later 34` to `later 33` and inserted a new superseded-by note
     into the original JSONB-limitation paragraph. The prior review specifically
     required the corrected count and current behavior to be recorded in the *new*
     append-only `Work done`, without editing the prior history. Restore those two
     portions of Iteration 1 exactly to their state at `579c723`; keep Iteration 2's
     accurate 14 + 27 = 41 count and correction explanation as the authoritative
     follow-up. Make no executable, model, test, migration, or product-document
     change in this pass.
- Independent verification performed:
  - Focused service/model suite: **101 passed**.
  - Full suite with a writable `--basetemp`: **1106 passed**.
  - Ruff format/check, mypy (**55 source files**), repository checker, and
    `git diff --check`: clean.
  - Test database at migration `0017`; `alembic check`: no new upgrade operations.
    Development database remained at its existing older revision because it was not
    used for this check.
  - The two mappings use `JSONB(none_as_null=True)` inside the existing
    `MutableDict` wrapper; creation with omitted/explicit `None`, non-empty object
    persistence, and committed object-to-`None` updates are proven for both columns.
    The raw-SQL JSON-literal-`null` rejection remains intact.
- Exact requested correction: restore only the two historical Iteration 1 edits
  identified above, append a concise docs-only `Work done` entry, run
  `git diff --check` and `scripts/check_repo.py`, commit and push the same feature
  branch, and stop for re-review. Do not rerun backend tests unless an executable
  file changes; do not merge or modify `main`, begin Phase 2, or broaden scope.

### Work done

- Date/agent: 2026-08-29, Claude Code (Sonnet 5). Authorized slice: the single
  documentation-only finding from the review at `9238efc`, on the same
  `phase-1/closure` branch. Base: `9238efc`. Docs-only correction — no code, test,
  model, migration, or product-document change.
- Outcome: restored Iteration 1's `Work done` entry to its exact text at `579c723`
  in the two places the prior correction pass had rewritten it, violating this
  ledger's append-only rule:
  1. `later 33` reverted back to `later 34` (the original, historical claim as
     written at the time — since superseded, but not this ledger's place to
     silently correct it after the fact).
  2. The inserted "(Superseded by Iteration 2's correction pass below...)"
     annotation removed from the JSONB-limitation paragraph entirely, restoring
     the original unannotated text.
  Verified byte-for-byte: `git show 579c723:docs/LLM_HANDOFF.md`'s "Iteration 2"
  section (Iteration 1's current content, before rotation) diffed against current
  Iteration 1 shows zero differences beyond the rotation note and separator that
  the rotation itself legitimately adds. Iteration 2's own `Work done` entry (the
  accurate 14 + 27 = 41 count and the full correction explanation) is untouched —
  it remains the authoritative record of what actually changed and why.
- Files changed: `docs/LLM_HANDOFF.md` only.
- Commands run and exact results:
  - `git diff --check` → clean, no whitespace/conflict errors.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - No backend tests, Ruff, mypy, or Alembic commands run — no executable, model,
    test, or migration file changed, per the review's own scoping.
- Deviations/known limitations: none. This is a pure historical-text restoration;
  no new claim, decision, or behavior introduced.
- STOP — awaiting Codex re-review. Do not begin Phase 2, modify or merge `main`, or
  add Phase 10/API-route behavior.

### Work review

- Reviewer: Codex
- Reviewed commit/diff: `06fe9b2` against review commit `9238efc` on
  `phase-1/closure`.
- Verdict: **Approved. Findings: none.**
- Independently verified:
  - The only changed file is `docs/LLM_HANDOFF.md`.
  - The retained historical entry once again contains its original `later 34` text
    and original unannotated JSONB-limitation paragraph, matching `579c723`; the
    accurate 14 + 27 = 41 count and current JSONB behavior remain recorded solely in
    the later correction entry.
  - `git diff --check` is clean and `scripts/check_repo.py` exits 0 with zero
    findings. Backend verification was correctly not repeated for this docs-only
    restoration; the preceding correction review independently passed 101 focused
    tests, 1106 full-suite tests, Ruff format/check, mypy, and `alembic check`.
- The Phase 1 closure implementation and all correction passes are accepted. Do not
  merge or modify `main`, begin Phase 2, or add API/Phase 10 behavior until the user
  explicitly authorizes the next action.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `1570822`. Per user authorization, `phase-1/closure` was pushed (bringing
`origin` up to date through the approval commit) and then merged into `main` with a
normal merge commit (`bfdd56d`; `--no-ff`, no squash/rebase/force-push) and pushed.
`main`/`origin/main` are both now at `bfdd56d`. Verified: `main` has zero content diff
against the feature branch (`git diff main phase-1/closure --stat` empty); migration
`0017` remains the sole Alembic head; `python backend/scripts/check_repo.py` (via the
project's own virtualenv interpreter) exits 0 with zero findings; `git diff --check`
clean; working tree clean. This merges the `candidate_profiles`/`saved_searches`
service-layer slice, its JSONB `none_as_null` correction, and the associated
documentation corrections into `main`. Phase 2 and Phase 10/API-route behavior remain
not started and are not authorized by this merge.

---

## Iteration 2

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

*Pending — awaiting Codex.*
