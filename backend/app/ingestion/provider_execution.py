import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.collection_run_provider_attempt import COVERED_WHITESPACE
from app.db.models.raw_job_ingestion import RawJobIngestion
from app.ingestion.hashing import canonical_json_hash
from app.ingestion.identity import (
    UNRESOLVABLE_IDENTITY_MESSAGE,
    UnresolvableIdentityError,
    resolve_identity,
)
from app.ingestion.persistence import UpsertKind, persist_posting
from app.providers.base import DiscoveryProvider
from app.schemas.discovered_job import DiscoveredJob, ProviderError, SourceRunStats
from app.schemas.provider import SourceQuery

logger = logging.getLogger(__name__)


class UnsupportedDiscoveryResultError(RuntimeError):
    """The provider returned a malformed or internally inconsistent result —
    a genuine adapter-contract violation, never a legitimate per-source
    failure. A source reporting `completed=False`/`incomplete_results=True`,
    or a `ProviderError`, is a *valid*, expected shape handled gracefully —
    this exception is reserved for a result whose own claims about itself
    don't add up (provider/source name mismatches, or a
    `jobs_found`/actual-`DiscoveredJob`-count disagreement that
    `DiscoveryResult`'s own pydantic validator cannot catch, since it has no
    way to distinguish a truthful zero from a lying or buggy adapter).
    Raised, and this provider's execution aborted, before any further
    posting is processed — callers must treat this as a whole-run-aborting
    failure, never a per-provider-continuing one (docs/ARCHITECTURE.md's
    orchestration section)."""


@dataclass
class ProviderExecutionState:
    """Mutated in place by `execute_provider_query()`; owned and passed in
    by the caller (`pipeline.py::run()` or `orchestrator.py::run_saved_search()`).
    Never built and returned only on success — a "build-then-return" seam
    would silently discard everything accumulated before a mid-execution
    exception, which is exactly the defect this design avoids: every field
    below is updated as soon as the corresponding fact becomes known, so a
    caller's exception handler can always read whatever was genuinely
    established before the raise.

    `source_stats` and `selected_errors` are populated immediately after a
    valid `DiscoveryResult` is received — before any posting is written or
    persisted — so a downstream raw-storage/identity/persistence exception
    still leaves this run's known `retry_count`/`rate_limited`/
    `incomplete_results` values and `failures` entries available to the
    caller, per the binding correction requiring known result telemetry to
    survive a later failure.
    """

    per_source_discovered: dict[str, int] = field(default_factory=dict)
    per_source_inserted: dict[str, int] = field(default_factory=dict)
    per_source_updated: dict[str, int] = field(default_factory=dict)
    failures: list[dict[str, object]] = field(default_factory=list)
    had_parse_error: bool = False
    had_conflict: bool = False
    possibly_incomplete: bool = False
    source_stats: dict[str, SourceRunStats] = field(default_factory=dict)
    selected_errors: dict[str, ProviderError] = field(default_factory=dict)


def resolve_attempt_status(stat: SourceRunStats) -> str:
    """The `collection_run_provider_attempts.status` value a source's own
    `SourceRunStats` implies on a *normal* completion path — never used on
    an aborted provider's rows, which are always `'failed'` regardless of
    what an individual source reported (docs/ARCHITECTURE.md's
    orchestration section)."""
    if not stat.completed:
        return "failed"
    if stat.incomplete_results:
        return "partial"
    return "completed"


def resolve_attempt_error_fields(
    selected_error: ProviderError | None,
) -> tuple[str | None, str | None]:
    """The `(error_category, error_message)` pair a source's selected
    (chronologically-latest, ties broken by later `result.errors` position)
    `ProviderError` implies — `error_message` is trimmed against this
    schema's own `COVERED_WHITESPACE` constant (never Python's broader
    default `str.strip()` set), matching the ORM validator's own
    normalization exactly."""
    if selected_error is None:
        return None, None
    error_message = None
    if selected_error.detail is not None:
        error_message = selected_error.detail.strip(COVERED_WHITESPACE) or None
    return selected_error.category.value, error_message


async def _write_fetched_row(
    engine: AsyncEngine, job: DiscoveredJob, fetched_at: datetime
) -> uuid.UUID:
    """Transaction A_i: commits exactly one `RawJobIngestion` row,
    `processing_status='fetched'`, before anything that could fail for
    identity/persistence reasons even begins — this transaction has no
    dependency on that later code at all, so it cannot fail because of a
    bug in it."""
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
    this transaction itself fails, the row remains at `fetched` (its own
    `session.begin()` rolls back), and the failure propagates with the
    original `UnresolvableIdentityError` retained as `__cause__` — never
    silently discarded."""
    try:
        async with AsyncSession(bind=engine) as session, session.begin():
            raw = await session.get(RawJobIngestion, raw_id)
            assert raw is not None
            raw.processing_status = "parse_error"
            raw.error_message = UNRESOLVABLE_IDENTITY_MESSAGE
    except Exception as terminal_update_exc:
        raise terminal_update_exc from identity_exc


async def execute_provider_query(
    engine: AsyncEngine,
    provider: DiscoveryProvider,
    query: SourceQuery,
    state: ProviderExecutionState,
    *,
    observed_at: datetime,
) -> None:
    """Executes one provider/query pair against attempt rows the caller has
    already created, mutating `state` in place. Creates and finalizes no
    `CollectionRun` or `CollectionRunProviderAttempt` row itself — the
    caller (`pipeline.py::run()`, which owns exactly one provider per run,
    or `orchestrator.py::run_saved_search()`, which owns several) decides
    when and how to create/finalize those, on whatever schedule its own
    design requires.

    Any exception raised here (`provider.discover()` raising,
    `UnsupportedDiscoveryResultError`, or any raw-storage/identity/
    persistence/database exception) must be treated by the caller as
    aborting — never continued past as a per-source/per-provider recoverable
    outcome. Only a fully-formed, self-consistent `DiscoveryResult`'s own
    graceful per-source `completed=False`/`incomplete_results=True`/
    `ProviderError` entries are a *valid*, non-exceptional degraded outcome
    — those are handled here exactly as `pipeline.run()` always has, never
    raised.
    """
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

    # `DiscoveryResult`'s own pydantic validator cannot check these — it has
    # no way to tell a truthful zero from a lying/buggy adapter. Checked
    # here, before any raw row is written: each is a whole-run contract
    # violation, never a legitimate per-source failure (that is
    # `completed=False`/`incomplete_results=True`/`ProviderError`, handled
    # gracefully below).
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

    # From this point on, `result` is fully validated and self-consistent —
    # every field below is recorded onto `state` immediately, before the
    # per-posting loop that follows, so it survives even if that loop later
    # raises (the binding correction this module exists to satisfy).
    state.source_stats = {stat.source: stat for stat in result.source_stats}
    state.possibly_incomplete = result.possibly_incomplete

    latest_error_by_source: dict[str, ProviderError] = {}
    for error in result.errors:
        current = latest_error_by_source.get(error.source)
        if current is None or error.occurred_at >= current.occurred_at:
            latest_error_by_source[error.source] = error
    state.selected_errors = latest_error_by_source

    # One entry per `ProviderError`, in `result.errors` order — never
    # deduplicated or collapsed to the single selected error above. `detail`
    # is never logged (only ever written to this list and to the
    # corresponding attempt row's own `error_message`).
    state.failures = [
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

    for source in query.sources:
        state.per_source_discovered.setdefault(source, 0)
        state.per_source_inserted.setdefault(source, 0)
        state.per_source_updated.setdefault(source, 0)
    for job in result.jobs:
        state.per_source_discovered[job.source] = state.per_source_discovered.get(job.source, 0) + 1

    raw_ingestion_ids = [
        await _write_fetched_row(engine, job, job.discovered_at) for job in result.jobs
    ]

    for job, raw_id in zip(result.jobs, raw_ingestion_ids, strict=True):
        try:
            natural_key = resolve_identity(job)
        except UnresolvableIdentityError as identity_exc:
            await _mark_parse_error(engine, raw_id, identity_exc)
            logger.warning("ingestion_parse_error raw_ingestion_id=%s", raw_id)
            state.had_parse_error = True
            continue

        outcome = await persist_posting(engine, natural_key, job, observed_at, raw_id)
        if outcome.kind is UpsertKind.INSERTED:
            state.per_source_inserted[job.source] = state.per_source_inserted.get(job.source, 0) + 1
        elif outcome.kind is UpsertKind.UPDATED:
            state.per_source_updated[job.source] = state.per_source_updated.get(job.source, 0) + 1
        elif outcome.kind is UpsertKind.ATTACHED:
            # A new JobOccurrence was created, but no new Job — the existing
            # Job's own last_seen_at was what advanced, so this counts as an
            # update to that Job, not an insertion of one.
            state.per_source_updated[job.source] = state.per_source_updated.get(job.source, 0) + 1
        elif outcome.kind is UpsertKind.QUARANTINED:
            # Quarantined: descriptive/canonical fields never applied, but
            # observational state did advance — bucketed with the other
            # partial-write outcome, not with a clean insert.
            state.per_source_updated[job.source] = state.per_source_updated.get(job.source, 0) + 1
            state.had_conflict = True
            logger.warning(
                "ingestion_identity_conflict raw_ingestion_id=%s "
                "identity_conflict_id=%s job_occurrence_id=%s",
                raw_id,
                outcome.conflict_id,
                outcome.occurrence_id,
            )
        elif outcome.kind is UpsertKind.AMBIGUOUS:
            # A new, standalone Job was created (like INSERTED) rather than
            # guessed into one of several candidates — counts as an
            # insertion, not an update, since a real new Job exists; flagged
            # the same way QUARANTINED is.
            state.per_source_inserted[job.source] = state.per_source_inserted.get(job.source, 0) + 1
            state.had_conflict = True
            logger.warning(
                "ingestion_identity_conflict raw_ingestion_id=%s "
                "identity_conflict_id=%s job_occurrence_id=%s",
                raw_id,
                outcome.conflict_id,
                outcome.occurrence_id,
            )
        else:
            # Fail closed for any future UpsertKind this dispatch does not
            # yet know how to bucket, rather than silently miscounting.
            raise AssertionError(f"unhandled UpsertKind: {outcome.kind!r}")
