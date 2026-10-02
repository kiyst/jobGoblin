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

- Date/agent: 2026-10-01, Claude Code (Opus 5.5). Same slice
  (`slice_id: 2026-09-30-phase3-baseline-correction-go-remote-25ac578`,
  risk class **H**, `slice_kind: parser`, `declared_gate: final`), same
  branch `phase-3/baseline-correction-go-remote-v2`, same base
  `25ac578f6e980eb73964de17d8f32ca1f2695867`. One bounded `C3`/`A3`
  correction cycle for Sol's two findings against `C2`/`A2`. `C`
  (`70e0e92`), `C2` (`467ec75`) and `A2` (`be89084`) are preserved
  unamended; `C3` is `A2`'s direct child. **`A2`'s receipt
  (`24a31360-502b-4c35-8be3-a35374679077`) is superseded and must not be
  reused** -- a fresh receipt is required for `C3`. Sol accepted the
  remote office-attendance blocker, the exact `remote_type_cases.json`
  owner mapping, the Git scope, and `A2`'s receipt structure; those are
  byte-for-byte unchanged here. Not approved: awaiting Sol's re-review.
  Ending commit: this commit.
- **Sol P1 (go rescue crossed a newline)**: confirmed reproduction at
  `C2` -- `"Production experience with Python,\nGo, Java."` returned
  `golang`/`java`/`python`. Root cause: `_go_list_neighbor_rescue` looked
  up the cue sentence by the raw *segment's* start offset, and the
  segment after `"Python,"` starts on the newline itself, which belongs
  to the first line's sentence span. Fix: a new `_segment_token_offsets`
  helper gives each token's own absolute source offset (index-aligned
  with `_tokenize_segment`), and `_sentence_index_at` places the `Go`
  *token* in its sentence. The same audit found a second instance of
  the defect class that Sol did not list: the accepted neighbor could
  also come from another line (`"Production experience: Go,\nPython."`
  returned `golang`), contrary to the frozen contract's existing rule
  that the cue, `go`, and its structural evidence share one sentence.
  The neighbor token's own offset must now also fall in `Go`'s sentence.
  Every prior structural guard is unchanged: `go`-only scope, sole-token
  segment, same-sentence cue, immediate raw-segment adjacency, no
  skipping empty/intervening segments, boundary-touching unambiguous
  neighbor, strong-cue requirement, weak-cue exclusion, anchored-region
  behavior, and `c`/`r`/`node` behavior.
- **Sol P2 (exhaustive allowlist record was incomplete)**: the evaluator
  output diff also changes five `false_positive_outside_frozen_set`
  denominators (dev `0/21 -> 0/22`, holdout `0/14 -> 0/15`, combined
  `0/35 -> 0/37`, Anthropic `0/9 -> 0/10`, GitLab `0/14 -> 0/15`), which
  follow mechanically from the precision denominators. The inaccurate
  "no other line changed" claim in Iteration 1 is replaced in place with
  the precise rule: no output line changes outside the complete approved
  metric/record allowlist plus these five denominator changes. The
  headline precision/recall, mismatch counts, the four corrected records,
  and the absence of new false-positive/confidently-wrong results were
  already correct. No baseline report, corpus, evaluator, label, or
  taxonomy changed.
- Files changed (closed correction list):
  `backend/app/normalization/skills.py` (token-offset sentence lookup,
  same-sentence neighbor, docstring), `backend/tests/
  test_normalization_skills.py` (3 direct unit tests for the new
  helpers), `backend/tests/fixtures/normalization/skill_cases.json`
  (92 -> 98 cases), `docs/LLM_HANDOFF.md` (this entry, the P2
  correction in Iteration 1, and the rotation above). New regression
  cases: comma immediately before newline, comma before newline plus
  indentation, semicolon immediately before newline (all: `python`,
  `java`, no `golang`); same-line positive control and cue-bearing line
  after an unrelated line (both: `golang`, `java`, `python`); only
  neighbor on the following line (`python` only).
- Verification: `ruff format --check`/`ruff check` clean; `mypy` clean
  (171 source files); focused skills + remote + verification-scope
  **326 passed** (was 317; remote and verification-scope suites
  unchanged); full backend suite **3187 passed** (was 3178 at `C2`; +6
  fixtures, +3 unit tests);
  `check_repo.py` clean; `git diff --check` clean. `python -m
  scripts.evaluate_phase3_corpus` output is byte-identical to the
  approved `C2` output, and a mechanical line-by-line check of its diff
  against the immutable baseline matches the corrected exhaustive
  allowlist exactly (36 removed / 24 added lines, none unexpected, none
  missing).
- Mutation proofs: **P1** -- restoring the defective segment-start offset
  makes the three delimiter-before-newline regressions fail by returning
  a spurious `golang`, while both positive controls still pass;
  restoring the fix passes all. **Neighbor same-sentence guard** --
  removing the neighbor sentence check makes the following-line-neighbor
  regression fail; restored, it passes. Because the offset change sits
  inside the same function as the other skills guards, all six earlier
  skills guard mutations (go-only scope, strong-cue relevance,
  same-sentence cue, standalone segment, no empty-segment skip,
  boundary-touching neighbor) were re-run against `C3`'s code: each
  isolating witness fails under its mutant and passes after
  restoration. The five remote guard mutations were not re-run:
  `remote.py`, its tests, and its fixture are byte-identical to `C2`,
  and `skills.py` shares no code with `remote.py` (its import-boundary
  test forbids cross-parser imports), so no change here can reach them;
  the remote focused suite stays green.
- Adversarial review (offsets, delimiters before newlines, leading
  whitespace, empty segments, sentence topology): correct for CRLF before
  `Go`, an empty segment before a newline, a cue later on `Go`'s own
  line, blank lines, tab indentation, a parenthesized `Go` on either side
  of a newline, a terminator followed by a newline, `Go` first in the
  text, and a neighbor separated from `Go` by a terminator. Residual,
  unchanged by design: a lone CR or U+2028 is not a sentence boundary in
  this module (only `\n` and `.!?` runs are, matching the existing
  anchor grammar and the contract's no-Unicode-fuzzy-matching rule); the
  HTML converter already normalizes CR/CRLF to `\n` upstream.
- Deviations/known limitations: the same-sentence neighbor check goes
  beyond Sol's literal P1 text but enforces an already-approved contract
  rule within the closed file list; disclosed here for review. The three
  residual `golang` misses, the `salary.*` wiring gap, and the
  exposed-holdout caveat on `gitlab:8512432002` are unchanged.
- STOP -- this commit is candidate `C3` (see `workflow-metadata` below,
  `state: pending`). Next: a fresh receipt-eligible `--gate final`
  coordinator run against `C3` and, only if it passes, publication `A3`.
  No `R`, merge, `M`, `Q`, remote or verification-mapping change,
  provider contact, production data access, or title normalization.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-30-phase3-baseline-correction-go-remote-25ac578
slice_kind: parser
risk_class: H
base_sha: 25ac578f6e980eb73964de17d8f32ca1f2695867
declared_gate: final
executed_gate: final
candidate_sha: 14083dd27c73609e67bdaac2793f3769bdb367e7
receipt_id: dcbb1847-7130-4f78-a833-b51732754965
receipt_path: docs/verification-receipts/14083dd27c73609e67bdaac2793f3769bdb367e7/dcbb1847-7130-4f78-a833-b51732754965.json
fixture_path: backend/tests/fixtures/normalization/skill_cases.json
fixture_count: 98
```

### Work review

- Date/reviewer: 2026-10-01, Sol. Diff reviewed: candidate `C3`
  (`14083dd`) and its publication `A3` (`5ec94f3`) on
  `phase-3/baseline-correction-go-remote-v2`, against the frozen
  correction contract, Sol's prior P1/P2 findings, and the closed
  affected-file list.
- Dispositions:
  - P1 candidate-offset correction: accepted. `_go_list_neighbor_rescue`
    now resolves the `go` token's sentence from its own token offset, so a
    relevance cue can no longer be borrowed across a newline.
  - Same-sentence neighbour enforcement: accepted as enforcement of the
    frozen contract's same-sentence requirement, not new semantics.
  - P2 corrected evaluator allowlist: accepted, including the five
    `false_positive_outside_frozen_set` denominator changes.
  - Residual lone-CR / U+2028 sentence-boundary disclosure: accepted as a
    disclosed limitation.
  - Inherited `remote_type` office-attendance correction: accepted
    unchanged.
  - Exact-path `remote_type_cases.json` fixture ownership mapping:
    accepted unchanged.
  - Fresh `C3` receipt and the `A3` `pending` -> `published` transition:
    accepted.
  - Git structure (single-parent `C3` -> `A3`) and affected-file
    boundaries: accepted.
- Independent verification performed: 326 focused tests passed; the
  defective candidate-offset mutant made all three newline regressions
  fail; removing the same-sentence neighbour check made its dedicated
  regression fail; restored targeted probes passed; `check_repo.py` and
  `check_handoff.py` passed; candidate and publication `git diff --check`
  passed; `require_single_parent(A3, C3)` and
  `validate_c_to_a_transition(C3, A3)` passed.
- Relied on, not repeated: the genuine receipt's 3187-test full suite and
  34/34 mutation witnesses. The six earlier skills mutation runs were
  inspected but not repeated. The five `remote_type` mutations were not
  rerun because that surface is byte-identical and unreachable from the
  skills change.
- Findings by severity with exact references: none.
- Missing/inconclusive checks: none beyond the relied-on receipt evidence
  stated above.
- Verdict: **approved** -- no executable findings.
- Exact bounded correction: none required.
- STOP -- record-only. No merge, `M`, `Q`, executable-file modification,
  provider contact, production-data access, title normalization, or new
  slice is authorized by this review.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-30-phase3-baseline-correction-go-remote-25ac578
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-01T18:41:07.778740+00:00
candidate_sha: 14083dd27c73609e67bdaac2793f3769bdb367e7
publication_commit_sha: 5ec94f376bc13cfb00b00152ce822184f8bed4f1
receipt_path: docs/verification-receipts/14083dd27c73609e67bdaac2793f3769bdb367e7/dcbb1847-7130-4f78-a833-b51732754965.json
receipt_id: dcbb1847-7130-4f78-a833-b51732754965
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-01. Merged `phase-3/baseline-correction-go-remote-v2`
  at approved, reviewed commit `3629be3b3bd267358f3b515cfeae14179a74cce2`
  (`R`; Sol's "approved -- no executable findings" verdict on
  `C3=14083dd`/`A3=5ec94f3`, above) into `main` via `git merge --no-ff`.
  Merge commit: `689f94c65ebdb278dba0c8bb20bb6b1c272b9716`. Pre-merge
  `main`/`origin/main` tip (rollback boundary):
  `25ac578f6e980eb73964de17d8f32ca1f2695867`.
- Pre-merge checks: freshly fetched `origin`; confirmed the feature
  branch and its origin both sat at `3629be3`, and `main`/`origin/main`
  were both clean and synchronized at `25ac578` before merging;
  re-confirmed `validate_c_a_r_chain(C3, A3, R)` and
  `check_merge_eligibility(C3, A3, R)` both still returned `approved`
  with `findings: none` and `reviewer_model: Sol Medium`, and that
  receipt `dcbb1847-7130-4f78-a833-b51732754965` remained schema-valid,
  bound to `C3`, and independently recomputed as approval-eligible.
- Followed the documented `M -> Q` release sequence: `M` was created
  locally, not pushed; zero content difference between `M` and `R`
  confirmed (`git diff 3629be3 689f94c`, empty); `check_review.
  validate_merge(R, M, 25ac578)` confirmed `M`'s exact two-parent shape;
  `verification_coordinator.run_post_merge_verification` was run against
  `M` in a disposable detached worktree (always full/final) -- artifact
  `6cf79e0d-73d9-4035-971d-1defbca18cf3`, all 11 steps PASS, full pytest
  suite **3187 passed**, all 34 mutation witnesses pass, no migration
  triggered, worktree initial/final snapshots identical with no residual
  worktree entry, cleanup PASS. `Q` was authored as `M`'s direct mainline
  child, bundling that artifact with this append-only merge record in
  one commit -- this entry itself.
- Post-merge evidence status: `docs/post-merge/
  689f94c65ebdb278dba0c8bb20bb6b1c272b9716/
  6cf79e0d-73d9-4035-971d-1defbca18cf3.json`, referencing original
  receipt `dcbb1847-7130-4f78-a833-b51732754965` (`docs/
  verification-receipts/14083dd27c73609e67bdaac2793f3769bdb367e7/
  dcbb1847-7130-4f78-a833-b51732754965.json`). `check_review.
  validate_published(C3, A3, R, M, Q)` and `verification_coordinator.
  confirm_main_unchanged` are run immediately before push; see the
  agent's final report for their results rather than restating them here
  ahead of time.
- STOP -- report the synchronized final `main` SHA and stop. No title
  normalization, provider integration, persistence wiring, API/
  tool-calling work, another parser correction, or any new slice without
  separate explicit user authorization.

## Iteration 2

### Work done

- Date/agent: 2026-10-02, Claude (implementer). Branch `phase-3/title-normalization`,
  base `aed2694720b0344ae54feeef1916805f91e6b508` (Q of the Go/remote correction).
  Ending commit: this commit (candidate `C`).
- Slice: Phase 3 title classifier, Class H, `slice_kind: parser`, `gate: final`.
  Frozen contract, in precedence order: the title-normalization proposal; Sol's
  A1-A12 binding amendment table; Sol's corrected A2/A4/A5 fragment and final
  12-item mutation-witness inventory. Decisions applied: D1 `INFERRED` only; D2 all
  30 realistic titles as smoke/regression cases; D3 `forward deployed engineer`
  unsupported; D4 nine-title vocabulary frozen.
- Files (closed nine-file list, all within it):
  `backend/app/normalization/titles.py` (new),
  `backend/tests/test_normalization_titles.py` (new),
  `backend/tests/fixtures/normalization/title_cases.json` (new),
  `backend/scripts/verification_scope.py`, `backend/tests/test_verification_scope.py`,
  `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, this file.
- Implementation: `classify_title(title) -> TitleResult` (`canonical_title`,
  `role_family`, `outcome`); the exact contract tables, per-segment
  `MATCH`/`AMBIGUOUS`/`NONE` verdicts, and A5/corrected-fragment precedence; the A7
  bounded per-code-point policy (no unrestricted NFKC, no Unicode casefold); the A6
  single approved decoration; the A8 `TitleResult` invariants; and A9 import-time
  table validation (`TitleVocabularyError`). No regular expressions; no record IDs,
  employer names, splits, or per-title exceptions. Imports only the standard library,
  `types.py`, and `identifiers.py`.
- A11: separate exact-path `_TITLE_FIXTURE_FILES` (`title_cases.json` ->
  `test-fixture:title-classifier`) registered at both exact-map sites. Tests cover the
  exact category, disjointness from every other fixture map, no contract family, no
  literal focus target, `unrelated_cases.json` still raising
  `OwnerMappingRequiredError`, and clear-and-restore fault injection.
- Fixture: 200 cases (42 positive, 27 negative, 27 boundary, 17 ambiguity, 21
  collision, 36 unicode, 30 realistic). The expectations were hand-authored, not
  produced by running the parser. Realistic cases are byte-identical to the frozen
  corpus titles (a test enforces this). They are primary-reviewer-approved
  smoke/regression expectations only, never accuracy, holdout, coverage, precision,
  recall, or generalization evidence. Result: 22 matched, 6 unsupported, 2 ambiguous,
  with exactly Sol's per-record lists.
- Unchanged: `python -m scripts.evaluate_phase3_corpus` output is byte-identical to
  its output at `aed2694` (1366 lines). The frozen corpus, annotations, evaluator,
  every other parser, the skill taxonomy, provider mapping, persistence, migrations,
  and APIs are untouched.
- Local checks: 362 focused tests passed (`tests/test_normalization_titles.py` 276,
  `tests/test_verification_scope.py` 86). ruff, ruff format and mypy are clean on the
  changed code. The full suite and all witnesses are left to the coordinator's
  `gate=final` receipt, recorded in `A`.
- Mutation proofs (ad hoc harness against `titles.py`; source restored byte-for-byte,
  SHA-256 verified): **11 of 12 frozen witnesses proven** (01, 03-12). Each failed
  under its mutant and passed after restoration; the positive controls for 03 and 09
  passed both ways.
  **Witness 02 is NOT PROVEN as specified.** `Technical Recruiter Software Engineer`
  stays `AMBIGUOUS` with `PREFIX_BLOCKERS` disabled, because `recruiter` is also in the
  frozen `PREFIX_ROLE_DESIGNATORS`. Every blocker except `of`/`for`/`to`/`and`/`or`/
  `&` is also a designator, so no witness containing one of the others can isolate
  this guard. The guard itself is load-bearing: the non-inventory fixture cases
  `collision_prefix_blocker_and_only` and `collision_prefix_blocker_for_only` both
  fail under the same mutant. The inventory was not changed; that decision is Sol's.
- Self-review (contract-conformance and counterexample passes): no defect found.
  Contract-exact behaviours disclosed for review:
  - The decoration is ignored only when its content is ASCII letters and spaces, so
    `[Expression-of-Interest]` is processed normally (this resolves "normalized tokens
    are exactly" conservatively).
  - `counsels` is not a designator (the frozen set has `counsel` only).
  - `leads` is an allowed prefix (only the later-terminal set contains it).
  - `Software Engineer II` is `unsupported` (an alias must be the suffix).
  - `Software Engineering Manager` is `ambiguous` (A3 `software` signal).
- Environment: one harness write failed with a transient Windows `Errno 22`. The file
  was verified intact, and the harness was rerun with write-retry and hash
  verification. The local Postgres container was started for verification.
- Outside this slice: the 3 remaining `skills.golang` misses (disclosed backlog) and
  the `salary.*` missing-wired-input gap (future provider-composition work).
- STOP after `A` for Sol's independent review. No `R`, merge, persistence wiring,
  Phase 3 exit audit, or Phase 4 work.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-02-phase3-title-normalization-aed2694
slice_kind: parser
risk_class: H
base_sha: aed2694720b0344ae54feeef1916805f91e6b508
declared_gate: final
fixture_path: backend/tests/fixtures/normalization/title_cases.json
fixture_count: 200
```
