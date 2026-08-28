import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base

# Split by who acted (ADR 0006): `not_interested` (user dismissed without
# applying) vs. `rejected_by_employer`/`withdrawn_by_user` are distinct,
# unlike a single ambiguous "rejected"/"withdrawn" value.
STATUSES = (
    "interested",
    "not_interested",
    "applied",
    "recruiter_contacted",
    "screening",
    "interviewing",
    "offer",
    "rejected_by_employer",
    "withdrawn_by_user",
)

# The two statuses that require applied_at IS NULL; the remaining seven
# require applied_at IS NOT NULL. See the CHECK below (ADR 0006).
PRE_APPLICATION_STATUSES = ("interested", "not_interested")
POST_APPLICATION_STATUSES = (
    "applied",
    "recruiter_contacted",
    "screening",
    "interviewing",
    "offer",
    "rejected_by_employer",
    "withdrawn_by_user",
)


class UserJob(Base):
    """Per-(user, job) personal tracking state — save/hide/archive flags
    plus the applied-status workflow (docs/DATA_MODEL.md's `user_jobs`
    section, master spec §36; ADR 0006). Deliberately isolated from source
    data: nothing in `providers/`/`ingestion/` may ever write this table
    (ARCHITECTURE.md §5) — `services/user_jobs.py` is the only writer, and
    within that, `set_status()` is the only function permitted to write
    `status`/`applied_at`/`status_changed_at` together. This Phase 1 slice
    migrates the schema and implements exactly that one service function;
    `saved`/`hidden`/`archived` toggle functions, API routes, derived
    workspace fields, and `job_notes` CRUD are Phase 10 work.

    `user_id`/`job_id` are both NOT NULL, `ON DELETE CASCADE` — a user's
    personal tracking data has no meaning without the user, and a
    tracking row has no meaning without the job it tracks. Not this
    schema's first CASCADE from `users` (`candidate_profiles.user_id`,
    `saved_searches.user_id` already use it) or from a domain aggregate
    (`job_occurrences.job_id`, `collection_run_provider_attempts.
    collection_run_id`, the `saved_search_*` child tables, and
    `candidate_skills.candidate_profile_id` all already use `ON DELETE
    CASCADE`) — only the specific pairing (a user-state table cascading
    from both its user AND its job) is new here.

    `applied_at` is the single source of truth for "has the user
    applied" — there is no separate boolean; application code and the UI
    derive it as `applied_at IS NOT NULL`. `status` is a plain
    `CHECK`-restricted enum (no ORM trim/case transform — a closed
    literal set, not a canonical join-key identifier, matching
    `identity_conflicts.status`/`collection_runs.status`'s treatment), no
    server default: fresh creation must explicitly supply `interested` or
    `not_interested`. A bidirectional `CHECK` (ADR 0006) requires
    `applied_at IS NULL` for the two pre-application statuses and
    `applied_at IS NOT NULL` for every post-application status — a hard
    database invariant, not application-code discipline alone. Backwards
    transitions (e.g. correcting `interviewing` back to `interested`) are
    permitted; this is a personal tracker, not a workflow engine with a
    hard-blocked transition graph — only the NULL-ness pairing is ever
    enforced.

    `status_changed_at` is NOT NULL with **no** server default — a
    business timestamp representing since when the current `status` value
    has held, explicitly supplied at row creation and updated only by
    `set_status()` when `status` actually changes. It is deliberately
    **not** an ORM `onupdate` column like `updated_at` below: `updated_at`
    advances on every write to this row (e.g. toggling `saved`),
    `status_changed_at` must not.

    `saved`/`hidden`/`archived` are independent boolean flags (NOT NULL,
    `server_default false`), orthogonal to `status`/`applied_at` and to
    each other — no `CHECK` relates any of them. `archived` is a terminal
    "declutter" flag layered on top of whatever `status`/`applied_at`
    already hold; archiving never destroys that history.

    `created_at`/`updated_at` follow the established global convention —
    not previously specified in this table's own design note.
    """

    __tablename__ = "user_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        CheckConstraint(
            f"status IN {STATUSES}",
            name="status_valid",
        ),
        CheckConstraint(
            f"(status IN {PRE_APPLICATION_STATUSES} AND applied_at IS NULL) "
            f"OR (status IN {POST_APPLICATION_STATUSES} AND applied_at IS NOT NULL)",
            name="status_applied_at_consistency",
        ),
    )


# PostgreSQL does not automatically index a referencing foreign-key
# column. (user_id, job_id) is covered by the UNIQUE constraint's own
# index (leading column user_id), but job_id has no index of its own —
# this one supports lookups and CASCADE-maintenance beginning with job_id
# (e.g. "does any user track this job" during a Job-related operation).
Index("ix_user_jobs_job_id", UserJob.job_id)
