import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    CollectionRun,
    CollectionRunProviderAttempt,
    Job,
    JobOccurrence,
    RawJobIngestion,
    User,
    UserJob,
)
from app.ingestion import pipeline
from app.ingestion.clock import FixedClock
from app.ingestion.identity import resolve_identity
from app.ingestion.persistence import upsert_job_occurrence
from app.providers.base import DiscoveryProvider
from app.providers.fixture import FixtureProvider
from app.schemas.discovered_job import DiscoveredJob, DiscoveryResult, SourceRunStats
from app.schemas.provider import ProviderCapabilities, ProviderHealth, SourceQuery

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "discovery"


def _load_fixture(name: str) -> DiscoveredJob:
    data = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return DiscoveredJob(**data)


async def _cleanup(
    engine: AsyncEngine,
    *,
    user_ids: list[uuid.UUID],
    job_ids: list[uuid.UUID],
    collection_run_ids: list[uuid.UUID],
    raw_ingestion_ids: list[uuid.UUID],
) -> None:
    """Deletes everything this test created, in FK-safe order.
    `Job` cascades to `JobOccurrence` and `UserJob`; `CollectionRun`
    cascades to `CollectionRunProviderAttempt`. `RawJobIngestion` has no
    cascade pointing at it, so it is deleted explicitly."""
    async with AsyncSession(bind=engine) as session:
        for raw_id in raw_ingestion_ids:
            existing = await session.get(RawJobIngestion, raw_id)
            if existing is not None:
                await session.delete(existing)
        for run_id in collection_run_ids:
            existing_run = await session.get(CollectionRun, run_id)
            if existing_run is not None:
                await session.delete(existing_run)
        for job_id in job_ids:
            existing_job = await session.get(Job, job_id)
            if existing_job is not None:
                await session.delete(existing_job)
        for user_id in user_ids:
            existing_user = await session.get(User, user_id)
            if existing_user is not None:
                await session.delete(existing_user)
        await session.commit()


async def _occurrence_by_job_id(engine: AsyncEngine, source_job_id: str) -> JobOccurrence:
    async with AsyncSession(bind=engine) as session:
        result = await session.execute(
            select(JobOccurrence).where(JobOccurrence.source_job_id == source_job_id)
        )
        occurrence = result.scalar_one()
        # Force attribute access before the session closes.
        _ = (occurrence.id, occurrence.job_id, occurrence.last_seen_at, occurrence.first_seen_at)
        return occurrence


async def _occurrence_by_url(engine: AsyncEngine, source_url_normalized: str) -> JobOccurrence:
    async with AsyncSession(bind=engine) as session:
        result = await session.execute(
            select(JobOccurrence).where(
                JobOccurrence.source_job_id.is_(None),
                JobOccurrence.source_url_normalized == source_url_normalized,
            )
        )
        occurrence = result.scalar_one()
        _ = (occurrence.id, occurrence.job_id, occurrence.last_seen_at, occurrence.first_seen_at)
        return occurrence


async def _job_count(engine: AsyncEngine) -> int:
    async with AsyncSession(bind=engine) as session:
        return (await session.execute(select(func.count()).select_from(Job))).scalar_one()


async def _occurrence_count(engine: AsyncEngine) -> int:
    async with AsyncSession(bind=engine) as session:
        return (await session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()


async def _raw_ingestion_count(engine: AsyncEngine) -> int:
    async with AsyncSession(bind=engine) as session:
        return (
            await session.execute(select(func.count()).select_from(RawJobIngestion))
        ).scalar_one()


async def test_two_run_natural_key_spine(
    db_engine: AsyncEngine,
    make_user: Callable[..., User],
    make_user_job: Callable[..., UserJob],
) -> None:
    """The full approved slice: two `CollectionRun`s, four fixtures in run
    1 (one per natural-key form plus the genuinely unkeyable case), the
    three resolvable fixtures resubmitted byte-identical in run 2, a
    `UserJob` created between the two runs proven untouched afterward."""
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = t1 + timedelta(hours=6)

    job_tenant = _load_fixture("clean_tenant_scoped")
    job_no_tenant = _load_fixture("missing_salary_no_tenant")
    job_url_fallback = _load_fixture("url_fallback_only")
    job_unprocessable = _load_fixture("unprocessable")

    query = SourceQuery(sources=["fixture_ats"])

    user_ids: list[uuid.UUID] = []
    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []

    try:
        # ------------------------------------------------------------------
        # Run 1
        # ------------------------------------------------------------------
        provider_1 = FixtureProvider(
            [job_tenant, job_no_tenant, job_url_fallback, job_unprocessable], called_at=t1
        )
        clock_1 = FixedClock(t1)
        run1_id = await pipeline.run(db_engine, provider_1, query, observed_at=t1, clock=clock_1)
        collection_run_ids.append(run1_id)

        assert await _raw_ingestion_count(db_engine) == 4
        assert await _job_count(db_engine) == 3
        assert await _occurrence_count(db_engine) == 3

        async with AsyncSession(bind=db_engine) as session:
            run1 = await session.get(CollectionRun, run1_id)
            assert run1 is not None
            assert run1.status == "completed_with_errors"
            assert run1.jobs_discovered == 4
            assert run1.jobs_inserted == 3
            assert run1.jobs_updated == 0
            assert run1.failures == []

            attempts_1 = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == run1_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts_1) == 1
            assert attempts_1[0].status == "completed"
            assert attempts_1[0].jobs_discovered == 4
            assert attempts_1[0].jobs_inserted == 3
            assert attempts_1[0].jobs_updated == 0

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)  # captured before any assertion
            assert len(raw_rows) == 4
            by_status = {row.processing_status for row in raw_rows}
            assert by_status == {"normalized", "parse_error"}
            parse_error_rows = [r for r in raw_rows if r.processing_status == "parse_error"]
            assert len(parse_error_rows) == 1
            assert parse_error_rows[0].job_occurrence_id is None
            assert parse_error_rows[0].error_message is not None

        occurrence_tenant = await _occurrence_by_job_id(db_engine, "REQ-1001")
        occurrence_no_tenant = await _occurrence_by_job_id(db_engine, "987654321")
        occurrence_url = await _occurrence_by_url(
            db_engine, "https://gamma.example.com/careers/data-analyst-role"
        )
        # Captured before any assertion on these occurrences, so a later
        # assertion failure still leaves cleanup able to find these rows.
        job_ids.extend(
            [occurrence_tenant.job_id, occurrence_no_tenant.job_id, occurrence_url.job_id]
        )
        assert occurrence_tenant.first_seen_at == t1
        assert occurrence_tenant.last_seen_at == t1

        async with AsyncSession(bind=db_engine) as session:
            job_tenant_row = await session.get(Job, occurrence_tenant.job_id)
            assert job_tenant_row is not None
            assert job_tenant_row.first_seen_at == t1
            assert job_tenant_row.last_seen_at == t1
            job_no_tenant_row = await session.get(Job, occurrence_no_tenant.job_id)
            assert job_no_tenant_row is not None
            assert job_no_tenant_row.salary_min is None
            assert job_no_tenant_row.salary_max is None
            assert job_no_tenant_row.compensation_text is None

        # ------------------------------------------------------------------
        # UserJob created between the two runs
        # ------------------------------------------------------------------
        user = make_user(email="ingestion-spine@example.com")
        async with AsyncSession(bind=db_engine) as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
            user_id = user.id
        user_ids.append(user_id)

        user_job = make_user_job(
            user_id=user_id,
            job_id=occurrence_tenant.job_id,
            status_changed_at=t1,
            status="applied",
            applied_at=t1,
            saved=True,
        )
        async with AsyncSession(bind=db_engine) as session:
            session.add(user_job)
            await session.commit()
            await session.refresh(user_job)
            user_job_snapshot = {
                "status": user_job.status,
                "applied_at": user_job.applied_at,
                "status_changed_at": user_job.status_changed_at,
                "saved": user_job.saved,
                "hidden": user_job.hidden,
                "archived": user_job.archived,
                "updated_at": user_job.updated_at,
            }
            user_job_id = user_job.id

        # ------------------------------------------------------------------
        # Run 2 — byte-identical resubmission of the three resolvable fixtures
        # ------------------------------------------------------------------
        provider_2 = FixtureProvider([job_tenant, job_no_tenant, job_url_fallback], called_at=t2)
        clock_2 = FixedClock(t2)
        run2_id = await pipeline.run(db_engine, provider_2, query, observed_at=t2, clock=clock_2)
        collection_run_ids.append(run2_id)

        assert await _raw_ingestion_count(db_engine) == 7  # 4 + 3
        assert await _job_count(db_engine) == 3  # unchanged — no new Job
        assert await _occurrence_count(db_engine) == 3  # unchanged — no new occurrence

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.status == "completed"
            assert run2.jobs_discovered == 3
            assert run2.jobs_inserted == 0
            assert run2.jobs_updated == 3

            attempts_2 = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == run2_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts_2) == 1
            assert attempts_2[0].status == "completed"
            assert attempts_2[0].jobs_discovered == 3
            assert attempts_2[0].jobs_inserted == 0
            assert attempts_2[0].jobs_updated == 3

            run2_raw_rows = (
                (
                    await session.execute(
                        select(RawJobIngestion).where(RawJobIngestion.fetched_at == t2)
                    )
                )
                .scalars()
                .all()
            )
            raw_ingestion_ids.extend(row.id for row in run2_raw_rows)  # before any assertion
            assert len(run2_raw_rows) == 3
            assert all(row.processing_status == "normalized" for row in run2_raw_rows)

        occurrence_tenant_after = await _occurrence_by_job_id(db_engine, "REQ-1001")
        assert occurrence_tenant_after.id == occurrence_tenant.id  # same row, not a duplicate
        assert occurrence_tenant_after.first_seen_at == t1  # never moves
        assert occurrence_tenant_after.last_seen_at == t2  # advanced forward

        occurrence_no_tenant_after = await _occurrence_by_job_id(db_engine, "987654321")
        assert occurrence_no_tenant_after.id == occurrence_no_tenant.id
        assert occurrence_no_tenant_after.last_seen_at == t2

        occurrence_url_after = await _occurrence_by_url(
            db_engine, "https://gamma.example.com/careers/data-analyst-role"
        )
        assert occurrence_url_after.id == occurrence_url.id
        assert occurrence_url_after.last_seen_at == t2

        async with AsyncSession(bind=db_engine) as session:
            job_tenant_after = await session.get(Job, occurrence_tenant.job_id)
            assert job_tenant_after is not None
            assert job_tenant_after.first_seen_at == t1
            assert job_tenant_after.last_seen_at == t2

        # ------------------------------------------------------------------
        # UserJob must be completely unaffected by run 2
        # ------------------------------------------------------------------
        async with AsyncSession(bind=db_engine) as session:
            reloaded_user_job = await session.get(UserJob, user_job_id)
            assert reloaded_user_job is not None
            assert reloaded_user_job.status == user_job_snapshot["status"]
            assert reloaded_user_job.applied_at == user_job_snapshot["applied_at"]
            assert reloaded_user_job.status_changed_at == user_job_snapshot["status_changed_at"]
            assert reloaded_user_job.saved == user_job_snapshot["saved"]
            assert reloaded_user_job.hidden == user_job_snapshot["hidden"]
            assert reloaded_user_job.archived == user_job_snapshot["archived"]
            # The one column the model's own docstring says advances on any
            # write to this row — the strongest available proof that
            # ingestion never wrote to `user_jobs` at all.
            assert reloaded_user_job.updated_at == user_job_snapshot["updated_at"]
    finally:
        await _cleanup(
            db_engine,
            user_ids=user_ids,
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_reobservation_normalizes_text_fields_identically_to_first_insert(
    db_engine: AsyncEngine,
) -> None:
    """Regression: the "found" (update) branch of `upsert_job_occurrence`
    must apply the exact same `@validates` trim/blank-collapse
    normalization as the "not found" (insert) branch — a Core-style
    `update()` statement would bypass `@validates` entirely and let a
    covered-whitespace-padded value land on re-observation even though the
    identical value would have been trimmed on first insert. Verified two
    ways: the stored value is trimmed exactly like the insert path, and a
    covered-whitespace-*only* value collapses to `NULL` on re-observation
    too, not just on creation."""
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)
    t1 = datetime(2026, 7, 1, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    job_ids: list[uuid.UUID] = []
    try:
        async with AsyncSession(bind=db_engine) as session, session.begin():
            first = await upsert_job_occurrence(session, natural_key, job, t1)
        job_ids.append(first.job_id)

        padded_job = job.model_copy(
            update={
                "title": "  Senior Backend Engineer\t",
                "apply_url": "   \r\n  ",  # covered-whitespace only -> must collapse to None
                "requisition_id_raw": " REQ-1001 ",
            }
        )
        async with AsyncSession(bind=db_engine) as session, session.begin():
            second = await upsert_job_occurrence(session, natural_key, padded_job, t2)
        assert second.inserted is False
        assert second.occurrence_id == first.occurrence_id

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.apply_url is None  # collapsed, not stored as whitespace
            assert occurrence.requisition_id_raw == "REQ-1001"  # trimmed

            job_row = await session.get(Job, first.job_id)
            assert job_row is not None
            assert job_row.title == "Senior Backend Engineer"  # trimmed, matching insert-path rules
    finally:
        async with AsyncSession(bind=db_engine) as session:
            for job_id in job_ids:
                existing = await session.get(Job, job_id)
                if existing is not None:
                    await session.delete(existing)
            await session.commit()


async def test_out_of_order_replay_never_moves_last_seen_at_backward(
    db_engine: AsyncEngine,
) -> None:
    """An observation timestamped *earlier* than the last one already
    recorded must never move `last_seen_at` backward, on either
    `JobOccurrence` or its parent `Job` (docs binding decision, point 6) —
    `GREATEST(existing, incoming)`, not a blind overwrite."""
    t2 = datetime(2026, 6, 1, tzinfo=UTC)
    t0 = t2 - timedelta(days=1)  # older than t2, submitted *after* t2 was already recorded
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)

    job_ids: list[uuid.UUID] = []
    try:
        async with AsyncSession(bind=db_engine) as session, session.begin():
            first = await upsert_job_occurrence(session, natural_key, job, t2)
        job_ids.append(first.job_id)

        async with AsyncSession(bind=db_engine) as session, session.begin():
            replay = await upsert_job_occurrence(session, natural_key, job, t0)
        assert replay.inserted is False
        assert replay.job_id == first.job_id
        assert replay.occurrence_id == first.occurrence_id

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.last_seen_at == t2  # unchanged — t0 < t2, never regresses
            job_row = await session.get(Job, first.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t2
    finally:
        async with AsyncSession(bind=db_engine) as session:
            for job_id in job_ids:
                existing = await session.get(Job, job_id)
                if existing is not None:
                    await session.delete(existing)
            await session.commit()


async def test_unprocessable_fixture_isolated_from_siblings(db_engine: AsyncEngine) -> None:
    """The unprocessable fixture never blocks its batch-mates: run all four
    together and confirm the other three still fully processed (a
    dedicated, narrower isolation proof alongside the full spine test
    above)."""
    t1 = datetime(2026, 2, 1, tzinfo=UTC)
    job_tenant = _load_fixture("clean_tenant_scoped")
    job_no_tenant = _load_fixture("missing_salary_no_tenant")
    job_url_fallback = _load_fixture("url_fallback_only")
    job_unprocessable = _load_fixture("unprocessable")

    provider = FixtureProvider(
        [job_unprocessable, job_tenant, job_no_tenant, job_url_fallback], called_at=t1
    )
    query = SourceQuery(sources=["fixture_ats"])
    clock = FixedClock(t1)

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(db_engine, provider, query, observed_at=t1, clock=clock)
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)
            statuses = sorted(row.processing_status for row in raw_rows)
            assert statuses == ["normalized", "normalized", "normalized", "parse_error"]

        occurrence_tenant = await _occurrence_by_job_id(db_engine, "REQ-1001")
        occurrence_no_tenant = await _occurrence_by_job_id(db_engine, "987654321")
        occurrence_url = await _occurrence_by_url(
            db_engine, "https://gamma.example.com/careers/data-analyst-role"
        )
        job_ids.extend(
            [occurrence_tenant.job_id, occurrence_no_tenant.job_id, occurrence_url.job_id]
        )
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_unexpected_failure_propagates_and_marks_run_failed(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception other than `UnresolvableIdentityError` is never caught
    as a `parse_error` — it propagates, and the run/attempt are marked
    `failed` best-effort first. Already-committed Transaction-A rows from
    earlier in the batch remain intact."""
    t1 = datetime(2026, 3, 1, tzinfo=UTC)
    job_tenant = _load_fixture("clean_tenant_scoped")
    job_no_tenant = _load_fixture("missing_salary_no_tenant")

    provider = FixtureProvider([job_tenant, job_no_tenant], called_at=t1)
    query = SourceQuery(sources=["fixture_ats"])
    clock = FixedClock(t1)

    async def _broken_persist(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated unexpected persistence failure")

    monkeypatch.setattr(pipeline, "_persist_posting", _broken_persist)

    with pytest.raises(RuntimeError, match="simulated unexpected persistence failure"):
        await pipeline.run(db_engine, provider, query, observed_at=t1, clock=clock)

    async with AsyncSession(bind=db_engine) as session:
        runs = (await session.execute(select(CollectionRun))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        run_id = runs[0].id

        attempts = (
            (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(attempts) == 1
        assert attempts[0].status == "failed"

        raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
        assert len(raw_rows) == 2  # both Transaction-A rows survived
        assert all(row.processing_status == "fetched" for row in raw_rows)  # never advanced
        raw_ids = [row.id for row in raw_rows]

    await _cleanup(
        db_engine, user_ids=[], job_ids=[], collection_run_ids=[run_id], raw_ingestion_ids=raw_ids
    )


class _TwoSourceProvider:
    """A minimal `DiscoveryProvider` returning one job each from two
    genuinely different sources — proving `pipeline.run()` writes each
    `CollectionRunProviderAttempt` row its **own** source's counts, not the
    run-wide aggregate applied uniformly to every attempt (regression: the
    two sources are given deliberately different discovered/inserted
    counts here specifically so a bug that conflates them would be
    visible, not accidentally masked by both sources happening to match)."""

    name = "two_source_provider"

    def __init__(
        self, jobs_by_source: dict[str, list[DiscoveredJob]], *, called_at: datetime
    ) -> None:
        self._jobs_by_source = jobs_by_source
        self._called_at = called_at

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        jobs = [job for source in query.sources for job in self._jobs_by_source.get(source, [])]
        stats = [
            SourceRunStats(
                source=source, completed=True, jobs_found=len(self._jobs_by_source.get(source, []))
            )
            for source in query.sources
        ]
        return DiscoveryResult(
            provider=self.name,
            jobs=jobs,
            source_stats=stats,
            started_at=self._called_at,
            completed_at=self._called_at,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, healthy=True, last_checked_at=self._called_at)


async def test_per_source_attempt_counters_are_not_the_run_wide_aggregate(
    db_engine: AsyncEngine,
) -> None:
    t1 = datetime(2026, 8, 1, tzinfo=UTC)
    base = _load_fixture("clean_tenant_scoped")
    job_a = base.model_copy(
        update={"source": "source_a", "source_job_id": "A-1", "source_tenant_id": "tenant-a"}
    )
    job_b1 = base.model_copy(
        update={"source": "source_b", "source_job_id": "B-1", "source_tenant_id": "tenant-b"}
    )
    job_b2 = base.model_copy(
        update={"source": "source_b", "source_job_id": "B-2", "source_tenant_id": "tenant-b"}
    )

    provider = _TwoSourceProvider({"source_a": [job_a], "source_b": [job_b1, job_b2]}, called_at=t1)
    query = SourceQuery(sources=["source_a", "source_b"])
    clock = FixedClock(t1)

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(db_engine, provider, query, observed_at=t1, clock=clock)
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            assert run.jobs_discovered == 3  # 1 + 2, the correct run-level rollup
            assert run.jobs_inserted == 3

            attempts = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == run_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_source = {a.source: a for a in attempts}
            assert len(by_source) == 2
            assert by_source["source_a"].jobs_discovered == 1
            assert by_source["source_a"].jobs_inserted == 1
            assert by_source["source_b"].jobs_discovered == 2
            assert by_source["source_b"].jobs_inserted == 2

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)

        for source_job_id in ("A-1", "B-1", "B-2"):
            occurrence = await _occurrence_by_job_id(db_engine, source_job_id)
            job_ids.append(occurrence.job_id)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


class _MismatchedSourcesProvider:
    """A minimal `DiscoveryProvider` that deliberately returns
    `source_stats` for a source the query never asked for — proving
    `pipeline.run()` itself enforces `SourceQuery.sources ==
    DiscoveryResult.requested_sources` (docs/ARCHITECTURE.md §6.3: this is
    a call-site invariant, not something `DiscoveryResult` can check on
    its own)."""

    name = "mismatched_provider"

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        return DiscoveryResult(
            provider=self.name,
            jobs=[],
            source_stats=[
                SourceRunStats(source="a_source_never_requested", completed=True, jobs_found=0)
            ],
            started_at=datetime(2026, 5, 1, tzinfo=UTC),
            completed_at=datetime(2026, 5, 1, tzinfo=UTC),
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name, healthy=True, last_checked_at=datetime(2026, 5, 1, tzinfo=UTC)
        )


async def test_pipeline_rejects_source_stats_mismatched_against_query_sources(
    db_engine: AsyncEngine,
) -> None:
    provider: DiscoveryProvider = _MismatchedSourcesProvider()
    query = SourceQuery(sources=["fixture_ats"])
    clock = FixedClock(datetime(2026, 5, 1, tzinfo=UTC))

    with pytest.raises(RuntimeError, match="do not match SourceQuery.sources"):
        await pipeline.run(
            db_engine, provider, query, observed_at=datetime(2026, 5, 1, tzinfo=UTC), clock=clock
        )

    async with AsyncSession(bind=db_engine) as session:
        runs = (await session.execute(select(CollectionRun))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        run_id = runs[0].id

    await _cleanup(
        db_engine, user_ids=[], job_ids=[], collection_run_ids=[run_id], raw_ingestion_ids=[]
    )
