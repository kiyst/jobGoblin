import uuid
from collections.abc import Callable
from datetime import UTC, datetime, tzinfo

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Job, User, UserJob
from app.services.user_jobs import set_status
from tests.conftest import real_committed_user_job

_CHANGED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_LATER = datetime(2026, 1, 2, tzinfo=UTC)
_LATEST = datetime(2026, 1, 3, tzinfo=UTC)
_EVEN_LATER = datetime(2026, 1, 4, tzinfo=UTC)
_NAIVE = datetime(2026, 1, 5)  # no tzinfo, deliberately


class _UtcOffsetNoneTzinfo(tzinfo):
    """A `tzinfo` whose `utcoffset()` returns `None`. Per Python's own
    datetime contract, a datetime is aware only when `tzinfo` is not `None`
    **and** `tzinfo.utcoffset(self)` is not `None` — this `tzinfo` leaves
    `.tzinfo` non-`None` while the datetime is still effectively naive, the
    exact gap a bare `changed_at.tzinfo is None` check would miss."""

    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None


_BROKEN_TZ_CHANGED_AT = datetime(2026, 1, 6, tzinfo=_UtcOffsetNoneTzinfo())


async def _insert_user_and_job(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
) -> tuple[uuid.UUID, uuid.UUID]:
    user = make_user(email="user-jobs-service-fixture@example.com")
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


async def _insert_user_job(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
    **user_job_kwargs: object,
) -> UserJob:
    user_id, job_id = await _insert_user_and_job(db_session, make_user, make_job)
    user_job = make_user_job(
        user_id=user_id, job_id=job_id, status_changed_at=_CHANGED_AT, **user_job_kwargs
    )
    db_session.add(user_job)
    await db_session.commit()
    await db_session.refresh(user_job)
    return user_job


# --------------------------------------------------------------------------
# set_status() — first transition into a post-application status
# --------------------------------------------------------------------------


async def test_first_transition_into_post_application_sets_applied_at(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    assert user_job.applied_at is None

    await set_status(db_session, user_job, "applied", changed_at=_LATER)

    assert user_job.status == "applied"
    assert user_job.applied_at == _LATER
    assert user_job.status_changed_at == _LATER


# --------------------------------------------------------------------------
# set_status() — later post-application transitions preserve applied_at
# --------------------------------------------------------------------------


async def test_further_post_application_transitions_preserve_original_applied_at(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job = await _insert_user_job(db_session, make_user, make_job, make_user_job)

    await set_status(db_session, user_job, "recruiter_contacted", changed_at=_LATER)
    first_applied_at = user_job.applied_at
    assert first_applied_at == _LATER

    await set_status(db_session, user_job, "interviewing", changed_at=_LATEST)
    assert user_job.status == "interviewing"
    assert user_job.applied_at == first_applied_at  # unchanged
    assert user_job.status_changed_at == _LATEST

    await set_status(db_session, user_job, "offer", changed_at=_EVEN_LATER)
    assert user_job.status == "offer"
    assert user_job.applied_at == first_applied_at  # still unchanged
    assert user_job.status_changed_at == _EVEN_LATER


# --------------------------------------------------------------------------
# set_status() — backwards transition clears applied_at
# --------------------------------------------------------------------------


async def test_backwards_transition_clears_applied_at(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job = await _insert_user_job(
        db_session,
        make_user,
        make_job,
        make_user_job,
        status="interviewing",
        applied_at=_CHANGED_AT,
    )

    await set_status(db_session, user_job, "interested", changed_at=_LATER)

    assert user_job.status == "interested"
    assert user_job.applied_at is None
    assert user_job.status_changed_at == _LATER


# --------------------------------------------------------------------------
# set_status() — same-status call is a no-op
# --------------------------------------------------------------------------


async def test_same_status_is_noop_preserving_timestamps(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job = await _insert_user_job(
        db_session,
        make_user,
        make_job,
        make_user_job,
        status="applied",
        applied_at=_CHANGED_AT,
    )
    original_applied_at = user_job.applied_at
    original_status_changed_at = user_job.status_changed_at

    await set_status(db_session, user_job, "applied", changed_at=_LATER)

    assert user_job.applied_at == original_applied_at
    assert user_job.status_changed_at == original_status_changed_at


# --------------------------------------------------------------------------
# set_status() — invalid input rejected before any mutation
# --------------------------------------------------------------------------


async def test_invalid_status_rejected_without_mutation(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    original_status = user_job.status
    original_applied_at = user_job.applied_at
    original_status_changed_at = user_job.status_changed_at

    with pytest.raises(ValueError, match="invalid status"):
        await set_status(db_session, user_job, "bogus_status", changed_at=_LATER)

    assert user_job.status == original_status
    assert user_job.applied_at == original_applied_at
    assert user_job.status_changed_at == original_status_changed_at


async def test_naive_changed_at_rejected_without_mutation(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    user_job = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    original_status = user_job.status
    original_applied_at = user_job.applied_at
    original_status_changed_at = user_job.status_changed_at

    with pytest.raises(ValueError, match="timezone-aware"):
        await set_status(db_session, user_job, "applied", changed_at=_NAIVE)

    assert user_job.status == original_status
    assert user_job.applied_at == original_applied_at
    assert user_job.status_changed_at == original_status_changed_at


async def test_changed_at_with_none_utcoffset_rejected_without_mutation(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    """A `tzinfo` whose `utcoffset()` returns `None` leaves `.tzinfo`
    non-`None` — a bare `changed_at.tzinfo is None` check would wrongly
    accept it. `set_status()` must check `utcoffset()` too."""
    user_job = await _insert_user_job(db_session, make_user, make_job, make_user_job)
    original_status = user_job.status
    original_applied_at = user_job.applied_at
    original_status_changed_at = user_job.status_changed_at

    with pytest.raises(ValueError, match="timezone-aware"):
        await set_status(db_session, user_job, "applied", changed_at=_BROKEN_TZ_CHANGED_AT)

    assert user_job.status == original_status
    assert user_job.applied_at == original_applied_at
    assert user_job.status_changed_at == original_status_changed_at


# --------------------------------------------------------------------------
# set_status() — flushes but never commits; caller controls the transaction
# --------------------------------------------------------------------------


async def test_flushes_without_committing_caller_controls_transaction(
    db_engine: AsyncEngine,
) -> None:
    async with real_committed_user_job(
        db_engine, "user-jobs-service-flush@example.com", status_changed_at=_CHANGED_AT
    ) as (session, _user_id, _job_id, user_job_id):
        user_job = await session.get(UserJob, user_job_id)
        assert user_job is not None

        await set_status(session, user_job, "applied", changed_at=_LATER)

        # Flushed: visible within the same still-open transaction.
        same_session_reread = await session.get(UserJob, user_job_id)
        assert same_session_reread is not None
        assert same_session_reread.status == "applied"

        # Not committed: a genuinely separate session/connection must not
        # see the change yet.
        async with AsyncSession(bind=db_engine) as other_session:
            other_view = await other_session.get(UserJob, user_job_id)
            assert other_view is not None
            assert other_view.status == "interested"

        await session.rollback()

        async with AsyncSession(bind=db_engine) as verify_session:
            rolled_back = await verify_session.get(UserJob, user_job_id)
            assert rolled_back is not None
            assert rolled_back.status == "interested"


# --------------------------------------------------------------------------
# The CHECK is the real backstop, even bypassing set_status() entirely
# --------------------------------------------------------------------------


async def test_bypassing_set_status_still_rejected_by_database_check(
    db_session: AsyncSession,
    make_user: Callable[..., User],
    make_job: Callable[..., Job],
    make_user_job: Callable[..., UserJob],
) -> None:
    """ADR 0006's own stated rationale for the `CHECK`: the single-writer
    discipline (`set_status()` is the only function meant to pair these
    two columns) is a code-structure convention, not something the
    database can enforce directly — a future bug that writes `.status`
    directly, bypassing `set_status()`, must still be rejected at commit."""
    user_job = await _insert_user_job(db_session, make_user, make_job, make_user_job)

    user_job.status = "applied"  # bypasses set_status() entirely
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
