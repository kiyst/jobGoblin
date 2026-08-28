import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import TextClause, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import CollectionRun, CollectionRunProviderAttempt
from tests.conftest import real_committed_collection_run_provider_attempt

_STARTED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_LATER = datetime(2026, 1, 2, tzinfo=UTC)
_EARLIER = datetime(2025, 12, 31, tzinfo=UTC)

_DIRECT_SQL_BASE_COLUMNS = {
    "provider": "'fixture_provider'",
    "source": "'greenhouse'",
    "started_at": "now()",
    "status": "'running'",
}

_ERROR_CATEGORIES = (
    "timeout",
    "rate_limited",
    "auth_error",
    "blocked",
    "parse_error",
    "not_found",
    "upstream_error",
    "unknown",
)


async def _insert_collection_run(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> uuid.UUID:
    """Returns the new run's id, captured immediately after its own
    commit — `session.commit()` expires every attribute of every object in
    the session, so a later commit (e.g. adding an attempt) would
    otherwise expire this id before it's read."""
    run = make_collection_run(started_at=_STARTED_AT)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run.id


def _direct_sql_insert_statement(
    collection_run_id: uuid.UUID, overrides: dict[str, str]
) -> tuple[TextClause, dict[str, object]]:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    columns.update(overrides)
    column_names = ["id", "collection_run_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":collection_run_id", *columns.values()]
    params: dict[str, object] = {"collection_run_id": collection_run_id}
    stmt = text(
        f"INSERT INTO collection_run_provider_attempts ({', '.join(column_names)}) "
        f"VALUES ({', '.join(column_values)})"
    )
    return stmt, params


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession,
    collection_run_id: uuid.UUID,
    overrides: dict[str, str],
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely.
    `id`/`collection_run_id` are always supplied; `provider`/`source`/
    `started_at`/`status` default to a valid row and are replaced (not
    duplicated) by any of the same keys in `overrides`. Asserts PostgreSQL
    itself rejects the insert, and that the session recovers."""
    stmt, params = _direct_sql_insert_statement(collection_run_id, overrides)
    with pytest.raises(IntegrityError):
        await db_session.execute(stmt.bindparams(**params))
        await db_session.commit()
    await db_session.rollback()


async def _assert_direct_sql_insert_accepted(
    db_session: AsyncSession,
    collection_run_id: uuid.UUID,
    overrides: dict[str, str],
    *,
    returning: str | None = None,
) -> Any:
    stmt, params = _direct_sql_insert_statement(collection_run_id, overrides)
    if returning:
        stmt = text(f"{stmt.text} RETURNING {returning}")
    result = await db_session.execute(stmt.bindparams(**params))
    await db_session.commit()  # must not raise
    if returning:
        return result.one()
    return None


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (
        await db_session.execute(select(func.count()).select_from(CollectionRunProviderAttempt))
    ).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_attempt(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert isinstance(attempt.id, uuid.UUID)

    fetched = await db_session.get(CollectionRunProviderAttempt, attempt.id)
    assert fetched is not None
    assert fetched.collection_run_id == run_id
    assert fetched.provider == "fixture_provider"
    assert fetched.source == "greenhouse"
    assert fetched.started_at == _STARTED_AT
    assert fetched.completed_at is None
    assert fetched.status == "running"
    assert fetched.jobs_discovered == 0
    assert fetched.jobs_inserted == 0
    assert fetched.jobs_updated == 0
    assert fetched.retry_count == 0
    assert fetched.rate_limited is False
    assert fetched.error_category is None
    assert fetched.error_message is None
    assert fetched.incomplete_results is False
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


# --------------------------------------------------------------------------
# collection_run_id FK — NOT NULL, ON DELETE CASCADE
# --------------------------------------------------------------------------


async def test_nonexistent_collection_run_id_rejected(
    db_session: AsyncSession,
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    attempt = make_collection_run_provider_attempt(
        collection_run_id=uuid.uuid4(),
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_collection_run_id_omitted_rejected(db_session: AsyncSession) -> None:
    """`collection_run_id` is NOT NULL — an attempt row cannot exist
    without its parent run."""
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO collection_run_provider_attempts ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_collection_run_cascades_and_isolates_unrelated_attempt(
    db_engine: AsyncEngine,
) -> None:
    """Deleting the parent `CollectionRun` must delete (`CASCADE`) its own
    attempt row — never merely null it out, since an attempt row has no
    independent meaning without its run. A second, unrelated run's own
    attempt row must be completely unaffected."""
    async with (
        real_committed_collection_run_provider_attempt(
            db_engine,
            "cr-provider-attempt-1@example.com",
            provider="fixture_provider",
            source="greenhouse",
            started_at=_STARTED_AT,
        ) as (_session_1, _user_id_1, _saved_search_id_1, run_id_1, attempt_id_1),
        real_committed_collection_run_provider_attempt(
            db_engine,
            "cr-provider-attempt-2@example.com",
            provider="fixture_provider",
            source="greenhouse",
            started_at=_STARTED_AT,
        ) as (_session_2, _user_id_2, _saved_search_id_2, run_id_2, attempt_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            run_1 = await delete_session.get(CollectionRun, run_id_1)
            assert run_1 is not None
            await delete_session.delete(run_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            assert await verify_session.get(CollectionRun, run_id_1) is None
            assert await verify_session.get(CollectionRunProviderAttempt, attempt_id_1) is None

            run_2 = await verify_session.get(CollectionRun, run_id_2)
            assert run_2 is not None
            attempt_2 = await verify_session.get(CollectionRunProviderAttempt, attempt_id_2)
            assert attempt_2 is not None
            assert attempt_2.collection_run_id == run_id_2


# --------------------------------------------------------------------------
# UNIQUE (collection_run_id, provider, source)
# --------------------------------------------------------------------------


async def test_duplicate_collection_run_provider_source_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    first = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(first)
    await db_session.commit()

    duplicate = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_duplicate_collection_run_provider_source_rejected_via_direct_sql(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_accepted(db_session, run_id, {})
    await _assert_direct_sql_insert_rejected(db_session, run_id, {})


async def test_same_provider_two_sources_coexist_under_one_run(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    """The exact Phase 2 fixture scenario (ARCHITECTURE.md §11): one
    provider (`fixture_provider`) executes two sources under the same
    run — `healthy_source` completes, `broken_source` fails. Both rows
    coexist under the same `collection_run_id` because the `UNIQUE`
    constraint keys on `(collection_run_id, provider, source)`, not
    `(collection_run_id, provider)` alone."""
    run_id = await _insert_collection_run(db_session, make_collection_run)

    healthy = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="healthy_source",
        started_at=_STARTED_AT,
        status="completed",
        completed_at=_LATER,
        jobs_discovered=5,
        jobs_inserted=5,
    )
    failed = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="broken_source",
        started_at=_STARTED_AT,
        status="failed",
        completed_at=_LATER,
        error_category="upstream_error",
        error_message="503 from upstream",
    )
    db_session.add_all([healthy, failed])
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(select(func.count()).select_from(CollectionRunProviderAttempt))
    ).scalar_one()
    assert count == 2


# --------------------------------------------------------------------------
# status enum
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["running", "completed", "partial", "failed"])
async def test_valid_status_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    status: str,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    completed_at = None if status == "running" else _LATER
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status=status,
        completed_at=completed_at,
    )
    db_session.add(attempt)
    await db_session.commit()  # must not raise


async def test_invalid_status_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="bogus_status",
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_invalid_status_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {"status": "'bogus_status'"})


async def test_direct_sql_status_omitted_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    """`status` is NOT NULL with no server default — fresh creation must
    explicitly supply `'running'`."""
    run_id = await _insert_collection_run(db_session, make_collection_run)
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["status"]
    column_names = ["id", "collection_run_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":collection_run_id", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO collection_run_provider_attempts ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(collection_run_id=run_id)
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# status / completed_at lifecycle consistency matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
async def test_terminal_status_with_completed_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    status: str,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status=status,
        completed_at=_LATER,
    )
    db_session.add(attempt)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
async def test_direct_sql_terminal_status_with_completed_at_accepted(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], status: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_accepted(
        db_session, run_id, {"status": f"'{status}'", "completed_at": "now()"}
    )


async def test_running_status_with_null_completed_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="running",
        completed_at=None,
    )
    db_session.add(attempt)
    await db_session.commit()  # must not raise


async def test_running_status_with_non_null_completed_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="running",
        completed_at=_LATER,
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_running_status_with_non_null_completed_at_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {"completed_at": "now()"})


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
async def test_terminal_status_with_null_completed_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    status: str,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status=status,
        completed_at=None,
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
async def test_direct_sql_terminal_status_with_null_completed_at_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], status: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {"status": f"'{status}'"})


# --------------------------------------------------------------------------
# completed_at >= started_at ordering
# --------------------------------------------------------------------------


async def test_completed_at_equal_started_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="completed",
        completed_at=_STARTED_AT,
    )
    db_session.add(attempt)
    await db_session.commit()  # must not raise


async def test_completed_at_after_started_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="completed",
        completed_at=_LATER,
    )
    db_session.add(attempt)
    await db_session.commit()  # must not raise


async def test_completed_at_before_started_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="completed",
        completed_at=_EARLIER,
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_completed_at_equal_started_at_accepted(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_accepted(
        db_session,
        run_id,
        {
            "status": "'completed'",
            "started_at": "'2026-01-01T00:00:00+00'::timestamptz",
            "completed_at": "'2026-01-01T00:00:00+00'::timestamptz",
        },
    )


async def test_direct_sql_completed_at_after_started_at_accepted(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_accepted(
        db_session,
        run_id,
        {
            "status": "'completed'",
            "started_at": "'2026-01-01T00:00:00+00'::timestamptz",
            "completed_at": "'2026-01-02T00:00:00+00'::timestamptz",
        },
    )


async def test_direct_sql_completed_at_before_started_at_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(
        db_session,
        run_id,
        {
            "status": "'completed'",
            "started_at": "'2026-01-02T00:00:00+00'::timestamptz",
            "completed_at": "'2026-01-01T00:00:00+00'::timestamptz",
        },
    )


# --------------------------------------------------------------------------
# started_at — NOT NULL, no server default
# --------------------------------------------------------------------------


async def test_direct_sql_started_at_omitted_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["started_at"]
    column_names = ["id", "collection_run_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":collection_run_id", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO collection_run_provider_attempts ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(collection_run_id=run_id)
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# created_at / updated_at — standard lifecycle pair, server-defaulted
# --------------------------------------------------------------------------


async def test_direct_sql_created_and_updated_at_default_to_now(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    row = await _assert_direct_sql_insert_accepted(
        db_session, run_id, {}, returning="created_at, updated_at"
    )
    assert row is not None
    assert row.created_at is not None
    assert row.updated_at is not None


async def test_updated_at_advances_on_real_committed_update(db_engine: AsyncEngine) -> None:
    async with real_committed_collection_run_provider_attempt(
        db_engine,
        "cr-provider-attempt-updated-at@example.com",
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    ) as (session, _user_id, _saved_search_id, _run_id, attempt_id):
        attempt = await session.get(CollectionRunProviderAttempt, attempt_id)
        assert attempt is not None
        original_updated_at = attempt.updated_at

        attempt.status = "completed"
        attempt.completed_at = _LATER
        await session.commit()
        await session.refresh(attempt)

        assert attempt.updated_at > original_updated_at


async def test_timestamps_are_utc_aware(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="completed",
        completed_at=_LATER,
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert attempt.started_at.tzinfo is not None
    assert attempt.completed_at is not None
    assert attempt.completed_at.tzinfo is not None
    assert attempt.created_at.tzinfo is not None
    assert attempt.updated_at.tzinfo is not None


# --------------------------------------------------------------------------
# jobs_discovered / jobs_inserted / jobs_updated / retry_count — non-negative
# counters, default 0
# --------------------------------------------------------------------------

_COUNTER_COLUMNS = ("jobs_discovered", "jobs_inserted", "jobs_updated", "retry_count")


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_counter_defaults_to_zero_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    column: str,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert getattr(attempt, column) == 0


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_direct_sql_counter_defaults_to_zero(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], column: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    row = await _assert_direct_sql_insert_accepted(db_session, run_id, {}, returning=column)
    assert row is not None
    assert getattr(row, column) == 0


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
@pytest.mark.parametrize("value", [0, 5])
async def test_counter_non_negative_values_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    column: str,
    value: int,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        **{column: value},
    )
    db_session.add(attempt)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_counter_negative_value_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    column: str,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        **{column: -1},
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("column", _COUNTER_COLUMNS)
async def test_direct_sql_counter_negative_value_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], column: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {column: "-1"})


# --------------------------------------------------------------------------
# rate_limited / incomplete_results — independent booleans, default false
# --------------------------------------------------------------------------


async def test_rate_limited_and_incomplete_results_default_to_false(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert attempt.rate_limited is False
    assert attempt.incomplete_results is False


async def test_direct_sql_rate_limited_and_incomplete_results_default_to_false(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    row = await _assert_direct_sql_insert_accepted(
        db_session, run_id, {}, returning="rate_limited, incomplete_results"
    )
    assert row is not None
    assert row.rate_limited is False
    assert row.incomplete_results is False


async def test_rate_limited_true_persists_after_reload_and_is_independent_of_status(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    """`rate_limited` is an independent boolean like `incomplete_results` —
    no `CHECK` ties it to `status` or to `incomplete_results`. A `partial`
    row may be `rate_limited = true` while `incomplete_results = false`,
    proving all three vary independently at the database level."""
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="partial",
        completed_at=_LATER,
        rate_limited=True,
        incomplete_results=False,
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert attempt.rate_limited is True
    assert attempt.incomplete_results is False
    assert attempt.status == "partial"


async def test_incomplete_results_independent_of_status(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    """No `CHECK` ties `incomplete_results` to `status` — a clean,
    completed run may still be flagged as incomplete (e.g. a result cap
    was hit), and a `partial` row may still have `incomplete_results =
    false` at the database level; Phase 2's application logic establishes
    the normal pairing, not a database constraint."""
    run_id = await _insert_collection_run(db_session, make_collection_run)
    completed_but_incomplete = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="completed",
        completed_at=_LATER,
        incomplete_results=True,
    )
    partial_but_not_flagged = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="lever",
        started_at=_STARTED_AT,
        status="partial",
        completed_at=_LATER,
        incomplete_results=False,
    )
    db_session.add_all([completed_but_incomplete, partial_but_not_flagged])
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# provider / source — required canonical identifiers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_provider_and_source_are_lowercased_and_trimmed_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    column: str,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    kwargs: dict[str, object] = {
        "collection_run_id": run_id,
        "provider": "fixture_provider",
        "source": "greenhouse",
        "started_at": _STARTED_AT,
    }
    kwargs[column] = "\t ATS_Scrapers \n"
    attempt = make_collection_run_provider_attempt(**kwargs)
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert getattr(attempt, column) == "ats_scrapers"


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_non_lowercase_provider_or_source_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], column: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {column: "'Greenhouse'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_whitespace_wrapped_provider_or_source_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], column: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {column: r"E'\tgreenhouse\n'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_empty_provider_or_source_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], column: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {column: "''"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_non_ascii_provider_or_source_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    column: str,
) -> None:
    """The ASCII slug-format `CHECK`, not the ORM's `str.lower()`
    validator, is what actually rejects this: "café" is already lowercase
    under Python's `lower()`, so the ORM passes it through unchanged, and
    only the slug-format `CHECK` (ASCII-only by construction) catches
    it."""
    run_id = await _insert_collection_run(db_session, make_collection_run)
    kwargs: dict[str, object] = {
        "collection_run_id": run_id,
        "provider": "fixture_provider",
        "source": "greenhouse",
        "started_at": _STARTED_AT,
    }
    kwargs[column] = "café"
    attempt = make_collection_run_provider_attempt(**kwargs)
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_non_ascii_provider_or_source_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], column: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {column: "'café'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_embedded_space_provider_or_source_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    column: str,
) -> None:
    """Already trimmed and already lowercase by the ORM validator, so only
    the slug-format `CHECK` (not the ORM validator itself) rejects this —
    same rationale as `test_non_ascii_provider_or_source_rejected_on_orm_path`."""
    run_id = await _insert_collection_run(db_session, make_collection_run)
    kwargs: dict[str, object] = {
        "collection_run_id": run_id,
        "provider": "fixture_provider",
        "source": "greenhouse",
        "started_at": _STARTED_AT,
    }
    kwargs[column] = "green house"
    attempt = make_collection_run_provider_attempt(**kwargs)
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_embedded_space_provider_or_source_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun], column: str
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {column: "'green house'"})


# --------------------------------------------------------------------------
# error_category — nullable, plain CHECK-restricted enum, no ORM transform
# --------------------------------------------------------------------------


async def test_error_category_defaults_to_none(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert attempt.error_category is None


@pytest.mark.parametrize("category", _ERROR_CATEGORIES)
async def test_error_category_valid_values_accepted_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
    category: str,
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="failed",
        completed_at=_LATER,
        error_category=category,
    )
    db_session.add(attempt)
    await db_session.commit()  # must not raise


async def test_error_category_invalid_value_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="failed",
        completed_at=_LATER,
        error_category="bogus_category",
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_error_category_invalid_value_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(
        db_session, run_id, {"error_category": "'bogus_category'"}
    )


async def test_error_category_no_case_fold_uppercase_rejected_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    """`error_category` is a plain `CHECK`-restricted enum like `status` —
    unlike `provider`/`source`, it gets no ORM case-fold. An otherwise-
    valid value in the wrong case is rejected, not silently normalized."""
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        status="failed",
        completed_at=_LATER,
        error_category="TIMEOUT",
    )
    db_session.add(attempt)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# error_message — nullable, case-preserving free text, trim/blank-to-None
# --------------------------------------------------------------------------


async def test_error_message_defaults_to_none(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert attempt.error_message is None


async def test_error_message_whitespace_only_becomes_none_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        error_message="   \t\n  ",
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert attempt.error_message is None


async def test_error_message_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession,
    make_collection_run: Callable[..., CollectionRun],
    make_collection_run_provider_attempt: Callable[..., CollectionRunProviderAttempt],
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    attempt = make_collection_run_provider_attempt(
        collection_run_id=run_id,
        provider="fixture_provider",
        source="greenhouse",
        started_at=_STARTED_AT,
        error_message="  Mixed-Case Value  ",
    )
    db_session.add(attempt)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert attempt.error_message == "Mixed-Case Value"


async def test_direct_sql_empty_error_message_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {"error_message": "''"})


async def test_direct_sql_whitespace_wrapped_error_message_rejected(
    db_session: AsyncSession, make_collection_run: Callable[..., CollectionRun]
) -> None:
    run_id = await _insert_collection_run(db_session, make_collection_run)
    await _assert_direct_sql_insert_rejected(db_session, run_id, {"error_message": r"E'\tvalue\n'"})
