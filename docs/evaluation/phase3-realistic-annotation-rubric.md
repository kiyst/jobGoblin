# Phase 3 realistic-corpus annotation rubric

`rubric_version: 1.0.1`

Status: frozen input to the realistic-corpus annotation stage (Sol-approved
freeze/evaluation contract, 2026-09-27; corrected 2026-09-27 per Sol's Stage 1
pre-annotation review, findings F1/F2). Both independent annotation passes
(Claude, Sol) receive this exact file, byte-identical, alongside the
byte-identical sanitized source packet and the committed skills taxonomy
(`backend/app/taxonomy/skills.yaml`) — nothing else. This document, together
with that packet and taxonomy, fully determines
`freeze_phase3_realistic_corpus.py`'s canonical `source_packet_hash` (see that
script's `compute_source_packet_hash`).

**Superseded evidence**: `rubric_version: 1.0.0` (the version this document
replaces) and its rubric hash
(`bb4c8ac44ccb7bf6c0978d36bb4350449076df032e337ef6a8b03a651ee2ade0`, recorded
in commit `7644e20e30fdde6e38a840e3b621b6217b93ce14`'s handoff entry) are
preserved as historical record only. No annotation was ever run against
`1.0.0` — this correction bumps the version because the rubric changed before
any annotation exists, per the standing rule below.

Editing this file after either pass has been sealed and hashed invalidates
both passes; a rubric revision requires a fresh `rubric_version` and a fresh
annotation cycle. Never edit a rubric a pass has already been hashed against.

**This rubric requires no access to parser implementation details.** Every
rule below is stated in terms of the record's own text and a closed,
implementation-independent output domain — never in terms of what the
current `classify_*()` code happens to recognize. An annotator who has never
read `backend/app/normalization/*.py` can apply every rule in this document
completely.

## Scope

One annotation per record for: the three scalar fields (`remote_type`,
`employment_type`, `seniority`); the ten composite components
(`experience.minimum`, `experience.maximum`, `salary.minimum`,
`salary.maximum`, `salary.currency`, `salary.period`, `location.city`,
`location.state`, `location.country`, `location.postal_code`); and every
canonical skill id in the frozen taxonomy (currently 15). 3 + 10 + 15 = 28
annotations per record.

## Source fields per annotation (closed, no exceptions)

Each annotation is scored **strictly from the field(s) listed below** — never
from any other field of the same record, even when the value plainly also
appears there. This table is closed and fixed regardless of how obviously a
value appears elsewhere; it is not an editorial judgment call.

| Annotation | Sourced field(s) | If every sourced field is null or empty |
|---|---|---|
| `remote_type`, `employment_type`, `seniority`, `experience.minimum`, `experience.maximum` | `title` + `description`, pooled as one combined body of evidence | `absent` |
| `skills.<canonical id>` (all 15) | `title` + `description`, pooled | `absent` |
| `salary.minimum`, `salary.maximum`, `salary.currency`, `salary.period` | `compensation_text` **only** | `absent` — even if a compensation figure is stated in `title` or `description`; those fields are never consulted for salary |
| `location.city`, `location.state`, `location.country`, `location.postal_code` | `location_raw` **only** | `absent` — even if a location is stated in `title` or `description`; those fields are never consulted for location |

This table exists because the corpus's own evaluation harness wires each
parser to exactly these fields (e.g. the salary classifier only ever
receives `compensation_text`, never `description`). A record whose
`description` says "$120,000–$150,000" but whose `compensation_text` is
null must be annotated `salary.minimum` = `absent`, `salary.maximum` =
`absent`, and so on — this is not a parser limitation being papered over; it
reflects which field this corpus actually asks each annotation to describe.

For the `title` + `description` pooled fields: treat the two as one combined
body of evidence, not title-then-description in a fixed precedence order. A
value stated in the title alone (e.g. a title reading "Staff Engineer") is
sufficient on its own — no corroboration in `description` is required. If
title and description genuinely state two different, non-equivalent values
with no textual basis to prefer one, that is the `ambiguous` outcome (below),
not a precedence rule to resolve silently.

## Outcomes (closed set, shared vocabulary for scalars and composite components)

Every field above has a fixed **canonical output domain** (defined per field
in the next section). Exactly one of the following outcomes applies:

- **`present_supported`** — the sourced field(s) unambiguously supply a
  value, and that value is representable by the field's canonical output
  domain **as stated in this rubric** — regardless of whether the phrasing
  used is one the current parser implementation happens to recognize. If a
  future or different implementation could correctly derive the value from
  this same text, and the value fits the domain, the outcome is
  `present_supported`. Requires a non-null `expected_value` and a
  non-`unavailable` `expected_provenance`.
- **`present_unsupported_form`** — the sourced field(s) state this field's
  information, but the value **cannot be represented** by the canonical
  output domain at all (see per-field examples below) — not "the parser
  doesn't happen to recognize this phrasing" but "no value in the domain
  could correctly represent what the text says." `expected_value` is null,
  `expected_provenance` is `"unavailable"`.
- **`absent`** — missing information: the sourced field(s) do not address
  this annotation at all (including the case where every sourced field is
  null, per the table above). `expected_value` is null, `expected_provenance`
  is `"unavailable"`.
- **`ambiguous`** — the sourced field(s) support two or more genuinely
  different, non-equivalent readings, with no textual basis to prefer one
  (see "Ambiguity rule" below). `expected_value` is null,
  `expected_provenance` is `"unavailable"`.

This is a bidirectional rule, not four independent choices: `outcome` is
`present_supported` **if and only if** `expected_value` is non-null (which is
itself iff `expected_provenance` is not `"unavailable"`). A
`present_supported`/null pairing and an `absent`/non-null pairing are both
invalid annotations under this rubric, matching
`evaluate_phase3_corpus.py`'s `_validate_scored_label`, the same invariant
this corpus is built to satisfy.

## Canonical output domain per field, with unsupported-form examples

| Field | Canonical output domain | `present_unsupported_form` example |
|---|---|---|
| `remote_type` | exactly one of `remote`, `hybrid`, `onsite` | a work arrangement stated that is none of these three and not a straightforward synonym of one (e.g. "workation", "digital nomad friendly" with no onsite/hybrid/remote commitment stated) |
| `employment_type` | exactly one of `full_time`, `part_time`, `seasonal`, `internship` | an arrangement stated that is none of these four (e.g. "contract", "temp-to-perm", "1099 consultant") |
| `seniority` | exactly one of `entry_level`, `mid_level`, `senior`, `staff`, `principal`, `director` | a seniority framing not equivalent to any of these six (e.g. "C-suite executive", "VP of Engineering" — outside this closed ladder) |
| `experience.minimum`, `experience.maximum` | a whole-number (integer) count of years | a fractional or non-integer-only amount that cannot be rounded without inventing information (e.g. "2.5 years minimum" — 2 or 3 would both misstate the text) |
| `salary.minimum`, `salary.maximum` | an integer amount | a fractional amount, or a figure expressed only as a formula/equity grant/commission structure with no fixed number stated (e.g. "1% equity, salary DOE") |
| `salary.currency` | any non-empty string | none under the current schema — any textual currency mention is representable as a string, so this outcome does not arise for `salary.currency`; use `absent` when no currency is stated, even if an amount is |
| `salary.period` | any non-empty string | none under the current schema, for the same reason as `salary.currency` |
| `location.city`, `location.state`, `location.country`, `location.postal_code` | any non-empty string | none under the current schema, for the same reason as `salary.currency` — any textual mention is representable; use `absent` when the sub-field genuinely is not stated |

The `salary.currency`/`salary.period`/`location.*` domains are deliberately
unrestricted free text (any non-empty string satisfies them), so
`present_unsupported_form` structurally cannot occur for those eight fields
under this schema — do not annotate it there. This is a real, correct
consequence of the domain being open-ended for those fields, not an
oversight; it means the only meaningful distinction for those fields is
`present_supported` vs. `absent` vs. `ambiguous`.

## Provenance rule (for every `present_supported` annotation)

`expected_provenance` is one of exactly two values for this corpus:

- **`parsed_description`** — the sourced field(s) state the value directly
  and literally, needing no combination or interpretation (e.g.
  `location_raw` reading exactly "Remote"; `compensation_text` stating
  "$120,000" directly as a single number).
- **`inferred`** — deriving the value requires combining more than one piece
  of textual evidence, or applying straightforward domain judgment to map
  stated wording onto the closed domain (e.g. `seniority` derived from a
  title reading "Staff Engineer"; `experience.minimum` derived from "Bachelor's
  degree plus 5 years of experience" requiring the reader to recognize "5
  years" as the minimum rather than a degree-equivalency clause).

No other provenance tag applies to a realistic-corpus annotation (there is no
structured metadata feed and no separate "explicit source" distinct from the
posting text itself); `derived`/`structured_metadata`/`explicit_source` must
never be used here. `unavailable` is used exactly when `expected_value` is
null (`absent`, `present_unsupported_form`, or `ambiguous`).

## Missing-information handling (`absent`)

Use `absent` whenever the sourced field(s) for this annotation (per the
source-field table above) do not address it at all — including when every
sourced field is null — not even in an unsupported or ambiguous form. This is
the default for any field the sourced text simply never mentions. Do not use
`absent` for a field that is mentioned but unclear (`ambiguous`) or mentioned
in a form the domain cannot represent (`present_unsupported_form`).

## Ambiguity rule

Use `ambiguous` only when the sourced field(s) themselves support two or more
genuinely different, non-equivalent values, with no textual basis (wording,
section placement, an explicit qualifier) to prefer one over the other. A
field that is merely *loosely* worded but still resolves to one clear
reading under ordinary-English interpretation is not ambiguous — annotate
the one clear reading instead. Do not use `ambiguous` as a catch-all for "I
am not fully certain"; it specifically means the sourced text itself is
multi-valued, not that the annotator finds the call hard. A genuine conflict
between `title` and `description` for a pooled-evidence field (see the
source-field table) is exactly this case.

## Skill-label rule

A skill-id annotation is scored on `outcome` alone (no `expected_value`/
`expected_provenance` — the outcome itself already states whether this
canonical id is expected to be identified for this record), sourced from
`title` + `description` pooled, per the source-field table. For each of the
15 canonical ids, in every record:

- `present_supported` — the sourced text names this exact skill (or one of
  its taxonomy aliases) unambiguously.
- `present_unsupported_form` — the skill is named, but only embedded in a
  way that cannot be represented as identifying this canonical id at all
  (e.g. as part of an unrelated compound proper noun that is not a reference
  to the skill itself).
- `absent` — the sourced text never mentions this skill at all.
- `ambiguous` — the sourced text's reference to this skill is genuinely
  multi-valued under the ambiguity rule above (rare for a single skill id;
  reserve for a genuine textual ambiguity, not annotator uncertainty).

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

## Annotation-pass JSON schema (exact, closed)

Both Claude's and Sol's sealed pass file share this one schema, validated by
`freeze_phase3_realistic_corpus.load_annotation_pass`. Exactly six top-level
fields, no more, no fewer:

```json
{
  "schema_version": "1",
  "annotator_role": "claude",
  "rubric_version": "1.0.1",
  "source_packet_hash": "<the canonical sha256 hex handed to you with this packet>",
  "frozen_at": "2026-09-27T18:00:00+00:00",
  "records": {
    "<record id>": { "...": "one annotation object per field below" }
  }
}
```

- `schema_version` is the fixed string `"1"`.
- `annotator_role` is exactly `"claude"` or exactly `"sol"` — whichever role
  you were told you are performing. Never anything else.
- `rubric_version` is exactly `"1.0.1"` (this document's version) — copy it
  verbatim, do not derive or reformat it.
- `source_packet_hash` is the canonical hash value you were given alongside
  this rubric, the taxonomy, and the sanitized source packet — copy it
  verbatim.
- `frozen_at` is a timezone-aware ISO 8601 timestamp (e.g.
  `2026-09-27T18:00:00+00:00`, or with a `Z` suffix) marking when you sealed
  this pass. A naive timestamp (no offset) is rejected.
- `records` is a JSON object keyed by **exactly** the record ids you were
  given with the packet (each formatted `<board_token>:<job_id>`, e.g.
  `"gitlab:8396674002"`) — every one of them, none added, none removed,
  none renamed.

**Each record's value** is a JSON object with exactly these seven keys —
three scalar fields, three composite groups, and `skills`:

```json
{
  "remote_type":      {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
  "employment_type":  {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
  "seniority":        {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
  "experience": {
    "minimum": {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
    "maximum": {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"}
  },
  "salary": {
    "minimum": {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
    "maximum": {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
    "currency": {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
    "period":   {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"}
  },
  "location": {
    "city":        {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
    "state":       {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
    "country":     {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"},
    "postal_code": {"outcome": "...", "expected_value": null, "expected_provenance": "unavailable"}
  },
  "skills": {
    "<every one of the 15 canonical ids you were given with the taxonomy>": {"outcome": "..."}
  }
}
```

Every scalar/composite label object has **exactly three keys**: `outcome`,
`expected_value`, `expected_provenance` — never a fourth key of any kind
(there is no field for your reasoning, a confidence score, or a note; put
none of that in this file). Every skill label object has **exactly one
key**: `outcome`. `outcome` is one of the four strings from "Outcomes"
above. `expected_value`'s shape is fixed per field (see the domain table);
`expected_provenance` is `"parsed_description"`, `"inferred"`, or
`"unavailable"` per the provenance rule above.

**Compact valid example** (one record, a 2-canonical-id taxonomy
`{alpha, beta}` for brevity — the real taxonomy has 15 real ids, every one of
which must appear). `source_packet_hash` below is an illustrative placeholder
only — copy the *actual* value you were given with your packet, never this
one (this document's own bytes feed into that hash, so no value written here
could ever be the real one):

```json
{
  "schema_version": "1",
  "annotator_role": "claude",
  "rubric_version": "1.0.1",
  "source_packet_hash": "<the actual value handed to you with your packet, copied verbatim>",
  "frozen_at": "2026-09-27T18:00:00+00:00",
  "records": {
    "gitlab:8396674002": {
      "remote_type": {"outcome": "present_supported", "expected_value": "remote", "expected_provenance": "parsed_description"},
      "employment_type": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
      "seniority": {"outcome": "present_supported", "expected_value": "senior", "expected_provenance": "inferred"},
      "experience": {
        "minimum": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
        "maximum": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"}
      },
      "salary": {
        "minimum": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
        "maximum": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
        "currency": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
        "period": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"}
      },
      "location": {
        "city": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
        "state": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
        "country": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
        "postal_code": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"}
      },
      "skills": {
        "alpha": {"outcome": "present_supported"},
        "beta": {"outcome": "absent"}
      }
    }
  }
}
```

A fresh annotator receiving only the declared packet (sanitized records,
this rubric, and the taxonomy), their assigned `annotator_role`, and the
`source_packet_hash` above can produce a loader-valid file matching this
schema exactly, without seeing any code, any test, or the other pass.
