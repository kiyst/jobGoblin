# Phase 3 realistic-corpus annotation rubric

`rubric_version: 1.0.0`

Status: frozen input to the realistic-corpus annotation stage (Sol-approved
freeze/evaluation contract, 2026-09-27). Both independent annotation passes
(Claude, Sol) receive this exact file, byte-identical, alongside the
byte-identical sanitized source packet and the committed skills taxonomy
(`backend/app/taxonomy/skills.yaml`) — nothing else. This document, together
with that packet and taxonomy, fully determines
`freeze_phase3_realistic_corpus.py`'s canonical `source_packet_hash` (see that
script's `compute_source_packet_hash`).

Editing this file after either pass has been sealed and hashed invalidates
both passes; a rubric revision requires a fresh `rubric_version` and a fresh
annotation cycle. Never edit a rubric a pass has already been hashed against.

## Scope

One annotation per record for: the three scalar parsers (`remote_type`,
`employment_type`, `seniority`); the ten composite components
(`experience.minimum`, `experience.maximum`, `salary.minimum`,
`salary.maximum`, `salary.currency`, `salary.period`, `location.city`,
`location.state`, `location.country`, `location.postal_code`); and every
canonical skill id in the frozen taxonomy (currently 15). 3 + 10 + 15 = 28
annotations per record.

Annotate strictly from the sanitized `fields` (`title`, `description`,
`location_raw`, `compensation_text`) of the record under review. Never
consult `classify_*()` output, the other pass's file, or any prior
annotation — blindness to those is the entire point of running two
independent passes; see "Procedural blindness" below.

## Outcomes (closed set, shared vocabulary for scalars and composite components)

Exactly one of:

- **`present_supported`** — the record's text states this field's value, and
  that value fits the parser's supported vocabulary/shape exactly (see
  "Value and provenance rules" below). Requires a non-null `expected_value`
  and a non-`unavailable` `expected_provenance`.
- **`present_unsupported_form`** — the record's text states this field's
  value, but in a form the parser is not designed to resolve (see
  "Unsupported-form rule"). `expected_value` is null, `expected_provenance`
  is `"unavailable"`.
- **`absent`** — missing information: the record's text simply does not
  address this field at all (see "Missing-information handling").
  `expected_value` is null, `expected_provenance` is `"unavailable"`.
- **`ambiguous`** — the record's text supports two or more genuinely
  different, non-equivalent readings for this field, with no textual basis
  to prefer one (see "Ambiguity rule"). `expected_value` is null,
  `expected_provenance` is `"unavailable"`.

This is a bidirectional rule, not four independent choices: `outcome` is
`present_supported` **if and only if** `expected_value` is non-null (which is
itself iff `expected_provenance` is not `"unavailable"`). A
`present_supported`/null pairing and an `absent`/non-null pairing are both
invalid annotations under this rubric, matching
`evaluate_phase3_corpus.py`'s `_validate_scored_label`, the same invariant
this corpus is built to satisfy.

## Value and provenance rules

`expected_value`'s shape is fixed per parser/component, mirroring
`evaluate_phase3_corpus.py`'s own `_EXPECTED_VALUE_VALIDATORS`:

| Field | Value shape |
|---|---|
| `remote_type` | one of `"remote"`, `"hybrid"`, `"onsite"` |
| `employment_type` | one of `"full_time"`, `"part_time"`, `"seasonal"`, `"internship"` |
| `seniority` | one of `"entry_level"`, `"mid_level"`, `"senior"`, `"staff"`, `"principal"`, `"director"` |
| `experience.minimum`, `experience.maximum` | integer (years), never a `bool` |
| `salary.minimum`, `salary.maximum` | integer, never a `bool` |
| `salary.currency`, `salary.period` | non-empty string |
| `location.city`, `location.state`, `location.country`, `location.postal_code` | non-empty string |

`expected_provenance` is one of the six `Provenance` tags (in decreasing
trust order): `explicit_source`, `structured_metadata`, `parsed_description`,
`derived`, `inferred`, `unavailable`. For a realistic-corpus annotation
(there is no structured metadata feed and no separate "explicit source"
distinct from the posting text itself), the only two tags a `present_*`
annotation should ever use are:

- `parsed_description` — the value is stated directly and needs no
  inference (e.g. a location field reading exactly "Remote").
- `inferred` — the value requires combining or interpreting the text (e.g.
  seniority inferred from a title like "Staff Engineer").

`derived`/`structured_metadata`/`explicit_source` do not apply to this
corpus's provenance and must not be used. `unavailable` is used exactly when
`expected_value` is null (`absent`, `present_unsupported_form`, or
`ambiguous`).

## Missing-information handling (`absent`)

Use `absent` whenever the record's `title`/`description`/`location_raw`/
`compensation_text` text does not address the field at all — not even in an
unsupported or ambiguous form. This is the default for any field the
posting simply never mentions. Do not use `absent` for a field that is
mentioned but unclear (`ambiguous`) or mentioned in a form the parser cannot
resolve (`present_unsupported_form`) — those are distinct outcomes with
distinct handling below.

## Ambiguity rule

Use `ambiguous` only when the text itself supports two or more genuinely
different, non-equivalent values for the field, with no textual basis
(title wording, section placement, explicit qualifier) to prefer one over
the other. A field that is merely *loosely* worded but still resolves to one
clear reading under ordinary-English interpretation is not ambiguous —
annotate the one clear reading instead. Do not use `ambiguous` as a
catch-all for "I am not fully certain"; it specifically means the text
itself is multi-valued, not that the annotator finds the call hard.

## Unsupported-form rule

Use `present_unsupported_form` when the field's information is genuinely
present in the text but expressed in a form outside the parser's supported
vocabulary/shape from the table above — for example, a salary period
expressed as neither an hourly/annual/etc. token the parser is designed to
recognize, or a seniority phrase that does not map onto the closed
`seniority` vocabulary. This outcome exists specifically so that a parser's
correct abstention on out-of-vocabulary input is never scored as a missing
capability the same way true absence is — see
`evaluate_phase3_corpus.py`'s separate `false_positive_absent` versus
`false_positive_unsupported_form` metrics, which must never be merged.

## Skill-label rule

A skill-id annotation is scored on `outcome` alone (no `expected_value`/
`expected_provenance` — the outcome itself already states whether
`classify_skills` is expected to return that canonical id for this record).
For each of the 15 canonical ids, in every record:

- `present_supported` — the record's text names this exact skill (or one of
  its taxonomy aliases) in a form `classify_skills` is expected to
  recognize.
- `present_unsupported_form` — the skill is named, but only in a form the
  classifier is not designed to recognize (e.g. buried in an unrelated
  compound term).
- `absent` — the record's text never mentions this skill at all.
- `ambiguous` — the text's reference to this skill is genuinely multi-valued
  under the ambiguity rule above (rare for a single skill id; reserve for a
  genuine textual ambiguity, not annotator uncertainty).

Every one of the 15 ids must receive one of these four outcomes for every
record — never a subset, and never left blank because a skill obviously
doesn't apply; "obviously doesn't apply" is exactly what `absent` records.

## Procedural blindness

Each pass (Claude, then Sol, in a separate task) receives only this rubric,
the taxonomy, and the byte-identical sanitized source packet — never the
other pass's labels, reasoning, or files, and never `classify_*()` output.
This is **procedural blindness**: a guarantee about what each annotation
task is given as input, enforced by how the two tasks are run. It is **not
a cryptographic guarantee** — nothing in the rubric, the packet, or the
resulting annotation-pass file cryptographically prevents an annotator from
having seen prohibited material by some other means. The guarantee rests on
the two passes genuinely being run as separate, isolated tasks with only
the declared inputs supplied.
