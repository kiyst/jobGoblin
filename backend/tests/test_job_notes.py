import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import TextClause, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Job, JobNote, User, UserJob
from tests.conftest import real_committed_job_note

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_DIRECT_SQL_BASE_COLUMNS = {
    "body": "'A valid note.'",
}


async def _insert_user_job(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> uuid.UUID:
    """Returns the new user_job's id, captured immediately after its own
    commit — `session.commit()` expires every attribute of every object in
    the session, so a later commit (e.g. adding a `JobNote`) would
    otherwise expire it before it's read."""
    user = make_user(email="job-notes-fixture@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user_id = user.id

    job = make_job(first_seen_at=_NOW, last_seen_at=_NOW)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    job_id = job.id

    user_job = make_user_job(user_id=user_id, job_id=job_id, status_changed_at=_NOW)
    db_session.add(user_job)
    await db_session.commit()
    await db_session.refresh(user_job)
    return user_job.id


def _direct_sql_insert_statement(
    user_job_id: uuid.UUID, overrides: dict[str, str]
) -> tuple[TextClause, dict[str, object]]:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    columns.update(overrides)
    column_names = ["id", "user_job_id", *columns.keys()]
    column_values = ["gen_random_uuid()", ":user_job_id", *columns.values()]
    params: dict[str, object] = {"user_job_id": user_job_id}
    stmt = text(
        f"INSERT INTO job_notes ({', '.join(column_names)}) VALUES ({', '.join(column_values)})"
    )
    return stmt, params


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession,
    user_job_id: uuid.UUID,
    overrides: dict[str, str],
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely.
    `id`/`user_job_id` are always supplied; `body` defaults to a valid row
    and is replaced (not duplicated) by the same key in `overrides`. Asserts
    PostgreSQL itself rejects the insert, and that the session recovers."""
    stmt, params = _direct_sql_insert_statement(user_job_id, overrides)
    with pytest.raises(IntegrityError):
        await db_session.execute(stmt.bindparams(**params))
        await db_session.commit()
    await db_session.rollback()


async def _assert_direct_sql_insert_accepted(
    db_session: AsyncSession,
    user_job_id: uuid.UUID,
    overrides: dict[str, str],
    *,
    returning: str | None = None,
) -> Any:
    stmt, params = _direct_sql_insert_statement(user_job_id, overrides)
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
    count = (await db_session.execute(select(func.count()).select_from(JobNote))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_row(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    make_job_note: Callable[..., JobNote],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    note = make_job_note(user_job_id=user_job_id, body="Applied through referral.")
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    assert isinstance(note.id, uuid.UUID)

    fetched = await db_session.get(JobNote, note.id)
    assert fetched is not None
    assert fetched.user_job_id == user_job_id
    assert fetched.body == "Applied through referral."
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


# --------------------------------------------------------------------------
# user_job_id FK — NOT NULL, ON DELETE CASCADE
# --------------------------------------------------------------------------


async def test_nonexistent_user_job_id_rejected(
    db_session: AsyncSession,
    make_job_note: Callable[..., JobNote],
) -> None:
    note = make_job_note(user_job_id=uuid.uuid4())
    db_session.add(note)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_user_job_id_omitted_rejected(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO job_notes ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# Two-level CASCADE isolation — through User, Job, and UserJob directly
# --------------------------------------------------------------------------


async def test_deleting_user_cascades_through_user_job_and_isolates_unrelated_note(
    db_engine: AsyncEngine,
) -> None:
    """Deleting a `User` cascades through its `UserJob` all the way down to
    its `JobNote` rows — the same two-level-`CASCADE` shape already used by
    `saved_search_titles`/`candidate_skills`. A second, unrelated user's own
    note must be completely unaffected."""
    async with (
        real_committed_job_note(
            db_engine, "job-notes-user-cascade-1@example.com", status_changed_at=_NOW
        ) as (_session_1, user_id_1, _job_id_1, user_job_id_1, note_id_1),
        real_committed_job_note(
            db_engine, "job-notes-user-cascade-2@example.com", status_changed_at=_NOW
        ) as (_session_2, user_id_2, _job_id_2, user_job_id_2, note_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            user_1 = await delete_session.get(User, user_id_1)
            assert user_1 is not None
            await delete_session.delete(user_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            assert await verify_session.get(User, user_id_1) is None
            assert await verify_session.get(UserJob, user_job_id_1) is None
            assert await verify_session.get(JobNote, note_id_1) is None

            assert await verify_session.get(User, user_id_2) is not None
            user_job_2 = await verify_session.get(UserJob, user_job_id_2)
            assert user_job_2 is not None
            note_2 = await verify_session.get(JobNote, note_id_2)
            assert note_2 is not None
            assert note_2.user_job_id == user_job_id_2


async def test_deleting_job_cascades_through_user_job_and_isolates_unrelated_note(
    db_engine: AsyncEngine,
) -> None:
    """Deleting a `Job` cascades through its `UserJob` down to its
    `JobNote` rows. A second, unrelated job's own note must be completely
    unaffected."""
    async with (
        real_committed_job_note(
            db_engine, "job-notes-job-cascade-1@example.com", status_changed_at=_NOW
        ) as (_session_1, _user_id_1, job_id_1, user_job_id_1, note_id_1),
        real_committed_job_note(
            db_engine, "job-notes-job-cascade-2@example.com", status_changed_at=_NOW
        ) as (_session_2, _user_id_2, job_id_2, user_job_id_2, note_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            job_1 = await delete_session.get(Job, job_id_1)
            assert job_1 is not None
            await delete_session.delete(job_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            assert await verify_session.get(Job, job_id_1) is None
            assert await verify_session.get(UserJob, user_job_id_1) is None
            assert await verify_session.get(JobNote, note_id_1) is None

            assert await verify_session.get(Job, job_id_2) is not None
            user_job_2 = await verify_session.get(UserJob, user_job_id_2)
            assert user_job_2 is not None
            note_2 = await verify_session.get(JobNote, note_id_2)
            assert note_2 is not None
            assert note_2.user_job_id == user_job_id_2


async def test_deleting_user_job_cascades_and_isolates_unrelated_note(
    db_engine: AsyncEngine,
) -> None:
    """Deleting a `UserJob` directly (not via its `User`/`Job` parent)
    deletes its own `JobNote` rows. A second, unrelated `UserJob`'s own
    note must be completely unaffected."""
    async with (
        real_committed_job_note(
            db_engine, "job-notes-user-job-cascade-1@example.com", status_changed_at=_NOW
        ) as (_session_1, _user_id_1, _job_id_1, user_job_id_1, note_id_1),
        real_committed_job_note(
            db_engine, "job-notes-user-job-cascade-2@example.com", status_changed_at=_NOW
        ) as (_session_2, _user_id_2, _job_id_2, user_job_id_2, note_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            user_job_1 = await delete_session.get(UserJob, user_job_id_1)
            assert user_job_1 is not None
            await delete_session.delete(user_job_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            assert await verify_session.get(UserJob, user_job_id_1) is None
            assert await verify_session.get(JobNote, note_id_1) is None

            user_job_2 = await verify_session.get(UserJob, user_job_id_2)
            assert user_job_2 is not None
            note_2 = await verify_session.get(JobNote, note_id_2)
            assert note_2 is not None
            assert note_2.user_job_id == user_job_id_2


# --------------------------------------------------------------------------
# body — required, trim-only, non-empty
# --------------------------------------------------------------------------


async def test_direct_sql_body_omitted_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    column_names = ["id", "user_job_id"]
    column_values = ["gen_random_uuid()", ":user_job_id"]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO job_notes ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(user_job_id=user_job_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_body_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    make_job_note: Callable[..., JobNote],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    note = make_job_note(user_job_id=user_job_id, body="  Mixed-Case Note  ")
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    assert note.body == "Mixed-Case Note"


async def test_body_whitespace_only_rejected_on_orm_path(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    make_job_note: Callable[..., JobNote],
) -> None:
    """Unlike `identity_conflicts.resolution` (optional narrative, blank
    collapsed to `NULL`), a `job_notes` row's only reason to exist is to
    hold `body` — a whitespace-only note is rejected outright."""
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    note = make_job_note(user_job_id=user_job_id, body="   \t\n  ")
    db_session.add(note)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_empty_body_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    await _assert_direct_sql_insert_rejected(db_session, user_job_id, {"body": "''"})


async def test_direct_sql_whitespace_wrapped_body_rejected(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    """Already trimmed/case-preserved by the ORM validator on that path —
    direct SQL independently proves the database itself rejects an
    untrimmed value, bypassing the ORM entirely."""
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    await _assert_direct_sql_insert_rejected(db_session, user_job_id, {"body": r"E'\tnote\n'"})


# --------------------------------------------------------------------------
# created_at / updated_at — standard lifecycle pair, server-defaulted
# --------------------------------------------------------------------------


async def test_direct_sql_created_and_updated_at_default_to_now(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    row = await _assert_direct_sql_insert_accepted(
        db_session, user_job_id, {}, returning="created_at, updated_at"
    )
    assert row is not None
    assert row.created_at is not None
    assert row.updated_at is not None


async def test_timestamps_are_utc_aware(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    make_job_note: Callable[..., JobNote],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    note = make_job_note(user_job_id=user_job_id)
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    assert note.created_at.tzinfo is not None
    assert note.updated_at.tzinfo is not None


async def test_defaults_are_independent_across_multiple_rows(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    make_job_note: Callable[..., JobNote],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    first = make_job_note(user_job_id=user_job_id, body="First note.")
    second = make_job_note(user_job_id=user_job_id, body="Second note.")
    db_session.add_all([first, second])
    await db_session.commit()
    await db_session.refresh(first)
    await db_session.refresh(second)

    assert first.body == "First note."
    assert second.body == "Second note."
    assert first.id != second.id


async def test_updated_at_advances_on_real_committed_update(db_engine: AsyncEngine) -> None:
    async with real_committed_job_note(
        db_engine, "job-notes-updated-at@example.com", status_changed_at=_NOW
    ) as (session, _user_id, _job_id, _user_job_id, note_id):
        note = await session.get(JobNote, note_id)
        assert note is not None
        original_updated_at = note.updated_at

        note.body = "Updated note body."
        await session.commit()
        await session.refresh(note)

        assert note.updated_at > original_updated_at


# --------------------------------------------------------------------------
# No UNIQUE constraint — multiple notes per user_job are accepted
# --------------------------------------------------------------------------


async def test_multiple_notes_for_same_user_job_accepted(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    make_job_note: Callable[..., JobNote],
) -> None:
    user_job_id = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    first = make_job_note(user_job_id=user_job_id, body="First note.")
    second = make_job_note(user_job_id=user_job_id, body="Second note.")
    third = make_job_note(user_job_id=user_job_id, body="Third note.")
    db_session.add_all([first, second, third])
    await db_session.commit()  # must not raise

    count = (
        await db_session.execute(
            select(func.count()).select_from(JobNote).where(JobNote.user_job_id == user_job_id)
        )
    ).scalar_one()
    assert count == 3
