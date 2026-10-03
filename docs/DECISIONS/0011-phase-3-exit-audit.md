# 0011 — Phase 3 exit audit and closure

## Status

Accepted. Phase 3 exit-audit slice (`phase-3/exit-audit`, risk class D, `slice_kind:
docs`, `gate: docs`), base `b31916827c07715bb59f430ad52dd0193561c35b`. This ADR is the
durable Phase 3 closure artifact. Its contract is the implementer's read-only exit-audit
proposal, Astra's phase-gate review of decisions D1/D2 with its evidence corrections, and
Sol Medium's primary-review approval adopting those amendments and one binding
clarification. It changes no executable file, fixture, test, schema, migration, or
configuration.

[ADR 0010](0010-realistic-evaluation-corpus-methodology.md) stays unchanged as a
historical, point-in-time record. Its context sentence "Title normalization remains
unimplemented" was true when written. This ADR supersedes that sentence as a description
of current state; it does not edit it.

## Closure statement

> Phase 3 deterministic parser contracts are complete within their approved conservative scope. Production normalization composition, parser-version persistence, provider-field mapping, and useful live-data coverage are not complete. Closure does not authorize Phase 4 implementation or normalized persistence; the recorded integration preconditions remain binding.

## Context

The audited state is `main` = `origin/main` = `b31916827c07715bb59f430ad52dd0193561c35b`,
which is `Q` for the title-normalization merge `M` =
`a3c1c12053e7990b88e2c01f6736425cb59f3453`.

Committed verification evidence relied on, not rerun for this audit:

- Receipt `1541f94b-45fe-49ef-af52-2afd39fcb367`
  (`docs/verification-receipts/4c6f933fb3112357f6a96f751115776e74831d73/`): candidate
  `C2` = `4c6f933`, `gate: final`, full suite 3,470 passed, 34/34 registered mutation
  witnesses passed, `approval_eligible: true`.
- Post-merge artifact `bb3ce6d0-5c3f-4791-a5a9-fcd61fb6a56e`
  (`docs/post-merge/a3c1c12053e7990b88e2c01f6736425cb59f3453/`): verification of the
  merged tree at `M`, all 11 steps PASS, full suite 3,470 passed, 34/34 witnesses passed,
  no migration triggered, worktree snapshots identical and cleanup PASS.

The 34 registered witnesses are experience 21, location 8, and salary 5. The title
classifier's 12 frozen witnesses are ordinary tests in
`tests/test_normalization_titles.py` (`test_witness_*`). Each was proven load-bearing at
slice time and runs inside the full suite.

## Parser inventory

All eight parser areas named by the Phase 3 exit gate exist on `main`. Paths are relative
to `backend/`.

| Area | Entry point | Result | Fixture (cases) | Test module |
|---|---|---|---|---|
| Title | `app/normalization/titles.py::classify_title` | `TitleResult` | `tests/fixtures/normalization/title_cases.json` (200) | `tests/test_normalization_titles.py` |
| Salary | `app/normalization/salary.py::classify_salary` | `SalaryResult` | `salary_cases.json` (105) | `tests/test_normalization_salary.py` |
| Location | `app/normalization/location.py::classify_location` | `LocationResult` | `location_cases.json` (125) | `tests/test_normalization_location.py` |
| Remote type | `app/normalization/remote.py::classify_remote_type` | `NormalizationResult[RemoteType]` | `remote_type_cases.json` (77) | `tests/test_normalization_remote.py` |
| Employment | `app/normalization/employment.py::classify_employment_type` | `NormalizationResult[EmploymentType]` | `employment_type_cases.json` (80) | `tests/test_normalization_employment.py` |
| Seniority | `app/normalization/seniority.py::classify_seniority` | `NormalizationResult[Seniority]` | `seniority_cases.json` (91) | `tests/test_normalization_seniority.py` |
| Experience | `app/normalization/experience.py::classify_experience` | `ExperienceRange` | `experience_cases.json` (90) | `tests/test_normalization_experience.py` |
| Skills | `app/normalization/skills.py::classify_skills` (with `app/normalization/taxonomy.py` and `app/taxonomy/skills.yaml`) | `list[SkillMatch]` | `skill_cases.json` (98) | `tests/test_normalization_skills.py`, `tests/test_normalization_taxonomy.py` |

## Independently verified audit evidence

The implementer reproduced these checks read-only and offline at `b319168`. Astra
independently verified them.

1. **Runtime and provenance sweep.** The sweep collected 940 distinct input strings: every
   string-valued `title`, `description`, `location`, and `compensation_text` in the eight
   normalization fixtures, plus the `title`, `description`, `location_raw`, and
   `compensation_text` fields of the 30 frozen-corpus records.
   - The five title/description parsers (remote, employment, seniority, experience,
     skills) were each called twice per string: once as `(s, None)` and once as `(s, s)`.
   - `classify_salary`, `classify_location`, and `classify_title` were each called once
     per string.
   - That is 12,220 parser invocations. None raised an exception, and none returned a
     `NormalizationResult` or `SkillMatch` carrying `explicit_source` or
     `structured_metadata`.
   - This result holds for these inputs and this invocation pattern only. It is not a
     proof over all inputs.
2. **Evaluator output.** `python -m scripts.evaluate_phase3_corpus` produced:
   - 91,994 bytes;
   - 1,366 CRLF-terminated lines with a final newline;
   - UTF-8 SHA-256
     `87a92187a2d37d5150fe998d06042449f6b74d540cecd15d1bba97dd94801de6`.

   This is the same hash Sol recorded for the title slice. The frozen corpus, its
   annotations, and the evaluator are unchanged since that review.
3. **Transitive import closure.** Importing all ten normalization modules in a fresh
   interpreter loads only these application modules: `app.normalization.*`,
   `app.schemas`, and `app.schemas.identifiers`. Beyond the standard library, it loads
   only one third-party package, `yaml`.
4. **Salary annotations.** There are 120 salary-component annotations (30 records × 4
   components):
   - 100 are `present_supported` with missing wired input;
   - the other 20 are `absent`, with zero false positives.

### Scope of the realistic-corpus evidence

The realistic corpus evaluates **seven** parsers, not eight: remote type, employment,
seniority, experience, salary, location, and skills. Title is not an evaluator field.

The 30 realistic title cases in `title_cases.json` are byte-identical to the frozen-corpus
titles. The test `test_realistic_titles_are_byte_identical_to_the_frozen_corpus` enforces
this. Their outcomes are 22 matched, 6 unsupported, and 2 ambiguous. They are
primary-reviewer-approved smoke/regression expectations only. They are never accuracy,
holdout, coverage, precision, recall, or generalization evidence.

Current evaluator results for the combined split (30 records):

- zero runtime failures (0/30 for each of the seven parsers);
- zero `confidently_wrong` values;
- zero false positives in every applicable category (`absent`,
  `present_unsupported_form`, `ambiguous`);
- skills recall 37/40;
- 159 mismatches: 100 `missing_wired_input_gap` (all salary), 56 `supported_abstention`,
  and 3 `recall_miss` (all `skills.golang`).

These zero-wrong-value and zero-false-positive findings apply to this frozen 30-record
corpus and this evaluator invocation only. They are not a production accuracy claim and
not a claim about other employers, sources, or text.

## Requirement-to-evidence matrix

Requirements are quoted from `docs/PHASE_RISK_CHECKLIST.md`'s Phase 3 section.

### Entry checks

| Requirement | Evidence | Status |
|---|---|---|
| Raw fields and provenance storage are stable. | `jobs.field_provenance`, `jobs.description_raw`, `location_raw`, `compensation_text`, `raw_job_ingestions.raw_payload`, and `raw_job_ingestions.parser_version` exist ([DATA_MODEL.md](../DATA_MODEL.md)). The latest migration is `0017_job_notes` (Phase 1); Phase 3 added no migration. | Satisfied |
| Each parser has an explicit unknown outcome. | `NormalizationResult.__post_init__` enforces value `None` if and only if `Provenance.UNAVAILABLE` (`app/normalization/types.py`). Composite results carry one `NormalizationResult` per component. Title adds a closed `TitleOutcome` (`matched`/`no_title`/`unsupported`/`ambiguous`). Skills documents an empty list as "no skill recognized" (`skills.py` module docstring), with provenance assigned per match. | Satisfied |

### Required prevention

| Requirement | Evidence | Status |
|---|---|---|
| Keep parsers pure: text/value in, normalized value plus provenance out. | Each module exposes one `classify_*` function that performs no I/O. Each test module has a `test_classify_*_is_deterministic` test. Taxonomy file I/O happens only in the explicit `load_taxonomy(path)` call, whose result is passed into `classify_skills`; nothing is loaded at import time. | Satisfied |
| Separate extraction from product filtering/scoring policy. | No `matching/` package exists. Outside `app/normalization/`, nothing in `app/` imports a Phase 3 parser. Ingestion imports only the pre-Phase-3 `normalization/url.py`, and the ORM imports only `normalization/company.py` (see "Out of Phase 3 scope" below). | Satisfied |
| Preserve raw input and parser version. | Raw input is preserved: parsers are pure and never mutate inputs, and the raw storage columns exist. `RawJobIngestion.parser_version` already exists as a nullable storage column. Phase 3 defines no normalization-version value and no version threading. | Conditional at the pure-parser boundary; binding precondition D1 below |
| Test negative and ambiguous examples as heavily as happy paths. | See "Boundary and ambiguity coverage" below. | Satisfied |
| Prefer `NULL` over a low-confidence guess. | On the current corpus run: zero `confidently_wrong` values and zero false positives in every applicable category, with 56 supported abstentions. | Satisfied, within the corpus scope stated above |
| Build a regression corpus from realistic captured payloads with sensitive information removed. | Frozen corpus `tests/fixtures/evaluation/phase3_realistic_corpus.json`: 30 records, 840 labels, employer-disjoint 20 dev / 10 holdout, fully adjudicated. Methodology, sanitization, and lineage are in ADR 0010; first exposure is in `docs/evaluation/phase3-realistic-corpus-baseline-report.md`. | Satisfied; limitations L5–L7 below |

### Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| Title, salary, location, remote type, employment, seniority, experience, and skill parsers pass table-driven positive, negative, boundary, and ambiguity tests. | All eight exist (inventory above). Each has a parametrized fixture-driven suite, and all passed in the receipt and post-merge artifact above (3,470 tests). | Satisfied |
| Parsed/derived/inferred values cannot appear as explicit-source facts. | See "Provenance safety" below. Nothing persists parser output yet. | Satisfied as an implementation/test result |
| No parser imports providers, ORM models, UI code, or network clients. | Seven parsers each have an exact AST allow-list test (`test_import_boundary_allow_list`) with a synthetic rejection test. Title has an exact-set test (`test_module_imports_only_the_allowed_pure_modules`). Taxonomy has a deny-list test (`test_taxonomy_module_has_no_forbidden_imports`). The transitive closure check is clean. | Satisfied |

### Import boundary detail

Standard-library imports are ordinary and are not listed as boundary concerns: `re`,
`unicodedata`, `dataclasses`, `typing`, `enum`, `collections.abc`, `types`, and
`pathlib`.

Application imports:

- every parser except skills imports only `app.normalization.types`;
- `skills.py` additionally imports `app.normalization.taxonomy` and
  `app.schemas.identifiers`;
- `titles.py` additionally imports `app.schemas.identifiers`;
- `taxonomy.py` imports `app.schemas.identifiers`.

Third-party imports: `yaml` in `taxonomy.py` only. No parser imports `app.db`,
`app.providers`, `app.ingestion`, `app.services`, `app.api`, an HTTP/network client, or an
ORM/database driver.

### Provenance safety

The shared `Provenance` enum is permissive: it includes `EXPLICIT_SOURCE` and
`STRUCTURED_METADATA`, and `NormalizationResult` would accept either. The guarantee that
parser output never claims explicit or structured provenance is therefore an
implementation/test result, not a type-level or universal guarantee. It rests on:

- no parser module assigns either member in code; the only mentions are in the `salary.py`
  and `titles.py` docstrings, which explain why those tags are never emitted;
- `test_every_result_uses_only_inferred_or_unavailable_provenance` in the title tests;
- every fixture case pins its exact expected provenance;
- the 12,220-invocation sweep above.

Any future parser, composition layer, or provider mapping that assigns those tags must be
reviewed against [DATA_MODEL.md's Provenance section](../DATA_MODEL.md#provenance).

### Boundary and ambiguity coverage

Raw counts of value-expecting versus abstaining fixture cases are not a rigor measure, are
not comparable across parsers, and are not offered as evidence of equal rigor. The
substantive evidence is:

- **Title:** explicitly labelled categories (42 positive, 27 negative, 27 boundary, 17
  ambiguity, 21 collision, 36 Unicode, 30 realistic) and 12 load-bearing witnesses.
- **Experience, location, salary:** named boundary, conflict, and Unicode fixture cases,
  plus registered mutation witnesses (21, 8, and 5) run under every `gate: final`
  receipt.
- **Remote type, employment, seniority, skills:** named adversarial cases (by `origin:
  synthetic_adversarial`: remote 50, employment 54, seniority 46, skills 56) covering
  conflicts, rejected near-misses, and boundary forms, plus dedicated tests. Skills also
  covers the ambiguous aliases `c`/`r`/`go`/`node` with a closed anchor rule and fail-closed
  Unicode boundary handling. These four parsers have no registered mutation witnesses. The
  exit gate does not require them.

Only the title fixture labels categories in a schema field. For the other seven, boundary
and ambiguity coverage is identified by case IDs, notes, and dedicated tests.

## Parser-contract completion vs. production readiness

The eight parser contracts are complete within their approved conservative scope. That is
not production readiness:

- no parser is wired into ingestion;
- no normalized value is persisted;
- no parser-version identifier exists;
- providers do not map fields into parser inputs (salary receives no input on the corpus);
- live-data coverage is low (L1 below).

## Accepted conservative limitations

These are recorded as known limitations. They are neither production-readiness claims nor
new Phase 3 failures, and no Phase 3 criterion sets a coverage or recall threshold. ADR
0010 states that no pass threshold is defined.

- **L1 — Low realistic supported-field coverage.** Supported cases the parser abstained
  on: `remote_type` 23/23, `experience.minimum` 14/14, `location.state` 3/3,
  `location.country` 10/15 (5/15 correct). These abstentions are safe but extract little
  from real Greenhouse text.
- **L2 — Three exposed Go recall misses.** The `skills.golang` misses
  `gitlab:8463922002`, `gitlab:8490477002`, and `gitlab:8514960002` are all
  already-exposed GitLab holdout records.
- **L3 — Deliberate city abstention.** `location.city` is never populated (0/6 supported
  cases) by approved design: no gazetteer exists.
- **L4 — Salary composition/input gap.** 100 of 120 salary-component annotations are
  `present_supported` with missing wired input, because `classify_salary` reads only
  `compensation_text`, which is empty for these postings. Supplying input is
  provider-composition work, not a parser defect.
- **L5 — Three country-provenance differences.** Three `location.country` values are
  correct but tagged `parsed_description` where annotators expected `inferred`. Neither
  tag claims explicit or structured provenance.
- **L6 — Exposed/burned holdout.** All 10 GitLab holdout records were exposed by the
  baseline run. The `gitlab:8512432002` Go recovery is informational only, never fresh
  generalization evidence. The corpus is 30 records from three employers, all Greenhouse.
- **L7 — No automated realistic-output enforcement for seven parsers.** Only the title
  tests read the frozen corpus. For the other seven parsers, realistic results are
  protected only by the evaluator-output hash comparison recorded at review time.
  Precondition D2 below closes this before normalized persistence.

## Binding integration preconditions

These preconditions bind any future slice, in any phase, that would persist a Phase 3
classifier result. Phase 3 closure does not satisfy them and does not authorize the work
they govern.

### D1 — Parser version

> Before any Phase 3 classifier result is first persisted—including through a development, fixture, backfill, or live-provider path—the normalization integration must define and verify a deterministic parser-version identifier bound to the implementation and any taxonomy or configuration affecting its output. Every persisted result must be traceable to its preserved source input, parser version, and field provenance. Missing or unresolvable version evidence must prevent that normalized write. This must be independently reviewed and tested before the write path is enabled. Raw acquisition or storage alone does not authorize normalization persistence.

Clarifications:

- `RawJobIngestion.parser_version` already exists as a nullable storage column. No code
  writes it today.
- Phase 3 defines no normalization-version value and no version threading.
- Parser-version compliance is therefore conditional at the pure-parser boundary: Phase 3
  parsers cannot violate it because they persist nothing, and nothing may persist their
  output until D1 is met.
- A single combined normalization-pipeline version is permitted, provided it
  deterministically identifies every relevant parser, taxonomy, and configuration input.
- The lack of a current consumer is not, by itself, the justification for this deferral.
  The version identifier must be designed against the actual persisted-write contract it
  protects, and that contract does not exist until normalization integration.

### D2 — Executable realistic-output protection

Before normalized persistence, executable protection over the realistic corpus must:

- reject runtime failures, confidently-wrong values, and false positives in every
  applicable category;
- preserve the demonstrated supported-value coverage separately per component, including
  skills recall, so a regression in any one component fails on its own;
- test provenance separately from value correctness;
- keep zero-coverage and missing-input components (for example `location.city` and the
  salary components) explicitly unproven, never treated as passing;
- avoid both a single giant output snapshot and a gate that checks only for zero false
  positives.

### Other deferred integration obligations

Each item below is deferred to a separately authorized integration slice, subject to D1
and D2. None is authorized here.

- Provider-field mapping into parser inputs, including salary input composition.
- `jobs.field_provenance` writes and the merge rule that never overwrites
  `explicit_source` with weaker provenance.
- Persisting `jobs.normalized_title`/`job_family`, the other normalized `jobs` columns, and
  the deferred `job_skills` table.
- Applying taxonomy resolution to `candidate_skills` or `saved_search_titles`; this waits
  for an actual matching consumer.

## Out of Phase 3 scope

`app/db/models/company.py` imports `app.normalization.company.normalize_domain`. This
contradicts the `db/` row of [ARCHITECTURE.md §5](../ARCHITECTURE.md#5-dependency-boundaries).
The import predates Phase 3: it is a Phase 1 domain-canonicalization helper documented in
DATA_MODEL.md's `companies` section, not one of the eight Phase 3 parsers. It is recorded
here as a pre-existing exception and is not a Phase 3 exit-gate finding.

## Consequences

- Phase 3 is closed. The roadmap records the closure statement above.
- Phase 4 still requires its own entry review per `docs/PHASE_RISK_CHECKLIST.md`, its own
  proposal, and separate user authorization. This ADR does not begin Phase 4.
- Any slice that would persist a classifier result must show D1 and D2 satisfied, with
  independent review, before its write path is enabled.
- Reopening a parser contract, for example to recover the L2 misses or improve L1
  coverage, is a new, separately authorized slice. It must follow ADR 0010's
  exposed-holdout rules.
