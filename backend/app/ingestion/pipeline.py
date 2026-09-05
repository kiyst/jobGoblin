import asyncio
import logging
import uuid
from contextlib import suppress
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.collection_run import CollectionRun
from app.db.models.collection_run_provider_attempt import CollectionRunProviderAttempt
from app.ingestion.clock import Clock

# `_write_fetched_row` is re-exported (not just used internally) because a
# large existing test suite already calls `pipeline._write_fetched_row(...)`
# directly to set up fixtures — moving its implementation to
# `provider_execution.py` must not break that existing, public-by-usage
# surface.
from app.ingestion.provider_execution import (
    ProviderExecutionState,
    UnsupportedDiscoveryResultError,
    _write_fetched_row,
    execute_provider_query,
    resolve_attempt_error_fields,
    resolve_attempt_status,
)
from app.providers.base import DiscoveryProvider
from app.schemas.provider import SourceQuery

logger = logging.getLogger(__name__)

__all__ = ["run", "UnsupportedDiscoveryResultError", "_write_fetched_row"]


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

    A source-level failure never discards a sibling source's successful
    results (docs/ARCHITECTURE.md §6.3/§9/§11, docs/PHASE_RISK_CHECKLIST.md's
    cross-cutting non-negotiable): `SourceRunStats.completed=False` or
    `incomplete_results=True`, and any `ProviderError`, are all handled
    gracefully — jobs from every other source still persist normally, and
    each source's own `CollectionRunProviderAttempt` row records its own
    outcome independently (`status`, `error_category`/`error_message`,
    `retry_count`, `rate_limited`, `incomplete_results`). `CollectionRun.
    status` becomes `'completed_with_errors'` (never `'failed'`) whenever
    any source failed, was incomplete, or reported an error, alongside the
    existing per-posting `had_parse_error`/`had_conflict` triggers.
    `'failed'` remains reserved for the exception path below — a genuine
    crash, never a source telling the pipeline plainly that it failed.

    Only `UnresolvableIdentityError` is ever caught and reclassified as
    `parse_error`. Every other exception — including
    `asyncio.CancelledError` — triggers a best-effort attempt to mark the
    `CollectionRun`/`CollectionRunProviderAttempt` rows `status='failed'`
    and is then always re-raised, never swallowed
    (`KeyboardInterrupt`/`SystemExit` are never caught at all — they are
    not `Exception` or `CancelledError` subclasses, so this function's
    exception clauses never see them).

    The actual discover-through-persist logic lives in
    `app/ingestion/provider_execution.py::execute_provider_query()` — this
    function owns only `CollectionRun`/attempt-row creation and
    finalization, so the same execution primitive is shared with
    `app/ingestion/orchestrator.py::run_saved_search()` without either
    caller reaching into the other's internals.
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

    logger.info(
        "ingestion_run_started run_id=%s provider=%s sources=%s",
        collection_run_id,
        provider.name,
        ",".join(query.sources),
    )

    state = ProviderExecutionState()
    for source in query.sources:
        state.per_source_discovered.setdefault(source, 0)
        state.per_source_inserted.setdefault(source, 0)
        state.per_source_updated.setdefault(source, 0)

    try:
        await execute_provider_query(engine, provider, query, state, observed_at=observed_at)

        jobs_discovered = sum(state.per_source_discovered.values())
        inserted = sum(state.per_source_inserted.values())
        updated = sum(state.per_source_updated.values())
        run_status = (
            "completed_with_errors"
            if state.had_parse_error or state.had_conflict or state.possibly_incomplete
            else "completed"
        )
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
                    failures=state.failures,
                )
            )
            for source, attempt_id in attempt_ids.items():
                stat = state.source_stats[source]
                attempt_status = resolve_attempt_status(stat)
                selected_error = state.selected_errors.get(source)
                error_category, error_message = resolve_attempt_error_fields(selected_error)
                await session.execute(
                    update(CollectionRunProviderAttempt)
                    .where(CollectionRunProviderAttempt.id == attempt_id)
                    .values(
                        status=attempt_status,
                        completed_at=completed_at,
                        jobs_discovered=state.per_source_discovered.get(source, 0),
                        jobs_inserted=state.per_source_inserted.get(source, 0),
                        jobs_updated=state.per_source_updated.get(source, 0),
                        retry_count=stat.retry_count,
                        rate_limited=stat.rate_limited,
                        incomplete_results=stat.incomplete_results,
                        error_category=error_category,
                        error_message=error_message,
                    )
                )
        logger.info(
            "ingestion_run_completed run_id=%s status=%s discovered=%d inserted=%d updated=%d",
            collection_run_id,
            run_status,
            jobs_discovered,
            inserted,
            updated,
        )
        return collection_run_id

    except (Exception, asyncio.CancelledError) as run_exc:
        failed_at = clock.now()
        jobs_discovered = sum(state.per_source_discovered.values())
        inserted = sum(state.per_source_inserted.values())
        updated = sum(state.per_source_updated.values())
        duration_ms = int((failed_at - run_started_at).total_seconds() * 1000)
        logger.error(
            "ingestion_run_failed run_id=%s exception_type=%s",
            collection_run_id,
            type(run_exc).__name__,
        )
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
                    .values(
                        status="failed",
                        completed_at=failed_at,
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
                            status="failed",
                            completed_at=failed_at,
                            jobs_discovered=state.per_source_discovered.get(source, 0),
                            jobs_inserted=state.per_source_inserted.get(source, 0),
                            jobs_updated=state.per_source_updated.get(source, 0),
                        )
                    )
        raise
