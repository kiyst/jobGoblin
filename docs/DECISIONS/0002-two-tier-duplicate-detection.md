# 0002 — Two-tier duplicate detection

## Status
Accepted, revised (Rev 3): Tier 1's conflict-handling no longer routes through
`duplicate_groups` — see [0007](0007-identity-conflict-quarantine.md).

## Context
The master spec describes duplicate handling in two places that read as one feature but
aren't: `JobOccurrence` attachment (multiple sources feeding one `Job`) and
`duplicate_candidate`/`duplicate_group_id` fields for probable duplicates. Without
separating these, it's ambiguous whether "dedup" means merging occurrences into a job or
flagging separate jobs as maybe-the-same — and code implementing both under one concept
would likely end up silently merging things that shouldn't be merged, which the spec
explicitly forbids (§19: "Do NOT automatically delete based solely on fuzzy similarity").

## Decision
Two tiers, different confidence, different behavior:

**Tier 1 — deterministic identity resolution** (`ingestion/identity.py` — moved out of
`dedupe/` in Rev 2 since it runs during ingestion, before a `Job` even exists, not as a
post-persistence pass; see [ARCHITECTURE.md §4](../ARCHITECTURE.md#4-repository-structure)).
Signals: normalized canonical URL match, or a **scoped** requisition/tenant match — never
a bare requisition ID (a requisition ID is only unique within one ATS tenant or company;
full precedence order and collision handling in
[0004-scoped-deterministic-identity.md](0004-scoped-deterministic-identity.md)). A match
here means the incoming `DiscoveredJob` is the *same appearance* being re-observed, or a
*new occurrence* of an already-known job — it attaches to the existing `Job`
automatically. No user-visible "duplicate" is ever created at this tier; it's invisible
plumbing. When Tier 1's own signals are ambiguous or conflict with each other, that
**does** surface as a reviewable case — but **not** through `duplicate_groups` below.
**Rev 3 correction:** a second design review found the original plan to route Tier 1
conflicts through `duplicate_groups` was both semantically wrong (conflating an exact-match
conflict with a probabilistic similarity suggestion) and, for one specific case,
mechanically infeasible (see [0004](0004-scoped-deterministic-identity.md)'s "Collision
and ambiguity handling"). Tier 1 conflicts now route to a dedicated
`identity_conflicts` table instead — full design in
[0007-identity-conflict-quarantine.md](0007-identity-conflict-quarantine.md).

**Tier 2 — probabilistic duplicate candidates** (`dedupe/similarity.py` +
`grouping.py`, runs as a separate pass over existing `Job` rows, Phase 6). Signals:
normalized company + normalized title + location + posting date proximity + description
similarity. A match here means two *independently created* `Job` rows are suspected of
describing the same real-world opening (e.g. discovered via two aggregators with no
shared canonical link). These get a shared `duplicate_group_id` and surface in the UI
for the user to inspect. **The system never merges `Job` rows based on Tier 2 signals
alone** — that remains a human-confirmed action, not implemented in the MVP.

## Consequences
- "Same job, multiple sources" (the common case, when a canonical link exists) never
  shows as a duplicate to the user — it's just one `Job` with multiple occurrence badges.
- "Probably the same job, but we can't prove it" is visible and inspectable, never
  silently dropped or silently merged.
- `ingestion/identity.py` has zero false-positive tolerance (its signals are exact-match,
  scoped per [0004](0004-scoped-deterministic-identity.md)); `dedupe/similarity.py` is
  allowed to be wrong sometimes because its output is a suggestion, not a mutation.
- A future "confirm merge" user action can consume `duplicate_groups` without changing
  how Tier 1 works.
- `duplicate_groups`' `reason` enum is now purely fuzzy/manual values
  (`fuzzy_title_company_location` / `description_similarity` / `manual`) — a Rev 2
  addition, `identity_conflict`, was removed once it became clear that value belonged to
  a mechanically different table with different feasibility constraints, not this one
  (see [0007](0007-identity-conflict-quarantine.md)).
