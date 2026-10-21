"""Seed or remove labelled demo jobs for the local read-only jobs API demo
(Phase 4 S4; `docs/DECISIONS/0019-local-read-only-jobs-api.md`).

FIXTURE DATA ONLY. These rows are hand-written examples, not live Greenhouse
ingestion. Nothing here calls a provider, the network, or the ingestion
pipeline; rows are inserted directly through the ORM.

Writes only to the disposable TEST database. The target URL is resolved with
`resolve_test_database_url` and must pass `assert_is_disposable_test_database`,
so this can never write to the developer database. The API and service layer
themselves stay read-only (ADR 0019); this host-side fixture tool is the only
writer.

The rows share the test database with the pytest suite, so remove them before
running the tests:

    cd backend
    python -m scripts.seed_demo_jobs            # seed (idempotent)
    python -m scripts.seed_demo_jobs --remove   # remove exactly the demo rows

Every demo row is identified by its label: the company name
`JobGoblin <label> Co (fixture data)`, occurrence provider `demo`, source
`demo_fixture`, and source job IDs `<label>-1`, `<label>-2`, and so on.
`--remove` deletes only those rows (their jobs cascade to their occurrences).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings
from app.db.models.company import Company
from app.db.models.job import Job
from app.db.models.job_occurrence import JobOccurrence
from app.normalization.url import normalize_url
from scripts.db_safety import assert_is_disposable_test_database, resolve_test_database_url

DEMO_PROVIDER = "demo"
DEMO_SOURCE = "demo_fixture"
DEFAULT_LABEL = "DEMO"
_BASE_TIME = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

# (title suffix, company?, location_raw, country, employment_type, seniority,
#  description_clean, occurrence active flags)
_JOBS: tuple[
    tuple[str, bool, str | None, str | None, str | None, str | None, str | None, tuple[bool, ...]],
    ...,
] = (
    (
        "Senior Software Engineer",
        True,
        "Remote, United States",
        "United States",
        "full_time",
        "senior",
        "Fixture description for the local demo. Not live Greenhouse data.",
        (True, False),
    ),
    ("Staff Engineer", False, "Toronto, Canada", "Canada", None, "staff", None, (True,)),
    ("Product Designer", True, "Remote", None, None, None, None, (True,)),
    (
        "Data Engineer (no active occurrence)",
        True,
        "Berlin, Germany",
        "Germany",
        "full_time",
        None,
        None,
        (False,),
    ),
)


def company_name(label: str) -> str:
    return f"JobGoblin {label} Co (fixture data)"


def _demo_url(label: str, number: int) -> str:
    return f"https://example.invalid/{label.lower()}/jobs/{number}"


async def seed_demo_jobs(engine: AsyncEngine, label: str = DEFAULT_LABEL) -> list[uuid.UUID]:
    """Inserts the labelled demo rows unless they already exist (idempotent).
    Returns the demo job IDs, newest first."""
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        existing = (
            await session.execute(select(Company).where(Company.name == company_name(label)))
        ).scalar_one_or_none()
        if existing is not None:
            labelled = select(JobOccurrence.job_id).where(
                JobOccurrence.provider == DEMO_PROVIDER,
                JobOccurrence.source == DEMO_SOURCE,
                JobOccurrence.source_job_id.like(f"{label}-%"),
            )
            rows = (
                await session.execute(
                    select(Job.id)
                    .where(Job.id.in_(labelled))
                    .order_by(Job.last_seen_at.desc(), Job.id.desc())
                )
            ).scalars()
            return list(rows)
        company = Company(name=company_name(label))
        session.add(company)
        await session.flush()
        job_ids: list[uuid.UUID] = []
        number = 0
        for index, (
            suffix,
            with_company,
            location,
            country,
            employment,
            seniority,
            description,
            actives,
        ) in enumerate(_JOBS):
            seen = _BASE_TIME - timedelta(days=index)
            job = Job(
                company_id=company.id if with_company else None,
                title=f"{label} {suffix}",
                location_raw=location,
                country=country,
                employment_type=employment,
                seniority=seniority,
                description_clean=description,
                canonical_url=_demo_url(label, index + 1),
                first_seen_at=seen - timedelta(days=30),
                last_seen_at=seen,
            )
            session.add(job)
            await session.flush()
            job_ids.append(job.id)
            for occurrence_index, active in enumerate(actives):
                number += 1
                url = _demo_url(label, 100 + number)
                session.add(
                    JobOccurrence(
                        job_id=job.id,
                        provider=DEMO_PROVIDER,
                        source=DEMO_SOURCE,
                        source_job_id=f"{label}-{number}",
                        source_url=url,
                        source_url_normalized=normalize_url(
                            url, provider=DEMO_PROVIDER, source=DEMO_SOURCE
                        ),
                        apply_url=None,
                        is_active=active,
                        first_seen_at=seen - timedelta(days=30),
                        last_seen_at=seen - timedelta(hours=occurrence_index),
                    )
                )
        await session.commit()
        return job_ids


async def remove_demo_jobs(engine: AsyncEngine, label: str = DEFAULT_LABEL) -> int:
    """Deletes exactly the labelled demo rows. Returns the number of jobs removed."""
    async with AsyncSession(bind=engine) as session:
        job_ids = set(
            (
                await session.execute(
                    select(JobOccurrence.job_id).where(
                        JobOccurrence.provider == DEMO_PROVIDER,
                        JobOccurrence.source == DEMO_SOURCE,
                        JobOccurrence.source_job_id.like(f"{label}-%"),
                    )
                )
            ).scalars()
        )
        if job_ids:
            await session.execute(delete(Job).where(Job.id.in_(job_ids)))
        await session.execute(delete(Company).where(Company.name == company_name(label)))
        await session.commit()
        return len(job_ids)


def _test_engine() -> AsyncEngine:
    settings = get_settings()
    url = resolve_test_database_url(settings.test_database_url)
    assert_is_disposable_test_database(url, settings.database_url)
    return create_async_engine(url)


async def _main(remove: bool) -> int:
    engine = _test_engine()
    try:
        if remove:
            count = await remove_demo_jobs(engine)
            print(f"removed {count} demo jobs (fixture data) from the test database")
        else:
            ids = await seed_demo_jobs(engine)
            print("seeded demo jobs (FIXTURE DATA, not live Greenhouse ingestion):")
            for job_id in ids:
                print(f"  {job_id}")
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remove", action="store_true", help="remove the demo rows")
    args = parser.parse_args(argv)
    return asyncio.run(_main(args.remove))


if __name__ == "__main__":
    sys.exit(main())
