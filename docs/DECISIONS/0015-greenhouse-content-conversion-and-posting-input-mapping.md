# 0015 — Greenhouse content conversion and strict posting-input mapping

## Status

Accepted with Phase 4 Slice S2b (`phase-4/greenhouse-content-mapping-s2b`, risk class H,
`slice_kind: parser`, `gate: final`), base `e670575d5b05395cb9eeb2ec84833cc0034c7002`
(`Q` of the S2 merge). Pilot product slice 3 of 3 under
[ADR 0012](0012-workflow-throughput-protocol-pilot.md).

The contract is the implementer's consolidated S2b proposal as amended by the user's
decisions U1–U4 and Sol Medium's binding proposal review (amendments A1–A20 and a
corrected mutation inventory W1–W19), integrated into one frozen contract. This ADR
changes nothing in [ADR 0011](0011-phase-3-exit-audit.md),
[ADR 0013](0013-direct-greenhouse-job-board-provider.md), or
[ADR 0014](0014-pure-posting-composition-and-scoped-d2.md).

## Context

ADR 0014 §7 recorded, but did not implement, the provider-field allowlist: only
Greenhouse `title`, `location.name`, and converted `content` may become parser inputs.
ADR 0014 §8 made S2b the offline slice that converts `content` and maps those three
fields, before the separately authorized S2c live canary.

Two repository facts shaped the evidence:

- No captured raw Greenhouse `content` HTML exists. ADR 0010's acquisition never retained
  raw bodies; the corpus holds converted, contact-redacted text only; S1's canary sample
  has no `content`; S1's records are synthetic.
- The only real encoding evidence is ADR 0010's detail-endpoint observation for three
  boards, whose `content` was escaped once more than plain HTML. How the `/jobs?content=true`
  list endpoint, the one S1 calls, encodes `content` is unknown. ADR 0014 §7 deferred
  list-endpoint content-mode evidence (U6) to S2b; S2b cannot produce it offline, so that
  deferral is not discharged here and moves to S2c.

## Decision

### 1. Modules and placement

- `app/providers/greenhouse_content.py`: the provider-specific conversion boundary.
  Standard library only (`dataclasses`, `enum`, `html`, `html.parser`, `re`, `typing`,
  `unicodedata`); no I/O, logging, network, or global mutable state.
- `app/providers/greenhouse.py`: `GreenhouseBoard.content_mode`, and conversion inside
  `_to_discovered_job`. It imports `greenhouse_content` and nothing else new; it imports
  neither `normalization/` nor the mapper.
- `app/providers/greenhouse_posting_inputs.py`: the provider-to-normalization bridge,
  `greenhouse_posting_inputs(job) -> PostingInputs`. It imports only
  `app.normalization.posting` and `app.schemas.discovered_job`. It is the sole, named
  exception to ARCHITECTURE's rule that `providers/` never imports `normalization/`: it
  uses only the `PostingInputs` value type and calls no parser.

No other runtime module imports either new module, and `greenhouse.py` itself remains
unregistered and unreachable at runtime.

### 2. Content modes

Exactly two modes, declared per board and never inferred from content, a board token, or
anything else. There is no mode lookup, fallback, or retry under another mode.

| Mode | Behavior |
|---|---|
| `disabled` (default) | No selective or keyed access to, interpretation of, or conversion of `content`: no membership test, indexing, `.get`, comparison, stringification, hashing, or converter call. Field-agnostic source parsing (S1's whole-record JSON parse) and the whole-record deep copy required to preserve `raw` may traverse it without branching on its value. `description=None`, exactly as in S1. |
| `declared-double-escaped` | The conversion contract below. |

`declared-double-escaped` is the compatibility name of the reviewed one-predecode
algorithm in `scripts/greenhouse_html_convert.py` (ADR 0010). **It is not a claim that
every accepted input contains escaped tags**: literal HTML with no escaped-angle reference
is also accepted, because the single `html.unescape()` pass is then a no-op. Input this
mode rejects stays rejected. Observing a different encoding shape later does not authorize
a new mode. `standard` is not accepted.

An invalid mode (anything other than the exact built-in `str` values above) raises the
fixed message `content_mode must be 'disabled' or 'declared-double-escaped'`, without the
supplied value, as `GreenhouseConfigurationError` at board construction and as
`ValueError` from the converter.

### 3. Conversion contract

`convert_greenhouse_content(content, *, mode) -> ContentConversion(text, outcome)`.
`text` is non-`None` iff `outcome` is `converted`. The outcome set is closed: `converted`,
`not_requested`, `absent`, `blank`, `invalid_type`, `input_too_large`, `output_too_large`,
`empty_after_conversion`, `mixed_literal_and_escaped_markup`,
`unsupported_angle_reference`, `residual_nested_encoding`, `unclosed_suppressed_element`,
`malformed_truncated_markup`, `parser_error`.

Validation order, first failure wins:

1. mode (`disabled` returns `not_requested` before `content` is inspected);
2. absent (`None`) or type: only an exact built-in `str` is accepted; a subclass or any
   other object is `invalid_type`;
3. input length: more than `MAX_CONTENT_CHARS` (200,000) is `input_too_large`;
4. blank: only covered whitespace (`" \t\n\r"`) is `blank`;
5. raw encoding checks, then exactly one `html.unescape()`, then decoded encoding checks;
6. extraction with `html.parser.HTMLParser(convert_charrefs=True)`, followed by the
   end-of-input integrity check below; `parser_error` precedes
   `unclosed_suppressed_element` (an open `script`/`style`), which precedes
   `malformed_truncated_markup`;
7. meaningfulness: text made only of whitespace or Unicode format (`Cf`) characters,
   including empty text, is `empty_after_conversion`;
8. output length: more than `MAX_DESCRIPTION_CHARS` (100,000) is `output_too_large`.

The encoding checks reuse the reviewed script's exact predicates and precedence:

- raw: a literal `<`/`>` together with an escaped-angle reference (named `&lt;`/`&gt;`/
  `&LT;`/`&GT;`, decimal `60`/`62`, or hex `3c`/`3e`, each with the script's exact
  terminator rule) or a semicolonless named form is `mixed_literal_and_escaped_markup`;
  otherwise a semicolonless named `&lt`/`&gt`/`&LT`/`&GT` is
  `unsupported_angle_reference`;
- decoded: a semicolonless named form is `unsupported_angle_reference`; otherwise a
  remaining escaped-angle reference is `residual_nested_encoding`.

The semicolonless guard is deliberately blunt: `&ltimes;` is rejected as
`unsupported_angle_reference`. `&Lt;`/`&Gt;` are unrelated entities (U+226A/U+226B) and
are accepted.

Extraction rules:

- line endings (CRLF and lone CR) become LF before parsing and again afterwards, which
  covers decoded `&#13;`;
- block tags are exactly `p div br li h1–h6 ul ol`; each start, end, or self-closing tag
  ensures one `\n`; every other tag is inline and inserts nothing; lists get no markers;
- `script`/`style` content is dropped; an unclosed one is `unclosed_suppressed_element`;
- attributes, comments, declarations, processing instructions, and CDATA sections are
  never emitted; malformed ordinary tags are tolerated through the parser's recovery;
- per line, runs of ASCII space/tab collapse to one space; runs of blank lines collapse
  to one; leading and trailing `\n` are stripped; no-break space and every other Unicode
  whitespace or format character is kept.

Only a `RecursionError` from `HTMLParser.feed()`/`close()` becomes `parser_error`; any
other exception is a defect and propagates. Output is plain text and never re-escaped.
Conversion is a pure function of `(content, mode)` on a given interpreter.

**End-of-input integrity (fail-closed truncation).** `html.parser`, and therefore the
oracle, silently drops everything after an unterminated comment, an unterminated quoted
attribute, or a tag-like fragment such as `A<B rest`, and would report the remaining
prefix as success. This module instead feeds the decoded text followed by one internal
marker element `<NAME></NAME>`:

- `NAME` is `ghintegrity-` plus one more `z` than the longest `ghintegrity-z…` run in the
  decoded text, compared case-insensitively. The name therefore occurs nowhere in the
  source, so source text cannot forge, satisfy, collide with, or suppress the check.
  Selection is pure and linear-time.
- The marker emits no text and no block boundary.
- After the parser closes, exactly one ordered start/end pair of the marker must have been
  seen. Otherwise an unfinished construct swallowed or corrupted the end of the input,
  and the outcome is `malformed_truncated_markup` with no text.
- Caps measure only source and output text, never marker material.

- Whether a `script`/`style` element is still open is recorded before the marker is fed,
  so the marker cannot complete a dangling `</style`-style end tag and hide the open
  element; that case stays `unclosed_suppressed_element`.

Malformed ordinary markup that keeps its trailing visible text still converts unchanged:
unclosed or mismatched ordinary tags, and a bare `<` that is not a tag start. Two
deliberate behavior changes from the original candidate:

- a trailing unfinished fragment such as `A</`, `x</p`, or `<p>Intro</p><!` now
  abstains;
- an unclosed raw-text element (`title`, `textarea`, `xmp`, `iframe`, `noembed`,
  `noframes`, `plaintext` on CPython 3.12.13) now abstains. `html.parser` treats its
  content as literal text, so it swallows the marker; in the oracle it turns all later
  markup into literal text. Closed raw-text elements still convert.

Where this module converts, its text still equals the oracle's. Only end-of-input
swallowing is detected: when a later quote or `-->` closes a swallowing construct
mid-input, the lost text is not detected, and the outcome stays `converted`.

Extraction rides on the running interpreter's standard-library `html.parser`. Its handling
of comments, declarations, CDATA, and unterminated markup has changed between CPython patch
releases, and the oracle shares that parser, so differential agreement alone cannot detect
such drift. Determinism and the never-raises guarantee were verified on CPython 3.12.13 (the
project allows `>=3.12,<3.13`). Literal golden expectations for the parser-sensitive
inputs are pinned separately, so a standard-library behavior change fails a test and
requires review.

**This is deterministic text extraction only.** It is not sanitization or security
cleaning. Converted text can contain contact details or anything else the source
contained; nothing redacts it.

**Caps** count Python Unicode code points, not bytes. Exactly at a cap is accepted, one
past it abstains, and nothing is truncated. The byte boundary is a separate layer: S1
caps a complete HTTP response at five megabytes before any record exists, and the
character cap bounds a direct converter call.

### 4. Adapter outcome partition (U4)

- A disabled board is neutral: `description=None`, no content warning, no degradation.
- On an enabled board only `converted` is neutral. Every other outcome, including
  `absent` and `blank`, is an incomplete conversion: the job is kept with
  `description=None`, and the board becomes partial if otherwise usable. This applies
  S1's existing semantics: `incomplete_results=True`, `possibly_incomplete=True`, and
  partial health.
- A board whose kept records all fail conversion is still completed, with every job
  retained. A successful empty board stays complete and not incomplete, because no record
  needed conversion. All-board failure is unchanged.
- Record validity, skipping, duplicate handling, completeness evidence, retries, labels,
  and `compensation_text=None` are unchanged.

### 5. Warnings

Incomplete outcomes are aggregated source-wide and reported as exactly one warning per
outcome, sorted by outcome value:

`greenhouse content_unconverted=<outcome> count=<decimal>`

These warnings contain no board token, content, excerpt, exception text, title, job ID,
URL, or raw value. S1's existing per-board diagnostics, which do carry the public board
token, are unchanged.

### 6. Raw preservation and temporary traceability

Conversion reads only the original `content` value, and only on an enabled board. It
never modifies the source record or `raw`. `raw` remains a deep, structurally equal,
non-aliased copy of the whole record with an equal `canonical_json_hash`, including the
original HTML and unknown fields.

No `DiscoveredJob` or persistence field records the mode or outcome. Until S3, the
available evidence is the immutable board configuration, `ContentConversion.outcome`,
the internal aggregate counts, the token-free warnings, the retained raw structure, and
`description is None` on abstention. **This is not D1 traceability.** S3 must bind
persisted normalization to source input, conversion mode and version, parser version,
and provenance.

### 7. Strict mapping

| Greenhouse source | `DiscoveredJob` | `PostingInputs` |
|---|---|---|
| `title` | `title`, verbatim (S1) | `title` |
| `location.name` | `location`, verbatim (S1) | `location` |
| `content` | `description`, converted under a declared mode | `description` |

`greenhouse_posting_inputs` raises a fixed `TypeError` for a non-`DiscoveredJob` and a
fixed `ValueError` unless `provider` and `source` are both `"greenhouse"`. It reads only
`provider`, `source`, `title`, `description`, and `location`, by direct attribute access,
and returns `PostingInputs(title=job.title, description=job.description,
location=job.location)` with no transformation. Whitespace, Unicode, and the empty/`None`
distinction are preserved exactly; string-object identity is diagnostic only, not a
contract. It never reads `raw`, `company`, URLs, IDs, timestamps, or
`compensation_text`, and uses no reflection, serialization, dynamic import or execution,
or fallback (AST checks plus access tracing). Never parser inputs: `company_name`,
`metadata`, `departments`, `offices`, `updated_at`, `first_published`, `requisition_id`,
`absolute_url`, `pay_transparency`, and any other raw key. The bridge creates no
provenance tag; parsers assign their own.

### 8. Evidence identities

- Differential oracle (frozen and unmodified): `backend/scripts/greenhouse_html_convert.py`
  canonical-LF SHA-256 `fff4b1c09765eb02def5f79c7b1b9bbfa58e20b1ed96edd2b96c5c852e2cd06f`;
  its tests `backend/tests/test_greenhouse_html_convert.py`
  `2bdf301475fa79aad36ac84efa1ee73bc0959d2e376dcd6e49eb63084b89fcd1`. Both are pinned;
  either changing fails and requires review. Shared vectors and the category mapping
  must agree.
- Corpus `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json`: canonical JSON
  SHA-256 `ca6e129110b71801e18d6bfba84d59376c689f67cb470f1335ab8805cd388f00`, committed
  content (canonical-LF) SHA-256
  `1863541bb784419be16bf4ffcf88bf1b4408c951a03b12008e9645e9f18e6930`, the authoritative
  value. An earlier abbreviated form, `…6e930`, was a typo; the corpus did not change.
- Canary `backend/tests/fixtures/discovery/greenhouse_live_canary.json`: committed content
  (canonical-LF) SHA-256 `690b0a5d0f85599c44b88d2d2b483114ba4bc0db19647238feee280a2a6db4d5`.
  It has no `content` and proves only existing title/location behavior.
- Every other input is synthetic. The 30 corpus envelopes are reconstructed synthetic raw
  shape, built in the test as
  `html.escape("<div>" + html.escape(description, quote=False) + "</div>", quote=False)`,
  not captured Greenhouse HTML.

### 9. Bounded D2 claim

> For these 30 reconstructed synthetic envelopes, S1→S2b produces the same three parser-input strings as the published S2 corpus invocation and therefore reproduces its pinned outputs. This is regression evidence for that exact reconstructed shape, not captured raw-HTML, list-endpoint encoding, generalization, or live-provider evidence.

Title remains smoke-only.

### 10. Retained limitations

- Real list-endpoint (`/jobs?content=true`) encoding is unproven; there is no captured
  raw `content` evidence.
- Real HTML variety is unproven; table cells and `section`/`blockquote`/`pre`/`hr` content
  run together, `noscript`/`template` text is kept, and legitimate escaped code examples
  are rejected.
- Unicode-whitespace and format characters are preserved; output made only of them
  abstains.
- Only end-of-input truncation is fail-closed. Text swallowed mid-input by a construct
  that a later quote or `-->` closes is still lost silently.
- Behavior depends on the interpreter's `html.parser`; it was verified on CPython 3.12.13
  and is golden-pinned for parser-sensitive inputs, not guaranteed across patch releases.
- In-memory descriptions are unredacted. Nothing logs or persists them; storage policy is
  S3's.
- D1 is unsatisfied and no normalized write is authorized. ADR 0011 L4 stays open: salary
  is not composed and `compensation_text` stays `None`. The ten unproven components of
  ADR 0014 stay unproven. The corpus is exposed (ADR 0010/0011), with three employers and
  30 records; title is smoke evidence only.
- Nothing is registered or reachable at runtime; this is no production-usefulness claim.
  S2b's mutation experiments are recorded advisory-candidate evidence, not registered
  witnesses; the 34 registered witnesses are unchanged.

### 11. Pilot and S2c

S2b is pilot product slice 3 of 3. After its `Q`, the ADR 0012 pilot evaluation happens
before any S2c authorization. S2c remains a separate Class H slice requiring:

- explicit network authorization;
- Sol Medium and Astra review;
- a review of Greenhouse's Job Board API terms of use;
- one named board initially; a second only with authorization that names it explicitly,
  or an original authorization that names it conditionally;
- default-off execution, GET-only requests, and explicit attempt, time, response, and
  record caps;
- no raw or content logging, no retention by default, and no database write;
- a pre-agreed categorical report that includes the observed raw encoding shape.

No observed encoding may cause automatic mode selection or fallback; S2c may not
silently select `standard` or another algorithm.

## Exclusions

S2b does not contact Greenhouse or any network; use a database or production data;
persist anything or thread D1/`parser_version`; add a migration or schema field; register
or wire anything into the registry, composition root, settings, kill switch, or
ingestion; compose salary; map any non-allowlisted field; change any parser, the
taxonomy, the corpus or annotations, the evaluator, the frozen scripts converter or its
tests, `posting.py`, the D2 module, or any validator, verification tool, schema, or
registered witness; or begin S2c, S3, or S4.

## Consequences

- A Greenhouse board can now yield parser-ready `description` text offline, under an
  explicit declaration, with abstention reported as incomplete results.
- A three-field bridge to `PostingInputs` exists and is guarded; nothing calls it at
  runtime.
- S2c can test the declared mode against one real board's list response; S3 must still
  satisfy D1 before any normalized write.
