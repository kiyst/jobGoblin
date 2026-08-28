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
`saved_search_locations` documentation correction pass and its merge record) was
removed rather than kept alongside a third entry, since this entry's `Work review`
(below) requested changes that are being addressed in this rotation's Iteration 2.
Nothing below was rewritten — only renumbered.*

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

---

## Iteration 2

### Work done

- Date/agent: 2026-08-27, Claude Code (Sonnet 5). Authorized slice: bounded correction
  pass addressing review findings 1-4 at commit `d9185fb`, on the same
  `tooling/repository-validation` branch. Base: `d9185fb` (Codex's review). No CI,
  `companies`, migration, or product-behavior changes.
- Outcome: all four findings addressed in `backend/scripts/check_repo.py`.
  1. Added `check_constraints_table_integrity`, run only for `docs/DATA_MODEL.md`:
     reports a finding if the "Phase 1 constraints & indexes" section/table is missing
     or has no data rows, or if it has rows but zero rows yield a parseable UNIQUE/INDEX
     signature — closing the fail-open gap `check_duplicate_constraint_rows` had.
  2. Widened `_BARE_REVISION_RE` from `` `(000\d)` `` to `` `(0\d{3})` ``, so revisions
     `0010` and later are inspected (still requires the leading-zero, four-digit,
     backtick-delimited shape, so years/ports are not misdetected).
  3. `_chain_integrity_findings` now also detects: a non-null parent that doesn't exist
     in the revision set; a merge/tuple `down_revision` (rejected outright — this
     project requires one unbranched chain); and disconnected components, by walking
     parent links from the sole head and flagging any revision never reached.
     `check_migration_chain_integrity` catches Alembic's own `CommandError` and returns
     it as a normal `Finding` instead of an uncontrolled traceback.
  4. Added `_display_path`: renders a finding's path repository-relative
     (`docs/DATA_MODEL.md`, `backend/migrations`) when the path exists on disk inside
     the repo, forward-slash-normalized for cross-platform determinism; falls back to
     the given path unchanged for synthetic/nonexistent paths used by unit tests.
     Applied at every `Finding(...)` call site.
- Files changed:
  - `backend/scripts/check_repo.py` — the four fixes above; module docstring updated to
    describe the hardened guarantees.
  - `backend/tests/test_check_repo.py` — 11 new tests: missing constraints-summary
    section, a section with rows but no extractable signatures (plus one confirming a
    valid section is *not* flagged), existing/nonexistent revisions at `0010`+, missing
    migration parent, disconnected migration graph (a `0004`/`0005` cycle unreachable
    from the head, invisible to the pre-existing head/base/shared-down-revision checks),
    rejection of a tuple/merge parent, and three path-relativity tests (`_display_path`
    on a real file, on a synthetic nonexistent path, and end-to-end through
    `check_links_and_anchors` against the real `README.md`).
- Commands run and exact results:
  - `python scripts/check_repo.py` from `backend/` → exit 0, zero findings.
  - Same script invoked from an unrelated working directory (outside the repo) → exit 0.
  - `ruff format --check .` → 36 files already formatted (after one `ruff format .` pass
    to apply its own reflow of a multi-line `assert any(...)`).
  - `ruff check .` → all checks passed.
  - `mypy app tests scripts` → success, 27 source files.
  - `pytest tests/test_check_repo.py -v` → 33 passed (22 prior + 11 new).
  - `pytest -q` (full suite) → 239 passed.
  - `git status`/`git diff --check` → only `backend/scripts/check_repo.py` and
    `backend/tests/test_check_repo.py` changed; no whitespace/conflict errors.
- Deviations/known limitations: none. README/workflow text was not changed — no
  invocation or behavior wording needed correction, per the bounded scope.
- STOP — awaiting Codex review. Do not add CI, begin `companies`, modify migrations, or
  alter product behavior.

### Work review

*Pending — awaiting Codex.*
