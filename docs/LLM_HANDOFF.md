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
`companies` implementation pass and Codex's first review requesting the normalization
correction) was removed rather than kept alongside a third entry, since this entry's
`Work review` and merge record (below) mean it is no longer pending either. Nothing
below was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: bounded correction
  pass addressing the sole finding at review commit `7bd27a7`, on the same
  `phase-1/companies` branch. Base: `7bd27a7`. No `jobs`, reconciliation, CI, or `main`
  changes.
- Outcome: `normalize_domain()`'s structural checks (`www.`/trailing-dot strip,
  IP-literal rejection, multi-label check) now run on the canonical, post-IDNA/UTS #46
  value, not the raw pre-mapping input — closing the exact bypasses the review
  reproduced. Reordered `app/normalization/company.py`: userinfo/port/path/query/
  fragment extraction is unchanged (pure URI-delimiter syntax, no UTS #46 ambiguity),
  but `idna.encode(host, uts46=True, std3_rules=True)` now runs immediately on the
  extracted host, and only the resulting canonical ASCII string is then checked for a
  leading `www.`, a trailing root dot, an IP literal, and multi-label shape. Verified
  behavior-preserving for every previously-passing case (pure-ASCII mapping is an
  identity transform) and confirmed fixed for all four reproduced bypasses.
- Files changed:
  - `backend/app/normalization/company.py` — reordered as above; docstring explains why
    IDNA/UTS #46 must run before the structural checks, with the exact bypass evidence.
  - `backend/tests/test_companies.py` — 6 new regression tests: an ASCII doubled
    trailing dot (`acme.com..`) returning `None`; U+3002 (ideographic full stop) and
    U+FF0E (fullwidth full stop) each proven equivalent to `www.`/a trailing dot for
    both the leading-`www` and trailing-root-dot cases (4 tests); UTS-46-mapped
    fullwidth digits producing an IPv4 literal (`１２７.０.０.１` -> `127.0.0.1`)
    returning `None`.
  - `docs/DATA_MODEL.md` — corrected the domain-normalization algorithm's step order
    (IDNA/UTS #46 conversion now documented as running before the `www.`/trailing-dot/
    IP-literal/multi-label checks, not after); added a "Rev 13" note explaining the bug
    and fix, with the same four reproduced-bypass examples.
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `ruff format --check .`, `ruff check .` → passed (41 files).
  - `mypy app tests scripts` → success, 31 source files.
  - `pytest tests/test_companies.py -v` → 75 passed (69 prior + 6 new).
  - `pytest -q` (full suite) → 315 passed.
  - `DATABASE_URL=...jobgoblin_test`: `alembic downgrade 0008` / `upgrade head`
    (round-trip), `alembic check` (`No new upgrade operations detected` — same
    informational `Computed`-column `UserWarning` as before) — no migration change was
    needed or made, since this was a pure application-layer normalization bug.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged.
  - `git status`/`git diff --check` → only `backend/app/normalization/company.py`,
    `backend/tests/test_companies.py`, and `docs/DATA_MODEL.md` changed; no whitespace/
    conflict errors.
- Deviations/known limitations: none. Migration `0009` was not touched — no schema drift
  was found or expected, per the review's own condition for touching it.
- STOP — awaiting Codex review. Do not begin `jobs`, implement reconciliation, add CI, or
  modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Correction diff reviewed:
  `7bd27a7..8917bcd` on `phase-1/companies`; working tree clean and synchronized with
  origin before this review entry.
- Independent verification:
  - Inspected the reordered IDNA/UTS #46 canonicalization, all six regression tests,
    and the corrected DATA_MODEL algorithm. Final `www.`/root-dot stripping,
    multi-label validation, and IP-literal rejection now operate on the canonical ASCII
    hostname, closing the reviewed identity bypass without altering migration `0009`.
  - `python scripts/check_repo.py`: exit 0, zero findings.
  - `ruff format --check .`, `ruff check .`: passed (41 files).
  - `mypy app tests scripts`: passed (31 source files).
  - `pytest tests/test_companies.py -q`: 75 passed.
  - `pytest -q --basetemp=.pytest_cache/codex_companies_rereview`: 315 passed.
  - Direct adversarial probes confirmed U+3002 separator variants converge correctly,
    full-width/mixed-separator IPv4 forms return `None`, doubled trailing dots return
    `None`, and `www.127.0.0.1`/`www.local` cannot evade the final checks.
- Findings: none.
- Missing/inconclusive checks: the reviewer did not repeat the migration mutation or
  Docker image build because this correction changed no dependency, model, or migration;
  Claude's recorded test-database round-trip and `alembic check` passed with development
  remaining at `0006`.
- Verdict: approved.
- Exact requested corrections: none. The `companies` slice and its normalization
  correction are accepted. Do not begin `jobs`, implement reconciliation, add CI, or
  merge/modify `main` until the user explicitly authorizes the next action.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `dd40c0b`. Per user authorization, `phase-1/companies` was fast-forward merged
into `main` (no merge commit; `main` was a strict ancestor) and pushed. `main`/
`origin/main` are both now at `dd40c0b`. Verified: `main` has zero content diff against
the feature branch; `python backend/scripts/check_repo.py` (via the project's own
virtualenv interpreter) exits 0 with zero findings; working tree clean. No squash/
rebase/force-push/branch-deletion. `jobs` not started.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `jobs`, Class H per
  docs/LLM_WORKFLOW.md (first migration to actually exercise `ON DELETE RESTRICT`; a
  large canonical record with many downstream dependencies, even though identity
  resolution itself is out of scope — that lives entirely on `job_occurrences`, a
  separate, later slice). Base `80c0425` on `main` -> branch `phase-1/jobs`.
- Outcome: model, migration `0010`, factory/real-commit helpers, and 198 new tests
  implemented and verified against real PostgreSQL.
  - `Job` model (~46 columns, no UNIQUE constraint of its own): `company_id` nullable
    FK -> `companies`, `ON DELETE RESTRICT`, plain non-unique index (`DiscoveredJob.
    company` is nullable in ARCHITECTURE.md — requiring one would force ingestion to
    reject a valid job or manufacture a fake company); `remote_type`/`salary_period`
    nullable text with `CHECK`-restricted enums (`'unknown'` sentinel deliberately not
    implemented — `NULL` means unknown); `compensation_explicit` nullable boolean, no
    default; 25 nullable free-text columns sharing one `@validates` handler (trim,
    blank-to-`None`) and a NULL-safe trim/non-empty `CHECK` pair each (generated via a
    small `_trim_not_empty_checks` helper — 50 CHECKs, not hand-duplicated); non-negative
    + min<=max `CHECK`s on the three numeric pairs; `saved_search_locations`-style
    coordinate range/pairing `CHECK`s; `certifications` (`MutableList`-wrapped
    `ARRAY(Text)`) and `field_provenance` (`MutableDict`-wrapped `JSONB`, top-level-object
    `CHECK`); `first_seen_at`/`last_seen_at` NOT NULL with **no** server default plus
    `CHECK (first_seen_at <= last_seen_at)` — they describe observation time, not
    row-creation time, so the factory requires both explicitly, matching the columns.
    `duplicate_group_id` omitted entirely (target table `duplicate_groups` is Phase 6,
    doesn't exist yet — deferred to that phase's own migration, not added unconstrained).
- Files changed:
  - `backend/app/db/models/job.py` (new); `backend/app/db/models/__init__.py`,
    `backend/app/db/base.py` — registration/docstring.
  - `backend/migrations/versions/0010_jobs.py` (new, `down_revision = "0009"`).
  - `backend/tests/conftest.py` — `make_job` (requires `first_seen_at`/`last_seen_at`
    explicitly, no default), `real_committed_job`.
  - `backend/tests/test_jobs.py` (new) — 198 tests, heavily parametrized per instruction
    rather than repetitive bodies: all 25 nullable-text columns (default/blank-to-none/
    trim/direct-SQL empty/direct-SQL wrapped); `remote_type`/`salary_period` valid+NULL
    accepted, invalid rejected (including `'unknown'` explicitly rejected); non-negative
    and min<=max checks across all three numeric pairs; coordinate range/pairing
    (ORM+direct SQL); `field_provenance` NULL/valid-object/non-object-array/string/
    JSON-null rejection, top-level `MutableDict` mutation persisting after reload,
    documented nested-mutation limitation, and the replace-whole-object workaround;
    `certifications` NULL-vs-empty-list and `MutableList` append persisting after
    reload; `company_id` NULL/valid/nonexistent, deleting an unrelated company,
    deleting a referenced company rejected with both rows surviving, deleting the job
    then the company succeeding; `first_seen_at`/`last_seen_at` equal/ordered/inverted
    (ORM + direct SQL); timestamps and test isolation.
  - `docs/DATA_MODEL.md` — `jobs` marked **Implemented**; added "Rev 14" note recording
    the nullable `company_id`, removed `'unknown'` sentinel, nullable
    `compensation_explicit`, deferred `duplicate_group_id`, and explicit-observation-time
    decisions; updated the FK summary rows and added the `jobs` constraints-summary row.
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `ruff format --check .`, `ruff check .` → passed (44 files).
  - `mypy app tests scripts` → success, 33 source files.
  - `pytest tests/test_jobs.py -q` → 198 passed.
  - `pytest -q` (full suite) → 513 passed.
  - `DATABASE_URL=...jobgoblin_test`: `alembic upgrade head` (`0009 -> 0010`, existing
    head), `downgrade 0009` / `upgrade head` (round-trip), `downgrade base` / `upgrade
    head` (fresh `base -> head`), `alembic check` (`No new upgrade operations detected`
    — same informational `Computed`-column `UserWarning` as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`information_schema.columns`, `pg_constraint`,
    `pg_indexes`) — confirmed the FK's `ON DELETE RESTRICT` (`confdeltype = 'r'`) and
    the `company_id` index.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Deviations/known limitations: none. `job_occurrences`, `raw_job_ingestions`,
  `identity_conflicts`, and `duplicate_groups` remain unimplemented, per explicit scope.
- STOP — awaiting Codex review. Do not begin `job_occurrences`, ingestion, providers,
  normalization, reconciliation, add CI, or modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Implementation diff reviewed:
  `80c0425..819c682` on `phase-1/jobs`; branch clean and synchronized with origin before
  the review's documentation-only corrections.
- Independent verification:
  - Manually compared all model and migration columns, nullability, types, server
    defaults, 50 nullable-text CHECKs, enum/range/ordering/coordinate/JSON checks,
    `company_id` FK/index, and downgrade behavior. Model and migration match.
  - Inspected all 198 tests, including separate-session mutable collection proofs and
    real-commit `ON DELETE RESTRICT` failure/recovery/cleanup behavior.
  - `python scripts/check_repo.py`: exit 0, zero findings.
  - `ruff format --check .`, `ruff check .`: passed (44 files).
  - `mypy app tests scripts`: passed (33 source files).
  - `pytest tests/test_jobs.py -q`: 198 passed.
  - `pytest -q --basetemp=.pytest_cache/codex_jobs_review`: 513 passed.
  - `alembic check` against `jobgoblin_test` at `0010 (head)`: no new upgrade
    operations detected; only the known informational warning for the pre-existing
    `companies.normalized_name` computed column appeared.
- Findings:
  1. **Low, mechanical documentation only — phase status and counts were stale.**
     `docs/ROADMAP.md` still ended the `companies` status with "No other Phase 1 table is
     implemented yet," omitting the now-implemented `jobs`/`0010` slice. The `Work done`
     summary also said 24 nullable-text columns/48 generated CHECKs, while the actual
     synchronized tuple contains 25 columns/50 CHECKs. Under
     `docs/LLM_WORKFLOW.md`'s standing mechanical-documentation rule, the reviewer
     updated the roadmap status and corrected only those three numeric references.
- Missing/inconclusive checks: the reviewer did not repeat destructive migration
  downgrade/fresh-rebuild operations; Claude recorded existing-head, round-trip, fresh
  `base -> head`, live-schema inspection, and development-database isolation as passing.
  The reviewer independently confirmed the test database is at `0010` and model/schema
  autogeneration reports no drift.
- Verdict: approved after mechanical documentation corrections; no executable finding.
- Exact requested corrections: none. The `jobs` slice is accepted. Do not begin
  `job_occurrences`, ingestion, providers, normalization, reconciliation, add CI, or
  merge/modify `main` until the user explicitly authorizes the next action.
- STOP — reviewer changed only the mechanical documentation described above and this
  `Work review`; no implementation, migration, test, dependency, or product behavior
  was changed.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `c3f80dd`. Per user authorization, `phase-1/jobs` was fast-forward merged into
`main` (no merge commit; `main` was a strict ancestor) and pushed. `main`/`origin/main`
are both now at `c3f80dd`. Verified: `main` has zero content diff against the feature
branch; `python backend/scripts/check_repo.py` (via the project's own virtualenv
interpreter) exits 0 with zero findings; working tree clean. No squash/rebase/
force-push/branch-deletion. `job_occurrences` not started.
