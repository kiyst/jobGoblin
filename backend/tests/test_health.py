import pytest
from httpx import AsyncClient

from app.config import Settings, get_settings
from app.main import app
from tests.conftest import UNREACHABLE_DATABASE_URL


async def test_health_ok(client: AsyncClient) -> None:
    """`/health` must succeed without ever touching the database."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ok_even_when_database_unreachable(client: AsyncClient) -> None:
    """`/health` stays healthy even if PostgreSQL is completely unreachable.

    This is the behavioral requirement, not just "the route doesn't call the
    DB" — force an unreachable DATABASE_URL and confirm /health is unaffected.
    """
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url=UNREACHABLE_DATABASE_URL, database_connect_timeout_seconds=1.0
    )
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_fails_cleanly_when_database_unavailable(
    client: AsyncClient, unreachable_settings: Settings
) -> None:
    """`/ready` must return a clean non-success status, not crash or hang."""
    app.dependency_overrides[get_settings] = lambda: unreachable_settings
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "unavailable"}
    # No connection details, credentials, or driver error text ever appear.
    assert "jobgoblin" not in response.text
    assert "asyncpg" not in response.text
    assert "127.0.0.1" not in response.text


async def test_ready_succeeds_when_database_available(
    client: AsyncClient, real_database_available: bool
) -> None:
    """`/ready` returns 200 when PostgreSQL is actually reachable.

    Skipped (not failed) when no PostgreSQL is reachable at the configured
    DATABASE_URL — e.g. Docker/Postgres isn't running locally. Run
    `docker compose up -d postgres` first to exercise this case.
    """
    if not real_database_available:
        pytest.skip("no reachable PostgreSQL at the configured DATABASE_URL")
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
