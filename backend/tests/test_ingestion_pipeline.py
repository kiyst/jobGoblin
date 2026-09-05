import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    CollectionRun,
    CollectionRunProviderAttempt,
    IdentityConflict,
    Job,
    JobOccurrence,
    RawJobIngestion,
    User,
    UserJob,
)
from app.ingestion import persistence, pipeline, provider_execution
from app.ingestion.clock import FixedClock
from app.ingestion.identity import resolve_identity
from app.ingestion.natural_key import NaturalKey, NaturalKeyDomain
from app.ingestion.persistence import (
    CandidateResolutionUnstableError,
    InvalidRawIngestionAssociationError,
    UpsertKind,
    UpsertOutcome,
    persist_posting,
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
    cascade pointing at it, so it is deleted explicitly. Neither of
    `IdentityConflict`'s own FKs cascades *to* it either (both are
    `ON DELETE SET NULL` — this table is an audit trail by design), so any
    conflict row a test's `persist_posting`/`pipeline.run()` call created
    against one of these raw ingestion ids is deleted explicitly first —
    otherwise it would silently survive every other delete below as a
    permanently orphaned row in the shared disposable test database."""
    async with AsyncSession(bind=engine) as session:
        if raw_ingestion_ids:
            conflicts = (
                (
                    await session.execute(
                        select(IdentityConflict).where(
                            IdentityConflict.incoming_raw_job_ingestion_id.in_(raw_ingestion_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for conflict in conflicts:
                await session.delete(conflict)
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


async def _conflict_count(engine: AsyncEngine) -> int:
    async with AsyncSession(bind=engine) as session:
        return (
            await session.execute(select(func.count()).select_from(IdentityConflict))
        ).scalar_one()


async def _collection_run_count(engine: AsyncEngine) -> int:
    async with AsyncSession(bind=engine) as session:
        return (await session.execute(select(func.count()).select_from(CollectionRun))).scalar_one()


async def _attempt_count(engine: AsyncEngine) -> int:
    async with AsyncSession(bind=engine) as session:
        return (
            await session.execute(select(func.count()).select_from(CollectionRunProviderAttempt))
        ).scalar_one()


async def _create_job_and_occurrence_directly(
    engine: AsyncEngine,
    job: DiscoveredJob,
    *,
    observed_at: datetime,
    canonical_url_normalized: str | None = None,
) -> uuid.UUID:
    """Directly inserts a `Job`/`JobOccurrence` pair, bypassing
    `upsert_job_occurrence`/`persist_posting` entirely. Used only to
    construct a pre-existing anomalous state (e.g. two independently
    created Jobs that already share a canonical URL or tenant+requisition)
    that this slice's own code path could never itself produce — its own
    advisory locks serialize every attach attempt for a given signal —
    for the multiple-candidate adversarial tests. Returns the new Job's
    id."""
    async with AsyncSession(bind=engine) as session, session.begin():
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
        job_id = new_job.id

        occurrence = JobOccurrence(
            job_id=job_id,
            provider=job.provider,
            source=job.source,
            source_tenant_id=job.source_tenant_id,
            source_job_id=job.source_job_id,
            requisition_id_raw=job.requisition_id_raw,
            source_url=job.source_url,
            source_url_normalized=None,
            apply_url=job.apply_url,
            canonical_url=job.canonical_url,
            canonical_url_normalized=canonical_url_normalized,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            posted_at=job.posted_at,
        )
        session.add(occurrence)
        await session.flush()
    return job_id


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
        assert second.kind is UpsertKind.UPDATED
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


async def test_canonical_evidence_mismatch_quarantines_without_moving_disputed_fields(
    db_engine: AsyncEngine,
) -> None:
    """A canonical-URL mismatch on an existing natural key quarantines
    (ADR 0007's `evidence_mismatch`): no error is raised, no second
    occurrence is created, disputed/descriptive fields stay frozen on the
    existing occurrence, but observational fields (`last_seen_at`,
    `is_active`, and the parent `Job`'s own `last_seen_at`) still advance —
    the same guarantee a clean re-observation gets."""
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)
    t1 = datetime(2026, 7, 2, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        raw_id_1 = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)
        raw_ids.append(raw_id_1)
        first = await persist_posting(db_engine, natural_key, job, t1, raw_id_1)
        job_ids.append(first.job_id)

        conflicting = job.model_copy(
            update={
                "canonical_url": "https://different.example.com/jobs/REQ-1001",
                "discovered_at": t2,
            }
        )
        raw_id_2 = await pipeline._write_fetched_row(
            db_engine, conflicting, conflicting.discovered_at
        )
        raw_ids.append(raw_id_2)
        second = await persist_posting(db_engine, natural_key, conflicting, t2, raw_id_2)

        assert second.kind is UpsertKind.QUARANTINED
        assert second.occurrence_id == first.occurrence_id
        assert second.conflict_id is not None

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.last_seen_at == t2  # observational field advances
            assert occurrence.is_active is True
            assert occurrence.canonical_url == job.canonical_url  # disputed field frozen
            assert occurrence.canonical_url_normalized == job.canonical_url

            job_row = await session.get(Job, first.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t2  # parent Job observational field advances too

            conflict = await session.get(IdentityConflict, second.conflict_id)
            assert conflict is not None
            assert conflict.conflict_type == "evidence_mismatch"
            assert conflict.status == "open"
            assert conflict.existing_job_occurrence_id == first.occurrence_id
            assert conflict.incoming_raw_job_ingestion_id == raw_id_2
            assert conflict.existing_value == {"canonical_url_normalized": job.canonical_url}
            assert conflict.incoming_value == {
                "canonical_url_normalized": "https://different.example.com/jobs/REQ-1001"
            }

            raw_2 = await session.get(RawJobIngestion, raw_id_2)
            assert raw_2 is not None
            assert raw_2.processing_status == "identity_conflict"
            assert raw_2.job_occurrence_id == first.occurrence_id

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == first.job_id)
                )
            ).scalar_one()
            assert occurrence_count == 1  # no second occurrence created
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_pipeline_quarantines_conflicting_posting_and_marks_run_completed_with_errors(
    db_engine: AsyncEngine,
) -> None:
    """Through the full pipeline (not just `persist_posting` directly): a
    canonical-URL mismatch quarantines rather than failing the run. The raw
    row transitions to `identity_conflict` (never stays `fetched`, never
    becomes `parse_error`), and the run/attempt report
    `completed_with_errors`, not `failed`."""
    job = _load_fixture("clean_tenant_scoped")
    conflicting = job.model_copy(
        update={
            "canonical_url": "https://different.example.com/jobs/REQ-1001",
            "discovered_at": datetime(2026, 7, 3, 1, tzinfo=UTC),
        }
    )
    query = SourceQuery(sources=["fixture_ats"])
    t1 = datetime(2026, 7, 3, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    job_ids: list[uuid.UUID] = []
    run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
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

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([conflicting], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        run_ids.append(run2_id)

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.status == "completed_with_errors"
            assert run2.jobs_discovered == 1
            assert run2.jobs_inserted == 0
            assert run2.jobs_updated == 1  # quarantined counts as updated

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
            assert attempts_2[0].jobs_updated == 1

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
            assert sorted(row.processing_status for row in raw_rows) == [
                "identity_conflict",
                "normalized",
            ]
            conflicting_raw = next(
                row for row in raw_rows if row.processing_status == "identity_conflict"
            )
            assert conflicting_raw.job_occurrence_id == occurrence.id

            conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
            assert len(conflicts) == 1
            assert conflicts[0].existing_job_occurrence_id == occurrence.id
            assert conflicts[0].incoming_raw_job_ingestion_id == conflicting_raw.id

            reloaded = await session.get(JobOccurrence, occurrence.id)
            assert reloaded is not None
            assert reloaded.last_seen_at == t2  # observational field still advances
            assert reloaded.canonical_url == job.canonical_url  # disputed field frozen
    finally:
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
        assert replay.kind is UpsertKind.UPDATED
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

    original_persist = provider_execution.persist_posting
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

    monkeypatch.setattr(provider_execution, "persist_posting", _fail_on_second_posting)
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
    # Distinct canonical_url per job (base's own is otherwise shared
    # unchanged by model_copy) — required since Tier 2 now exists: three
    # postings sharing one canonical URL would have two of them ATTACH to
    # the first's Job instead of each getting its own, which is exactly
    # what this test must *not* exercise (it's purely about per-source
    # counter isolation).
    job_a = base.model_copy(
        update={
            "provider": "two_source_provider",
            "source": "source_a",
            "source_job_id": "A-1",
            "source_tenant_id": "tenant-a",
            "canonical_url": "https://acme.example.com/jobs/two-source-a-1",
        }
    )
    job_b1 = base.model_copy(
        update={
            "provider": "two_source_provider",
            "source": "source_b",
            "source_job_id": "B-1",
            "source_tenant_id": "tenant-b",
            "canonical_url": "https://acme.example.com/jobs/two-source-b-1",
        }
    )
    job_b2 = base.model_copy(
        update={
            "provider": "two_source_provider",
            "source": "source_b",
            "source_job_id": "B-2",
            "source_tenant_id": "tenant-b",
            "canonical_url": "https://acme.example.com/jobs/two-source-b-2",
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
    ],
)
async def test_pipeline_fails_closed_for_malformed_provider_result_states(
    db_engine: AsyncEngine,
    case: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `DiscoveryResult` whose own claims about itself don't add up (a
    provider/source name mismatch) is a genuine adapter-contract
    violation — always a whole-run failure before any posting is
    written, never a graceful per-source outcome. A source legitimately
    failing/partially succeeding is a *different*, now gracefully handled
    case — see `test_pipeline_persists_healthy_source_jobs_while_sibling_
    source_fails` and its neighbors below."""
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
        completed=True,
        jobs_found=len(result_jobs),
    )
    result = DiscoveryResult(
        provider=provider_name,
        jobs=result_jobs,
        source_stats=[stat],
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


async def test_pipeline_fails_closed_when_jobs_found_does_not_match_actual_count(
    db_engine: AsyncEngine,
) -> None:
    """`DiscoveryResult`'s own pydantic validator cannot check this — a
    source claiming `jobs_found` that disagrees with the actual number of
    `DiscoveredJob` entries attributed to it is a whole-run contract
    violation, checked before any raw row is written."""
    called_at = datetime(2026, 10, 2, tzinfo=UTC)
    job = _load_fixture("clean_tenant_scoped").model_copy(
        update={"provider": "fixture_provider", "source": "fixture_ats"}
    )
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[job],
        # Declares 5 jobs but only 1 DiscoveredJob is actually attributed
        # to this source.
        source_stats=[SourceRunStats(source="fixture_ats", completed=True, jobs_found=5)],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])

    run_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
    try:
        with pytest.raises(pipeline.UnsupportedDiscoveryResultError, match="jobs_found"):
            await pipeline.run(
                db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
            )

        async with AsyncSession(bind=db_engine) as session:
            run = (await session.execute(select(CollectionRun))).scalar_one()
            run_ids.append(run.id)
            assert run.status == "failed"
            attempt = (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run.id
                    )
                )
            ).scalar_one()
            assert attempt.status == "failed"
            assert (
                await session.execute(select(func.count()).select_from(RawJobIngestion))
            ).scalar_one() == 0
            assert (await session.execute(select(func.count()).select_from(Job))).scalar_one() == 0
            assert (
                await session.execute(select(func.count()).select_from(JobOccurrence))
            ).scalar_one() == 0
    finally:
        async with AsyncSession(bind=db_engine) as session:
            current_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
        run_ids = list(current_run_ids - preexisting_run_ids)
        await _cleanup(
            db_engine, user_ids=[], job_ids=[], collection_run_ids=run_ids, raw_ingestion_ids=[]
        )


async def test_pipeline_fails_closed_when_completed_false_source_has_actual_jobs(
    db_engine: AsyncEngine,
) -> None:
    """A source reporting `completed=False` (with the `jobs_found=0` its
    own pydantic validator already requires) but that nonetheless has a
    real `DiscoveredJob` attributed to it — a case only reachable via a
    buggy/dishonest adapter, since `DiscoveryResult`'s own validator only
    checks `jobs_found`, never cross-references actual job attribution
    against `completed`. Must fail the whole run, never silently persist
    or silently drop that job."""
    called_at = datetime(2026, 10, 3, tzinfo=UTC)
    job = _load_fixture("clean_tenant_scoped").model_copy(
        update={"provider": "fixture_provider", "source": "fixture_ats"}
    )
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[job],
        source_stats=[
            SourceRunStats(source="fixture_ats", completed=False, jobs_found=0),
        ],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])

    run_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
    try:
        with pytest.raises(pipeline.UnsupportedDiscoveryResultError, match="completed=False"):
            await pipeline.run(
                db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
            )

        async with AsyncSession(bind=db_engine) as session:
            run = (await session.execute(select(CollectionRun))).scalar_one()
            run_ids.append(run.id)
            assert run.status == "failed"
            assert (
                await session.execute(select(func.count()).select_from(RawJobIngestion))
            ).scalar_one() == 0
            assert (await session.execute(select(func.count()).select_from(Job))).scalar_one() == 0
    finally:
        async with AsyncSession(bind=db_engine) as session:
            current_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
        run_ids = list(current_run_ids - preexisting_run_ids)
        await _cleanup(
            db_engine, user_ids=[], job_ids=[], collection_run_ids=run_ids, raw_ingestion_ids=[]
        )


async def test_pipeline_fails_closed_when_completed_false_source_reports_incomplete_results(
    db_engine: AsyncEngine,
) -> None:
    """`completed=False, incomplete_results=True` is not a valid
    combination — a source either failed outright (`completed=False`) or
    partially succeeded (`completed=True, incomplete_results=True`);
    nothing about "incomplete" makes sense for a source that produced
    nothing at all."""
    called_at = datetime(2026, 10, 4, tzinfo=UTC)
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[],
        source_stats=[
            SourceRunStats(
                source="fixture_ats", completed=False, jobs_found=0, incomplete_results=True
            ),
        ],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])

    run_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
    try:
        with pytest.raises(
            pipeline.UnsupportedDiscoveryResultError, match="not a valid combination"
        ):
            await pipeline.run(
                db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
            )

        async with AsyncSession(bind=db_engine) as session:
            run = (await session.execute(select(CollectionRun))).scalar_one()
            run_ids.append(run.id)
            assert run.status == "failed"
            assert (
                await session.execute(select(func.count()).select_from(RawJobIngestion))
            ).scalar_one() == 0
    finally:
        async with AsyncSession(bind=db_engine) as session:
            current_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
        run_ids = list(current_run_ids - preexisting_run_ids)
        await _cleanup(
            db_engine, user_ids=[], job_ids=[], collection_run_ids=run_ids, raw_ingestion_ids=[]
        )


async def test_pipeline_persists_healthy_source_jobs_while_sibling_source_fails(
    db_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """ARCHITECTURE.md §11's required partial-failure fixture case: one
    source succeeds while a sibling fails within the same run — the
    healthy source's job must still be fully persisted, and the failed
    source's own attempt row must independently record its own outcome,
    never contaminating or discarding the healthy source's telemetry."""
    called_at = datetime(2026, 10, 5, tzinfo=UTC)
    healthy_job = _load_fixture("clean_tenant_scoped").model_copy(
        update={"provider": "fixture_provider", "source": "healthy_source"}
    )
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[healthy_job],
        source_stats=[
            SourceRunStats(source="healthy_source", completed=True, jobs_found=1),
            SourceRunStats(source="broken_source", completed=False, jobs_found=0),
        ],
        errors=[
            ProviderError(
                source="broken_source",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                detail="SECRET_PROVIDER_DETAIL",
                occurred_at=called_at,
            )
        ],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["healthy_source", "broken_source"])
    caplog.set_level(logging.INFO, logger="app.ingestion.pipeline")

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
        )
        collection_run_ids.append(run_id)

        # Captured before any assertion below, so a later assertion
        # failure still leaves cleanup able to find these rows.
        assert healthy_job.source_job_id is not None
        occurrence = await _occurrence_by_job_id(db_engine, healthy_job.source_job_id)
        job_ids.append(occurrence.job_id)
        async with AsyncSession(bind=db_engine) as session:
            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            assert run.status == "completed_with_errors"
            assert run.jobs_discovered == 1
            assert run.jobs_inserted == 1
            assert run.jobs_updated == 0
            assert run.failures == [
                {
                    "provider": "fixture_provider",
                    "source": "broken_source",
                    "error": {
                        "category": "timeout",
                        "retryable": True,
                        "detail": "SECRET_PROVIDER_DETAIL",
                        "occurred_at": called_at.isoformat(),
                    },
                }
            ]

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
            assert by_source["healthy_source"].status == "completed"
            assert by_source["healthy_source"].jobs_discovered == 1
            assert by_source["healthy_source"].jobs_inserted == 1
            assert by_source["healthy_source"].error_category is None
            assert by_source["healthy_source"].error_message is None
            assert by_source["broken_source"].status == "failed"
            assert by_source["broken_source"].jobs_discovered == 0
            assert by_source["broken_source"].jobs_inserted == 0
            assert by_source["broken_source"].error_category == "timeout"
            assert by_source["broken_source"].error_message == "SECRET_PROVIDER_DETAIL"

            assert len(raw_rows) == 1  # only the healthy source's job was ever fetched
            assert raw_rows[0].processing_status == "normalized"

        messages = [record.getMessage() for record in caplog.records]
        assert any("ingestion_run_completed" in message for message in messages)
        assert all("SECRET_PROVIDER_DETAIL" not in message for message in messages)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_pipeline_marks_source_partial_without_provider_error(
    db_engine: AsyncEngine,
) -> None:
    """A source that partially succeeded (`completed=True,
    incomplete_results=True`) with no accompanying `ProviderError` at all
    — a clean, truncated-but-successful pagination result is not an error
    condition (per the model's own docstring). `status='partial'`, error
    fields stay `NULL`, and no fabricated `failures` entry is invented."""
    called_at = datetime(2026, 10, 6, tzinfo=UTC)
    job_a = _load_fixture("clean_tenant_scoped").model_copy(
        update={"provider": "fixture_provider", "source": "fixture_ats"}
    )
    job_b = _load_fixture("missing_salary_no_tenant").model_copy(
        update={"provider": "fixture_provider", "source": "fixture_ats"}
    )
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[job_a, job_b],
        source_stats=[
            SourceRunStats(
                source="fixture_ats", completed=True, jobs_found=2, incomplete_results=True
            )
        ],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
        )
        collection_run_ids.append(run_id)

        # Captured before any assertion below, so a later assertion
        # failure still leaves cleanup able to find these rows.
        assert job_a.source_job_id is not None
        occ_a = await _occurrence_by_job_id(db_engine, job_a.source_job_id)
        job_ids.append(occ_a.job_id)
        assert job_b.source_job_id is not None
        occ_b = await _occurrence_by_job_id(db_engine, job_b.source_job_id)
        job_ids.append(occ_b.job_id)
        async with AsyncSession(bind=db_engine) as session:
            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            assert run.status == "completed_with_errors"
            assert run.failures == []

            attempt = (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run_id
                    )
                )
            ).scalar_one()
            assert attempt.status == "partial"
            assert attempt.incomplete_results is True
            assert attempt.error_category is None
            assert attempt.error_message is None
            assert attempt.jobs_discovered == 2
            assert attempt.jobs_inserted == 2
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_pipeline_keeps_completed_source_status_despite_nonfatal_provider_error(
    db_engine: AsyncEngine,
) -> None:
    """A `ProviderError` alone never changes a `completed=True,
    incomplete_results=False` source's own `status` — it stays
    `'completed'`, even though the parent run still becomes
    `completed_with_errors` and the error is still fully recorded."""
    called_at = datetime(2026, 10, 7, tzinfo=UTC)
    job = _load_fixture("clean_tenant_scoped").model_copy(
        update={"provider": "fixture_provider", "source": "fixture_ats"}
    )
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[job],
        source_stats=[SourceRunStats(source="fixture_ats", completed=True, jobs_found=1)],
        errors=[
            ProviderError(
                source="fixture_ats",
                category=ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                detail="succeeded after one retry",
                occurred_at=called_at,
            )
        ],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
        )
        collection_run_ids.append(run_id)

        # Captured before any assertion below, so a later assertion
        # failure still leaves cleanup able to find these rows.
        assert job.source_job_id is not None
        occurrence = await _occurrence_by_job_id(db_engine, job.source_job_id)
        job_ids.append(occurrence.job_id)
        async with AsyncSession(bind=db_engine) as session:
            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            assert run.status == "completed_with_errors"
            assert len(run.failures) == 1

            attempt = (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run_id
                    )
                )
            ).scalar_one()
            assert attempt.status == "completed"  # never downgraded by the error alone
            assert attempt.error_category == "rate_limited"
            assert attempt.error_message == "succeeded after one retry"
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_pipeline_marks_fully_failed_source_without_provider_error(
    db_engine: AsyncEngine,
) -> None:
    """A source that fully failed (`completed=False`) but with no
    accompanying `ProviderError` at all — `status='failed'`, error fields
    stay `NULL` (no `CHECK` ties them together), and no fabricated
    `failures` entry is invented from thin air."""
    called_at = datetime(2026, 10, 8, tzinfo=UTC)
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[],
        source_stats=[SourceRunStats(source="fixture_ats", completed=False, jobs_found=0)],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])

    collection_run_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
        )
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            assert run.status == "completed_with_errors"
            assert run.failures == []

            attempt = (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run_id
                    )
                )
            ).scalar_one()
            assert attempt.status == "failed"
            assert attempt.error_category is None
            assert attempt.error_message is None
            assert attempt.jobs_discovered == 0
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=[],
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=[],
        )


async def test_pipeline_selects_latest_provider_error_per_source_and_retains_all(
    db_engine: AsyncEngine,
) -> None:
    """Multiple `ProviderError`s for one source are valid and must not
    discard anything: every error survives individually in
    `CollectionRun.failures`, in `result.errors` order, while each
    source's own attempt-level `error_category`/`error_message` reflects
    only the chronologically latest one — ties broken by later list
    position."""
    t1 = datetime(2026, 10, 9, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[],
        source_stats=[
            SourceRunStats(source="multi_error_source", completed=False, jobs_found=0),
            SourceRunStats(source="tie_source", completed=False, jobs_found=0),
        ],
        errors=[
            ProviderError(
                source="multi_error_source",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                detail="first, earlier timestamp",
                occurred_at=t1,
            ),
            ProviderError(
                source="multi_error_source",
                category=ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                detail="second, later timestamp — must win",
                occurred_at=t2,
            ),
            ProviderError(
                source="tie_source",
                category=ProviderErrorCategory.AUTH_ERROR,
                retryable=False,
                detail="tie, earlier position",
                occurred_at=t1,
            ),
            ProviderError(
                source="tie_source",
                category=ProviderErrorCategory.BLOCKED,
                retryable=False,
                detail="tie, later position — must win",
                occurred_at=t1,
            ),
        ],
        started_at=t1,
        completed_at=t1,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["multi_error_source", "tie_source"])

    collection_run_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine, provider, query, observed_at=t1, clock=FixedClock(t1)
        )
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            failures = cast(list[dict[str, Any]], run.failures)
            assert len(failures) == 4  # every error retained, none collapsed
            assert [f["error"]["detail"] for f in failures] == [
                "first, earlier timestamp",
                "second, later timestamp — must win",
                "tie, earlier position",
                "tie, later position — must win",
            ]

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
            assert by_source["multi_error_source"].error_category == "rate_limited"
            assert (
                by_source["multi_error_source"].error_message
                == "second, later timestamp — must win"
            )
            assert by_source["tie_source"].error_category == "blocked"
            assert by_source["tie_source"].error_message == "tie, later position — must win"
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=[],
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=[],
        )


async def test_pipeline_populates_retry_count_and_rate_limited_from_source_stats(
    db_engine: AsyncEngine,
) -> None:
    """`SourceRunStats.retry_count`/`.rate_limited` must reach the attempt
    row exactly — previously always left at their `0`/`False` defaults
    regardless of what the provider actually reported."""
    called_at = datetime(2026, 10, 10, tzinfo=UTC)
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[],
        source_stats=[
            SourceRunStats(
                source="fixture_ats",
                completed=False,
                jobs_found=0,
                retry_count=3,
                rate_limited=True,
            )
        ],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=["fixture_ats"])

    collection_run_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
        )
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            attempt = (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run_id
                    )
                )
            ).scalar_one()
            assert attempt.retry_count == 3
            assert attempt.rate_limited is True
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=[],
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=[],
        )


async def test_pipeline_normalizes_error_message_with_the_shared_covered_whitespace_set(
    db_engine: AsyncEngine,
) -> None:
    """The Core-update `error_message` normalization must match
    `CollectionRunProviderAttempt`'s own ORM validator and database `CHECK`
    exactly: trim only `COVERED_WHITESPACE` (space/tab/LF/CR), never
    Python's broader default `str.strip()` whitespace set. Covered outer
    whitespace is trimmed; non-covered Unicode whitespace (e.g. U+00A0) is
    left byte-for-byte intact; a covered-whitespace-only detail collapses
    to `NULL`; a non-covered-whitespace-only detail stays non-`NULL`.
    `CollectionRun.failures[*].error.detail` never inherits any of this —
    it is always the exact original `ProviderError.detail`."""
    called_at = datetime(2026, 10, 11, tzinfo=UTC)
    covered_outer = "  \t\n\r  mixed covered outer whitespace  \t\n\r  "
    non_covered_preserved = " non-breaking spaces preserved "
    covered_only = "   \t\n\r   "
    non_covered_only = "   "

    sources = ["covered-outer", "non-covered-preserved", "covered-only", "non-covered-only"]
    details = {
        "covered-outer": covered_outer,
        "non-covered-preserved": non_covered_preserved,
        "covered-only": covered_only,
        "non-covered-only": non_covered_only,
    }
    result = DiscoveryResult(
        provider="fixture_provider",
        jobs=[],
        source_stats=[
            SourceRunStats(source=source, completed=True, jobs_found=0) for source in sources
        ],
        errors=[
            ProviderError(
                source=source,
                category=ProviderErrorCategory.UNKNOWN,
                retryable=False,
                detail=detail,
                occurred_at=called_at,
            )
            for source, detail in details.items()
        ],
        started_at=called_at,
        completed_at=called_at,
    )
    provider: DiscoveryProvider = _StaticResultProvider(result)
    query = SourceQuery(sources=sources)

    collection_run_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine, provider, query, observed_at=called_at, clock=FixedClock(called_at)
        )
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            failures = cast(list[dict[str, Any]], run.failures)
            failures_by_source = {f["source"]: f["error"]["detail"] for f in failures}
            # `failures` never inherits attempt-message normalization —
            # always the exact original ProviderError.detail, for every case.
            assert failures_by_source == details

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
            assert by_source["covered-outer"].error_message == "mixed covered outer whitespace"
            assert by_source["non-covered-preserved"].error_message == non_covered_preserved
            assert by_source["covered-only"].error_message is None
            assert by_source["non-covered-only"].error_message == non_covered_only
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=[],
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=[],
        )


def _user_job_snapshot(user_job: UserJob) -> dict[str, object]:
    """Every persisted column except `id` (the identity itself, compared
    separately by `session.get()` on the same id) — used to prove a
    `UserJob` is *fully* unchanged, not merely on the one or two columns a
    narrower check happened to look at."""
    return {
        "user_id": user_job.user_id,
        "job_id": user_job.job_id,
        "saved": user_job.saved,
        "hidden": user_job.hidden,
        "archived": user_job.archived,
        "applied_at": user_job.applied_at,
        "status": user_job.status,
        "status_changed_at": user_job.status_changed_at,
        "created_at": user_job.created_at,
        "updated_at": user_job.updated_at,
    }


async def test_three_run_conflict_matrix(
    db_engine: AsyncEngine,
    make_user: Callable[..., User],
    make_user_job: Callable[..., UserJob],
) -> None:
    """The exact three-run counter/table matrix from the approved proposal:
    Run 1 creates the occurrence cleanly; Run 2 disputes its canonical URL
    (quarantine) alongside an unrelated valid posting; Run 3 disputes it
    again via a distinct new `RawJobIngestion` (a second, independent
    conflict, never a duplicate of Run 2's). Cumulative `CollectionRun`/
    attempt row totals, every run's and its one attempt's exact status and
    counters, every persisted `UserJob` column, and quarantined raw rows'
    `error_message` are all checked after each run."""
    t1 = datetime(2026, 9, 10, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)
    t3 = t2 + timedelta(hours=1)
    query = SourceQuery(sources=["fixture_ats"])

    user_ids: list[uuid.UUID] = []
    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []

    try:
        # ------------------------------------------------------------------
        # Run 1 — clean insert
        # ------------------------------------------------------------------
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("clean_tenant_scoped")], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run1_id)

        assert await _raw_ingestion_count(db_engine) == 1
        assert await _job_count(db_engine) == 1
        assert await _occurrence_count(db_engine) == 1
        assert await _conflict_count(db_engine) == 0
        assert await _collection_run_count(db_engine) == 1
        assert await _attempt_count(db_engine) == 1

        occurrence_1 = await _occurrence_by_job_id(db_engine, "REQ-1001")
        job_ids.append(occurrence_1.job_id)

        async with AsyncSession(bind=db_engine) as session:
            run1 = await session.get(CollectionRun, run1_id)
            assert run1 is not None
            assert run1.status == "completed"
            assert run1.jobs_discovered == 1
            assert run1.jobs_inserted == 1
            assert run1.jobs_updated == 0

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
            assert attempts_1[0].jobs_discovered == 1
            assert attempts_1[0].jobs_inserted == 1
            assert attempts_1[0].jobs_updated == 0

        # UserJob created between runs, proven fully unchanged after Run 2 and Run 3
        user = make_user(email="conflict-matrix@example.com")
        async with AsyncSession(bind=db_engine) as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
            user_id = user.id
        user_ids.append(user_id)

        user_job = make_user_job(
            user_id=user_id,
            job_id=occurrence_1.job_id,
            status_changed_at=t1,
            status="applied",
            applied_at=t1,
        )
        async with AsyncSession(bind=db_engine) as session:
            session.add(user_job)
            await session.commit()
            await session.refresh(user_job)
            user_job_id = user_job.id
            user_job_snapshot = _user_job_snapshot(user_job)

        # ------------------------------------------------------------------
        # Run 2 — conflicting posting + an unrelated new valid posting
        # ------------------------------------------------------------------
        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider(
                [
                    _load_fixture("evidence_mismatch_conflicting"),
                    _load_fixture("missing_salary_no_tenant"),
                ],
                called_at=t2,
            ),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run2_id)

        assert await _raw_ingestion_count(db_engine) == 3
        assert await _job_count(db_engine) == 2
        assert await _occurrence_count(db_engine) == 2
        assert await _conflict_count(db_engine) == 1
        assert await _collection_run_count(db_engine) == 2
        assert await _attempt_count(db_engine) == 2

        occurrence_no_tenant = await _occurrence_by_job_id(db_engine, "987654321")
        job_ids.append(occurrence_no_tenant.job_id)

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.status == "completed_with_errors"
            assert run2.jobs_discovered == 2
            assert run2.jobs_inserted == 1
            assert run2.jobs_updated == 1

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
            assert attempts_2[0].jobs_discovered == 2
            assert attempts_2[0].jobs_inserted == 1
            assert attempts_2[0].jobs_updated == 1

            occurrence_1_after_run2 = await session.get(JobOccurrence, occurrence_1.id)
            assert occurrence_1_after_run2 is not None
            assert occurrence_1_after_run2.last_seen_at == t2
            assert occurrence_1_after_run2.canonical_url == occurrence_1.canonical_url

            reloaded_user_job = await session.get(UserJob, user_job_id)
            assert reloaded_user_job is not None
            assert _user_job_snapshot(reloaded_user_job) == user_job_snapshot

            quarantined_after_run2 = (
                (
                    await session.execute(
                        select(RawJobIngestion).where(
                            RawJobIngestion.processing_status == "identity_conflict"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(quarantined_after_run2) == 1
            assert quarantined_after_run2[0].error_message is None

        # ------------------------------------------------------------------
        # Run 3 — the same conflicting posting again, via a new ingestion
        # ------------------------------------------------------------------
        run3_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("evidence_mismatch_conflicting")], called_at=t3),
            query,
            observed_at=t3,
            clock=FixedClock(t3),
        )
        collection_run_ids.append(run3_id)

        assert await _raw_ingestion_count(db_engine) == 4
        assert await _job_count(db_engine) == 2  # unchanged
        assert await _occurrence_count(db_engine) == 2  # unchanged
        assert await _conflict_count(db_engine) == 2  # a second, distinct conflict
        assert await _collection_run_count(db_engine) == 3
        assert await _attempt_count(db_engine) == 3

        async with AsyncSession(bind=db_engine) as session:
            run3 = await session.get(CollectionRun, run3_id)
            assert run3 is not None
            assert run3.status == "completed_with_errors"
            assert run3.jobs_discovered == 1
            assert run3.jobs_inserted == 0
            assert run3.jobs_updated == 1

            attempts_3 = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == run3_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts_3) == 1
            assert attempts_3[0].status == "completed"
            assert attempts_3[0].jobs_discovered == 1
            assert attempts_3[0].jobs_inserted == 0
            assert attempts_3[0].jobs_updated == 1

            occurrence_1_after_run3 = await session.get(JobOccurrence, occurrence_1.id)
            assert occurrence_1_after_run3 is not None
            assert occurrence_1_after_run3.last_seen_at == t3
            assert occurrence_1_after_run3.canonical_url == occurrence_1.canonical_url

            reloaded_user_job_after_run3 = await session.get(UserJob, user_job_id)
            assert reloaded_user_job_after_run3 is not None
            assert _user_job_snapshot(reloaded_user_job_after_run3) == user_job_snapshot

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)
            assert sorted(row.processing_status for row in raw_rows) == [
                "identity_conflict",
                "identity_conflict",
                "normalized",
                "normalized",
            ]
            quarantined_raw_rows = [
                row for row in raw_rows if row.processing_status == "identity_conflict"
            ]
            assert len(quarantined_raw_rows) == 2
            assert all(row.error_message is None for row in quarantined_raw_rows)
    finally:
        await _cleanup(
            db_engine,
            user_ids=user_ids,
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_quarantine_advances_observational_timestamps_monotonically(
    db_engine: AsyncEngine,
) -> None:
    """Quarantine still advances `last_seen_at` on both the occurrence and
    its parent `Job` (the same guarantee a clean re-observation gets), and
    an out-of-order `observed_at` submitted for a *later* quarantine attempt
    must never move either timestamp backward — mirroring
    `test_out_of_order_replay_never_moves_last_seen_at_backward`'s
    non-conflict guarantee for the conflict path."""
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)
    t1 = datetime(2026, 9, 15, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)  # earlier than t3, submitted *after* t3
    t3 = t1 + timedelta(hours=3)  # later — advances last_seen_at forward

    conflicting = job.model_copy(
        update={
            "canonical_url": "https://different.example.com/jobs/REQ-1001",
            "discovered_at": t3,
        }
    )

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        raw_id_1 = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)
        raw_ids.append(raw_id_1)
        first = await persist_posting(db_engine, natural_key, job, t1, raw_id_1)
        job_ids.append(first.job_id)

        # Quarantine attempt #1, observed later (t3) — advances forward.
        raw_id_2 = await pipeline._write_fetched_row(
            db_engine, conflicting, conflicting.discovered_at
        )
        raw_ids.append(raw_id_2)
        second = await persist_posting(db_engine, natural_key, conflicting, t3, raw_id_2)
        assert second.kind is UpsertKind.QUARANTINED

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.last_seen_at == t3
            job_row = await session.get(Job, first.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t3

        # Quarantine attempt #2, a fresh ingestion of the same conflicting
        # content, observed *earlier* (t2 < t3) — must never move backward.
        raw_id_3 = await pipeline._write_fetched_row(
            db_engine, conflicting, conflicting.discovered_at
        )
        raw_ids.append(raw_id_3)
        third = await persist_posting(db_engine, natural_key, conflicting, t2, raw_id_3)
        assert third.kind is UpsertKind.QUARANTINED

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.last_seen_at == t3  # unchanged — t2 < t3, never regresses
            job_row = await session.get(Job, first.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t3

            conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
            assert len(conflicts) == 2  # one per distinct ingestion, not deduplicated
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_quarantine_rollback_discards_all_effects_and_marks_run_failed(
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure injected via the private `persistence._after_quarantine_flush`
    seam — after the occurrence's and parent `Job`'s observational mutation,
    the `IdentityConflict` insert, and the raw terminal update have all been
    flushed inside `persist_posting`'s own transaction, but before that
    transaction commits — must roll back all four effects together. Run
    through `pipeline.run()` (not `persist_posting` directly) so the
    run/attempt-failure counters can be checked too, mirroring
    `test_unexpected_failure_propagates_and_marks_run_failed`'s
    fail-on-second-posting pattern."""
    t1 = datetime(2026, 9, 20, tzinfo=UTC)
    t2 = t1 + timedelta(hours=2)
    job = _load_fixture("clean_tenant_scoped")
    conflicting = job.model_copy(
        update={
            "canonical_url": "https://different.example.com/jobs/REQ-1001",
            "discovered_at": t2,
        }
    )
    unrelated = _load_fixture("missing_salary_no_tenant").model_copy(update={"discovered_at": t2})
    query = SourceQuery(sources=["fixture_ats"])

    job_ids: list[uuid.UUID] = []
    run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([job], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        run_ids.append(run1_id)

        occurrence_before = await _occurrence_by_job_id(db_engine, "REQ-1001")

        async def _raise() -> None:
            raise RuntimeError("simulated rollback trigger")

        monkeypatch.setattr(persistence, "_after_quarantine_flush", _raise)

        with pytest.raises(RuntimeError, match="simulated rollback trigger"):
            await pipeline.run(
                db_engine,
                # `unrelated` processed first (succeeds, commits its own
                # transaction) before `conflicting` fails mid-transaction.
                FixtureProvider([unrelated, conflicting], called_at=t2),
                query,
                observed_at=t2,
                clock=FixedClock(t2),
            )

        async with AsyncSession(bind=db_engine) as session:
            runs = (await session.execute(select(CollectionRun))).scalars().all()
            failed_run = next(run for run in runs if run.id != run1_id)
            run_ids.append(failed_run.id)
            assert failed_run.status == "failed"
            assert failed_run.jobs_discovered == 2
            assert failed_run.jobs_inserted == 1  # unrelated's already-committed insert
            assert failed_run.jobs_updated == 0  # conflicting's attempt fully rolled back

            attempts = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == failed_run.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "failed"
            assert attempts[0].jobs_inserted == 1
            assert attempts[0].jobs_updated == 0

            occurrence_after = await session.get(JobOccurrence, occurrence_before.id)
            assert occurrence_after is not None
            assert occurrence_after.last_seen_at == t1  # unchanged — rolled back
            assert occurrence_after.is_active is True
            assert occurrence_after.canonical_url == job.canonical_url

            job_after = await session.get(Job, occurrence_before.job_id)
            assert job_after is not None
            assert job_after.last_seen_at == t1  # parent Job unchanged too — rolled back

            conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
            assert conflicts == []  # no conflict row survives the rollback

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
            assert len(raw_rows) == 3
            assert sorted(row.processing_status for row in raw_rows) == [
                "fetched",
                "normalized",
                "normalized",
            ]
            fetched_row = next(row for row in raw_rows if row.processing_status == "fetched")
            assert fetched_row.job_occurrence_id is None
            assert fetched_row.source_identifier == "REQ-1001"

        async with AsyncSession(bind=db_engine) as session:
            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
        job_ids = list(current_job_ids - preexisting_job_ids)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_persist_posting_rejects_unrelated_raw_row_with_different_payload(
    db_engine: AsyncEngine,
) -> None:
    """URL-fallback domain: two unrelated postings share
    `source_identifier=NULL` (both lack `source_job_id`), so that check
    alone cannot distinguish them — `raw_content_hash` must. `discovered_at`
    is held identical between the two postings so this test isolates the
    hash check specifically (a `fetched_at` mismatch would also legitimately
    reject this raw_id, but that is a separate check covered by the sibling
    test below)."""
    job_a = _load_fixture("url_fallback_only")
    job_b = job_a.model_copy(
        update={
            "source_url": "https://gamma.example.com/careers/different-role",
            "canonical_url": None,
            "raw": {
                "title": "Different Role",
                "url": "https://gamma.example.com/careers/different-role",
            },
        }
    )
    t1 = datetime(2026, 9, 22, tzinfo=UTC)

    raw_ids: list[uuid.UUID] = []
    job_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
    try:
        raw_id_a = await pipeline._write_fetched_row(db_engine, job_a, job_a.discovered_at)
        raw_ids.append(raw_id_a)

        natural_key_b = resolve_identity(job_b)
        with pytest.raises(InvalidRawIngestionAssociationError, match="content hash"):
            await persist_posting(db_engine, natural_key_b, job_b, t1, raw_id_a)

        async with AsyncSession(bind=db_engine) as session:
            raw_a = await session.get(RawJobIngestion, raw_id_a)
            assert raw_a is not None
            assert raw_a.processing_status == "fetched"
            assert raw_a.job_occurrence_id is None
            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
            assert current_job_ids == preexisting_job_ids  # no mutation occurred at all
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_persist_posting_rejects_unrelated_raw_row_with_mismatched_fetched_at(
    db_engine: AsyncEngine,
) -> None:
    """URL-fallback domain, isolating the `fetched_at` check specifically:
    two postings share byte-identical `raw` content (so the content-hash
    check alone would pass) but differ in `discovered_at`."""
    job_a = _load_fixture("url_fallback_only")
    job_b = job_a.model_copy(update={"discovered_at": job_a.discovered_at + timedelta(days=1)})
    t1 = datetime(2026, 9, 23, tzinfo=UTC)

    raw_ids: list[uuid.UUID] = []
    job_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
    try:
        raw_id_a = await pipeline._write_fetched_row(db_engine, job_a, job_a.discovered_at)
        raw_ids.append(raw_id_a)

        natural_key_b = resolve_identity(job_b)
        with pytest.raises(InvalidRawIngestionAssociationError, match="fetched_at"):
            await persist_posting(db_engine, natural_key_b, job_b, t1, raw_id_a)

        async with AsyncSession(bind=db_engine) as session:
            raw_a = await session.get(RawJobIngestion, raw_id_a)
            assert raw_a is not None
            assert raw_a.processing_status == "fetched"
            assert raw_a.job_occurrence_id is None
            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
            assert current_job_ids == preexisting_job_ids
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_persist_posting_rejects_natural_key_that_does_not_match_the_job(
    db_engine: AsyncEngine,
) -> None:
    """A genuinely valid raw/job pair (matching hash, `fetched_at`,
    provider/source, and `source_identifier`) combined with a `natural_key`
    resolved for a *different* tenant must still be rejected. None of the
    raw-association checks alone can catch this: `RawJobIngestion` has no
    `source_tenant_id` column, so a forged tenant on an otherwise-identical
    natural key agrees with every check that compares `natural_key` against
    `raw`. Only re-resolving `job`'s own identity and requiring exact
    equality with the supplied `natural_key` catches it."""
    job = _load_fixture("clean_tenant_scoped")
    genuine_natural_key = resolve_identity(job)
    forged_natural_key = NaturalKey(
        domain=NaturalKeyDomain.TENANT,
        provider=genuine_natural_key.provider,
        source=genuine_natural_key.source,
        tenant_id="evil-corp",
        job_id=genuine_natural_key.job_id,
        url_normalized=genuine_natural_key.url_normalized,
    )
    assert forged_natural_key != genuine_natural_key
    t1 = datetime(2026, 9, 26, tzinfo=UTC)

    raw_ids: list[uuid.UUID] = []
    job_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
    try:
        raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)
        raw_ids.append(raw_id)

        with pytest.raises(InvalidRawIngestionAssociationError, match="natural_key"):
            await persist_posting(db_engine, forged_natural_key, job, t1, raw_id)

        async with AsyncSession(bind=db_engine) as session:
            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "fetched"
            assert raw_row.job_occurrence_id is None

            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
            assert current_job_ids == preexisting_job_ids  # no Job/Occurrence created

            conflicts_for_raw = (
                (
                    await session.execute(
                        select(IdentityConflict).where(
                            IdentityConflict.incoming_raw_job_ingestion_id == raw_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert conflicts_for_raw == []
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_persist_posting_rejects_reprocessing_the_same_raw_id(
    db_engine: AsyncEngine,
) -> None:
    """Reprocessing an already-consumed `raw_id` fails before any mutation
    — the structural guard behind "one `IdentityConflict` per distinct new
    `RawJobIngestion`": a raw row already turned `normalized` (or, in the
    sibling assertion below, `identity_conflict`) can never be consumed a
    second time."""
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)
    t1 = datetime(2026, 9, 24, tzinfo=UTC)

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)
        raw_ids.append(raw_id)

        first = await persist_posting(db_engine, natural_key, job, t1, raw_id)
        job_ids.append(first.job_id)

        with pytest.raises(InvalidRawIngestionAssociationError, match="fetched state"):
            await persist_posting(db_engine, natural_key, job, t1, raw_id)

        async with AsyncSession(bind=db_engine) as session:
            occurrence = await session.get(JobOccurrence, first.occurrence_id)
            assert occurrence is not None
            assert occurrence.last_seen_at == t1  # not re-mutated by the rejected retry
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_persist_posting_rejects_reprocessing_a_quarantined_raw_id(
    db_engine: AsyncEngine,
) -> None:
    """The same reprocessing guard, specifically for a raw row already
    turned `identity_conflict`: a second call with the same `raw_id` must
    not create a second `IdentityConflict` row."""
    job = _load_fixture("clean_tenant_scoped")
    natural_key = resolve_identity(job)
    t1 = datetime(2026, 9, 25, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)

    conflicting = job.model_copy(
        update={
            "canonical_url": "https://different.example.com/jobs/REQ-1001",
            "discovered_at": t2,
        }
    )

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        raw_id_1 = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)
        raw_ids.append(raw_id_1)
        first = await persist_posting(db_engine, natural_key, job, t1, raw_id_1)
        job_ids.append(first.job_id)

        raw_id_2 = await pipeline._write_fetched_row(
            db_engine, conflicting, conflicting.discovered_at
        )
        raw_ids.append(raw_id_2)
        second = await persist_posting(db_engine, natural_key, conflicting, t2, raw_id_2)
        assert second.kind is UpsertKind.QUARANTINED

        with pytest.raises(InvalidRawIngestionAssociationError, match="fetched state"):
            await persist_posting(db_engine, natural_key, conflicting, t2, raw_id_2)

        async with AsyncSession(bind=db_engine) as session:
            conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
            assert len(conflicts) == 1  # not duplicated by the rejected retry
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_conflict_telemetry_is_sanitized_but_evidence_preserves_normalized_secret(
    db_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The literal secret is placed in a URL *query parameter* that
    `normalize_url()` retains (it is not on the tracking-parameter
    deny-list) — proving the exact normalized secret-bearing evidence is
    stored in `identity_conflicts` (its intended function), while the
    secret appears in no captured log record."""
    secret = "TOKEN_DO_NOT_EXPOSE"
    job = _load_fixture("clean_tenant_scoped").model_copy(
        update={"canonical_url": f"https://acme.example.com/jobs/REQ-1001?auth={secret}"}
    )
    conflicting = job.model_copy(
        update={
            "canonical_url": f"https://acme.example.com/jobs/REQ-1001-moved?auth={secret}",
            "discovered_at": job.discovered_at + timedelta(hours=1),
        }
    )
    query = SourceQuery(sources=["fixture_ats"])
    t1 = job.discovered_at
    t2 = conflicting.discovered_at
    caplog.set_level(logging.INFO, logger="app.ingestion.pipeline")

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([job], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run1_id)
        occurrence = await _occurrence_by_job_id(db_engine, "REQ-1001")
        job_ids.append(occurrence.job_id)
        assert occurrence.canonical_url_normalized is not None
        assert secret in occurrence.canonical_url_normalized  # the allow-listed query survives

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([conflicting], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run2_id)

        async with AsyncSession(bind=db_engine) as session:
            conflict = (await session.execute(select(IdentityConflict))).scalar_one()
            assert secret in str(conflict.existing_value)
            assert secret in str(conflict.incoming_value)

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)

        messages = [record.getMessage() for record in caplog.records]
        assert any("ingestion_identity_conflict" in message for message in messages)
        assert all(secret not in message for message in messages)
        warning_messages = [
            record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
        ]
        assert len(warning_messages) == 1
        assert warning_messages[0].startswith("ingestion_identity_conflict raw_ingestion_id=")
        assert "identity_conflict_id=" in warning_messages[0]
        assert "job_occurrence_id=" in warning_messages[0]
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_tier2_canonical_url_attaches_to_existing_job(db_engine: AsyncEngine) -> None:
    """Two postings with different natural keys (TENANT domain, then
    NO_TENANT domain) but the same normalized canonical URL: the second
    attaches to the first's Job (Tier 2) rather than creating a
    duplicate. The secondary fixture's own `utm_source` tracking
    parameter proves `normalize_url()`'s stripping is what makes the two
    canonical URLs equal, not merely identical raw strings."""
    t1 = datetime(2026, 3, 10, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)
    query = SourceQuery(sources=["fixture_ats"])

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("canonical_url_match_primary")], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run1_id)
        occurrence_primary = await _occurrence_by_job_id(db_engine, "WID-500")
        job_ids.append(occurrence_primary.job_id)

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("canonical_url_match_secondary")], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run2_id)

        assert await _job_count(db_engine) == 1
        assert await _occurrence_count(db_engine) == 2

        occurrence_secondary = await _occurrence_by_job_id(db_engine, "987650001")
        assert occurrence_secondary.job_id == occurrence_primary.job_id

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.status == "completed"
            assert run2.jobs_discovered == 1
            assert run2.jobs_inserted == 0
            assert run2.jobs_updated == 1  # ATTACHED buckets as updated, never inserted

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
            assert attempts_2[0].jobs_inserted == 0
            assert attempts_2[0].jobs_updated == 1

            job_row = await session.get(Job, occurrence_primary.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t2  # advanced by the attach
            assert job_row.first_seen_at == t1  # unchanged — the Job already existed

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
            assert all(row.processing_status == "normalized" for row in raw_rows)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_tier3_tenant_requisition_attaches_to_existing_job(db_engine: AsyncEngine) -> None:
    """Two postings with different natural keys, no canonical URL, but the
    same `(provider, source, source_tenant_id, requisition_id_raw)`: the
    second attaches via Tier 3 to the first's Job, using the existing
    `ix_job_occurrences_tenant_requisition_lookup` index."""
    t1 = datetime(2026, 3, 11, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)
    query = SourceQuery(sources=["fixture_ats"])

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("tenant_requisition_match_primary")], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run1_id)
        occurrence_primary = await _occurrence_by_job_id(db_engine, "REQ-777")
        job_ids.append(occurrence_primary.job_id)

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("tenant_requisition_match_secondary")], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run2_id)

        assert await _job_count(db_engine) == 1
        assert await _occurrence_count(db_engine) == 2

        occurrence_secondary = await _occurrence_by_job_id(db_engine, "REQ-778-REPOST")
        assert occurrence_secondary.job_id == occurrence_primary.job_id

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.status == "completed"
            assert run2.jobs_inserted == 0
            assert run2.jobs_updated == 1

            job_row = await session.get(Job, occurrence_primary.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t2

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_tier3_scoping_rejects_different_tenant_same_requisition(
    db_engine: AsyncEngine,
) -> None:
    """Same `requisition_id_raw`, different `source_tenant_id`: must
    create two separate Jobs, never attach — proves Tier 3's tenant
    scoping, mirroring the existing Tier-1 two-tenants precedent."""
    t1 = datetime(2026, 3, 12, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)
    query = SourceQuery(sources=["fixture_ats"])

    different_tenant_job = _load_fixture("tenant_requisition_match_secondary").model_copy(
        update={
            "source_tenant_id": "different-tenant-co",
            "source_job_id": "REQ-999-DIFFERENT-TENANT",
        }
    )

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("tenant_requisition_match_primary")], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run1_id)
        occurrence_primary = await _occurrence_by_job_id(db_engine, "REQ-777")
        job_ids.append(occurrence_primary.job_id)

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([different_tenant_job], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run2_id)

        assert await _job_count(db_engine) == 2
        assert await _occurrence_count(db_engine) == 2

        occurrence_different_tenant = await _occurrence_by_job_id(
            db_engine, "REQ-999-DIFFERENT-TENANT"
        )
        assert occurrence_different_tenant.job_id != occurrence_primary.job_id
        job_ids.append(occurrence_different_tenant.job_id)

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.jobs_inserted == 1
            assert run2.jobs_updated == 0

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_usable_canonical_url_miss_does_not_fall_back_to_tier3(
    db_engine: AsyncEngine,
) -> None:
    """A posting with a *usable* canonical URL that matches nothing at
    Tier 2 must create a new Job via Tier 5, even when its tenant+
    requisition would have matched an existing Job at Tier 3 — a usable
    canonical URL's miss is not license to fall back to a weaker signal
    for the same posting (ARCHITECTURE.md §8's conservative precedence).
    This is the precedence regression the review specifically required."""
    t1 = datetime(2026, 3, 13, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)
    query = SourceQuery(sources=["fixture_ats"])

    would_match_tier3_but_has_url = _load_fixture("tenant_requisition_match_secondary").model_copy(
        update={
            "source_job_id": "REQ-779-HAS-URL",
            "canonical_url": "https://acme-holdings.example.com/jobs/req-779-has-url",
        }
    )

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([_load_fixture("tenant_requisition_match_primary")], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run1_id)
        occurrence_primary = await _occurrence_by_job_id(db_engine, "REQ-777")
        job_ids.append(occurrence_primary.job_id)

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([would_match_tier3_but_has_url], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run2_id)

        assert await _job_count(db_engine) == 2  # NOT attached via Tier 3

        occurrence_new = await _occurrence_by_job_id(db_engine, "REQ-779-HAS-URL")
        assert occurrence_new.job_id != occurrence_primary.job_id
        job_ids.append(occurrence_new.job_id)

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.jobs_inserted == 1
            assert run2.jobs_updated == 0

            job_primary_after = await session.get(Job, occurrence_primary.job_id)
            assert job_primary_after is not None
            assert job_primary_after.last_seen_at == t1  # untouched by run 2

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_tier2_multiple_candidates_persists_ambiguous_match(db_engine: AsyncEngine) -> None:
    """Two independently pre-existing Jobs that already share a canonical
    URL (a pre-existing anomaly this slice's own code cannot itself
    produce, since its own advisory lock serializes every attach attempt
    for a given URL) — a third posting sharing that URL under a new
    natural key must create a standalone Job/JobOccurrence and persist an
    `ambiguous_match` `identity_conflicts` row naming both candidates,
    never guessing which one to attach to and never raising."""
    t0 = datetime(2026, 3, 14, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    shared_url = "https://ambiguous.example.com/jobs/shared"

    base = _load_fixture("canonical_url_match_primary")
    job_x = base.model_copy(
        update={
            "source_tenant_id": "tenant-x",
            "source_job_id": "AMB-X",
            "canonical_url": shared_url,
        }
    )
    job_y = base.model_copy(
        update={
            "source_tenant_id": "tenant-y",
            "source_job_id": "AMB-Y",
            "canonical_url": shared_url,
        }
    )
    job_z = base.model_copy(
        update={
            "source_tenant_id": "tenant-z",
            "source_job_id": "AMB-Z",
            "canonical_url": shared_url,
        }
    )

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        job_x_id = await _create_job_and_occurrence_directly(
            db_engine, job_x, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_y_id = await _create_job_and_occurrence_directly(
            db_engine, job_y, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_ids.extend([job_x_id, job_y_id])

        natural_key_z = resolve_identity(job_z)
        raw_id_z = await pipeline._write_fetched_row(db_engine, job_z, job_z.discovered_at)
        raw_ids.append(raw_id_z)

        outcome = await persist_posting(db_engine, natural_key_z, job_z, t1, raw_id_z)
        job_ids.append(outcome.job_id)  # the new standalone Job, captured before any assertion

        assert outcome.kind is UpsertKind.AMBIGUOUS
        assert outcome.ambiguous_candidate_job_ids == tuple(sorted([job_x_id, job_y_id]))
        assert outcome.conflict_id is not None

        async with AsyncSession(bind=db_engine) as session:
            assert (
                await session.execute(select(func.count()).select_from(Job))
            ).scalar_one() == 3  # job_x, job_y, and the new standalone Job

            new_occurrence = await session.get(JobOccurrence, outcome.occurrence_id)
            assert new_occurrence is not None
            assert new_occurrence.job_id == outcome.job_id
            assert new_occurrence.job_id not in (job_x_id, job_y_id)

            # Neither candidate was mutated or given a second occurrence.
            job_x_row = await session.get(Job, job_x_id)
            assert job_x_row is not None
            assert job_x_row.last_seen_at == t0
            job_y_row = await session.get(Job, job_y_id)
            assert job_y_row is not None
            assert job_y_row.last_seen_at == t0
            for candidate_id in (job_x_id, job_y_id):
                occurrence_count = (
                    await session.execute(
                        select(func.count())
                        .select_from(JobOccurrence)
                        .where(JobOccurrence.job_id == candidate_id)
                    )
                ).scalar_one()
                assert occurrence_count == 1

            conflict = await session.get(IdentityConflict, outcome.conflict_id)
            assert conflict is not None
            assert conflict.conflict_type == "ambiguous_match"
            assert conflict.status == "open"
            assert conflict.existing_job_occurrence_id is None
            assert conflict.incoming_raw_job_ingestion_id == raw_id_z
            assert conflict.existing_value == sorted([str(job_x_id), str(job_y_id)])
            assert conflict.incoming_value == [str(outcome.occurrence_id)]

            raw_z = await session.get(RawJobIngestion, raw_id_z)
            assert raw_z is not None
            assert raw_z.processing_status == "identity_conflict"
            assert raw_z.job_occurrence_id == outcome.occurrence_id
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_tier3_multiple_candidates_persists_ambiguous_match(db_engine: AsyncEngine) -> None:
    """The Tier-3 analog of the above: two independently pre-existing Jobs
    already sharing a `(provider, source, source_tenant_id,
    requisition_id_raw)` combination — a third, no-canonical-URL posting
    with a new natural key sharing that combination must create a
    standalone Job/JobOccurrence and persist an `ambiguous_match` row
    naming both candidates, never raising."""
    t0 = datetime(2026, 3, 15, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)

    base = _load_fixture("tenant_requisition_match_primary")
    job_x = base.model_copy(update={"source_job_id": "TREQ-X"})
    job_y = base.model_copy(update={"source_job_id": "TREQ-Y"})
    job_z = base.model_copy(update={"source_job_id": "TREQ-Z"})

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        job_x_id = await _create_job_and_occurrence_directly(db_engine, job_x, observed_at=t0)
        job_y_id = await _create_job_and_occurrence_directly(db_engine, job_y, observed_at=t0)
        job_ids.extend([job_x_id, job_y_id])

        natural_key_z = resolve_identity(job_z)
        raw_id_z = await pipeline._write_fetched_row(db_engine, job_z, job_z.discovered_at)
        raw_ids.append(raw_id_z)

        outcome = await persist_posting(db_engine, natural_key_z, job_z, t1, raw_id_z)
        job_ids.append(outcome.job_id)  # captured before any assertion

        assert outcome.kind is UpsertKind.AMBIGUOUS
        assert outcome.ambiguous_candidate_job_ids == tuple(sorted([job_x_id, job_y_id]))
        assert outcome.conflict_id is not None

        async with AsyncSession(bind=db_engine) as session:
            assert (await session.execute(select(func.count()).select_from(Job))).scalar_one() == 3

            new_occurrence = await session.get(JobOccurrence, outcome.occurrence_id)
            assert new_occurrence is not None
            assert new_occurrence.job_id == outcome.job_id

            job_x_row = await session.get(Job, job_x_id)
            assert job_x_row is not None
            assert job_x_row.last_seen_at == t0
            job_y_row = await session.get(Job, job_y_id)
            assert job_y_row is not None
            assert job_y_row.last_seen_at == t0

            conflict = await session.get(IdentityConflict, outcome.conflict_id)
            assert conflict is not None
            assert conflict.conflict_type == "ambiguous_match"
            assert conflict.existing_job_occurrence_id is None
            assert conflict.existing_value == sorted([str(job_x_id), str(job_y_id)])
            assert conflict.incoming_value == [str(outcome.occurrence_id)]

            raw_z = await session.get(RawJobIngestion, raw_id_z)
            assert raw_z is not None
            assert raw_z.processing_status == "identity_conflict"
            assert raw_z.job_occurrence_id == outcome.occurrence_id
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_tier2_three_or_more_candidates_persists_full_candidate_set(
    db_engine: AsyncEngine,
) -> None:
    """The fast `<=2` ambiguity probe only ever sees two of the candidates,
    but the persisted `existing_value` must name every distinct candidate
    Job — proving `_discover_all_candidates` (not the probe) is what gets
    persisted. Three independently pre-existing Jobs share one canonical
    URL; a fourth posting under a new natural key sharing that URL must
    produce an `ambiguous_match` row listing all three, sorted."""
    t0 = datetime(2026, 3, 16, 12, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    shared_url = "https://ambiguous.example.com/jobs/three-way-shared"

    base = _load_fixture("canonical_url_match_primary")
    job_x = base.model_copy(
        update={
            "source_tenant_id": "tenant-x3",
            "source_job_id": "AMB3-X",
            "canonical_url": shared_url,
        }
    )
    job_y = base.model_copy(
        update={
            "source_tenant_id": "tenant-y3",
            "source_job_id": "AMB3-Y",
            "canonical_url": shared_url,
        }
    )
    job_w = base.model_copy(
        update={
            "source_tenant_id": "tenant-w3",
            "source_job_id": "AMB3-W",
            "canonical_url": shared_url,
        }
    )
    job_z = base.model_copy(
        update={
            "source_tenant_id": "tenant-z3",
            "source_job_id": "AMB3-Z",
            "canonical_url": shared_url,
        }
    )

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        job_x_id = await _create_job_and_occurrence_directly(
            db_engine, job_x, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_y_id = await _create_job_and_occurrence_directly(
            db_engine, job_y, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_w_id = await _create_job_and_occurrence_directly(
            db_engine, job_w, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_ids.extend([job_x_id, job_y_id, job_w_id])

        natural_key_z = resolve_identity(job_z)
        raw_id_z = await pipeline._write_fetched_row(db_engine, job_z, job_z.discovered_at)
        raw_ids.append(raw_id_z)

        outcome = await persist_posting(db_engine, natural_key_z, job_z, t1, raw_id_z)
        job_ids.append(outcome.job_id)  # captured before any assertion

        assert outcome.kind is UpsertKind.AMBIGUOUS
        expected = tuple(sorted([job_x_id, job_y_id, job_w_id]))
        assert outcome.ambiguous_candidate_job_ids == expected
        assert len(outcome.ambiguous_candidate_job_ids) == 3

        async with AsyncSession(bind=db_engine) as session:
            conflict = await session.get(IdentityConflict, outcome.conflict_id)
            assert conflict is not None
            assert conflict.existing_value == sorted(str(job_id) for job_id in expected)
            assert len(conflict.existing_value) == 3
            assert conflict.incoming_value == [str(outcome.occurrence_id)]
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_pre_lock_ambiguity_probe_disagreement_fails_closed(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the fast `<=2` probe reports ambiguity before any candidate lock
    is attempted, but the authoritative unbounded requery
    (`_discover_all_candidates`) resolves to fewer than two real
    candidates, this is a disagreement between two queries, not a genuine
    ambiguity — fail closed with `CandidateResolutionUnstableError` and
    persist nothing, never trust the disagreeing fast probe. Touches no
    candidate at all, since this is detected before any lock attempt."""
    t1 = datetime(2026, 3, 20, tzinfo=UTC)
    job = _load_fixture("canonical_url_match_primary").model_copy(
        update={"source_job_id": "PRELOCK-DISAGREE"}
    )

    async def _fake_discover(session: AsyncSession, filter_clause: object) -> list[uuid.UUID]:
        return [uuid.uuid4(), uuid.uuid4()]  # unconditionally "ambiguous", never real

    monkeypatch.setattr(persistence, "_discover_candidates", _fake_discover)

    natural_key = resolve_identity(job)
    raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)

    raw_ids = [raw_id]
    try:
        with pytest.raises(CandidateResolutionUnstableError):
            await persist_posting(db_engine, natural_key, job, t1, raw_id)

        async with AsyncSession(bind=db_engine) as session:
            assert (
                await session.execute(select(func.count()).select_from(Job))
            ).scalar_one() == 0  # nothing created at all

            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "fetched"
            assert raw_row.job_occurrence_id is None
    finally:
        await _cleanup(
            db_engine, user_ids=[], job_ids=[], collection_run_ids=[], raw_ingestion_ids=raw_ids
        )


async def test_post_lock_recheck_ambiguity_probe_disagreement_fails_closed(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The post-lock analog of the above: the fast probe's post-lock
    recheck reports ambiguity, but the authoritative unbounded requery
    resolves to only the one real candidate already locked — fail closed
    with `CandidateResolutionUnstableError`, never trust the disagreeing
    recheck, and mutate nothing."""
    t0 = datetime(2026, 3, 21, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    job = _load_fixture("canonical_url_match_primary").model_copy(
        update={"source_job_id": "POSTLOCK-DISAGREE"}
    )
    existing_variant = job.model_copy(update={"source_job_id": "POSTLOCK-DISAGREE-EXISTING"})

    existing_job_id = await _create_job_and_occurrence_directly(
        db_engine, existing_variant, observed_at=t0, canonical_url_normalized=job.canonical_url
    )
    fake_other_job_id = uuid.uuid4()  # never created

    real_discover = persistence._discover_candidates
    call_count = 0

    async def _fake_discover(
        session: AsyncSession, filter_clause: ColumnElement[bool]
    ) -> list[uuid.UUID]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return await real_discover(session, filter_clause)  # real: [existing_job_id]
        return [existing_job_id, fake_other_job_id]  # fake ambiguous recheck

    monkeypatch.setattr(persistence, "_discover_candidates", _fake_discover)

    natural_key = resolve_identity(job)
    raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)

    job_ids = [existing_job_id]
    raw_ids = [raw_id]
    try:
        with pytest.raises(CandidateResolutionUnstableError):
            await persist_posting(db_engine, natural_key, job, t1, raw_id)

        assert call_count == 2

        async with AsyncSession(bind=db_engine) as session:
            job_row = await session.get(Job, existing_job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t0  # untouched

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == existing_job_id)
                )
            ).scalar_one()
            assert occurrence_count == 1  # no second occurrence created

            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "fetched"
            assert raw_row.job_occurrence_id is None
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_candidate_changes_after_lock_is_detected_not_retried(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the post-lock recheck resolves to a *different* single Job than
    the one just locked, `persist_posting` must fail closed with
    `CandidateResolutionUnstableError` — never retry with the new
    candidate (that would mean acquiring a second Job's lock while still
    holding the first's, an inconsistent lock order)."""
    t0 = datetime(2026, 3, 16, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    job = _load_fixture("canonical_url_match_primary").model_copy(
        update={"source_job_id": "SWITCH-TEST"}
    )
    existing_variant = job.model_copy(update={"source_job_id": "SWITCH-EXISTING"})

    existing_job_id = await _create_job_and_occurrence_directly(
        db_engine, existing_variant, observed_at=t0, canonical_url_normalized=job.canonical_url
    )
    other_job_id = uuid.uuid4()  # never fetched — the mismatch check rejects before any lookup

    call_count = 0

    async def _fake_discover(session: AsyncSession, filter_clause: object) -> list[uuid.UUID]:
        nonlocal call_count
        call_count += 1
        return [existing_job_id] if call_count == 1 else [other_job_id]

    monkeypatch.setattr(persistence, "_discover_candidates", _fake_discover)

    natural_key = resolve_identity(job)
    raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)

    job_ids = [existing_job_id]
    raw_ids = [raw_id]
    try:
        with pytest.raises(CandidateResolutionUnstableError):
            await persist_posting(db_engine, natural_key, job, t1, raw_id)

        assert call_count == 2  # discovered once, rechecked once — never retried

        async with AsyncSession(bind=db_engine) as session:
            job_row = await session.get(Job, existing_job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t0  # unchanged

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == existing_job_id)
                )
            ).scalar_one()
            assert occurrence_count == 1  # no second occurrence created

            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "fetched"
            assert raw_row.job_occurrence_id is None
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_candidate_becomes_ambiguous_after_lock_is_detected_not_retried(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the post-lock recheck resolves to *more than one* real Job (both
    confirmed by the authoritative unbounded requery, unlike the
    disagreement tests above), persist a genuine `ambiguous_match` outcome
    instead of attaching — proving this branch is reachable even when the
    ambiguity only appears after the first candidate's lock is already
    held, not merely at initial discovery, and that the first candidate's
    lock is never used to mutate it."""
    t0 = datetime(2026, 3, 17, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    job = _load_fixture("canonical_url_match_primary").model_copy(
        update={"source_job_id": "AMBIGUOUS-RECHECK"}
    )
    existing_variant = job.model_copy(update={"source_job_id": "AMBIGUOUS-RECHECK-EXISTING"})
    other_variant = job.model_copy(update={"source_job_id": "AMBIGUOUS-RECHECK-OTHER"})

    existing_job_id = await _create_job_and_occurrence_directly(
        db_engine, existing_variant, observed_at=t0, canonical_url_normalized=job.canonical_url
    )
    other_job_id = await _create_job_and_occurrence_directly(
        db_engine, other_variant, observed_at=t0, canonical_url_normalized=job.canonical_url
    )

    call_count = 0

    async def _fake_discover(session: AsyncSession, filter_clause: object) -> list[uuid.UUID]:
        nonlocal call_count
        call_count += 1
        # The fast probe only ever "sees" one candidate on the first call
        # (as if the other row weren't visible yet), then both on recheck —
        # the authoritative `_discover_all_candidates` requery is never
        # mocked, so it always sees both real rows regardless.
        return [existing_job_id] if call_count == 1 else [existing_job_id, other_job_id]

    monkeypatch.setattr(persistence, "_discover_candidates", _fake_discover)

    natural_key = resolve_identity(job)
    raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)

    job_ids = [existing_job_id, other_job_id]
    raw_ids = [raw_id]
    try:
        outcome = await persist_posting(db_engine, natural_key, job, t1, raw_id)
        job_ids.append(outcome.job_id)  # captured before any assertion

        assert call_count == 2  # discovered once, rechecked once — never retried
        assert outcome.kind is UpsertKind.AMBIGUOUS
        assert outcome.ambiguous_candidate_job_ids == tuple(sorted([existing_job_id, other_job_id]))

        async with AsyncSession(bind=db_engine) as session:
            # The candidate whose lock was already held is never mutated.
            job_row = await session.get(Job, existing_job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t0
            other_row = await session.get(Job, other_job_id)
            assert other_row is not None
            assert other_row.last_seen_at == t0

            for candidate_id in (existing_job_id, other_job_id):
                occurrence_count = (
                    await session.execute(
                        select(func.count())
                        .select_from(JobOccurrence)
                        .where(JobOccurrence.job_id == candidate_id)
                    )
                ).scalar_one()
                assert occurrence_count == 1  # no second occurrence on either candidate

            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "identity_conflict"
            assert raw_row.job_occurrence_id == outcome.occurrence_id
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


def test_upsert_outcome_ambiguous_requires_at_least_two_candidates() -> None:
    """`UpsertOutcome.__post_init__` is the validation boundary for
    `AMBIGUOUS`'s invariants — fail closed at construction time rather
    than trusting every caller to only ever build a valid one."""
    with pytest.raises(ValueError, match="at least two candidate Job IDs"):
        UpsertOutcome(
            job_id=uuid.uuid4(),
            occurrence_id=uuid.uuid4(),
            kind=UpsertKind.AMBIGUOUS,
            ambiguous_candidate_job_ids=None,
        )
    with pytest.raises(ValueError, match="at least two candidate Job IDs"):
        UpsertOutcome(
            job_id=uuid.uuid4(),
            occurrence_id=uuid.uuid4(),
            kind=UpsertKind.AMBIGUOUS,
            ambiguous_candidate_job_ids=(uuid.uuid4(),),
        )


def test_upsert_outcome_ambiguous_requires_distinct_candidates() -> None:
    duplicate_id = uuid.uuid4()
    with pytest.raises(ValueError, match="must be distinct"):
        UpsertOutcome(
            job_id=uuid.uuid4(),
            occurrence_id=uuid.uuid4(),
            kind=UpsertKind.AMBIGUOUS,
            ambiguous_candidate_job_ids=(duplicate_id, duplicate_id),
        )


def test_upsert_outcome_ambiguous_requires_sorted_candidates() -> None:
    ids = sorted([uuid.uuid4(), uuid.uuid4()])
    unsorted = tuple(reversed(ids))
    assert unsorted[0] > unsorted[1]  # confirm the fixture is genuinely unsorted
    with pytest.raises(ValueError, match="must be sorted"):
        UpsertOutcome(
            job_id=uuid.uuid4(),
            occurrence_id=uuid.uuid4(),
            kind=UpsertKind.AMBIGUOUS,
            ambiguous_candidate_job_ids=unsorted,
        )


def test_upsert_outcome_non_ambiguous_rejects_candidate_ids() -> None:
    """A non-AMBIGUOUS outcome carrying `ambiguous_candidate_job_ids` would
    silently corrupt any caller that trusts `kind` alone (`pipeline.py`'s
    counter dispatch, `persist_posting`'s conflict-row construction) —
    reject it at construction, for every non-AMBIGUOUS kind, not just
    one."""
    for kind in (
        UpsertKind.INSERTED,
        UpsertKind.UPDATED,
        UpsertKind.QUARANTINED,
        UpsertKind.ATTACHED,
    ):
        with pytest.raises(ValueError, match="only an AMBIGUOUS outcome"):
            UpsertOutcome(
                job_id=uuid.uuid4(),
                occurrence_id=uuid.uuid4(),
                kind=kind,
                ambiguous_candidate_job_ids=(uuid.uuid4(), uuid.uuid4()),
            )


async def test_ambiguous_match_rollback_discards_all_effects_and_marks_run_failed(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure injected via the private `persistence._after_ambiguous_flush`
    seam — after the new Job, new JobOccurrence, `IdentityConflict` insert,
    and raw terminal update have all been flushed inside `persist_posting`'s
    own transaction, but before that transaction commits — must roll back
    all four effects together. Run through `pipeline.run()` so run/attempt
    failure counters can be checked too, mirroring the quarantine slice's
    own rollback-test pattern."""
    t0 = datetime(2026, 3, 22, tzinfo=UTC)
    t2 = t0 + timedelta(hours=2)
    shared_url = "https://ambiguous.example.com/jobs/rollback-shared"
    query = SourceQuery(sources=["fixture_ats"])

    base = _load_fixture("canonical_url_match_primary")
    job_x = base.model_copy(
        update={
            "source_tenant_id": "rb-tenant-x",
            "source_job_id": "RB-AMB-X",
            "canonical_url": shared_url,
        }
    )
    job_y = base.model_copy(
        update={
            "source_tenant_id": "rb-tenant-y",
            "source_job_id": "RB-AMB-Y",
            "canonical_url": shared_url,
        }
    )
    job_z = base.model_copy(
        update={
            "source_tenant_id": "rb-tenant-z",
            "source_job_id": "RB-AMB-Z",
            "canonical_url": shared_url,
            "discovered_at": t2,
        }
    )
    unrelated = _load_fixture("missing_salary_no_tenant").model_copy(update={"discovered_at": t2})

    job_ids: list[uuid.UUID] = []
    run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
    try:
        job_x_id = await _create_job_and_occurrence_directly(
            db_engine, job_x, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_y_id = await _create_job_and_occurrence_directly(
            db_engine, job_y, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_ids.extend([job_x_id, job_y_id])  # captured before any assertion

        async def _raise() -> None:
            raise RuntimeError("simulated ambiguous rollback trigger")

        monkeypatch.setattr(persistence, "_after_ambiguous_flush", _raise)

        with pytest.raises(RuntimeError, match="simulated ambiguous rollback trigger"):
            await pipeline.run(
                db_engine,
                # `unrelated` processed first (succeeds, commits its own
                # transaction) before `job_z` fails mid-transaction.
                FixtureProvider([unrelated, job_z], called_at=t2),
                query,
                observed_at=t2,
                clock=FixedClock(t2),
            )

        # `unrelated`'s own committed insert must also be tracked for
        # cleanup regardless of whether the assertions below all pass.
        async with AsyncSession(bind=db_engine) as session:
            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
        job_ids = list(set(job_ids) | (current_job_ids - preexisting_job_ids))

        async with AsyncSession(bind=db_engine) as session:
            runs = (await session.execute(select(CollectionRun))).scalars().all()
            assert len(runs) == 1
            failed_run = runs[0]
            run_ids.append(failed_run.id)
            assert failed_run.status == "failed"
            assert failed_run.jobs_discovered == 2
            assert failed_run.jobs_inserted == 1  # unrelated's already-committed insert
            assert failed_run.jobs_updated == 0  # ambiguous attempt fully rolled back

            attempts = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == failed_run.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "failed"
            assert attempts[0].jobs_inserted == 1
            assert attempts[0].jobs_updated == 0

            job_x_row = await session.get(Job, job_x_id)
            assert job_x_row is not None
            assert job_x_row.last_seen_at == t0  # unchanged — rolled back
            job_y_row = await session.get(Job, job_y_id)
            assert job_y_row is not None
            assert job_y_row.last_seen_at == t0
            for candidate_id in (job_x_id, job_y_id):
                occurrence_count = (
                    await session.execute(
                        select(func.count())
                        .select_from(JobOccurrence)
                        .where(JobOccurrence.job_id == candidate_id)
                    )
                ).scalar_one()
                assert occurrence_count == 1  # no second occurrence survived

            conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
            assert conflicts == []  # no ambiguous_match conflict row survives the rollback

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
            assert sorted(row.processing_status for row in raw_rows) == ["fetched", "normalized"]
            fetched_row = next(row for row in raw_rows if row.processing_status == "fetched")
            assert fetched_row.job_occurrence_id is None
            assert fetched_row.source_identifier == "RB-AMB-Z"

        # Only job_x, job_y, and unrelated's own new Job survive — the
        # standalone ambiguous Job for job_z was never committed.
        assert len(job_ids) == 3
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_reprocessing_terminal_ambiguous_raw_row_is_rejected(db_engine: AsyncEngine) -> None:
    """Once a raw row has transitioned to `identity_conflict` via an
    `ambiguous_match` outcome, reprocessing the same `raw_id` again must
    fail at `_validate_raw_association`'s `processing_status != 'fetched'`
    check before any mutation — never creating a second conflict row or
    touching the standalone Job/JobOccurrence already created."""
    t0 = datetime(2026, 3, 23, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    shared_url = "https://ambiguous.example.com/jobs/reprocess-shared"

    base = _load_fixture("canonical_url_match_primary")
    job_x = base.model_copy(
        update={
            "source_tenant_id": "rp-tenant-x",
            "source_job_id": "RP-AMB-X",
            "canonical_url": shared_url,
        }
    )
    job_y = base.model_copy(
        update={
            "source_tenant_id": "rp-tenant-y",
            "source_job_id": "RP-AMB-Y",
            "canonical_url": shared_url,
        }
    )
    job_z = base.model_copy(
        update={
            "source_tenant_id": "rp-tenant-z",
            "source_job_id": "RP-AMB-Z",
            "canonical_url": shared_url,
        }
    )

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        job_x_id = await _create_job_and_occurrence_directly(
            db_engine, job_x, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_y_id = await _create_job_and_occurrence_directly(
            db_engine, job_y, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_ids.extend([job_x_id, job_y_id])

        natural_key_z = resolve_identity(job_z)
        raw_id_z = await pipeline._write_fetched_row(db_engine, job_z, job_z.discovered_at)
        raw_ids.append(raw_id_z)

        first = await persist_posting(db_engine, natural_key_z, job_z, t1, raw_id_z)
        job_ids.append(first.job_id)  # captured before any assertion
        assert first.kind is UpsertKind.AMBIGUOUS

        with pytest.raises(InvalidRawIngestionAssociationError):
            await persist_posting(db_engine, natural_key_z, job_z, t1, raw_id_z)

        async with AsyncSession(bind=db_engine) as session:
            conflicts = (
                (
                    await session.execute(
                        select(IdentityConflict).where(
                            IdentityConflict.incoming_raw_job_ingestion_id == raw_id_z
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(conflicts) == 1  # never a second conflict row

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == first.job_id)
                )
            ).scalar_one()
            assert occurrence_count == 1  # no second occurrence created

            raw_row = await session.get(RawJobIngestion, raw_id_z)
            assert raw_row is not None
            assert raw_row.processing_status == "identity_conflict"  # unchanged
            assert raw_row.job_occurrence_id == first.occurrence_id
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_pipeline_persists_ambiguous_match_alongside_clean_posting_in_same_batch(
    db_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """Batch isolation: one ambiguous posting and one clean posting in the
    same provider batch — the ambiguous posting must be quarantined
    (standalone Job + `ambiguous_match` conflict) while the clean posting
    completes normally, with exact counters, raw states/links, conflict
    contents, and sanitized log events."""
    t0 = datetime(2026, 3, 24, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    shared_url = "https://ambiguous.example.com/jobs/batch-shared"
    query = SourceQuery(sources=["fixture_ats"])
    caplog.set_level(logging.INFO, logger="app.ingestion.pipeline")

    base = _load_fixture("canonical_url_match_primary")
    job_x = base.model_copy(
        update={
            "source_tenant_id": "batch-tenant-x",
            "source_job_id": "BATCH-AMB-X",
            "canonical_url": shared_url,
        }
    )
    job_y = base.model_copy(
        update={
            "source_tenant_id": "batch-tenant-y",
            "source_job_id": "BATCH-AMB-Y",
            "canonical_url": shared_url,
        }
    )
    job_z = base.model_copy(
        update={
            "source_tenant_id": "batch-tenant-z",
            "source_job_id": "BATCH-AMB-Z",
            "canonical_url": shared_url,
            "discovered_at": t1,
        }
    )
    clean = _load_fixture("missing_salary_no_tenant").model_copy(update={"discovered_at": t1})

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
    try:
        job_x_id = await _create_job_and_occurrence_directly(
            db_engine, job_x, observed_at=t0, canonical_url_normalized=shared_url
        )
        job_y_id = await _create_job_and_occurrence_directly(
            db_engine, job_y, observed_at=t0, canonical_url_normalized=shared_url
        )

        run_id = await pipeline.run(
            db_engine,
            FixtureProvider([job_z, clean], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run_id)

        # Captured immediately once the run has committed — before any of
        # the assertions below, which must not gate whether the Jobs this
        # run actually created (the standalone ambiguous Job and the clean
        # insert) get cleaned up if one of them fails.
        async with AsyncSession(bind=db_engine) as session:
            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
        job_ids = list(current_job_ids - preexisting_job_ids)

        conflict_id: uuid.UUID
        ambiguous_raw_id: uuid.UUID
        ambiguous_occurrence_id: uuid.UUID

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            assert run.status == "completed_with_errors"
            assert run.jobs_discovered == 2
            assert run.jobs_inserted == 2  # ambiguous standalone Job + clean insert
            assert run.jobs_updated == 0

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
            assert attempts[0].status == "completed"  # never "completed_with_errors"
            assert attempts[0].jobs_discovered == 2
            assert attempts[0].jobs_inserted == 2
            assert attempts[0].jobs_updated == 0

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)
            assert sorted(row.processing_status for row in raw_rows) == [
                "identity_conflict",
                "normalized",
            ]

            ambiguous_raw = next(
                row for row in raw_rows if row.processing_status == "identity_conflict"
            )
            clean_raw = next(row for row in raw_rows if row.processing_status == "normalized")
            ambiguous_raw_id = ambiguous_raw.id
            assert ambiguous_raw.job_occurrence_id is not None
            ambiguous_occurrence_id = ambiguous_raw.job_occurrence_id

            conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
            assert len(conflicts) == 1
            conflict = conflicts[0]
            conflict_id = conflict.id
            assert conflict.conflict_type == "ambiguous_match"
            assert conflict.existing_job_occurrence_id is None
            assert conflict.incoming_raw_job_ingestion_id == ambiguous_raw_id
            assert conflict.existing_value == sorted([str(job_x_id), str(job_y_id)])
            assert conflict.incoming_value == [str(ambiguous_occurrence_id)]

            ambiguous_occurrence = await session.get(JobOccurrence, ambiguous_occurrence_id)
            assert ambiguous_occurrence is not None
            assert ambiguous_occurrence.job_id not in (job_x_id, job_y_id)

            clean_occurrence = await _occurrence_by_job_id(db_engine, "987654321")
            assert clean_raw.job_occurrence_id == clean_occurrence.id

            job_x_row = await session.get(Job, job_x_id)
            assert job_x_row is not None
            assert job_x_row.last_seen_at == t0  # untouched by the batch
            job_y_row = await session.get(Job, job_y_id)
            assert job_y_row is not None
            assert job_y_row.last_seen_at == t0

        messages = [record.getMessage() for record in caplog.records]
        assert any("ingestion_run_started" in message for message in messages)
        assert any("ingestion_identity_conflict" in message for message in messages)
        assert any("ingestion_run_completed" in message for message in messages)
        warning_messages = [
            record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
        ]
        assert warning_messages == [
            f"ingestion_identity_conflict raw_ingestion_id={ambiguous_raw_id} "
            f"identity_conflict_id={conflict_id} job_occurrence_id={ambiguous_occurrence_id}"
        ]
        # No candidate evidence content ever appears in logs.
        joined_messages = "".join(messages)
        assert str(job_x_id) not in joined_messages
        assert str(job_y_id) not in joined_messages
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_pipeline_fails_closed_for_unhandled_upsert_kind(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pipeline's counter-dispatch chain must fail closed, not silently
    miscount, if `persist_posting` ever returns an outcome whose `kind`
    isn't one of the five real `UpsertKind` values — proving the final
    `else: raise AssertionError(...)` branch is reachable and that the
    run/attempt are still marked failed with no falsely successful
    counters, exactly like any other unexpected mid-run exception."""
    t1 = datetime(2026, 3, 25, tzinfo=UTC)
    job = _load_fixture("clean_tenant_scoped")
    provider = FixtureProvider([job], called_at=t1)
    query = SourceQuery(sources=["fixture_ats"])

    class _FakeOutcome:
        kind = object()  # matches none of UpsertKind's five members
        job_id = uuid.uuid4()
        occurrence_id = uuid.uuid4()
        conflict_id = None

    async def _fake_persist_posting(*args: object, **kwargs: object) -> object:
        return _FakeOutcome()

    monkeypatch.setattr(provider_execution, "persist_posting", _fake_persist_posting)

    collection_run_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    try:
        with pytest.raises(AssertionError, match="unhandled UpsertKind"):
            await pipeline.run(db_engine, provider, query, observed_at=t1, clock=FixedClock(t1))

        async with AsyncSession(bind=db_engine) as session:
            run = (await session.execute(select(CollectionRun))).scalar_one()
            collection_run_ids.append(run.id)
            assert run.status == "failed"
            assert run.jobs_discovered == 1
            assert run.jobs_inserted == 0  # never falsely counted as inserted
            assert run.jobs_updated == 0

            attempt = (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run.id
                    )
                )
            ).scalar_one()
            assert attempt.status == "failed"
            assert attempt.jobs_inserted == 0
            assert attempt.jobs_updated == 0

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)
            assert len(raw_rows) == 1
            # Never reached persist_posting's own real terminal update.
            assert raw_rows[0].processing_status == "fetched"
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=[],
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_candidate_deleted_between_discovery_and_lock_uses_real_transactions(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Genuine two-transaction race, not a monkeypatched query result:
    transaction A completes initial candidate discovery and pauses (via
    the `_before_candidate_lock` test seam); transaction B deletes and
    commits the candidate Job; transaction A resumes and attempts the Job
    lock. Must raise `CandidateResolutionUnstableError` with complete
    rollback, never mutate a stale candidate. The coordinated gather is
    bounded by a timeout and the deleting task always signals `resume` in
    `finally`, so a failure on either side cannot hang the suite; cleanup
    includes the candidate Job id best-effort even though the race itself
    is expected to delete it."""
    t0 = datetime(2026, 3, 18, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    job_existing = _load_fixture("canonical_url_match_primary").model_copy(
        update={"source_job_id": "DELETE-RACE-EXISTING"}
    )
    job_attaching = _load_fixture("canonical_url_match_primary").model_copy(
        update={"source_tenant_id": None, "source_job_id": "DELETE-RACE-ATTACH"}
    )

    existing_job_id = await _create_job_and_occurrence_directly(
        db_engine,
        job_existing,
        observed_at=t0,
        canonical_url_normalized=job_existing.canonical_url,
    )

    paused = asyncio.Event()
    resume = asyncio.Event()

    async def _pause_before_lock() -> None:
        paused.set()
        await resume.wait()

    monkeypatch.setattr(persistence, "_before_candidate_lock", _pause_before_lock)

    natural_key = resolve_identity(job_attaching)
    raw_id = await pipeline._write_fetched_row(
        db_engine, job_attaching, job_attaching.discovered_at
    )

    async def _attempt_attach() -> Exception | UpsertOutcome:
        try:
            return await persist_posting(db_engine, natural_key, job_attaching, t1, raw_id)
        except Exception as exc:  # noqa: BLE001 - captured for assertion below, not swallowed
            return exc

    async def _delete_candidate() -> None:
        await paused.wait()
        try:
            async with AsyncSession(bind=db_engine) as session:
                job_row = await session.get(Job, existing_job_id)
                assert job_row is not None
                await session.delete(job_row)
                await session.commit()
        finally:
            # Always unblocks the paused attach task, even if the delete
            # itself failed — otherwise a failure here leaves
            # `_attempt_attach()` waiting on `resume` forever.
            resume.set()

    job_ids: list[uuid.UUID] = [existing_job_id]  # best-effort cleanup even if the race fails
    raw_ids = [raw_id]
    try:
        result, _ = await asyncio.wait_for(
            asyncio.gather(_attempt_attach(), _delete_candidate()), timeout=10
        )

        assert isinstance(result, CandidateResolutionUnstableError)

        async with AsyncSession(bind=db_engine) as session:
            assert (await session.get(Job, existing_job_id)) is None  # genuinely deleted by task B

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.source_job_id == "DELETE-RACE-ATTACH")
                )
            ).scalar_one()
            assert occurrence_count == 0  # the attach never completed

            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "fetched"
            assert raw_row.job_occurrence_id is None
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_tier1_reobservation_vs_parent_deletion_uses_real_transactions_no_deadlock(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Genuine two-transaction race proving Tier 1's parent-before-child
    lock order (the review's Finding-1 correction) is deadlock-free:
    transaction A completes its unlocked existing-occurrence discovery and
    pauses (via the `_before_tier1_parent_lock` test seam) immediately
    before acquiring the parent `Job`'s row lock; transaction B deletes
    and commits that same Job (cascading to its occurrence); transaction
    A resumes and attempts the parent lock. Must raise
    `CandidateResolutionUnstableError` with complete rollback — and, the
    point of this test, must complete at all rather than deadlock. An
    earlier child-before-parent lock order could deadlock against exactly
    this kind of concurrent parent delete; the bounded timeout below turns
    a regression back to that order into a test failure instead of a hung
    suite."""
    t0 = datetime(2026, 3, 20, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    job = _load_fixture("clean_tenant_scoped").model_copy(
        update={"source_job_id": "TIER1-PARENT-DELETE-RACE"}
    )

    existing_job_id = await _create_job_and_occurrence_directly(db_engine, job, observed_at=t0)

    paused = asyncio.Event()
    resume = asyncio.Event()

    async def _pause_before_parent_lock() -> None:
        paused.set()
        await resume.wait()

    monkeypatch.setattr(persistence, "_before_tier1_parent_lock", _pause_before_parent_lock)

    natural_key = resolve_identity(job)
    raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)

    async def _attempt_reobservation() -> Exception | UpsertOutcome:
        try:
            return await persist_posting(db_engine, natural_key, job, t1, raw_id)
        except Exception as exc:  # noqa: BLE001 - captured for assertion below, not swallowed
            return exc

    async def _delete_parent() -> None:
        await paused.wait()
        try:
            async with AsyncSession(bind=db_engine) as session:
                job_row = await session.get(Job, existing_job_id)
                assert job_row is not None
                await session.delete(job_row)
                await session.commit()
        finally:
            # Always unblocks the paused reobservation task, even if the
            # delete itself failed.
            resume.set()

    job_ids: list[uuid.UUID] = [existing_job_id]  # best-effort cleanup even if the race fails
    raw_ids = [raw_id]
    try:
        result, _ = await asyncio.wait_for(
            asyncio.gather(_attempt_reobservation(), _delete_parent()), timeout=10
        )

        assert isinstance(result, CandidateResolutionUnstableError)

        async with AsyncSession(bind=db_engine) as session:
            assert (await session.get(Job, existing_job_id)) is None  # genuinely deleted by task B

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.source_job_id == "TIER1-PARENT-DELETE-RACE")
                )
            ).scalar_one()
            assert occurrence_count == 0  # cascaded away with the parent

            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "fetched"  # reobservation never completed
            assert raw_row.job_occurrence_id is None
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_tier1_reassociation_between_probe_and_lock_is_detected_not_stale(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Genuine two-transaction race proving the scalar-only initial probe
    (`_existing_occurrence_identity_query`) actually prevents a stale ORM
    identity-map read, not just a stale-`Job`-lock read: transaction A
    completes its unlocked scalar probe and pauses (via the
    `_before_tier1_parent_lock` test seam) before acquiring the parent
    `Job`'s row lock; transaction B reassigns that same occurrence's
    `job_id` to a second, independently existing Job and commits;
    transaction A resumes, locks the *original* parent (which still
    exists — this is reassociation, not deletion), then loads the
    occurrence fresh under its own `FOR UPDATE` and finds its `job_id` no
    longer matches the scalar probe. Must raise
    `CandidateResolutionUnstableError` before any mutation — if the probe
    had instead loaded the full ORM entity (the defect this test guards
    against), the session's identity map could have returned that same
    stale-`job_id` instance on the later `FOR UPDATE` load, letting the
    equality check pass against a parent that is no longer this
    occurrence's actual parent. Proves neither Job's `last_seen_at`
    advances and the raw row stays `fetched`/unlinked. This is
    defense-in-depth: no current writer reassigns `job_id` at all; only a
    documented advisory/row-lock-compliant future writer would."""
    t0 = datetime(2026, 3, 21, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    job = _load_fixture("clean_tenant_scoped").model_copy(
        update={"source_job_id": "TIER1-REASSOC-RACE"}
    )

    original_job_id = await _create_job_and_occurrence_directly(db_engine, job, observed_at=t0)

    async with AsyncSession(bind=db_engine) as session, session.begin():
        second_job = Job(
            title="Second job for reassociation race",
            first_seen_at=t0,
            last_seen_at=t0,
        )
        session.add(second_job)
        await session.flush()
        second_job_id = second_job.id

    occurrence_before = await _occurrence_by_job_id(db_engine, "TIER1-REASSOC-RACE")
    occurrence_id = occurrence_before.id

    paused = asyncio.Event()
    resume = asyncio.Event()

    async def _pause_before_parent_lock() -> None:
        paused.set()
        await resume.wait()

    monkeypatch.setattr(persistence, "_before_tier1_parent_lock", _pause_before_parent_lock)

    natural_key = resolve_identity(job)
    raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)

    async def _attempt_reobservation() -> Exception | UpsertOutcome:
        try:
            return await persist_posting(db_engine, natural_key, job, t1, raw_id)
        except Exception as exc:  # noqa: BLE001 - captured for assertion below, not swallowed
            return exc

    async def _reassign_occurrence() -> None:
        await paused.wait()
        try:
            async with AsyncSession(bind=db_engine) as session, session.begin():
                occurrence = await session.get(JobOccurrence, occurrence_id)
                assert occurrence is not None
                occurrence.job_id = second_job_id
        finally:
            # Always unblocks the paused reobservation task, even if the
            # reassignment itself failed.
            resume.set()

    job_ids: list[uuid.UUID] = [original_job_id, second_job_id]
    raw_ids = [raw_id]
    try:
        result, _ = await asyncio.wait_for(
            asyncio.gather(_attempt_reobservation(), _reassign_occurrence()), timeout=10
        )

        assert isinstance(result, CandidateResolutionUnstableError)

        async with AsyncSession(bind=db_engine) as session:
            original_job_after = await session.get(Job, original_job_id)
            assert original_job_after is not None
            assert original_job_after.last_seen_at == t0  # unchanged — reobservation never landed

            second_job_after = await session.get(Job, second_job_id)
            assert second_job_after is not None
            assert second_job_after.last_seen_at == t0  # never touched either

            occurrence_after = await session.get(JobOccurrence, occurrence_id)
            assert occurrence_after is not None
            assert occurrence_after.job_id == second_job_id  # task B's reassignment did commit
            assert occurrence_after.last_seen_at == t0  # reobservation never mutated it

            raw_row = await session.get(RawJobIngestion, raw_id)
            assert raw_row is not None
            assert raw_row.processing_status == "fetched"
            assert raw_row.job_occurrence_id is None
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=[],
            raw_ingestion_ids=raw_ids,
        )


async def test_attach_rollback_discards_all_three_effects_and_marks_run_failed(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure injected via the private `persistence._after_attach_flush`
    seam — after the existing Job's `last_seen_at` update, the new
    `JobOccurrence` insert, and the raw row's terminal update have all
    been flushed inside `persist_posting`'s own transaction, but before
    that transaction commits — must roll back all three effects
    together. Run through `pipeline.run()` so run/attempt-failure
    counters can be checked too, mirroring the evidence-mismatch slice's
    own rollback-test pattern."""
    t1 = datetime(2026, 3, 19, tzinfo=UTC)
    t2 = t1 + timedelta(hours=2)
    query = SourceQuery(sources=["fixture_ats"])

    primary = _load_fixture("canonical_url_match_primary")
    secondary = _load_fixture("canonical_url_match_secondary").model_copy(
        update={"discovered_at": t2}
    )
    unrelated = _load_fixture("tenant_requisition_match_primary").model_copy(
        update={"source_job_id": "ATTACH-ROLLBACK-UNRELATED", "discovered_at": t2}
    )

    job_ids: list[uuid.UUID] = []
    run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    async with AsyncSession(bind=db_engine) as session:
        preexisting_job_ids = set((await session.execute(select(Job.id))).scalars().all())
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([primary], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        run_ids.append(run1_id)
        occurrence_primary = await _occurrence_by_job_id(db_engine, "WID-500")

        async def _raise() -> None:
            raise RuntimeError("simulated attach rollback trigger")

        monkeypatch.setattr(persistence, "_after_attach_flush", _raise)

        with pytest.raises(RuntimeError, match="simulated attach rollback trigger"):
            await pipeline.run(
                db_engine,
                # `unrelated` (a plain insert) is processed first and
                # commits its own transaction; `secondary` (the attach)
                # fails mid-transaction.
                FixtureProvider([unrelated, secondary], called_at=t2),
                query,
                observed_at=t2,
                clock=FixedClock(t2),
            )

        async with AsyncSession(bind=db_engine) as session:
            runs = (await session.execute(select(CollectionRun))).scalars().all()
            failed_run = next(r for r in runs if r.id != run1_id)
            run_ids.append(failed_run.id)
            assert failed_run.status == "failed"
            assert failed_run.jobs_discovered == 2
            assert failed_run.jobs_inserted == 1  # unrelated's already-committed insert
            assert failed_run.jobs_updated == 0  # rolled-back attach contributes to neither

            attempts = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == failed_run.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "failed"
            assert attempts[0].jobs_inserted == 1
            assert attempts[0].jobs_updated == 0

            job_after = await session.get(Job, occurrence_primary.job_id)
            assert job_after is not None
            assert job_after.last_seen_at == t1  # unchanged — rolled back

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == occurrence_primary.job_id)
                )
            ).scalar_one()
            assert occurrence_count == 1  # no second occurrence survived

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
            assert len(raw_rows) == 3
            assert sorted(row.processing_status for row in raw_rows) == [
                "fetched",
                "normalized",
                "normalized",
            ]
            fetched_row = next(row for row in raw_rows if row.processing_status == "fetched")
            assert fetched_row.job_occurrence_id is None
            assert fetched_row.source_identifier == "987650001"

        async with AsyncSession(bind=db_engine) as session:
            current_job_ids = set((await session.execute(select(Job.id))).scalars().all())
        job_ids = list(current_job_ids - preexisting_job_ids)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_attached_occurrence_behaves_normally_under_tier1_on_resubmission(
    db_engine: AsyncEngine,
) -> None:
    """Resubmitting the *same* natural key that was originally attached
    via Tier 2 resolves through Tier 1's found branch on the second
    submission (structurally guaranteed — Tier 2/3 only ever run when
    Tier 1 finds nothing) — proving the attached occurrence behaves
    identically to any other occurrence afterward: no duplicate, no
    residual special state from having been created via Tier 2."""
    t1 = datetime(2026, 3, 20, tzinfo=UTC)
    t2 = t1 + timedelta(hours=1)
    t3 = t2 + timedelta(hours=1)
    query = SourceQuery(sources=["fixture_ats"])

    primary = _load_fixture("canonical_url_match_primary")
    secondary = _load_fixture("canonical_url_match_secondary")

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([primary], called_at=t1),
            query,
            observed_at=t1,
            clock=FixedClock(t1),
        )
        collection_run_ids.append(run1_id)
        occurrence_primary = await _occurrence_by_job_id(db_engine, "WID-500")
        job_ids.append(occurrence_primary.job_id)

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([secondary], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run2_id)
        occurrence_secondary_first = await _occurrence_by_job_id(db_engine, "987650001")
        assert occurrence_secondary_first.job_id == occurrence_primary.job_id

        run3_id = await pipeline.run(
            db_engine,
            FixtureProvider([secondary], called_at=t3),
            query,
            observed_at=t3,
            clock=FixedClock(t3),
        )
        collection_run_ids.append(run3_id)

        assert await _job_count(db_engine) == 1
        assert await _occurrence_count(db_engine) == 2  # unchanged — no third occurrence

        async with AsyncSession(bind=db_engine) as session:
            run3 = await session.get(CollectionRun, run3_id)
            assert run3 is not None
            assert run3.jobs_inserted == 0
            assert run3.jobs_updated == 1

            occurrence_secondary_after = await session.get(
                JobOccurrence, occurrence_secondary_first.id
            )
            assert occurrence_secondary_after is not None
            assert occurrence_secondary_after.id == occurrence_secondary_first.id
            assert occurrence_secondary_after.last_seen_at == t3

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )


async def test_attach_never_moves_job_last_seen_at_backward(db_engine: AsyncEngine) -> None:
    """An attach submitted with an `observed_at` earlier than the existing
    Job's current `last_seen_at` must never move it backward — mirrors
    Tier 1's own out-of-order-replay guarantee, now proven for the
    attach path."""
    t2 = datetime(2026, 3, 21, tzinfo=UTC)
    t0 = t2 - timedelta(days=1)  # older than t2, submitted after t2 was already recorded
    query = SourceQuery(sources=["fixture_ats"])

    primary = _load_fixture("canonical_url_match_primary")
    secondary = _load_fixture("canonical_url_match_secondary")

    job_ids: list[uuid.UUID] = []
    collection_run_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        run1_id = await pipeline.run(
            db_engine,
            FixtureProvider([primary], called_at=t2),
            query,
            observed_at=t2,
            clock=FixedClock(t2),
        )
        collection_run_ids.append(run1_id)
        occurrence_primary = await _occurrence_by_job_id(db_engine, "WID-500")
        job_ids.append(occurrence_primary.job_id)

        run2_id = await pipeline.run(
            db_engine,
            FixtureProvider([secondary], called_at=t0),
            query,
            observed_at=t0,
            clock=FixedClock(t0),
        )
        collection_run_ids.append(run2_id)

        async with AsyncSession(bind=db_engine) as session:
            job_row = await session.get(Job, occurrence_primary.job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t2  # unchanged — t0 < t2, never regresses

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ids.extend(row.id for row in raw_rows)
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ids,
        )
