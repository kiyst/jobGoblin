import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job import Job
from app.db.models.job_occurrence import JobOccurrence
from app.ingestion.natural_key import NaturalKey, NaturalKeyDomain
from app.normalization.url import normalize_url
from app.schemas.discovered_job import DiscoveredJob


@dataclass(frozen=True, slots=True)
class UpsertOutcome:
    job_id: uuid.UUID
    occurrence_id: uuid.UUID
    inserted: bool


class DeferredIdentityConflictError(RuntimeError):
    """A natural-key match has conflicting corroborating evidence.

    A later slice will persist the full ADR-0007 quarantine transition.
    Until then, this distinct exception fails closed without overwriting
    either side's evidence or misclassifying the payload as a parse error.
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
    key.

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

    The found branch updates observational state only. Descriptive,
    canonical, and source-provided fields remain frozen until the later
    provenance/merge and conflict-quarantine slices can reconcile them.
    When both stored and incoming normalized canonical URLs exist and
    disagree, the function fails closed before any mutation with
    `DeferredIdentityConflictError`.

    `observed_at` — the caller-supplied business timestamp, never a
    server-side `now()` — only ever moves `last_seen_at` (on both the
    occurrence and its parent `Job`) forward: `max(existing, incoming)`,
    computed in Python against the value just read under the row lock held
    above (safe without a second round trip, unlike a blind SQL `GREATEST`
    write), never a blind overwrite — so an out-of-order replay can never
    move it backward.
    """
    lock_key = natural_key.advisory_lock_key()
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=lock_key))

    occurrence = (await session.execute(_select_existing(natural_key))).scalar_one_or_none()

    if occurrence is not None:
        incoming_canonical_url = _normalize_canonical_url(job)
        if (
            occurrence.canonical_url_normalized is not None
            and incoming_canonical_url is not None
            and occurrence.canonical_url_normalized != incoming_canonical_url
        ):
            raise DeferredIdentityConflictError(
                "canonical URL evidence mismatch requires deferred conflict quarantine"
            )

        occurrence.last_seen_at = max(occurrence.last_seen_at, observed_at)
        occurrence.is_active = True

        job_row = await session.get(Job, occurrence.job_id)
        assert job_row is not None
        job_row.last_seen_at = max(job_row.last_seen_at, observed_at)

        await session.flush()
        return UpsertOutcome(job_id=occurrence.job_id, occurrence_id=occurrence.id, inserted=False)

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
    return UpsertOutcome(job_id=new_job_id, occurrence_id=new_occurrence.id, inserted=True)
