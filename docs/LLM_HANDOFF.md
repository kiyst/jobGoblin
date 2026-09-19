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

- Date/agent: 2026-09-18, Claude Code (Sonnet 5). Risk class H
  (process/security-relevant tooling, same category as every prior
  Workflow v3.2 tooling slice). Base `B` -> candidate `C`:
  `27a2a5e2cf81b2e347d1fa19012822fe1f0b6198` -> this commit; new branch
  `tooling/workflow-v3.2-post-merge-q-producer`, cut from `main` after a
  freshly verified clean checkout (`main` == `origin/main`, `check_repo.py`
  clean, `git diff --check` clean). `slice_kind: tooling`.
  `slice_id: 2026-09-18-post-merge-q-producer-27a2a5e`. Implements the
  bounded, proposal-reviewed "post-merge `Q`-evidence producer" slice:
  Workflow v3.2's `C -> A -> R -> M -> Q` chain had a validator for `Q`
  (`check_review.validate_q`/`validate_published`) but no producer at
  all until this slice.
- **Producer:** `verification_coordinator.run_post_merge_verification`,
  taking a new `PostMergeEligibleRequest` (only the five chain commit
  SHAs -- `candidate_sha`, `publication_sha`, `review_sha`, `merge_sha`,
  `expected_first_parent` -- no `base_sha`/`slice_id`/receipt-reference
  field for a caller to forge). Every one of those values is instead
  derived from `check_review.validate_c_a_r_chain`'s own independently
  re-validated chain output, before any worktree is created. The
  migration trigger is computed over that same chain-derived
  `base_sha..candidate_sha` range -- never a caller-supplied range and
  never `base_sha..merge_sha` -- so nothing external can suppress a
  genuine migration requirement. Verification runs in a disposable
  detached worktree at `M` (always full/final, never gated or
  focus-narrowed), reusing the receipt producer's own worktree/lock/
  cache-cleanup lifecycle under its own `post-merge-coordinator-`
  run-directory prefix. Emission is explicitly fail-closed: a failed
  verification run, a cleanup failure, or an artifact that would fail
  its own self-validation (`check_review._validate_post_merge_artifact_
  schema`/`_validate_post_merge_artifact_evidence`, called before the
  write) all produce *no file at all* -- a deliberate divergence from
  the existing receipt producer, which does write a receipt marked
  `approval_eligible: false` on a failed run. The function only ever
  writes the artifact file; committing `Q` (bundling that file with the
  append-only merge-record edit to the handoff, per the mainline-`Q`-
  next policy in `LLM_WORKFLOW.md`) remains a separate step.
- **Cleanup-prefix fix:** `cleanup_stale_coordinator_dirs` is now
  parameterized (`prefix: str = "coordinator-"`), restricted to a closed
  set of exactly two known prefixes (`"coordinator-"`,
  `"post-merge-coordinator-"`); an unrecognized prefix (including an
  empty string, which would otherwise match every directory) is rejected
  before any directory is ever scanned.
- **Release-sequence guard:** new `confirm_main_unchanged(expected_sha)`
  re-fetches `origin/main` and refuses if it no longer equals
  `expected_sha` -- run immediately before pushing a locally-prepared
  `M`/`Q` together, so a remote that advanced in the meantime is caught
  before the push rather than raced against.
- **Adversarial self-review** (fresh subagent, full twelve-question
  pass; see `LLM_WORKFLOW.md`'s "Adversarial implementer self-review"):
  no Critical/High findings. Confirmed clean, with concrete evidence:
  the stage-1/2 pre-flight (`validate_c_a_r_chain`/`validate_merge`)
  genuinely runs before any worktree is created on every path; every
  raise point between the worktree stage and the artifact write is an
  unguarded `raise` with no exception-swallowing; `base_sha` is assigned
  exactly once, from the chain-derived `published_base_sha`, with no
  other path into the migration decision; the prefix-rejection in
  `cleanup_stale_coordinator_dirs` is the function's literal first
  statement; there is no TOCTOU window since `A`/`R` content is read
  from immutable commit objects and `M`'s worktree is independently
  snapshotted before/after. Three Medium findings (test-rigor gaps, not
  implementation defects) were fixed in response: two rejection tests
  now also assert a worktree-creation guard (proving *when* rejection
  happens, not just *that* it does, since `.verify-tmp` absence alone
  couldn't distinguish "never created" from "created and cleaned up");
  the success and verify-invocation-failure tests now assert
  `.verify-tmp` is clean (empty or absent) directly, since it is
  gitignored and `git status` is blind to it; and a new regression
  (`test_post_merge_verification_writes_no_artifact_when_self_
  validation_fails`) proves the artifact's own self-validation gate --
  not just the `returncode`/`all_passed` check -- independently blocks
  emission, using a stand-in `verify.py` that mis-reports `all_passed:
  true` while silently omitting a required step. Three Low findings
  were reviewed and accepted as pre-existing, informational, and out of
  this slice's bounded scope (see Deviations below), not fixed here.
- **Documentation (the three proposal-approved addenda):** `docs/
  DECISIONS/0009-workflow-v3.2-activation.md` gains "Post-merge
  evidence: one-time bootstrap exception for M = 9649cba" (the corrected
  explanation: a conforming `Q` remains constructible on a sibling
  branch at any time, since Git places no limit on a commit's children
  -- what is actually foreclosed is only `main`'s own already-pushed
  linear continuation from `M`; the reason is procedural, not technical,
  since `M`'s own tree already contained the `Q` tooling; the
  preserved evidence is reported and rerunnable, not "independently
  reproducible from Git") and "Post-merge (`Q`) evidence producer"
  (describing this slice's implementation). `docs/LLM_WORKFLOW.md` gains
  "Post-merge (`Q`) evidence producer" and "Project policy: `Q` is the
  next mainline commit after `M`" (explicitly framed as this project's
  own policy choice, not a `validate_q` requirement; a precondition --
  an approved producer or evidence-capture procedure must exist *before*
  merge authorization, not after; the mainline-shape rule; a fail-closed
  stop-at-`M` rule if post-merge verification or `Q` validation ever
  fails; and the release sequence tying `confirm_main_unchanged` into
  the push step). This handoff gains the "Post-merge evidence status"
  pointer note on the prior Merge record entry (above) and this Work
  done entry itself.
- Files changed: `backend/scripts/verification_coordinator.py` (edited);
  `backend/tests/test_verification_coordinator_post_merge.py` (new, 16
  tests); `docs/DECISIONS/0009-workflow-v3.2-activation.md` (edited);
  `docs/LLM_WORKFLOW.md` (edited); `docs/LLM_HANDOFF.md` (this entry,
  the prior entry's pointer note, and the two-iteration rotation below).
  No production parser (`app/normalization/*`), model, migration, or
  live-provider file touched; no database lifecycle operation performed.
- **Two-iteration rotation applied**: the oldest iteration (the Slice 2
  contract-harness bounded-correction pass, already merged) is deleted;
  the former Iteration 2 (the original v3.2 activation candidate/review
  cycle) and Iteration 3 (the C7-C10 correction saga plus the merge
  record) are renumbered to Iteration 1 and Iteration 2 respectively,
  with every in-prose cross-reference to the renumbered iteration
  updated to match; this entry becomes the new Iteration 3.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (159
  source files, backend + `.claude/hooks`). Full pytest suite: **2663
  passed**. All 34 mutation witnesses pass unmodified. `check_repo.py`
  exits 0. `git diff --check` clean.
- Deviations/known limitations (all reviewed, accepted, non-blocking):
  (1) on a worktree-removal failure, cleanup still deletes the physical
  worktree directory without `git worktree remove`/`prune`, which can
  leave a dangling `.git/worktrees/<id>` metadata entry -- inherited,
  byte-identical behavior from the existing `run_receipt_eligible_
  verification`, not introduced or changed by this slice; (2)
  `cleanup_stale_coordinator_dirs` cannot detect or repair that kind of
  leak, since it only scans `COORDINATOR_RUN_ROOT`, never `git worktree
  list` -- same shared, pre-existing limitation; (3) no dedup/lock scopes
  a given `merge_sha` itself, so two concurrent producer runs against the
  same `M` could both succeed and coexist as separate untracked artifact
  files under `docs/post-merge/<merge_sha>/` -- harmless in practice,
  since `validate_q` requires exactly one *committed* artifact addition,
  and the actual choice of which artifact becomes `Q` is made at commit
  time, not by the producer.
- STOP — this is a bounded tooling slice only. Do not author `R`, merge,
  create a real `M`/`Q` for this slice or retroactively for `M =
  9649cba`, begin another slice, rebase, or force-push.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-18-post-merge-q-producer-27a2a5e
slice_kind: tooling
risk_class: H
base_sha: 27a2a5e2cf81b2e347d1fa19012822fe1f0b6198
declared_gate: final
executed_gate: final
candidate_sha: 3397e1d37a558b9e714c5970ed66f4d98989e7b6
receipt_id: a78ee96c-ee63-4e70-9269-4d8f52874371
receipt_path: docs/verification-receipts/3397e1d37a558b9e714c5970ed66f4d98989e7b6/a78ee96c-ee63-4e70-9269-4d8f52874371.json
full_suite_count: 2663
focused_test_count: 16
mutation_witness_count: 34
```

### Work review

- Sol's review of `C` = `3397e1d37a558b9e714c5970ed66f4d98989e7b6` and
  `A` = `a7f53f80366de4699fe152c399c752cf05fe7f9e`: **Approved, no
  executable findings.** Independent verification performed: ran all 16
  new post-merge-`Q`-producer tests; validated the committed `C..A`
  transition and receipt (`approval_eligible` recomputes to `true`);
  confirmed `check_repo.py` and `git diff --check` pass; confirmed the
  branch is clean and synchronized. The full 2,663-test suite was not
  independently re-run.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-18-post-merge-q-producer-27a2a5e
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-18T00:00:00Z
candidate_sha: 3397e1d37a558b9e714c5970ed66f4d98989e7b6
publication_commit_sha: a7f53f80366de4699fe152c399c752cf05fe7f9e
receipt_path: docs/verification-receipts/3397e1d37a558b9e714c5970ed66f4d98989e7b6/a78ee96c-ee63-4e70-9269-4d8f52874371.json
receipt_id: a78ee96c-ee63-4e70-9269-4d8f52874371
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-18. Merged `tooling/workflow-v3.2-post-merge-q-producer`
  at approved, reviewed commit `2635ffc608c20526c3ee7e5e12c7411c003ad5f5`
  (Sol's "Approved, no executable findings" verdict on `C`/`A`, above)
  into `main` via `git merge --no-ff`. Merge commit:
  `c33accdadd54fab756e8f4aef5be6a86123e148b`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `27a2a5e2cf81b2e347d1fa19012822fe1f0b6198`.
- Pre-merge checks: confirmed the feature branch and its origin both sat
  at `2635ffc`, and `main`/`origin/main` were both clean and
  synchronized at `27a2a5e` before merging.
- **This is the first merge to follow the documented `M -> Q` release
  sequence** (`LLM_WORKFLOW.md`'s "Project policy: `Q` is the next
  mainline commit after `M`"): `M` was created locally, not pushed;
  `verification_coordinator.run_post_merge_verification` was run
  against `M` in a disposable detached worktree (always full/final);
  its resulting artifact
  (`docs/post-merge/c33accdadd54fab756e8f4aef5be6a86123e148b/
  d1accc51-726b-4011-a41a-d24e4e12baaa.json`) reported all 11 steps
  PASS, 2,663 full-suite tests, 34/34 mutation witnesses, and an
  identical tracked-tree SHA before and after (zero content drift); this
  commit (`Q`) bundles that artifact addition with this merge-record
  append, as the single commit immediately following `M` on `main`'s
  mainline — never a merge-record-only commit.
- Post-merge verification, all run directly against merged `main`
  (independent of the `Q` producer's own run above):
  - `git diff --quiet 2635ffc HEAD` — zero content difference between
    merged `main` and the approved feature-branch tip, confirmed.
  - `git diff --check` — clean.
  - `python -m scripts.check_repo` — clean.
  - No migration/schema changes: `git diff --stat 27a2a5e..HEAD --
    backend/alembic backend/migrations` and `git log --oneline
    27a2a5e..HEAD -- backend/alembic backend/migrations` both empty.
  - `check_review.validate_published(C, A, R, M, Q)` — **succeeds**,
    returning the independently re-validated artifact, confirming the
    complete `C -> A -> R -> M -> Q` chain.
- STOP — report the synchronized final `main` SHA and stop. No Slice 3,
  no other Phase 3/4 parser, no other new slice, without separate
  explicit user authorization.

---

## Iteration 2

### Work done

- Date/agent: 2026-09-18, Claude Code (Sonnet 5). Risk class **H**
  (deliberately, not the R this project's own review discipline might
  default to for a pure-function, no-DB/network slice: ambiguous-alias
  false matches are Phase 3's own named primary risk — "confidently
  storing false facts from ambiguous text" — and this is novel,
  foundational infrastructure two future parsers depend on for
  correctness, not a "repeated established pattern"). Base `B` ->
  candidate `C`: `21dee74bae122bc634c77d3d0c55d03be128b716` -> this
  commit; new branch `phase-3/skill-taxonomy-foundation`, cut from a
  freshly verified clean `main` (`main` == `origin/main`, `check_repo.py`
  clean, `git diff --check` clean). `slice_kind: tooling` (not `parser`:
  `check_handoff.py` requires `slice_kind: parser` to declare a
  `fixture_path`/`fixture_count` pointing at a single JSON-array
  regression corpus, the classic classifier-fixture pattern the six
  merged parsers each use — this slice is deliberately not itself a
  classifier, so that shape doesn't fit; its own fault-injection
  fixtures are individual YAML files exercised via `pytest.mark.
  parametrize`, not one JSON corpus. The future `classify_skill` parser
  that consumes this taxonomy is the correct place for `slice_kind:
  parser` and a real fixture corpus). `slice_id:
  2026-09-18-skill-taxonomy-foundation-21dee74`. Implements the
  three-round-negotiated, user-approved skill-taxonomy-foundation
  proposal and its amendments.
- **Schema, grammar, and typed result** (`backend/app/normalization/
  taxonomy.py`, `backend/app/taxonomy/skills.yaml`): `skills.yaml` has
  exactly two top-level keys (`schema_version: 1`, `entries`); each entry
  has exactly three keys (`canonical_id`, `display_name`, `aliases`).
  `canonical_id` reuses `app.schemas.identifiers.is_canonical_slug()`
  verbatim — the same grammar already enforced on every `provider`/
  `source` column — never a new regex. `TaxonomyLookupResult` is a new,
  dedicated type (`status: TaxonomyLookupStatus` paired with
  `entry: TaxonomyEntry | None`, invariant-enforced in `__post_init__`
  exactly like `NormalizationResult`'s own value/provenance invariant,
  two static factories as the only construction path) — deliberately
  not a reuse of `NormalizationResult`/`Provenance`, since taxonomy-
  resolution success is orthogonal to a parser's own input-provenance
  trust level.
- **YAML safety**: no YAML library existed in this repo before this
  slice (confirmed by direct search). Adds `PyYAML==6.0.3` (pinned
  exactly like the existing `idna==3.19` precedent) to
  `backend/pyproject.toml`, plus a `yaml.*` mypy override (PyYAML ships
  no type stubs, same treatment as the existing `asyncpg.*` override).
  `yaml.safe_load` alone does not reject a duplicate YAML mapping key
  (silent last-write-wins) — `_StrictYamlLoader(yaml.SafeLoader)`
  overrides `construct_mapping` to raise instead, mirroring this
  project's own `verification_receipts._StrictDecoder` (JSON) duplicate-
  key rejection.
- **Lookup normalization** (precisely defined, not borrowed): checked
  `location.py`/`salary.py` directly rather than assume a shared
  convention — they share only NFKC-normalize + strip the project's
  `_WHITESPACE` set before diverging into field-specific casing
  (location/salary each uppercase some fields, lowercase others, per
  field). This taxonomy defines its own rule:
  NFKC-normalize -> strip `_WHITESPACE` -> collapse repeated internal
  whitespace -> lowercase-fold. Punctuation (`+`, `#`, `.`, `-`) is
  preserved literally (`c` vs `c++` vs `c#` must stay distinct).
  Whitespace adjacent to punctuation is not reconciled — a stated
  limitation, not an oversight.
- **Collision rejection**: both `canonical_id` and every alias become
  lookup keys, inserted into one flat global `normalized_key -> entry`
  index. Any collision — cross-entry, or two of the same entry's own
  keys (including an alias equal to its own entry's `canonical_id`) —
  is rejected at load time, no first/last-wins. A load-time check also
  requires `normalize(display_name)` be reachable via the entry's own
  `canonical_id` or an alias (rejecting an entry unreachable by its own
  display name).
- **Frozen seed** (15 entries, explicitly reduced from an earlier
  ~40-60 estimate to keep this a genuine foundation slice, not a
  vocabulary attempt): `python`, `javascript`(`js`), `typescript`(`ts`),
  `java`, `cpp`(`c++`,`cplusplus`), `csharp`(`c#`,`c-sharp`), `c`,
  `golang`(`go`), `rlang`(`r`), `postgresql`(`postgres`), `mysql`,
  `mongodb`(`mongo`), `kubernetes`(`k8s`), `docker`, `node.js`
  (`node`,`nodejs`). Every alias individually justified (see the
  slice's proposal record for the full rationale table); ambiguous
  near-misses deliberately excluded or kept unaliased (`c`/`cpp`/
  `csharp` never alias to each other; `java`/`javascript` never alias to
  each other; `postgres` included but `psql` deliberately excluded, since
  that names the CLI client, not the database skill).
- **Exact-match only, by design**: `TaxonomyIndex.lookup()` never
  tokenizes or scans a larger string — proven by a dedicated test
  feeding a full sentence and asserting `UNKNOWN`, alongside the same
  token resolving correctly on its own. No free-text scanning, no
  skill classifier, implemented in this slice.
- **Unblocks skill, not title**: a future `classify_skill` parser calls
  this lookup per already-segmented token and wraps results in its own
  `NormalizationResult[list[str]]`. Title is **not** unblocked — job
  titles are free-form multi-word phrases needing a different, likely
  hierarchical taxonomy schema, their own seed-sourcing rule, and a
  phrase/segment-extraction normalization approach; only the general
  pattern (versioned, duplicate-rejecting, schema-validated YAML with a
  typed unknown result) is a reusable template, never this schema or
  data directly.
- **Documentation corrections, kept bounded to exactly the identified
  stale passages**: `docs/ROADMAP.md`'s Phase 3 status text incorrectly
  claimed the location classifier was "not merged, not complete" —
  independently verified via `git log`/`git show` that it merged at
  `a32b5cc` (approval `c1a5235`) and is a genuine ancestor of `main`;
  corrected, and this slice's own status recorded alongside it.
  `docs/ARCHITECTURE.md`'s identical duplicate of the same stale claim
  (it explicitly deferred to ROADMAP and inherited the staleness) is
  also corrected; `taxonomy.py`/`skills.yaml` marked implemented
  (candidate/publication stage); `titles.py`/`skills.py`/`titles.yaml`/
  `industries.yaml`/`aliases.yaml` explicitly left as still-planned, not
  touched further.
- **Adversarial self-review** (fresh subagent; DB/ORM/concurrency
  questions from `LLM_WORKFLOW.md`'s twelve-question pass explicitly
  marked not-applicable, confirmed by the import-boundary test and by
  direct inspection of this module's import list). No Critical/High
  findings. One Medium finding fixed: `TaxonomyIndex`'s "immutable"
  claim was asserted but not enforced — `@dataclass(frozen=True)` only
  blocks rebinding the `_by_normalized_key` attribute, never in-place
  mutation of the `dict` it pointed to (reproduced: assigning into the
  dict directly silently corrupted a lookup). Fixed: `__post_init__` now
  defensively copies the caller's mapping into a `MappingProxyType`, so
  neither the constructor's caller nor any other holder of a reference
  can mutate the index post-construction — proven by two new regressions
  (direct in-place assignment now raises `TypeError`; mutating the
  caller's own source dict after construction no longer affects the
  index, proving a copy was made, not merely a wrap). One Low finding
  fixed: a blank-after-whitespace-strip alias lacked a dedicated test
  (behavior was already correct — added the missing regression). One
  Low/informational finding (an NBSP-only `display_name` is still
  correctly rejected, just under the "not reachable" message rather than
  "blank") left as-is — fails closed either way, a message-clarity nit
  only.
- **Real gap found by the tooling's own fail-closed design, not a review
  finding**: `verification_scope.classify_path` correctly refused to
  classify the 12 new non-Python YAML fixture files under
  `backend/tests/fixtures/taxonomy/` (`OwnerMappingRequiredError` —
  "no declared exact rule"), exactly as it's designed to for any
  unmapped non-`.py` path under `backend/tests/`. A new directory
  prefix was not an option (the two existing prefix rules must stay
  disjoint); added a new exact-path map, `_TAXONOMY_FIXTURE_FILES`
  (all 12 files -> `"test-fixture:skill-taxonomy"`), wired into the
  same validation/lookup path `_RECORD_FILES` already uses. Confirmed
  this new category never spuriously requires contract-family/guard
  coverage (`required_contract_families` only recognizes `parser`/
  `adapter`/`contract-record` kinds against location/salary/
  experience). 4 new regressions added, including a complete-inventory
  check (every file actually present in the fixtures directory, not
  just samples).
- Files changed: `backend/app/normalization/taxonomy.py` (new);
  `backend/app/taxonomy/skills.yaml` (new); `backend/tests/
  test_normalization_taxonomy.py` (new, 63 tests);
  `backend/scripts/verification_scope.py`,
  `backend/tests/test_verification_scope.py` (edited, 4 new tests —
  see the fixture-classification gap above); `backend/tests/
  fixtures/taxonomy/*.yaml` (new, 12 fixtures: 11 fault-injection, 1
  positive control);
  `backend/pyproject.toml` (edited — `PyYAML==6.0.3` pin, `yaml.*` mypy
  override); `docs/ROADMAP.md`, `docs/ARCHITECTURE.md` (edited, bounded
  stale-passage corrections only); `docs/LLM_HANDOFF.md` (this entry,
  plus the two-iteration rotation below). No production parser other
  than this new module touched; no migration/model/service/API file
  touched; no database lifecycle operation performed; no provider
  contact of any kind.
- **Two-iteration rotation applied**: the oldest iteration (the original
  v3.2 activation candidate/review cycle, C1-C6) is deleted; its two
  remaining internal cross-references from the newer iteration (which
  had read "Iteration 1" as a pointer to it) were first rewritten as
  self-contained prose naming the actual work directly, so they do not
  dangle after deletion. The former Iteration 2 (the C7-C10 correction
  saga, merge record, and post-merge-evidence-status note) and
  Iteration 3 (the Q-producer slice's Work done/review/merge
  record/`Q` publication) are renumbered to Iteration 1 and Iteration 2
  respectively; this entry becomes the new Iteration 3.
- Verification: `ruff format --check`/`ruff check`/`mypy` clean (161
  source files, backend + `.claude/hooks`). Full pytest suite: **2730
  passed** (2663 + 63 taxonomy + 4 scope). All 34 mutation witnesses
  pass unmodified. `check_repo.py` exits 0. `git diff --check` clean.
  Genuine external `python -m scripts.verify --level routine
  --compat-v3.1`: all 10 checks PASS.
- Deviations/known limitations: none beyond what the proposal itself
  already disclosed (a small, explicitly non-exhaustive 15-entry seed;
  the Go/R exact-match positive controls are documented as not
  guaranteeing a future classifier's word-boundary safety), plus the
  informational display-name-blank-message nit noted above.
- STOP — this is a bounded parser-foundation slice only. Do not author
  `R`, merge, create `Q`, or begin any title-parser work without
  separate explicit user authorization.

#### Correction round 1 (Sol review of C/A: 4 bounded findings)

- **Supersedes candidate `C` = `138f68d8aee7931662877c9971e85ecd51ffa0c9`
  and publication `A` = `639f9b4f99635f8de0458be49e0122dc939c7fa2`.** The
  receipt published there
  (`docs/verification-receipts/138f68d8aee7931662877c9971e85ecd51ffa0c9/
  d4b54862-f2f1-425e-b12b-5636653259db.json`) is **not reusable** and is
  superseded by this correction round's own fresh candidate/publication
  cycle below. `C`/`A` are preserved unamended, never rewritten.
- **Finding 1 (strict `schema_version`)**: `bool` is an `int` subclass
  and `True == 1` in Python — the prior `!= _SUPPORTED_SCHEMA_VERSION`
  comparison silently accepted `schema_version: true`. Fixed:
  `load_taxonomy` now explicitly rejects any `schema_version` that is
  not a genuine, non-`bool` `int` equal to `1`, mirroring this
  project's own `verification_receipts._require_positive_int`. New
  fixture `schema_version_boolean_true.yaml` + regression proves it.
- **Finding 2 (`_StrictYamlLoader` unhashable-key safety)**: YAML's
  explicit `? ... : ...` syntax permits a non-scalar (sequence/mapping)
  mapping key, which is unhashable — `key in seen` would previously
  raise a raw `TypeError`, escaping this module's own closed
  `TaxonomyValidationError`. Fixed: the membership check is now wrapped
  in `try/except TypeError`, re-raising as `TaxonomyValidationError`.
  New fixture `sequence_mapping_key.yaml` + regression proves it.
- **Finding 3 (fixture-inventory test didn't discover anything)**:
  `test_every_taxonomy_fixture_file_is_mapped_never_owner_mapping_
  required` only iterated the already-declared `verification_scope.
  _TAXONOMY_FIXTURE_FILES` dict's own keys — it could never have caught
  a fixture file added to disk but never added to that dict (or vice
  versa). Fixed: it now genuinely enumerates `backend/tests/fixtures/
  taxonomy/*.yaml` on disk and asserts exact-set equality against the
  dict's keys, not merely that the dict's own declared entries resolve.
  `_TAXONOMY_FIXTURE_FILES` is updated to include the two new fixtures
  from findings 1/2, which this stricter test now requires.
- **Finding 4 (honest deviation reconciliation, not a "no deviations"
  claim)**:
  - `PyYAML==6.0.3` vs. the proposal's approved `6.0.2`: this was a
    real, unflagged deviation, not a necessary one — `6.0.2` is still
    published and installs cleanly on this exact Python 3.12/Windows
    environment (`pip install PyYAML==6.0.2` succeeds via a prebuilt
    wheel, verified). The original implementation simply pinned
    whatever was already present in the `.venv` rather than the
    literal approved version. **Corrected**: downgraded to
    `PyYAML==6.0.2` in `backend/pyproject.toml`, matching the approved
    proposal exactly; the full taxonomy suite re-passes under it.
  - `slice_kind: tooling` vs. the proposal's `parser`: this remains a
    genuine, deliberate deviation from the proposal's literal text, but
    one this correction round judges **necessary, not avoidable**, and
    is surfacing explicitly rather than deciding silently: `check_
    handoff.py`'s schema requires `slice_kind: parser` to declare a
    `fixture_path`/`fixture_count` pointing at exactly one JSON-array
    regression corpus — the classic classifier input/expected-output
    pattern the six merged parsers each use. This slice's own fixtures
    are deliberately individual malformed-YAML fault-injection files
    (proving loader validation, not classifier behavior), not one JSON
    corpus, and the proposal itself repeatedly emphasized this slice is
    *not* a classifier. Satisfying `parser`'s schema requirement would
    mean either fabricating a `fixture_path` that misrepresents what
    this slice actually is, or restructuring its real fixtures into an
    artificial JSON-array shape solely to satisfy the label — both
    changes to the approved contract's substance, not bookkeeping. This
    was already applied as its own separate commit
    (`0f22516`) with the same reasoning recorded in its own commit
    message; restated here in full per this correction's explicit
    request rather than left implicit. If Sol judges this
    classification itself still requires the user's separate
    authorization (as opposed to a self-directed correction, the way
    the two earlier self-found tooling defects in this project's
    history were always escalated before being folded into scope),
    that should be raised as its own finding rather than assumed
    settled by this entry.
- Files changed (this correction only):
  `backend/app/normalization/taxonomy.py`,
  `backend/scripts/verification_scope.py`,
  `backend/tests/test_normalization_taxonomy.py`,
  `backend/tests/test_verification_scope.py`,
  `backend/pyproject.toml` (all edited); `backend/tests/fixtures/
  taxonomy/{schema_version_boolean_true,sequence_mapping_key}.yaml`
  (new). No skill classifier, no title-parser work, no other production
  file touched.
- Verification (this correction round): `ruff format --check`/
  `ruff check`/`mypy` clean (161 source files, backend + `.claude/
  hooks`). Full pytest suite: **2732 passed** (2730 + 2 new). All 34
  mutation witnesses pass unmodified. `check_repo.py` exits 0.
  `git diff --check` clean.
- STOP — this is a bounded correction only. Do not author `R`, merge,
  create `Q`, implement the skill classifier, or begin title work.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-18-skill-taxonomy-foundation-21dee74
slice_kind: tooling
risk_class: H
base_sha: 21dee74bae122bc634c77d3d0c55d03be128b716
declared_gate: final
executed_gate: final
candidate_sha: c08e89d3fe073ac34cada82e52df3710cb9e2c3d
receipt_id: 2231dafb-4057-4b1b-9c86-f51780a18907
receipt_path: docs/verification-receipts/c08e89d3fe073ac34cada82e52df3710cb9e2c3d/2231dafb-4057-4b1b-9c86-f51780a18907.json
full_suite_count: 2732
focused_test_count: 131
mutation_witness_count: 34
```

### Work review

- Sol's review of `C2` = `c08e89d3fe073ac34cada82e52df3710cb9e2c3d` and
  `A2` = `f652b5d1fd32fabaeaccc80fa6aa83891c32e4cb`: **Approved, no
  executable findings.** Independent verification performed: confirmed
  all three bounded corrections (strict `schema_version`,
  `_StrictYamlLoader` unhashable-key handling, the genuinely-discovering
  fixture-inventory test) are closed; ran 131 focused tests, passing;
  validated the `C2..A2` transition and receipt; recomputed
  `approval_eligible: true`; confirmed `check_repo.py` and
  `git diff --check` pass. Sol accepts `slice_kind: tooling` as the
  appropriate, necessary deviation from the proposal's `parser` label —
  this is executable taxonomy-foundation infrastructure, not a
  classifier with the JSON-array fixture corpus `slice_kind: parser`
  requires; risk class `H` and the `final` gate remain unchanged. The
  full 2,732-test suite and the 34 mutation witnesses were not
  independently re-run. Disclosed: the first focused-test launch hit a
  transient Pydantic startup `MemoryError`; a fresh-process retry passed
  131/131, and that retry's result is what this verdict relies on.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-09-18-skill-taxonomy-foundation-21dee74
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-09-19T00:00:00Z
candidate_sha: c08e89d3fe073ac34cada82e52df3710cb9e2c3d
publication_commit_sha: f652b5d1fd32fabaeaccc80fa6aa83891c32e4cb
receipt_path: docs/verification-receipts/c08e89d3fe073ac34cada82e52df3710cb9e2c3d/2231dafb-4057-4b1b-9c86-f51780a18907.json
receipt_id: 2231dafb-4057-4b1b-9c86-f51780a18907
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-09-19. Merged `phase-3/skill-taxonomy-foundation` at
  approved, reviewed commit `ab6d27d300e81e76049d54623c3efea12bebebb4`
  (Sol's "Approved, no executable findings" verdict on `C2`/`A2`,
  above) into `main` via `git merge --no-ff`. Merge commit:
  `1876f7e2168d90e36a1fb46f039cd5969fe49d6c`. Pre-merge `main`/
  `origin/main` tip (rollback boundary):
  `21dee74bae122bc634c77d3d0c55d03be128b716`.
- Pre-merge checks: confirmed the feature branch and its origin both sat
  at `ab6d27d`, and `main`/`origin/main` were both clean and
  synchronized at `21dee74` before merging; re-confirmed
  `check_merge_eligibility(C2, A2, R)` still returned `approved`
  immediately beforehand.
- Followed the documented `M -> Q` release sequence
  (`LLM_WORKFLOW.md`'s "Project policy: `Q` is the next mainline commit
  after `M`"): `M` was created locally, not pushed; zero content
  difference between `M` and `R` confirmed
  (`git diff --quiet ab6d27d HEAD`);
  `verification_coordinator.run_post_merge_verification` was run
  against `M` in a disposable detached worktree (always full/final);
  its artifact
  (`docs/post-merge/1876f7e2168d90e36a1fb46f039cd5969fe49d6c/
  73f4500a-f122-4b0b-9019-75a631a40289.json`) reported all 11 steps
  PASS, 2,732 full-suite tests, 34/34 mutation witnesses, and an
  identical tracked-tree SHA before and after; this commit (`Q`)
  bundles that artifact addition with this merge-record append, as the
  single commit immediately following `M` on `main`'s mainline — never
  a merge-record-only commit.
- Post-merge verification, all run directly against merged `main`
  (independent of the `Q` producer's own run above):
  - `git diff --quiet ab6d27d HEAD` — zero content difference between
    merged `main` and the approved feature-branch tip, confirmed.
  - `git diff --check` — clean.
  - `python -m scripts.check_repo` — clean.
  - No migration/schema changes: `git diff --stat 21dee74..HEAD --
    backend/alembic backend/migrations` and `git log --oneline
    21dee74..HEAD -- backend/alembic backend/migrations` both empty.
  - `check_review.validate_published(C2, A2, R, M, Q)` — **succeeds**,
    returning the independently re-validated artifact, confirming the
    complete `C2 -> A2 -> R -> M -> Q` chain.
  - `verification_coordinator.confirm_main_unchanged` — run immediately
    before push, confirmed `origin/main` still equaled the pre-merge
    tip.
- STOP — report the synchronized final `main` SHA and stop. No skill
  classifier, no title-parser work, no other new slice, without
  separate explicit user authorization.

---

## Iteration 3

### Work done

- Date/agent: 2026-09-19, Claude Code (Sonnet 5). Risk class **H** (same
  primary-risk reasoning as the taxonomy-foundation slice: ambiguous-alias
  false matches are Phase 3's own named risk, and this is the first
  classifier consuming that taxonomy). Base `B` -> candidate `C`:
  `d0159a4cc0faf9fb13f30ea814fa2e6c204570bb` -> this commit; new branch
  `phase-3/skill-classifier`, cut from a freshly verified clean `main`
  (`main` == `origin/main`, both at `d0159a4`). `slice_kind: parser` (unlike
  the taxonomy foundation: this slice owns a genuine single JSON-array
  fixture corpus, the classic classifier-fixture shape). `slice_id:
  2026-09-19-skill-classifier-d0159a4`. Implements the four-round-negotiated,
  user-approved `classify_skills` proposal and its amendments in full.
- **Classifier** (`backend/app/normalization/skills.py`):
  `classify_skills(title, description, *, taxonomy) -> list[SkillMatch]`.
  One shared segment/token grammar (`[,;|:/]` then
  `[^\s()\[\]{}"&]+`, hyphen/`+`/`#`/`.` preserved); a single-vs-doubled
  trailing-punctuation rule (`.`/`!`/`?`); the ambiguous keys `c`/`r`/`go`/
  `node` require standalone-in-segment (title) or a narrow role-noun
  adjacency for `c`/`r`/`go` only (title), or an explicit anchor-bounded
  region (description) — never punctuation structure alone. The
  description anchor grammar (`skills:`/`languages:`/`technologies:`/
  `tech stack:`) is ASCII-literal and covered-whitespace-exact (no `\s`,
  no `re.IGNORECASE`, no `.lower()`), valid only at start-of-field,
  start-of-line, or immediately after a genuine sentence terminator; a
  region's end is a terminator's own `Pattern.end()` (Python's exclusive
  slice convention), inclusive of the whole punctuation run, so the
  existing single-vs-doubled rule remains the only thing deciding
  match/no-match once a token is extracted. `SkillMatch.__post_init__`
  revalidates `canonical_id` against `is_canonical_slug()` and
  `display_name` against this module's own covered-whitespace class,
  never a bare truthiness check; `provenance` must be a genuine
  `Provenance` member. Every error message is fixed and categorical.
  Exact-match taxonomy lookup only — no taxonomy growth, no persistence,
  no `parser_version`.
- **Fixtures and tests**: `backend/tests/fixtures/normalization/
  skill_cases.json` (61 cases, each isolating one mechanism — tokenizer
  boundaries, the `node`/`c`/`r`/`go` ambiguity rule, the title
  role-noun-adjacency rule and its three counterexamples, terminal
  punctuation and its malformed-run negatives, the anchor grammar's three
  start conditions and two Unicode no-break-space negatives (before and
  after the colon — see the adversarial finding below), region
  termination at a genuine sentence boundary, cross-field dedup/provenance
  escalation); honestly labeled `synthetic_representative`/
  `synthetic_adversarial`, never `sanitized_capture`.
  `backend/tests/test_normalization_skills.py` (76 tests): the fixture
  corpus, origin-honesty, determinism, sort/dedup invariants, `SkillMatch`
  unit-level invariant tests (non-slug `canonical_id`, whitespace-only/
  covered-whitespace-only/empty `display_name`, non-enum `provenance`,
  and a check that no invariant-violation message ever contains the
  offending input text), and the AST import-boundary allow-list.
- **Disclosed, necessary deviation** (found by actually running
  `verification_scope.classify_path` against the new fixture path, not by
  code review): `backend/tests/fixtures/normalization/skill_cases.json`
  is a non-`.py` path under `backend/tests/` with no exact rule, so it
  raised `OwnerMappingRequiredError` exactly like the taxonomy
  foundation's own YAML fixtures once did. Fixed the same way: added one
  exact-path entry, `_SKILL_FIXTURE_FILES`, to
  `backend/scripts/verification_scope.py` (never a new directory prefix),
  classifying it as `test-fixture:skill-classifier` — deliberately not a
  `contract-record` kind, since this fixture has no contract-harness
  guard/family involvement. Three new regression tests added to
  `backend/tests/test_verification_scope.py` mirroring the existing
  taxonomy-fixture ones. This was not part of the approved file list;
  flagging it here rather than treating it as silently in scope.
- **Adversarial self-review finding, fixed before this commit**: an
  independent adversarial-review pass (read-only, against the working
  tree before this candidate existed) found that the description
  anchor's post-colon whitespace group (`[\t\n\r ]*`, zero-or-more, with
  no mandatory literal after it) never actually rejected a non-covered
  whitespace lookalike sitting immediately after the colon — unlike
  every other whitespace span in the anchor grammar, which is always
  followed by a mandatory literal a lookalike can't satisfy. Concretely,
  `"Skills: Go"` (a no-break space right after the colon) produced a
  `golang` match, because the un-consumed no-break space was left as the
  first character of the region text, where the region's own ordinary
  Unicode-`\s`-aware tokenizer still treated it as a token separator —
  silently rescuing the ambiguous key the anchor grammar exists to gate.
  This directly contradicted the module's own docstring, which explicitly
  claimed this case was already rejected. Fixed by adding
  `_has_uncovered_whitespace_immediately_after` and an explicit rejection
  check in `_anchor_regions` for exactly this case; added fixture
  `description_nbsp_lookalike_after_colon_rejected` as the regression.
  Everything else the review checked (region/terminator index arithmetic,
  overlapping anchors, the ASCII casefold table, punctuation-stripping
  edge cases, exception safety on empty/very-long input, and hand
  re-derivation of the trickier fixture cases) held up with no further
  findings.
- **Two-iteration rotation applied**: the oldest iteration (the original
  v3.2 activation candidate/review cycle, C1–C6) is deleted; the former
  Iteration 2 (the post-merge `Q`-producer slice) and Iteration 3 (the
  skill-taxonomy-foundation slice) are renumbered to Iteration 1 and
  Iteration 2 respectively; this entry becomes the new Iteration 3.
- Files changed: `backend/app/normalization/skills.py` (new);
  `backend/tests/fixtures/normalization/skill_cases.json` (new, 61
  cases); `backend/tests/test_normalization_skills.py` (new, 76 tests);
  `backend/scripts/verification_scope.py`,
  `backend/tests/test_verification_scope.py` (edited, 3 new tests (one
  new parametrized case plus two new functions) — see the disclosed
  deviation above); `docs/ROADMAP.md` (edited: corrected
  the stale "skill-taxonomy foundation ... not yet merged" passage to
  record its actual merge SHA, and added this slice's own status
  paragraph); `docs/LLM_HANDOFF.md` (this entry, plus the two-iteration
  rotation above). No taxonomy file, migration, model, service, API, or
  live-provider file touched; no database lifecycle operation performed;
  no provider contact of any kind. `docs/ARCHITECTURE.md` intentionally
  not touched — its `skills.py` filename entry already matches this
  slice exactly; a separate, genuinely stale passage there (the
  taxonomy-foundation's own tree entries still say "candidate/publication
  stage, not yet merged") was noticed but is out of this slice's
  authorized two-document scope, so it is disclosed here rather than
  silently fixed.
- Verification: genuine `verification_coordinator.run_receipt_eligible_
  verification` run against `C` (`109a3070375be1b8a412abc3dbbbbc76dc379290`)
  in a disposable detached worktree. All 12 steps PASS: `ruff format
  --check`, `ruff check`, `mypy` (163 source files), `check_repo.py`,
  `git diff --check`, DB URL validation, DB reachability, focused pytest
  (`tests/test_normalization_skills.py tests/test_verification_scope.py`,
  145 passed), full pytest suite (**2811 passed**), 34 mutation
  witnesses (34 passed, 0 failed — all pre-existing experience/location/
  salary guards, none of this module's own since it has no contract-
  harness guard family), handoff metadata validation, cleanup. Receipt
  `769a9115-2e13-4c92-abfe-6c37a92e26e9`, `approval_eligible: true`.
  A first attempt at this same coordinator call failed with the full
  pytest suite step genuinely `FAIL`ing (blocking the mutation-witnesses
  step as `NOT RUN`, which correctly refused receipt emission — no
  receipt is possible on any step failure). Diagnosed by running
  `scripts.verify` directly against two fresh, separate disposable
  worktrees at the same candidate SHA (once with no `--focus`, once
  replicating the coordinator's exact computed `--focus` targets) —
  both passed cleanly, 2811/2811, matching this project's own prior
  "transient first-run failure, clean fresh-process retry" pattern
  (the taxonomy-foundation slice's Pydantic `MemoryError` precedent).
  The retry that produced this receipt is a fresh, independent run, not
  a rerun of the failed attempt's own state.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-09-19-skill-classifier-d0159a4
slice_kind: parser
risk_class: H
base_sha: d0159a4cc0faf9fb13f30ea814fa2e6c204570bb
declared_gate: final
executed_gate: final
candidate_sha: 109a3070375be1b8a412abc3dbbbbc76dc379290
receipt_id: 769a9115-2e13-4c92-abfe-6c37a92e26e9
receipt_path: docs/verification-receipts/109a3070375be1b8a412abc3dbbbbc76dc379290/769a9115-2e13-4c92-abfe-6c37a92e26e9.json
fixture_path: backend/tests/fixtures/normalization/skill_cases.json
fixture_count: 61
full_suite_count: 2811
focused_test_count: 145
mutation_witness_count: 34
```
