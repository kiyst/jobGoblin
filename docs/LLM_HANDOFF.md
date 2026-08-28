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
initial checker implementation and Codex's first review requesting findings 1-4) was
removed rather than kept alongside a third entry, since this entry's `Work review`
(below) requested one further change that is being addressed in this rotation's
Iteration 2. Nothing below was rewritten — only renumbered.*

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

- Date/reviewer: 2026-08-27, Codex. Correction diff reviewed:
  `d9185fb..5bd70ec` on `tooling/repository-validation`; branch clean and synchronized
  with origin before this review entry.
- Independent verification:
  - Inspected every correction and new test. Findings 1, 2, and 4 are resolved; the
    missing-parent, reachability, and merge-parent logic requested in finding 3 is also
    correct.
  - `python scripts/check_repo.py`: exit 0, zero findings.
  - `ruff format --check .`, `ruff check .`: passed (36 files).
  - `mypy app tests scripts`: passed (27 source files).
  - `pytest -q` with a reviewer-writable temporary root: 239 passed.
  - Directly injected a `CommandError` into the initial revision walk and confirmed it
    still escapes uncaught before the new graph-integrity handler runs.
- Findings:
  1. **Medium — Alembic graph-load errors can still bypass the normal-finding handler.**
     `backend/scripts/check_repo.py:557-575` catches `CommandError` while
     `check_migration_chain_integrity()` calls `get_heads()`/`walk_revisions()`, but
     `run_checks()` first calls `_revision_map(script)` at
     `backend/scripts/check_repo.py:597`; `_revision_map()` performs its own
     `walk_revisions()` at `backend/scripts/check_repo.py:420-426` outside that handler.
     A malformed/missing-parent graph can therefore raise during revision-map creation
     and terminate with a traceback before `check_migration_chain_integrity()` is ever
     reached. A direct injected `CommandError("broken graph")` reproduced the uncaught
     path. Load/walk the graph once under one handler (or catch the earlier traversal),
     return a repository-relative normal `Finding`, and avoid continuing revision-
     citation checks when no valid revision map exists.
- Missing/inconclusive checks: none. The checker is database-free; the full existing
  suite passed against the configured environment.
- Verdict: changes requested (one narrow executable correction).
- Exact bounded correction:
  1. Make the first Alembic graph traversal in the production `run_checks()` path
     convert `CommandError` into the same sorted `backend/migrations:1: ...` finding;
     do not traverse the graph once outside and again inside separate error handling.
  2. Add a test at the `run_checks()`/orchestration boundary—not only the pure helper—
     that injects a graph-load `CommandError`, asserts no exception escapes, and asserts
     one normal repository-relative finding/nonzero CLI outcome.
  3. Rerun checker from two CWDs, Ruff, mypy, targeted checker tests, and the full suite;
     update the concise handoff entry, commit/push the same branch, and stop.
  4. Do not add CI, begin `companies`, modify migrations, or alter product behavior.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-27, Claude Code (Sonnet 5). Authorized slice: bounded correction
  pass addressing the sole remaining finding at review commit `5934d1c`, on the same
  `tooling/repository-validation` branch. Base: `5934d1c`. No CI, `companies`,
  migration, or product-behavior changes.
- Outcome: the migration graph is now walked exactly once in the production path, under
  one `CommandError` boundary.
  - Added `MigrationGraph` (a frozen dataclass of `heads`/`revisions`) and
    `_load_migration_graph(script) -> MigrationGraph | Finding`: the single place that
    calls `script.get_heads()`/`script.walk_revisions()`; a `CommandError` there returns
    one `Finding` at `backend/migrations:1` instead of propagating.
  - `_revision_map` now takes a `MigrationGraph` (derives the citation map from the
    already-walked `revisions`, no second walk); `check_migration_chain_integrity` now
    takes a `MigrationGraph` too (pure structural checks only — no longer does its own
    try/except, since loading already happened once upstream).
  - `run_checks()` calls `_load_migration_graph` once; on failure it appends that one
    finding, skips `check_alembic_references` entirely for every file (no valid revision
    map exists to check citations against), still runs the graph-independent checks
    (links/anchors, duplicate-summary rows, constraints-table integrity), and skips
    `check_migration_chain_integrity` (nothing further to say about a graph that failed
    to load).
- Files changed:
  - `backend/scripts/check_repo.py` — the single-load refactor above; module docstring
    updated to describe it.
  - `backend/tests/test_check_repo.py` — added
    `test_run_checks_and_cli_survive_a_migration_graph_load_failure`: monkeypatches
    `_script_directory` to return a stub whose `walk_revisions()` raises `CommandError`,
    then asserts `run_checks()` returns exactly one `backend/migrations:1: ...` finding
    (no exception escapes) and that `main()` returns exit code `1`.
- Commands run and exact results:
  - `python scripts/check_repo.py` from `backend/` → exit 0, zero findings.
  - Same script invoked from an unrelated working directory → exit 0.
  - `ruff format --check .` → 36 files already formatted.
  - `ruff check .` → all checks passed.
  - `mypy app tests scripts` → success, 27 source files.
  - `pytest tests/test_check_repo.py -v` → 34 passed (33 prior + 1 new).
  - `pytest -q` (full suite) → 240 passed.
  - `git status`/`git diff --check` → only `backend/scripts/check_repo.py` and
    `backend/tests/test_check_repo.py` changed; no whitespace/conflict errors.
- Deviations/known limitations: none.
- STOP — awaiting Codex review. Do not add CI, begin `companies`, modify migrations, or
  alter product behavior.

### Work review

- Date/reviewer: 2026-08-27, Codex. Correction diff reviewed:
  `5934d1c..0dea3e2` on `tooling/repository-validation`; branch clean and synchronized
  with origin before this review entry.
- Independent verification:
  - Inspected the single-load `MigrationGraph` refactor and orchestration-level failure
    test. `get_heads()`/`walk_revisions()` now occur only inside
    `_load_migration_graph()` under one `CommandError` boundary; graph-dependent checks
    are skipped after load failure while independent checks still run.
  - Confirmed the injected failure produces one repository-relative
    `backend/migrations:1: ...` finding and makes `main()` return nonzero without an
    exception escaping.
  - `python scripts/check_repo.py` from `backend`: exit 0, zero findings.
  - Same checker invoked from an unrelated working directory: exit 0, zero findings.
  - `ruff format --check .`, `ruff check .`: passed (36 files).
  - `mypy app tests scripts`: passed (27 source files).
  - `pytest -q` with a reviewer-writable temporary root: 240 passed.
- Findings: none.
- Missing/inconclusive checks: none. This tooling is intentionally offline and
  database-free; no migration or product-runtime file changed.
- Verdict: approved.
- Exact requested corrections: none. The repository-validation tooling slice and its
  correction passes are accepted. Do not add CI, begin `companies`, or merge/modify
  `main` until the user explicitly authorizes the next action.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `fc12091`. Per user authorization, `tooling/repository-validation` was
fast-forward merged into `main` (no merge commit; `main` was a strict ancestor) and
pushed. `main`/`origin/main` are both now at `fc12091`. Verified: `main` has zero
content diff against the feature branch; `python scripts/check_repo.py` from `backend/`
exits 0 with zero findings; working tree clean. No squash/rebase/force-push/branch-
deletion. `companies` not started.
