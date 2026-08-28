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
`jobs` implementation pass, its approval, and merge record) was removed rather than kept
alongside a third entry, since it was already merged and is no longer pending. Nothing
below was rewritten — only renumbered.*

### Work done

- Date/agent: 2026-08-28, Claude Code (Sonnet 5). Authorized slice: `job_occurrences`,
  Class H per docs/LLM_WORKFLOW.md — this is the table the project's deterministic
  identity-resolution scheme (ADR 0004) is built on; its three partial unique indexes
  are the scoped identity signals ADR 0004 defines. Base `04fce4a` on `main` -> branch
  `phase-1/job-occurrences`.
- Outcome: new URL-normalization module, model, migration `0011`, factory/real-commit
  helpers, and 128 new tests implemented and verified against real PostgreSQL (125
  from initial implementation, plus 3 from the adversarial self-review below).
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
  - `backend/tests/test_job_occurrences.py` (new) — 128 tests: `normalize_url()`
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
  - `pytest tests/test_job_occurrences.py -q` → 128 passed.
  - `pytest -q` (full suite) → 641 passed.
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
- Adversarial self-review (per docs/LLM_WORKFLOW.md's new self-review step, run
  retroactively against this already-committed diff by a fresh Explore-agent
  context with no prior knowledge of the implementation): all 12 questions checked
  against `git show`/current file contents, not against this entry's own summary.
  - Assumptions challenged: that `normalize_url()`'s output always already satisfies
    the `*_normalized` columns' own trim/non-empty `CHECK`s; that ORM-side
    `lower()`/DB-side `lower()` always agree for `provider`/`source`; that the
    partition-matrix tests actually exercise both halves of the `(provider, source)`
    compound key, not just one.
  - Findings fixed (2):
    1. **High** — `normalize_url()` could return a non-`None` value with a literal
       trailing space (e.g. `normalize_url("http://acme.com/careers ")`), because
       `urlsplit()` only strips `\t`/`\n`/`\r` from the whole input, not a raw space,
       and `path.rstrip("/")` doesn't touch it either. That value would fail the
       column's own trim `CHECK` if ever written outside the ORM's `@validates` path
       (e.g. a future raw-SQL/Core insert on Phase 2's persistence path) — silently
       contradicting the "malformed input returns `None`" contract. Fixed in
       `backend/app/normalization/url.py` by stripping the assembled result against
       the same trim-character set the DB `CHECK`s use, before returning. Regression
       test: `test_normalize_url_strips_trailing_space_in_path` (fails against the
       pre-fix function).
    2. **Low** — the unique-index partition-matrix tests for "different
       provider/source accepted" only ever varied `provider`, never `source`, leaving
       half the compound key's claim unverified. Added
       `test_same_id_under_different_source_accepted` and
       `test_same_fallback_url_under_different_source_accepted` in
       `backend/tests/test_job_occurrences.py`, mirroring the existing
       provider-variation tests with `source` varied instead.
  - Not fixed, recorded as a known limitation: **Medium** — `provider`/`source`
    canonicalization relies on Python's `str.lower()` (ORM) matching PostgreSQL's
    `lower()` (DB `CHECK`), which can diverge for non-ASCII input depending on server
    locale/collation (e.g. Turkish dotted-İ). Not fixed because a fix (e.g.
    restricting these columns to ASCII) would be a new schema/semantic decision
    beyond this slice's 21-point authorization, not a bug-fix within it. In practice
    `provider`/`source` are fixed ASCII machine identifiers set by this project's own
    ingestion code (`ats_scrapers`, `greenhouse`, `jobspy`, etc.), never external
    user input, so the risk is latent rather than reachable today. **Superseded in
    Iteration 2 below** — Codex's review found this unsafe enough in natural-key
    columns to fix directly rather than accept.
  - Verification rerun after the fix: `ruff format --check .`/`ruff check .` (48
    files, passed), `mypy app tests scripts` (36 files, success),
    `pytest tests/test_job_occurrences.py -q` (128 passed, up from 125),
    `pytest -q` full suite (641 passed, up from 638), `check_repo.py` (exit 0),
    `git diff --check` (clean). No schema/migration file changed by this pass, so
    migration round-trip/fresh-rebuild checks were not rerun (unaffected surface).
- Deviations/known limitations: the ORM/DB `lower()` divergence above. Otherwise
  none. `raw_job_ingestions`, `identity_conflicts`, `duplicate_groups`, and the
  actual match-precedence application logic remain unimplemented, per explicit
  scope — ADR 0004/ARCHITECTURE.md §8's end-to-end idempotent re-observation
  requirement is deferred to Phase 2, since it needs the persistence path, not
  merely this table.
- STOP — awaiting Codex review. Do not begin any later table, ingestion, providers,
  normalization, reconciliation, add CI, or modify `main`.

### Work review

- Date/reviewer: 2026-08-28, Codex. Effective implementation and self-review diff
  reviewed: `04fce4a..bbfc422` on `phase-1/job-occurrences`; branch clean and synchronized
  with origin before this review entry. The workflow-only `main` commit `3d47cd6` was
  inspected separately because it is not an ancestor of this feature branch.
- Independent verification:
  - Inspected URL canonicalization, model/migration parity, all partial-index predicates,
    concurrent-insert cleanup, cascade isolation, factory behavior, product-document
    updates, and the retroactive adversarial self-review.
  - `python scripts/check_repo.py`: exit 0, zero findings.
  - `ruff format --check .`, `ruff check .`: passed (48 files).
  - `mypy app tests scripts`: passed (36 source files).
  - `pytest tests/test_job_occurrences.py -q`: 128 passed.
  - `pytest -q --basetemp=.pytest_cache/codex_job_occurrences_review`: 641 passed.
  - `alembic check` against `jobgoblin_test` at `0011 (head)`: no new upgrade
    operations detected; only the known warning for the pre-existing companies computed
    column appeared.
  - Direct probes reproduced the URL and Unicode-identifier findings below; PostgreSQL
    maps U+0130 to `i` while Python maps it to `i` + U+0307 in this environment.
- Findings:
  1. **High — malformed URL whitespace is silently deleted or retained, creating false
     identity matches.** `backend/app/normalization/url.py:116-154` calls `urlsplit()`
     before checking the raw input and then strips only the assembled value's outer
     whitespace. Python's parser silently deletes embedded TAB/LF/CR anywhere in the
     URL: `https://exa<TAB>mple.com/job` becomes `https://example.com/job`, and
     `https://example.com/jo<LF>b` becomes `https://example.com/job`. An internal raw
     space survives (`.../jo b`), despite the function claiming to accept only
     syntactically valid URLs. These malformed inputs can therefore collide with a
     different valid occurrence. Trim the approved wrapper whitespace before parsing,
     reject any covered whitespace remaining inside the trimmed input, and remove the
     post-assembly `strip()` workaround. Percent-encoded whitespace remains valid.
     Add regressions for space/TAB/LF/CR in host, path, and query plus ordinary outer
     wrapper whitespace.
  2. **Medium — equivalent DNS root-dot hosts do not canonicalize together.**
     `_canonicalize_host()` returns IDNA output unchanged, so `example.com.` and U+3002
     variants normalize to `example.com.` rather than `example.com`; they do not match
     the same URL without the DNS root separator. Strip exactly one trailing root dot
     from the post-IDNA ASCII domain form; doubled/empty-label forms must return `None`.
     Add ASCII and Unicode-equivalence regressions.
  3. **Medium — the acknowledged Python/PostgreSQL lowercase divergence is unsafe in
     natural-key columns.** `provider` and `source` are controlled machine identifiers,
     so leaving arbitrary Unicode as a known limitation is unnecessary and lets the ORM
     and DB disagree before values reach three identity indexes. Add DB/model parity
     CHECKs restricting each to a documented lowercase ASCII slug grammar, recommended
     `^[a-z0-9][a-z0-9._-]*$`, while retaining the current trim/lower/non-empty checks.
     Add ORM and direct-SQL accepted/rejected tests, including non-ASCII. Canonicalize
     `normalize_url()`'s optional allow-list context with the same trim/lower rule before
     lookup so future evidence-based entries cannot miss because of caller casing.
  4. **Medium — the valid-state factory bypasses the fallback identity invariant by
     default.** `backend/tests/conftest.py:468-498` supplies a valid absolute
     `source_url` but leaves `source_url_normalized = NULL`; the baseline test asserts
     that state, and the null/null uniqueness test describes these as malformed URLs
     while actually using the same valid default URL three times. The model may remain
     deliberately non-deriving, but the factory is an application caller and must create
     valid states by default: compute `source_url_normalized = normalize_url(...)` with
     provider/source context, using distinct defaults or explicit IDs so unrelated test
     rows do not collide. Keep the model-non-derivation test by constructing/overriding
     that exceptional state explicitly. Change the null/null fallback test to use
     genuinely malformed, distinct raw URLs whose normalizer result is `None`.
  5. **Medium, integration/process — the feature branch omitted the workflow commit it
     claims to apply.** `3d47cd6` is on `main` but is not an ancestor of `bbfc422`, so
     `main` and the feature branch have diverged and the usual fast-forward merge is
     currently impossible. Merge `origin/main` into `phase-1/job-occurrences` with a
     normal merge commit after fetching (no rebase/force-push); do not modify `main`.
- Missing/inconclusive checks: the reviewer did not repeat destructive migration
  downgrade/fresh-rebuild operations; Claude recorded them as passing. The live test DB
  is at `0011`, autogeneration reports no drift, and all relevant tests passed.
- Verdict: changes requested (three bounded executable corrections, one valid-factory
  correction, and one branch-integration correction).
- Exact bounded correction:
  1. Address findings 1-4 without changing the three partial-index definitions or
     expanding into ingestion/match-precedence behavior. Correct implementation and
     DATA_MODEL wording where the malformed-whitespace/root-dot/ASCII-slug contract
     changes.
  2. Add regression tests that fail against `bbfc422`, including the exact reproduced
     inputs and corrected factory/null-fallback semantics.
  3. Merge `origin/main` into the feature branch normally so `3d47cd6` becomes an
     ancestor; do not rebase, squash, force-push, or touch `main`.
  4. Rerun the fresh-context adversarial self-review plus repository checker, Ruff,
     mypy, targeted/full tests, migration round-trip/fresh `base -> head`/`alembic check`
     against `jobgoblin_test`, and confirm development remains untouched. Update the
     concise `Work done`, commit/push the same branch, and stop for re-review.
  5. Do not begin later tables, ingestion, providers, matching, reconciliation, or CI.
- STOP — reviewer changed only this `Work review`; no implementation files were changed.

---

## Iteration 2

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
     both the model and migration `0011` (amended in place — not yet merged to `main`),
     alongside the existing trim/lower/non-empty CHECKs. Makes the Python
     `str.lower()`-vs-PostgreSQL-`lower()` divergence on non-ASCII input structurally
     impossible rather than an accepted limitation.
     `normalize_url()`'s per-`(provider, source)` allow-list lookup is now
     canonicalized (trim+lower) before the dict lookup.
  4. **Valid-state test factory (Medium).** `make_job_occurrence`/
     `real_committed_job_occurrence` (`backend/tests/conftest.py`) now compute
     `source_url_normalized = normalize_url(source_url, provider=provider,
     source=source)` by default. The model's own non-derivation test
     (`test_normalized_url_columns_are_not_auto_derived_from_raw_urls`) now
     constructs `JobOccurrence` directly, bypassing the factory, to isolate the
     model's behavior from the factory's. The null/null fallback-key test
     (`test_multiple_rows_with_null_source_job_id_and_null_normalized_url_accepted`)
     now uses three distinct, genuinely malformed raw URLs (each independently
     verified via `assert normalize_url(...) is None`), not the same valid default
     URL three times.
  5. **Branch integration.** Merged `origin/main` into `phase-1/job-occurrences` with
     a real merge commit (`git merge --no-ff`, no rebase/squash/force-push) so
     `3d47cd6` (the adversarial-self-review workflow doc change) is now an ancestor.
     `main`/`origin/main` unchanged at `3d47cd6` throughout; no conflicts.
- Adversarial self-review (fresh Explore-agent context, no prior knowledge of this
  correction pass, run against the actual working-tree diff before commit): all 12
  questions checked, including hand-executed edge cases (bare `.` host, doubled
  root-dot, userinfo-whitespace ordering, all-whitespace input, IP-with-trailing-dot,
  `%20`) and a full run of the DB-backed suite to confirm the new Postgres `~`
  regex/`lower()`/`trim()` CHECK SQL actually executes as intended.
  - One **Low** finding: `test_direct_sql_embedded_space_provider_or_source_rejected`
    only tested the slug-format violation via direct SQL, not the ORM path (unlike
    the non-ASCII case, which had both). Fixed: added
    `test_embedded_space_provider_or_source_rejected_on_orm_path`.
  - No Critical/High/Medium findings. Explicitly checked and clean: no path lets
    validated `provider`/`source` violate the new CHECK; whitespace/root-dot edge
    cases (bare `.`, doubled dot, userinfo ordering, all-whitespace, IP-with-dot,
    `%20`) all behave correctly; no array/JSONB columns; the three partial-index
    definitions are byte-identical before/after; both concurrency tests construct
    `JobOccurrence` directly and are unaffected by the factory change;
    `monkeypatch.setitem` on the module-level allow-list dict is guaranteed
    torn down by pytest regardless of test outcome; migration/model CHECK names and
    SQL text are byte-identical; `docs/DATA_MODEL.md`'s new "Rev 16" section matches
    actual code behavior; the whitespace-rejection behavior change is documented for
    Phase 2's future consumer in both the module docstring and DATA_MODEL.md.
- Files changed:
  - `backend/app/normalization/url.py` — whitespace rejection, root-dot stripping,
    allow-list canonicalization.
  - `backend/app/db/models/job_occurrence.py` — `provider_slug_format`/
    `source_slug_format` CHECKs, docstring update.
  - `backend/migrations/versions/0011_job_occurrences.py` — matching CHECKs (amended
    in place; migration not yet merged to `main`).
  - `backend/tests/conftest.py` — `make_job_occurrence`/`real_committed_job_occurrence`
    compute `source_url_normalized` by default.
  - `backend/tests/test_job_occurrences.py` — 22 new/rewritten tests (root-dot
    equivalence, embedded-whitespace rejection ×6, outer-wrapper-whitespace,
    percent-encoded-whitespace, allow-list canonicalization, non-ASCII/embedded-space/
    leading-hyphen slug-format rejection ×3 columns×ORM+direct-SQL, slug-format
    positive case, rewritten non-auto-derivation and null/null fallback tests).
  - `docs/DATA_MODEL.md` — "Rev 16 corrections" note; updated `provider` column row
    and the Phase 1 constraints-summary row for the new CHECK.
- Commands run and exact results:
  - `python scripts/check_repo.py` (from `backend/`) → exit 0, zero findings (checked
    before and after the `origin/main` merge).
  - `ruff format --check .`, `ruff check .` → passed (48 files).
  - `mypy app tests scripts` → success, 36 source files.
  - `pytest tests/test_job_occurrences.py -q` → 150 passed (up from 128).
  - `pytest -q` (full suite) → 663 passed (up from 641).
  - `DATABASE_URL=...jobgoblin_test`: `alembic downgrade 0010` / `upgrade head`
    (reapply amended `0011`), round-trip, `downgrade base` / `upgrade head` (fresh
    `base -> head`, re-run again after the `origin/main` merge), `alembic check`
    (`No new upgrade operations detected` — same informational `Computed`-column
    warning as before) — all passed.
  - `alembic current` against the **development** database (no override) → `0006`,
    unchanged throughout.
  - `git status`/`git diff --check` → only the files listed above; no whitespace/
    conflict errors. Merge commit contains only `docs/LLM_WORKFLOW.md` from `main`.
- Deviations/known limitations: none new. `raw_job_ingestions`, `identity_conflicts`,
  `duplicate_groups`, and the actual match-precedence application logic remain
  unimplemented, per explicit scope (unchanged from Iteration 1).
- STOP — awaiting Codex re-review. Do not begin any later table, ingestion, providers,
  normalization, reconciliation, add CI, or modify `main`.

### Work review

*Pending — awaiting Codex re-review.*
