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

## Phase 2 implementation notes (Tier 2/3 cross-occurrence attachment slice)

`ingestion/persistence.py::upsert_job_occurrence()` implements match-precedence steps 2
and 3 as a bounded slice, following Tier 1's own "found" branch. Decisions resolved during
implementation:

- **Tier 2/3 are mutually exclusive per posting, not sequential fallbacks.** Step 2
  (canonical URL) is attempted only when the incoming canonical URL normalizes to a usable
  value; a miss there proceeds directly to step 5 (create a new `Job`) — step 3 (tenant-
  scoped requisition) is **never** attempted for that posting, even though this ADR's own
  step ordering lists it next. Step 3 is attempted only when the incoming canonical URL
  does *not* normalize to a usable value at all, and both `source_tenant_id`/
  `requisition_id_raw` are present. A usable canonical URL's miss is not license to fall
  back to step 3's weaker signal for the same posting — doing so risks a false merge (two
  postings with genuinely different canonical URLs, sharing only a tenant/requisition
  value) that is more damaging than the duplicate-`Job` outcome it would prevent. The
  reverse ordering (trying step 3 after any step-2 miss, regardless of canonical-URL
  usability) was considered and explicitly declined for this slice; adopting it later
  would be a separate ADR/product decision, not a silent implementation change.
- **Step 4 (company-scoped requisition, fallback-only) is deferred, not implemented.**
  `DiscoveredJob.company` is raw text; no capability in the ingestion pipeline resolves
  raw company text into a `companies.id` today. Step 4's own key,
  `(company_id, requisition_id_raw)`, needs an input this pipeline cannot produce — this
  is a missing *prerequisite*, not merely an unwritten implementation, so it cannot be
  attempted in any form (not even a shadow-detection query) until a dedicated
  company-resolution capability exists. This slice's own residual duplicate-creation risk
  for step-4-only-matchable postings (no tenant at all, but a resolvable company+
  requisition match) is accepted **temporarily**, pending that prerequisite — this slice
  does not complete deterministic identity resolution.
- **Candidate counting is by distinct `job_id`, not by occurrence row.** Multiple existing
  occurrences already correctly attached to the same `Job` (e.g. two prior sources already
  merged) count as one candidate, not multiple — getting this wrong would make an
  already-correctly-merged `Job` spuriously ambiguous on its third and further occurrence.
- **Multiple candidates persist a genuine `ambiguous_match` conflict, never fail the
  whole run (later slice).** The fast `<=2` probe (`_discover_candidates`) still
  triggers ambiguity detection at both the pre-lock and post-lock-recheck sites in
  `_attach_to_candidate`, but the persisted evidence is the complete, deterministically
  sorted, distinct candidate set from an authoritative unbounded requery
  (`_discover_all_candidates`), run under the same tier-specific advisory lock already
  held — never the probe's own truncated result. If that authoritative requery
  disagrees with the probe and resolves to fewer than two candidates, this is treated as
  instability, not ambiguity: `CandidateResolutionUnstableError` is raised and nothing is
  persisted. A genuine, stable ambiguity creates a standalone Job/JobOccurrence —
  exactly as Tier 5's zero-candidate path already does — tagged `UpsertKind.AMBIGUOUS`,
  and `persist_posting` records it as an `identity_conflicts` row
  (`conflict_type='ambiguous_match'`): `existing_value` is the sorted array of every
  candidate Job-ID string; `incoming_value` is a single-element array holding the new
  JobOccurrence's own ID string — the two arrays intentionally hold different entity
  types (Jobs vs. the one new JobOccurrence), not a symmetry bug. No candidate row is
  ever mutated on this path, including at the post-lock site where the first
  candidate's own Job row may already be locked `FOR UPDATE` — that lock is held, but
  neither `_attach_to_candidate` nor its caller writes to it. Counted as `jobs_inserted`
  in `pipeline.py` (a real, standalone Job was created), with the same `had_conflict`
  flag and `ingestion_identity_conflict` log line (IDs only) the `QUARANTINED` outcome
  already used, and an exhaustive, fail-closed dispatch over all five `UpsertKind`
  values (any future unhandled value raises rather than silently miscounting). This
  replaces the earlier `AmbiguousIdentityMatchError` design, which raised uncaught and
  failed the whole ingestion run for any ambiguous posting.
- **Candidate resolution is single-pass and fail-closed, never retried.** After the
  tier-specific advisory lock (a new `canonical_url_advisory_lock_key()`/
  `tenant_requisition_advisory_lock_key()` pair in `natural_key.py`, sharing
  `NaturalKey`'s own encoding scheme under fresh domain tags 4/5 — deliberately not
  reusing any `NaturalKeyDomain` tag, including `TENANT`'s own tag 1, since a posting's
  `source_job_id` and `requisition_id_raw` can coincidentally share a value), a candidate
  Job is locked `FOR UPDATE` and the same candidate query is re-run once under that lock.
  If the candidate disappeared (deleted concurrently) or the recheck resolves to a
  different single Job or more than one Job, `persist_posting` fails closed with
  `CandidateResolutionUnstableError`/`AmbiguousIdentityMatchError` rather than retrying —
  retrying while holding a lock on a stale candidate risks accumulating locks in
  inconsistent order across concurrent transactions, a deadlock surface strictly worse
  than one safe failure. Lock order is always parent (`Job`) before child
  (`JobOccurrence`), compatible with `jobs` -> `job_occurrences` `ON DELETE CASCADE`. This
  parent-before-child order is now global, not Tier-2/3-specific: Tier 1's own found
  branch (below) discovers its existing occurrence unlocked, locks the parent `Job`
  first, then re-locks and revalidates the occurrence — an initial implementation locked
  the occurrence (child) first and the parent second, which was itself a latent
  opposite-order deadlock surface against any future writer that deletes a `Job`; see the
  correctness-gap note below.
- **Writer discipline this guarantee depends on**: every current ingestion write path
  treats `job_occurrences`/`jobs` identity evidence as immutable once written — nothing
  deletes a `Job`/`JobOccurrence` row or updates its identity columns in place. Any future
  supported path that deletes or changes that evidence (an administrative Job-merge/
  delete feature, for example) must acquire the corresponding signal's advisory lock and
  this same parent-before-child lock order, so a delete- or change-in-flight is either
  fully visible or fully blocked to this code, never half-visible. Out-of-band manual SQL
  remains outside this guarantee, matching this codebase's posture elsewhere.
- **A new `UpsertKind.ATTACHED` outcome counts as `jobs_updated`, never `jobs_inserted`**,
  at both `collection_runs` and `collection_run_provider_attempts` levels — no new `Job`
  was created; the existing `Job`'s own `last_seen_at` is what advanced, matching a plain
  update far more than an insertion.
- **A pre-existing correctness gap, only reachable once a `Job` can have multiple
  occurrences under different natural keys (which this slice is the first to make
  possible), was fixed as part of this slice**: Tier 1's own found-branch parent-`Job`
  fetch changed from a plain `session.get()` to `SELECT ... FOR UPDATE`, since two
  concurrent updates to the same `Job.last_seen_at` from different natural-key branches
  (Tier 1 re-observing one occurrence, Tier 2/3 attaching another) could otherwise lose an
  update under READ COMMITTED, moving `last_seen_at` backward.
- **A correction to that fix, made during review**: the fix above was initially applied
  by locking the occurrence (child) first via its own discovery query, then the parent
  `Job` second — the opposite of the parent-before-child order this same document
  requires of Tier 2/3 and of any future Job-deletion writer. That opposite order was
  itself a latent deadlock surface: a future delete path locks the parent first, then
  cascades to lock children, so Tier 1 holding the child while waiting on the parent could
  deadlock against it holding the parent while waiting on the child. The found branch now
  discovers the existing occurrence unlocked, locks the parent `Job` first, then re-locks
  and revalidates the occurrence by re-running the identical discovery query — if either
  row is gone, or the occurrence no longer belongs to the just-locked parent,
  `upsert_job_occurrence` fails closed with `CandidateResolutionUnstableError` rather than
  a bare assertion. A real two-transaction PostgreSQL test
  (`test_tier1_reobservation_vs_parent_deletion_uses_real_transactions_no_deadlock`)
  proves both outcomes: no deadlock, and correct fail-closed behavior when the parent is
  deleted mid-resolution.
- **A further correction, made during a second review pass**: the unlocked discovery step
  above was itself initially implemented by loading the full `JobOccurrence` ORM entity —
  which seeds the session's identity map keyed by that row's primary key. SQLAlchemy does
  not refresh an already-loaded instance's attributes from a later `SELECT` matching the
  same primary key within the same session/transaction unless explicitly told to, so the
  later `FOR UPDATE` query could have returned that same cached instance with its `job_id`
  still reading the value from *before* a concurrent reassociation, letting the intended
  revalidation check pass against a parent that was no longer this occurrence's actual
  parent. The initial probe now selects only bare `id`/`job_id` scalar columns
  (`_existing_occurrence_identity_query`), never the ORM entity, so it never touches the
  identity map — the later `FOR UPDATE` load of the full entity is always that row's
  *first* load into the session, guaranteed fresh from the database. A real
  two-transaction PostgreSQL test
  (`test_tier1_reassociation_between_probe_and_lock_is_detected_not_stale`) reassigns the
  occurrence's `job_id` to a second Job between the scalar probe and the parent lock,
  proving `CandidateResolutionUnstableError` is still raised and neither Job's
  observational state advances. This is defense-in-depth: no current writer reassigns
  `job_id` at all; only a documented advisory/row-lock-compliant future writer would.

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

## Addendum (2026-08-30): the Greenhouse live-ingestion proof's identity labels

The Greenhouse live-to-disposable-database ingestion proof
(`backend/scripts/live_proof_greenhouse_ingestion.py`) is a diagnostic script that
fetches one real posting directly over HTTP — it does not invoke the `ats-scrapers`
dependency at all — yet it deliberately labels every row it produces
`provider="ats_scrapers"`, `source="greenhouse"`, the same pair the (still purely
diagnostic, non-shipped) Greenhouse canary already used. This is a narrow, explicit
extension of this ADR's identity model, not a silent inheritance:

- `provider`/`source` are this project's internal categorization labels for the
  natural-key/identity domain (see `app/db/models/raw_job_ingestions.py`'s own
  docstring), not a literal attribution of which Python dependency performed a fetch.
  This ADR's own natural-key design exists specifically to make *the same real-world
  posting* collide onto the same `(provider, source, tenant, job_id)` tuple regardless
  of which code path observed it — a real `AtsScrapersProvider`-based Greenhouse
  adapter, built later, must resolve to the same `Job`/`JobOccurrence` this diagnostic
  script creates for a genuinely re-observed posting, not a duplicate one requiring a
  future backfill migration to unify two label spaces.
- **This does not authorize a production direct-HTTP Greenhouse adapter**, and it does
  not redefine `provider="ats_scrapers"` to mean "any direct HTTP call to an ATS this
  project happens to make." It authorizes exactly one diagnostic script's identity
  labels, for the reason stated above. A future production adapter that fetches
  Greenhouse directly (bypassing `ats-scrapers`) as a deliberate, permanent design —
  rather than a one-off diagnostic proof — would need its own explicit identity-label
  decision, made the same way this one was: stated, reasoned, and recorded here, not
  inferred from this diagnostic script's precedent alone.
