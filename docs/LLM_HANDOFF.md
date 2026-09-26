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

- Date/agent: 2026-09-26, Claude Code (Sonnet 5). Risk class **H** (same
  slice, same authorization). Base `B` (unchanged for this slice's whole
  correction lifetime, `7ce4a1d`) -> candidate `C6`: this commit; same
  branch `phase-3/realistic-evaluation-corpus`, on top of the existing
  pushed tip `A5 = 58de6976d72a370a871882f069bf74abcc1e1a1c`. `slice_id:
  2026-09-20-realistic-evaluation-corpus-7ce4a1d` (unchanged). One
  bounded correction round for Sol's three findings on `C5 =
  e5a72f6926b826ca9af8cdb93e5368d1fb8ddae8` / `A5 =
  58de6976d72a370a871882f069bf74abcc1e1a1c`, both of which remain
  unamended, still pushed, still present in history exactly as they
  were; the `C5`/`A5` receipt cycle
  (`59ee72fa-ca86-4596-bf9c-a8e971cf9ed2`) is superseded and
  non-reusable as of this entry. No proposal rewrite, no new semantics,
  no network contact, board-token request, corpus acquisition, staged/
  review-artifact change, parser/taxonomy change, evaluation-label
  change, database work, or workflow-tooling change.
- **Finding 1 (uppercase angle-entity bypass)**: `_ESCAPED_ANGLE_
  REFERENCE_RE` and `_UNTERMINATED_NAMED_ANGLE_RE` only recognized
  lowercase `lt`/`gt`, but `html.unescape()` also decodes the all-
  uppercase aliases `&LT;`/`&GT;` (and their semicolonless legacy forms)
  to `<`/`>` -- confirmed empirically -- so a double-encoded document
  using the uppercase spelling could bypass both the mixed-content and
  residual-nested-encoding checks entirely. Fixed by adding `|LT|GT` to
  both regex alternations, exactly as specified; the mixed-case `&Lt;`/
  `&Gt;` (real, distinct, unrelated named entities, U+226A/U+226B) are
  confirmed to still not match either regex. Nine new regressions cover
  uppercase acceptance, uppercase mixed-content rejection, uppercase
  semicolonless-form rejection (both a followed-by-more-text and a bare
  form), uppercase nested-encoding rejection, and non-classification of
  the mixed-case entities -- full parity with the existing lowercase
  coverage.
- **Finding 2 (unknown `content_mode` bypass)**:
  `BoardAcquisitionSpec.__post_init__`'s `if content_mode ==
  "declared-double-escaped": ... elif mode_basis_ref is not None: raise
  ...` let an unrecognized `content_mode` string with `mode_basis_ref=
  None` fall through both branches and construct successfully with no
  validation at all; with a non-`None` `mode_basis_ref` it raised the
  wrong, misleading message ("must be None when content_mode is
  'standard'") even though the mode wasn't `"standard"`. Fixed by adding
  an explicit `content_mode not in _VALID_CONTENT_MODES` check as the
  first statement in `__post_init__`, before the mode/basis logic --
  independent of the CLI parser and of static type hints. Two new
  regressions cover both invalid combinations.
- **Finding 3 (three required caller-level proofs, previously
  missing)**: (1) a synthetic outer-encoded description whose email and
  phone are built from numeric character references (`&#64;` for '@',
  `&#53;` for the phone's leading digit) at the original single-encoded
  source, then escaped one further layer -- neither the raw `content`
  field nor the single permitted `html.unescape()` output ever contains
  a literal '@' or '555' (confirmed empirically); both only become
  literal via `HTMLParser(convert_charrefs=True)`'s own entity decoding
  during HTML-to-text extraction, a third, separate decoding mechanism.
  Both are correctly redacted in the final description. (2) A spy
  around `_redact_contact_patterns` proving description redaction is
  called exactly once, with the final converted text -- the payload has
  no `title`/`location` keys, so neither triggers its own independent
  call that could confound the count. (3) A genuine `_fetch_board` test
  (via `httpx.MockTransport`) under `declared-double-escaped` mode with
  two selected detail records: the first mixes literal and escaped
  markup and is correctly rejected/skipped without aborting the board;
  the second is genuinely once-escaped valid content and is fetched,
  converted, and returned.
- **Adversarial self-review**: a dedicated pass traced the uppercase
  regex fix character-by-character against `html.unescape()`'s actual
  behavior (no `re.IGNORECASE` flag present; the fix is precisely
  scoped, no over- or under-matching), confirmed the `__post_init__`
  ordering guarantee and that `_parse_board_arg`'s own mode check is
  legitimate defense-in-depth rather than dead code, and independently
  re-derived all three Finding-3 test claims rather than trusting their
  docstrings. One gap found and closed before this commit: the new
  uppercase-form tests had no equivalent of the existing lowercase
  `residual-nested-encoding`/bare-semicolonless-form tests; added
  `test_declared_mode_rejects_uppercase_nested_named_encoding` and
  `test_declared_mode_rejects_bare_uppercase_semicolonless_form` for
  full parity.
- **Mutation-proved**: temporarily reverted the Finding-1 regex change
  (dropped `|LT|GT` from both constants) and reran the html-convert
  suite -- exactly the 3 uppercase-rejection tests failed (the
  uppercase-success test does not require the fix, since decoding
  itself is unaffected -- only the *validation* regexes changed), all
  other tests unaffected; restored and confirmed all pass again.
  Temporarily reverted the Finding-2 `__post_init__` ordering fix and
  reran the fetcher suite -- exactly the 2 new
  `test_board_acquisition_spec_rejects_unknown_mode_*` tests failed
  (one with a silent non-raise, one with the old misleading message,
  matching the exact defect described above), all other tests
  unaffected; restored and confirmed all pass again.
- Files changed: `backend/scripts/greenhouse_html_convert.py` (regex
  fix), `backend/scripts/fetch_greenhouse_evaluation_postings.py`
  (`__post_init__` ordering fix), `backend/tests/
  test_greenhouse_html_convert.py` (49 -> 58 tests),
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py` (81 ->
  86 tests), `docs/LLM_HANDOFF.md` (this entry, plus the iteration
  rotation above). `docs/DECISIONS/0010-realistic-evaluation-corpus-
  methodology.md` not touched this round -- no design/semantic change,
  only bug fixes and test completeness within the already-documented
  contract.
- Verification: pending — see the workflow-metadata block below and the
  publication (`A6`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
executed_gate: final
candidate_sha: 4771c2df38a7c913a852fa5cfe24dc795c5d587f
receipt_id: 69759bd7-d539-4417-8685-730900e4db20
receipt_path: docs/verification-receipts/4771c2df38a7c913a852fa5cfe24dc795c5d587f/69759bd7-d539-4417-8685-730900e4db20.json
full_suite_count: 3062
focused_test_count: 276
mutation_witness_count: 34
```

### Work review

- Sol's review of `C6` = `4771c2df38a7c913a852fa5cfe24dc795c5d587f` and
  `A6` = `6cbda7135ae21e6fe818313f0dfaf9fa0097b247`: **Approved, no
  executable findings.** Independently verified: `C6`'s sole parent is
  `A5` (`58de6976d72a370a871882f069bf74abcc1e1a1c`) and `A6`'s sole
  parent is `C6`, confirming a clean, unamended, single-parent chain;
  the correction remained within the bounded scope named for this
  round (`backend/scripts/greenhouse_html_convert.py`,
  `backend/scripts/fetch_greenhouse_evaluation_postings.py`,
  `backend/tests/test_greenhouse_html_convert.py`,
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py`,
  `docs/LLM_HANDOFF.md` -- no proposal rewrite, no new semantics); the
  uppercase `LT`/`GT` entity handling closes the fail-closed bypass
  while the mixed-case `Lt`/`Gt` (real, distinct, unrelated named
  entities) correctly remain unclassified by either shared regex;
  `BoardAcquisitionSpec.__post_init__` now rejects an unrecognized
  `content_mode` before any mode/basis relationship validation runs;
  the encoded-PII decode/HTML-to-text-ordering test, the exactly-once
  redaction spy, and the genuine `_fetch_board` mixed-encoding
  failure-isolation test are substantive, not merely docstring claims.
  Ran the two directly affected test modules --
  `backend/tests/test_greenhouse_html_convert.py` and
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py` --
  **144/144 passed**. Confirmed the working tree is clean and
  `main`/`origin/main` remain unchanged at
  `7ce4a1dc770827653ccf8140188c5d1dec6621d8`. Sol did **not**
  independently repeat the full 3,062-test suite or all 34 mutation
  witnesses; those remain supported by `A6`'s own genuine
  receipt-eligible verification, not re-derived here.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-26T00:00:00Z
candidate_sha: 4771c2df38a7c913a852fa5cfe24dc795c5d587f
publication_commit_sha: 6cbda7135ae21e6fe818313f0dfaf9fa0097b247
receipt_path: docs/verification-receipts/4771c2df38a7c913a852fa5cfe24dc795c5d587f/69759bd7-d539-4417-8685-730900e4db20.json
receipt_id: 69759bd7-d539-4417-8685-730900e4db20
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-27. Merged `phase-3/realistic-evaluation-corpus` at
  approved, reviewed commit `ccfda9055cefbc4088f75e2659f54c9be703cc3c`
  (`R`; Sol's "Approved, no executable findings" verdict on `C6`/`A6`,
  above) into `main` via `git merge --no-ff`. Merge commit:
  `41963baf4797b1b2b6fee1f72311dd6b84d7b6a3`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `7ce4a1dc770827653ccf8140188c5d1dec6621d8`.
- Pre-merge checks: freshly fetched `origin`; confirmed the feature
  branch and its origin both sat at `ccfda90`, and `main`/`origin/main`
  were both clean and synchronized at `7ce4a1d` before merging;
  re-confirmed `validate_c_a_r_chain(C6, A6, R)` and
  `check_merge_eligibility(C6, A6, R)` both still returned `approved`
  immediately beforehand, with no unexpected advancement or divergence
  on either ref.
- Followed the documented `M -> Q` release sequence: `M` was created
  locally, not pushed; zero content difference between `M` and `R`
  confirmed (`git diff --quiet ccfda90 HEAD`);
  `verification_coordinator.run_post_merge_verification` was run
  against `M` in a disposable detached worktree (always full/final) --
  artifact `e04e1475-ef8e-4c91-9e89-84f70b9c28fb`, all 11 steps PASS,
  full pytest suite **3062 passed**, all 34 mutation witnesses pass,
  no migration triggered, cleanup PASS. `Q` was authored as `M`'s direct
  mainline child, bundling that artifact with this append-only merge
  record in one commit -- this entry itself.
- Post-merge evidence status: `docs/post-merge/
  41963baf4797b1b2b6fee1f72311dd6b84d7b6a3/
  e04e1475-ef8e-4c91-9e89-84f70b9c28fb.json`, referencing original
  receipt `69759bd7-d539-4417-8685-730900e4db20` (`docs/
  verification-receipts/4771c2df38a7c913a852fa5cfe24dc795c5d587f/
  69759bd7-d539-4417-8685-730900e4db20.json`). `check_review.
  validate_published(C6, A6, R, M, Q)` and `verification_coordinator.
  confirm_main_unchanged` are run immediately before push; see the
  agent's final report for their results rather than restating them
  here ahead of time.
- STOP -- report the synchronized final `main` SHA and stop. No
  realistic-corpus freezing, evaluation, provider contact, title-
  normalization work, or another slice without separate explicit user
  authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-27, Claude Code (Sonnet 5). New slice, Sol-approved
  freeze/evaluation contract (three negotiation rounds). Risk class **H**,
  `slice_kind: tooling`, `declared_gate: final`. Base `main`@
  `0dae4683645599369d41d0228b0edad1cfad73ce` (confirmed clean,
  `main == origin/main` before starting). `slice_id:
  2026-09-27-realistic-corpus-freeze-evaluation-0dae468`. New branch
  `phase-3/realistic-corpus-freeze-evaluation`. **This is Stage 1 of 8 in
  the approved staged execution sequence only** -- rubric, common-packet
  tooling, and the freeze/evaluator scaffolding. No annotation pass, no
  adjudication, no corpus freeze, no baseline evaluation, no provider
  contact, no database work, and no parser-semantic change performed or
  authorized by this commit. This is a checkpoint within an incomplete
  slice, not a candidate `C` -- no receipt-eligible verification run, no
  `A`/`R`/`M`/`Q` authorized yet.
- **Frozen rubric**: `docs/evaluation/phase3-realistic-annotation-
  rubric.md`, `rubric_version: 1.0.0`. Defines all four outcomes
  (`present_supported`/`present_unsupported_form`/`absent`/`ambiguous`),
  the bidirectional value/provenance rule (mirroring
  `evaluate_phase3_corpus.py`'s own `_validate_scored_label`), the closed
  per-parser/component value vocabulary, the two provenance tags this
  corpus may actually use (`parsed_description`/`inferred`), missing-
  information/ambiguity/unsupported-form handling, the skill-label rule,
  and an explicit "procedural, not cryptographic" blindness statement.
- **`backend/scripts/freeze_phase3_realistic_corpus.py`** (new) +
  **`backend/tests/test_freeze_phase3_realistic_corpus.py`** (new, 31
  tests, entirely synthetic fixtures -- no real posting text). Implements:
  `compute_source_packet_hash` (the binding canonical manifest -- salvage/
  taxonomy/rubric paths and sha256 plus `rubric_version`, canonical-JSON
  serialized, sha256 hashed); `load_annotation_pass` (closed 6-key top-
  level schema, closed per-label schema -- 3-key scalar/composite, 1-key
  skill -- exhaustive 3+10+taxonomy-size label count, role/rubric-version/
  recomputed-hash cross-check); `load_adjudication_audit` (validates every
  genuine pass disagreement has a complete adjudication, every required
  agreement audit per the deterministic rule -- every `present_supported`
  agreement, plus the lexicographically-smallest record id per non-
  `present_supported` (label, outcome, employer) stratum -- is present,
  and an `overturned` entry both has a matching disagreement and actually
  changes the previously agreed label); `deterministic_split` (employers
  sorted ascending, lexicographically last is `holdout`); `build_corpus`
  (verifies the salvage sha256 and retained-only candidates, merges both
  validated passes plus adjudication evidence into
  `evaluate_phase3_corpus.py`'s own committed schema -- agreements tagged
  `annotator_role: "claude+sol:agreed"`, adjudicated disagreements tagged
  `"adjudicated:user"` with a `second_annotation` chosen to be whichever
  raw pass differs from the final value, keeping the existing corpus
  validator's "a disagreement must reflect an actual difference"
  invariant satisfiable even when the final answer exactly matches one
  raw pass -- copies `fields` unmodified, atomically create-only writes,
  and self-checks the result by calling the real
  `evaluate_phase3_corpus.load_corpus`, never a shadow reimplementation,
  before the write is made durable). A CLI `manifest` subcommand prints
  the canonical packet/hash for handing to each fresh annotator task; a
  `build` subcommand is implemented and tested but not invoked against
  real data this stage.
- **`backend/scripts/evaluate_phase3_corpus.py`** extended (bounded, no
  parser-semantic or existing-metric change): `evaluate_corpus` now also
  returns one `"employer:<name>"` key per distinct employer across the
  whole corpus; `render_report` prints those sections (sorted after dev/
  holdout/combined) and, given the loaded records, an explicit note that
  per-`template_family` subdivision is intentionally omitted since every
  record's `template_family` is `"unknown"` (never silently duplicating
  the combined result under a fake breakdown). `backend/tests/
  test_evaluate_phase3_corpus.py`: 62 -> 66 tests (4 new: per-employer
  keys reflect the matching split subset, sorted employer ordering, the
  template note appears/is absent correctly).
- Verification: `ruff format --check`/`ruff check` clean on all four
  touched/added files; `mypy` clean on both scripts; full backend suite
  **3097 passed** (was 3062; +35 = 31 new freeze-builder tests + 4 new
  evaluator tests); `check_repo.py` clean; `git diff --check` clean.
- Adversarial self-review: traced the `second_annotation` "whichever raw
  pass differs from final" rule against all three cases (final matches
  neither raw, final matches Claude's raw, final matches Sol's raw) to
  confirm the existing corpus validator's "no actual difference" check
  can never spuriously fire; confirmed an `overturned` audit entry whose
  adjudication resolves back to the original agreed value is rejected
  (a genuine overturn must change the label); confirmed extra (non-
  required) agreement audits are accepted, not just the minimum; confirmed
  the deterministic split raises on fewer than two employers rather than
  silently picking an arbitrary holdout.
- Known limitation: `_validate_raw_label` checks the bidirectional
  outcome/value rule and restricts `present_supported` provenance to
  `parsed_description`/`inferred`, but does not re-validate each parser's
  exact value vocabulary (e.g. `remote_type in {"remote","hybrid",
  "onsite"}`) -- that is deferred to `build_corpus`'s own authoritative
  `load_corpus` self-check on the merged output, deliberately avoiding a
  second, independently-drifting copy of `evaluate_phase3_corpus.py`'s
  `_EXPECTED_VALUE_VALIDATORS`.
- Files changed: `docs/evaluation/phase3-realistic-annotation-rubric.md`
  (new), `backend/scripts/freeze_phase3_realistic_corpus.py` (new),
  `backend/tests/test_freeze_phase3_realistic_corpus.py` (new),
  `backend/scripts/evaluate_phase3_corpus.py` (extended),
  `backend/tests/test_evaluate_phase3_corpus.py` (extended),
  `docs/LLM_HANDOFF.md` (this entry, plus the iteration rotation above).
- STOP -- this is a checkpoint within an incomplete slice, not a
  candidate. No annotation pass, adjudication, corpus freeze, baseline
  evaluation, provider contact, database work, parser change, title
  normalization, `R`, merge, `M`, or `Q` is authorized by this commit.
  Waiting for Sol's pre-annotation review of the rubric and tooling.
