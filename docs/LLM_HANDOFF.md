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

- Date/agent: 2026-10-03, Claude (implementer). Branch `phase-4/pure-posting-composition-s2`,
  base `0c2c14b573609c6b2dfc67c0d9f14de97c31e03d` (`Q` of the S1 merge). Ending commit:
  this commit, the **immutable pre-publication advisory candidate**, for Sol Medium's
  advisory implementation review. It is not final `C`: no coordinator run, receipt, `A`,
  or formal review exists.
- Slice: Phase 4 S2, a pure provider-neutral `normalize_posting` composition plus scoped
  ADR 0011 D2 protection, and [ADR 0014](DECISIONS/0014-pure-posting-composition-and-scoped-d2.md).
  Pilot product slice 2 of 3 under ADR 0012. Risk class H, `slice_kind: parser`,
  `declared_gate: final`, fixture `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json`
  (30 records). Focused selector: `tests/test_normalization_posting.py
  tests/test_normalization_posting_realistic.py`, **235** tests collected (73 + 162).
  Counts are kept out of the metadata block: the schema has no selector field and the
  receipt cross-validates any duplicated count exactly.
- Contract identity (gitignored runtime packets, never committed):
  - frozen contract `.claude/runtime/phase4-s2-frozen-contract.md`, SHA-256
    `b966b4d4cb9a8ac46c30b5cb65b65280b65239db1b91d986aca1d7b3060a80a2`. It integrates the
    user's authorization, Sol Medium's consolidated proposal review (approved with binding
    amendments A1–A12, which supersede conflicting proposal text), and the proposal;
  - proposal `phase4-s2-proposal.md` `288bb4163cb04d8baeef226764bfa4e92f14780c021b9f0eb9b9dc98d1029c3d`;
    Sol review relay `phase4-s2-sol-review.md` `8f0cfde5120927c3a1d3aaf72fd9724472edd2fbdc3fdc3a3e1df15c4283ebf3`;
  - D2 expectation manifest `phase4-s2-d2-expectation-manifest.json`
    `f480ed2ec0305a7a85987fb9cfca8e1763816c2cad7a50d13203d0893b104d65` and its generator
    `phase4-s2-d2-manifest-generator.py`
    `fff152a4dcd8055aec433191fc9eee4aecd79697656c26766aa414cb4195563c`: derivation and
    review evidence only. The tests never read or require them (A1).
- Files (exact closed seven-path list): `backend/app/normalization/posting.py` (new);
  `backend/tests/test_normalization_posting.py` (new);
  `backend/tests/test_normalization_posting_realistic.py` (new); `docs/DECISIONS/0014-…`
  (new); `docs/ROADMAP.md` (S1 marked merged; S2 bullet); `docs/ARCHITECTURE.md` (§4 tree
  row; §5 note); this file (rotation: the pilot-activation iteration removed, S1's
  iteration retained byte-for-byte as Iteration 1).
- Material behavior: `PostingInputs`/`NormalizedPosting`/`normalize_posting` as frozen —
  validation before any parser call with fixed `TypeError` messages; call order title,
  remote type, employment, seniority, experience, location, skills; exceptions propagate
  and stop later parsers; `result.inputs is inputs`; identical parser result objects;
  skills a new tuple of the identical `SkillMatch` objects; no salary; exact import
  allow-list. Nothing at runtime calls it; no provider, HTML, persistence, `parser_version`,
  migration, or evaluator change.
- D2 durable contract (A1–A9): the realistic module holds literal committed data for the
  30-ID universe, all 13 annotation partitions, correct maps, abstention, confidently-wrong
  and three false-positive sets, the four salary missing-input sets, skills hit/miss/
  false-positive sets, title smoke, the three provenance exceptions, covered/unproven
  lists, and headline totals. Identity pins: corpus canonical JSON
  `ca6e129110b71801e18d6bfba84d59376c689f67cb470f1335ab8805cd388f00`; taxonomy
  canonical-LF `926a2a46cb0c603b953d989f449551af2d1a82cb3b50084a4005e78d7730c67c`
  (D2 evidence identities, not D1). An independent scorer is cross-checked against public
  `evaluate_corpus` (opportunity matrices, runtime failures, per-record mismatch multiset);
  per-record direct-parser equivalence is checked. Totals: 0 runtime failures, 0
  confidently wrong, 0 false positives, skills recall 37/40 (3 known `golang` misses), 56
  supported abstentions, 100 salary gaps, 33 correct values, 159 evaluator mismatches.
  Covered: `employment_type`, `seniority`, `location.country`, plus skills recall.
  Unproven (10): `remote_type`, `experience.minimum`/`maximum`, `location.city`/`state`/
  `postal_code`, and the four `salary.*`. Title smoke only: 22/6/2/0.
- Verification at this candidate (no receipt-producing coordinator run):
  - both new modules: **235 passed**; related existing normalization, title, taxonomy,
    types, evaluator, and freeze modules plus the new ones (14 modules): **1,490 passed**;
    `tests/contracts`: **130 passed**. No database fixture is requested and no network is
    used;
  - `ruff format --check`, `ruff check`, and `mypy` on the three Python files: clean;
  - evaluator `python -m scripts.evaluate_phase3_corpus`: SHA-256
    `87a92187a2d37d5150fe998d06042449f6b74d540cecd15d1bba97dd94801de6`, 91,994 bytes,
    1,366 CRLF lines, unchanged;
  - `check_handoff`, `check_repo`, `git diff --check`, seven-path scope, and runtime-file
    hashes: see the agent's report for this commit.
- Mutation experiments (A10, exactly nine; recorded, not registered). Each anchor occurred
  once in `posting.py`; baseline witness and controls passed; under the single mutation
  every named witness failed and the stable controls passed; the source was restored
  byte-identically (final source SHA-256 `4efe44180eedd042f0200d5cb67cd9422e73cf79d12a0263b716b57c461cef7e`
  before and after each); the witness then passed. All nine were rerun after the self-review fixes. Log
  `.claude/runtime/phase4-s2-mutation-log.json`
  (`0a1a809da7f6e8e026c621ca181ab2a2ab75d5d4dac3606a5aa34aebad9d7663`), driver
  `phase4-s2-mutation-driver.py` (`1de80be18f764454f6584bbd0a6a574734aaeb5710d35c259b07bbb2d2187d92`).
  Witness names drop the `test_` prefix:
  - M1a unused `.salary` import → `import_boundary_is_the_exact_allow_list`;
  - M1b defaulted `salary` field → `normalized_posting_fields_are_exact_with_no_salary`
    (the realistic `salary_is_not_composed_and_stays_unproven` also detects it and was
    deselected from the control run as overlap coverage);
  - M2 seniority title/description swap → `correct_values_are_exact[seniority]`;
  - M3 `None` to location → `correct_values_are_exact[location.country]` and
    `supported_abstentions_are_exact[location.country]`;
  - M4 employment provenance set to `EXPLICIT_SOURCE` via `object.__setattr__` →
    `emitted_provenance_never_claims_explicit_or_structured_sources` and the employment
    provenance test (value sets and the identity test stayed green);
  - M5 `TaxonomyIndex({})` to skills → `skills_recall_hits_are_exact`;
  - M6 employment forced to `full_time` → `false_positive_sets_are_exact[employment_type-false_positive_absent]`;
  - M7 copied `PostingInputs` → `results_pass_through_as_the_identical_objects`;
  - M8 `United States`/`INFERRED` for the unique `Strategic Finance` / `San Francisco Bay
    Area` input (`discord:8575166002`, predicate asserted by
    `m8_input_predicate_matches_exactly_one_record`) → the `location.country` correct and
    abstention tests; false-positive and provenance controls stayed green.
- Deviation for Sol (M8 mechanism): Sol's text mutates "the existing `LocationResult` in
  place". Run literally, that rewrites `classify_location`'s module-level
  `_UNAVAILABLE_RESULT`, the single object returned for every all-unavailable location, so
  every later abstaining record also emitted `United States` and two stable controls
  (`location.country` absent and ambiguous false-positive sets) failed. That attempt's log
  is kept as `phase4-s2-mutation-log-attempt1-inplace-m8.json`
  (`8b0264e0badf4c91e33d855c7d245d9393731e3e5627f3a3c374791fe931ac26`). The recorded M8
  keeps the predicate, value, provenance, witnesses, and controls and builds a new
  `LocationResult` instead. The finding is documented in `posting.py` and ADR 0014:
  results pass through by identity and can be parser-owned shared objects, so callers
  must never mutate them.
- Other disclosed interpretations: a format-character-only title yields `classify_title`'s
  own `unsupported` outcome (its approved contract), not `no_title`; per-record
  direct-parser equivalence lives in the realistic module.
- Adversarial self-review (a fresh read-only subagent, before commit): no P1. Fixed before
  commit:
  - P2-1: ADR 0014 overstated what D2 catches. It now names what is pinned per record and
    what is not (skill-match order, duplicates, and display names). Provenance on `None`
    values and title provenance are fixed by the result types' own invariants;
  - P2-2: the ROADMAP and ARCHITECTURE S2 notes now carry the bounded-claim qualifiers;
  - P3-1: a `PostingInputs` subclass whose attribute reads change between reads could pass
    an unvalidated value to a parser. `_validate` now returns the values it read once and
    checked, and the parsers receive exactly those. The regression test
    `test_parsers_receive_exactly_the_values_that_were_validated` failed against the
    pre-fix code and passes now;
  - P3-2: the static import allow-list cannot see `__import__`, `importlib`, `exec`, or
    `eval`; a separate AST check with synthetic rejections now asserts their absence;
  - P3-3: the per-record provenance test now runs over the covered components and asserts
    they are non-empty; a literal category non-overlap test was added;
  - P3-4: a no-op expression was removed; P3-5: returned skill IDs are asserted to lie
    within the annotated set.

  Accepted unchanged: `str` subclasses pass validation (the `isinstance` contract), and
  the scorer shares the evaluator's category naming, which the literal sets backstop.
- Known limitations: D2 holds only at the composition boundary on an exposed 30-record,
  three-employer corpus; title is smoke-only; ten components are unproven; salary is not
  composed (L4 open); HTML conversion, list-endpoint escaping, and unredacted text are
  unproven; D1 is unsatisfied; the mutation experiments are not registered guards.
- Pilot metrics so far (pilot product slice 2 of 3): proposal-review rounds 1 (Sol,
  approved with A1–A12); advisory-review rounds 0; executable findings 0; pre-`A`
  correction commits 0; post-`A` 0; full-suite executions 0; receipt-producing executions
  0; user relays 3 (the S2 overview request, decisions U1–U7 with the D2 freeze, and this
  authorization with the Sol review relay). Branch created 2026-10-04T01:01:23Z.
- STOP after pushing this candidate for Sol Medium's advisory implementation review. No
  final `C`, coordinator receipt, `A`, formal `R`, merge, `M`/`Q`, Greenhouse contact,
  production data access, or S2b.

**Pre-publication advisory review — approved (Sol Medium, advisory only; not formal R).** Reviewed immutable advisory candidate `d418025aaf1443d9212ced50094800b2756cafb8` against frozen-contract SHA-256 `b966b4d4cb9a8ac46c30b5cb65b65280b65239db1b91d986aca1d7b3060a80a2`; all material changes through that SHA were reviewed, with no advisory findings. Independent review confirmed the exact seven-path scope and clean ancestry; prevalidation and exact parser-input wiring; fixed result fields, call order, pass-through identity and provenance behavior; salary and unauthorized-import exclusion; absence of runtime reachability, provider mapping, persistence, database, migration or network behavior; the bounded D2 accounting and evaluator identity; 235 focused tests, 1,490 related tests, 130 contract tests, clean Ruff/mypy and repository checks. The nine mutation records and byte-identical restoration were inspected and accepted. M8’s new-`LocationResult` mechanism is approved without a replacement witness: literal in-place mutation contaminates `classify_location`’s shared unavailable singleton, while the recorded mutation preserves the exact unique predicate, injected `United States`/`INFERRED` result, required failing witnesses and stable false-positive/provenance controls without unrelated contamination. The candidate remains advisory-only; final candidate-bound verification may proceed, while formal R retains unrestricted authority to reject the slice.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-03-phase4-pure-posting-composition-s2-0c2c14b
slice_kind: parser
risk_class: H
base_sha: 0c2c14b573609c6b2dfc67c0d9f14de97c31e03d
declared_gate: final
executed_gate: final
candidate_sha: 2a3f50d681d2a97b9adc2cf097f933ce4507ead2
receipt_id: 5b39efd7-64c7-491f-8ca0-98803789b1e4
receipt_path: docs/verification-receipts/2a3f50d681d2a97b9adc2cf097f933ce4507ead2/5b39efd7-64c7-491f-8ca0-98803789b1e4.json
fixture_path: backend/tests/fixtures/evaluation/phase3_realistic_corpus.json
fixture_count: 30
```

### Work review

- Date/reviewer: 2026-10-04 (UTC), Sol (primary, Sol Medium). Formal review of Phase 4 S2,
  the pure provider-neutral `normalize_posting` composition with scoped D2 protection, on
  `phase-4/pure-posting-composition-s2`:
  - base `0c2c14b573609c6b2dfc67c0d9f14de97c31e03d`;
  - final candidate `C` = `2a3f50d681d2a97b9adc2cf097f933ce4507ead2`;
  - publication `A` = `95e975164560bb35021076eadf650af11720482c`.

  Reviewed against the frozen contract (SHA-256
  `b966b4d4cb9a8ac46c30b5cb65b65280b65239db1b91d986aca1d7b3060a80a2`), which integrates
  the proposal, Sol's binding amendments A1–A12, and the user's decisions U1–U7. Sol's
  earlier pre-publication advisory review of `d418025` was advisory only; this is the
  formal review.
- Sol's formal verdict, as relayed by the user: **approved**, findings none, primary
  reviewer Sol (Sol Medium), gate `final`, for `C`/`A` above, receipt
  `5b39efd7-64c7-491f-8ca0-98803789b1e4`, and frozen-contract SHA-256 `b966b4d4…80a2`.
  The relay states the verdict and chain; it is the authority for this review. The
  evidence below is classified by source.
- Independently checked evidence (re-verified from Git plumbing and the receipt itself
  when this review was recorded; not inferred from prose):
  - **Ancestry and refs:** `A`'s sole parent is `C`; `C`'s sole parent is the advisory
    candidate `d418025`, whose sole parent is the base; the local and remote branch both
    equal `A`; `main`/`origin/main`/remote `main` remain at the base; the tree was clean.
  - **Scope:** `base..C` changes exactly the seven authorized paths; `d418025..C` changes
    only this file (the advisory paragraph inserted verbatim before valid `state: pending`
    metadata); `C..A` adds only the C-bound receipt and the permitted pending -> published
    metadata transition with `executed_gate: final` (`validate_c_to_a_transition` passed).
  - **Receipt:** receipt file SHA-256
    `05d60a10e2bdb64a90b19ce0223ac31f17e4d1d559ae9ce69ec5ebeaf6541766`; schema-valid; bound
    to `C`, the base, gate `final`, the slice, and risk class H; consistent with the
    committed verifier, checker, and configuration hashes; affected surface (`docs-only`,
    `generic-changed-test`, `handoff-transition`, `unmapped`) and migration determination
    (not triggered) independently recomputed and identical; complete active witness
    inventory; approval eligibility recomputed as `true`.
  - **Frozen contract:** runtime packet hash unchanged and untracked.
- Receipt-derived evidence (produced by the genuine coordinator run at `C`; not rerun):
  - all 12 steps PASS: Ruff format/check, mypy, `check_repo`, `git diff --check`,
    disposable test-database URL validation and reachability, focused pytest (235
    passed), full pytest suite (3,909 passed), contract mutation witnesses (34/34
    passed), handoff metadata validation, temporary-directory cleanup;
  - isolated-worktree integrity, cache redirection, and worktree removal.
- Reused advisory evidence (from Sol's pre-publication advisory review of `d418025`,
  recorded verbatim in `Work done`; not re-executed for this review):
  - the contract checks: prevalidation and exact parser-input wiring, fixed result fields,
    call order, identity pass-through and provenance behavior, salary and
    unauthorized-import exclusion, and absence of runtime reachability, provider mapping,
    persistence, database, migration, or network behavior;
  - the bounded D2 accounting and Phase 3 evaluator identity (SHA-256
    `87a92187a2d37d5150fe998d06042449f6b74d540cecd15d1bba97dd94801de6`);
  - 1,490 related tests, 130 contract tests, and clean Ruff/mypy and repository checks at
    the advisory candidate;
  - the nine manual S2 mutation experiments (M1a, M1b, M2–M8) and their byte-identical
    restoration evidence. These were inspected during advisory review; **they were not
    run by the coordinator** and are not registered witnesses.
- Formal-review dispositions:
  - M8: constructing a predicate-limited new `LocationResult` is the valid isolating
    mutation, because literal in-place mutation contaminates `classify_location`'s
    shared unavailable singleton. Accepted without a replacement witness.
  - The pre-commit self-review fixes recorded in `Work done` (bounded documentation
    wording, read-once validated values, dynamic-import check, non-vacuous provenance and
    category checks, annotated-skill assertion) are accepted.
  - The focused count is recorded in prose rather than metadata, consistent with the
    schema; the receipt's focused count (235) matches.
- Limitations retained:
  - D2 is satisfied only at the pure `normalize_posting` composition boundary, for the
    exact covered outputs of the exposed 30-record, three-employer corpus under the
    pinned identities;
  - title is smoke evidence only; ten components are unproven; salary is not composed
    (ADR 0011 L4 stays open);
  - skill-match order, duplicates, and display names are not pinned per record;
  - HTML conversion, Greenhouse list-endpoint escaping, provider-field mapping, and
    unredacted text are unproven;
  - D1 remains unsatisfied and no normalized write is authorized;
  - the composition is not reachable at runtime. No claim of runtime reachability or
    production usefulness may be made for S2.
- Pilot metrics (ADR 0012, pilot product slice 2 of 3), accepted as recorded:
  proposal-review rounds 1; advisory-review rounds 1 (no findings); semantic pre-`A`
  correction commits 0; handoff-only finalization commits 1; post-`A` corrections 0;
  receipt-producing executions 1; full-suite executions through `A` 1; user relays
  through `A` publication 4, plus one identical re-paste. The relay for this formal
  review occurred after `A` and is outside that boundary.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings.
- Exact bounded correction: none required.
- STOP -- record-only. This review authorizes no merge, `M`, `Q`, Greenhouse contact,
  S2b, runtime wiring, persistence, or other slice. Merge requires separate user
  authorization.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-03-phase4-pure-posting-composition-s2-0c2c14b
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-04T02:49:44+00:00
candidate_sha: 2a3f50d681d2a97b9adc2cf097f933ce4507ead2
publication_commit_sha: 95e975164560bb35021076eadf650af11720482c
receipt_path: docs/verification-receipts/2a3f50d681d2a97b9adc2cf097f933ce4507ead2/5b39efd7-64c7-491f-8ca0-98803789b1e4.json
receipt_id: 5b39efd7-64c7-491f-8ca0-98803789b1e4
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-04 (UTC). Merged `phase-4/pure-posting-composition-s2` into `main` with
  `git merge --no-ff`, at the approved, reviewed commit
  `fa7ff78115a5158444443b6c55962f2f9b8e6359` (`R`). `R` is Sol Medium's
  "approved -- no findings" formal verdict on
  `C=2a3f50d681d2a97b9adc2cf097f933ce4507ead2` /
  `A=95e975164560bb35021076eadf650af11720482c`.
  - Merge commit `M`: `f509e80f68505dbdee7d8aed5f2748b805eaec4d`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `0c2c14b573609c6b2dfc67c0d9f14de97c31e03d`.
  - Full lineage: base `0c2c14b` -> advisory candidate `d418025` -> `C` `2a3f50d` ->
    `A` `95e9751` -> `R` `fa7ff78` -> `M` `f509e80` -> `Q` (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch and its origin both sat at `R`, and `R`'s sole parent is `A`;
  - `main`/`origin/main`/remote `main` were clean and synchronized at the rollback
    boundary;
  - receipt `5b39efd7-64c7-491f-8ca0-98803789b1e4` was schema-valid, bound to `C`, the
    base, and gate `final`, and independently recomputed as approval-eligible;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`, `gate: final`,
    `published_slice_kind: parser`.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, 0c2c14b)` passed.
  - `verification_coordinator.run_post_merge_verification` ran against `M` in a
    disposable detached worktree (always full/final). It produced artifact
    `eb15c344-c68f-42a9-8df0-97739b73e953`:
    - all 11 steps PASS, including the disposable test-database URL validation and
      reachability preflight, repository and handoff checks;
    - full pytest suite: **3909 passed**;
    - all 34 registered mutation witnesses passed;
    - no migration triggered;
    - identical worktree snapshots (tracked tree `f15200ce06978387a4f3807cbb58a3d1d1aacee9`),
      worktree removed with no residual entry or directory, and cleanup PASS.

    The post-merge coordinator did not run S2's nine manual mutation experiments
    (M1a, M1b, M2–M8); they remain advisory-candidate evidence, not registered
    witnesses. No test made a live network request.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit (this entry).
- Post-merge evidence:
  `docs/post-merge/f509e80f68505dbdee7d8aed5f2748b805eaec4d/eb15c344-c68f-42a9-8df0-97739b73e953.json`
  (SHA-256 of the artifact file as written:
  `cee2a213134a20ef8dba4a9ed2ca42c0abf4a2394139234db026b6cda4f08a8f`). It references
  original receipt `5b39efd7-64c7-491f-8ca0-98803789b1e4`
  (`docs/verification-receipts/2a3f50d681d2a97b9adc2cf097f933ce4507ead2/5b39efd7-64c7-491f-8ca0-98803789b1e4.json`).
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- S2 status: merged. S2 adds a pure, provider-neutral `normalize_posting` composition
  (`app/normalization/posting.py`) and executable D2 protection at that boundary, plus
  [ADR 0014](DECISIONS/0014-pure-posting-composition-and-scoped-d2.md).
  - D2 is satisfied only at the pure `normalize_posting` composition boundary, for the
    exact covered outputs of the exposed 30-record corpus under the pinned corpus and
    taxonomy identities.
  - S2 introduces no runtime-reachable composition, provider mapping, HTML conversion,
    persistence, salary composition, or live Greenhouse contact, and it is not a
    production-usefulness proof.
  - D1 remains unsatisfied; no normalized write is authorized.
  - S2b remains unstarted and requires separate authorization; S2c, S3, and S4 likewise.
    Phase 4 is not complete.
- Retained limitations: title is smoke evidence only; ten components are unproven
  (`remote_type`, `experience.minimum`/`maximum`, `location.city`/`state`/`postal_code`,
  and the four `salary.*`); salary is not composed (ADR 0011 L4 open); skill-match order,
  duplicates, and display names are not pinned per record; HTML conversion, list-endpoint
  escaping, provider-field mapping, and unredacted text are unproven; the composition is
  not reachable at runtime; the nine mutation experiments are not registered guards.
- Pilot metrics through merge (ADR 0012, pilot product slice 2 of 3):
  - proposal-review rounds: 1; advisory-review rounds: 1 (no findings); formal-review
    rounds: 1;
  - findings: 0 advisory, 0 formal; 2 P2 and 5 P3 pre-commit self-review findings, fixed
    before the advisory candidate;
  - semantic pre-`A` correction commits: 0; handoff-only finalization commits: 1;
    post-`A` corrections: 0;
  - receipt-producing executions: 1 (the clean-path target); full-suite executions: 2
    (the `C` receipt run and the post-merge run at `M`);
  - user relays: 4 through `A` publication, plus the formal-review relay and the merge
    authorization (6 through merge), plus one identical re-paste;
  - escaped post-merge defects: none known at merge; newly reachable runtime product
    behavior: none, by design.

  These are measurements, not conclusions; the pilot's exit comparison happens after
  the third slice.
- STOP -- report the synchronized final `main` SHA and stop. No S2b, Greenhouse contact,
  runtime provider wiring, normalized persistence, D1 work, migration, or another slice
  without separate explicit user authorization.

## Iteration 2

### Work done

- Date/agent: 2026-10-04, Claude (implementer). Branch
  `phase-4/greenhouse-content-mapping-s2b`, base
  `e670575d5b05395cb9eeb2ec84833cc0034c7002` (`Q` of the S2 merge). Ending commit: this
  commit, the **immutable pre-publication advisory candidate**, for Sol Medium's advisory
  implementation review. It is not final `C`: no coordinator run, receipt, `A`, or formal
  review exists.
- Slice: Phase 4 S2b, offline Greenhouse content conversion and strict `PostingInputs`
  mapping, plus
  [ADR 0015](DECISIONS/0015-greenhouse-content-conversion-and-posting-input-mapping.md).
  Pilot product slice 3 of 3 under ADR 0012. Risk class H, `slice_kind: parser`,
  `declared_gate: final`, fixture `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json`
  (30 records; the reconstructed-envelope source). Focused selector:
  `tests/test_greenhouse_content.py tests/test_greenhouse_posting_inputs.py`, **284** tests
  collected (219 + 65).
- Contract identity: frozen contract `.claude/runtime/phase4-s2b-frozen-contract.md`
  (gitignored, never committed), SHA-256
  `e409427bccfecd4f3f04c839f47826f5727355788ceab8fee061e6985e519df2`. Precedence: the
  user's decisions U1–U4 and requirements, then Sol Medium's binding amendments A1–A20
  and corrected mutation inventory W1–W19, then the proposal.
- Files (exact closed nine-path list):
  - `backend/app/providers/greenhouse_content.py` (new);
  - `backend/app/providers/greenhouse_posting_inputs.py` (new);
  - `backend/app/providers/greenhouse.py` (`content_mode`, conversion, partition, warnings);
  - `backend/tests/test_greenhouse_content.py` and `test_greenhouse_posting_inputs.py` (new);
  - `docs/DECISIONS/0015-…` (new);
  - `docs/ROADMAP.md`: the S2b bullet, plus the S2 bullet's merge SHAs, replacing its
    stale "S2b and later slices remain unauthorized" sentence (disclosed: beyond the S2b
    bullet itself);
  - `docs/ARCHITECTURE.md`: §4 tree rows (including S1's missing `greenhouse.py` row), the
    `providers/` dependency row's single named exception for the bridge, a §5 note, and a
    §10 note;
  - this file (rotation: S1's iteration removed, S2's retained byte-for-byte as
    Iteration 1).
- Material behavior:
  - **Board mode.** `GreenhouseBoard.content_mode` is `disabled` (default) or
    `declared-double-escaped`. Any other value raises the fixed A3 message.
  - **Disabled boards.** `content` is never read by key or converted. It travels only
    inside S1's whole-record parse and deep copy for `raw`.
  - **Declared boards.** `description` is the converter's text or `None`. Only
    `converted` is neutral. Every other outcome keeps the job with `description=None` and
    makes the board partial (`incomplete_results`, `possibly_incomplete`, partial health).
  - **Warnings.** Source-wide and token-free, one per outcome, sorted:
    `greenhouse content_unconverted=<outcome> count=<n>`.
  - **Unchanged from S1:** `raw` (deep, equal, non-aliased, equal hash), record validity,
    skipping, completeness, labels, and `compensation_text=None`.
  - **Converter.** It reimplements the frozen script's declared-mode algorithm exactly.
    - Order: mode, type (exact `str`), 200,000-code-point input cap, blank, encoding,
      one decode, extraction, meaningfulness, 100,000-code-point output cap. Nothing is
      truncated.
    - Only `RecursionError` from the parser becomes `parser_error`.
  - **Mapper.** It reads only `provider`/`source`/`title`/`description`/`location` and
    returns those three values unchanged, with fixed errors.
  - Nothing registers, imports the mapper, or persists. No salary, no schema field, no
    parser, taxonomy, corpus, evaluator, or script change.
- Evidence identities (pinned in tests):
  - oracle script canonical-LF `fff4b1c0…cd06f` and its tests `2bdf3014…9fcd1`;
  - corpus canonical JSON `ca6e1291…8f00` and committed content
    `1863541bb784419be16bf4ffcf88bf1b4408c951a03b12008e9645e9f18e6930`;
  - canary `690b0a5d…db4d5`.

  The A16 bounded claim appears verbatim in ADR 0015 §9 and the test module docstring.
- Verification at this candidate (no receipt-producing coordinator run; no network,
  database, or provider contact):
  - focused: **284 passed**;
  - acceptance selection, i.e. the focused modules plus unchanged
    `test_greenhouse_provider.py`, `test_greenhouse_html_convert.py`,
    `test_canary_greenhouse_mapping.py`, both S2 modules, and the D2 module: **857 passed**;
  - `tests/contracts`: **130 passed**;
  - full suite: **4,193 passed**;
  - `ruff format --check`, `ruff check`, `mypy` on the five Python files: clean;
  - evaluator `python -m scripts.evaluate_phase3_corpus`: SHA-256 `87a92187…01de6`,
    91,994 bytes, unchanged;
  - `check_handoff`, `check_repo`, `git diff --check`, nine-path scope: see the agent's
    report for this commit.
- Mutation experiments W1–W19 (recorded, not registered; driver
  `.claude/runtime/phase4-s2b-mutation-driver.py`
  `bd6d9844d59dd4df50739639f79e27b9ae11b48d3cdde305bc08aee328385ed5`, log
  `phase4-s2b-mutation-log.json`
  `c06cfd5a412f9ef3a34dab67cdaf0c98bbba71d41f1d911290087e7c4c568c71`).
  - **Procedure.** Each experiment applied one unique anchor to one production file. The
    witness and controls passed beforehand. Under the mutation every named witness
    failed (W3 including both the raw `&ltfoo` and post-decode `&amp;ltfoo` cases) and the
    corrected controls passed. The file was restored byte-identically and the witness
    passed again.
  - **Restoration hashes,** before and after every experiment:
    - `greenhouse_content.py` `c1999524d8fa046195d954c00a9560e02feb169ed7f141352ce9e9b3a4a2adef`;
    - `greenhouse.py` `6c486d20c13eda813ef47315aa1c319a954cf03dc60b7455c0a7d19f73b22ed8`
      (CRLF working-tree form; its committed LF blob is
      `f20ee294dfe2f37da68deb238a5422db9bf2dd244efde0c9f154fe38903edf63`. The other two
      files are LF on disk and equal their committed blobs);
    - `greenhouse_posting_inputs.py` `00809ff005012f29f569df25a52e311c310e72802d7bf0e08aaca8e0b955fd2e`.
  - **Overlaps,** from the full overlap selection in the log. These are disclosed and none
    is a control:
    - W1–W5, W8, W9: oracle-differential cases;
    - W1/W2: conversion-warning and partition tests;
    - W4: the W5 control and the `<script>`-only abstention case;
    - W6: the code-point and order tests;
    - W8: the parser-sensitive goldens;
    - W10/W11: S1 `t05`/`t07` and the canary and mixed-board tests;
    - W12/W13/W15–W17: the canary test;
    - W14–W18: `mapper_ast_boundary` and/or the access trace;
    - W17: the corpus round trip, normalize-flow, and direct-mapping tests;
    - W19: the no-network-primitive import test.
  - **Driver caveat.** The driver keys pytest results on node ID up to the first space,
    so some parametrized counts are understated (for example, the W3 control shows 2 of
    its 3 cases, which pass when run directly). Pass/fail verdicts are unaffected.
- Deviations and disclosures for Sol:
  - **Reconstruction escaping.** The reconstruction uses `html.escape(…, quote=False)` at
    both layers. The proposal's read-only check implied default quoting; the reviewer
    verified that both variants round-trip all 30 records.
  - **Hash abbreviation typo.** The proposal's (and so A15's) abbreviation `1863541b…6e930`
    has a typo; the full committed-content hash ends `…8e6930` and is the value pinned.
  - **Access guard scope.** The A5 test mapping raises on keyed access (`[]`, `get`, `in`,
    `pop`, `setdefault`), not on `items()`/`values()`. Deep copying for `raw`, which A13
    requires, iterates items.
- Adversarial self-review (a fresh read-only subagent, before commit). It reported no P1;
  its 60,000-input differential fuzz against the oracle found 0 disagreements beyond the
  documented abstentions. It accidentally left an empty `%TEMP%\claude_fuzz.py` outside
  the repository. Fixed before commit:
  - **P2-1.** Unterminated comments, quoted attributes, and `<letter` silently truncate
    while staying `converted` (inherited from the oracle and `html.parser`). Now disclosed
    in the module, ADR §3/§10, and ROADMAP ("fail-closed" now names the enumerated
    cases), and pinned by golden tests.
  - **P2-2.** Output depends on the interpreter's `html.parser`, which the oracle shares.
    Disclosed as verified on CPython 3.12.13, with literal golden expectations for
    parser-sensitive inputs. The catch is not broadened.
  - **P2-3.** The "never touched" wording overclaimed, since the deep copy for `raw` still
    carries `content`. Reworded in the code and ADR.
  - **P3s.** The W11 control was renamed `test_description_populated_on_declared_board`.
    ADR 0015 now states that ADR 0014's U6 list-endpoint deferral moves to S2c. The
    ARCHITECTURE tree alignment was fixed. The hash typo, reconstruction quoting, ROADMAP
    S2 edit, and access-guard scope are disclosed above.
- Known limitations:
  - no captured raw `content` or list-endpoint encoding evidence, and U6 moves to S2c;
  - synthetic HTML only;
  - table and section content merges, `noscript`/`template` text is kept, and escaped
    code examples are rejected;
  - silent truncation after unterminated markup;
  - interpreter-dependent parser behavior;
  - unredacted in-memory text;
  - no mode or outcome traceability on the job (A11), which is not D1;
  - D1 unsatisfied; salary excluded (L4); ten unproven components; title smoke-only;
    exposed 30-record corpus;
  - nothing runtime-reachable; mutation experiments not registered.
- Pilot metrics so far (pilot product slice 3 of 3):
  - review rounds: proposal 1 (Sol, approved with A1–A20); advisory 0;
  - findings: 0 executable;
  - correction commits: 0 pre-`A`, 0 post-`A`;
  - full-suite executions: 2 non-receipt (implementer and self-review subagent);
    receipt-producing executions: 0;
  - user relays: 2 (the S2b proposal request, and this authorization with Sol's table);
  - branch created 2026-10-04T04:02:30Z.
- STOP after pushing this candidate for Sol Medium's advisory implementation review. No
  final `C`, coordinator receipt, `A`, formal `R`, merge, `M`/`Q`, Greenhouse or network
  contact, database access, pilot evaluation, S2c, S3, or S4.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-04-phase4-greenhouse-content-mapping-s2b-e670575
slice_kind: parser
risk_class: H
base_sha: e670575d5b05395cb9eeb2ec84833cc0034c7002
declared_gate: final
fixture_path: backend/tests/fixtures/evaluation/phase3_realistic_corpus.json
fixture_count: 30
```
