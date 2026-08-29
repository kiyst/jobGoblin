import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

# Same four-character whitespace set as every other trim-only column in this
# project: space, tab, line feed, carriage return.
_COVERED_WHITESPACE = " \t\n\r"


class JobNote(Base):
    """A single user-authored note attached to a `UserJob` tracking row
    (docs/DATA_MODEL.md's `job_notes` section; master spec §36). This is
    Phase 1's final schema table — see ARCHITECTURE.md §13/ROADMAP.md.
    `services/` remains the only layer ever permitted to write this table
    (ARCHITECTURE.md §5); no CRUD service, API route, or workspace behavior
    is implemented in this slice. This table's Phase 1 consumers are its
    own factory, PostgreSQL constraint tests, and cascade-isolation tests —
    Phase 10 is this table's first production CRUD writer, not the first
    consumer of the schema itself.

    `user_job_id` is NOT NULL, `ON DELETE CASCADE` — a note has no meaning
    without the tracking row it annotates. This table carries no direct
    `user_id` column: ownership is reached and enforced entirely through
    the required `user_job_id` -> `user_jobs.id` foreign key, matching this
    schema's existing precedent for tables one hop from a user-scoped
    parent (`saved_search_titles.saved_search_id`, `candidate_skills.
    candidate_profile_id` — neither carries a redundant `user_id` either).
    Because `user_jobs` itself cascades from both `users.id` and `jobs.id`,
    deleting a `User` or a `Job` cascades two levels deep, through
    `user_jobs`, to this table — the same two-level-CASCADE shape already
    used by `saved_search_titles`/`saved_search_locations` (via
    `saved_searches.user_id`) and `candidate_skills` (via
    `candidate_profiles.user_id`), not a new pattern. What is new here is
    that `user_jobs` has two parent FKs, so `job_notes` is reachable by a
    two-level cascade from *either* `users` or `jobs`, not just one.

    `body` is required, case-preserving free text: NOT NULL, ORM-trimmed
    (the established four-character whitespace set), with a matching
    database `CHECK` pair requiring an already-trimmed, non-empty value.
    Unlike `identity_conflicts.resolution` (optional narrative bolted onto
    an otherwise-complete row), a `job_notes` row's only reason to exist is
    to hold `body` — an empty or whitespace-only note is rejected, not
    collapsed to `NULL`, since there is no `NULL` state for this column at
    all. `body` is arbitrary user-authored content and must never be
    logged verbatim by any future code path (PHASE_RISK_CHECKLIST.md's
    cross-cutting PII/logging non-negotiable) — a documentation note, not
    a database constraint.

    No `UNIQUE` constraint: multiple notes may legitimately exist for the
    same `user_job_id` — a running list of timestamped notes, not one
    edit-in-place field.

    `created_at`/`updated_at` follow the established global convention —
    already specified for this table since Rev 3 (unlike every other table
    this session, there was no table-doc-omission tension to resolve here).
    """

    __tablename__ = "job_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
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
        CheckConstraint(
            r"body = trim(both E'\t\n\r ' from body)",
            name="body_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from body) <> ''",
            name="body_not_empty",
        ),
    )

    @validates("body")
    def _normalize_body(self, _key: str, value: str) -> str:
        """Trim-only, case preserved — required free text, not a canonical
        identifier."""
        return value.strip(_COVERED_WHITESPACE)


# Phase 10's "all notes for this job, most recent first" lookup.
# PostgreSQL does not automatically index a referencing foreign-key column.
Index("ix_job_notes_user_job_id_created_at", JobNote.user_job_id, JobNote.created_at.desc())
