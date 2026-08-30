import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import IdentityConflict, Job, JobOccurrence, RawJobIngestion
from app.ingestion import pipeline
from app.ingestion.identity import resolve_identity
from app.ingestion.persistence import (
    UpsertKind,
    UpsertOutcome,
    persist_posting,
    upsert_job_occurrence,
)
from app.schemas.discovered_job import DiscoveredJob

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "discovery"


def _load_fixture(name: str) -> DiscoveredJob:
    data = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return DiscoveredJob(**data)


async def _concurrent_upsert(
    engine: AsyncEngine, job: DiscoveredJob, observed_at: datetime
) -> tuple[UpsertOutcome, UpsertOutcome]:
    natural_key = resolve_identity(job)

    async def _attempt() -> UpsertOutcome:
        async with AsyncSession(bind=engine) as session, session.begin():
            return await upsert_job_occurrence(session, natural_key, job, observed_at)

    return await asyncio.gather(_attempt(), _attempt())


@pytest.mark.parametrize(
    "fixture_name",
    ["clean_tenant_scoped", "missing_salary_no_tenant", "url_fallback_only"],
)
async def test_concurrent_identical_natural_key_produces_no_orphan_or_duplicate(
    db_engine: AsyncEngine, fixture_name: str
) -> None:
    """Two genuinely concurrent calls resolving the *same* natural key must
    never both create a `Job` — exactly one row survives, and the loser's
    call resolves to that same row rather than orphaning a speculative one
    it might otherwise have started. Covers all three natural-key forms
    (docs binding decision, point 4/7), not only the tenant-scoped one."""
    t1 = datetime(2026, 4, 1, tzinfo=UTC)
    job = _load_fixture(fixture_name)

    job_ids: list[uuid.UUID] = []
    try:
        outcome_a, outcome_b = await _concurrent_upsert(db_engine, job, t1)

        assert outcome_a.job_id == outcome_b.job_id
        assert outcome_a.occurrence_id == outcome_b.occurrence_id
        assert {outcome_a.kind, outcome_b.kind} == {UpsertKind.INSERTED, UpsertKind.UPDATED}
        job_ids.append(outcome_a.job_id)

        async with AsyncSession(bind=db_engine) as session:
            job_count = (
                await session.execute(
                    select(func.count()).select_from(Job).where(Job.id == outcome_a.job_id)
                )
            ).scalar_one()
            assert job_count == 1

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == outcome_a.job_id)
                )
            ).scalar_one()
            assert occurrence_count == 1
    finally:
        async with AsyncSession(bind=db_engine) as session:
            for job_id in job_ids:
                existing = await session.get(Job, job_id)
                if existing is not None:
                    await session.delete(existing)
            await session.commit()


async def test_concurrent_conflicting_canonical_urls_quarantine_the_loser(
    db_engine: AsyncEngine,
) -> None:
    """Two genuinely concurrent postings resolving the *same*, previously-
    absent natural key but disagreeing on canonical URL: exactly one wins
    (`INSERTED`) and the other quarantines (`QUARANTINED`) under the same
    advisory lock that already prevents duplicate/orphaned rows — never
    both inserted, never both quarantined, never a second occurrence.
    Each task creates and commits its own `RawJobIngestion` row
    independently before racing `persist_posting`, matching real
    concurrent-posting behavior (Transaction A_i always precedes B_i).
    Assertions read the actual winner back off each task's own outcome
    rather than assuming which one wins — real advisory-lock contention is
    not deterministic here."""
    t1 = datetime(2026, 4, 2, tzinfo=UTC)
    base = _load_fixture("clean_tenant_scoped")
    job_a = base.model_copy(update={"canonical_url": "https://acme.example.com/jobs/variant-a"})
    job_b = base.model_copy(update={"canonical_url": "https://acme.example.com/jobs/variant-b"})
    natural_key = resolve_identity(base)  # same natural key regardless of canonical_url

    async def _attempt(job: DiscoveredJob) -> tuple[uuid.UUID, UpsertOutcome]:
        raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)
        outcome = await persist_posting(db_engine, natural_key, job, t1, raw_id)
        return raw_id, outcome

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        (raw_id_a, outcome_a), (raw_id_b, outcome_b) = await asyncio.gather(
            _attempt(job_a), _attempt(job_b)
        )
        raw_ids.extend([raw_id_a, raw_id_b])
        job_ids.append(outcome_a.job_id)

        assert outcome_a.job_id == outcome_b.job_id
        assert outcome_a.occurrence_id == outcome_b.occurrence_id
        assert {outcome_a.kind, outcome_b.kind} == {UpsertKind.INSERTED, UpsertKind.QUARANTINED}

        # Determine winner/loser dynamically — never assume which task won.
        if outcome_a.kind is UpsertKind.INSERTED:
            winner_job, loser_job, loser_raw_id = job_a, job_b, raw_id_b
        else:
            winner_job, loser_job, loser_raw_id = job_b, job_a, raw_id_a

        async with AsyncSession(bind=db_engine) as session:
            job_count = (
                await session.execute(
                    select(func.count()).select_from(Job).where(Job.id == outcome_a.job_id)
                )
            ).scalar_one()
            assert job_count == 1
            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == outcome_a.job_id)
                )
            ).scalar_one()
            assert occurrence_count == 1

            occurrence = await session.get(JobOccurrence, outcome_a.occurrence_id)
            assert occurrence is not None
            assert occurrence.canonical_url == winner_job.canonical_url
            assert occurrence.canonical_url_normalized == winner_job.canonical_url

            raw_rows = (
                (
                    await session.execute(
                        select(RawJobIngestion).where(RawJobIngestion.id.in_([raw_id_a, raw_id_b]))
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(row.processing_status for row in raw_rows) == [
                "identity_conflict",
                "normalized",
            ]

            conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
            assert len(conflicts) == 1
            assert conflicts[0].incoming_raw_job_ingestion_id == loser_raw_id
            assert conflicts[0].existing_value == {
                "canonical_url_normalized": winner_job.canonical_url
            }
            assert conflicts[0].incoming_value == {
                "canonical_url_normalized": loser_job.canonical_url
            }
    finally:
        async with AsyncSession(bind=db_engine) as session:
            conflicts_to_remove = (
                (
                    await session.execute(
                        select(IdentityConflict).where(
                            IdentityConflict.incoming_raw_job_ingestion_id.in_(raw_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for conflict in conflicts_to_remove:
                await session.delete(conflict)
            await session.commit()

            for raw_id in raw_ids:
                existing_raw = await session.get(RawJobIngestion, raw_id)
                if existing_raw is not None:
                    await session.delete(existing_raw)
            await session.commit()

            for job_id in job_ids:
                existing_job = await session.get(Job, job_id)
                if existing_job is not None:
                    await session.delete(existing_job)
            await session.commit()


async def test_concurrent_tier2_attach_produces_no_duplicate_job(db_engine: AsyncEngine) -> None:
    """Two genuinely concurrent postings with *different* natural keys
    (so Tier 1's own lock never serializes them at all) but the same
    normalized canonical URL: exactly one wins (`INSERTED`) and the other
    attaches (`ATTACHED`) via Tier 2's own canonical-URL advisory lock —
    never two Jobs for the same real posting. Assertions read the actual
    winner back off each task's own outcome, never assuming which one
    wins."""
    t1 = datetime(2026, 4, 3, tzinfo=UTC)
    base = _load_fixture("canonical_url_match_primary")
    job_a = base.model_copy(update={"source_tenant_id": "tenant-race-a", "source_job_id": "RACE-A"})
    job_b = base.model_copy(update={"source_tenant_id": "tenant-race-b", "source_job_id": "RACE-B"})

    async def _attempt(job: DiscoveredJob) -> tuple[uuid.UUID, UpsertOutcome]:
        natural_key = resolve_identity(job)
        raw_id = await pipeline._write_fetched_row(db_engine, job, job.discovered_at)
        outcome = await persist_posting(db_engine, natural_key, job, t1, raw_id)
        return raw_id, outcome

    job_ids: list[uuid.UUID] = []
    raw_ids: list[uuid.UUID] = []
    try:
        (raw_id_a, outcome_a), (raw_id_b, outcome_b) = await asyncio.gather(
            _attempt(job_a), _attempt(job_b)
        )
        raw_ids.extend([raw_id_a, raw_id_b])
        job_ids.append(outcome_a.job_id)

        assert outcome_a.job_id == outcome_b.job_id
        assert outcome_a.occurrence_id != outcome_b.occurrence_id  # two distinct occurrences
        assert {outcome_a.kind, outcome_b.kind} == {UpsertKind.INSERTED, UpsertKind.ATTACHED}

        async with AsyncSession(bind=db_engine) as session:
            job_count = (
                await session.execute(
                    select(func.count()).select_from(Job).where(Job.id == outcome_a.job_id)
                )
            ).scalar_one()
            assert job_count == 1

            occurrence_count = (
                await session.execute(
                    select(func.count())
                    .select_from(JobOccurrence)
                    .where(JobOccurrence.job_id == outcome_a.job_id)
                )
            ).scalar_one()
            assert occurrence_count == 2  # both postings' own occurrences survive

            raw_rows = (
                (
                    await session.execute(
                        select(RawJobIngestion).where(RawJobIngestion.id.in_([raw_id_a, raw_id_b]))
                    )
                )
                .scalars()
                .all()
            )
            assert all(row.processing_status == "normalized" for row in raw_rows)
    finally:
        async with AsyncSession(bind=db_engine) as session:
            for raw_id in raw_ids:
                existing_raw = await session.get(RawJobIngestion, raw_id)
                if existing_raw is not None:
                    await session.delete(existing_raw)
            await session.commit()

            for job_id in job_ids:
                existing_job = await session.get(Job, job_id)
                if existing_job is not None:
                    await session.delete(existing_job)
            await session.commit()
