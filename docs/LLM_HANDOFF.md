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

- Date/agent: 2026-09-12, Claude Code (Sonnet 5). Risk class R
  (routine tooling — new, self-contained test infrastructure; no
  production-code, identity, concurrency, security, or external
  surface). Base -> ending commit: `d28bf03` -> this commit; new branch
  `tooling/workflow-v3.2-slice2-contract-harness`. Workflow v3.2 Slice 2
  of the staged proposal: the deterministic parser-contract harness,
  implemented per the frozen Slice 2 proposal plus Sol's ten binding
  final clarifications and one further binding resolution (the
  superseded-guard correction below), all relayed as text and treated as
  the complete implementation contract — no further proposal round.
- Outcome: `backend/tests/contracts/` (new package) plus
  `backend/scripts/contract_mutation_witnesses.py` (new, standalone,
  never collected by pytest). Covers all three existing parsers
  (`location`, `salary`, `experience` — only these three seeded, per
  the binding scope). Key modules: `schema.py` (closed record types; an
  independently-declared provenance vocabulary, never importing
  `app.normalization.types.NormalizationResult`), `taxonomy.py` (the
  guard inventory — see the corrected arithmetic below), `loader.py`
  (fail-closed JSON loader enforcing ~12 distinct validation
  categories, including a record_id-to-real-fields consistency check
  added during self-review), `transforms.py` (five mechanical,
  parser-independent string transforms; deterministic `ascii_recase`
  mixed-mode algorithm), `runner.py` (invokes an adapter and compares
  actual vs. expected), `adapters/{location,salary,experience}.py`
  (each imports only its own public `classify_*` entry point — enforced
  at the AST symbol level, including a dynamic-bypass check for
  `getattr`/`setattr`/`importlib.import_module`/`__import__`, added
  during self-review), `records/{location,salary,experience}.json` (34
  hand-authored primary-witness case records, each fully materialized:
  original input, deterministic transform parameters, expected
  transformed input, complete expected output, and a durable rationale
  citing the exact historical commit), and `mutation_registry.py` (34
  replayable mutants — "simple" ones monkeypatch a live module
  attribute or small atomic helper function; "structural" ones edit
  source text via an anchor asserted to occur exactly once and load the
  mutated text as a fully isolated module via `importlib`, never
  touching the shared checkout — plus **committed, frozen baseline
  fingerprints** for the production source file, the JSON record, and
  the adapter file per guard, corrected during self-review; see below).
- **Corrected inventory arithmetic** (a factual correction discovered
  through source-history verification, not a deviation from the
  authorized contract): `experience/g07-reversed-label-anchor`'s own
  historical fix (`2589eec` finding 1) was itself fully superseded by a
  later fix (`2fcdc0f` finding 3, `experience/g18-description-label-
  value-scope-removed`) that removed the description-side reversed-label
  path entirely — confirmed directly against the current
  `experience.py` source, which never calls `_LABEL_VALUE_RE`/
  `_match_label_value_phrase` from `_extract_description_bounds` in any
  form. Per the user's binding resolution: g07 is retained as a
  **historical record**, `status="superseded"`, `superseded_by`
  pointing to g18, with **no primary witness and no mutant** (a written
  approval is not a substitute for executable mutation evidence, and
  g18's own witness is never double-counted as g07's). Corrected counts:
  **35 historical guard records** (location 8, salary 5, experience 22),
  of which **34 are active** (experience 21) with exactly one primary
  witness and mutant each, and **1 is superseded** with neither. The
  taxonomy module asserts these exact counts at import time.
  `loader.py` fails closed if any record references the superseded
  guard, and `collect_all` requires exactly one primary witness per
  *active* guard only.
- Fresh-context adversarial self-review (via an independent subagent,
  per the user's explicit requirement) found six real defects before
  this entry was written, all fixed and re-verified before commit:
  1. **[Critical] Vacuous staleness check** — fingerprints were
     originally computed fresh from current files at import time, then
     compared against themselves in the same run — a tautology that
     could never detect drift. Fixed: fingerprints are now committed,
     frozen baseline values (`_FROZEN_SOURCE_FP`/`_FROZEN_ADAPTER_FP`/
     `_FROZEN_RECORD_FP`), computed once against this commit's exact
     content; the witness script recomputes fresh values at run time
     and compares against these frozen ones. Empirically re-verified:
     appending a harmless comment to `location.py` and rerunning the
     `location/g01` witness correctly reports `STALE source
     fingerprint`; restoring the file and rerunning correctly passes
     again.
  2. **[High] AST import-boundary bypassable via dynamic access** —
     the original checker only inspected literal `Import`/`ImportFrom`/
     `Attribute` nodes, missing `importlib.import_module`,
     `__import__`, and computed-name `getattr`/`setattr`/`delattr`.
     Fixed: a new detector rejects these call forms in every adapter
     and non-mutation-registry harness module (the mutation registry
     and witness script are the sole, deliberately exempt, sanctioned
     users of dynamic access to production internals).
  3. **[Medium] Misdocumented fingerprint granularity** — the module
     docstring claimed "exact production source region" precision;
     fingerprints are actually whole-file hashes. Corrected to disclose
     this honestly (over-broad staleness triggers, never under-broad).
  4. **[Low] `record_id` tokens not cross-validated** — a record's
     embedded transform/target/boundary tokens were never checked
     against its real fields. Fixed: `loader.py` now rejects a mismatch.
  5. **[Low] `transform.parameters` accepted unknown extra keys** —
     fixed via an exact-keys check keyed by transform name
     (`TRANSFORM_PARAMETER_KEYS`).
  6. Two existing self-tests whose own fixtures became inconsistent
     under fix #4's stricter rule were corrected to remain internally
     consistent (one rewritten to test the new consistency rule
     directly; one's duplicate-record construction adjusted to keep its
     copied record's real fields matching its record_id).
  No confidently-wrong output, cleanup/restoration-on-failure gap, or
  registry/cardinality drift was found; the reviewer's report is
  preserved in this session's transcript.
- Files changed: `backend/tests/contracts/__init__.py`, `schema.py`,
  `taxonomy.py`, `loader.py`, `runner.py`, `transforms.py`,
  `mutation_registry.py`, `adapters/__init__.py`,
  `adapters/{location,salary,experience}.py`,
  `records/{location,salary,experience}.json`, `test_harness_self.py`,
  `test_harness_import_boundary.py`,
  `test_{location,salary,experience}_contract.py`,
  `backend/scripts/contract_mutation_witnesses.py`, this handoff entry.
  No production parser, existing fixture, existing parser test,
  verifier, workflow document, hook, metadata validator, dependency
  file, or other version-bearing consumer touched.
- Mutation-witness acceptance run (per binding clarification: run all
  34 active witnesses now, not added to routine pytest or `verify.py`):
  `python -m scripts.contract_mutation_witnesses` — **34 passed, 0
  failed**, each asserting both the documented erroneous output under
  its mutant and the documented restored output matching its contract
  record; superseded g07 correctly reported as having no witness, by
  design, separately from the 34.
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass (17
  new source files). `python -m scripts.check_repo` exits 0. Genuine
  external `python -m scripts.verify --level routine --focus
  tests/contracts/test_location_contract.py
  tests/contracts/test_salary_contract.py
  tests/contracts/test_experience_contract.py
  tests/contracts/test_harness_self.py
  tests/contracts/test_harness_import_boundary.py` — all 11 steps PASS:
  **102 focused / 2295 full-suite tests**. (One full-suite run
  immediately prior showed 2 unrelated failures in
  `test_collection_run_provider_attempts.py`/`test_ingestion_pipeline.py`
  — both passed individually in isolation and the full suite passed
  cleanly at 2295/2295 on the very next run with no code change in
  between; recorded here as a one-off database-state artifact from the
  disposable database container being freshly rebuilt that run, not a
  regression from this slice, which touches no ingestion/database
  code.)
- Deviations/known limitations: only the 34 primary-witness records are
  committed (no additional generated/transformed records) — within
  scope, since binding clarification 10 requires exactly one primary
  witness per active guard but does not mandate additional records.
  Fingerprint staleness detection is file-level, not anchor/region-level
  (disclosed in the module docstring, not overclaimed). `experience/g07`
  is a permanent historical record with no witness, by design.
- STOP — this is Slice 2 only. Do not implement Slice 3 (fast/final
  verifier profiles, durable receipts, metadata-schema split, workflow-
  version activation), touch any production parser/fixture/existing
  test, or begin another Phase 3/4 parser. Do not merge without separate
  explicit user authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: tooling
verification_level: routine
focused_test_selector: tests/contracts/test_location_contract.py tests/contracts/test_salary_contract.py tests/contracts/test_experience_contract.py tests/contracts/test_harness_self.py tests/contracts/test_harness_import_boundary.py
focused_test_count: 102
full_suite_count: 2295
```

---

## Iteration 2

### Work done

- Date/agent: 2026-09-13, Claude Code (Sonnet 5). Risk class R
  (unchanged). Base -> ending commit: `d8c2c09` -> this commit; same
  branch `tooling/workflow-v3.2-slice2-contract-harness`. Bounded
  correction pass applying Sol's five re-review findings against the
  frozen Slice 2 implementation, relayed as text (no separate `###
  Work review` commit exists on this branch or its origin prior to
  this one). Scope held exactly to the harness's own files, per the
  correction's explicit boundary — no production parser, workflow-
  version consumer, or Slice 3 file touched.
- Five findings addressed:
  1. **Import boundary strengthened for equivalent forms/aliases** —
     `test_harness_import_boundary.py`'s detectors now catch `from app
     import normalization` (an equivalent whole-module bind, not just
     `import app.normalization`) and alias-resolved dynamic calls (e.g.
     `from importlib import import_module as load; load(...)`), via a
     new import-alias map that resolves any locally-bound name back to
     its canonical dotted origin before checking it against the banned
     set. Two new isolated synthetic regressions added.
  2. **Expected-output validation made genuinely parser/field-
     discriminated** — replaced the generic "str or int" check with
     `schema.OUTPUT_FIELD_TYPES` (location's four fields: `str`;
     salary/experience numeric bounds: `int`; salary currency/period:
     `str`), enforced in `loader._load_expected_output`. `bool` is
     still rejected outright before the field-specific check runs
     (Python's `bool` is an `int` subclass). `None` is still accepted
     only paired with `unavailable` provenance (unchanged, `ExpectedField`'s
     own invariant).
  3. **Record traceability enforced**: a record_id's slug must start
     with its own `parser` name; a base record's record_id/transform
     must be `variant-base`/`transform-none`; a generated record must
     never use `variant-base` (reserved, so record_id alone signals
     kind); a base record's `historical_defect_ref` must equal its
     guard inventory entry's; and (in `collect_all`, requiring the
     full three-file set) a generated record's `base_record_id` must
     resolve to an actual **base** record (never another generated
     record) sharing its parser, guard_ref, `original_input`, and
     `target` exactly.
  4. **`contract_mutation_witnesses.py` now loads records through the
     fail-closed loader** (`tests.contracts.loader.collect_all`),
     never raw `json.loads`. Before running any witness, it now
     requires: the registry's declared record exists in the loaded
     set; it is that guard's designated primary witness; its
     parser/guard_ref agree with the registry entry; and the
     registry's own `input_` is byte-for-byte identical to the
     record's `expected_transformed_input`. The restored-output
     assertion now compares against the loaded record's own
     `expected_output` directly, not a second raw JSON read.
  5. **Experience-adapter docstring corrected**: it previously implied
     the non-target field is always `None`; corrected to state that a
     record may deliberately populate both `title` and `description`
     together for a cross-source witness (e.g.
     `experience/g05-internal-conflict-precedence`, whose own record
     does exactly this), with `target.input_field` naming the field
     the guard's mechanism most centrally concerns, not "the only
     non-null one."
- Finding 5's docstring edit changed `adapters/experience.py`'s own
  file bytes, which correctly triggered a `STALE adapter fingerprint`
  failure for all 21 experience guards on the next witness run
  (confirming the staleness check, corrected in Iteration 1, genuinely
  fires on a real, intentional change). Recomputed and re-froze only
  `_FROZEN_ADAPTER_FP["experience"]` (`03c559ec88386dc7` ->
  `dfa142423607a5a3`); every other frozen fingerprint (both other
  adapters, all three parser sources, all 34 records) is byte-identical
  to Iteration 1's baseline, confirmed by recomputing all of them fresh
  and diffing.
- Direct fault-injection tests added for every accepted-invalid case
  above: 2 new import-boundary synthetic regressions (finding 1); 5 new
  loader tests covering wrong-type values for each parser/field
  combination plus a bool-still-rejected control (finding 2); 9 new
  loader tests covering the parser-prefix mismatch, base-transform/
  variant misuse, generated-variant-base masquerade, historical_defect_ref
  disagreement, generated-record chaining to a non-base record, and
  generated-record original_input/target mismatches (finding 3); 6 new
  tests exercising `_check_record_matches_registry_entry` directly
  (missing record, non-primary witness, guard/parser/input mismatches,
  and the real matching case) (finding 4).
- Files changed: `backend/scripts/contract_mutation_witnesses.py`,
  `backend/tests/contracts/adapters/experience.py`,
  `backend/tests/contracts/loader.py`,
  `backend/tests/contracts/mutation_registry.py` (frozen adapter
  fingerprint re-freeze only),
  `backend/tests/contracts/schema.py`,
  `backend/tests/contracts/test_harness_import_boundary.py`,
  `backend/tests/contracts/test_harness_self.py`, this handoff entry.
  No production parser, existing fixture, existing parser test,
  verifier, workflow document, hook, metadata validator, dependency
  file, or other version-bearing consumer touched. The corrected
  35-historical/34-active/1-superseded inventory is unchanged (asserted
  fresh at import time, confirmed).
- Mutation-witness acceptance run: `python -m
  scripts.contract_mutation_witnesses` — **34 passed, 0 failed**
  (re-run after the adapter-fingerprint re-freeze above).
- Verification: `ruff format --check`/`ruff check`/`mypy` all pass.
  `python -m scripts.check_repo` exits 0. Genuine external `python -m
  scripts.verify --level routine --focus
  tests/contracts/test_location_contract.py
  tests/contracts/test_salary_contract.py
  tests/contracts/test_experience_contract.py
  tests/contracts/test_harness_self.py
  tests/contracts/test_harness_import_boundary.py` — all 11 steps PASS:
  **123 focused / 2316 full-suite tests** (both counts grew by exactly
  21, matching the 21 new fault-injection/regression tests added across
  the two test files).
- Deviations/known limitations: unchanged from Iteration 1's disclosed
  limitations. No new limitations introduced — this pass only tightens
  validation and traceability; no behavior change to any of the 34
  primary-witness records' own expected outputs.
- STOP — this is still Slice 2 only, now corrected. Do not implement
  Slice 3, touch any production parser/fixture/existing test, or begin
  another Phase 3/4 parser. Do not merge without separate explicit user
  authorization.

```workflow-metadata
workflow_version: v3.1-pilot
slice_kind: tooling
verification_level: routine
focused_test_selector: tests/contracts/test_location_contract.py tests/contracts/test_salary_contract.py tests/contracts/test_experience_contract.py tests/contracts/test_harness_self.py tests/contracts/test_harness_import_boundary.py
focused_test_count: 123
full_suite_count: 2316
```
