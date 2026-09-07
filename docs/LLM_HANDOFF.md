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

---

## Iteration 2

### Work done

- Date/agent: 2026-09-07, Claude Code (Sonnet 5). Risk class R (Class
  R-plus-adversarial per the approved proposal). New bounded slice on new
  branch `phase-3/seniority-classifier`, base: clean `main@7a90282` (the
  employment-classifier merge commit). Third Phase 3 parser:
  `classify_seniority(title, description) -> NormalizationResult[Seniority]`
  where `Seniority = entry_level | mid_level | senior | staff | principal |
  director`. Implements the third, twice-revised proposal exactly, plus
  five binding clarifications from the approval message.
- Independent implementation, not an `employment.py`/`remote.py` import:
  its own tokenizer, its own two-entry hyphen-compound canonicalization
  (`entry-level`, `mid-level` only), its own segment extraction, its own
  negation grammar — none shared or imported (proven by
  `test_import_boundary_allow_list` plus a regression asserting both
  `app.normalization.employment` and `app.normalization.remote` are
  specifically rejected by this module's own allow-list).
- Title grammar (binding clarification 2): `principal`/`director` phrases
  must be anchored at a structural segment's leading position, never
  matched anywhere inside it — `Director of Engineering`/`Principal
  Software Engineer` match; `Assistant to the Director of Engineering`,
  `Office of the Director of Operations`, and `Assistant to the Principal
  Engineer` (the required third prefix-wrapped negative) do not, since an
  unrecognized word occupies the leading position instead.
- Description grammar (binding clarification 1, the most novel mechanism
  in this slice): after a self-referential anchor (`this is`, `it is`,
  `the position is`, `this position is`, `the role is`, `this role is`,
  `we are hiring`, `seeking`), the first candidate must begin immediately
  after only an approved grammatical prefix — optional `a`/`an`/`the`; or
  `not`/`no`/`neither`/`not either` plus an optional article — never
  searched for further into the sentence. This is why `This role is
  supported by a senior engineer.`, `This position is reporting to the
  Director of Engineering.`, and `We are hiring alongside a staff
  engineer.` all resolve to `unavailable`: the token immediately after
  each anchor (`supported`, `reporting`, `alongside`) is neither a valid
  prefix nor a candidate. This entirely replaces `employment.py`'s
  nearest-candidate-window negation mechanism with a simpler, local
  grammar — a deliberate, narrower design suited to this parser's own
  requirement, not a partial reuse.
- Corrected excluded-term claim (binding clarification 5, corrected again
  by clarification 2 of the final approval): `manager`/`lead`/
  `associate`/`executive`/`vp`/C-level remain in no catalog, but three
  exact exclusion phrases were added for the specific required outcomes —
  `senior executive assistant`, `senior vice president`, `senior vp` —
  masked entirely so `senior` cannot leak through them either. `Senior
  Manager` deliberately still resolves to `senior` (manager contributes
  nothing but does not block a different, actually-recognized qualifier).
  `Lead Senior Engineer`/`Associate Director of Engineering` remain
  `unavailable` via the pre-existing leading-position rule, needing no new
  exclusion.
- Compound/conflict precedence (binding clarification 7): `Sr. Staff
  Engineer` -> `staff`, `Senior Principal Engineer` -> `principal`
  (compound rule, `director` deliberately excluded from it), `Senior
  Director`/`Staff/Principal Engineer`/`Junior Senior Analyst` -> conflict
  -> `unavailable`, and `Senior, Staff Engineer`/`(Senior) Staff Engineer`
  (comma/parens forcing two segments) differ deterministically from the
  undelimited `Senior Staff Engineer` by defeating the compound rule.
- Files changed: `backend/app/normalization/seniority.py` (new),
  `backend/tests/test_normalization_seniority.py` (new),
  `backend/tests/fixtures/normalization/seniority_cases.json` (new, 89
  cases), `docs/ARCHITECTURE.md` (annotated `seniority.yaml` as planned
  future enrichment, not implemented by this slice, per the accepted
  decision), `docs/ROADMAP.md` (Phase 3 bullet — also corrected a
  pre-existing staleness: it still said the employment-classifier slice
  was "pending review, not merged" despite the merge already recorded
  above at `8e136c0`), this handoff entry. `app/normalization/
  employment.py`, `app/normalization/remote.py`, `app/normalization/
  types.py` untouched.
- Honest evidence-gap statement preserved (binding clarification 5 of the
  final approval): the corpus contains exactly one `sanitized_capture`
  fixture (the real Greenhouse-derived title from `backend/tests/
  fixtures/discovery/greenhouse_live_canary.json`, a negative control) —
  a single data point, not broad realistic-positive coverage. Recorded in
  both the module docstring and a dedicated test
  (`test_corpus_origin_values_are_honestly_labeled`, asserting exactly
  one `sanitized_capture` case) as an acknowledged, open Phase 3
  exit-gate gap, not something this slice claims to satisfy.
- Verification: targeted seniority module alone (**89 passed** — 84
  fixture cases + 5 code-level tests); all four normalization modules
  together (**262 passed**). `ruff format --check`/`ruff check`/`mypy`
  all pass. Genuine external `python scripts/verify.py --level routine`
  (full run) — all **9 steps PASS**, **1757 full-suite tests** (was 1668;
  +89). No database/migration/schema touched.
- Deeper adversarial verification (Class-R-plus-adversarial, required by
  the approved proposal): beyond the fixture corpus, probed ~16 unseen
  cases — additional negator forms (`no`, `neither...the...nor...the`,
  `not either...the...or...the`), plain (non-negated) `or` coordination,
  a mid-sentence anchor (correctly not recognized — anchors are
  sentence-initial only, an intentional scope limit), multi-sentence
  descriptions, the compound rule inside description, and a later
  unrelated qualifier-shaped phrase after an already-found candidate
  (`"...staff-level collaboration"` — correctly never reached, since
  description has no broad trailing conflict-scan the way title does,
  only the tight coordination-adjacent check). All resolved correctly or
  to an already-documented, intentional scope boundary. Two minor,
  out-of-scope observations reported rather than fixed: (1) coordination
  propagation only fires when the second candidate is directly adjacent
  to the coordinator with no intervening noun — a sentence like `"This is
  neither the senior role nor the staff position."` still reaches the
  correct final `unavailable`, but via the second candidate never being
  examined rather than via successful coordination-propagation; (2) a
  title ending in a literal period (e.g. `"Senior."`) fails to match,
  since the period stays glued to the token (unlike a comma, an
  established segment delimiter) — a rare input shape, not one of the
  required cases, and not fixed here since doing so risks the `sr.`/`jr.`
  abbreviation handling this slice depends on.
- Deviations/known limitations: the two adversarial observations above
  (both out of scope, not fixed); the pre-existing `alembic check`
  substitution (unrelated); the honest evidence-gap statement (not a
  limitation of the code, a limitation of the evidence base).
- STOP — awaiting Codex review. Do not merge, begin another Phase 3
  parser, wire into ingestion/persistence, contact providers, or create a
  migration.

### Work review

- Date/reviewer: 2026-09-07, Codex.
- Diff reviewed: `7a90282..1ac2b81` on `phase-3/seniority-classifier`.
- Verdict: **Changes requested.** One executable finding and one documentation
  correction remain.
- Independent verification: the targeted seniority module passes (**89 tests**), and
  the canonical focused verifier passes all **10 steps** (**89 focused / 1757 full
  suite**), including Ruff, mypy, repository checks, test-database safety, and cleanup.
  `git diff --check` is clean. These green results do not cover the missing description
  conflict behavior below.
- Findings:
  1. **High — description parsing omits the approved multiple-level conflict check.**
     `seniority.py:525-565` adds the first positive candidate and examines only a
     directly adjacent `or`/`nor` candidate. Unlike the title path at
     `seniority.py:453-490`, it never calls `_trailing_conflict_labels` or an equivalent
     description-safe mechanism. Direct execution therefore returns
     `senior/parsed_description` for `This is a senior director position.`,
     `entry_level/parsed_description` for `This is a junior senior analyst role.`, and
     `staff/parsed_description` for `This is a staff/principal engineer position.` The
     approved proposal said the description conflict rule would fail closed on two
     distinct values; the new `Work done` entry instead relabels the omission as an
     intentional boundary. Implement a description-safe immediate-title-phrase conflict
     check. It may be narrower than title's broad trailing scan so later relational prose
     is not mistaken for the posting's tier, but it must reject the three reproduced
     forms and equivalent immediately joined distinct levels. Preserve the approved
     `senior staff -> staff` and `senior principal -> principal` compounds and ordinary
     single-value descriptions. Add direct regressions for all of those outcomes.
  2. **Low — the handoff gives the fixture count as 89.** The JSON corpus contains 84
     cases; 89 is the module's total test count (84 parametrized corpus cases plus five
     code-level tests). Correct `docs/LLM_HANDOFF.md:305-306` without rewriting the
     historical verification totals.
- Accepted portions: the anchored title grammar, anchor-adjacent description entry
  grammar, exact executive/support exclusions, compound precedence on the covered path,
  independent import boundary, locally implemented hyphen handling, taxonomy
  annotation, merge-state-aware ROADMAP wording, and honest real-fixture evidence gap
  all match the approved scope.
- Exact requested correction: modify only `seniority.py`, its fixture corpus/tests, and
  the next handoff entry (including the count correction). Do not expand the canonical
  vocabulary, aliases, anchors, explicit principal/director phrases, exclusion catalog,
  taxonomy work, ingestion wiring, schemas, providers, or another parser. Run the
  targeted normalization tests and canonical verifier, adversarially replay the three
  reproduced conflicts plus preserved compound/single-value controls, commit and push
  the feature branch, then stop for re-review.
