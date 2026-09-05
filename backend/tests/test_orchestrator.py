import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    CollectionRun,
    CollectionRunProviderAttempt,
    SavedSearch,
    SavedSearchTitle,
)
from app.ingestion import orchestrator, provider_execution
from app.ingestion.clock import FixedClock
from app.ingestion.orchestrator import (
    DuplicateEnabledProviderError,
    InactiveSavedSearchError,
    MalformedEnabledProviderError,
    SavedSearchNotFoundError,
    run_saved_search,
)
from app.providers.registry import ProviderRegistrationError, ProviderRegistry
from app.schemas.discovered_job import (
    DiscoveredJob,
    DiscoveryResult,
    ProviderError,
    ProviderErrorCategory,
    SourceRunStats,
)
from app.schemas.provider import (
    ProviderCapabilities,
    ProviderHealth,
    SourceCapabilities,
    SourceQuery,
)
from tests.conftest import real_committed_user_and_saved_search
from tests.support.configurable_provider import ConfigurableProvider
from tests.test_ingestion_pipeline import _cleanup, _load_fixture


def _job(
    provider: str, source: str, *, source_job_id: str, discovered_at: datetime
) -> DiscoveredJob:
    """Builds a distinct posting from the shared `clean_tenant_scoped` base
    fixture. `canonical_url`/`source_url`/`apply_url` are also overridden
    (keyed by `source_job_id`) — otherwise every job built from this one
    base fixture would share the same canonical URL, and Tier 2
    cross-occurrence attachment (out of this slice's scope entirely) would
    silently attach a "second" job to the first one's existing Job instead
    of inserting a genuinely new one, corrupting these tests' own
    insert/update counter assertions."""
    base = _load_fixture("clean_tenant_scoped")
    url = f"https://acme.example.com/jobs/{source_job_id}"
    return base.model_copy(
        update={
            "provider": provider,
            "source": source,
            "source_job_id": source_job_id,
            "requisition_id_raw": source_job_id,
            "discovered_at": discovered_at,
            "source_url": url,
            "canonical_url": url,
            "apply_url": f"{url}/apply",
        }
    )


def _capabilities(provider: str, source: str, **source_kwargs: object) -> ProviderCapabilities:
    defaults: dict[str, object] = {"source": source, "max_concurrency": 1}
    defaults.update(source_kwargs)
    return ProviderCapabilities(provider=provider, sources={source: SourceCapabilities(**defaults)})  # type: ignore[arg-type]


def _result(
    provider: str,
    source: str,
    jobs: list[DiscoveredJob],
    *,
    completed: bool = True,
    jobs_found: int | None = None,
    incomplete_results: bool = False,
    errors: list[ProviderError] | None = None,
    at: datetime,
) -> DiscoveryResult:
    stats = [
        SourceRunStats(
            source=source,
            completed=completed,
            jobs_found=len(jobs) if jobs_found is None else jobs_found,
            incomplete_results=incomplete_results,
        )
    ]
    return DiscoveryResult(
        provider=provider,
        jobs=jobs,
        source_stats=stats,
        errors=errors or [],
        started_at=at,
        completed_at=at,
    )


async def _cleanup_ids_for(
    engine: AsyncEngine, source_job_id: str | None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Resolves the `Job.id` and `RawJobIngestion.id` a successfully
    persisted posting produced, for test cleanup tracking. Every test that
    lets a posting reach `persist_posting()` must capture both ids via this
    helper — otherwise the disposable test database silently accumulates
    leaked `raw_job_ingestions`/`jobs` rows across test runs, corrupting a
    later, unrelated test's own row-count assertions (the exact defect
    class this helper exists to prevent)."""
    assert source_job_id is not None
    from app.db.models import JobOccurrence, RawJobIngestion

    async with AsyncSession(bind=engine) as session:
        occurrence = (
            await session.execute(
                select(JobOccurrence).where(JobOccurrence.source_job_id == source_job_id)
            )
        ).scalar_one()
        raw = (
            await session.execute(
                select(RawJobIngestion).where(RawJobIngestion.source_identifier == source_job_id)
            )
        ).scalar_one()
        return occurrence.job_id, raw.id


async def _collection_run(engine: AsyncEngine, run_id: uuid.UUID) -> CollectionRun:
    async with AsyncSession(bind=engine) as session:
        result = await session.get(CollectionRun, run_id)
        assert result is not None
        return result


async def _attempts(engine: AsyncEngine, run_id: uuid.UUID) -> list[CollectionRunProviderAttempt]:
    async with AsyncSession(bind=engine) as session:
        rows = await session.execute(
            select(CollectionRunProviderAttempt).where(
                CollectionRunProviderAttempt.collection_run_id == run_id
            )
        )
        return list(rows.scalars().all())


async def _run_count(engine: AsyncEngine, saved_search_id: uuid.UUID) -> int:
    async with AsyncSession(bind=engine) as session:
        result = await session.execute(
            select(func.count())
            .select_from(CollectionRun)
            .where(CollectionRun.saved_search_id == saved_search_id)
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# Happy paths: two providers, empty list, None-skip.
# ---------------------------------------------------------------------------


async def test_two_providers_succeed_in_one_run(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 1, tzinfo=UTC)
    clock = FixedClock(t1)
    job_a = _job("alpha", "source_a", source_job_id="A-1", discovered_at=t1)
    job_b = _job("beta", "source_b", source_job_id="B-1", discovered_at=t1)
    provider_a = ConfigurableProvider(
        "alpha",
        capabilities=_capabilities("alpha", "source_a"),
        result=_result("alpha", "source_a", [job_a], at=t1),
    )
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b], at=t1),
    )
    registry = ProviderRegistry([provider_a, provider_b])

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-two-providers@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            for job in (job_a, job_b):
                job_id, raw_id = await _cleanup_ids_for(db_engine, job.source_job_id)
                job_ids.append(job_id)
                raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed"
            assert run.saved_search_id == saved_search_id
            assert sorted(run.providers_attempted) == ["alpha", "beta"]
            assert run.jobs_discovered == 2
            assert run.jobs_inserted == 2

            attempts = await _attempts(db_engine, run_id)
            assert len(attempts) == 2
            assert {a.status for a in attempts} == {"completed"}
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


async def test_explicit_empty_enabled_providers_completes_with_zero_writes(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 2, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-empty-providers@example.com", enabled_providers=[]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed"
            assert run.providers_attempted == []
            assert run.jobs_discovered == 0
            assert run.failures == []
            attempts = await _attempts(db_engine, run_id)
            assert attempts == []
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


async def test_query_planner_none_result_is_silently_skipped(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 3, tzinfo=UTC)
    clock = FixedClock(t1)
    job_b = _job("beta", "source_b", source_job_id="B-2", discovered_at=t1)
    provider_a = ConfigurableProvider("alpha", capabilities=_capabilities("alpha", "source_a"))
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b], at=t1),
    )
    registry = ProviderRegistry([provider_a, provider_b])

    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine,
        "orch-none-skip@example.com",
        enabled_providers=["alpha", "beta"],
        enabled_sources={"alpha": []},
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            job_id, raw_id = await _cleanup_ids_for(db_engine, job_b.source_job_id)
            job_ids.append(job_id)
            raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed"
            assert run.providers_attempted == ["beta"]
            assert run.failures == []
            assert provider_a.discover_call_count == 0
            assert provider_b.discover_call_count == 1
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


# ---------------------------------------------------------------------------
# Pre-write validation: malformed slug, inactive, duplicate, unknown-name.
# ---------------------------------------------------------------------------


async def test_malformed_enabled_provider_slug_zero_writes(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 4, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    async with real_committed_user_and_saved_search(
        db_engine, "orch-malformed-slug@example.com", enabled_providers=["Not-A-Valid-Slug"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(MalformedEnabledProviderError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )
            assert await _run_count(db_engine, saved_search_id) == 0
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=[],
                raw_ingestion_ids=[],
            )


async def test_non_string_enabled_provider_element_zero_writes(db_engine: AsyncEngine) -> None:
    """`enabled_providers` is a plain `text[]` with no CHECK constraining its
    elements, so a `None` element is possible through the database even
    though no current caller can produce one. `is_canonical_slug()` assumes
    `str` and would otherwise raise a raw `TypeError` — this must instead
    fail closed the same way a malformed string does."""
    t1 = datetime(2026, 4, 4, 12, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    async with real_committed_user_and_saved_search(
        db_engine, "orch-non-string-provider@example.com", enabled_providers=["alpha", None]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(MalformedEnabledProviderError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )
            assert await _run_count(db_engine, saved_search_id) == 0
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=[],
                raw_ingestion_ids=[],
            )


async def test_inactive_saved_search_zero_writes(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 5, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    async with real_committed_user_and_saved_search(
        db_engine, "orch-inactive@example.com", is_active=False
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(InactiveSavedSearchError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )
            assert await _run_count(db_engine, saved_search_id) == 0
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=[],
                raw_ingestion_ids=[],
            )


async def test_duplicate_enabled_providers_zero_writes(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 6, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    async with real_committed_user_and_saved_search(
        db_engine, "orch-duplicate@example.com", enabled_providers=["alpha", "alpha"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(DuplicateEnabledProviderError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )
            assert await _run_count(db_engine, saved_search_id) == 0
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=[],
                raw_ingestion_ids=[],
            )


async def test_saved_search_not_found_zero_writes(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 7, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    missing_id = uuid.uuid4()
    with pytest.raises(SavedSearchNotFoundError):
        await run_saved_search(db_engine, missing_id, registry, clock=clock, observed_at=t1)
    assert await _run_count(db_engine, missing_id) == 0


# ---------------------------------------------------------------------------
# Planning failures: sibling-continuing.
# ---------------------------------------------------------------------------


async def test_planning_failure_unknown_provider_plus_successful_sibling(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 8, tzinfo=UTC)
    clock = FixedClock(t1)
    job_b = _job("beta", "source_b", source_job_id="B-3", discovered_at=t1)
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b], at=t1),
    )
    registry = ProviderRegistry([provider_b])

    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-unknown-provider@example.com", enabled_providers=["ghost", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            job_id, raw_id = await _cleanup_ids_for(db_engine, job_b.source_job_id)
            job_ids.append(job_id)
            raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed_with_errors"
            assert run.providers_attempted == ["beta"]
            assert len(run.failures) == 1
            failure = cast(dict[str, object], run.failures[0])
            assert failure["provider"] == "ghost"
            assert failure["source"] is None
            assert cast(dict[str, object], failure["error"])["category"] == "unknown"
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


async def test_graceful_provider_error_plus_successful_sibling(db_engine: AsyncEngine) -> None:
    """A graceful, non-raising `DiscoveryResult` reporting `completed=False`
    and a real `ProviderError` for one provider is not an exception at all —
    it must never abort the run, and a sibling provider must still succeed
    normally, exactly as `pipeline.run()`'s own single-provider graceful
    handling already proves, now composed across two providers."""
    t1 = datetime(2026, 4, 8, 12, tzinfo=UTC)
    clock = FixedClock(t1)
    job_b = _job("beta", "source_b", source_job_id="B-9", discovered_at=t1)
    failing_result = DiscoveryResult(
        provider="alpha",
        jobs=[],
        source_stats=[SourceRunStats(source="source_a", completed=False, jobs_found=0)],
        errors=[
            ProviderError(
                source="source_a",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                detail="simulated upstream timeout",
                occurred_at=t1,
            )
        ],
        started_at=t1,
        completed_at=t1,
    )
    provider_a = ConfigurableProvider(
        "alpha", capabilities=_capabilities("alpha", "source_a"), result=failing_result
    )
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b], at=t1),
    )
    registry = ProviderRegistry([provider_a, provider_b])

    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-graceful-error@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            job_id, raw_id = await _cleanup_ids_for(db_engine, job_b.source_job_id)
            job_ids.append(job_id)
            raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed_with_errors"
            assert sorted(run.providers_attempted) == ["alpha", "beta"]
            assert len(run.failures) == 1
            failure = cast(dict[str, object], run.failures[0])
            assert failure["provider"] == "alpha"
            assert failure["source"] == "source_a"
            assert cast(dict[str, object], failure["error"])["category"] == "timeout"

            attempts = await _attempts(db_engine, run_id)
            alpha_attempt = next(a for a in attempts if a.provider == "alpha")
            beta_attempt = next(a for a in attempts if a.provider == "beta")
            assert alpha_attempt.status == "failed"
            assert beta_attempt.status == "completed"
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


async def test_all_planning_failures_completed_with_errors(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 9, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine,
        "orch-all-planning-failed@example.com",
        enabled_providers=["ghost-one", "ghost-two"],
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed_with_errors"
            assert run.providers_attempted == []
            assert len(run.failures) == 2
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


async def test_all_none_skipped_completes_cleanly(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 10, tzinfo=UTC)
    clock = FixedClock(t1)
    provider_a = ConfigurableProvider("alpha", capabilities=_capabilities("alpha", "source_a"))
    provider_b = ConfigurableProvider("beta", capabilities=_capabilities("beta", "source_b"))
    registry = ProviderRegistry([provider_a, provider_b])
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine,
        "orch-all-none-skip@example.com",
        enabled_providers=["alpha", "beta"],
        enabled_sources={"alpha": [], "beta": []},
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed"
            assert run.providers_attempted == []
            assert run.failures == []
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


# ---------------------------------------------------------------------------
# Whole-run abort: registry drift, discover() exception, malformed result.
# ---------------------------------------------------------------------------


async def test_provider_registry_name_drift_aborts_whole_run(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 11, tzinfo=UTC)
    clock = FixedClock(t1)

    class _DriftingProvider:
        def __init__(self, name: str) -> None:
            self.name = name
            self._capabilities = _capabilities(name, "source_a")

        def capabilities(self) -> ProviderCapabilities:
            return self._capabilities

        async def discover(
            self, query: SourceQuery
        ) -> DiscoveryResult:  # pragma: no cover - never reached
            raise AssertionError("discover() must never be called for a drifted provider")

        async def health(self) -> ProviderHealth:  # pragma: no cover - unused
            raise NotImplementedError

    drifting = _DriftingProvider("alpha")
    registry = ProviderRegistry([drifting])
    drifting.name = "beta"  # drift after registration

    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-registry-drift@example.com", enabled_providers=["alpha"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(ProviderRegistrationError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )

            async with AsyncSession(bind=db_engine) as session:
                runs = (
                    (
                        await session.execute(
                            select(CollectionRun).where(
                                CollectionRun.saved_search_id == saved_search_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            collection_run_ids.extend(run.id for run in runs)
            assert len(runs) == 1
            run = runs[0]
            assert run.status == "failed"
            assert run.providers_attempted == []
            attempts = await _attempts(db_engine, run.id)
            assert attempts == []
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


async def test_unexpected_discover_exception_aborts_whole_run_no_sibling(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 12, tzinfo=UTC)
    clock = FixedClock(t1)
    provider_a = ConfigurableProvider(
        "alpha",
        capabilities=_capabilities("alpha", "source_a"),
        raise_on_discover=RuntimeError("boom"),
    )
    provider_b = ConfigurableProvider("beta", capabilities=_capabilities("beta", "source_b"))
    registry = ProviderRegistry([provider_a, provider_b])

    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-discover-raises@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(RuntimeError, match="boom"):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )

            async with AsyncSession(bind=db_engine) as session:
                runs = (
                    (
                        await session.execute(
                            select(CollectionRun).where(
                                CollectionRun.saved_search_id == saved_search_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            collection_run_ids.extend(run.id for run in runs)
            assert len(runs) == 1
            run = runs[0]
            assert run.status == "failed"
            assert provider_b.discover_call_count == 0

            attempts = await _attempts(db_engine, run.id)
            assert len(attempts) == 1
            assert attempts[0].status == "failed"
            assert attempts[0].error_category == "unknown"
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


async def test_malformed_discovery_result_aborts_whole_run_no_sibling(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 13, tzinfo=UTC)
    clock = FixedClock(t1)
    job_a = _job("alpha", "source_a", source_job_id="A-4", discovered_at=t1)
    malformed = _result("wrong_provider_name", "source_a", [job_a], at=t1)
    provider_a = ConfigurableProvider(
        "alpha", capabilities=_capabilities("alpha", "source_a"), result=malformed
    )
    provider_b = ConfigurableProvider("beta", capabilities=_capabilities("beta", "source_b"))
    registry = ProviderRegistry([provider_a, provider_b])

    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-malformed-result@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(provider_execution.UnsupportedDiscoveryResultError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )

            async with AsyncSession(bind=db_engine) as session:
                runs = (
                    (
                        await session.execute(
                            select(CollectionRun).where(
                                CollectionRun.saved_search_id == saved_search_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            collection_run_ids.extend(run.id for run in runs)
            run = runs[0]
            assert run.status == "failed"
            assert provider_b.discover_call_count == 0
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


async def test_cancellation_mid_provider_aborts_whole_run(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 14, tzinfo=UTC)
    clock = FixedClock(t1)
    provider_a = ConfigurableProvider(
        "alpha",
        capabilities=_capabilities("alpha", "source_a"),
        raise_on_discover=asyncio.CancelledError(),
    )
    provider_b = ConfigurableProvider("beta", capabilities=_capabilities("beta", "source_b"))
    registry = ProviderRegistry([provider_a, provider_b])

    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-cancellation@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(asyncio.CancelledError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )

            async with AsyncSession(bind=db_engine) as session:
                runs = (
                    (
                        await session.execute(
                            select(CollectionRun).where(
                                CollectionRun.saved_search_id == saved_search_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            collection_run_ids.extend(run.id for run in runs)
            run = runs[0]
            assert run.status == "failed"
            assert provider_b.discover_call_count == 0
            attempts = await _attempts(db_engine, run.id)
            assert all(a.status != "running" for a in attempts)
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


# ---------------------------------------------------------------------------
# Transaction-boundary regressions: cancellation delivered after a
# durable commit but before the awaiting caller's next line runs.
# ---------------------------------------------------------------------------


async def test_cancellation_after_begin_attempt_commit_leaves_no_row_running(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates cancellation delivered after `_begin_provider_attempt()`'s
    transaction has already committed (attempt row + `providers_attempted`
    durable) but before its `await` returns control to `run_saved_search()`
    — the exact window that previously left `current_attempt_ids` unset
    while a real `status='running'` row already existed, permanently. Wraps
    the real helper (letting it genuinely commit) and then raises
    `CancelledError`, proving the abort handler still discovers and
    finalizes the row via `_fetch_running_attempts`, never leaving it
    permanently `running`."""
    t1 = datetime(2026, 4, 22, tzinfo=UTC)
    clock = FixedClock(t1)
    provider_a = ConfigurableProvider("alpha", capabilities=_capabilities("alpha", "source_a"))
    registry = ProviderRegistry([provider_a])

    real_begin = orchestrator._begin_provider_attempt

    async def _begin_then_cancel(*args: object, **kwargs: object) -> dict[str, uuid.UUID]:
        await real_begin(*args, **kwargs)  # type: ignore[arg-type]
        raise asyncio.CancelledError()

    monkeypatch.setattr(orchestrator, "_begin_provider_attempt", _begin_then_cancel)

    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-cancel-after-begin-commit@example.com", enabled_providers=["alpha"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(asyncio.CancelledError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )

            async with AsyncSession(bind=db_engine) as session:
                runs = (
                    (
                        await session.execute(
                            select(CollectionRun).where(
                                CollectionRun.saved_search_id == saved_search_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            collection_run_ids.extend(run.id for run in runs)

            assert len(runs) == 1
            run = runs[0]
            assert run.status == "failed"
            # _begin_provider_attempt's own transaction genuinely committed
            # before the simulated cancellation:
            assert run.providers_attempted == ["alpha"]

            attempts = await _attempts(db_engine, run.id)
            assert len(attempts) == 1
            assert attempts[0].status == "failed"  # not stuck at 'running'
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=[],
            )


async def test_cancellation_after_success_finalization_commit_does_not_duplicate_or_overwrite(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates cancellation delivered after `_finalize_provider_success()`'s
    transaction has already committed (attempt row terminal, counters
    incremented, `failures` merged) but before its `await` returns control
    to `run_saved_search()` — the exact window that previously let the
    abort handler re-run against an already-finalized provider, appending
    its `ProviderError` a second time and overwriting its completed attempt
    back to `'failed'`. Wraps the real finalizer (letting it genuinely
    commit) and then raises `CancelledError` — proves alpha's one error
    remains exactly one error, its completed attempt stays completed, its
    counters remain exactly what `_finalize_provider_success` committed,
    and the parent run still ends `'failed'` because orchestration itself
    was cancelled (beta is never reached)."""
    t1 = datetime(2026, 4, 23, tzinfo=UTC)
    clock = FixedClock(t1)
    job_a = _job("alpha", "source_a", source_job_id="A-10", discovered_at=t1)
    result_with_error = DiscoveryResult(
        provider="alpha",
        jobs=[job_a],
        source_stats=[SourceRunStats(source="source_a", completed=True, jobs_found=1)],
        errors=[
            ProviderError(
                source="source_a",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                detail="transient timeout, retried successfully",
                occurred_at=t1,
            )
        ],
        started_at=t1,
        completed_at=t1,
    )
    provider_a = ConfigurableProvider(
        "alpha", capabilities=_capabilities("alpha", "source_a"), result=result_with_error
    )
    provider_b = ConfigurableProvider("beta", capabilities=_capabilities("beta", "source_b"))
    registry = ProviderRegistry([provider_a, provider_b])

    real_finalize = orchestrator._finalize_provider_success

    async def _finalize_then_cancel(*args: object, **kwargs: object) -> None:
        await real_finalize(*args, **kwargs)  # type: ignore[arg-type]
        raise asyncio.CancelledError()

    monkeypatch.setattr(orchestrator, "_finalize_provider_success", _finalize_then_cancel)

    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine,
        "orch-cancel-after-success-commit@example.com",
        enabled_providers=["alpha", "beta"],
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(asyncio.CancelledError):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )

            async with AsyncSession(bind=db_engine) as session:
                runs = (
                    (
                        await session.execute(
                            select(CollectionRun).where(
                                CollectionRun.saved_search_id == saved_search_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            collection_run_ids.extend(run.id for run in runs)
            job_id, raw_id = await _cleanup_ids_for(db_engine, job_a.source_job_id)
            job_ids.append(job_id)
            raw_ingestion_ids.append(raw_id)

            assert len(runs) == 1
            run = runs[0]
            assert run.status == "failed"  # orchestration itself was cancelled
            assert len(run.failures) == 1  # alpha's one error, never duplicated
            assert provider_b.discover_call_count == 0  # beta never reached

            attempts = await _attempts(db_engine, run.id)
            assert len(attempts) == 1
            assert attempts[0].provider == "alpha"
            assert attempts[0].status == "completed"  # never overwritten to 'failed'

            sum_discovered = sum(a.jobs_discovered for a in attempts)
            sum_inserted = sum(a.jobs_inserted for a in attempts)
            sum_updated = sum(a.jobs_updated for a in attempts)
            assert run.jobs_discovered == sum_discovered == 1
            assert run.jobs_inserted == sum_inserted == 1
            assert run.jobs_updated == sum_updated == 0
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


# ---------------------------------------------------------------------------
# A ProviderError on a completed=True source must still force
# completed_with_errors, not just a non-completed attempt.
# ---------------------------------------------------------------------------


async def test_provider_error_on_completed_source_forces_completed_with_errors(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 24, tzinfo=UTC)
    clock = FixedClock(t1)
    job_a = _job("alpha", "source_a", source_job_id="A-11", discovered_at=t1)
    job_b = _job("beta", "source_b", source_job_id="B-11", discovered_at=t1)
    result_with_error = DiscoveryResult(
        provider="alpha",
        jobs=[job_a],
        source_stats=[
            SourceRunStats(
                source="source_a", completed=True, jobs_found=1, incomplete_results=False
            )
        ],
        errors=[
            ProviderError(
                source="source_a",
                category=ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                detail="rate limited but retried successfully",
                occurred_at=t1,
            )
        ],
        started_at=t1,
        completed_at=t1,
    )
    provider_a = ConfigurableProvider(
        "alpha", capabilities=_capabilities("alpha", "source_a"), result=result_with_error
    )
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b], at=t1),
    )
    registry = ProviderRegistry([provider_a, provider_b])

    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-error-on-completed@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            for job in (job_a, job_b):
                job_id, raw_id = await _cleanup_ids_for(db_engine, job.source_job_id)
                job_ids.append(job_id)
                raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed_with_errors"
            assert len(run.failures) == 1
            failure = cast(dict[str, object], run.failures[0])
            assert failure["provider"] == "alpha"
            assert failure["source"] == "source_a"

            attempts = await _attempts(db_engine, run_id)
            alpha_attempt = next(a for a in attempts if a.provider == "alpha")
            beta_attempt = next(a for a in attempts if a.provider == "beta")
            assert alpha_attempt.status == "completed"
            assert alpha_attempt.error_category == "rate_limited"
            assert beta_attempt.status == "completed"
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


# ---------------------------------------------------------------------------
# Partial progress: exact-once counters, SQL-SUM reconciliation, no double
# counting, provider 1's totals survive provider 2's failure.
# ---------------------------------------------------------------------------


async def test_persistence_exception_after_partial_progress_preserves_exact_counters(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    t1 = datetime(2026, 4, 15, tzinfo=UTC)
    clock = FixedClock(t1)

    job_a = _job("alpha", "source_a", source_job_id="A-5", discovered_at=t1)
    job_b1 = _job("beta", "source_b", source_job_id="B-5", discovered_at=t1)
    job_b2 = _job("beta", "source_b", source_job_id="B-6", discovered_at=t1)

    provider_a = ConfigurableProvider(
        "alpha",
        capabilities=_capabilities("alpha", "source_a"),
        result=_result("alpha", "source_a", [job_a], at=t1),
    )
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b1, job_b2], at=t1),
    )
    registry = ProviderRegistry([provider_a, provider_b])

    original_persist = provider_execution.persist_posting
    call_count = 0

    async def _fail_on_second_posting(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count == 3:  # 1st call is provider alpha's only posting; 2nd/3rd are beta's two
            raise RuntimeError("simulated persistence failure SECRET_VALUE")
        return await original_persist(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(provider_execution, "persist_posting", _fail_on_second_posting)

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-partial-progress@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            with pytest.raises(RuntimeError, match="simulated persistence failure"):
                await run_saved_search(
                    db_engine, saved_search_id, registry, clock=clock, observed_at=t1
                )

            # Every cleanup ID is captured first, before any assertion that
            # could fail — a fallible assertion below must never leave a
            # row uncaptured for cleanup.
            async with AsyncSession(bind=db_engine) as session:
                runs = (
                    (
                        await session.execute(
                            select(CollectionRun).where(
                                CollectionRun.saved_search_id == saved_search_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            collection_run_ids.extend(run.id for run in runs)

            async with AsyncSession(bind=db_engine) as session:
                from app.db.models import JobOccurrence

                occurrences = (
                    (
                        await session.execute(
                            select(JobOccurrence).where(
                                JobOccurrence.source_job_id.in_(
                                    [job_a.source_job_id, job_b1.source_job_id]
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            job_ids.extend(occurrence.job_id for occurrence in occurrences)

            async with AsyncSession(bind=db_engine) as session:
                from app.db.models import RawJobIngestion

                raws = (
                    (
                        await session.execute(
                            select(RawJobIngestion.id).where(
                                RawJobIngestion.source_identifier.in_(
                                    [
                                        job_a.source_job_id,
                                        job_b1.source_job_id,
                                        job_b2.source_job_id,
                                    ]
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                raw_ingestion_ids.extend(raws)

            # Assertions follow — every ID above already tracked, so a
            # failure here still leaves nothing behind in the shared
            # disposable test database.
            assert len(runs) == 1
            run = runs[0]
            assert run.status == "failed"

            attempts = await _attempts(db_engine, run.id)
            assert len(attempts) == 2
            alpha_attempt = next(a for a in attempts if a.provider == "alpha")
            beta_attempt = next(a for a in attempts if a.provider == "beta")
            assert alpha_attempt.status == "completed"
            assert alpha_attempt.jobs_discovered == 1
            assert alpha_attempt.jobs_inserted == 1
            assert beta_attempt.status == "failed"
            assert beta_attempt.jobs_discovered == 2
            assert (
                beta_attempt.jobs_inserted == 1
            )  # only the first of beta's two postings persisted

            # The regression: CollectionRun's absolute rollup must equal
            # SUM(attempt rows) exactly, with no loss or double-counting —
            # never derived from a parallel Python running total.
            sum_discovered = sum(a.jobs_discovered for a in attempts)
            sum_inserted = sum(a.jobs_inserted for a in attempts)
            sum_updated = sum(a.jobs_updated for a in attempts)
            assert run.jobs_discovered == sum_discovered == 3
            assert run.jobs_inserted == sum_inserted == 2
            assert run.jobs_updated == sum_updated == 0
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


# ---------------------------------------------------------------------------
# Parse error / identity conflict force completed_with_errors independently
# of any ProviderError.
# ---------------------------------------------------------------------------


async def test_parse_error_forces_completed_with_errors_without_provider_error(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 16, tzinfo=UTC)
    clock = FixedClock(t1)
    unkeyable = _load_fixture("unprocessable").model_copy(
        update={"provider": "alpha", "source": "source_a", "discovered_at": t1}
    )
    provider_a = ConfigurableProvider(
        "alpha",
        capabilities=_capabilities("alpha", "source_a"),
        result=_result("alpha", "source_a", [unkeyable], at=t1),
    )
    registry = ProviderRegistry([provider_a])

    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-parse-error@example.com", enabled_providers=["alpha"]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            async with AsyncSession(bind=db_engine) as session:
                from app.db.models import RawJobIngestion

                raw = (
                    (
                        await session.execute(
                            select(RawJobIngestion).where(
                                RawJobIngestion.provider == "alpha",
                                RawJobIngestion.source == "source_a",
                                RawJobIngestion.processing_status == "parse_error",
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
            if raw is not None:
                raw_ingestion_ids.append(raw.id)

            run = await _collection_run(db_engine, run_id)
            assert run.status == "completed_with_errors"
            assert run.failures == []
            assert raw is not None
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


# ---------------------------------------------------------------------------
# local_enforcement determinism and providers_enforced_locally nesting.
# ---------------------------------------------------------------------------


async def test_providers_enforced_locally_is_deterministic_sorted_json(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 17, tzinfo=UTC)
    clock = FixedClock(t1)
    job_a = _job("alpha", "source_a", source_job_id="A-7", discovered_at=t1)
    job_b = _job("beta", "source_b", source_job_id="B-7", discovered_at=t1)
    # Neither source supports any of the populated filters, so every
    # populated field for each source lands in local_enforcement.
    provider_a = ConfigurableProvider(
        "alpha",
        capabilities=_capabilities("alpha", "source_a"),
        result=_result("alpha", "source_a", [job_a], at=t1),
    )
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b], at=t1),
    )
    registry = ProviderRegistry([provider_a, provider_b])

    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine,
        "orch-enforced-locally@example.com",
        enabled_providers=["alpha", "beta"],
        salary_floor=100_000,
        employment_types=["full_time"],
        seniority=["senior"],
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            for job in (job_a, job_b):
                job_id, raw_id = await _cleanup_ids_for(db_engine, job.source_job_id)
                job_ids.append(job_id)
                raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            enforced = cast(dict[str, dict[str, list[str]]], run.providers_enforced_locally)
            assert set(enforced.keys()) == {"alpha", "beta"}
            for provider_entry in enforced.values():
                fields = (
                    provider_entry["source_a"]
                    if "source_a" in provider_entry
                    else provider_entry["source_b"]
                )
                assert fields == sorted(fields)
                assert "salary_floor" in fields
                assert "employment_types" in fields
                assert "seniority" in fields
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


# ---------------------------------------------------------------------------
# Timestamps: per-provider attempt started_at strictly increasing, never
# inherited from an earlier provider or the run itself.
# ---------------------------------------------------------------------------


async def test_per_provider_attempt_timestamps_are_distinct_and_ordered(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 4, 18, tzinfo=UTC)
    clock = FixedClock(t1)
    job_a = _job("alpha", "source_a", source_job_id="A-8", discovered_at=t1)
    job_b = _job("beta", "source_b", source_job_id="B-8", discovered_at=t1)

    def _advance() -> None:
        clock.advance(1)

    provider_a = ConfigurableProvider(
        "alpha",
        capabilities=_capabilities("alpha", "source_a"),
        result=_result("alpha", "source_a", [job_a], at=t1),
        on_discover=_advance,
    )
    provider_b = ConfigurableProvider(
        "beta",
        capabilities=_capabilities("beta", "source_b"),
        result=_result("beta", "source_b", [job_b], at=t1),
        on_discover=_advance,
    )
    registry = ProviderRegistry([provider_a, provider_b])

    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    async with real_committed_user_and_saved_search(
        db_engine, "orch-timestamps@example.com", enabled_providers=["alpha", "beta"]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            for job in (job_a, job_b):
                job_id, raw_id = await _cleanup_ids_for(db_engine, job.source_job_id)
                job_ids.append(job_id)
                raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            attempts = await _attempts(db_engine, run_id)
            alpha_attempt = next(a for a in attempts if a.provider == "alpha")
            beta_attempt = next(a for a in attempts if a.provider == "beta")

            assert alpha_attempt.started_at == run.started_at
            assert beta_attempt.started_at > alpha_attempt.started_at
            assert alpha_attempt.completed_at is not None
            assert beta_attempt.completed_at is not None
            assert alpha_attempt.completed_at <= beta_attempt.started_at
            assert run.completed_at is not None
            assert run.completed_at >= beta_attempt.completed_at
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


# ---------------------------------------------------------------------------
# Deterministic provider processing order and child (title/location)
# ordering — never insertion order.
# ---------------------------------------------------------------------------


async def test_deterministic_provider_processing_order(db_engine: AsyncEngine) -> None:
    t1 = datetime(2026, 4, 19, tzinfo=UTC)
    clock = FixedClock(t1)

    def _providers() -> (
        tuple[ConfigurableProvider, ConfigurableProvider, DiscoveredJob, DiscoveredJob]
    ):
        job_z = _job("zeta", "source_z", source_job_id=f"Z-{uuid.uuid4()}", discovered_at=t1)
        job_a = _job("alpha", "source_a", source_job_id=f"A-{uuid.uuid4()}", discovered_at=t1)
        zeta = ConfigurableProvider(
            "zeta",
            capabilities=_capabilities("zeta", "source_z"),
            result=_result("zeta", "source_z", [job_z], at=t1),
        )
        alpha = ConfigurableProvider(
            "alpha",
            capabilities=_capabilities("alpha", "source_a"),
            result=_result("alpha", "source_a", [job_a], at=t1),
        )
        return zeta, alpha, job_z, job_a

    # Explicit list — preserved in the array's own given order, never sorted.
    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    zeta, alpha, job_z, job_a = _providers()
    registry_explicit = ProviderRegistry([zeta, alpha])
    async with real_committed_user_and_saved_search(
        db_engine, "orch-order-explicit@example.com", enabled_providers=["zeta", "alpha"]
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry_explicit, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            for job in (job_z, job_a):
                job_id, raw_id = await _cleanup_ids_for(db_engine, job.source_job_id)
                job_ids.append(job_id)
                raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            assert run.providers_attempted == ["zeta", "alpha"]
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )

    # NULL — expands to every registered provider name, alphabetically
    # sorted, never registration order (registered here as [zeta, alpha]).
    job_ids = []
    raw_ingestion_ids = []
    collection_run_ids = []
    zeta2, alpha2, job_z2, job_a2 = _providers()
    registry_null = ProviderRegistry([zeta2, alpha2])
    async with real_committed_user_and_saved_search(
        db_engine, "orch-order-null@example.com", enabled_providers=None
    ) as (_session, user_id, saved_search_id):
        try:
            run_id = await run_saved_search(
                db_engine, saved_search_id, registry_null, clock=clock, observed_at=t1
            )
            collection_run_ids.append(run_id)
            for job in (job_z2, job_a2):
                job_id, raw_id = await _cleanup_ids_for(db_engine, job.source_job_id)
                job_ids.append(job_id)
                raw_ingestion_ids.append(raw_id)

            run = await _collection_run(db_engine, run_id)
            assert run.providers_attempted == ["alpha", "zeta"]
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=job_ids,
                collection_run_ids=collection_run_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )


async def test_deterministic_child_ordering_not_insertion_order(db_engine: AsyncEngine) -> None:
    async with real_committed_user_and_saved_search(
        db_engine, "orch-child-order@example.com", enabled_providers=[]
    ) as (session, user_id, saved_search_id):
        try:
            titles = [
                SavedSearchTitle(saved_search_id=saved_search_id, title=title)
                for title in ["Zebra Engineer", "Apple Engineer", "Mango Engineer"]
            ]
            for title in titles:
                session.add(title)
            await session.commit()
            for title in titles:
                await session.refresh(title)

            # All three share the identical created_at (PostgreSQL's now()
            # is fixed at transaction start, not per-statement) — proving
            # the ordering below comes from the (created_at, id) tie-break,
            # never from insertion sequence.
            assert len({t.created_at for t in titles}) == 1

            expected_order = [t.title for t in sorted(titles, key=lambda t: t.id)]

            result_1 = await session.execute(
                select(SavedSearchTitle.title)
                .where(SavedSearchTitle.saved_search_id == saved_search_id)
                .order_by(SavedSearchTitle.created_at, SavedSearchTitle.id)
            )
            order_1 = [row[0] for row in result_1.all()]
            result_2 = await session.execute(
                select(SavedSearchTitle.title)
                .where(SavedSearchTitle.saved_search_id == saved_search_id)
                .order_by(SavedSearchTitle.created_at, SavedSearchTitle.id)
            )
            order_2 = [row[0] for row in result_2.all()]

            assert order_1 == order_2 == expected_order
        finally:
            await _cleanup(
                db_engine,
                user_ids=[user_id],
                job_ids=[],
                collection_run_ids=[],
                raw_ingestion_ids=[],
            )


# ---------------------------------------------------------------------------
# SavedSearch deletion race: FOR SHARE protects the parent/FK
# initialization only.
# ---------------------------------------------------------------------------


async def test_saved_search_deletion_race_survives_with_saved_search_id_null(
    db_engine: AsyncEngine,
) -> None:
    """Exercises `run_saved_search()` itself — not a copied SQL sequence.
    `_after_saved_search_locked` (a narrow, private, no-op-by-default
    coordination seam `run_saved_search()` calls immediately after its own
    real `FOR SHARE` lock is acquired) starts a genuinely concurrent
    `DELETE` and waits for it to actually reach PostgreSQL and block on
    that real lock, before letting `run_saved_search()`'s own transaction
    proceed to commit. If the real lock were ever removed from production,
    the `DELETE` would instead complete immediately during this window,
    and `run_saved_search()`'s own later `CollectionRun` insert would then
    hit a genuine foreign-key violation against the now-deleted parent row
    — surfacing as an unexpected exception out of `run_saved_search()`
    itself, failing this test loudly, not silently passing."""
    t1 = datetime(2026, 4, 21, tzinfo=UTC)
    clock = FixedClock(t1)
    registry = ProviderRegistry([])
    delete_started = asyncio.Event()

    async with real_committed_user_and_saved_search(
        db_engine, "orch-deletion-race@example.com", enabled_providers=[]
    ) as (_session, user_id, saved_search_id):
        collection_run_id: uuid.UUID | None = None
        deleter_task: asyncio.Task[None] | None = None

        async def _deleter() -> None:
            async with AsyncSession(bind=db_engine) as session, session.begin():
                delete_started.set()
                await session.execute(delete(SavedSearch).where(SavedSearch.id == saved_search_id))

        async def _start_concurrent_delete_and_let_it_block() -> None:
            nonlocal deleter_task
            deleter_task = asyncio.create_task(_deleter())
            await asyncio.wait_for(delete_started.wait(), timeout=5)
            # Scheduling safety margin only — correctness comes from the
            # real FOR SHARE row lock run_saved_search() itself is holding
            # at this point, not this sleep; it only gives the DELETE
            # statement time to actually reach PostgreSQL and start
            # waiting on that lock before this seam returns and
            # run_saved_search()'s own transaction is allowed to commit.
            await asyncio.sleep(0.2)

        try:
            collection_run_id = await asyncio.wait_for(
                run_saved_search(
                    db_engine,
                    saved_search_id,
                    registry,
                    clock=clock,
                    observed_at=t1,
                    _after_saved_search_locked=_start_concurrent_delete_and_let_it_block,
                ),
                timeout=10,
            )
            assert deleter_task is not None
            await asyncio.wait_for(deleter_task, timeout=5)

            async with AsyncSession(bind=db_engine) as session:
                still_saved_search = await session.get(SavedSearch, saved_search_id)
                assert still_saved_search is None  # the delete completed

                run = await session.get(CollectionRun, collection_run_id)
                assert run is not None
                assert run.saved_search_id is None  # ON DELETE SET NULL fired
                assert run.status == "completed"
        finally:
            if deleter_task is not None and not deleter_task.done():
                deleter_task.cancel()
                with suppress(asyncio.CancelledError):
                    await deleter_task
            async with AsyncSession(bind=db_engine) as cleanup_session:
                if collection_run_id is not None:
                    existing_run = await cleanup_session.get(CollectionRun, collection_run_id)
                    if existing_run is not None:
                        await cleanup_session.delete(existing_run)
                        await cleanup_session.commit()
    # `real_committed_user_and_saved_search`'s own cleanup tries to delete
    # the SavedSearch again on exit — harmless, since `_deleter()` already
    # removed it (its own `get()`-then-delete pattern tolerates an
    # already-missing row, matching every other `real_committed_*` helper's
    # documented failure-safe cleanup behavior).
