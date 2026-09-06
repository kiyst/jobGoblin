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

- Date/agent: 2026-09-05, Claude Code (Sonnet 5). Risk class R correction
  pass on `phase-2/closure` for the two bounded findings from the original
  Phase 2 closure pass's review (that original pass and its review are now
  rotated out of this ledger per the two-iteration rule; both remain in
  Git history at commit `cffe8a1` and its review commit). Base: `cffe8a1`
  plus the uncommitted review. Only the affected test file and this
  handoff ledger changed — no fixture content, product code, architecture
  wording, or ROADMAP closure-candidate status touched, per the user's
  explicit preservation instruction.
- Outcome, addressing each finding exactly:
  1. **Cleanup not failure-safe.** Audited both new tests end to end.
     `test_two_distinct_tenants_sharing_source_job_id_produce_two_jobs` now
     queries the run's `JobOccurrence`/`RawJobIngestion` rows and extends
     `job_ids`/`raw_ingestion_ids` immediately after `pipeline.run()`
     returns, before any assertion (previously deferred until after the
     four global-count assertions).
     `test_null_tenant_natural_key_collision_resolves_to_one_occurrence` now
     captures run 1's raw-ingestion id immediately after run 1 (before its
     `first_seen_at`/`last_seen_at` assertions), and run 2's new raw-
     ingestion id immediately after run 2 (before any of the count/content
     assertions that follow) — using the same
     already-captured-ids-minus-new-rows pattern
     `test_two_run_natural_key_spine` established. Both tests' later
     assertions now read from data already captured for cleanup, not the
     other way around.
  2. **NULL-tenant test's first-run counters unproven.** Added an assertion
     block immediately after run 1's raw-ingestion id is captured: `run1`
     is `completed`, `jobs_discovered=1`, `jobs_inserted=1`,
     `jobs_updated=0`, `failures=[]`; its sole
     `CollectionRunProviderAttempt` is `completed`,
     `jobs_discovered=1`/`jobs_inserted=1`/`jobs_updated=0`, and
     `error_category`/`error_message` are both `None` (the "empty failure
     state" Codex requested). The existing run-2 `inserted=0, updated=1`
     assertions are unchanged, so the full insert-then-update transition is
     now proven end to end.
- Files changed: `backend/tests/test_ingestion_pipeline.py` (both tests'
  cleanup-capture ordering; new first-run assertion block in the
  NULL-tenant test), this handoff entry. No fixture, product code, migration,
  or other documentation file touched.
- Verification: the two focused tests directly (**2 passed**); the full
  relevant ingestion/identity suite (`test_ingestion_pipeline.py`,
  `test_ingestion_concurrency.py`, `test_ingestion_natural_key.py`,
  `test_job_occurrences.py`, `test_orchestrator.py`): **250 passed**;
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **9 steps PASS**, **1495 full-suite tests**, ~130-143s across reruns.
  `alembic heads` confirms `0017` remains the sole head; `git diff --stat
  origin/main -- migrations/` is empty; dev database (`jobgoblin`) confirmed
  unchanged at `0006`. Explicit disposable-database row-count check (`jobs`,
  `job_occurrences`, `raw_job_ingestions`, `collection_runs`,
  `collection_run_provider_attempts`, `identity_conflicts`, `users`,
  `user_jobs`): 0 before the suite, 0 after.
- Adversarial self-review (abbreviated, proportionate to Class R): re-broke
  both invariants exercised in the prior review (`_existing_occurrence_
  conditions()`'s `TENANT`-domain tenant filter removed; `NO_TENANT`-domain
  filter inverted) to prove finding 1's fix is actually load-bearing, not
  just finding 2's new assertions. (1) With the tenant filter removed,
  `test_two_distinct_tenants_...` still failed at the same assertion as
  before — but this time a fresh disposable-database row-count check
  immediately afterward confirmed **0 rows in every affected table**,
  proving the earlier-captured ids let `finally` clean up completely despite
  the failure (this is the exact scenario the prior review's finding 1 said
  could leak rows before the fix). (2) With the `NO_TENANT` filter inverted,
  the second `pipeline.run()` call itself raised a real
  `UniqueViolationError` (as before) rather than failing at an assertion;
  because the raising call never returns, its own internally-written
  `CollectionRun`/attempt/raw rows cannot be captured by any id-after-return
  pattern — a pre-existing structural property shared by every test in this
  file that calls `pipeline.run()` once per line, not a regression from
  this correction and not one of the two findings. The resulting one leaked
  row per table was identified and deleted, and a fresh row-count check
  confirmed 0 before the final verification run above. Both temporary
  breaks were then reverted (`git diff --stat -- backend/app/ingestion/
  persistence.py` empty afterward), and the two focused tests re-confirmed
  passing.
- Deviations/known limitations: the pre-existing `alembic check`
  substitution (unrelated, recorded previously); the structural
  raise-before-return cleanup limitation noted above, which affects the
  whole file, not just these two tests, and was left unmodified as out of
  scope for this bounded correction.
- STOP — awaiting Codex re-review. Do not merge, begin Phase 3, contact
  providers, add production behavior, or create a migration.

### Work review

- Date/reviewer: 2026-09-05, Codex.
- Diff reviewed: `cffe8a1..d09ac00` on `phase-2/closure`.
- Verdict: **Approved.** Both bounded findings are closed, and no further
  corrections are required.
- Independent review: inspected both corrected tests and the two-iteration
  ledger rotation. In the distinct-tenant case, the run id, both resulting
  Job ids, and both raw-ingestion ids are now captured before the first
  post-run assertion. In the NULL-tenant case, the first run's Job/raw ids
  and the second run's newly-created raw id are captured before their
  respective assertions. The first run and its sole provider attempt now
  explicitly prove `completed`, `discovered=1`, `inserted=1`, `updated=0`,
  and an empty failure/error state, completing the insert-then-update matrix.
- Verification: reran the two corrected tests directly (**2 passed**) and
  independently ran `python scripts/verify.py --level routine`: all **9
  checks PASS**, including Ruff, mypy, repository/diff checks, disposable-DB
  safety/reachability, **1495 full-suite tests**, and temporary-directory
  cleanup. No product code, fixture content, schema, migration, architecture,
  or ROADMAP semantics changed in this correction.
- Exit-gate disposition: the reviewed closure candidate satisfies the bounded
  Phase 2 exit-gate corrections. Phase 2 may be declared complete after this
  approved branch is merged into `main` and the normal post-merge checks pass.
  Tier 4 remains deliberately deferred and is not represented as implemented.
- Exact requested corrections: none.
- STOP — do not merge to `main` or begin Phase 3 until the user explicitly
  authorizes that action.

### Merge record

- Date: 2026-09-05. User authorized merging `phase-2/closure` into `main`
  following Codex's Approved re-review and Phase 2 exit-gate sign-off
  (commit `0ca367f`) above.
- Pre-merge state: `main` and `origin/main` both at `4db557c`; feature
  branch `phase-2/closure` pushed and clean at `0ca367f` (containing
  correction commit `cffe8a1`, correction commit `d09ac00`, and Codex's
  approval commit `0ca367f`).
- Merge: `git merge --no-ff phase-2/closure` on `main` — merge commit
  `d4bd606`. `git diff phase-2/closure HEAD` is empty (zero content
  difference); `git diff --check` and `check_repo.py` both exit 0; working
  tree clean.
- Post-merge verification: genuine external `python scripts/verify.py
  --level routine` (full run) — all **9 steps PASS** (Ruff format/check,
  mypy, `check_repo.py`, `git diff --check`, disposable-database URL/
  reachability, **1495 full-suite tests**, temp-directory cleanup).
  `alembic heads` confirms `0017` remains the sole head; `git diff --stat
  4db557c -- migrations/` is empty — no migration introduced by the merge.
  Dev database (`jobgoblin`) confirmed unchanged at the pre-existing `0006`
  — untouched throughout.
- Pushed: `main` at `d4bd606`, matching `origin/main`.
- Rollback boundary: to revert this slice, reset `main` to `4db557c` (the
  commit immediately before this merge) — this removes both new fixture
  pairs, the two fixture-driven identity tests in
  `test_ingestion_pipeline.py`, the ARCHITECTURE.md §11 wording correction,
  and the ROADMAP.md closure-candidate note cleanly, with no migration to
  reverse and no data written by this slice to any environment.
- **Phase 2 is officially complete.** Every documented Phase 2 requirement
  is satisfied, intentionally deferred with an approved architectural
  reason (Tier 4; `ProviderRegistry` production composition; live
  providers — none of these are Phase 2 exit criteria), or now closed by
  this branch; Codex's independent exit-gate review found no remaining
  blocker. Tier 4 remains explicitly deferred, not implemented.
- STOP — do not propose or begin Phase 3, live-provider integration,
  production `ProviderRegistry` composition, parallel/concurrent provider
  execution, the scheduler, API routes, or any migration without separate
  authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-06, Claude Code (Sonnet 5). Risk class R implementation
  of the approved Phase 3 remote-classifier proposal (v3 plus its binding
  implementation clarifications) on `phase-3/remote-classifier`, based on
  clean `main@199eb00`. This is the first Phase 3 parser slice — a bounded,
  pure-function proof of the parser pattern the remaining seven required
  parsers (title, salary, location, employment, seniority, experience,
  skill) will each follow in their own future slices. Not wired into
  ingestion/persistence, no `parser_version` threading, no `field_provenance`
  write, no other parser touched.
- Outcome:
  - **`app/normalization/types.py`** (new) — `Provenance` (`StrEnum`, the
    six-value docs/DATA_MODEL.md vocabulary exactly) and
    `NormalizationResult[T]` (frozen dataclass: one atomic `value`/
    `provenance` pair). `__post_init__` checks, in order: (1)
    `isinstance(provenance, Provenance)` — rejecting a raw string or
    unknown value with a fixed, categorical `ValueError` containing no
    interpolated runtime content, checked first specifically because a raw
    string sharing a real member's text (e.g. literal `"unavailable"`)
    would otherwise silently satisfy the invariant below without being a
    real member; (2) `value is None` iff `provenance is
    Provenance.UNAVAILABLE`, its own separate fixed categorical message.
    Documented as deliberately narrow to one atomic value — a future
    composite parser (salary, location) composes several independent
    `NormalizationResult`s or defines its own structured per-field result,
    never one shared provenance tag across sub-fields.
  - **`app/normalization/remote.py`** (new) — `classify_remote_type(title,
    description) -> NormalizationResult[Literal["remote","hybrid","onsite"]]`.
    Pipeline: NFKC-normalize, fold curly apostrophes to straight, case-fold;
    split into sentences on `. ; : ! ?`; tokenize each sentence on
    whitespace/`,()[]{}"/&-`/en-em-dash (apostrophe deliberately excluded,
    so contractions survive as one token; zero-width/format characters
    never stripped and never a boundary, so an obfuscated keyword fails
    closed rather than matching); catalog phrases compiled through the
    identical pipeline (`_compile_phrase`), never a hand-written parallel
    regex. Exclusion-span masking removes every token of a matched
    exclusion phrase (e.g. "remote sensing") from all later consideration,
    including the embedded "remote" token itself. Negation suppresses only
    the *nearest* candidate(s) to a cue within a 3-token same-sentence
    window (a tie suppresses both, never neither; a cue never suppresses
    every candidate in its window). Context-exclusion cues (e.g. "stipend")
    suppress *every* candidate in their own 3-token window. Cross-field
    precedence: any conflict anywhere (within one field or between fields)
    -> `(None, UNAVAILABLE)`; title-only -> `INFERRED`; description-only ->
    `PARSED_DESCRIPTION`; agreement -> `PARSED_DESCRIPTION`; no signal
    anywhere -> `(None, UNAVAILABLE)`. Catalogs are deliberately minimal and
    exhaustive for this slice (5 remote / 1 hybrid / 4 onsite phrases, 3
    exclusion phrases, 5 context cues, 6 negation cues) — an unsupported
    phrase (e.g. "telecommute") returns no signal, never a guess.
  - **`backend/tests/fixtures/normalization/remote_type_cases.json`** (new,
    27 cases) — every case labeled `synthetic_representative` or
    `synthetic_adversarial`; none claim `sanitized_capture`, since no real
    captured project text exists yet for this parser. Covers the full v3
    matrix plus every binding-clarification proof case: negation
    nearest-only (`"Not remote, onsite."` -> `onsite`), negation tie-break
    (`"Remote not onsite."` -> `unavailable`), straight- and
    curly-apostrophe contractions, the 3-token context-exclusion window,
    sentence-boundary-blocks-phrase-match, and the unsupported-phrase case.
  - **`backend/tests/test_normalization_types.py`** (new, 13 tests) —
    table-driven valid/invalid `(value, provenance)` pairs, including the
    present-value-with-raw-string case that would otherwise silently bypass
    the None invariant, each asserting the exact fixed error message.
  - **`backend/tests/test_normalization_remote.py`** (new, 30 tests) —
    corpus-driven (table-first, one parametrized test over the JSON file),
    plus an origin-honesty check, a determinism check (identical input ->
    bit-for-bit identical result twice — idempotence narrowed to this claim
    only, not "output fed back in as title is stable", which would not be a
    meaningful invariant for a free-text-in/enum-out function), and an
    AST-based import-boundary test proving neither new module imports
    `app.providers`/`app.db`/`app.ingestion`/`app.services`/`app.api`/
    `sqlalchemy`/`asyncpg`/`alembic`/`httpx`/`fastapi`.
  - **`docs/ARCHITECTURE.md`** §4 — added `remote.py`/`types.py` to the
    `normalization/` diagram (previously missing `remote.py` despite
    `remote_type` being a required Phase 3 parser and schema column).
    **`docs/ROADMAP.md`** — states the first Phase 3 slice is implemented
    on this branch, explicitly not a Phase 3 completion claim; the other
    seven parsers remain unstarted.
- Files changed: exactly the six files above plus this handoff entry. No
  `db/models/`, `ingestion/`, `providers/`, `services/`, `api/`, or
  migration file touched.
- A real bug was found and fixed during testing, before any commit: the
  initial context-exclusion cue list included the word "software", which
  incorrectly suppressed the "remote" signal in the extremely common title
  "Software Engineer (Remote)" — caught by the corpus's own
  `positive_punctuation_heavy`/`positive_unicode_fullwidth` cases failing.
  Narrowed the cue list to `stipend`/`collaboration`/`vpn`/`protocol`/
  `allowance` — words unambiguous in this context, rejecting
  `tool`/`tools`/`software`/`equipment`/`access` as too generic and
  title-collision-prone.
- Verification: `ruff format --check`, `ruff check`, `mypy` all pass on the
  four new files; the two targeted test modules directly (**43 passed**);
  genuine external `python scripts/verify.py --level routine` (full run) —
  all **9 steps PASS**, **1538 full-suite tests** (was 1495; +43),
  temp-directory cleanup, ~100-107s across reruns. `check_repo.py` and
  `git diff --check` both exit 0 standalone. No database/migration/schema
  touched by this slice at all (pure Python, no `--focus` needed since
  nothing here exercises PostgreSQL).
- Adversarial self-review (abbreviated, proportionate to Class R): four
  targeted breaks, each reverted cleanly (`git diff --stat` empty
  afterward) and each proven to fail the specific test(s) designed to
  catch it. (1) Disabled exclusion-span masking — the three
  `false_positive_remote_*` cases failed, each leaking an unmasked
  "remote" instead of `None`. (2) Reverted negation from
  nearest-candidate-only to suppress-every-candidate-in-window — exactly
  `negation_nearest_only_comma_onsite` failed (`"Not remote, onsite."`
  incorrectly became `unavailable` instead of `onsite`), while the other
  two negation cases were unaffected (correctly, since neither
  distinguishes the two behaviors). (3) Removed the `isinstance(provenance,
  Provenance)` guard — all three `test_non_enum_provenance_...` cases
  failed; critically, `NormalizationResult(value="remote",
  provenance="inferred")` (a raw string) then constructed with **no error
  at all**, proving this is exactly the invariant-bypass the guard exists
  to prevent. (4) Disabled sentence-splitting and additionally treated `.`
  as an ordinary token boundary (simulating a period treated as just
  another separator) — `sentence_boundary_prevents_cross_sentence_phrase_
  match` failed, with "on"/"site" now incorrectly combining across the
  removed boundary into a spurious "onsite" match that conflicted with the
  later "remote", producing `unavailable` instead of the expected clean
  `remote`.
- Deviations/known limitations: the pre-existing `alembic check`
  substitution (unrelated, recorded previously, and not applicable here
  since no schema/migration was touched). The documented, accepted
  negation-window limitation (a negator more than 3 tokens from its target
  is not recognized) — stated in `remote.py`'s own module docstring, not
  silently handled.
- STOP — awaiting Codex review. Do not merge, begin another Phase 3 parser,
  wire into ingestion/persistence, contact providers, or create a migration.
