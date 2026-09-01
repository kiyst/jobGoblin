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

- Date/agent: 2026-08-31, Codex acting as the user-authorized implementer. Class R
  tooling slice on `codex/tooling-safe-compaction`, based on clean
  `main@10b9432`. Outcome: safe Claude Code compaction policy plus automatic,
  credential-free recovery snapshots around built-in manual/auto compaction.
- Added root `CLAUDE.md` with durable compact instructions: preserve current
  authorization, Git state, active slice/verdict, unresolved decisions, safety
  invariants, verification, external side effects, rollback boundaries, and recovery
  document pointers; discard superseded conversation detail recoverable from Git.
- Added project hooks in `.claude/settings.json` and
  `.claude/hooks/compact_checkpoint.py`:
  - `PreCompact(manual|auto)` atomically snapshots only Git refs/cleanliness,
    trigger, classification, and documentation pointers under ignored
    `.claude/runtime/`.
  - `SessionStart(compact)` injects that checkpoint after compaction and requires
    reconciliation against current Git/docs before any state-changing action.
  - Hooks never store transcript content, compacted summaries, environment values,
    database URLs, credentials, or source-file contents; they perform no network or
    database operation and never block emergency auto-compaction.
- Safe-moment policy: clean synchronized `main` after a verified merge-record commit
  is optimal; a clean pushed feature branch stopped at committed `Work done`/
  `Work review` is secondary/recoverable. Proactive manual compaction is not requested
  amid uncommitted work, running verification, external/destructive activity,
  incomplete handoff writing, or unresolved corrections. Claude Code exposes no safe
  project hook to force `/compact` at a semantic milestone, so this slice deliberately
  does not launch a nested Claude process or lower the automatic threshold.
- Added nine offline tests for optimal/fail-closed classification, pushed-feature and
  dirty-tree states, credential/transcript exclusion, atomic write/cleanup, and restore
  output. A real hook simulation correctly classified this dirty implementation branch
  as unsafe for proactive compaction and restored the snapshot; no secret or external
  state was accessed.
- Verification: genuine external
  `python scripts/verify.py --level routine --focus tests/test_compact_checkpoint.py`
  completed all **10 steps PASS**: Ruff format/check, mypy, repository checker,
  `git diff --check`, database URL safety/reachability, **9 focused tests**, **1379
  full-suite tests**, and temporary-directory cleanup in 129.86s. Settings JSON parsed
  successfully; direct pre/restore hook simulation succeeded.
- Files changed: `CLAUDE.md`, `.claude/settings.json`,
  `.claude/hooks/compact_checkpoint.py`, `.gitignore`, `docs/LLM_WORKFLOW.md`,
  `backend/tests/test_compact_checkpoint.py`, and this handoff entry. No product,
  schema, migration, provider, ingestion, database, or network behavior changed.
- STOP — awaiting independent review. Do not merge to `main`, begin another product
  slice, or treat a compacted summary as new authorization.

### Work review

- Date/agent: 2026-09-01, Claude Code (Sonnet 5), acting as independent reviewer of
  `codex/tooling-safe-compaction`. Diff reviewed: `10b9432..c750762` (7 files: `CLAUDE.md`,
  `.claude/settings.json`, `.claude/hooks/compact_checkpoint.py`, `.gitignore`,
  `docs/LLM_WORKFLOW.md`, `backend/tests/test_compact_checkpoint.py`, this handoff).
  Confirmed no product/schema/migration/provider/ingestion file changed.
- Independent verification performed: read every changed file directly (not the Work
  done summary alone); ran the genuine external
  `python scripts/verify.py --level routine --focus tests/test_compact_checkpoint.py`
  from `backend/` — all **10 steps PASS**, **9 focused tests**, **1379 full-suite tests**,
  matching the claimed counts exactly. Dispatched a fresh-context documentation-verification
  pass (no prior context on this diff) against Claude Code's own published hooks/memory
  documentation to check the claims below rather than trusting either my own or the
  implementer's assumptions about undocumented behavior.
- Checks explicitly requested by the user, with results:
  - **`PreCompact`/`SessionStart(compact)` hook registration**: confirmed both are real,
    documented Claude Code hook events; `SessionStart`'s documented matcher values include
    `compact`; matchers are regex, so `"manual|auto"` correctly matches either trigger.
    `${CLAUDE_PROJECT_DIR}` is a real, documented substituted variable. (No literal `/hooks`
    TUI view is reachable from this non-interactive harness; verified via direct
    `.claude/settings.json` inspection plus external documentation confirmation instead.)
  - **Root `CLAUDE.md` loading**: confirmed Claude Code auto-loads a root `CLAUDE.md` and
    explicitly re-reads/re-injects it after `/compact` (no `/memory`/`/status` view
    reachable from this harness either; confirmed via the file's presence at the documented
    location plus external documentation).
  - **`PreCompact` never blocks emergency auto-compaction**: verified by construction —
    `main()`'s `"pre"` branch wraps `write_checkpoint()` in a bare `except Exception` and
    always returns `0`; the function never writes anything to stdout in that mode. This
    matches every documented Claude Code hook-blocking mechanism (nonzero exit; a stdout
    `"decision"`-shaped field) with neither present. `PreCompact`'s own blocking mechanism
    specifically is not independently documented in what the verification pass could reach,
    so this is "non-blocking by construction," not "non-blocking per cited spec" — worth
    recording as a residual documentation gap, not a code defect.
  - **Checkpoint contains only credential-free Git metadata and doc pointers**: confirmed by
    reading `render_checkpoint`/`capture_git_snapshot` — only branch/HEAD/main/origin-main/
    upstream strings, a clean boolean, a classification/reason string, and the fixed
    `RECOVERY_DOCS` path list. No `os.environ` access anywhere in the module.
  - **Atomic replacement and temp-file cleanup**: `tempfile.mkstemp` + `os.replace` (atomic
    and overwrite-safe on both POSIX and Windows) + `finally: unlink(missing_ok=True)`.
    Confirmed no leftover `.tmp` file after a successful write via the existing test.
  - **Clean synchronized `main` is the only OPTIMAL state**: confirmed — `optimal_checkpoint`
    and its four fail-closed parametrized cases (dirty, wrong branch, stale `origin/main`,
    stale `main`) are all correctly implemented and tested.
  - **Dirty is unsafe; clean pushed feature branch is only recoverable**: confirmed via
    `pushed_feature_checkpoint` and both corresponding tests.
  - **Post-compaction restoration requires re-reading Git state and docs**: confirmed —
    stated in both the injected checkpoint's own "Mandatory recovery" section and
    independently in `CLAUDE.md` itself, doubly reinforced.
  - **No transcript/summary/env value/DB URL/credential/source content stored**: confirmed
    by code reading and the existing dedicated test (which also proves it even when a real
    `DATABASE_URL`-shaped env var is present in the process environment).
- Findings, by severity:
  1. **Medium — the routine verifier never lints or type-checks the new hook script.**
     `verify.py`'s `ruff_format_command()`/`ruff_check_command()` run against `.` with
     `cwd=BACKEND_DIR`, and `mypy_command()` scans only `app tests scripts` — all scoped
     inside `backend/`. `.claude/hooks/compact_checkpoint.py` lives at the repository root's
     `.claude/` directory and is covered by neither. Confirmed by running `ruff format
     --check`/`ruff check`/`mypy` directly against the file (all pass today), but nothing in
     the standard verification workflow enforces this going forward, and the Work done
     entry's "Ruff format/check, mypy ... PASS" phrasing does not make this scope gap
     explicit. No fix applied — flagged for the user/Codex to decide whether expanding
     `verify.py`'s scope is worth doing in a follow-up, since `verify.py` itself is
     explicitly out of this slice's stated file list.
  2. **Low-Medium — one of four checkpoint classifications is never asserted by name.**
     `checkpoint_classification()`'s fourth branch ("RECOVERABLE WITH RECONCILIATION" — clean,
     but neither an optimal main-sync nor a pushed-feature-equals-upstream state, e.g. clean
     `main` lagging `origin/main`, or a clean branch with no configured upstream at all) is
     reachable — one of the existing parametrized `test_optimal_checkpoint_fails_closed_when_main_state_differs`
     cases (`{"origin_main_head": "older"}`) even produces a snapshot that would resolve to
     it — but no test calls `checkpoint_classification()` on such a snapshot and asserts the
     resulting label/reason; only the unrelated `optimal_checkpoint` boolean is checked for
     those cases.
  3. **Low — `restore_context()`'s call site is not exception-guarded, unlike
     `write_checkpoint()`'s.** `main()`'s `"restore"` branch calls it directly; a present-but-
     unreadable checkpoint file (encoding error, permission error) would raise uncaught,
     exiting the `SessionStart(compact)` hook non-zero. The graceful fallback message only
     covers the *missing*-file case. Lower stakes than `PreCompact` (a failing `SessionStart`
     hook is not the emergency-compaction path this design is centrally protecting), but
     inconsistent with the module's own stated non-blocking posture.
  4. **Low — the temp-file cleanup path is proven only for the success case.**
     `test_write_checkpoint_is_atomic_and_restore_prints_it` confirms no `.tmp` file remains
     after a *successful* write; no test forces `os.fdopen`/`os.replace` to fail and confirms
     the `finally` block's `unlink(missing_ok=True)` still fires. Low severity because
     `main()`'s broad exception handling around `write_checkpoint()` already guarantees
     non-blocking behavior regardless of whether cleanup itself succeeds.
  5. **Informational — risk classification.** This slice is filed Class R; its central
     invariant (credential/env-var exclusion from a persisted artifact) is explicitly one of
     `LLM_WORKFLOW.md`'s own listed Class H triggers ("security/privacy"). Actual risk is low
     (Git-derived metadata only), and the verification depth already applied (full offline
     suite, genuine external routine-verifier run) matches Class H's own bar in practice — a
     labeling point, not a verification gap.
- Missing/inconclusive checks: no literal Claude Code `/hooks`, `/memory`, or `/status`
  interactive view was reachable from this non-interactive review harness; those specific
  checks were performed via direct file inspection plus an independent documentation-
  verification pass instead, as noted above. `PreCompact`'s own stdin field name/blocking
  mechanism is not independently confirmed against public documentation (see finding
  discussion above) — the code's behavior was verified by construction instead.
- Verdict: **Approved with binding clarifications** — the compaction-safety design,
  credential-exclusion guarantee, and non-blocking behavior are all independently confirmed;
  Findings 1-4 are bounded verification/robustness gaps, not design defects, and Finding 5 is
  informational only.
- Exact bounded correction, if the user authorizes one: address Findings 1-4 in
  `.claude/hooks/compact_checkpoint.py`, `backend/tests/test_compact_checkpoint.py`, and (only
  if the user separately authorizes expanding verification scope) `backend/scripts/verify.py`.
  No change to `CLAUDE.md`, `.claude/settings.json`, `.gitignore`, or `docs/LLM_WORKFLOW.md`
  is required by any finding above.
- STOP — do not merge `main`, begin the `ambiguous_match` slice, or treat this review as
  authorization for a correction pass until the user explicitly approves one.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-01, Claude Code (Sonnet 5). Class H correction pass on
  `codex/tooling-safe-compaction` for Findings 1-4 from review commit
  `58995c1` (`c750762..58995c1`). Base `58995c1`. Reclassified Class H (not
  the original Class R) because this pass directly touches
  context-recovery and credential-exclusion behavior — matching Finding 5's
  own observation in the review being corrected. No product code,
  `CLAUDE.md`, `.claude/settings.json`, database code, providers,
  ingestion, or the `ambiguous_match` proposal touched.
- **Documentation correction to the prior review, not a rewrite of it**: my
  own `58995c1` review stated `PreCompact`'s stdin `"trigger"` field and its
  blocking mechanism were not independently confirmed against public
  documentation (a fresh-context agent dispatch could not reach that
  specific section). The user's authorization for this correction pass
  states the full official `PreCompact` reference does document both: a
  `trigger` field with `manual`/`auto` values, and that returning exit code
  `2` or emitting `{"decision": "block"}` blocks compaction — with an
  explicit warning that blocking a recovery compaction triggered by a
  context-limit error would surface the original failure instead of
  preventing it. Recording this per the user's instruction, as a correction
  to the review's own residual uncertainty, not as newly independently
  re-verified by this pass: `compact_checkpoint.py`'s existing exit-0/
  no-decision-output behavior in `"pre"` mode is consistent with that
  spec either way. Iteration 1's own historical text is left exactly as
  written.
- Outcome, addressing each finding exactly:
  1. **Medium — the routine verifier now lints and type-checks the hook
     script on every run.** Added `CLAUDE_HOOKS_DIR = REPO_ROOT / ".claude" /
     "hooks"` to `scripts/verify.py`; `ruff_format_command()`/
     `ruff_check_command()`/`mypy_command()` now include it alongside the
     existing `backend/`-scoped targets. Confirmed empirically (`--show-settings`/
     `--verbose`) that both tools resolve `backend/pyproject.toml`'s own
     config for a path outside `backend/` when invoked with
     `cwd=BACKEND_DIR`, exactly as the existing targets already do — no new
     config file needed. The existing 10-step verifier structure is
     unchanged; only the Ruff/mypy steps' own argument lists grew. Updated
     `test_verify.py`'s three exact-command tests plus a new test proving
     `CLAUDE_HOOKS_DIR` resolves to the real directory containing
     `compact_checkpoint.py` (so the command tests aren't asserting
     coverage of an empty path).
  2. **Low-Medium — the "RECOVERABLE WITH RECONCILIATION" classification is
     now asserted by name.** New parametrized test covers both a clean
     `main` unsynchronized from `origin/main` and a clean feature branch
     with no configured upstream at all (`upstream_head=""`, matching
     `_git`'s own fail-safe for an unresolvable `@{upstream}`), asserting
     both `optimal_checkpoint`/`pushed_feature_checkpoint` are `False` and
     the classification/reason match exactly.
  3. **Low — `restore_context()` now fails safely for a present-but-broken
     checkpoint.** New `_read_checkpoint_safely()` catches `(OSError,
     ValueError)` (the latter covers `UnicodeDecodeError`) around the
     existence check and read, falling back to the exact same fixed,
     pre-existing safe message — never exception text, never a path other
     than the one already-named `CHECKPOINT_PATH` constant, never partial
     file content. `main()`'s `"restore"` branch additionally wraps
     `restore_context()` in a broad `except Exception`, mirroring the
     `"pre"` branch's own established defense-in-depth pattern, so the
     `SessionStart(compact)` hook cannot fail even from an unanticipated
     future regression. Added three tests: an actually-invalid-UTF-8 file
     on disk (no monkeypatching needed), an injected `Path.read_text`
     failure scoped to only the checkpoint's own path (delegates to the
     real method for anything else), and a forced `restore_context()`
     failure proving `main(["restore"])` still emits the fallback and
     returns `0`.
  4. **Addressed — atomic-replacement failure now has dedicated failure-path
     tests.** Two new tests inject an `os.replace` failure: one calls
     `write_checkpoint()` directly and confirms (a) no `.tmp` file remains
     in the runtime directory afterward and (b) a pre-existing, genuinely
     different prior checkpoint file is byte-for-byte untouched; the other
     calls the real `main(["pre"])` entry point under the same injected
     failure and confirms it still returns `0` — the existing `finally:
     temporary_path.unlink(missing_ok=True)` and the `"pre"` branch's
     existing broad exception handling were already correct; these tests
     newly prove it rather than leaving it implicit.
- Files changed: `.claude/hooks/compact_checkpoint.py`; `backend/scripts/
  verify.py`; `backend/tests/test_compact_checkpoint.py`; `backend/tests/
  test_verify.py`; this handoff. `CLAUDE.md`, `.claude/settings.json`,
  `.gitignore`, `docs/LLM_WORKFLOW.md` unchanged — confirmed by `git status`.
- Commands run and exact results:
  - Direct `ruff format`/`ruff check` against `backend/` and against
    `.claude/hooks/compact_checkpoint.py` explicitly -> clean.
  - `mypy app tests scripts` (now including `CLAUDE_HOOKS_DIR` via
    `mypy_command()`) -> clean, 82 source files.
  - `python -m pytest tests/test_compact_checkpoint.py tests/test_verify.py -q`
    -> **90 passed** (was 83 combined pre-pass: 9 + 74; net +7 in
    `test_compact_checkpoint.py`, +1 in `test_verify.py`).
  - Full suite -> **1387 passed** (was 1379).
  - `python -m scripts.check_repo` -> exit 0, zero findings.
  - `git diff --check` -> clean.
  - **Genuine external `python scripts/verify.py --level routine --focus
    tests/test_compact_checkpoint.py tests/test_verify.py`** -> all **10
    steps PASS** (Ruff format/check — now covering `.claude/hooks/` —,
    mypy — same —, `check_repo.py`, `git diff --check`, database URL
    safety, real test-database reachability, focused pytest **90 passed**,
    full suite **1387 passed**, temporary-directory cleanup) in `125.14s`.
  - No `/compact` was executed during this pass.
- Adversarial self-review: confirmed (a) `_read_checkpoint_safely()`'s
  `except (OSError, ValueError)` is reached before any partial content
  could be printed, since the `try` block's `return` is the only path that
  ever yields real file content; (b) the new `main()`-level `"restore"`
  guard prints the exact same fixed fallback text as the primary guard,
  never a different message that could itself leak something; (c) the
  atomic-replacement tests exercise `write_checkpoint()` and `main(["pre"])`
  through the real, unmodified code path — the injected failure is at
  `os.replace` only, so the temp-file creation, write, and `finally`
  cleanup are all genuinely exercised, not bypassed; (d) `CLAUDE_HOOKS_DIR`
  is a directory, not the specific file, so any future file added under
  `.claude/hooks/` is automatically covered without a further verifier
  change. Found no further issues beyond the four findings addressed above.
- Deviations/known limitations: none new. `main` untouched throughout; no
  merge performed.
- STOP — awaiting Codex re-review. Do not merge `main`, begin the
  `ambiguous_match` slice, or execute `/compact`.

### Work review

- Date/agent: 2026-09-01, Codex. Final correction diff reviewed:
  `58995c1..87f65d7` on `codex/tooling-safe-compaction`.
- Independent verification performed: inspected all five changed files and traced the
  verifier command construction, every checkpoint classification, safe-read/fallback
  flow, atomic replacement failure, prior-checkpoint preservation, and both hook entry
  points. Ran the genuine external routine verifier focused on
  `tests/test_compact_checkpoint.py` and `tests/test_verify.py`: all **10 steps PASS**,
  including **90 focused tests** and **1387 full-suite tests**. No `/compact`, network
  request, product operation, or database mutation was performed.
- Prior-finding disposition:
  1. **Medium finding closed.** The canonical verifier's existing Ruff format/lint and
     mypy steps now include the real repository-root `.claude/hooks/` directory. Exact
     argv and path existence are tested without adding a parallel or silently skipped
     verification path.
  2. **Low-Medium finding closed.** Both clean-but-unsynchronized state shapes assert
     `RECOVERABLE WITH RECONCILIATION` and its reason explicitly.
  3. **Low restore finding closed.** Missing, unreadable, invalidly encoded, and
     unexpectedly failing restore paths emit only the fixed recovery fallback and
     return success; exception text, checkpoint contents, and alternate paths are not
     exposed.
  4. **Low cleanup finding closed.** Injected atomic-replacement failure proves the
     temporary file is removed, the prior checkpoint remains byte-for-byte unchanged,
     and the real `pre` entry point returns zero.
  5. **Informational classification disposition accepted.** The correction was treated
     as Class H and received Class-H-equivalent verification depth; no historical entry
     was rewritten.
- Documentation clarification checked: the current official `PreCompact` reference
  documents the `trigger` values and blocking behavior. The hook returns success without
  a block decision and therefore leaves emergency automatic compaction unblocked.
- Adversarial cases checked: an unsynchronized clean tree cannot become optimal; an
  upstream-less feature branch cannot become pushed/recoverable; malformed checkpoint
  bytes and read failures cannot enter injected context; replacement failure cannot
  destroy the last valid checkpoint or leave its temporary candidate behind; future
  Python hooks placed in `.claude/hooks/` enter routine static analysis automatically.
  No further findings.
- Missing/inconclusive checks: a real interactive `/compact` was intentionally deferred
  to the optimal post-merge clean-`main` acceptance checkpoint. This review validates
  the offline hook boundaries and canonical verifier, not Claude Code's interactive UI.
- Verdict: **Approved**. The safe-compaction tooling and correction pass are accepted;
  no further correction is required.
- Exact requested corrections: none.
- STOP — do not merge to `main`, execute `/compact`, or begin `ambiguous_match` or any
  other product slice until the user explicitly authorizes the next action.
