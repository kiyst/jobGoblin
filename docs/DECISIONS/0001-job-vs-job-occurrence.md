# 0001 — Job vs. JobOccurrence

## Status
Accepted.

## Context
Job postings for the same conceptual opening routinely appear on multiple sources: an
employer's ATS (Workday, Greenhouse), plus aggregators that scrape or re-list it
(LinkedIn, Indeed, Glassdoor). Each appearance can differ in URL, applicant count,
posting date, and even description quality. Collapsing all of these into a single row
per "job" destroys provenance (which source said what) and source-specific facts
(applicant count is meaningless once merged across sources). Treating every appearance
as an independent, unrelated job produces duplicate spam in the feed and hides that
they're the same opportunity.

## Decision
Split into two entities:

- **`Job`** — the conceptual opening. Holds resolved canonical fields (title, company,
  salary, location, etc.), each with a provenance tag, resolved from whichever
  occurrence(s) supplied the best-available value (see DATA_MODEL.md's field-merging
  section).
- **`JobOccurrence`** — one observed appearance on one `(provider, source)` pair. Holds
  everything that is inherently source-specific: `source_url`, `apply_url`,
  `applicant_count`, per-source `first_seen_at`/`last_seen_at`, and a link to the
  `RawJobIngestion` that produced it.

A `Job` has one or more `JobOccurrence`s. New occurrences attach to an existing `Job`
when ingestion finds a **scoped** deterministic identity match — never a bare/unscoped
requisition-ID match, which is unsafe (a requisition ID is only unique within one ATS
tenant or company; see [0004-scoped-deterministic-identity.md](0004-scoped-deterministic-identity.md)
for the full precedence order and why). Otherwise a new `Job` is created. This
deterministic attachment is distinct from — and runs before — the probabilistic
duplicate-candidate tier described in
[0002-two-tier-duplicate-detection.md](0002-two-tier-duplicate-detection.md).

## Consequences
- Applicant counts, source URLs, and per-source freshness are never averaged, summed, or
  otherwise conflated across sources — they stay attached to the occurrence that
  reported them.
- A `Job` can be "closed" only when every occurrence is inactive; a single source
  removing a posting doesn't hide the job if it's still live elsewhere.
- Every write path that creates an occurrence must decide identity-resolution first
  (`ingestion/identity.py`, scoped per [0004](0004-scoped-deterministic-identity.md)),
  which centralizes the one piece of logic every provider adapter would otherwise
  reimplement inconsistently.
- Query code that just wants "the job to show in the feed" reads `Job`'s resolved
  fields; code that needs "where did this come from and can I click through" reads
  `JobOccurrence`.
