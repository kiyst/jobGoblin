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
final tooling checker correction pass, its approval, and the merge record) was removed
rather than kept alongside a third entry, since this entry's `Work review` (below)
requested changes that are being addressed in this rotation's Iteration 2. Nothing below
was rewritten — only renumbered.*

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

- Date/reviewer: 2026-08-28, Codex. Implementation diff reviewed:
  `a8d7456..80c595e` on `phase-1/companies`; working tree clean before this review.
- Independent verification:
  - Inspected the domain normalizer, model/migration parity, generated-column expression,
    self-referential FK and cleanup helpers, concurrency test, dependency declaration,
    and product-document updates.
  - `python scripts/check_repo.py`: exit 0, zero findings.
  - `ruff format --check .`, `ruff check .`: passed (41 files).
  - `mypy app tests scripts`: passed (31 source files).
  - `pytest tests/test_companies.py -q`: 69 passed.
  - `pytest -q --basetemp=.pytest_cache/codex_companies_review`: 309 passed. The first
    full-suite invocation used pytest's default Windows temp root and produced eight
    setup errors because that external directory was inaccessible to the reviewer
    account; rerunning with the repository-owned ignored temp root passed completely.
  - Direct adversarial calls reproduced the canonicalization bypasses below.
- Findings:
  1. **High — structural hostname checks run before UTS #46 mapping, allowing identity
     and IP-rejection bypasses.** `backend/app/normalization/company.py:83-101` strips
     ASCII `www.`/`.` and rejects IP literals *before* `idna.encode(..., uts46=True)`.
     UTS #46 can itself map separator and digit characters into those ASCII forms, so
     the post-mapping value is never checked against the approved invariants. Reproduced:
     `www\u3002acme.com -> www.acme.com` (does not collide with `acme.com`),
     `acme.com\u3002 -> acme.com.` (retains a root separator), and
     `\uff11\uff12\uff17.\uff10.\uff10.\uff11 -> 127.0.0.1` (a mapped IP literal is
     accepted). Separately, `acme.com.. -> acme.com.` because one dot is removed before
     IDNA sees the remaining empty/root label. These outcomes contradict the documented
     one-`www`/one-root-dot canonicalization, empty-label rejection, and IP-literal
     rejection, and they create distinct unique-index keys for equivalent identities.
- Missing/inconclusive checks: the reviewer did not repeat the already-recorded Docker
  image build or Alembic mutation sequence; Docker access is unavailable to this
  execution account. The committed migration evidence plus model/migration inspection,
  checker/static checks, all 69 targeted tests, and all 309 tests were conclusive for
  everything except the finding above.
- Verdict: changes requested (one bounded normalization/test correction).
- Exact bounded correction:
  1. Reorder/refactor `normalize_domain()` so IDNA/UTS #46 produces the canonical ASCII
     hostname before final structural canonicalization and validation. Strip exactly one
     leading `www.` and one permitted root-label dot from that canonical form, then
     re-check non-empty labels/multi-label shape and reject IP literals on the final
     stored value. A doubled trailing separator must return `None`, not leave one behind.
  2. Add regression tests for an ASCII doubled trailing dot, U+3002/U+FF0E separator
     variants affecting leading `www` and the trailing root dot, and UTS-46-mapped
     full-width digits producing an IPv4 literal. Prove equivalent `www`/root-dot inputs
     converge and mapped IPs return `None`.
  3. Update implementation/doc wording only where needed to state that final structural
     validation occurs after UTS #46 mapping. Do not change migration `0009` unless
     `alembic check` demonstrates actual schema drift.
  4. Rerun the repository checker, Ruff, mypy, targeted company tests, full suite,
     migration round-trip/`alembic check` against `jobgoblin_test`, and confirm the
     development database remains untouched. Commit/push the same branch and stop.
  5. Do not begin `jobs`, implement reconciliation, add CI, merge/modify `main`, or expand
     the normalization contract beyond this canonical-form validation fix.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

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
