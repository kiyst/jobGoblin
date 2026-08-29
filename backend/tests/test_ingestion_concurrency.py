import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Job, JobOccurrence
from app.ingestion.identity import resolve_identity
from app.ingestion.persistence import UpsertOutcome, upsert_job_occurrence
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
        assert {outcome_a.inserted, outcome_b.inserted} == {True, False}
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
