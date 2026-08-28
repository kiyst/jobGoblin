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
first checker correction pass and Codex's review requesting the single-load fix) was
removed rather than kept alongside a third entry, since this entry's `Work review` and
merge record (below) mean it is no longer pending either. Nothing below was rewritten —
only renumbered.*

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

---

## Iteration 2

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `companies`, Class H
  per docs/LLM_WORKFLOW.md (first self-referential FK, first `ON DELETE SET NULL`, first
  PostgreSQL generated column). Base `a8d7456` on `main` -> branch `phase-1/companies`.
- Outcome: model, domain-normalization module, migration `0009`, factory/real-commit
  helpers, and 69 new tests implemented and verified against real PostgreSQL.
  - `app/normalization/company.py::normalize_domain()`: pure function, trim/lowercase,
    bare-host-or-`scheme://`-URL parsing (custom, not `urlsplit`, which misparses a bare
    `host:port` as scheme+path), strips userinfo/port/path/query/fragment/one leading
    `www.`/one trailing dot, rejects single-label hosts/IP literals/invalid ports/
    missing hosts, converts through `idna.encode(host, uts46=True, std3_rules=True)`.
    Never raises — unparseable input returns `None`.
  - `Company` model: `name` (trim-only `@validates`, matching `CHECK`s);
    `normalized_name` as SQLAlchemy `Computed(..., persisted=True)` — a real PostgreSQL
    `GENERATED ALWAYS AS (...) STORED` column, verified via `information_schema.columns`
    and a direct-SQL insert that omits it entirely; `domain` (`@validates` delegates to
    `normalize_domain()`) with a partial `UNIQUE (lower(domain)) WHERE domain IS NOT
    NULL` index; `duplicate_of_company_id` self-referential FK (`ON DELETE SET NULL`)
    plus a `CHECK` rejecting direct self-reference; `homepage_url`/`career_page_url`/
    `industry` nullable text with NULL-safe normalization `CHECK`s, ORM blank-to-`None`.
  - `idna==3.19` added as a **direct** runtime dependency (`backend/pyproject.toml`,
    BSD-3-Clause, documented consumer/replacement-boundary inline) — not relied on
    transitively; stdlib `str.encode("idna")` only implements IDNA2003 and doesn't
    support UTS #46 validation/mapping (`uts46=True`, `std3_rules=True`).
- Files changed:
  - `backend/app/normalization/__init__.py`, `backend/app/normalization/company.py` (new).
  - `backend/app/db/models/company.py` (new); `backend/app/db/models/__init__.py`,
    `backend/app/db/base.py` — registration/docstring.
  - `backend/migrations/versions/0009_companies.py` (new, `down_revision = "0008"`).
  - `backend/pyproject.toml` — `idna==3.19` direct dependency.
  - `backend/tests/conftest.py` — `make_company`, `real_committed_company`,
    `real_committed_duplicate_company_pair` (two real-committed companies, one
    `duplicate_of` the other, for the `ON DELETE SET NULL` test).
  - `backend/tests/test_companies.py` (new) — 69 tests: every `normalize_domain()` step/
    case (casing/`www`/Unicode-punycode collisions, distinct domains, single-label/IP-
    literal/empty-label/invalid-port/missing-host/oversized/invalid-IDNA -> `None`);
    generated `normalized_name` on insert and name-update (real commit), direct-SQL
    omission proving PostgreSQL generates it, direct-SQL attempt to set it directly
    rejected (`ProgrammingError`, not `IntegrityError` — a `GeneratedAlwaysError`, a
    different condition from a constraint violation); two colliding `normalized_name`s
    accepted; case-insensitive/direct-SQL domain collision, multiple `NULL` domains, a
    real concurrent same-domain insert race (exactly one winner); self-reference and
    nonexistent-target rejection, valid reference accepted, real-commit `ON DELETE SET
    NULL`; nullable-text blank-to-`None` and direct-SQL rejection (parametrized across
    all three columns); timestamps and test isolation.
  - `docs/DATA_MODEL.md` — `companies` marked **Implemented**; added "Rev 12" note;
    corrected the domain-normalization algorithm description to the actual
    IDNA2008/UTS#46 implementation; updated the "Phase 1 constraints & indexes" row.
  - `docs/ROADMAP.md` — Phase 1 status line describes the `companies` slice as complete.
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `ruff format --check .`, `ruff check .` → passed (41 files).
  - `mypy app tests scripts` → success, 31 source files.
  - `pytest tests/test_companies.py -v` → 69 passed.
  - `pytest -q` (full suite) → 309 passed.
  - `DATABASE_URL=...jobgoblin_test`: `alembic upgrade head` (`0008 -> 0009`),
    `downgrade 0008` / `upgrade head` (round-trip), `downgrade base` / `upgrade head`
    (fresh `base -> head`), `alembic check` (`No new upgrade operations detected` — one
    informational `UserWarning` that computed defaults aren't diffable, expected/known
    Alembic limitation for `Computed` columns) — all passed.
  - `alembic current` against the **development** database (no `DATABASE_URL` override)
    → `0006`, unchanged throughout.
  - Live schema inspected directly (`information_schema.columns`, `pg_constraint`,
    `pg_indexes`) — confirmed the generated column, all named checks/FK, and both
    indexes match the model exactly.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
  - `docker compose build backend` → succeeded, `idna-3.19` confirmed installed in the
    image (dependency changed, per instruction).
- Deviations/known limitations: none. `jobs.company_id` (`ON DELETE RESTRICT`) does not
  exist yet — `jobs` isn't implemented; no reconciliation/merge workflow exists or is
  implied by `duplicate_of_company_id`, per explicit scope.
- STOP — awaiting Codex review. Do not begin `jobs`, implement reconciliation, add CI, or
  modify `main`.

### Work review

*Pending — awaiting Codex.*
