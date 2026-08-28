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

*Rotated in from "Iteration 2" per the two-iteration rule: both this entry's and the
prior Iteration 1's `Work review` are no longer pending (both approved, both already
merged to `main`), so the prior Iteration 1 (the `saved_search_locations` implementation
pass and Codex's first review requesting the doc correction) was removed rather than
kept alongside a third entry. Nothing below was rewritten — only renumbered.*

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
- Ending commit: `02be34f` (`docs(phase-1): remove obsolete saved_search_locations
  constraints row`).
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
  - No executable, model, migration, or test file changed, per explicit instruction.
- Migration revisions: none. `0001`–`0008` unchanged.
- Commands run and exact results:
  - `git diff --check` → no output (no whitespace errors, no conflict markers).
  - Repository search: `grep -n "^| \`saved_search_locations\`" docs/DATA_MODEL.md` →
    exactly one match (the complete Rev 11 row).
  - Repository search: `grep -rn "lower(trim(location_text))"` across the repository →
    matches only in (a) the migration's own docstring, contrasting it with the
    implemented formula; (b) `docs/DATA_MODEL.md`'s Rev 11 note, likewise contrasting
    it explicitly; (c) Codex's own historical `Work review` narration. No location
    presents the superseded formula as the current implementation.
  - Backend tests, `ruff`, `mypy`, and Alembic migration checks were **not** rerun, per
    explicit instruction — no executable or migration file was changed by this pass.
- Deviations and ADR impact: none. No ADR impact — documentation-only correction.
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
- Verdict: approved.
- Exact requested corrections: none. The `saved_search_locations` slice is accepted.
  Do not begin `companies` or merge/modify `main` until the user explicitly authorizes
  the next action.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `05be8dc`. Per user authorization, `phase-1/saved-search-locations` was
fast-forward merged into `main` (no merge commit; `main` was a strict ancestor) and
pushed. `main`/`origin/main` are both now at `0f4da2c`, which also carries the
`LLM_WORKFLOW.md` v2 process update. Verified: `main` has zero content diff against the
feature branch; migration head is `0008` (`alembic heads`, file-based, no DB
connection); working tree clean. Full backend suite intentionally not rerun — pure
fast-forward of an already-verified tree. Development database not touched. No
squash/rebase/force-push/branch-deletion. `companies` not started.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-27, Claude Code (Sonnet 5). Authorized slice: repository-
  validation tooling, Class R. Base `a47a8f1` on `main` -> branch
  `tooling/repository-validation`.
- Outcome: added `backend/scripts/check_repo.py`, a deterministic, offline, database-
  free checker covering (1) markdown link/heading-anchor validation, (2) duplicate
  `docs/DATA_MODEL.md` constraints-summary rows detected by per-row UNIQUE/INDEX
  *signature* comparison (not whole-row or flattened-CHECK-column comparison — the
  user's explicit correction to the original proposal), (3) stale/nonexistent Alembic
  revision references in product docs, (4) migration-chain integrity via Alembic's own
  `ScriptDirectory` (no DB connection). `docs/LLM_HANDOFF.md` is excluded from checks
  2-3 (rotating ledger preserves superseded wording on purpose) but still covered by
  check 1.
- Conventions applied: `Path(__file__).resolve()`-based path resolution (mirrors
  `app/config.py`'s `REPOSITORY_ROOT`), reusing the existing `alembic` dependency
  instead of hand-parsing migration files, no new dependency, no console-script entry,
  no CI wiring (all per explicit instruction).
- Files changed:
  - `backend/scripts/__init__.py` (new, empty) — makes `scripts` importable.
  - `backend/scripts/check_repo.py` (new) — the checker; `main()` prints sorted
    `path:line: message` findings, exit 1 if any.
  - `backend/tests/test_check_repo.py` (new) — 22 tests: link/anchor validation
    (missing target, missing anchor, image targets, fenced/inline code exclusion,
    GitHub slug-algorithm parity), duplicate-row detection (signature match after
    `lower(...)`/`trim(...)` normalization, distinct columns not flagged, exact-
    duplicate fallback for CHECK-only rows, partial-vs-plain UNIQUE not confused,
    differing `WHERE` not a duplicate, and the explicit `saved_search_locations`
    Rev 11 regression case), Alembic reference checks, pure `_chain_integrity_findings`
    unit tests (clean chain, forked chain), a real-repository integration test
    (`run_checks()` against the actual repo), and a subprocess CWD-independence test.
  - `README.md` — documented `python scripts/check_repo.py` under a new "Repository
    consistency checker" section; `mypy` invocation updated to include `scripts`.
  - `docs/LLM_WORKFLOW.md` — verification matrix's "Mechanical docs only" and "Model or
    migration" rows now require `python scripts/check_repo.py`.
- One correction made during self-verification (not by Codex): the first
  implementation's `_UNIQUE_OR_INDEX_RE` used a `[^)]*` character class that cannot
  skip past the inner `)` of a wrapped column like `lower(location_text)`, so it never
  matched any wrapped-column constraint and silently produced zero signatures —
  caught because the two tests requiring an actual signature match failed (0 findings
  instead of 1), even though the real-repository integration test still passed
  trivially (asserts zero findings, which is also true when extraction silently no-ops).
  Fixed by replacing the regex with a depth-tracking balanced-paren scan
  (`_match_unique_or_index`) plus a top-level-comma splitter
  (`_split_top_level_commas`); one test's expected line number was also corrected (the
  duplicate is reported at the second/duplicate row's own line, not the first row's).
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `pytest tests/test_check_repo.py -v` → 22 passed.
  - `pytest -q` (full suite) → 228 passed.
  - `ruff format --check .` → 36 files already formatted.
  - `ruff check .` → all checks passed.
  - `mypy app tests scripts` → success, 27 source files.
  - Subprocess invocation from an unrelated `tmp_path`-style directory outside
    `backend/` → exit 0 (proves path resolution is CWD-independent).
  - `git diff --check` (after doc edits) → no output.
- Deviations/known limitations: none beyond the one corrected bug above, fixed before
  this entry was written. No CI wiring, no `companies` work, no migration changes, no
  product-behavior changes.
- STOP — awaiting Codex review. Do not add CI, begin `companies`, modify migrations, or
  alter product behavior.

### Work review

- Date/reviewer: 2026-08-27, Codex. Diff reviewed: `a47a8f1..3290b31` on
  `tooling/repository-validation`; branch clean and synchronized with origin before
  this review entry.
- Independent verification:
  - Inspected the full checker, all 22 tests, README/workflow integration, and handoff
    rotation. The balanced-parenthesis UNIQUE/INDEX parser correctly handles nested
    `lower(trim(...))` expressions and catches the saved-location regression.
  - `python scripts/check_repo.py`: exit 0, zero findings.
  - `ruff format --check .`, `ruff check .`: passed (36 files).
  - `mypy app tests scripts`: passed (27 source files).
  - `pytest -q` with a reviewer-writable temporary root: 228 passed.
  - Direct counterexamples confirmed the findings below: a documented `0010` revision
    and an orphaned revision parent both currently return no finding.
- Findings:
  1. **Medium — duplicate-summary validation still fails open if its target table is
     missing or no signatures can be parsed.** `backend/scripts/check_repo.py:242-292`
     returns an empty result when the named heading/table disappears, its Markdown
     shape changes, or UNIQUE/INDEX extraction silently produces zero signatures;
     `run_checks()` at `backend/scripts/check_repo.py:458-480` treats that as success.
     Consequently the real-repository integration test can still pass trivially under
     the same no-op failure mode described in this pass's own Work done. Make the
     DATA_MODEL check require exactly one target section with data rows and at least
     one parsed UNIQUE/INDEX signature, reporting a finding otherwise. Add regression
     tests for a missing section and an unparseable/no-signature section.
  2. **Medium — revision-reference detection stops after migration `0009`.**
     `backend/scripts/check_repo.py:345` uses ``r"`(000\d)`"``, so a current or future
     citation such as migration `0010` is never inspected. A direct call with `0010`
     in both the text and revision map returned no finding only because the regex did
     not match. Support the project's four-digit, leading-zero revision convention
     (for example `0\d{3}` in the existing backtick context) and add known/nonexistent
     `0010`-or-later tests without turning ordinary years or ports into revisions.
  3. **Medium — migration-chain validation does not prove parent existence or graph
     connectivity.** `backend/scripts/check_repo.py:396-435` checks head/base counts
     and shared `down_revision` values, but never verifies that every non-null parent
     exists or that walking from the sole head visits every revision. The synthetic
     chain `0001 -> NULL`, `0002 -> 9999`, `0003 -> 0002` with head `0003` returns no
     findings. Add missing-parent and full-connectivity validation (including tests for
     an orphan/disconnected component; reject tuple/merge parents because this project
     requires one unbranched chain). Convert Alembic graph-loading failures into a
     normal sorted finding instead of an uncontrolled traceback where practical.
  4. **Low — CLI finding paths are checkout-dependent absolute paths.** Production
     checks construct findings with `str(path)` and `str(MIGRATIONS_DIR)` throughout
     `backend/scripts/check_repo.py`, so identical defects produce different output on
     different machines despite the checker being described as deterministic. Render
     repository files relative to `REPO_ROOT` (for example `docs/DATA_MODEL.md` and
     `backend/migrations`) while leaving synthetic external paths usable in unit tests.
- Missing/inconclusive checks: Docker/database state is irrelevant to this offline
  tooling slice. The initial targeted reviewer run hit sandbox-owned pytest temp-folder
  permissions; rerunning the complete suite with an explicitly writable temp root
  passed 228/228, confirming this was environmental rather than a repository failure.
- Verdict: changes requested.
- Exact bounded correction:
  1. Address only findings 1-4 in the checker and its tests. Update README/workflow text
     only if behavior or invocation wording needs correction; do not expand categories.
  2. Add focused tests proving fail-closed constraints-table discovery/extraction,
     `0010`-or-later revision handling, orphan/connectivity rejection, and stable
     repository-relative CLI paths.
  3. Rerun the checker from `backend` and an unrelated CWD, Ruff format/check, mypy over
     `app tests scripts`, targeted checker tests, and the full suite. Record exact
     outcomes concisely, commit/push the same tooling branch, and stop.
  4. Do not add CI, begin `companies`, modify migrations, or alter product behavior.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.
