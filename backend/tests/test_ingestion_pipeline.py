import json
import logging
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
from app.ingestion.natural_key import NaturalKey
from app.ingestion.persistence import (
    DeferredIdentityConflictError,
    UpsertOutcome,
    upsert_job_occurrence,
)
from app.providers.base import DiscoveryProvider
from app.providers.fixture import FixtureProvider
from app.schemas.discovered_job import (
    DiscoveredJob,
    DiscoveryResult,
    ProviderError,
    ProviderErrorCategory,
    SourceRunStats,
)
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

            all_raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            run1_raw_ids = set(raw_ingestion_ids)
            run2_raw_rows = [row for row in all_raw_rows if row.id not in run1_raw_ids]
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


async def test_reobservation_only_advances_observational_fields(
    db_engine: AsyncEngine,
) -> None:
    """A natural-key replay may advance observation state, but changed or
    missing source/descriptive values remain frozen until later
    provenance/merge behavior can reconcile them."""
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)
    t1 = datetime(2026, 7, 1, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    job_ids: list[uuid.UUID] = []
    try:
        async with AsyncSession(bind=db_engine) as session, session.begin():
            first = await upsert_job_occurrence(session, natural_key, job, t1)
        job_ids.append(first.job_id)

        changed_job = job.model_copy(
            update={
                "title": "Replacement title must not win",
                "location": None,
                "compensation_text": None,
                "posted_at": None,
                "apply_url": None,
                "canonical_url": None,
                "requisition_id_raw": "DIFFERENT-REQUISITION",
            }
        )
        async with AsyncSession(bind=db_engine) as session, session.begin():
            second = await upsert_job_occurrence(session, natural_key, changed_job, t2)
        assert second.inserted is False
        assert second.occurrence_id == first.occurrence_id

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.last_seen_at == t2
            assert occurrence.is_active is True
            assert occurrence.posted_at == job.posted_at
            assert occurrence.apply_url == job.apply_url
            assert occurrence.canonical_url == job.canonical_url
            assert occurrence.canonical_url_normalized == job.canonical_url
            assert occurrence.requisition_id_raw == job.requisition_id_raw

            job_row = await session.get(Job, first.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t2
            assert job_row.title == job.title
            assert job_row.location_raw == job.location
            assert job_row.compensation_text == job.compensation_text
            assert job_row.canonical_url == job.canonical_url
    finally:
        async with AsyncSession(bind=db_engine) as session:
            for job_id in job_ids:
                existing = await session.get(Job, job_id)
                if existing is not None:
                    await session.delete(existing)
            await session.commit()


async def test_canonical_evidence_mismatch_fails_closed_before_mutation(
    db_engine: AsyncEngine,
) -> None:
    """Until conflict persistence is implemented, a canonical mismatch is
    a distinct propagated failure: it is not a parse error and cannot
    mutate even observational state."""
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)
    t1 = datetime(2026, 7, 2, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    job_ids: list[uuid.UUID] = []
    try:
        async with AsyncSession(bind=db_engine) as session, session.begin():
            first = await upsert_job_occurrence(session, natural_key, job, t1)
        job_ids.append(first.job_id)

        conflicting = job.model_copy(
            update={"canonical_url": "https://different.example.com/jobs/REQ-1001"}
        )
        async with AsyncSession(bind=db_engine) as session:
            with pytest.raises(DeferredIdentityConflictError):
                async with session.begin():
                    await upsert_job_occurrence(session, natural_key, conflicting, t2)

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.last_seen_at == t1
            assert occurrence.canonical_url == job.canonical_url
            assert occurrence.canonical_url_normalized == job.canonical_url

            job_row = await session.get(Job, first.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t1
            assert job_row.canonical_url == job.canonical_url
    finally:
        async with AsyncSession(bind=db_engine) as session:
            for job_id in job_ids:
                existing = await session.get(Job, job_id)
                if existing is not None:
                    await session.delete(existing)
            await session.commit()


async def test_pipeline_leaves_conflicting_raw_row_fetched_and_marks_run_failed(
    db_engine: AsyncEngine,
) -> None:
    """The deferred conflict is neither normalized nor parse_error: the
    durable raw row remains fetched and the enclosing run fails."""
    job = _load_fixture("clean_tenant_scoped")
    conflicting = job.model_copy(
        update={"canonical_url": "https://different.example.com/jobs/REQ-1001"}
    )
    query = SourceQuery(sources=["fixture_ats"])
    t1 = datetime(2026, 7, 3, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    job_ids: list[uuid.UUID] = []
    run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
        preexisting_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
        preexisting_raw_ids = set(
            (await session.execute(select(RawJobIngestion.id))).scalars().all()
        )
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([job], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        run_ids.append(run1_id)

        occurrence = await _occurrence_by_job_id(db_engine, "REQ-1001")
        job_ids.append(occurrence.job_id)

        with pytest.raises(DeferredIdentityConflictError):
            await pipeline.run(
                db_engine,
                FixtureProvider([conflicting], called_at=t2),
                query,
                observed_at=t2,
                clock=FixedClock(t2),
            )

        async with AsyncSession(bind=db_engine) as session:
            runs = (await session.execute(select(CollectionRun))).scalars().all()
            failed_run = next(run for run in runs if run.id != run1_id)
            run_ids.append(failed_run.id)
            assert failed_run.status == "failed"
            assert failed_run.jobs_discovered == 1
            assert failed_run.jobs_inserted == 0
            assert failed_run.jobs_updated == 0

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
            assert sorted(row.processing_status for row in raw_rows) == ["fetched", "normalized"]

            reloaded = await session.get(JobOccurrence, occurrence.id)
            assert reloaded is not None
            assert reloaded.last_seen_at == t1
            assert reloaded.canonical_url == job.canonical_url
    finally:
        async with AsyncSession(bind=db_engine) as session:
            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
            current_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
            current_raw_ids = set(
                (await session.execute(select(RawJobIngestion.id))).scalars().all()
            )
        job_ids = list(current_job_ids - preexisting_job_ids)
        run_ids = list(current_run_ids - preexisting_run_ids)
        raw_ids = list(current_raw_ids - preexisting_raw_ids)
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=run_ids,
            raw_ingestion_ids=raw_ids,
        )


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


async def test_parse_error_telemetry_is_sanitized_logged_safely_and_uses_fetch_time(
    db_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Raw evidence may contain a secret-bearing malformed URL, but
    persisted/logged telemetry may not; fetched_at comes from the posting's
    discovery event rather than the independent observation timestamp."""
    secret = "TOKEN_DO_NOT_EXPOSE"
    base = _load_fixture("unprocessable")
    job = base.model_copy(
        update={
            "source_url": f"/careers/postings/456?token={secret}",
            "raw": {"url": f"/careers/postings/456?token={secret}"},
        }
    )
    observed_at = datetime(2026, 9, 1, tzinfo=UTC)
    provider = FixtureProvider([job], called_at=observed_at)
    query = SourceQuery(sources=["fixture_ats"])
    caplog.set_level(logging.INFO, logger="app.ingestion.pipeline")

    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine,
            provider,
            query,
            observed_at=observed_at,
            clock=FixedClock(observed_at),
        )
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            raw = (await session.execute(select(RawJobIngestion))).scalar_one()
            raw_ids.append(raw.id)
            assert raw.processing_status == "parse_error"
            assert raw.fetched_at == job.discovered_at
            assert raw.fetched_at != observed_at
            assert raw.error_message == (
                "posting has neither a stable source identifier nor a normalizable source URL"
            )
            assert secret in str(raw.raw_payload)
            assert secret not in raw.error_message

        messages = [record.getMessage() for record in caplog.records]
        assert any("ingestion_run_started" in message for message in messages)
        assert any("ingestion_parse_error" in message for message in messages)
        assert any("ingestion_run_completed" in message for message in messages)
        assert all(secret not in message for message in messages)
        warning_messages = [
            record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
        ]
        assert warning_messages == [f"ingestion_parse_error raw_ingestion_id={raw_ids[0]}"]
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=[],
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_unexpected_failure_propagates_and_marks_run_failed(
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An exception other than `UnresolvableIdentityError` is never caught
    as a `parse_error` — it propagates, and the run/attempt are marked
    `failed` best-effort first. A failure on posting two preserves the
    exact durable progress from posting one in both telemetry levels."""
    t1 = datetime(2026, 3, 1, tzinfo=UTC)
    job_tenant = _load_fixture("clean_tenant_scoped")
    job_no_tenant = _load_fixture("missing_salary_no_tenant")

    provider = FixtureProvider([job_tenant, job_no_tenant], called_at=t1)
    query = SourceQuery(sources=["fixture_ats"])
    clock = FixedClock(t1)

    original_persist = pipeline._persist_posting
    call_count = 0

    async def _fail_on_second_posting(
        engine: AsyncEngine,
        natural_key: NaturalKey,
        job: DiscoveredJob,
        observed_at: datetime,
        raw_id: uuid.UUID,
    ) -> UpsertOutcome:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("simulated unexpected persistence failure SECRET_VALUE")
        return await original_persist(engine, natural_key, job, observed_at, raw_id)

    monkeypatch.setattr(pipeline, "_persist_posting", _fail_on_second_posting)
    caplog.set_level(logging.INFO, logger="app.ingestion.pipeline")

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        with pytest.raises(RuntimeError, match="simulated unexpected persistence failure"):
            await pipeline.run(db_engine, provider, query, observed_at=t1, clock=clock)

        async with AsyncSession(bind=db_engine) as session:
            runs = (await session.execute(select(CollectionRun))).scalars().all()
            assert len(runs) == 1
            run = runs[0]
            collection_run_ids.append(run.id)
            assert run.status == "failed"
            assert run.jobs_discovered == 2
            assert run.jobs_inserted == 1
            assert run.jobs_updated == 0

            attempts = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == run.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "failed"
            assert attempts[0].jobs_discovered == 2
            assert attempts[0].jobs_inserted == 1
            assert attempts[0].jobs_updated == 0

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
            assert len(raw_rows) == 2
            assert sorted(row.processing_status for row in raw_rows) == ["fetched", "normalized"]

            jobs = (await session.execute(select(Job))).scalars().all()
            job_ids.extend(row.id for row in jobs)
            assert len(jobs) == 1

        messages = [record.getMessage() for record in caplog.records]
        assert any("ingestion_run_started" in message for message in messages)
        assert any("ingestion_run_failed" in message for message in messages)
        assert all("SECRET_VALUE" not in message for message in messages)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
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
        update={
            "provider": "two_source_provider",
            "source": "source_a",
            "source_job_id": "A-1",
            "source_tenant_id": "tenant-a",
        }
    )
    job_b1 = base.model_copy(
        update={
            "provider": "two_source_provider",
            "source": "source_b",
            "source_job_id": "B-1",
            "source_tenant_id": "tenant-b",
        }
    )
    job_b2 = base.model_copy(
        update={
            "provider": "two_source_provider",
            "source": "source_b",
            "source_job_id": "B-2",
            "source_tenant_id": "tenant-b",
        }
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


class _StaticResultProvider:
    name = "fixture_provider"

    def __init__(self, result: DiscoveryResult) -> None:
        self._result = result

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        return self._result

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=True,
            last_checked_at=self._result.completed_at,
        )


@pytest.mark.parametrize(
    "case",
    [
        "result_provider_mismatch",
        "job_provider_mismatch",
        "provider_error",
        "source_not_completed",
        "incomplete_results",
    ],
)
async def test_pipeline_fails_closed_for_unsupported_provider_result_states(
    db_engine: AsyncEngine,
    case: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Until the later partial-success slice owns these states, the spine
    must report failure before writing any posting rather than claiming a
    fully completed collection."""
    called_at = datetime(2026, 10, 1, tzinfo=UTC)
    job = _load_fixture("clean_tenant_scoped")
    provider_name = "wrong_provider" if case == "result_provider_mismatch" else "fixture_provider"
    result_jobs = (
        [job.model_copy(update={"provider": "wrong_provider"})]
        if case == "job_provider_mismatch"
        else []
    )

    stat = SourceRunStats(
        source="fixture_ats",
        completed=case != "source_not_completed",
        jobs_found=len(result_jobs),
        incomplete_results=case == "incomplete_results",
    )
    errors = (
        [
            ProviderError(
                source="fixture_ats",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                detail="SECRET_PROVIDER_DETAIL",
                occurred_at=called_at,
            )
        ]
        if case == "provider_error"
        else []
    )
    result = DiscoveryResult(
        provider=provider_name,
        jobs=result_jobs,
        source_stats=[stat],
        errors=errors,
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])
    caplog.set_level(logging.INFO, logger="app.ingestion.pipeline")

    run_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
    try:
        with pytest.raises(pipeline.UnsupportedDiscoveryResultError):
            await pipeline.run(
                db_engine,
                provider,
                query,
                observed_at=called_at,
                clock=FixedClock(called_at),
            )

        async with AsyncSession(bind=db_engine) as session:
            run = (await session.execute(select(CollectionRun))).scalar_one()
            run_ids.append(run.id)
            assert run.status == "failed"
            assert run.jobs_discovered == 0
            attempts = (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run.id
                    )
                )
            ).scalar_one()
            assert attempts.status == "failed"
            assert attempts.jobs_discovered == 0
            assert (
                await session.execute(select(func.count()).select_from(RawJobIngestion))
            ).scalar_one() == 0
            assert (await session.execute(select(func.count()).select_from(Job))).scalar_one() == 0

        messages = [record.getMessage() for record in caplog.records]
        assert any("ingestion_run_failed" in message for message in messages)
        assert all("SECRET_PROVIDER_DETAIL" not in message for message in messages)
    finally:
        async with AsyncSession(bind=db_engine) as session:
            current_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
        run_ids = list(current_run_ids - preexisting_run_ids)
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=[],
            collection_run_ids=run_ids,
            raw_ingestion_ids=[],
        )
