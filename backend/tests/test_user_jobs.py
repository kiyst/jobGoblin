import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import TextClause, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Job, User, UserJob
from tests.conftest import real_committed_user_job

_CHANGED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_LATER = datetime(2026, 1, 2, tzinfo=UTC)

_PRE_APPLICATION_STATUSES = ("interested", "not_interested")
_POST_APPLICATION_STATUSES = (
    "applied",
    "recruiter_contacted",
    "screening",
    "interviewing",
    "offer",
    "rejected_by_employer",
    "withdrawn_by_user",
)

_DIRECT_SQL_BASE_COLUMNS = {
    "status": "'interested'",
    "status_changed_at": "now()",
}


async def _insert_user_and_job(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (user_id, job_id), each captured immediately after its own
    commit — `session.commit()` expires every attribute of every object in
    the session, so a later commit (e.g. adding a `UserJob`) would
    otherwise expire these ids before they're read."""
    user = make_user(email="user-jobs-fixture@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user_id = user.id

    job = make_job(first_seen_at=_CHANGED_AT, last_seen_at=_CHANGED_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    job_id = job.id

    return user_id, job_id


def _direct_sql_insert_statement(
    user_id: uuid.UUID, job_id: uuid.UUID, overrides: dict[str, str]
) -> tuple[TextClause, dict[str, object]]:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    columns.update(overrides)
    column_names = ["id", "user_id", "job_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":user_id", ":job_id", *columns.values()]
    params: dict[str, object] = {"user_id": user_id, "job_id": job_id}
    stmt = text(
        f"INSERT INTO user_jobs ({', '.join(column_names)}) VALUES ({', '.join(column_values)})"
    )
    return stmt, params


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    overrides: dict[str, str],
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely.
    `id`/`user_id`/`job_id` are always supplied; `status`/`status_changed_at`
    default to a valid row and are replaced (not duplicated) by any of the
    same keys in `overrides`. Asserts PostgreSQL itself rejects the insert,
    and that the session recovers."""
    stmt, params = _direct_sql_insert_statement(user_id, job_id, overrides)
    with pytest.raises(IntegrityError):
        await db_session.execute(stmt.bindparams(**params))
        await db_session.commit()
    await db_session.rollback()


async def _assert_direct_sql_insert_accepted(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    overrides: dict[str, str],
    *,
    returning: str | None = None,
) -> Any:
    stmt, params = _direct_sql_insert_statement(user_id, job_id, overrides)
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
    count = (await db_session.execute(select(func.count()).select_from(UserJob))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_row(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(user_id=user_id, job_id=job_id, status_changed_at=_CHANGED_AT)
    db_session.add(user_job)
    await db_session.commit()
    await db_session.refresh(user_job)

    assert isinstance(user_job.id, uuid.UUID)

    fetched = await db_session.get(UserJob, user_job.id)
    assert fetched is not None
    assert fetched.user_id == user_id
    assert fetched.job_id == job_id
    assert fetched.saved is False
    assert fetched.hidden is False
    assert fetched.archived is False
    assert fetched.applied_at is None
    assert fetched.status == "interested"
    assert fetched.status_changed_at == _CHANGED_AT
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


# --------------------------------------------------------------------------
# user_id / job_id FK — NOT NULL, ON DELETE CASCADE from both parents
# --------------------------------------------------------------------------


async def test_nonexistent_user_id_rejected(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    job = make_job(first_seen_at=_CHANGED_AT, last_seen_at=_CHANGED_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    user_job = make_user_job(user_id=uuid.uuid4(), job_id=job.id, status_changed_at=_CHANGED_AT)
    db_session.add(user_job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_nonexistent_job_id_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_user_job: Callable[..., UserJob],
) -> None:
    user = make_user(email="user-jobs-nonexistent-job@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    user_job = make_user_job(user_id=user.id, job_id=uuid.uuid4(), status_changed_at=_CHANGED_AT)
    db_session.add(user_job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_user_id_omitted_rejected(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    _user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", "job_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":job_id", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO user_jobs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(job_id=job_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_job_id_omitted_rejected(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    user_id, _job_id = await _insert_user_and_job(db_session, make_user, make_job)
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", "user_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":user_id", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO user_jobs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(user_id=user_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_user_cascades_and_isolates_unrelated_row(db_engine: AsyncEngine) -> None:
    """Deleting the referenced `User` must delete (`CASCADE`) their own
    `UserJob` row — never merely null it out. A second, unrelated user's
    own row must be completely unaffected."""
    async with (
        real_committed_user_job(
            db_engine, "user-jobs-user-cascade-1@example.com", status_changed_at=_CHANGED_AT
        ) as (_session_1, user_id_1, _job_id_1, user_job_id_1),
        real_committed_user_job(
            db_engine, "user-jobs-user-cascade-2@example.com", status_changed_at=_CHANGED_AT
        ) as (_session_2, user_id_2, _job_id_2, user_job_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            user_1 = await delete_session.get(User, user_id_1)
            assert user_1 is not None
            await delete_session.delete(user_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            assert await verify_session.get(User, user_id_1) is None
            assert await verify_session.get(UserJob, user_job_id_1) is None

            user_2 = await verify_session.get(User, user_id_2)
            assert user_2 is not None
            user_job_2 = await verify_session.get(UserJob, user_job_id_2)
            assert user_job_2 is not None
            assert user_job_2.user_id == user_id_2


async def test_deleting_job_cascades_and_isolates_unrelated_row(db_engine: AsyncEngine) -> None:
    """Deleting the referenced `Job` must delete (`CASCADE`) its own
    `UserJob` row — never merely null it out. A second, unrelated job's
    own row must be completely unaffected."""
    async with (
        real_committed_user_job(
            db_engine, "user-jobs-job-cascade-1@example.com", status_changed_at=_CHANGED_AT
        ) as (_session_1, _user_id_1, job_id_1, user_job_id_1),
        real_committed_user_job(
            db_engine, "user-jobs-job-cascade-2@example.com", status_changed_at=_CHANGED_AT
        ) as (_session_2, _user_id_2, job_id_2, user_job_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            job_1 = await delete_session.get(Job, job_id_1)
            assert job_1 is not None
            await delete_session.delete(job_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            assert await verify_session.get(Job, job_id_1) is None
            assert await verify_session.get(UserJob, user_job_id_1) is None

            job_2 = await verify_session.get(Job, job_id_2)
            assert job_2 is not None
            user_job_2 = await verify_session.get(UserJob, user_job_id_2)
            assert user_job_2 is not None
            assert user_job_2.job_id == job_id_2


# --------------------------------------------------------------------------
# UNIQUE (user_id, job_id)
# --------------------------------------------------------------------------


async def test_duplicate_user_job_rejected_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    first = make_user_job(user_id=user_id, job_id=job_id, status_changed_at=_CHANGED_AT)
    db_session.add(first)
    await db_session.commit()

    duplicate = make_user_job(user_id=user_id, job_id=job_id, status_changed_at=_CHANGED_AT)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_duplicate_user_job_rejected_via_direct_sql(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    await _assert_direct_sql_insert_accepted(db_session, user_id, job_id, {})
    await _assert_direct_sql_insert_rejected(db_session, user_id, job_id, {})


# --------------------------------------------------------------------------
# status enum + status / applied_at consistency (ADR 0006)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", _PRE_APPLICATION_STATUSES)
async def test_pre_application_status_with_null_applied_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    status: str,
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(
        user_id=user_id,
        job_id=job_id,
        status=status,
        status_changed_at=_CHANGED_AT,
        applied_at=None,
    )
    db_session.add(user_job)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("status", _POST_APPLICATION_STATUSES)
async def test_post_application_status_with_non_null_applied_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    status: str,
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(
        user_id=user_id,
        job_id=job_id,
        status=status,
        status_changed_at=_CHANGED_AT,
        applied_at=_CHANGED_AT,
    )
    db_session.add(user_job)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("status", _PRE_APPLICATION_STATUSES)
async def test_pre_application_status_with_non_null_applied_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    status: str,
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(
        user_id=user_id,
        job_id=job_id,
        status=status,
        status_changed_at=_CHANGED_AT,
        applied_at=_CHANGED_AT,
    )
    db_session.add(user_job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("status", _PRE_APPLICATION_STATUSES)
async def test_direct_sql_pre_application_status_with_non_null_applied_at_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    status: str,
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    await _assert_direct_sql_insert_rejected(
        db_session, user_id, job_id, {"status": f"'{status}'", "applied_at": "now()"}
    )


@pytest.mark.parametrize("status", _POST_APPLICATION_STATUSES)
async def test_post_application_status_with_null_applied_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    status: str,
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(
        user_id=user_id,
        job_id=job_id,
        status=status,
        status_changed_at=_CHANGED_AT,
        applied_at=None,
    )
    db_session.add(user_job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("status", _POST_APPLICATION_STATUSES)
async def test_direct_sql_post_application_status_with_null_applied_at_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    status: str,
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    await _assert_direct_sql_insert_rejected(db_session, user_id, job_id, {"status": f"'{status}'"})


async def test_invalid_status_rejected_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(
        user_id=user_id, job_id=job_id, status="bogus_status", status_changed_at=_CHANGED_AT
    )
    db_session.add(user_job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_invalid_status_rejected(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    await _assert_direct_sql_insert_rejected(
        db_session, user_id, job_id, {"status": "'bogus_status'"}
    )


async def test_direct_sql_status_omitted_rejected(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    """`status` is NOT NULL with no server default — fresh creation must
    explicitly supply `interested` or `not_interested`."""
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["status"]
    column_names = ["id", "user_id", "job_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":user_id", ":job_id", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO user_jobs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(user_id=user_id, job_id=job_id)
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# status_changed_at — NOT NULL, no server default
# --------------------------------------------------------------------------


async def test_direct_sql_status_changed_at_omitted_rejected(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["status_changed_at"]
    column_names = ["id", "user_id", "job_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":user_id", ":job_id", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO user_jobs ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(user_id=user_id, job_id=job_id)
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# created_at / updated_at — standard lifecycle pair, server-defaulted;
# status_changed_at is a distinct business timestamp, never touched by
# an ORM onupdate
# --------------------------------------------------------------------------


async def test_direct_sql_created_and_updated_at_default_to_now(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    row = await _assert_direct_sql_insert_accepted(
        db_session, user_id, job_id, {}, returning="created_at, updated_at"
    )
    assert row is not None
    assert row.created_at is not None
    assert row.updated_at is not None


async def test_timestamps_are_utc_aware(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(user_id=user_id, job_id=job_id, status_changed_at=_CHANGED_AT)
    db_session.add(user_job)
    await db_session.commit()
    await db_session.refresh(user_job)

    assert user_job.status_changed_at.tzinfo is not None
    assert user_job.created_at.tzinfo is not None
    assert user_job.updated_at.tzinfo is not None


async def test_toggling_orthogonal_flag_advances_updated_at_not_status_changed_at(
    db_engine: AsyncEngine,
) -> None:
    """`updated_at` is the standard ORM-`onupdate` lifecycle column — it
    advances on any write to the row. `status_changed_at` is a distinct
    business timestamp that must change only when `status` actually
    changes through `set_status()` — toggling an orthogonal flag like
    `saved` must never touch it."""
    async with real_committed_user_job(
        db_engine, "user-jobs-orthogonal-flag@example.com", status_changed_at=_CHANGED_AT
    ) as (session, _user_id, _job_id, user_job_id):
        user_job = await session.get(UserJob, user_job_id)
        assert user_job is not None
        original_status_changed_at = user_job.status_changed_at
        original_updated_at = user_job.updated_at

        user_job.saved = True
        await session.commit()
        await session.refresh(user_job)

        assert user_job.status_changed_at == original_status_changed_at
        assert user_job.updated_at > original_updated_at


# --------------------------------------------------------------------------
# saved / hidden / archived — independent booleans, default false
# --------------------------------------------------------------------------


async def test_saved_hidden_archived_default_to_false(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(user_id=user_id, job_id=job_id, status_changed_at=_CHANGED_AT)
    db_session.add(user_job)
    await db_session.commit()
    await db_session.refresh(user_job)

    assert user_job.saved is False
    assert user_job.hidden is False
    assert user_job.archived is False


async def test_direct_sql_saved_hidden_archived_default_to_false(
    db_session: AsyncSession, make_user: Callable[..., User], make_job: Callable[..., Job]
) -> None:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    row = await _assert_direct_sql_insert_accepted(
        db_session, user_id, job_id, {}, returning="saved, hidden, archived"
    )
    assert row is not None
    assert row.saved is False
    assert row.hidden is False
    assert row.archived is False


async def test_saved_hidden_archived_independent_of_status_and_each_other(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    """No `CHECK` relates `saved`/`hidden`/`archived` to `status` or to
    each other — an `archived`, `hidden`, unsaved, post-application row is
    just as valid as a fresh, unsaved, unhidden, unarchived one."""
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(
        user_id=user_id,
        job_id=job_id,
        status="offer",
        status_changed_at=_CHANGED_AT,
        applied_at=_CHANGED_AT,
        saved=True,
        hidden=True,
        archived=True,
    )
    db_session.add(user_job)
    await db_session.commit()  # must not raise
