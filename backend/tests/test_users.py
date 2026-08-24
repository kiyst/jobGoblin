import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import User
from tests.conftest import (
    _DEVELOPMENT_DATABASE_NAME,
    DEFAULT_TEST_DATABASE_URL,
    assert_is_disposable_test_database,
)


def test_guard_rejects_the_development_database() -> None:
    """The fail-closed guard itself is tested directly (no DB connection
    needed) — proves it actually rejects the ordinary development database
    rather than merely being trusted to."""
    with pytest.raises(RuntimeError, match="does not look like a disposable test database"):
        assert_is_disposable_test_database(
            f"postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/{_DEVELOPMENT_DATABASE_NAME}"
        )


def test_guard_rejects_a_url_with_no_test_marker() -> None:
    with pytest.raises(RuntimeError, match="does not look like a disposable test database"):
        assert_is_disposable_test_database(
            "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/some_other_db"
        )


def test_guard_accepts_the_configured_test_database() -> None:
    assert_is_disposable_test_database(DEFAULT_TEST_DATABASE_URL)  # must not raise


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


async def test_orm_path_whitespace_only_email_rejected(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """Whitespace-only input normalizes (app-side) to "" via the validator —
    the DB's not-empty CHECK is what actually rejects it from there."""
    db_session.add(make_user(email="   "))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


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


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession, email_sql_literal: str
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely,
    assert PostgreSQL itself rejects it, and that the session recovers."""
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(f"INSERT INTO users (id, email) VALUES (gen_random_uuid(), {email_sql_literal})")
        )
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_empty_email_rejected(db_session: AsyncSession) -> None:
    """ "is empty" — the not-empty CHECK rejects a literal empty string."""
    await _assert_direct_sql_insert_rejected(db_session, "''")

    count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 0


async def test_direct_sql_spaces_only_email_rejected(db_session: AsyncSession) -> None:
    """ "contains only spaces" — normalizes to '' and fails the not-empty CHECK."""
    await _assert_direct_sql_insert_rejected(db_session, "'   '")


async def test_direct_sql_tab_newline_only_email_rejected(db_session: AsyncSession) -> None:
    """ "contains only tabs/newlines" — the covered whitespace set (space, tab,
    LF, CR) reduces this to '' too, same as spaces-only."""
    await _assert_direct_sql_insert_rejected(db_session, r"E'\t\n\r'")


async def test_direct_sql_tab_newline_wrapped_lowercase_email_rejected(
    db_session: AsyncSession,
) -> None:
    """ "has leading or trailing covered whitespace" — an otherwise-valid,
    already-lowercase email is still rejected if it isn't already trimmed;
    the database never trims on write, only validates that it already is."""
    await _assert_direct_sql_insert_rejected(db_session, r"E'\tperson@example.com\n'")


async def test_direct_sql_tab_newline_wrapped_mixed_case_email_rejected(
    db_session: AsyncSession,
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, r"E'\tPerson@Example.COM\n'")


async def test_direct_sql_mixed_case_email_rejected_by_normalization_check(
    db_session: AsyncSession,
) -> None:
    """ "contains uppercase characters"."""
    await _assert_direct_sql_insert_rejected(db_session, "'Mixed@Case.com'")

    count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 0


async def test_direct_sql_whitespace_wrapped_form_cannot_coexist_with_normalized_equivalent(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """The unique index alone can't prevent this (a whitespace-wrapped value
    hashes differently from its trimmed form) — it's the normalization CHECK
    that guarantees a wrapped duplicate can never be stored at all, so there
    is nothing left for the index to fail to catch."""
    db_session.add(make_user(email="collide@example.com"))
    await db_session.commit()

    await _assert_direct_sql_insert_rejected(db_session, r"E'\tcollide@example.com\n'")

    count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 1


async def test_direct_sql_valid_normalized_email_accepted(db_session: AsyncSession) -> None:
    """The CHECK constraints aren't overly strict — a genuinely already-normalized
    value inserted directly via SQL (bypassing the ORM) is accepted."""
    await db_session.execute(
        text("INSERT INTO users (id, email) VALUES (gen_random_uuid(), 'direct@example.com')")
    )
    await db_session.commit()

    count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 1


async def test_null_email_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, "NULL")


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
