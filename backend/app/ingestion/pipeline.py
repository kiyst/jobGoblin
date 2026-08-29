import asyncio
import uuid
from contextlib import suppress
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.collection_run import CollectionRun
from app.db.models.collection_run_provider_attempt import CollectionRunProviderAttempt
from app.db.models.raw_job_ingestion import RawJobIngestion
from app.ingestion.clock import Clock
from app.ingestion.hashing import canonical_json_hash
from app.ingestion.identity import UnresolvableIdentityError, resolve_identity
from app.ingestion.natural_key import NaturalKey
from app.ingestion.persistence import UpsertOutcome, upsert_job_occurrence
from app.providers.base import DiscoveryProvider
from app.schemas.discovered_job import DiscoveredJob
from app.schemas.provider import SourceQuery


async def _write_fetched_row(
    engine: AsyncEngine, job: DiscoveredJob, fetched_at: datetime
) -> uuid.UUID:
    """Transaction A_i (docs binding decision, point 3): commits exactly one
    `RawJobIngestion` row, `processing_status='fetched'`, before anything
    that could fail for identity/persistence reasons even begins — this
    transaction has no dependency on that later code at all, so it cannot
    fail because of a bug in it."""
    async with AsyncSession(bind=engine) as session, session.begin():
        raw = RawJobIngestion(
            provider=job.provider,
            source=job.source,
            source_identifier=job.source_job_id,
            fetched_at=fetched_at,
            raw_payload=job.raw,
            raw_content_hash=canonical_json_hash(job.raw),
            processing_status="fetched",
        )
        session.add(raw)
        await session.flush()
        raw_id = raw.id
    return raw_id


async def _mark_parse_error(
    engine: AsyncEngine, raw_id: uuid.UUID, identity_exc: UnresolvableIdentityError
) -> None:
    """Transaction C_i: reroutes a `RawJobIngestion` row to
    `processing_status='parse_error'` after `resolve_identity` raised. If
    this transaction itself fails, the row remains at `fetched` (C_i's own
    `session.begin()` rolls back), and the failure propagates with the
    original `UnresolvableIdentityError` retained as `__cause__` — never
    silently discarded (docs binding decision, point 7)."""
    try:
        async with AsyncSession(bind=engine) as session, session.begin():
            raw = await session.get(RawJobIngestion, raw_id)
            assert raw is not None
            raw.processing_status = "parse_error"
            raw.error_message = str(identity_exc)
    except Exception as terminal_update_exc:
        raise terminal_update_exc from identity_exc


async def _persist_posting(
    engine: AsyncEngine,
    natural_key: NaturalKey,
    job: DiscoveredJob,
    observed_at: datetime,
    raw_id: uuid.UUID,
) -> UpsertOutcome:
    """Transaction B_i: `Job`/`JobOccurrence` upsert and the terminal
    `RawJobIngestion` update, in the same transaction. Any exception here —
    including from `upsert_job_occurrence` itself — is not caught: it
    propagates out of this function, `session.begin()` rolls back
    everything this transaction touched, and the row from Transaction A_i
    is left exactly as it was (`fetched`), untouched."""
    async with AsyncSession(bind=engine) as session, session.begin():
        outcome = await upsert_job_occurrence(session, natural_key, job, observed_at)
        raw = await session.get(RawJobIngestion, raw_id)
        assert raw is not None
        raw.processing_status = "normalized"
        raw.job_occurrence_id = outcome.occurrence_id
    return outcome


async def run(
    engine: AsyncEngine,
    provider: DiscoveryProvider,
    query: SourceQuery,
    *,
    observed_at: datetime,
    clock: Clock,
) -> uuid.UUID:
    """Runs one `CollectionRun` to completion and returns its id.

    `observed_at` is the business timestamp for `Job`/`JobOccurrence`
    (docs binding decision, point 6) — never used for run/attempt
    lifecycle timestamps, which come from `clock` instead, kept
    deliberately independent.

    Only `UnresolvableIdentityError` is ever caught and reclassified as
    `parse_error`. Every other exception — including
    `asyncio.CancelledError` — triggers a best-effort attempt to mark the
    `CollectionRun`/`CollectionRunProviderAttempt` rows `status='failed'`
    and is then always re-raised, never swallowed
    (`KeyboardInterrupt`/`SystemExit` are never caught at all — they are
    not `Exception` or `CancelledError` subclasses, so this function's
    exception clauses never see them).
    """
    run_started_at = clock.now()

    async with AsyncSession(bind=engine) as session, session.begin():
        collection_run = CollectionRun(
            started_at=run_started_at,
            status="running",
            providers_attempted=[provider.name],
        )
        session.add(collection_run)
        await session.flush()
        collection_run_id = collection_run.id

        attempt_ids: dict[str, uuid.UUID] = {}
        for source in query.sources:
            attempt = CollectionRunProviderAttempt(
                collection_run_id=collection_run_id,
                provider=provider.name,
                source=source,
                started_at=run_started_at,
                status="running",
            )
            session.add(attempt)
            await session.flush()
            attempt_ids[source] = attempt.id

    try:
        result = await provider.discover(query)

        if set(result.requested_sources) != set(query.sources):
            raise RuntimeError(
                f"DiscoveryResult.source_stats sources {sorted(result.requested_sources)} "
                f"do not match SourceQuery.sources {sorted(query.sources)}"
            )

        raw_ingestion_ids = [
            await _write_fetched_row(engine, job, observed_at) for job in result.jobs
        ]

        # Per-source counters: `collection_run_provider_attempts` is the
        # "authoritative per-source detail" table (its own model docstring)
        # — each attempt row must get *its own* source's counts, never the
        # run-wide totals applied uniformly. `collection_runs`' own three
        # counters are the run-level rollup (the sum across sources), which
        # is genuinely a different, correctly-shared value.
        per_source_discovered: dict[str, int] = dict.fromkeys(query.sources, 0)
        per_source_inserted: dict[str, int] = dict.fromkeys(query.sources, 0)
        per_source_updated: dict[str, int] = dict.fromkeys(query.sources, 0)
        for job in result.jobs:
            per_source_discovered[job.source] = per_source_discovered.get(job.source, 0) + 1

        had_parse_error = False
        for job, raw_id in zip(result.jobs, raw_ingestion_ids, strict=True):
            try:
                natural_key = resolve_identity(job)
            except UnresolvableIdentityError as identity_exc:
                await _mark_parse_error(engine, raw_id, identity_exc)
                had_parse_error = True
                continue

            outcome = await _persist_posting(engine, natural_key, job, observed_at, raw_id)
            if outcome.inserted:
                per_source_inserted[job.source] = per_source_inserted.get(job.source, 0) + 1
            else:
                per_source_updated[job.source] = per_source_updated.get(job.source, 0) + 1

        jobs_discovered = sum(per_source_discovered.values())
        inserted = sum(per_source_inserted.values())
        updated = sum(per_source_updated.values())
        run_status = "completed_with_errors" if had_parse_error else "completed"
        completed_at = clock.now()
        duration_ms = int((completed_at - run_started_at).total_seconds() * 1000)

        async with AsyncSession(bind=engine) as session, session.begin():
            await session.execute(
                update(CollectionRun)
                .where(CollectionRun.id == collection_run_id)
                .values(
                    status=run_status,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    jobs_discovered=jobs_discovered,
                    jobs_inserted=inserted,
                    jobs_updated=updated,
                )
            )
            for source, attempt_id in attempt_ids.items():
                await session.execute(
                    update(CollectionRunProviderAttempt)
                    .where(CollectionRunProviderAttempt.id == attempt_id)
                    .values(
                        status="completed",
                        completed_at=completed_at,
                        jobs_discovered=per_source_discovered.get(source, 0),
                        jobs_inserted=per_source_inserted.get(source, 0),
                        jobs_updated=per_source_updated.get(source, 0),
                    )
                )
        return collection_run_id

    except (Exception, asyncio.CancelledError):
        failed_at = clock.now()
        # `suppress(Exception)` alone would not catch a second
        # `asyncio.CancelledError` raised during this best-effort telemetry
        # write (it is a `BaseException` subclass, not `Exception` —
        # confirmed via `asyncio.CancelledError.__mro__`) — which would let
        # that second cancellation silently replace the original exception
        # instead of the `raise` below re-raising it. Both must be
        # suppressed here for the "telemetry failure never masks the
        # original exception" guarantee to actually hold.
        with suppress(Exception, asyncio.CancelledError):
            async with AsyncSession(bind=engine) as session, session.begin():
                await session.execute(
                    update(CollectionRun)
                    .where(CollectionRun.id == collection_run_id)
                    .values(status="failed", completed_at=failed_at)
                )
                for attempt_id in attempt_ids.values():
                    await session.execute(
                        update(CollectionRunProviderAttempt)
                        .where(CollectionRunProviderAttempt.id == attempt_id)
                        .values(status="failed", completed_at=failed_at)
                    )
        raise
