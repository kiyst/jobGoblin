import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import CandidateProfile, CandidateSkill, User
from app.db.models.candidate_skill import PRIORITIES
from tests.conftest import real_committed_user_profile_and_skill


async def _insert_user_and_profile(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    email: str,
    **profile_kwargs: object,
) -> uuid.UUID:
    """Returns the new profile's id, captured immediately after its own
    commit — `session.commit()` expires every attribute of every object in
    the session (savepoint-backed commits included), so a later commit (e.g.
    adding a skill) would otherwise expire this id before it's read, and
    touching an expired attribute outside an active await under asyncpg's
    async dialect raises `MissingGreenlet` instead of transparently
    refreshing it — the same bug the `candidate_profiles` slice hit."""
    user = make_user(email=email)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user_id = user.id

    profile = make_candidate_profile(user_id, **profile_kwargs)
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile.id


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession, profile_id: uuid.UUID, skill_sql_literal: str
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely,
    assert PostgreSQL itself rejects it, and that the session recovers."""
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO candidate_skills "
                "(id, candidate_profile_id, skill, priority) "
                f"VALUES (gen_random_uuid(), :profile_id, {skill_sql_literal}, 'must_have')"
            ).bindparams(profile_id=profile_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_valid_skill(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "skill-owner@example.com"
    )

    skill = make_candidate_skill(
        profile_id, skill="Python", category="language", priority="must_have"
    )
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    assert isinstance(skill.id, uuid.UUID)

    fetched = await db_session.get(CandidateSkill, skill.id)
    assert fetched is not None
    assert fetched.candidate_profile_id == profile_id
    assert fetched.skill == "Python"
    assert fetched.category == "language"
    assert fetched.priority == "must_have"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


async def test_skill_is_trimmed_on_input(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    """The ORM validator trims exactly the four covered whitespace
    characters, but — unlike `User._normalize_email` — never touches case."""
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "trim@example.com"
    )

    skill = make_candidate_skill(profile_id, skill="\t Kubernetes \n")
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.skill == "Kubernetes"


async def test_direct_sql_empty_skill_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "direct-empty@example.com"
    )
    await _assert_direct_sql_insert_rejected(db_session, profile_id, "''")

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 0


async def test_direct_sql_whitespace_only_skill_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    """Covered-whitespace-only (space/tab/LF/CR) reduces to '' the same way
    an empty string does."""
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "direct-whitespace@example.com"
    )
    await _assert_direct_sql_insert_rejected(db_session, profile_id, r"E'\t\n\r'")


async def test_direct_sql_non_normalized_skill_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
) -> None:
    """An otherwise-valid value that isn't already trimmed is still
    rejected — the database never trims on write, only validates that it
    already is."""
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "direct-wrapped@example.com"
    )
    await _assert_direct_sql_insert_rejected(db_session, profile_id, r"E'\tPython\n'")


async def test_direct_sql_whitespace_wrapped_duplicate_cannot_bypass_uniqueness(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    """The unique index alone can't prevent this (a whitespace-wrapped value
    hashes differently from its trimmed form) — it's the normalization CHECK
    that guarantees a wrapped duplicate can never be stored at all, so there
    is nothing left for the index to fail to catch. Mirrors
    `test_users.py`'s equivalent test for `email`."""
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "wrapped-duplicate@example.com"
    )
    db_session.add(make_candidate_skill(profile_id, skill="Python"))
    await db_session.commit()

    await _assert_direct_sql_insert_rejected(db_session, profile_id, r"E'\tPython\n'")

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 1


async def test_duplicate_skill_same_case_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "dup-same-case@example.com"
    )
    db_session.add(make_candidate_skill(profile_id, skill="Python"))
    await db_session.commit()

    db_session.add(make_candidate_skill(profile_id, skill="Python"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 1


async def test_duplicate_skill_case_insensitive_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "dup-case-insensitive@example.com"
    )
    db_session.add(make_candidate_skill(profile_id, skill="Python"))
    await db_session.commit()

    db_session.add(make_candidate_skill(profile_id, skill="python"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 1


async def test_case_is_preserved_despite_case_insensitive_uniqueness(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    """The unique index is case-insensitive (`lower(skill)`), but the stored
    value itself is never lowercased — display case must survive a
    round-trip."""
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "case-preserved@example.com"
    )
    skill = make_candidate_skill(profile_id, skill="Python")
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.skill == "Python"

    fetched = await db_session.get(CandidateSkill, skill.id)
    assert fetched is not None
    assert fetched.skill == "Python"


async def test_same_skill_different_profiles_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    """Uniqueness is scoped per profile, not global."""
    first_profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "profile-one@example.com"
    )
    second_profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "profile-two@example.com"
    )

    db_session.add(make_candidate_skill(first_profile_id, skill="Python"))
    db_session.add(make_candidate_skill(second_profile_id, skill="Python"))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 2


async def test_distinct_skills_same_profile_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "distinct-skills@example.com"
    )

    db_session.add(make_candidate_skill(profile_id, skill="Python"))
    db_session.add(make_candidate_skill(profile_id, skill="Kubernetes"))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 2


async def test_nonexistent_candidate_profile_id_rejected(
    db_session: AsyncSession,
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    db_session.add(make_candidate_skill(uuid.uuid4()))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == 0


async def test_deleting_profile_cascades_to_candidate_skill(db_engine: AsyncEngine) -> None:
    """Uses real, separately-committed transactions so the `ON DELETE
    CASCADE` from `candidate_profiles` is actually exercised by PostgreSQL,
    not merely implied by ORM-side cascade configuration."""
    async with real_committed_user_profile_and_skill(
        db_engine, "cascade-owner@example.com", skill="Python"
    ) as (session, _user_id, profile_id, skill_id):
        profile = await session.get(CandidateProfile, profile_id)
        assert profile is not None
        await session.delete(profile)
        await session.commit()

        assert await session.get(CandidateSkill, skill_id) is None

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(CandidateSkill))
        ).scalar_one()
        assert count == 0


async def test_every_allowed_priority_value_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "priorities@example.com"
    )
    for index, priority in enumerate(PRIORITIES):
        db_session.add(make_candidate_skill(profile_id, skill=f"skill-{index}", priority=priority))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(CandidateSkill))
    ).scalar_one()
    assert count == len(PRIORITIES)


async def test_invalid_priority_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "invalid-priority@example.com"
    )
    db_session.add(make_candidate_skill(profile_id, priority="nice_to_have"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_category_defaults_to_none(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "category-default@example.com"
    )
    skill = make_candidate_skill(profile_id)
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.category is None


async def test_category_is_settable_free_text(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    """`category` has no enum `CHECK` — any non-null text is accepted, not
    just the documented examples."""
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "category-freeform@example.com"
    )
    skill = make_candidate_skill(profile_id, category="something-not-in-the-examples")
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.category == "something-not-in-the-examples"


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_candidate_profile: Callable[..., CandidateProfile],
    make_candidate_skill: Callable[..., CandidateSkill],
) -> None:
    profile_id = await _insert_user_and_profile(
        db_session, make_user, make_candidate_profile, "tz@example.com"
    )
    skill = make_candidate_skill(profile_id)
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    now = datetime.now(UTC)
    assert abs((now - skill.created_at).total_seconds()) < 60
    assert abs((now - skill.updated_at).total_seconds()) < 60


async def test_updating_a_skill_advances_updated_at(db_engine: AsyncEngine) -> None:
    """Same rationale as `test_users.py`/`test_candidate_profiles.py`'s
    equivalent tests: PostgreSQL's `now()` is fixed for the lifetime of one
    transaction, so this uses real, separately-committed transactions."""
    async with real_committed_user_profile_and_skill(
        db_engine, "updated-at@example.com", skill="Python"
    ) as (session, _user_id, _profile_id, skill_id):
        skill = await session.get(CandidateSkill, skill_id)
        assert skill is not None
        created_at = skill.created_at
        first_updated_at = skill.updated_at

        skill.priority = "preferred"
        await session.commit()
        await session.refresh(skill)
        second_updated_at = skill.updated_at

        assert second_updated_at > first_updated_at
        assert second_updated_at >= created_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(CandidateSkill))
        ).scalar_one()
        assert count == 0
