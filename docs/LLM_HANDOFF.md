# LLM Engineering Handoff

Purpose: this file is the shared communication ledger between the implementing LLM and
the reviewing LLM. Update it at the end of every bounded implementation or correction
pass so the user does not have to copy status messages between agents.

This ledger records only the two latest completed iterations. Git remains the source of
truth for diffs and rollback; record commit or base references whenever they exist.

## Required workflow

1. Before working, read the master project documentation, `PHASE_RISK_CHECKLIST.md`,
   and both iterations in this file.
2. The implementing LLM completes only the approved slice, runs the required checks,
   and fills in a new `Work done` section. It must not fill in its own `Work review`.
3. The reviewing LLM independently inspects the repository and actual diff, runs
   proportionate checks, gives the user its findings, and writes the same findings in
   that iteration's `Work review` section. A review does not authorize code changes.
4. The implementing LLM reads the latest review on its next run. It changes only
   findings approved by the user, then records that correction pass as the next
   iteration.
5. Never allow both LLMs to edit implementation files simultaneously. Only the active
   implementer writes code; the reviewer writes only its `Work review` entry unless the
   user explicitly transfers implementation ownership.

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
- The reviewing LLM may commit only its own `Work review` entry unless the user
  explicitly authorizes implementation changes.
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

---

## Iteration 1

*Rotated in from "Iteration 2" per the two-iteration rule: its `Work review` (below) is
no longer pending — Codex gave its finding and requested correction, which are being
addressed in this rotation's Iteration 2 — so the previous Iteration 1 (the focused
`saved_search_titles` test correction pass and Codex's approval of it) was removed
rather than kept alongside two already-reviewed entries. Nothing below was rewritten —
only renumbered, with "Ending commit" backfilled to the actual hash Codex reviewed.*

### Work done

- Date and agent: 2026-08-26, Claude Code (Sonnet 5).
- Approved phase/slice: `saved_search_locations` only — the final child table of the
  `saved_searches` group. No `companies`, no other table, no expansion of scope.
- Outcome: model, migration `0008`, factories, and database tests implemented and
  verified against real PostgreSQL. 206 tests passed, 0 skipped (up from 168 — 38 new
  `saved_search_locations` tests).
- Base/starting commit: `0333f10` (`docs(review): record saved-search-titles merge
  into main`) on `main` — the commit recording the prior slice's merge, itself on top
  of `aca923e` (Codex's approval of the `saved_search_titles` correction pass).
  Confirmed `main`/`origin/main` clean and at `0333f10` before making any changes.
  Branch `phase-1/saved-search-locations` created directly from `0333f10`.
- Ending commit or working-tree state: `ab2bdb9` (`feat(phase-1): implement saved
  search locations slice` — this is the commit Codex's `Work review` below actually
  reviewed).
- Two schema questions the user caught that the implementing agent's own proposal had
  missed, resolved by explicit approval before migration `0008` was written:
  1. `latitude`/`longitude` must be present together — a database `CHECK` requiring
     both NULL or both non-NULL (a half-geocoded row is not a valid state).
  2. `docs/DATA_MODEL.md`'s prose claiming each location has a "radius/remote
     override" was stale wording (no remote-override column has ever been documented
     or approved) — corrected in place, no new column invented.
- Product decisions approved by the user before this pass began (nine items, all
  confirmed as-proposed or as corrected above):
  1. `location_text` normalization option (a): ORM `@validates` trims exactly
     space/tab/LF/CR, case preserved; matching `CHECK`s requiring already-normalized
     and non-empty.
  2. Unique functional index on `(saved_search_id, lower(location_text))` only — no
     redundant `trim()` inside the index, since the `CHECK`s already guarantee
     pre-trimmed storage; `docs/DATA_MODEL.md` corrected to explain this equivalent
     but stronger stored-value invariant.
  3. NULL-safe coordinate-range `CHECK`s: latitude `[-90, 90]`, longitude
     `[-180, 180]`.
  4. Coordinate-pair `CHECK` requiring both NULL or both non-NULL (see schema
     question 1 above).
  5. `latitude`, `longitude`, and `radius_miles_override` remain unconstrained-
     precision `numeric` — no precision or scale specified.
  6. NULL-safe non-negative `CHECK` for `radius_miles_override`.
  7. `created_at`/`updated_at` per the established global convention, including ORM-
     driven `updated_at`.
  8. Stale "radius/remote override" documentation phrase corrected; no remote-override
     column invented (see schema question 2 above).
  9. No redundant plain index on `saved_search_id` — already the composite unique
     index's leading column.
- Files changed:
  - `backend/app/db/models/saved_search_location.py` (new) — `SavedSearchLocation`
    model. `location_text` uses a `@validates` normalizer (trim only, no lowercasing —
    same case-handling as `SavedSearchTitle.title`). Six `CheckConstraint`s in
    `__table_args__`: `location_text` normalized/non-empty, `latitude`/`longitude`
    range, the coordinate-pair `(latitude IS NULL) = (longitude IS NULL)` invariant,
    and `radius_miles_override` non-negative. The case-insensitive unique index is a
    module-level `Index(...)` call after the class, using `lower(...)` only (not
    `lower(trim(...))`, per decision 2).
  - `backend/app/db/models/__init__.py` — registers `SavedSearchLocation` alongside
    the other five models.
  - `backend/app/db/base.py` — docstring updated to mention all six Phase 1 models.
  - `backend/migrations/versions/0008_saved_search_locations.py` (new) —
    `down_revision = "0007"`. Table created with all constraints defined inline in
    `op.create_table(...)` (the established pattern); the functional unique index
    added via a separate `op.create_index(...)`. Docstring explicitly notes the
    corrected stale "radius/remote override" wording and that no new column was
    added. `downgrade()` drops the index then the table.
  - `backend/tests/conftest.py`:
    - Added `make_saved_search_location`, a factory fixture matching
      `make_saved_search_title`'s pattern (takes `saved_search_id` explicitly).
    - Added `real_committed_user_saved_search_and_location`, mirroring
      `real_committed_user_saved_search_and_title`'s failure-safe real-commit
      lifecycle/cleanup pattern exactly (built on top of
      `real_committed_user_and_saved_search`), for `saved_search_locations`' own
      cascade-delete/`updated_at` tests.
  - `backend/tests/test_saved_search_locations.py` (new) — 38 tests: valid insert/
    retrieve; ORM trimming of a whitespace-wrapped `location_text` (case preserved);
    direct-SQL rejection of an empty, a covered-whitespace-only, and a non-normalized
    `location_text`; direct-SQL rejection of a whitespace-wrapped duplicate attempting
    to bypass the uniqueness index; same-case and case-insensitive duplicate
    rejection; confirmation that case is preserved despite case-insensitive
    uniqueness; the same `location_text` accepted on two different saved searches
    (per-search scoping); distinct locations accepted on one search; nonexistent
    `saved_search_id` FK rejection; `ON DELETE CASCADE` from `saved_searches` (real
    commits) proven two ways — the deleted search's own location removed, a second,
    independent search's location surviving untouched; latitude/longitude defaulting
    to `None`; both settable together; range-`CHECK` boundary-accepted and
    just-past-boundary-rejected cases for both latitude and longitude (parameterized);
    coordinate-pair both-NULL accepted, both-non-NULL accepted, and **both one-sided
    invalid states rejected** — latitude-only and longitude-only — each proven twice,
    once through the ORM and once through a direct raw-SQL `INSERT` that bypasses the
    ORM entirely, so the `CHECK` is proven to be enforced by PostgreSQL itself, not
    merely by attribute-assignment order in application code; `radius_miles_override`
    nullable default, non-negative `CHECK` accepted (zero/positive)/rejected
    (negative), and fractional-precision round-trip; UTC-aware timestamps; and
    `updated_at` advancing on an ORM update (real commit).
  - `docs/DATA_MODEL.md` — `saved_search_locations` marked **Implemented**; added a
    "Rev 11" note; corrected the table's own "radius/remote override" prose to
    "radius override" only; updated the table's own column list (adding
    `created_at`/`updated_at`, documenting all six `CHECK`s, and explaining the
    `lower(...)`-only index formula versus the previously-documented
    `lower(trim(...))`); added the first `saved_search_locations` row to the
    "Phase 1 constraints & indexes" summary table.
  - `docs/ROADMAP.md` — Phase 1 status line now also describes the
    `saved_search_locations` slice as complete and verified.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the focused
    `saved_search_titles` test correction pass — removed; prior Iteration 2
    renumbered to Iteration 1; this entry appended as the new Iteration 2).
- Migration revisions: `0008` (new, `down_revision = "0007"`) — adds
  `saved_search_locations`. `0001`–`0007` unchanged.
- Commands run and exact results:
  - `git checkout -b phase-1/saved-search-locations 0333f10` → success, clean tree,
    `HEAD` at `0333f10`.
  - `ruff format .` → 33 files left unchanged (no reformatting needed at any point).
  - `ruff check .` → all checks passed.
  - `mypy app tests` → success, 24 source files.
  - `pytest -v -k saved_search_location` (first and only run) → **38 passed** — no
    failures this time; every id captured before any later commit, avoiding the
    expired-attribute (`MissingGreenlet`) bug that recurred on earlier slices.
  - `pytest -v` (full suite) → **206 passed, 0 skipped**.
  - `DATABASE_URL=...jobgoblin_test alembic current` (before any change) → `0007`.
  - `DATABASE_URL=...jobgoblin_test alembic upgrade head` → success, `0007 -> 0008`
    ("existing `0007 -> 0008`" scenario).
  - `DATABASE_URL=...jobgoblin_test alembic downgrade 0007` / `upgrade head` →
    success (round-trip scenario).
  - `DATABASE_URL=...jobgoblin_test alembic check` → `No new upgrade operations
    detected.`
  - `DATABASE_URL=...jobgoblin_test alembic downgrade base` / `upgrade head` →
    success, ` -> 0001 -> ... -> 0007 -> 0008` (fresh `base -> head`).
  - `alembic current` against the **development** database (default `DATABASE_URL`,
    no override) → `0006`, unchanged throughout — confirmed untouched.
  - `pytest -q` (final re-run after the full migration verification sequence) →
    **206 passed**.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: "define nullability/defaults/
  uniqueness/checks/indexes/ON DELETE before implementing each table" — all nine
  product decisions above were approved before migration `0008` was written, including
  two the user caught that the implementing agent's own proposal had missed; "every
  migration is reviewed and tested upgrade -> downgrade -> upgrade" — exercised as
  four scenarios (existing `0007 -> 0008`, round-trip, fresh `base -> head`,
  `alembic check`); "PostgreSQL behavior is tested against PostgreSQL" — the
  coordinate-pair invariant (including both one-sided-invalid states) is proven
  against real Postgres constraint enforcement both via the ORM and via direct SQL
  bypassing it entirely, not asserted from code; "destructive cascades" — proven both
  for the deleted search's own location and for a second, unrelated search's location
  surviving untouched.
- Skipped or unavailable verification: none. Every command above executed for real,
  including the development-database confirmation.
- Deviations and ADR impact: none — every test passed on the first run; no format,
  lint, or type-check findings at any point. No ADR impact — Phase 1
  implementation-slice detail only.
- Known limitations: `radius_miles_override`'s fallback to `saved_searches.radius_miles`
  when NULL is an application-layer concern — nothing in this migration enforces or
  reads that fallback; `updated_at` still only advances for ORM-driven writes
  (unchanged, out of scope for this pass, same as every prior table).
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `companies` or alter
  `main`.

### Work review

- Date and reviewing agent: 2026-08-26, Codex.
- Diff/revision reviewed: feature commit `ab2bdb9` against `main` commit `0333f10`
  on `phase-1/saved-search-locations`; the branch was clean and matched
  `origin/phase-1/saved-search-locations` before this review entry.
- Verification performed:
  - Inspected the complete `0333f10..ab2bdb9` diff across the model, migration,
    fixtures, all 38 new tests, data-model documentation, roadmap, and handoff rotation.
  - Confirmed model and migration agree on nullability, types, normalization and
    non-empty checks, coordinate ranges, the both-or-neither coordinate invariant,
    non-negative radius override, timestamps, foreign-key cascade, and the functional
    unique index.
  - `ruff format --check .`: passed (33 files already formatted).
  - `ruff check .`: passed.
  - `mypy app tests`: passed (24 source files).
  - `pytest -v`: 206 passed, 0 skipped.
  - Independently ran `0008 -> 0007 -> 0008`: passed.
  - Independently rebuilt the disposable test database via `base -> head`: passed.
  - `alembic check` at test-database head: no new upgrade operations detected.
  - Live-schema inspection confirmed all six named checks, the `ON DELETE CASCADE`
    foreign key, and unique `(saved_search_id, lower(location_text))` index. The test
    database was at `0008` with zero location rows; development remained untouched at
    `0006`.
- Findings, ordered by severity, with file and line references:
  1. **Low — the constraints summary retains the obsolete location-index row.**
     `docs/DATA_MODEL.md:912` correctly documents the implemented
     `(saved_search_id, lower(location_text))` index and all approved checks, but
     `docs/DATA_MODEL.md:913` immediately repeats `saved_search_locations` with the
     superseded `(saved_search_id, lower(trim(location_text)))` formula. This leaves
     the authoritative summary internally contradictory even though the detailed
     section, model, migration, tests, and live schema are correct. Remove only the
     obsolete second row.
- Missing or inconclusive verification: none material. Docker process listing was
  unavailable to the sandbox, but every database-backed test, migration operation,
  Alembic comparison, and direct live-schema query connected to PostgreSQL successfully.
- Architecture/documentation consistency: implementation and detailed documentation
  match the nine approved decisions; only the stale duplicate summary row above is
  inconsistent.
- Verdict: changes requested (documentation-only).
- Exact requested corrections:
  1. Delete the obsolete `saved_search_locations` constraints-summary row containing
     `lower(trim(location_text))` from `docs/DATA_MODEL.md`; retain the complete Rev 11
     row containing `lower(location_text)`.
  2. Verify with `git diff --check` and a repository search that only one
     `saved_search_locations` constraints-summary row remains and that no current
     documentation presents `lower(trim(location_text))` as the implemented formula.
     Rotate/update only the handoff `Work done`, commit and push this documentation-only
     correction on the same branch, and stop. Backend checks do not need to be rerun
     because no executable or migration file should change.
  3. Do not begin `companies`, modify or merge `main`, or expand this correction pass.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

### Work done

- Date and agent: 2026-08-26, Claude Code (Sonnet 5).
- Approved phase/slice: documentation-only correction pass over the
  `saved_search_locations` slice — the single finding requested in the previous
  iteration's `Work review` approved as one pass. No `companies`, no other table.
- Outcome: the finding addressed. No backend tests rerun, per explicit instruction
  (no executable or migration file changed).
- Base/starting commit: `ab2bdb9` (`feat(phase-1): implement saved search locations
  slice`) on branch `phase-1/saved-search-locations`, with Codex's review commit
  `dfa6adb` (`docs(review): request saved search location doc correction`) on top.
  Confirmed via `git log --oneline` and `git status` (clean, up to date with origin)
  before making any changes.
- Ending commit or working-tree state: this commit (recorded by the agent completing
  this pass; see the agent's final response for the actual resolved hash, per this
  file's own "Git workflow" instructions above).
- Root cause: `docs/DATA_MODEL.md`'s "Phase 1 constraints & indexes" summary table
  contained two rows for `saved_search_locations` — the correct, complete Rev 11 row
  (`lower(location_text)`, all six `CHECK`s) immediately followed by a pre-existing,
  now-obsolete row using the superseded `lower(trim(location_text))` formula. The
  previous implementation pass added the correct row but did not notice or remove the
  older one already present in the file.
- Files changed:
  - `docs/DATA_MODEL.md` — deleted the obsolete second `saved_search_locations` row
    (`UNIQUE (saved_search_id, lower(trim(location_text)))` | "one entry per location
    text per search"); the complete Rev 11 row is now the only
    `saved_search_locations` row in the summary table. No other line changed.
  - `docs/LLM_HANDOFF.md` — this rotation (old Iteration 1 — the focused
    `saved_search_titles` test correction pass — removed; prior Iteration 2 renumbered
    to Iteration 1; this entry appended as the new Iteration 2).
  - No executable, model, migration, or test file changed, per explicit instruction.
- Migration revisions: none. `0001`–`0008` unchanged.
- Commands run and exact results:
  - `git diff --check` → no output (no whitespace errors, no conflict markers).
  - Repository search: `grep -n "^| \`saved_search_locations\`" docs/DATA_MODEL.md` →
    exactly one match (the complete Rev 11 row).
  - Repository search: `grep -rn "lower(trim(location_text))"` across the repository →
    matches only in (a) `backend/migrations/versions/0008_saved_search_locations.py`'s
    own docstring, which explains the implemented index is *not* this formula
    (contrasting it, not presenting it as current); (b) `docs/DATA_MODEL.md`'s Rev 11
    note, which likewise contrasts it explicitly ("not `lower(trim(location_text))` as
    an earlier revision... implied"); (c) Codex's own `Work review` text above,
    historical record of the finding itself, which is not rewritten. No location
    presents the superseded formula as the current implementation.
  - Backend tests, `ruff`, `mypy`, and Alembic migration checks were **not** rerun, per
    explicit instruction — no executable or migration file was changed by this pass.
- Risks exercised from `PHASE_RISK_CHECKLIST.md`: none specific to this pass — a
  documentation-only correction with no schema or code change.
- Skipped or unavailable verification: backend test suite, `ruff`/`mypy`, and Alembic
  round-trip/`alembic check` were deliberately not rerun, per the review's own
  instruction that they aren't needed since no executable or migration file changed.
- Deviations and ADR impact: none. No ADR impact — documentation-only correction.
- Known limitations: none new, beyond what Iteration 1 already documented.
- Recommended next smallest slice: none proposed by the implementing agent — per the
  workflow, this pass stops for Codex's review before any further slice is considered.
- STOP — awaiting Codex review and user approval. Do not begin `companies` or alter
  `main`.

### Work review

- Date and reviewing agent: 2026-08-26, Codex.
- Diff/revision reviewed: documentation correction commit `02be34f` against review
  commit `dfa6adb` on `phase-1/saved-search-locations`; branch clean and synchronized
  with origin before this review entry.
- Verification performed:
  - Inspected the complete diff: the only product-document change deletes the obsolete
    `saved_search_locations` constraints-summary row from `docs/DATA_MODEL.md`.
  - `git diff --check dfa6adb..02be34f`: passed.
  - Repository search confirms exactly one current `saved_search_locations` summary
    row remains. Other mentions of `lower(trim(location_text))` explicitly identify it
    as superseded or occur in historical review narration.
  - Backend and migration checks were correctly not repeated for this documentation-
    only correction; the implementation verification from the preceding review remains
    applicable.
- Findings: none.
- Missing or inconclusive verification: none for this correction.
- Architecture/documentation consistency: restored; the detailed section, constraints
  summary, model, migration, tests, and live schema now agree.
- Verdict: approved.
- Exact requested corrections: none. The `saved_search_locations` slice is accepted.
  Do not begin `companies` or merge/modify `main` until the user explicitly authorizes
  the next action.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.
