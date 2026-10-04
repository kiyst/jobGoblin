# 0014 — Pure posting composition and scoped D2 protection

## Status

Accepted with Phase 4 Slice 2 (`phase-4/pure-posting-composition-s2`, risk class H,
`slice_kind: parser`, `gate: final`), base `0c2c14b573609c6b2dfc67c0d9f14de97c31e03d`
(`Q` of the S1 merge). Pilot product slice 2 of 3 under
[ADR 0012](0012-workflow-throughput-protocol-pilot.md).

Its contract is the implementer's consolidated S2 proposal as amended by Sol Medium's
binding proposal review (amendments A1–A12) and the user's decisions U1–U7, integrated
into one frozen contract. This ADR supersedes only the five-slice table in
[ADR 0013](0013-direct-greenhouse-job-board-provider.md); every other part of ADR 0013,
and all of [ADR 0011](0011-phase-3-exit-audit.md), is unchanged.

## Context

ADR 0011 left two binding integration preconditions: D1 (a deterministic parser version
before any normalized write) and D2 (executable realistic-output protection). Only the
title tests read the frozen realistic corpus (ADR 0011 limitation L7). ADR 0013 said D2
must be satisfied before the first provider-to-parser mapping slice, and planned S2 as
composition, HTML conversion, and D2 together.

The user split that plan (U1): this slice delivers the pure composition and D2 alone, so
that D2 is reviewed and merged before any provider field reaches a parser.

## Decision

### 1. Composition boundary

`backend/app/normalization/posting.py` defines:

- `PostingInputs(title, description, location)`: provider-neutral, each `str | None`,
  plain text only, no compensation field, and no normalization of its own;
- `NormalizedPosting`: `inputs`, `title`, `remote_type`, `employment_type`, `seniority`,
  `experience`, `location`, and `skills` (a tuple). There is no salary attribute;
- `normalize_posting(inputs, *, taxonomy)`.

Contract:

- **Validation first.** The argument must be a `PostingInputs` instance and each field
  `str` or `None`; otherwise a fixed, categorical `TypeError` with no interpolated value
  is raised before any parser runs.
- **Fixed order and wiring.** `classify_title(title)`; then `classify_remote_type`,
  `classify_employment_type`, `classify_seniority`, `classify_experience`, each
  `(title, description)`; then `classify_location(location)`; then
  `classify_skills(title, description, taxonomy=taxonomy)`. This keeps the evaluator's
  relative order with title added first. A parser exception propagates immediately and no
  later parser runs.
- **Pass-through.** `result.inputs is inputs`, and every parser result is the identical
  object the parser returned. Skills are the only container exception: a new tuple of the
  identical `SkillMatch` objects, in order. No value or provenance is assigned,
  rewritten, merged, filtered, scored, or reconciled across fields. Results can be
  parser-owned shared objects, so callers must never mutate them.
- **Purity.** No I/O, logging, global state, or import-time loading; the taxonomy is a
  required keyword argument. An exact AST import allow-list admits only `__future__`,
  `dataclasses`, `app.normalization.types`, and the seven composed parser and taxonomy
  modules.
- **Salary excluded.** No compensation input, no salary output, and no salary import. ADR
  0011 limitation L4 stays open.
- **No provider types.** Nothing in the composition sees `DiscoveredJob`, a raw payload,
  or a provider field. Nothing at runtime calls it.

### 2. D2 at the composition boundary

`backend/tests/test_normalization_posting_realistic.py` is the durable D2 contract. It
calls `normalize_posting` once per record of the frozen 30-record corpus, scores every
component with an independent minimal scorer, and compares the results with literal
committed expectations:

- the exact 30-record ID universe and every component's annotation partition;
- per component: exact correct `{record_id: value}` maps, supported-abstention sets,
  confidently-wrong sets, and false-positive sets for the absent, unsupported-form, and
  ambiguous outcomes;
- the four salary missing-input sets, taken from the evaluator while salary stays outside
  composition;
- skills recall-hit, known-miss, and false-positive sets;
- the title smoke expectations, provenance exceptions, covered and unproven lists, and
  headline totals.

It also proves those literals are exhaustive (no duplicate, missing, or extra IDs; outcome
partitions; present-supported cases partition exactly into correct, supported abstention,
confidently wrong, or missing-input gap; skills expectations exhaust every frozen skill
annotation; result categories do not overlap). It cross-checks the scorer against the
public `evaluate_corpus` result (opportunity matrices, runtime-failure counts, and the
per-record `(parser, component, category)` mismatch multiset for composed components)
without importing private evaluator helpers, and checks per-record, per-field equality
with direct parser calls.

The expectations were recomputed from the committed corpus and current parsers at the
base, not remembered. They were derived from a gitignored review aid (the D2 expectation
manifest, SHA-256 `f480ed2ec0305a7a85987fb9cfca8e1763816c2cad7a50d13203d0893b104d65`, and
its generator, SHA-256 `fff152a4dcd8055aec433191fc9eee4aecd79697656c26766aa414cb4195563c`).
The tests never read or require either file.

Headline totals (combined, 30 records): 0 runtime failures; 0 confidently wrong; 0 false
positives in components or skills; skills recall 37/40 with exactly three known
`skills.golang` misses (`gitlab:8463922002`, `gitlab:8490477002`, `gitlab:8514960002`);
56 supported abstentions; 100 salary missing-input gaps; 33 correct supported values; 159
evaluator mismatches.

**Identity pins.** The test module pins:

- corpus canonical JSON SHA-256
  `ca6e129110b71801e18d6bfba84d59376c689f67cb470f1335ab8805cd388f00` (the corpus parsed and
  re-serialized with sorted keys, ASCII escapes, and compact separators, so it is
  independent of checkout line endings);
- taxonomy canonical-LF SHA-256
  `926a2a46cb0c603b953d989f449551af2d1a82cb3b50084a4005e78d7730c67c` (the file's UTF-8 text
  after replacing CRLF and lone CR with LF).

These are D2 evidence identities. They are not a D1 parser-version implementation.

### 3. Accounting

- **Covered:** exactly three annotated components, `employment_type` (10 correct),
  `seniority` (18), and `location.country` (5), plus skills recall (37 hits), commonly
  reported as four covered areas.
- **Unproven (exactly ten):** `remote_type`, `experience.minimum`, `experience.maximum`,
  `location.city`, `location.state`, `location.postal_code`, `salary.minimum`,
  `salary.maximum`, `salary.currency`, `salary.period`. Four have supported cases but
  zero coverage (`remote_type` 0/23, `experience.minimum` 0/14, `location.city` 0/6,
  `location.state` 0/3); two have no supported cases (`experience.maximum`,
  `location.postal_code`); the four salary components are not composed. They receive only
  no-crash, no-false-positive, and no-confidently-wrong checks and are never reported as
  covered.
- **Title** is not part of the 28-label realistic annotation schema and is neither
  covered nor unproven in this accounting. Its 30-record expectations (22 matched, 6
  unsupported, 2 ambiguous, 0 no-title) are smoke/regression evidence only. They are not
  title accuracy evidence, do not satisfy D2 for title, and never inflate the covered
  count.

### 4. Provenance

The composition creates no provenance tag. The D2 module tests provenance separately from
value correctness:

- every correct composed value carries its annotation's provenance, except exactly three
  accepted exceptions (ADR 0011 limitation L5): `location.country` for
  `anthropic:4610158008`, `gitlab:8396674002`, and `gitlab:8512432002`, each expected
  `inferred` and currently emitted as `parsed_description`;
- skills provenance is `parsed_description`;
- no output uses `explicit_source` or `structured_metadata`.

### 5. Exact-set policy

Any change to an exact set fails, including an added correct value or a removed
abstention. The failure message is neutral: "realistic-output contract changed; review
required". A failure is a review trigger, never an automatic regression or improvement
classification. The holdout is already exposed (ADR 0010/0011), so updating a literal
requires renewed review of the output change and its evidence. No "improvement" policy
exists in the composition layer or the tests.

### 6. Bounded D2 claim

> S2 satisfies ADR 0011 D2 only at the pure `normalize_posting` composition boundary, for the exact covered outputs demonstrated by the current exposed 30-record corpus under the pinned corpus and taxonomy identities. Exact-set failures are review triggers, not automatic regression or improvement classifications. This evidence does not establish title accuracy or generalization; HTML conversion; Greenhouse list-endpoint or provider-field mapping; behavior on unredacted text; salary or any other unproven component; production composition; normalized persistence; or D1 parser-version traceability. D1 remains unsatisfied, and no normalized write is authorized.

### 7. Provider-field allowlist for S2b (recorded, not implemented)

Only these Greenhouse fields may later become parser inputs, and only in separately
authorized S2b:

| Greenhouse source | Through | `PostingInputs` |
|---|---|---|
| `title` | `DiscoveredJob.title`, verbatim (S1) | `title` |
| `location.name` | `DiscoveredJob.location`, verbatim (S1) | `location` |
| `content` | HTML-to-text conversion inside the adapter, declared content mode, `DiscoveredJob.description` | `description` |

Never parser inputs: `company_name`, `metadata`, `departments`, `offices`,
`updated_at`, `first_published`, `requisition_id`, `absolute_url`, `pay_transparency`
(never requested), or any other raw key. The corpus descriptions were converted from
detail-endpoint responses in `declared-double-escaped` mode and contact-redacted
(ADR 0010); list-endpoint content-mode evidence is deferred to S2b (U6).

### 8. Revised Phase 4 sequence

This replaces ADR 0013's five-slice table.

1. **S1** — offline direct Greenhouse adapter. Complete (`M=48cc5c7`, `Q=0c2c14b`).
2. **S2** — this slice: pure, provider-neutral `normalize_posting` composition plus
   scoped D2 protection. No provider mapping and no write.
3. **S2b** — offline Greenhouse HTML-to-text conversion and provider-to-`PostingInputs`
   mapping, using declared content-mode evidence. No persistence.
4. **S2c** — a separately authorized, **bounded read-only live canary**, not production
   ingestion: one small Greenhouse board initially, optionally a second only after the
   first succeeds; a real response through S1 + S2 + S2b; no database write; a
   default-off kill switch; response, time, and size caps; no raw-body logging; a review
   of Greenhouse's terms of use; Sol Medium and Astra review; explicit network
   authorization.
5. **S3** — D1 parser-version threading and normalized/provenance persistence.
6. **S4** — read API.
7. Later controlled live operation and broader enablement, only after separate approval.

S1, S2, and S2b are the three ADR 0012 pilot product slices. S2c occurs after the pilot
evaluation and before persistence. Each slice needs its own proposal and authorization.

## Exclusions

S2 does not: modify any provider; convert HTML or move the converter; map any provider
field into a parser input (including setting `DiscoveredJob.description`); register or
wire anything into the registry, composition root, or ingestion; persist anything, write
`field_provenance`, apply a merge rule, or define or thread a `parser_version`; add a
migration; contact Greenhouse or any live source; access production data; change any
parser, the taxonomy, the corpus, its annotations, or the evaluator; compose salary
input; or change a validator, schema, verification tool, or the registered witness
inventory.

## Consequences

- A pure composition exists with executable realistic-output protection at its boundary.
  Nothing calls it at runtime.
- A change to any exact-pinned realistic output, or to the corpus or taxonomy content,
  fails the D2 module and requires review before its expectations change. Pinned per
  record: every component value or abstention, provenance on every correct value, skills
  recall and false-positive membership by canonical ID, and title outcome, canonical
  title, and role family. Provenance on absent values is fixed by `NormalizationResult`'s
  own invariant (a `None` value is always `unavailable`), and title provenance by
  `TitleResult`'s. Not pinned per record: skill-match order, duplicates, and display names
  (only the aggregate skills provenance set is pinned).
- D1 remains a binding precondition for S3's first normalized write.
- The 34 registered mutation witnesses are unchanged. S2's nine mutation experiments are
  recorded advisory-candidate evidence, not registered guards.
