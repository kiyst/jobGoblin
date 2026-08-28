import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import SavedSearch, SavedSearchLocation, User
from tests.conftest import real_committed_user_saved_search_and_location


async def _insert_saved_search(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    email: str,
) -> uuid.UUID:
    """Returns the new saved search's id, captured immediately after its own
    commit — `session.commit()` expires every attribute of every object in
    the session (savepoint-backed commits included), so a later commit (e.g.
    adding a location) would otherwise expire this id before it's read."""
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


async def _assert_direct_sql_location_text_insert_rejected(
    db_session: AsyncSession, saved_search_id: uuid.UUID, location_text_sql_literal: str
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely,
    assert PostgreSQL itself rejects it, and that the session recovers."""
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO saved_search_locations (id, saved_search_id, location_text) "
                f"VALUES (gen_random_uuid(), :saved_search_id, {location_text_sql_literal})"
            ).bindparams(saved_search_id=saved_search_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchLocation))
    ).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_valid_location(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "location-owner@example.com"
    )

    location = make_saved_search_location(saved_search_id, location_text="Ashburn, VA")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert isinstance(location.id, uuid.UUID)

    fetched = await db_session.get(SavedSearchLocation, location.id)
    assert fetched is not None
    assert fetched.saved_search_id == saved_search_id
    assert fetched.location_text == "Ashburn, VA"
    assert fetched.latitude is None
    assert fetched.longitude is None
    assert fetched.radius_miles_override is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


async def test_location_text_is_trimmed_on_input(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    """The ORM validator trims exactly the four covered whitespace
    characters but — unlike `User._normalize_email` — never touches case."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "trim@example.com"
    )
    location = make_saved_search_location(saved_search_id, location_text="\t Ashburn, VA \n")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert location.location_text == "Ashburn, VA"


async def test_direct_sql_empty_location_text_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-empty-location@example.com"
    )
    await _assert_direct_sql_location_text_insert_rejected(db_session, saved_search_id, "''")


async def test_direct_sql_whitespace_only_location_text_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-whitespace-location@example.com"
    )
    await _assert_direct_sql_location_text_insert_rejected(
        db_session, saved_search_id, r"E'\t\n\r'"
    )


async def test_direct_sql_non_normalized_location_text_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """An otherwise-valid value that isn't already trimmed is still
    rejected — the database never trims on write, only validates that it
    already is."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-wrapped-location@example.com"
    )
    await _assert_direct_sql_location_text_insert_rejected(
        db_session, saved_search_id, r"E'\tAshburn, VA\n'"
    )


async def test_direct_sql_whitespace_wrapped_duplicate_cannot_bypass_uniqueness(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    """The unique index alone can't prevent this (a whitespace-wrapped value
    hashes differently from its trimmed form) — it's the normalization
    CHECK that guarantees a wrapped duplicate can never be stored at all, so
    there is nothing left for the index to fail to catch."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "wrapped-duplicate@example.com"
    )
    db_session.add(make_saved_search_location(saved_search_id, location_text="Ashburn, VA"))
    await db_session.commit()

    await _assert_direct_sql_location_text_insert_rejected(
        db_session, saved_search_id, r"E'\tAshburn, VA\n'"
    )

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchLocation))
    ).scalar_one()
    assert count == 1


async def test_duplicate_location_text_same_case_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "dup-same-case@example.com"
    )
    db_session.add(make_saved_search_location(saved_search_id, location_text="Ashburn, VA"))
    await db_session.commit()

    db_session.add(make_saved_search_location(saved_search_id, location_text="Ashburn, VA"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchLocation))
    ).scalar_one()
    assert count == 1


async def test_duplicate_location_text_case_insensitive_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "dup-case-insensitive@example.com"
    )
    db_session.add(make_saved_search_location(saved_search_id, location_text="Ashburn, VA"))
    await db_session.commit()

    db_session.add(make_saved_search_location(saved_search_id, location_text="ashburn, va"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchLocation))
    ).scalar_one()
    assert count == 1


async def test_case_is_preserved_despite_case_insensitive_uniqueness(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "case-preserved@example.com"
    )
    location = make_saved_search_location(saved_search_id, location_text="Ashburn, VA")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert location.location_text == "Ashburn, VA"

    fetched = await db_session.get(SavedSearchLocation, location.id)
    assert fetched is not None
    assert fetched.location_text == "Ashburn, VA"


async def test_same_location_text_different_saved_searches_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    """Uniqueness is scoped per saved search, not global."""
    first_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "search-one@example.com"
    )
    second_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "search-two@example.com"
    )

    db_session.add(make_saved_search_location(first_id, location_text="Ashburn, VA"))
    db_session.add(make_saved_search_location(second_id, location_text="Ashburn, VA"))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchLocation))
    ).scalar_one()
    assert count == 2


async def test_distinct_location_texts_same_saved_search_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "distinct-locations@example.com"
    )
    db_session.add(make_saved_search_location(saved_search_id, location_text="Ashburn, VA"))
    db_session.add(make_saved_search_location(saved_search_id, location_text="Reston, VA"))
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchLocation))
    ).scalar_one()
    assert count == 2


async def test_nonexistent_saved_search_id_rejected(
    db_session: AsyncSession,
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    db_session.add(make_saved_search_location(uuid.uuid4()))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (
        await db_session.execute(select(func.count()).select_from(SavedSearchLocation))
    ).scalar_one()
    assert count == 0


async def test_deleting_saved_search_cascades_to_location(db_engine: AsyncEngine) -> None:
    """Uses real, separately-committed transactions so `ON DELETE CASCADE`
    from `saved_searches` is actually exercised by PostgreSQL, not merely
    implied by ORM-side cascade configuration."""
    async with real_committed_user_saved_search_and_location(
        db_engine, "cascade-owner@example.com"
    ) as (session, _user_id, saved_search_id, location_id):
        saved_search = await session.get(SavedSearch, saved_search_id)
        assert saved_search is not None
        await session.delete(saved_search)
        await session.commit()

        assert await session.get(SavedSearchLocation, location_id) is None

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(SavedSearchLocation))
        ).scalar_one()
        assert count == 0


async def test_cascade_deletion_preserves_another_saved_searchs_locations(
    db_engine: AsyncEngine,
) -> None:
    """Deleting one saved search must not touch an unrelated saved search's
    locations."""
    async with (
        real_committed_user_saved_search_and_location(
            db_engine, "cascade-first@example.com", location_text="First Search Location"
        ) as (session, _user_id_1, saved_search_id_1, location_id_1),
        real_committed_user_saved_search_and_location(
            db_engine, "cascade-second@example.com", location_text="Second Search Location"
        ) as (_session_2, _user_id_2, _saved_search_id_2, location_id_2),
    ):
        saved_search_1 = await session.get(SavedSearch, saved_search_id_1)
        assert saved_search_1 is not None
        await session.delete(saved_search_1)
        await session.commit()

        assert await session.get(SavedSearchLocation, location_id_1) is None

        async with AsyncSession(bind=db_engine) as verify_session:
            remaining_location = await verify_session.get(SavedSearchLocation, location_id_2)
            assert remaining_location is not None
            assert remaining_location.location_text == "Second Search Location"


async def test_latitude_longitude_default_to_none(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "coords-default@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert location.latitude is None
    assert location.longitude is None


async def test_latitude_longitude_settable_together(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "coords-set@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.latitude = Decimal("39.0437")
    location.longitude = Decimal("-77.4875")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert location.latitude == Decimal("39.0437")
    assert location.longitude == Decimal("-77.4875")


@pytest.mark.parametrize("latitude", [Decimal(-90), Decimal(90)])
async def test_latitude_in_range_accepts_boundary_values(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
    latitude: Decimal,
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, f"latitude-ok-{latitude}@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.latitude = latitude
    location.longitude = Decimal(0)
    db_session.add(location)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("latitude", [Decimal("-90.1"), Decimal("90.1")])
async def test_latitude_out_of_range_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
    latitude: Decimal,
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, f"latitude-bad-{latitude}@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.latitude = latitude
    location.longitude = Decimal(0)
    db_session.add(location)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("longitude", [Decimal(-180), Decimal(180)])
async def test_longitude_in_range_accepts_boundary_values(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
    longitude: Decimal,
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, f"longitude-ok-{longitude}@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.latitude = Decimal(0)
    location.longitude = longitude
    db_session.add(location)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("longitude", [Decimal("-180.1"), Decimal("180.1")])
async def test_longitude_out_of_range_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
    longitude: Decimal,
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, f"longitude-bad-{longitude}@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.latitude = Decimal(0)
    location.longitude = longitude
    db_session.add(location)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_coordinate_pair_both_null_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "coords-both-null@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    db_session.add(location)
    await db_session.commit()  # must not raise


async def test_coordinate_pair_both_non_null_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "coords-both-set@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.latitude = Decimal("39.0437")
    location.longitude = Decimal("-77.4875")
    db_session.add(location)
    await db_session.commit()  # must not raise


async def test_coordinate_pair_latitude_only_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "coords-latitude-only@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.latitude = Decimal("39.0437")
    db_session.add(location)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_coordinate_pair_longitude_only_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "coords-longitude-only@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.longitude = Decimal("-77.4875")
    db_session.add(location)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_coordinate_pair_latitude_only_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """Bypasses the ORM entirely with a single raw INSERT, proving the
    coordinate-pair CHECK is enforced by PostgreSQL itself, not merely by
    attribute-assignment order in application code."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-coords-latitude-only@example.com"
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO saved_search_locations "
                "(id, saved_search_id, location_text, latitude, longitude) "
                "VALUES (gen_random_uuid(), :saved_search_id, 'Ashburn, VA', 39.0437, NULL)"
            ).bindparams(saved_search_id=saved_search_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_coordinate_pair_longitude_only_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "direct-coords-longitude-only@example.com"
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO saved_search_locations "
                "(id, saved_search_id, location_text, latitude, longitude) "
                "VALUES (gen_random_uuid(), :saved_search_id, 'Ashburn, VA', NULL, -77.4875)"
            ).bindparams(saved_search_id=saved_search_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_radius_miles_override_defaults_to_none(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "radius-override-default@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert location.radius_miles_override is None


@pytest.mark.parametrize("value", [Decimal(0), Decimal(5)])
async def test_radius_miles_override_non_negative_accepts_zero_and_positive(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
    value: Decimal,
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, f"radius-override-ok-{value}@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.radius_miles_override = value
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert location.radius_miles_override == value


async def test_radius_miles_override_non_negative_rejects_negative_value(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "radius-override-bad@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.radius_miles_override = Decimal(-5)
    db_session.add(location)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_radius_miles_override_preserves_fractional_precision(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    """No precision/scale CHECK — a fractional value must round-trip
    exactly, not get truncated or rounded."""
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "radius-override-fractional@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    location.radius_miles_override = Decimal("12.75")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    assert location.radius_miles_override == Decimal("12.75")


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    make_saved_search_location: Callable[..., SavedSearchLocation],
) -> None:
    saved_search_id = await _insert_saved_search(
        db_session, make_user, make_saved_search, "tz@example.com"
    )
    location = make_saved_search_location(saved_search_id)
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    now = datetime.now(UTC)
    assert abs((now - location.created_at).total_seconds()) < 60
    assert abs((now - location.updated_at).total_seconds()) < 60


async def test_updated_at_advances_on_orm_update(db_engine: AsyncEngine) -> None:
    """Same rationale as the other tables' equivalent tests: PostgreSQL's
    `now()` is fixed for the lifetime of one transaction, so this uses real,
    separately-committed transactions."""
    async with real_committed_user_saved_search_and_location(
        db_engine, "updated-at-location@example.com", location_text="Ashburn, VA"
    ) as (session, _user_id, _saved_search_id, location_id):
        location = await session.get(SavedSearchLocation, location_id)
        assert location is not None
        created_at = location.created_at
        first_updated_at = location.updated_at

        location.location_text = "Reston, VA"
        await session.commit()
        await session.refresh(location)
        second_updated_at = location.updated_at

        assert second_updated_at > first_updated_at
        assert second_updated_at >= created_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(SavedSearchLocation))
        ).scalar_one()
        assert count == 0
