# Phase 3 realistic-corpus annotation rubric

`rubric_version: 1.0.4`

Status: frozen input to the realistic-corpus annotation stage (Sol-approved
freeze/evaluation contract, 2026-09-27; corrected 2026-09-27 per Sol's Stage 1
pre-annotation review, findings F1/F2; corrected again 2026-09-27 per Sol's
Stage 1 re-review, findings F7/F8/F9/F10; corrected a third time 2026-09-27
per Sol's final Stage 1 re-review, findings F11/F12/F13; corrected a fourth
time 2026-09-27 per Sol's final Stage 1 re-review of that correction,
findings F14/F15). Both independent annotation passes (Claude, Sol) receive
this exact file, byte-identical, alongside the byte-identical sanitized
source packet and the committed skills taxonomy
(`backend/app/taxonomy/skills.yaml`) — nothing else. This document, together
with that packet and taxonomy, fully determines
`freeze_phase3_realistic_corpus.py`'s canonical `source_packet_hash` (see that
script's `compute_source_packet_hash`).

**Superseded evidence** (none of these versions was ever annotated against):

| Version | Rubric sha256 | `source_packet_hash` |
|---|---|---|
| `1.0.0` (commit `7644e20e30fdde6e38a840e3b621b6217b93ce14`) | `bb4c8ac44ccb7bf6c0978d36bb4350449076df032e337ef6a8b03a651ee2ade0` | `867e5b6d30a4fc858de3146122437ca03a936936c8f88ddc0348ab5dedb92957` |
| `1.0.1` (commit `64dd730`) | `47f833d80eb37c8046fc6b243e53fbeaa4cdab78c6b71a52748ecb42e7106f2c` | `914ebc5700a4baf9f7b15d25e109ea86d647ef9c8d5bd2fb8e04cdb608299651` |
| `1.0.2` (commit `d2097b4`) | `736d53bb7da78cd558fb6f7cab1c18fc991940416e059f5e60cc3b92e19ea0f9` | `08409a3e57dccf84c34127675078106d6c510ff71813860fb23b69fd26bed55a` |
| `1.0.3` (commit `80b4672`) | `3948ec6a09c188a95b9a2ee1fb9ecd94edda2ab5c48bb39e32826e36f51f7f87` | `b56b0f65529fc83a8f30c8958ba697544a321a003b323220b92a7c1ac8c6dd1b` |

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

## Role-relevance filter (applied first, before any outcome is chosen)

An annotation may be `present_supported`, `present_unsupported_form`, or
`ambiguous` **only when the sourced text makes the assertion about the
advertised position itself or its candidate requirements.** Before applying
any rule below, discard (treat as if absent) any sourced-text mention that:

- describes a **different person** or a reporting relationship, not the
  candidate (e.g. who the role reports to, who a manager oversees);
- describes a **customer, client, or end-user's** team/role rather than the
  candidate's own work;
- is a **generic company-wide benefits/policy heading** not specific to this
  requisition (e.g. a boilerplate "how we support our employees" section
  shared across every posting);
- is a **company or product description** (what the company builds, what
  language its product is written in) rather than a statement of what the
  candidate will do or must know;
- is a **passing example or illustration** not presented as part of the
  role's actual work or requirements.

If, after discarding irrelevant mentions, **no relevant mention of this
annotation's topic remains**, the outcome is `absent` — the same as if the
topic were never mentioned at all. If **at least one relevant mention
remains**, apply the normal outcome rules to the relevant mention(s) only;
an irrelevant mention never creates an `ambiguous` conflict with a relevant
one (relevant evidence always governs; irrelevant evidence is simply
disregarded, not weighed against it). Two or more *relevant* mentions that
genuinely conflict are still `ambiguous`, per the rule below.

**Synthetic examples** (fabricated text, not derived from any real posting):

| Sourced text | Field | Correct outcome | Why |
|---|---|---|---|
| "How we support our full-time team: unlimited PTO, healthcare from day one." (a boilerplate benefits section) | `employment_type` | `absent` (unless the role's own details state it elsewhere) | Generic benefits heading, not an assertion that *this* role is full-time |
| "This role reports to the Director of Engineering." | `seniority` | `absent` (unless the role's own seniority is stated elsewhere) | Describes the reporting line, not the candidate's own level |
| "You will lead a team of senior and intermediate engineers." | `seniority` | `absent` **from this sentence alone** (unless other relevant text independently states the candidate's own level) | "Senior"/"intermediate" here describe the candidate's *reports*, not the candidate |
| "Our platform is built primarily in Java." (company/product description; the requirements section asks for Python) | `skills.java` | `absent` | Product description, not a requirement of the candidate |
| "3+ years of professional Python development experience required." (positive control — an actual role requirement) | `skills.python`, `experience.minimum` | `present_supported` | Directly states a requirement of the candidate for this role |

## Source fields per annotation (closed, no exceptions)

Each annotation's **ground truth** is determined from the field(s) listed
below — the full set of text a careful human reader would consult to
determine whether this record's advertised role genuinely has this
property. This is deliberately broader than what the current parser
implementation is wired to receive; see "Ground truth versus current parser
input (wiring gap)" below for how that difference is measured, not hidden.

| Annotation | Sourced field(s) for ground truth | If every sourced field is null or empty |
|---|---|---|
| `remote_type`, `employment_type`, `seniority`, `experience.minimum`, `experience.maximum`, `skills.<canonical id>` (all 15) | `title` + `description`, pooled as one combined body of evidence | `absent` |
| `salary.minimum`, `salary.maximum`, `salary.currency`, `salary.period` | `title` + `description` + `compensation_text`, pooled | `absent` |
| `location.city`, `location.state`, `location.country`, `location.postal_code` | `title` + `description` + `location_raw`, pooled | `absent` |

For every pooled-evidence field: treat all sourced fields as one combined
body of evidence, not a fixed precedence order. A value stated in any one of
them (e.g. a title reading "Staff Engineer") is sufficient on its own — no
corroboration in the others is required. If two sourced fields genuinely
state two different, non-equivalent values with no textual basis to prefer
one, that is the `ambiguous` outcome (below), not a precedence rule to
resolve silently.

## Ground truth versus current parser input (wiring gap)

The corpus's evaluation harness currently wires `classify_salary` to
`compensation_text` **only** and `classify_location` to `location_raw`
**only** — never to `description`, even though salary or location
information is frequently stated there instead (in this batch, all 30
retained records have `compensation_text == null`, while an offline scan
found dollar-figure salary evidence in `description` for 24 of the 30 and
some salary/compensation mention in all 30).

**Annotate the semantic ground truth from the full sourced-field set above,
regardless of whether the narrower wired field (`compensation_text` /
`location_raw`) is null.** Do not annotate `absent` merely because the wired
field is null if the pooled evidence (including `description`) genuinely
supports a value — that would hide a real provider/input-mapping gap behind
a false "nothing to see here."

**Do not** invent, extract, or backfill a `compensation_text` (or
`location_raw`) value anywhere in this pipeline — the actual parser
invocation continues to run unmodified against the field as it exists in
the record. The evaluator (not the annotation, and not this rubric)
separately checks, at evaluation time, whether the record's own
`compensation_text`/`location_raw` was completely missing (null, or
present but whitespace-only — the real parser aborts on a blank string
exactly like a null one, so both are treated identically) while the
annotation says `present_supported`, and reports that combination
explicitly as a **missing-wired-input gap**
(`ParserComponentMetrics.missing_wired_input_gap`) — distinct from, and
never merged into, `supported_correctness`/`supported_abstention`/
`confidently_wrong`, which continue to mean "the parser's actual wired
input was present" (see `docs/evaluation` baseline report once produced).

**This metric only detects a completely absent wired input.** It cannot
and does not detect a wired input that is present but incomplete or
mis-mapped (e.g. `compensation_text` populated with only part of the
actual figure, or the wrong span) — recognizing that requires later,
manual mismatch attribution against the baseline report's per-record
mismatch details, not this metric.

This means: **this corpus can measure the current end-to-end salary gap
(how often real salary information exists but never reaches the parser at
all)**, but it **cannot measure salary-parser correctness on realistic
non-null inputs** — that requires a separately reviewed extraction/mapping
slice to actually populate `compensation_text` (or an equivalent wired
field) from `description`, which is explicitly out of scope here.

## Outcomes (closed set, shared vocabulary for scalars and composite components)

Every field above has a fixed **canonical output domain** (defined per field
in the next section). Exactly one of the following outcomes applies, to the
*relevant* sourced evidence (after the role-relevance filter above):

- **`present_supported`** — the sourced field(s) unambiguously supply a
  value, and that value is representable by the field's canonical output
  domain **as stated in this rubric** — regardless of whether the phrasing
  used is one the current parser implementation happens to recognize, and
  regardless of which specific sourced field carries it. Requires a
  non-null `expected_value` and a non-`unavailable` `expected_provenance`.
- **`present_unsupported_form`** — the sourced field(s) state this field's
  information, but the value **cannot be represented** by the canonical
  output domain at all (see per-field examples below) — not "the parser
  doesn't happen to recognize this phrasing" but "no value in the domain
  could correctly represent what the text says." `expected_value` is null,
  `expected_provenance` is `"unavailable"`.
- **`absent`** — missing information: no *relevant* sourced evidence
  addresses this annotation at all (including when every sourced field is
  null, and including when every mention found is filtered out by the
  role-relevance filter). `expected_value` is null, `expected_provenance`
  is `"unavailable"`.
- **`ambiguous`** — two or more *relevant* pieces of sourced evidence
  support genuinely different, non-equivalent readings, with no textual
  basis to prefer one (see "Ambiguity rule" below). `expected_value` is
  null, `expected_provenance` is `"unavailable"`.

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
| `experience.minimum`, `experience.maximum` | a whole-number (integer) count of years | a fractional or non-integer-only amount that cannot be rounded without inventing information (e.g. "2.5 years minimum") |
| `salary.minimum`, `salary.maximum` | an integer amount | a fractional amount, or a figure expressed only as a formula/equity grant/commission structure with no fixed number stated (e.g. "1% equity, salary DOE") |
| `salary.currency` | an ISO 4217 currency code (e.g. `USD`, `CAD`, `GBP`, `EUR`) | a currency described only in a way that cannot be resolved to one ISO code (see the currency table below) |
| `salary.period` | exactly one of `hourly`, `daily`, `monthly`, `annual` (per `docs/DATA_MODEL.md`'s `salary_period` enum) | a period stated that maps to none of these four and cannot be reduced to one without inventing information (e.g. "per project", "one-time signing bonus" — not a recurring period at all) |
| `location.city` | a deterministic cleaned canonical spelling (see the location table below) | none under the current schema — any cleaned textual token is representable as a string; use `absent` when not stated |
| `location.state` | exactly one USPS two-letter code (50 states + DC — the current classifier is US-only; see the location table below) | a non-US state/province/region equivalent, or any spelled-out or otherwise non-two-letter form that cannot be mapped to exactly one USPS code |
| `location.country` | one canonical full-English-name form (see the alias table below) | none under the current schema — any country name is representable; use `absent` when not stated |
| `location.postal_code` | a deterministic normalized textual form (see the location table below) | none under the current schema — any normalized textual token is representable as a string; use `absent` when not stated |

### Numeric range decision table (`experience.minimum`/`.maximum`, `salary.minimum`/`.maximum`)

Applies identically to years-of-experience and salary amounts — only the
domain unit differs (years vs. currency amount).

| Pattern in sourced text | `minimum` | `maximum` |
|---|---|---|
| Single fixed value ("$120,000", "5 years of experience") | that value, `present_supported` | that same value, `present_supported` |
| Closed range ("$100,000–$120,000", "3-5 years") | lower bound, `present_supported` | upper bound, `present_supported` |
| Lower-bounded, open-ended ("$100,000+", "5+ years", "at least 5 years", "minimum 5 years") | that value, `present_supported` | `absent` — no upper bound is stated, this is missing information, not an unsupported form |
| Upper-bounded only ("up to $150,000", "up to 2 years") | `absent` — no lower bound is stated | that value, `present_supported` |
| A closed range plus a separate "ideally"/"preferred" figure inside it ("3-5 years, ideally 4") | lower bound of the range, `present_supported` | upper bound of the range, `present_supported` — the preferred figure is not part of the min/max domain and is disregarded, not treated as an ambiguity |
| Fractional/non-integer-only value ("2.5 years minimum") | `present_unsupported_form` | (apply independently to whichever bound is fractional) |

### Multiple/nested/conditional requirement table (`experience.minimum`/`.maximum`, `salary.minimum`/`.maximum`)

For records stating more than one numeric threshold. **Never sum
potentially overlapping periods or figures unless the text itself
explicitly makes them additive** — inventing a combined total the text
does not state is exactly the kind of interpretation this rubric forbids.
All examples below are fabricated.

| Pattern | Rule | Fabricated example |
|---|---|---|
| Independent requirements joined by "and", two co-equal domains, no combined figure stated | `ambiguous` — the schema has one undifferentiated `minimum`/`maximum` pair; two genuinely different, non-overlapping thresholds cannot both be represented and neither is more "the" answer than the other | "3+ years of backend engineering experience and 3+ years of frontend engineering experience." |
| Explicit cumulative/additive wording | Sum exactly as the text states — `present_supported` with the stated total, never an invented one | "5 years of engineering experience, plus 2 additional years in a lead role, for a combined total of 7 years." → `minimum = 7` |
| Nested/subset "including" wording: one general/overall threshold with a narrower sub-requirement nested inside it | Annotate the **general/outer** figure only; the nested narrower figure has no dedicated schema field and is not separately captured — this is a scope limitation, not an ambiguity | "5+ years of engineering management experience, including 2+ years managing other managers." → `minimum = 5`; the "2+ years managing managers" detail is not annotated anywhere |
| Alternatives joined by "or", same numeric field, genuinely different thresholds depending on which path applies | `ambiguous` — the true minimum depends on an unresolvable condition | "5 years of experience with a Bachelor's degree, or 3 years of experience with a Master's degree." |
| Alternatives joined by "or" where only one path is expressed as a number (the other is a non-numeric alternative, e.g. a degree with no experience figure) | The numeric path alone is `present_supported`; the non-numeric alternative is simply not part of this field's domain | "5+ years of professional experience, or an equivalent combination of education and experience." → `minimum = 5` |
| Preferred/ideal threshold stated alongside a required one | Annotate the **required** (gating) threshold only; the preferred/ideal figure is disregarded, not treated as an ambiguity (same principle as the "ideally 4" row above) | "3+ years required; 5+ years strongly preferred." → `minimum = 3` |
| Multiple salary ranges tied to different locations/conditions, no basis to prefer one for this specific record | `ambiguous` | "Salary: $130,000–$150,000 (San Francisco Bay Area); $110,000–$130,000 (Remote, all other US locations)." with no location stated elsewhere in this record indicating which band applies |
| Multiple salary ranges tied to different locations/conditions, where this record's own stated location clearly selects one band | Annotate that band's figures only, `present_supported` | Same ranges as above, but this record's `location_raw` states "San Francisco, CA" → `minimum = 130000`, `maximum = 150000` |

### Currency normalization table (`salary.currency`)

| Sourced text | Annotation | Provenance |
|---|---|---|
| "USD", "US Dollars", "$" with no other currency plausible from context | `USD` | `inferred` if the text is a symbol or a spelled-out name (mapping to the ISO code is a small interpretive step); `parsed_description` if the ISO code itself is already stated verbatim |
| "CAD", "C$", "CAN$" | `CAD` | as above |
| A bare `$`/generic currency symbol where the record's own location/context makes more than one dollar-denominated currency plausible (e.g. the same text also references a non-US country) | `ambiguous` | — |
| No currency word/symbol stated at all, even though an amount is | `absent` | — |

### Location normalization table (`location.city`/`.state`/`.country`/`.postal_code`)

**Annotate the canonical normalized output a correct classifier would
produce, not a verbatim copy of the source substring.** Aliases that are
semantically equivalent (e.g. `location_raw` reading "Remote, US") are not
a conflict with a canonical form that looks textually different (e.g.
country `United States`) — the corrected classifier output and the
source text agree in meaning even though the spelling differs, so scoring
that as `confidently_wrong` would be false.

- **Country**: one canonical full-English-name form. At minimum:
  `US`/`U.S.`/`USA`/`United States` → `United States`;
  `UK`/`United Kingdom` → `United Kingdom`. Any other country name is
  written in its own canonical full English form (e.g. "Germany",
  "Canada", "Australia") — the same alias-collapsing principle applies
  even though this table does not enumerate every country.
- **US state**: exactly one USPS two-letter code, uppercase, no periods
  (e.g. "Texas" → `TX`, "Calif." → `CA`) — this is the one location
  sub-field with a genuinely closed, mechanically validated domain in the
  current (US-only) classifier design. **A non-US state/province/region
  has no dedicated canonical form in this domain at all** — it is
  `present_unsupported_form`, exactly as the domain table above states:
  `outcome = "present_unsupported_form"`, `expected_value = null`,
  `expected_provenance = "unavailable"`. Never write the region's natural
  form into `expected_value` — the loader's closed USPS-code validator
  rejects any non-USPS-code value outright, including a genuine, clearly
  stated non-US region name.
- **City**: a deterministic cleaned canonical spelling — trim surrounding
  whitespace and punctuation, preserve the source text's own capitalization
  and spelling otherwise (no gazetteer-based renaming). A **region**, not a
  city, must not be silently annotated as one: phrases like "San Francisco
  Bay Area", "Greater Boston Area", or "Pacific Northwest" name a region,
  not a single city, and are `absent` for `city` (not `present_supported`
  with the region's name standing in for a city) unless the text also
  separately names an actual city within it.
- **Postal code**: a deterministic normalized textual form. A US ZIP5 is
  exactly five ASCII digits (`"95814"`); a US ZIP+4 is exactly five ASCII
  digits, one hyphen, and four ASCII digits (`"95814-1234"`) — not "digits
  only," since the hyphen is a required, literal part of the ZIP+4 form,
  not a digit. No internal spaces in either form. A non-US postal code is
  written trimmed, in its own natural form.

**Known, deliberate scope boundary** (not a new discovery, not something
these examples are working around): the current classifier never
populates `city` at all, for any input, by permanent design (no
city gazetteer exists) — so `location.city`'s `supported_abstention` is
expected to be at or near 100% whenever `city` is annotated
`present_supported`. This is a real, correctly-reported finding about
current classifier coverage, not a bug in this rubric or the evaluator.

| Situation | Rule |
|---|---|
| Text names exactly one geographic location, optionally with a remote/hybrid modifier ("Austin, TX (Hybrid)") | Annotate `city`/`state`/etc. from the geographic part only; the modifier is `remote_type`'s concern, not a location conflict |
| Text names two or more genuinely different geographic locations with no marked primary ("Austin, TX or Remote (anywhere in the US)"; "San Francisco or New York") | `ambiguous` for whichever sub-field actually differs between the candidates (e.g. `city`); a sub-field that happens to agree across all candidates (e.g. `country` is `United States` in both) may still be `present_supported` |
| Text gives a sub-field only implicitly (e.g. a well-known city with no state/country stated) | `absent` for the unstated sub-field — do not infer a state/country from world knowledge of the city |
| `location_raw` states some but not all sub-fields, and `description` states the rest with no conflict (e.g. `location_raw` = "Austin, TX" with no country stated; `description` separately confirms a US-based role with nothing contradicting Texas) | `description` may fill the missing sub-field (`country = United States`, `inferred`) — this is ordinary pooled-evidence handling, not a special case |
| `location_raw` and `description` state genuinely different, non-equivalent values for the same sub-field (not just a different spelling of the same value) | `ambiguous` for that sub-field — a true semantic conflict, not resolved silently in either field's favor |
| `location_raw` clearly and unambiguously states a non-US province/region as the role's location (fabricated example: `location_raw` = "Toronto, Ontario, Canada") | `location.state`: `outcome = "present_unsupported_form"`, `expected_value = null`, `expected_provenance = "unavailable"` — **never** `"Ontario"` in `expected_value`; `location.country`: `present_supported`, `expected_value = "Canada"` (the country sub-field's domain is open free text and is unaffected); `location.city`: `present_supported` per the city rule above, subject to the citywide abstention note |

## Provenance rule (for every `present_supported` annotation)

`expected_provenance` is one of exactly two values for this corpus:

- **`parsed_description`** — the sourced field(s) state the value directly
  and literally, needing no combination or interpretation (e.g. a location
  field reading exactly "Remote"; an amount stated directly as a single
  number with its ISO currency code already spelled out).
- **`inferred`** — deriving the value requires combining more than one piece
  of textual evidence, or applying straightforward domain judgment to map
  stated wording onto the closed domain (e.g. `seniority` derived from a
  title reading "Staff Engineer"; a currency symbol mapped to its ISO code;
  `experience.minimum` derived from "Bachelor's degree plus 5 years of
  experience" requiring the reader to recognize "5 years" as the minimum
  rather than a degree-equivalency clause).

No other provenance tag applies to a realistic-corpus annotation (there is no
structured metadata feed and no separate "explicit source" distinct from the
posting text itself); `derived`/`structured_metadata`/`explicit_source` must
never be used here. `unavailable` is used exactly when `expected_value` is
null (`absent`, `present_unsupported_form`, or `ambiguous`).

## Missing-information handling (`absent`)

Use `absent` whenever no *relevant* sourced evidence (per the role-relevance
filter and the source-field table above) addresses this annotation at all —
including when every sourced field is null. This is the default for any
field the sourced text simply never mentions, or only mentions in a way the
role-relevance filter discards. Do not use `absent` for a field that is
mentioned but unclear (`ambiguous`) or mentioned in a form the domain cannot
represent (`present_unsupported_form`).

## Ambiguity rule

Use `ambiguous` only when two or more *relevant* pieces of sourced evidence
themselves support genuinely different, non-equivalent values, with no
textual basis (wording, section placement, an explicit qualifier) to prefer
one over the other. A field that is merely *loosely* worded but still
resolves to one clear reading under ordinary-English interpretation is not
ambiguous — annotate the one clear reading instead. Do not use `ambiguous`
as a catch-all for "I am not fully certain"; it specifically means the
relevant sourced text itself is multi-valued, not that the annotator finds
the call hard. An irrelevant mention (per the role-relevance filter) never
creates an ambiguity against a relevant one.

## Skill-label rule

A skill-id annotation is scored on `outcome` alone (no `expected_value`/
`expected_provenance` — the outcome itself already states whether this
canonical id is expected to be identified for this record), sourced from
`title` + `description` pooled, per the source-field table, and subject to
the role-relevance filter above (a skill named only in a company/product
description, not as part of the role's own work or requirements, is
`absent` for that id — see the `skills.java` example above). For each of
the 15 canonical ids, in every record:

- `present_supported` — relevant sourced text names this exact skill (or one
  of its taxonomy aliases) unambiguously as part of the role's own work or
  requirements.
- `present_unsupported_form` — the skill is named relevantly, but only
  embedded in a way that cannot be represented as identifying this
  canonical id at all (e.g. as part of an unrelated compound proper noun
  that is not a reference to the skill itself).
- `absent` — no relevant sourced text mentions this skill at all.
- `ambiguous` — relevant sourced text's reference to this skill is
  genuinely multi-valued under the ambiguity rule above (rare for a single
  skill id; reserve for a genuine textual ambiguity, not annotator
  uncertainty).

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
  "rubric_version": "1.0.4",
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
- `rubric_version` is exactly `"1.0.4"` (this document's version) — copy it
  verbatim, do not derive or reformat it.
- `source_packet_hash` is the canonical hash value you were given alongside
  this rubric, the taxonomy, and the sanitized source packet — copy it
  verbatim.
- `frozen_at` is a timezone-aware ISO 8601 timestamp (e.g.
  `2026-09-27T18:00:00+00:00`, or with a `Z` suffix) marking when you sealed
  this pass. A naive timestamp (no offset) is rejected.
- `records` is a JSON object keyed by **exactly** the record ids you were
  given with the packet (each formatted `<board_token>:<job_id>`) — every
  one of them, none added, none removed, none renamed.

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

**Compact valid example.** Entirely synthetic: a fabricated record id, a
fabricated 2-canonical-id taxonomy (`{alpha, beta}`, for brevity — the real
taxonomy has 15 real ids, every one of which must appear), and fabricated
labels with no correspondence to any of the 30 real evaluation records or
their actual content. `source_packet_hash` below is an illustrative
placeholder — copy the *actual* value you were given with your packet,
never this one (this document's own bytes feed into that hash, so no value
written here could ever be the real one):

```json
{
  "schema_version": "1",
  "annotator_role": "claude",
  "rubric_version": "1.0.4",
  "source_packet_hash": "<the actual value handed to you with your packet, copied verbatim>",
  "frozen_at": "2026-09-27T18:00:00+00:00",
  "records": {
    "examplecorp:0000000001": {
      "remote_type": {"outcome": "present_supported", "expected_value": "remote", "expected_provenance": "parsed_description"},
      "employment_type": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
      "seniority": {"outcome": "absent", "expected_value": null, "expected_provenance": "unavailable"},
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
schema exactly, without seeing any code, any test, or the other pass. **No
rubric example may pre-label or quote any of the 30 real evaluation
records** — every example in this document is fabricated, including the one
above.
