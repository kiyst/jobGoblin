import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import SavedSearch, SavedSearchTitle, User
from tests.conftest import real_committed_user_saved_search_and_title


async def _insert_saved_search(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    email: str,
) -> uuid.UUID:
    """Returns the new saved search's id, captured immediately after its own
    commit — `session.commit()` expires every attribute of every object in
    the session (savepoint-backed commits included), so a later commit (e.g.
    adding a title) would otherwise expire this id before it's read."""
    user = make_user(email=email)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user_id = user.id

    saved_search = make_saved_search(user_id)
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)
    return saved_search.id


async def _assert_direct_sql_title_insert_rejected(
    db_session: AsyncSession, saved_search_id: uuid.UUID, title_sql_literal: str
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely,
    assert PostgreSQL itself rejects it, and that the session recovers."""
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO saved_search_titles (id, saved_search_id, title) "
                f"VALUES (gen_random_uuid(), :saved_search_id, {title_sql_literal})"
            ).bindparams(saved_search_id=saved_search_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_valid_title(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "title-owner@example.com"
    )

    title = make_saved_search_title(saved_search_id, title="Backend Engineer")
    db_session.add(title)
    await db_session.commit()
    await db_session.refresh(title)

    assert isinstance(title.id, uuid.UUID)

    fetched = await db_session.get(SavedSearchTitle, title.id)
    assert fetched is not None
    assert fetched.saved_search_id == saved_search_id
    assert fetched.title == "Backend Engineer"
    assert fetched.is_primary is False
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


async def test_title_is_trimmed_on_input(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    """The ORM validator trims exactly the four covered whitespace
    characters but — unlike `User._normalize_email` — never touches case."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "trim@example.com"
    )
    title = make_saved_search_title(saved_search_id, title="\t Backend Engineer \n")
    db_session.add(title)
    await db_session.commit()
    await db_session.refresh(title)

    assert title.title == "Backend Engineer"


async def test_direct_sql_empty_title_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-empty-title@example.com"
    )
    await _assert_direct_sql_title_insert_rejected(db_session, saved_search_id, "''")


async def test_direct_sql_whitespace_only_title_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-whitespace-title@example.com"
    )
    await _assert_direct_sql_title_insert_rejected(db_session, saved_search_id, r"E'\t\n\r'")


async def test_direct_sql_non_normalized_title_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """An otherwise-valid value that isn't already trimmed is still
    rejected — the database never trims on write, only validates that it
    already is."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-wrapped-title@example.com"
    )
    await _assert_direct_sql_title_insert_rejected(
        db_session, saved_search_id, r"E'\tBackend Engineer\n'"
    )


async def test_direct_sql_whitespace_wrapped_duplicate_cannot_bypass_uniqueness(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    """The unique index alone can't prevent this (a whitespace-wrapped value
    hashes differently from its trimmed form) — it's the normalization
    CHECK that guarantees a wrapped duplicate can never be stored at all, so
    there is nothing left for the index to fail to catch."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "wrapped-duplicate@example.com"
    )
    db_session.add(make_saved_search_title(saved_search_id, title="Backend Engineer"))
    await db_session.commit()

    await _assert_direct_sql_title_insert_rejected(
        db_session, saved_search_id, r"E'\tBackend Engineer\n'"
    )

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 1


async def test_duplicate_title_same_case_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "dup-same-case@example.com"
    )
    db_session.add(make_saved_search_title(saved_search_id, title="Backend Engineer"))
    await db_session.commit()

    db_session.add(make_saved_search_title(saved_search_id, title="Backend Engineer"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 1


async def test_duplicate_title_case_insensitive_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "dup-case-insensitive@example.com"
    )
    db_session.add(make_saved_search_title(saved_search_id, title="Backend Engineer"))
    await db_session.commit()

    db_session.add(make_saved_search_title(saved_search_id, title="backend engineer"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 1


async def test_case_is_preserved_despite_case_insensitive_uniqueness(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "case-preserved@example.com"
    )
    title = make_saved_search_title(saved_search_id, title="Backend Engineer")
    db_session.add(title)
    await db_session.commit()
    await db_session.refresh(title)

    assert title.title == "Backend Engineer"

    fetched = await db_session.get(SavedSearchTitle, title.id)
    assert fetched is not None
    assert fetched.title == "Backend Engineer"


async def test_same_title_different_saved_searches_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    """Uniqueness is scoped per saved search, not global."""
    first_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "search-one@example.com"
    )
    second_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "search-two@example.com"
    )

    db_session.add(make_saved_search_title(first_id, title="Backend Engineer"))
    db_session.add(make_saved_search_title(second_id, title="Backend Engineer"))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 2


async def test_distinct_titles_same_saved_search_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "distinct-titles@example.com"
    )
    db_session.add(make_saved_search_title(saved_search_id, title="Backend Engineer"))
    db_session.add(make_saved_search_title(saved_search_id, title="Software Engineer"))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 2


async def test_nonexistent_saved_search_id_rejected(
    db_session: AsyncSession,
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    db_session.add(make_saved_search_title(uuid.uuid4()))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 0


async def test_is_primary_defaults_to_false(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "is-primary-default@example.com"
    )
    title = make_saved_search_title(saved_search_id)
    db_session.add(title)
    await db_session.commit()
    await db_session.refresh(title)

    assert title.is_primary is False


async def test_is_primary_settable_true(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "is-primary-true@example.com"
    )
    title = make_saved_search_title(saved_search_id, is_primary=True)
    db_session.add(title)
    await db_session.commit()
    await db_session.refresh(title)

    assert title.is_primary is True


async def test_direct_sql_null_is_primary_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-null-primary@example.com"
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO saved_search_titles "
                "(id, saved_search_id, title, is_primary) "
                "VALUES (gen_random_uuid(), :saved_search_id, 'Backend Engineer', NULL)"
            ).bindparams(saved_search_id=saved_search_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_one_primary_plus_multiple_non_primary_titles_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "one-primary-many-aliases@example.com"
    )
    db_session.add(
        make_saved_search_title(saved_search_id, title="Backend Engineer", is_primary=True)
    )
    db_session.add(
        make_saved_search_title(saved_search_id, title="Software Engineer", is_primary=False)
    )
    db_session.add(
        make_saved_search_title(saved_search_id, title="Platform Engineer", is_primary=False)
    )
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 3


async def test_two_primary_titles_same_saved_search_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "two-primaries@example.com"
    )
    db_session.add(
        make_saved_search_title(saved_search_id, title="Backend Engineer", is_primary=True)
    )
    await db_session.commit()

    db_session.add(
        make_saved_search_title(saved_search_id, title="Software Engineer", is_primary=True)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 1


async def test_primary_titles_on_two_different_saved_searches_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    """The partial unique index is scoped per saved search, not global."""
    first_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "primary-search-one@example.com"
    )
    second_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "primary-search-two@example.com"
    )

    db_session.add(make_saved_search_title(first_id, title="Backend Engineer", is_primary=True))
    db_session.add(make_saved_search_title(second_id, title="Backend Engineer", is_primary=True))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 2


async def test_zero_primary_titles_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    """Zero primary titles is a valid, unconstrained state — the partial
    unique index only rejects a *second* true row, never requires a first."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "zero-primaries@example.com"
    )
    db_session.add(make_saved_search_title(saved_search_id, title="Backend Engineer"))
    db_session.add(make_saved_search_title(saved_search_id, title="Software Engineer"))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchTitle))
    ).scalar_one()
    assert count == 2


async def test_changing_primary_title_by_clearing_old_before_setting_new(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "changing-primary@example.com"
    )
    old_primary = make_saved_search_title(
        saved_search_id, title="Backend Engineer", is_primary=True
    )
    new_primary = make_saved_search_title(saved_search_id, title="Software Engineer")
    db_session.add(old_primary)
    db_session.add(new_primary)
    await db_session.commit()

    old_primary.is_primary = False
    await db_session.commit()

    new_primary.is_primary = True
    await db_session.commit()  # must not raise
    await db_session.refresh(old_primary)
    await db_session.refresh(new_primary)

    assert old_primary.is_primary is False
    assert new_primary.is_primary is True


async def test_deleting_saved_search_cascades_to_title(db_engine: AsyncEngine) -> None:
    """Uses real, separately-committed transactions so `ON DELETE CASCADE`
    from `saved_searches` is actually exercised by PostgreSQL, not merely
    implied by ORM-side cascade configuration."""
    async with real_committed_user_saved_search_and_title(
        db_engine, "cascade-owner@example.com"
    ) as (session, _user_id, saved_search_id, title_id):
        saved_search = await session.get(SavedSearch, saved_search_id)
        assert saved_search is not None
        await session.delete(saved_search)
        await session.commit()

        assert await session.get(SavedSearchTitle, title_id) is None

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(SavedSearchTitle))
        ).scalar_one()
        assert count == 0


async def test_cascade_deletion_preserves_another_saved_searchs_titles(
    db_engine: AsyncEngine,
) -> None:
    """Deleting one saved search must not touch an unrelated saved search's
    titles."""
    async with (
        real_committed_user_saved_search_and_title(
            db_engine, "cascade-first@example.com", title="First Search Title"
        ) as (session, _user_id_1, saved_search_id_1, title_id_1),
        real_committed_user_saved_search_and_title(
            db_engine, "cascade-second@example.com", title="Second Search Title"
        ) as (_session_2, _user_id_2, _saved_search_id_2, title_id_2),
    ):
        saved_search_1 = await session.get(SavedSearch, saved_search_id_1)
        assert saved_search_1 is not None
        await session.delete(saved_search_1)
        await session.commit()

        assert await session.get(SavedSearchTitle, title_id_1) is None

        async with AsyncSession(bind=db_engine) as verify_session:
            remaining_title = await verify_session.get(SavedSearchTitle, title_id_2)
            assert remaining_title is not None
            assert remaining_title.title == "Second Search Title"


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_title: Callable[..., SavedSearchTitle],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "tz@example.com"
    )
    title = make_saved_search_title(saved_search_id)
    db_session.add(title)
    await db_session.commit()
    await db_session.refresh(title)

    now = datetime.now(UTC)
    assert abs((now - title.created_at).total_seconds()) < 60
    assert abs((now - title.updated_at).total_seconds()) < 60


async def test_updated_at_advances_on_orm_title_update(db_engine: AsyncEngine) -> None:
    """Same rationale as the other tables' equivalent tests: PostgreSQL's
    `now()` is fixed for the lifetime of one transaction, so this uses real,
    separately-committed transactions."""
    async with real_committed_user_saved_search_and_title(
        db_engine, "updated-at-title@example.com", title="Backend Engineer"
    ) as (session, _user_id, _saved_search_id, title_id):
        title = await session.get(SavedSearchTitle, title_id)
        assert title is not None
        created_at = title.created_at
        first_updated_at = title.updated_at

        title.title = "Senior Backend Engineer"
        await session.commit()
        await session.refresh(title)
        second_updated_at = title.updated_at

        assert second_updated_at > first_updated_at
        assert second_updated_at >= created_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(SavedSearchTitle))
        ).scalar_one()
        assert count == 0


async def test_updated_at_advances_on_orm_primary_state_update(db_engine: AsyncEngine) -> None:
    async with real_committed_user_saved_search_and_title(
        db_engine, "updated-at-primary@example.com", title="Backend Engineer"
    ) as (session, _user_id, _saved_search_id, title_id):
        title = await session.get(SavedSearchTitle, title_id)
        assert title is not None
        created_at = title.created_at
        first_updated_at = title.updated_at

        title.is_primary = True
        await session.commit()
        await session.refresh(title)
        second_updated_at = title.updated_at

        assert second_updated_at > first_updated_at
        assert second_updated_at >= created_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(SavedSearchTitle))
        ).scalar_one()
        assert count == 0
