# 0004 — Scoped deterministic identity resolution and URL normalization

## Status
Accepted, revised (Rev 3 / second design review). Supersedes the identity-matching
portions of [0001-job-vs-job-occurrence.md](0001-job-vs-job-occurrence.md) and
[0002-two-tier-duplicate-detection.md](0002-two-tier-duplicate-detection.md) (both
updated to point here rather than restate it). Collision/conflict handling below was
found to be infeasible as originally written and is now delegated to
[0007-identity-conflict-quarantine.md](0007-identity-conflict-quarantine.md) — see the
"Rev 3 revision" subsection under Decision.

## Context
Rev 1 of the architecture treated "identical ATS requisition ID" as a standalone
deterministic signal for attaching a new occurrence to an existing `Job`, alongside
canonical-URL match and `(provider, source, source_job_id)` match. A design review
correctly flagged this as unsafe: a requisition ID is only unique *within the scope that
issued it* — one ATS tenant, one employer's instance of a platform. Two different
companies hosted on the same ATS (or the same company across two ATS migrations) can
legitimately reuse the same requisition number. Matching on a bare requisition ID risks
silently attaching one employer's occurrence to a completely unrelated employer's `Job`
— exactly the "silently merge unrelated jobs" failure mode the project's dedup
requirements (§19) explicitly forbid.

A related gap: canonical-URL matching was specified ("identical canonical URL") without
defining what "identical" means. Two URLs that are semantically the same posting can
differ in case, tracking parameters, trailing slash, or default port — comparing raw
strings would under-match; naively stripping *all* query parameters would over-match
(some ATS platforms encode the actual posting identity in a query parameter, not the
path).

## Decision

### Scoped identity signals
Add `source_tenant_id` and `requisition_id_raw` to `job_occurrences` (see
[DATA_MODEL.md](../DATA_MODEL.md)). `source_tenant_id` identifies the ATS
tenant/employer-account *within* `(provider, source)` — a Workday tenant subdomain, a
Greenhouse board token, a Lever company slug — and is null for sources with no tenant
concept (LinkedIn, Indeed). `requisition_id_raw` is the requisition ID exactly as
reported by that source, never compared on its own.

### Canonical URL normalization
Defined once, in `normalization/url.py`, applied before any comparison:
1. Lowercase scheme and host.
2. Drop the fragment (`#...`).
3. Strip default ports (`:80` for http, `:443` for https).
4. Normalize trailing slash (strip except for the bare root path).
5. Strip known tracking query parameters (a maintained deny-list: `utm_*`, `gh_src`,
   `lever-source`, `trk`, `li_fat_id`, `ref`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`, and
   similar).
6. **Retain parameters that are part of a given source's identity scheme** even if they'd
   otherwise look like tracking noise (e.g. a query parameter that actually encodes the
   posting/requisition ID for a given ATS) — governed by a per-source allow-list that
   overrides the generic deny-list. This list starts empty/conservative and grows only
   when a specific source is confirmed (during Phase 4/7 adapter work) to encode identity
   in a query parameter.
7. Sort remaining query parameters alphabetically for stable string comparison.

The result is stored as `job_occurrences.canonical_url_normalized` /
`source_url_normalized` (see [DATA_MODEL.md](../DATA_MODEL.md)) — the raw values are kept
too, for display and click-through, but only the normalized forms participate in
matching.

### Match precedence (tried in order; first match wins)
1. **Natural key, same occurrence**: `(provider, source, source_tenant_id,
   source_job_id)` exact match → this is a re-observation of the *same* occurrence row,
   not a new one — update in place. Enforced by two separate partial unique indexes, not
   one — see "NULL-safety" below.
2. **Normalized canonical URL** exact match across *different* occurrences → strongest
   cross-occurrence signal; a URL is inherently host-scoped so no additional tenant
   scoping is needed here.
3. **Tenant-scoped requisition**: `(provider, source, source_tenant_id,
   requisition_id_raw)` exact match across occurrences, when no canonical URL is
   available but a tenant is known. **Rev 3 fix:** the key now includes `provider`/
   `source`, not just `source_tenant_id` — see "Namespace scoping" below.
4. **Company-scoped requisition — fallback only**: `(company_id, requisition_id_raw)`
   exact match, used only when `source_tenant_id` is unavailable at all. Weaker, because
   a requisition ID isn't guaranteed unique across a company's own multiple ATS
   instances.
5. No match → create a new `Job` — provided a stable occurrence key can actually be
   derived (`source_job_id`, or a normalized `source_url` via the fallback
   `job_occurrences_fallback_url_key` index). **Phase 2 clarification (narrow, no schema
   change):** a payload with neither is not "no match" in the sense this step means —
   there is no key at all to create an occurrence *under*. Such a payload is recorded as
   `processing_status = 'parse_error'` (its raw form still preserved in
   `raw_job_ingestions.raw_payload`) rather than persisted as an unkeyed occurrence, which
   the database could not actually enforce as unique.

### NULL-safety (Rev 3 fix)
Step 1's natural key was originally one partial unique index —
`UNIQUE (provider, source, source_tenant_id, source_job_id) WHERE source_job_id IS NOT
NULL` — which does not actually enforce uniqueness when `source_tenant_id` is `NULL`,
because PostgreSQL unique indexes treat every `NULL` as distinct from every other `NULL`.
Since `source_tenant_id` is `NULL` by design for LinkedIn/Indeed (no tenant concept),
this silently permitted unlimited duplicate rows for exactly the sources re-ingested most
often. Fixed with two separate partial indexes instead of one combined index or a
PG15 `NULLS NOT DISTINCT` clause (see [ARCHITECTURE.md §2](../ARCHITECTURE.md#2-architectural-style-confirmed)
for the version-portability reasoning): one scoped to `source_tenant_id IS NOT NULL`,
one scoped to `source_tenant_id IS NULL` with `source_tenant_id` simply omitted from its
key (the semantically correct key for those sources, not a workaround). Full SQL and the
required Phase 1 tests are in
[ARCHITECTURE.md §8](../ARCHITECTURE.md#8-deterministic-identity-resolution).

### Namespace scoping (Rev 3 fix)
Step 3's key originally omitted `provider`/`source`
(`(source_tenant_id, requisition_id_raw)` alone), which implicitly assumed a
`source_tenant_id` value is comparable across different providers/sources without saying
so. It isn't specified to be — a Workday tenant subdomain captured via `ats_scrapers` and
some hypothetical value another library might call a "tenant ID" for an unrelated source
have no defined relationship. The key now includes the full `(provider, source,
source_tenant_id, requisition_id_raw)` namespace it's actually scoped within. If a real
need later arises to match across two genuinely different providers hitting the same
real-world ATS tenant, that requires defining an explicit, separately normalized ATS
identity concept (e.g. a `companies`-level `ats_tenant_key`) — not silently dropping
`provider`/`source` from this key and hoping tenant identifiers happen to collide
meaningfully.

### Collision and ambiguity handling (Rev 3 revision)
Originally (Rev 2) this ADR said a conflict at step 1 or 2, or an ambiguous match at step
4, should "create a new `Job` for the incoming occurrence." **For step 1 specifically,
that's infeasible**: a step-1 match means a row with that exact natural key *already
exists*; inserting a second row with the same key would violate the constraint that makes
step 1 meaningful in the first place. The corrected behavior, detailed in
[0007-identity-conflict-quarantine.md](0007-identity-conflict-quarantine.md):
- **`evidence_mismatch`** (step 1 only): the natural key matches an existing occurrence,
  but the incoming payload's normalized canonical URL conflicts with the one already
  recorded. No second occurrence is created; the existing occurrence's disputed field is
  left untouched, purely observational fields still update, and an `identity_conflicts`
  row is recorded.
- **`ambiguous_match`** (steps 2–4): a matching step finds more than one distinct
  candidate `Job`. This *is* a genuinely new occurrence (no existing row shares its
  natural key), so creating a new, standalone `Job` for it remains valid and safe — it's
  flagged via an `identity_conflicts` row for review rather than guessed into one of the
  candidates.

Both route to a new `identity_conflicts` table (Phase 1 migration, first used by Phase
2's fixture proof) — **not** `duplicate_groups`, which
[0002](0002-two-tier-duplicate-detection.md) now reserves exclusively for Tier 2's fuzzy
matching. Every signal used in steps 1–4 remains an *exact* match on a scoped key — it's
the scoping that's new relative to Rev 1, not the exactness; a correctly-scoped exact
match with no conflicting evidence still auto-attaches with no review.

`jobs.requisition_id` (the resolved §20 display field) is populated from whichever
occurrence's value is most authoritative, after identity resolution — it is never used as
an input to identity resolution itself.

## Consequences
- Two unrelated companies reusing the same requisition number, or a job board scraping a
  requisition ID without tenant context, can no longer cause a silent cross-employer
  merge.
- Every provider adapter (Phase 4's `AtsScrapersProvider`, Phase 7's `JobSpyProvider`)
  must populate `source_tenant_id` whenever the underlying source exposes one — this is
  now a concrete adapter responsibility, not an afterthought. For `ats-scrapers`
  specifically, confirming exactly which field maps to tenant identity per ATS type is
  flagged as open Phase 4 work (see [ARCHITECTURE.md §10](../ARCHITECTURE.md#10-where-ats-scrapers-and-jobspy-plug-in)).
- URL normalization is centralized in one pure function, testable independently of any
  provider or database (per [ARCHITECTURE.md §5](../ARCHITECTURE.md#5-dependency-boundaries)'s
  rule that `normalization/` has no external dependencies) — the fixture-driven proof
  ([ARCHITECTURE.md §11](../ARCHITECTURE.md#11-fixture-driven-end-to-end-ingestion-proof-phase-2-target))
  includes a dedicated colliding-requisition-across-tenants case specifically to prove
  this doesn't regress.
- The per-source URL allow-list (retained identity query parameters) will need real-world
  tuning once Phase 4/7 adapters see actual ATS/aggregator URLs; it's deliberately
  specified as "starts conservative, grows with evidence" rather than guessed exhaustively
  now.
