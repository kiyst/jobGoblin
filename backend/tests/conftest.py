from collections.abc import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import check_database_connection
from app.main import app

# Deliberately unroutable-fast: port 1 on loopback refuses connections
# immediately on every platform this runs on, so the "database unavailable"
# test fails fast rather than waiting out a timeout. No public internet
# address is ever contacted by this suite.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@127.0.0.1:1/jobgoblin"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def unreachable_settings() -> Settings:
    return Settings(database_url=UNREACHABLE_DATABASE_URL, database_connect_timeout_seconds=1.0)


@pytest_asyncio.fixture
async def real_database_available() -> bool:
    """True if the configured DATABASE_URL is actually reachable right now.

    Used to skip the database-available `/ready` test cleanly when no
    PostgreSQL is running locally (e.g. Docker isn't available) rather than
    failing the whole suite — the database-unavailable case is what proves
    the failure path, and doesn't depend on this.
    """
    try:
        await check_database_connection(get_settings())
    except Exception:
        return False
    return True


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    """A fresh engine per test, against the real dev PostgreSQL.

    Function-scoped (not session-scoped) specifically to match pytest-asyncio's
    function-scoped event loop (`asyncio_default_fixture_loop_scope =
    "function"`, pyproject.toml) — a session-scoped async fixture would try to
    outlive that loop. The overhead of one engine per test is negligible at
    this suite's size.

    Requires `alembic upgrade head` to have already been run against this
    database (docs/PHASE_RISK_CHECKLIST.md's Phase 1 entry: PostgreSQL
    behavior is tested against PostgreSQL, never mocked or substituted).
    """
    engine = create_async_engine(get_settings().database_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """One isolated transaction per test.

    Everything the test does — including any `session.commit()` — happens
    inside a SAVEPOINT nested in an outer transaction on a single checked-out
    connection; the outer transaction is always rolled back at teardown, so
    no test's rows ever persist or leak into another test's view of the
    database. A test that needs to see genuinely separate, real transactions
    (e.g. to observe `now()` advance between commits — Postgres's `now()` is
    fixed for the lifetime of one transaction, savepoints included) should use
    `db_engine` directly instead and clean up its own rows explicitly.
    """
    async with db_engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint") as session:
            yield session
        await conn.rollback()


@pytest.fixture
def make_user() -> Callable[..., User]:
    """Factory for a valid `User` — tests only deviate from this intentionally."""

    def _make(email: str = "person@example.com") -> User:
        return User(email=email)

    return _make
