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

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Class H correction pass on
  `phase-2/tier2-tier3-identity-attachment` for the single bounded finding in
  review commit `6eadd00` (`272afb8..6eadd00`). Base `272afb8`. Addresses
  exactly Finding 1 from Iteration 1's `Work review`; every otherwise-approved
  Tier-2/Tier-3 and Tier-1 behavior (precedence, candidate revalidation,
  `ATTACHED -> jobs_updated`, three-effect rollback boundary, existing-index
  reuse, Tier-4 deferral, parent-before-child lock order) is unchanged.
- Outcome, addressing the finding exactly:
  1. **Medium — Tier 1's initial probe no longer seeds the ORM identity map.**
     `_existing_occurrence_query()` (full entity, `FOR UPDATE`-chainable) is
     unchanged in shape but its domain-filter conditions are now shared via a
     new `_existing_occurrence_conditions()` helper. A new
     `_existing_occurrence_identity_query()` selects only the bare
     `JobOccurrence.id`/`job_id` scalar columns — never the ORM entity — and
     is what `upsert_job_occurrence`'s found branch now uses for the initial,
     unlocked probe. Because that probe never touches the identity map, the
     later `FOR UPDATE` load of `_existing_occurrence_query()` is always that
     row's *first* load into the session, so its `job_id` is guaranteed fresh
     from the database rather than a value cached from before a concurrent
     reassociation. The revalidation check (`occurrence.id`/`job_id` vs. the
     scalar probe) is otherwise unchanged — still fails closed with
     `CandidateResolutionUnstableError`, never a bare assertion. Added
     `test_tier1_reassociation_between_probe_and_lock_is_detected_not_stale`:
     two real, separately-committed PostgreSQL transactions (via
     `_before_tier1_parent_lock` + `asyncio.Event`s, mirroring the existing
     Tier-1-vs-parent-deletion test's shape) — transaction A pauses right
     after the scalar probe, transaction B reassigns the same occurrence's
     `job_id` to a second, independently existing Job and commits,
     transaction A resumes, locks the *original* parent (which still exists),
     loads the occurrence fresh, and fails closed with
     `CandidateResolutionUnstableError` before any mutation. Proved this is a
     genuine regression test, not vacuous, by temporarily reverting the probe
     to the full-entity query and confirming the test fails (it returned
     `UpsertKind.UPDATED` instead of raising) before restoring the fix and
     re-confirming green. Also proves neither Job's `last_seen_at` advances
     and the raw row stays `fetched`/unlinked. Updated
     `upsert_job_occurrence`'s docstring and ADR 0004's Phase-2 notes to
     describe the identity-map hazard and the scalar-probe correction.
- Files changed: `backend/app/ingestion/persistence.py`;
  `backend/tests/test_ingestion_pipeline.py`;
  `docs/DECISIONS/0004-scoped-deterministic-identity.md`; this handoff. No
  migration; no change to `natural_key.py`, `pipeline.py`, or
  `test_ingestion_concurrency.py`.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 73 source files.
  - Focused (`test_ingestion_pipeline.py` + `test_ingestion_concurrency.py`
    + `test_ingestion_natural_key.py`) -> **54 passed** (53 at `272afb8`, +1
    new reassociation regression).
  - Full suite with a workspace-local `--basetemp` -> **1176 passed** (was
    1175).
  - The four real-transaction concurrency tests (both pre-existing genuine
    races, the Tier-1-vs-parent-deletion one, and the new reassociation one)
    rerun 5x each in a stress loop -> stable, no flakiness, no timeouts.
  - `alembic check` (against `jobgoblin_test`) -> `No new upgrade operations
    detected`.
  - Development database (`alembic current`, default `DATABASE_URL`) ->
    `0006`, unchanged.
  - `python scripts/check_repo.py` -> exit 0, zero findings.
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - Table-count queries against `jobgoblin_test` after the full run, and
    after the deliberate revert-and-fail run below -> every ingestion-related
    table at 0 rows both times; no leaked test data, including on the
    intentional failure path.
- Adversarial self-review (fresh read of the complete corrected diff before
  this entry): rather than only reasoning about the fix, empirically proved
  the new test is a genuine regression guard by reverting the probe to
  `_existing_occurrence_query()` (loading the full entity) and rerunning it
  in isolation — it failed with the stale `job_id` silently accepted
  (`UpsertKind.UPDATED` returned instead of the exception), and its own
  `finally`-based cleanup still left zero leaked rows even on that induced
  failure; then restored the fix and reconfirmed green. Confirmed
  `_discover_candidates` (Tier 2/3's own candidate discovery) has no
  analogous defect: it already selects only the scalar `job_id` column and
  never loads a `JobOccurrence` entity before the candidate's `Job` lock, so
  Tier 2/3's `_attach_to_candidate` was never exposed to this identity-map
  hazard in the first place. Confirmed the `Job` `FOR UPDATE` load in Tier
  1's found branch is likewise always a first load (nothing earlier in that
  transaction touches `Job` via the ORM). Found no further issues beyond the
  one finding addressed above.
- Deviations/known limitations: none beyond those already disclosed in
  Iteration 1 (Tier 4's deferral; `ambiguous_match` persistence and its
  evidence shape as a separate future slice; multiple-candidate failures are
  whole-run, not per-posting-isolated, until that future slice lands).
  `QueryPlanner`, `ProviderRegistry`, multi-source partial-success handling,
  live providers, Phase 3 normalization, API routes, scheduling, and the
  workflow-automation/tooling slice remain explicitly out of scope. `main`
  untouched throughout.
- STOP — awaiting Codex re-review. Do not begin `ambiguous_match`, Tier 4,
  `QueryPlanner`, `ProviderRegistry`, multi-source handling, live providers,
  normalization, APIs, scheduling, the workflow-automation/tooling slice, or
  modify/merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Correction diff reviewed:
  `6eadd00..370af23` on
  `phase-2/tier2-tier3-identity-attachment`.
- The remaining finding from review commit `6eadd00` is closed:
  `_existing_occurrence_identity_query()` now probes only bare `id`/`job_id`
  columns and therefore cannot seed SQLAlchemy's ORM identity map. After the
  parent `Job` lock, `_existing_occurrence_query().with_for_update()` performs
  the entity's first session load and compares its fresh database `id` and
  `job_id` against the scalar probe before any mutation. Shared conditions
  keep the two query shapes aligned.
- The new two-transaction regression pauses after the scalar probe, commits a
  real reassociation to a second parent, and proves
  `CandidateResolutionUnstableError`, unchanged observational state on both
  Jobs and the occurrence, and a fetched/unlinked raw row. Its timeout,
  `finally` release, and cleanup cover the prior test-hygiene requirements.
- Independent proportionate verification: repository checker exit 0; Ruff
  format/check clean; mypy clean across **73 source files**; focused suite
  **54 passed**; `alembic check` against `jobgoblin_test` reports no drift;
  `git diff --check` clean; working tree clean. The correction is localized,
  so the independently reported full-suite **1176 passed** result was not
  redundantly repeated in this re-review.
- Findings: none.
- **Verdict: approved.** The Tier-2/Tier-3 cross-occurrence identity-
  attachment slice and all correction passes are accepted. STOP — do not
  merge this branch into `main`, begin `ambiguous_match`/Tier 4 or another
  product slice, or start workflow-automation tooling until the user
  explicitly authorizes the next action.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `b235d18` (no findings). Per user authorization,
`phase-2/tier2-tier3-identity-attachment` was merged into `main` with a normal
merge commit (`1f4f787`; `--no-ff`, no squash/rebase/force-push) and pushed.
`main`/`origin/main` are both now at `1f4f787`. Verified: feature branch was
clean and pushed at `b235d18` and `main`/`origin/main` were still at `bd59a14`
immediately before the merge; `main` has zero content diff against the feature
branch (`git diff main phase-2/tier2-tier3-identity-attachment --stat` empty);
migration `0017` remains the sole Alembic head; `python
backend/scripts/check_repo.py` exits 0 with zero findings; `git diff --check`
clean; development database reconfirmed at `0006`; working tree clean.

**Rollback boundary:** reverting `1f4f787` (a single merge commit) restores
`main` to `bd59a14` exactly — no schema/migration exists in this slice to
downgrade, and no data migration accompanies it (Tier-3's supporting index,
`ix_job_occurrences_tenant_requisition_lookup`, already existed before this
slice). This merges Phase 2's fourth vertical slice only (Tier-2/Tier-3
cross-occurrence identity attachment: mutually exclusive Tier-2/Tier-3
precedence, single-pass fail-closed candidate resolution,
`AmbiguousIdentityMatchError`/`CandidateResolutionUnstableError`, the new
canonical-URL/tenant-requisition advisory-lock domain, `UpsertKind.ATTACHED`,
the corrected global parent-before-child lock discipline including Tier 1's
own found-branch fix, and the scalar-probe fresh-entity revalidation) — it
does **not** complete Phase 2. `ambiguous_match` persistence, Tier 4, the
company-resolution prerequisite it depends on, `QueryPlanner`,
`ProviderRegistry`, multi-source partial-success handling, live providers,
Phase 3 normalization, API routes, scheduling, and the workflow-automation
tooling slice all remain not started and are not authorized by this merge.

---

## Iteration 2

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Authorized slice: Workflow v3
  automation/tooling program, **first bounded slice — routine-verifier
  foundation** — Class H (safety-relevant database-target logic; otherwise
  Class R tooling). Base `main`@`adb6e62` -> branch
  `tooling/workflow-v3-routine-verifier`. Implements exactly the approved
  proposal's first slice with the 11 binding clarifications; no CI, markers,
  `--level schema`/`--level high-risk`, status generator, metrics, or handoff
  automation.
- Outcome, per the binding clarifications:
  1. **`backend/scripts/db_safety.py`** — `assert_is_disposable_test_database`,
     its `_redact` helper (renamed `redact_database_url`, same body), and
     `DEFAULT_TEST_DATABASE_URL` moved out of `tests/conftest.py` verbatim
     (behavior/exception type/redaction/conservative name-only comparison all
     unchanged — proven by `test_users.py`'s 9 existing assertions passing
     unmodified against the new import path). New `resolve_test_database_url()`
     factors out the `test_database_url or DEFAULT_TEST_DATABASE_URL` fallback
     so `conftest.py`'s `db_engine` fixture and `verify.py` share one
     expression, never two copies. Deliberately not under `app/db/` — tooling
     only, never packaged (`pyproject.toml` ships only `app/`).
  2. **`backend/scripts/verify.py --level routine`** — runs, in order: Ruff
     format check, Ruff lint, mypy, `check_repo.py` (its own subprocess step,
     `-m scripts.check_repo`, never assumed covered merely by
     `test_check_repo.py`'s in-process function tests), `git diff --check`, a
     pure URL-parsing disposable-test-database validation (dev DB need not be
     reachable), a real test-database reachability preflight (must succeed
     before pytest runs), optional focused pytest when `--focus` is given, then
     the full suite. Every step reports PASS/FAIL/NOT RUN with a duration;
     first failure blocks all later steps as NOT RUN rather than silently
     omitting them. Every tool invocation is `[sys.executable, "-m", ...]`
     (`git diff --check` is the one necessary exception) — identical on
     Windows and Linux, confirmed by real runs from both `backend/` and the
     repository root.
  3. **`.verify-tmp/<unique-per-run>/`** — `create_run_dir()` uses
     `tempfile.mkdtemp` under a gitignored `.verify-tmp/` root; `safe_rmtree()`
     resolves both paths and refuses to delete anything not actually located
     under that root (proven against a `.verify-tmp-evil` lookalike-prefix
     attempt, not just a naive string check) before removing only that
     invocation's own directory in `finally`.
  4. **`--focus`** accepts file paths and `path::node_id` targets; each is
     validated (no leading `-`; the pre-`::` portion must resolve to a real
     file under `backend/tests`) before being passed to pytest as argv list
     elements, never a shell string. Focused and full-suite results are
     reported as separate steps; routine verification always runs the full
     suite regardless of `--focus`.
  5. **No recursive pytest invocation**: `test_verify.py`'s 65 tests inject a
     fake subprocess runner and/or a fake connectivity check everywhere;
     `verify.main()` is never called from any test (confirmed by grep). The
     genuine end-to-end `python scripts/verify.py --level routine` command was
     run for real, repeatedly, outside pytest — see Commands below.
  6. **Pytest result parsing**: `parse_pytest_summary()` scans backward for
     pytest 8.3.4's real summary line, handling both the framed and `-q`
     unframed shapes and the optional parenthesized `(H:MM:SS)` suffix pytest
     appends on longer runs. **Found and fixed during verification**: the
     first version didn't anticipate that suffix, so a genuine full-suite run
     ("1235 passed in 101.82s (0:01:41)") reported PASS but "counts
     unavailable" — never a wrong or invented count, but not the intended
     accurate report either. Fixed and reconfirmed against a real run.
  7. **`docs/LLM_WORKFLOW.md`** now durably contains: a `Definition of Ready`
     section; three named review verdicts (Approved / Approved with binding
     clarifications / Redesign required); a concise-amendments-not-full-
     rewrites rule; a two-round Class H revision limit with a joint-decision-
     table fallback; a required-invariants-vs-recommended-mechanisms
     distinction; a `Verification matrix` note pointing at `verify.py` as the
     canonical way to run its "Python without schema" row once a level exists.
     `docs/PHASE_RISK_CHECKLIST.md` was deliberately **not** touched — it
     already contains a generic pointer to `LLM_WORKFLOW.md` for exactly this
     content, so no additional pointer was needed.
  8. **Corrected known-stale status now**: `README.md` no longer claims
     "Phase 1 in progress, users-only"; `docs/ROADMAP.md` no longer claims
     "two Phase 2 slices merged" / Tier-2/Tier-3 "not yet merged" — both now
     state the Git-verified truth (three Phase 2 vertical slices merged
     through `main`@`adb6e62`, confirmed via `git log --oneline --merges main`
     before writing either correction). No status generator was built.
     `README.md`'s Verification section now leads with
     `python scripts/verify.py --level routine`; the prior manual chain
     remains as an explicitly-labeled troubleshooting/reference fallback, now
     also including `git diff --check` (missing from the original chain) so
     it doesn't silently under-represent what the canonical command runs.
  9. **Roadmap ordering correction recorded, not implemented**: routine
     verifier (this slice) -> schema level -> minimal CI (routine/schema only)
     -> high-risk level + incremental marker adoption -> canonical-status/
     handoff validators -> mechanically-derived metrics. CI is explicitly not
     gated behind complete marker adoption or high-risk orchestration.
- Files changed: `backend/scripts/verify.py` (new), `backend/scripts/db_safety.py`
  (new), `backend/tests/test_verify.py` (new, 65 tests), `backend/tests/conftest.py`,
  `backend/tests/test_users.py`, `backend/app/config.py` (one-line comment fix,
  found by adversarial review — see below), `.gitignore`, `README.md`,
  `docs/LLM_WORKFLOW.md`, `docs/ROADMAP.md`, this handoff. `docs/PHASE_RISK_CHECKLIST.md`
  deliberately not touched. No migration; no CI YAML; no product code changed.
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean on all changed/new files.
  - `mypy app tests scripts` -> clean, 76 source files (was 73).
  - `python -m pytest tests/test_verify.py -q` -> **65 passed** (unit tests
    only; never launches a real subprocess or calls `main()`).
  - `python -m pytest tests/test_users.py -q` -> **26 passed**, unchanged,
    proving the `db_safety.py` extraction is behavior-preserving.
  - Full suite with a workspace-local `--basetemp` -> **1241 passed** (was
    1176 on `main`; +65 new unit tests).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - **Genuine external `python scripts/verify.py --level routine`** (never
    from inside pytest), run repeatedly across fixes: final run -> all 8
    steps PASS, `1241 passed`, `108.33s` total; also run successfully from
    the repository root (not just `backend/`) with identical behavior; also
    run with `--focus tests/test_ingestion_hashing.py` -> focused (5 passed)
    and full-suite steps both reported separately, both PASS.
  - Adversarial external runs (real invocations, not just unit tests):
    `TEST_DATABASE_URL` malformed -> `disposable test-database URL
    validation` FAILs cleanly with `ArgumentError` (see finding below), no
    crash, no credential leak, pytest steps NOT RUN; `TEST_DATABASE_URL`
    equal to the dev database -> same step FAILs with the guard's own safe
    message, pytest steps NOT RUN; `TEST_DATABASE_URL` safely-named but
    unroutable (port 1) -> URL validation PASSes, reachability preflight
    FAILs with `unreachable: ConnectionRefusedError` (type name only), full
    suite correctly NOT RUN rather than silently skipped/passing; `--focus`
    given a `-`-prefixed or path-outside-`backend/tests` target -> rejected
    before any step runs, exit 2.
  - Development database (`alembic current`, default `DATABASE_URL`) ->
    `0006`, unchanged; no migration touched.
  - `.verify-tmp/` confirmed empty (only the gitignored root itself remains)
    after every genuine run, including the deliberately-failing adversarial
    ones.
- Adversarial self-review: dispatched a fresh subagent (no prior context on
  this diff) to independently check all 11 binding requirements plus general
  correctness against the actual repository. It found and I fixed **two Low
  findings**, both documentation drift this slice's own refactor introduced:
  `app/config.py`'s comment on `test_database_url` still named
  `tests/conftest.py` as `DEFAULT_TEST_DATABASE_URL`'s home (now
  `scripts/db_safety.py`); `README.md`'s "Dedicated test database" section
  still named `tests/conftest.py::assert_is_disposable_test_database` as the
  guard's defining location (now `scripts/db_safety.py`, re-imported by
  `conftest.py`). Both fixed; full verification matrix rerun clean afterward.
  Separately, I found and fixed the pytest-summary-parser gap under item 6
  above by running the genuine full suite and noticing "counts unavailable"
  where a count was expected — the pinned-shape assumption was incomplete,
  not the parsing logic's fail-closed behavior, which worked exactly as
  designed (reported unavailable, never invented zero). No other findings
  from either pass.
- Deviations/known limitations: `redact_database_url`'s em-dash character in
  `assert_is_disposable_test_database`'s message can render as a mangled
  glyph on a non-UTF-8 Windows console codepage when printed — a pre-existing
  cosmetic property of the message string itself (moved verbatim, not
  introduced by this slice), not a data-correctness issue. `--level schema`/
  `--level high-risk`, CI, markers, the status generator, handoff-structure
  validation, and process metrics remain explicitly out of scope, per the
  recorded roadmap ordering. `main` untouched throughout.
- STOP — awaiting Codex review. Do not add CI, resume Phase 2 product work,
  begin `--level schema`/`high-risk`, markers, the status generator, metrics,
  or handoff automation, or merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Diff reviewed:
  `adb6e62..6000658` on `tooling/workflow-v3-routine-verifier`.
- Independent verification: repository checker exit 0; Ruff format/check
  clean; mypy clean across **76 source files**; focused verifier/safety suite
  **91 passed**; working tree clean after review cleanup. A genuine external
  `python scripts/verify.py --level routine --focus tests/test_verify.py`
  run did **not** pass: its first four steps passed, then `git diff --check`
  failed with exit 129 because the subprocess did not apply this repository's
  required command-local `safe.directory`; all database/pytest steps were
  correctly reported `NOT RUN`.
- Findings:
  1. **Medium — the canonical verifier is not usable by the Codex reviewer
     environment it is explicitly intended to unify with Claude/local/CI.**
     `git_diff_check_command()` returns bare `git diff --check`; this checkout
     requires `-c safe.directory=C:/Users/Throw/Desktop/gitProjects/jobGoblin`
     for Git commands under the reviewer SID, so the advertised identical
     external invocation fails before pytest. Build the Git command with the
     script-derived, absolute `REPO_ROOT` as command-local
     `git -c safe.directory=<REPO_ROOT> diff --check` (never mutate global Git
     configuration), unit-test the exact argv, and rerun the genuine verifier
     from both repository root and `backend/` in the reviewer-compatible
     environment.
  2. **Medium — temporary-directory cleanup fails open and is absent from the
     result summary.** `safe_rmtree()` uses `ignore_errors=True`; `main()`
     prints/returns a successful summary before cleanup in `finally`. A
     permission failure can therefore leave `.verify-tmp/run-*` behind while
     the canonical verifier reports all checks passed, reproducing the exact
     stale-directory problem this slice is meant to eliminate. Require a
     strict child (`resolved != root` as well as `is_relative_to(root)`), do
     not ignore deletion errors, execute cleanup on every path, and include a
     `temporary-directory cleanup` PASS/FAIL result before printing the final
     summary/choosing the exit code. Add tests for refusing the root itself,
     surfaced deletion failure/nonzero outcome, cleanup after an earlier
     verification failure, and successful concurrent-run isolation.
  3. **Low — the known Phase-1 status correction is incomplete and the new
     handoff overclaims it.** `README.md` says Phase 1 is complete, but
     `docs/ROADMAP.md:134` still begins “Phase 1: in progress,” and its closing
     Phase-1 paragraph still says the exit gate remains to be verified before
     declaring completion. Phase 1's closure was already merged. Correct both
     stale ROADMAP statements to the Git-verified completed state; keep the
     already-correct three-slice Phase-2 update. Record the correction in a
     new `Work done` entry rather than rewriting historical ledger text.
- **Verdict: changes requested.** The safety extraction, command structure,
  direct repository-check step, focus validation, non-recursive tests,
  database preflight/redaction, unique run directories, Workflow-v3 durable
  rules, Phase-2 status, and routine-verifier result model are otherwise
  accepted. Make only the three bounded corrections above, run the genuine
  verifier end to end plus focused/static checks, append concise `Work done`,
  commit and push, then stop for re-review. Do not add CI/schema/high-risk
  levels or resume product work.
