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

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/remote-classifier` for the two remaining findings from
  the prior iteration's `Work review` (that prior iteration's own Work
  done and review are now rotated out of this ledger per the
  two-iteration rule; both remain in Git history at commit `c8a1217` and
  its review commit). Base: commit `c8a1217` plus the uncommitted review.
  Preserved: the accepted description positive catalog and context
  protections, coordinated/unresolved negation, the fail-closed import
  allow-list, `NormalizationResult`/`Provenance`, the public signature,
  and the pure/offline scope. No ingestion/persistence/providers/models/
  migration or other parser touched. **Note on this ledger's own
  structure**: the prior iteration's `Work review` was found misplaced on
  disk — inserted ahead of the now-superseded original review under the
  wrong heading, with its matching `Work done` appearing only afterward.
  Its content was reproduced byte-for-byte, unchanged; only its position
  was moved so it sits paired with the `Work done` it actually reviews,
  per this file's own stated purpose. Flagged rather than silently
  leaving the ledger self-contradictory.
- Outcome, addressing each finding exactly:
  1. **Title false positives from bare subject/domain modifiers.**
     Replaced `title`'s "bare marker matches anywhere" rule with a
     conservative structural rule (`_extract_title_signal`): a bare marker
     counts only when it is (a) the complete title, (b) parenthesized or
     bracketed, or (c) its own delimiter-separated segment (split on
     comma/pipe/colon, or a hyphen/en-dash/em-dash surrounded by
     whitespace — never one glued inside a word like "on-site").
     Separately, explicit multi-word phrases (`"fully remote"`, `"100%
     remote"`, `"work remotely"`, `"work from home"`, `"work from
     anywhere"`, `"wfh"`, `"work in the office"`) count anywhere in the
     title, since they are inherently unambiguous. A leading `Remote`/
     `Hybrid` directly modifying an occupational/domain noun now fails
     every case and returns `unavailable`. Title negation support was not
     reintroduced — the structural rule needed it for nothing in this
     catalog's scope, and adding it back would reopen the exact
     "matches anywhere" risk this closes.
  2. **`_is_comma_contrast` couldn't distinguish a comma from other
     separators.** The tokenizer (`_tokenize`) previously discarded the
     *identity* of whatever sat between two tokens — a comma, a hyphen, a
     slash, an em-dash, and plain whitespace all produced the same "zero
     tokens in between" gap. Added `_tokenize_with_spans`, which returns
     each token's character offsets alongside its text; `_is_comma_
     contrast` now looks at the **raw substring** between two candidates'
     original character spans and requires it to match
     `_EXACT_COMMA_GAP_RE` (`\A\s*,\s*\Z`) — exactly one comma, optionally
     surrounded by whitespace, and nothing else.
  3. **Removed the false "accepted limitation" claim.** The module
     docstring's "title still uses an enumerated exclusion list" section
     is deleted entirely and replaced with a full description of the
     actual structural-marker contract.
- New fixture cases (corpus now 67 total, +8 net): the three reproduced
  ambiguous titles as unavailable regressions, one positive exact-comma
  control, and four separator-rejection regressions (whitespace, hyphen,
  slash, em-dash). `conflicting_title_vs_description`'s title reworded
  from the ambiguous `"Remote Customer Support Specialist"` to the
  explicit structural marker `"Customer Support Specialist (Remote)"`,
  per the review's own instruction.
- Files changed: `backend/app/normalization/remote.py` (title-signal
  redesign, span-aware tokenizer, comma-contrast rule, docstring
  rewritten), `backend/tests/fixtures/normalization/remote_type_cases.json`
  (8 new cases, 1 reworded), this handoff entry. `app/normalization/
  types.py`, both test files, and `docs/ROADMAP.md` untouched.
- Verification: both targeted modules directly (**85 passed**, was 77);
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **9 steps PASS**, **1580 full-suite tests** (was 1572; +8). No
  database/migration/schema touched.
- Adversarial self-review (abbreviated, proportionate to Class R): probed
  ten entirely unseen ambiguous titles beyond the three reproduced
  strings — all ten correctly returned `unavailable`, including a
  hyphen-glued `"Remote-First"` case. Separately probed comma-boundary
  edge cases (spacing variants, a double comma, a bare tab) — every
  variant behaved exactly as the exact-comma regex specifies. Two
  targeted breaks, each reverted cleanly: (1) reverted title matching to
  "bare marker found anywhere" — the three reproduced regressions failed,
  each leaking again; (2) reverted the comma check to token-gap-only —
  all four separator-rejection regressions failed, while the exact-comma
  positive control remained correctly unaffected.
- Deviations/known limitations: the pre-existing `alembic check`
  substitution. The negation-window and dual-unconnected-negator
  limitations, unchanged. No remaining title false-positive limitation is
  claimed — tested against 13 total ambiguous titles and none leaked.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-06, Codex.
- Diff reviewed: `c8a1217..3a8cc70` on `phase-3/remote-classifier`.
- Verdict: **Changes requested.** Both prior findings are substantively closed: title
  evidence is now structural rather than bare-token-anywhere, and comma contrast is
  derived from the original character gap rather than a punctuation-blind token gap.
  One narrow fail-closed defect remains in the new structural-title implementation.
- Independent verification: inspected the three-file correction and handoff
  rearrangement; directly reran both targeted modules (**85 passed**); ran the
  canonical verifier (**all 10 checks PASS, 1580 full-suite tests**); replayed the
  three previously leaking domain titles and the comma/whitespace/hyphen/slash/dash
  matrix successfully; and exercised malformed delimiter pairs directly.
- Finding:
  1. **Low — mismatched bracket types are accepted as a valid structural title
     marker.** `_PAREN_BRACKET_RE` uses a combined opening class and combined closing
     class, so it does not require matching pairs. Consequently both `(Remote]
     Infrastructure Engineer` and `[Remote) Infrastructure Engineer` currently return
     `remote/inferred`, even though neither contains a valid parenthesized or bracketed
     segment. This conflicts with the classifier's conservative, fail-closed contract
     and with the documented structural-marker rule. Parse `(...)` and `[...]` as
     separate alternatives (or otherwise enforce paired delimiter types), preserve
     valid matched-parenthesis/bracket behavior, and add unavailable regressions for
     both crossed forms.
- Prior-finding disposition: the acknowledged arbitrary-leading-title false positives
  now return unavailable; valid exact/parenthesized/bracketed/delimited and explicit-
  phrase title cases remain supported; `_is_comma_contrast` now requires exactly one
  raw comma with optional surrounding whitespace and rejects the requested alternative
  separators. The description catalog, negation protections, import allow-list,
  `NormalizationResult`/`Provenance`, public signature, and pure/offline boundary
  remain accepted.
- Mechanical ledger note: Iteration 2 did not contain its required `Work review`
  heading/pending placeholder after the implementer rearranged the historical blocks.
  This review adds the missing heading in its proper paired location; no historical
  review wording was altered.
- Exact requested correction: change only the paired-delimiter extraction and its
  regression corpus/tests, plus the next handoff entry. Run the targeted modules and
  canonical verifier. Do not merge or begin another parser pending re-review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/remote-classifier` for the single Low finding from
  Iteration 1's `Work review` above. Base: commit `3a8cc70` plus the
  uncommitted review. Preserved: the structural title-marker rule, the
  separator-exact comma-contrast rule, the description positive catalog
  and context protections, coordinated/unresolved negation, the
  fail-closed import allow-list, `NormalizationResult`/`Provenance`, the
  public signature, and the pure/offline scope. No ingestion/persistence/
  providers/models/migration or other parser touched.
- Outcome: `_PAREN_BRACKET_RE` previously matched any opening `(`/`[`
  followed eventually by any closing `)`/`]`, accepting crossed forms like
  `"(Remote]"` or `"[Remote)"` as a valid structural marker. Rewrote it as
  two entirely separate alternatives — `\(([^()\[\]]*)\)` or
  `\[([^()\[\]]*)\]` — so a match only ever comes from a properly paired
  delimiter type; `_title_segments` now reads whichever capture group
  actually matched (`group(1)` for parens, `group(2)` for brackets). A
  crossed-delimiter title now matches neither alternative at all: its
  mismatched characters are left in the plain delimiter-split remainder,
  same as any other stray punctuation, and the whole (undelimited, since
  neither `(`/`[` nor `)`/`]` is a segment delimiter) title fails the
  exact-segment-match check just like `"Remote Systems Administrator"`
  does — no separate exclusion or special-case was needed.
- New fixture cases (corpus now 70 total, +3 net): the two reproduced
  crossed-delimiter regressions (`title_crossed_paren_then_bracket_
  rejected` for `"(Remote] Infrastructure Engineer"`,
  `title_crossed_bracket_then_paren_rejected` for `"[Remote) Infrastructure
  Engineer"`), and one new positive control
  (`positive_control_valid_matched_bracket_marker`,
  `"Facilities Coordinator [Remote]"` -> `remote`/`inferred`) proving valid
  matched-bracket behavior is preserved with actual coverage, not merely
  asserted — no prior fixture exercised a bracket-only marker.
- Files changed: `backend/app/normalization/remote.py` (paired-delimiter
  regex and `_title_segments`, plus an updated docstring on
  `_title_segments`), `backend/tests/fixtures/normalization/
  remote_type_cases.json` (3 new cases), this handoff entry. No other
  file touched.
- Verification: both targeted modules directly (**88 passed**, was 85);
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **10 steps PASS**, **1583 full-suite tests** (was 1580; +3). `ruff
  format --check`/`ruff check`/`mypy` all pass. `check_repo.py` and `git
  diff --check` both pass as part of the verifier. No database/migration/
  schema touched.
- Adversarial self-review: given the narrow, single-finding scope of this
  correction (not separately requested this round), verification relied on
  the two crossed-form regressions themselves — both directly exercise the
  exact defect reported (a crossed pair previously returning a confident
  positive) and both now pass against the corrected regex, alongside the
  new valid-bracket positive control and every previously-passing
  parenthesized/bracketed case (`positive_title_only_remote`,
  `hybrid_cloud_title_and_description_exclusion`'s title, etc.),
  confirming the fix is targeted and did not regress valid matched-pair
  behavior.
- Deviations/known limitations: none beyond those already recorded in
  Iteration 1 (pre-existing `alembic check` substitution; negation-window
  and dual-unconnected-negator scope).
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-06, Codex.
- Diff reviewed: `3a8cc70..7c0bd05` on `phase-3/remote-classifier`.
- Verdict: **Approved with one documentation-only binding clarification.** The
  paired-delimiter defect is closed and there are no remaining executable findings.
- Independent verification: inspected the three-file correction; directly replayed
  both crossed forms (now `unavailable`), valid `(...)` and `[...]` controls (still
  `remote/inferred`), and the prior arbitrary-leading-title regression; reran both
  targeted modules (**88 passed**); and ran the canonical verifier (**all 10 checks
  PASS, 1583 full-suite tests**). Ruff, mypy, repository checks, database safety,
  focused/full pytest, and temporary-directory cleanup all passed.
- Finding disposition: `_PAREN_BRACKET_RE` now encodes `(...)` and `[...]` as separate
  alternatives, and `_title_segments` selects the populated capture group. Neither
  crossed form can be extracted as a structural segment, while both valid pair types
  remain supported. The change is bounded to the requested parser, corpus, and ledger
  files; no other parser, database, migration, provider, or ingestion code changed.
- Documentation-only clarification: Iteration 2's `Work done` says the canonical
  verifier passed “all 9 steps,” but the genuine verifier output reports **10** steps
  (the tenth is temporary-directory cleanup). Correct this current claim to “all 10
  steps” before merge. This is mechanical, does not require another test run, and does
  not require another Codex re-review.
- Merge remains a separate user authorization. Do not begin another parser or wire
  Phase 3 behavior into ingestion as part of that merge.
