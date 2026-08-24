import os
from collections.abc import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import check_database_connection
from app.main import app

# The disposable database `db_engine`/`db_session` run destructive schema
# tests against — deliberately independent of `app.config.Settings`
# (DATABASE_URL), which points at the ordinary development database. See
# .env.example and README.md's "Dedicated test database" section.
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)

# Real, current name of the ordinary development database — the one database
# these tests must never be able to target, regardless of TEST_DATABASE_URL.
_DEVELOPMENT_DATABASE_NAME = "jobgoblin"


def assert_is_disposable_test_database(url: str) -> None:
    """Fail closed: refuse to run destructive database tests against
    anything that doesn't clearly look like a disposable test database.

    Raises `RuntimeError` (a hard test failure, not a skip) if the resolved
    database name is the known development database name, or doesn't contain
    "test" at all. Database tests create and drop schema/data; running them
    against `jobgoblin` would corrupt real development state.
    """
    name = make_url(url).database or ""
    if name.lower() == _DEVELOPMENT_DATABASE_NAME or "test" not in name.lower():
        raise RuntimeError(
            f"Refusing to run database tests against {url!r}: its database name "
            f"({name!r}) does not look like a disposable test database. It must "
            f"contain 'test' and must not be {_DEVELOPMENT_DATABASE_NAME!r} (the "
            "development database). Set TEST_DATABASE_URL to a database created "
            "for this purpose — see README.md's 'Dedicated test database' section."
        )


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
    """A fresh engine per test, against the dedicated disposable test
    database (`TEST_DATABASE_URL`) — never the ordinary development database.

    Function-scoped (not session-scoped) specifically to match pytest-asyncio's
    function-scoped event loop (`asyncio_default_fixture_loop_scope =
    "function"`, pyproject.toml) — a session-scoped async fixture would try to
    outlive that loop. The overhead of one engine per test is negligible at
    this suite's size.

    Requires `alembic upgrade head` to have already been run against
    `TEST_DATABASE_URL` (docs/PHASE_RISK_CHECKLIST.md's Phase 1 entry:
    PostgreSQL behavior is tested against PostgreSQL, never mocked or
    substituted) — see README.md's "Dedicated test database" section.
    """
    assert_is_disposable_test_database(TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL)
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
