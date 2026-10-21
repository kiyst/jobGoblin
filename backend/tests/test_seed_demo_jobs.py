"""Demo seed script tests (Phase 4 S4; ADR 0019), against the disposable test DB.

Each test uses its own unique label, so it never touches a manually seeded demo
(label `DEMO`), and removes exactly its own rows.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models.company import Company
from app.db.models.job import Job
from app.db.models.job_occurrence import JobOccurrence
from app.main import app
from app.services.job_read import JobReader, job_reader, open_read_only_reader
from scripts import seed_demo_jobs as demo


@pytest_asyncio.fixture
async def label(db_engine: AsyncEngine) -> AsyncIterator[str]:
    value = f"DEMOT{secrets.token_hex(3).upper()}"
    try:
        yield value
    finally:
        await demo.remove_demo_jobs(db_engine, value)


async def _count(engine: AsyncEngine, label: str) -> tuple[int, int]:
    async with AsyncSession(bind=engine) as session:
        jobs = (
            await session.execute(
                select(func.count()).select_from(Job).where(Job.title.like(f"{label} %"))
            )
        ).scalar_one()
        occurrences = (
            await session.execute(
                select(func.count())
                .select_from(JobOccurrence)
                .where(JobOccurrence.source_job_id.like(f"{label}-%"))
            )
        ).scalar_one()
        return jobs, occurrences


async def test_seed_is_labelled_idempotent_and_removable(
    db_engine: AsyncEngine, label: str
) -> None:
    first = await demo.seed_demo_jobs(db_engine, label)
    assert len(first) == 4
    assert await _count(db_engine, label) == (4, 5)
    assert await demo.seed_demo_jobs(db_engine, label) == first  # idempotent, no duplicates
    assert await _count(db_engine, label) == (4, 5)
    async with AsyncSession(bind=db_engine) as session:
        providers = set(
            (
                await session.execute(
                    select(JobOccurrence.provider, JobOccurrence.source).where(
                        JobOccurrence.source_job_id.like(f"{label}-%")
                    )
                )
            ).all()
        )
        assert providers == {("demo", "demo_fixture")}
        company = (
            await session.execute(select(Company).where(Company.name == demo.company_name(label)))
        ).scalar_one()
        assert "fixture data" in company.name
    assert await demo.remove_demo_jobs(db_engine, label) == 4
    assert await _count(db_engine, label) == (0, 0)


async def test_the_api_serves_the_seeded_fixture_rows(db_engine: AsyncEngine, label: str) -> None:
    await demo.seed_demo_jobs(db_engine, label)
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def reader_override() -> AsyncIterator[JobReader]:
        async with open_read_only_reader(maker) as reader:
            yield reader

    app.dependency_overrides[job_reader] = reader_override
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            active = (await client.get("/jobs", params={"title": label})).json()
            everything = (
                await client.get("/jobs", params={"title": label, "include_inactive": "true"})
            ).json()
            remote = (
                await client.get("/jobs", params={"title": f"{label} senior", "location": "remote"})
            ).json()
    finally:
        app.dependency_overrides.clear()
    assert len(active["items"]) == 3
    assert len(everything["items"]) == 4
    (item,) = remote["items"]
    assert item["title"] == f"{label} Senior Software Engineer"
    assert item["company"]["name"] == demo.company_name(label)


def test_the_seed_script_refuses_the_development_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin"
    monkeypatch.setattr(
        demo, "get_settings", lambda: Settings(database_url=url, test_database_url=url)
    )
    with pytest.raises(Exception):  # noqa: B017 - any refusal before an engine exists
        demo._test_engine()
