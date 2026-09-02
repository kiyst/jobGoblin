import asyncio
import logging
import uuid
from contextlib import suppress
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.collection_run import CollectionRun
from app.db.models.collection_run_provider_attempt import (
    COVERED_WHITESPACE,
    CollectionRunProviderAttempt,
)
from app.db.models.raw_job_ingestion import RawJobIngestion
from app.ingestion.clock import Clock
from app.ingestion.hashing import canonical_json_hash
from app.ingestion.identity import (
    UNRESOLVABLE_IDENTITY_MESSAGE,
    UnresolvableIdentityError,
    resolve_identity,
)
from app.ingestion.persistence import UpsertKind, persist_posting
from app.providers.base import DiscoveryProvider
from app.schemas.discovered_job import DiscoveredJob, ProviderError
from app.schemas.provider import SourceQuery

logger = logging.getLogger(__name__)


class UnsupportedDiscoveryResultError(RuntimeError):
    """The provider returned a malformed or internally inconsistent result —
    a genuine adapter-contract violation, never a legitimate per-source
    failure. A source reporting `completed=False`/`incomplete_results=True`,
    or a `ProviderError`, is a *valid*, expected shape handled gracefully
    (see `run()`'s own docstring) — this exception is reserved for a result
    whose own claims about itself don't add up (provider/source name
    mismatches, or a `jobs_found`/actual-`DiscoveredJob`-count
    disagreement that `DiscoveryResult`'s own pydantic validator cannot
    catch, since it has no way to distinguish a truthful zero from a lying
    or buggy adapter). Raised, and the whole run aborted, before any raw
    row is written."""


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
            raw.error_message = UNRESOLVABLE_IDENTITY_MESSAGE
    except Exception as terminal_update_exc:
        raise terminal_update_exc from identity_exc


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

    per_source_discovered: dict[str, int] = dict.fromkeys(query.sources, 0)
    per_source_inserted: dict[str, int] = dict.fromkeys(query.sources, 0)
    per_source_updated: dict[str, int] = dict.fromkeys(query.sources, 0)

    try:
        result = await provider.discover(query)

        if result.provider != provider.name:
            raise UnsupportedDiscoveryResultError(
                "DiscoveryResult.provider does not match the invoked provider"
            )
        if set(result.requested_sources) != set(query.sources):
            raise UnsupportedDiscoveryResultError(
                f"DiscoveryResult.source_stats sources {sorted(result.requested_sources)} "
                f"do not match SourceQuery.sources {sorted(query.sources)}"
            )
        if any(job.provider != result.provider for job in result.jobs):
            raise UnsupportedDiscoveryResultError(
                "DiscoveredJob.provider does not match DiscoveryResult.provider"
            )

        # `DiscoveryResult`'s own pydantic validator cannot check these — it
        # has no way to tell a truthful zero from a lying/buggy adapter.
        # Checked here, before any raw row is written: each is a whole-run
        # contract violation, never a legitimate per-source failure (that is
        # `completed=False`/`incomplete_results=True`/`ProviderError`,
        # handled gracefully below).
        actual_job_counts: dict[str, int] = {}
        for job in result.jobs:
            actual_job_counts[job.source] = actual_job_counts.get(job.source, 0) + 1
        for stat in result.source_stats:
            actual_count = actual_job_counts.get(stat.source, 0)
            if not stat.completed and actual_count > 0:
                raise UnsupportedDiscoveryResultError(
                    f"source {stat.source!r} reports completed=False but "
                    f"{actual_count} DiscoveredJob entries are attributed to it"
                )
            if not stat.completed and stat.incomplete_results:
                raise UnsupportedDiscoveryResultError(
                    f"source {stat.source!r} reports completed=False and "
                    "incomplete_results=True, which is not a valid combination"
                )
            if stat.jobs_found != actual_count:
                raise UnsupportedDiscoveryResultError(
                    f"source {stat.source!r} declared jobs_found={stat.jobs_found} but "
                    f"{actual_count} DiscoveredJob entries are attributed to it"
                )

        stats_by_source = {stat.source: stat for stat in result.source_stats}

        # The chronologically latest error per source (ties broken by later
        # position in `result.errors`) becomes that source's single
        # attempt-level `error_category`/`error_message` — but every error is
        # still preserved individually in `collection_runs.failures` below,
        # never collapsed. A `ProviderError` alone never changes a
        # `completed=True` source's own `status` (docs binding decision).
        latest_error_by_source: dict[str, ProviderError] = {}
        for error in result.errors:
            current = latest_error_by_source.get(error.source)
            if current is None or error.occurred_at >= current.occurred_at:
                latest_error_by_source[error.source] = error

        # One entry per `ProviderError`, in `result.errors` order — never
        # deduplicated or collapsed to the single selected error above.
        # `detail` is never logged (only ever written to this column and to
        # the corresponding attempt row's own `error_message`).
        failures = [
            {
                "provider": result.provider,
                "source": error.source,
                "error": {
                    "category": error.category.value,
                    "retryable": error.retryable,
                    "detail": error.detail,
                    "occurred_at": error.occurred_at.isoformat(),
                },
            }
            for error in result.errors
        ]

        for job in result.jobs:
            per_source_discovered[job.source] = per_source_discovered.get(job.source, 0) + 1

        raw_ingestion_ids = [
            await _write_fetched_row(engine, job, job.discovered_at) for job in result.jobs
        ]

        # Per-source counters: `collection_run_provider_attempts` is the
        # "authoritative per-source detail" table (its own model docstring)
        # — each attempt row must get *its own* source's counts, never the
        # run-wide totals applied uniformly. `collection_runs`' own three
        # counters are the run-level rollup (the sum across sources), which
        # is genuinely a different, correctly-shared value.
        had_parse_error = False
        had_conflict = False
        for job, raw_id in zip(result.jobs, raw_ingestion_ids, strict=True):
            try:
                natural_key = resolve_identity(job)
            except UnresolvableIdentityError as identity_exc:
                await _mark_parse_error(engine, raw_id, identity_exc)
                logger.warning("ingestion_parse_error raw_ingestion_id=%s", raw_id)
                had_parse_error = True
                continue

            outcome = await persist_posting(engine, natural_key, job, observed_at, raw_id)
            if outcome.kind is UpsertKind.INSERTED:
                per_source_inserted[job.source] = per_source_inserted.get(job.source, 0) + 1
            elif outcome.kind is UpsertKind.UPDATED:
                per_source_updated[job.source] = per_source_updated.get(job.source, 0) + 1
            elif outcome.kind is UpsertKind.ATTACHED:
                # A new JobOccurrence was created, but no new Job — the
                # existing Job's own last_seen_at was what advanced, so
                # this counts as an update to that Job, not an insertion
                # of one.
                per_source_updated[job.source] = per_source_updated.get(job.source, 0) + 1
            elif outcome.kind is UpsertKind.QUARANTINED:
                # Quarantined: descriptive/canonical fields never applied,
                # but observational state did advance — bucketed with the
                # other partial-write outcome, not with a clean insert.
                per_source_updated[job.source] = per_source_updated.get(job.source, 0) + 1
                had_conflict = True
                logger.warning(
                    "ingestion_identity_conflict raw_ingestion_id=%s "
                    "identity_conflict_id=%s job_occurrence_id=%s",
                    raw_id,
                    outcome.conflict_id,
                    outcome.occurrence_id,
                )
            elif outcome.kind is UpsertKind.AMBIGUOUS:
                # A new, standalone Job was created (like INSERTED) rather
                # than guessed into one of several candidates — counts as
                # an insertion, not an update, since a real new Job exists;
                # flagged the same way QUARANTINED is.
                per_source_inserted[job.source] = per_source_inserted.get(job.source, 0) + 1
                had_conflict = True
                logger.warning(
                    "ingestion_identity_conflict raw_ingestion_id=%s "
                    "identity_conflict_id=%s job_occurrence_id=%s",
                    raw_id,
                    outcome.conflict_id,
                    outcome.occurrence_id,
                )
            else:
                # Fail closed for any future UpsertKind this dispatch does
                # not yet know how to bucket, rather than silently miscounting.
                raise AssertionError(f"unhandled UpsertKind: {outcome.kind!r}")

        jobs_discovered = sum(per_source_discovered.values())
        inserted = sum(per_source_inserted.values())
        updated = sum(per_source_updated.values())
        had_source_issue = result.possibly_incomplete
        run_status = (
            "completed_with_errors"
            if had_parse_error or had_conflict or had_source_issue
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
                    failures=failures,
                )
            )
            for source, attempt_id in attempt_ids.items():
                stat = stats_by_source[source]
                if not stat.completed:
                    attempt_status = "failed"
                elif stat.incomplete_results:
                    attempt_status = "partial"
                else:
                    attempt_status = "completed"
                selected_error = latest_error_by_source.get(source)
                # `update()` is a Core statement — it bypasses the model's
                # own `@validates("error_message")` trim/blank-to-`None`
                # normalization, which only fires on ORM attribute
                # assignment. Applied manually here, against the model's own
                # `COVERED_WHITESPACE` constant (never Python's broader
                # default `str.strip()` whitespace set) so this Core-update
                # path normalizes identically to what ORM-path assignment of
                # the same value would do — an adapter-supplied
                # covered-whitespace-only `detail` still collapses to `None`
                # rather than violate `error_message`'s own non-empty
                # `CHECK`, but non-covered Unicode whitespace (e.g. U+00A0)
                # is left byte-for-byte intact, exactly as the ORM validator
                # would leave it.
                error_message = None
                if selected_error is not None and selected_error.detail is not None:
                    error_message = selected_error.detail.strip(COVERED_WHITESPACE) or None
                await session.execute(
                    update(CollectionRunProviderAttempt)
                    .where(CollectionRunProviderAttempt.id == attempt_id)
                    .values(
                        status=attempt_status,
                        completed_at=completed_at,
                        jobs_discovered=per_source_discovered.get(source, 0),
                        jobs_inserted=per_source_inserted.get(source, 0),
                        jobs_updated=per_source_updated.get(source, 0),
                        retry_count=stat.retry_count,
                        rate_limited=stat.rate_limited,
                        incomplete_results=stat.incomplete_results,
                        error_category=(
                            selected_error.category.value if selected_error is not None else None
                        ),
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
        jobs_discovered = sum(per_source_discovered.values())
        inserted = sum(per_source_inserted.values())
        updated = sum(per_source_updated.values())
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
                            jobs_discovered=per_source_discovered.get(source, 0),
                            jobs_inserted=per_source_inserted.get(source, 0),
                            jobs_updated=per_source_updated.get(source, 0),
                        )
                    )
        raise
