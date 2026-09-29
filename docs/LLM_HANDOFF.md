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

- Date/agent: 2026-09-27, Claude Code (Sonnet 5). Same slice, same
  authorization (`slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-
  0dae468`, risk class **H**, `slice_kind: tooling`, `declared_gate: final`).
  Same branch `phase-3/realistic-corpus-freeze-evaluation`, on top of the
  existing pushed checkpoint `80b4672`, preserved unamended. One bounded
  correction round for Sol's final Stage 1 re-review verdict on that
  checkpoint (two findings, F14/F15). Every unaffected F11-F13 rule
  (canonical location forms, the multi-requirement decision table, the
  gap-metric rename/applicability sentinel, `_is_meaningfully_present`'s
  whitespace handling) is preserved unchanged. No annotation pass,
  adjudication, corpus freeze, baseline evaluation, provider contact,
  database work, or parser-semantic change performed. Ending commit: this
  commit.
- **F14 (contradictory non-US `location.state` instructions)**: the
  canonical-domain table already correctly classified a non-US state/
  province/region as `present_unsupported_form`, but the location-
  normalization table's US-state bullet contradicted it, saying to
  annotate such a value "in its own natural written form" -- a value the
  loader's closed USPS-code validator would reject outright. Corrected
  that bullet to state explicitly: `outcome = "present_unsupported_form"`,
  `expected_value = null`, `expected_provenance = "unavailable"`, and
  that the region's natural form must never be written into
  `expected_value`. Added a fabricated synthetic example to the location
  situation/rule table (`location_raw` = "Toronto, Ontario, Canada" ->
  `location.state` is `present_unsupported_form`/null/unavailable, while
  `location.country` = `"Canada"` `present_supported` is unaffected, since
  country's domain is open free text). Also corrected the adjacent
  postal-code wording, which described ZIP+4 as "digits only" -- a ZIP+4
  is exactly five ASCII digits, one hyphen, and four ASCII digits, and the
  hyphen is a required literal part of the form, not a digit; ZIP5 remains
  exactly five ASCII digits.
- **F15 (format-character-only wired inputs silently counted as
  present)**: `_is_meaningfully_present` previously used a bare
  `value.strip() != ""` check, which does not strip Unicode format
  characters (category `Cf`, e.g. U+200B zero-width space, U+FEFF BOM,
  U+180E Mongolian vowel separator) -- confirmed directly that
  `classify_salary`/`classify_location` return entirely unavailable
  results for all three, individually and mixed with ordinary whitespace,
  yet the old check reported them as "present." Replaced it with the
  project's own established meaningful-text rule, mirrored from
  `fetch_greenhouse_evaluation_postings.py`'s `_has_meaningful_text`: a
  value is meaningfully present only if it contains at least one
  character that is neither Unicode whitespace (`str.isspace()`) nor
  category `Cf`. Added `import unicodedata`. Seven new regressions: U+200B-
  only, U+FEFF-only, U+180E-only, and ordinary whitespace mixed with only
  those three (all four parametrized as "rejected"); a positive control
  mixing `Cf` characters with genuine visible content (accepted); and one
  end-to-end test through the real `evaluate_corpus`/`classify_salary`
  pipeline confirming a U+200B-only `compensation_text` routes a
  `present_supported` salary annotation to `missing_wired_input_gap`,
  never `supported_abstention`.
- Because the annotation contract changed a fourth time before any
  annotation exists, `RUBRIC_VERSION` bumped `1.0.3 -> 1.0.4`. **Historical,
  superseded evidence** (none ever annotated against), all four now
  recorded in the rubric's own superseded-evidence table: `1.0.0` (commit
  `7644e20`), `1.0.1` (commit `64dd730`), `1.0.2` (commit `d2097b4`), and
  `1.0.3` (rubric sha256
  `3948ec6a09c188a95b9a2ee1fb9ecd94edda2ab5c48bb39e32826e36f51f7f87`,
  `source_packet_hash b56b0f65529fc83a8f30c8958ba697544a321a003b323220b92a
  7c1ac8c6dd1b`, commit `80b4672`). **Current**: rubric sha256
  `70961ec18fcbd5a316bb6ae49b4c9edc0cc1b3957aa6f5cd1f59c1684057eeb9`,
  `source_packet_hash 010a13e0b5040121d4f55df62a0dc3780033469c316380cc1e4
  15c5a86641f92` (taxonomy/salvage hashes unchanged).
- Verification: `ruff format --check`/`ruff check` clean on all four
  touched files; `mypy` clean on both scripts; full backend suite **3128
  passed** (was 3121; +7 = the F15 regressions above); `check_repo.py`
  clean; `git diff --check` clean; focused
  `test_evaluate_phase3_corpus.py` (83 tests) and
  `test_freeze_phase3_realistic_corpus.py` (43 tests, unchanged -- no
  freeze-builder logic touched this round beyond the `RUBRIC_VERSION`
  constant it imports indirectly via the rubric path) both green.
- Adversarial self-review: independently reproduced Sol's exact claim
  before fixing anything -- ran `classify_salary` directly against
  U+200B/U+FEFF/U+180E and a mixed string, confirmed all four return
  entirely unavailable results, and confirmed `unicodedata.category()`
  reports `Cf` for all three code points in this environment's Unicode
  database before trusting the fix's premise; confirmed the new
  `_is_meaningfully_present` body is character-for-character identical in
  logic to `fetch_greenhouse_evaluation_postings.py`'s own
  `_has_meaningful_text`, not a lookalike reimplementation; confirmed the
  new fabricated location example's `country` sub-field is genuinely
  unaffected by the `state` fix (open free-text domain, no validator
  change) rather than assuming it without checking; confirmed no
  existing test asserted the old (incorrect) "natural written form"
  behavior anywhere, so no other test needed updating for F14.
- Files changed: `docs/evaluation/phase3-realistic-annotation-rubric.md`
  (F14 corrections + synthetic example, `rubric_version` bump),
  `backend/scripts/evaluate_phase3_corpus.py` (F15 fix, `unicodedata`
  import, docstring), `backend/tests/test_evaluate_phase3_corpus.py`
  (76 -> 83 tests), `backend/scripts/freeze_phase3_realistic_corpus.py`
  (`RUBRIC_VERSION` bump only), `docs/LLM_HANDOFF.md` (this entry, plus
  the iteration rotation above).
- STOP -- this remained a checkpoint within an incomplete slice, not a
  candidate, when written. Sol's final Stage 1 re-review subsequently
  approved this checkpoint with no further findings (reported by the
  user); Stage 1 concluded and annotation began. See Iteration 2 for the
  completed annotation, adjudication, corpus freeze, and baseline
  evaluation, and this slice's first candidate/publication record.

---

## Iteration 2

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
state: pending
slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-0dae468
slice_kind: tooling
risk_class: H
base_sha: 0dae4683645599369d41d0228b0edad1cfad73ce
declared_gate: final
```
