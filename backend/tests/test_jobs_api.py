"""Local read-only jobs API tests (Phase 4 S4; ADR 0019), against the disposable
PostgreSQL test database.

Rows are real and committed, and every list assertion is scoped by a per-test
unique title marker, so rows left by any other test cannot change a result.
The `job_reader` dependency is overridden with the production
`open_read_only_reader` bound to the test engine: the same read-only,
always-rolled-back code path as in production, only the engine differs.
"""

from __future__ import annotations

import ast
import secrets
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models.company import Company
from app.db.models.job import Job
from app.db.models.job_occurrence import JobOccurrence
from app.main import app
from app.normalization.url import normalize_url
from app.services import job_read
from app.services.job_read import (
    CursorPosition,
    JobReader,
    encode_cursor,
    job_reader,
    open_read_only_reader,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

LIST_KEYS = {
    "id",
    "title",
    "company",
    "location_raw",
    "country",
    "employment_type",
    "seniority",
    "canonical_url",
    "first_seen_at",
    "last_seen_at",
    "active",
}
DETAIL_KEYS = LIST_KEYS | {"description_clean", "occurrences"}
OCCURRENCE_KEYS = {
    "provider",
    "source",
    "source_url",
    "apply_url",
    "is_active",
    "first_seen_at",
    "last_seen_at",
}
FORBIDDEN_KEYS = {
    "description_raw",
    "field_provenance",
    "raw_payload",
    "parser_version",
    "salary_min",
    "salary_max",
    "score",
    "source_tenant_id",
    "source_job_id",
    "requisition_id",
    "requisition_id_raw",
    "raw_job_ingestion_id",
    "occurrence_id",
    "applicant_count",
    "source_url_normalized",
    "canonical_url_normalized",
    "saved",
    "hidden",
    "status",
}
INVALID_QUERY = {"error": {"code": "invalid_query", "message": "Invalid query parameters"}}
INVALID_CURSOR = {"error": {"code": "invalid_cursor", "message": "Invalid pagination cursor"}}
NOT_FOUND = {"error": {"code": "job_not_found", "message": "Job not found"}}
INTERNAL = {"error": {"code": "internal_error", "message": "Internal server error"}}
T0 = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api(db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def reader_override() -> AsyncIterator[JobReader]:
        async with open_read_only_reader(maker) as reader:
            yield reader

    app.dependency_overrides[job_reader] = reader_override
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@dataclass
class Seeder:
    engine: AsyncEngine
    marker: str = field(default_factory=lambda: f"zq{secrets.token_hex(5)}")
    job_ids: list[uuid.UUID] = field(default_factory=list)
    company_ids: list[uuid.UUID] = field(default_factory=list)
    counter: int = 0

    async def company(self, name: str | None = None) -> uuid.UUID:
        async with AsyncSession(bind=self.engine, expire_on_commit=False) as session:
            company = Company(name=name or f"{self.marker} Company")
            session.add(company)
            await session.commit()
            self.company_ids.append(company.id)
            return company.id

    async def job(
        self,
        title: str | None = "Engineer",
        *,
        last_seen_at: datetime = T0,
        company_id: uuid.UUID | None = None,
        location_raw: str | None = None,
        country: str | None = None,
        employment_type: str | None = None,
        seniority: str | None = None,
        description_clean: str | None = None,
        description_raw: str | None = None,
        canonical_url: str | None = None,
        occurrences: Iterable[tuple[bool, datetime]] = ((True, T0),),
        marked: bool = True,
    ) -> uuid.UUID:
        async with AsyncSession(bind=self.engine, expire_on_commit=False) as session:
            job = Job(
                title=f"{self.marker} {title}" if marked and title is not None else title,
                company_id=company_id,
                location_raw=location_raw,
                country=country,
                employment_type=employment_type,
                seniority=seniority,
                description_clean=description_clean,
                description_raw=description_raw,
                canonical_url=canonical_url,
                first_seen_at=last_seen_at - timedelta(days=1),
                last_seen_at=last_seen_at,
            )
            if seniority is not None:
                # Present in storage, so its absence from every response is meaningful.
                job.field_provenance = {"seniority": {"source": "inferred"}}
            session.add(job)
            await session.flush()
            for active, seen in occurrences:
                self.counter += 1
                url = f"https://example.invalid/{self.marker}/jobs/{self.counter}"
                session.add(
                    JobOccurrence(
                        job_id=job.id,
                        provider="testprov",
                        source="testsrc",
                        source_tenant_id=f"{self.marker}-tenant",
                        source_job_id=f"{self.marker}-{self.counter}",
                        requisition_id_raw="REQ-SECRET",
                        source_url=url,
                        source_url_normalized=normalize_url(
                            url, provider="testprov", source="testsrc"
                        ),
                        apply_url=f"{url}/apply",
                        is_active=active,
                        first_seen_at=seen - timedelta(days=1),
                        last_seen_at=seen,
                    )
                )
            await session.commit()
            self.job_ids.append(job.id)
            return job.id

    async def cleanup(self) -> None:
        async with AsyncSession(bind=self.engine) as session:
            if self.job_ids:
                await session.execute(delete(Job).where(Job.id.in_(self.job_ids)))
            if self.company_ids:
                await session.execute(delete(Company).where(Company.id.in_(self.company_ids)))
            await session.commit()


@pytest_asyncio.fixture
async def seed(db_engine: AsyncEngine) -> AsyncIterator[Seeder]:
    seeder = Seeder(db_engine)
    try:
        yield seeder
    finally:
        await seeder.cleanup()


async def _list(api: AsyncClient, seed: Seeder, **params: str) -> Any:
    query = {"title": seed.marker, **params}
    response = await api.get("/jobs", params=query)
    assert response.status_code == 200, response.text
    return response.json()


def _ids(body: Any) -> list[str]:
    return [item["id"] for item in body["items"]]


# ---------------------------------------------------------------------------
# Response shapes and exclusions
# ---------------------------------------------------------------------------


async def test_list_and_detail_expose_exactly_the_contract_fields(
    api: AsyncClient, seed: Seeder
) -> None:
    company_id = await seed.company()
    job_id = await seed.job(
        "Senior Engineer",
        company_id=company_id,
        location_raw="Remote, United States",
        country="United States",
        employment_type="full_time",
        seniority="senior",
        description_clean="Clean text.",
        description_raw="<p>RAW-SECRET</p>",
        canonical_url="https://example.invalid/canonical",
    )
    body = await _list(api, seed)
    assert set(body) == {"items", "next_cursor"}
    (item,) = body["items"]
    assert set(item) == LIST_KEYS
    assert item["company"] == {"id": str(company_id), "name": f"{seed.marker} Company"}
    assert item["country"] == "United States"
    assert item["employment_type"] == "full_time"
    assert item["seniority"] == "senior"
    assert item["active"] is True

    detail = (await api.get(f"/jobs/{job_id}")).json()
    assert set(detail) == DETAIL_KEYS
    assert detail["description_clean"] == "Clean text."
    for occurrence in detail["occurrences"]:
        assert set(occurrence) == OCCURRENCE_KEYS
    for text in ((await api.get("/jobs", params={"title": seed.marker})).text, str(detail)):
        assert "RAW-SECRET" not in text
        assert "REQ-SECRET" not in text
        assert f"{seed.marker}-tenant" not in text
        assert "field_provenance" not in text
    flat = set(detail) | {key for o in detail["occurrences"] for key in o}
    assert not flat & FORBIDDEN_KEYS


async def test_absent_values_are_null_and_company_may_be_null(
    api: AsyncClient, seed: Seeder
) -> None:
    job_id = await seed.job("Bare")
    (item,) = (await _list(api, seed))["items"]
    for key in (
        "company",
        "location_raw",
        "country",
        "employment_type",
        "seniority",
        "canonical_url",
    ):
        assert item[key] is None, key
    detail = (await api.get(f"/jobs/{job_id}")).json()
    assert detail["description_clean"] is None
    assert detail["occurrences"][0]["apply_url"] is not None


# ---------------------------------------------------------------------------
# Active scope
# ---------------------------------------------------------------------------


async def test_active_only_by_default_and_include_inactive(api: AsyncClient, seed: Seeder) -> None:
    active_id = await seed.job("Active", occurrences=((False, T0), (True, T0)))
    inactive_id = await seed.job("Inactive", occurrences=((False, T0),))
    default = await _list(api, seed)
    assert _ids(default) == [str(active_id)]
    explicit_false = await _list(api, seed, include_inactive="false")
    assert _ids(explicit_false) == [str(active_id)]
    everything = await _list(api, seed, include_inactive="true")
    assert set(_ids(everything)) == {str(active_id), str(inactive_id)}
    flags = {item["id"]: item["active"] for item in everything["items"]}
    assert flags == {str(active_id): True, str(inactive_id): False}
    # An inactive job is still retrievable by ID.
    detail = (await api.get(f"/jobs/{inactive_id}")).json()
    assert detail["active"] is False


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


async def test_each_filter_is_case_insensitive_and_combinable(
    api: AsyncClient, seed: Seeder
) -> None:
    a = await seed.job(
        "Senior Software Engineer",
        location_raw="Remote, United States",
        country="United States",
        employment_type="full_time",
        seniority="senior",
    )
    b = await seed.job(
        "Product Designer",
        location_raw="Toronto, Canada",
        country="Canada",
        employment_type="part_time",
        seniority="staff",
    )
    assert _ids(await _list(api, seed, location="REMOTE")) == [str(a)]
    assert _ids(await _list(api, seed, country="canada")) == [str(b)]
    assert _ids(await _list(api, seed, employment_type="FULL_TIME")) == [str(a)]
    assert _ids(await _list(api, seed, seniority="Staff")) == [str(b)]
    assert _ids(await _list(api, seed, country="Canad")) == []  # exact, not substring
    response = await api.get("/jobs", params={"title": f"{seed.marker.upper()} senior SOFTWARE"})
    assert _ids(response.json()) == [str(a)]
    combined = await _list(api, seed, location="remote", employment_type="full_time")
    assert _ids(combined) == [str(a)]
    assert _ids(await _list(api, seed, location="remote", seniority="staff")) == []


async def test_filters_exclude_null_values_without_error(api: AsyncClient, seed: Seeder) -> None:
    """A NULL column never matches a filter on that column, and never errors
    (advisory review 1, finding 2)."""
    nameless = await seed.job(None, marked=False, location_raw=f"{seed.marker} City")
    placeless = await seed.job("Placeless")  # location_raw and country are NULL
    by_location = await api.get("/jobs", params={"location": seed.marker})
    assert _ids(by_location.json()) == [str(nameless)]
    both = await api.get("/jobs", params={"location": seed.marker, "title": "a"})
    assert (both.status_code, _ids(both.json())) == (200, [])
    assert _ids(await _list(api, seed, location="city")) == []
    assert _ids(await _list(api, seed, country="canada")) == []
    assert _ids(await _list(api, seed)) == [str(placeless)]


async def test_filters_are_trimmed_and_wildcards_are_literal(
    api: AsyncClient, seed: Seeder
) -> None:
    percent = await seed.job("100% remote")
    underscore = await seed.job("a_b role")
    backslash = await seed.job("back\\slash role")
    decoys = {
        "100%": await seed.job("100X remote"),
        "a_b": await seed.job("aXb role"),
        "back\\slash": await seed.job("backXslash role"),
    }
    for pattern, expected in (("100%", percent), ("a_b", underscore), ("back\\slash", backslash)):
        # Unscoped by the marker on purpose: a wildcard reading would also match
        # the decoy, so the decoy's absence proves literal matching.
        response = await api.get("/jobs", params={"title": pattern, "limit": "100"})
        hits = _ids(response.json())
        assert str(expected) in hits, pattern
        assert str(decoys[pattern]) not in hits, pattern
    for pattern, expected in (("100%", percent), ("a_b", underscore), ("back\\slash", backslash)):
        response = await api.get("/jobs", params={"title": f"  {seed.marker} {pattern}  "})
        assert _ids(response.json()) == [str(expected)], pattern


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def test_cursor_pagination_is_stable_with_equal_timestamps(
    api: AsyncClient, seed: Seeder
) -> None:
    ids = [await seed.job(f"Tie {n}") for n in range(10)]
    expected = [str(i) for i in sorted(ids, reverse=True)]  # same last_seen_at: id DESC
    for limit in ("1", "3", "25"):
        seen: list[str] = []
        cursor: str | None = None
        pages = 0
        while True:
            params = {"title": seed.marker, "limit": limit}
            if cursor:
                params["cursor"] = cursor
            body = (await api.get("/jobs", params=params)).json()
            seen += _ids(body)
            cursor = body["next_cursor"]
            pages += 1
            if cursor is None:
                break
            assert pages <= 20
        assert seen == expected, limit


async def test_ordering_is_last_seen_desc_then_id_desc(api: AsyncClient, seed: Seeder) -> None:
    older = await seed.job("Older", last_seen_at=T0 - timedelta(hours=1))
    newer = await seed.job("Newer", last_seen_at=T0 + timedelta(hours=1))
    tie_a = await seed.job("Tie A", last_seen_at=T0)
    tie_b = await seed.job("Tie B", last_seen_at=T0)
    ties = [str(i) for i in sorted((tie_a, tie_b), reverse=True)]
    assert _ids(await _list(api, seed)) == [str(newer), *ties, str(older)]


async def test_default_and_maximum_limits(api: AsyncClient, seed: Seeder) -> None:
    for n in range(101):
        await seed.job(f"Bulk {n}", last_seen_at=T0 - timedelta(seconds=n))
    default = await _list(api, seed)
    assert len(default["items"]) == 25 and default["next_cursor"] is not None
    maximum = await _list(api, seed, limit="100")
    assert len(maximum["items"]) == 100 and maximum["next_cursor"] is not None
    rest = await _list(api, seed, limit="100", cursor=maximum["next_cursor"])
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None


# ---------------------------------------------------------------------------
# Error contract (fixed, non-reflective, never 422)
# ---------------------------------------------------------------------------

ECHO = "ECHOzz9"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "-1"},
        {"limit": ECHO},
        {"limit": "1.5"},
        {"limit": "+5"},
        {"limit": "0005"},
        {"limit": ""},
        {"include_inactive": "TRUE"},
        {"include_inactive": ECHO},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"country": "x" * 65},
        {"location": f"bad\x00{ECHO}"},
        {"seniority": f"bad\n{ECHO}"},
        {"sort": ECHO},
        {ECHO: "1"},
    ],
)
async def test_invalid_query_parameters(api: AsyncClient, params: dict[str, str]) -> None:
    response = await api.get("/jobs", params=params)
    assert response.status_code == 400
    assert response.json() == INVALID_QUERY
    assert ECHO not in response.text


@pytest.mark.parametrize("name", ["title", "location", "country", "employment_type", "seniority"])
@pytest.mark.parametrize("value", ["\tEngineer", "Engineer\n", "\rEngineer\r", "\x0bEngineer"])
async def test_leading_or_trailing_control_characters_are_invalid(
    api: AsyncClient, name: str, value: str
) -> None:
    """Control characters are invalid even where trimming would remove them
    (Sol Medium formal review finding); ordinary spaces are still trimmed."""
    response = await api.get("/jobs", params={name: value})
    assert (response.status_code, response.json()) == (400, INVALID_QUERY)


async def test_ordinary_spaces_are_still_trimmed(api: AsyncClient, seed: Seeder) -> None:
    job_id = await seed.job("Spacey")
    response = await api.get("/jobs", params={"title": f"   {seed.marker} spacey   "})
    assert (response.status_code, _ids(response.json())) == (200, [str(job_id)])


async def test_repeated_parameters_are_invalid(api: AsyncClient) -> None:
    response = await api.get(f"/jobs?title=a&title={ECHO}")
    assert (response.status_code, response.json()) == (400, INVALID_QUERY)
    assert ECHO not in response.text


def _b64(text: str) -> str:
    import base64

    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        ECHO + "!",
        "a" * 257,
        _b64("not json " + ECHO),
        _b64('["list"]'),
        _b64('{"i": "' + str(uuid.uuid4()) + '"}'),
        _b64('{"i": "' + str(uuid.uuid4()) + '", "t": "2030-01-01T12:00:00+00:00", "x": 1}'),
        _b64('{"i": "' + str(uuid.uuid4()) + '", "t": "2030-01-01T12:00:00"}'),
        _b64('{"i": "' + ECHO + '", "t": "2030-01-01T12:00:00+00:00"}'),
        _b64('{"i": 5, "t": "2030-01-01T12:00:00+00:00"}'),
        # Decodes cleanly but lies outside the representable range once
        # normalized to UTC (advisory review 1, finding 1).
        _b64('{"i": "' + str(uuid.uuid4()) + '", "t": "0001-01-01T00:00:00+01:00"}'),
        _b64('{"i": "' + str(uuid.uuid4()) + '", "t": "9999-12-31T23:59:59-01:00"}'),
        _b64('{"i": "' + str(uuid.uuid4()).upper() + '", "t": "2030-01-01T12:00:00+00:00"}'),
        "%%%",
        "",
    ],
)
async def test_invalid_cursor(api: AsyncClient, cursor: str) -> None:
    response = await api.get(f"/jobs?cursor={quote(cursor, safe='')}")
    assert response.status_code == 400
    assert response.json() == INVALID_CURSOR
    assert ECHO not in response.text


async def test_invalid_query_takes_precedence_over_invalid_cursor(api: AsyncClient) -> None:
    response = await api.get("/jobs", params={"limit": "0", "cursor": "!!!"})
    assert (response.status_code, response.json()) == (400, INVALID_QUERY)


async def test_a_non_utc_cursor_is_the_same_instant(api: AsyncClient, seed: Seeder) -> None:
    """A cursor carrying a non-UTC offset denotes the same boundary instant
    (advisory review 1, findings 1-2)."""
    first = await seed.job("First", last_seen_at=T0 + timedelta(minutes=1))
    second = await seed.job("Second", last_seen_at=T0)
    shifted = (T0 + timedelta(minutes=1)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    cursor = _b64('{"i": "' + str(first) + '", "t": "' + shifted.isoformat() + '"}')
    assert _ids(await _list(api, seed, cursor=cursor)) == [str(second)]


async def test_a_valid_cursor_round_trips(api: AsyncClient, seed: Seeder) -> None:
    first = await seed.job("First", last_seen_at=T0 + timedelta(minutes=1))
    second = await seed.job("Second", last_seen_at=T0)
    cursor = encode_cursor(CursorPosition(T0 + timedelta(minutes=1), first))
    assert _ids(await _list(api, seed, cursor=cursor)) == [str(second)]


@pytest.mark.parametrize(
    "job_id",
    ["not-a-uuid", ECHO, "1234", "0" * 65, str(uuid.uuid4()) + "x", "%00"],
)
async def test_malformed_job_id_is_not_found(api: AsyncClient, job_id: str) -> None:
    response = await api.get(f"/jobs/{quote(job_id, safe='')}")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert ECHO not in response.text


async def test_missing_job_is_not_found(api: AsyncClient) -> None:
    response = await api.get(f"/jobs/{uuid.uuid4()}")
    assert (response.status_code, response.json()) == (404, NOT_FOUND)


# ---------------------------------------------------------------------------
# Detail occurrences
# ---------------------------------------------------------------------------


async def test_occurrences_are_ordered_last_seen_desc_then_id_desc(
    api: AsyncClient, seed: Seeder, db_engine: AsyncEngine
) -> None:
    job_id = await seed.job(
        "Multi",
        occurrences=(
            (True, T0 - timedelta(hours=2)),
            (False, T0),
            (True, T0),
            (True, T0 - timedelta(hours=1)),
        ),
    )
    async with AsyncSession(bind=db_engine) as session:
        rows = (
            await session.execute(
                select(
                    JobOccurrence.id, JobOccurrence.last_seen_at, JobOccurrence.source_url
                ).where(JobOccurrence.job_id == job_id)
            )
        ).all()
    expected = [url for _, _, url in sorted(rows, key=lambda r: (r[1], r[0]), reverse=True)]
    detail = (await api.get(f"/jobs/{job_id}")).json()
    assert [o["source_url"] for o in detail["occurrences"]] == expected
    assert len(expected) == 4


# ---------------------------------------------------------------------------
# Read-only guarantees
# ---------------------------------------------------------------------------


async def test_requests_never_commit_or_flush(
    api: AsyncClient, seed: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = await seed.job("Readonly")

    async def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a read-only request must never commit or flush")

    monkeypatch.setattr(AsyncSession, "commit", forbidden)
    monkeypatch.setattr(AsyncSession, "flush", forbidden)
    assert (await api.get("/jobs", params={"title": seed.marker})).status_code == 200
    assert (await api.get(f"/jobs/{job_id}")).status_code == 200


async def test_the_reader_transaction_rejects_writes(db_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with open_read_only_reader(maker) as reader:
        await reader.list_jobs(job_read.JobListQuery(title="zq-none", limit=1))
        with pytest.raises(DBAPIError, match="read-only transaction"):
            await reader._session.execute(
                insert(Company).values(id=uuid.uuid4(), name="must-not-exist")
            )


# ---------------------------------------------------------------------------
# Unexpected failures leak nothing
# ---------------------------------------------------------------------------

LEAKY = "SELECT secret FROM jobs WHERE token='SECRET-MARKER' C:\\Users\\path\\file.py"


class _ExplodingReader:
    async def list_jobs(self, query: object) -> object:
        raise RuntimeError(LEAKY)

    async def get_job(self, job_id: object) -> object:
        raise RuntimeError(LEAKY)


async def test_route_failures_return_the_fixed_generic_500(api: AsyncClient) -> None:
    async def exploding() -> AsyncIterator[object]:
        yield _ExplodingReader()

    app.dependency_overrides[job_reader] = exploding
    for path in ("/jobs?title=x", f"/jobs/{uuid.uuid4()}"):
        response = await api.get(path)
        assert (response.status_code, response.json()) == (500, INTERNAL)
        for marker in ("SECRET-MARKER", "SELECT", "Users", "file.py", "Traceback"):
            assert marker not in response.text


async def test_dependency_failures_return_a_generic_500(api: AsyncClient) -> None:
    async def failing() -> AsyncIterator[object]:
        raise RuntimeError(LEAKY)
        yield  # pragma: no cover

    app.dependency_overrides[job_reader] = failing
    for path in ("/jobs", f"/jobs/{uuid.uuid4()}"):
        response = await api.get(path)
        assert response.status_code == 500
        for marker in ("SECRET-MARKER", "SELECT", "Users", "file.py", "Traceback"):
            assert marker not in response.text


# ---------------------------------------------------------------------------
# Localhost-only Compose bindings
# ---------------------------------------------------------------------------


def test_compose_binds_backend_and_postgres_to_localhost_only() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["backend"]["ports"] == ["127.0.0.1:8000:8000"]
    assert services["postgres"]["ports"] == ["127.0.0.1:5432:5432"]


# ---------------------------------------------------------------------------
# Import boundaries
# ---------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", ["app/api/jobs.py", "app/api/deps.py"])
def test_routes_import_only_services_schemas_and_web_framework(module: str) -> None:
    for name in _imports(BACKEND_DIR / module):
        top = name.split(".")[0]
        assert top in {
            "__future__",
            "logging",
            "typing",
            "fastapi",
            "starlette",
        } or name.startswith(("app.services", "app.schemas", "app.api")), (module, name)


def test_response_schemas_import_only_stdlib_and_pydantic() -> None:
    for name in _imports(BACKEND_DIR / "app" / "schemas" / "job_read.py"):
        assert name.split(".")[0] in {"__future__", "uuid", "datetime", "pydantic"}, name


def test_read_service_performs_no_writes_and_imports_no_ingestion() -> None:
    path = BACKEND_DIR / "app" / "services" / "job_read.py"
    imports = _imports(path)
    assert not [
        n for n in imports if n.startswith(("app.ingestion", "app.providers", "app.normalization"))
    ]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not called & {
        "commit",
        "flush",
        "add",
        "delete",
        "with_for_update",
        "insert",
        "update",
        "merge",
        "add_all",
        "begin",
    }


def test_app_registers_only_the_health_and_jobs_routes() -> None:
    paths = {getattr(route, "path", None) for route in app.routes}
    api_paths = {p for p in paths if p and not p.startswith(("/docs", "/redoc", "/openapi"))}
    assert api_paths == {"/health", "/ready", "/jobs", "/jobs/{job_id}"}
    jobs_methods = {
        method
        for route in app.routes
        if getattr(route, "path", "").startswith("/jobs")
        for method in getattr(route, "methods", set())
    }
    assert jobs_methods == {"GET"}
