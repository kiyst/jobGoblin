import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import CandidateProfile, User
from app.db.models.candidate_profile import REMOTE_PREFERENCES

ARRAY_FIELDS = [
    "target_role_families",
    "certifications",
    "preferred_industries",
    "excluded_industries",
    "preferred_locations",
]


async def _insert_user(
    db_session: AsyncSession, make_user: Callable[..., User], email: str
) -> User:
    user = make_user(email=email)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@asynccontextmanager
async def _real_committed_user_and_profile(
    db_engine: AsyncEngine, email: str, **profile_kwargs: object
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID, uuid.UUID]]:
    """Creates a `User` and `CandidateProfile` via real, separately-committed
    transactions on `db_engine` (not the savepoint-isolated `db_session`),
    for tests that need genuinely durable commits (e.g. to exercise
    `ON DELETE CASCADE` or observe `updated_at` actually advance). Guarantees
    cleanup even if the test body raises or leaves the session in a
    failed-transaction state — a prior version of these tests committed rows
    with no cleanup path at all, which left permanent rows in the shared
    disposable test database on any assertion failure.

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


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_valid_profile(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "profile-owner@example.com")
    user_id = user.id  # captured before any later commit expires `user`

    profile = make_candidate_profile(user_id, remote_preference="hybrid")
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    assert isinstance(profile.id, uuid.UUID)

    fetched = await db_session.get(CandidateProfile, profile.id)
    assert fetched is not None
    assert fetched.user_id == user_id
    assert fetched.remote_preference == "hybrid"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


async def test_only_one_profile_per_user(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "one-profile@example.com")
    user_id = user.id  # captured before any later commit expires `user`

    db_session.add(make_candidate_profile(user_id))
    await db_session.commit()

    db_session.add(make_candidate_profile(user_id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == 1


async def test_nonexistent_user_id_rejected(
    db_session: AsyncSession,
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    db_session.add(make_candidate_profile(uuid.uuid4()))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == 0


async def test_deleting_user_cascades_to_candidate_profile(db_engine: AsyncEngine) -> None:
    """Uses `db_engine` directly (real, separate transactions) so the
    `ON DELETE CASCADE` is actually exercised by PostgreSQL, not merely
    implied by ORM-side cascade configuration."""
    async with _real_committed_user_and_profile(
        db_engine, "cascade-owner@example.com", remote_preference="remote"
    ) as (session, user_id, profile_id):
        user = await session.get(User, user_id)
        assert user is not None
        await session.delete(user)
        await session.commit()

        assert await session.get(CandidateProfile, profile_id) is None

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(CandidateProfile))
        ).scalar_one()
        assert count == 0
        user_count = (
            await verify_session.execute(select(func.count()).select_from(User))
        ).scalar_one()
        assert user_count == 0


async def test_every_allowed_remote_preference_value_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    for value in REMOTE_PREFERENCES:
        user = await _insert_user(db_session, make_user, f"{value}@example.com")
        db_session.add(make_candidate_profile(user.id, remote_preference=value))
        await db_session.commit()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == len(REMOTE_PREFERENCES)


async def test_invalid_remote_preference_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "invalid-remote@example.com")
    db_session.add(make_candidate_profile(user.id, remote_preference="fully_remote"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_nullable_fields_default_to_none(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "nullable-fields@example.com")
    profile = make_candidate_profile(user.id)
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    assert profile.target_role_families is None
    assert profile.years_experience is None
    assert profile.education is None
    assert profile.certifications is None
    assert profile.clearance is None
    assert profile.preferred_industries is None
    assert profile.excluded_industries is None
    assert profile.preferred_locations is None
    assert profile.relocation_willingness is None
    assert profile.salary_expectation_min is None
    assert profile.salary_expectation_max is None


async def test_empty_array_is_distinct_from_null(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    """NULL means "never specified"; an explicitly stored empty array means
    "specified as none" — the two must round-trip as distinguishable
    values, not collapse to the same representation."""
    unset_user = await _insert_user(db_session, make_user, "unset-array@example.com")
    unset_profile = make_candidate_profile(unset_user.id)
    db_session.add(unset_profile)

    explicit_user = await _insert_user(db_session, make_user, "empty-array@example.com")
    explicit_profile = make_candidate_profile(explicit_user.id)
    explicit_profile.target_role_families = []
    db_session.add(explicit_profile)

    await db_session.commit()
    await db_session.refresh(unset_profile)
    await db_session.refresh(explicit_profile)

    assert unset_profile.target_role_families is None
    assert explicit_profile.target_role_families == []


@pytest.mark.parametrize("field", ARRAY_FIELDS)
async def test_appending_to_array_field_persists_after_reload(
    db_engine: AsyncEngine, field: str
) -> None:
    """A plain `ARRAY(Text)` column looks unchanged to SQLAlchemy's
    unit-of-work after an in-place `.append()` — the model wraps these
    columns with `MutableList.as_mutable` (see
    `app/db/models/candidate_profile.py`) specifically so this mutation is
    tracked and actually written on commit, instead of being silently
    dropped. Reloads from a genuinely separate session (not just
    `.refresh()` on the same object) so this proves the value was written to
    PostgreSQL, not merely echoed back from the original session's identity
    map."""
    async with _real_committed_user_and_profile(
        db_engine,
        f"array-mutate-{field}@example.com",
        remote_preference="no_preference",
        **{field: ["first"]},
    ) as (session, _user_id, profile_id):
        profile = await session.get(CandidateProfile, profile_id)
        assert profile is not None
        getattr(profile, field).append("second")
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(CandidateProfile, profile_id)
            assert reloaded is not None
            assert getattr(reloaded, field) == ["first", "second"]


async def test_relocation_willingness_null_means_unknown(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "relocation@example.com")
    profile = make_candidate_profile(user.id)
    profile.relocation_willingness = False
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    assert profile.relocation_willingness is False


@pytest.mark.parametrize(
    "field,value",
    [
        (field, value)
        for field in ("years_experience", "salary_expectation_min", "salary_expectation_max")
        for value in (0, 5)
    ],
)
async def test_non_negative_check_accepts_zero_and_positive(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    field: str,
    value: int,
) -> None:
    user = await _insert_user(db_session, make_user, f"non-negative-ok-{field}-{value}@example.com")
    profile = make_candidate_profile(user.id)
    setattr(profile, field, value)
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    assert getattr(profile, field) == value


@pytest.mark.parametrize(
    "field", ["years_experience", "salary_expectation_min", "salary_expectation_max"]
)
async def test_non_negative_check_rejects_negative_value(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    field: str,
) -> None:
    user = await _insert_user(db_session, make_user, f"non-negative-bad-{field}@example.com")
    profile = make_candidate_profile(user.id)
    setattr(profile, field, -1)
    db_session.add(profile)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == 0


async def test_salary_min_equal_to_max_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-equal@example.com")
    profile = make_candidate_profile(user.id)
    profile.salary_expectation_min = 100_000
    profile.salary_expectation_max = 100_000
    db_session.add(profile)
    await db_session.commit()  # must not raise


async def test_salary_min_less_than_max_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-range@example.com")
    profile = make_candidate_profile(user.id)
    profile.salary_expectation_min = 90_000
    profile.salary_expectation_max = 120_000
    db_session.add(profile)
    await db_session.commit()  # must not raise


async def test_salary_min_greater_than_max_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-inverted@example.com")
    profile = make_candidate_profile(user.id)
    profile.salary_expectation_min = 150_000
    profile.salary_expectation_max = 100_000
    db_session.add(profile)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == 0


async def test_salary_min_without_max_is_not_constrained_by_ordering_check(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-min-only@example.com")
    profile = make_candidate_profile(user.id)
    profile.salary_expectation_min = 150_000
    db_session.add(profile)
    await db_session.commit()  # must not raise


async def test_salary_max_without_min_is_not_constrained_by_ordering_check(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-max-only@example.com")
    profile = make_candidate_profile(user.id)
    profile.salary_expectation_max = 150_000
    db_session.add(profile)
    await db_session.commit()  # must not raise


async def test_updating_a_profile_advances_updated_at(db_engine: AsyncEngine) -> None:
    """Same rationale as `test_users.py`'s equivalent test: PostgreSQL's
    `now()` is fixed for the lifetime of one transaction (including nested
    savepoints), so this uses `db_engine` directly for two genuinely
    separate, really-committed transactions."""
    async with _real_committed_user_and_profile(
        db_engine, "updated-at@example.com", remote_preference="onsite"
    ) as (session, _user_id, profile_id):
        profile = await session.get(CandidateProfile, profile_id)
        assert profile is not None
        created_at = profile.created_at
        first_updated_at = profile.updated_at

        profile.remote_preference = "remote"
        await session.commit()
        await session.refresh(profile)
        second_updated_at = profile.updated_at

        assert second_updated_at > first_updated_at
        assert second_updated_at >= created_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(CandidateProfile))
        ).scalar_one()
        assert count == 0


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    user = await _insert_user(db_session, make_user, "tz@example.com")
    profile = make_candidate_profile(user.id)
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    now = datetime.now(UTC)
    assert abs((now - profile.created_at).total_seconds()) < 60
    assert abs((now - profile.updated_at).total_seconds()) < 60
