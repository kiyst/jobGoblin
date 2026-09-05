import asyncio
import logging
import uuid
from contextlib import suppress
from datetime import datetime

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.collection_run import CollectionRun
from app.db.models.collection_run_provider_attempt import CollectionRunProviderAttempt
from app.db.models.saved_search import SavedSearch
from app.db.models.saved_search_location import SavedSearchLocation
from app.db.models.saved_search_title import SavedSearchTitle
from app.discovery.query_planner import QueryPlanner, QueryPlanValidationError
from app.ingestion.clock import Clock
from app.ingestion.provider_execution import (
    ProviderExecutionState,
    execute_provider_query,
    resolve_attempt_error_fields,
    resolve_attempt_status,
)
from app.providers.registry import ProviderRegistry, UnknownProviderError
from app.schemas.identifiers import is_canonical_slug
from app.schemas.provider import SourceQuery

logger = logging.getLogger(__name__)

# Every message below is a fixed, categorical string — same non-
# interpolation convention as `QueryPlanValidationError`/
# `ProviderRegistrationError`: never the actual malformed value, the actual
# provider list, or any caught exception's own text.
_ERROR_SAVED_SEARCH_NOT_FOUND = "no SavedSearch exists for the given id"
_ERROR_INACTIVE_SAVED_SEARCH = "the saved search is not active"
_ERROR_MALFORMED_ENABLED_PROVIDER = (
    "saved_search.enabled_providers contains a value that is not a string or does not "
    "match the canonical provider-slug grammar"
)
_ERROR_DUPLICATE_ENABLED_PROVIDER = (
    "saved_search.enabled_providers contains a duplicate provider name"
)

# Used only for a whole-run-aborted provider's own attempt rows — never for
# a graceful per-source `ProviderError` (that keeps its own real category/
# detail via `resolve_attempt_error_fields`). Not one of `ProviderErrorCategory`'s
# 8 values is a better fit for "this provider's execution was aborted by an
# unrelated whole-run failure," so the existing `"unknown"` value is reused
# rather than inventing a new one.
_ABORT_ERROR_CATEGORY = "unknown"
_ABORT_ERROR_MESSAGE = "this provider's execution was aborted before completing"

# Used only for a planning failure (an unknown provider, or a
# QueryPlanValidationError) — occurs before any source is ever resolved, so
# there is no real source to attribute it to. `source: null` is a legitimate
# use of `collection_runs.failures`'s existing, unconstrained-by-CHECK JSON
# shape (docs/DATA_MODEL.md), not a new invented shape — the same "NULL for
# unknown values, never an invented sentinel" convention this whole schema
# already follows elsewhere.
_PLANNING_FAILURE_CATEGORY = "unknown"


class SavedSearchNotFoundError(RuntimeError):
    """No `SavedSearch` exists for the given id. Raised before any
    `CollectionRun` row is created — a caller-side usage error, not a
    per-provider planning outcome."""


class InactiveSavedSearchError(RuntimeError):
    """`saved_search.is_active` is `False`. Raised before any
    `CollectionRun` row is created. Running collection for a paused search
    is not supported by this slice — there is no current caller needing a
    manual-preview override (Phase 8's API doesn't exist yet), and adding
    one now would be speculative; a future explicit override belongs to
    whichever slice actually introduces such a caller."""


class MalformedEnabledProviderError(RuntimeError):
    """An entry in `saved_search.enabled_providers` is not a `str`, or does
    not match the canonical provider-slug grammar. Raised before any
    `CollectionRun` row is created — never silently dropped, and never
    allowed to reach `CollectionRun.failures.provider` unvalidated."""


class DuplicateEnabledProviderError(RuntimeError):
    """`saved_search.enabled_providers` contains the same provider name more
    than once. Raised before any `CollectionRun` row is created — never
    silently deduplicated."""


def _serialize_local_enforcement(
    provider_name: str, local_enforcement: dict[str, set[str]]
) -> dict[str, dict[str, list[str]]]:
    """`SourceQuery.local_enforcement` is `dict[str, set[str]]` — not
    JSON-serializable as-is, and Python `set` iteration order is not
    guaranteed deterministic. Converts each set to a sorted list before it
    is ever merged into `collection_runs.providers_enforced_locally`, so the
    persisted JSON is byte-identical across runs regardless of the set's
    internal hash order."""
    return {provider_name: {source: sorted(fields) for source, fields in local_enforcement.items()}}


async def _append_planning_failure(
    engine: AsyncEngine,
    collection_run_id: uuid.UUID,
    provider_name: str,
    detail: str,
    occurred_at: datetime,
) -> None:
    """Durably records one planning failure the moment it is known — never
    batched to the end. `detail` is always the raising exception's own
    `str()`, which is itself already one of `QueryPlanValidationError`'s or
    `UnknownProviderError`'s fixed, categorical, non-interpolating
    messages — never further runtime data."""
    entry = {
        "provider": provider_name,
        "source": None,
        "error": {
            "category": _PLANNING_FAILURE_CATEGORY,
            "retryable": False,
            "detail": detail,
            "occurred_at": occurred_at.isoformat(),
        },
    }
    async with AsyncSession(bind=engine) as session, session.begin():
        await session.execute(
            update(CollectionRun)
            .where(CollectionRun.id == collection_run_id)
            .values(failures=CollectionRun.failures.op("||")(cast([entry], JSONB)))
        )


async def _begin_provider_attempt(
    engine: AsyncEngine,
    collection_run_id: uuid.UUID,
    provider_name: str,
    query: SourceQuery,
    started_at: datetime,
) -> dict[str, uuid.UUID]:
    """Atomically, in one transaction: appends `provider_name` to
    `providers_attempted`, merges this provider's serialized
    `local_enforcement` into `providers_enforced_locally`, and creates one
    `CollectionRunProviderAttempt` row (`status='running'`) per source —
    immediately before this provider's `discover()` call, never pre-created
    for the whole plan. `started_at` is a fresh `clock.now()` read taken by
    the caller for this provider specifically — never the run's own
    `started_at`, and never reused from an earlier provider."""
    enforced_locally_entry = _serialize_local_enforcement(provider_name, query.local_enforcement)
    async with AsyncSession(bind=engine) as session, session.begin():
        await session.execute(
            update(CollectionRun)
            .where(CollectionRun.id == collection_run_id)
            .values(
                providers_attempted=func.array_append(
                    CollectionRun.providers_attempted, provider_name
                ),
                providers_enforced_locally=CollectionRun.providers_enforced_locally.op("||")(
                    cast(enforced_locally_entry, JSONB)
                ),
            )
        )
        attempt_ids: dict[str, uuid.UUID] = {}
        for source in query.sources:
            attempt = CollectionRunProviderAttempt(
                collection_run_id=collection_run_id,
                provider=provider_name,
                source=source,
                started_at=started_at,
                status="running",
            )
            session.add(attempt)
            await session.flush()
            attempt_ids[source] = attempt.id
    return attempt_ids


async def _finalize_provider_success(
    engine: AsyncEngine,
    collection_run_id: uuid.UUID,
    attempt_ids: dict[str, uuid.UUID],
    state: ProviderExecutionState,
    completed_at: datetime,
) -> None:
    """One transaction: finalizes this provider's own attempt rows (status/
    counts/error fields, exactly as `pipeline.run()` already computes for
    its single provider) and atomically increments `CollectionRun`'s own
    rollup counters by this provider's exact deltas — a single SQL
    `col = col + :delta` expression per counter, never a Python read-
    modify-write, so this increment cannot race with anything. Also merges
    this provider's own graceful `ProviderError` entries (if any) into
    `collection_runs.failures`, in their original `result.errors` order —
    jsonb `||` against an empty list is a no-op, so no conditional branch is
    needed when `state.failures` happens to be empty."""
    discovered_delta = sum(state.per_source_discovered.values())
    inserted_delta = sum(state.per_source_inserted.values())
    updated_delta = sum(state.per_source_updated.values())
    async with AsyncSession(bind=engine) as session, session.begin():
        await session.execute(
            update(CollectionRun)
            .where(CollectionRun.id == collection_run_id)
            .values(
                jobs_discovered=CollectionRun.jobs_discovered + discovered_delta,
                jobs_inserted=CollectionRun.jobs_inserted + inserted_delta,
                jobs_updated=CollectionRun.jobs_updated + updated_delta,
                failures=CollectionRun.failures.op("||")(cast(state.failures, JSONB)),
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


async def _finalize_provider_aborted(
    engine: AsyncEngine,
    collection_run_id: uuid.UUID,
    attempt_ids: dict[str, uuid.UUID],
    state: ProviderExecutionState,
    failed_at: datetime,
) -> None:
    """Best-effort, called only for the one provider that was still in
    flight when a whole-run abort occurred. Every attempt row becomes
    `'failed'` uniformly — never a mix of `'completed'`/`'partial'` derived
    from a `DiscoveryResult` that may or may not have even been received —
    with a fixed, sanitized `error_category`/`error_message` (never the
    aborting exception's own text). `retry_count`/`rate_limited`/
    `incomplete_results` still use `state.source_stats`, if known,
    preserving genuinely-known telemetry through the failure; if the abort
    happened before `state.source_stats` was ever populated (`discover()`
    itself raised), every value falls back to its own safe default. Known
    graceful `ProviderError` entries (`state.failures`) are still merged
    into `collection_runs.failures` even though the run is aborting."""
    async with AsyncSession(bind=engine) as session, session.begin():
        if state.failures:
            await session.execute(
                update(CollectionRun)
                .where(CollectionRun.id == collection_run_id)
                .values(failures=CollectionRun.failures.op("||")(cast(state.failures, JSONB)))
            )
        for source, attempt_id in attempt_ids.items():
            stat = state.source_stats.get(source)
            await session.execute(
                update(CollectionRunProviderAttempt)
                .where(CollectionRunProviderAttempt.id == attempt_id)
                .values(
                    status="failed",
                    completed_at=failed_at,
                    jobs_discovered=state.per_source_discovered.get(source, 0),
                    jobs_inserted=state.per_source_inserted.get(source, 0),
                    jobs_updated=state.per_source_updated.get(source, 0),
                    retry_count=stat.retry_count if stat is not None else 0,
                    rate_limited=stat.rate_limited if stat is not None else False,
                    incomplete_results=stat.incomplete_results if stat is not None else False,
                    error_category=_ABORT_ERROR_CATEGORY,
                    error_message=_ABORT_ERROR_MESSAGE,
                )
            )


async def run_saved_search(
    engine: AsyncEngine,
    saved_search_id: uuid.UUID,
    provider_registry: ProviderRegistry,
    *,
    clock: Clock,
    observed_at: datetime,
) -> uuid.UUID:
    """Runs one `CollectionRun` spanning every provider selected for
    `saved_search_id`, sequentially. See docs/ARCHITECTURE.md's
    orchestration section for the complete design; summarized:

    - Loads the authoritative `SavedSearch` by id itself (never accepts a
      caller-supplied instance, which could be stale) plus its
      `SavedSearchTitle`/`SavedSearchLocation` rows, `ORDER BY created_at,
      id` — deterministic, not insertion order (PostgreSQL `now()` is fixed
      at transaction start, so rows inserted together share `created_at`).
      Locks the `SavedSearch` row `FOR SHARE` for the duration of this one
      initialization transaction only, so a concurrent delete cannot
      complete while `CollectionRun.saved_search_id` is being written to
      reference it — this protects only the parent-row/FK initialization,
      never a serializable snapshot of the title/location child rows.
    - `saved_search.enabled_providers`: `NULL` expands to every registered
      provider name (sorted); an explicit list is validated (every entry a
      `str` matching the canonical slug grammar, no duplicates) before any
      write and then used in its own given order — `enabled_providers` is a
      plain `text[]` with no CHECK constraining its elements, so even a
      non-string element (unreachable through any current caller, but not
      through the database) fails closed the same way. A canonical-but-
      unregistered name is *not* rejected here — it becomes a per-provider
      planning failure once the loop reaches it.
    - `saved_search.is_active=False` raises before any write.
    - Providers execute strictly sequentially. `UnknownProviderError` (an
      unregistered name) and `QueryPlanValidationError` (a planning
      defect) are the *only* two exceptions that continue to the next
      provider — both durably recorded the instant they occur, `source:
      null`, since no source was ever resolved. Every other exception
      (`ProviderRegistrationError`/name drift, an unexpected
      `provider.discover()` exception, `UnsupportedDiscoveryResultError`,
      any raw-storage/identity/persistence/database exception, or
      cancellation) aborts the *entire* run.
    - Attempt rows are created lazily, atomically with `providers_attempted`
      and `providers_enforced_locally`, immediately before that provider's
      `discover()` call — never pre-created, never left behind for a
      provider never reached.
    - On normal per-provider completion: that provider's own attempt rows
      finalize and its jobs_discovered/inserted/updated deltas are
      atomically added to `CollectionRun`'s own rollup (`col = col +
      :delta`, one SQL expression, in the same transaction as the attempt
      rows — this cannot race with anything, since both writes commit or
      roll back together).
    - On a whole-run abort: the in-flight provider's own attempt rows are
      finalized best-effort from whatever `ProviderExecutionState` already
      captured, then `CollectionRun`'s own rollup is *recomputed from a
      fresh `SELECT SUM(...)` over every persisted attempt row for this
      run* and written as an absolute value — never derived from a
      parallel in-memory running total, which could fall out of sync with
      the database if a cancellation is delivered between a provider's
      commit finishing and the next line of Python resuming. This makes
      `CollectionRun`'s rollup always exactly `SUM` over its own attempt
      rows, provably, on every path.
    - Status: `'failed'` only for a whole-run abort; `'completed_with_errors'`
      for a natural completion with any planning failure, graceful
      `ProviderError`, non-`'completed'` attempt, parse error, or identity
      conflict — including the case where *every* provider produced a
      planning failure; `'completed'` otherwise, including an explicit
      empty provider list or every provider being silently skipped by
      `QueryPlanner` returning `None`.
    """
    async with AsyncSession(bind=engine, expire_on_commit=False) as session, session.begin():
        loaded = await session.execute(
            select(SavedSearch).where(SavedSearch.id == saved_search_id).with_for_update(read=True)
        )
        saved_search = loaded.scalar_one_or_none()
        if saved_search is None:
            raise SavedSearchNotFoundError(_ERROR_SAVED_SEARCH_NOT_FOUND)
        if not saved_search.is_active:
            raise InactiveSavedSearchError(_ERROR_INACTIVE_SAVED_SEARCH)

        titles_result = await session.execute(
            select(SavedSearchTitle.title)
            .where(SavedSearchTitle.saved_search_id == saved_search_id)
            .order_by(SavedSearchTitle.created_at, SavedSearchTitle.id)
        )
        titles = [row[0] for row in titles_result.all()]

        locations_result = await session.execute(
            select(SavedSearchLocation.location_text)
            .where(SavedSearchLocation.saved_search_id == saved_search_id)
            .order_by(SavedSearchLocation.created_at, SavedSearchLocation.id)
        )
        locations = [row[0] for row in locations_result.all()]

        enabled_providers = saved_search.enabled_providers
        if enabled_providers is None:
            resolved_provider_names = provider_registry.names()
        else:
            for name in enabled_providers:
                # `is_canonical_slug()` assumes `str` and raises a raw
                # `TypeError` on anything else (e.g. `None`) — checked here
                # first so a non-string element fails closed with the same
                # sanitized `MalformedEnabledProviderError` as a malformed
                # string, never an unhandled `TypeError`. `enabled_providers`
                # is a plain `text[]` with no CHECK constraining its
                # elements, so this is not merely a defensive formality.
                if not isinstance(name, str) or not is_canonical_slug(name):
                    raise MalformedEnabledProviderError(_ERROR_MALFORMED_ENABLED_PROVIDER)
            if len(set(enabled_providers)) != len(enabled_providers):
                raise DuplicateEnabledProviderError(_ERROR_DUPLICATE_ENABLED_PROVIDER)
            resolved_provider_names = list(enabled_providers)

        run_started_at = clock.now()
        collection_run = CollectionRun(
            saved_search_id=saved_search_id,
            started_at=run_started_at,
            status="running",
        )
        session.add(collection_run)
        await session.flush()
        collection_run_id = collection_run.id
    # Transaction commits here, releasing the FOR SHARE lock. `saved_search`
    # remains fully readable afterward (`expire_on_commit=False`): every
    # column was already loaded by the `SELECT` above, so no further
    # database access happens through this instance.

    logger.info(
        "ingestion_run_started run_id=%s saved_search_id=%s providers=%s",
        collection_run_id,
        saved_search_id,
        ",".join(resolved_provider_names),
    )

    any_planning_failure = False
    run_had_parse_error = False
    run_had_conflict = False
    any_attempt_not_completed = False
    current_attempt_ids: dict[str, uuid.UUID] | None = None
    current_state: ProviderExecutionState | None = None

    try:
        for provider_name in resolved_provider_names:
            try:
                registered = provider_registry.get(provider_name)
            except UnknownProviderError as exc:
                await _append_planning_failure(
                    engine, collection_run_id, provider_name, str(exc), clock.now()
                )
                any_planning_failure = True
                continue
            # `ProviderRegistrationError` (including name drift) is
            # deliberately NOT caught here — it propagates to the whole-run
            # abort handler below; a registry-integrity failure is never
            # treated as an ordinary per-provider planning outcome.

            try:
                query = QueryPlanner.plan(
                    saved_search, registered.capabilities, titles=titles, locations=locations
                )
            except QueryPlanValidationError as exc:
                await _append_planning_failure(
                    engine, collection_run_id, provider_name, str(exc), clock.now()
                )
                any_planning_failure = True
                continue

            if query is None:
                # A legitimate empty selection — no attempt row, no
                # `providers_attempted` entry, no failure (docs/ARCHITECTURE.md
                # §6.6).
                continue

            provider_started_at = clock.now()
            attempt_ids = await _begin_provider_attempt(
                engine, collection_run_id, provider_name, query, provider_started_at
            )
            current_attempt_ids = attempt_ids

            state = ProviderExecutionState()
            for source in query.sources:
                state.per_source_discovered.setdefault(source, 0)
                state.per_source_inserted.setdefault(source, 0)
                state.per_source_updated.setdefault(source, 0)
            current_state = state

            await execute_provider_query(
                engine, registered.provider, query, state, observed_at=observed_at
            )
            # Any exception above propagates to the whole-run abort handler
            # below; `current_attempt_ids`/`current_state` remain bound to
            # this provider's own values, which the abort handler reads.

            provider_completed_at = clock.now()
            await _finalize_provider_success(
                engine, collection_run_id, attempt_ids, state, provider_completed_at
            )
            any_attempt_not_completed = any_attempt_not_completed or any(
                resolve_attempt_status(stat) != "completed" for stat in state.source_stats.values()
            )
            run_had_parse_error = run_had_parse_error or state.had_parse_error
            run_had_conflict = run_had_conflict or state.had_conflict

            # This provider is now fully finalized — no longer "in flight,"
            # so a later provider's abort must not re-touch its rows.
            current_attempt_ids = None
            current_state = None

        completed_at = clock.now()
        duration_ms = int((completed_at - run_started_at).total_seconds() * 1000)
        status = (
            "completed_with_errors"
            if (
                any_planning_failure
                or run_had_parse_error
                or run_had_conflict
                or any_attempt_not_completed
            )
            else "completed"
        )
        async with AsyncSession(bind=engine) as session, session.begin():
            await session.execute(
                update(CollectionRun)
                .where(CollectionRun.id == collection_run_id)
                .values(status=status, completed_at=completed_at, duration_ms=duration_ms)
            )
        logger.info(
            "ingestion_run_completed run_id=%s status=%s",
            collection_run_id,
            status,
        )
        return collection_run_id

    except (Exception, asyncio.CancelledError) as run_exc:
        failed_at = clock.now()
        duration_ms = int((failed_at - run_started_at).total_seconds() * 1000)
        logger.error(
            "ingestion_run_failed run_id=%s exception_type=%s",
            collection_run_id,
            type(run_exc).__name__,
        )
        with suppress(Exception, asyncio.CancelledError):
            if current_attempt_ids is not None and current_state is not None:
                await _finalize_provider_aborted(
                    engine, collection_run_id, current_attempt_ids, current_state, failed_at
                )
            async with AsyncSession(bind=engine) as session, session.begin():
                totals = await session.execute(
                    select(
                        func.coalesce(func.sum(CollectionRunProviderAttempt.jobs_discovered), 0),
                        func.coalesce(func.sum(CollectionRunProviderAttempt.jobs_inserted), 0),
                        func.coalesce(func.sum(CollectionRunProviderAttempt.jobs_updated), 0),
                    ).where(CollectionRunProviderAttempt.collection_run_id == collection_run_id)
                )
                sum_discovered, sum_inserted, sum_updated = totals.one()
                await session.execute(
                    update(CollectionRun)
                    .where(CollectionRun.id == collection_run_id)
                    .values(
                        status="failed",
                        completed_at=failed_at,
                        duration_ms=duration_ms,
                        jobs_discovered=sum_discovered,
                        jobs_inserted=sum_inserted,
                        jobs_updated=sum_updated,
                    )
                )
        raise
