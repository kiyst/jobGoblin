from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_job import PRE_APPLICATION_STATUSES, STATUSES, UserJob


async def set_status(
    session: AsyncSession, user_job: UserJob, new_status: str, *, changed_at: datetime
) -> None:
    """The only function permitted to write `UserJob.status`/`.applied_at`/
    `.status_changed_at` together (ADR 0006). Flushes through `session` so
    the database `CHECK` constraints are evaluated immediately, but never
    commits or rolls back — the caller owns the transaction.

    Raises `ValueError` (without mutating `user_job`) for an unrecognized
    `new_status` or a timezone-unaware `changed_at` — both are caller bugs,
    not data conditions the database should have to reject. Per Python's
    own datetime contract, a datetime is aware only when `tzinfo` is not
    `None` **and** `tzinfo.utcoffset(self)` is not `None` — a `tzinfo`
    subclass whose `utcoffset()` returns `None` still leaves `.tzinfo`
    non-`None`, so checking `.tzinfo is None` alone is not sufficient.

    Same-status calls are a no-op: `applied_at` and `status_changed_at` are
    left untouched. Otherwise: transitioning into a post-application status
    for the first time sets `applied_at = changed_at`; a later transition
    between post-application statuses preserves the original `applied_at`;
    transitioning back to `interested`/`not_interested` clears `applied_at`
    to `None`. `status_changed_at` is set to `changed_at` on every actual
    status change.
    """
    if new_status not in STATUSES:
        raise ValueError(f"invalid status: {new_status!r}")
    if changed_at.tzinfo is None or changed_at.utcoffset() is None:
        raise ValueError("changed_at must be timezone-aware, got a naive datetime")

    if new_status == user_job.status:
        return

    now_pre_application = new_status in PRE_APPLICATION_STATUSES
    was_pre_application = user_job.status in PRE_APPLICATION_STATUSES

    if now_pre_application:
        user_job.applied_at = None
    elif was_pre_application:
        user_job.applied_at = changed_at
    # else: was already post-application, staying post-application —
    # applied_at is preserved untouched.

    user_job.status = new_status
    user_job.status_changed_at = changed_at

    await session.flush()
