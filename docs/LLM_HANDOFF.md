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

- Date/agent: 2026-09-15, Claude Code (Sonnet 5). Risk class H (same
  process/security-relevant tooling as the original activation candidate
  work, C1-C6). Base `B` -> candidate
  `C7`: `66202c23facff6bd33d8f624e327cabdd40708b4` -> this commit; branch
  `tooling/workflow-v3.2-activation` (continued). `slice_kind: tooling`.
  `slice_id: 2026-09-13-workflow-v3-2-activation-66202c2` (unchanged --
  same base, same underlying activation slice).
- **Supersedes the original activation review record.** Sol approved `C6` =
  `332947196d028b9a46a52aa3c44e51028d5f7e0c` / `A6` =
  `4ee69a96981c01b12bce1ad3ce7706ff34b5a149`, with `R` =
  `0c42aae891a24181f871df56e52b732322fd1d0e` recording that verdict.
  Immediately after, independently running the full `check_review.
  validate_c_a_r_chain(C6, A6, R)` (and therefore `check_merge_
  eligibility`) for the first time -- Sol's own approval was necessarily
  based on direct receipt/repo inspection, since `R` did not yet exist
  when they reviewed -- surfaced a genuine failure: the receipt's
  `checker_hash` for `backend/scripts/check_handoff.py` did not match
  what `check_review.py`'s own hash cross-check recomputed. Root cause:
  that cross-check hashed a *fresh detached-worktree checkout* of the
  file, while the coordinator that produced the receipt hashes the
  *authoring checkout's on-disk bytes* directly -- and that file
  currently carries LF-only line endings in the long-lived authoring
  checkout (never freshly re-checked-out under this project's
  `core.autocrlf=true`), while a fresh worktree checkout smudges it to
  CRLF, so the two hashes diverge. This is a latent defect in `check_
  review.py`'s own tooling, not a problem with `C6`/`A6`'s actual content
  -- `R`'s own structure, the `A6..R` append-only diff, and the review-
  metadata cross-check all independently passed. Per explicit user
  instruction: `C6`/`A6`/`R` are preserved exactly as pushed, never
  amended or rewritten, but this cycle's review record is **not treated
  as valid merge-eligible approval** -- a fresh `C7`/`A7` cycle (this
  iteration) is required, with a new `R` to be authored only after a
  fresh Sol re-review.
- Fix: defines one canonical, platform-independent hashing mechanism,
  reused identically everywhere a file's content is hashed for receipt
  purposes. New `verification_receipts.blob_bytes_at_commit`/
  `committed_file_hash` read the exact committed Git blob bytes for
  `<commit_sha>:<repo_relative_path>` directly from the object database
  via `git cat-file` -- never a working-tree or fresh-checkout read,
  which can differ from the committed bytes whenever a local checkout
  filter (`core.autocrlf`) converts line endings on smudge. Never text-
  decoded, never newline-normalized. Fails closed for a missing commit/
  path, a git failure, or a non-blob object. `dependency_and_config_
  inputs` is rewritten on top of it (now takes `commit_sha` instead of a
  working-tree `repo_root` read) and fails closed on a duplicate or
  malformed path. `verification_coordinator._file_hash_at` and `check_
  review.py`'s `_cross_check_recorded_hashes` (the worktree-spinning-up
  `_recompute_hashes_at_candidate` is deleted entirely, no longer needed)
  both now call this single mechanism, so receipt generation and review-
  time recomputation can never independently diverge again.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2637
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean. New regressions prove: an LF
  authoring-checkout hash and a genuinely CRLF-smudged fresh-worktree
  hash for the same commit are identical; changing committed content
  changes the hash; mutating working-tree bytes without changing the Git
  blob does not; and a real coordinator-generated receipt's hashes agree
  with `check_review.py`'s independent recomputation even after the
  authoring checkout is subsequently mutated on disk.
- Deviations/known limitations: none beyond the superseded original
  activation review record noted above.

#### Correction round 1 (own follow-on finding, before Sol re-review)

- **Supersedes candidate `C7` = `cf60c424dcbc551874f94686fd8b3332cb9d4a86`
  and publication `A7` = `f215fe8031eab8da4a48c5410de5cd0afdf1d6f4`.** The
  receipt published there
  (`docs/verification-receipts/cf60c424dcbc551874f94686fd8b3332cb9d4a86/
  562fad62-93f1-45be-9f52-4e69ced38a82.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. **Correction (Sol's review of `C8`/`A8`):** `C7`/`A7` were
  not independently pushed as branch tips before `C8` was committed on
  top of them -- but pushing `A8` (a descendant of `C8`, a descendant of
  `A7`, a descendant of `C7`) made all three reachable on the remote
  branch as superseded ancestors. They are therefore **not** "purely
  local" or "never pushed to origin"; that was incorrect wording in this
  entry's original form. Both are still preserved unamended, never
  rewritten, per the same discipline as every other correction round in
  this project.
- Found while independently proving the frozen contract's own required
  step -- "the complete `C7 -> A7 -> synthetic-R` chain validates
  successfully before publishing the real `R`" -- using a throwaway,
  never-pushed synthetic `R` in a disposable worktree (deleted
  immediately after). `check_review.extract_review_metadata_text` (and
  `extract_escalation_blocks`) scanned the *entire* handoff file for a
  `workflow-review-metadata`/`workflow-escalation-metadata` block,
  instead of scoping to the newest `## Iteration N` section the way
  `check_handoff.py`'s own metadata-block search already does. Once
  the original activation `R` (recording Sol's approval of `C6`/`A6`,
  preserved unchanged) and this iteration's own review block coexist in
  the same file, that unscoped search finds both and raises "more than
  one block found" -- this is not merely a test artifact: it would also
  have broken the real `R` for this iteration once authored, since that
  historical block never goes away.
- Fix: new `_latest_iteration_text` scopes to the text from the newest
  `## Iteration N` heading onward (mirroring `check_handoff.py`'s own
  per-iteration scoping); both `extract_review_metadata_text` and
  `extract_escalation_blocks` now search within that scope only. New
  regressions prove: extraction correctly returns the latest iteration's
  own block when an earlier iteration's historical block coexists (never
  raising "more than one" for two blocks in two different iterations);
  escalation-block extraction is scoped identically; and two genuine
  blocks within the *same* latest iteration are still correctly rejected
  as "more than one".
- Files changed (this correction only): `backend/scripts/check_review.py`
  (edited); `backend/tests/test_check_review.py` (edited). No production
  parser (`app/normalization/*`) touched; no migration/model file
  touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2640
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 2 (Sol review of C8/A8: two bounded issues)

- **Supersedes candidate `C8` = `d23273c0addd30717046edc8dfe8b58ebca835b6`
  and publication `A8` = `a056f77b8f949b020dcee2b21267e2b6b4fab2dd`.** The
  receipt published there
  (`docs/verification-receipts/d23273c0addd30717046edc8dfe8b58ebca835b6/
  e917a12f-1b43-43ca-8323-62df0dff785a.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C8`/`A8` are preserved unamended, never rewritten; both
  are reachable on the remote branch (pushed as ancestors of `A8`'s own
  push), not merely local.
- **Finding 1 (A→R boundary):** `check_review.py`'s prior fix (this
  project's own "scope to the latest `## Iteration N` section" approach,
  from the previous correction round) was still not precise enough.
  Review and escalation metadata are now extracted and validated
  *exclusively* from the exact appended suffix
  (`handoff_at_r[len(handoff_at_a):]`), never by searching the whole
  handoff file and never by searching "the latest iteration onward" --
  neither of those weaker scopes can distinguish an already-existing
  historical block from what `R` itself actually added.
  `validate_a_to_r_transition` now computes and returns this suffix
  (after confirming the pure-append invariant), and itself enforces:
  the suffix introduces no new `## Iteration N` heading, and the suffix
  contains exactly one `### Work review` section. `extract_review_
  metadata_text`/`extract_escalation_blocks` are reverted to their
  original simple form (extract from exactly the text given -- no
  internal scoping of their own) since the caller (`validate_c_a_r_
  chain`) now always passes this exact suffix, never the whole file.
  New regressions prove, via genuine Git commits: a fabricated `##
  Iteration N` heading appended between two review blocks is rejected
  outright (the full-transition regression); an escalation block hidden
  behind that same fabricated heading is rejected identically (the
  analogous hidden-escalation proof); and a suffix with two `### Work
  review` sections (no fake iteration needed) is also rejected.
- **Finding 2 (handoff wording):** The previous correction round's own
  entry incorrectly described `C7`/`A7` as "purely local" and "never
  pushed to origin". Corrected in place (see that entry, above): `C7`/
  `A7` were not independently pushed as branch tips before `C8`, but
  pushing `A8` (a descendant of `C8`, a descendant of `A7`, a descendant
  of `C7`) made all three reachable on the remote branch as superseded
  ancestors.
- Files changed (this correction only): `backend/scripts/check_review.py`
  (edited); `backend/tests/test_check_review.py` (edited);
  `docs/LLM_HANDOFF.md` (wording correction to the prior entry, plus this
  entry). No production parser (`app/normalization/*`) touched; no
  migration/model file touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2643
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

#### Correction round 3 (Sol review of C9/A9: one bounded issue)

- **Supersedes candidate `C9` = `5a3e18787b878d61035815bca0d31d2f04603e8a`
  and publication `A9` = `033e935e7681db7e402b4f3e9790ae5de12eb50e`.** The
  receipt published there
  (`docs/verification-receipts/5a3e18787b878d61035815bca0d31d2f04603e8a/
  7801c0b5-4993-4d24-8b8e-8a99142fa230.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C9`/`A9` are preserved unamended, never rewritten; both
  are reachable on the remote branch (pushed as ancestors of `A9`'s own
  push), not merely local.
- **Finding (remaining Medium A→R boundary gap):** Sol's C9/A9 re-review
  confirmed both prior findings closed, but found that the previous
  round's suffix-shape check -- "the suffix introduces no new `##
  Iteration N` heading, and contains exactly one `### Work review`
  section" -- did not reject an appended **second** `### Work done`
  heading carrying its own, independently schema-valid
  `workflow-metadata` block, placed after an otherwise-legitimate
  review. `check_merge_eligibility` incorrectly returned `approved` for
  such a suffix, and `check_handoff.py` would then treat that appended
  Work-done metadata as the current state -- violating the closed,
  review-only `A -> R` transition.
- Fix: hardened the exact appended-suffix grammar in `check_review.py`'s
  `validate_a_to_r_transition`. New `_LEVEL_2_OR_3_HEADING_RE` locates
  every level-2 (`## `) or level-3 (`### `) heading introduced by the
  suffix. The suffix is now rejected unless: its first heading is
  exactly its sole `### Work review`; no additional level-2 or level-3
  heading follows (including a second `### Work done`); and no
  `workflow-metadata` fenced block appears anywhere in the suffix (that
  block belongs exclusively to a `### Work done` section, which the
  suffix may never introduce). Ordinary prose beneath the sole `### Work
  review` heading, and validated `workflow-escalation-metadata` blocks
  alongside the review, remain permitted, exactly as before.
- New regressions prove, via genuine Git commits and the full chain: the
  required reproduction -- a suffix pairing a valid `### Work review`
  with an appended second `### Work done` section containing
  *structurally valid* `workflow-metadata` (independently confirmed
  schema-valid via `check_handoff.validate_structure` before the
  reproduction, so the rejection is proven to be about the closed
  transition, not malformed content) -- is rejected by
  `validate_a_to_r_transition`, `validate_c_a_r_chain`, **and**
  `check_merge_eligibility` alike; a bare `workflow-metadata` block
  appended with no heading at all is rejected identically; and two
  neighboring positive controls confirm ordinary review prose beneath
  the sole `### Work review` heading, and a validated escalation block
  alongside the review, both still validate successfully end-to-end.
- Files changed (this correction only): `backend/scripts/check_review.py`
  (edited); `backend/tests/test_check_review.py` (edited);
  `docs/LLM_HANDOFF.md` (this entry, plus resetting the metadata block
  below to `state: pending` for the fresh `C10`/`A10` cycle). No
  production parser (`app/normalization/*`) touched; no migration/model
  file touched.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (158
  source files, backend + `.claude/hooks`). Full pytest suite: **2647
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `M`/`Q`, begin another slice, or modify product/parser behavior.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-13-workflow-v3-2-activation-66202c2
slice_kind: tooling
risk_class: H
base_sha: 66202c23facff6bd33d8f624e327cabdd40708b4
declared_gate: final
executed_gate: final
candidate_sha: c7933d072d2c7f92844ec3206863010ef13ff2ad
receipt_id: c22ded07-a429-4154-a6ea-84c553758baa
receipt_path: docs/verification-receipts/c7933d072d2c7f92844ec3206863010ef13ff2ad/c22ded07-a429-4154-a6ea-84c553758baa.json
full_suite_count: 2647
focused_test_count: 480
mutation_witness_count: 34
```

### Work review

- Sol's re-review of `C10` = `c7933d072d2c7f92844ec3206863010ef13ff2ad`
  and `A10` = `688216a8ea1e4da52cb026d2e075a2608c262953`: **Approved, no
  findings.** The A→R suffix now rejects an appended second Work-done
  section or `workflow-metadata` block while allowing ordinary review
  prose and valid escalation metadata. Independent verification
  performed: all 87 focused review tests passed; the `C10→A10`
  publication shape, receipt validity, and hash cross-checks were
  confirmed; `approval_eligible` was independently recomputed; `ruff`,
  `check_repo.py`, and `git diff --check` passed; the branch is clean
  and synchronized. The full 2,647-test suite and the 34 mutation
  witnesses were not independently re-run; those results are taken from
  Claude's receipt.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-13-workflow-v3-2-activation-66202c2
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-17T00:00:00Z
candidate_sha: c7933d072d2c7f92844ec3206863010ef13ff2ad
publication_commit_sha: 688216a8ea1e4da52cb026d2e075a2608c262953
receipt_path: docs/verification-receipts/c7933d072d2c7f92844ec3206863010ef13ff2ad/c22ded07-a429-4154-a6ea-84c553758baa.json
receipt_id: c22ded07-a429-4154-a6ea-84c553758baa
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-17. Merged `tooling/workflow-v3.2-activation` at
  approved, reviewed commit `a070ba974e321f360c0a36282bffabe700be617d`
  (Sol's "Approved, no findings" verdict on `C10`/`A10`, above) into
  `main` via `git merge --no-ff`. Merge commit:
  `9649cba1deebdc73911790de3ccb2ac51fd483a6`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `66202c23facff6bd33d8f624e327cabdd40708b4`.
- Pre-merge checks: confirmed the feature branch and its origin both sat
  at `a070ba9`, and `main`/`origin/main` were both clean and
  synchronized at `66202c23` before merging.
- Post-merge verification, all run directly against merged `main`:
  - `git diff --quiet a070ba9 HEAD` — zero content difference between
    merged `main` and the approved feature-branch tip, confirmed.
  - `git diff --check` — clean.
  - `python -m scripts.check_repo` — clean.
  - No migration/schema changes: `git diff --stat 66202c23..HEAD --
    backend/alembic backend/migrations` and `git log --oneline
    66202c23..HEAD -- backend/alembic backend/migrations` both empty.
  - `python -m scripts.verify --level routine --gate final --focus
    tests/test_check_handoff.py tests/test_check_review.py
    tests/test_migration_matrix.py tests/test_verification_coordinator.py
    tests/test_verification_lock.py tests/test_verification_receipts.py
    tests/test_verification_scope.py tests/test_verification_worktree.py
    tests/test_verify.py` — **all 12 checks PASS**, 480 focused /
    2,647 full-suite tests passed.
  - `python -m scripts.contract_mutation_witnesses` — **34 passed, 0
    failed**, out of 34 active-guard witnesses.
- Pushed: `main` pushed to `origin/main`
  (`66202c23..9649cba1deebdc73911790de3ccb2ac51fd483a6`); both now
  synchronized.
- This merge activates Workflow v3.2's own tooling (schema-v2
  `workflow-metadata`, verification receipts, `C -> A -> R` chain/merge
  validation) as reusable machinery. It does **not** itself authorize
  Slice 3 product/parser work, `Q` post-merge evidence generation, or
  any other new slice — those remain separate authorizations.
- STOP — report the synchronized final `main` SHA and stop. No `Q`
  artifact, no Slice 3, no other Phase 3/4 parser, without separate
  explicit user authorization.
- **Post-merge evidence status:** no `Q` exists for this merge; see ADR
  0009's "Post-merge evidence: one-time bootstrap exception for
  M = 9649cba" for the full record. `validate_published` will fail for
  this `(C10, A10, R, M)` tuple unless a conforming `Q` is later
  authorized and published. The post-merge verification above (zero
  content diff, clean statics, 12/12 canonical-verifier checks, 34/34
  mutation witnesses) was genuinely run and reported here; it can be
  rerun against `M`'s tree for equivalent fresh evidence, but the
  original run's own output was not captured as a durable artifact.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-18, Claude Code (Sonnet 5). Risk class H
  (process/security-relevant tooling, same category as every prior
  Workflow v3.2 tooling slice). Base `B` -> candidate `C`:
  `27a2a5e2cf81b2e347d1fa19012822fe1f0b6198` -> this commit; new branch
  `tooling/workflow-v3.2-post-merge-q-producer`, cut from `main` after a
  freshly verified clean checkout (`main` == `origin/main`, `check_repo.py`
  clean, `git diff --check` clean). `slice_kind: tooling`.
  `slice_id: 2026-09-18-post-merge-q-producer-27a2a5e`. Implements the
  bounded, proposal-reviewed "post-merge `Q`-evidence producer" slice:
  Workflow v3.2's `C -> A -> R -> M -> Q` chain had a validator for `Q`
  (`check_review.validate_q`/`validate_published`) but no producer at
  all until this slice.
- **Producer:** `verification_coordinator.run_post_merge_verification`,
  taking a new `PostMergeEligibleRequest` (only the five chain commit
  SHAs -- `candidate_sha`, `publication_sha`, `review_sha`, `merge_sha`,
  `expected_first_parent` -- no `base_sha`/`slice_id`/receipt-reference
  field for a caller to forge). Every one of those values is instead
  derived from `check_review.validate_c_a_r_chain`'s own independently
  re-validated chain output, before any worktree is created. The
  migration trigger is computed over that same chain-derived
  `base_sha..candidate_sha` range -- never a caller-supplied range and
  never `base_sha..merge_sha` -- so nothing external can suppress a
  genuine migration requirement. Verification runs in a disposable
  detached worktree at `M` (always full/final, never gated or
  focus-narrowed), reusing the receipt producer's own worktree/lock/
  cache-cleanup lifecycle under its own `post-merge-coordinator-`
  run-directory prefix. Emission is explicitly fail-closed: a failed
  verification run, a cleanup failure, or an artifact that would fail
  its own self-validation (`check_review._validate_post_merge_artifact_
  schema`/`_validate_post_merge_artifact_evidence`, called before the
  write) all produce *no file at all* -- a deliberate divergence from
  the existing receipt producer, which does write a receipt marked
  `approval_eligible: false` on a failed run. The function only ever
  writes the artifact file; committing `Q` (bundling that file with the
  append-only merge-record edit to the handoff, per the mainline-`Q`-
  next policy in `LLM_WORKFLOW.md`) remains a separate step.
- **Cleanup-prefix fix:** `cleanup_stale_coordinator_dirs` is now
  parameterized (`prefix: str = "coordinator-"`), restricted to a closed
  set of exactly two known prefixes (`"coordinator-"`,
  `"post-merge-coordinator-"`); an unrecognized prefix (including an
  empty string, which would otherwise match every directory) is rejected
  before any directory is ever scanned.
- **Release-sequence guard:** new `confirm_main_unchanged(expected_sha)`
  re-fetches `origin/main` and refuses if it no longer equals
  `expected_sha` -- run immediately before pushing a locally-prepared
  `M`/`Q` together, so a remote that advanced in the meantime is caught
  before the push rather than raced against.
- **Adversarial self-review** (fresh subagent, full twelve-question
  pass; see `LLM_WORKFLOW.md`'s "Adversarial implementer self-review"):
  no Critical/High findings. Confirmed clean, with concrete evidence:
  the stage-1/2 pre-flight (`validate_c_a_r_chain`/`validate_merge`)
  genuinely runs before any worktree is created on every path; every
  raise point between the worktree stage and the artifact write is an
  unguarded `raise` with no exception-swallowing; `base_sha` is assigned
  exactly once, from the chain-derived `published_base_sha`, with no
  other path into the migration decision; the prefix-rejection in
  `cleanup_stale_coordinator_dirs` is the function's literal first
  statement; there is no TOCTOU window since `A`/`R` content is read
  from immutable commit objects and `M`'s worktree is independently
  snapshotted before/after. Three Medium findings (test-rigor gaps, not
  implementation defects) were fixed in response: two rejection tests
  now also assert a worktree-creation guard (proving *when* rejection
  happens, not just *that* it does, since `.verify-tmp` absence alone
  couldn't distinguish "never created" from "created and cleaned up");
  the success and verify-invocation-failure tests now assert
  `.verify-tmp` is clean (empty or absent) directly, since it is
  gitignored and `git status` is blind to it; and a new regression
  (`test_post_merge_verification_writes_no_artifact_when_self_
  validation_fails`) proves the artifact's own self-validation gate --
  not just the `returncode`/`all_passed` check -- independently blocks
  emission, using a stand-in `verify.py` that mis-reports `all_passed:
  true` while silently omitting a required step. Three Low findings
  were reviewed and accepted as pre-existing, informational, and out of
  this slice's bounded scope (see Deviations below), not fixed here.
- **Documentation (the three proposal-approved addenda):** `docs/
  DECISIONS/0009-workflow-v3.2-activation.md` gains "Post-merge
  evidence: one-time bootstrap exception for M = 9649cba" (the corrected
  explanation: a conforming `Q` remains constructible on a sibling
  branch at any time, since Git places no limit on a commit's children
  -- what is actually foreclosed is only `main`'s own already-pushed
  linear continuation from `M`; the reason is procedural, not technical,
  since `M`'s own tree already contained the `Q` tooling; the
  preserved evidence is reported and rerunnable, not "independently
  reproducible from Git") and "Post-merge (`Q`) evidence producer"
  (describing this slice's implementation). `docs/LLM_WORKFLOW.md` gains
  "Post-merge (`Q`) evidence producer" and "Project policy: `Q` is the
  next mainline commit after `M`" (explicitly framed as this project's
  own policy choice, not a `validate_q` requirement; a precondition --
  an approved producer or evidence-capture procedure must exist *before*
  merge authorization, not after; the mainline-shape rule; a fail-closed
  stop-at-`M` rule if post-merge verification or `Q` validation ever
  fails; and the release sequence tying `confirm_main_unchanged` into
  the push step). This handoff gains the "Post-merge evidence status"
  pointer note on the prior Merge record entry (above) and this Work
  done entry itself.
- Files changed: `backend/scripts/verification_coordinator.py` (edited);
  `backend/tests/test_verification_coordinator_post_merge.py` (new, 16
  tests); `docs/DECISIONS/0009-workflow-v3.2-activation.md` (edited);
  `docs/LLM_WORKFLOW.md` (edited); `docs/LLM_HANDOFF.md` (this entry,
  the prior entry's pointer note, and the two-iteration rotation below).
  No production parser (`app/normalization/*`), model, migration, or
  live-provider file touched; no database lifecycle operation performed.
- **Two-iteration rotation applied**: the oldest iteration (the Slice 2
  contract-harness bounded-correction pass, already merged) is deleted;
  the former Iteration 2 (the original v3.2 activation candidate/review
  cycle) and Iteration 3 (the C7-C10 correction saga plus the merge
  record) are renumbered to Iteration 1 and Iteration 2 respectively,
  with every in-prose cross-reference to the renumbered iteration
  updated to match; this entry becomes the new Iteration 3.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (159
  source files, backend + `.claude/hooks`). Full pytest suite: **2663
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- Deviations/known limitations (all reviewed, accepted, non-blocking):
  (1) on a worktree-removal failure, cleanup still deletes the physical
  worktree directory without `git worktree remove`/`prune`, which can
  leave a dangling `.git/worktrees/<id>` metadata entry -- inherited,
  byte-identical behavior from the existing `run_receipt_eligible_
  verification`, not introduced or changed by this slice; (2)
  `cleanup_stale_coordinator_dirs` cannot detect or repair that kind of
  leak, since it only scans `COORDINATOR_RUN_ROOT`, never `git worktree
  list` -- same shared, pre-existing limitation; (3) no dedup/lock scopes
  a given `merge_sha` itself, so two concurrent producer runs against the
  same `M` could both succeed and coexist as separate untracked artifact
  files under `docs/post-merge/<merge_sha>/` -- harmless in practice,
  since `validate_q` requires exactly one *committed* artifact addition,
  and the actual choice of which artifact becomes `Q` is made at commit
  time, not by the producer.
- STOP — this is a bounded tooling slice only. Do not author `R`, merge,
  create a real `M`/`Q` for this slice or retroactively for `M =
  9649cba`, begin another slice, rebase, or force-push.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-18-post-merge-q-producer-27a2a5e
slice_kind: tooling
risk_class: H
base_sha: 27a2a5e2cf81b2e347d1fa19012822fe1f0b6198
declared_gate: final
executed_gate: final
candidate_sha: 3397e1d37a558b9e714c5970ed66f4d98989e7b6
receipt_id: a78ee96c-ee63-4e70-9269-4d8f52874371
receipt_path: docs/verification-receipts/3397e1d37a558b9e714c5970ed66f4d98989e7b6/a78ee96c-ee63-4e70-9269-4d8f52874371.json
full_suite_count: 2663
focused_test_count: 16
mutation_witness_count: 34
```

### Work review

- Sol's review of `C` = `3397e1d37a558b9e714c5970ed66f4d98989e7b6` and
  `A` = `a7f53f80366de4699fe152c399c752cf05fe7f9e`: **Approved, no
  executable findings.** Independent verification performed: ran all 16
  new post-merge-`Q`-producer tests; validated the committed `C..A`
  transition and receipt (`approval_eligible` recomputes to `true`);
  confirmed `check_repo.py` and `git diff --check` pass; confirmed the
  branch is clean and synchronized. The full 2,663-test suite was not
  independently re-run.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-18-post-merge-q-producer-27a2a5e
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-18T00:00:00Z
candidate_sha: 3397e1d37a558b9e714c5970ed66f4d98989e7b6
publication_commit_sha: a7f53f80366de4699fe152c399c752cf05fe7f9e
receipt_path: docs/verification-receipts/3397e1d37a558b9e714c5970ed66f4d98989e7b6/a78ee96c-ee63-4e70-9269-4d8f52874371.json
receipt_id: a78ee96c-ee63-4e70-9269-4d8f52874371
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-18. Merged `tooling/workflow-v3.2-post-merge-q-producer`
  at approved, reviewed commit `2635ffc608c20526c3ee7e5e12c7411c003ad5f5`
  (Sol's "Approved, no executable findings" verdict on `C`/`A`, above)
  into `main` via `git merge --no-ff`. Merge commit:
  `c33accdadd54fab756e8f4aef5be6a86123e148b`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `27a2a5e2cf81b2e347d1fa19012822fe1f0b6198`.
- Pre-merge checks: confirmed the feature branch and its origin both sat
  at `2635ffc`, and `main`/`origin/main` were both clean and
  synchronized at `27a2a5e` before merging.
- **This is the first merge to follow the documented `M -> Q` release
  sequence** (`LLM_WORKFLOW.md`'s "Project policy: `Q` is the next
  mainline commit after `M`"): `M` was created locally, not pushed;
  `verification_coordinator.run_post_merge_verification` was run
  against `M` in a disposable detached worktree (always full/final);
  its resulting artifact
  (`docs/post-merge/c33accdadd54fab756e8f4aef5be6a86123e148b/
  d1accc51-726b-4011-a41a-d24e4e12baaa.json`) reported all 11 steps
  PASS, 2,663 full-suite tests, 34/34 mutation witnesses, and an
  identical tracked-tree SHA before and after (zero content drift); this
  commit (`Q`) bundles that artifact addition with this merge-record
  append, as the single commit immediately following `M` on `main`'s
  mainline — never a merge-record-only commit.
- Post-merge verification, all run directly against merged `main`
  (independent of the `Q` producer's own run above):
  - `git diff --quiet 2635ffc HEAD` — zero content difference between
    merged `main` and the approved feature-branch tip, confirmed.
  - `git diff --check` — clean.
  - `python -m scripts.check_repo` — clean.
  - No migration/schema changes: `git diff --stat 27a2a5e..HEAD --
    backend/alembic backend/migrations` and `git log --oneline
    27a2a5e..HEAD -- backend/alembic backend/migrations` both empty.
  - `check_review.validate_published(C, A, R, M, Q)` — **succeeds**,
    returning the independently re-validated artifact, confirming the
    complete `C -> A -> R -> M -> Q` chain.
- STOP — report the synchronized final `main` SHA and stop. No Slice 3,
  no other Phase 3/4 parser, no other new slice, without separate
  explicit user authorization.

---

## Iteration 3

### Work done

- Date/agent: 2026-09-18, Claude Code (Sonnet 5). Risk class **H**
  (deliberately, not the R this project's own review discipline might
  default to for a pure-function, no-DB/network slice: ambiguous-alias
  false matches are Phase 3's own named primary risk — "confidently
  storing false facts from ambiguous text" — and this is novel,
  foundational infrastructure two future parsers depend on for
  correctness, not a "repeated established pattern"). Base `B` ->
  candidate `C`: `21dee74bae122bc634c77d3d0c55d03be128b716` -> this
  commit; new branch `phase-3/skill-taxonomy-foundation`, cut from a
  freshly verified clean `main` (`main` == `origin/main`, `check_repo.py`
  clean, `git diff --check` clean). `slice_kind: parser`. `slice_id:
  2026-09-18-skill-taxonomy-foundation-21dee74`. Implements the
  three-round-negotiated, user-approved skill-taxonomy-foundation
  proposal and its amendments.
- **Schema, grammar, and typed result** (`backend/app/normalization/
  taxonomy.py`, `backend/app/taxonomy/skills.yaml`): `skills.yaml` has
  exactly two top-level keys (`schema_version: 1`, `entries`); each entry
  has exactly three keys (`canonical_id`, `display_name`, `aliases`).
  `canonical_id` reuses `app.schemas.identifiers.is_canonical_slug()`
  verbatim — the same grammar already enforced on every `provider`/
  `source` column — never a new regex. `TaxonomyLookupResult` is a new,
  dedicated type (`status: TaxonomyLookupStatus` paired with
  `entry: TaxonomyEntry | None`, invariant-enforced in `__post_init__`
  exactly like `NormalizationResult`'s own value/provenance invariant,
  two static factories as the only construction path) — deliberately
  not a reuse of `NormalizationResult`/`Provenance`, since taxonomy-
  resolution success is orthogonal to a parser's own input-provenance
  trust level.
- **YAML safety**: no YAML library existed in this repo before this
  slice (confirmed by direct search). Adds `PyYAML==6.0.3` (pinned
  exactly like the existing `idna==3.19` precedent) to
  `backend/pyproject.toml`, plus a `yaml.*` mypy override (PyYAML ships
  no type stubs, same treatment as the existing `asyncpg.*` override).
  `yaml.safe_load` alone does not reject a duplicate YAML mapping key
  (silent last-write-wins) — `_StrictYamlLoader(yaml.SafeLoader)`
  overrides `construct_mapping` to raise instead, mirroring this
  project's own `verification_receipts._StrictDecoder` (JSON) duplicate-
  key rejection.
- **Lookup normalization** (precisely defined, not borrowed): checked
  `location.py`/`salary.py` directly rather than assume a shared
  convention — they share only NFKC-normalize + strip the project's
  `_WHITESPACE` set before diverging into field-specific casing
  (location/salary each uppercase some fields, lowercase others, per
  field). This taxonomy defines its own rule:
  NFKC-normalize -> strip `_WHITESPACE` -> collapse repeated internal
  whitespace -> lowercase-fold. Punctuation (`+`, `#`, `.`, `-`) is
  preserved literally (`c` vs `c++` vs `c#` must stay distinct).
  Whitespace adjacent to punctuation is not reconciled — a stated
  limitation, not an oversight.
- **Collision rejection**: both `canonical_id` and every alias become
  lookup keys, inserted into one flat global `normalized_key -> entry`
  index. Any collision — cross-entry, or two of the same entry's own
  keys (including an alias equal to its own entry's `canonical_id`) —
  is rejected at load time, no first/last-wins. A load-time check also
  requires `normalize(display_name)` be reachable via the entry's own
  `canonical_id` or an alias (rejecting an entry unreachable by its own
  display name).
- **Frozen seed** (15 entries, explicitly reduced from an earlier
  ~40-60 estimate to keep this a genuine foundation slice, not a
  vocabulary attempt): `python`, `javascript`(`js`), `typescript`(`ts`),
  `java`, `cpp`(`c++`,`cplusplus`), `csharp`(`c#`,`c-sharp`), `c`,
  `golang`(`go`), `rlang`(`r`), `postgresql`(`postgres`), `mysql`,
  `mongodb`(`mongo`), `kubernetes`(`k8s`), `docker`, `node.js`
  (`node`,`nodejs`). Every alias individually justified (see the
  slice's proposal record for the full rationale table); ambiguous
  near-misses deliberately excluded or kept unaliased (`c`/`cpp`/
  `csharp` never alias to each other; `java`/`javascript` never alias to
  each other; `postgres` included but `psql` deliberately excluded, since
  that names the CLI client, not the database skill).
- **Exact-match only, by design**: `TaxonomyIndex.lookup()` never
  tokenizes or scans a larger string — proven by a dedicated test
  feeding a full sentence and asserting `UNKNOWN`, alongside the same
  token resolving correctly on its own. No free-text scanning, no
  skill classifier, implemented in this slice.
- **Unblocks skill, not title**: a future `classify_skill` parser calls
  this lookup per already-segmented token and wraps results in its own
  `NormalizationResult[list[str]]`. Title is **not** unblocked — job
  titles are free-form multi-word phrases needing a different, likely
  hierarchical taxonomy schema, their own seed-sourcing rule, and a
  phrase/segment-extraction normalization approach; only the general
  pattern (versioned, duplicate-rejecting, schema-validated YAML with a
  typed unknown result) is a reusable template, never this schema or
  data directly.
- **Documentation corrections, kept bounded to exactly the identified
  stale passages**: `docs/ROADMAP.md`'s Phase 3 status text incorrectly
  claimed the location classifier was "not merged, not complete" —
  independently verified via `git log`/`git show` that it merged at
  `a32b5cc` (approval `c1a5235`) and is a genuine ancestor of `main`;
  corrected, and this slice's own status recorded alongside it.
  `docs/ARCHITECTURE.md`'s identical duplicate of the same stale claim
  (it explicitly deferred to ROADMAP and inherited the staleness) is
  also corrected; `taxonomy.py`/`skills.yaml` marked implemented
  (candidate/publication stage); `titles.py`/`skills.py`/`titles.yaml`/
  `industries.yaml`/`aliases.yaml` explicitly left as still-planned, not
  touched further.
- **Adversarial self-review** (fresh subagent; DB/ORM/concurrency
  questions from `LLM_WORKFLOW.md`'s twelve-question pass explicitly
  marked not-applicable, confirmed by the import-boundary test and by
  direct inspection of this module's import list). No Critical/High
  findings. One Medium finding fixed: `TaxonomyIndex`'s "immutable"
  claim was asserted but not enforced — `@dataclass(frozen=True)` only
  blocks rebinding the `_by_normalized_key` attribute, never in-place
  mutation of the `dict` it pointed to (reproduced: assigning into the
  dict directly silently corrupted a lookup). Fixed: `__post_init__` now
  defensively copies the caller's mapping into a `MappingProxyType`, so
  neither the constructor's caller nor any other holder of a reference
  can mutate the index post-construction — proven by two new regressions
  (direct in-place assignment now raises `TypeError`; mutating the
  caller's own source dict after construction no longer affects the
  index, proving a copy was made, not merely a wrap). One Low finding
  fixed: a blank-after-whitespace-strip alias lacked a dedicated test
  (behavior was already correct — added the missing regression). One
  Low/informational finding (an NBSP-only `display_name` is still
  correctly rejected, just under the "not reachable" message rather than
  "blank") left as-is — fails closed either way, a message-clarity nit
  only.
- Files changed: `backend/app/normalization/taxonomy.py` (new);
  `backend/app/taxonomy/skills.yaml` (new); `backend/tests/
  test_normalization_taxonomy.py` (new, 63 tests); `backend/tests/
  fixtures/taxonomy/*.yaml` (new, 12 fixtures: 11 fault-injection, 1
  positive control);
  `backend/pyproject.toml` (edited — `PyYAML==6.0.3` pin, `yaml.*` mypy
  override); `docs/ROADMAP.md`, `docs/ARCHITECTURE.md` (edited, bounded
  stale-passage corrections only); `docs/LLM_HANDOFF.md` (this entry,
  plus the two-iteration rotation below). No production parser other
  than this new module touched; no migration/model/service/API file
  touched; no database lifecycle operation performed; no provider
  contact of any kind.
- **Two-iteration rotation applied**: the oldest iteration (the original
  v3.2 activation candidate/review cycle, C1-C6) is deleted; its two
  remaining internal cross-references from the newer iteration (which
  had read "Iteration 1" as a pointer to it) were first rewritten as
  self-contained prose naming the actual work directly, so they do not
  dangle after deletion. The former Iteration 2 (the C7-C10 correction
  saga, merge record, and post-merge-evidence-status note) and
  Iteration 3 (the Q-producer slice's Work done/review/merge
  record/`Q` publication) are renumbered to Iteration 1 and Iteration 2
  respectively; this entry becomes the new Iteration 3.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (161
  source files, backend + `.claude/hooks`). Full pytest suite: **2726
  passed** (2663 + 63 new). `check_repo.py` exits 0. `git diff --check`
  clean.
- Deviations/known limitations: none beyond what the proposal itself
  already disclosed (a small, explicitly non-exhaustive 15-entry seed;
  the Go/R exact-match positive controls are documented as not
  guaranteeing a future classifier's word-boundary safety), plus the
  informational display-name-blank-message nit noted above.
- STOP — this is a bounded parser-foundation slice only. Do not author
  `R`, merge, create `Q`, or begin any title-parser work without
  separate explicit user authorization.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-09-18-skill-taxonomy-foundation-21dee74
slice_kind: parser
risk_class: H
base_sha: 21dee74bae122bc634c77d3d0c55d03be128b716
declared_gate: final
```
