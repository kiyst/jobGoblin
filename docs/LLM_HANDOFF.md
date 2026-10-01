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
  allowlist -- **corrected at `C3` per Sol P2:** the original wording
  here ("no other line changed") was inaccurate; the precise rule is
  that no output line changes outside the complete approved metric/
  record allowlist plus five mechanically derived
  `false_positive_outside_frozen_set` denominator changes that this
  entry originally omitted (dev `0/21 -> 0/22`, holdout `0/14 -> 0/15`,
  combined `0/35 -> 0/37`, Anthropic `0/9 -> 0/10`, GitLab `0/14 ->
  0/15`): `dev` skills precision/recall
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
state: published
slice_id: 2026-09-30-phase3-baseline-correction-go-remote-25ac578
slice_kind: parser
risk_class: H
base_sha: 25ac578f6e980eb73964de17d8f32ca1f2695867
declared_gate: final
executed_gate: final
candidate_sha: 467ec75273c3bee00e939c720cba072b2b7754d1
receipt_id: 24a31360-502b-4c35-8be3-a35374679077
receipt_path: docs/verification-receipts/467ec75273c3bee00e939c720cba072b2b7754d1/24a31360-502b-4c35-8be3-a35374679077.json
fixture_path: backend/tests/fixtures/normalization/skill_cases.json
fixture_count: 92
```

### C2 correction (ownership-mapping gap)

- Original candidate `C = 70e0e9258006bbd7da77317fe06b41d0281e70b9` (above)
  is preserved **unamended** -- not rebased, not force-pushed. Running
  the receipt-eligible Workflow v3.2 coordinator against `C` with
  `--gate final` failed before any test executed, with:
  `scripts.verification_scope.OwnerMappingRequiredError:
  'backend/tests/fixtures/normalization/remote_type_cases.json' is a
  non-Python path under backend/tests/ with no declared exact rule --
  owner mapping required before verification can proceed`. Diagnosis:
  `backend/tests/fixtures/normalization/skill_cases.json` has long been
  registered in `scripts/verification_scope.py`'s `_SKILL_FIXTURE_FILES`,
  but the sibling `remote_type_cases.json` fixture (which already existed
  at 70 cases before this slice) was never registered anywhere -- a
  pre-existing ownership-mapping gap this slice's own diff was the first
  to expose by actually changing that file through the receipt-eligible
  path, not a defect this slice introduced.
- `C2 = this commit` adds exactly one narrowly bounded correction, in
  exactly three files (`backend/scripts/verification_scope.py`,
  `backend/tests/test_verification_scope.py`, this entry in
  `docs/LLM_HANDOFF.md`): a new, dedicated `_REMOTE_FIXTURE_FILES` exact-
  path table (never folded into `_SKILL_FIXTURE_FILES`), mapping
  `backend/tests/fixtures/normalization/remote_type_cases.json` to the
  distinct category `test-fixture:remote-classifier`, integrated into
  both existing exact-map iteration sites
  (`_validate_configuration`'s duplicate-detection list and
  `classify_path`'s own exact-map tuple) -- the identical pattern already
  used for `_SKILL_FIXTURE_FILES`/`_TAXONOMY_FIXTURE_FILES`/
  `_EVALUATION_FIXTURE_FILES`. No wildcard or directory-wide fallback; an
  unrelated unmapped non-Python path under the same `normalization/`
  fixtures directory still fails closed with `OwnerMappingRequiredError`
  (directly tested). The new category follows the existing `test-
  fixture:*` naming convention, so it automatically falls outside
  `required_contract_families`'s `parser`/`adapter`/`contract-record`
  kinds (no location/salary/experience coverage requirement) and is
  never flagged `directly_execute` (never a literal pytest `--focus`
  target) -- both confirmed by dedicated tests, with no change to either
  function's own logic. **No parser semantics, fixture content, or
  evaluator behavior changed by this correction** -- `skills.py`/
  `remote.py`/both fixture JSON files/the frozen corpus are byte-
  identical to `C`.
- Verification: `ruff format --check`/`ruff check` clean (171 files);
  `mypy` clean (171 source files); focused `test_verification_scope.py`
  **79 passed** (was 72); combined focused (`test_normalization_skills.py`
  + `test_normalization_remote.py` + `test_verification_scope.py`)
  **317 passed**; full backend suite **3178 passed**
  (was 3171 at `C`; +7 new verification-scope tests); `check_repo.py`
  clean; `git diff --check` clean. Realistic-corpus evaluator output
  reconfirmed byte-identical to `C`'s own approved output.
- Adversarial self-review: direct fault injection
  (`test_remote_fixture_mapping_is_load_bearing`, mirroring the existing
  `test_duplicate_exact_rule_is_rejected_at_configuration_time` pattern)
  temporarily clears `_REMOTE_FIXTURE_FILES`, confirms
  `classify_path` raises `OwnerMappingRequiredError` on the exact
  previously-failing path, restores the table, and confirms
  classification passes again -- proving the new mapping, not some
  other fallback, is what fixes the original failure.
- STOP -- `C2` is the corrected candidate for this slice. Waiting for the
  receipt-eligible coordinator to be rerun against `C2` and, only if it
  passes, for publication `A2` (separately authorized). No `R`, merge,
  `M`, `Q`, broader verification-tooling change, parser change, fixture-
  content change, provider contact, database access, or title
  normalization is authorized here.

---

## Iteration 2

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
