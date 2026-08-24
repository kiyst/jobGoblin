# 0003 — Minimal Phase 1 schema

## Status
Accepted.

## Context
§48 of the master spec lists ~18 candidate tables and explicitly says "do not create
unnecessary tables merely because this list exists." Several of the listed tables have
no consumer until a later phase ships: `job_skills` needs the skill taxonomy (Phase 3) to
normalize against; `duplicate_groups` needs the fuzzy-similarity pass (Phase 6);
`contacts`/`contact_sources` need contact intelligence (Phase 13, explicitly deferred);
`notifications` has no described producer anywhere in the spec. Migrating these now would
mean either leaving them empty and unindexed for months, or guessing at a shape that
Phase 3/6/13 design work would likely revise anyway.

## Decision
Phase 1 migrates exactly: `users`, `candidate_profiles`, `candidate_skills`,
`saved_searches`, `saved_search_titles`, `saved_search_locations`, `companies`, `jobs`,
`job_occurrences`, `raw_job_ingestions`, `identity_conflicts`, `collection_runs`,
`user_jobs`, `job_notes`.

**Rev 3 addition — `identity_conflicts`:** this looks like it should follow the same
"defer until something uses it" logic as `duplicate_groups`/`collection_run_provider_attempts`
below, but it's included in Phase 1 instead, for a narrower reason than "the schema is
ready": Phase 2's fixture-driven ingestion proof
([ARCHITECTURE.md §11](../ARCHITECTURE.md#11-fixture-driven-end-to-end-ingestion-proof-phase-2-target))
exercises `ingestion/identity.py`'s conflict handling
([ADR 0007](0007-identity-conflict-quarantine.md)) as one of its required test cases —
that proof needs somewhere to actually write `evidence_mismatch`/`ambiguous_match` rows,
which means the table has to exist by the time Phase 2 runs. Phase 1 is where migrations
happen in this project's phase sequencing, so it lands there — one phase earlier than the
"nothing uses it yet" tables below, but for the same underlying principle (a table is
migrated in the phase immediately before something needs to write to it, not earlier).

Deferred tables are still named and roughly shaped in
[DATA_MODEL.md](../DATA_MODEL.md#later-tables-not-migrated-in-phase-1) so that
foreign-key targets referenced early (e.g. `jobs.duplicate_group_id`) have a stable name
reserved, but the deferred tables themselves aren't created until the phase that
populates them lands.

`candidate_skills` and `saved_search_*` child tables are the one addition beyond a
literal reading of "minimal" — they're included in Phase 1 (not deferred) because
without them, `candidate_profiles.target_role_families`/skills and
`saved_searches` titles/locations would have to live as unstructured array columns that
Phase 3's per-title/per-skill alias resolution would need to split out anyway. Splitting
now costs one extra migration; splitting later costs a backfill migration plus rewriting
whatever code had assumed array columns.

## Consequences
- No empty, purpose-guessed tables sit in the schema for multiple phases.
- Each later phase's migration PR is self-contained: adding `job_skills` in Phase 3 is
  reviewable purely in terms of what Phase 3 needs, not as leftover Phase 1 scaffolding.
- Anything currently referencing a deferred table by name (e.g. `jobs.duplicate_group_id`
  as a nullable FK with no target table yet) must be a nullable column with the
  constraint added when the target table is created, not a hard FK from day one.
