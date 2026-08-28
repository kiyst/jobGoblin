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
`job_occurrences` correction pass, its approval, and merge record) was removed rather
than kept alongside a third entry, since it was already merged and is no longer
pending. Nothing below was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `raw_job_ingestions`,
  Class H per docs/LLM_WORKFLOW.md (ingestion-adjacent audit table whose FK interacts
  with a destructive lifecycle event — deleting a `JobOccurrence` must preserve, not
  cascade-delete, its referencing ingestion rows). Base `e7a0a60` on `main` -> branch
  `phase-1/raw-job-ingestions`.
- Outcome: new model, migration `0012`, factory/real-commit helpers, and 74 new tests
  implemented and verified against real PostgreSQL.
  - `RawJobIngestion` model: `provider`/`source` reuse `job_occurrences`' canonical-
    identifier treatment verbatim (ORM trim+lowercase; DB `CHECK` requires already-
    canonical, ASCII-slug `^[a-z0-9][a-z0-9._-]*$`), generalized to a second table
    since these are internal categorization labels, not "raw" external data.
    `source_identifier`/`parser_version`/`error_message` are nullable, case-preserving,
    NULL-safe `CHECK` pairs. `job_occurrence_id` is nullable, `ON DELETE SET NULL`
    (audit trail survives occurrence deletion). `fetched_at` is NOT NULL with **no**
    server default (represents the actual fetch event, which may differ from row-
    insertion time — buffering/replay/backfill). `raw_payload` is NOT NULL jsonb with a
    top-level-object `CHECK`, deliberately **not** `MutableDict`-wrapped (an immutable,
    write-once snapshot — documented as an application-level convention, not a schema
    guarantee; whole-value/direct-SQL writes remain possible). `raw_content_hash` is
    NOT NULL with a trim/non-empty `CHECK` only — no format/length constraint
    (application-computed). `processing_status` is a `CHECK`-restricted enum
    (`fetched`/`parse_error`/`normalized`/`identity_conflict`). `created_at`/
    `updated_at` follow the established global convention.
  - **The key design decision**: the `processing_status`/`job_occurrence_id`
    consistency invariant is database-enforced in only one direction —
    `processing_status IN ('fetched', 'parse_error') ⟹ job_occurrence_id IS NULL`.
    The reverse (`normalized`/`identity_conflict` ⟹ non-null) is deliberately **not** a
    `CHECK`: enforcing it would make `ON DELETE SET NULL`'s own cascade `UPDATE`
    violate the `CHECK` whenever a `normalized`/`identity_conflict` row's target
    occurrence is deleted, turning `SET NULL` into `RESTRICT` in practice — exactly
    the historical audit-preservation state ADR 0005 exists to support. This was a
    user-approved correction to the original proposal (which asked for both
    directions) after the conflict was identified during the pre-implementation
    adversarial analysis. Phase 1 has no ingestion service to test the fresh-write-side
    contract against; Phase 2's persistence-service tests will own that.
  - No uniqueness constraint of any kind (intentionally append-only audit log — a
    re-observed posting gets a new row every fetch). Index:
    `(job_occurrence_id, fetched_at DESC)`.
- Files changed:
  - `backend/app/db/models/raw_job_ingestion.py` (new).
  - `backend/app/db/models/__init__.py`, `backend/app/db/base.py` —
    registration/docstring.
  - `backend/migrations/versions/0012_raw_job_ingestions.py` (new,
    `down_revision = "0011"`).
  - `backend/tests/conftest.py` — `make_raw_job_ingestion` (requires `fetched_at`
    explicitly, no default), `real_committed_raw_job_ingestion` (builds on
    `real_committed_job_occurrence`; defaults to a linked `normalized` row since it
    exists specifically to exercise `ON DELETE SET NULL`, but a caller may pass
    `job_occurrence_id=None` to start a row unlinked instead).
  - `backend/tests/test_raw_job_ingestions.py` (new) — 74 tests: canonical-identifier
    `provider`/`source` (ORM + direct-SQL, including non-ASCII/embedded-space/
    leading-hyphen rejection and a `.`/`_`/`-` positive case); nullable trim-only text
    columns; `raw_content_hash` trim/non-empty with an arbitrary-non-hex positive case;
    `processing_status` enum validity; the full status/occurrence consistency matrix
    (every status accepted with a NULL occurrence — including a dedicated test
    documenting `normalized`/`identity_conflict`+NULL as the DB-permitted post-deletion
    state, not a fresh-write pattern; `fetched`/`parse_error` rejected with a non-null
    occurrence; `normalized`/`identity_conflict` accepted with one); the `ON DELETE
    SET NULL` isolation test (deleting one occurrence nulls only its own ingestion
    row, preserving it, while a second, unrelated ingestion row stays untouched);
    `raw_payload`'s top-level-object `CHECK` against SQL `NULL`, JSON `null`, arrays,
    and scalars, a representative-object round-trip, and a separate-session reload
    proving lifecycle updates don't alter it (semantic equality, not byte-for-byte);
    `fetched_at`'s no-default requirement; `created_at`/`updated_at`'s server default
    and `updated_at` advancing on a real update; timestamp UTC-awareness.
  - `docs/DATA_MODEL.md` — `raw_job_ingestions` marked **Implemented**; added "Rev 17"
    note recording the canonical-identifier generalization, the one-directional
    consistency `CHECK` and its rationale, the `raw_payload`/`raw_content_hash`
    decisions, and `fetched_at`'s no-default treatment; added the constraints-summary
    row.
  - `docs/ROADMAP.md` — Phase 1 status line describes the `raw_job_ingestions` slice
    as complete.
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings.
  - `ruff format --check .`, `ruff check .` → passed (51 files).
  - `mypy app tests scripts` → success, 38 source files.
  - `pytest tests/test_raw_job_ingestions.py -q` → 74 passed.
  - `pytest -q` (full suite) → 737 passed.
  - `DATABASE_URL=...jobgoblin_test`: `alembic upgrade head` (`0011 -> 0012`, existing
    head), `downgrade 0011` / `upgrade head` (round-trip), `downgrade base` / `upgrade
    head` (fresh `base -> head`), `alembic check` (`No new upgrade operations detected`
    — same informational `Computed`-column `UserWarning` as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - Live schema inspected directly (`pg_constraint`, `pg_indexes`) — confirmed the
    FK's `ON DELETE SET NULL` (`confdeltype = 'n'`), exactly 17 `CHECK` constraints,
    and the single lookup index; no partial/unique index exists, matching design.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of the
  implementation, run against the actual uncommitted diff before commit; full
  12-question Class H depth): one **Medium** finding — the
  `real_committed_raw_job_ingestion` helper's `setdefault`-based linking logic
  (correctly fixed earlier in this same pass after an initial bug where it
  unconditionally forced a non-null `job_occurrence_id` regardless of requested
  `processing_status`) had no docstring warning that passing `processing_status=
  "fetched"`/`"parse_error"` without also passing `job_occurrence_id=None` would fail
  at `commit()`. Fixed: added an explicit docstring note. No Critical/High findings.
  Explicitly checked and clean: CHECK text is character-for-character identical
  between model and migration, including the one-directional consistency clause;
  provider/source ASCII-slug and JSONB top-level-object edge cases (JSON `null` vs SQL
  `NULL` vs array vs scalar) all behave correctly; no partial index exists (confirmed
  against the migration, not assumed) and no unique constraint exists anywhere on this
  table, so no concurrency test was needed; the `raw_payload`-survives-update test uses
  genuine separate-session reload with semantic (not byte-for-byte) equality; the FK
  isolation test is not vacuous (the second occurrence uses a distinct `source_url` to
  avoid an unrelated `job_occurrences` uniqueness collision, and both rows are proven
  to exist and diverge post-deletion); naming-convention resolution matches between
  model and migration; no stale docstrings between the two files; the asymmetric CHECK
  neither over- nor under-constrains Phase 2's documented two-step write pattern.
- Deviations/known limitations: none new. `identity_conflicts`, `collection_runs`,
  `collection_run_provider_attempts`, `user_jobs`, and all ingestion/matching/
  reconciliation logic remain unimplemented, per explicit scope. The
  `normalized`/`identity_conflict` ⟹ non-null-occurrence half of the consistency
  invariant is intentionally not database-enforced (see design decision above) —
  Phase 2's persistence-service tests, not this schema, own proving fresh writes
  always set it.
- STOP — awaiting Codex review. Do not begin `identity_conflicts` or any other slice,
  and do not modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: `e7a0a60..caa36c8`.
- Verdict: **changes requested** (one bounded documentation-phase correction; schema
  and executable behavior otherwise accepted).
- Verification performed:
  - Inspected the model, migration, factories/real-commit cleanup, complete targeted
    test file, DATA_MODEL/ROADMAP changes, and the asymmetric status/FK contract.
  - Repository checker, `ruff format --check`, `ruff check`, and
    `mypy app tests scripts` passed.
  - `tests/test_raw_job_ingestions.py`: **74 passed**. Full suite: **737 passed**.
  - `alembic check` against `jobgoblin_test`: no new upgrade operations; test schema
    is at `0012 (head)`. The reviewer did not repeat Claude's destructive migration
    downgrade/fresh-rebuild sequence or the live-schema catalog inspection.
- Findings:
  1. **Low — the new first-writer wording assigns fixture ingestion to the wrong
     phase.** `backend/app/db/models/raw_job_ingestion.py`, migration `0012`, and the
     implemented `raw_job_ingestions` introduction in `docs/DATA_MODEL.md` say
     "Phase 4+ ingestion code is the first writer." The canonical roadmap explicitly
     makes Phase 2's offline fixture pipeline write `RawJobIngestion` as part of
     `Fixture -> RawJobIngestion -> identity resolution -> Job -> JobOccurrence`;
     Phase 4 introduces the first real `ats-scrapers` provider. The same stale
     "Phase 4+" ownership wording also remains in the previously merged
     `JobOccurrence` model/migration/DATA_MODEL text. This is documentation-only, but
     it misstates the immediate consumer contract the new schema was designed for.
- Exact bounded correction:
  1. Replace all six stale Phase-4 ownership claims in the two model docstrings, the
     `0011`/`0012` migration docstrings, and the corresponding two DATA_MODEL passages
     with consistent wording: Phase 2's fixture ingestion is the first writer/user of
     the persistence and deterministic-identity path; Phase 4 is the first live ATS
     provider to reuse that path.
  2. Do not alter schema, migrations' operations/revision metadata, tests, or product
     behavior. Run `git diff --check`, the repository checker, and Ruff against the
     touched Python files; backend/Alembic test reruns are unnecessary for comment-only
     changes. Update concise `Work done`, commit/push the same branch, and stop.
  3. Do not begin `identity_conflicts` or any other slice, and do not modify `main`.
- STOP — reviewer changed only this `Work review`; no implementation files changed.

---

## Iteration 2

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
  finding text in this file's Iteration 1 `Work review` above (a historical quotation
  of the defect, not live documentation, correctly left as-is).
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
