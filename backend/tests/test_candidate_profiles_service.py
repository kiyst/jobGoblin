import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import CandidateProfile, User
from app.services import candidate_profiles
from tests.conftest import real_committed_user


async def _insert_user(
    db_session: AsyncSession, make_user: Callable[..., User], email: str
) -> uuid.UUID:
    user = make_user(email=email)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user.id


# --------------------------------------------------------------------------
# create() — "seeded" proof: a profile created exclusively through the
# service, then fetched back exclusively through the service.
# --------------------------------------------------------------------------


async def test_create_persists_and_is_fetchable_through_the_service(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "cp-create@example.com")

    created = await candidate_profiles.create(
        db_session,
        user_id,
        remote_preference="hybrid",
        years_experience=5,
        education="B.S. Computer Science",
    )
    assert created.user_id == user_id
    assert created.id is not None

    fetched = await candidate_profiles.get_for_user(db_session, user_id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.remote_preference == "hybrid"
    assert fetched.years_experience == 5
    assert fetched.education == "B.S. Computer Science"


async def test_create_omits_unprovided_optional_fields_as_none(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "cp-omitted@example.com")

    created = await candidate_profiles.create(db_session, user_id, remote_preference="onsite")

    assert created.years_experience is None
    assert created.education is None
    assert created.certifications is None
    assert created.target_role_families is None
    assert created.salary_expectation_min is None
    assert created.salary_expectation_max is None


async def test_create_rejects_invalid_remote_preference_with_zero_mutation(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "cp-bad-enum@example.com")

    with pytest.raises(ValueError, match="invalid remote_preference"):
        await candidate_profiles.create(db_session, user_id, remote_preference="bogus")

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == 0


async def test_create_duplicate_user_rejected_by_database(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`CandidateProfile.user_id` is `UNIQUE` — the database itself rejects a
    second profile for the same user, not a Python-side pre-check."""
    user_id = await _insert_user(db_session, make_user, "cp-duplicate@example.com")

    await candidate_profiles.create(db_session, user_id, remote_preference="no_preference")
    await db_session.commit()  # make the first profile durable before the conflicting attempt

    with pytest.raises(IntegrityError):
        await candidate_profiles.create(db_session, user_id, remote_preference="remote")
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateProfile))
    ).scalar_one()
    assert count == 1


# --------------------------------------------------------------------------
# get_for_user()
# --------------------------------------------------------------------------


async def test_get_for_user_returns_none_when_no_profile_exists(db_session: AsyncSession) -> None:
    assert await candidate_profiles.get_for_user(db_session, uuid.uuid4()) is None


# --------------------------------------------------------------------------
# update() — validation before mutation, not-found, partial update, explicit
# None, and the database CHECK remaining the backstop for non-enum fields.
# --------------------------------------------------------------------------


async def test_update_partial_change_preserves_untouched_fields(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "cp-partial@example.com")
    await candidate_profiles.create(
        db_session,
        user_id,
        remote_preference="hybrid",
        education="B.S. Computer Science",
        years_experience=5,
    )

    updated = await candidate_profiles.update(db_session, user_id, years_experience=6)

    assert updated is not None
    assert updated.years_experience == 6
    assert updated.education == "B.S. Computer Science"  # untouched
    assert updated.remote_preference == "hybrid"  # untouched


async def test_update_can_set_a_nullable_field_explicitly_to_none(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "cp-clear@example.com")
    await candidate_profiles.create(
        db_session, user_id, remote_preference="hybrid", education="B.S."
    )

    updated = await candidate_profiles.update(db_session, user_id, education=None)

    assert updated is not None
    assert updated.education is None


async def test_update_rejects_unknown_field_with_zero_mutation(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "cp-unknown-field@example.com")
    await candidate_profiles.create(
        db_session, user_id, remote_preference="hybrid", years_experience=5
    )

    with pytest.raises(ValueError, match="cannot update fields"):
        await candidate_profiles.update(db_session, user_id, not_a_real_field="x")

    profile = await candidate_profiles.get_for_user(db_session, user_id)
    assert profile is not None
    assert profile.years_experience == 5  # unchanged


async def test_update_rejects_invalid_remote_preference_with_zero_mutation(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "cp-update-bad-enum@example.com")
    await candidate_profiles.create(db_session, user_id, remote_preference="hybrid")

    with pytest.raises(ValueError, match="invalid remote_preference"):
        await candidate_profiles.update(db_session, user_id, remote_preference="bogus")

    profile = await candidate_profiles.get_for_user(db_session, user_id)
    assert profile is not None
    assert profile.remote_preference == "hybrid"  # unchanged


async def test_update_validates_before_checking_existence(db_session: AsyncSession) -> None:
    """An invalid field name/enum value raises `ValueError` even when no
    profile exists at all for `user_id` — validation never depends on a
    fetch having succeeded first."""
    with pytest.raises(ValueError, match="cannot update fields"):
        await candidate_profiles.update(db_session, uuid.uuid4(), not_a_real_field="x")


async def test_update_returns_none_when_profile_missing(db_session: AsyncSession) -> None:
    assert await candidate_profiles.update(db_session, uuid.uuid4(), years_experience=1) is None


async def test_update_database_rejects_invalid_check_backed_value(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`years_experience_non_negative` is a database `CHECK`, not
    re-validated in Python by `update()` — a negative value is only caught
    when the service's internal `flush()` runs."""
    user_id = await _insert_user(db_session, make_user, "cp-check-backstop@example.com")
    await candidate_profiles.create(db_session, user_id, remote_preference="hybrid")

    with pytest.raises(IntegrityError):
        await candidate_profiles.update(db_session, user_id, years_experience=-1)
    await db_session.rollback()


async def test_update_database_rejects_ordering_check_across_two_columns(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`salary_expectation_min_le_max` is a cross-column database `CHECK`,
    not re-validated in Python — raising `salary_expectation_min` above the
    row's own existing `salary_expectation_max` is only caught at
    `flush()`."""
    user_id = await _insert_user(db_session, make_user, "cp-ordering-backstop@example.com")
    await candidate_profiles.create(
        db_session,
        user_id,
        remote_preference="hybrid",
        salary_expectation_min=50_000,
        salary_expectation_max=100_000,
    )

    with pytest.raises(IntegrityError):
        await candidate_profiles.update(db_session, user_id, salary_expectation_min=150_000)
    await db_session.rollback()


# --------------------------------------------------------------------------
# Transaction ownership: flush, not commit; caller controls commit/rollback.
# --------------------------------------------------------------------------


async def test_create_and_update_flush_without_committing_caller_controls_transaction(
    db_engine: AsyncEngine,
) -> None:
    async with real_committed_user(db_engine, "cp-service-flush@example.com") as (session, user_id):
        created = await candidate_profiles.create(session, user_id, remote_preference="hybrid")
        profile_id = created.id

        # Flushed: visible within the same still-open transaction.
        same_session_view = await candidate_profiles.get_for_user(session, user_id)
        assert same_session_view is not None
        assert same_session_view.id == profile_id

        # Not committed: a genuinely separate session/connection must not see it.
        async with AsyncSession(bind=db_engine) as other_session:
            other_view = await other_session.get(CandidateProfile, profile_id)
            assert other_view is None

        await session.commit()  # make the profile durable for the update half below

        updated = await candidate_profiles.update(session, user_id, years_experience=3)
        assert updated is not None

        same_session_after_update = await candidate_profiles.get_for_user(session, user_id)
        assert same_session_after_update is not None
        assert same_session_after_update.years_experience == 3

        async with AsyncSession(bind=db_engine) as other_session:
            other_view = await other_session.get(CandidateProfile, profile_id)
            assert other_view is not None
            assert other_view.years_experience is None  # update() not yet committed

        await session.rollback()

        async with AsyncSession(bind=db_engine) as verify_session:
            rolled_back = await verify_session.get(CandidateProfile, profile_id)
            assert rolled_back is not None
            assert rolled_back.years_experience is None
