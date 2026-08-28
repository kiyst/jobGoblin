import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import TextClause, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import CollectionRun, SavedSearch
from tests.conftest import real_committed_collection_run

_STARTED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_LATER = datetime(2026, 1, 2, tzinfo=UTC)
_EARLIER = datetime(2025, 12, 31, tzinfo=UTC)

_DIRECT_SQL_BASE_COLUMNS = {
    "started_at": "now()",
    "status": "'running'",
}


def _direct_sql_insert_statement(
    overrides: dict[str, str], *, saved_search_id: uuid.UUID | None = None
) -> tuple[TextClause, dict[str, object]]:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    columns.update(overrides)
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    params: dict[str, object] = {}
    if saved_search_id is not None:
        column_names.append("saved_search_id")
        column_values.append(":saved_search_id")
        params["saved_search_id"] = saved_search_id
    stmt = text(
        f"INSERT INTO collection_runs ({', '.join(column_names)}) "
        f"VALUES ({', '.join(column_values)})"
    )
    return stmt, params


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession,
    overrides: dict[str, str],
    *,
    saved_search_id: uuid.UUID | None = None,
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely.
    `id` is always supplied; `started_at`/`status` default to a valid row
    and are replaced (not duplicated) by any of the same keys in
    `overrides`. Asserts PostgreSQL itself rejects the insert, and that
    the session recovers."""
    stmt, params = _direct_sql_insert_statement(overrides, saved_search_id=saved_search_id)
    with pytest.raises(IntegrityError):
        await db_session.execute(stmt.bindparams(**params) if params else stmt)
        await db_session.commit()
    await db_session.rollback()


async def _assert_direct_sql_insert_accepted(
    db_session: AsyncSession,
    overrides: dict[str, str],
    *,
    saved_search_id: uuid.UUID | None = None,
    returning: str | None = None,
) -> Any:
    stmt, params = _direct_sql_insert_statement(overrides, saved_search_id=saved_search_id)
    if returning:
        stmt = text(f"{stmt.text} RETURNING {returning}")
    result = await db_session.execute(stmt.bindparams(**params) if params else stmt)
    await db_session.commit()  # must not raise
    if returning:
        return result.one()
    return None


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (await db_session.execute(select(func.count()).select_from(CollectionRun))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_run(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert isinstance(run.id, uuid.UUID)

    fetched = await db_session.get(CollectionRun, run.id)
    assert fetched is not None
    assert fetched.saved_search_id is None
    assert fetched.started_at == _STARTED_AT
    assert fetched.completed_at is None
    assert fetched.status == "running"
    assert fetched.providers_attempted == []
    assert fetched.providers_enforced_locally == {}
    assert fetched.jobs_discovered == 0
    assert fetched.jobs_inserted == 0
    assert fetched.jobs_updated == 0
    assert fetched.failures == []
    assert fetched.duration_ms is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


# --------------------------------------------------------------------------
# saved_search_id FK
# --------------------------------------------------------------------------


async def test_nonexistent_saved_search_id_rejected(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, saved_search_id=uuid.uuid4())
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_saved_search_sets_fk_null_and_preserves_run(
    db_engine: AsyncEngine,
) -> None:
    """Deleting the referenced `SavedSearch` must null out
    `saved_search_id` and preserve the run row — never delete it. A
    second, unrelated run (referencing a different, undeleted saved
    search) must be completely unaffected."""
    async with (
        real_committed_collection_run(
            db_engine, "collection-run-1@example.com", started_at=_STARTED_AT
        ) as (_session_1, _user_id_1, saved_search_id_1, run_id_1),
        real_committed_collection_run(
            db_engine, "collection-run-2@example.com", started_at=_STARTED_AT
        ) as (_session_2, _user_id_2, saved_search_id_2, run_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            saved_search_1 = await delete_session.get(SavedSearch, saved_search_id_1)
            assert saved_search_1 is not None
            await delete_session.delete(saved_search_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            run_1 = await verify_session.get(CollectionRun, run_id_1)
            assert run_1 is not None
            assert run_1.saved_search_id is None

            assert await verify_session.get(SavedSearch, saved_search_id_1) is None

            run_2 = await verify_session.get(CollectionRun, run_id_2)
            assert run_2 is not None
            assert run_2.saved_search_id == saved_search_id_2

            saved_search_2 = await verify_session.get(SavedSearch, saved_search_id_2)
            assert saved_search_2 is not None


# --------------------------------------------------------------------------
# status enum
# --------------------------------------------------------------------------


async def test_invalid_status_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status="bogus_status")
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_invalid_status_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"status": "'bogus_status'"})


async def test_direct_sql_status_omitted_rejected(db_session: AsyncSession) -> None:
    """`status` is NOT NULL with no server default — fresh creation must
    explicitly supply `'running'`."""
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["status"]
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO collection_runs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# status / completed_at lifecycle consistency matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["completed", "completed_with_errors", "failed"])
async def test_terminal_status_with_completed_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    status: str,
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status=status, completed_at=_LATER)
    db_session.add(run)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("status", ["completed", "completed_with_errors", "failed"])
async def test_direct_sql_terminal_status_with_completed_at_accepted(
    db_session: AsyncSession, status: str
) -> None:
    await _assert_direct_sql_insert_accepted(
        db_session, {"status": f"'{status}'", "completed_at": "now()"}
    )


async def test_running_status_with_null_completed_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status="running", completed_at=None)
    db_session.add(run)
    await db_session.commit()  # must not raise


async def test_running_status_with_non_null_completed_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status="running", completed_at=_LATER)
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_running_status_with_non_null_completed_at_rejected(
    db_session: AsyncSession,
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"completed_at": "now()"})


@pytest.mark.parametrize("status", ["completed", "completed_with_errors", "failed"])
async def test_terminal_status_with_null_completed_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    status: str,
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status=status, completed_at=None)
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("status", ["completed", "completed_with_errors", "failed"])
async def test_direct_sql_terminal_status_with_null_completed_at_rejected(
    db_session: AsyncSession, status: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"status": f"'{status}'"})


# --------------------------------------------------------------------------
# completed_at >= started_at ordering
# --------------------------------------------------------------------------


async def test_completed_at_equal_started_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status="completed", completed_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()  # must not raise


async def test_completed_at_after_started_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status="completed", completed_at=_LATER)
    db_session.add(run)
    await db_session.commit()  # must not raise


async def test_completed_at_before_started_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status="completed", completed_at=_EARLIER)
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_completed_at_before_started_at_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(
        db_session,
        {
            "status": "'completed'",
            "started_at": "'2026-01-02T00:00:00+00'::timestamptz",
            "completed_at": "'2026-01-01T00:00:00+00'::timestamptz",
        },
    )


# --------------------------------------------------------------------------
# started_at — NOT NULL, no server default
# --------------------------------------------------------------------------


async def test_direct_sql_started_at_omitted_rejected(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["started_at"]
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO collection_runs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# created_at / updated_at — standard lifecycle pair, server-defaulted
# --------------------------------------------------------------------------


async def test_direct_sql_created_and_updated_at_default_to_now(db_session: AsyncSession) -> None:
    row = await _assert_direct_sql_insert_accepted(
        db_session, {}, returning="created_at, updated_at"
    )
    assert row is not None
    assert row.created_at is not None
    assert row.updated_at is not None


async def test_updated_at_advances_on_real_committed_update(db_engine: AsyncEngine) -> None:
    async with real_committed_collection_run(
        db_engine, "collection-run-updated-at@example.com", started_at=_STARTED_AT
    ) as (session, _user_id, _saved_search_id, run_id):
        run = await session.get(CollectionRun, run_id)
        assert run is not None
        original_updated_at = run.updated_at

        run.status = "completed"
        run.completed_at = _LATER
        await session.commit()
        await session.refresh(run)

        assert run.updated_at > original_updated_at


async def test_timestamps_are_utc_aware(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, status="completed", completed_at=_LATER)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.started_at.tzinfo is not None
    assert run.completed_at is not None
    assert run.completed_at.tzinfo is not None
    assert run.created_at.tzinfo is not None
    assert run.updated_at.tzinfo is not None


# --------------------------------------------------------------------------
# jobs_discovered / jobs_inserted / jobs_updated — non-negative counters,
# default 0
# --------------------------------------------------------------------------

_COUNTER_COLUMNS = ("jobs_discovered", "jobs_inserted", "jobs_updated")


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_counter_defaults_to_zero_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    column: str,
) -> None:
    run = make_collection_run(started_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert getattr(run, column) == 0


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_direct_sql_counter_defaults_to_zero(db_session: AsyncSession, column: str) -> None:
    row = await _assert_direct_sql_insert_accepted(db_session, {}, returning=column)
    assert row is not None
    assert getattr(row, column) == 0


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
@pytest.mark.parametrize("value", [0, 5])
async def test_counter_non_negative_values_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    column: str,
    value: int,
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, **{column: value})
    db_session.add(run)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_counter_negative_value_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    column: str,
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, **{column: -1})
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_direct_sql_counter_negative_value_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: "-1"})


# --------------------------------------------------------------------------
# duration_ms — nullable, non-negative
# --------------------------------------------------------------------------


async def test_duration_ms_defaults_to_none(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.duration_ms is None


@pytest.mark.parametrize("value", [0, 5000])
async def test_duration_ms_non_negative_values_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    value: int,
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, duration_ms=value)
    db_session.add(run)
    await db_session.commit()  # must not raise


async def test_duration_ms_negative_value_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT, duration_ms=-1)
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_duration_ms_negative_value_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"duration_ms": "-1"})


# --------------------------------------------------------------------------
# providers_attempted — TEXT[], NOT NULL, default '{}', MutableList-wrapped
# --------------------------------------------------------------------------


async def test_providers_attempted_defaults_to_empty_list_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.providers_attempted == []


async def test_direct_sql_providers_attempted_defaults_to_empty_array(
    db_session: AsyncSession,
) -> None:
    row = await _assert_direct_sql_insert_accepted(db_session, {}, returning="providers_attempted")
    assert row is not None
    assert row.providers_attempted == []


async def test_providers_attempted_round_trips_order_preserved(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(
        started_at=_STARTED_AT, providers_attempted=["healthy_source", "broken_source"]
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.providers_attempted == ["healthy_source", "broken_source"]


async def test_providers_attempted_in_place_append_persists_after_separate_session_reload(
    db_engine: AsyncEngine,
) -> None:
    """`MutableList`-wrapped: an in-place `.append()` on an already-loaded
    row must be tracked by the unit of work and survive a genuinely
    separate-session reload, not just the same session's identity map."""
    async with real_committed_collection_run(
        db_engine,
        "collection-run-providers-append@example.com",
        started_at=_STARTED_AT,
        providers_attempted=["healthy_source"],
    ) as (session, _user_id, _saved_search_id, run_id):
        run = await session.get(CollectionRun, run_id)
        assert run is not None
        run.providers_attempted.append("broken_source")
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(CollectionRun, run_id)
            assert reloaded is not None
            assert reloaded.providers_attempted == ["healthy_source", "broken_source"]


async def test_defaults_are_independent_across_multiple_rows(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    """A classic mutable-default trap: appending to one row's defaulted
    `providers_attempted`/`failures` must never affect another row's
    independently-defaulted value."""
    run_1 = make_collection_run(started_at=_STARTED_AT)
    run_2 = make_collection_run(started_at=_STARTED_AT)
    db_session.add_all([run_1, run_2])
    await db_session.commit()
    await db_session.refresh(run_1)
    await db_session.refresh(run_2)

    run_1.providers_attempted.append("healthy_source")
    run_1.failures.append({"provider": "broken_source", "source": "x", "error": "boom"})
    await db_session.commit()
    await db_session.refresh(run_1)
    await db_session.refresh(run_2)

    assert run_1.providers_attempted == ["healthy_source"]
    assert run_2.providers_attempted == []
    assert run_1.failures == [{"provider": "broken_source", "source": "x", "error": "boom"}]
    assert run_2.failures == []


# --------------------------------------------------------------------------
# providers_enforced_locally — JSONB object, NOT NULL, default '{}', not
# Mutable-wrapped (whole-value assignment only)
# --------------------------------------------------------------------------


async def test_providers_enforced_locally_defaults_to_empty_object_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.providers_enforced_locally == {}


async def test_direct_sql_providers_enforced_locally_defaults_to_empty_object(
    db_session: AsyncSession,
) -> None:
    row = await _assert_direct_sql_insert_accepted(
        db_session, {}, returning="providers_enforced_locally"
    )
    assert row is not None
    assert row.providers_enforced_locally == {}


async def test_providers_enforced_locally_whole_value_assignment_persists(
    db_engine: AsyncEngine,
) -> None:
    shape: dict[str, object] = {"fixture_provider": {"healthy_source": ["salary_floor"]}}
    async with real_committed_collection_run(
        db_engine,
        "collection-run-enforced-locally@example.com",
        started_at=_STARTED_AT,
    ) as (session, _user_id, _saved_search_id, run_id):
        run = await session.get(CollectionRun, run_id)
        assert run is not None
        run.providers_enforced_locally = shape
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(CollectionRun, run_id)
            assert reloaded is not None
            assert reloaded.providers_enforced_locally == shape


async def test_direct_sql_providers_enforced_locally_sql_null_rejected(
    db_session: AsyncSession,
) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", *columns.keys(), "providers_enforced_locally"]
    column_values = ["gen_random_uuid()", *columns.values(), "NULL"]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO collection_runs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize(
    "wrong_shape_json",
    ["'null'::jsonb", "'[1, 2]'::jsonb", "'\"scalar\"'::jsonb", "'42'::jsonb"],
    ids=["json_null", "array", "scalar_string", "scalar_number"],
)
async def test_direct_sql_providers_enforced_locally_wrong_shape_rejected(
    db_session: AsyncSession, wrong_shape_json: str
) -> None:
    await _assert_direct_sql_insert_rejected(
        db_session, {"providers_enforced_locally": wrong_shape_json}
    )


# --------------------------------------------------------------------------
# failures — JSONB array, NOT NULL, default '[]', MutableList-wrapped
# --------------------------------------------------------------------------


async def test_failures_defaults_to_empty_list_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run = make_collection_run(started_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    assert run.failures == []


async def test_direct_sql_failures_defaults_to_empty_array(db_session: AsyncSession) -> None:
    row = await _assert_direct_sql_insert_accepted(db_session, {}, returning="failures")
    assert row is not None
    assert row.failures == []


async def test_failures_in_place_append_persists_after_separate_session_reload(
    db_engine: AsyncEngine,
) -> None:
    """`MutableList`-wrapped over jsonb: a top-level `.append()` on an
    already-loaded row must be tracked and survive a separate-session
    reload."""
    async with real_committed_collection_run(
        db_engine, "collection-run-failures-append@example.com", started_at=_STARTED_AT
    ) as (session, _user_id, _saved_search_id, run_id):
        run = await session.get(CollectionRun, run_id)
        assert run is not None
        run.failures.append(
            {"provider": "fixture_provider", "source": "broken_source", "error": "timeout"}
        )
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(CollectionRun, run_id)
            assert reloaded is not None
            assert reloaded.failures == [
                {"provider": "fixture_provider", "source": "broken_source", "error": "timeout"}
            ]


async def test_direct_sql_failures_sql_null_rejected(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", *columns.keys(), "failures"]
    column_values = ["gen_random_uuid()", *columns.values(), "NULL"]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO collection_runs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize(
    "wrong_shape_json",
    ["'null'::jsonb", "'{\"a\": 1}'::jsonb", "'\"scalar\"'::jsonb", "'42'::jsonb"],
    ids=["json_null", "object", "scalar_string", "scalar_number"],
)
async def test_direct_sql_failures_wrong_shape_rejected(
    db_session: AsyncSession, wrong_shape_json: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"failures": wrong_shape_json})


# --------------------------------------------------------------------------
# Honest partial-failure representation (no CHECK ties failures/counters
# to status)
# --------------------------------------------------------------------------


async def test_planning_time_failure_can_exist_without_a_provider_attempt(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    """A `QueryPlanner` validation failure (ARCHITECTURE.md §6.6 step 2)
    is recorded in `failures` even though the rejected provider was never
    attempted at all — `providers_attempted` deliberately does not (and
    must not) list it. Nothing in the schema requires any correlation
    between `failures` entries and `providers_attempted` entries."""
    run = make_collection_run(
        started_at=_STARTED_AT,
        status="failed",
        completed_at=_LATER,
        providers_attempted=[],
        failures=[
            {
                "provider": "unknown_provider",
                "source": "unknown_source",
                "error": "unknown source in enabled_sources",
            }
        ],
    )
    db_session.add(run)
    await db_session.commit()  # must not raise
    await db_session.refresh(run)

    assert run.providers_attempted == []
    assert len(run.failures) == 1


async def test_completed_with_errors_retains_successful_nonzero_rollups(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    """The exact Phase 2 fixture scenario: one healthy source persists
    jobs, one broken source fails — the run-level rollups must remain
    accurate for the successful source while `failures` records the
    failed one. No `CHECK` blocks this combination."""
    run = make_collection_run(
        started_at=_STARTED_AT,
        status="completed_with_errors",
        completed_at=_LATER,
        providers_attempted=["healthy_source", "broken_source"],
        jobs_discovered=5,
        jobs_inserted=3,
        jobs_updated=2,
        failures=[
            {
                "provider": "fixture_provider",
                "source": "broken_source",
                "error": "timeout",
            }
        ],
    )
    db_session.add(run)
    await db_session.commit()  # must not raise
    await db_session.refresh(run)

    assert run.jobs_discovered == 5
    assert run.jobs_inserted == 3
    assert run.jobs_updated == 2
    assert len(run.failures) == 1
