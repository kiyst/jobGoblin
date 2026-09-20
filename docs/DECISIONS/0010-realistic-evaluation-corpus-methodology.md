# 0010: Realistic Phase 3 evaluation corpus -- methodology, sanitization, and readiness

## Status

Accepted (Class H realistic-corpus evaluation slice).

## Context

`PHASE_RISK_CHECKLIST.md`'s Phase 3 "Required prevention" list names an
unmet exit criterion: "Build a regression corpus from realistic captured
payloads with sensitive information removed." All seven merged Phase 3
classifiers (`remote_type`, `employment_type`, `seniority`, `experience`,
`salary`, `location`, `skills`) are tested only against synthetic
fixtures; every one of their own test suites explicitly asserts no case
claims `origin: "sanitized_capture"`. `app/normalization/taxonomy.py` is
infrastructure the `skills` classifier consumes, not itself a classifier.
Title normalization remains unimplemented.

This slice defines how a real, honestly-sourced evaluation corpus is
acquired, sanitized, annotated, partitioned, and scored -- without
weakening correctness, database-safety, credential-safety, or
fail-closed publication controls, and without introducing a new
workflow/verification framework.

## Decision

### Acquisition and sanitization

- Public Greenhouse Job Board API only, GET-only, no credentials, a
  closed board-token list named in the user's own authorization
  statement -- never substituted.
- Two-phase fetch per board: one metadata-only list request (never
  `content=true`), then deterministic selection of up to 10 job ids
  (sorted by stringified id, before any description exists to examine),
  then one detail request per selected id (never `questions=true`/
  `pay_transparency=true`). Zero retries, matching
  `canary_greenhouse.py`'s own established property.
- Only `id`, `title`, `location.name`, and `content` are ever read from
  a response. Every other key -- documented or not -- is never
  traversed, logged, staged, or committed, because nothing in
  `fetch_greenhouse_evaluation_postings.py` accesses it. The committed
  schema (`title`, `description`, `location_raw`, `compensation_text`,
  the provenance block) is closed independently of what the upstream API
  happens to send.
- HTML-to-text conversion (`greenhouse_html_convert.convert_html_to_text`)
  is deterministic: covered whitespace is exactly `" \t\n\r"`; CRLF/CR
  normalize to `\n`; each block boundary is one `\n`; horizontal
  ASCII space/tab runs collapse to one space per line; repeated
  generated blank lines collapse to one; NBSP and every other Unicode
  whitespace/format character are preserved unchanged.
- Email/phone-pattern redaction is defense in depth only -- it is never
  claimed to guarantee the absence of personal/contact data. Every
  sanitized candidate requires mandatory manual human review before it
  may be committed.
- Raw response bodies and raw HTML exist only as in-process values for
  the duration of processing one job, then are discarded -- never
  written to any file, temporary or otherwise, in raw form.
- The fetcher requires at least two distinct boards to each yield >=1
  usable record; otherwise it aborts and stages nothing. A failing
  board is skipped, never retried, never substituted with an unapproved
  one.
- Staging is a fixed, gitignored path, written atomically and
  create-only, only after the full authorized batch succeeds. The final
  committed corpus is likewise atomic and create-only -- a later
  revision is a new file, never an overwrite.

### `compensation_text`

The fetcher never populates a dedicated compensation field (none is
fetched). A non-null `compensation_text` may only be introduced later,
manually, as a verbatim substring of the record's own sanitized
`description`, recorded with its exact source offsets. The corpus
loader validates this at load time: `description[start:end] ==
compensation_text` exactly, or the record fails closed.

### Annotation

- Labels are assigned by reading `fields` only, blind to any parser
  output.
- Every annotation records `annotator_role`, `rubric_version`,
  `annotation_provenance`, and is explicitly `frozen: true` (with
  `frozen_at`) before any evaluation run may use it.
- A disagreement between two independent annotations escalates to
  explicit adjudication, recorded on the annotation itself; an
  unresolved disagreement (`adjudication` missing/null) fails the
  loader closed.
- Four outcome classes per parser/component: `present_supported`,
  `present_unsupported_form` (documented, deliberately unhandled),
  `absent`, `ambiguous`. `expected_value`/`expected_provenance` are
  required for every outcome (never merely "where convenient"):
  `present_supported` may carry a real value; the other three require
  `expected_value: null` and `expected_provenance: "unavailable"`,
  mirroring `NormalizationResult`'s own invariant.
- `skills` is scored differently: a frozen `expected_canonical_ids`
  set. Any returned skill outside that set scores as a false positive
  unconditionally. Correcting a genuine annotation omission is only
  ever a new corpus revision -- never an in-place edit of the current
  one -- and graduates one exposed holdout record to `dev` when it
  happens.
- When a holdout record's mismatch is manually inspected, that record's
  `split` moves to `dev` in the next revision; it is never reused as an
  unbiased holdout example again.

### Partitioning and readiness

Development and holdout use disjoint employer/template groups wherever
at least two employers exist in the corpus. Readiness is evidence, not
an arbitrary count: the evaluator reports the achieved opportunity
matrix (every parser/component x outcome class, with real counts) --
never a target the corpus writer fabricates examples to fill. A
naturally-empty cell is a disclosed gap.

### Metrics

Every metric reports numerator and denominator explicitly; a zero
denominator prints `N/A`, never `0%`. Supported-case correctness,
supported-case abstention, and confidently-wrong output share one
denominator (`present_supported` annotations with a runtime result).
False positives on `absent`/`present_unsupported_form`/`ambiguous` are
three separate denominators, never merged. Runtime failures are counted
per parser invocation. Composite parsers (`experience`, `salary`,
`location`) are scored per independently-annotated component, never as
one all-or-nothing match. `skills` is scored set-based (precision/
recall) against the frozen expected set. No pass threshold is defined
anywhere -- this is a report, not a gate.

## Consequences

- The evaluator (`evaluate_phase3_corpus.py`) and fetcher
  (`fetch_greenhouse_evaluation_postings.py`) are product-evaluation
  code, not workflow/verification tooling -- they never touch
  `verify.py`/`check_review.py`/the coordinator, and are excluded from
  any discretionary-tooling freeze.
- Nothing in this slice changes parser semantics, database state, or
  the existing C -> A -> R -> M -> Q publication chain.
- Until the separately authorized network contact and manual review
  complete, no real corpus exists and no accuracy claim is made -- the
  loader and evaluator are validated only against hand-constructed
  fixtures proving the mechanism itself is correct.
