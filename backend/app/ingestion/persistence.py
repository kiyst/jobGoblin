import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy import Select, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.identity_conflict import IdentityConflict
from app.db.models.job import Job
from app.db.models.job_occurrence import JobOccurrence
from app.db.models.raw_job_ingestion import RawJobIngestion
from app.ingestion.hashing import canonical_json_hash
from app.ingestion.identity import UnresolvableIdentityError, resolve_identity
from app.ingestion.natural_key import NaturalKey, NaturalKeyDomain
from app.normalization.url import normalize_url
from app.schemas.discovered_job import DiscoveredJob


class UpsertKind(Enum):
    """The three outcomes `persist_posting`/`upsert_job_occurrence` can
    reach for one posting. `QUARANTINED` replaces the earlier
    `DeferredIdentityConflictError` design: a canonical-URL evidence
    mismatch is now a real ADR-0007 quarantine transition, not a failure
    that aborts the enclosing run."""

    INSERTED = "inserted"
    UPDATED = "updated"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class UpsertOutcome:
    job_id: uuid.UUID
    occurrence_id: uuid.UUID
    kind: UpsertKind
    conflict_id: uuid.UUID | None = None


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


def _normalize_canonical_url(job: DiscoveredJob) -> str | None:
    if job.canonical_url is None:
        return None
    return normalize_url(job.canonical_url, provider=job.provider, source=job.source)


def _select_existing(natural_key: NaturalKey) -> Select[tuple[JobOccurrence]]:
    """Selects the full ORM entity (not bare columns) so the "found" branch
    below can update it by plain attribute assignment — which runs through
    `JobOccurrence`'s own `@validates` normalization — rather than a
    Core-style `update()` statement, which does not."""
    query = select(JobOccurrence).where(
        JobOccurrence.provider == natural_key.provider,
        JobOccurrence.source == natural_key.source,
    )
    if natural_key.domain is NaturalKeyDomain.TENANT:
        query = query.where(
            JobOccurrence.source_tenant_id == natural_key.tenant_id,
            JobOccurrence.source_job_id == natural_key.job_id,
        )
    elif natural_key.domain is NaturalKeyDomain.NO_TENANT:
        query = query.where(
            JobOccurrence.source_tenant_id.is_(None),
            JobOccurrence.source_job_id == natural_key.job_id,
        )
    else:
        query = query.where(
            JobOccurrence.source_job_id.is_(None),
            JobOccurrence.source_url_normalized == natural_key.url_normalized,
        )
    return query.with_for_update()


async def upsert_job_occurrence(
    session: AsyncSession,
    natural_key: NaturalKey,
    job: DiscoveredJob,
    observed_at: datetime,
) -> UpsertOutcome:
    """Creates or updates the `Job`/`JobOccurrence` pair for `job`'s natural
    key. Never touches `RawJobIngestion` or `IdentityConflict` — that is
    `persist_posting`'s responsibility, since only it holds the validated
    `raw_id` an `IdentityConflict` row must reference.

    Holds a PostgreSQL advisory transaction lock keyed by `natural_key`
    (`NaturalKey.advisory_lock_key()`) for the remainder of the caller's
    transaction, acquired *before* the existence check below. This is what
    makes the following check-then-act sequence safe without a speculative/
    orphan `Job` row and without an `ON CONFLICT` clause: every other
    transaction attempting to resolve the *same* natural key blocks on the
    lock until this one commits or rolls back, so by the time this function
    reaches the "not found" branch, no concurrent transaction can possibly
    be inserting the same key underneath it. The "found" branch never
    assigns `job_id` — it only ever mutates observational columns on the
    already-resolved, already-loaded ORM instance — so an existing
    occurrence is never reassigned to a different `Job`, and its
    association is never lost.

    The found branch **always** advances observational state
    (`last_seen_at`/`is_active` on the occurrence, `last_seen_at` on the
    parent `Job`) — whether or not the incoming payload's normalized
    canonical URL agrees with the one already recorded. Descriptive,
    canonical, and source-provided fields remain frozen either way. When
    both stored and incoming normalized canonical URLs exist and disagree,
    the returned outcome's `kind` is `QUARANTINED` rather than `UPDATED` —
    `persist_posting` uses that signal to record the `IdentityConflict` row
    ADR 0007 requires; this function itself never mutates the disputed
    field and never creates that row.

    `observed_at` — the caller-supplied business timestamp, never a
    server-side `now()` — only ever moves `last_seen_at` (on both the
    occurrence and its parent `Job`) forward: `max(existing, incoming)`,
    computed in Python against the value just read under the row lock held
    above (safe without a second round trip, unlike a blind SQL `GREATEST`
    write), never a blind overwrite — so an out-of-order replay can never
    move it backward, including when it lands on the quarantine branch.
    """
    lock_key = natural_key.advisory_lock_key()
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=lock_key))

    occurrence = (await session.execute(_select_existing(natural_key))).scalar_one_or_none()

    if occurrence is not None:
        incoming_canonical_url = _normalize_canonical_url(job)
        is_conflict = (
            occurrence.canonical_url_normalized is not None
            and incoming_canonical_url is not None
            and occurrence.canonical_url_normalized != incoming_canonical_url
        )

        occurrence.last_seen_at = max(occurrence.last_seen_at, observed_at)
        occurrence.is_active = True

        job_row = await session.get(Job, occurrence.job_id)
        assert job_row is not None
        job_row.last_seen_at = max(job_row.last_seen_at, observed_at)

        await session.flush()
        kind = UpsertKind.QUARANTINED if is_conflict else UpsertKind.UPDATED
        return UpsertOutcome(job_id=occurrence.job_id, occurrence_id=occurrence.id, kind=kind)

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
        canonical_url_normalized=_normalize_canonical_url(job),
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        posted_at=job.posted_at,
    )
    session.add(new_occurrence)
    await session.flush()
    return UpsertOutcome(
        job_id=new_job_id, occurrence_id=new_occurrence.id, kind=UpsertKind.INSERTED
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


async def persist_posting(
    engine: AsyncEngine,
    natural_key: NaturalKey,
    job: DiscoveredJob,
    observed_at: datetime,
    raw_id: uuid.UUID,
) -> UpsertOutcome:
    """Owns the one transaction that validates `raw_id`'s association with
    `job`, resolves/mutates the `Job`/`JobOccurrence` pair, and (for a
    quarantine outcome) records the `IdentityConflict` row and reroutes the
    raw row to `processing_status='identity_conflict'` — or, for a clean
    insert/update, to `processing_status='normalized'`. Any exception here
    — including from `_validate_raw_association` or
    `upsert_job_occurrence` — is not caught: it propagates out of this
    function, `session.begin()` rolls back everything this transaction
    touched, and the row `_validate_raw_association` locked is left exactly
    as it was.

    Reprocessing the same `raw_id` a second time (e.g. a retried call after
    a transient failure elsewhere) fails at `_validate_raw_association`'s
    `processing_status != 'fetched'` check before any mutation — this is
    what makes "one `IdentityConflict` per distinct new `RawJobIngestion`"
    a structural guarantee rather than an application-level convention:
    a raw row already turned `identity_conflict`/`normalized` can never
    reach the quarantine branch again.
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

        raw.processing_status = "normalized"
        raw.job_occurrence_id = resolution.occurrence_id
        await session.flush()
        return resolution
