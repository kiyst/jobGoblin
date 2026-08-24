# 0006 — UserJob workflow invariants

## Status
Accepted.

## Context
Rev 1's `user_jobs` table stored `applied` (boolean), `applied_at` (nullable
timestamp), and `status` (a 9-value enum including `archived`, `withdrawn`, `rejected`)
as three independently writable columns with nothing tying them together. Nothing
prevented, for example, `applied = true` while `status = 'interested'`, or `applied_at`
set while `applied = false`, or `status = 'rejected'` with no `applied_at` at all — three
different fields all claiming to represent overlapping facts, able to disagree with each
other by simple omission in application code.

Separately, the single `status` enum conflated who took an action (the spec's requested
distinction: user dismissed without applying vs. employer rejected vs. user withdrew) and
conflated a terminal "archived" state with the substantive workflow state it was archiving
— once a row was archived, whether it had been an active application, a rejection, or
just an unconsidered "interested" entry was lost.

## Decision

**Drop the independent `applied` boolean.** `applied_at` (nullable) is the single source
of truth for "has the user applied" — application code and the UI derive it as
`applied_at IS NOT NULL` rather than trusting a separately-set flag that could drift out
of sync.

**Split `status` values by who acted, and pull "archived" out entirely:**
- `status` enum: `interested`, `not_interested`, `applied`, `recruiter_contacted`,
  `screening`, `interviewing`, `offer`, `rejected_by_employer`, `withdrawn_by_user`.
- `archived` becomes an independent boolean flag (alongside the existing `saved` and
  `hidden` flags), not a status value. A row can be archived regardless of which status
  it was in, without losing that status — an archived "offer" and an archived
  "not_interested" remain distinguishable.

**Enforce status/applied_at consistency with a database `CHECK` constraint:**

```text
CHECK (
  (status IN ('interested', 'not_interested') AND applied_at IS NULL)
  OR
  (status IN ('applied', 'recruiter_contacted', 'screening', 'interviewing',
              'offer', 'rejected_by_employer', 'withdrawn_by_user')
   AND applied_at IS NOT NULL)
)
```

This is a hard invariant enforced by Postgres itself — not something that can be violated
by a future bug in application code, only by a change to the constraint itself.

**Single writer for the pair:** exactly one service function
(`services/user_jobs.py::set_status()`) is permitted to write `status` and `applied_at`
together. It sets `applied_at` the first time a row transitions into a post-application
status (never overwriting it on subsequent post-application transitions, so the original
application date survives e.g. `recruiter_contacted → interviewing → offer`), and clears
it only when a caller explicitly moves status back to `interested`/`not_interested` (a
correction), in the same write. This is enforced by code structure/review (per
[ARCHITECTURE.md §5](../ARCHITECTURE.md#5-dependency-boundaries)), not by a trigger — the
`CHECK` constraint is the actual backstop if this discipline is ever violated.

**Transitions are not hard-blocked.** This is a personal job-search tracker, not a
workflow engine — a user correcting a mis-click (e.g. accidentally marking `interviewing`
when they meant `screening`) is a normal, expected action, including moving "backwards."
The invariant enforced is internal consistency (status and applied_at can't contradict
each other), not a state-machine transition graph. `saved`/`hidden`/`archived` remain
fully independent boolean flags orthogonal to `status`, exactly as before.

## Consequences
- It is no longer possible to persist a `user_jobs` row where the applied flag, the
  applied date, and the workflow status disagree — the database rejects it outright.
- "User dismissed without ever applying," "employer rejected," "user withdrew," and
  "archived" are four independently readable facts, not conflated into one status
  dimension.
- Every existing read/write path that assumed an `applied` boolean column must be
  updated to read `applied_at IS NOT NULL` instead — there is no migration-compatibility
  concern yet since no application code exists (this is a Phase 0/1 design document, not
  a live schema), but this is the shape Phase 1's migration commits directly.
- Phase 1 acceptance criteria ([ARCHITECTURE.md §13](../ARCHITECTURE.md#13-phase-1-acceptance-criteria-strengthened-rev-2))
  require a test proving the database itself rejects an inconsistent `(status,
  applied_at)` combination, not just that application code happens to avoid producing
  one.
