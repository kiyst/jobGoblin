import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import SavedSearch, User
from app.services import saved_searches
from tests.conftest import real_committed_user

JSONB_FIELDS = ["enabled_sources", "scoring_weights"]


async def _insert_user(
    db_session: AsyncSession, make_user: Callable[..., User], email: str
) -> uuid.UUID:
    user = make_user(email=email)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user.id


async def _jsonb_typeof(db_session: AsyncSession, search_id: uuid.UUID, column: str) -> str | None:
    """Queries PostgreSQL's own `jsonb_typeof(...)` directly, bypassing the
    ORM's Python-level `None` deserialization entirely — the only way to
    distinguish a genuine SQL `NULL` (`jsonb_typeof` itself returns SQL
    `NULL`, i.e. `None` here) from a stored JSON `null` literal
    (`jsonb_typeof` returns the string `'null'`)."""
    result = await db_session.execute(
        text(f"SELECT jsonb_typeof({column}) FROM saved_searches WHERE id = :search_id").bindparams(
            search_id=search_id
        )
    )
    value: str | None = result.scalar_one()
    return value


# --------------------------------------------------------------------------
# create() — "seeded" proof: a search created exclusively through the
# service, then fetched back exclusively through the service.
# --------------------------------------------------------------------------


async def test_create_persists_and_is_fetchable_through_the_service(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-create@example.com")

    created = await saved_searches.create(
        db_session,
        user_id,
        name="Backend roles",
        remote_rules="any",
        polling_schedule="manual",
        salary_floor=100_000,
    )
    assert created.user_id == user_id
    assert created.id is not None

    fetched = await saved_searches.get_for_user(db_session, user_id, created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Backend roles"
    assert fetched.salary_floor == 100_000


async def test_create_omits_is_active_so_the_server_default_applies(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`create()` never passes `is_active` to the ORM constructor at all —
    the column's own `server_default` (`true`) must be what actually sets
    it, not a Python-side default silently duplicating it."""
    user_id = await _insert_user(db_session, make_user, "ss-default-active@example.com")

    created = await saved_searches.create(
        db_session, user_id, name="Default active", remote_rules="any", polling_schedule="manual"
    )

    await db_session.commit()
    await db_session.refresh(created)
    assert created.is_active is True


@pytest.mark.parametrize("column", JSONB_FIELDS)
async def test_create_omitted_jsonb_field_stores_genuine_sql_null(
    db_session: AsyncSession, make_user: Callable[..., User], column: str
) -> None:
    """Regression for the fixed `None`-vs-JSON-`null` bug: creating without
    `enabled_sources`/`scoring_weights` at all must store a real SQL `NULL`
    — not the JSON literal `null`, which would fail this column's own
    `jsonb_typeof(...) = 'object'` `CHECK`."""
    user_id = await _insert_user(db_session, make_user, f"ss-jsonb-omitted-{column}@example.com")

    created = await saved_searches.create(
        db_session, user_id, name="Backend roles", remote_rules="any", polling_schedule="manual"
    )

    assert getattr(created, column) is None
    assert await _jsonb_typeof(db_session, created.id, column) is None


@pytest.mark.parametrize("column", JSONB_FIELDS)
async def test_create_explicit_none_jsonb_field_stores_genuine_sql_null(
    db_session: AsyncSession, make_user: Callable[..., User], column: str
) -> None:
    """Passing `None` explicitly for `enabled_sources`/`scoring_weights` must
    behave identically to omitting it — both store a real SQL `NULL`."""
    user_id = await _insert_user(
        db_session, make_user, f"ss-jsonb-explicit-none-{column}@example.com"
    )

    created = await saved_searches.create(
        db_session,
        user_id,
        name="Backend roles",
        remote_rules="any",
        polling_schedule="manual",
        **{column: None},
    )

    assert getattr(created, column) is None
    assert await _jsonb_typeof(db_session, created.id, column) is None


@pytest.mark.parametrize("column", JSONB_FIELDS)
async def test_create_persists_and_reloads_a_representative_dict(
    db_session: AsyncSession, make_user: Callable[..., User], column: str
) -> None:
    """A representative non-empty dict for `enabled_sources`/
    `scoring_weights` persists and reloads through the service, and is a
    genuine JSON object at the database level (not merely non-`None` in
    Python)."""
    user_id = await _insert_user(db_session, make_user, f"ss-jsonb-dict-{column}@example.com")
    value: dict[str, object] = {"greenhouse": True, "weight": 1}

    if column == "enabled_sources":
        created = await saved_searches.create(
            db_session,
            user_id,
            name="Backend roles",
            remote_rules="any",
            polling_schedule="manual",
            enabled_sources=value,
        )
    else:
        created = await saved_searches.create(
            db_session,
            user_id,
            name="Backend roles",
            remote_rules="any",
            polling_schedule="manual",
            scoring_weights=value,
        )
    assert getattr(created, column) == value
    assert await _jsonb_typeof(db_session, created.id, column) == "object"

    fetched = await saved_searches.get_for_user(db_session, user_id, created.id)
    assert fetched is not None
    assert getattr(fetched, column) == value


async def test_create_multiple_searches_for_same_user_accepted(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-multiple@example.com")

    first = await saved_searches.create(
        db_session, user_id, name="Search A", remote_rules="any", polling_schedule="manual"
    )
    second = await saved_searches.create(
        db_session, user_id, name="Search B", remote_rules="remote_only", polling_schedule="daily"
    )

    assert first.id != second.id
    count = (
        await db_session.execute(
            select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user_id)
        )
    ).scalar_one()
    assert count == 2


async def test_create_rejects_invalid_remote_rules_with_zero_mutation(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-bad-remote-rules@example.com")

    with pytest.raises(ValueError, match="invalid remote_rules"):
        await saved_searches.create(
            db_session, user_id, name="Bad", remote_rules="bogus", polling_schedule="manual"
        )

    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == 0


async def test_create_rejects_invalid_polling_schedule_with_zero_mutation(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-bad-polling@example.com")

    with pytest.raises(ValueError, match="invalid polling_schedule"):
        await saved_searches.create(
            db_session, user_id, name="Bad", remote_rules="any", polling_schedule="bogus"
        )

    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == 0


# --------------------------------------------------------------------------
# get_for_user() — ownership scoping: a wrong owner is indistinguishable
# from a nonexistent row.
# --------------------------------------------------------------------------


async def test_get_for_user_returns_none_when_no_such_id_exists(db_session: AsyncSession) -> None:
    assert await saved_searches.get_for_user(db_session, uuid.uuid4(), uuid.uuid4()) is None


async def test_get_for_user_returns_none_for_another_users_real_search(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    owner_id = await _insert_user(db_session, make_user, "ss-real-owner@example.com")
    other_user_id = await _insert_user(db_session, make_user, "ss-other-user@example.com")
    search = await saved_searches.create(
        db_session, owner_id, name="Owner's search", remote_rules="any", polling_schedule="manual"
    )

    assert await saved_searches.get_for_user(db_session, other_user_id, search.id) is None


# --------------------------------------------------------------------------
# update() — validation before mutation, ownership scoping, partial update,
# explicit None, and the database CHECK remaining the backstop.
# --------------------------------------------------------------------------


async def test_update_partial_change_preserves_untouched_fields(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-partial@example.com")
    search = await saved_searches.create(
        db_session,
        user_id,
        name="Backend roles",
        remote_rules="any",
        polling_schedule="manual",
        salary_floor=100_000,
    )

    updated = await saved_searches.update(db_session, user_id, search.id, salary_floor=120_000)

    assert updated is not None
    assert updated.salary_floor == 120_000
    assert updated.name == "Backend roles"  # untouched
    assert updated.remote_rules == "any"  # untouched


async def test_update_can_set_a_nullable_field_explicitly_to_none(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-clear@example.com")
    search = await saved_searches.create(
        db_session,
        user_id,
        name="Backend roles",
        remote_rules="any",
        polling_schedule="manual",
        salary_floor=100_000,
    )

    updated = await saved_searches.update(db_session, user_id, search.id, salary_floor=None)

    assert updated is not None
    assert updated.salary_floor is None


@pytest.mark.parametrize("column", JSONB_FIELDS)
async def test_update_can_clear_an_existing_dict_to_genuine_sql_null(
    db_session: AsyncSession, make_user: Callable[..., User], column: str
) -> None:
    """Regression for the fixed `None`-vs-JSON-`null` bug: an existing
    `enabled_sources`/`scoring_weights` dict can be cleared to `None`
    through `update()`, committed, and reloaded as a genuine SQL `NULL` —
    not the JSON literal `null`, which would have raised `IntegrityError`
    before the `JSONB(none_as_null=True)` mapping fix."""
    user_id = await _insert_user(db_session, make_user, f"ss-jsonb-clear-{column}@example.com")
    initial_value: dict[str, object] = {"greenhouse": True}
    if column == "enabled_sources":
        created = await saved_searches.create(
            db_session,
            user_id,
            name="Backend roles",
            remote_rules="any",
            polling_schedule="manual",
            enabled_sources=initial_value,
        )
    else:
        created = await saved_searches.create(
            db_session,
            user_id,
            name="Backend roles",
            remote_rules="any",
            polling_schedule="manual",
            scoring_weights=initial_value,
        )
    search_id = created.id  # captured before any later commit expires `created`
    assert await _jsonb_typeof(db_session, search_id, column) == "object"

    updated = await saved_searches.update(db_session, user_id, search_id, **{column: None})
    assert updated is not None
    assert getattr(updated, column) is None

    await db_session.commit()

    assert await _jsonb_typeof(db_session, search_id, column) is None
    reloaded = await saved_searches.get_for_user(db_session, user_id, search_id)
    assert reloaded is not None
    assert getattr(reloaded, column) is None


async def test_update_can_set_is_active_false(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`is_active` is excluded from `create()`'s own parameters but must
    still be reachable through `update()`."""
    user_id = await _insert_user(db_session, make_user, "ss-deactivate@example.com")
    search = await saved_searches.create(
        db_session, user_id, name="Backend roles", remote_rules="any", polling_schedule="manual"
    )

    updated = await saved_searches.update(db_session, user_id, search.id, is_active=False)

    assert updated is not None
    assert updated.is_active is False


async def test_update_rejects_unknown_field_with_zero_mutation(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-unknown-field@example.com")
    search = await saved_searches.create(
        db_session,
        user_id,
        name="Backend roles",
        remote_rules="any",
        polling_schedule="manual",
        salary_floor=100_000,
    )

    with pytest.raises(ValueError, match="cannot update fields"):
        await saved_searches.update(db_session, user_id, search.id, not_a_real_field="x")

    unchanged = await saved_searches.get_for_user(db_session, user_id, search.id)
    assert unchanged is not None
    assert unchanged.salary_floor == 100_000


async def test_update_rejects_invalid_enum_with_zero_mutation(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user_id = await _insert_user(db_session, make_user, "ss-update-bad-enum@example.com")
    search = await saved_searches.create(
        db_session, user_id, name="Backend roles", remote_rules="any", polling_schedule="manual"
    )

    with pytest.raises(ValueError, match="invalid remote_rules"):
        await saved_searches.update(db_session, user_id, search.id, remote_rules="bogus")

    unchanged = await saved_searches.get_for_user(db_session, user_id, search.id)
    assert unchanged is not None
    assert unchanged.remote_rules == "any"


async def test_update_validates_before_checking_existence(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="cannot update fields"):
        await saved_searches.update(db_session, uuid.uuid4(), uuid.uuid4(), not_a_real_field="x")


async def test_update_returns_none_when_search_missing(db_session: AsyncSession) -> None:
    result = await saved_searches.update(db_session, uuid.uuid4(), uuid.uuid4(), salary_floor=1)
    assert result is None


async def test_update_by_wrong_owner_returns_none_and_leaves_database_unchanged(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    owner_id = await _insert_user(db_session, make_user, "ss-wrong-owner-owner@example.com")
    attacker_id = await _insert_user(db_session, make_user, "ss-wrong-owner-attacker@example.com")
    search = await saved_searches.create(
        db_session,
        owner_id,
        name="Owner's search",
        remote_rules="any",
        polling_schedule="manual",
        salary_floor=100_000,
    )

    result = await saved_searches.update(db_session, attacker_id, search.id, salary_floor=1)

    assert result is None
    unchanged = await saved_searches.get_for_user(db_session, owner_id, search.id)
    assert unchanged is not None
    # database genuinely unchanged, not just the return value
    assert unchanged.salary_floor == 100_000


async def test_update_database_rejects_invalid_check_backed_value(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`radius_miles_non_negative` is a database `CHECK`, not re-validated in
    Python by `update()` — a negative value is only caught when the
    service's internal `flush()` runs."""
    user_id = await _insert_user(db_session, make_user, "ss-check-backstop@example.com")
    search = await saved_searches.create(
        db_session, user_id, name="Backend roles", remote_rules="any", polling_schedule="manual"
    )

    with pytest.raises(IntegrityError):
        await saved_searches.update(db_session, user_id, search.id, radius_miles=-1)
    await db_session.rollback()


async def test_update_database_rejects_ordering_check_across_two_columns(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`salary_floor_le_preferred_salary` is a cross-column database `CHECK`,
    not re-validated in Python — raising `salary_floor` above the row's own
    existing `preferred_salary` is only caught at `flush()`."""
    user_id = await _insert_user(db_session, make_user, "ss-ordering-backstop@example.com")
    search = await saved_searches.create(
        db_session,
        user_id,
        name="Backend roles",
        remote_rules="any",
        polling_schedule="manual",
        salary_floor=50_000,
        preferred_salary=100_000,
    )

    with pytest.raises(IntegrityError):
        await saved_searches.update(db_session, user_id, search.id, salary_floor=150_000)
    await db_session.rollback()


async def test_update_database_rejects_is_active_none(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """`is_active` is `NOT NULL` with no Python-side re-validation in
    `update()` even though it's in the update allow-list — passing `None`
    is only caught when the service's internal `flush()` runs."""
    user_id = await _insert_user(db_session, make_user, "ss-is-active-not-null@example.com")
    search = await saved_searches.create(
        db_session, user_id, name="Backend roles", remote_rules="any", polling_schedule="manual"
    )

    with pytest.raises(IntegrityError):
        await saved_searches.update(db_session, user_id, search.id, is_active=None)
    await db_session.rollback()


# --------------------------------------------------------------------------
# Transaction ownership: flush, not commit; caller controls commit/rollback.
# --------------------------------------------------------------------------


async def test_create_and_update_flush_without_committing_caller_controls_transaction(
    db_engine: AsyncEngine,
) -> None:
    async with real_committed_user(db_engine, "ss-service-flush@example.com") as (session, user_id):
        created = await saved_searches.create(
            session, user_id, name="Backend roles", remote_rules="any", polling_schedule="manual"
        )
        search_id = created.id

        # Flushed: visible within the same still-open transaction.
        same_session_view = await saved_searches.get_for_user(session, user_id, search_id)
        assert same_session_view is not None

        # Not committed: a genuinely separate session/connection must not see it.
        async with AsyncSession(bind=db_engine) as other_session:
            assert await other_session.get(SavedSearch, search_id) is None

        await session.commit()  # make the search durable for the update half below

        updated = await saved_searches.update(session, user_id, search_id, salary_floor=150_000)
        assert updated is not None

        same_session_after_update = await saved_searches.get_for_user(session, user_id, search_id)
        assert same_session_after_update is not None
        assert same_session_after_update.salary_floor == 150_000

        async with AsyncSession(bind=db_engine) as other_session:
            other_view = await other_session.get(SavedSearch, search_id)
            assert other_view is not None
            assert other_view.salary_floor is None  # update() not yet committed

        await session.rollback()

        async with AsyncSession(bind=db_engine) as verify_session:
            rolled_back = await verify_session.get(SavedSearch, search_id)
            assert rolled_back is not None
            assert rolled_back.salary_floor is None
