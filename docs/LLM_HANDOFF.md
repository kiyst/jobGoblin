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

- Date/agent: 2026-09-07, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/seniority-classifier` for both findings in Iteration
  1's `Work review` above. Base: commit `1ac2b81` plus the uncommitted
  review. Preserved: the anchored title grammar, the anchor-adjacent
  description entry grammar, the exact executive/support exclusions, the
  compound rule (`senior`+`staff`/`principal`), the independent import
  boundary, the locally-implemented hyphen handling, the taxonomy
  annotation, and the honest evidence-gap statement. Modified only
  `seniority.py`, its fixture corpus, and this handoff entry.
- Finding 1 (High — description conflict check was missing): added
  `_immediate_trailing_conflict`, a description-safe conflict check
  distinct from title's `_trailing_conflict_labels`. Unlike title's
  mechanism (which scans the *entire* trailing token list), this only
  checks the position immediately after the just-matched candidate —
  skipping a leading run of pure-punctuation hard tokens (`,`, `/`, `&`,
  `-`, `–`, `—`, which are formatting, not relational prose) — and never
  scans further. This is what makes `"This is a senior director
  position."`, `"This is a junior senior analyst role."`, and `"This is a
  staff/principal engineer position."` all now correctly resolve to
  `unavailable` (all three reproduced by Codex's review), while `"This is
  a senior role reporting to the director of engineering."` still
  correctly resolves to `senior` — the real relational prose ("reporting
  to the") after the immediate position is never scanned into. The check
  only runs in the non-negated branch (a negated first candidate already
  suppresses the whole phrase via the existing prefix grammar; adding a
  second conflict check there would be redundant, not protective).
- Finding 2 (Low — fixture count documentation error): corrected
  `docs/LLM_HANDOFF.md`'s prior Iteration 1 entry, which read "89 cases"
  for the fixture corpus — the JSON file has always had 84 cases; 89 was
  always the module's total test count (84 parametrized + 5 code-level).
  Fixed the file-count claim only; the historical verification totals
  (89/173/1757 etc.) were already correct and are unchanged.
- No vocabulary, alias, anchor, explicit principal/director phrase, or
  exclusion catalog expansion — confirmed by inspection of the diff
  before committing.
- Files changed: `backend/app/normalization/seniority.py`
  (`_immediate_trailing_conflict`, `_PUNCTUATION_HARD_TOKENS`, and the
  `_extract_description_signal` call site), `backend/tests/fixtures/
  normalization/seniority_cases.json` (7 new cases, 91 total, was 84),
  this handoff entry (both the count correction in Iteration 1's already-
  rotated-out text and this new entry). `backend/tests/
  test_normalization_seniority.py`, `docs/ARCHITECTURE.md`,
  `docs/ROADMAP.md`, `app/normalization/employment.py`,
  `app/normalization/remote.py`, `app/normalization/types.py` untouched.
- Verification: targeted seniority module alone (**96 passed** — 91
  fixture cases + 5 code-level tests, was 89); all four normalization
  modules together (**269 passed**). `ruff format --check`/`ruff
  check`/`mypy` all pass. Genuine external `python scripts/verify.py
  --level routine` (full run) — all **9 steps PASS**, **1764 full-suite
  tests** (was 1757; +7, exactly matching the 7 net-new fixture cases).
  No database/migration/schema touched.
- Focused adversarial replay (required this round): beyond the fixture
  corpus, probed 9 unseen cases — additional immediately-joined pairs not
  literally matching the three reproduced forms (`"director staff"`,
  `"principal senior"`, comma-joined and ampersand-joined variants, all
  correctly `unavailable`); confirmed the compound rule still takes
  precedence over the new conflict check (`"senior staff engineer
  position"` still resolves to `staff`, since the compound consumes both
  tokens before the conflict check ever runs on the remainder);
  confirmed negated immediately-joined phrases still resolve safely via
  the existing negation grammar with no crash; and confirmed a longer,
  more elaborate relational-prose sentence (`"...that occasionally
  supports our director of engineering initiatives"`) still does not
  produce a false conflict. No new issues found.
- Deviations/known limitations: none new. The two adversarial
  observations recorded in the prior iteration (coordination-adjacency
  requiring direct adjacency; a title ending in a literal period) remain
  unchanged, out of scope for this pass. The pre-existing `alembic check`
  substitution remains, unrelated.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-07, Codex.
- Diff reviewed: `976abaa..5186598` on `phase-3/seniority-classifier`.
- Verdict: **Approved.** No executable findings.
- The High description-conflict finding is closed. Independent direct replay confirms
  `senior director`, `junior senior`, and `staff/principal` descriptions now fail
  closed, including comma/ampersand/dash variants, while `senior staff -> staff`,
  `senior principal -> principal`, ordinary single-value descriptions, negated forms,
  and later reporting/collaboration prose retain their approved behavior. The new
  immediate-only mechanism satisfies the invariant without importing title's broad
  trailing scan into description prose.
- The documentation correction is also closed: the historical entry now accurately
  distinguishes 84 original fixture cases from 89 original module tests; this pass adds
  seven fixtures for 91 cases and 96 module tests.
- Independent verification: all four normalization modules pass (**269 tests**); the
  canonical focused verifier passes all **10 steps** (**96 focused / 1764 full suite**),
  including Ruff, mypy, repository checks, test-database safety, and cleanup.
  `git diff --check` is clean. No schema or migration changed.
- Scope remained exactly bounded to `seniority.py`, its fixture corpus, and the handoff
  ledger. No vocabulary, aliases, anchors, principal/director phrases, exclusions,
  taxonomy implementation, ingestion wiring, provider behavior, or other parser changed.
- The seniority-classifier slice and its correction pass are accepted. Do not merge or
  begin another Phase 3 parser until the user explicitly authorizes that action.

### Merge record

- Date: 2026-09-07. User authorized merging `phase-3/seniority-classifier`
  into `main` following Codex's Approved review (no executable findings;
  approval commit `0c92b7d`) above.
- Pre-merge state: `main` and `origin/main` both at `7a90282`; feature
  branch `phase-3/seniority-classifier` and its origin both clean and
  synced at `0c92b7d` (containing implementation/correction commits
  `1ac2b81`, `5186598`, and the review-approval commit `0c92b7d`).
- Merge: `git merge --no-ff phase-3/seniority-classifier` on `main` —
  merge commit `92fcefc`. `git diff phase-3/seniority-classifier HEAD`
  is empty (zero content difference); `git diff --check` and
  `check_repo.py` both exit 0; working tree clean.
- Post-merge verification: genuine external `python scripts/verify.py
  --level routine` (full run, no `--focus`) — all **9 steps PASS** (Ruff
  format/check, mypy, `check_repo.py`, `git diff --check`,
  disposable-database URL/reachability, **1764 full-suite tests**,
  temp-directory cleanup).
- Pushed: `main` at `92fcefc`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `7a90282` (the
  commit immediately before this merge) — this removes
  `app/normalization/seniority.py`, both new test/fixture files, and the
  `docs/ARCHITECTURE.md`/`docs/ROADMAP.md` wording changes cleanly, with
  no migration to reverse and no data written by this slice to any
  environment (pure Python, never wired into ingestion/persistence).
- **Phase 3's third parser slice is merged, not Phase 3 itself.** The
  deterministic entry_level/mid_level/senior/staff/principal/director
  classifier (independently implemented, no import from or modification
  of `remote.py`/`employment.py`) is now on `main`, reviewed across two
  correction rounds with no remaining executable findings. `seniority.yaml`
  remains annotated as planned future enrichment, not implemented by this
  slice. The other five required Phase 3 parsers (title, salary, location,
  experience, skill) remain unstarted; this classifier is not wired into
  `ingestion/pipeline.py` or `ingestion/persistence.py`, and no
  `parser_version`/`field_provenance` write exists yet — those remain
  Phase 4+ concerns.
- STOP — do not begin or propose another Phase 3 parser, wire this
  classifier into ingestion/persistence, contact providers, or create a
  migration without separate authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-08, Claude Code (Sonnet 5). Risk class R (tooling —
  process/infrastructure only, no identity/concurrency/security/external
  behavior). Base -> ending commit: `f003595` -> this commit; branch
  `tooling/workflow-v3.1-handoff-metadata` (new branch, base: clean
  `main@f003595`, the seniority-classifier merge-record commit).
  Implements the Workflow v3.1 pilot's first (of three) piloted slices exactly as
  user-authorized: a `slice_kind`/`verification_level` structured metadata
  block in `LLM_HANDOFF.md`'s `Work done` entries, its validator, a
  required `verify.py` step that cross-checks that block against the same
  invocation's own observed counts, a `--docs-only` verifier mode, a
  `workflow_version` marker in the compaction checkpoint, and the durable
  process text (claim-to-evidence matrix, historical-defect checklist,
  confidently-wrong blocking rule, two-pass requirement) in
  `docs/LLM_WORKFLOW.md`/`CLAUDE.md`.
- `backend/scripts/check_handoff.py` (new): offline, no-subprocess
  validator for the metadata block — presence/allowed-values/cross-field
  structure (`validate_structure`), fixture-count cross-check against the
  real fixture file for `slice_kind: parser` (`validate_fixture_count`),
  and a cross-check against a caller-supplied actual run
  (`validate_against_run`) enforcing that `verification_level: not_run`
  never coexists with a fabricated numeric count and that `slice_kind:
  parser` requires real focused testing. Only ever inspects the *newest*
  `## Iteration N`'s `Work done` section — historical, already-rotated
  entries are never checked.
- `backend/scripts/verify.py`: added `handoff_metadata_step` (new,
  required, unconditional — runs even under `--docs-only`), wired via a
  `pytest_counts` dict shared across `_build_steps`'s pytest step
  closures using `run_pytest_step`'s new `counts_sink`/`counts_key`
  keyword-only parameters (a side channel; no second pytest subprocess is
  ever launched to re-derive counts). Added `--docs-only` (mutually
  exclusive with `--focus`, enforced in `_parse_args`), which skips the
  two database steps and both pytest steps while still requiring the
  handoff-metadata step to pass with `verification_level: not_run`.
- `.claude/hooks/compact_checkpoint.py`: added `WORKFLOW_VERSION =
  "v3.1-pilot"`, included in `render_checkpoint`'s output as `Workflow
  version: v3.1-pilot`.
- `docs/LLM_WORKFLOW.md`: new "Workflow v3.1 pilot (three-slice trial)"
  section — claim-to-evidence matrix template, the nine-category
  historical-defect checklist (grounded in this project's actual past
  defects: the `employment.py` mask-order bug, the seniority immediate-
  trailing-conflict gap, and the negation/attribution gaps the first
  `classify_experience` preflight caught), the confidently-wrong blocking
  rule, the two-pass requirement, the `slice_kind`/metadata-block
  reference, and the mandatory post-third-slice retrospective trigger.
  Also documents `--docs-only` in the verification matrix section.
- `CLAUDE.md`: new "Workflow v3.1 (pilot)" marker section; compaction
  instructions now also preserve the active workflow version and the
  active slice's `slice_kind`/`verification_level`.
- Files changed: `backend/scripts/check_handoff.py` (new),
  `backend/tests/test_check_handoff.py` (new, 43 tests),
  `backend/scripts/verify.py`, `backend/tests/test_verify.py` (15 new
  tests; 2 existing `_build_steps` structural tests updated for the new
  trailing step), `.claude/hooks/compact_checkpoint.py`,
  `backend/tests/test_compact_checkpoint.py` (1 new test),
  `docs/LLM_WORKFLOW.md`, `CLAUDE.md`, this handoff entry (two-iteration
  rotation: deleted the original Iteration 1, renumbered the
  seniority-classifier's Work done/Work review/Merge record to Iteration
  1, appended this entry as Iteration 2). No application code
  (`app/normalization/*`, `app/db/*`, ingestion) touched; no schema or
  migration.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (104
  source files under `app`/`tests`/`scripts`/`.claude/hooks`).
  `python -m scripts.check_repo` exits 0. Genuine external `python
  scripts/verify.py --level routine --focus tests/test_check_handoff.py
  tests/test_verify.py tests/test_compact_checkpoint.py` (full run,
  before this entry existed, to prove the wiring end-to-end): **10 of 11
  steps PASS** — **146 focused / 1820 full-suite tests** — with the new
  `handoff metadata validation` step correctly FAILing (`"the newest
  'Work done' section has no 'workflow-metadata' block"`), proving the
  step actually inspects the real file rather than trivially passing.
  This entry's own metadata block below now supplies that block; a
  second genuine run after this entry is committed (recorded by the
  reviewer's independent verification, per the standing process) is
  expected to show all 11 steps PASS.
- Self-review (Class R, abbreviated per `LLM_WORKFLOW.md`'s scaled-depth
  rule): confirmed `check_handoff.py` never imports or calls anything
  from `verify.py` (no recursive verifier invocation); confirmed
  `run_pytest_step`'s `counts_sink`/`counts_key` default to `None`/`""`
  so every pre-existing call site (all of them, until this slice) is
  unaffected; confirmed `_build_steps`'s `docs_only` branch never
  constructs the database/pytest `Step` closures at all under
  `--docs-only` (not merely skips running them) via a test whose fake
  runner/connectivity-check raise if called; confirmed
  `validate_against_run` independently rejects a parser-slice's
  `not_run` focused count even when isolated from `validate_structure`
  (a defense-in-depth unit test, not merely relying on the structural
  check).
- Deviations/known limitations: this entry's own metadata block is
  necessarily written after the verification run whose counts it
  declares (146/1820, from the run above) rather than the reviewer
  re-deriving them independently — this is inherent to how any
  self-describing ledger works and is exactly why `check_handoff.py`'s
  cross-check against the *reviewer's own* subsequent run exists as a
  separate, independent safeguard. The nine-category historical-defect
  checklist and the pilot's success thresholds are newly authored process
  text, not independently re-derived from a separate source, since this
  is their first codification.
- STOP — awaiting Codex review. Do not merge, begin `classify_experience`
  or any other Phase 3 parser, or start pilot slice 2/3 of Workflow v3.1
  without separate authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: tooling
verification_level: routine
focused_test_selector: tests/test_check_handoff.py tests/test_verify.py tests/test_compact_checkpoint.py
focused_test_count: 146
full_suite_count: 1820
```
