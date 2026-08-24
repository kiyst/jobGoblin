import uuid
from collections.abc import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import Settings, get_settings
from app.db.models import CandidateProfile, User
from app.db.session import check_database_connection
from app.main import app

# The disposable database `db_engine`/`db_session` run destructive schema
# tests against. Only used as a fallback when `Settings.test_database_url`
# (loaded from `.env`/`TEST_DATABASE_URL`, same mechanism as every other
# setting — see app/config.py) isn't set. See .env.example and README.md's
# "Dedicated test database" section.
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test"


def _redact(url: str | URL) -> str:
    """A safe-to-print form of a database URL: driver/host/port/database
    only — never username or password. Used anywhere a misconfigured URL
    might otherwise end up in a raised exception or test output."""
    parsed = url if isinstance(url, URL) else make_url(url)
    return f"{parsed.drivername}://{parsed.host}:{parsed.port}/{parsed.database}"


def assert_is_disposable_test_database(test_url: str, development_url: str) -> None:
    """Fail closed: refuse to run destructive database tests against
    anything that doesn't clearly look like a disposable test database,
    *distinct from the actually-configured development database*.

    Raises `RuntimeError` (a hard test failure, not a skip) if either:
    - `test_url`'s database name equals `development_url`'s database name
      (case-insensitive) — compared by **name alone**, deliberately ignoring
      host, port, credentials, or driver spelling. A first version of this
      guard compared `(host, port, database)` tuples, which let a
      `localhost` test URL and a `127.0.0.1` development URL — or an
      explicit `:5432` versus an omitted default port — pass as "different"
      even when they resolve to the exact same server. Two different
      connection strings can reach the same database in more ways than can
      be reliably enumerated, so this guard doesn't try: it's deliberately
      conservative and rejects on name match alone, accepting that a
      same-named database on a genuinely separate server will also be
      rejected. For a fail-closed guard protecting against irreversible
      schema/data loss, an occasional false rejection is the correct
      trade-off against a false acceptance.
    - `test_url`'s database name doesn't contain "test" at all.

    Database tests create and drop schema/data; running them against
    whatever `DATABASE_URL` actually points at — the real check, not a
    hardcoded name — would corrupt real development state. Never includes a
    raw, credential-bearing URL in the raised message; see `_redact` above.
    """
    test_parsed = make_url(test_url)
    dev_parsed = make_url(development_url)

    test_name = (test_parsed.database or "").lower()
    dev_name = (dev_parsed.database or "").lower()

    same_name_as_development = test_name == dev_name
    missing_test_marker = "test" not in test_name

    if same_name_as_development or missing_test_marker:
        reasons = []
        if same_name_as_development:
            reasons.append(
                "its database name matches the configured development database's "
                f"name ({_redact(dev_parsed)})"
            )
        if missing_test_marker:
            reasons.append("its database name does not contain 'test'")
        raise RuntimeError(
            f"Refusing to run database tests against {_redact(test_parsed)}: "
            + " and ".join(reasons)
            + ". Set TEST_DATABASE_URL to a distinct, clearly-named disposable "
            "test database — see README.md's 'Dedicated test database' section."
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
    database — never the ordinary development database.

    The test database URL comes from `Settings.test_database_url`
    (`app.config`), loaded from `.env`/`TEST_DATABASE_URL` through the same
    mechanism as every other setting, falling back to
    `DEFAULT_TEST_DATABASE_URL` only if unset — not a separate
    `os.environ.get` bypassing the project's usual configuration loading.

    Function-scoped (not session-scoped) specifically to match pytest-asyncio's
    function-scoped event loop (`asyncio_default_fixture_loop_scope =
    "function"`, pyproject.toml) — a session-scoped async fixture would try to
    outlive that loop. The overhead of one engine per test is negligible at
    this suite's size.

    Requires `alembic upgrade head` to have already been run against the test
    database (docs/PHASE_RISK_CHECKLIST.md's Phase 1 entry: PostgreSQL
    behavior is tested against PostgreSQL, never mocked or substituted) — see
    README.md's "Dedicated test database" section.
    """
    settings = get_settings()
    test_url = settings.test_database_url or DEFAULT_TEST_DATABASE_URL
    assert_is_disposable_test_database(test_url, settings.database_url)
    engine = create_async_engine(test_url)
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


@pytest.fixture
def make_candidate_profile() -> Callable[..., CandidateProfile]:
    """Factory for a valid `CandidateProfile` — tests only deviate from this
    intentionally. Takes the owning `user_id` explicitly rather than creating
    a `User` itself, so callers control and can inspect that row (e.g. to
    delete it and observe the cascade)."""

    def _make(
        user_id: uuid.UUID,
        *,
        remote_preference: str = "no_preference",
    ) -> CandidateProfile:
        return CandidateProfile(user_id=user_id, remote_preference=remote_preference)

    return _make
