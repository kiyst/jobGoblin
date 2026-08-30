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

---

## Iteration 2

### Work done

- Date/agent: 2026-08-30, Claude Code (Sonnet 5). Class H correction pass on
  `tooling/workflow-v3-routine-verifier` for the three bounded findings in
  review commit `103fbaa` (`6000658..103fbaa`). Base `6000658`. Addresses
  exactly Findings 1-3 from Iteration 1's `Work review`; every
  otherwise-accepted routine-verifier behavior (safety extraction, command
  structure, direct repository-check step, focus validation, non-recursive
  tests, database preflight/redaction, unique run directories, Workflow-v3
  durable rules, Phase-2 status, result model) is unchanged.
- Outcome, addressing each finding exactly:
  1. **Medium — `git diff --check` now works in the Codex reviewer
     environment.** `git_diff_check_command()` returns
     `["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "diff",
     "--check"]` — command-local via `-c`, never global/user Git config.
     `REPO_ROOT.as_posix()` (forward slashes) because Git's config-value
     parser treats a bare backslash as an escape character, which a raw
     Windows path would otherwise trip. Added
     `test_git_diff_check_command_is_the_one_non_python_step`'s exact-argv
     assertion (including a `no backslash` check) and reran the genuine
     `python scripts/verify.py --level routine --focus tests/test_verify.py`
     from both `backend/` and the repository root.
  2. **Medium — temporary-directory cleanup now fails closed and is its own
     reported step.** `safe_rmtree()` now refuses `path == must_be_under`
     (a strict-child check, not merely `is_relative_to`, which is trivially
     true of a path and itself) and never passes `ignore_errors=True` — its
     new injectable `remove` parameter (default `shutil.rmtree`) lets a
     deletion failure propagate to the caller instead of being swallowed.
     New `cleanup_run_dir_step()` wraps it as a PASS/FAIL `StepResult`; new
     `_execute_and_cleanup()` runs the step list, then *always* appends the
     cleanup result in a `finally` — including after an earlier verification
     failure — before returning. `main()` now builds its exit code from
     *all* results, so a failed cleanup alone makes the run exit nonzero.
     Added 8 tests: root-refusal, a genuinely-surfaced deletion failure (via
     injected `remove`, since real filesystem permission failures are
     unreliable to simulate portably), a nonexistent-child deletion now
     correctly raising instead of silently succeeding, `cleanup_run_dir_step`
     PASS/FAIL reporting, and — via `_execute_and_cleanup` — cleanup still
     running and reported after an earlier step's failure, a surfaced
     cleanup failure making the overall result set non-all-PASS, and
     concurrent-run isolation (cleaning up one invocation's directory never
     touches a second, still-active one).
  3. **Low — corrected the remaining stale Phase-1 ROADMAP statements.**
     `docs/ROADMAP.md`: "Phase 1: in progress (updated 2026-08-28)" ->
     "Phase 1: complete (updated 2026-08-30)"; removed the closing claim that
     "the rest of Phase 1's exit gate... remains to be independently
     verified before declaring the phase complete", replaced with the
     Git-verified basis for completion — all fifteen tables migrated, the
     `phase-1/closure` slice merged (`bfdd56d`), and Phase 2 subsequently
     authorized and three vertical slices merged, which
     `PHASE_RISK_CHECKLIST.md`'s own phase-gating rule could not have
     permitted had Phase 1's exit gate not already been satisfied. The
     already-correct three-slice Phase-2 paragraph is untouched. Recorded
     here, in this new entry — Iteration 1's historical `Work done`/
     `Work review` text is left exactly as written.
- Files changed: `backend/scripts/verify.py`; `backend/tests/test_verify.py`;
  `docs/ROADMAP.md`; this handoff. No migration; no product code; no
  `db_safety.py` change (Finding 1/2 are both `verify.py`-local).
- Commands run and exact results:
  - `ruff format .` / `ruff check .` -> clean.
  - `mypy app tests scripts` -> clean, 76 source files.
  - `python -m pytest tests/test_verify.py -q` -> **73 passed** (was 65;
    net +8 for this pass's new/replaced cleanup and Git-argv tests).
  - Full suite with a workspace-local `--basetemp` -> **1249 passed** (was
    1241).
  - `python -m scripts.check_repo` -> exit 0, zero findings (confirms the
    ROADMAP.md edits introduced no broken links/anchors and no stale
    migration-revision references — `bfdd56d` is a commit hash, not a
    4-digit migration revision, so it does not trip that check).
  - `git diff --check` -> clean (benign LF/CRLF notices only).
  - **Genuine external verifier reruns** (never from inside pytest): both
    `cd backend && python scripts/verify.py --level routine --focus
    tests/test_verify.py` and the repository-root equivalent
    (`python backend/scripts/verify.py --level routine --focus
    tests/test_verify.py`) -> all **10** steps PASS in each run, including
    the new `temporary-directory cleanup` step; `focused pytest` **73
    passed**, `full pytest suite` **1249 passed**.
  - `.verify-tmp/` confirmed to contain only the empty, gitignored root after
    every run in this pass.
- Adversarial self-review (fresh read of the corrected diff before this
  entry): confirmed the strict-child check is evaluated *before*
  `is_relative_to` specifically because `Path.is_relative_to` is trivially
  true of a path compared to itself — without the explicit `resolved ==
  root` branch, the prior code would have let `must_be_under` itself reach
  `remove()`, exactly the defect Codex found. Confirmed `_execute_and_cleanup`
  correctly appends the cleanup result even when `_run_steps` itself never
  raises (the normal case, including the fail-fast/NOT-RUN path) and traced
  that an unexpected exception escaping `_run_steps` would still run cleanup
  via `finally` before re-propagating (a genuine crash, not a reported
  result — outside this finding's scope, unchanged from before). Confirmed
  `main()`'s `remove=` is never overridden from its real default in
  production, only in tests. Found no further issues beyond the three
  findings addressed above.
- Deviations/known limitations: unchanged from Iteration 1 (no CI, markers,
  `--level schema`/`--level high-risk`, status generator, metrics, or
  handoff automation; `--level` choices remain `["routine"]` only). `main`
  untouched throughout.
- STOP — awaiting Codex re-review. Do not add CI, schema/high-risk levels,
  markers, status automation, handoff automation, metrics, or resume product
  work, or merge `main`.

### Work review

- Date/agent: 2026-08-30, Codex. Correction diff reviewed:
  `103fbaa..1f54e20` on `tooling/workflow-v3-routine-verifier`.
- All three findings from review commit `103fbaa` are closed:
  1. The Git step now applies the script-derived repository path through a
     command-local `-c safe.directory=...` with forward slashes, never global
     configuration. It succeeds in the Codex reviewer environment that
     reproduced the original failure.
  2. Cleanup now requires a strict resolved child, refuses the temp root,
     propagates removal failures into a reported cleanup result, always runs
     after verification, and participates in the overall exit decision.
  3. ROADMAP now marks Phase 1 complete and removes the stale outstanding-
     exit-gate claim while preserving the correct three-slice Phase-2 status.
- Independent verification used the new canonical command itself:
  `python scripts/verify.py --level routine --focus tests/test_verify.py`.
  All **10 steps passed**: Ruff format/check, mypy, repository checker, Git
  diff check, database URL safety, real test-database reachability, focused
  pytest **73 passed**, full suite **1249 passed**, and temporary-directory
  cleanup. The `.verify-tmp` root was independently confirmed empty afterward;
  working tree clean.
- Findings: none.
- **Verdict: approved.** The Workflow-v3 routine-verifier foundation and its
  correction pass are accepted. STOP — do not merge this branch into `main`,
  add schema/high-risk levels or CI/markers/status/handoff automation, or
  resume Phase-2 product work until the user explicitly authorizes the next
  action.

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `0c9787b` (no findings). Per user authorization,
`tooling/workflow-v3-routine-verifier` was merged into `main` with a normal merge
commit (`257b6a5`; `--no-ff`, no squash/rebase/force-push) and pushed.
`main`/`origin/main` are both now at `257b6a5`. Verified: feature branch was clean
and pushed at `0c9787b` and `main`/`origin/main` were still at `adb6e62`
immediately before the merge; `main` has zero content diff against the feature
branch (`git diff main tooling/workflow-v3-routine-verifier --stat` empty);
migration `0017` remains the sole Alembic head; the canonical
`python scripts/verify.py --level routine` command itself was run against merged
`main` and reported **all 9 steps PASS** (Ruff format/check, mypy, `check_repo.py`,
`git diff --check`, database URL safety, real test-database reachability, full
suite **1249 passed**, temporary-directory cleanup) in `117.52s`; `.verify-tmp`
confirmed to contain no run directory afterward; development database reconfirmed
at `0006`; working tree clean.

**Rollback boundary:** reverting `257b6a5` (a single merge commit) restores `main`
to `adb6e62` exactly — no schema/migration exists in this slice to downgrade, and
no data migration accompanies it. This merges the Workflow v3 tooling program's
first slice only (the routine-verifier foundation: `scripts/verify.py --level
routine`, `scripts/db_safety.py`, the fail-closed temporary-directory cleanup
reported as its own step, the reviewer-safe `git diff --check` invocation, the
Phase-1-complete/three-slice-Phase-2 ROADMAP correction, and Workflow v3's durable
process rules in `docs/LLM_WORKFLOW.md`) — it does **not** add CI, pytest markers,
`--level schema`/`--level high-risk`, a canonical-status generator, handoff-
structure automation, process/performance metrics, or any Phase 2 product change,
all of which remain not started and are not authorized by this merge.
