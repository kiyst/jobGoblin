import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base

REMOTE_PREFERENCES = ("remote", "hybrid", "onsite", "no_preference")


class CandidateProfile(Base):
    """ "Who is the user professionally" (docs/DATA_MODEL.md §candidate_profiles).

    One-to-one with `users` for now (`user_id` is UNIQUE): kept as its own
    table, not columns on `users`, because it's what a future
    multi-profile/multi-resume feature would key off of.

    The five `text[]` columns are nullable with no server default: NULL means
    the candidate has never specified that field; an empty array would mean
    "explicitly specified as none" — a distinct state this slice does not yet
    populate but that the schema leaves room for (approved product decision,
    2026-08-24; not stated in docs/DATA_MODEL.md's column notes).
    """

    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    target_role_families: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    certifications: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    clearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_industries: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    excluded_industries: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    preferred_locations: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    relocation_willingness: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    remote_preference: Mapped[str] = mapped_column(Text, nullable=False)
    salary_expectation_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_expectation_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
            "remote_preference IN ('remote', 'hybrid', 'onsite', 'no_preference')",
            name="remote_preference_valid",
        ),
        CheckConstraint(
            "years_experience IS NULL OR years_experience >= 0",
            name="years_experience_non_negative",
        ),
        CheckConstraint(
            "salary_expectation_min IS NULL OR salary_expectation_min >= 0",
            name="salary_expectation_min_non_negative",
        ),
        CheckConstraint(
            "salary_expectation_max IS NULL OR salary_expectation_max >= 0",
            name="salary_expectation_max_non_negative",
        ),
        CheckConstraint(
            "salary_expectation_min IS NULL OR salary_expectation_max IS NULL "
            "OR salary_expectation_min <= salary_expectation_max",
            name="salary_expectation_min_le_max",
        ),
    )
