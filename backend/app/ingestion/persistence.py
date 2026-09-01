import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy import ColumnElement, Select, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.identity_conflict import IdentityConflict
from app.db.models.job import Job
from app.db.models.job_occurrence import JobOccurrence
from app.db.models.raw_job_ingestion import RawJobIngestion
from app.ingestion.hashing import canonical_json_hash
from app.ingestion.identity import UnresolvableIdentityError, resolve_identity
from app.ingestion.natural_key import (
    NaturalKey,
    NaturalKeyDomain,
    canonical_url_advisory_lock_key,
    canonicalize_nullable_text,
    tenant_requisition_advisory_lock_key,
)
from app.normalization.url import normalize_url
from app.schemas.discovered_job import DiscoveredJob


class UpsertKind(Enum):
    """The five outcomes `persist_posting`/`upsert_job_occurrence` can
    reach for one posting. `QUARANTINED` replaces the earlier
    `DeferredIdentityConflictError` design: a canonical-URL evidence
    mismatch is now a real ADR-0007 quarantine transition, not a failure
    that aborts the enclosing run. `ATTACHED` is a new `JobOccurrence`
    created under an *existing* Job found via Tier 2/3 cross-occurrence
    matching — distinct from `INSERTED` (a brand-new Job) because no new
    Job was created here; see `pipeline.py`'s counter bucketing.
    `AMBIGUOUS` replaces the earlier `AmbiguousIdentityMatchError`
    whole-run-failure design: Tier 2/3 finding more than one distinct
    candidate Job now creates a standalone Job/JobOccurrence (like
    `INSERTED`, and counted the same way) rather than aborting the run,
    and records the complete candidate set as an ADR-0007 `ambiguous_match`
    `identity_conflicts` row — see `UpsertOutcome.
    ambiguous_candidate_job_ids`."""

    INSERTED = "inserted"
    UPDATED = "updated"
    QUARANTINED = "quarantined"
    ATTACHED = "attached"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class UpsertOutcome:
    """`ambiguous_candidate_job_ids` is populated if and only if
    `kind is UpsertKind.AMBIGUOUS` — enforced by `__post_init__` below,
    not merely by convention, since an outcome that disagreed with its own
    `kind` here would silently corrupt whichever caller trusts `kind` alone
    (`pipeline.py`'s counter dispatch, `persist_posting`'s conflict-row
    construction). When present, it is the complete, deterministically
    sorted, distinct tuple of every candidate Job matched — never the
    `<=2` fast ambiguity probe's own truncated result."""

    job_id: uuid.UUID
    occurrence_id: uuid.UUID
    kind: UpsertKind
    conflict_id: uuid.UUID | None = None
    ambiguous_candidate_job_ids: tuple[uuid.UUID, ...] | None = None

    def __post_init__(self) -> None:
        if self.kind is UpsertKind.AMBIGUOUS:
            ids = self.ambiguous_candidate_job_ids
            if ids is None or len(ids) < 2:
                raise ValueError("an AMBIGUOUS outcome must carry at least two candidate Job IDs")
            if len(set(ids)) != len(ids):
                raise ValueError("an AMBIGUOUS outcome's candidate Job IDs must be distinct")
            if tuple(sorted(ids)) != ids:
                raise ValueError("an AMBIGUOUS outcome's candidate Job IDs must be sorted")
        elif self.ambiguous_candidate_job_ids is not None:
            raise ValueError("only an AMBIGUOUS outcome may carry ambiguous_candidate_job_ids")


class InvalidRawIngestionAssociationError(RuntimeError):
    """`raw_id`/`natural_key` do not genuinely correspond to the `job`
    being persisted. Raised by `persist_posting` before any mutation —
    existence, `processing_status`, linkage, provider/source,
    `source_identifier`, `raw_content_hash`, `fetched_at`, and (finally)
    exact agreement between `natural_key` and `job`'s own re-resolved
    identity are all checked under a `SELECT ... FOR UPDATE` lock first.

    The `raw_content_hash`/`fetched_at` checks exist because
    `source_identifier` alone is ambiguous in the URL-fallback domain: a
    posting with no `source_job_id` has `source_identifier IS NULL` on
    *every* such row from the same provider/source, not just the correct
    one, since `NULL == NULL` cannot distinguish them. `raw_content_hash`
    ties the raw row to *this exact posting's content*; `fetched_at`
    (written from `job.discovered_at` by Transaction A_i) is a second,
    independent corroborating signal.

    The final `natural_key`-vs-`job` check exists because none of the
    checks above ever compares `natural_key` to `job` directly — only to
    `raw`. A caller-supplied `natural_key` that happens to share
    `provider`/`source`/`source_identifier` with a genuinely matching
    raw/job pair, but disagrees on `source_tenant_id` or the normalized
    URL (neither of which `RawJobIngestion` itself stores), would
    otherwise pass every check above while still describing a *different*
    posting than `job` actually is — letting the found branch
    mutate/quarantine the wrong occurrence, or the insert branch acquire
    an advisory lock for one key while inserting an occurrence whose
    provider/source-derived fields describe another. Re-resolving
    `job`'s own identity via `resolve_identity(job)` and requiring exact
    equality with the supplied `natural_key` closes this gap.

    A caller that always derives `natural_key` from `job` itself via
    `resolve_identity()` and always pairs `job`/`raw_id` correctly (as
    `ingestion/pipeline.py`'s own
    `zip(result.jobs, raw_ingestion_ids, strict=True)` does) never hits
    this — it exists as defense-in-depth against a hypothetical future
    caller bug, not evidence of a known one.
    """


class CandidateResolutionUnstableError(RuntimeError):
    """A single existing/candidate row found by an unlocked discovery query
    could not be stably confirmed after acquiring its row lock(s) — either
    a row was deleted between discovery and lock acquisition, or the same
    discovery query no longer resolves to that same single row once re-run
    under the lock. Raised by both Tier 1's own found-branch revalidation
    (`upsert_job_occurrence`) and Tier 2/3's `_attach_to_candidate`.

    Also raised by `_attach_to_candidate` when its fast `<=2` ambiguity
    probe (`_discover_candidates`) disagrees with the authoritative,
    unbounded candidate requery (`_discover_all_candidates`) run once the
    probe reports more than one candidate: if that authoritative requery
    resolves to fewer than two candidates, this is instability between two
    queries, not a genuine, stable ambiguity, and nothing is persisted.

    Distinct from a genuine, stable `UpsertKind.AMBIGUOUS` outcome: that
    means the authoritative requery confirmed two or more real, currently
    existing candidates; this exception means the candidate set could not
    be stably confirmed at all — under concurrent modification, or via a
    disagreement between the fast probe and the authoritative requery.
    Should be unreachable given correct locking discipline by every writer
    that touches `job_occurrences`/`jobs` identity evidence — exists as a
    defensive bound, never as an expected code path in normal operation.

    Never retried within the same transaction. Both call sites fail closed
    on the first sign of instability rather than looping: retrying while
    still holding a lock on a stale row would risk accumulating locks in
    inconsistent orders across concurrent transactions — a deadlock
    surface strictly worse than failing this one transaction closed and
    letting the caller (ultimately a fresh `pipeline.run()` invocation)
    resolve it fresh.
    """


def _normalize_canonical_url(job: DiscoveredJob) -> str | None:
    if job.canonical_url is None:
        return None
    return normalize_url(job.canonical_url, provider=job.provider, source=job.source)


def _existing_occurrence_conditions(natural_key: NaturalKey) -> list[ColumnElement[bool]]:
    """Tier 1's own domain-scoped lookup conditions (ADR 0004's three
    natural-key forms) — shared by both query shapes below, so the scalar
    identity probe and the full-entity query can never drift apart and
    match different rows."""
    conditions: list[ColumnElement[bool]] = [
        JobOccurrence.provider == natural_key.provider,
        JobOccurrence.source == natural_key.source,
    ]
    if natural_key.domain is NaturalKeyDomain.TENANT:
        conditions += [
            JobOccurrence.source_tenant_id == natural_key.tenant_id,
            JobOccurrence.source_job_id == natural_key.job_id,
        ]
    elif natural_key.domain is NaturalKeyDomain.NO_TENANT:
        conditions += [
            JobOccurrence.source_tenant_id.is_(None),
            JobOccurrence.source_job_id == natural_key.job_id,
        ]
    else:
        conditions += [
            JobOccurrence.source_job_id.is_(None),
            JobOccurrence.source_url_normalized == natural_key.url_normalized,
        ]
    return conditions


def _existing_occurrence_query(natural_key: NaturalKey) -> Select[tuple[JobOccurrence]]:
    """Selects the full ORM entity (not bare columns) so the "found" branch
    below can update it by plain attribute assignment — which runs through
    `JobOccurrence`'s own `@validates` normalization — rather than a
    Core-style `update()` statement, which does not.

    Deliberately returns an *unlocked* query shape — never `.with_for_update()`
    itself. `upsert_job_occurrence`'s found branch chains `.with_for_update()`
    onto this query itself only to load the entity *fresh*, for the first
    time, after the parent `Job`'s own row lock is already held — never for
    the initial, unlocked discovery probe. See `_existing_occurrence_identity_query`
    and that function's own docstring for why."""
    return select(JobOccurrence).where(*_existing_occurrence_conditions(natural_key))


def _existing_occurrence_identity_query(
    natural_key: NaturalKey,
) -> Select[tuple[uuid.UUID, uuid.UUID]]:
    """The initial, unlocked Tier-1 discovery probe — selects only the bare
    `id`/`job_id` scalar columns, never the `JobOccurrence` ORM entity.

    This is deliberate, not an optimization: loading the full entity here
    would seed the session's identity map with a `JobOccurrence` instance
    keyed by its primary key. SQLAlchemy does not refresh an already-loaded
    instance's attributes from a later `SELECT` matching the same primary
    key inside the same session/transaction unless explicitly told to — so
    if `upsert_job_occurrence`'s later `FOR UPDATE` query happened to return
    that same cached instance, its `job_id` could still read the *stale*
    value from this probe even though the database row had since been
    reassociated to a different `Job`, defeating the revalidation check
    below. Selecting bare columns here never touches the identity map, so
    the later `FOR UPDATE` load of `_existing_occurrence_query` is always
    that entity's *first* load into this session — guaranteed fresh from
    the database, not a cached instance."""
    return select(JobOccurrence.id, JobOccurrence.job_id).where(
        *_existing_occurrence_conditions(natural_key)
    )


async def _discover_candidates(
    session: AsyncSession, filter_clause: ColumnElement[bool]
) -> list[uuid.UUID]:
    """At most two distinct `job_id` values matching `filter_clause` —
    enough to distinguish zero/one/more-than-one without counting the full
    candidate set. Safely re-callable: used for both initial discovery and
    the single post-lock revalidation pass in `_attach_to_candidate`."""
    return list(
        (
            await session.execute(
                select(JobOccurrence.job_id).where(filter_clause).distinct().limit(2)
            )
        )
        .scalars()
        .all()
    )


async def _discover_all_candidates(
    session: AsyncSession, filter_clause: ColumnElement[bool]
) -> tuple[uuid.UUID, ...]:
    """The complete, deterministically sorted, distinct `job_id` set
    matching `filter_clause` — unlike `_discover_candidates`'s `LIMIT 2`
    fast ambiguity probe, this performs no `LIMIT` and is only ever called
    once that probe (at either the pre-lock or post-lock recheck site in
    `_attach_to_candidate`) has already reported more than one candidate.

    Deliberately a plain, unlocked scalar query, never `.with_for_update()`
    on any candidate: the tier-specific advisory lock the caller already
    holds by the time either call site can reach this already serializes
    every other writer for this signal, so no per-candidate row lock is
    needed to make this result stable, and this function never mutates
    anything. Sorted using `uuid.UUID`'s own total ordering (by integer
    value) for a deterministic, reproducible persisted evidence array —
    never the order PostgreSQL happens to return rows in."""
    candidates = (
        (await session.execute(select(JobOccurrence.job_id).where(filter_clause).distinct()))
        .scalars()
        .all()
    )
    return tuple(sorted(candidates))


async def _before_candidate_lock() -> None:
    """Test seam only — a no-op in production. Tests monkeypatch this to
    pause execution (e.g. awaiting an `asyncio.Event`) between initial
    candidate discovery and the Job row-lock attempt below, to
    deterministically exercise "candidate deleted concurrently" using two
    real, separately-committed PostgreSQL transactions rather than
    relying on real-world timing or mocking the query itself."""
    return None


async def _before_tier1_parent_lock() -> None:
    """Test seam only — a no-op in production. Tests monkeypatch this to
    pause execution between Tier 1's initial unlocked existing-occurrence
    discovery and the parent `Job` row-lock attempt below, to
    deterministically exercise "parent Job deleted concurrently" using two
    real, separately-committed PostgreSQL transactions — the Tier-1
    analogue of `_before_candidate_lock` above, kept as a separate seam
    since the two pause points guard unrelated code paths."""
    return None


async def _attach_to_candidate(
    session: AsyncSession,
    filter_clause: ColumnElement[bool],
    natural_key: NaturalKey,
    job: DiscoveredJob,
    observed_at: datetime,
) -> UpsertOutcome | tuple[uuid.UUID, ...] | None:
    """Single-pass, fail-closed candidate resolution under the caller's
    already-held tier-specific advisory lock (Tier 2's canonical-URL lock,
    or Tier 3's tenant-requisition lock — never both for the same posting,
    since Tiers 2/3 are mutually exclusive per `upsert_job_occurrence`).

    Three possible return shapes:
    - `None` — no candidate exists at all; the caller falls through to
      Tier 5 (create a standalone Job/JobOccurrence, `UpsertKind.INSERTED`).
    - `UpsertOutcome` (`kind=UpsertKind.ATTACHED`) — exactly one stable
      candidate was found, locked, and attached to.
    - `tuple[uuid.UUID, ...]` (length >= 2) — a genuine, stable ambiguity:
      the authoritative, unbounded requery (`_discover_all_candidates`)
      confirms more than one distinct candidate Job. Touches no candidate
      row. The caller (`upsert_job_occurrence`) falls through to the same
      Tier 5 creation code used for `None`, but tags the result
      `UpsertKind.AMBIGUOUS` with this tuple attached; `persist_posting`
      then records it as an ADR-0007 `ambiguous_match` `identity_conflicts`
      row.

    Never retries while holding a lock on a stale candidate: any
    instability discovered after the parent Job's row lock is acquired —
    including the fast `<=2` probe disagreeing with the authoritative,
    unbounded requery once it is run — fails this transaction closed via
    `CandidateResolutionUnstableError` rather than looping (see that
    exception's own docstring for why).

    Candidate-locking state at the two points ambiguity can be detected is
    never uniform, and is documented precisely here rather than implied:
    the **pre-lock** site (before `_before_candidate_lock()`/any
    `FOR UPDATE`) touches no candidate row at all. The **post-lock
    recheck** site runs after the first candidate's own Job row is already
    locked `FOR UPDATE` — that lock is held, but neither this function nor
    its caller ever mutates that row or any other candidate's row on this
    path; only a new, standalone Job/JobOccurrence is created, exactly as
    the `None` (zero-candidate) case already does.

    Lock order: the tier-specific advisory lock (held by the caller before
    this function runs) is acquired before this function's own Job
    `FOR UPDATE` (parent) lock, which is in turn acquired before the new
    `JobOccurrence` (child) is inserted — parent before child, compatible
    with `jobs` -> `job_occurrences` `ON DELETE CASCADE`. Once the Job's
    row lock is held, no concurrent `DELETE FROM jobs WHERE id = ...` can
    proceed on that row until this transaction ends, so the child insert
    that follows is race-free by construction. `_discover_all_candidates`
    is a plain, unlocked scalar query — it never acquires a `FOR UPDATE`
    lock on any candidate; the advisory lock already held for this signal
    is what makes its result stable, not a row lock.

    Writer-discipline this guarantee depends on: every current ingestion
    write path treats `job_occurrences`/`jobs` identity evidence
    (`canonical_url_normalized`, `provider`/`source`/`source_tenant_id`/
    `requisition_id_raw`) as immutable once written — nothing here or
    elsewhere in this codebase updates those columns in place, or deletes
    a `Job`/`JobOccurrence` row at all. Any future supported path that
    deletes or changes that evidence (an administrative Job-merge/delete
    feature, for example) must acquire the corresponding signal's advisory
    lock and this same parent-before-child lock order, so a delete- or
    change-in-flight is either fully visible (the row is already gone or
    already changed, detected by the checks below) or fully blocked (lock
    contention) to this code — never half-visible. Out-of-band manual SQL
    remains outside this guarantee, matching this codebase's existing
    posture elsewhere (e.g. no defense against a manual `UPDATE` of
    `raw_content_hash` via `psql`).
    """
    candidates = await _discover_candidates(session, filter_clause)
    if not candidates:
        return None
    if len(candidates) > 1:
        all_candidates = await _discover_all_candidates(session, filter_clause)
        if len(all_candidates) < 2:
            raise CandidateResolutionUnstableError(
                "ambiguity probe reported multiple candidates but the authoritative "
                "unbounded requery resolved to fewer than two"
            )
        return all_candidates
    candidate_job_id = candidates[0]

    await _before_candidate_lock()

    job_row = (
        await session.execute(select(Job).where(Job.id == candidate_job_id).with_for_update())
    ).scalar_one_or_none()
    if job_row is None:
        raise CandidateResolutionUnstableError(
            "candidate job was deleted before its lock could be acquired"
        )

    # The lock proves the Job row itself survived; it does not prove the
    # candidate query still resolves to it exclusively. Re-run it once,
    # now under the Job's own row lock in addition to the tier lock,
    # before mutating anything.
    recheck = await _discover_candidates(session, filter_clause)
    if len(recheck) > 1:
        all_candidates = await _discover_all_candidates(session, filter_clause)
        if len(all_candidates) < 2:
            raise CandidateResolutionUnstableError(
                "ambiguity probe reported multiple candidates after acquiring the "
                "candidate's row lock but the authoritative unbounded requery "
                "resolved to fewer than two"
            )
        return all_candidates
    if recheck != [candidate_job_id]:
        raise CandidateResolutionUnstableError(
            "candidate job identity changed after its lock was acquired"
        )

    job_row.last_seen_at = max(job_row.last_seen_at, observed_at)
    new_occurrence = JobOccurrence(
        job_id=candidate_job_id,
        provider=job.provider,
        source=job.source,
        source_tenant_id=job.source_tenant_id,
        source_job_id=job.source_job_id,
        requisition_id_raw=job.requisition_id_raw,
        source_url=job.source_url,
        source_url_normalized=natural_key.url_normalized,
        apply_url=job.apply_url,
        canonical_url=job.canonical_url,
        canonical_url_normalized=_normalize_canonical_url(job),
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        posted_at=job.posted_at,
    )
    session.add(new_occurrence)
    await session.flush()
    return UpsertOutcome(
        job_id=candidate_job_id, occurrence_id=new_occurrence.id, kind=UpsertKind.ATTACHED
    )


async def upsert_job_occurrence(
    session: AsyncSession,
    natural_key: NaturalKey,
    job: DiscoveredJob,
    observed_at: datetime,
) -> UpsertOutcome:
    """Resolves `job`'s natural key against Tier 1 (exact natural-key
    match); on a miss, Tier 2 (normalized canonical URL) or Tier 3
    (tenant-scoped requisition) — mutually exclusive, see below; on a miss
    there too, Tier 5 (create a new Job). Never touches `RawJobIngestion`
    or `IdentityConflict` — that is `persist_posting`'s responsibility,
    since only it holds the validated `raw_id` an `IdentityConflict` row
    must reference.

    Holds a PostgreSQL advisory transaction lock keyed by `natural_key`
    (`NaturalKey.advisory_lock_key()`) for the remainder of the caller's
    transaction, acquired *before* the Tier-1 existence check. This is
    what makes the following check-then-act sequence safe without a
    speculative/orphan `Job` row and without an `ON CONFLICT` clause:
    every other transaction attempting to resolve the *same* natural key
    blocks on the lock until this one commits or rolls back. The "found"
    branch never assigns `job_id` — it only ever mutates observational
    columns on the already-resolved, already-loaded ORM instance — so an
    existing occurrence is never reassigned to a different `Job`, and its
    association is never lost.

    The found branch **always** advances observational state
    (`last_seen_at`/`is_active` on the occurrence, `last_seen_at` on the
    parent `Job`) — whether or not the incoming payload's normalized
    canonical URL agrees with the one already recorded. Descriptive,
    canonical, and source-provided fields remain frozen either way. When
    both stored and incoming normalized canonical URLs exist and disagree,
    the returned outcome's `kind` is `QUARANTINED` rather than `UPDATED` —
    `persist_posting` uses that signal to record the `IdentityConflict`
    row ADR 0007 requires; this function itself never mutates the
    disputed field and never creates that row.

    The found branch discovers the existing occurrence via an *unlocked*
    scalar-only probe first (`_existing_occurrence_identity_query` — bare
    `id`/`job_id` columns, deliberately never the ORM entity; see that
    function's own docstring for why loading the entity here would risk
    revalidating against a stale, session-cached value instead of the
    database's current one), then acquires the parent `Job`'s row lock via
    `SELECT ... FOR UPDATE` *before* loading the occurrence entity itself —
    parent-before-child, the same order Tier 2/3's `_attach_to_candidate`
    uses below, and the order compatible with `jobs` -> `job_occurrences`
    `ON DELETE CASCADE`. An earlier version of this function locked the
    occurrence (child) first and the parent `Job` second; that was itself a
    latent opposite-order deadlock surface against any future writer that
    deletes a `Job` (which locks the parent first, then cascades to lock
    its children): this function would hold the child lock while wanting
    the parent, while such a writer would hold the parent while wanting the
    child. Discovering unlocked and re-locking parent-then-child removes
    that surface entirely — both this function and any lock-order-compliant
    future writer always contend for the parent first, so one simply waits
    for the other rather than deadlocking.

    Once the parent lock is held, the occurrence entity is loaded — for the
    first time in this session — via the same domain query, now
    `FOR UPDATE` (`_existing_occurrence_query`); if it no longer exists, or
    its `id`/`job_id` disagree with the earlier scalar probe, this fails
    closed with `CandidateResolutionUnstableError` — never a bare assertion.
    Because this `FOR UPDATE` load is always that row's *first* load into
    the session (the probe above never touched the ORM identity map), its
    `job_id` is guaranteed fresh from the database — not a cached value
    left over from before a concurrent reassociation. The parent lock
    itself is also required *because* Tier 2/3 below can give one Job more
    than one occurrence under different natural keys (reachable via
    different advisory locks that do not serialize against each other);
    without it, two concurrent updates to the same Job's `last_seen_at`
    from different natural-key branches could lose an update, moving it
    backward.

    Tier 2 and Tier 3 are **mutually exclusive per posting**, matching
    ADR 0004's own conservative precedence: Tier 2 is attempted only when
    the incoming canonical URL normalizes to a usable value; if it does,
    and Tier 2 finds zero candidates, resolution proceeds directly to
    Tier 5 — Tier 3 is never attempted for that posting. Tier 3 is
    attempted only when the incoming canonical URL does *not* normalize to
    a usable value at all, and both `source_tenant_id`/`requisition_id_raw`
    are present. A usable canonical URL's miss at Tier 2 is not license to
    fall back to Tier 3's weaker signal for the same posting — doing so
    would risk a false merge (two postings with genuinely different
    canonical URLs, sharing only a tenant/requisition value) being treated
    as more damaging than the duplicate-Job outcome it would prevent.
    When `_attach_to_candidate` reports a genuine, stable ambiguity (more
    than one distinct candidate Job) rather than `None` or a single
    `ATTACHED` outcome, this function falls through to the same Tier 5
    creation code used for the zero-candidate case — a standalone
    Job/JobOccurrence is created exactly as `INSERTED` would create one —
    but tags the resulting outcome `UpsertKind.AMBIGUOUS` and attaches the
    complete candidate tuple, so `persist_posting` can record it as an
    ADR-0007 `ambiguous_match` `identity_conflicts` row instead of
    guessing which candidate the posting actually belongs to.

    Tier 4 (company-scoped requisition, fallback-only) remains deferred:
    `DiscoveredJob.company` is raw text, and no company-resolution
    capability (raw text -> `companies.id`) exists in the ingestion
    pipeline yet — Tier 4 needs an input this pipeline cannot produce
    today, not merely an unwritten implementation. This slice does not
    complete deterministic identity resolution; Tier 4's own residual
    duplicate-creation risk is accepted temporarily, pending that
    prerequisite.

    `observed_at` — the caller-supplied business timestamp, never a
    server-side `now()` — only ever moves `last_seen_at` (on both the
    occurrence and its parent `Job`) forward: `max(existing, incoming)`,
    never a blind overwrite — so an out-of-order replay can never move it
    backward, including when it lands on the quarantine or attach branch.
    """
    lock_key = natural_key.advisory_lock_key()
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=lock_key))

    incoming_canonical_url = _normalize_canonical_url(job)
    existing_probe = (
        await session.execute(_existing_occurrence_identity_query(natural_key))
    ).one_or_none()

    if existing_probe is not None:
        probed_occurrence_id, probed_job_id = existing_probe

        await _before_tier1_parent_lock()

        job_row = (
            await session.execute(select(Job).where(Job.id == probed_job_id).with_for_update())
        ).scalar_one_or_none()
        if job_row is None:
            raise CandidateResolutionUnstableError(
                "existing occurrence's parent job was deleted before its lock could be acquired"
            )

        occurrence = (
            await session.execute(_existing_occurrence_query(natural_key).with_for_update())
        ).scalar_one_or_none()
        if (
            occurrence is None
            or occurrence.id != probed_occurrence_id
            or occurrence.job_id != probed_job_id
        ):
            raise CandidateResolutionUnstableError(
                "existing occurrence was deleted or reassociated before its lock could be acquired"
            )

        is_conflict = (
            occurrence.canonical_url_normalized is not None
            and incoming_canonical_url is not None
            and occurrence.canonical_url_normalized != incoming_canonical_url
        )

        occurrence.last_seen_at = max(occurrence.last_seen_at, observed_at)
        occurrence.is_active = True
        job_row.last_seen_at = max(job_row.last_seen_at, observed_at)

        await session.flush()
        kind = UpsertKind.QUARANTINED if is_conflict else UpsertKind.UPDATED
        return UpsertOutcome(job_id=occurrence.job_id, occurrence_id=occurrence.id, kind=kind)

    ambiguous_candidate_job_ids: tuple[uuid.UUID, ...] | None = None

    if incoming_canonical_url is not None:
        canonical_lock_key = canonical_url_advisory_lock_key(incoming_canonical_url)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=canonical_lock_key)
        )
        attach_outcome = await _attach_to_candidate(
            session,
            JobOccurrence.canonical_url_normalized == incoming_canonical_url,
            natural_key,
            job,
            observed_at,
        )
        if isinstance(attach_outcome, UpsertOutcome):
            return attach_outcome
        # `None` (zero candidates) or a genuine ambiguity tuple -> Tier 5
        # below, either as a plain INSERTED or tagged AMBIGUOUS. Tier 3 is
        # never attempted for this posting either way (see docstring above).
        ambiguous_candidate_job_ids = attach_outcome
    else:
        tenant_c = canonicalize_nullable_text(job.source_tenant_id)
        requisition_c = canonicalize_nullable_text(job.requisition_id_raw)
        if tenant_c is not None and requisition_c is not None:
            tenant_requisition_lock_key = tenant_requisition_advisory_lock_key(
                natural_key.provider, natural_key.source, tenant_c, requisition_c
            )
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)").bindparams(
                    key=tenant_requisition_lock_key
                )
            )
            attach_outcome = await _attach_to_candidate(
                session,
                (JobOccurrence.provider == natural_key.provider)
                & (JobOccurrence.source == natural_key.source)
                & (JobOccurrence.source_tenant_id == tenant_c)
                & (JobOccurrence.requisition_id_raw == requisition_c),
                natural_key,
                job,
                observed_at,
            )
            if isinstance(attach_outcome, UpsertOutcome):
                return attach_outcome
            ambiguous_candidate_job_ids = attach_outcome

    new_job = Job(
        title=job.title,
        location_raw=job.location,
        compensation_text=job.compensation_text,
        canonical_url=job.canonical_url,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )
    session.add(new_job)
    await session.flush()
    new_job_id = new_job.id

    new_occurrence = JobOccurrence(
        job_id=new_job_id,
        provider=job.provider,
        source=job.source,
        source_tenant_id=job.source_tenant_id,
        source_job_id=job.source_job_id,
        requisition_id_raw=job.requisition_id_raw,
        source_url=job.source_url,
        source_url_normalized=natural_key.url_normalized,
        apply_url=job.apply_url,
        canonical_url=job.canonical_url,
        canonical_url_normalized=incoming_canonical_url,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        posted_at=job.posted_at,
    )
    session.add(new_occurrence)
    await session.flush()
    kind = UpsertKind.AMBIGUOUS if ambiguous_candidate_job_ids is not None else UpsertKind.INSERTED
    return UpsertOutcome(
        job_id=new_job_id,
        occurrence_id=new_occurrence.id,
        kind=kind,
        ambiguous_candidate_job_ids=ambiguous_candidate_job_ids,
    )


async def _select_raw_for_association(session: AsyncSession, raw_id: uuid.UUID) -> RawJobIngestion:
    raw = (
        await session.execute(
            select(RawJobIngestion).where(RawJobIngestion.id == raw_id).with_for_update()
        )
    ).scalar_one_or_none()
    if raw is None:
        raise InvalidRawIngestionAssociationError(f"no RawJobIngestion row for id {raw_id}")
    return raw


def _validate_raw_association(
    raw: RawJobIngestion, natural_key: NaturalKey, job: DiscoveredJob
) -> None:
    """Every check below runs before any occurrence/conflict/raw mutation —
    see `InvalidRawIngestionAssociationError`'s own docstring for why the
    hash/`fetched_at` checks are load-bearing, not redundant, in the
    URL-fallback domain, and why the final `natural_key` re-resolution check
    is load-bearing too: `raw` has no `source_tenant_id`/normalized-URL
    column of its own to compare `natural_key` against, so a caller-supplied
    `natural_key` that shares `provider`/`source`/`source_identifier` with a
    genuinely matching raw/job pair — but disagrees on tenant or normalized
    URL — would otherwise pass every check above undetected, letting the
    found branch mutate/quarantine the *wrong* occurrence, or the insert
    branch acquire an advisory lock for one key while inserting an
    occurrence whose actual provider/source-derived fields describe another.
    """
    if raw.processing_status != "fetched":
        raise InvalidRawIngestionAssociationError("raw_id is not in the fetched state")
    if raw.job_occurrence_id is not None:
        raise InvalidRawIngestionAssociationError("raw_id is already linked to an occurrence")
    if raw.provider != natural_key.provider or raw.source != natural_key.source:
        raise InvalidRawIngestionAssociationError("raw_id provider/source does not match posting")
    if raw.source_identifier != natural_key.job_id:
        raise InvalidRawIngestionAssociationError("raw_id source_identifier does not match posting")
    if raw.raw_content_hash != canonical_json_hash(job.raw):
        raise InvalidRawIngestionAssociationError("raw_id content hash does not match posting")
    if raw.fetched_at != job.discovered_at:
        raise InvalidRawIngestionAssociationError("raw_id fetched_at does not match posting")
    try:
        expected_natural_key = resolve_identity(job)
    except UnresolvableIdentityError as exc:
        raise InvalidRawIngestionAssociationError(
            "natural_key does not match the posting's own resolved identity"
        ) from exc
    if expected_natural_key != natural_key:
        raise InvalidRawIngestionAssociationError(
            "natural_key does not match the posting's own resolved identity"
        )


async def _after_quarantine_flush() -> None:
    """Test seam only — a no-op in production. Tests monkeypatch this to
    simulate a failure after the occurrence's observational mutation, the
    parent `Job`'s observational mutation, the `IdentityConflict` insert,
    and the raw row's terminal update have all been flushed within
    `persist_posting`'s own transaction, but before that transaction
    commits — proving rollback discards all four effects together, not
    just some. Never a public parameter on `persist_posting`'s signature:
    a production caller cannot inject a failure here, only tests reaching
    it via `monkeypatch.setattr(persistence, "_after_quarantine_flush",
    ...)`.
    """
    return None


async def _after_attach_flush() -> None:
    """Test seam only — a no-op in production. Tests monkeypatch this to
    simulate a failure after the existing Job's `last_seen_at` update, the
    new `JobOccurrence` insert (both flushed inside `_attach_to_candidate`),
    and the raw row's terminal update (flushed in `persist_posting`) have
    all been sent to PostgreSQL, but before `persist_posting`'s transaction
    commits — proving rollback discards all three effects together. Never
    a public parameter; only reachable via
    `monkeypatch.setattr(persistence, "_after_attach_flush", ...)`.
    """
    return None


async def _after_ambiguous_flush() -> None:
    """Test seam only — a no-op in production. Tests monkeypatch this to
    simulate a failure after the new Job, new JobOccurrence (both flushed
    inside `upsert_job_occurrence`'s Tier-5 fallthrough), the
    `IdentityConflict` insert, and the raw row's terminal update (both
    flushed here in `persist_posting`) have all been sent to PostgreSQL,
    but before `persist_posting`'s transaction commits — proving rollback
    discards all four effects together, not just some. Never a public
    parameter; only reachable via
    `monkeypatch.setattr(persistence, "_after_ambiguous_flush", ...)`.
    """
    return None


async def persist_posting(
    engine: AsyncEngine,
    natural_key: NaturalKey,
    job: DiscoveredJob,
    observed_at: datetime,
    raw_id: uuid.UUID,
) -> UpsertOutcome:
    """Owns the one transaction that validates `raw_id`'s association with
    `job`, resolves/mutates the `Job`/`JobOccurrence` pair, and (for a
    quarantine or ambiguous-match outcome) records the `IdentityConflict`
    row and reroutes the raw row to `processing_status='identity_conflict'`
    — or, for a clean insert/update/attach, to `processing_status=
    'normalized'`. Any exception here — including from
    `_validate_raw_association` or `upsert_job_occurrence` (which includes
    `CandidateResolutionUnstableError`) — is not caught: it propagates out
    of this function, `session.begin()` rolls back everything this
    transaction touched, and the row `_validate_raw_association` locked is
    left exactly as it was.

    Reprocessing the same `raw_id` a second time (e.g. a retried call after
    a transient failure elsewhere) fails at `_validate_raw_association`'s
    `processing_status != 'fetched'` check before any mutation — this is
    what makes "one `IdentityConflict` per distinct new `RawJobIngestion`"
    a structural guarantee rather than an application-level convention:
    a raw row already turned `identity_conflict`/`normalized` can never
    reach the quarantine or ambiguous-match branch again.
    """
    async with AsyncSession(bind=engine) as session, session.begin():
        raw = await _select_raw_for_association(session, raw_id)
        _validate_raw_association(raw, natural_key, job)

        resolution = await upsert_job_occurrence(session, natural_key, job, observed_at)

        if resolution.kind is UpsertKind.QUARANTINED:
            occurrence = await session.get(JobOccurrence, resolution.occurrence_id)
            assert occurrence is not None
            conflict = IdentityConflict(
                existing_job_occurrence_id=resolution.occurrence_id,
                incoming_raw_job_ingestion_id=raw_id,
                conflict_type="evidence_mismatch",
                existing_value={"canonical_url_normalized": occurrence.canonical_url_normalized},
                incoming_value={"canonical_url_normalized": _normalize_canonical_url(job)},
                status="open",
            )
            session.add(conflict)
            raw.processing_status = "identity_conflict"
            raw.job_occurrence_id = resolution.occurrence_id
            await session.flush()
            await _after_quarantine_flush()
            return UpsertOutcome(
                job_id=resolution.job_id,
                occurrence_id=resolution.occurrence_id,
                kind=UpsertKind.QUARANTINED,
                conflict_id=conflict.id,
            )

        if resolution.kind is UpsertKind.AMBIGUOUS:
            assert resolution.ambiguous_candidate_job_ids is not None
            conflict = IdentityConflict(
                existing_job_occurrence_id=None,
                incoming_raw_job_ingestion_id=raw_id,
                conflict_type="ambiguous_match",
                existing_value=[str(job_id) for job_id in resolution.ambiguous_candidate_job_ids],
                incoming_value=[str(resolution.occurrence_id)],
                status="open",
            )
            session.add(conflict)
            raw.processing_status = "identity_conflict"
            raw.job_occurrence_id = resolution.occurrence_id
            await session.flush()
            await _after_ambiguous_flush()
            return UpsertOutcome(
                job_id=resolution.job_id,
                occurrence_id=resolution.occurrence_id,
                kind=UpsertKind.AMBIGUOUS,
                conflict_id=conflict.id,
                ambiguous_candidate_job_ids=resolution.ambiguous_candidate_job_ids,
            )

        raw.processing_status = "normalized"
        raw.job_occurrence_id = resolution.occurrence_id
        await session.flush()
        if resolution.kind is UpsertKind.ATTACHED:
            await _after_attach_flush()
        return resolution
