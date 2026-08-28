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
`raw_job_ingestions` initial implementation pass and Codex's changes-requested review at
`53a2cad`, requesting the stale Phase-4 wording correction) was removed rather than kept
alongside a third entry — its one finding was addressed in this entry's correction pass,
which Codex then approved and the user merged. Nothing below was rewritten — only
renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: the one bounded
  documentation correction from the review at `53a2cad`, on the same
  `phase-1/raw-job-ingestions` branch. Base: `53a2cad`. Comment/documentation changes
  only — no schema, migration operations/revision metadata, test, or product-behavior
  changes.
- Outcome: all six stale "Phase 4+ ingestion code is the first writer" claims replaced
  with consistent wording: Phase 2's offline fixture pipeline is the first writer/user
  of the raw-ingestion and deterministic-identity persistence path; Phase 4 introduces
  the first live ATS provider that reuses that same path. A seventh, unrelated "Phase
  4+" mention (`docs/DATA_MODEL.md`'s field-provenance-merging passage, about
  `ingestion/persistence.py`'s cross-source merge logic) was left untouched — it is a
  distinct, correctly-scoped claim (no multi-source merge scenario exists before a
  second real provider in Phase 4), not part of the six the review identified.
- Files changed:
  - `backend/app/db/models/job_occurrence.py` — class docstring.
  - `backend/app/db/models/raw_job_ingestion.py` — class docstring.
  - `backend/migrations/versions/0011_job_occurrences.py` — module docstring.
  - `backend/migrations/versions/0012_raw_job_ingestions.py` — module docstring.
  - `docs/DATA_MODEL.md` — the `job_occurrences` and `raw_job_ingestions` introduction
    passages.
- Commands run and exact results (lightweight, per the review's own scoping — no
  backend/Alembic reruns for comment-only changes):
  - `git diff --check` → clean.
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `ruff format`, `ruff check` against the four touched Python files → all
    unchanged/passed.
- Deviations/known limitations: none. Confirmed via `grep` that no other stale
  "Phase 4+ ingestion code is the first writer"/"Phase 4+ ingestion code, out of scope"
  occurrences remain anywhere in the tracked tree, other than Codex's own quoted
  finding text in this file's prior `Work review` (a historical quotation of the
  defect, not live documentation, correctly left as-is).
- STOP — awaiting Codex re-review. Do not begin `identity_conflicts` or any other
  slice, and do not modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `53a2cad..029be54`.
- Verdict: **approved**. Findings: none.
- Verified independently:
  - Inspected all six requested wording changes across the two model docstrings, two
    migration docstrings, and two DATA_MODEL passages. They now consistently identify
    Phase 2's offline fixture pipeline as the first writer/user and Phase 4 as the
    first live ATS provider reusing that path.
  - Repository search confirms the stale first-writer claims are gone. The remaining
    DATA_MODEL "Phase 4+" field-provenance statement is a separate, valid claim and was
    correctly left unchanged.
  - `git diff --check`, repository checker, `ruff format --check`, and `ruff check`
    passed for the bounded correction. Backend/Alembic tests were not repeated because
    only comments/documentation changed; the implementation review at `53a2cad`
    already recorded **74 targeted / 737 full-suite tests** and clean schema drift.
- The `raw_job_ingestions` implementation and correction pass are accepted. Do not
  merge to `main` or begin `identity_conflicts`/another slice until the user explicitly
  authorizes the next action.
- STOP — reviewer changed only this `Work review`; no implementation files changed.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `82245e5`. Per user authorization, `phase-1/raw-job-ingestions` was merged into
`main` with a normal merge commit (`863e1d9`; `--no-ff`, no squash/rebase/force-push)
and pushed. `main`/`origin/main` are both now at `863e1d9`. Verified: `main` has zero
content diff against the feature branch; migration `0012` (`down_revision = "0011"`)
is present in `main`; `python backend/scripts/check_repo.py` (via the project's own
virtualenv interpreter) exits 0 with zero findings; working tree clean. No later
Phase 1 table (`identity_conflicts` or otherwise) started or proposed.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `identity_conflicts`,
  Class H per docs/LLM_WORKFLOW.md — two independent `ON DELETE SET NULL` relationships,
  a first-of-its-kind bidirectional status/timestamp lifecycle `CHECK`, and a
  `conflict_type`-conditional JSON shape `CHECK`. Base `214ef9d` on `main` -> branch
  `phase-1/identity-conflicts`.
- Outcome: new model, migration `0013`, factory/real-commit helpers, and 65 new tests
  implemented and verified against real PostgreSQL.
  - `IdentityConflict` model: `conflict_type`/`status` are plain `CHECK`-restricted
    enums, no ORM trim/case transform (matching `raw_job_ingestions.processing_status`'s
    treatment — closed literal sets, not cross-table join keys).
    `existing_value`/`incoming_value` are NOT NULL jsonb whose shape depends on
    `conflict_type`: a JSON object for `evidence_mismatch`, a JSON array for
    `ambiguous_match`, enforced by a `CHECK` conditional on `conflict_type` for each
    column (only the top-level shape — empty objects/arrays explicitly accepted,
    proven by dedicated tests). Not `MutableDict`/`MutableList`-wrapped: immutable,
    write-once snapshots, same rationale as `raw_job_ingestions.raw_payload`.
    `existing_job_occurrence_id`/`incoming_raw_job_ingestion_id` are both nullable,
    `ON DELETE SET NULL`. `status`/`resolved_at` consistency and a new
    `resolved_at >= created_at` ordering `CHECK` are both fully bidirectional (neither
    interacts with either FK's cascade). `status` has no server default.
    `resolution` is nullable, ORM-trimmed with blank collapsed to `NULL`, but has no
    backing `CHECK` (direct SQL bypasses the normalization entirely, tested explicitly).
    `created_at`/`updated_at` follow the established global convention.
  - **The key design decision** (mirroring `raw_job_ingestions`' precedent in a new
    shape): only the safe direction of the `conflict_type`/`existing_job_occurrence_id`
    relationship is a `CHECK` — `ambiguous_match` requires `existing_job_occurrence_id
    IS NULL` (safe: an `ambiguous_match` row never has a non-null value to begin with).
    The reverse (`evidence_mismatch` implying non-null) is deliberately **not** a
    `CHECK`: enforcing it would turn `ON DELETE SET NULL` into `RESTRICT` in practice
    whenever a disputed occurrence is later deleted. `incoming_raw_job_ingestion_id`
    gets no `CHECK` at all for the same reason. This asymmetric design was part of the
    user's original authorization (not discovered mid-implementation this time).
  - Two FK constraints (`existing_job_occurrence_id`→`job_occurrences`,
    `incoming_raw_job_ingestion_id`→`raw_job_ingestions`) required explicit, shortened
    names (`fk_identity_conflicts_existing_occurrence`,
    `fk_identity_conflicts_incoming_ingestion`) — the naming convention's full template
    exceeds Postgres's 63-byte identifier limit for both (64 and 70 chars) and would
    otherwise be silently truncated with a hash suffix. Caught via direct DDL rendering
    before writing the migration.
  - Indexes: `(status)`, `(existing_job_occurrence_id)`,
    `(incoming_raw_job_ingestion_id)` — three plain, non-unique indexes; no uniqueness
    constraint anywhere (no concurrency test needed).
- Files changed:
  - `backend/app/db/models/identity_conflict.py` (new).
  - `backend/app/db/models/__init__.py`, `backend/app/db/base.py` —
    registration/docstring.
  - `backend/migrations/versions/0013_identity_conflicts.py` (new,
    `down_revision = "0012"`).
  - `backend/tests/conftest.py` — `make_identity_conflict` (both FKs default `None`,
    `status` defaults to `"open"` as a Python-level factory convenience only — the
    database itself has no server default), `real_committed_identity_conflict` (builds
    on `real_committed_job_occurrence` and `real_committed_raw_job_ingestion` in
    parallel — two structurally independent parent chains, not nested — with an
    `ingestion_occurrence_kwargs` override to avoid the ingestion's own internal
    occurrence colliding with the conflict's primary occurrence on
    `job_occurrences`' fallback-URL unique index).
  - `backend/tests/test_identity_conflicts.py` (new) — 65 tests: `conflict_type`/
    `status` enum validity; the full `status`/`resolved_at` lifecycle matrix (3 valid +
    3 invalid pairings, ORM + direct SQL) plus the `resolved_at`-vs-`created_at`
    ordering boundary (equal/after accepted, before rejected, via direct SQL with
    explicit timestamps); both JSON shapes accepted (including empty object/array) and
    12 wrong-shape/JSON-null/scalar rejection cases across both columns and both
    conflict types; the `ambiguous_match`-requires-null-occurrence `CHECK` (accepted/
    rejected, ORM + direct SQL) alongside `evidence_mismatch`'s DB-permitted-but-not-
    required null case; nonexistent-FK rejection for both relationships; both
    independent `ON DELETE SET NULL` cascades proven in isolation from each other and
    from an unrelated conflict row; `resolution`'s ORM normalization vs. its absence
    on direct SQL; a separate-session reload proving both snapshots survive an
    unrelated lifecycle update unchanged; timestamp server-defaults and UTC-awareness.
  - `docs/DATA_MODEL.md` — `identity_conflicts` marked **Implemented**; added "Rev 18"
    note recording every resolved decision; added/updated the constraints-summary row.
  - `docs/ROADMAP.md` — Phase 1 status line describes the `identity_conflicts` slice
    as complete.
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `ruff format --check .`, `ruff check .` → passed (54 files).
  - `mypy app tests scripts` → success, 40 source files.
  - `pytest tests/test_identity_conflicts.py -q` → 65 passed.
  - `pytest -q` (full suite) → 802 passed.
  - `DATABASE_URL=...jobgoblin_test`: `alembic upgrade head` (`0012 -> 0013`, existing
    head), `downgrade 0012` / `upgrade head` (round-trip), `downgrade base` / `upgrade
    head` (fresh `base -> head`), `alembic check` (`No new upgrade operations detected`
    — same informational `Computed`-column `UserWarning` as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`pg_constraint`, `pg_indexes`) — confirmed both
    FKs' `ON DELETE SET NULL` (`confdeltype = 'n'`), exactly 7 `CHECK` constraints, and
    the three lookup indexes; no partial/unique index exists, matching design.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual uncommitted diff before commit; full
  12-question Class H depth): one **Medium** finding — the docstrings' claim that an
  empty object/array is deliberately accepted (only top-level shape enforced, no
  non-empty requirement) was asserted in both the model and migration docstrings but
  had zero test coverage; a future accidental tightening of the shape `CHECK` could
  silently break the documented behavior with nothing to catch it. Fixed: added 4
  regression tests (empty object for `evidence_mismatch`, empty array for
  `ambiguous_match`, each via ORM and direct SQL). No Critical/High findings.
  Explicitly checked and clean: `conflict_type`/`status`'s lack of ORM transform
  matches the established `processing_status` precedent, no interaction issue; all 7
  `CheckConstraint` bodies are byte-identical between model and migration, including
  both custom FK names; the separate-session snapshot-survival test is genuine, not
  vacuous; no partial index and no unique constraint exist on this table (confirmed
  against the migration, not assumed); the `real_committed_identity_conflict` helper's
  three-real-row cleanup unwinds correctly even when a test body deletes one parent
  itself (both SET-NULL cascade tests do); neither cascade test could pass vacuously —
  both conflict rows in each test are proven to actually exist via distinct
  `source_url` overrides on both parent chains, avoiding the exact
  `job_occurrences`-fallback-URL collision class already caught once before in this
  project; both ADR 0007 fixture shapes (evidence_mismatch with a real occurrence,
  ambiguous_match with a null one) are constructible without hitting any CHECK Phase 2
  shouldn't.
- Deviations/known limitations: none new. `collection_runs`,
  `collection_run_provider_attempts`, `user_jobs`, and all ingestion/matching/
  reconciliation logic remain unimplemented, per explicit scope. The
  `evidence_mismatch` ⟹ non-null-occurrence half of its consistency invariant, and any
  `incoming_raw_job_ingestion_id` non-null requirement, are intentionally not
  database-enforced (see design decision above) — Phase 2's persistence-service tests,
  not this schema, own proving fresh writes always set them.
- STOP — awaiting Codex review. Do not begin `collection_runs`, `user_jobs`, or any
  other slice, and do not modify `main`.

### Work review

*Pending — awaiting Codex.*
