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

- Date/agent: 2026-09-28, Claude Code (Sonnet 5). Same slice, same
  authorization (`slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-
  0dae468`, risk class **H**, `slice_kind: tooling`, `declared_gate: final`).
  Same branch `phase-3/realistic-corpus-freeze-evaluation`, base
  `0dae4683645599369d41d0228b0edad1cfad73ce` (unchanged, reconfirmed
  against freshly-fetched `origin/main` immediately before this commit).
  Completes the remainder of the approved 8-item freeze/evaluation
  contract: two procedurally-blind independent annotation passes (Claude
  and Sol, each 30 records x 28 labels against rubric 1.0.4, sealed and
  hashed before either was revealed to the other), the full human
  adjudication/audit interview (95 genuine disagreements + 220 required
  agreement audits, every decision made and recorded by the user
  personally, none by an agent), the deterministic corpus freeze, and the
  first baseline evaluation. Ending commit: this commit.
- Base -> ending commit: `0dae4683645599369d41d0228b0edad1cfad73ce` ->
  this commit.
- Outcome: publishes durable, tracked copies of the two sealed annotation
  passes and the adjudication/audit evidence, the frozen corpus fixture,
  and a tracked baseline evaluation report -- exactly the closed set of
  outputs authorized for this completion. No release manifest is created:
  that concept traces only to a separate, unapproved future
  three-annotator proposal, not to this slice's actual contract, per
  explicit user clarification this round. Conventions applied:
  deterministic employer-sorted dev/holdout split (`Anthropic`+`Discord`
  dev, `GitLab` holdout -- `GitLab` is lexicographically last);
  adjudication/audit identity is exactly `user` throughout, never an
  agent/model identity; create-only/atomic writes for every new sealed or
  durable artifact. No new semantic decision -- this is mechanical
  completion and publication-preparation of the already-frozen,
  previously-approved contract; no rubric, taxonomy, classifier, or
  provider-mapping change of any kind.
- Files changed: `docs/evaluation/phase3-realistic-pass-claude.json`
  (new, durable byte-identical copy of the sealed Claude pass, sha256
  `f732c9d0f1fa0f19609dc84c7346fab69d84d0f3646ac18a87b44ad5b87bc71d`);
  `docs/evaluation/phase3-realistic-pass-sol.json` (new, durable
  byte-identical copy of the sealed Sol pass, sha256
  `b6ce0ff33a94aa8afcc4332f26596ec548f264a6429f643ae696d5b1042227e1`);
  `docs/evaluation/phase3-realistic-adjudication-audit.json` (new,
  schema-conformant adjudication/audit artifact mechanically derived from
  the completed pending-adjudication working file, sha256
  `8de5a3faf48e662fc13cad7b5d8c1d8958061cbf06f04e38862358ff300f8ad9`);
  `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json` (new,
  frozen corpus, 30 records/840 labels, 20 dev/10 holdout, sha256
  `1863541bb784419be16bf4ffcf88bf1b4408c951a03b12008e9645e9f18e6930`);
  `docs/evaluation/phase3-realistic-corpus-baseline-report.md` (new,
  tracked baseline report embedding the verbatim deterministic evaluator
  output plus source/lineage hashes); `docs/ROADMAP.md` (Phase 3 status
  was stale -- still named the superseded branch and claimed "not yet
  reviewed, not merged" for the prior slice, which is in fact already
  merged at `M=41963baf4797b1b2b6fee1f72311dd6b84d7b6a3`/
  `Q=0dae4683645599369d41d0228b0edad1cfad73ce`; corrected and recorded
  this slice's own completed work); `docs/LLM_HANDOFF.md` (this entry,
  Iteration 1's F15 "six"->"seven" wording correction, its corrected STOP
  note, and the iteration rotation).
- Verification: `ruff format --check`/`ruff check` clean (171 files, no
  Python file touched this round); `mypy` clean (171 source files); full
  backend suite **3128 passed** (unchanged from the prior checkpoint --
  no test file touched this round); `check_repo.py` clean; `git diff
  --check` clean. Receipt-eligible `--gate final` verification via
  `scripts.verification_coordinator.run_receipt_eligible_verification`,
  run against this exact candidate commit from a disposable detached
  worktree: receipt id/path and executed-gate confirmation recorded in
  this same block's `published` transition on the direct child commit.
- Adversarial self-review (tooling-slice abbreviated pass): confirmed the
  "release manifest"/"lineage sidecar" terms the initiating message used
  trace only to the separate, unapproved future three-annotator proposal
  (grepped this session's own record), never to this slice's actual
  8-item contract or to `verification_scope.py`'s one pre-registered
  fixture path -- raised this discrepancy to the user before writing
  anything, rather than silently importing unauthorized future-workflow
  vocabulary; confirmed by direct byte/string comparison (not merely
  re-hashing) that all three durable `docs/evaluation/` copies are
  identical to their sealed `.evaluation-staging/` originals and that the
  baseline report's embedded evaluator output is byte-for-byte identical
  to the actual deterministic run (reproduced twice, identical both
  times); confirmed `docs/ROADMAP.md`'s Phase 3 paragraph was genuinely
  stale before editing it, rather than assuming staleness; confirmed the
  F15 handoff wording defect (a stated regression-test count of "six"
  against Iteration 1's own recorded 76 -> 83 = +7 delta) is exactly the
  harmless discrepancy previously noted and deferred, not a substantive
  count error. No regression test applicable this round -- no executable
  code changed. Remaining limitation: the baseline report's disclosed
  findings (a `salary.*` wiring gap, several supported-field abstentions,
  one `skills.golang` recall gap, two `remote_type` ambiguous false
  positives) are intentionally left uncorrected, per contract, pending a
  separately authorized future correction slice.
- Deviations/known limitations: none beyond what the baseline report
  itself discloses (see that report's own "Headline result"/"Holdout
  exposure" sections). No release manifest was created -- confirmed with
  the user this was never part of this slice's actual contract.
- STOP -- candidate `C` for this slice (see `workflow-metadata` below,
  `state: pending`). No `R`, merge, `M`, or `Q` is authorized by this
  commit. Do not fix any baseline finding, rerun classifiers for
  correction purposes, contact providers, access the database, or begin
  title normalization. Waiting for Sol's independent review of this
  candidate.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-0dae468
slice_kind: tooling
risk_class: H
base_sha: 0dae4683645599369d41d0228b0edad1cfad73ce
declared_gate: final
executed_gate: final
candidate_sha: 03609018215285cca21dd31fc126978fe2de8d15
receipt_id: 338d5c4b-37fd-47dd-a220-f67919ca45de
receipt_path: docs/verification-receipts/03609018215285cca21dd31fc126978fe2de8d15/338d5c4b-37fd-47dd-a220-f67919ca45de.json
```

### Work review

- Date/reviewer: 2026-09-30, Sol. Diff reviewed: `C..A`
  (`0360901..1ec12a6`) on `phase-3/realistic-corpus-freeze-evaluation`,
  against the approved two-annotator pilot contract and its closed
  affected-file list only -- the separate, unapproved future
  three-annotator proposal's requirements (release manifest, lineage
  sidecar terminology) were explicitly not applied.
- Independent verification performed: confirmed `A` is `C`'s direct
  single-parent child; confirmed `C..A` changes only the one new receipt
  file plus the `workflow-metadata` block's `pending` -> `published`
  transition in `docs/LLM_HANDOFF.md`, no other byte or path; independently
  recomputed the receipt's schema validity and `approval_eligible: true`;
  confirmed `docs/evaluation/phase3-realistic-pass-claude.json` and
  `docs/evaluation/phase3-realistic-pass-sol.json` are byte-identical to
  their sealed `.evaluation-staging/` originals; confirmed
  `docs/evaluation/phase3-realistic-adjudication-audit.json` is
  byte-identical to the validated working artifact and contains exactly
  95 completed disagreements and 220 completed required agreement audits;
  confirmed the frozen corpus has 30 records x 28 labels = 840 labels
  with valid embedded lineage; independently rebuilt the corpus and its
  SHA-256 matched the committed
  `1863541bb784419be16bf4ffcf88bf1b4408c951a03b12008e9645e9f18e6930`
  exactly; confirmed the employer-disjoint split is 20 dev (Anthropic +
  Discord) / 10 holdout (GitLab); independently reran
  `python -m scripts.evaluate_phase3_corpus` and its output matched
  `docs/evaluation/phase3-realistic-corpus-baseline-report.md`'s embedded
  report byte-for-byte; confirmed the report accurately discloses the
  baseline findings (salary wiring gap, supported-field abstentions, one
  skills recall gap, two remote_type ambiguous false positives) and the
  exposed-holdout limitation; confirmed no classifier, taxonomy, provider
  mapping, rubric label, corpus decision, or file outside the closed
  affected-file list changed; confirmed the deferred F15 "six"->"seven"
  wording correction is accurate and bounded.
- Findings by severity with exact references: none.
- Missing/inconclusive checks: focused tests' first attempt failed only
  on an inaccessible inherited Windows temp directory (environmental, not
  a defect in the candidate); a rerun with an isolated writable base
  passed 126/126. No other check was inconclusive.
- Verdict: **approved**.
- Exact bounded correction: none required.
- STOP -- record-only. No merge, `M`, `Q`, executable-file modification,
  parser correction, provider contact, database access, or new slice is
  authorized by this review.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-0dae468
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-30T00:56:08.703120+00:00
candidate_sha: 03609018215285cca21dd31fc126978fe2de8d15
publication_commit_sha: 1ec12a68d933ed8addc0d7f930c8799de3c93d4b
receipt_path: docs/verification-receipts/03609018215285cca21dd31fc126978fe2de8d15/338d5c4b-37fd-47dd-a220-f67919ca45de.json
receipt_id: 338d5c4b-37fd-47dd-a220-f67919ca45de
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-30. Merged `phase-3/realistic-corpus-freeze-evaluation`
  at approved, reviewed commit `babc74fff16b5575f482bbb37fa947f11429f1bf`
  (`R`; Sol's "approved, findings: none" verdict on `C=0360901`/
  `A=1ec12a6`, above) into `main` via `git merge --no-ff`. Merge commit:
  `fccbf62d2f5f7df10f46b174c1aff96ed18b3ef7`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `0dae4683645599369d41d0228b0edad1cfad73ce`.
- Pre-merge checks: freshly fetched `origin`; confirmed the feature
  branch and its origin both sat at `babc74f`, and `main`/`origin/main`
  were both clean and synchronized at `0dae468` before merging;
  re-confirmed `validate_c_a_r_chain(C, A, R)` and
  `check_merge_eligibility(C, A, R)` both still returned `approved`
  immediately beforehand, with no unexpected advancement or divergence
  on either ref.
- Followed the documented `M -> Q` release sequence: `M` was created
  locally, not pushed; zero content difference between `M` and `R`
  confirmed (`git diff babc74f fccbf62`, empty); `verification_
  coordinator.run_post_merge_verification` was run against `M` in a
  disposable detached worktree (always full/final) -- artifact
  `175e0726-8d9c-4d0a-abf7-83fecd886540`, all 11 steps PASS, full pytest
  suite **3128 passed**, all 34 mutation witnesses pass, no migration
  triggered, cleanup PASS. `Q` was authored as `M`'s direct mainline
  child, bundling that artifact with this append-only merge record in
  one commit -- this entry itself.
- Post-merge evidence status: `docs/post-merge/
  fccbf62d2f5f7df10f46b174c1aff96ed18b3ef7/
  175e0726-8d9c-4d0a-abf7-83fecd886540.json`, referencing original
  receipt `338d5c4b-37fd-47dd-a220-f67919ca45de` (`docs/
  verification-receipts/03609018215285cca21dd31fc126978fe2de8d15/
  338d5c4b-37fd-47dd-a220-f67919ca45de.json`). `check_review.
  validate_published(C, A, R, M, Q)` and `verification_coordinator.
  confirm_main_unchanged` are run immediately before push; see the
  agent's final report for their results rather than restating them here
  ahead of time.
- STOP -- report the synchronized final `main` SHA and stop. No
  baseline-driven parser corrections, title-normalization work, provider
  contact, database access, or another slice without separate explicit
  user authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-30, Claude Code (Sonnet 5). First post-baseline
  Phase 3 correction slice (`slice_id: 2026-09-30-phase3-baseline-
  correction-go-remote-25ac578`, risk class **H**, `slice_kind: parser`,
  `declared_gate: final`), branch
  `phase-3/baseline-correction-go-remote-v2`, base
  `25ac578f6e980eb73964de17d8f32ca1f2695867` (main tip immediately after
  the freeze/evaluation slice's `Q`, reconfirmed against `origin/main`
  immediately before branching). Implements the frozen implementation
  contract (original proposal + A1-A4 amendment table + Sol's six
  further binding implementation amendments on the mechanics and
  affected-file list) for exactly the two disclosed baseline defects:
  the `skills.golang` recall gap and the `remote_type` location-
  conditional ambiguous false positives. No rubric, taxonomy, corpus
  fixture, provider mapping, or unrelated parser touched. This replaces
  (on a fresh branch from the same base) an earlier implementation
  attempt on `phase-3/baseline-correction-go-remote` that predated
  Sol's six mechanical-precision amendments; that earlier branch is
  superseded and not merged. Ending commit: this commit.
- Outcome: `skills.py` gains a new `_go_list_neighbor_rescue` function,
  restricted to `normalized_key == "go"` only (never `c`/`r`/`node`),
  requiring all three: (1) `go` is the sole token in its own raw
  delimiter-split segment; (2) the token touching the shared boundary of
  the immediately preceding or immediately following raw segment --
  never a segment further away, never reached by skipping an empty or
  intervening segment, and never a match elsewhere inside that adjacent
  segment -- is an unambiguous taxonomy match; (3) the cue-scoped
  sentence containing it (split on a newline or a genuine `.!?`
  terminator run, this module's own ASCII/covered-whitespace
  conventions throughout, no Unicode-aware fuzzy matching anywhere in
  the new code) contains one of exactly nine closed, strong candidate-
  qualification/work-history cue phrases. Per Sol's binding
  clarification, bare `programming language(s)`/`technology stack`/
  `tech stack` are deliberately excluded from the cue set (they can
  describe a product or company environment, not a candidate
  requirement) -- proven by dedicated colon-delimited and literal
  negative-control fixtures that isolate the cue check from the
  standalone/adjacency checks. The existing anchored-region mechanism
  is untouched. `remote.py` gains one new closed phrase, `"required to
  be in the office"`, processed through the *same* candidate/negation/
  context-exclusion pipeline as every other description phrase but
  tagged as a non-value blocker (never enters `survivors`, can never
  itself become `onsite`); `classify_remote_type` downgrades an
  otherwise-final `remote` result to `(None, unavailable)` when the
  blocker is present, and never touches an independently resolved
  `hybrid`/`onsite` result.
- Files changed (exactly the closed affected-file list, no other path):
  `backend/app/normalization/skills.py`,
  `backend/tests/test_normalization_skills.py`,
  `backend/tests/fixtures/normalization/skill_cases.json` (72 -> 92
  cases), `backend/app/normalization/remote.py`,
  `backend/tests/test_normalization_remote.py`,
  `backend/tests/fixtures/normalization/remote_type_cases.json` (70 ->
  77 cases), `docs/ROADMAP.md` (bounded: recorded the freeze/evaluation
  slice's actual `M`/`Q`, this slice's candidate status and recovered/
  remaining defect counts, the GitLab-holdout-exposure caveat -- no
  broader rewrite), `docs/LLM_HANDOFF.md` (this entry plus the
  iteration rotation above).
- Verification: `ruff format --check`/`ruff check` clean (171 files);
  `mypy` clean (171 source files); focused suite (`test_normalization_
  skills.py` + `test_normalization_remote.py`) **238 passed** (was 195;
  +43 = 20 new/adjusted skill fixtures + 12 direct unit tests on the new
  helper functions + 7 new remote fixtures + 4 direct unit tests on the
  blocker); full backend suite **3171 passed** (was 3128; the local
  disposable Postgres test database was briefly down for an earlier run
  of this same suite, producing environment-only connection-refused
  errors unrelated to this slice's pure-function parser changes; brought
  back up via `docker compose up -d postgres` and the full suite reran
  clean); `check_repo.py` clean; `git diff --check` clean. Full-report
  diff of `python -m scripts.evaluate_phase3_corpus` against the
  immutable baseline report matches the frozen contract's exact
  allowlist with no other line changed: `dev` skills precision/recall
  `21/21,21/22 -> 22/22,22/22`, mismatches `124 -> 121`; `holdout`
  skills precision/recall `14/14,14/18 -> 15/15,15/18`, mismatches
  `39 -> 38`; `combined` skills precision/recall `35/35,35/40 ->
  37/37,37/40`, `remote_type` ambiguous false positives `2/2 -> 0/2`,
  mismatches `163 -> 159`; `employer:Anthropic` skills `9/9,9/10 ->
  10/10,10/10`, mismatches `60 -> 59`; `employer:Discord` ambiguous
  false positives `2/2 -> 0/2`, mismatches `64 -> 62`;
  `employer:GitLab` skills `14/14,14/18 -> 15/15,15/18`, mismatches
  `39 -> 38`. Exactly the two named `golang` recoveries
  (`anthropic:4502508008`, `gitlab:8512432002`) and the two named
  `remote_type` corrections (`discord:8214127002`, `discord:8545675002`)
  changed; every other record, including `discord:8498984002` (the real
  hybrid record used throughout as the negative control that rejected
  an earlier, unsafe draft of the remote fix) and the three disclosed
  unfixed `golang` misses, is byte-identical to the baseline.
- Adversarial self-review: 11 independent mutation proofs performed
  directly against this commit's own code (mutate -> confirm the
  targeted isolating witness fails -> restore -> confirm it passes
  again), one per safety conjunct: (1) `go`-only scope removed -- `c`/
  `r`/`node` guard fixtures fail; (2) weak cues (`programming
  language(s)`/`technology stack`/`tech stack`) accepted -- both
  colon-variant guard fixtures fail; (3) same-cue-scoped-sentence
  boundary removed (cue search widened to the whole text) -- both
  cross-sentence guard fixtures fail; (4) standalone-segment
  enforcement removed -- the imperative-verb-usage guard fixture fails;
  (5) empty/intervening-segment skip permitted -- the no-skip guard
  fixture fails; (6) boundary-touching-token-only requirement loosened
  to "anywhere in the adjacent segment" -- the boundary-vs-elsewhere
  guard fixtures fail; (7) blocker's downgrade-of-`remote` disabled --
  the location-conditional guard fixture fails; (8) blocker allowed to
  manufacture `onsite` -- both bare-blocker guard fixtures fail; (9)
  blocker allowed to downgrade an independently-resolved `hybrid` --
  that guard fixture fails; (10) blocker allowed to downgrade an
  independently-resolved `onsite` -- that guard fixture fails; (11)
  blocker bypasses negation (checked directly against unmasked tokens
  outside the candidate pipeline) -- the negated-blocker-plus-qualified-
  remote guard fixture fails. All 11 restored cleanly (238/238 passing,
  full corpus report byte-identical to the verified-correct version
  after every restoration). Contract-conformance pass: walked every
  numbered mechanical requirement in the frozen contract and confirmed
  each is enforced by one of the 11 mutation proofs above or by direct
  code inspection (ASCII-only casefold via `_ASCII_UPPER_TO_LOWER`,
  never `re.IGNORECASE`/`.lower()`, confirmed by reading every new
  function; existing anchored-region code path confirmed untouched by
  diff). Counterexample pass: constructed fresh adversarial inputs not
  drawn from the fixture corpus -- a cue-bearing sentence whose only
  candidate neighbors are non-taxonomy words (`"...Elixir, Go, Crystal,
  and Nim."`) correctly stays empty; an all-uppercase cue and candidate
  (`"PRODUCTION EXPERIENCE with Python, GO, Java."`) still correctly
  rescues, confirming the ASCII-casefold cue check is case-insensitive
  by design, not merely by fixture coincidence; a hyphenated `"Go-lang"`
  token correctly fails to match at all (pre-existing exact-match
  taxonomy lookup behavior, not a new gap). No new defect found by
  either pass.
- Deviations/known limitations: none beyond what was already disclosed
  in the approved contract (three residual `golang` misses; `salary.*`
  wiring gap deferred to Phase 4+; the `gitlab:8512432002` holdout fix
  is informational confirmation only, never independent proof of
  generalization).
- STOP -- this commit is candidate `C` for this slice (see
  `workflow-metadata` below, `state: pending`). Per the explicit
  authorization for this round, this covers implementation,
  verification, adversarial self-review, creation and push of candidate
  `C` only -- it does not authorize publication `A`, review `R`, merge
  `M`, post-merge `Q`, provider contact, database access, title
  normalization, persistence integration, or another product slice.
  Waiting for Sol's independent review of the actual diff.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-09-30-phase3-baseline-correction-go-remote-25ac578
slice_kind: parser
risk_class: H
base_sha: 25ac578f6e980eb73964de17d8f32ca1f2695867
declared_gate: final
fixture_path: backend/tests/fixtures/normalization/skill_cases.json
fixture_count: 92
```
