# 0007 — Identity conflict quarantine workflow

## Status
Accepted.

## Context
[ADR 0004](0004-scoped-deterministic-identity.md) originally said that when deterministic
identity resolution hit a conflict — either Tier 1's natural-key match disagreeing with
other evidence, or a fallback tier matching more than one candidate `Job` — the system
should "create a new `Job` for the incoming occurrence" and flag it via
`duplicate_groups`. A second design review found two problems with this:

1. **It's mechanically infeasible for the Tier 1 case.** A Tier 1 match means a row with
   that exact natural key (`provider`, `source`, `source_tenant_id`, `source_job_id`)
   **already exists** in `job_occurrences` — that's what "matched" means. Inserting a
   *second* row with the same key to represent "the new Job" would violate the very
   unique constraint that makes Tier 1 matching meaningful
   ([ARCHITECTURE.md §8](../ARCHITECTURE.md#8-deterministic-identity-resolution)). There
   is no version of "create a new occurrence" that works here.
2. **It's semantically wrong regardless of feasibility.** `duplicate_groups`
   ([ADR 0002](0002-two-tier-duplicate-detection.md)) exists to hold *probabilistic
   similarity suggestions* — "these two independently-created Jobs are probably the
   same." An identity conflict is the opposite kind of fact: *exact*-match evidence that
   disagrees with itself. Storing both under one `reason` enum conflates "we're not sure"
   with "we're sure something's wrong but don't know how to fix it," which would make the
   review UI and any future tooling built against `duplicate_groups` harder to reason
   about, not easier.

## Decision

### Two conflict kinds, only one of which is actually a Tier-1 problem
- **`evidence_mismatch`** — Tier 1 only. The incoming payload's natural key matches an
  *existing* `job_occurrences` row, but its normalized canonical URL conflicts with the
  value already recorded for that occurrence. Since the occurrence already exists, the
  fix is **quarantine, not creation**: leave the disputed field(s) untouched on the
  existing row, still update purely observational fields (`last_seen_at`, `is_active`,
  and the parent `Job.last_seen_at`) since the posting genuinely was observed again, and
  record the disagreement for review. `applicant_count`/`applicant_count_text` are not
  updated by this observational step in Phase 2 — `DiscoveredJob` does not currently
  represent either field, so there is nothing to observe yet; a later source that
  populates them will extend this same observational-update step, not change its shape.
- **`ambiguous_match`** — Tiers 2–4. A matching tier finds **more than one** distinct
  candidate `Job` to attach to. Unlike the Tier 1 case, this *is* a genuinely new
  occurrence (no row shares its natural key yet), so creating a new, standalone `Job` for
  it remains valid and doesn't violate anything — it's simply flagged, rather than
  guessed into one of the ambiguous candidates. This part of Rev 2's original plan was
  fine and is preserved; only the Tier 1 case needed a different mechanism.

### The `identity_conflicts` table
New table (see [DATA_MODEL.md](../DATA_MODEL.md) for full column definitions):
`id`, `existing_job_occurrence_id` (nullable — set for `evidence_mismatch`, `NULL` for
`ambiguous_match`), `incoming_raw_job_ingestion_id`, `conflict_type`
(`evidence_mismatch` / `ambiguous_match`), `existing_value` (jsonb — the disputed field
for `evidence_mismatch`, or a JSON array of candidate `job_id`s for `ambiguous_match`),
`incoming_value` (jsonb, same shape convention), `status` (`open` / `resolved` /
`ignored`), `resolution` (nullable free-form text), `created_at`, `resolved_at`.
No automated merge/resolution action exists — `resolution` is a narrative field a human
fills in, consistent with this project's "never auto-merge" stance applied elsewhere
(`companies.duplicate_of_company_id`, Tier 2's own human-confirmed merge requirement).

Deliberately **not** an extension of `duplicate_groups` — see Context above. Deliberately
**not** keyed by `job_id` alone — `existing_job_occurrence_id` is more precise for
`evidence_mismatch` (the conflict is about one specific occurrence's recorded value, not
the resolved `Job` fields, which may synthesize data from several occurrences).

### `raw_job_ingestions.job_occurrence_id` linking (the explicit semantic choice item 3 asked for)
`job_occurrence_id` is populated in **both** conflict cases, not left `NULL`:
- `evidence_mismatch` → points at the **existing** occurrence (the payload genuinely is
  about that occurrence; we just don't trust one of its field values yet).
- `ambiguous_match` → points at the **new** occurrence the incoming payload produced
  (which was created and is fully queryable; it's the *attachment decision* against the
  ambiguous candidates that's unresolved, not whether a row exists).

It stays `NULL` only for the transient `fetched` state and for `parse_error` — the two
cases where no occurrence exists for the payload to be linked to at all. This makes
`job_occurrence_id`'s meaning uniform: "is there an occurrence this payload is linked
to," independent of whether that link is fully trusted (see
[ADR 0005](0005-raw-ingestion-vs-provider-attempts.md)'s updated nullable-behavior
section).

### `raw_job_ingestions.processing_status` (renamed from `retrieval_status`)
Narrowed to states that can actually apply to a payload that was fetched (see
[ADR 0005](0005-raw-ingestion-vs-provider-attempts.md) for the full before/after): `fetched`,
`parse_error`, `normalized`, `identity_conflict`. The last value is set whenever this
payload's processing produced an `identity_conflicts` row, whether that was an
`evidence_mismatch` or an `ambiguous_match` — both are "this needs human review," which is
the distinction that matters at the payload-status level; the `identity_conflicts.conflict_type`
column is where the finer distinction lives.

### Phase placement
`identity_conflicts` migrates in **Phase 1**, not Phase 6 alongside `duplicate_groups` and
not deferred indefinitely like other not-yet-needed tables
([ADR 0003](0003-minimal-phase1-schema.md)). Reason: Phase 2's fixture-driven ingestion
proof exercises this exact conflict-handling logic as required test cases (an
`evidence_mismatch` fixture and an `ambiguous_match` fixture — see
[ARCHITECTURE.md §11](../ARCHITECTURE.md#11-fixture-driven-end-to-end-ingestion-proof-phase-2-target)),
so the table must already exist when Phase 2 runs. **Phase 2 is the first phase that
writes to it** — Phase 1 only migrates the schema.

## Transaction walkthrough — `evidence_mismatch` (the case that needed redesigning)

1. `ingestion/pipeline.py` receives a `DiscoveredJob` from a provider and writes a
   `RawJobIngestion` row: `processing_status = 'fetched'`, `job_occurrence_id = NULL`.
2. Normalization runs and succeeds (this is not a `parse_error` case).
3. `ingestion/identity.py` computes the natural key
   `(provider, source, source_tenant_id, source_job_id)` and finds an existing
   `job_occurrences` row with that exact key — Tier 1 match.
4. It compares the incoming payload's normalized canonical URL against the existing
   row's `canonical_url_normalized`. They disagree (both non-null, and different).
5. **Within one transaction**, `ingestion/persistence.py`:
   a. Updates the existing `job_occurrences` row's observational fields only —
      `last_seen_at = max(existing, observed_at)` (the caller-supplied, injected business
      timestamp — never a server-side `now()`) and `is_active = true` — and the parent
      `Job`'s own `last_seen_at = max(existing, observed_at)` the same way. **Does not**
      touch `canonical_url`/`canonical_url_normalized` on the occurrence, or any other
      descriptive/source field on either row. `applicant_count`/`applicant_count_text`
      are not updated here in Phase 2: `DiscoveredJob` does not currently carry either
      field, so this step has nothing to observe for them yet.
   b. Inserts an `identity_conflicts` row: `existing_job_occurrence_id` = the existing
      occurrence's id, `incoming_raw_job_ingestion_id` = this raw ingestion's id,
      `conflict_type = 'evidence_mismatch'`, `existing_value = {"canonical_url_normalized":
      "<existing value>"}`, `incoming_value = {"canonical_url_normalized": "<incoming
      value>"}`, `status = 'open'`.
   c. Updates the `RawJobIngestion` row: `processing_status = 'identity_conflict'`,
      `job_occurrence_id` = the existing occurrence's id.
6. The transaction commits. **No second `job_occurrences` row was ever inserted** — the
   natural-key unique index was never at risk of violation, because step 5a only ever
   issues an `UPDATE` against the row Tier 1 already found, never an `INSERT`.
7. Later, a human reviews the open `identity_conflicts` row (out of scope for Phase 1–2:
   no review UI exists yet, but the data is fully queryable), sets `resolution` and
   `status = 'resolved'`/`'ignored'`, and — if warranted — manually updates the
   occurrence's disputed field through the normal application write path. No automated
   resolution exists.

## Phase 2 implementation notes (evidence_mismatch conflict persistence slice)

`ingestion/persistence.py::persist_posting()` implements the transaction walkthrough above
verbatim, with these decisions resolved during implementation:

- **Repeated mismatch**: a natural key already under an open `evidence_mismatch` that is
  observed again with the *same* disputed evidence still produces a **new**
  `identity_conflicts` row per distinct new `RawJobIngestion` — never deduplicated or
  merged with the earlier open conflict. `resolution`/`status` transitions are a human
  review action against each row individually; nothing in this slice auto-closes an older
  conflict just because a newer, structurally identical one exists.
- **Counter bucket**: a quarantined posting increments `jobs_updated` (both
  `collection_runs` and `collection_run_provider_attempts`), not `jobs_inserted` — the
  occurrence's observational state did advance, even though its disputed field did not.
- **Evidence sensitivity**: `existing_value`/`incoming_value` are protected, narrowly-
  scoped evidence — the same sensitivity tier as `raw_job_ingestions.raw_payload` — and are
  never copied into logs, `error_message`, or (in a later API phase) an unauthenticated
  response. The one log line this slice adds (`ingestion_identity_conflict`, `WARNING`)
  carries only the three relevant ids (`raw_ingestion_id`, `identity_conflict_id`,
  `job_occurrence_id`), never either disputed value.
- **`error_message`**: stays `NULL` for a quarantined `RawJobIngestion` row — quarantine is
  not a parse failure, and the disputed evidence itself already lives in
  `identity_conflicts`, not in a free-text message.
- **`created_at`/`updated_at`**: rely on the table's existing `server_default now()`; no
  explicit timestamp is set by application code at conflict-creation time.
- **Raw-ingestion association**: `persist_posting()` never trusts a caller-supplied
  `raw_id`/`natural_key` pair to actually correspond to `job`. Before any mutation, it
  locks the raw row (`SELECT ... FOR UPDATE`) and validates existence,
  `processing_status = 'fetched'`, `job_occurrence_id IS NULL`, provider/source,
  `source_identifier`, `raw_content_hash`, and `fetched_at` — the last two specifically
  because `source_identifier` alone is `NULL` for every URL-fallback-domain posting from a
  given provider/source, not just the correct one, and so cannot alone distinguish an
  unrelated fetched row from the genuine match. It then also re-resolves `job`'s own
  identity (`resolve_identity(job)`) and requires exact equality with the supplied
  `natural_key` — none of the checks against `raw` above ever compare `natural_key` to
  `job` directly, so a forged `natural_key` sharing `provider`/`source`/
  `source_identifier` with a genuinely matching raw/job pair, but disagreeing on
  `source_tenant_id` or the normalized URL (neither of which `RawJobIngestion` itself
  stores), would otherwise pass undetected. This also structurally enforces "one
  conflict per distinct new ingestion": a raw row already turned
  `identity_conflict`/`normalized` fails the `processing_status` check before it could
  ever produce a second conflict row.

## Consequences
- The natural-key unique index is never at risk of violation by conflict handling —
  every write path that could hit a conflict either `UPDATE`s an existing row or
  `INSERT`s a genuinely new one, never both for the same key.
- `duplicate_groups` stays a clean, single-purpose table for Tier 2's fuzzy matching
  (Phase 6) — no mixed-confidence `reason` values.
- `identity_conflicts` existing from Phase 1 means Phase 2's fixture proof can exercise
  the full conflict workflow with zero placeholder/deferred-table workarounds.
- A future review UI (post-MVP) has a single, well-typed table to query for "everything
  that needs a human's attention" from the deterministic identity layer, separate from
  the fuzzy-duplicate review queue.
