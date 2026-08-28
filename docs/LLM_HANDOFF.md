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
`companies` normalization correction pass, its approval, and the merge record) was
removed rather than kept alongside a third entry, since this entry's `Work review` and
merge record (below) mean it is no longer pending either. Nothing below was rewritten —
only renumbered.*

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

---

## Iteration 2

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `job_occurrences`,
  Class H per docs/LLM_WORKFLOW.md — this is the table the project's deterministic
  identity-resolution scheme (ADR 0004) is built on; its three partial unique indexes
  are the scoped identity signals ADR 0004 defines. Base `04fce4a` on `main` -> branch
  `phase-1/job-occurrences`.
- Outcome: new URL-normalization module, model, migration `0011`, factory/real-commit
  helpers, and 125 new tests implemented and verified against real PostgreSQL.
  - `app/normalization/url.py::normalize_url()` (new): a narrowly scoped, pure,
    schema-bound identity canonicalizer (docs/PHASE_RISK_CHECKLIST.md's Phase 1
    clarification added this slice — schema-bound identity canonicalizers like this
    and `normalize_domain()` are in scope; content normalization remains Phase 3).
    Deliberately not built on `normalize_domain()`: retains `www.`, accepts IP-literal
    hosts. Accepts only absolute `http`/`https` URLs with a hostname and no userinfo;
    rejects relative/protocol-relative/invalid-port input by returning `None`, never
    raising. IDNA/UTS #46 host canonicalization, default-port stripping, root/trailing
    -slash path normalization (case preserved), and a tracking-parameter deny-list
    (case-insensitive `utm_*` prefix plus nine exact names) with an empty
    per-`(provider, source)` allow-list hook for future evidence-based additions.
  - `JobOccurrence` model: `provider`/`source` are canonical identifiers (ORM
    lowercase+trim, `CHECK` requires already-canonical); `source_tenant_id`/
    `source_job_id`/`requisition_id_raw`/`apply_url`/`canonical_url`/
    `applicant_count_text` stay case-preserving, nullable, NULL-safe `CHECK` pairs;
    `source_url` required, trim-only; `source_url_normalized`/
    `canonical_url_normalized` are **not** auto-derived by the model — application-
    owned, matching Phase 2's future persistence-path responsibility — with a `CHECK`
    that `canonical_url IS NULL` implies `canonical_url_normalized IS NULL`;
    `first_seen_at`/`last_seen_at` NOT NULL, no default, no `onupdate`, `CHECK
    (first_seen_at <= last_seen_at)`; `is_active` NOT NULL `server_default true`.
    Three partial unique indexes implement ADR 0004's scoped natural key exactly
    (tenant-scoped, no-tenant, fallback-URL); three lookup indexes for match-precedence
    and the active-occurrences feed query.
- Files changed:
  - `backend/app/normalization/url.py` (new).
  - `backend/app/db/models/job_occurrence.py` (new); `backend/app/db/models/__init__.py`,
    `backend/app/db/base.py` — registration/docstring.
  - `backend/migrations/versions/0011_job_occurrences.py` (new, `down_revision =
    "0010"`).
  - `backend/tests/conftest.py` — `make_job_occurrence` (requires `job_id`/
    `first_seen_at`/`last_seen_at` explicitly), `real_committed_job_occurrence`.
  - `backend/tests/test_job_occurrences.py` (new) — 125 tests: `normalize_url()`
    adversarially (Unicode/punycode host equivalence, Unicode separator variants,
    default/non-default ports, IPv4/bracketed-IPv6, credentials/malformed-port/
    protocol-relative/relative rejection, fragment removal, root/trailing-path
    equivalence, path-case preservation, repeated/blank query values, case-insensitive
    exact and arbitrary-`utm_*` tracking-param stripping, deterministic sort, empty-
    query omission); the complete unique-index partition matrix (9 scenarios, including
    the exact ADR-0004 NULL-tenant loophole and the null/null fallback-key
    non-collision); two real concurrent-insert races (no-tenant key, fallback-URL key)
    each proving exactly one winner with failure-safe cleanup; `ON DELETE CASCADE`
    isolation between two jobs' occurrences; the `is_active` default proven via a raw
    SQL insert that omits the column; canonical-identifier/case-preserving/normalized-
    URL text handling; and timestamps/test isolation.
  - `docs/PHASE_RISK_CHECKLIST.md` — clarified that Phase 1 may contain narrowly scoped,
    pure, schema-bound identity canonicalizers (company-domain, occurrence-URL), while
    content normalization (title/salary/location/skill/etc.) remains excluded until
    Phase 3.
  - `docs/DATA_MODEL.md` — `job_occurrences` marked **Implemented**; added "Rev 15" note
    recording `normalize_url()`, the application-owned (not database-derived) normalized
    URL columns, canonical `provider`/`source` identifiers, and the explicit-
    observation-time decisions; added the `job_occurrences` constraints-summary row.
  - `docs/ROADMAP.md` — Phase 1 status line describes the `job_occurrences` slice as
    complete.
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `ruff format --check .`, `ruff check .` → passed (48 files).
  - `mypy app tests scripts` → success, 36 source files.
  - `pytest tests/test_job_occurrences.py -q` → 125 passed.
  - `pytest -q` (full suite) → 638 passed.
  - `DATABASE_URL=...jobgoblin_test`: `alembic upgrade head` (`0010 -> 0011`, existing
    head), `downgrade 0010` / `upgrade head` (round-trip), `downgrade base` / `upgrade
    head` (fresh `base -> head`), `alembic check` (`No new upgrade operations detected`
    — same informational `Computed`-column `UserWarning` as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`pg_indexes`, `pg_constraint`) — confirmed all
    three partial unique indexes' exact `WHERE` clauses, three lookup indexes, and the
    `job_id` FK/PK.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Deviations/known limitations: none. `raw_job_ingestions`, `identity_conflicts`,
  `duplicate_groups`, and the actual match-precedence application logic remain
  unimplemented, per explicit scope — ADR 0004/ARCHITECTURE.md §8's end-to-end
  idempotent re-observation requirement is deferred to Phase 2, since it needs the
  persistence path, not merely this table.
- STOP — awaiting Codex review. Do not begin any later table, ingestion, providers,
  normalization, reconciliation, add CI, or modify `main`.

### Work review

*Pending — awaiting Codex.*
