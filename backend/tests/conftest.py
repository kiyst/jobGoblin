import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import Settings, get_settings
from app.db.models import (
    CandidateProfile,
    CandidateSkill,
    Company,
    Job,
    JobOccurrence,
    SavedSearch,
    SavedSearchLocation,
    SavedSearchTitle,
    User,
)
from app.db.session import check_database_connection
from app.main import app
from app.normalization.url import normalize_url

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


@pytest.fixture
def make_candidate_skill() -> Callable[..., CandidateSkill]:
    """Factory for a valid `CandidateSkill` — tests only deviate from this
    intentionally. Takes the owning `candidate_profile_id` explicitly rather
    than creating a `CandidateProfile` itself, matching
    `make_candidate_profile`'s pattern."""

    def _make(
        candidate_profile_id: uuid.UUID,
        *,
        skill: str = "Python",
        category: str | None = None,
        priority: str = "must_have",
    ) -> CandidateSkill:
        return CandidateSkill(
            candidate_profile_id=candidate_profile_id,
            skill=skill,
            category=category,
            priority=priority,
        )

    return _make


@pytest.fixture
def make_saved_search() -> Callable[..., SavedSearch]:
    """Factory for a valid `SavedSearch` — tests only deviate from this
    intentionally. Takes the owning `user_id` explicitly, matching
    `make_candidate_profile`'s pattern."""

    def _make(
        user_id: uuid.UUID,
        *,
        name: str = "Backend roles",
        remote_rules: str = "any",
        polling_schedule: str = "manual",
    ) -> SavedSearch:
        return SavedSearch(
            user_id=user_id,
            name=name,
            remote_rules=remote_rules,
            polling_schedule=polling_schedule,
        )

    return _make


@pytest.fixture
def make_saved_search_title() -> Callable[..., SavedSearchTitle]:
    """Factory for a valid `SavedSearchTitle` — tests only deviate from this
    intentionally. Takes the owning `saved_search_id` explicitly, matching
    `make_candidate_skill`'s pattern."""

    def _make(
        saved_search_id: uuid.UUID,
        *,
        title: str = "Backend Engineer",
        is_primary: bool = False,
    ) -> SavedSearchTitle:
        return SavedSearchTitle(
            saved_search_id=saved_search_id,
            title=title,
            is_primary=is_primary,
        )

    return _make


@pytest.fixture
def make_saved_search_location() -> Callable[..., SavedSearchLocation]:
    """Factory for a valid `SavedSearchLocation` — tests only deviate from
    this intentionally. Takes the owning `saved_search_id` explicitly,
    matching `make_saved_search_title`'s pattern."""

    def _make(
        saved_search_id: uuid.UUID,
        *,
        location_text: str = "Ashburn, VA",
    ) -> SavedSearchLocation:
        return SavedSearchLocation(
            saved_search_id=saved_search_id,
            location_text=location_text,
        )

    return _make


@pytest.fixture
def make_company() -> Callable[..., Company]:
    """Factory for a valid `Company` — tests only deviate from this
    intentionally. Unlike every other factory above, `Company` has no owning
    parent row to take an id for — it is a top-level Phase 1 table."""

    def _make(
        *,
        name: str = "Acme Corp",
        domain: str | None = None,
        homepage_url: str | None = None,
        career_page_url: str | None = None,
        industry: str | None = None,
        duplicate_of_company_id: uuid.UUID | None = None,
    ) -> Company:
        return Company(
            name=name,
            domain=domain,
            homepage_url=homepage_url,
            career_page_url=career_page_url,
            industry=industry,
            duplicate_of_company_id=duplicate_of_company_id,
        )

    return _make


@asynccontextmanager
async def real_committed_company(
    db_engine: AsyncEngine, **company_kwargs: object
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID]]:
    """Creates a `Company` via a real, separately-committed transaction on
    `db_engine` (not the savepoint-isolated `db_session`), for tests that
    need a genuinely durable commit (e.g. to observe `updated_at` actually
    advance). Same failure-safe lifecycle/cleanup rationale as
    `real_committed_user_and_profile` above — cleanup always runs in a fresh
    session and fetches before deleting, so a row already removed by the
    test body itself is skipped rather than erroring.
    """
    company_kwargs.setdefault("name", "Acme Corp")

    session = AsyncSession(bind=db_engine)
    company_id: uuid.UUID | None = None
    try:
        company = Company(**company_kwargs)
        session.add(company)
        await session.commit()
        await session.refresh(company)
        company_id = company.id

        yield session, company_id
    finally:
        with suppress(Exception):
            await session.rollback()
        await session.close()

        async with AsyncSession(bind=db_engine) as cleanup_session:
            if company_id is not None:
                existing_company = await cleanup_session.get(Company, company_id)
                if existing_company is not None:
                    await cleanup_session.delete(existing_company)
                    await cleanup_session.commit()


@asynccontextmanager
async def real_committed_duplicate_company_pair(
    db_engine: AsyncEngine,
    *,
    original_kwargs: dict[str, object] | None = None,
    duplicate_kwargs: dict[str, object] | None = None,
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID]]:
    """Creates two real, separately-committed `Company` rows — an "original"
    and a "duplicate" whose `duplicate_of_company_id` points at the
    original — for tests that exercise the self-referential FK's real
    `ON DELETE SET NULL` behavior (deleting the original must clear the
    duplicate's `duplicate_of_company_id`, never cascade-delete it). Cleanup
    fetches and deletes the duplicate first, then the original, tolerating
    either already being gone (e.g. the test itself deleted the original).
    """
    resolved_original_kwargs: dict[str, object] = {"name": "Acme Corp"}
    resolved_original_kwargs.update(original_kwargs or {})
    resolved_duplicate_kwargs: dict[str, object] = {"name": "Acme Corporation"}
    resolved_duplicate_kwargs.update(duplicate_kwargs or {})

    async with real_committed_company(db_engine, **resolved_original_kwargs) as (
        session,
        original_id,
    ):
        duplicate = Company(duplicate_of_company_id=original_id, **resolved_duplicate_kwargs)
        session.add(duplicate)
        duplicate_id: uuid.UUID | None = None
        try:
            await session.commit()
            await session.refresh(duplicate)
            duplicate_id = duplicate.id

            yield session, original_id, duplicate_id
        finally:
            if duplicate_id is not None:
                with suppress(Exception):
                    await session.rollback()
                async with AsyncSession(bind=db_engine) as cleanup_session:
                    existing_duplicate = await cleanup_session.get(Company, duplicate_id)
                    if existing_duplicate is not None:
                        await cleanup_session.delete(existing_duplicate)
                        await cleanup_session.commit()


@pytest.fixture
def make_job() -> Callable[..., Job]:
    """Factory for a valid `Job` — tests only deviate from this
    intentionally. Unlike every other factory above, `first_seen_at`/
    `last_seen_at` have **no default here at all**: they describe
    observation time, not row-creation time (there is no server default on
    the columns themselves either), so every call site must supply both
    explicitly. `company_id` defaults to `None` — `Job.company_id` is
    nullable by design (docs/ARCHITECTURE.md's `DiscoveredJob.company`)."""

    def _make(
        *,
        first_seen_at: datetime,
        last_seen_at: datetime,
        company_id: uuid.UUID | None = None,
    ) -> Job:
        return Job(
            company_id=company_id,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )

    return _make


@asynccontextmanager
async def real_committed_job(
    db_engine: AsyncEngine,
    *,
    first_seen_at: datetime,
    last_seen_at: datetime,
    **job_kwargs: object,
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID]]:
    """Creates a `Job` via a real, separately-committed transaction on
    `db_engine`, for tests that need a genuinely durable commit (e.g. to
    observe `updated_at` actually advance, or to exercise `company_id`'s
    `ON DELETE RESTRICT` against a real, separately-committed `Company`
    row). Same failure-safe lifecycle/cleanup rationale as
    `real_committed_company` above.
    """
    session = AsyncSession(bind=db_engine)
    job_id: uuid.UUID | None = None
    try:
        job = Job(first_seen_at=first_seen_at, last_seen_at=last_seen_at, **job_kwargs)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

        yield session, job_id
    finally:
        with suppress(Exception):
            await session.rollback()
        await session.close()

        async with AsyncSession(bind=db_engine) as cleanup_session:
            if job_id is not None:
                existing_job = await cleanup_session.get(Job, job_id)
                if existing_job is not None:
                    await cleanup_session.delete(existing_job)
                    await cleanup_session.commit()


@pytest.fixture
def make_job_occurrence() -> Callable[..., JobOccurrence]:
    """Factory for a valid `JobOccurrence` — tests only deviate from this
    intentionally. Like `make_job`, `first_seen_at`/`last_seen_at` have no
    default at all — every call site must supply both explicitly. `job_id`
    is also required (no default): a `JobOccurrence` cannot exist without a
    real `Job` row to reference, and this factory deliberately doesn't
    create one implicitly, matching `make_candidate_profile`'s
    take-the-parent-id-explicitly pattern.

    `source_url_normalized` defaults to `normalize_url(source_url, ...)` —
    this factory is an application caller, not the model itself, so a
    "valid occurrence" by default must actually be identity-consistent,
    the same way a real ingestion write would be. A test that needs the
    model's own non-derivation behavior, or a deliberately malformed/NULL
    normalized value, overrides the attribute explicitly after
    construction (see test_job_occurrences.py)."""

    def _make(
        *,
        job_id: uuid.UUID,
        first_seen_at: datetime,
        last_seen_at: datetime,
        provider: str = "ats_scrapers",
        source: str = "greenhouse",
        source_url: str = "https://boards.greenhouse.io/acme/jobs/12345",
    ) -> JobOccurrence:
        return JobOccurrence(
            job_id=job_id,
            provider=provider,
            source=source,
            source_url=source_url,
            source_url_normalized=normalize_url(source_url, provider=provider, source=source),
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )

    return _make


@asynccontextmanager
async def real_committed_job_occurrence(
    db_engine: AsyncEngine,
    *,
    first_seen_at: datetime,
    last_seen_at: datetime,
    job_kwargs: dict[str, object] | None = None,
    **occurrence_kwargs: object,
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID]]:
    """Builds on `real_committed_job`: additionally creates a real,
    separately-committed `JobOccurrence` referencing it, with its own
    best-effort cleanup (occurrence, then — via the wrapped helper — job)
    so a partially cascaded state is skipped rather than treated as an
    error, same rationale as every other `real_committed_*` helper above.
    Same "valid by default" rationale as `make_job_occurrence`:
    `source_url_normalized` defaults to `normalize_url(source_url, ...)`
    unless the caller already passed one explicitly.
    """
    provider = str(occurrence_kwargs.setdefault("provider", "ats_scrapers"))
    source = str(occurrence_kwargs.setdefault("source", "greenhouse"))
    source_url = str(
        occurrence_kwargs.setdefault("source_url", "https://boards.greenhouse.io/acme/jobs/12345")
    )
    occurrence_kwargs.setdefault(
        "source_url_normalized", normalize_url(source_url, provider=provider, source=source)
    )

    async with real_committed_job(
        db_engine, first_seen_at=first_seen_at, last_seen_at=last_seen_at, **(job_kwargs or {})
    ) as (session, job_id):
        occurrence = JobOccurrence(
            job_id=job_id,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            **occurrence_kwargs,
        )
        session.add(occurrence)
        occurrence_id: uuid.UUID | None = None
        try:
            await session.commit()
            await session.refresh(occurrence)
            occurrence_id = occurrence.id

            yield session, job_id, occurrence_id
        finally:
            if occurrence_id is not None:
                with suppress(Exception):
                    await session.rollback()
                async with AsyncSession(bind=db_engine) as cleanup_session:
                    existing_occurrence = await cleanup_session.get(JobOccurrence, occurrence_id)
                    if existing_occurrence is not None:
                        await cleanup_session.delete(existing_occurrence)
                        await cleanup_session.commit()


@asynccontextmanager
async def real_committed_user_and_profile(
    db_engine: AsyncEngine, email: str, **profile_kwargs: object
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID]]:
    """Creates a `User` and `CandidateProfile` via real, separately-committed
    transactions on `db_engine` (not the savepoint-isolated `db_session`),
    for tests that need genuinely durable commits (e.g. to exercise
    `ON DELETE CASCADE` or observe `updated_at` actually advance). Guarantees
    cleanup even if the test body raises or leaves the session in a
    failed-transaction state — an earlier version of these tests committed
    rows with no cleanup path at all, which left permanent rows in the shared
    disposable test database on any assertion failure.

    Lives here (not in a single test module) so more than one test module
    can reuse it without importing from each other — see
    `real_committed_user_profile_and_skill` below, which builds on this.

    Captures both ids immediately after each row's own commit and yields
    plain UUIDs, not ORM attribute access after a later commit: `commit()`
    expires every attribute of every object in the session by default, and
    reading an expired attribute outside of an active await under asyncpg's
    async dialect raises `MissingGreenlet` instead of transparently
    refreshing it.

    Cleanup always runs in a fresh session (the caller's session may be
    closed, or mid-failed-transaction, by the time cleanup runs) and fetches
    each row before deleting it, so a row already removed by the test body
    itself (e.g. the profile, after its owning user was deleted and the
    delete cascaded) is skipped rather than erroring.
    """
    session = AsyncSession(bind=db_engine)
    user_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    try:
        user = User(email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

        profile = CandidateProfile(user_id=user_id, **profile_kwargs)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        profile_id = profile.id

        yield session, user_id, profile_id
    finally:
        with suppress(Exception):
            await session.rollback()
        await session.close()

        async with AsyncSession(bind=db_engine) as cleanup_session:
            if profile_id is not None:
                existing_profile = await cleanup_session.get(CandidateProfile, profile_id)
                if existing_profile is not None:
                    await cleanup_session.delete(existing_profile)
                    await cleanup_session.commit()
            if user_id is not None:
                existing_user = await cleanup_session.get(User, user_id)
                if existing_user is not None:
                    await cleanup_session.delete(existing_user)
                    await cleanup_session.commit()


@asynccontextmanager
async def real_committed_user_profile_and_skill(
    db_engine: AsyncEngine,
    email: str,
    *,
    profile_kwargs: dict[str, object] | None = None,
    **skill_kwargs: object,
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Builds on `real_committed_user_and_profile`: additionally creates a
    `CandidateSkill` row on the same real-commit lifecycle, with its own
    best-effort cleanup (skill, then — via the wrapped helper — profile,
    then user) so a partially cascaded state is skipped rather than treated
    as an error, same rationale as the wrapped helper above.
    """
    skill_kwargs.setdefault("skill", "Python")
    skill_kwargs.setdefault("priority", "must_have")
    resolved_profile_kwargs: dict[str, object] = {"remote_preference": "no_preference"}
    resolved_profile_kwargs.update(profile_kwargs or {})
    async with real_committed_user_and_profile(db_engine, email, **resolved_profile_kwargs) as (
        session,
        user_id,
        profile_id,
    ):
        skill = CandidateSkill(candidate_profile_id=profile_id, **skill_kwargs)
        session.add(skill)
        skill_id: uuid.UUID | None = None
        try:
            await session.commit()
            await session.refresh(skill)
            skill_id = skill.id

            yield session, user_id, profile_id, skill_id
        finally:
            if skill_id is not None:
                with suppress(Exception):
                    await session.rollback()
                async with AsyncSession(bind=db_engine) as cleanup_session:
                    existing_skill = await cleanup_session.get(CandidateSkill, skill_id)
                    if existing_skill is not None:
                        await cleanup_session.delete(existing_skill)
                        await cleanup_session.commit()


@asynccontextmanager
async def real_committed_user_and_saved_search(
    db_engine: AsyncEngine, email: str, **saved_search_kwargs: object
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID]]:
    """Creates a `User` and `SavedSearch` via real, separately-committed
    transactions on `db_engine`, for tests that need genuinely durable
    commits (e.g. to exercise `ON DELETE CASCADE` or observe `updated_at`
    actually advance). Same failure-safe lifecycle/cleanup rationale as
    `real_committed_user_and_profile` above.
    """
    saved_search_kwargs.setdefault("name", "Backend roles")
    saved_search_kwargs.setdefault("remote_rules", "any")
    saved_search_kwargs.setdefault("polling_schedule", "manual")

    session = AsyncSession(bind=db_engine)
    user_id: uuid.UUID | None = None
    saved_search_id: uuid.UUID | None = None
    try:
        user = User(email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

        saved_search = SavedSearch(user_id=user_id, **saved_search_kwargs)
        session.add(saved_search)
        await session.commit()
        await session.refresh(saved_search)
        saved_search_id = saved_search.id

        yield session, user_id, saved_search_id
    finally:
        with suppress(Exception):
            await session.rollback()
        await session.close()

        async with AsyncSession(bind=db_engine) as cleanup_session:
            if saved_search_id is not None:
                existing_saved_search = await cleanup_session.get(SavedSearch, saved_search_id)
                if existing_saved_search is not None:
                    await cleanup_session.delete(existing_saved_search)
                    await cleanup_session.commit()
            if user_id is not None:
                existing_user = await cleanup_session.get(User, user_id)
                if existing_user is not None:
                    await cleanup_session.delete(existing_user)
                    await cleanup_session.commit()


@asynccontextmanager
async def real_committed_user_saved_search_and_title(
    db_engine: AsyncEngine,
    email: str,
    *,
    saved_search_kwargs: dict[str, object] | None = None,
    **title_kwargs: object,
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Builds on `real_committed_user_and_saved_search`: additionally creates
    a `SavedSearchTitle` row on the same real-commit lifecycle, with its own
    best-effort cleanup (title, then — via the wrapped helper — saved
    search, then user) so a partially cascaded state is skipped rather than
    treated as an error, same rationale as the wrapped helper above.
    """
    title_kwargs.setdefault("title", "Backend Engineer")
    async with real_committed_user_and_saved_search(
        db_engine, email, **(saved_search_kwargs or {})
    ) as (session, user_id, saved_search_id):
        title = SavedSearchTitle(saved_search_id=saved_search_id, **title_kwargs)
        session.add(title)
        title_id: uuid.UUID | None = None
        try:
            await session.commit()
            await session.refresh(title)
            title_id = title.id

            yield session, user_id, saved_search_id, title_id
        finally:
            if title_id is not None:
                with suppress(Exception):
                    await session.rollback()
                async with AsyncSession(bind=db_engine) as cleanup_session:
                    existing_title = await cleanup_session.get(SavedSearchTitle, title_id)
                    if existing_title is not None:
                        await cleanup_session.delete(existing_title)
                        await cleanup_session.commit()


@asynccontextmanager
async def real_committed_user_saved_search_and_location(
    db_engine: AsyncEngine,
    email: str,
    *,
    saved_search_kwargs: dict[str, object] | None = None,
    **location_kwargs: object,
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Builds on `real_committed_user_and_saved_search`: additionally creates
    a `SavedSearchLocation` row on the same real-commit lifecycle, with its
    own best-effort cleanup (location, then — via the wrapped helper —
    saved search, then user) so a partially cascaded state is skipped
    rather than treated as an error, same rationale as the wrapped helper
    above.
    """
    location_kwargs.setdefault("location_text", "Ashburn, VA")
    async with real_committed_user_and_saved_search(
        db_engine, email, **(saved_search_kwargs or {})
    ) as (session, user_id, saved_search_id):
        location = SavedSearchLocation(saved_search_id=saved_search_id, **location_kwargs)
        session.add(location)
        location_id: uuid.UUID | None = None
        try:
            await session.commit()
            await session.refresh(location)
            location_id = location.id

            yield session, user_id, saved_search_id, location_id
        finally:
            if location_id is not None:
                with suppress(Exception):
                    await session.rollback()
                async with AsyncSession(bind=db_engine) as cleanup_session:
                    existing_location = await cleanup_session.get(SavedSearchLocation, location_id)
                    if existing_location is not None:
                        await cleanup_session.delete(existing_location)
                        await cleanup_session.commit()
