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
  - Full suite -> **1387 passed**.
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

**Merge record (appended, not a rewrite of the entry above):** Approved at review
commit `3af3b28` (no findings). Per user authorization, `codex/tooling-safe-compaction`
was merged into `main` with a normal merge commit (`8920a4e`; `--no-ff`, no
squash/rebase/force-push) and pushed. `main`/`origin/main` are both now at `8920a4e`.
Verified: feature branch was clean and pushed at `3af3b28`, and `main`/`origin/main`
were still at `10b9432` immediately before the merge; `main` has zero content diff
against the feature branch (`git diff main codex/tooling-safe-compaction --stat`
empty); migration `0017` remains the sole Alembic head; `python -m scripts.check_repo`
exited `0`; `git diff --check` was clean; working tree clean throughout. No `/compact`,
network request, or database mutation was performed during the merge.

**Rollback boundary:** reverting `8920a4e` (a single merge commit) restores `main` to
`10b9432` exactly — no schema/migration exists in this slice to downgrade, and no data
migration accompanies it. This merges the safe-compaction tooling only (root
`CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/compact_checkpoint.py`, the
canonical verifier's expanded Ruff/mypy scope over `.claude/hooks/`, and their tests) —
it does **not** touch product code, schema, migrations, providers, ingestion, or the
`ambiguous_match` proposal, all of which remain not started and are not authorized by
this merge.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-01, Claude Code (Sonnet 5). Class H implementation of the
  approved `ambiguous_match` identity-conflict persistence slice on
  `phase-2/ambiguous-match-persistence`, based on clean `main@e18b2b3`.
- Outcome: Tier 2/3 finding more than one distinct candidate Job no longer raises
  `AmbiguousIdentityMatchError` (a whole-run failure). It now creates a standalone
  Job/JobOccurrence, exactly like a clean insert, and persists an ADR-0007
  `ambiguous_match` `identity_conflicts` row, isolated per posting. No schema or
  migration change — the existing Phase-1 `identity_conflicts` table and its
  `ambiguous_match` array-shape `CHECK` already supported this shape.
- Binding decisions applied exactly as authorized:
  1. `_discover_candidates()`'s `<=2` probe remains the ambiguity *trigger* at both
     `_attach_to_candidate` sites (pre-lock, post-lock recheck); a new
     `_discover_all_candidates()` (unlocked, unbounded, sorted by UUID) supplies the
     *persisted* evidence. If that authoritative requery resolves to fewer than two
     candidates, `CandidateResolutionUnstableError` is raised and nothing is
     persisted — new tests cover both the pre-lock and post-lock-recheck
     disagreement cases, plus a 3-candidate case proving the full set (not just the
     probe's two) is what gets persisted.
  2. `UpsertOutcome.__post_init__` enforces the invariants at construction:
     `AMBIGUOUS` requires >=2 distinct, sorted candidate IDs; every other kind must
     carry none. Four direct unit tests cover missing/singleton/duplicate/unsorted
     tuples and cross-kind rejection.
  3. `existing_value` = sorted candidate Job-ID strings; `incoming_value` =
     single-element array with the new JobOccurrence's ID string — documented
     explicitly (code and all three touched decision/architecture docs) as
     intentionally different entity types, not a symmetry bug.
  4. New `_after_ambiguous_flush()` test seam mirrors `_after_quarantine_flush`/
     `_after_attach_flush`; a forced post-flush failure proves the new Job, new
     JobOccurrence, `IdentityConflict`, and raw terminal update all roll back
     together. A separate test proves reprocessing the same terminal raw row is
     rejected by `_validate_raw_association`'s existing `processing_status` check,
     with no second conflict row and no further mutation.
  5. `pipeline.py`'s counter dispatch is now an exhaustive if/elif over all five
     `UpsertKind` values (`QUARANTINED` moved out of the trailing `else`); a final
     `else: raise AssertionError(...)` fails closed for any future unrecognized
     kind. `AMBIGUOUS` buckets `jobs_inserted` (a real Job was created) and sets
     `had_conflict`; a dedicated test forces a fake outcome kind to prove the
     fail-closed branch and confirms no falsely successful counters.
  6. `AmbiguousIdentityMatchError` deleted; every surviving reference updated —
     `UpsertKind`/`_attach_to_candidate`/`upsert_job_occurrence`/`persist_posting`
     docstrings, `CandidateResolutionUnstableError`'s own docstring, ADR 0004, ADR
     0007 (new "Phase 2 implementation notes" section), ARCHITECTURE.md §8/§11,
     DATA_MODEL.md's `identity_conflicts` row notes, ROADMAP.md.
  - Preserved unchanged: standalone-Job creation (no guessing among candidates);
    zero candidate mutation on either ambiguity site, documented precisely per-site
    (pre-lock touches nothing; post-lock recheck may already hold one candidate's
    `FOR UPDATE` lock but never writes to it); one atomic transaction;
    `completed_with_errors` run status / `completed` attempt status; sanitized
    IDs-only logging; `CandidateResolutionUnstableError` untouched and fail-closed.
  - ROADMAP.md rewritten to be merge-state-neutral per the user's explicit
    correction: dropped the fixed "three merged slices" count (would go stale on
    the next merge), and the new `ambiguous_match` capability is described as
    "implemented, not yet merged — on branch `phase-2/ambiguous-match-persistence`,
    awaiting review and merge authorization."
- Files changed: `backend/app/ingestion/persistence.py`, `backend/app/ingestion/
  pipeline.py`, `backend/tests/test_ingestion_pipeline.py` (11 new tests, 3
  rewritten to persist instead of raise; `test_candidate_changes_after_lock_is_
  detected_not_retried` left unchanged — a genuinely different code path);
  `docs/DECISIONS/0004-scoped-deterministic-identity.md`, `docs/DECISIONS/
  0007-identity-conflict-quarantine.md`, `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/ROADMAP.md`; this handoff entry. No schema,
  migration, provider, or network file touched.
- Verification: genuine external `python scripts/verify.py --level routine --focus
  tests/test_ingestion_pipeline.py` — all **10 steps PASS**: Ruff format/check,
  mypy (82 source files), `check_repo.py`, `git diff --check`, database-URL
  safety, real test-database reachability, **49 focused tests**, **1398
  full-suite tests** (was 1387; net +11), temp-directory cleanup, in ~160s.
  `alembic heads` confirms `0017` remains the sole head (no migration added; `git
  diff --stat migrations/` is empty). `alembic current` against the configured
  dev database (`jobgoblin`) shows it pre-existingly stamped at `0006`, far behind
  head — a condition that predates this branch (this slice adds zero migrations)
  and was **not** remediated: no `alembic upgrade` was run against it; a direct
  before/after `alembic current` check confirms it stayed at `0006` throughout.
  All schema/database work in this slice ran only against the disposable
  `jobgoblin_test` database.
- Adversarial self-review: dispatched a fresh-context subagent against the actual
  diff (not this summary). It confirmed correct control flow (no candidate
  mutation on either ambiguity path), correct `INSERTED`-vs-`AMBIGUOUS` tagging,
  airtight `UpsertOutcome` validation, correct evidence shape against
  DATA_MODEL.md's own `CHECK`, exhaustive/unreachable-else pipeline dispatch, and
  zero leftover `AmbiguousIdentityMatchError` references. It found one real defect
  class (Medium-High): six new tests captured cleanup IDs
  (`job_ids.append(...)`/preexisting-set-diff) *after* assertions that could fail,
  risking a leaked row in the disposable test database on a genuine regression.
  Fixed in all six by moving the capture to immediately follow the mutating call,
  before any assertion — reverified by rerunning the full suite (still 1398
  passed).
- Deviations/known limitations: `alembic check` itself could not be exercised
  end-to-end because of the pre-existing stale dev database described above;
  substituted with `alembic heads` (single, unchanged head) plus an empty
  `migrations/` diff, which together give the equivalent no-schema-drift guarantee
  for a no-migration slice without touching the dev database.
- STOP — awaiting Codex review. Do not merge, start Tier 4, add schema changes,
  contact live providers, or expand this slice.
