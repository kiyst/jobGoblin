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
  pass on `phase-3/employment-classifier` for all four findings in
  Iteration 1's `Work review` above. Base: commit `cee74e5` plus the
  uncommitted review. Preserved: the axis split/scope, `EmploymentType`
  vocabulary, cross-axis inert masking concept, same-axis-conflict rule,
  fail-closed import allow-list, `NormalizationResult`/`Provenance`, public
  signature, and pure/offline scope. No ingestion/persistence/providers/
  models/migration or other parser touched.
- Outcome, addressing each finding exactly:
  1. **Negation direction/clause-aware binding.** The nearest-candidate
     search now tries the *forward* tier (candidates after the negator)
     first; only falls back to the *backward* tier when no forward
     candidate is in-window. Fixes the reported false facts (`"part-time
     role... not a full-time position"` -> `part_time`, its symmetric
     swap -> `full_time`, `"seasonal work... not a full-time position"`
     -> `seasonal`) while preserving both required-unchanged patterns
     (`"Not internship, full-time position available."` -> `full_time`;
     trailing backward-only negation with no forward candidate ->
     `unavailable`). Replaced the prior "known limitation" fixture with
     the fixed expectation and added the full asymmetric matrix (6 new
     `negation_direction_*` cases).
  2. **Separator identity.** `_TOKEN_RE` now treats comma/slash/ampersand/
     en-dash/em-dash as their own standalone hard tokens instead of
     silently vanishing like whitespace. A further adversarial finding
     during this same pass: a plain ASCII hyphen with whitespace on
     either side (`"full - time"`) was still slipping through as
     transparent, unlike the two genuinely-approved spellings — fixed by
     normalizing only *glued* hyphens (`(?<=\S)-(?=\S)`) to a space before
     tokenization, so a spaced hyphen now tokenizes as its own hard token
     too. Applies uniformly to multi-token cross-axis mask phrases (no
     separate code path). 9 new `separator_exactness_*` regressions
     (title and description; slash, comma, ampersand, en-dash, glued
     em-dash, spaced hyphen; one multi-token mask-phrase case; one
     positive control for the space-separated spelling).
  3. **Structural title matrix.** Added the 11 missing
     `structural_matrix_*` cells to complete the 4-structural-form
     (whole-title, parenthesized, bracketed, delimiter-segment) x
     4-value cross-product (16 total, 5 pre-existing + 11 new). Also
     added an explicit docstring statement that no "explicit phrase
     anywhere" mechanism exists for `title` in this slice, and why —
     rather than leaving its absence implicit.
  4. **ROADMAP correction.** Replaced the blanket "Phases 4-14: not
     started" bullet with a narrow correction: the Greenhouse canary
     (`64a3534`) and disposable-database live proof (`907b3f0`) are
     merged prework, the production `AtsScrapersProvider` adapter and
     Phase 4 completion remain outstanding. Confirmed both commits are
     ancestors of `main` before writing this.
- Files changed: `backend/app/normalization/employment.py` (tokenizer,
  negation direction, docstring), `backend/tests/fixtures/normalization/
  employment_type_cases.json` (1 replaced in place + 26 new, 66 total,
  was 40), `docs/ROADMAP.md` (Phase 4 bullet), this handoff entry.
  `backend/tests/test_normalization_employment.py`, `app/normalization/
  types.py`, `app/normalization/remote.py` untouched.
- Verification: targeted employment module alone (**71 passed** — 66
  fixture cases + 5 code-level tests —, was 45); all three normalization
  modules together (**159 passed**). `ruff format --check`/`ruff
  check`/`mypy` all pass. Genuine external `python scripts/verify.py
  --level routine` (full run) — all **9 steps PASS**, **1654 full-suite
  tests** (was 1628; +26, exactly matching the 26 net-new fixture cases).
  No database/migration/schema touched.
- Fresh-context adversarial review of the corrected negation and separator
  mechanisms (required this round, not abbreviated): probed ~13 unseen
  sentences beyond the fixture corpus (multi-clause negation with mixed
  forward/backward assertions, `"neither...nor"` combined with direction,
  underscore/tab/double-space/mixed-case separators, a slash-separated
  disjunction title). All resolved correctly or to an already-documented,
  orthogonal scope limitation. One new, out-of-scope observation
  surfaced and reported rather than fixed: `"This is neither seasonal nor
  a full-time position."` still lets `full_time` survive, because
  or/nor coordination propagation requires *exactly* one token between
  spans, and the article "a" breaks that gap here — an existing
  characteristic of the coordination mechanism itself (unchanged by this
  pass), not something finding 1 asked this pass to fix.
- Deviations/known limitations: the coordination-adjacency gap above
  (new observation, out of scope, not fixed); the pre-existing `alembic
  check` substitution (unrelated). No other known limitation remains
  from Iteration 1's review — the previously-documented negation
  direction limitation is fixed, not merely narrowed.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-07, Codex.
- Diff reviewed: `cee74e5..db1805f` on `phase-3/employment-classifier`.
- Verdict: **Changes requested.** The four requested corrections materially improve
  the classifier: direction-aware negation fixes the reproduced contrast family, the
  16-cell structural-title matrix is present, and ROADMAP now states the Phase 4 proof
  history accurately. Two remaining mechanisms still emit confident false facts and
  block approval.
- Independent verification: inspected all four changed files; reran the three
  normalization modules (**159 passed**); ran the canonical verifier with employment
  focus (**all 10 checks PASS, 71 focused / 1654 full-suite tests**); replayed the
  corrected forward/backward matrix and required preserved cases; and directly probed
  article-bearing coordination and compound-hyphen variants.
- Findings:
  1. **High — article-bearing `neither…nor`/`either…or` coordination still leaks a
     negated employment value.** The disclosed `This is neither seasonal nor a
     full-time position.` returns `full_time/parsed_description`; so does the even more
     explicit `This is neither a seasonal role nor a full-time position.`. `This is not
     either a seasonal role or a full-time position.` also returns `full_time`.
     Calling this out of scope is not acceptable: it is the same negation/coordination
     safety contract corrected in this pass, and Phase 3 must prefer unknown over the
     exact value the sentence excludes. Extend coordination narrowly to accept the
     coordinator followed by an optional article/determiner (`a`, `an`, or `the`), not
     arbitrary intervening prose. Add `nor a`, `or a`, and at least one `an`/`the`
     regression, while preserving non-coordinated candidates as independent.
  2. **High — global glued-hyphen normalization still creates unsupported evidence.**
     `_GLUED_HYPHEN_RE` replaces every ASCII hyphen between non-whitespace characters,
     not exactly one approved compound joiner. Direct execution classifies `Full--Time`
     and `Full---Time` as `full_time`, and `This is a non-full-time position.` as
     `full_time/parsed_description`—the opposite of what the `non-` prefix says. The
     same mechanism affects multi-token mask vocabulary. Replace global hyphen removal
     with exact, boundary-aware canonicalization of the approved spellings only
     (`full-time`, `part-time`, and the explicitly approved cross-axis compounds), or
     preserve spans/separators during matching. A recognized spelling embedded in a
     larger hyphen chain (`non-full-time`, `full-time-ish`) must not be normalized as an
     independent positive. Add title/description regressions for double/triple hyphens,
     `non-full-time`, and a boundary-wrapped approved positive; preserve ordinary
     `full-time`/`full time` and the approved mask cases.
- Prior-finding disposition: the original backward-nearest contrast cases now produce
  the required results; slash/comma/ampersand/dash and whitespace-surrounded-hyphen
  regressions pass; the complete four-form-by-four-value title matrix is present with
  no phrase-anywhere claim; and ROADMAP correctly distinguishes merged Greenhouse proof
  work from the unstarted production adapter. These portions are accepted.
- Exact requested correction: change only the two mechanisms above, their corpus/tests,
  and the next handoff entry. Do not expand the vocabulary or add label/value formats,
  title-suffix heuristics, shared utilities, ingestion wiring, migrations, providers,
  or another parser. Run targeted normalization tests and the canonical verifier;
  adversarially test coordination determiners and hyphen-chain boundaries; commit/push
  the feature branch; stop for re-review.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-07, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-3/employment-classifier` for both remaining findings in
  Iteration 1's `Work review` above. Base: commit `db1805f` plus the
  uncommitted review. Preserved: every already-accepted correction
  (direction/clause-aware negation, the 16-cell structural-title matrix,
  the ROADMAP Phase 4 wording, axis split/scope, `EmploymentType`
  vocabulary, same-axis-conflict rule, fail-closed import allow-list,
  `NormalizationResult`/`Provenance`, public signature, pure/offline
  scope). Modified only `employment.py`, its corpus/tests, and this
  handoff entry — `docs/ROADMAP.md` untouched this pass, per instruction.
- Outcome, addressing each finding exactly:
  1. **Article-bearing `neither…nor`/`either…or` coordination.**
     `_is_coordinated` now accepts a gap of exactly one coordinating
     token (`"or"`/`"nor"`, unchanged) **or** exactly one coordinating
     token followed by exactly one determiner (`"a"`, `"an"`, `"the"`) —
     never arbitrary intervening prose (verified adversarially: an extra
     word between the determiner and the candidate, e.g. `"or a very
     full-time position"`, correctly still fails to coordinate). Fixes
     all three reproduced leaks (`"neither seasonal nor a full-time
     position"`, `"neither a seasonal role nor a full-time position"`,
     `"not either a seasonal role or a full-time position"`) -> all now
     `unavailable`. 6 new `coordination_determiner_*`/`coordination_
     preserves_*` regressions, including an `"an"` form, a `"the"` form,
     and one proving a non-coordinated (`"and"`-joined) independent
     candidate still survives untouched.
  2. **Glued-hyphen normalization was global, not boundary-aware.**
     Replaced the blanket `_GLUED_HYPHEN_RE` (any hyphen between
     non-whitespace characters) with
     `_canonicalize_approved_hyphen_compounds`: an explicit, small list
     of exactly four approved compound spellings (`full-time`,
     `part-time`, `contract-to-hire`, `temp-to-perm`), each matched only
     at a genuine word boundary and only when **not** immediately
     preceded or followed by another hyphen. `"Full--Time"`/
     `"Full---Time"` never match the literal single-hyphen pattern at
     all; `"non-full-time"`/`"full-time-ish"` are blocked by the adjacent-
     hyphen lookaround. Any hyphen surviving this step is tokenized as
     its own hard token (`_TOKEN_RE`, unchanged from the prior pass). 9
     new `hyphen_boundary_*` regressions: double/triple hyphen (title),
     `non-`/`-ish` chains (description), and positive controls for
     ordinary `full-time`, `full time`, and both approved masked
     compounds.
- Files changed: `backend/app/normalization/employment.py`
  (`_is_coordinated`, `_canonicalize_approved_hyphen_compounds` replacing
  `_GLUED_HYPHEN_RE`, docstring), `backend/tests/fixtures/normalization/
  employment_type_cases.json` (14 new cases — 6 coordination + 8
  hyphen-boundary —, 80 total, was 66), this handoff entry.
  `backend/tests/test_normalization_employment.py`, `docs/ROADMAP.md`,
  `app/normalization/types.py`, `app/normalization/remote.py` untouched.
- Verification: targeted employment module alone (**85 passed**, was 71
  — 80 fixture cases + 5 code-level tests); all three normalization
  modules together (**173 passed**). `ruff format --check`/`ruff
  check`/`mypy` all pass. Genuine external `python scripts/verify.py
  --level routine` (full run) — all **9 steps PASS**, **1668 full-suite
  tests** (was 1654; +14, exactly matching the 14 net-new fixture cases).
  No database/migration/schema touched.
- Adversarial testing of coordination determiners and hyphen-chain
  boundaries (required this round): probed 14 unseen cases beyond the
  fixture corpus. Confirmed the determiner extension stays narrow — an
  extra word between the coordinator/determiner and the candidate
  (`"or a very full-time position"`, `"or perhaps a full-time
  position"`) correctly fails to coordinate, leaving the farther
  candidate to survive on its own merits rather than being wrongly
  suppressed. Confirmed the hyphen-boundary fix generalizes beyond the
  two reported prefixes/suffixes (`"quasi-full-time"`,
  `"full-time-equivalent"`, `"Part--Time"` all correctly rejected) and
  handles degenerate stray-hyphen inputs (`"-full-time"`, `"full-time-
  position"` typo-shaped forms) conservatively (unavailable, not a
  guess). No new issues found.
- Deviations/known limitations: none new. The pre-existing `alembic
  check` substitution remains, unrelated to this slice. The
  coordination-adjacency gap noted in the prior pass (an intervening
  article breaking plain `"or"/"nor"` propagation) is now closed for the
  single-determiner case; arbitrary multi-word intervening prose between
  a coordinator and a candidate is still not coordinated, by design, not
  as a remaining defect.
- STOP — awaiting Codex re-review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-07, Codex.
- Diff reviewed: `db1805f..428703f` on `phase-3/employment-classifier`.
- Verdict: **Approved.** No executable findings.
- The two requested corrections are closed. Direct adversarial replay confirms the
  three reported article-bearing coordination cases now fail closed, while the
  extension remains limited to `or`/`nor` followed by at most one approved
  determiner. Double/triple hyphens and prefix/suffix chains such as
  `non-full-time` and `full-time-ish` no longer create positive evidence; ordinary
  approved `full-time`/`part-time` spellings and the two approved cross-axis mask
  compounds remain functional.
- Independent verification: all three normalization modules pass (**173 tests**);
  the canonical focused verifier passes all **10 steps** (**85 focused / 1668 full
  suite**), including Ruff, mypy, repository checks, test-database safety and
  cleanup. `git diff --check` is clean. No schema or migration changed.
- Scope is appropriately bounded to `employment.py`, the fixture corpus, and this
  handoff ledger. The existing design choice not to coordinate across arbitrary
  intervening prose is documented and is not expanded by this correction.
- The employment classifier correction pass is accepted. Do not merge or begin
  another Phase 3 parser until the user explicitly authorizes that action.

### Merge record

- Date: 2026-09-07. User authorized merging `phase-3/employment-classifier`
  into `main` following Codex's Approved review (no executable findings;
  approval commit `67cf09b`) above.
- Pre-merge state: `main` and `origin/main` both at `243a78a`; feature
  branch `phase-3/employment-classifier` and its origin both clean and
  synced at `67cf09b` (containing implementation/correction commits
  `cee74e5`, `db1805f`, `428703f`, and the review-approval commit
  `67cf09b`).
- Merge: `git merge --no-ff phase-3/employment-classifier` on `main` —
  merge commit `8e136c0`. `git diff phase-3/employment-classifier HEAD`
  is empty (zero content difference); `git diff --check` and
  `check_repo.py` both exit 0; working tree clean.
- Post-merge verification: genuine external `python scripts/verify.py
  --level routine` (full run, no `--focus`) — all **9 steps PASS** (Ruff
  format/check, mypy, `check_repo.py`, `git diff --check`,
  disposable-database URL/reachability, **1668 full-suite tests**,
  temp-directory cleanup).
- Pushed: `main` at `8e136c0`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `243a78a` (the
  commit immediately before this merge) — this removes
  `app/normalization/employment.py`, both new test/fixture files, and the
  `docs/ROADMAP.md`/`docs/LLM_HANDOFF.md` wording changes cleanly, with
  no migration to reverse and no data written by this slice to any
  environment (pure Python, never wired into ingestion/persistence).
- **Phase 3's second parser slice is merged, not Phase 3 itself.** The
  deterministic full_time/part_time/seasonal/internship classifier
  (`jobs.employment_type` only — `jobs.contract_type` and `jobs.shift`
  remain untouched, deferred/unplanned respectively) is now on `main`,
  reviewed across two correction rounds with no remaining executable
  findings. The other six required Phase 3 parsers (title, salary,
  location, seniority, experience, skill) remain unstarted; this
  classifier is not wired into `ingestion/pipeline.py` or
  `ingestion/persistence.py`, and no `parser_version`/`field_provenance`
  write exists yet — those remain Phase 4+ concerns.
- STOP — do not begin or propose another Phase 3 parser, wire this
  classifier into ingestion/persistence, contact providers, or create a
  migration without separate authorization.
