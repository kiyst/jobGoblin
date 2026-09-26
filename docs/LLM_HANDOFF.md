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

- Date/agent: 2026-09-24, Claude Code (Sonnet 5). Risk class **H** (same
  slice, same authorization). Base `B` (unchanged for this slice's whole
  correction lifetime, `7ce4a1d`) -> candidate `C5`: this commit; same
  branch `phase-3/realistic-evaluation-corpus`, on top of the existing
  pushed tip `A4 = 549229bde2c59f6453b69c852c9ce5175b6a2f52`. `slice_id:
  2026-09-20-realistic-evaluation-corpus-7ce4a1d` (unchanged). Implements
  Sol's frozen, twice-revised sanitizer-correction design proposal
  (addressing the real double-HTML-encoding defect discovered during the
  authorized acquisition against `gitlab`/`anthropic`/`discord`, and the
  30-candidate manually-reviewed salvage batch produced from it, both
  preserved unchanged by this slice). No network contact, board-token
  request, corpus acquisition, staged/review-artifact change, parser-
  semantic change, database work, or unrelated tooling performed.
- **Explicit input-mode contract**: `convert_html_to_text(html, *,
  mode="standard")` gained a second mode, `"declared-double-escaped"`,
  selected only by an explicit caller argument -- never inferred from
  content. `"standard"` (the default) is byte-for-behavior identical to
  the function's behavior before this change, with zero new checks at
  any stage. `"declared-double-escaped"` permits exactly one additional
  `html.unescape()` pass, bracketed by two fail-closed validation
  stages sharing one pair of fixed regex constants
  (`_ESCAPED_ANGLE_REFERENCE_RE` for fully-terminated named/decimal/hex
  escaped angle-bracket forms; `_UNTERMINATED_NAMED_ANGLE_RE` for a
  semicolonless `&lt`/`&gt` prefix, rejected regardless of what follows
  it, since its interaction with `html.unescape()`'s own legacy
  longer-entity matching -- e.g. the real, unrelated `&ltimes;` -- is not
  trusted to be safe): raw-input validation
  (`"mixed-literal-and-escaped-markup"` if a literal angle bracket and an
  escaped form coexist; `"unsupported-angle-reference"` for any bare
  semicolonless form) and post-decode validation
  (`"unsupported-angle-reference"` or `"residual-nested-encoding"`). A
  new `HtmlDoubleEncodingError(HtmlConversionError)` carries only a fixed
  category string, never content. A documented accepted limitation: a
  legitimate escaped-code example that survives exactly one correct
  decode is indistinguishable from a genuine unresolved second layer, so
  `"declared-double-escaped"` mode conservatively rejects it too --
  proved by a direct regression, never "fixed" by making the check
  smarter (that would violate the bounded design).
- **Explicit board specification and CLI grammar**: `BoardAcquisitionSpec`
  (`board_token`, `employer`, closed `content_mode`, `mode_basis_ref`)
  replaces the prior bare `(board_token, employer)` tuple everywhere
  (`run_acquisition`, `_fetch_board`, `_sanitize_job_detail`,
  `SanitizedCandidate`). `mode_basis_ref` is required (non-`None`) iff
  `content_mode == "declared-double-escaped"`, matching a closed grammar
  (`^(prior-capture|probe):[A-Za-z0-9_-]{1,100}$`) that resolves the
  authorization circularity: it must cite either a stable reference to
  evidence already retained from an earlier, separately authorized
  capture, or a separately authorized, distinct probe -- never the
  run's own unapproved contact. No permanent board-token-to-mode
  inference table exists anywhere. CLI grammar:
  `token:Employer:standard` (3 parts) or
  `token:Employer:declared-double-escaped:basis-kind:basis-id` (5
  parts); `_parse_board_arg` reuses the existing `validate_board_token`
  (translating its `ValueError` to `argparse.ArgumentTypeError`) and
  rejects every malformed input during argument parsing, strictly before
  `run_acquisition` is reachable. `mode_basis_ref`/`content_mode` are
  appended as fixed-format text onto the existing free-text
  `sanitization_lineage` provenance field -- no new structured schema
  field, so `evaluate_phase3_corpus.py`'s provenance validator needed no
  change, staying within this correction's frozen file scope.
- **Redaction ownership unchanged**: `_redact_contact_patterns` remains
  entirely in `fetch_greenhouse_evaluation_postings.py`, called exactly
  once per description, strictly after the full conversion (all decode
  stages) completes.
- **Adversarial self-review findings, fixed before this commit**: (1) a
  test claiming to prove "`_parse_board_arg` never contacts the
  network" asserted only that the function is not a coroutine -- a
  synchronous function can still perform blocking I/O, so the assertion
  proved nothing; removed rather than papered over (the actual
  guarantee -- every malformed input raises during argument parsing,
  strictly before `run_acquisition` is ever reachable in `main()` --
  is already established by the other `_parse_board_arg` rejection
  tests together with `main()`'s own control flow). (2)
  `BoardAcquisitionSpec`'s docstring claimed its mode/basis invariant as
  a hard contract, but nothing enforced it at construction -- only
  `_parse_board_arg` checked it, so any non-CLI caller building a spec
  directly could silently construct an inconsistent, unauthorized
  combination. Fixed: added `__post_init__` validation to the dataclass
  itself, with new regressions proving both valid combinations succeed
  and both invalid combinations raise `ValueError` at construction,
  independent of the CLI.
- Files changed (exactly the six named in the frozen proposal's scope,
  no others): `backend/scripts/greenhouse_html_convert.py`,
  `backend/scripts/fetch_greenhouse_evaluation_postings.py`,
  `backend/tests/test_greenhouse_html_convert.py` (26 -> 49 tests),
  `backend/tests/test_fetch_greenhouse_evaluation_postings.py` (60 ->
  81 tests), `docs/DECISIONS/0010-realistic-evaluation-corpus-
  methodology.md` (states the corrected contract and the salvage
  batch's honest lineage), `docs/LLM_HANDOFF.md` (this entry, plus the
  iteration rotation above).
- Verification: pending — see the workflow-metadata block below and the
  publication (`A5`) entry that will follow it.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
executed_gate: final
candidate_sha: e5a72f6926b826ca9af8cdb93e5368d1fb8ddae8
receipt_id: 59ee72fa-ca86-4596-bf9c-a8e971cf9ed2
receipt_path: docs/verification-receipts/e5a72f6926b826ca9af8cdb93e5368d1fb8ddae8/59ee72fa-ca86-4596-bf9c-a8e971cf9ed2.json
full_suite_count: 3048
focused_test_count: 262
mutation_witness_count: 34
```

---

## Iteration 2

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
state: pending
slice_id: 2026-09-20-realistic-evaluation-corpus-7ce4a1d
slice_kind: tooling
risk_class: H
base_sha: 7ce4a1dc770827653ccf8140188c5d1dec6621d8
declared_gate: final
```
