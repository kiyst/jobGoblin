import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import SavedSearch, User
from app.db.models.saved_search import POLLING_SCHEDULES, REMOTE_RULES
from tests.conftest import real_committed_user_and_saved_search

ARRAY_FIELDS = [
    "excluded_titles",
    "industries",
    "employment_types",
    "seniority",
    "must_have_skills",
    "preferred_skills",
    "excluded_keywords",
    "preferred_companies",
    "excluded_companies",
    "enabled_providers",
]

JSONB_FIELDS = ["enabled_sources", "scoring_weights"]


async def _insert_user(
    db_session: AsyncSession, make_user: Callable[..., User], email: str
) -> User:
    user = make_user(email=email)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _assert_direct_sql_name_insert_rejected(
    db_session: AsyncSession, user_id: uuid.UUID, name_sql_literal: str
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely,
    assert PostgreSQL itself rejects it, and that the session recovers."""
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO saved_searches "
                "(id, user_id, name, remote_rules, polling_schedule) "
                f"VALUES (gen_random_uuid(), :user_id, {name_sql_literal}, 'any', 'manual')"
            ).bindparams(user_id=user_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def _assert_direct_sql_jsonb_insert_rejected(
    db_session: AsyncSession, user_id: uuid.UUID, column: str, json_sql_literal: str
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO saved_searches "
                f"(id, user_id, name, remote_rules, polling_schedule, {column}) "
                "VALUES (gen_random_uuid(), :user_id, 'Direct SQL Search', 'any', 'manual', "
                f"{json_sql_literal})"
            ).bindparams(user_id=user_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_valid_saved_search(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "search-owner@example.com")
    user_id = user.id  # captured before any later commit expires `user`

    saved_search = make_saved_search(
        user_id, name="Backend roles", remote_rules="remote_only", polling_schedule="daily"
    )
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert isinstance(saved_search.id, uuid.UUID)

    fetched = await db_session.get(SavedSearch, saved_search.id)
    assert fetched is not None
    assert fetched.user_id == user_id
    assert fetched.name == "Backend roles"
    assert fetched.remote_rules == "remote_only"
    assert fetched.polling_schedule == "daily"
    assert fetched.is_active is True
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


async def test_insert_and_retrieve_a_fully_populated_saved_search(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """Every column populated at once, not just the handful the other tests
    touch individually."""
    user = await _insert_user(db_session, make_user, "fully-populated@example.com")
    saved_search = make_saved_search(
        user.id, name="Senior Backend Roles", remote_rules="hybrid_ok", polling_schedule="weekly"
    )
    saved_search.excluded_titles = ["intern"]
    saved_search.industries = ["fintech"]
    saved_search.employment_types = ["full_time"]
    saved_search.seniority = ["senior"]
    saved_search.must_have_skills = ["python"]
    saved_search.preferred_skills = ["kubernetes"]
    saved_search.excluded_keywords = ["unpaid"]
    saved_search.preferred_companies = ["acme"]
    saved_search.excluded_companies = ["globex"]
    saved_search.enabled_providers = ["jobspy"]
    saved_search.radius_miles = Decimal("25.5")
    saved_search.salary_floor = 120_000
    saved_search.preferred_salary = 150_000
    saved_search.recency_limit_hours = 72
    saved_search.enabled_sources = {"jobspy": ["linkedin", "indeed"]}
    saved_search.scoring_weights = {"title_weight": 2}
    saved_search.is_active = False
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    fetched = await db_session.get(SavedSearch, saved_search.id)
    assert fetched is not None
    assert fetched.name == "Senior Backend Roles"
    assert fetched.remote_rules == "hybrid_ok"
    assert fetched.polling_schedule == "weekly"
    assert fetched.excluded_titles == ["intern"]
    assert fetched.industries == ["fintech"]
    assert fetched.employment_types == ["full_time"]
    assert fetched.seniority == ["senior"]
    assert fetched.must_have_skills == ["python"]
    assert fetched.preferred_skills == ["kubernetes"]
    assert fetched.excluded_keywords == ["unpaid"]
    assert fetched.preferred_companies == ["acme"]
    assert fetched.excluded_companies == ["globex"]
    assert fetched.enabled_providers == ["jobspy"]
    assert fetched.radius_miles == Decimal("25.5")
    assert fetched.salary_floor == 120_000
    assert fetched.preferred_salary == 150_000
    assert fetched.recency_limit_hours == 72
    assert fetched.enabled_sources == {"jobspy": ["linkedin", "indeed"]}
    assert fetched.scoring_weights == {"title_weight": 2}
    assert fetched.is_active is False
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


async def test_name_is_trimmed_on_input(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """The ORM validator trims exactly the four covered whitespace
    characters but — unlike `User._normalize_email` — never touches case."""
    user = await _insert_user(db_session, make_user, "trim@example.com")
    saved_search = make_saved_search(user.id, name="\t Senior Backend Roles \n")
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert saved_search.name == "Senior Backend Roles"


async def test_direct_sql_empty_name_rejected(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = await _insert_user(db_session, make_user, "direct-empty-name@example.com")
    await _assert_direct_sql_name_insert_rejected(db_session, user.id, "''")


async def test_direct_sql_whitespace_only_name_rejected(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = await _insert_user(db_session, make_user, "direct-whitespace-name@example.com")
    await _assert_direct_sql_name_insert_rejected(db_session, user.id, r"E'\t\n\r'")


async def test_direct_sql_non_normalized_name_rejected(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """An otherwise-valid value that isn't already trimmed is still
    rejected — the database never trims on write, only validates that it
    already is."""
    user = await _insert_user(db_session, make_user, "direct-wrapped-name@example.com")
    await _assert_direct_sql_name_insert_rejected(db_session, user.id, r"E'\tBackend Roles\n'")


async def test_duplicate_name_across_saved_searches_is_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """`name` has no uniqueness requirement — a user may have multiple saved
    searches sharing the same name."""
    user = await _insert_user(db_session, make_user, "duplicate-name@example.com")
    db_session.add(make_saved_search(user.id, name="Backend roles"))
    db_session.add(make_saved_search(user.id, name="Backend roles"))
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == 2


async def test_every_allowed_remote_rules_value_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    for value in REMOTE_RULES:
        user = await _insert_user(db_session, make_user, f"remote-{value}@example.com")
        db_session.add(make_saved_search(user.id, remote_rules=value))
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == len(REMOTE_RULES)


async def test_invalid_remote_rules_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "invalid-remote-rules@example.com")
    db_session.add(make_saved_search(user.id, remote_rules="fully_remote"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_every_allowed_polling_schedule_value_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    for value in POLLING_SCHEDULES:
        user = await _insert_user(db_session, make_user, f"polling-{value}@example.com")
        db_session.add(make_saved_search(user.id, polling_schedule=value))
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == len(POLLING_SCHEDULES)


async def test_invalid_polling_schedule_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "invalid-polling@example.com")
    db_session.add(make_saved_search(user.id, polling_schedule="every_minute"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_is_active_defaults_true(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "is-active-default@example.com")
    saved_search = make_saved_search(user.id)
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert saved_search.is_active is True


async def test_is_active_settable_false(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "is-active-false@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.is_active = False
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert saved_search.is_active is False


async def test_nullable_fields_default_to_none(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "nullable-fields@example.com")
    saved_search = make_saved_search(user.id)
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    for field in ARRAY_FIELDS:
        assert getattr(saved_search, field) is None
    assert saved_search.radius_miles is None
    assert saved_search.salary_floor is None
    assert saved_search.preferred_salary is None
    assert saved_search.recency_limit_hours is None
    for field in JSONB_FIELDS:
        assert getattr(saved_search, field) is None


async def test_empty_array_is_distinct_from_null(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """NULL means "never specified"; an explicitly stored empty array means
    "specified as none" — the two must round-trip as distinguishable
    values, not collapse to the same representation. Mirrors the same test
    for `candidate_profiles`."""
    unset_user = await _insert_user(db_session, make_user, "unset-array@example.com")
    unset_search = make_saved_search(unset_user.id)
    db_session.add(unset_search)

    explicit_user = await _insert_user(db_session, make_user, "empty-array@example.com")
    explicit_search = make_saved_search(explicit_user.id)
    explicit_search.industries = []
    db_session.add(explicit_search)

    await db_session.commit()
    await db_session.refresh(unset_search)
    await db_session.refresh(explicit_search)

    assert unset_search.industries is None
    assert explicit_search.industries == []


@pytest.mark.parametrize("field", ARRAY_FIELDS)
async def test_appending_to_array_field_persists_after_reload(
    db_engine: AsyncEngine, field: str
) -> None:
    """A plain `ARRAY(Text)` column looks unchanged to SQLAlchemy's
    unit-of-work after an in-place `.append()` — the model wraps these
    columns with `MutableList.as_mutable` specifically so this mutation is
    tracked and actually written on commit."""
    async with real_committed_user_and_saved_search(
        db_engine, f"array-mutate-{field}@example.com", **{field: ["first"]}
    ) as (session, _user_id, saved_search_id):
        saved_search = await session.get(SavedSearch, saved_search_id)
        assert saved_search is not None
        getattr(saved_search, field).append("second")
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(SavedSearch, saved_search_id)
            assert reloaded is not None
            assert getattr(reloaded, field) == ["first", "second"]


async def test_nullable_jsonb_fields_default_to_none(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "jsonb-default@example.com")
    saved_search = make_saved_search(user.id)
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert saved_search.enabled_sources is None
    assert saved_search.scoring_weights is None


@pytest.mark.parametrize("field", JSONB_FIELDS)
async def test_explicit_empty_jsonb_object_is_distinct_from_null(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    field: str,
) -> None:
    """NULL means "never specified"; an explicitly stored empty JSON object
    means "specified as empty" — the two must round-trip as distinguishable
    values, mirroring the same NULL-vs-empty-array distinction already
    proven for the `text[]` columns."""
    unset_user = await _insert_user(db_session, make_user, f"jsonb-unset-{field}@example.com")
    unset_search = make_saved_search(unset_user.id)
    db_session.add(unset_search)

    explicit_user = await _insert_user(db_session, make_user, f"jsonb-empty-{field}@example.com")
    explicit_search = make_saved_search(explicit_user.id)
    setattr(explicit_search, field, {})
    db_session.add(explicit_search)

    await db_session.commit()
    await db_session.refresh(unset_search)
    await db_session.refresh(explicit_search)

    assert getattr(unset_search, field) is None
    assert getattr(explicit_search, field) == {}


async def test_jsonb_round_trip_of_a_nested_dict(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "jsonb-round-trip@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.enabled_sources = {
        "jobspy": ["linkedin", "indeed"],
        "ats_scrapers": [],
    }
    saved_search.scoring_weights = {"title_weight": 2, "nested": {"salary_weight": 1}}
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert saved_search.enabled_sources == {
        "jobspy": ["linkedin", "indeed"],
        "ats_scrapers": [],
    }
    assert saved_search.scoring_weights == {"title_weight": 2, "nested": {"salary_weight": 1}}


@pytest.mark.parametrize("field", JSONB_FIELDS)
async def test_setting_a_top_level_jsonb_key_persists_after_reload(
    db_engine: AsyncEngine, field: str
) -> None:
    """A plain `JSONB` column looks unchanged to SQLAlchemy's unit-of-work
    after an in-place top-level `dict.__setitem__` — the model wraps these
    columns with `MutableDict.as_mutable` specifically so this mutation is
    tracked and actually written on commit."""
    async with real_committed_user_and_saved_search(
        db_engine, f"jsonb-mutate-{field}@example.com", **{field: {"first": 1}}
    ) as (session, _user_id, saved_search_id):
        saved_search = await session.get(SavedSearch, saved_search_id)
        assert saved_search is not None
        getattr(saved_search, field)["second"] = 2
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(SavedSearch, saved_search_id)
            assert reloaded is not None
            assert getattr(reloaded, field) == {"first": 1, "second": 2}


async def test_enabled_sources_provider_list_replacement_persists_after_reload(
    db_engine: AsyncEngine,
) -> None:
    """The documented, supported workaround for `MutableDict`'s nested-
    mutation limitation (see `test_mutating_a_nested_jsonb_value_is_not_tracked`
    below) is to replace the whole top-level value rather than mutate it in
    place: `enabled_sources[provider] = [*old_sources, new_source]` is a
    top-level `__setitem__` on the column itself, so it *is* tracked — using
    the real documented `enabled_sources` shape, not an arbitrary dict."""
    async with real_committed_user_and_saved_search(
        db_engine,
        "enabled-sources-replacement@example.com",
        enabled_sources={"jobspy": ["linkedin"]},
    ) as (session, _user_id, saved_search_id):
        saved_search = await session.get(SavedSearch, saved_search_id)
        assert saved_search is not None
        assert saved_search.enabled_sources is not None
        saved_search.enabled_sources["jobspy"] = ["linkedin", "indeed"]
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(SavedSearch, saved_search_id)
            assert reloaded is not None
            assert reloaded.enabled_sources == {"jobspy": ["linkedin", "indeed"]}


async def test_mutating_a_nested_jsonb_value_is_not_tracked(db_engine: AsyncEngine) -> None:
    """Documents `MutableDict`'s real limitation: only the wrapped column's
    own top-level `__setitem__`/`__delitem__` is instrumented. Mutating a
    value already nested inside it is invisible to the unit-of-work and is
    silently dropped on commit — the exact caveat documented on
    `SavedSearch.enabled_sources`/`scoring_weights`."""
    async with real_committed_user_and_saved_search(
        db_engine,
        "jsonb-nested-mutation@example.com",
        scoring_weights={"nested": {"title_weight": 1}},
    ) as (session, _user_id, saved_search_id):
        saved_search = await session.get(SavedSearch, saved_search_id)
        assert saved_search is not None
        assert saved_search.scoring_weights is not None
        saved_search.scoring_weights["nested"]["title_weight"] = 999  # type: ignore[index]  # not tracked
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(SavedSearch, saved_search_id)
            assert reloaded is not None
            assert reloaded.scoring_weights == {"nested": {"title_weight": 1}}


async def test_enabled_sources_rejects_a_non_object_json_value(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = await _insert_user(db_session, make_user, "enabled-sources-array@example.com")
    await _assert_direct_sql_jsonb_insert_rejected(
        db_session, user.id, "enabled_sources", "'[]'::jsonb"
    )


async def test_enabled_sources_accepts_a_valid_object(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = await _insert_user(db_session, make_user, "enabled-sources-object@example.com")
    await db_session.execute(
        text(
            "INSERT INTO saved_searches "
            "(id, user_id, name, remote_rules, polling_schedule, enabled_sources) "
            "VALUES (gen_random_uuid(), :user_id, 'Direct SQL Search', 'any', 'manual', "
            '\'{"jobspy": ["linkedin"]}\'::jsonb)'
        ).bindparams(user_id=user.id)
    )
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == 1


async def test_enabled_sources_rejects_a_json_null_literal(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    """A JSON `null` value (`'null'::jsonb`) is distinct from SQL `NULL`:
    `jsonb_typeof('null'::jsonb)` is `'null'`, not `'object'`, so the
    object-only CHECK must reject it even though a genuine SQL `NULL` in
    this column is allowed."""
    user = await _insert_user(db_session, make_user, "enabled-sources-json-null@example.com")
    await _assert_direct_sql_jsonb_insert_rejected(
        db_session, user.id, "enabled_sources", "'null'::jsonb"
    )


async def test_scoring_weights_rejects_a_non_object_json_value(
    db_session: AsyncSession, make_user: Callable[..., User]
) -> None:
    user = await _insert_user(db_session, make_user, "scoring-weights-scalar@example.com")
    await _assert_direct_sql_jsonb_insert_rejected(
        db_session, user.id, "scoring_weights", "'1'::jsonb"
    )


@pytest.mark.parametrize("field", ["salary_floor", "preferred_salary", "recency_limit_hours"])
@pytest.mark.parametrize("value", [0, 5])
async def test_non_negative_check_accepts_zero_and_positive(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    field: str,
    value: int,
) -> None:
    user = await _insert_user(db_session, make_user, f"non-negative-ok-{field}-{value}@example.com")
    saved_search = make_saved_search(user.id)
    setattr(saved_search, field, value)
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert getattr(saved_search, field) == value


@pytest.mark.parametrize("field", ["salary_floor", "preferred_salary", "recency_limit_hours"])
async def test_non_negative_check_rejects_negative_value(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    field: str,
) -> None:
    user = await _insert_user(db_session, make_user, f"non-negative-bad-{field}@example.com")
    saved_search = make_saved_search(user.id)
    setattr(saved_search, field, -1)
    db_session.add(saved_search)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("value", [Decimal(0), Decimal(5)])
async def test_radius_miles_non_negative_check_accepts_zero_and_positive(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
    value: Decimal,
) -> None:
    """`radius_miles` requires a non-negative value, same as the integer
    numeric fields — only its precision/scale is left unconstrained."""
    user = await _insert_user(db_session, make_user, f"radius-ok-{value}@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.radius_miles = value
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert saved_search.radius_miles == value


async def test_radius_miles_non_negative_check_rejects_negative_value(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "radius-bad@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.radius_miles = Decimal(-5)
    db_session.add(saved_search)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_radius_miles_preserves_fractional_precision(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    """`radius_miles` has no precision/scale CHECK — a fractional value must
    round-trip exactly, not get truncated or rounded."""
    user = await _insert_user(db_session, make_user, "radius-fractional@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.radius_miles = Decimal("12.75")
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    assert saved_search.radius_miles == Decimal("12.75")


async def test_salary_floor_equal_to_preferred_salary_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-equal@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.salary_floor = 100_000
    saved_search.preferred_salary = 100_000
    db_session.add(saved_search)
    await db_session.commit()  # must not raise


async def test_salary_floor_less_than_preferred_salary_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-range@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.salary_floor = 90_000
    saved_search.preferred_salary = 120_000
    db_session.add(saved_search)
    await db_session.commit()  # must not raise


async def test_salary_floor_greater_than_preferred_salary_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-inverted@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.salary_floor = 150_000
    saved_search.preferred_salary = 100_000
    db_session.add(saved_search)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_salary_floor_without_preferred_salary_is_not_constrained_by_ordering_check(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "salary-floor-only@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.salary_floor = 150_000
    db_session.add(saved_search)
    await db_session.commit()  # must not raise


async def test_preferred_salary_without_salary_floor_is_not_constrained_by_ordering_check(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "preferred-salary-only@example.com")
    saved_search = make_saved_search(user.id)
    saved_search.preferred_salary = 150_000
    db_session.add(saved_search)
    await db_session.commit()  # must not raise


async def test_nonexistent_user_id_rejected(
    db_session: AsyncSession,
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    db_session.add(make_saved_search(uuid.uuid4()))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (await db_session.execute(select(func.count()).select_from(SavedSearch))).scalar_one()
    assert count == 0


async def test_deleting_user_cascades_to_saved_search(db_engine: AsyncEngine) -> None:
    """Uses real, separately-committed transactions so `ON DELETE CASCADE`
    is actually exercised by PostgreSQL, not merely implied by ORM-side
    cascade configuration."""
    async with real_committed_user_and_saved_search(db_engine, "cascade-owner@example.com") as (
        session,
        user_id,
        saved_search_id,
    ):
        user = await session.get(User, user_id)
        assert user is not None
        await session.delete(user)
        await session.commit()

        assert await session.get(SavedSearch, saved_search_id) is None

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(SavedSearch))
        ).scalar_one()
        assert count == 0
        user_count = (
            await verify_session.execute(select(func.count()).select_from(User))
        ).scalar_one()
        assert user_count == 0


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_saved_search: Callable[..., SavedSearch],
) -> None:
    user = await _insert_user(db_session, make_user, "tz@example.com")
    saved_search = make_saved_search(user.id)
    db_session.add(saved_search)
    await db_session.commit()
    await db_session.refresh(saved_search)

    now = datetime.now(UTC)
    assert abs((now - saved_search.created_at).total_seconds()) < 60
    assert abs((now - saved_search.updated_at).total_seconds()) < 60


async def test_updating_a_saved_search_advances_updated_at(db_engine: AsyncEngine) -> None:
    """Same rationale as the other tables' equivalent tests: PostgreSQL's
    `now()` is fixed for the lifetime of one transaction, so this uses real,
    separately-committed transactions."""
    async with real_committed_user_and_saved_search(db_engine, "updated-at@example.com") as (
        session,
        _user_id,
        saved_search_id,
    ):
        saved_search = await session.get(SavedSearch, saved_search_id)
        assert saved_search is not None
        created_at = saved_search.created_at
        first_updated_at = saved_search.updated_at

        saved_search.is_active = False
        await session.commit()
        await session.refresh(saved_search)
        second_updated_at = saved_search.updated_at

        assert second_updated_at > first_updated_at
        assert second_updated_at >= created_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(SavedSearch))
        ).scalar_one()
        assert count == 0
