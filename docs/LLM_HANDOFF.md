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
`job_occurrences` initial implementation pass and Codex's changes-requested review at
`5ad85bd`) was removed rather than kept alongside a third entry — every finding it
raised was addressed in this entry's correction pass, which Codex then approved and the
user merged. Nothing below was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: bounded correction
  pass addressing the five findings at review commit `5ad85bd`, on the same
  `phase-1/job-occurrences` branch. Base: `5ad85bd`. No later table, ingestion,
  provider, normalization, reconciliation, CI, or `main` changes.
- Outcome: all five findings addressed; 22 new regression tests (150 total, up from
  128); fresh-context adversarial self-review run against the correction diff itself,
  which surfaced and closed one additional low test-coverage gap.
  1. **`normalize_url()` whitespace handling (High).** Now trims only symmetric outer
     wrapper whitespace before parsing (`value.strip(_TRIM_CHARS)`), then rejects
     (`None`) the whole input if any covered whitespace (`\t\n\r `) remains anywhere
     inside — instead of letting `urlsplit()` silently delete an embedded `\t`/`\n`/`\r`
     while leaving an embedded space untouched. Removed the prior post-assembly
     `.strip()` workaround (now redundant/unreachable). Percent-encoded whitespace
     (`%20`) is unaffected.
  2. **DNS root-dot host equivalence (Medium).** `_canonicalize_host()` now strips
     exactly one trailing dot from the post-IDNA ASCII form, so `example.com.` and its
     UTS #46-mapped equivalents (U+3002, U+FF0E) canonicalize identically to
     `example.com`. A doubled/empty label (`example.com..`, `.example.com`) still
     returns `None` — `idna.encode()` already treats these as errors.
  3. **ASCII slug-format `CHECK` on `provider`/`source` (Medium).** Added
     `provider_slug_format`/`source_slug_format` CHECKs (`^[a-z0-9][a-z0-9._-]*$`) to
     both the model and migration `0011`, alongside the existing trim/lower/non-empty
     CHECKs. Makes the Python `str.lower()`-vs-PostgreSQL-`lower()` divergence on
     non-ASCII input structurally impossible rather than an accepted limitation.
     `normalize_url()`'s per-`(provider, source)` allow-list lookup is now
     canonicalized (trim+lower) before the dict lookup.
  4. **Valid-state test factory (Medium).** `make_job_occurrence`/
     `real_committed_job_occurrence` (`backend/tests/conftest.py`) now compute
     `source_url_normalized = normalize_url(source_url, provider=provider,
     source=source)` by default. The model's own non-derivation test now constructs
     `JobOccurrence` directly, bypassing the factory. The null/null fallback-key test
     now uses three distinct, genuinely malformed raw URLs, not the same valid default
     URL three times.
  5. **Branch integration.** Merged `origin/main` into `phase-1/job-occurrences` with
     a real merge commit (`git merge --no-ff`) so `3d47cd6` (the adversarial-self-
     review workflow doc change) is now an ancestor. No conflicts.
- Files changed: `backend/app/normalization/url.py`, `backend/app/db/models/
  job_occurrence.py`, `backend/migrations/versions/0011_job_occurrences.py`,
  `backend/tests/conftest.py`, `backend/tests/test_job_occurrences.py`,
  `docs/DATA_MODEL.md` ("Rev 16 corrections").
- Commands run and exact results: `check_repo.py` exit 0 (before/after the merge);
  `ruff format --check .`/`ruff check .` passed (48 files); `mypy app tests scripts`
  success (36 files); `pytest tests/test_job_occurrences.py -q` 150 passed (up from
  128); full suite 663 passed (up from 641); migration `downgrade 0010`/`upgrade head`
  round-trip, fresh `base -> head` (re-run after the merge), `alembic check` clean;
  development DB unchanged at `0006`.
- STOP — awaiting Codex re-review. Do not begin any later table, ingestion, providers,
  normalization, reconciliation, add CI, or modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Diff reviewed: correction commit `112c6d8`,
  integration merge `d79ddec`, and handoff commit `5ea43ca`, against the requested
  corrections recorded at `5ad85bd`.
- Verdict: **approved**. Findings: none.
- Verified independently:
  - Inspected the implementation, migration/model parity, factory changes, tests,
    documentation, and branch ancestry. `3d47cd6` is now an ancestor of the feature
    branch; `main`/`origin/main` remain untouched at `3d47cd6`.
  - Manual adversarial probes confirmed embedded space/TAB/LF/CR rejection, accepted
    outer wrapper whitespace, percent-encoded whitespace preservation, ASCII and
    UTS #46 root-dot equivalence, and doubled/bare-dot rejection.
  - Repository checker, `ruff format --check`, `ruff check`, and
    `mypy app tests scripts` passed.
  - `tests/test_job_occurrences.py`: **150 passed**. Full suite: **663 passed**.
  - `alembic check` against `jobgoblin_test`: no new upgrade operations; test schema
    is at `0011 (head)`. The reviewer did not repeat Claude's destructive migration
    downgrade/fresh-rebuild sequence.
- The five bounded findings from `5ad85bd` are resolved. The `job_occurrences` slice
  is accepted. Do not merge it to `main`, begin another table, or advance into
  ingestion/providers/matching/reconciliation until the user explicitly authorizes
  the next action.
- STOP — reviewer changed only this `Work review`; no implementation files changed.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `59e4742`. Per user authorization, `phase-1/job-occurrences` was merged into
`main` with a normal merge commit (`81031af`; `--no-ff`, no squash/rebase/force-push)
and pushed. `main`/`origin/main` are both now at `81031af`. Verified: `main` has zero
content diff against the feature branch; migration `0011` (`down_revision = "0010"`)
is present in `main`; `python backend/scripts/check_repo.py` (via the project's own
virtualenv interpreter) exits 0 with zero findings; working tree clean. No later
Phase 1 table started or proposed.

---

## Iteration 2

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
