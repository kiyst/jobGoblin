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

---

## Iteration 2

### Work done

- Date/agent: 2026-09-27, Claude Code (Sonnet 5). Same slice, same
  authorization (`slice_id: 2026-09-27-realistic-corpus-freeze-evaluation-
  0dae468`, risk class **H**, `slice_kind: tooling`, `declared_gate: final`).
  Same branch `phase-3/realistic-corpus-freeze-evaluation`, on top of the
  existing pushed Stage 1 checkpoint `7644e20e30fdde6e38a840e3b621b6217b93
  ce14`, preserved unamended. One bounded correction round for Sol's Stage 1
  pre-annotation review verdict (**CHANGES REQUESTED**, six findings, F1/F2/
  F4 High, F3 High, F5/F6 Medium). No annotation pass, adjudication, corpus
  freeze, baseline evaluation, provider contact, database work, parser-
  semantic change, or new workflow tooling performed. Ending commit: this
  commit.
- **F1 (rubric not implementation-independent)**: replaced parser-relative
  labeling with an implementation-independent semantic ground truth --
  `present_supported` now means the sourced field(s) unambiguously supply a
  value representable by the field's closed canonical output domain
  *regardless of current parser recognition*; `present_unsupported_form`
  means the domain genuinely cannot represent the stated value (with the
  honest consequence, stated explicitly, that this outcome cannot arise at
  all for the four free-text fields whose domain is "any non-empty string").
  Added a closed **source-field table** (title+description pooled for the
  three scalars/experience/skills; `compensation_text` only for salary;
  `location_raw` only for location -- and the explicit rule that a value
  stated elsewhere, e.g. in `description` when `compensation_text` is null,
  is still `absent` for that annotation). The rubric now states plainly it
  requires no parser-implementation access.
- **F2 (pass schema undocumented)**: added the complete exact annotation-
  pass JSON schema to the rubric -- all six top-level fields, record-id
  format, scalar/composite/skills nesting, closed per-label keys, timestamp
  format, and a compact valid example (2-id synthetic taxonomy for brevity).
- **F3 (silent duplicate-JSON-key acceptance)**: both `load_annotation_pass`
  and `load_adjudication_audit` now parse with
  `object_pairs_hook=evaluate_phase3_corpus._reject_duplicate_keys` -- the
  one authoritative fail-closed mechanism, imported directly rather than
  reimplemented, so duplicate-key behavior can never drift between the two
  modules. Rejects duplicates at every nesting level (recursive by
  construction). Four new regressions: top-level and nested duplicates, for
  both the pass and adjudication-audit schemas.
- **F4 (adjudication/audit identity not enforced)**: `adjudicated_by` and
  `audited_by` must now equal exactly `"user"` (`_REQUIRED_HUMAN_IDENTITY`)
  -- previously only checked "non-empty string", so an agent/model identity
  could reach the hardcoded `annotator_role: "adjudicated:user"` label. Two
  new regressions (non-`"user"` `adjudicated_by`/`audited_by` rejected).
- **F5 (no field-aware value validation before audit)**: exposed
  `evaluate_phase3_corpus._EXPECTED_VALUE_VALIDATORS` as public
  `EXPECTED_VALUE_VALIDATORS` (pure rename, only reuse-motivated change to
  that file, no metric/parser-behavior change) and reused it in both
  `_validate_raw_label` (pass loading) and `_final_label_from_adjudication`
  (adjudicated values) via one shared `_validate_expected_value_for_field`
  helper -- invalid `remote_type`/`employment_type`/`seniority` values,
  bool-as-int numeric values, and invalid adjudicated values are now
  rejected during pass/adjudication loading, before any human audit work,
  not only later by `build_corpus`'s end-of-pipeline self-check. Three new
  regressions (invalid `remote_type` and bool-as-int `experience.minimum`
  in a pass; an invalid adjudicated `seniority` value).
- **F6 (racy existence-check-then-rename)**: replaced the
  check-then-`Path.rename()` sequence with `verification_receipts.
  write_receipt_atomic`'s proven primitive, reimplemented locally for
  `FreezeBuilderError` and corpus-specific JSON formatting: same-directory
  temp file, write + `flush()` + `os.fsync()`, `load_corpus` self-check
  against the temp file, then `os.link(temp, output_path)` -- create-if-
  absent is now the filesystem's own guarantee (`FileExistsError`), not a
  race-prone check in this process; the temp file is always unlinked in a
  `finally`. One new race/fault-injection regression: a monkeypatched
  `load_corpus` call injects a competing writer's sentinel file at the
  exact point between self-check and publication; proves the destination
  is left byte-identical to the sentinel and no temp file leaks.
- Because the rubric changed before any annotation exists, `RUBRIC_VERSION`
  bumped `1.0.0 -> 1.0.1`. **Historical, superseded evidence** (never
  annotated against): `rubric_version: 1.0.0`, rubric sha256
  `bb4c8ac44ccb7bf6c0978d36bb4350449076df032e337ef6a8b03a651ee2ade0`,
  `source_packet_hash 867e5b6d30a4fc858de3146122437ca03a936936c8f88ddc034
  8ab5dedb92957` (all recorded in superseded commit `7644e20`). **Current**:
  rubric sha256
  `47f833d80eb37c8046fc6b243e53fbeaa4cdab78c6b71a52748ecb42e7106f2c`,
  `source_packet_hash 914ebc5700a4baf9f7b15d25e109ea86d647ef9c8d5bd2fb8e04c
  db608299651` (taxonomy/salvage hashes unchanged from Stage 1).
- Verification: `ruff format --check`/`ruff check` clean on all four
  touched files; `mypy` clean on both scripts; full backend suite **3107
  passed** (was 3097; +10 = the F3/F4/F5/F6 regressions above); `check_repo.
  py` clean; `git diff --check` clean.
- Adversarial self-review: confirmed the F4 identity check is a strict `==`
  (not merely "truthy"), so an empty string or a look-alike role string both
  still fail; confirmed `_validate_expected_value_for_field` is a single
  shared choke point called from both the pass-loading and adjudication-
  resolution paths (no second copy to drift); confirmed the F6 race
  regression genuinely exercises the code path between self-check and
  `os.link` (not merely the earlier fast-fail check) by injecting the
  competing write from inside a monkeypatched `load_corpus`, the last call
  before `os.link`; confirmed the rubric's per-field domain table's "this
  outcome cannot occur" claims for `salary.currency`/`salary.period`/
  `location.*` against `EXPECTED_VALUE_VALIDATORS`'s actual validators
  (`_is_non_empty_str` for all eight) rather than asserting it from
  intuition.
- Files changed: `docs/evaluation/phase3-realistic-annotation-rubric.md`
  (rewritten sections, `rubric_version` bump), `backend/scripts/
  freeze_phase3_realistic_corpus.py` (F3/F4/F5/F6 fixes), `backend/tests/
  test_freeze_phase3_realistic_corpus.py` (31 -> 41 tests), `backend/
  scripts/evaluate_phase3_corpus.py` (one rename only, F5 reuse), `docs/
  LLM_HANDOFF.md` (this entry, plus the iteration rotation above).
- STOP -- this remains a checkpoint within an incomplete slice, not a
  candidate. No annotation pass, adjudication, corpus freeze, baseline
  evaluation, provider contact, database work, parser change, title
  normalization, `R`, merge, `M`, or `Q` is authorized by this commit.
  Waiting for Sol's re-review of the corrected Stage 1 checkpoint.
