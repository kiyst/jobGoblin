import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import User


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_valid_user(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = make_user(email="valid@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # UUID is generated application-side.
    assert isinstance(user.id, uuid.UUID)

    fetched = await db_session.get(User, user.id)
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.email == "valid@example.com"

    # Timestamps are non-null and timezone-aware.
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


async def test_email_is_normalized_on_input(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = make_user(email="  Person@Example.COM  ")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.email == "person@example.com"


async def test_duplicate_email_differing_only_by_case_rejected(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    db_session.add(make_user(email="dup@example.com"))
    await db_session.commit()

    db_session.add(make_user(email="DUP@example.com"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()  # required to recover the session before continuing

    count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 1


async def test_direct_sql_mixed_case_email_rejected_by_normalization_check(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO users (id, email) VALUES (gen_random_uuid(), 'Mixed@Case.com')")
        )
        await db_session.commit()
    await db_session.rollback()

    count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 0


async def test_empty_email_after_normalization_rejected(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """Whitespace-only input normalizes (app-side) to "" — the DB's
    non-empty CHECK is what actually rejects it, not the validator itself."""
    db_session.add(make_user(email="   "))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_whitespace_only_email_rejected(db_session: AsyncSession) -> None:
    """Bypasses the ORM validator entirely to prove the DB constraint itself
    rejects a literal whitespace-only value, not just the app-side strip."""
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO users (id, email) VALUES (gen_random_uuid(), '   ')")
        )
        await db_session.commit()
    await db_session.rollback()


async def test_null_email_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO users (id, email) VALUES (gen_random_uuid(), NULL)")
        )
        await db_session.commit()
    await db_session.rollback()


async def test_null_id_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO users (id, email) VALUES (NULL, 'x@example.com')")
        )
        await db_session.commit()
    await db_session.rollback()


async def test_updating_a_user_advances_updated_at(db_engine: AsyncEngine) -> None:
    """PostgreSQL's `now()` is fixed for the lifetime of one transaction
    (including nested savepoints), so this test deliberately uses `db_engine`
    directly for two genuinely separate, really-committed transactions rather
    than the savepoint-isolated `db_session` fixture — otherwise "insert" and
    "update" would observe the identical `now()` value and the assertion
    would be a false negative, not a real bug. Cleans up its own row
    explicitly so nothing leaks into other tests.
    """
    async with AsyncSession(bind=db_engine) as session:
        user = User(email="advances@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        created_at = user.created_at
        first_updated_at = user.updated_at

        try:
            user.email = "advances-changed@example.com"
            await session.commit()
            await session.refresh(user)
            second_updated_at = user.updated_at

            assert second_updated_at > first_updated_at
            assert second_updated_at >= created_at
        finally:
            await session.delete(user)
            await session.commit()

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (await verify_session.execute(select(func.count()).select_from(User))).scalar_one()
        assert count == 0


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = make_user(email="tz@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    now = datetime.now(UTC)
    assert abs((now - user.created_at).total_seconds()) < 60
    assert abs((now - user.updated_at).total_seconds()) < 60
